# Daedalus — PROGRESS log

Resume log across sessions/agents. Append-only. Newest at top.

---

## 2026-07-05 — Session 01: First clean end-to-end run ✅ MISSION MET

**Branch:** `session/01-first-run`

### What I ran
1. `./.venv/Scripts/python.exe -m pip install -r requirements.txt` → installed clean.
2. `./.venv/Scripts/python.exe -m pytest -q` → **128 passed, 11 skipped** in 8.14s
   (baseline was ~121; the 11 skipped are the intentional `test_week3/5/7` stubs — untouched).
3. `./.venv/Scripts/python.exe main.py "Write a Python function that reverses a string, with a test" --max-depth 1 --preset default`

### What happened — IT WORKED ON THE FIRST ATTEMPT
- **Real system score: 0.94** (≥ 0.88 threshold → PASS). Not the `-1.0` not-scored sentinel.
- Dimensions: Correctness 0.95, Completeness 1.0, Consistency 0.85, Runnability 0.95, Format 0.95.
- Build zip written: `outputs/builds/run_d142356b.zip` (843 bytes) →
  `requirements.txt`, `app/main.py`, `app/test_string_reversal.py`.
- **No thundering herd.** Single wave, ~1 coder agent. Provider waterfall degraded gracefully:
  - `cerebras` → 404 (model `qwen-3-235b-a22b-instruct-2507` doesn't exist / no access)
  - `nvidia/qwen2.5-coder-32b-instruct` → 410 Gone (EOL 2026-05-12)
  - `scaleway` → 403 FORBIDDEN (insufficient permissions)
  - `groq/llama-3.1-8b-instant` → **success** (coder role)
  - Evaluator + system eval used `nvidia/nemotron-3-super-120b-a12b:free` → success.

### Definition of Done — all green
- [x] `main.py ... --max-depth 1` completes
- [x] prints a real system score (0.94, not -1.0)
- [x] runnable zip in `outputs/builds/<run>.zip`
- [x] `pytest` still green (128 passed / 11 skipped)

### Real (non-blocking) issues observed — evidence for future sessions, do NOT pre-fix
These did NOT block the run (waterfall absorbed them) but are dead weight in the model lists:
- **Cerebras primary model is a 404** — `qwen-3-235b-a22b-instruct-2507` no longer valid. The
  weighted-primary provider is currently always missing on the first try. Worth fixing the model id
  so the fastest provider actually leads.
- **NVIDIA coder model EOL'd** (`qwen/qwen2.5-coder-32b-instruct`, gone 2026-05-12).
- **Scaleway 403** — key present but lacks resource permissions.
- Net: the coder waterfall effectively lands on Groq. Fine for now; run is green.

### Next
- Mission is met — a portfolio-showable clean run exists. Open PR for `session/01-first-run`.
- Optional next bite (evidence-backed, not required for DoD): refresh the dead model ids
  (Cerebras 404, NVIDIA 410) so the intended primary providers actually serve, cutting first-call latency.

### 2026-07-05 — Model ID Refresh Finding (Gemini)
- **Goal**: Find a live free-tier replacement for `z-ai/glm-4.5-air:free` (returns 404).
- **Evidence**: Queried OpenRouter API (`GET https://openrouter.ai/api/v1/models`). Confirmed `qwen/qwen3-coder:free` exists and is live.
- **Proposed Diff** (to apply to `models.py`):
  ```diff
  -    "openrouter/z-ai/glm-4.5-air:free",
  +    "openrouter/qwen/qwen3-coder:free",
  ```
- Note (Claude): Gemini reached the same replacement independently — validates AGENTS.md/GEMINI.md cold-start onboarding.

### 2026-07-05 — Model ID Refresh APPLIED + 429-triggered reorder (Claude)
Method: queried every provider's live `/models` endpoint with the `.env` keys (ground truth for this
account, vs. web guesses). Cerebras/Groq sit behind Cloudflare and 1010-block bare `urllib` — a browser
`User-Agent` gets past it. Scaleway's earlier 403 was a **key mix-up** (Cerebras key pasted into the
Scaleway slot); the corrected key lists 18 models fine.

