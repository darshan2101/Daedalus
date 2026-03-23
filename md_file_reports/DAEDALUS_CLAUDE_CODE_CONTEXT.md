# DAEDALUS — CLAUDE CODE IMPLEMENTATION CONTEXT
### Read this entire file before writing a single line of code.

---

## ━━━ SECTION 0 · WHO YOU ARE AND WHAT THIS IS ━━━

You are implementing **Daedalus** — a self-spawning hierarchical multi-agent
orchestrator built on top of an existing system called KimiFlow.

The vision: a user gives a goal ("Build a SaaS app with JWT auth"), and Daedalus
autonomously plans it into a DAG of major tasks, spawns agents at runtime, those
agents spawn sub-agents if needed, every output is evaluated on 5 dimensions,
failures are surgically repaired, and the final output is a production-quality
multi-file artifact.

---

## ━━━ SECTION 1 · NAMING — READ THIS FIRST ━━━

### The project is called DAEDALUS. Not KimiFlow. Not testKimiClaw.

**CRITICAL naming rules — apply everywhere without exception:**

| Wrong (old) | Correct (new) |
|---|---|
| `testKimiClaw` | `Daedalus` |
| `KimiFlow orchestrator` | `Daedalus` |
| `d:\Dev\testKimiClaw\` | `d:\Dev\Daedalus\` |
| Any `kimi` prefix in new files | Use `daedalus` prefix |

**What to keep:** The existing files `pipeline.py`, `agents.py`, `models.py` are
the KimiFlow leaf executor layer — they are UNCHANGED and keep their filenames.
Only new files and the rewritten `main.py` use the Daedalus naming.

**The GitHub repo is:** `github.com/darshan2101/Daedalus`
**The project root is:** `d:\Dev\Daedalus\`
**The MongoDB database is:** `Daedalus`
**The Upstash Redis database is:** `Daedalus` (huge-parrot-75854.upstash.io)

---

## ━━━ SECTION 2 · THREE CRITICAL TECHNICAL ISSUES TO FIX ━━━

These were identified during architectural review. Address all three before
or during implementation — do not skip them.

---

### ISSUE 1 · Windows Event Loop + nest_asyncio (Week 1, main.py)

**Problem:** On Windows with `ProactorEventLoop`, calling `asyncio.run()` inside
a LangGraph node that itself was invoked via `asyncio.run()` causes a
"This event loop is already running" error. Additionally, LangGraph's internal
machinery sometimes creates its own event loop which conflicts.

**Fix — add to the very top of `main.py` before any other imports:**

```python
# main.py — TOP OF FILE, before all other imports
import sys
import asyncio

# Windows ProactorEventLoop fix — must be set before any asyncio usage
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# nest_asyncio allows asyncio.run() calls inside already-running loops
# Required for LangGraph nodes calling async code on Windows
import nest_asyncio
nest_asyncio.apply()
```

**Add to requirements.txt:**
```
nest_asyncio>=1.6.0
```

**Why this works:** `nest_asyncio` patches the event loop to allow nested
`asyncio.run()` calls. This is the standard solution for LangGraph + async
on Windows. It has zero effect on non-Windows platforms.

---

### ISSUE 2 · Redis TTL — No Wildcard EXPIRE (infra/redis_client.py)

**Problem:** The plan mentions `EXPIRE run:{run_id}:* {ttl_seconds}` —
Redis does NOT support wildcard key expiry. This will silently fail.

**Fix — two-part solution:**

**Part A:** Set `ex=ttl_seconds` on EVERY key write:

```python
TTL_SECONDS = config["infra"]["redis_ttl_hours"] * 3600  # default: 48 * 3600

# Every SET/HSET must include ex= parameter:
redis.set(f"run:{run_id}:sem", 0, ex=TTL_SECONDS)
redis.hset(f"run:{run_id}:modules", mapping={agent_id: "active"})
redis.expire(f"run:{run_id}:modules", TTL_SECONDS)  # hset doesn't support ex=, use expire after
```

**Part B:** Maintain a key registry list per run, expire it at the end:

```python
# In redis_client.py — track all keys for a run
def register_key(run_id: str, key: str, ttl: int):
    """Register a key and set its TTL. Called after every key creation."""
    redis.sadd(f"run:{run_id}:_keys", key)
    redis.expire(key, ttl)
    redis.expire(f"run:{run_id}:_keys", ttl)

