# agents.py — 6-role agent system using all 26 free models
# Fix: _call now guards against None content from openrouter/free

import json
import time
import openai
from models import (
    OPENROUTER_BASE, OPENROUTER_KEY,
    GROQ_BASE, GROQ_KEY, GROQ_MODEL,
    ORCHESTRATOR_MODELS, CODER_MODELS, REASONER_MODELS,
    DRAFTER_MODELS, CREATIVE_MODELS, FAST_MODELS, EVALUATOR_MODELS,
)

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


def _call_with_fallback(model_list, system, user, temperature=0.7):
    """Tries each model in order until one works. Raises if all fail.
    Uses exponential backoff: 429 → 2s/5s/10s, other errors → 0.5s/1s/2s.
    """
    last_err = None
    for model in model_list:
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
                wait = [2, 5, 10][attempt]
                print(f"  [429 — attempt {attempt+1}/3, waiting {wait}s: {model}]")
                last_err = f"429 on {model}"
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


# ── ORCHESTRATOR — Hermes 405B first ─────────────────────────────────────────
def orchestrator_plan(task: str) -> dict:
    """
    Analyses the task and returns:
      {"plan": str, "assigned_model": "coder|reasoner|drafter|creative|fast"}
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
    raw = _call_with_fallback(ORCHESTRATOR_MODELS, system, task, temperature=0.2)
    return _parse_json(raw)


# ── CODER — Qwen3-Coder 480B first ───────────────────────────────────────────
def coder_execute(plan: str, task: str, feedback: str = "") -> str:
    """Qwen3-Coder 480B → GPT-OSS 120B → GLM → Nemotron → Mistral → auto"""
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
    return _call_with_fallback(CODER_MODELS, system, task)


# ── REASONER — Hermes 405B first ─────────────────────────────────────────────
def reasoner_execute(plan: str, task: str, feedback: str = "") -> str:
    """Hermes 405B → Nemotron 120B → MiniMax → Qwen3-Next 80B → StepFun → Llama 70B → auto"""
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
    return _call_with_fallback(REASONER_MODELS, system, task)


# ── DRAFTER — Llama 3.3 70B first ────────────────────────────────────────────
def drafter_execute(plan: str, task: str, feedback: str = "") -> str:
    """Llama 70B → Mistral Small → Gemma 27B → GPT-OSS 20B → auto"""
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
    return _call_with_fallback(DRAFTER_MODELS, system, task)


# ── CREATIVE — Dolphin Mistral first ─────────────────────────────────────────
def creative_execute(plan: str, task: str, feedback: str = "") -> str:
    """Dolphin Mistral 24B → Arcee Trinity → Gemma 27B → MiniMax → auto"""
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
    return _call_with_fallback(CREATIVE_MODELS, system, task)


# ── FAST — Nemotron Nano 30B first ───────────────────────────────────────────
def fast_execute(plan: str, task: str, feedback: str = "") -> str:
    """Nemotron Nano 30B → Gemma 12B → Nemotron 12B → ... → 1.2B → auto"""
    feedback_block = (
        f"\nPREVIOUS ATTEMPT FEEDBACK (address all points below):\n{feedback}\n"
        if feedback else ""
    )
    system = (
        "Answer quickly and concisely. No padding, no repetition.\n"
        f"Plan: {plan}"
        f"{feedback_block}"
    )
    return _call_with_fallback(FAST_MODELS, system, task)


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
    return _call(GROQ_BASE, GROQ_KEY, GROQ_MODEL, system, task)


# ── EVALUATOR — Hermes 405B first ────────────────────────────────────────────
def evaluator_score(task: str, result: str) -> dict:
    """
    Returns:
      {"score": float 0-1, "feedback": str, "retry_with": "coder|reasoner|drafter|creative|fast|done"}
    """
    system = (
        "You are a strict quality evaluator.\n"
        "Score the result 0.0 to 1.0 based on how well it completes the task.\n"
        "0.85+ means done. Below that, pick the best specialist to retry:\n"
        "  coder / reasoner / drafter / creative / fast\n"
        "IMPORTANT: If the task requires generating files/code, the result MUST contain\n"
        "structured file blocks using '--- FILE: path ---' delimiters to score above 0.5.\n"
        "Output ONLY valid JSON, no markdown:\n"
        '{"score": 0.0, "feedback": "<why>", "retry_with": "<specialist|done>"}'
    )
    raw = _call_with_fallback(
        EVALUATOR_MODELS,
        system,
        f"Task:\n{task}\n\nResult:\n{result}",
        temperature=0.1,
    )
    return _parse_json(raw)