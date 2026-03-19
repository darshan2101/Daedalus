"""
daedalus/local_coordinator.py
Lightweight coordinator scoped to one major agent.
Handles sub-task decomposition and parallel execution of sub-agents.
"""

import asyncio
import uuid
from typing import List, Dict
from rich.console import Console

from daedalus.state import AgentSpec, StepResult, RunState
from daedalus.sub_agent import run_agent_task

console = Console()


class LocalCoordinator:
    """
    Per-major-agent coordinator. Takes a parent spec and spawns sub-agents
    for fragmented sub-tasks, executing them in parallel up to the configured cap.
    """

    def __init__(self, parent_spec: AgentSpec, config: dict, state: RunState):
        self.parent_spec = parent_spec
        self.config = config
        self.state = state
        self.run_id = state["run_id"]
        self.max_parallel_sub = config.get("runtime", {}).get("max_parallel_sub", 3)
        self.max_depth = config.get("runtime", {}).get("max_recursion_depth", 5)

    async def run_sub_tasks(self, sub_tasks: List[Dict]) -> StepResult:
        """
        Execute a list of sub-tasks in parallel and merge their results
        into a single StepResult for the parent agent.

        Args:
            sub_tasks: List of dicts with 'task' and 'specialist' keys
                       (from MajorAgent complexity assessment).

        Returns:
            Merged StepResult combining all sub-agent outputs.
        """
        parent_id = self.parent_spec["agent_id"]
        parent_depth = self.parent_spec.get("depth", 0)
        new_depth = parent_depth + 1

        # Depth guard
        if new_depth >= self.max_depth:
            raise RuntimeError(
                f"Max recursion depth ({self.max_depth}) reached for {parent_id}. "
                f"Cannot create sub-agents at depth {new_depth}."
            )

        # Build sub-agent specs
        sub_specs = self._build_sub_specs(sub_tasks, parent_id, new_depth)

        console.print(
            f"  [dim]LocalCoordinator: {parent_id} → {len(sub_specs)} sub-agents at depth {new_depth}[/]"
        )

        # Execute sub-agents in parallel with semaphore cap
        semaphore = asyncio.Semaphore(self.max_parallel_sub)
        sub_results: List[StepResult] = []

        async def _run_sub(spec: AgentSpec):
            async with semaphore:
                return await run_agent_task(self.run_id, spec, self.config, self.state)

        sub_results = await asyncio.gather(*[_run_sub(s) for s in sub_specs])

        # Merge sub-results into a single parent result
        return self._merge_sub_results(sub_results)

    def _build_sub_specs(
        self, sub_tasks: List[Dict], parent_id: str, depth: int
    ) -> List[AgentSpec]:
        """Convert the LLM's sub_tasks list into proper AgentSpec dicts."""
        specs = []
        for i, st in enumerate(sub_tasks):
            sub_id = f"{parent_id}_s{i:02d}"
            specs.append({
                "agent_id": sub_id,
                "task": st.get("task", ""),
                "output_type": self.parent_spec.get("output_type", "code"),
                "threshold": self.parent_spec.get("threshold", 0.82),
                "dependencies": [],       # sub-agents are parallel within a parent
                "specialist": st.get("specialist", self.parent_spec.get("specialist", "coder")),
                "depth": depth,
                "parent_id": parent_id,
            })
        return specs

    def _merge_sub_results(self, sub_results: List[StepResult]) -> StepResult:
        """
        Merge multiple sub-agent StepResults into a single parent StepResult.
        Strategy: concatenate outputs, average quality scores.
        """
        parent_id = self.parent_spec["agent_id"]

        if not sub_results:
            return {
                "agent_id": parent_id,
                "task": self.parent_spec["task"],
                "result": "",
                "quality_score": 0.0,
                "iterations": 0,
                "status": "failed",
                "error": "No sub-results produced",
            }

        # Concatenate results
        merged_output_parts = []
        total_score = 0.0
        total_iterations = 0
        all_passed = True

        for sr in sub_results:
            sub_id = sr.get("agent_id", "unknown")
            sub_output = sr.get("result", "")
            sub_score = sr.get("quality_score", 0.0)

            merged_output_parts.append(
                f"--- SUB-AGENT: {sub_id} ---\n{sub_output}\n--- END SUB-AGENT ---"
            )
            total_score += sub_score
            total_iterations += sr.get("iterations", 1)

            if sr.get("status") != "done":
                all_passed = False

        avg_score = total_score / len(sub_results) if sub_results else 0.0
        merged_output = "\n\n".join(merged_output_parts)

        return {
            "agent_id": parent_id,
            "task": self.parent_spec["task"],
            "result": merged_output,
            "quality_score": avg_score,
            "iterations": total_iterations,
            "status": "done" if all_passed else "partial",
            "output_path": f"outputs/workspace/{parent_id}",
            "error": None,
        }