def expire_run(run_id: str, ttl_hours: int):
    """Called at run completion — refresh TTL on all tracked keys."""
    ttl = ttl_hours * 3600
    keys = redis.smembers(f"run:{run_id}:_keys") or set()
    for key in keys:
        redis.expire(key, ttl)
    redis.expire(f"run:{run_id}:_keys", ttl)
```

**Key operations that need TTL set individually:**
- `run:{run_id}:sem` → set on creation
- `run:{run_id}:modules` → expire after hset
- `run:{run_id}:sys_iter` → expire after incr  
- `run:{run_id}:agent:{agent_id}:iter` → expire after incr
- `run:{run_id}:agent:{agent_id}` → expire after hset
- `run:{run_id}:queue` → expire after lpush

---

### ISSUE 3 · asyncio.to_thread Bridge Safety (Week 3, sub_agent.py)

**Problem:** `asyncio.to_thread(pipeline.invoke, ...)` runs KimiFlow's
synchronous LangGraph pipeline in a thread pool. This is correct. However,
LangGraph's `StateGraph.invoke()` internally uses `asyncio.get_event_loop()`
in some versions, which will find no loop in the thread context and crash.

**Fix — wrap the pipeline call defensively:**

```python
# sub_agent.py / major_agent.py
import asyncio
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=8)

async def _call_kimiflow(self, state: dict) -> dict:
    """
    Bridge: runs synchronous KimiFlow pipeline.invoke in a thread pool.
    The thread gets its own event loop to prevent LangGraph from finding none.
    """
    def _run_in_thread(state):
        # Give the thread its own event loop (required for LangGraph internals)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            from pipeline import pipeline
            return pipeline.invoke(state, {"recursion_limit": 100})
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    return await asyncio.get_event_loop().run_in_executor(
        _executor, _run_in_thread, state
    )
```

**Why not `asyncio.to_thread`?** `asyncio.to_thread` is a convenience wrapper
for `run_in_executor` but doesn't give the thread its own event loop.
`run_in_executor` with the explicit `_run_in_thread` function that sets up
its own loop is the safe version.

---

## ━━━ SECTION 3 · EXISTING CODEBASE (DO NOT MODIFY THESE) ━━━

The following files exist and are the KimiFlow leaf executor layer.
**Do not modify them.** Daedalus wraps them — it does not replace them.

```
d:\Dev\Daedalus\
├── pipeline.py      ← LangGraph StateGraph: plan→execute→evaluate nodes
├── agents.py        ← All agent logic: _call(), _call_with_fallback(), specialists
├── models.py        ← Model lists per role, API keys from .env
├── main.py          ← WILL BE REWRITTEN by Daedalus (keep backup as main_kimiflow.py)
├── .env             ← Already has all credentials (see Section 4)
├── .env.example     ← Safe template, committed to git
├── .gitignore       ← .env is gitignored
└── requirements.txt ← Extend, don't replace
```

**KimiFlow's pipeline contract (what SubAgent calls):**
```python
# Input state dict:
state = {
    "task":           str,   # The task description
    "plan":           str,   # Can be empty string ""
    "assigned_model": str,   # specialist role: "coder|reasoner|drafter|creative|fast"
    "result":         str,   # Empty string ""
    "quality_score":  float, # 0.0
    "feedback":       str,   # Previous iteration feedback (empty on first call)
    "iterations":     int,   # 0
    "history":        list,  # [] on first call
}

# Output state dict (what pipeline.invoke returns):
result = {
    ...same fields...,
    "result":        str,    # The generated output
    "quality_score": float,  # Final score 0.0-1.0
    "feedback":      str,    # Evaluator feedback
    "iterations":    int,    # How many iterations it took
}
```

**The 6 specialist roles (from agents.py):**
- `coder` — Qwen3-Coder 480B first (code, APIs, tool calling)
- `reasoner` — Hermes 405B first (deep analysis, long docs)
- `drafter` — Llama 3.3 70B first (writing, summaries, reports)
- `creative` — Dolphin Mistral 24B first (stories, brainstorming)
- `fast` — Nemotron Nano 30B first (trivial / short answers)
- `researcher` — researcher waterfall
- Each has a waterfall of 4-12 free OpenRouter models + Groq fallback

---

## ━━━ SECTION 4 · INFRASTRUCTURE CREDENTIALS ━━━

All credentials are already in `.env`. The keys are:

```bash
# Existing (KimiFlow)
OPENROUTER_API_KEY=...
GROQ_API_KEY=...

