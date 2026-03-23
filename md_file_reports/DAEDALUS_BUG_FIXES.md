# DAEDALUS — CODE REVIEW & BUG FIXES
# Read this entire file before touching any code.
# All issues identified by static analysis of the full codebase.

---

## CRITICAL ISSUE 1 — Duplicate Key Error is NOT fixed (mongo_client.py + sub_agent.py)

### Root cause
`insert_checkpoint()` in `infra/mongo_client.py` uses `update_one` with `upsert=True` and `$set`.
This IS correct. But the `data` dict passed from `sub_agent.py` includes `agent_id` as a key:

```python
# sub_agent.py line 80
step_result: StepResult = {
    "agent_id": aid,   # ← THIS IS THE PROBLEM
    "task": task,
    ...
}
await insert_checkpoint(run_id, aid, step_result)
```

And `insert_checkpoint` does:
```python
async def insert_checkpoint(run_id, agent_id, data):
    await get_db().checkpoints.update_one(
        {"run_id": run_id, "agent_id": agent_id},
        {"$set": data},       # data contains agent_id — Mongo allows this on upsert
        upsert=True
    )
```

On a resume run, the checkpoint document ALREADY EXISTS from the previous pass.
`update_one` with `upsert=True` should UPDATE it — this should work.

**So why is E11000 still firing?**

Look at the MongoDB index:
```
run_agent_unique: { run_id: 1, agent_id: 1 } UNIQUE
```

The real bug: when `upsert=True` fails to match any document (because the query
uses `run_id` + `agent_id` as filter), MongoDB tries to INSERT a new document.
But `data` already has `agent_id` as a field — so MongoDB builds a document with
`run_id`, `agent_id` from the filter AND `agent_id` from `$set`. If the index
sees a conflict on the composite key, it throws E11000.

**But the deeper issue is this:** The upsert IS working on the first write.
The E11000 fires because `sub_agent.py` is called TWICE for the same agent_id
within the SAME resume pass — once by LangGraph's `execute_node`, and once by
the inline `GlobalCoordinator` fallback when LangGraph crashes.

Look at `main.py`:
```python
try:
    final_state = await graph.ainvoke(graph_state)  # LangGraph runs agents, writes checkpoints
    ...
except Exception as e:
    # LangGraph crashed AFTER agents already ran and wrote checkpoints
    from daedalus.coordinator import GlobalCoordinator
    coordinator = GlobalCoordinator(run_state, config)
    await coordinator.run()  # Inline coordinator runs the SAME agents AGAIN → E11000
```

The inline coordinator does NOT check `is_frozen()` before running — it checks
Redis, but Redis TTL may have expired or the key was never set properly.

### Fixes required

**Fix 1 — infra/mongo_client.py: make insert_checkpoint truly idempotent**
```python
async def insert_checkpoint(run_id: str, agent_id: str, data: dict):
    # Remove agent_id from data to avoid $set conflict with filter keys
    clean_data = {k: v for k, v in data.items() if k not in ("run_id", "agent_id")}
    clean_data["run_id"] = run_id
    clean_data["agent_id"] = agent_id
    await get_db().checkpoints.update_one(
        {"run_id": run_id, "agent_id": agent_id},
        {"$set": clean_data},
        upsert=True
    )
```

**Fix 2 — main.py: prevent double execution on LangGraph crash**
The inline fallback must NOT re-run agents that already completed in LangGraph.
Add a guard that reloads frozen state from Redis before the fallback runs:

```python
except Exception as e:
    console.print(f"[bold red]LangGraph execution failed: {e}[/bold red]")
    console.print(f"[yellow]Falling back to inline coordinator...[/]")
    
    # CRITICAL: reload run_state from MongoDB so we have latest agent_results
    # and Redis has frozen flags set — inline coordinator will skip completed agents
    try:
        saved = await db.runs.find_one({"_id": run_id})
        if saved:
            run_state.update({k: v for k, v in saved.items() 
                              if k in ("agent_results", "frozen_agents", 
                                       "system_iteration", "repair_attempts")})
    except Exception:
        pass  # Use whatever run_state we have
    
    from daedalus.coordinator import GlobalCoordinator
    ...
```

**Fix 3 — daedalus/coordinator.py: `_run_with_sem` must handle errors from checkpoint write**
Currently, if `insert_checkpoint` throws E11000, the exception propagates up through
`_run_with_sem` and the whole wave fails. Wrap it:

```python
async def _run_with_sem(agent: AgentSpec):
    async with semaphore:
        if is_frozen(self.run_id, agent["agent_id"]):
            console.print(f"  [dim grey]Skipping frozen agent: {agent['agent_id']} (Cached)[/]")
            return
        from daedalus.major_agent import MajorAgent
        major = MajorAgent(agent, self.config, self.state)
        result = await major.run()
        
        if "agent_results" not in self.state:
            self.state["agent_results"] = {}
        self.state["agent_results"][agent["agent_id"]] = result
        
        if result.get("quality_score", 0.0) >= agent.get("threshold", 0.0):
            from infra.redis_client import freeze_agent
            freeze_agent(self.run_id, agent["agent_id"])
```

Note: `sub_agent.py` already calls `insert_checkpoint` internally. The coordinator
doesn't need to call it again. The error is being surfaced FROM sub_agent.py's
checkpoint write — Fix 1 resolves it at the source.

---

## CRITICAL ISSUE 2 — LangGraph crashes because `update_run_status` rejects `"evaluating"` status

`mongo_client.py` has a MongoDB schema validator on the `runs` collection:
```python
"status": {"bsonType": "string", "enum": ["running","done","failed","paused"]}
```

But `coordinator.py` calls:
```python
await update_run_status(self.run_id, "evaluating", self.state)  # NOT in enum
await update_run_status(self.run_id, "repairing", self.state)   # NOT in enum
```

