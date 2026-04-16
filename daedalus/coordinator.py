"""
daedalus/coordinator.py
The Global Coordinator — manages DAG execution and parallel waves.
"""

import asyncio
from typing import List, Dict, Set
from rich.console import Console

from daedalus.state import RunState, AgentSpec, StepResult
from infra.mongo_client import update_run_status
from infra.redis_client import is_frozen, freeze_agent
from daedalus.sub_agent import run_agent_task


console = Console()

class GlobalCoordinator:
    def __init__(self, run_state: RunState, config: dict):
        self.state = run_state
        self.config = config
        self.run_id = run_state["run_id"]
        # Cap for parallel major agents from config
        self.max_parallel = config.get("runtime", {}).get("max_parallel_major", 3)

    def get_execution_waves(self) -> List[List[AgentSpec]]:
        """
        Produce a list of 'waves' (parallel batches) using Kahn's algorithm logic.
        Each wave contains agents whose dependencies are fully met by previous waves.
        """
        waves = []
        specs = {s["agent_id"]: s for s in self.state.get("agent_specs", [])}
        graph = self.state.get("dep_graph", {})
        
        # Calculate initial in-degrees
        in_degree = {aid: 0 for aid in specs}
        for aid, deps in graph.items():
            # aid depends on items in deps
            for dep in deps:
                in_degree[aid] += 1
        
        processed = set()
        while len(processed) < len(specs):
            # Find all nodes with in-degree 0 that haven't been processed
            current_wave_ids = [
                aid for aid, deg in in_degree.items() 
                if deg == 0 and aid not in processed
            ]
            
            if not current_wave_ids:
                # Should not happen if DAG is valid
                break
                
            current_wave = [specs[aid] for aid in current_wave_ids]
            waves.append(current_wave)
            
            for agent in current_wave:
                aid = agent["agent_id"]
                processed.add(aid)
                # 'Remove' edges: find who had 'aid' as a dependency
                # Note: our dep_graph encodes {"child": ["parent1", "parent2"]}
                # So we look for child nodes where 'aid' was in their deps.
                for child_id, deps in graph.items():
                    if aid in deps:
                        in_degree[child_id] -= 1
                        
        return waves

    async def run(self):
        """Main execution loop: Wave by Wave."""
        waves = self.get_execution_waves()
        if not waves:
            console.print("[yellow]Empty plan, nothing to execute.[/]")
            return

        from daedalus.repair import repair_if_needed
        
        while True:
            console.print(f"\n[bold blue]Starting Execution Engine (Run: {self.run_id})[/]")
            console.print(f"Total Waves: {len(waves)}\n")

            for i, wave in enumerate(waves):
                console.print(f"[bold cyan]🌊 Wave {i} ({len(wave)} agents)[/]")
                
                # Execute all agents in the wave (up to max_parallel cap)
                semaphore = asyncio.Semaphore(self.max_parallel)
                
                async def _run_with_sem(agent: AgentSpec):
                    async with semaphore:
                        # Skip if already marked frozen (success from prior run)
                        if is_frozen(self.run_id, agent["agent_id"]):
                            console.print(f"  [dim grey]Skipping frozen agent: {agent['agent_id']} (Cached)[/]")
                            return
                        
                        if agent.get("output_type") == "modular":
                            from daedalus.component_generator import ComponentGenerator
                            console.print(f"  [bold green]🛠️ Delegating {agent['agent_id']} to Modular Generation Engine[/]")
                            from kimiflow.agents import drafter_execute, coder_execute, evaluator_score
                            from daedalus.test_validator import TestValidator
                            
                            validator = TestValidator()
                            
                            async def async_drafter(*args, **kwargs):
                                return await asyncio.to_thread(drafter_execute, *args, **kwargs)
                                
                            async def async_coder(*args, **kwargs):
                                return await asyncio.to_thread(coder_execute, *args, **kwargs)
                                
                            async def async_evaluator(*args, **kwargs):
                                return await asyncio.to_thread(evaluator_score, *args, **kwargs)
        
                            async def async_fast(tests_code, impl_code):
                                return await validator.validate_module(".", tests_code, impl_code)

                            generator = ComponentGenerator(
                                config=self.config,
                                drafter_fn=async_drafter,
                                coder_fn=async_coder,
                                fast_fn=async_fast,
                                evaluator_fn=async_evaluator
                            )
                            
                            result = await generator.generate_module(agent)
                            if "quality_score" not in result:
                                result["quality_score"] = result.get("score", 0.0)
                        else:
                            # Call MajorAgent — it decides direct vs fragment
                            from daedalus.major_agent import MajorAgent
                            major = MajorAgent(agent, self.config, self.state)
                            result = await major.run()
                        
                        if "agent_results" not in self.state:
                            self.state["agent_results"] = {}
                            
                        if result.get("status") != "error":
                            self.state["agent_results"][agent["agent_id"]] = result

                            # Centralized threshold resolution
                            agent_threshold = agent.get("threshold") or self.config.get("thresholds", {}).get(
                                agent.get("output_type", "default"),
                                self.config.get("thresholds", {}).get("default", 0.82)
                            )
                            
                            if result.get("quality_score", 0.0) >= agent_threshold:
                                freeze_agent(self.run_id, agent["agent_id"])
                        else:
                            console.print(f"  [yellow]⚠ {agent['agent_id']} errored — preserving previous output[/]")
                            if agent["agent_id"] not in self.state["agent_results"]:
                                self.state["agent_results"][agent["agent_id"]] = result

                tasks = []
                delay = self.config.get("runtime", {}).get("wave_delay_seconds", 0)
                for index, agent in enumerate(wave):
                    if delay > 0 and index > 0:
                        await asyncio.sleep(delay)
                    tasks.append(asyncio.create_task(_run_with_sem(agent)))
                
                await asyncio.gather(*tasks)
                
                await update_run_status(self.run_id, "running", self.state)
                console.print(f"[dim grey italic]  Wave {i} complete. Checkpoint saved.[/]\n")

            console.print("[bold green]✅ All waves finished execution.[/]")

            # ── Merger: detect and resolve cross-agent interface conflicts ──
            console.print("\n[bold yellow]🔍 Checking for interface conflicts...[/]")
            from daedalus.merger import detect_and_resolve_all
            broken, self.state["agent_results"] = await detect_and_resolve_all(
                self.state.get("agent_results", {}),
                self.state.get("dep_graph", {}),
                self.run_id,
                system_iteration=self.state.get("system_iteration", 0),
                config=self.config
            )
            self.state["broken_interfaces"] = broken
            
            console.print("\n[bold magenta]📦 Aggregating outputs...[/]")
            from daedalus.aggregator import aggregate
            self.state = aggregate(self.run_id, self.state, self.config)
            
            out_path = self.state.get("output_path", "unknown")
            console.print(f"[bold green]✅ Aggregation complete. Output written to:[/] [white]{out_path}[/]")

            self.state["current_step"] = "evaluator"
            await update_run_status(self.run_id, "running", self.state)

            from daedalus.evaluator import evaluate_run
            self.state = evaluate_run(self.run_id, self.state, self.config)

            # Phase C: Repair Engine
            needs_repair, self.state = repair_if_needed(self.run_id, self.state, self.config)
            if not needs_repair:
                break
                
            self.state["current_step"] = "repairing"
            await update_run_status(self.run_id, "running", self.state)

        # Mark done
        self.state["current_step"] = "done"
        await update_run_status(self.run_id, "done", self.state)
