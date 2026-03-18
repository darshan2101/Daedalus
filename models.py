# models.py — full 26-model assignment across 6 roles

import os
from dotenv import load_dotenv
load_dotenv()

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_KEY  = os.getenv("OPENROUTER_API_KEY")

GROQ_BASE  = "https://api.groq.com/openai/v1"
GROQ_KEY   = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.3-70b-versatile"   # Groq Llama — unbreakable backup

# ── ORCHESTRATOR ──────────────────────────────────────────────────────────────
# Needs: planning, JSON output, task decomposition, delegation
ORCHESTRATOR_MODELS = [
    "nousresearch/hermes-3-llama-3.1-405b:free",  # 405B — best instruction following
    "nvidia/nemotron-3-super-120b-a12b:free",      # 120B MoE — strong reasoning
    "openai/gpt-oss-120b:free",                    # 120B — excellent structured output
    "minimax/minimax-m2.5:free",                   # large MoE — agentic specialist
    "meta-llama/llama-3.3-70b-instruct:free",      # 70B — reliable workhorse
    "openrouter/free",                             # auto-router safety net
]

# ── CODER / TOOL CALLER ───────────────────────────────────────────────────────
# Needs: code generation, tool calling, API integration, structured output
CODER_MODELS = [
    "qwen/qwen3-coder:free",                         # 480B MoE — SOTA code generation
    "openai/gpt-oss-120b:free",                      # 120B — strong tool use
    "z-ai/glm-4.5-air:free",                         # GLM — native tool calling
    "nvidia/nemotron-3-super-120b-a12b:free",        # 120B MoE — solid coding
    "mistralai/mistral-small-3.1-24b-instruct:free", # reliable Mistral
    "openrouter/free",
]

# ── REASONER ──────────────────────────────────────────────────────────────────
# Needs: multi-step analysis, long context, depth
REASONER_MODELS = [
    "nousresearch/hermes-3-llama-3.1-405b:free",    # 405B — deepest reasoning
    "nvidia/nemotron-3-super-120b-a12b:free",        # 120B MoE
    "minimax/minimax-m2.5:free",                     # large MoE, long context
    "qwen/qwen3-next-80b-a3b-instruct:free",         # 80B Qwen3 Next
    "stepfun/step-3.5-flash:free",                   # 196B MoE
    "meta-llama/llama-3.3-70b-instruct:free",        # reliable 70B
    "openrouter/free",
]

# ── DRAFTER ───────────────────────────────────────────────────────────────────
# Needs: fast reliable text output, writing, summaries
DRAFTER_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",        # 70B — proven reliable
    "mistralai/mistral-small-3.1-24b-instruct:free", # 24B — clean output
    "google/gemma-3-27b-it:free",                    # 27B — Google quality
    "openai/gpt-oss-20b:free",                       # 20B — fast GPT-OSS
    "openrouter/free",
]

# ── CREATIVE ──────────────────────────────────────────────────────────────────
# Needs: imaginative output, expressive writing, brainstorming
CREATIVE_MODELS = [
    "cognitivecomputations/dolphin-mistral-24b-venice-edition:free", # unconstrained creative
    "arcee-ai/trinity-large-preview:free",           # Arcee creative model
    "google/gemma-3-27b-it:free",                    # expressive writing
    "minimax/minimax-m2.5:free",                     # broad knowledge base
    "openrouter/free",
]

# ── FAST (triage, simple lookups, short answers) ─────────────────────────────
# Needs: speed, low latency, good enough for trivial tasks
FAST_MODELS = [
    "nvidia/nemotron-3-nano-30b-a3b:free",           # 30B MoE — fast nano
    "google/gemma-3-12b-it:free",                    # 12B — Google reliable
    "nvidia/nemotron-nano-12b-v2-vl:free",           # 12B vision+text
    "nvidia/nemotron-nano-9b-v2:free",               # 9B ultra-fast
    "arcee-ai/trinity-mini:free",                    # small Arcee
    "qwen/qwen3-4b:free",                            # 4B Qwen3
    "google/gemma-3-4b-it:free",                     # 4B Gemma
    "google/gemma-3n-e4b-it:free",                   # 4B Gemma-N
    "google/gemma-3n-e2b-it:free",                   # 2B lightning
    "liquid/lfm-2.5-1.2b-instruct:free",             # 1.2B ultra-fast
    "liquid/lfm-2.5-1.2b-thinking:free",             # 1.2B with light reasoning
    "openrouter/free",
]

# ── EVALUATOR ─────────────────────────────────────────────────────────────────
# Needs: judgment, critical analysis, scoring
EVALUATOR_MODELS = [
    "nousresearch/hermes-3-llama-3.1-405b:free",    # 405B — best judge
    "nvidia/nemotron-3-super-120b-a12b:free",        # 120B — strong critic
    "openai/gpt-oss-120b:free",                      # 120B — reliable scoring
    "minimax/minimax-m2.5:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "openrouter/free",
]