And `main.py` was calling:
```python
await update_run_status(run_id, "completed", ...)   # NOT in enum
```

### Fix — daedalus/coordinator.py: replace invalid statuses
```python
# Line: "evaluating" → "running"
await update_run_status(self.run_id, "running", self.state)

# Line: "repairing" → "running"  
await update_run_status(self.run_id, "running", self.state)
```

Also check `graph.py` for any calls using non-enum statuses and replace with "running".
Valid values are ONLY: `running`, `done`, `failed`, `paused`

---

## CRITICAL ISSUE 3 — Resume reloads stale agent_specs from MongoDB but agent_results is empty

In `main.py` resume path:
```python
run_state = await db.runs.find_one({"run_id": run_id})
```

The `runs` document stores `status` and config snapshot — but NOT the full
`agent_results` from previous passes. This means on resume, `agent_results = {}`
even though agents completed in a prior pass. The frozen Redis flags tell the
coordinator to skip agents, but the aggregator reads from `agent_results` —
which is empty — so the aggregator produces empty output.

### Fix — main.py resume path: restore agent_results from checkpoints
```python
if args.resume:
    run_id = args.resume
    run_state = await db.runs.find_one({"_id": run_id})
    if not run_state:
        run_state = await db.runs.find_one({"run_id": run_id})
    
    if not run_state:
        console.print(f"[bold red]Error: Run {run_id} not found.[/]")
        return
    
    # RESTORE agent_results from checkpoints collection
    checkpoints = await get_db().checkpoints.find({"run_id": run_id}).to_list(None)
    restored_results = {}
    for cp in checkpoints:
        aid = cp.get("agent_id")
        if aid:
            restored_results[aid] = {
                "agent_id": aid,
                "task": cp.get("task", ""),
                "result": cp.get("result", ""),
                "quality_score": cp.get("score", cp.get("quality_score", 0.0)),
                "iterations": cp.get("iterations", 1),
                "status": cp.get("status", "done"),
                "error": cp.get("error"),
            }
    run_state["agent_results"] = restored_results
    console.print(f"[bold blue]Resuming existing run: {run_id}[/]")
    console.print(f"[dim]Restored {len(restored_results)} agent results from checkpoints.[/]")
```

---

## MAJOR ISSUE 4 — local_coordinator.py still uses average not min for scoring

The `_merge_sub_results` method says:
```python
min_score = min(sub_scores) if sub_scores else 0.0
```

This IS correct (min is already there). But check the `status` field:
```python
"status": "done" if all_passed else "partial",
```

`"partial"` is not a valid checkpoint status (enum is `done|failed|frozen`).
When this gets written to MongoDB it may fail validation.

### Fix
```python
"status": "done" if all_passed else "failed",
```

---

## MAJOR ISSUE 5 — Scripts/ folder contains throwaway run-specific files

These files should be deleted — they are one-off patches from the E2E debugging
session and will cause confusion or accidental execution:

```
scripts/fix_mongo.py         ← manually patches MongoDB state for a specific run
scripts/check_frozen.py      ← debug script for run_575a5098 specifically  
scripts/check_mongo.py       ← debug script
scripts/list_runs.py         ← debug script
scripts/assemble_manually.py ← manual assembler bypass for a specific run
test_db.py                   ← loose test file in project root
```

Delete all of these. They are not tests (not in tests/), not utilities (not in infra/),
and they contain hardcoded run IDs that will mislead future debugging.

---

## MAJOR ISSUE 6 — `get_db()` missing `load_dotenv()` in mongo_client.py

`infra/mongo_client.py` does NOT call `load_dotenv()`. If this module is imported
before `main.py` calls `load_dotenv()`, `MONGODB_URI` will be None and the client
will connect to localhost (default), which silently fails.

### Fix — infra/mongo_client.py: add at top
```python
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()  # Add this line

_client: AsyncIOMotorClient | None = None
```

---

## MINOR ISSUE 7 — `update_run_status` has a logic bug with `$setOnInsert`

```python
set_on_insert = {
    "run_id": run_id,
    "started_at": now,
    "goal": state_update.get("goal", "") if state_update else "",
    "preset": state_update.get("preset", "default") if state_update else "default",
}
# Ensure keys in $setOnInsert aren't in $set
for key in list(set_on_insert.keys()) + ["_id"]:
    if key in update_doc:
        del update_doc[key]
```

This removes `goal` and `preset` from `$set` on every call, meaning goal/preset
will never be updated if the document already exists. This is intentional for
`setOnInsert` but means calls like `update_run_status(run_id, "done", final_state)`
won't persist the final state's goal if it changed. Minor but worth noting.

---

## IMPLEMENTATION ORDER

Fix these in exactly this order — each fix unblocks the next:

1. **infra/mongo_client.py** — Fix 1 (clean data before $set) + Fix 6 (load_dotenv)
2. **daedalus/coordinator.py** — Fix 3 (status enum) + error isolation in _run_with_sem  
3. **daedalus/graph.py** — Fix any "evaluating"/"repairing" status strings → "running"
4. **main.py** — Fix 2 (reload state before fallback) + Fix 3 (resume restores agent_results)
5. **daedalus/local_coordinator.py** — Fix status "partial" → "failed"
6. **Delete** all scripts/ files and test_db.py from root

After all fixes, run:
```bash
pytest tests/unit/ -v
```
All 51+ tests must still pass before any new E2E run.

Then run a FRESH run (not resume) with:
```bash
python main.py "Build a simple REST API with health check and echo endpoints" --preset default
```

This should complete cleanly without any E11000 errors, without any LangGraph
crash-to-fallback, and without any MongoDB validation errors.
Only start a SaaS preset run after the default preset run passes clean.
