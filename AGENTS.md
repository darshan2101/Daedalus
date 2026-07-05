# Daedalus — Agent Operating Contract

**Read this first, every session, before touching anything.** This is the shared context for every
agent working this repo (Claude, Gemini, Hermes). Do not drift from the goal or the method below.

## What Daedalus is
A multi-agent LLM orchestration engine (Python + LangGraph). Give it a goal -> an LLM planner decomposes it
into a dependency DAG of specialist agents -> a LangGraph state machine runs them in topological waves
(`execute -> merge -> aggregate -> evaluate -> (repair -> execute)*`) until a weighted quality score clears a
threshold. Multi-provider model waterfall + Redis circuit breaker + Mongo checkpoints.

## Current mission (single north star)
**One clean end-to-end run** = a portfolio-showable demo.
Done = `python main.py "<tiny goal>" --max-depth 1` completes, prints a **real** system score
(not the `-1.0` "not scored" sentinel), and writes a runnable zip to `outputs/builds/<run>.zip`,
with `pytest` still green (baseline ~121 passed / 11 skipped).

Nothing else is in scope until that run is green. No new features, no refactors, no provider additions
that aren't required to close this run.

## Method — do not lapse from these
1. **Evidence-first.** Run it, capture the *real* failure in `PROGRESS.md`, THEN fix the first real blocker.
   Never pre-fix a suspected problem (esp. the "thundering herd" rate-limit) before it actually fires.
2. **One bite per session.** One bite-sized objective; stop when it's done. Don't compound changes.
3. **Branch + PR per session** (`session/NN-<slug>`). Never commit straight to main. Never commit `.env`.
4. **`pytest` stays green.** The 11 skipped tests (`test_week3/5/7`) are intentional empty stubs — leave them.
5. **Log to `PROGRESS.md`.** Append what you ran, what happened, what you changed, what's next. It's the
   resume log across sessions and agents — chat context is disposable, this file is canonical.
6. **Honesty boundary.** Describe what the code *does*, not what it *aspires to*. Full reality audit at
   `F:\Darshan-New\DevTrainnig\my-career-ops\interview-prep\daedalus-reality-audit\`. Known gaps: no verified
   full run yet; "integration tests" are skipped stubs; modular-gen is Go-only. Don't overclaim these.

## Provider policy
- Waterfall lives in `models.py`, per role. It **already** leads with direct-provider sentinels
  (`__cerebras__` -> `__groq__` -> `__nvidia__` -> `__scaleway__`) and puts `openrouter/free` last. Keep it that way.
- **Weighting:** Cerebras primary (fastest, ~unlimited free) -> Groq -> NVIDIA NIM -> Scaleway -> OpenRouter (last resort only).
- **Watch:** `CODER_MODELS` and `CREATIVE_MODELS` lead with an OpenRouter free model. If the coder role 429s on
  the first run, reorder just those two to lead with a direct provider — *then* re-run. Not before.
- **Gemini/Mistral are NOT in the registry** (`kimiflow/agents.py` `_PROVIDER_REGISTRY`). Adding a `__gemini__`
  sentinel (OpenAI-compatible endpoint) is worth it given the Google AI Pro quota — but only if the wired
  providers can't close a run. Evidence-first applies here too.
- Keys are in `.env` (already filled). Var names in `SESSION-01-KICKOFF.md`. Scaleway uses `SCALEWAY_SECRET_KEY`.

## File map
- `main.py` — entry point, CLI, run/resume orchestration.
- `daedalus/graph.py` — LangGraph state machine (live graph = `build_resume_graph`; the plan node is dead on the main path).
- `daedalus/coordinator.py` — inline hand-rolled fallback (duplicates graph phase logic — real tech debt).
- `daedalus/{merger,aggregator,evaluator,repair,assembler,reporter}.py` — the phases.
- `daedalus/circuit_breaker.py`, `infra/redis_client.py`, `infra/mongo_client.py` — infra clients.
- `kimiflow/agents.py` — the 6-role agent system + provider registry + `_call_with_fallback`.
- `models.py` — per-role model waterfalls + provider base URLs/keys.
- `config.yaml` — runtime/threshold/infra config (`-1.0` = not-scored sentinel, distinct from `0.0`).
- `SESSION-01-KICKOFF.md` — session-01 setup + run steps (this session's handoff).

## Scope guardrails
- This repo is a **separate track from career-ops** — no graphify / apply-session / GRAPHIFY_UPDATE ceremony here.
- Env/venv: `.venv` (Python 3.11.15) at repo root. Install: `./.venv/Scripts/python.exe -m pip install -r requirements.txt`.
