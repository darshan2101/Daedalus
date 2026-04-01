"""
daedalus/reporter.py
Generates Markdown and JSON reports for a given run by extracting state from MongoDB.
"""

import json
import os
from datetime import datetime
import asyncio
from dotenv import load_dotenv

load_dotenv(override=True)

from rich.console import Console
from infra.mongo_client import get_run

console = Console()

async def generate_report(run_id: str, output_dir: str = "outputs/reports"):
    """
    Fetch the run_id from MongoDB, and write a JSON and Markdown report.
    Returns the paths to the generated reports.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    run_doc = await get_run(run_id)
    if not run_doc:
        console.print(f"[bold red]Error: Run {run_id} not found in MongoDB![/]")
        return None, None
        
    state = run_doc

    goal = state.get("goal", "Unknown")
    preset = state.get("preset", "Unknown")
    
    # 5-dimensional scores if present, fallback to system_score
    score = state.get("system_score", 0.0)
    dimensions = state.get("dimensions", {})
    breakdown = state.get("breakdown", "No breakdown available")
    
    iterations = state.get("system_iteration", 0)
    repair_attempts = state.get("repair_attempts", 0)
    
    weakest_agents = state.get("weakest_agents", [])
    broken_interfaces = state.get("broken_interfaces", [])
    errors = state.get("errors", [])
    
    agents = state.get("agent_specs", [])
    
    # Build JSON Report
    json_report = {
        "run_id": run_id,
        "timestamp": datetime.utcnow().isoformat(),
        "status": run_doc.get("status", "unknown"),
        "goal": goal,
        "preset": preset,
        "execution": {
            "iterations": iterations,
            "repair_attempts": repair_attempts,
            "agents_spawned": len(agents),
        },
        "evaluation": {
            "system_score": score,
            "dimensions": dimensions,
            "breakdown": breakdown,
            "weakest_agents_history": weakest_agents,
            "broken_interfaces_history": broken_interfaces,
            "errors": errors,
        }
    }
    
    json_path = os.path.join(output_dir, f"{run_id}_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_report, f, indent=4)
        
    # Build Markdown Report
    md_lines = [
        f"# Daedalus Run Report: `{run_id}`",
        f"**Date (UTC)**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Status**: {run_doc.get('status', 'unknown').upper()}",
        f"**Preset**: `{preset}`",
        "",
        "## Goal",
        f"> {goal}",
        "",
        "## Evaluation & Scores",
        f"**System Score**: `{score:.2f}`",
        "",
        "**Dimensions**:"
    ]
    
    if dimensions:
        for dim, val in dimensions.items():
            md_lines.append(f"- **{dim.capitalize()}**: {val}")
    else:
        md_lines.append("- N/A")
        
    md_lines.extend([
        "",
        "**Breakdown**:",
        f"{breakdown}",
        "",
        "## Execution Metrics",
        f"- **Agents Spawned**: {len(agents)}",
        f"- **Total System Iterations**: {iterations}",
        f"- **Repair Attempts Triggered**: {repair_attempts}",
        ""
    ])
    
    if weakest_agents:
        md_lines.append(f"**Weakest Agents Identified (Last Evaluation)**: {', '.join(weakest_agents)}\n")
    if broken_interfaces:
        md_lines.append(f"**Broken Interfaces Repaired**: {len(broken_interfaces)}\n")
    if errors:
        md_lines.append("## Errors Recorded")
        for err in errors:
            md_lines.append(f"- {err}")
            
    md_path = os.path.join(output_dir, f"{run_id}_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
        
    console.print(f"[bold green]Success: Generated Reports for {run_id}[/]")
    console.print(f"  JSON: {json_path}")
    console.print(f"  Markdown: {md_path}")
    
    return json_path, md_path

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        run_id = sys.argv[1]
        asyncio.run(generate_report(run_id))
    else:
        print("Usage: python -m daedalus.reporter <run_id>")
