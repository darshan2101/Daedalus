# Daedalus — Session 01 Kickoff (First Clean End-to-End Run)

> Paste-ready context for a fresh chat rooted at `F:\Darshan-New\Daedalus`.
> Goal of this track: get Daedalus **operational — one clean end-to-end run** = a portfolio-showable demo.

## Mission / Definition of Done
`python main.py "<tiny goal>" --max-depth 1` completes and prints a **real** system score
(not the `-1.0` sentinel) + writes a runnable zip to `outputs/builds/<run>.zip`, with `pytest` still green
(baseline ~121 passed / 11 skipped). The 11 skipped are intentional empty stubs (`test_week3/5/7`) — leave them.

## Why it was never done (the real blocker — NOT the code)
- Needs external infra: **MongoDB (Motor)**, **Upstash Redis (REST-specific client)**, **>=1 LLM key**.
- Historical failure = **P1 "thundering herd"**: many agents 429-ing OpenRouter free tier at once.
  - Sidestep, don't fight it: **tiny goal + `--max-depth 1` + default preset** (no Go needed) -> ~2-3 agents, one wave.
- `config.yaml` promises `fallback_semaphore: true` but Redis is still a hard dep in code (`infra/redis_client.py`).

## Current repo state (as of this kickoff)
- Branch created: **`session/01-first-run`** (git `safe.directory` already whitelisted).
- venv created at **`.venv`** (Python 3.11.15). **Deps NOT yet installed** — run:
  `./.venv/Scripts/python.exe -m pip install -r requirements.txt`
- Remote: `github.com/darshan2101/Daedalus`.

## Infra to provide (drop into `F:\Darshan-New\Daedalus\.env` — NEVER paste keys in chat)
Exact env var names (from `models.py` — note `.env.example` is stale on Scaleway):
```
# LLM providers (waterfall already leads with direct providers; openrouter is last-resort)
CEREBRAS_API_KEY=        # weighted primary — fastest, 2.88M RPD, effectively unlimited
GROQ_API_KEY=            # secondary — reliable free tier
NVIDIA_API_KEY=          # NVIDIA NIM — tertiary
SCALEWAY_SECRET_KEY=     # NOTE: SECRET_KEY, not API_KEY
OPENROUTER_API_KEY=      # last-resort auto-router only
OLLAMA_API_KEY=          # optional (Ollama Cloud, planner/reasoner fallback)
# Persistence (user providing real free-tier endpoints)
MONGODB_URI=mongodb+srv://...
MONGODB_DB=Daedalus
UPSTASH_REDIS_REST_URL=https://<db>.upstash.io
UPSTASH_REDIS_REST_TOKEN=
```

## LLM weighting decision (reliability-first)
Waterfall in `models.py` is **already correct**: each role leads with `__cerebras__`/`__groq__`/`__nvidia__`/`__scaleway__`
sentinels; `openrouter/free` is last. **Don't reorder pre-emptively (evidence-first).**
Exception to watch: `CODER_MODELS` and `CREATIVE_MODELS` lead with an *OpenRouter* free model before the direct
providers — if the coder role 429s on the first real run, reorder those two to lead with a direct provider, then re-run.

**NEW capacity (this account):** Google AI Pro -> generous **Gemini** usage; **Hermes agent** available.
Gemini/Mistral are NOT in the provider registry yet (`kimiflow/agents.py` `_PROVIDER_REGISTRY`). Adding a
`__gemini__` sentinel (OpenAI-compatible `generativelanguage.googleapis.com/v1beta/openai/`) and slotting it as a
strong primary is the highest-value enabling edit *if* the free-tier providers can't close a run. Still: **run first, add providers only on evidence.**

## Locked working agreement (from the original initiative)
- **Evidence-first:** run it, capture the *real* failure in `PROGRESS.md` before fixing anything. Do NOT pre-fix the herd.
- **Branch + PR per session** (`session/NN-<slug>`).
- One bite-sized objective per session; `pytest` stays green; append to `PROGRESS.md`; clean up debug scripts.
- Design spec: `docs/superpowers/specs/2026-06-08-daedalus-first-clean-run-design.md`.

## First concrete steps for the new session
1. Confirm `.env` filled (Mongo/Upstash reachable, >=1 LLM key valid).
2. `./.venv/Scripts/python.exe -m pip install -r requirements.txt`
3. `./.venv/Scripts/python.exe -m pytest -q`  -> confirm ~121 passed / 11 skipped baseline.
4. Sanity: quick script hitting one LLM call through the waterfall + a Mongo write + Redis set (prove infra live).
5. `./.venv/Scripts/python.exe main.py "Write a Python function that reverses a string, with a test" --max-depth 1 --preset default`
6. Capture exact outcome/failure -> `PROGRESS.md`. Fix the *first real* blocker only. PR when green.

## Reference (code-grounded reality audit, honest claim boundaries)
Lives in the career-ops repo: `F:\Darshan-New\DevTrainnig\my-career-ops\interview-prep\daedalus-reality-audit\`
(`00-INDEX.md` = honest pitch + 3 reality gaps; `01-how-it-works.md` = end-to-end flow with file:line anchors).
Key architecture facts: LangGraph state machine `execute->merge->aggregate->evaluate->(repair->execute)*`; live graph is
`build_resume_graph` (the plan node is dead code on the main path); `-1.0` = "not scored" sentinel, distinct from `0.0`.

## AGENTS.md note for this repo
This is a separate track from career-ops — **no graphify / apply-session / GRAPHIFY_UPDATE ceremony here.** Keep the
repo's own lightweight AGENTS.md: the working agreement above + the file map + "evidence-first, branch+PR, pytest green."
