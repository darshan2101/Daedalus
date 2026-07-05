# Daedalus

## What it is
Daedalus is a multi-agent LLM orchestration engine. Give it a goal, an LLM planner decomposes it into a dependency DAG of specialist agents, a LangGraph state machine runs them in topological waves, and a bounded repair loop retries until a weighted quality score clears a configurable threshold. Output is packaged as a reproducible build zip.

Stack: Python, LangGraph, LangChain-compatible model calling, async subprocess execution.

## What it actually does right now
- End-to-end run: `python main.py "<goal>" --max-depth 1`
- Real evaluator override: `runnability` is computed from `py_compile`, module import, and optional `pytest`, not LLM opinion
- Repair cap: bounded repair attempts so small goals don’t spawn unbounded loops
- Checkpoints: Mongo-backed run state with Redis circuit breaker fallbacks
- Provider waterfall: role-ranked LLM routing with fallback and rate-limit handling

## Verified state
- Pytest: `131 passed, 11 skipped`
- Clean end-to-end run confirmed with real system score and zipped build output

## Commands
```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe main.py "Write a Python function that reverses a string, with a test" --max-depth 1
```

## Key files
- `main.py` — entry point and CLI
- `daedalus/graph.py` — LangGraph state machine
- `daedalus/evaluator.py` — scoring, threshold gating, runnability override
- `daedalus/runnability_runner.py` — static + import + test execution checker
- `daedalus/merger.py`, `aggregator.py`, `repair.py`, `assembler.py`, `reporter.py` — pipeline phases
- `daedalus/circuit_breaker.py`, `infra/redis_client.py`, `infra/mongo_client.py` — infra
- `kimiflow/agents.py` — role registry + provider fallback
- `models.py` — per-role model waterfall and provider config
- `config.yaml` — thresholds, weights, runtime bounds, presets

## Config shape
- Thresholds: default/system/preset-specific in `config.yaml`
- Evaluation weights: dimensional scoring configured per preset
- Runtime bounds: max recursion, parallel caps, repair attempts, wave delays
- Infra: Mongo DB name, Redis TTL, checkpoint policy, Ollama toggle/timeout/roles

## Current focus
One verified portfolio-ready end-to-end run. No overclaimed capabilities.
