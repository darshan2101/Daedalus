import uuid
from typing import Dict, Any

from kimiflow.agents import _call_with_fallback, _parse_json
from models import ORCHESTRATOR_MODELS
from daedalus.state import RunState, AgentSpec

PLANNER_SYSTEM_PROMPT = """
You are the Daedalus Meta-Orchestrator. Given a goal, decompose it into major tasks.

Output ONLY valid JSON:
{
  "plan": "<one paragraph strategy>",
  "output_type": "<code|docs|design|research>",
  "agent_specs": [
    {
      "agent_id": "ag_<4chars>",
      "task": "<specific task description>",
      "output_type": "<code|docs|design|research>",
      "threshold": 0.88,
      "dependencies": ["ag_xxxx"],
      "specialist": "<coder|reasoner|drafter|creative|fast|researcher>"
    }
  ],
  "dep_graph": { "ag_xxxx": ["ag_yyyy"] }
}

Rules:
- agent_ids must be unique within the plan
- All dep_graph entries must reference valid agent_ids
- No circular dependencies
- threshold cannot be lower than default for output_type
- Avoid spawning agents for trivial tasks like single dependency files (e.g. requirements.txt, .gitignore). These should be part of the main coding agent's output.
- Every agent must have a unique agent_id.
- When multiple agents interact via API (frontend<->backend, auth<->backend), specify the EXACT endpoint path, method, and auth requirement in BOTH agents' task descriptions so they share a common contract.
- Example: if ag_auth secures POST /api/report, ag_front's task must explicitly state "call POST /api/report with JWT Bearer token in header".
- Always output valid JSON strictly matching the format above.
"""

async def plan_goal(goal: str, preset: str, config: dict) -> dict:
    import asyncio
    
    saas_rule = ""
    if preset == "saas":
        saas_rule = "\n- Rule: SaaS apps always need: schema, backend, auth, frontend, docs agents minimum"

    user_msg = f"Goal: {goal}\nPreset: {preset}{saas_rule}"
    raw = None
    
    # ── Try Ollama Cloud first (if configured and enabled) ────────────────
    ollama_enabled = config.get("infra", {}).get("ollama_enabled", True)
    ollama_roles = config.get("infra", {}).get("ollama_roles", ["planner", "reasoner"])
    
    if ollama_enabled and "planner" in ollama_roles:
        try:
            from infra.ollama_client import ollama_chat, is_configured as ollama_configured
            from models import OLLAMA_PLANNER_MODELS
            
            if ollama_configured():
                timeout = config.get("infra", {}).get("ollama_timeout_seconds", 120)
                for model in OLLAMA_PLANNER_MODELS:
                    print(f"  [trying ollama: {model}]")
                    messages = [
                        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ]
                    result = await ollama_chat(model, messages, temperature=0.2, timeout=float(timeout))
                    if result is not None:
                        print(f"  [success ollama: {model}]")
                        raw = result
                        break
        except Exception as e:
            print(f"  [Ollama unavailable: {e} — falling to OpenRouter]")
    
    # ── Fall back to OpenRouter waterfall ─────────────────────────────────
    if raw is None:
        def _run_planner():
            return _call_with_fallback(
                ORCHESTRATOR_MODELS,
                PLANNER_SYSTEM_PROMPT,
                user_msg,
                temperature=0.2
            )
        raw = await asyncio.to_thread(_run_planner)
    parsed = _parse_json(raw)
    
    if "agent_specs" not in parsed:
        raise ValueError(f"Planner response missing agent_specs: {parsed}")
        
    specs = []
    for s in parsed["agent_specs"]:
        s["depth"] = 0
        s["parent_id"] = None
        specs.append(s)
        
    dep_graph = parsed.get("dep_graph", {})
    
    _validate_dag(specs, dep_graph)
    specs = _tighten_thresholds(specs, config)
    
    return {
        "plan": parsed.get("plan", ""),
        "output_type": parsed.get("output_type", "code"),
        "agent_specs": specs,
        "dep_graph": dep_graph
    }

def _validate_dag(specs: list[dict], deps: dict) -> None:
    valid_ids = {s["agent_id"] for s in specs}
    for a, d in deps.items():
        if a not in valid_ids:
            raise ValueError(f"Unknown agent_id {a} in dep_graph")
        for dep in d:
            if dep not in valid_ids:
                raise ValueError(f"Unknown dependency {dep} for {a}")
    
    # check cycles
    visited = set()
    path = set()
    
    def node_has_cycle(node):
        if node in path:
            return True
        if node in visited:
            return False
        
        path.add(node)
        visited.add(node)
        
        for dep in deps.get(node, []):
            if node_has_cycle(dep):
                return True
                
        path.remove(node)
        return False
        
    for node in valid_ids:
        if node_has_cycle(node):
            raise ValueError("Circular dependency detected in plan")

def _tighten_thresholds(specs: list[dict], config: dict) -> list[dict]:
    thresholds = config.get("thresholds", {})
    def_thresh = thresholds.get("default", 0.82)
    for s in specs:
        base_thresh = thresholds.get(s["output_type"], def_thresh)
        s["threshold"] = max(s.get("threshold", 0), base_thresh)
    return specs