# Daedalus Phase 1 additions (already added)
MONGODB_URI=mongodb+srv://darshan:...@cluster0.pidly.mongodb.net/
MONGODB_DB=Daedalus
UPSTASH_REDIS_REST_URL=https://huge-parrot-75854.upstash.io
UPSTASH_REDIS_REST_TOKEN=gQAAAA...

# Phase 2 placeholders (leave as-is for now)
MODAL_TOKEN_ID=
MODAL_TOKEN_SECRET=
CLOUDFLARE_R2_ACCESS_KEY=
CLOUDFLARE_R2_SECRET_KEY=
CLOUDFLARE_R2_BUCKET=
```

**Services status:**
- MongoDB Atlas M0 → Cluster0 → `Daedalus` database ✅ connected
- Upstash Redis → `huge-parrot-75854` → `Daedalus` database ✅ connected  
- GitHub → `darshan2101/Daedalus` ✅ pushed
- Modal.com → account ready, Phase 2 only
- Cloudflare R2 → account ready, Phase 2 only

---

## ━━━ SECTION 5 · MONGODB SETUP — RUN THIS FIRST ━━━

**Before implementing anything, run this setup script to create all 8
collections with proper schemas and indexes.**

Save as `daedalus_mongo_setup.py` in the project root and run:
```bash
pip install pymongo python-dotenv
python daedalus_mongo_setup.py
```

```python
"""
Daedalus — MongoDB Atlas Setup Script
Run once to create all collections, indexes, and validation schemas.
"""

import os
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import CollectionInvalid

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB  = os.getenv("MONGODB_DB", "Daedalus")

if not MONGODB_URI:
    raise ValueError("MONGODB_URI not found in .env")

client = MongoClient(MONGODB_URI)
db     = client[MONGODB_DB]

print(f"\n Daedalus MongoDB Setup — {MONGODB_DB}")
print("-" * 52)

def create_collection(name, validator=None):
    try:
        db.create_collection(name, validator=validator) if validator else db.create_collection(name)
        print(f"  created  {name}")
    except CollectionInvalid:
        print(f"  exists   {name}  (skipped)")

def create_indexes(col_name, indexes):
    col = db[col_name]
    for idx in indexes:
        col.create_index(**idx)
    print(f"  indexed  {col_name}  ({len(indexes)} indexes)")

# 1. runs
create_collection("runs", {"$jsonSchema": {"bsonType": "object",
    "required": ["_id", "goal", "preset", "status", "started_at"],
    "properties": {
        "_id":               {"bsonType": "string"},
        "goal":              {"bsonType": "string"},
        "preset":            {"bsonType": "string", "enum": ["saas","docs","research","default"]},
        "status":            {"bsonType": "string", "enum": ["running","done","failed","paused"]},
        "started_at":        {"bsonType": "string"},
        "completed_at":      {"bsonType": ["string","null"]},
        "final_score":       {"bsonType": ["double","null"]},
        "system_iterations": {"bsonType": "int"},
        "total_agents":      {"bsonType": "int"},
        "config_snapshot":   {"bsonType": "object"},
    }}})
create_indexes("runs", [
    {"keys": [("status", ASCENDING), ("started_at", DESCENDING)], "name": "status_started"},
    {"keys": [("started_at", DESCENDING)], "name": "started_at_desc"},
])

# 2. checkpoints
create_collection("checkpoints", {"$jsonSchema": {"bsonType": "object",
    "required": ["run_id","agent_id","task","depth","status","timestamp"],
    "properties": {
        "run_id":    {"bsonType": "string"},
        "agent_id":  {"bsonType": "string"},
        "task":      {"bsonType": "string"},
        "depth":     {"bsonType": "int"},
        "parent_id": {"bsonType": ["string","null"]},
        "status":    {"bsonType": "string", "enum": ["done","failed","frozen"]},
        "result":    {"bsonType": "string"},
        "score":     {"bsonType": "double"},
        "iterations":{"bsonType": "int"},
        "frozen":    {"bsonType": "bool"},
        "timestamp": {"bsonType": "string"},
    }}})
