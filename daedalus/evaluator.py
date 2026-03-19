import json
from rich.console import Console
from daedalus.state import RunState
from models import EVALUATOR_MODELS
from kimiflow.agents import _call_with_fallback, _parse_json

console = Console()

EVAL_PROMPT = """You are the DAEDALUS SYSTEM EVALUATOR.
Your job is to holistically evaluate the final assembled output of a multi-agent system against the user's original goal.

Original Goal:
{goal}

Preset (Output Type):
{preset}

Agent Specifications (for context on who did what):
{agent_specs}

Final Assembled Output:
{combined_result}

INSTRUCTIONS:
1. Analyze the assembled output. Does it completely, accurately, and beautifully fulfill the original goal?
2. Score the system out of 1.0 (float). 
   - 0.95+ = Excellent, ready to ship.
   - 0.85-0.94 = Good, minor issues but passing.
   - < 0.85 = Needs repair (missing major requirements, broken code, logical holes, or failure to follow instructions).
3. Provide a brief explanation of your score in 'breakdown'.
4. If the score is < 0.85, identify the 'weakest_agents' by their agent_id (e.g. "ag_5b2d") based on the Agent Specifications and where the output fell short. If it's a passing run (>0.85), you can leave weakest_agents empty.

You MUST respond in valid JSON format ONLY:
{{
  "system_score": 0.95,
  "breakdown": "Explanation of the score...",
  "weakest_agents": ["ag_1a2b"] 
}}
"""

def evaluate_run(run_id: str, state: RunState, config: dict) -> RunState:
    console.print(f"\n[bold magenta]⚖️  Evaluating System Output...[/]")
    
    goal = state.get("goal", "Unknown Goal")
    preset = state.get("preset", "default")
    combined_result = state.get("combined_result", "")
    
    # Simplify agent specs for context
    specs_summary = []
    for s in state.get("agent_specs", []):
        specs_summary.append(f"- {s.get('agent_id')} ({s.get('specialist')}): {s.get('task')}")
    specs_text = "\n".join(specs_summary)

    # Truncate combined result if it's insanely massive, preserving most of it.
    # We will pass up to 100,000 characters to be safe for 128k context models.
    safe_result = combined_result[:100000]

    system_msg = "You are a top-tier software architect grading a system's output. Output ONLY valid JSON."
    user_msg = EVAL_PROMPT.format(
        goal=goal,
        preset=preset,
        agent_specs=specs_text,
        combined_result=safe_result
    )
    
    try:
        raw_response = _call_with_fallback(EVALUATOR_MODELS, system_msg, user_msg)
        parsed = _parse_json(raw_response)
        
        score = float(parsed.get("system_score", 0.0))
        breakdown = parsed.get("breakdown", "No breakdown provided.")
        weakest = parsed.get("weakest_agents", [])
        
        if not isinstance(weakest, list):
            weakest = []
            
        state["system_score"] = score
        state["breakdown"] = breakdown
        state["weakest_agents"] = weakest
        
        console.print(f"  [cyan]System Score:[/] [bold {'green' if score >= 0.85 else 'red'}]{score}[/]")
        console.print(f"  [cyan]Breakdown:[/] {breakdown}")
        if weakest:
            console.print(f"  [cyan]Weakest Agents:[/] {', '.join(weakest)}")
            
    except Exception as e:
        console.print(f"  [bold red]Evaluator Error:[/] {e}")
        state["system_score"] = 0.0
        state["weakest_agents"] = []
        
    return state
