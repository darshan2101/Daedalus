# DAEDALUS — SPEED OPTIMIZATION PROMPT
# Paste this entire prompt to Claude Code.
# Phase 1 bugs are fixed. This addresses why runs take hours instead of minutes.

---

## Why Daedalus is slow — root cause analysis

A 2-endpoint REST API taking hours comes from three compounding problems.
Fix all three. Do not skip any.

---

## PROBLEM 1 — Backoff waste: 429s burn 17 seconds per model before moving on

Every model gets 3 attempts at 2s + 5s + 10s = 17 seconds of sleep before giving up.
With 6 models in a waterfall, a fully-rate-limited call wastes up to 102 seconds
before reaching `openrouter/free` which actually works.

Each agent makes 3 waterfall calls (plan, execute, evaluate).
5 agents × 3 calls × 102 seconds worst case = 25+ minutes of pure sleeping.

### Fix — kimiflow/agents.py: reduce backoff on rate limits

```python
# BEFORE
except openai.RateLimitError:
    wait = [2, 5, 10][attempt]

# AFTER — cut to 1s/2s/3s. If a model is rate-limited it stays rate-limited.
# Moving faster to the next model is better than waiting.
except openai.RateLimitError:
    wait = [1, 2, 3][attempt]
    print(f"  [429 — attempt {attempt+1}/3, waiting {wait}s: {model}]")
    last_err = f"429 on {model}"
    time.sleep(wait)
```

Also add: if a model returns 429 on attempt 1, skip the remaining 2 attempts
and move immediately to the next model. 429 on free tier means "you're hitting
the limit" — retrying the same model 3 times almost never helps.

```python
except openai.RateLimitError:
    if attempt == 0:
        # First 429 — skip all retries for this model, move to next
        print(f"  [429 — skipping {model} (rate limited)]")
        last_err = f"429 on {model}"
        break  # Move to next model immediately
    wait = [0, 1, 2][attempt]
    if wait > 0:
        time.sleep(wait)
```

---

## PROBLEM 2 — Wrong model order: the slowest models are tried first

The current waterfall tries the biggest, most rate-limited models first and
reserves the fast reliable ones for last. This is backwards for free-tier usage.

On OpenRouter free tier, the 405B and 480B models are the most aggressively
rate-limited. `openrouter/free` and smaller models respond immediately.

### Fix — models.py: reorder ALL waterfalls — fast reliable first, big models last

**Philosophy:**
- `openrouter/free` and Groq = always available, always fast → go first or second
- Small/medium models (20B-70B) = usually available, fast → go early
- Large models (120B-480B) = often rate-limited → go last as quality upgrade
- Groq (llama-3.3-70b) = ironclad backup, add explicitly at end of every list

```python
# ── ORCHESTRATOR ──────────────────────────────────────────────────────────
# Needs: planning, JSON output, task decomposition
# Strategy: start fast and reliable, escalate to big models only if needed
ORCHESTRATOR_MODELS = [
    "openrouter/free",                             # instant, always works
    "meta-llama/llama-3.3-70b-instruct:free",      # 70B — proven fast + reliable
    "nvidia/nemotron-3-super-120b-a12b:free",      # 120B — good planning
    "nousresearch/hermes-3-llama-3.1-405b:free",   # 405B — best quality, slowest
]

# ── CODER ────────────────────────────────────────────────────────────────
CODER_MODELS = [
    "openrouter/free",                             # instant
    "mistralai/mistral-small-3.1-24b-instruct:free", # 24B — fast, solid code
    "z-ai/glm-4.5-air:free",                       # GLM — fast tool calling
    "nvidia/nemotron-3-super-120b-a12b:free",      # 120B MoE
    "qwen/qwen3-coder:free",                       # 480B — best quality, often slow
]

# ── REASONER ─────────────────────────────────────────────────────────────
REASONER_MODELS = [
    "openrouter/free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "stepfun/step-3.5-flash:free",                 # 196B MoE — surprisingly fast
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
]

# ── DRAFTER ──────────────────────────────────────────────────────────────
DRAFTER_MODELS = [
    "openrouter/free",
    "google/gemma-3-27b-it:free",                  # 27B — fast clean writing
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "meta-llama/llama-3.3-70b-instruct:free",
]

# ── EVALUATOR ────────────────────────────────────────────────────────────
# Evaluation does NOT need the biggest model — it needs reliable JSON output
EVALUATOR_MODELS = [
    "openrouter/free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
]

# ── FAST ─────────────────────────────────────────────────────────────────
# Keep fast models as-is — they're already the right size
# Just put openrouter/free first
FAST_MODELS = [
    "openrouter/free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "google/gemma-3-12b-it:free",
    # ... rest unchanged
]
```

---

## PROBLEM 3 — Merger runs 8 conflict checks in series, each a full waterfall