create_indexes("checkpoints", [
    {"keys": [("run_id", ASCENDING), ("agent_id", ASCENDING)], "unique": True, "name": "run_agent_unique"},
    {"keys": [("run_id", ASCENDING), ("frozen", ASCENDING)], "name": "run_frozen"},
    {"keys": [("run_id", ASCENDING), ("timestamp", DESCENDING)], "name": "run_timestamp"},
])

# 3. decision_logs
create_collection("decision_logs", {"$jsonSchema": {"bsonType": "object",
    "required": ["run_id","agent_id","depth","iteration","decision","timestamp"],
    "properties": {
        "run_id":         {"bsonType": "string"},
        "agent_id":       {"bsonType": "string"},
        "depth":          {"bsonType": "int"},
        "iteration":      {"bsonType": "int"},
        "decision":       {"bsonType": "string", "enum": ["retry","spawn_sub","freeze","terminate"]},
        "reason":         {"bsonType": "string"},
        "old_specialist": {"bsonType": ["string","null"]},
        "new_specialist": {"bsonType": ["string","null"]},
        "model_used":     {"bsonType": "string"},
        "score":          {"bsonType": "double"},
        "feedback":       {"bsonType": "string"},
        "latency_ms":     {"bsonType": "int"},
        "timestamp":      {"bsonType": "string"},
    }}})
create_indexes("decision_logs", [
    {"keys": [("run_id", ASCENDING), ("agent_id", ASCENDING)], "name": "run_agent"},
    {"keys": [("run_id", ASCENDING), ("timestamp", DESCENDING)], "name": "run_timestamp"},
    {"keys": [("run_id", ASCENDING), ("decision", ASCENDING)], "name": "run_decision"},
])

# 4. scores
create_collection("scores", {"$jsonSchema": {"bsonType": "object",
    "required": ["run_id","agent_id","iteration","weighted_total","timestamp"],
    "properties": {
        "run_id":         {"bsonType": "string"},
        "agent_id":       {"bsonType": "string"},
        "iteration":      {"bsonType": "int"},
        "correctness":    {"bsonType": "double"},
        "completeness":   {"bsonType": "double"},
        "consistency":    {"bsonType": "double"},
        "runnability":    {"bsonType": "double"},
        "format":         {"bsonType": "double"},
        "weighted_total": {"bsonType": "double"},
        "feedback":       {"bsonType": "string"},
        "retry_with":     {"bsonType": ["string","null"]},
        "timestamp":      {"bsonType": "string"},
    }}})
create_indexes("scores", [
    {"keys": [("run_id", ASCENDING), ("agent_id", ASCENDING), ("iteration", ASCENDING)], "name": "run_agent_iter"},
    {"keys": [("run_id", ASCENDING), ("weighted_total", DESCENDING)], "name": "run_score"},
])

# 5. agent_registry
create_collection("agent_registry", {"$jsonSchema": {"bsonType": "object",
    "required": ["run_id","agent_id","task","output_type","specialist","threshold","depth","status"],
    "properties": {
        "run_id":       {"bsonType": "string"},
        "agent_id":     {"bsonType": "string"},
        "task":         {"bsonType": "string"},
        "output_type":  {"bsonType": "string", "enum": ["code","docs","design","research"]},
        "specialist":   {"bsonType": "string", "enum": ["coder","reasoner","drafter","creative","fast","researcher"]},
        "threshold":    {"bsonType": "double"},
        "depth":        {"bsonType": "int"},
        "parent_id":    {"bsonType": ["string","null"]},
        "dependencies": {"bsonType": "array"},
        "status":       {"bsonType": "string", "enum": ["pending","running","done","failed","frozen","terminated"]},
        "score":        {"bsonType": ["double","null"]},
        "iterations":   {"bsonType": ["int","null"]},
    }}})
