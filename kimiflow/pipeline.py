# pipeline.py — 6-role self-correcting pipeline
# Roles: coder | reasoner | drafter | creative | fast
# Groq is the ironclad backup if ALL OpenRouter models fail

from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
from kimiflow.agents import (
    orchestrator_plan,
    coder_execute,
    reasoner_execute,
    drafter_execute,
    creative_execute,
    fast_execute,
    groq_draft,
    evaluator_score,
)

SPECIALIST_MAP = {
    "coder":    coder_execute,
    "reasoner": reasoner_execute,
    "drafter":  drafter_execute,
    "creative": creative_execute,
    "fast":     fast_execute,
}


class PipelineState(TypedDict):
    task:           str
    plan:           str
    assigned_model: str
    result:         str
    quality_score:  float
    threshold:      float
    feedback:       str
    iterations:     int


# ── Nodes ─────────────────────────────────────────────────────────────────────

def plan_node(state: PipelineState) -> PipelineState:
    print(f"\n[Orchestrator] Planning...")
    out = orchestrator_plan(state["task"])
    print(f"[Orchestrator] Plan: {out['plan']}")
    print(f"[Orchestrator] Assigned: {out['assigned_model']}")
    return {
        **state,
        "plan":           out["plan"],
        "assigned_model": out["assigned_model"],
    }


def execute_node(state: PipelineState) -> PipelineState:
    role     = state["assigned_model"]
    n        = state["iterations"] + 1
    feedback = state.get("feedback", "")   # evaluator feedback from prior iteration
    print(f"\n[Execute] Specialist: {role}  (run #{n})")
    if feedback and n > 1:
        print(f"[Execute] Applying feedback from iteration #{n-1}: {feedback[:120]}")

    fn = SPECIALIST_MAP.get(role)
    if fn is None:
        print(f"[Execute] Unknown role '{role}' — defaulting to drafter")
        fn = drafter_execute

    try:
        result = fn(state["plan"], state["task"], feedback)
    except RuntimeError as e:
        # All OpenRouter models failed — Groq is the ironclad fallback
        print(f"[Execute] All OpenRouter models failed. Using Groq backup.")
        print(f"[Execute] Reason: {e}")
        result = groq_draft(state["plan"], state["task"], feedback)

    print(f"[Execute] Got {len(result)} chars")
    return {**state, "result": result, "iterations": n}


def evaluate_node(state: PipelineState) -> PipelineState:
    print(f"\n[Evaluator] Scoring result...")
    ev = evaluator_score(state["task"], state["result"])
    print(f"[Evaluator] Score: {ev['score']:.2f} | {ev['feedback'][:100]}")
    print(f"[Evaluator] Next action: {ev['retry_with']}")
    return {
        **state,
        "quality_score":  ev["score"],
        "feedback":       ev["feedback"],
        "assigned_model": ev["retry_with"],
    }


# ── Routing ───────────────────────────────────────────────────────────────────

def should_retry(state: PipelineState) -> Literal["execute", "done"]:
    score      = state["quality_score"]
    next_model = state["assigned_model"]
    iters      = state["iterations"]

    threshold = state.get("threshold", 0.85)

    # ── Hard cap ──────────────────────────────────────────────────────────────
    if iters >= 15:
        print(f"[Router] Max 15 iterations reached (score={score:.2f}) — accepting result.")
        return "done"

    # ── Both signals agree: quality met ───────────────────────────────────────
    if score >= threshold and next_model == "done":
        print(f"[Router] Score {score:.2f} ≥ {threshold} and evaluator says done — finishing.")
        return "done"

    # ── Score met but evaluator still wants a retry ───────────────────────────
    # Trust the score; a good result should not be re-run unnecessarily.
    if score >= threshold:
        print(f"[Router] Score {score:.2f} ≥ {threshold} — accepting result "
              f"(evaluator suggested '{next_model}' but score threshold met).")
        return "done"

    # ── Evaluator explicitly satisfied (score may be slightly under threshold) ─
    if next_model == "done":
        print(f"[Router] Evaluator marked done (score={score:.2f}) — accepting result.")
        return "done"

    # ── Retry ─────────────────────────────────────────────────────────────────
    print(
        f"[Router] Score {score:.2f} < {threshold} on iteration {iters} "
        f"— retrying with '{next_model}'"
    )
    return "execute"


# ── Build & export ────────────────────────────────────────────────────────────

def build_pipeline():
    g = StateGraph(PipelineState)
    g.add_node("plan",     plan_node)
    g.add_node("execute",  execute_node)
    g.add_node("evaluate", evaluate_node)
    g.set_entry_point("plan")
    g.add_edge("plan",    "execute")
    g.add_edge("execute", "evaluate")
    g.add_conditional_edges(
        "evaluate",
        should_retry,
        {"execute": "execute", "done": END},
    )
    return g.compile()


pipeline = build_pipeline()