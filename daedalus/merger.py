"""
daedalus/merger.py
Cross-agent interface conflict detection and resolution.
Detects mismatches between agent outputs and produces canonical resolutions.
"""

import asyncio
import json
from typing import List, Dict, Any
from rich.console import Console

from daedalus.state import BrokenInterface, StepResult
from infra.mongo_client import get_db

console = Console()

# ── LLM Prompt Templates ─────────────────────────────────────────────────────

DETECT_CONFLICTS_PROMPT = """You are Daedalus Conflict Detector. Given the outputs of multiple agents that worked on related parts of a project, identify any INTERFACE CONFLICTS between them.

An interface conflict is when two agents make incompatible assumptions about:
- Data schemas or models (field names, types)
- API endpoints (paths, methods, request/response shapes)
- Function signatures or imports
- Configuration or environment variables
- Authentication flows

AGENT OUTPUTS:
{agent_outputs}

DEPENDENCY GRAPH:
{dep_graph}

Output ONLY valid JSON — a list of conflicts (empty list if none):
[
  {{
    "agent_a": "<agent_id>",
    "agent_b": "<agent_id>",
    "description": "<what is incompatible between them>"
  }}
]

If no conflicts exist, return: []
"""

RESOLVE_CONFLICT_PROMPT = """You are Daedalus Conflict Resolver. Two agents produced incompatible outputs.

CONFLICT: {description}

AGENT A ({agent_a}) OUTPUT:
{result_a}

AGENT B ({agent_b}) OUTPUT:
{result_b}

Determine which agent's version should be canonical. Produce a resolution.

Output ONLY valid JSON:
{{
  "canonical_agent": "<agent_id of the agent whose version wins>",
  "resolution": "<description of what the other agent must change>",
  "patched_output": "<corrected output for the losing agent, or empty string if no patch needed>"
}}
"""


async def _call_llm(system_prompt: str, user_msg: str) -> str:
    """Call LLM via the standard waterfall. Isolated for mocking in tests."""
    from kimiflow.agents import _call_with_fallback
    from models import REASONER_MODELS

    def _do():
        return _call_with_fallback(
            REASONER_MODELS,
            system_prompt,
            user_msg,
            temperature=0.1
        )
    return await asyncio.to_thread(_do)


async def detect_conflicts(
    agent_results: Dict[str, StepResult],
    dep_graph: Dict[str, List[str]],
) -> List[BrokenInterface]:
    """
    Inspect all agent outputs and identify interface conflicts.
    Returns a list of BrokenInterface dicts.
    """
    if len(agent_results) < 2:
        return []

    # Build a summary of each agent's output for the LLM
    agent_outputs = ""
    for aid, result in agent_results.items():
        output_text = result.get("result", "")[:2000]
        agent_outputs += f"\n--- Agent {aid} ---\n{output_text}\n"

    user_msg = DETECT_CONFLICTS_PROMPT.format(
        agent_outputs=agent_outputs,
        dep_graph=json.dumps(dep_graph, indent=2)
    )

    try:
        raw = await _call_llm("You detect interface conflicts between agent outputs.", user_msg)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        conflicts = json.loads(raw)
        if not isinstance(conflicts, list):
            return []

        broken: List[BrokenInterface] = []
        for c in conflicts:
            if "agent_a" in c and "agent_b" in c and "description" in c:
                broken.append({
                    "agent_a": c["agent_a"],
                    "agent_b": c["agent_b"],
                    "description": c["description"],
                    "attempt": 0,
                })

        if broken:
            console.print(f"  [yellow]⚠ Found {len(broken)} interface conflict(s)[/yellow]")
            for b in broken:
                console.print(f"    {b['agent_a']} ↔ {b['agent_b']}: {b['description']}")
        else:
            console.print("  [green]✔ No interface conflicts detected[/green]")

        return broken

    except (json.JSONDecodeError, Exception) as e:
        console.print(f"  [red]✖ Conflict detection failed: {e}[/red]")
        return []


async def resolve_conflict(
    interface: BrokenInterface,
    result_a: str,
    result_b: str,
    run_id: str,
) -> Dict[str, Any]:
    """
    Resolve one specific conflict pair via LLM.
    Returns resolution dict with canonical_agent, resolution description, and patched_output.
    Logs the resolution to MongoDB conflicts collection.
    """
    user_msg = RESOLVE_CONFLICT_PROMPT.format(
        description=interface["description"],
        agent_a=interface["agent_a"],
        agent_b=interface["agent_b"],
        result_a=result_a[:3000],
        result_b=result_b[:3000],
    )

    try:
        raw = await _call_llm("You resolve interface conflicts between agents.", user_msg)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        resolution = json.loads(raw)

        # Log to MongoDB
        import datetime
        db = get_db()
        await db.conflicts.insert_one({
            "run_id": run_id,
            "agent_a": interface["agent_a"],
            "agent_b": interface["agent_b"],
            "interface": interface["description"],
            "resolution": resolution.get("resolution", ""),
            "canonical_agent": resolution.get("canonical_agent", ""),
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        })

        console.print(
            f"  [green]✔ Resolved: {interface['agent_a']} ↔ {interface['agent_b']} "
            f"→ canonical: {resolution.get('canonical_agent', '?')}[/green]"
        )
        return resolution

    except (json.JSONDecodeError, Exception) as e:
        console.print(f"  [red]✖ Conflict resolution failed: {e}[/red]")
        return {"canonical_agent": "", "resolution": str(e), "patched_output": ""}


async def detect_and_resolve_all(
    agent_results: Dict[str, StepResult],
    dep_graph: Dict[str, List[str]],
    run_id: str,
) -> tuple[List[BrokenInterface], Dict[str, StepResult]]:
    """
    Convenience function: detect all conflicts, resolve each, patch agent_results.
    Returns (broken_interfaces, updated_agent_results).
    """
    broken = await detect_conflicts(agent_results, dep_graph)
    if not broken:
        return [], agent_results

    updated_results = dict(agent_results)

    for conflict in broken:
        a_id = conflict["agent_a"]
        b_id = conflict["agent_b"]
        result_a = agent_results.get(a_id, {}).get("result", "")
        result_b = agent_results.get(b_id, {}).get("result", "")

        resolution = await resolve_conflict(conflict, result_a, result_b, run_id)

        patched = resolution.get("patched_output", "")
        canonical = resolution.get("canonical_agent", "")
        if patched and canonical:
            loser_id = b_id if canonical == a_id else a_id
            if loser_id in updated_results:
                updated_results[loser_id] = {
                    **updated_results[loser_id],
                    "result": patched,
                }

    return broken, updated_results