create_indexes("agent_registry", [
    {"keys": [("run_id", ASCENDING), ("agent_id", ASCENDING)], "unique": True, "name": "run_agent_unique"},
    {"keys": [("run_id", ASCENDING), ("status", ASCENDING)], "name": "run_status"},
    {"keys": [("run_id", ASCENDING), ("depth", ASCENDING)], "name": "run_depth"},
])

# 6. conflicts
create_collection("conflicts", {"$jsonSchema": {"bsonType": "object",
    "required": ["run_id","system_iteration","agent_a","agent_b","interface","resolution","timestamp"],
    "properties": {
        "run_id":           {"bsonType": "string"},
        "system_iteration": {"bsonType": "int"},
        "agent_a":          {"bsonType": "string"},
        "agent_b":          {"bsonType": "string"},
        "interface":        {"bsonType": "string"},
        "resolution":       {"bsonType": "string"},
        "timestamp":        {"bsonType": "string"},
    }}})
create_indexes("conflicts", [
    {"keys": [("run_id", ASCENDING), ("system_iteration", ASCENDING)], "name": "run_iter"},
])

# 7. repair_log
create_collection("repair_log", {"$jsonSchema": {"bsonType": "object",
    "required": ["run_id","system_iteration","repair_attempt","broken_interfaces","reassigned_agents","outcome","timestamp"],
    "properties": {
        "run_id":            {"bsonType": "string"},
        "system_iteration":  {"bsonType": "int"},
        "repair_attempt":    {"bsonType": "int"},
        "broken_interfaces": {"bsonType": "array"},
        "reassigned_agents": {"bsonType": "array"},
        "frozen_agents":     {"bsonType": "array"},
        "outcome":           {"bsonType": "string", "enum": ["pass","fail_retry","fail_full_replan"]},
        "timestamp":         {"bsonType": "string"},
    }}})
create_indexes("repair_log", [
    {"keys": [("run_id", ASCENDING), ("repair_attempt", ASCENDING)], "name": "run_attempt"},
])

# 8. outputs
create_collection("outputs", {"$jsonSchema": {"bsonType": "object",
    "required": ["run_id","agent_id","output_type","content","timestamp"],
    "properties": {
        "run_id":      {"bsonType": "string"},
        "agent_id":    {"bsonType": "string"},
        "output_type": {"bsonType": "string"},
        "content":     {"bsonType": "string"},
        "score":       {"bsonType": ["double","null"]},
        "frozen":      {"bsonType": "bool"},
        "timestamp":   {"bsonType": "string"},
    }}})
create_indexes("outputs", [
    {"keys": [("run_id", ASCENDING), ("agent_id", ASCENDING)], "name": "run_agent"},
    {"keys": [("run_id", ASCENDING), ("frozen", ASCENDING)], "name": "run_frozen"},
])

# Seed verification
print("\n Seeding verification document...")
db["runs"].insert_one({
    "_id": "run_setup_verify", "goal": "Daedalus setup verification",
    "preset": "default", "status": "done",
    "started_at": datetime.utcnow().isoformat() + "Z",
    "completed_at": datetime.utcnow().isoformat() + "Z",
    "final_score": 1.0, "system_iterations": 0,
    "total_agents": 0, "config_snapshot": {"setup": True, "version": "1.0"},
})

print("\n" + "─" * 52)
print(f" Setup complete — {MONGODB_DB} ready")
for name in sorted(db.list_collection_names()):
    count = db[name].count_documents({})
    idx   = len(list(db[name].list_indexes()))
    print(f"   {name:<20} {count:>3} doc(s)   {idx} index(es)")
