# agents.py — 6-role agent system using all 26 free models
# Fix: _call now guards against None content from openrouter/free

import json
import time
import openai
from models import (
    OPENROUTER_BASE, OPENROUTER_KEY,
    GROQ_BASE, GROQ_KEY, GROQ_MODEL,
    CEREBRAS_BASE, CEREBRAS_KEY, CEREBRAS_MODEL,
    SCALEWAY_BASE, SCALEWAY_KEY,
    NVIDIA_BASE, NVIDIA_KEY,
    ORCHESTRATOR_MODELS, CODER_MODELS, REASONER_MODELS,
    DRAFTER_MODELS, CREATIVE_MODELS, FAST_MODELS, EVALUATOR_MODELS,
)
from daedalus.circuit_breaker import get_health_tracker

# ── File format instruction injected into every coder prompt ─────────────────
FILE_FORMAT_INSTRUCTION = """
CRITICAL OUTPUT FORMAT — you MUST follow this exactly:

For every file in the project, output it using this exact delimiter format:

--- FILE: relative/path/to/file.py ---
<file contents here>
--- END FILE ---

Rules:
- Use forward slashes in paths (e.g. app/main.py, app/auth/router.py)
- Output ALL files needed to run the project
- Do NOT use markdown code fences (no triple backticks)
- Do NOT add any explanation text between files — only the delimiters and content
- After ALL files, you may add a short "## Usage" section in plain text

Example:
--- FILE: app/main.py ---
from fastapi import FastAPI
app = FastAPI()
--- END FILE ---

--- FILE: requirements.txt ---
fastapi>=0.95.0
--- END FILE ---
"""


def _call(base_url, api_key, model, system, user, temperature=0.7):
    """Single model call with None-content guard."""
    client = openai.OpenAI(base_url=base_url, api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    content = resp.choices[0].message.content
    if content is None:
        raise ValueError(f"Model {model} returned None content")
    return content.strip()


_groq_disabled = False
_cerebras_disabled = False
_scaleway_disabled = False
_nvidia_disabled = False

# Provider registry: sentinel prefix → (base_url, api_key, default_model_or_None, disabled_flag_name)
_PROVIDER_REGISTRY = {
    "__groq__":     lambda: (GROQ_BASE,     GROQ_KEY,     GROQ_MODEL,     "_groq_disabled"),
    "__cerebras__": lambda: (CEREBRAS_BASE, CEREBRAS_KEY, CEREBRAS_MODEL, "_cerebras_disabled"),
    "__scaleway__": lambda: (SCALEWAY_BASE, SCALEWAY_KEY, None,           "_scaleway_disabled"),
    "__nvidia__":   lambda: (NVIDIA_BASE,   NVIDIA_KEY,   None,           "_nvidia_disabled"),
}

# Strings that indicate a daily/permanent limit (session-kill)
_DAILY_KILL_STRINGS = ("tokens per day", "TPD", "per day", "daily")

def _is_daily_limit(err_str):
    """Return True if the error string indicates a daily/permanent limit."""
    lower = err_str.lower()
    return any(s.lower() in lower for s in _DAILY_KILL_STRINGS)

import kimiflow.agents as _self  # self-reference for setattr on provider flags

def _call_with_fallback(model_list, system, user, temperature=0.7):
    """Tries each model in order until one works. Raises if all fail.
    Uses exponential backoff: 429 → 1s/2s/3s, other errors → 0.5s/1s/2s.
    Supports direct provider routing via __provider__ and __provider__:model sentinels.
    """
    global _groq_disabled, _cerebras_disabled, _scaleway_disabled, _nvidia_disabled
    last_err = None
    for model in model_list:
        # ── Check if this is a provider sentinel ──
        sentinel_prefix = None
        for prefix in _PROVIDER_REGISTRY:
            if model == prefix or (isinstance(model, str) and model.startswith(prefix + ":")):
                sentinel_prefix = prefix
                break

        if sentinel_prefix is not None:
            base_url, api_key, default_model, flag_name = _PROVIDER_REGISTRY[sentinel_prefix]()
            # Check if provider is disabled for this session
            if getattr(_self, flag_name, False):
                continue
            # Extract model name: __provider__:model or bare → default
            if ":" in model:
                target_model = model.split(":", 1)[1]
            else:
                if default_model is None:
                    # Prefix-only provider with no bare form — skip
                    print(f"  [skipping {model}: no default model for {sentinel_prefix}]")
                    continue
                target_model = default_model
            provider_label = sentinel_prefix.strip("_")
            try:
                print(f"  [trying: {provider_label}/{target_model}]")
                result = _call(base_url, api_key, target_model, system, user, temperature)
                print(f"  [success: {provider_label}/{target_model}]")
                return result
            except openai.RateLimitError as e:
                err_str = str(e)
                if _is_daily_limit(err_str):
                    print(f"  [{provider_label} daily limit on {target_model} — disabling for session]")
                    setattr(_self, flag_name, True)
                else:
                    print(f"  [{provider_label} 429 on {target_model} — skipping]")
                last_err = f"{provider_label} rate limit: {e}"
                continue
            except Exception as e:
                err_str = str(e)
                if _is_daily_limit(err_str):
                    print(f"  [{provider_label} daily limit on {target_model} — disabling for session]")
                    setattr(_self, flag_name, True)
                else:
                    print(f"  [{provider_label} failed: {e}]")
                last_err = f"{provider_label} fail: {e}"
                continue

        for attempt in range(3):  # up to 3 attempts per model before giving up
            try:
                print(f"  [trying: {model}]")
                result = _call(OPENROUTER_BASE, OPENROUTER_KEY,
                               model, system, user, temperature)
                print(f"  [success: {model}]")
                return result
            except openai.NotFoundError:
                print(f"  [404 — skipping: {model}]")
                last_err = f"404 on {model}"
                break  # 404 is permanent for this model — no retry
            except openai.RateLimitError:
                if attempt == 0:
                    # First 429 — skip all retries for this model, move to next
                    print(f"  [429 — skipping {model} (rate limited)]")
                    last_err = f"429 on {model}"
                    break  # Move to next model immediately
                wait = [0, 1, 2][attempt]
                if wait > 0:
                    time.sleep(wait)
            except ValueError as e:
                # None content — no point retrying same model
                print(f"  [null response — skipping: {model}]")
                last_err = str(e)
                break
            except Exception as e:
                wait = [0.5, 1, 2][attempt]
                print(f"  [error on {model} (attempt {attempt+1}/3): {e}]")
                last_err = str(e)
                time.sleep(wait)
        else:
            continue  # all 3 attempts used — move to next model
        # Only reached via `break` (404 or null) — move to next model
        continue
    raise RuntimeError(f"All models failed. Last: {last_err}")


def _parse_json(raw):
    """Extract and parse JSON from a response that may contain markdown.
    Returns a safe default dict if the LLM returns malformed JSON so the
    pipeline retries gracefully instead of crashing.
    """
    try:
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        s = cleaned.find("{")
        e = cleaned.rfind("}") + 1
        if s != -1 and e > 0:
            cleaned = cleaned[s:e]
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"  [_parse_json] WARNING: malformed JSON from model — {exc}")
        print(f"  [_parse_json] Raw snippet: {raw[:200]}")
        # Graceful degradation: low score triggers a fresh retry
        return {
            "score":      0.0,
            "feedback":   "Evaluator/orchestrator returned malformed JSON. Retrying.",
            "retry_with": "drafter",
            "plan":       "Retry the task following the output format instructions exactly.",
            "assigned_model": "drafter",
        }


