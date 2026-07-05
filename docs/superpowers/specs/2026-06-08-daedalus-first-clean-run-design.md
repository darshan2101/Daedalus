# Daedalus — Path to First Clean End-to-End Run (Design)

**Date:** 2026-06-08
**Status:** Approved (brainstorming) — pending implementation plan
**Owner:** Darshan
**Context:** Follows the reality audit at `<career-ops>/interview-prep/daedalus-reality-audit/`. That audit found Daedalus is a real, well-architected multi-agent orchestrator that has **never completed a verified end-to-end run** (free-tier rate-limit "thundering herd" was the open blocker; integration tests are skipped stubs). This effort closes that gap.

---

## North star

**Get ONE clean end-to-end run to complete** on a simple goal:

```
python main.py "<tiny goal>"
  → planner runs (real LLM)
  → agents execute in waves (no 429 cascade)
  → merge → aggregate → evaluate → real system score
  → outputs/builds/run_xxxx.zip contains a runnable artifact
```

Success = a real, non-sentinel system score is printed AND a zip with usable files is produced AND `pytest` is still green. This single result converts the audit's biggest "don't claim" into a "safe to claim," and yields a demo.

## Decisions locked (from brainstorming)

1. **Provider budget:** allow **one cheap reliable key** (e.g. a few dollars of OpenRouter credit, or a paid-tier Groq/other key) to prove the loop closes. *Then* harden the free-tier fallback afterward. Story becomes "proved it end-to-end, then made it run on free infra."
2. **Git cadence:** **branch + PR per session** (`session/NN-<slug>`) on `github.com/darshan2101/Daedalus`. Looks professional to a recruiter; keeps history clean.
3. **Strategy:** **evidence-first** — diagnose by running before fixing. Do not pre-fix the thundering herd; reproduce the real failure first.
4. **Track separation:** these Daedalus sessions are independent of the career-ops job-search protocols (no graphify / apply-session / GRAPHIFY_UPDATE ceremony).

## Per-session operating contract

Every session:
1. **One bite-sized objective** — finishable + mergeable in the session.
2. **Branch → work → PR** named `session/NN-<slug>` with a clear writeup.
3. **Test gate** — `pytest` stays green (baseline: 121 passed / 11 skipped) before merge; no regressions.
4. **`PROGRESS.md`** in the repo root — appended each session (what we did, what we learned, what's next). The cheap-resume log; analogous to career-ops apply-session.md.
5. **Cleanup** — no stray debug scripts left behind (Daedalus house Rule 2).

## Roadmap (rough — adjusts per evidence)

| Session | Objective | Flips which audit gap |
|--------|-----------|-----------------------|
| **01** | Boot + smoke baseline: fix git `safe.directory`, confirm remote, create venv + `pip install -r requirements.txt`, load fresh `.env`, run `tests/health/check.py`, attempt one tiny run, **capture the real failure log** in `PROGRESS.md`. No feature work. | — (establishes ground truth) |
| **02** | Pin one reliable primary model + tiny goal + low concurrency (cap 1–2) → **first run that completes** with a real score + zip. | "No verified end-to-end run" |
| **03+** | Harden, one PR each: re-introduce free-tier fallback path; un-stub one integration test (`test_week3_dag`); unify the circuit breaker to wrap all model calls; collapse the duplicated LangGraph/inline execution paths. | Each flips one "don't claim" → "safe to claim" |

## Session 01 scope (concrete, next action)

Prereq: fresh credentials placed by the user directly in `F:\Darshan-New\Daedalus\.env` (never pasted in chat). Required keys per the audit: `OPENROUTER_API_KEY`, `GROQ_API_KEY`, optional `CEREBRAS_API_KEY`/`NVIDIA_API_KEY`/`SCALEWAY_SECRET_KEY`/`OLLAMA_API_KEY`, `MONGODB_URI`, `MONGODB_DB`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`.

Steps:
1. `git config --global --add safe.directory F:/Darshan-New/Daedalus`; confirm `origin` points at `darshan2101/Daedalus`.
2. Create branch `session/01-boot-and-baseline`.
3. Python venv + `pip install -r requirements.txt`.
4. Run `python tests/health/check.py` — record which infra (Mongo/Redis/Ollama/OpenRouter) is reachable.
5. Run `pytest -q` — confirm the 121/11 baseline still holds on this machine.
6. Attempt `python main.py "build a small Go CLI todo app"` (tentative tiny goal — Go matches the modular path; swap if preferred).
7. **Capture the exact failure** (or success) into `PROGRESS.md`; commit; open PR #1.

Outcome of Session 01: a live, evidence-based baseline that replaces the static audit — we know exactly what breaks before we change any logic.

## Constraints / non-goals

- **Not** solving the thundering herd this week — only after we've reproduced it live.
- **Not** deploying (Railway) until a run completes locally.
- **Not** refactoring beyond what an in-progress objective requires.
- Secrets never enter chat or git; `.env` only.

## Open question for Session 01

- Tiny test goal: **Go CLI todo app** (default, exercises the modular/Go path) vs a non-code goal (docs/research preset, avoids the Go toolchain dependency). Decide at session start based on whether Go is installed locally.