print("\n Delete verification doc when confirmed:")
print("   db.runs.deleteOne({ _id: 'run_setup_verify' })")
print("─" * 52)
client.close()
```

**After running the setup script, verify in MongoDB Atlas UI:**
- Database: `Daedalus`
- Should show 8 collections: runs, checkpoints, decision_logs, scores,
  agent_registry, conflicts, repair_log, outputs
- Each collection should have its indexes visible under the Indexes tab

---

## ━━━ SECTION 6 · HARDWARE CONSTRAINTS ━━━

The development machine is:
- CPU: Intel i5-7400 @ 3.0GHz (4 cores, no hyperthreading)
- RAM: 32GB
- GPU: None
- OS: Windows 11
- All LLM inference is remote (OpenRouter + Groq APIs)

**Implications for implementation:**
- No local model loading — all LLM calls are HTTP to cloud APIs
- No Docker — use subprocess + venv for code execution in Phase 1
- No Redis daemon — use Upstash REST API via `upstash-redis` package
- No PostgreSQL — MongoDB Atlas M0 via `motor` (async) package
- Concurrency cap = 5 simultaneous LLM calls (OpenRouter rate limit, not RAM)
- `asyncio.Semaphore` as fallback if Upstash unreachable
- Max parallel major agents = 3, max parallel sub-agents per major = 3

---

## ━━━ SECTION 7 · WEEK-BY-WEEK IMPLEMENTATION PLAN ━━━

Follow this plan exactly. Do not skip ahead. Each week has a verification step —
only proceed to the next week when that step passes.

---

### WEEK 1–2 · Foundation + Planner

**Goal:** User runs `python main.py "Build a SaaS app"` → structured agent DAG
prints to console → MongoDB run document written → clean exit. No LLM execution yet.

**Files to create/modify:**

1. `daedalus_mongo_setup.py` — run immediately, then keep in repo
2. `config.yaml` — full schema (see master plan Part 2)
3. `daedalus/__init__.py` — empty
4. `daedalus/state.py` — all TypedDicts (RunState, AgentSpec, StepResult, BrokenInterface)
5. `daedalus/planner.py` — plan_goal(), _validate_dag(), _tighten_thresholds()
6. `infra/__init__.py` — empty
7. `infra/redis_client.py` — all wrappers WITH per-key TTL (see Issue 2 fix)
8. `infra/mongo_client.py` — Motor async wrappers
9. `infra/semaphore.py` — GlobalSemaphore (Redis-backed + asyncio fallback)
10. `infra/workspace.py` — local file ops: create_run_dir(), write_agent_output(), read_output()
11. `requirements.txt` — add Phase 1 deps including `nest_asyncio`
12. `main.py` — REWRITE with: nest_asyncio patch at top, Windows event loop fix,
    new argparse flags, run_id generation, planner call, MongoDB init

**requirements.txt additions:**
```
nest_asyncio>=1.6.0
upstash-redis>=1.0.0
motor>=3.0.0
pymongo>=4.0.0
pyyaml>=6.0.0
duckduckgo-search>=5.0.0
aiohttp>=3.9.0
```

**Verification — Week 1-2 complete when:**
```bash
python main.py "Build a SaaS task manager with JWT auth" --preset saas
```
Produces:
- Rich console panel showing plan text
- Agent tree printed: schema_agent, backend_agent, auth_agent, frontend_agent, docs_agent
- Dependency waves shown: Wave 0, Wave 1, Wave 2
- MongoDB Atlas UI shows new document in `runs` collection with status="running"
- No errors, clean exit

---

### WEEK 3–4 · DAG Execution + Major/Sub Agents

**Goal:** Full DAG executes with real KimiFlow calls. Parallel waves fire.
Agent results saved to MongoDB.

**Files to create:**
1. `daedalus/coordinator.py` — GlobalCoordinator (topological sort, execute_dag, resolve_conflicts)
2. `daedalus/local_coordinator.py` — LocalCoordinator (fragment_and_run, decompose_task)
3. `daedalus/major_agent.py` — MajorAgent (assess_complexity, execute_direct, merge_sub_results)
4. `daedalus/sub_agent.py` — SubAgent (_call_kimiflow using run_in_executor — see Issue 3 fix)
5. `daedalus/graph.py` — LangGraph graph, first 3 nodes: planner → execute_dag → report

**Critical: apply Issue 3 fix in sub_agent.py and major_agent.py**

**Verification — Week 3-4 complete when:**
```bash
python main.py "Build a simple REST API with user auth" --preset saas
```
Produces:
- All agents execute (real LLM calls)
- Rich console shows live agent tree with status icons
- MongoDB `agent_registry` collection has entries for each agent
- MongoDB `checkpoints` collection has entries after each agent completes
- MongoDB `decision_logs` has entries showing retry decisions
- Final output printed to console and saved to `outputs/workspace/{run_id}/`

---

### WEEK 5–6 · Evaluator + Repair + Assembly

**Goal:** 5-dimension evaluation fires. Surgical repair cycle works.
Final assembled output is a coherent multi-file project in a zip.

**Files to create:**
1. `daedalus/evaluator.py` — evaluate_output() + evaluate_combined()
2. `daedalus/merger.py` — detect_conflicts() + resolve_conflict()
3. `daedalus/repair.py` — surgical_repair() + 3-strike rule
4. `daedalus/assembler.py` — assemble_final() + _deduplicate_files()
5. `daedalus/reporter.py` — generate_report()
6. `daedalus/graph.py` — COMPLETE: all 7 nodes + all routing edges

**Verification — Week 5-6 complete when:**
Full end-to-end SaaS run completes. The `outputs/` directory contains:
- `workspace/{run_id}/final/` with all generated files
- `{run_id}.zip` with the complete project
- `run_{ts}.json` with full run report (scores, iterations, agent tree)

---

### WEEK 7+ · Polish + Crash Recovery

**Goal:** `--resume` works. Rich tree looks professional. Thresholds tuned.

**Tasks:**
1. Implement `--resume {run_id}` in main.py (read MongoDB checkpoints, skip frozen agents)
2. Redis TTL expiry on run completion (`expire_run()` called in reporter.py)
3. Rich live agent tree — nested panels with status icons (pending/running/done/failed/frozen)
4. Tune SaaS evaluation weights based on real runs
5. GitHub branching: `feat/planner`, `feat/dag-execution`, `feat/evaluator-repair`

---

## ━━━ SECTION 8 · COMPLETE DIRECTORY STRUCTURE ━━━

```
d:\Dev\Daedalus\
│
├── .env                         ← secrets (gitignored) — credentials already set
├── .env.example                 ← safe template (committed)
├── .gitignore
├── config.yaml                  ← NEW: all tuneable constants
├── requirements.txt             ← extend with new deps
├── daedalus_mongo_setup.py      ← run once to create collections + indexes
│
│── KimiFlow leaf layer (UNCHANGED) ──────────────────────────────────────
├── pipeline.py                  ← DO NOT MODIFY
├── agents.py                    ← DO NOT MODIFY
├── models.py                    ← DO NOT MODIFY
├── main_kimiflow_backup.py      ← backup of original main.py before rewrite
│
│── Daedalus core ─────────────────────────────────────────────────────────
├── main.py                      ← REWRITTEN entry point
├── daedalus/
│   ├── __init__.py
│   ├── state.py
│   ├── planner.py
│   ├── coordinator.py
│   ├── local_coordinator.py
│   ├── major_agent.py
│   ├── sub_agent.py
│   ├── graph.py
│   ├── evaluator.py
│   ├── merger.py
│   ├── repair.py
│   ├── assembler.py
│   └── reporter.py
│
│── Infrastructure ─────────────────────────────────────────────────────────
├── infra/
│   ├── __init__.py
│   ├── redis_client.py          ← Upstash REST + per-key TTL (Issue 2 fix applied)
│   ├── mongo_client.py          ← Motor async wrappers
│   ├── semaphore.py             ← Redis-backed + asyncio fallback
│   └── workspace.py             ← Local file ops (Phase 2: swap for R2)
│
│── Tools ───────────────────────────────────────────────────────────────────
├── tools/
│   ├── __init__.py
│   ├── web_search.py            ← DuckDuckGo (Phase 1)
│   ├── code_runner.py           ← Phase 2: Modal sandbox
│   └── url_reader.py            ← Fetch + clean URL
│
│── Outputs ─────────────────────────────────────────────────────────────────
└── outputs/
    └── workspace/
        └── {run_id}/
            ├── {agent_id}/
            ├── merge/
            └── final/