def _call_with_circuit_breaker(model_list, system, user, temperature=0.7):
    """
    Wrapper that skips models in circuit_open state.
    Calls _call_with_fallback for available models.
    Records success/error to health tracker.
    """
    tracker = get_health_tracker()
    
    for model in model_list:
        if not tracker.can_use_model(model):
            continue
        
        try:
            result = _call_with_fallback([model], system, user, temperature)
            tracker.record_success(model)
            return result
        except Exception as e:
            tracker.record_error(model, str(e))
            continue
    
    raise RuntimeError(f"All models failed.")


# ── ORCHESTRATOR — Hermes 405B first ─────────────────────────────────────────
def orchestrator_plan(task: str) -> dict:
    """
    ORCHESTRATOR ROLE — Decompose goal into modules
    
    CHECKLIST (verify each):
    ☐ Module list is complete (no pieces missing from original goal)
    ☐ Each module has ONE primary responsibility (no compound modules)
    ☐ Dependencies are explicit (module B depends on module A's interface)
    ☐ Success criteria are measurable (not "good" but "TestX passes")
    ☐ Module sequence respects dependencies (can't test user-service without auth gateway first)
    ☐ Assumptions are documented (we assume PostgreSQL, not choose it)
    
    OUTPUT FORMAT (JSON):
    {
      "modules": [...],
      "execution_sequence": [...],
      "assumptions": "..."
    }
    """
    system = (
        "You are the orchestrator of a 5-specialist AI pipeline.\n"
        "Analyse the task and assign it to exactly one specialist:\n"
        "  coder    → any code, APIs, tool calling, technical implementation\n"
        "  reasoner → deep analysis, multi-step logic, research, long documents\n"
        "  drafter  → writing, summaries, emails, reports, structured text\n"
        "  creative → stories, brainstorming, imaginative or open-ended tasks\n"
        "  fast     → trivial tasks, single lookups, yes/no, short answers\n\n"
        "Output ONLY valid JSON, no markdown:\n"
        '{"plan": "<one sentence plan>", "assigned_model": "<specialist>"}'
    )
    raw = _call_with_circuit_breaker(ORCHESTRATOR_MODELS, system, task, temperature=0.2)
    return _parse_json(raw)


