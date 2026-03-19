from rich.console import Console
from daedalus.state import RunState
from infra.redis_client import unfreeze_agent

console = Console()

def repair_if_needed(run_id: str, state: RunState, config: dict) -> tuple[bool, RunState]:
    """
    Checks if the system_score is below threshold and unfreezes the weakest agents
    to trigger another pass in the execution loop.
    Returns (True, state) if repair is triggered, (False, state) if not.
    """
    score = state.get("system_score", 0.0)
    threshold = config.get("thresholds", {}).get("system", 0.85)

    if score >= threshold:
        # Pass
        return False, state

    attempts = state.get("repair_attempts", 0)
    max_attempts = config.get("runtime", {}).get("max_repair_attempts", 3)

    if attempts >= max_attempts:
        console.print(f"\\n[bold red]⚠️  System Score ({score}) is below threshold ({threshold}), but max repair attempts ({max_attempts}) reached. Giving up.[/]")
        return False, state

    # We need to drop the score and do a repair
    state["repair_attempts"] = attempts + 1
    
    # Identify targets
    weakest = state.get("weakest_agents", [])
    
    if not weakest:
        # Fallback: find lowest scored agent in results
        results = state.get("agent_results", {})
        if results:
            # Sort by quality_score asc
            sorted_agents = sorted(results.items(), key=lambda x: x[1].get("quality_score", 0.0))
            weakest = [sorted_agents[0][0]]

    if not weakest:
        console.print("\\n[bold red]⚠️  Score is low, but no weakest agents identified to repair.[/]")
        return False, state

    console.print(f"\\n[bold yellow]🛠️  Repair pass {state['repair_attempts']}/{max_attempts} triggered![/]")
    console.print(f"    [dim]Score: {score} < {threshold}[/]")
    console.print(f"    [dim]Unfreezing agents: {', '.join(weakest)}[/]")

    # Unfreeze
    for aid in weakest:
        try:
            unfreeze_agent(run_id, aid)
        except Exception as e:
            console.print(f"[bold red]Failed to unfreeze {aid} in Redis:[/] {e}")

    return True, state
