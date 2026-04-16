import sys
import asyncio

# Windows ProactorEventLoop fix — must be set before any asyncio usage
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

import nest_asyncio
nest_asyncio.apply()

import os
import datetime
import uuid
import yaml
import argparse
from dotenv import load_dotenv
load_dotenv(override=True)

from rich.console import Console
from rich.panel import Panel

console = Console()

def parse_args():
    parser = argparse.ArgumentParser(description="Daedalus Orchestrator")
    parser.add_argument("goal",          nargs="*",        help="Goal for Daedalus to accomplish")
    parser.add_argument("--preset",      default="default", choices=["saas","docs","research","default"])
    parser.add_argument("--plan-review", action="store_true", help="Human approval gate after planning")
    parser.add_argument("--resume",      metavar="RUN_ID",  help="Resume from checkpoint")
    parser.add_argument("--threshold",   type=float,        help="Override all thresholds globally")
    parser.add_argument("--max-depth",   type=int,          help="Override max recursion depth")
    parser.add_argument("--quiet",       action="store_true")
    parser.add_argument("--verbose",     action="store_true")
    return parser.parse_args()

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

async def main_async():
    args = parse_args()
    config = load_config()
    
    # Global overrides
    if args.threshold is not None:
        for k in config.get("thresholds", {}):
            config["thresholds"][k] = args.threshold
    if args.max_depth is not None:
        config["runtime"]["max_recursion_depth"] = args.max_depth

    if args.quiet:
        import builtins
        _real_print = builtins.print
        def _quiet_print(*a, **kw):
            text = " ".join(str(x) for x in a)
            if any(text.startswith(p) for p in ("  [trying", "  [success", "  [error", "  [404", "  [429", "  [null")):
                return
            _real_print(*a, **kw)
        builtins.print = _quiet_print

    from infra.mongo_client import get_db, update_run_status
    db = get_db()
    
    run_state = None
    run_id = None
    
    # ── 1. Resume or Start New ─────────────────────────────────────────────
    if args.resume:
        run_id = args.resume
        run_state = await db.runs.find_one({"run_id": run_id})
        if not run_state:
            # Fallback to _id if legacy
            run_state = await db.runs.find_one({"_id": run_id})
        
        if not run_state:
            console.print(f"[bold red]Error: Run {run_id} not found.[/] Check MongoDB 'runs' collection.")
            return

        # Fix 3: Restore agent_results from checkpoints collection during resume
        from infra.mongo_client import get_checkpoints
        from infra.redis_client import freeze_agent
        checkpoints = await get_checkpoints(run_id)
        restored_results = {}
        for cp in checkpoints:
            aid = cp.get("agent_id")
            if aid:
                status = cp.get("status", "done")
                restored_results[aid] = {
                    "agent_id": aid,
                    "task": cp.get("task", ""),
                    "result": cp.get("result", ""),
                    "quality_score": cp.get("score", cp.get("quality_score", 0.0)),
                    "iterations": cp.get("iterations", 1),
                    "status": status,
                    "error": cp.get("error"),
                }
                if status == "done":
                    freeze_agent(run_id, aid)
        run_state["agent_results"] = restored_results
        
        # C1: Fresh budget for this resume session
        run_state["repair_attempts"] = 0
        run_state["system_iteration"] = 0
        
        console.print(f"[bold blue]Resuming existing run: {run_id}[/]")
        if restored_results:
             console.print(f"  [dim]Restored {len(restored_results)} agent results from checkpoints.[/]")
    else:
        goal = " ".join(args.goal).strip() if args.goal else ""
        if not goal:
            goal = input("What do you want to build or solve?\n> ")
            
        console.print(Panel.fit(f"[bold cyan]DAEDALUS ORCHESTRATOR[/bold cyan]\n\n[bold]Goal:[/bold] {goal}", border_style="cyan"))
        
        # Phase 1: Planning
        from daedalus.planner import plan_goal
        try:
            console.print(f"\n[bold yellow]Phase 1: Strategic Planning[/]")
            plan_result = await plan_goal(goal, args.preset, config)
            
            run_id = f"run_{uuid.uuid4().hex[:8]}"
            run_state = {
                "run_id": run_id,
                "goal": goal,
                "preset": args.preset,
                "plan": plan_result["plan"],
                "agent_specs": plan_result["agent_specs"],
                "dep_graph": plan_result["dep_graph"],
                "output_type": plan_result.get("output_type", "code"),
                "agent_results": {},
                "frozen_agents": [],
                "combined_result": "",
                "combined_score": 0.0,
                "broken_interfaces": [],
                "system_iteration": 0,
                "repair_attempts": 0,
                "current_step": "coordinator",
                "errors": []
            }
            
            await update_run_status(run_id, "running", run_state)
            
            # Show the plan
            console.print(Panel(run_state["plan"], title="[bold]Strategy[/bold]"))
            _print_dag_tree(run_state)
            
        except Exception as e:
            console.print(f"[bold red]Planning failed: {e}[/bold red]")
            return

    # ── 2. Execution: LangGraph or Inline Fallback ──────────────────────────
    use_langgraph = config.get("runtime", {}).get("use_langgraph", True)
    
    if use_langgraph:
        console.print(f"\n[bold yellow]Phase 2: LangGraph Orchestration[/]")
        try:
            # Fix 1: We already did plan_goal in main.py. Skip the plan_node entirely.
            from daedalus.graph import build_resume_graph
            graph = build_resume_graph(config)

            # Build the graph input state
            graph_state = {
                "run_id": run_id,
                "goal": run_state.get("goal", ""),
                "preset": run_state.get("preset", "default"),
                "config": config,
                "plan": run_state.get("plan", ""),
                "agent_specs": run_state.get("agent_specs", []),
                "dep_graph": run_state.get("dep_graph", {}),
                "output_type": run_state.get("output_type", "code"),
                "agent_results": run_state.get("agent_results", {}),
                "frozen_agents": run_state.get("frozen_agents", []),
                "combined_result": "",
                "combined_score": 0.0,
                # N3 Fix: preserve existing score on resume; use -1.0 sentinel for fresh runs
                "system_score": run_state.get("system_score", -1.0) if args.resume else -1.0,
                "breakdown": run_state.get("breakdown", "") if args.resume else "",
                "weakest_agents": [],
                "broken_interfaces": [],
                "system_iteration": run_state.get("system_iteration", 0),
                "repair_attempts": run_state.get("repair_attempts", 0),
                "any_agent_ran": True,
                "current_step": "executing",
                "errors": [],
                "should_repair": False,
                "done": False,
            }

            final_state = await graph.ainvoke(
                graph_state,
                config={"recursion_limit": 100}
            )
            from infra.mongo_client import update_run_status
            await update_run_status(run_id, "done", final_state)
            
            from daedalus.assembler import parse_and_zip
            zip_path = parse_and_zip(run_id, final_state)
            
            console.print(f"\n[bold green]✅ Daedalus Run {run_id} completed via LangGraph.[/]")
            raw_score = final_state.get('system_score', -1.0)
            score = raw_score if raw_score >= 0 else 0.0  # N3 Fix: don't clamp preserved sentinel
            console.print(f"System score: {score:.2f}")
            console.print(f"Build Package: {zip_path}")

        except Exception as e:
            console.print(f"[bold red]LangGraph execution failed: {e}[/bold red]")
            console.print(f"[yellow]Falling back to inline coordinator...[/]")
            
            # Fix 2: Reload run_state from MongoDB before fallback to have latest results/iterations
            try:
                saved = await db.runs.find_one({"_id": run_id})
                if saved:
                    # Update run_state with latest data from DB
                    for k in ("agent_results", "frozen_agents", "system_iteration", "repair_attempts"):
                        if k in saved:
                            run_state[k] = saved[k]
                
                # Also reload agent_results from checkpoints to be 100% sure
                from infra.mongo_client import get_checkpoints
                checkpoints = await get_checkpoints(run_id)
                for cp in checkpoints:
                    aid = cp.get("agent_id")
                    if aid:
                        run_state["agent_results"][aid] = {
                            "agent_id": aid,
                            "task": cp.get("task", ""),
                            "result": cp.get("result", ""),
                            "quality_score": cp.get("score", cp.get("quality_score", 0.0)),
                            "iterations": cp.get("iterations", 1),
                            "status": cp.get("status", "done"),
                            "error": cp.get("error"),
                        }
            except Exception as reload_err:
                console.print(f"[dim red]Warning: Failed to reload state before fallback: {reload_err}[/]")

            # Auto-fallback to inline flow
            from daedalus.coordinator import GlobalCoordinator
            try:
                coordinator = GlobalCoordinator(run_state, config)
                await coordinator.run()
                
                from daedalus.assembler import parse_and_zip
                zip_path = parse_and_zip(run_id, run_state)
                
                console.print(f"\n[bold green]✅ Run {run_id} completed (inline fallback).[/]")
                console.print(f"Build Package: {zip_path}")
            except Exception as e2:
                console.print(f"[bold red]Inline coordinator also failed: {e2}[/bold red]")
                if run_id:
                    await update_run_status(run_id, "failed", {"errors": [str(e), str(e2)]})
    else:
        # Inline fallback — proven flow
        console.print(f"\n[bold yellow]Phase 2: Global Coordination & Execution (inline)[/]")
        from daedalus.coordinator import GlobalCoordinator
        try:
            coordinator = GlobalCoordinator(run_state, config)
            await coordinator.run()
            console.print(f"\n[bold green]✅ Daedalus Run {run_id} finished execution.[/]")
            console.print(f"Results saved to MongoDB and outputs/workspace/")
        except Exception as e:
            console.print(f"[bold red]Coordination failed: {e}[/bold red]")
            if run_id:
                await update_run_status(run_id, "failed", {"errors": [str(e)]})

def _print_dag_tree(state: dict):
    from rich.tree import Tree
    from daedalus.coordinator import GlobalCoordinator
    
    tree = Tree(f"Daedalus Agent DAG ({state['run_id']})")
    # Borrow logic from Coordinator to show waves in UI
    coord = GlobalCoordinator(state, {})
    waves = coord.get_execution_waves()
    
    for i, wave in enumerate(waves):
        w_node = tree.add(f"Wave {i}")
        for agent in wave:
            w_node.add(f"[bold]{agent['agent_id']}[/bold] ({agent['specialist']}) -> {agent['task'][:60]}...")
    console.print(tree)

def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        console.print("\n[bold red]Interrupted by user. Exiting...[/]")
        sys.exit(0)

if __name__ == "__main__":
    main()