# ── CODER — Qwen3-Coder 480B first ───────────────────────────────────────────
def coder_execute(plan: str, task: str, feedback: str = "") -> str:
    """
    CODER ROLE — Build production-ready code modules
    
    CHECKLIST (verify each):
    ☐ All test cases from spec are implemented (no skipped tests)
    ☐ All tests pass (0 failures, 0 errors)
    ☐ Error handling is explicit (not hidden in defer/panic)
    ☐ Code follows language conventions (Go: godoc, no globals, error wrapping)
    ☐ No hardcoded values (use config, flags, or parameters)
    ☐ Test coverage is >80% (most functions have unit tests)
    
    OUTPUT FORMAT (JSON):
    {
      "module": "auth-gateway",
      "status": "complete|partial|failed",
      "test_results": {"total": 4, "passed": 4, "coverage": 87},
      "checklist": {...},
      "files": [...],
      "blockers": [],
      "next_module": "user-service"
    }
    """
    feedback_block = (
        f"\nPREVIOUS ATTEMPT FEEDBACK (address all points below):\n{feedback}\n"
        if feedback else ""
    )
    system = (
        "You are an expert software engineer and tool-calling specialist.\n"
        "Write complete, production-quality, well-commented code.\n"
        "Include error handling and type hints.\n"
        f"Plan: {plan}"
        f"{feedback_block}"
        f"\n{FILE_FORMAT_INSTRUCTION}"
    )
    return _call_with_circuit_breaker(CODER_MODELS, system, task)


# ── REASONER — Hermes 405B first ─────────────────────────────────────────────
def reasoner_execute(plan: str, task: str, feedback: str = "") -> str:
    """
    REASONER ROLE — Validate integration and system design
    
    CHECKLIST (verify each):
    ☐ Data flows are correct (input/output types match across modules)
    ☐ Error handling is consistent (all errors wrapped, context preserved)
    ☐ No circular dependencies (module A doesn't call B which calls A)
    ☐ Performance is reasonable (no obvious N+1, no blocking operations)
    ☐ Security contracts are sound (auth is enforced, secrets not logged)
    ☐ Integration assumptions are documented (what fails if PostgreSQL down?)
    
    OUTPUT FORMAT (JSON):
    {
      "modules_reviewed": ["auth-gateway", "user-service"],
      "integration_status": "complete|partial|failed",
      "data_flows": [...],
      "checklist": {...},
      "risks": [...],
      "next_step": "..."
    }
    """
    feedback_block = (
        f"\nPREVIOUS ATTEMPT FEEDBACK (address all points below):\n{feedback}\n"
        if feedback else ""
    )
    system = (
        "You are a deep analytical thinker. Work through problems step by step.\n"
        "Show your reasoning before your conclusion.\n"
        "Be thorough and precise.\n"
        f"Plan: {plan}"
        f"{feedback_block}"
    )
    return _call_with_circuit_breaker(REASONER_MODELS, system, task)


# ── DRAFTER — Llama 3.3 70B first ────────────────────────────────────────────
def drafter_execute(plan: str, task: str, feedback: str = "") -> str:
    """
    DRAFTER ROLE — Write unit tests and integration tests
    
    CHECKLIST (verify each):
    ☐ Unit tests cover all public functions (no function is untested)
    ☐ Each test is independent (no shared state between tests)
    ☐ Edge cases are covered (empty input, null, boundary values)
    ☐ Error cases are tested (what happens when dependency fails?)
    ☐ README explains module purpose and usage
    ☐ Examples are runnable (copy-paste should work)
    
    OUTPUT FORMAT (JSON):
    {
      "module": "...",
      "test_status": "complete|partial|failed",
      "unit_tests": {...},
      "integration_tests": {...},
      "checklist": {...},
      "files": [...]
    }
    """
    feedback_block = (
        f"\nPREVIOUS ATTEMPT FEEDBACK (address all points below):\n{feedback}\n"
        if feedback else ""
    )
    system = (
        "You are a skilled writer and communicator.\n"
        "Produce clear, well-structured, polished output.\n"
        f"Plan: {plan}"
        f"{feedback_block}"
    )
    return _call_with_circuit_breaker(DRAFTER_MODELS, system, task)


