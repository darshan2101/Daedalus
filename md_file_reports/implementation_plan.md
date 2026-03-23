# Daedalus — Final Stage: 3 Micro-Phases

The execution engine is complete (Weeks 3-4). The final stage brings the system to a **fully autonomous, deliverable-producing** orchestrator. Split into 3 focused phases so we can ship one at a time.

---

## Phase A — Aggregator `daedalus/aggregator.py`

**What it does:** After all agents pass, merge their individual outputs into one coherent deliverable.

### Rules by `output_type`

| Type | Strategy |
|------|----------|
| `code` | Parse `--- FILE: path ---` blocks from each agent, deduplicate, write to `outputs/workspace/{run_id}/final_code/` |
| `docs` | Concatenate agent outputs in wave order with section headers into one `FINAL.md` |
| `research` | Synthesize via a single LLM call (drafter) over all outputs → `FINAL_REPORT.md` |

### Files
- **[NEW] `daedalus/aggregator.py`** — `aggregate(run_id, state, config) → AggregateResult`
- **[MODIFY] `daedalus/coordinator.py`** — call aggregator after all waves complete
- **[MODIFY] `daedalus/state.py`** — add `combined_result: str` and `output_path: str` fields

### Verification

```bash
# Run a docs goal, confirm FINAL.md is written with all agent sections
python main.py "Design a full-stack SaaS documentation structure" --preset docs
# Then check:
dir outputs\workspace\run_*\FINAL.md
type outputs\workspace\run_*\FINAL.md | head -100
```

---

## Phase B — System Evaluator `daedalus/evaluator.py`

**What it does:** Score the *combined* final output holistically (not per-agent). Writes a `system_score` to MongoDB.

### Logic
- Takes the aggregated `combined_result` + original `goal`
- Single LLM call using `EVALUATOR_MODELS` with a system-wide rubric
- Returns `{ system_score, breakdown, weakest_agents[] }`
- Persists to MongoDB `runs` collection

### Files
- **[NEW] `daedalus/evaluator.py`** — `evaluate_run(run_id, state, config) → EvalResult`
- **[MODIFY] `daedalus/coordinator.py`** — call evaluator after aggregation

### Verification

```bash
python main.py "Design a full-stack SaaS documentation structure" --preset docs
# Check Mongolia for system_score:
python -c "
import asyncio, os
from dotenv import load_dotenv; load_dotenv()
from infra.mongo_client import get_db
async def show():
    db = get_db()
    doc = await db.runs.find_one(sort=[('_id', -1)])
    print('system_score:', doc.get('system_score'))
    print('status:', doc.get('status'))
asyncio.run(show())
"
```

---

## Phase C — Repair Engine `daedalus/repair.py`

**What it does:** If `system_score < threshold`, identify the weakest agents, unfreeze them in Redis, and re-run just those agents.

### Logic
1. Check `system_score` against `config.thresholds.system`
2. If below, pick the bottom-N agents by `quality_score` from `state["agent_results"]`
3. Call `unfreeze_agent(run_id, agent_id)` on each
4. Re-invoke `GlobalCoordinator` for only those agents' sub-graph
5. Re-aggregate and re-evaluate
6. Repeat up to `config.runtime.max_repair_attempts`

### Files
- **[NEW] `daedalus/repair.py`** — `repair_if_needed(run_id, state, config) → RepairResult`
- **[MODIFY] `daedalus/coordinator.py`** — call repair loop after evaluation

### Verification

```bash
# Resume a run that had at least one low-quality agent
python main.py --resume run_XXXXXXXX
# Observe repair loop triggering if system_score < threshold
```

---

## Recommended Order

> **Phase A first** — it's self-contained, immediately useful (produces real output files), and creates the data structures B and C depend on.

## Verification Plan (Phase A — recommended first)

### Automated
```bash
# Import check
python -c "from daedalus.aggregator import aggregate; print('Import OK')"

# Unit test (to be written in tests/unit/test_aggregator.py)
pytest tests/unit/test_aggregator.py -v
```

### Live End-to-End
```bash
python main.py "Design a full-stack SaaS documentation structure" --preset docs
# Expect to see: "FINAL.md written to outputs/workspace/run_XXX/"
dir outputs\workspace\  # confirm FINAL.md exists in latest run folder
```