```

---

## ━━━ SECTION 9 · CLI CONTRACT ━━━

```bash
# Basic usage
python main.py "Build a SaaS task manager with JWT auth"
python main.py "Build a SaaS task manager" --preset saas
python main.py "Research latest AI papers" --preset research

# Control flags
python main.py "Build a SaaS app" --plan-review      # human approval gate before execution
python main.py "Build a SaaS app" --quiet             # suppress model attempt noise
python main.py "Build a SaaS app" --threshold 0.90    # override all thresholds
python main.py "Build a SaaS app" --max-depth 3       # override recursion depth

# Recovery
python main.py --resume run_a1b2c3d4                  # resume from last checkpoint
```

**argparse additions to main.py:**
```python
parser.add_argument("goal",          nargs="?",        help="Goal for Daedalus to accomplish")
parser.add_argument("--preset",      default="default", choices=["saas","docs","research","default"])
parser.add_argument("--plan-review", action="store_true", help="Human approval gate after planning")
parser.add_argument("--resume",      metavar="RUN_ID",  help="Resume from checkpoint")
parser.add_argument("--threshold",   type=float,        help="Override all thresholds globally")
parser.add_argument("--max-depth",   type=int,          help="Override max recursion depth")
parser.add_argument("--quiet",       action="store_true")
parser.add_argument("--verbose",     action="store_true")
```

---

## ━━━ SECTION 10 · CONFIG.YAML COMPLETE SCHEMA ━━━

```yaml
runtime:
  max_recursion_depth:     5
  max_parallel_major:      3
  max_parallel_sub:        3
  max_system_iterations:   3
  max_module_iterations:   5
  plan_review:             false