# ── CREATIVE — Dolphin Mistral first ─────────────────────────────────────────
def creative_execute(plan: str, task: str, feedback: str = "") -> str:
    """
    CREATIVE ROLE — Test resilience and edge cases (Chaos engineer)
    
    CHECKLIST (verify each):
    ☐ Database unavailable → module fails gracefully (returns error, not crash)
    ☐ Network timeout → module returns timeout error (not hang forever)
    ☐ Empty/null input → module returns validation error (not crash)
    ☐ Missing secret → module fails at startup (not at runtime)
    ☐ Dependency slow → module has timeout (not freezes)
    ☐ All failures logged with context (not silent failures)
    
    OUTPUT FORMAT (JSON):
    {
      "module": "...",
      "chaos_tests": [...],
      "resilience_score": 0.75,
      "critical_issues": 1,
      "high_issues": 2,
      "next_step": "..."
    }
    """
    feedback_block = (
        f"\nPREVIOUS ATTEMPT FEEDBACK (address all points below):\n{feedback}\n"
        if feedback else ""
    )
    system = (
        "You are an imaginative and creative AI.\n"
        "Think outside the box. Be original, expressive, and engaging.\n"
        f"Plan: {plan}"
        f"{feedback_block}"
    )
    return _call_with_circuit_breaker(CREATIVE_MODELS, system, task)


# ── FAST — Nemotron Nano 30B first ───────────────────────────────────────────
def fast_execute(plan: str, task: str, feedback: str = "") -> str:
    """
    FAST ROLE — Quick health check
    
    CHECKLIST (verify each):
    ☐ Code compiles without errors
    ☐ Tests run (pass or fail, but run)
    ☐ README exists (even if incomplete)
    ☐ No obvious crashes (null pointers, panics caught)
    ☐ Correct language (Go code is in Go, not Python)
    ☐ Purpose is clear (README explains what it does)
    
    OUTPUT FORMAT (JSON):
    {
      "module": "...",
      "health_status": "healthy|degraded|failing",
      "checklist": {...},
      "quick_issues": [],
      "ready_for_review": true,
      "estimated_review_time": "..."
    }
    """
    feedback_block = (
        f"\nPREVIOUS ATTEMPT FEEDBACK (address all points below):\n{feedback}\n"
        if feedback else ""
    )
    system = (
        "Answer quickly and concisely. No padding, no repetition.\n"
        f"Plan: {plan}"
        f"{feedback_block}"
    )
    return _call_with_circuit_breaker(FAST_MODELS, system, task)


# ── GROQ BACKUP — always-on (Groq has no free cap issues) ────────────────────
def groq_draft(plan: str, task: str, feedback: str = "") -> str:
    """Direct Groq call — used as last-resort backup in pipeline."""
    feedback_block = (
        f"\nPREVIOUS ATTEMPT FEEDBACK (address all points below):\n{feedback}\n"
        if feedback else ""
    )
    system = (
        "You are a fast, efficient assistant. Answer clearly and completely.\n"
        f"Plan: {plan}"
        f"{feedback_block}"
        f"\n{FILE_FORMAT_INSTRUCTION}"
    )
    return _call_with_circuit_breaker(["__groq__"], system, task)


# ── EVALUATOR — Hermes 405B first ────────────────────────────────────────────
def evaluator_score(task: str, result: str) -> dict:
    """
    EVALUATOR ROLE — Score components
    
    CHECKLIST (verify each):
    ☐ All tests pass (0 failures, 0 errors)
    ☐ Code follows language conventions (godoc, no globals, etc.)
    ☐ Error handling is explicit (not hidden)
    ☐ No hardcoded values (all parameterized)
    ☐ Documentation is complete (README, examples, gotchas)
    ☐ Coverage >80% (most functions tested)
    
    OUTPUT FORMAT (JSON):
    {
      "module": "...",
      "implementation_score": 0.95,
      "test_score": 1.0,
      "overall_score": 0.95,
      "checklist": {...},
      "feedback": [...],
      "blockers": [],
      "ready_for_integration": true,
      "next_step": "..."
    }
    """
    system = (
        "You are a strict quality evaluator.\n"
        "Score the result 0.0 to 1.0 based on how well it completes the task.\n"
        "CRITICAL: If the task specifies a language or framework (e.g., Rust, Elixir, "
        "Go), the result MUST use that language. Switching languages is an automatic "
        "score of 0.0 regardless of functional correctness.\n"
        "0.85+ means done. Below that, pick the best specialist to retry:\n"
        "  coder / reasoner / drafter / creative / fast\n"
        "IMPORTANT: If the task requires generating files/code, the result MUST contain\n"
        "structured file blocks using '--- FILE: path ---' delimiters to score above 0.5.\n"
        "Output ONLY valid JSON, no markdown:\n"
        '{"score": 0.0, "feedback": "<why>", "retry_with": "<specialist|done>"}'
    )
    raw = _call_with_circuit_breaker(
        EVALUATOR_MODELS,
        system,
        f"Task:\n{task}\n\nResult:\n{result}",
        temperature=0.1,
    )
    return _parse_json(raw)