**Dead ids fixed in `models.py`:**
| Provider | Dead id | Live replacement | Roles |
|---|---|---|---|
| Cerebras | `qwen-3-235b-a22b-instruct-2507` | `gpt-oss-120b` | coder, evaluator |
| Cerebras | `llama3.1-8b` | `gemma-4-31b` | reasoner, fast, `CEREBRAS_MODEL` const |
| NVIDIA | `qwen/qwen2.5-coder-32b-instruct` (410 EOL) | `qwen/qwen3-next-80b-a3b-instruct` | coder |
| Scaleway | `llama-3.1-8b-instruct` (no 8B on Scaleway) | `llama-3.3-70b-instruct` | reasoner, fast |
| OpenRouter | `z-ai/glm-4.5-air:free` (404) | `qwen/qwen3-coder:free` (coder), `qwen/qwen3-next-80b-a3b-instruct:free` (drafter) | coder, drafter |

Cerebras' entire catalog for this account is 3 models: `gemma-4-31b`, `gpt-oss-120b`, `zai-glm-4.7`.

**429-triggered reorder (the documented AGENTS.md trigger finally fired):** after the id fixes, a run
showed `qwen/qwen3-coder:free` **429** (live but rate-limited) — the exact "coder role 429s on first run"
evidence AGENTS.md said to wait for. Per the contract, reordered `CODER_MODELS` + `CREATIVE_MODELS` to
lead with a direct provider (Cerebras / Groq) instead of an OpenRouter free model. Not done pre-emptively.

**Result — fully clean run:** `pytest` 128 passed / 11 skipped. Tiny goal runs with **zero** provider
errors (no 404/410/403/429), coder serves from `cerebras/gpt-oss-120b` on first try, **System score 1.00**,
zip at `outputs/builds/run_18afda38.zip`.

### Next / handoff (session paused on token budget)
- Working tree: `models.py` (modified) + `PROGRESS.md` (new) **staged** on `session/01-first-run` so the
  next agent's ("agy") edits show as unstaged and are reviewable in isolation. Not yet committed/PR'd.
- Deferred by decision (not needed for DoD): add `__gemini__` / `__mistral__` sentinels to the registry
  (both keys work, not yet wired). Revisit after more small-goal runs (auth demo, CV draft).

### 2026-07-05 — Run Validations (Auth Demo & CV Draft)
- **Goal**: Validate that the clean run holds beyond the trivial string-reverse goal.
- **Run 1 (Auth Demo)**: `"Write a Python function that hashes and verifies a password using the stdlib hashlib.scrypt, with a test"`
  - **Result**: Finished successfully.
  - **System Score**: 0.99
  - **Output Zip**: `outputs/builds/run_97b6a64e.zip`
  - **Provider Waterfall**: `scaleway` hit 429 on two models (`mistral-small-3.2-24b-instruct-2506` and `llama-3.3-70b-instruct`). It gracefully fell back to `groq/llama-3.1-8b-instant` for the drafter role. The coder role was served by `cerebras/gpt-oss-120b` with no errors.
- **Run 2 (CV Draft)**: `"Write a Python function that renders a one-page plaintext CV from a dict of name/role/skills/experience, with a test"`
  - **Result**: Finished successfully (required 3 iterations for the coder to pass evaluation).
  - **System Score**: 0.96
  - **Output Zip**: `outputs/builds/run_fb9bf7a5.zip`
  - **Provider Waterfall**: Clean waterfall. The coder role was served perfectly by `cerebras/gpt-oss-120b` for all 3 iterations.
- **Pytest**: `pytest -q` ran clean (128 passed, 11 skipped).
