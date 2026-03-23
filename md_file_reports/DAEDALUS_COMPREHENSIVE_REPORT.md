# DAEDALUS — COMPREHENSIVE ARCHITECTURE REPORT
# Full static analysis of every source file.
# Purpose: give Claude Code a complete picture so it can act autonomously
# without requiring human review of every change.
# Read this entire document before making any changes.

---

## SYSTEM HEALTH SUMMARY

The codebase is in good shape. The major stability bugs (E11000, LangGraph crashes,
resume restoring empty state) are all fixed. The four architectural improvements
(repair context injection, evaluator robustness, merger scaling, threshold sync)
are correctly implemented. The test suite has good coverage of the core modules.

What follows is an honest accounting of every remaining issue found, ordered by
severity, with precise fixes. Nothing here requires architectural redesign —
these are targeted improvements.

---

## CRITICAL (will cause incorrect behavior in production)

### C1 — evaluator.py: permanent failure still writes system_score = 0.0

**File:** `daedalus/evaluator.py` lines 125-128

**Problem:** When both retry attempts fail, the code does:
```python
if "system_score" not in state:
    state["system_score"] = 0.0  # No choice here
```
If this is a fresh run's first evaluation and both attempts fail (e.g., malformed
JSON twice), `system_score` is not in state yet, so it gets set to 0.0. This
triggers the repair engine, which unfreezes all agents and re-runs everything —
a full cascade from a transient LLM formatting error.

This is exactly what caused the score-0.00 repair cascade in the Elixir run.

**Fix — remove the 0.0 assignment entirely:**
```python
if attempt == max_eval_retries - 1:
    # Permanent failure — do NOT write system_score at all.
    # Leaving it absent means route_after_eval will see 0.0 via .get() default,
    # but we cannot distinguish "didn't run" from "ran and scored 0".
    # Better: set a sentinel that repair engine explicitly ignores.
    if "system_score" not in state:
        state["system_score"] = -1.0  # sentinel: evaluation failed, not a real score
    console.print(
        "  [bold red]Evaluator permanently failed. Score unchanged.[/]"
    )
    state["weakest_agents"] = state.get("weakest_agents", [])
```

Then in `daedalus/graph.py` `route_after_eval` and `daedalus/repair.py`
`repair_if_needed`, add a guard:
```python
score = state.get("system_score", 0.0)
if score < 0:  # sentinel: evaluation failed, skip repair
    console.print("[yellow]Skipping repair — evaluator did not produce a valid score.[/]")
    return "done"  # or return False, state
```

And update the unit test in `test_evaluator.py` — `test_evaluator_permanent_failure_keeps_score`
currently only tests the "score already exists" case. Add a test for the
"first evaluation ever fails" case and assert `system_score == -1.0`.

---

### C2 — sub_agent.py: threshold defaults are mismatched

**File:** `daedalus/sub_agent.py` lines 68 and 91

**Problem:**
```python
# Line 68 — threshold passed to KimiFlow pipeline for routing
"threshold": agent.get("threshold", 0.85),

# Line 91 — threshold used for freeze/fail decision
status = "done" if quality >= agent.get("threshold", 0.0) else "failed"
```

Line 68 defaults to 0.85 if no threshold on the agent spec.
Line 91 defaults to 0.0. These are different values used for related decisions.

If an agent spec somehow arrives without a threshold (possible if planner output
is partially malformed), line 68 tells KimiFlow "pass at 0.85" but line 91
freezes the agent as "done" for any score above 0.0. An agent scoring 0.3
would be frozen as passing.

**Fix — resolve threshold once from config, use that single variable everywhere:**
```python
# At the top of run_agent_task, after extracting aid/task/role:
agent_threshold = agent.get("threshold") or (
    config.get("thresholds", {}).get(
        agent.get("output_type", "default"),
        config.get("thresholds", {}).get("default", 0.82)
    )
)

# Line 68 becomes:
"threshold": agent_threshold,

# Line 91 becomes:
status = "done" if quality >= agent_threshold else "failed"

# Line 128 becomes:
console.print(f"    [red]✘ {aid} LOW QUALITY[/red] (Score: {quality:.2f} < {agent_threshold})")
```

---

## HIGH (degrades quality of complex runs, not crashes)

### H1 — merger.py: conflict detection truncates agent output to 2000 chars

**File:** `daedalus/merger.py` line ~97

**Problem:**
```python
output_text = result.get("result", "")[:2000]
```

The merger only sends the first 2000 characters of each agent's output to the
conflict detector LLM. For complex agents (Elixir auth was 9149 chars,
ag_realtime was 19768 chars), this means the LLM is detecting conflicts
based on partial output — it may miss conflicts that exist only in the
latter half of the code, and it may hallucinate conflicts that are actually
resolved in code it never saw.

