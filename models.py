# models.py — full 26-model assignment across 6 roles

import os
from dotenv import load_dotenv
load_dotenv(override=True)

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_KEY  = os.getenv("OPENROUTER_API_KEY")

GROQ_BASE  = "https://api.groq.com/openai/v1"
GROQ_KEY   = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.3-70b-versatile"   # Groq Llama — unbreakable backup

CEREBRAS_BASE  = "https://api.cerebras.ai/v1"
CEREBRAS_KEY   = os.getenv("CEREBRAS_API_KEY")
CEREBRAS_MODEL = "llama3.1-8b"           # Cerebras — 2.88M RPD, effectively unlimited

SCALEWAY_BASE  = "https://api.scaleway.ai/v1"
SCALEWAY_KEY   = os.getenv("SCALEWAY_SECRET_KEY")

NVIDIA_BASE    = "https://integrate.api.nvidia.com/v1"
NVIDIA_KEY     = os.getenv("NVIDIA_API_KEY")

# ── ORCHESTRATOR ──────────────────────────────────────────────────────────────
# Needs: planning, JSON output, task decomposition, delegation
ORCHESTRATOR_MODELS = [
    "__groq__",                                    # primary — Groq llama-3.3-70b direct
    "__nvidia__:meta/llama-3.3-70b-instruct",      # Nvidia NIM 40RPM
    "__scaleway__:llama-3.3-70b-instruct",         # Scaleway burst buffer
    "meta-llama/llama-3.3-70b-instruct:free",      # 70B — proven reliable
    "nvidia/nemotron-3-super-120b-a12b:free",      # 120B — strong reasoning
    "nousresearch/hermes-3-llama-3.1-405b:free",   # 405B — best instruction following
    "openrouter/free",                             # last-resort auto-router
]

# ── CODER / TOOL CALLER ───────────────────────────────────────────────────────
# Needs: code generation, tool calling, API integration, structured output
CODER_MODELS = [
    "z-ai/glm-4.5-air:free",                         # primary — confirmed working
    "__cerebras__:qwen-3-235b-a22b-instruct-2507",   # Cerebras 235B coder
    "__nvidia__:qwen/qwen2.5-coder-32b-instruct",    # Nvidia NIM coder
    "__scaleway__:qwen3-coder-30b-a3b-instruct",     # Scaleway coder
    "__groq__:llama-3.1-8b-instant",                 # Groq fast fallback
    "mistralai/mistral-small-3.1-24b-instruct:free", # reliable Mistral
    "nvidia/nemotron-3-super-120b-a12b:free",        # 120B MoE — solid coding
    "qwen/qwen3-coder:free",                         # 480B MoE — SOTA code generation
    "openrouter/free",                               # last-resort auto-router
]

# ── REASONER ──────────────────────────────────────────────────────────────────
# Needs: multi-step analysis, long context, depth
REASONER_MODELS = [
    "__groq__:llama-3.1-8b-instant",                 # primary — Groq 8B direct (separate RPD)
    "__cerebras__:llama3.1-8b",                      # Cerebras 2.88M RPD fallback
    "__nvidia__:meta/llama-4-maverick-17b-128e-instruct", # Nvidia Maverick
    "__scaleway__:llama-3.1-8b-instruct",            # Scaleway burst
    "meta-llama/llama-3.3-70b-instruct:free",
    "stepfun/step-3.5-flash:free",                   # 196B MoE
    "nvidia/nemotron-3-super-120b-a12b:free",
    "openrouter/free",                               # last-resort auto-router
]

# ── DRAFTER ───────────────────────────────────────────────────────────────────
# Needs: fast reliable text output, writing, summaries
DRAFTER_MODELS = [
    "google/gemma-3-27b-it:free",                    # primary — confirmed working
    "__scaleway__:mistral-small-3.2-24b-instruct-2506", # Scaleway Mistral
    "__scaleway__:llama-3.3-70b-instruct",           # Scaleway Llama
    "__groq__:llama-3.1-8b-instant",                 # Groq fast fallback
    "z-ai/glm-4.5-air:free",                         # GLM — confirmed working
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "openrouter/free",                               # last-resort auto-router
]

# ── CREATIVE ──────────────────────────────────────────────────────────────────
# Needs: imaginative output, expressive writing, brainstorming
CREATIVE_MODELS = [
    "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",  # P1: unique primary
    "__groq__",
    "google/gemma-3-27b-it:free",
    "arcee-ai/trinity-large-preview:free",
    "openrouter/free",                               # last-resort auto-router
]

# ── FAST (triage, simple lookups, short answers) ─────────────────────────────
# Needs: speed, low latency, good enough for trivial tasks
FAST_MODELS = [
    "nvidia/nemotron-3-nano-30b-a3b:free",           # primary — fast nano model
    "__cerebras__:llama3.1-8b",                      # Cerebras 2.88M RPD
    "__scaleway__:llama-3.1-8b-instruct",            # Scaleway burst
    "__groq__:llama-3.1-8b-instant",                 # Groq fast
    "google/gemma-3-12b-it:free",
    "openrouter/free",                               # last-resort auto-router
]

# ── EVALUATOR ─────────────────────────────────────────────────────────────────
# Needs: judgment, critical analysis, scoring
EVALUATOR_MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",        # primary — confirmed evaluator
    "__scaleway__:gpt-oss-120b",                     # Scaleway GPT-OSS
    "__cerebras__:qwen-3-235b-a22b-instruct-2507",   # Cerebras 235B
    "__groq__",                                      # Groq llama-3.3-70b
    "meta-llama/llama-3.3-70b-instruct:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "openrouter/free",                               # last-resort auto-router
]

# ── Ollama Cloud Models ─────────────────────────────────────────────────────
# Accessed via https://ollama.com API — requires OLLAMA_API_KEY
# Used as quality fallback for high-complexity roles only
# Free tier: session + weekly limits apply.
# Model names per /api/tags (no '-cloud' suffix for API access)

OLLAMA_BASE_URL = "https://ollama.com"

OLLAMA_PLANNER_MODELS = [
    "nemotron-3-super",              # 122B — best for agentic reasoning tasks
    "gpt-oss:120b",                  # 120B — strong instruction following
    "qwen3-next:80b",               # 80B — fast fallback
]

OLLAMA_REASONER_MODELS = [
    "deepseek-v3.1:671b",            # 671B — highest quality reasoning
    "cogito-2.1:671b",              # 671B — deep reasoning
    "nemotron-3-super",              # 122B — agentic fallback
]

OLLAMA_CODER_MODELS = [
    "qwen3-coder:480b",              # 480B — strongest coder
    "devstral-2:123b",              # 123B — strong code generation
    "gpt-oss:120b",                  # 120B — general fallback
]