"""
daedalus/graph.py
Formal LangGraph state machine for the Daedalus orchestrator.
Defines the plan → execute → merge → evaluate → repair → assemble routing.

If config.runtime.use_langgraph is false, main.py falls back to the inline
GlobalCoordinator flow instead of using this module.
"""

import asyncio
from typing import Annotated, TypedDict, Literal
from rich.console import Console

from langgraph.graph import StateGraph, END

console = Console()


# ── Graph State ───────────────────────────────────────────────────────────────

class DaedalusGraphState(TypedDict, total=False):
    """State passed through the LangGraph state machine."""
    # Identity
    run_id:            str
    goal:              str
    preset:            str
    config:            dict

    # Planner output
    plan:              str
    agent_specs:       list
    dep_graph:         dict
    output_type:       str

    # Execution
    agent_results:     dict
    frozen_agents:     list
    combined_result:   str
    combined_score:    float
    output_path:       str

    # Evaluator
    system_score:      float
    breakdown:         str
    weakest_agents:    list
    broken_interfaces: list

    # Control
    system_iteration:  int
    repair_attempts:   int
    current_step:      str
    errors:            list
    should_repair:     bool
    done:              bool


# ── Node Functions ────────────────────────────────────────────────────────────

async def plan_node(state: DaedalusGraphState) -> DaedalusGraphState:
    """Phase 1: Decompose the goal into an agent DAG."""
    console.print("\n[bold yellow]Phase 1: Strategic Planning[/]")
    from daedalus.planner import plan_goal

    config = state["config"]
    result = await plan_goal(state["goal"], state["preset"], config)

    return {
        **state,
        "plan": result["plan"],
        "agent_specs": result["agent_specs"],
        "dep_graph": result["dep_graph"],
        "output_type": result.get("output_type", "code"),
        "current_step": "executing",
    }


async def execute_node(state: DaedalusGraphState) -> DaedalusGraphState:
    """Phase 2: Execute all agents in topological waves."""
    console.print(f"\n[bold yellow]Phase 2: DAG Execution (iteration {state.get('system_iteration', 0)})[/]")
    from daedalus.coordinator import GlobalCoordinator

    # Build a RunState-compatible dict for the coordinator
    run_state = {
        "run_id": state["run_id"],
        "goal": state["goal"],
        "preset": state["preset"],
        "plan": state.get("plan", ""),
        "agent_specs": state.get("agent_specs", []),
        "dep_graph": state.get("dep_graph", {}),
        "output_type": state.get("output_type", "code"),
        "agent_results": state.get("agent_results", {}),
        "frozen_agents": state.get("frozen_agents", []),
        "combined_result": state.get("combined_result", ""),
        "combined_score": state.get("combined_score", 0.0),
        "broken_interfaces": state.get("broken_interfaces", []),
        "system_iteration": state.get("system_iteration", 0),
        "repair_attempts": state.get("repair_attempts", 0),
        "current_step": "executing",
        "errors": state.get("errors", []),
    }

    config = state["config"]
    coordinator = GlobalCoordinator(run_state, config)

    # Execute waves only (not the full coordinator loop — graph handles routing)
    waves = coordinator.get_execution_waves()
    from infra.redis_client import is_frozen, freeze_agent
    from infra.mongo_client import update_run_status

    for i, wave in enumerate(waves):
        console.print(f"[bold cyan]🌊 Wave {i} ({len(wave)} agents)[/]")
        semaphore = asyncio.Semaphore(config.get("runtime", {}).get("max_parallel_major", 3))

        async def _run_with_sem(agent):
            async with semaphore:
                if is_frozen(state["run_id"], agent["agent_id"]):
                    console.print(f"  [dim grey]Skipping frozen: {agent['agent_id']}[/]")
                    return
                from daedalus.major_agent import MajorAgent
                major = MajorAgent(agent, config, run_state)
                result = await major.run()
                run_state["agent_results"][agent["agent_id"]] = result
                if result.get("quality_score", 0.0) >= agent.get("threshold", 0.0):
                    freeze_agent(state["run_id"], agent["agent_id"])

        await asyncio.gather(*[_run_with_sem(a) for a in wave])
        await update_run_status(state["run_id"], "running", run_state)
        console.print(f"[dim grey italic]  Wave {i} complete.[/]\n")

    console.print("[bold green]✅ All waves finished execution.[/]")

    return {
        **state,
        "agent_results": run_state["agent_results"],
        "frozen_agents": run_state.get("frozen_agents", []),
        "current_step": "merging",
    }


async def merge_node(state: DaedalusGraphState) -> DaedalusGraphState:
    """Phase 2b: Detect and resolve cross-agent interface conflicts."""
    console.print("\n[bold yellow]🔍 Checking for interface conflicts...[/]")
    from daedalus.merger import detect_and_resolve_all

    broken, updated_results = await detect_and_resolve_all(
        state.get("agent_results", {}),
        state.get("dep_graph", {}),
        state["run_id"],
    )

    return {
        **state,
        "agent_results": updated_results,
        "broken_interfaces": broken,
        "current_step": "aggregating",
    }