**Fix — increase the truncation limit and be smarter about what to send:**
```python
# Instead of raw truncation, send a structured summary:
# - First 1000 chars (usually imports, type definitions, module declarations)
# - Last 1000 chars (usually the end of the main function/class)
# This gives the conflict detector the most architecturally relevant parts.

output_text = result.get("result", "")
if len(output_text) > 3000:
    head = output_text[:1500]
    tail = output_text[-1500:]
    output_text = head + "\n... [truncated] ...\n" + tail
```

Also increase the resolve_conflict truncation from 3000 to 4000 per agent.

---

### H2 — repair.py: repair_context only covers broken_interfaces, not evaluator feedback

**File:** `daedalus/repair.py`

**Problem:** The repair context injected into agents includes merger conflict
descriptions, which is correct. But the evaluator's `breakdown` field often
contains more actionable feedback than the merger — e.g., "missing GET /messages
endpoint", "Role schema not found", "router file missing routes". This evaluator
feedback is never passed to the re-running agents.

**Fix — include evaluator breakdown in repair context:**
```python
# In repair_if_needed, after building repair_context from broken_interfaces:

# Also inject relevant evaluator feedback
breakdown = state.get("breakdown", "")
weakest = state.get("weakest_agents", [])

if breakdown and weakest:
    for aid in weakest:
        if aid not in repair_context:
            repair_context[aid] = []
        # Add evaluator breakdown as additional context
        repair_context[aid].append(
            f"SYSTEM EVALUATOR FEEDBACK: {breakdown}"
        )

state["repair_context"] = repair_context
```

This means agents being repaired get BOTH the specific interface conflict
(from merger) AND the holistic system feedback (from evaluator). This is
the primary reason the Elixir run's `ag_schema` kept missing the `room_id`
field — the evaluator told the system about it but the info never reached
the agent.

---

### H3 — aggregator.py: "default" preset routes to docs, losing code output

**File:** `daedalus/aggregator.py` lines at bottom

**Problem:**
```python
if preset in ("code", "saas"):
    combined_text, out_path = _aggregate_code(run_id, state)
else:
    # Default, research, docs
    combined_text, out_path = _aggregate_docs(run_id, state)
```

When `--preset default` is used (which is the most common case), the aggregator
routes to `_aggregate_docs`. But `_aggregate_docs` just concatenates markdown
with headers — it does NOT extract `--- FILE: ---` blocks into actual files.

This means that for the "Build a REST API" default run, the code existed in the
raw output but the aggregator never extracted the actual `.py` files. The
assembler later does extract them from the combined markdown, but `final_code/`
is never populated — only `FINAL.md` and then the zip.

The evaluator also reads `combined_result` which in docs mode is the raw markdown,
not the structured code blocks. This inflates evaluator scores artificially for
default-preset runs because the evaluator sees the code inline.

**Fix — use output_type, not preset, to decide aggregation strategy:**
```python
def aggregate(run_id: str, state: RunState, config: dict) -> RunState:
    output_type = state.get("output_type", "code")
    preset = state.get("preset", "default")
    
    # Use code extraction if the run produced code output (regardless of preset)
    if output_type in ("code",) or preset in ("saas", "code"):
        combined_text, out_path = _aggregate_code(run_id, state)
    else:
        combined_text, out_path = _aggregate_docs(run_id, state)
    
    state["combined_result"] = combined_text
    state["output_path"] = out_path
    return state
```

---

### H4 — graph.py: execute_node and coordinator.py use different freeze thresholds

**File:** `daedalus/graph.py` line ~113 and `daedalus/coordinator.py` line ~74

**Problem:** In `graph.py execute_node`:
```python
if result.get("quality_score", 0.0) >= agent.get("threshold", 0.0):
    freeze_agent(state["run_id"], agent["agent_id"])
```

In `coordinator.py _run_with_sem`:
```python
if result.get("quality_score", 0.0) >= agent.get("threshold", 0.0):
    freeze_agent(self.run_id, agent["agent_id"])
```

Both default to 0.0 if threshold is missing — same bug as C2, duplicated in
two places. Fix both the same way as C2.

Also note: `coordinator.py` uses `result.get("quality_score")` but `sub_agent.py`
writes the field as `quality_score`. This is consistent. Good.

---

## MEDIUM (minor behavior issues, low risk)

### M1 — planner.py: PLANNER_SYSTEM_PROMPT has a saas-specific rule at global level

**File:** `daedalus/planner.py` in `PLANNER_SYSTEM_PROMPT`

**Problem:**
```
- SaaS apps always need: schema, backend, auth, frontend, docs agents minimum
```

This rule is hardcoded in the global planner prompt, which means it fires for
ALL presets. A `--preset research` or `--preset docs` goal will get a planner
that tries to add frontend and auth agents to a documentation task.

