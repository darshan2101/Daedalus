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
1. Analyze the assembled output. You must score it across 5 dimensions, each out of 1.0.
   - correctness: Logic, accuracy, and lack of bugs.
   - completeness: Are all requested features/requirements present?
   - consistency: Internal coherence, architectural alignment, variable naming.
   - runnability: Does it look like it will actually run/compile without crashing?
   - format: Cleanliness, structure, and adherence to standard patterns.
2. Provide a brief explanation of your scoring in 'breakdown'.
3. Identify the 'weakest_agents' by their agent_id (e.g. "ag_5b2d") based on the Agent Specifications and where the output fell short. If it's a perfect run, leave weakest_agents empty.

You MUST respond in valid JSON format ONLY:
{{
  "dimensions": {{
    "correctness": 0.95,
    "completeness": 0.90,
    "consistency": 0.85,
    "runnability": 0.80,
    "format": 0.95
  }},
  "breakdown": "Explanation of the scores...",
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

    safe_result = combined_result[:100000]

    system_msg = "You are a top-tier software architect grading a system's output. Output ONLY valid JSON."
    user_msg = EVAL_PROMPT.format(
        goal=goal,
        preset=preset,
        agent_specs=specs_text,
        combined_result=safe_result
    )
    
    max_eval_retries = 2
    for attempt in range(max_eval_retries):
        try:
            raw_response = _call_with_fallback(EVALUATOR_MODELS, system_msg, user_msg)
            parsed = _parse_json(raw_response)
            
            dimensions = parsed.get("dimensions", {})
            
            # Pull weights from config based on preset, fallback to default
            eval_weights_config = config.get("evaluation_weights", {})
            weights = eval_weights_config.get(preset, eval_weights_config.get("default", {
                "correctness": 0.30,
                "completeness": 0.20,
                "consistency": 0.20,
                "runnability": 0.20,
                "format": 0.10
            }))
            
            # Calculate weighted average
            score = 0.0
            for dim, weight in weights.items():
                dim_score = float(dimensions.get(dim, 0.0))
                score += dim_score * float(weight)

            breakdown = parsed.get("breakdown", "No breakdown provided.")
            weakest = parsed.get("weakest_agents", [])
            
            if not isinstance(weakest, list):
                weakest = []
                
            state["system_score"] = float(score)
            state["dimensions"] = dimensions
            state["breakdown"] = breakdown
            state["weakest_agents"] = weakest
            
            # Determine threshold for color coding print target
            output_type = state.get("output_type", "default")
            thresholds = config.get("thresholds", {})
            threshold = thresholds.get(output_type, thresholds.get("default", 0.82))

            console.print(f"  [cyan]System Score:[/] [bold {'green' if score >= threshold else 'red'}]{score:.2f}[/]")
            
            console.print(f"  [cyan]Dimensions:[/] ")
            for dim, dim_score in dimensions.items():
                console.print(f"    - {dim.capitalize()}: {dim_score} (weight: {weights.get(dim, 0.0)})")
                
            console.print(f"  [cyan]Breakdown:[/] {breakdown}")
            if weakest:
                console.print(f"  [cyan]Weakest Agents:[/] {', '.join(weakest)}")
                
            return state

        except Exception as e:
            console.print(f"  [bold yellow]Evaluator Attempt {attempt+1} failed:[/] {e}")
            if attempt == max_eval_retries - 1:
                # Permanent failure: Use sentinel if no score exists
                if "system_score" not in state:
                    state["system_score"] = -1.0  # sentinel: evaluation failed
                
                state["weakest_agents"] = state.get("weakest_agents", [])
                console.print(f"  [bold red]Evaluator permanently failed. Score preserved or set to sentinel (-1.0).[/]")
    
    return state
