"""
daedalus/sub_agent.py
The Bridge — maps Daedalus AgentSpecs to KimiFlow pipeline execution.
"""

import asyncio
import os
import time
from rich.console import Console
from typing import Dict, Any

from kimiflow.pipeline import pipeline
from daedalus.state import AgentSpec, StepResult, RunState
from infra.mongo_client import insert_checkpoint, log_decision
from infra.workspace import write_agent_output

console = Console()

async def run_agent_task(run_id: str, agent: AgentSpec, config: dict, state: RunState) -> StepResult:
    """
    Execute a single agent task using the KimiFlow leaf layer.
    """
    aid = agent["agent_id"]
    task = agent["task"]
    role = agent["specialist"]
    
    console.print(f"  [bold yellow]▶ {aid}[/bold yellow] ({role}) -> {task[:60]}...")
    
    # ── Gather dependency results for context ──────────────────────────
    # If the agent has dependencies, we pass their outputs into the prompt
    context_outputs = []
    dep_ids = agent.get("dependencies", [])
    agent_results = state.get("agent_results", {})
    
    for dep_id in dep_ids:
        if dep_id in agent_results:
            res = agent_results[dep_id]
            context_outputs.append(f"Output from dependency {dep_id}:\n{res.get('result', '')}")

    full_task = task
    if context_outputs:
        full_task = "\n\n".join(context_outputs) + f"\n\nYOUR TASK:\n{task}"

    # ── Execute KimiFlow Pipeline ─────────────────────────────────────
    # We use asyncio.to_thread because KimiFlow is primarily sync-blocked by HTTP
    def _do_kimi_work():
        # Max retries from config determines LangGraph recursion limit
        max_retries = config.get("runtime", {}).get("max_module_iterations", 1)
        
        initial_state = {
            "task": full_task,
            "plan": "",
            "assigned_model": role, # KimiFlow plan_node might override this, which is fine
            "result": "",
            "quality_score": 0.0,
            "feedback": "",
            "iterations": 0
        }
        
        # Call KimiFlow pipeline using LangGraph API
        return pipeline.invoke(
            initial_state, 
            {"recursion_limit": max(3, max_retries * 3)}
        )

    loop = asyncio.get_event_loop()
    start_time = time.time()
    
    try:
        # Run KimiFlow in thread to avoid blocking the Proactor event loop
        result = await loop.run_in_executor(None, _do_kimi_work)
        duration = time.time() - start_time
        
        import datetime
        now = datetime.datetime.utcnow().isoformat() + "Z"
        
        quality = result.get("quality_score", 0.0)
        status = "done" if quality >= agent.get("threshold", 0.0) else "failed"
        
        step_result: StepResult = {
            "agent_id": aid,
            "task": task,
            "depth": agent.get("depth", 0),
            "timestamp": now,
            "status": status,
            "result": result.get("result", ""),
            "quality_score": quality,
            "feedback": result.get("feedback", ""),
            "iterations": result.get("iterations", 1),
            "output_path": f"outputs/workspace/{aid}",
            "error": None
        }
        
        # ── Output Persistence ──────────────────────────────────────────
        # 1. Write to local file
        write_agent_output(run_id, aid, step_result["result"])
        
        # 2. Write to MongoDB checkpoints
        await insert_checkpoint(run_id, aid, step_result)
        
        # 3. Log decision
        await log_decision(run_id, aid, {
            "decision": "freeze" if status == "done" else "retry",
            "depth": agent.get("depth", 0),
            "iteration": result.get("iterations", 1),
            "timestamp": now,
            "status": status,
            "score": quality,
            "duration": duration
        })

        if status == "done":
            console.print(f"    [green]✔ {aid} PASSED[/green] (Score: {quality:.2f})")
        else:
            console.print(f"    [red]✘ {aid} LOW QUALITY[/red] (Score: {quality:.2f} < {agent['threshold']})")
            
        return step_result

    except Exception as e:
        console.print(f"    [bold red]✖ {aid} ERROR: {str(e)}[/bold red]")
        return {
            "agent_id": aid,
            "status": "error",
            "result": "",
            "quality_score": 0.0,
            "feedback": "",
            "iterations": 1,
            "output_path": None,
            "error": str(e)
        }