**Fix — make the saas rule conditional:**
```python
# In plan_goal(), build the prompt dynamically:
saas_rule = ""
if preset == "saas":
    saas_rule = "\n- SaaS apps always need: schema, backend, auth, frontend, docs agents minimum"

user_msg = f"Goal: {goal}\nPreset: {preset}{saas_rule}"
```

And remove it from the static `PLANNER_SYSTEM_PROMPT`.

---

### M2 — state.py: StepResult TypedDict is missing fields that sub_agent.py writes

**File:** `daedalus/state.py`

**Problem:** `StepResult` is defined as:
```python
class StepResult(TypedDict):
    agent_id: str
    task: str
    result: str
    score: float        # ← named 'score'
    iterations: int
    frozen: bool
```

But `sub_agent.py` writes:
```python
step_result: StepResult = {
    "agent_id": aid,
    "task": task,
    "depth": ...,       # ← not in TypedDict
    "timestamp": ...,   # ← not in TypedDict
    "status": ...,      # ← not in TypedDict
    "result": ...,
    "quality_score": ..., # ← named differently than TypedDict's 'score'
    "feedback": ...,    # ← not in TypedDict
    "iterations": ...,
    "output_path": ..., # ← not in TypedDict
    "error": ...        # ← not in TypedDict
}
```

The TypedDict is stale — it documents neither the actual fields written nor
their names. This means type checkers and any code that reads `result.get("score")`
(expecting the TypedDict definition) will fail silently against actual data
that has `quality_score`.

**Fix — update StepResult to match reality:**
```python
class StepResult(TypedDict, total=False):
    agent_id:      str
    task:          str
    depth:         int
    timestamp:     str
    status:        str          # "done" | "failed" | "error"
    result:        str
    quality_score: float        # renamed from 'score'
    feedback:      str
    iterations:    int
    output_path:   Optional[str]
    error:         Optional[str]
```

Also search for any code reading `result.get("score")` and change to
`result.get("quality_score")`.

---

### M3 — local_coordinator.py: test expects status "partial" but code writes "failed"

**File:** `tests/unit/test_local_coord.py` line ~176
`daedalus/local_coordinator.py` `_merge_sub_results`

**Problem:** The test `test_partial_failure_marked_partial` asserts:
```python
assert result["status"] == "failed"
```

But the test name says "partial". The test was written after the fix that
changed `"partial"` to `"failed"`. The test name is now misleading — it tests
that partial failure produces `"failed"` status, which is correct behavior.

**Fix — rename the test to match what it actually tests:**
```python
def test_partial_failure_marked_failed(self):
    """If some sub-agents fail, merged status is 'failed' (not 'partial')."""
```

---

### M4 — tests/unit/test_evaluator.py: missing test for first-ever evaluation failure

**File:** `tests/unit/test_evaluator.py`

**Problem:** `test_evaluator_permanent_failure_keeps_score` tests the case where
`system_score` already exists in state. It does not test the case where this is
the first evaluation ever (state has no `system_score`) and both attempts fail.

After fix C1 is applied (sentinel -1.0), add:
```python
def test_evaluator_permanent_failure_first_run_uses_sentinel(mock_state, mock_config):
    # No system_score in state — first ever evaluation, both fail
    assert "system_score" not in mock_state
    responses = [Exception("Fail 1"), Exception("Fail 2")]
    
    with patch("daedalus.evaluator._call_with_fallback", side_effect=responses):
        state = evaluate_run("run_123", mock_state, mock_config)
    
    # Should be -1.0 sentinel, NOT 0.0
    assert state["system_score"] == -1.0
```

---

### M5 — main.py: graph_state initializes system_score to 0.0

**File:** `main.py` line ~162

**Problem:**
```python
graph_state = {
    ...
    "system_score": 0.0,   # ← hardcoded
    ...
}
```

After fix C1 (sentinel -1.0), the initial system_score should also be -1.0
to signal "not yet evaluated" rather than "scored zero". Otherwise a resume
that fails evaluation on the first attempt won't be distinguishable from
a run that actually scored 0.0.

```python
"system_score": -1.0,  # sentinel: not yet evaluated
```

---

## LOW (cosmetic / future hygiene)

### L1 — _parse_json graceful degradation returns incorrect fields for evaluator context

**File:** `kimiflow/agents.py` `_parse_json` fallback

When `_parse_json` fails, it returns:
```python
{
    "score": 0.0,
    "feedback": "...",
    "retry_with": "drafter",
    "plan": "...",
    "assigned_model": "drafter",
}
```

This is designed for the KimiFlow pipeline evaluator which reads `score`,
`feedback`, and `retry_with`. But `daedalus/evaluator.py` calls `_parse_json`
too and reads `dimensions`, `breakdown`, and `weakest_agents`. When
`daedalus/evaluator.py` gets this fallback dict, `dimensions` will be `{}`,
the score calculation will be 0.0, and `breakdown` will be empty.