async def aggregate_node(state: DaedalusGraphState) -> DaedalusGraphState:
    """Phase 3: Aggregate all agent outputs into a combined deliverable."""
    console.print("\n[bold magenta]📦 Aggregating outputs...[/]")
    from daedalus.aggregator import aggregate

    # Build temporary RunState for aggregator
    run_state = dict(state)
    run_state = aggregate(state["run_id"], run_state, state["config"])

    out_path = run_state.get("output_path", "unknown")
    console.print(f"[bold green]✅ Aggregation complete → {out_path}[/]")

    return {
        **state,
        "combined_result": run_state.get("combined_result", ""),
        "output_path": run_state.get("output_path", ""),
        "current_step": "evaluating",
    }


async def evaluate_node(state: DaedalusGraphState) -> DaedalusGraphState:
    """Phase 4: System-level holistic evaluation."""
    console.print("\n[bold yellow]Phase 4: System Evaluation[/]")
    from daedalus.evaluator import evaluate_run

    run_state = dict(state)
    run_state = evaluate_run(state["run_id"], run_state, state["config"])

    return {
        **state,
        "system_score": run_state.get("system_score", 0.0),
        "breakdown": run_state.get("breakdown", ""),
        "weakest_agents": run_state.get("weakest_agents", []),
        "current_step": "repair_check",
    }


async def repair_node(state: DaedalusGraphState) -> DaedalusGraphState:
    """Phase 5: Repair Engine — unfreeze weakest agents for re-run."""
    console.print("\n[bold red]🔧 Repair Engine triggered[/]")
    from daedalus.repair import repair_if_needed

    run_state = dict(state)
    needs_repair, run_state = repair_if_needed(state["run_id"], run_state, state["config"])

    return {
        **state,
        "frozen_agents": run_state.get("frozen_agents", []),
        "system_iteration": run_state.get("system_iteration", 0),
        "repair_attempts": run_state.get("repair_attempts", 0),
        "should_repair": needs_repair,
        "current_step": "executing" if needs_repair else "done",
    }


# ── Routing Functions ─────────────────────────────────────────────────────────

def route_after_eval(state: DaedalusGraphState) -> str:
    """After evaluation: assemble if passing, repair if failing."""
    config = state.get("config", {})
    threshold = config.get("thresholds", {}).get("system", 0.85)
    score = state.get("system_score", 0.0)

    if score >= threshold:
        console.print(f"[green]System score {score:.2f} ≥ {threshold} → PASS[/]")
        return "done"
    else:
        max_attempts = config.get("runtime", {}).get("max_repair_attempts", 3)
        attempts = state.get("repair_attempts", 0)
        if attempts >= max_attempts:
            console.print(f"[red]Max repair attempts ({max_attempts}) exhausted → finishing[/]")
            return "done"
        console.print(f"[yellow]System score {score:.2f} < {threshold} → REPAIR[/]")
        return "repair"


def route_after_repair(state: DaedalusGraphState) -> str:
    """After repair: loop back to execute if repairs were made."""
    if state.get("should_repair", False):
        return "execute"
    return "done"


# ── Graph Builder ─────────────────────────────────────────────────────────────

def build_daedalus_graph(config: dict) -> StateGraph:
    """
    Build and compile the Daedalus LangGraph state machine.

    Flow:
      plan → execute → merge → aggregate → evaluate
                                              ↓
                                     pass → END
                                     fail → repair → execute (loop)
    """
    graph = StateGraph(DaedalusGraphState)

    # Add nodes
    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_node)
    graph.add_node("merge", merge_node)
    graph.add_node("aggregate", aggregate_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("repair", repair_node)

    # Set entry point
    graph.set_entry_point("plan")

    # Linear edges
    graph.add_edge("plan", "execute")
    graph.add_edge("execute", "merge")
    graph.add_edge("merge", "aggregate")
    graph.add_edge("aggregate", "evaluate")

    # Conditional edges
    graph.add_conditional_edges("evaluate", route_after_eval, {
        "done": END,
        "repair": "repair",
    })
    graph.add_conditional_edges("repair", route_after_repair, {
        "execute": "execute",
        "done": END,
    })

    return graph.compile()


def build_resume_graph(config: dict) -> StateGraph:
    """
    Build a graph for --resume runs that skip the planning phase.
    Entry point is 'execute' directly.
    """
    graph = StateGraph(DaedalusGraphState)

    graph.add_node("execute", execute_node)
    graph.add_node("merge", merge_node)
    graph.add_node("aggregate", aggregate_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("repair", repair_node)

    graph.set_entry_point("execute")

    graph.add_edge("execute", "merge")
    graph.add_edge("merge", "aggregate")
    graph.add_edge("aggregate", "evaluate")

    graph.add_conditional_edges("evaluate", route_after_eval, {
        "done": END,
        "repair": "repair",
    })
    graph.add_conditional_edges("repair", route_after_repair, {
        "execute": "execute",
        "done": END,
    })

    return graph.compile()