Every interface conflict gets its own sequential LLM call.
8 conflicts × full waterfall = 8 sequential round trips.
With 3 repair passes, that's 24 sequential merger calls.

### Fix — daedalus/merger.py: run conflict resolutions in parallel

Find the loop that calls `resolve_conflict` for each pair and parallelize it:

```python
# BEFORE (sequential — in detect_and_resolve_all or similar)
for conflict in conflicts:
    resolution = await resolve_conflict(conflict, ...)
    resolved.append(resolution)

# AFTER (parallel)
import asyncio
tasks = [resolve_conflict(c, result_a, result_b, run_id) for c in conflicts]
resolutions = await asyncio.gather(*tasks, return_exceptions=True)
# Filter out exceptions (failed resolutions) gracefully
for i, res in enumerate(resolutions):
    if isinstance(res, Exception):
        print(f"  [dim]Conflict {i} resolution failed: {res}[/]")
    else:
        resolved.append(res)
```

Also: **cap the number of conflicts the merger will process per pass.**
8 conflict checks is excessive for most runs. Add a config limit:

```yaml
# config.yaml
runtime:
  max_merger_conflicts: 3   # Only resolve the 3 most critical conflicts per pass
```

And in merger.py, slice the conflicts list:
```python
max_conflicts = config.get("runtime", {}).get("max_merger_conflicts", 3)
conflicts_to_resolve = conflicts[:max_conflicts]
```

---

## PROBLEM 4 — Groq is not being used as a fast parallel fallback

Groq (llama-3.3-70b) has no meaningful rate limits on the free tier and responds
in 1-3 seconds. It's currently only used as a last resort after ALL OpenRouter
models fail. It should be the second model tried — after `openrouter/free`.

### Fix — kimiflow/agents.py: add Groq to the early waterfall

Add a Groq entry to `_call_with_fallback` by including it as a real model entry,
or add it explicitly as position 2 in every model list in models.py:

```python
# In _call_with_fallback, after the first model fails, try Groq before OpenRouter
# OR, simpler: add a special GROQ sentinel string to model lists

# In models.py — add to each list after openrouter/free:
ORCHESTRATOR_MODELS = [
    "openrouter/free",
    "__groq__",   # sentinel → resolved to Groq call in _call_with_fallback
    "meta-llama/llama-3.3-70b-instruct:free",
    ...
]

# In agents.py _call_with_fallback:
for model in model_list:
    if model == "__groq__":
        try:
            result = _call(GROQ_BASE, GROQ_KEY, GROQ_MODEL, system, user, temperature)
            print(f"  [success: groq/{GROQ_MODEL}]")
            return result
        except Exception as e:
            print(f"  [groq failed: {e}]")
            continue
    # ... existing logic
```

---

## PROBLEM 5 — Complexity assessment adds an extra LLM call for every agent

`major_agent.py` calls `_assess_complexity()` for every agent — this is an extra
LLM call (through the full waterfall) just to decide whether to fragment.

For the orchestrator preset the planner already decides the right agent granularity.
Most tasks should go DIRECT. The complexity check only adds value for genuinely
ambiguous long tasks.

### Fix — major_agent.py: raise the fragmentation threshold

```python
# BEFORE
if len(task) < 200:
    return False, []

# AFTER — skip complexity check for anything under 800 chars
# Most planner-generated tasks are focused enough not to need fragmentation
if len(task) < 800:
    return False, []

# Also: add a config flag to disable fragmentation entirely for speed
if not config.get("runtime", {}).get("allow_fragmentation", True):
    return False, []
```

Add to config.yaml:
```yaml
runtime:
  allow_fragmentation: true   # set false for speed on simple goals
```

---

## Expected impact after all fixes

| Fix | Time saved per run (estimate) |
|---|---|
| Faster backoff (1s/2s/3s + skip on first 429) | 40-60% reduction in wait time |
| Reordered waterfall (fast first) | 50-70% fewer models tried before success |
| Parallel merger conflicts | 8 sequential → 8 parallel (saves ~60s per pass) |
| Groq as position 2 | Near-instant fallback for orchestrator/evaluator |
| Raise fragmentation threshold | Eliminates ~40% of complexity-check LLM calls |

A 2-endpoint REST API should complete in **5-12 minutes** after these fixes,
not hours. The SaaS auth system should be **20-40 minutes**, not hours.

---

## After implementing all fixes

Run a timing test:
```bash
time python main.py "Build a REST API with a health endpoint" --preset default
```

Target: under 10 minutes. If still over 15 minutes, share the full console
output and we'll identify which model is still bottlenecking.

Also add to config.yaml for the timing test:
```yaml
runtime:
  allow_fragmentation: false   # disable for speed benchmark
  max_merger_conflicts: 2
```

## Cleanup reminder
Delete the scripts/ folder if it still exists:
```bash
rm -rf scripts/
```