The evaluator's retry loop catches this because score 0.0 triggers a retry.
But it's cleaner to have `_parse_json` return sensible defaults for both
call contexts, or have the evaluator use its own parse function.

**Low priority** — the existing retry in evaluator.py handles this gracefully.
No immediate fix needed, but worth noting.

---

### L2 — merger.py RESOLVE_CONFLICT_PROMPT truncates context to 3000 chars

Already noted in H1. The 3000 char limit on each agent's output during conflict
resolution means the resolver sometimes patches based on incomplete information.
Combined fix with H1.

---

### L3 — redis_client.py: no error handling on Upstash connection failure

**File:** `infra/redis_client.py`

`get_redis()` creates the client unconditionally. If `UPSTASH_REDIS_REST_URL`
or `UPSTASH_REDIS_REST_TOKEN` is missing/invalid, the first Redis operation
will throw. This will crash the run at the first `freeze_agent` or `is_frozen`
call.

Currently the system silently depends on Redis being configured. For Phase 2
(hosted deployment), this needs proper error handling and a local dict fallback.
Not urgent for Phase 1 local use.

---

## TEST COVERAGE GAPS

The following scenarios have no tests and should be added before Phase 2:

1. `sub_agent.py run_agent_task` — no unit test exists. The bridge to KimiFlow
   is completely untested. Add a test that mocks `pipeline.invoke` and verifies
   that repair_context is correctly prepended to the task.

2. `main.py resume path` — no test for the checkpoint restoration logic.
   Mock `get_checkpoints` returning 3 agents and assert `run_state["agent_results"]`
   has all 3 restored correctly.

3. `aggregator.py` with mixed preset/output_type — after fix H3, test that
   `output_type=code` with `preset=default` routes to `_aggregate_code`.

4. `repair.py` — no test for evaluator breakdown being included in repair_context
   (after fix H2). Add: mock state with breakdown="Missing endpoint X" and
   weakest=["ag_1"], assert repair_context["ag_1"] contains the breakdown text.

5. `graph.py route_after_eval` — no test for the sentinel score (-1.0) case.
   After fix C1, add: state with system_score=-1.0 should route to "done"
   (skip repair), not "repair".

---

## IMPLEMENTATION ORDER

Fix in this order — each depends on the previous being stable:

**Round 1 — Correctness (do first, they prevent false behavior):**
1. `daedalus/evaluator.py` — C1: sentinel -1.0 on permanent failure
2. `daedalus/graph.py` + `daedalus/repair.py` — C1 companion: guard against sentinel
3. `main.py` — M5: initial system_score = -1.0
4. `daedalus/sub_agent.py` — C2: unified threshold resolution
5. `daedalus/graph.py` + `daedalus/coordinator.py` — H4: same threshold fix in execute_node

**Round 2 — Quality (do second, they improve complex run convergence):**
6. `daedalus/repair.py` — H2: inject evaluator breakdown into repair_context
7. `daedalus/merger.py` — H1: smarter truncation (head+tail), larger limit
8. `daedalus/aggregator.py` — H3: use output_type not preset for routing

**Round 3 — Hygiene (do third, low risk):**
9. `daedalus/planner.py` — M1: saas rule conditional on preset
10. `daedalus/state.py` — M2: update StepResult TypedDict
11. `tests/unit/test_local_coord.py` — M3: rename misleading test

**Round 4 — Tests (do last, validate all the above):**
12. Add all 5 missing test cases listed in TEST COVERAGE GAPS

---

## VERIFICATION AFTER ALL FIXES

Run in order:
```bash
pytest tests/unit/ -v                    # all unit tests must pass
pytest tests/unit/test_evaluator.py -v  # sentinel behavior confirmed
pytest tests/unit/test_repair.py -v     # evaluator breakdown in context confirmed
pytest tests/unit/test_graph.py -v      # sentinel routing confirmed
```

Then run the Elixir chat app benchmark:
```powershell
$start = Get-Date
python main.py "Build a small real-time chat application in Elixir with Phoenix framework. Include user authentication with JWT tokens, authorization roles (admin and regular user), a REST API for message history, and a WebSocket channel for real-time messaging. Admin users can delete any message, regular users can only delete their own." --preset saas
$end = Get-Date
Write-Host "Total time: $(($end - $start).TotalMinutes) minutes"
```

Success criteria vs the previous run (67 min, score 0.68):
- Time: under 45 minutes
- Final score: above 0.80
- Repair passes: 1-2 (was 3, all exhausted)
- No score-0.00 phantom repair triggered by JSON parse failure
- Repair context visible in logs: "CRITICAL: YOUR PREVIOUS OUTPUT HAD INTERFACE CONFLICTS"
- Evaluator breakdown visible in repair context
