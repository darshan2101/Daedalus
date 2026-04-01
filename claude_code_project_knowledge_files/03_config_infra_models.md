# Daedalus — Config, Infra & Models Reference

## config.yaml
```yaml
runtime:
  max_recursion_depth:    5
  max_parallel_major:     3
  max_parallel_sub:       3
  max_system_iterations:  3
  max_repair_attempts:    3
  max_module_iterations:  5      # default — must match sub_agent.py line 72
  plan_review:            false
  use_langgraph:          true
  allow_fragmentation:    true
  max_merger_conflicts:   5
  wave_delay_seconds:     5      # P1 fix — stagger between agent launches in a wave

thresholds:
  system:   0.85
  code:     0.88
  docs:     0.80
  design:   0.75
  research: 0.82
  default:  0.82

evaluation_weights:
  default:
    correctness:   0.30
    completeness:  0.20
    consistency:   0.20
    runnability:   0.20
    format:        0.10
  saas:
    correctness:   0.28
    completeness:  0.20
    consistency:   0.20
    runnability:   0.27
    format:        0.05

infra:
  mongodb_db:              "Daedalus"
  redis_ttl_hours:         48
  checkpoint_every_agent:  true
  ollama_enabled:          true
  ollama_timeout_seconds:  120
  ollama_roles:            [planner, reasoner]

concurrency:
  global_cap:              5
  fallback_semaphore:      true
```

## CLI Flags
```
python main.py "goal"
python main.py --preset saas "goal"
python main.py --resume <run_id>
python main.py --threshold 0.75
python main.py --max-depth 3
python main.py --quiet / --verbose
python main.py --plan-review
```

## Models (models.py)
Sentinel `"__groq__"` → Groq `llama-3.3-70b-versatile`
Sentinel `"openrouter/free"` → OpenRouter free tier

Roles: ORCHESTRATOR_MODELS, CODER_MODELS, REASONER_MODELS, EVALUATOR_MODELS, DRAFTER, CREATIVE, FAST, RESEARCHER

Dead model removed from all lists: `openai/gpt-oss-120b:free` (lines 22, 98, 111)
Active Ollama models: `nemotron-3-super` for planner/reasoner

## MongoDB (motor async)
Collections: `runs`, `checkpoints`, `decision_logs`, `scores`, `registry`
```python
get_db()
insert_checkpoint(run_id, agent_id, data)   # upsert
get_checkpoints(run_id) -> list[dict]
update_run_status(run_id, status, state)
```

## Redis (Upstash REST)
```python
is_frozen(run_id, agent_id) -> bool
freeze_agent(run_id, agent_id)
unfreeze_agent(run_id, agent_id)
```
Fallback: `asyncio.Semaphore` if Upstash unreachable

## Outputs Structure
```
outputs/
  workspace/run_<id>/ag_<id>/output.txt
  workspace/run_<id>/final_code/
  builds/run_<id>.zip
  reports/run_<id>_report.json
```

## Env Vars Required
```
OPENROUTER_API_KEY=sk-or-v1-...
ZAI_API_KEY=...
GROQ_API_KEY=gsk_...
OLLAMA_API_KEY=...
MONGODB_URI=mongodb+srv://...
MONGODB_DB=Daedalus
UPSTASH_REDIS_REST_URL=https://huge-parrot-75854.upstash.io
UPSTASH_REDIS_REST_TOKEN=...
```

## Resume Stress Test — Pass Criteria
- All 5 agents show `Skipping frozen` in log
- `No agents ran — skipping conflict detection` appears
- `No agents ran this pass — preserving existing score` appears
- Total time < 5 minutes
- System score preserved from original run (not reset to 0 or -1)
