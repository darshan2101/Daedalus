# KimiFlow Legacy Archive

These files were part of the original **KimiFlow** leaf-layer pipeline, which predates the Daedalus orchestrator.

They are preserved here for reference but **are no longer imported or executed** by the main Daedalus system.

## Files

| File | Purpose |
|------|---------|
| `agents.py` | 6-role agent system (coder, reasoner, drafter, creative, fast, evaluator) calling OpenRouter + Groq |
| `pipeline.py` | LangGraph `StateGraph` pipeline wiring plan→execute→evaluate→retry |
| `main_kimiflow_backup.py` | Old `main.py` entry point before Daedalus orchestrator |
| `old_task.py` | Earliest scratch task runner |
| `daedalus_mongo_setup.py` | One-time MongoDB collection & schema setup script |

## Current Architecture

The live system now uses:
- `main.py` — Daedalus entry point (planning + coordination)
- `daedalus/planner.py` — Strategic goal decomposition (Ollama Cloud first)
- `daedalus/coordinator.py` — Wave-based parallel agent execution
- `daedalus/sub_agent.py` — Bridge to KimiFlow pipeline (still called internally)
- `infra/` — MongoDB, Redis, workspace helpers

> Note: `sub_agent.py` still invokes the KimiFlow `pipeline` from `_history/kimiflow_legacy/pipeline.py`
> via a relative import. If you remove these files, update the import in `sub_agent.py` accordingly.