concurrency:
  global_cap:              5
  fallback_semaphore:      true

thresholds:
  code:                    0.88
  docs:                    0.80
  design:                  0.75
  research:                0.82
  default:                 0.82

evaluation_weights:
  default:
    correctness:           0.30
    completeness:          0.20
    consistency:           0.20
    runnability:           0.20
    format:                0.10
  saas:
    correctness:           0.28
    completeness:          0.20
    consistency:           0.20
    runnability:           0.27
    format:                0.05

presets:
  saas:
    description: "Full-stack SaaS application"
    must_pass: ["routes_connect", "auth_wired", "frontend_calls_backend"]
    default_major_agents: 5

infra:
  mongodb_db:              "Daedalus"
  redis_ttl_hours:         48
  checkpoint_every_agent:  true

logging:
  level:                   "INFO"
  show_model_attempts:     true
  rich_tree:               true
```

---

## ━━━ SECTION 11 · SUMMARY OF WHAT MAKES DAEDALUS DIFFERENT ━━━

| Capability | KimiFlow (before) | Daedalus (after) |
|---|---|---|
| Task decomposition | None — one LLM | Hierarchical DAG: major → sub |
| Parallelism | Sequential | asyncio.gather() waves |
| Agent spawning | None | Runtime-spawned by coordinator |
| Failure handling | Retry same specialist | Surgical repair + frozen modules |
| State persistence | Local JSON | MongoDB Atlas + Upstash Redis |
| Crash recovery | None | --resume from checkpoint |
| Concurrency control | None | Redis semaphore (cap=5) |
| Conflict resolution | None | Merger LLM call |
| Recursion depth | 0 (flat) | 5 levels (config-driven) |
| Evaluation | 1 score | 5 weighted dimensions |
| Code execution | None | Phase 2: Modal.com sandbox |
| File storage | Local outputs/ | Phase 2: Cloudflare R2 |

---

## ━━━ SECTION 12 · BEFORE YOU WRITE ANY CODE — CHECKLIST ━━━

1. [ ] Confirm project root is `d:\Dev\Daedalus\` — never reference `testKimiClaw`
2. [ ] Run `python daedalus_mongo_setup.py` — verify 8 collections created
3. [ ] Verify `.env` has all 4 Daedalus credentials (MONGODB_URI, MONGODB_DB, UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN)
4. [ ] Backup current `main.py` as `main_kimiflow_backup.py` before rewriting
5. [ ] Add `nest_asyncio` to requirements.txt before writing main.py
6. [ ] Never modify `pipeline.py`, `agents.py`, or `models.py`
7. [ ] Apply Issue 2 fix (per-key TTL) in infra/redis_client.py from the start
8. [ ] Apply Issue 3 fix (run_in_executor with own loop) in sub_agent.py in Week 3

---

*This context document supersedes any conflicting instructions in the master plan.
The master plan (daedalus_master_plan.md) remains the source of truth for function
signatures, data schemas, and execution flow details not covered here.*
