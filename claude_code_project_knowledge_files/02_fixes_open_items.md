# Daedalus — Fixes Applied & Open Items

## Test Suite Baseline
**87 passed, 11 skipped** — verified baseline as of last zip review.
Full suite command: `python -m pytest tests/ -v --tb=short` (never just `tests/unit/`)

Key test files:
- `tests/unit/test_phase2b_fixes.py` — 6 tests (recursion formula, default safety, epsilon, 3x patch prevention)
- `tests/unit/test_merger.py` — 11 tests including O4 (skips resolved pairs)
- `tests/integration/test_resume.py` — resume restoration

---

## All Fixes Applied and Verified (Code-Confirmed in Zip)

| Fix | File | Location | Status |
|-----|------|----------|--------|
| Bug 1: Recursion formula `1+(max_retries*2)+3` | `sub_agent.py` | line 88 | ✅ Zip verified |
| Bug 1b: Default value `max_module_iterations=5` | `sub_agent.py` | line 72 | ✅ Zip verified |
| Bug 2: Threshold epsilon `score >= threshold - 0.005` | `graph.py` | route_after_eval | ✅ Zip verified |
| Bug 3: Patch validation two separate guards | `merger.py` | — | ✅ Zip verified |
| N1: Agent freeze on resume | `main.py` | — | ✅ Zip verified |
| N2: JSON sanitization `_sanitize_json_escapes()` | `merger.py` | line 17 | ✅ Code present, live unverified |
| N3: Score preservation on resume | `main.py` | lines 183, 204 | ✅ Code present, live unverified |
| N4: Merger gate on `any_agent_ran` | `graph.py` | merge_node | ✅ Live run verified |
| O4: Skip re-detecting resolved conflicts from DB | `merger.py` | detect_and_resolve_all | ✅ Zip + test verified |
| Dead model removed: `openai/gpt-oss-120b:free` | `models.py` | lines 22, 98, 111 all removed | ✅ Verified |

---

## Open Items — Current Status

| ID | Issue | Status |
|----|-------|--------|
| **P1** | OpenRouter thundering herd / rate limit saturation | **IN PROGRESS — ACTIVE BLOCKER** |
| N2 | JSON sanitization — code present, never triggered in live run | Needs full run |
| N3 | Score preservation — needs run with successful evaluation | Needs full run |
| O3 | Bug 2 epsilon — evaluation never completed near boundary | Needs full run |
| UX1 | `System score: 0.00` display when sentinel is -1.0 | Backlog |

---

## P1 — Active Investigation Detail (DO NOT SKIP)

**Root cause confirmed:** All agents launch in `asyncio.gather` simultaneously ("thundering herd"). All request the same model at T=0, saturating per-model rate limit buckets instantly.

**Approved plan — two changes only:**

**Change 1: Model de-synchronization (`models.py`)**
Assign a unique primary model per role so parallel agents hit different rate limit buckets.
Agent must FIRST produce an evidence table from recent run logs — count `[success: X]` and `[429 — skipping X]` per model — before proposing any model assignments. No code until evidence table is reviewed and approved.

**Change 2: Wave stagger (`coordinator.py` + `config.yaml`)**
- Add `wave_delay_seconds: 5` to `config.yaml` under `runtime:`
- In `coordinator.py` wave execution loop: `await asyncio.sleep(config.get("runtime", {}).get("wave_delay_seconds", 0))` between individual agent task creations within a wave (not between waves)
- Must be `asyncio.sleep` not `time.sleep`

**Files to touch for P1:** `models.py`, `config.yaml`, `coordinator.py` ONLY.

**Sequence:** Evidence table → review → model assignment diff → review → coordinator.py stagger diff → review → full test suite → fresh Elixir benchmark run (full log, not summary)

That benchmark run will also verify N2, N3, O3 if evaluation completes.

---

## Phase 1 Close Criteria (before Railway deployment)

Phase 1 does not close until ALL of:
1. P1 implemented, fresh full run completes without rate-limit cascade failure
2. That run produces a valid system score (evaluation completes successfully)
3. N2, N3, O3 verified by that run's log
4. Resume stress test: all 5 agents frozen, score preserved, time under 5 minutes

---

## Agent Behaviour Patterns to Watch For

- **Fabricating verification:** Claims a fix is verified when the log never exercised the code path. Check whether the relevant log line actually appears.
- **Wrong patch target:** Previously patched `infra.mongo_client.get_db` instead of `daedalus.merger.get_db`. Rule: patch where the name is used, not where it's defined.
- **Unit-only test runs:** Agent submits `tests/unit/` results instead of full `tests/`. Always require full suite.
- **Wrong file for thundering herd:** `local_coordinator.py` handles sub-agent fragmentation. Wave-level parallel launch is in `coordinator.py`. Do not repeat the wrong-file mistake.
- **Text claims without diffs:** Rejected. Every claimed change requires diff shown or zip uploaded.
- **Reactive cleanup:** Cleanup is proactive, before commencing next task. Not after being reminded.
