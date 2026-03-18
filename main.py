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
load_dotenv()

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
    goal = " ".join(args.goal).strip() if args.goal else ""
    if not goal:
        goal = input("What do you want to build or solve?\n> ")

    if args.quiet:
        import builtins
        _real_print = builtins.print
        def _quiet_print(*a, **kw):
            text = " ".join(str(x) for x in a)
            if any(text.startswith(p) for p in ("  [trying", "  [success", "  [error", "  [404", "  [429", "  [null")):
                return
            _real_print(*a, **kw)
        builtins.print = _quiet_print

    config = load_config()
    
    if args.threshold is not None:
        for k in config.get("thresholds", {}):
            config["thresholds"][k] = args.threshold
    if args.max_depth is not None:
        config["runtime"]["max_recursion_depth"] = args.max_depth

    # Connect DB
    from infra.mongo_client import get_db
    db = get_db()
    
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    
    now = datetime.datetime.utcnow().isoformat() + "Z"
    await db.runs.insert_one({
        "_id": run_id,
        "goal": goal,
        "preset": args.preset,
        "status": "running",
        "started_at": now,
        "completed_at": None,
        "final_score": None,
        "system_iterations": 0,
        "total_agents": 0,
        "config_snapshot": config
    })

    console.print(Panel.fit(f"[bold cyan]DAEDALUS ORCHESTRATOR[/bold cyan]\n\n[bold]Goal:[/bold] {goal}", border_style="cyan"))

    from daedalus.planner import plan_goal
    
    try:
        plan_output = await plan_goal(goal, args.preset, config)
        console.print(Panel(plan_output["plan"], title="[bold]Plan[/bold]"))
        
        from rich.tree import Tree
        tree = Tree(f"Daedalus Agent DAG ({run_id})")
        
        specs = {s["agent_id"]: s for s in plan_output["agent_specs"]}
        # Calculate waves
        in_degree = {s: 0 for s in specs}
        for u, deps in plan_output.get("dep_graph", {}).items():
            for d in deps:
                in_degree[u] = in_degree.get(u, 0) + 1
                
        waves = []
        queue = [s for s in specs if in_degree[s] == 0]
        while queue:
            waves.append(queue)
            next_queue = []
            for u in queue:
                for v, deps in plan_output.get("dep_graph", {}).items():
                    if u in deps:
                        in_degree[v] -= 1
                        if in_degree[v] == 0:
                            next_queue.append(v)
            queue = next_queue
            
        for i, wave in enumerate(waves):
            wave_node = tree.add(f"Wave {i}")
            for a in wave:
                wave_node.add(f"[bold]{a}[/bold] ({specs[a]['specialist']}) -> {specs[a]['task']}")
                
        console.print(tree)
        
        # update the db
        await db.runs.update_one(
            {"_id": run_id},
            {"$set": {"total_agents": len(specs), "plan": plan_output["plan"]}}
        )
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        await db.runs.update_one({"_id": run_id}, {"$set": {"status": "failed"}})

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()