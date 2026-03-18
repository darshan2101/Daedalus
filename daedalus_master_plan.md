# DAEDALUS ORCHESTRATOR — COMPLETE MASTER PLAN
### Version 1.0 · March 2026 · Built on Daedalus

---

> **North Star**: A self-spawning hierarchical multi-agent system where a Planner decomposes
> any goal into a DAG of major tasks, spawns Major Agents that may spawn Sub-Agents, evaluates
> outputs at every level, surgically repairs failures, and produces production-quality output
> for truly *anything* — code, SaaS apps, research, docs, pipelines.

---

## ━━━ PART 0 · ACCOUNTS & INFRASTRUCTURE (COMPLETE) ━━━

### Services Active
| Service | Purpose | Status |
|---|---|---|
| GitHub `darshan2101/Daedalus` | Source control | ✅ Pushed |
| MongoDB Atlas M0 · `Daedalus` db | State, checkpoints, logs | ✅ URI in .env |
| Upstash Redis `huge-parrot-75854` | Semaphore, counters, frozen flags | ✅ Token in .env |
| OpenRouter | 26 free LLM models | ✅ Existing |
| Groq | Ironclad LLM fallback | ✅ Existing |
| Modal.com | Phase 2 · sandboxed code execution | 🔜 Account ready |
| Cloudflare R2 | Phase 2 · large file workspace | 🔜 Account ready |

### Critical `.env` Keys Added
```
MONGODB_URI   = mongodb+srv://darshan:...@cluster0.pidly.mongodb.net/
MONGODB_DB    = Daedalus
UPSTASH_REDIS_REST_URL   = https://huge-parrot-75854.upstash.io
UPSTASH_REDIS_REST_TOKEN = gQAAAA...
```

---

## ━━━ PART 1 · COMPLETE DIRECTORY STRUCTURE ━━━

```
d:\Dev\testKimiClaw\               ← project root = Daedalus repo
│
├── .env                            ← secrets (gitignored)
├── .env.example                    ← safe template (committed)
├── .gitignore
├── config.yaml                     ← NEW: all tuneable constants
├── requirements.txt                ← extend with new deps
│
│── ── Daedalus (UNCHANGED leaf layer) ────────────────────────────────
├── main.py                         ← Daedalus entry point (rewritten)
├── pipeline.py                     ← Daedalus pipeline (unchanged)
├── agents.py                       ← Daedalus specialists (unchanged)
├── models.py                       ← Model lists (unchanged)
│
│── ── Daedalus Core ───────────────────────────────────────────────────
├── daedalus/
│   ├── __init__.py
│   ├── state.py                    ← All TypedDicts for Daedalus
│   ├── planner.py                  ← Goal → task DAG + agent specs
│   ├── coordinator.py              ← Global coordinator
│   ├── local_coordinator.py        ← Per-major-agent coordinator
│   ├── major_agent.py              ← Major agent runtime (async)
│   ├── sub_agent.py                ← Sub-agent (calls Daedalus)
│   ├── graph.py                    ← LangGraph orchestration graph
│   ├── evaluator.py                ← 5-dimension weighted evaluator
│   ├── merger.py                   ← Interface conflict resolution
│   ├── repair.py                   ← Surgical repair cycle
│   ├── assembler.py                ← Combine module outputs → final
│   └── reporter.py                 ← Post-run report generator
│
│── ── Infrastructure ──────────────────────────────────────────────────
├── infra/
│   ├── __init__.py
│   ├── redis_client.py             ← Upstash Redis REST wrapper
│   ├── mongo_client.py             ← Motor async MongoDB wrapper
│   ├── semaphore.py                ← Global LLM concurrency cap
│   └── workspace.py                ← File workspace (local → R2 Phase 2)
│
│── ── Tools ───────────────────────────────────────────────────────────
├── tools/
│   ├── __init__.py
│   ├── web_search.py               ← DuckDuckGo search (Phase 1)
│   ├── code_runner.py              ← Modal sandbox (Phase 2)
│   └── url_reader.py               ← Fetch + clean a URL
│
│── ── Outputs ─────────────────────────────────────────────────────────
└── outputs/
    └── workspace/
        └── {run_id}/
            ├── {agent_id}/         ← per-agent working files
            ├── merge/              ← global coordinator merge area
            └── final/              ← assembled final output + zip
```

---

## ━━━ PART 2 · CONFIG.YAML (COMPLETE SCHEMA) ━━━

```yaml
# config.yaml — Daedalus global configuration
# All values override-able via CLI flags

runtime:
  max_recursion_depth:     5      # Major → Sub → Sub-Sub max depth
  max_parallel_major:      3      # asyncio.gather cap for major agents
  max_parallel_sub:        3      # asyncio.gather cap per major agent
  max_system_iterations:   3      # Global surgical-repair cycles
  max_module_iterations:   5      # Per-module retry cycles (mirrors Daedalus)
  plan_review:             false  # true = --plan-review CLI flag inserts human gate

concurrency:
  global_cap:              5      # Max simultaneous LLM calls system-wide
  fallback_semaphore:      true   # Use asyncio.Semaphore if Redis unreachable

thresholds:
  code:                    0.88
  docs:                    0.80
  design:                  0.75
  research:                0.82
  default:                 0.82

evaluation_weights:        # Must sum to 1.0 per preset
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
    runnability:           0.27   # higher — does the app actually run?
    format:                0.05

presets:
  saas:
    description: "Full-stack SaaS application"
    must_pass:              ["routes_connect", "auth_wired", "frontend_calls_backend"]
    default_major_agents:   5  # schema, backend, auth, frontend, docs

infra:
  mongodb_db:              "Daedalus"
  redis_ttl_hours:         48     # Auto-expire Redis keys after run
  checkpoint_every_agent:  true   # Write checkpoint after every agent completion

logging:
  level:                   "INFO"
  show_model_attempts:     true   # false = --quiet equivalent
  rich_tree:               true   # Show live agent tree in terminal
```

---

## ━━━ PART 3 · ALL DATA SCHEMAS ━━━

### 3.1 · Daedalus State TypedDicts (`daedalus/state.py`)

```python
from typing import TypedDict, Optional

class AgentSpec(TypedDict):
    agent_id:       str          # uuid4 short e.g. "ag_a1b2"
    task:           str          # Full task description for this agent
    output_type:    str          # code | docs | design | research
    threshold:      float        # From config per output_type (planner can tighten)
    dependencies:   list[str]    # agent_ids this must wait for
    depth:          int          # 0 = major, 1+ = sub
    parent_id:      Optional[str]
    specialist:     str          # coder|reasoner|drafter|creative|fast|researcher

class StepResult(TypedDict):
    agent_id:       str
    task:           str
    result:         str
    score:          float
    iterations:     int
    frozen:         bool

class BrokenInterface(TypedDict):
    agent_a:        str          # agent_id
    agent_b:        str          # agent_id
    description:    str          # what is broken between them
    attempt:        int          # which repair attempt

class RunState(TypedDict):
    # ── Identity
    run_id:               str    # uuid4 e.g. "run_a1b2c3d4"
    goal:                 str
    preset:               str    # saas | default | research | ...

    # ── Planner output
    plan:                 str
    agent_specs:          list[AgentSpec]
    dep_graph:            dict[str, list[str]]  # {agent_id: [dep_ids]}
    output_type:          str    # dominant output type for the run

    # ── Execution tracking
    agent_results:        dict[str, StepResult]   # {agent_id: StepResult}
    frozen_agents:        list[str]               # agent_ids that passed

    # ── Combined output
    combined_result:      str
    combined_score:       float
    broken_interfaces:    list[BrokenInterface]

    # ── Iteration control
    system_iteration:     int    # 0-based, max = max_system_iterations
    repair_attempts:      int    # surgical attempts in current system iteration

    # ── Meta
    current_step:         str    # planner|executing|evaluating|repairing|done
    errors:               list[str]
```

---

### 3.2 · MongoDB Collection Schemas

#### Collection: `runs`
```json
{
  "_id":            "run_a1b2c3d4",
  "goal":           "Build a SaaS app with auth...",
  "preset":         "saas",
  "status":         "running | done | failed | paused",
  "started_at":     "2026-03-18T09:00:00Z",
  "completed_at":   null,
  "final_score":    null,
  "system_iterations": 1,
  "total_agents":   7,
  "config_snapshot": { ...full config.yaml at run time... }
}
```

#### Collection: `checkpoints`
```json
{
  "run_id":         "run_a1b2c3d4",
  "agent_id":       "ag_a1b2",
  "task":           "Build FastAPI backend with JWT auth",
  "depth":          0,
  "parent_id":      null,
  "status":         "done | failed | frozen",
  "result":         "...full output text...",
  "score":          0.91,
  "iterations":     3,
  "frozen":         true,
  "timestamp":      "2026-03-18T09:05:00Z"
}
```

#### Collection: `decision_logs`
```json
{
  "run_id":         "run_a1b2c3d4",
  "agent_id":       "ag_a1b2",
  "depth":          0,
  "iteration":      2,
  "decision":       "retry | spawn_sub | freeze | terminate",
  "reason":         "score 0.71 < 0.88, specialist switching coder→reviewer",
  "old_specialist": "coder",
  "new_specialist": "reviewer",
  "model_used":     "qwen/qwen3-coder:free",
  "score":          0.71,
  "feedback":       "Missing auth middleware on protected routes",
  "latency_ms":     4200,
  "timestamp":      "2026-03-18T09:05:00Z"
}
```

#### Collection: `scores`
```json
{
  "run_id":         "run_a1b2c3d4",
  "agent_id":       "ag_a1b2",
  "iteration":      2,
  "correctness":    0.90,
  "completeness":   0.85,
  "consistency":    0.80,
  "runnability":    0.70,
  "format":         0.95,
  "weighted_total": 0.83,
  "feedback":       "Auth middleware missing on /api/users route",
  "retry_with":     "reviewer",
  "timestamp":      "2026-03-18T09:05:00Z"
}
```

#### Collection: `agent_registry`
```json
{
  "run_id":         "run_a1b2c3d4",
  "agent_id":       "ag_a1b2",
  "task":           "Build FastAPI backend",
  "output_type":    "code",
  "specialist":     "coder",
  "threshold":      0.88,
  "depth":          0,
  "parent_id":      null,
  "dependencies":   ["ag_c3d4"],
  "status":         "pending | running | done | failed | frozen | terminated",
  "score":          0.91,
  "iterations":     3
}
```

#### Collection: `conflicts`
```json
{
  "run_id":         "run_a1b2c3d4",
  "system_iteration": 1,
  "agent_a":        "ag_b1c2",
  "agent_b":        "ag_c3d4",
  "interface":      "User model schema mismatch",
  "resolution":     "agent_a User schema adopted as canonical",
  "timestamp":      "2026-03-18T09:10:00Z"
}
```

#### Collection: `repair_log`
```json
{
  "run_id":         "run_a1b2c3d4",
  "system_iteration": 1,
  "repair_attempt": 1,
  "broken_interfaces": ["backend↔frontend: missing /api/auth/refresh"],
  "reassigned_agents": ["ag_frontend_01"],
  "frozen_agents":     ["ag_backend_01", "ag_schema_01"],
  "outcome":           "pass | fail_retry | fail_full_replan",
  "timestamp":         "2026-03-18T09:15:00Z"
}
```

---

### 3.3 · Redis Key Taxonomy (`infra/redis_client.py`)

```
Semaphore (global LLM call cap):
  run:{run_id}:sem                    INCR/DECR   integer 0-5

Frozen module flags:
  run:{run_id}:modules                HSET/HGETALL  {agent_id: "frozen|active"}

Iteration counters:
  run:{run_id}:sys_iter               INCR          integer
  run:{run_id}:agent:{agent_id}:iter  INCR          integer

Agent metadata (fast lookup):
  run:{run_id}:agent:{agent_id}       HSET          {score, feedback, status, specialist}

Task queue (coordinator → agents):
  run:{run_id}:queue                  LPUSH/RPOP    JSON-encoded AgentSpec

All keys expire: TTL = config.infra.redis_ttl_hours * 3600
Set via: EXPIRE run:{run_id}:* {ttl_seconds}
```

---

## ━━━ PART 4 · MODULE RESPONSIBILITIES & FUNCTION SIGNATURES ━━━

### 4.1 · `daedalus/planner.py`

**Responsibility**: Take the raw goal string and produce a complete `RunState` skeleton —
the full agent DAG, all `AgentSpec` entries, dependency graph, and dominant `output_type`.

```python
async def plan_goal(goal: str, preset: str, config: dict) -> dict:
    """
    LLM call → parses JSON to produce:
    {
      "plan": str,
      "output_type": str,
      "agent_specs": [AgentSpec, ...],
      "dep_graph": { agent_id: [dep_ids] }
    }
    Validates: no circular deps, all dep_ids exist, depth=0 for all major agents.
    """

def _validate_dag(specs: list[AgentSpec], deps: dict) -> None:
    """Raise ValueError if circular dependency or missing dep_id."""

def _tighten_thresholds(specs: list[AgentSpec], config: dict) -> list[AgentSpec]:
    """
    Planner can tighten thresholds per task, never loosen past config defaults.
    """

PLANNER_SYSTEM_PROMPT = """
You are the Daedalus Meta-Orchestrator. Given a goal, decompose it into major tasks.

Output ONLY valid JSON:
{
  "plan": "<one paragraph strategy>",
  "output_type": "<code|docs|design|research>",
  "agent_specs": [
    {
      "agent_id": "ag_<4chars>",
      "task": "<specific task description>",
      "output_type": "<code|docs|design|research>",
      "threshold": 0.88,
      "dependencies": ["ag_xxxx"],
      "specialist": "<coder|reasoner|drafter|creative|fast|researcher>"
    }
  ],
  "dep_graph": { "ag_xxxx": ["ag_yyyy"] }
}

Rules:
- agent_ids must be unique within the plan
- All dep_graph entries must reference valid agent_ids
- No circular dependencies
- threshold cannot be lower than default for output_type
- SaaS apps always need: schema, backend, auth, frontend, docs agents minimum
"""
```

---

### 4.2 · `daedalus/coordinator.py` (Global)

**Responsibility**: Orchestrate the full DAG execution, call `asyncio.gather()` on
dependency-free agents, enforce global concurrency cap, handle merge conflicts,
trigger surgical repair, manage --resume from checkpoints.

```python
class GlobalCoordinator:
    def __init__(self, run_state: RunState, config: dict): ...

    async def execute_dag(self) -> RunState:
        """
        Main entry point. Topological sort → waves of parallel execution.
        Returns final RunState with all agent_results populated.
        """

    async def _execute_wave(self, agent_ids: list[str]) -> None:
        """asyncio.gather() a wave of agents with concurrency cap."""

    async def _spawn_major_agent(self, spec: AgentSpec) -> StepResult:
        """Create MajorAgent instance, run it, return StepResult."""

    def _topological_sort(self, dep_graph: dict) -> list[list[str]]:
        """
        Kahn's algorithm → returns ordered waves (list of lists).
        Wave 0 = no deps, Wave 1 = depends only on Wave 0, etc.
        """

    async def resolve_conflicts(self, results: dict[str, StepResult]) -> dict:
        """
        LLM merger call when interfaces between agents conflict.
        Logs to MongoDB conflicts collection.
        Returns updated results dict.
        """

    async def terminate_agent(self, agent_id: str, reason: str) -> None:
        """
        Marks agent as terminated in Redis + MongoDB.
        Coordinator re-assigns task to next-best specialist.
        """

    async def resume_from_checkpoint(self, run_id: str) -> RunState:
        """--resume flag: read MongoDB checkpoints, skip frozen agents."""
```

---

### 4.3 · `daedalus/major_agent.py`

**Responsibility**: Execute one major task. Acts as its own local coordinator for sub-agents.
Decides whether to run the task itself (via Daedalus) or fragment it into sub-agents.

```python
class MajorAgent:
    def __init__(self, spec: AgentSpec, context: str, config: dict):
        self.spec     = spec
        self.context  = context  # combined output of dependency agents
        self.config   = config
        self.local_coordinator = LocalCoordinator(spec, config)

    async def run(self) -> StepResult:
        """
        1. Assess task complexity → fragment or execute directly
        2. If fragmentable: delegate to local_coordinator
        3. If simple: call Daedalus directly via _execute_direct()
        4. Evaluate module output
        5. Retry/repair up to max_module_iterations
        6. Return StepResult
        """

    async def _assess_complexity(self) -> bool:
        """
        LLM call: should this task be fragmented into sub-tasks?
        Returns True if task warrants sub-agent spawning.
        Rules: always fragment if task > 2000 chars or planner marks complex.
        """

    async def _execute_direct(self, feedback: str = "", history: list = []) -> str:
        """Call Daedalus pipeline for this task directly."""
        from pipeline import pipeline
        state = { "task": self.spec["task"], ... }
        result = await asyncio.to_thread(
            pipeline.invoke, state, {"recursion_limit": 100}
        )
        return result["result"]

    async def _merge_sub_results(self, sub_results: list[StepResult]) -> str:
        """Merge sub-agent outputs into one coherent module output."""
```

---

### 4.4 · `daedalus/local_coordinator.py`

**Responsibility**: Lightweight version of GlobalCoordinator scoped to one major agent.
Spawns sub-agents, runs them in parallel (up to cap), collects results.

```python
class LocalCoordinator:
    def __init__(self, parent_spec: AgentSpec, config: dict): ...

    async def fragment_and_run(self, task: str, context: str) -> list[StepResult]:
        """
        1. LLM call: decompose task into sub-tasks
        2. Validate depth < max_recursion_depth
        3. asyncio.gather() sub-agents
        4. Return list of StepResults
        """

    async def _decompose_task(self, task: str) -> list[AgentSpec]:
        """LLM decomposes major task into sub-tasks. Returns list of sub-AgentSpecs."""

    async def _spawn_sub_agent(self, spec: AgentSpec, context: str) -> StepResult:
        """Create SubAgent, run it, return StepResult."""

    def _check_depth(self, depth: int) -> None:
        """Raise RuntimeError if depth >= config.max_recursion_depth."""
```

---

### 4.5 · `daedalus/sub_agent.py`

**Responsibility**: Smallest unit of execution. Calls Daedalus (via `asyncio.to_thread`)
with a specific task, retry loop, evaluator feedback. Matches existing Daedalus contract exactly.

```python
class SubAgent:
    def __init__(self, spec: AgentSpec, context: str, config: dict): ...

    async def run(self) -> StepResult:
        """
        Inner loop identical to Daedalus retry logic:
        - Call execute → evaluate → feedback loop
        - Max iterations: config.max_module_iterations
        - Threshold: spec.threshold
        - Returns StepResult with final score
        """

    async def _call_Daedalus(self, task: str, feedback: str, history: list) -> str:
        """
        asyncio.to_thread wraps the synchronous pipeline.invoke call.
        This is the bridge between async Daedalus and sync Daedalus.
        """
        from pipeline import pipeline
        state = {
            "task":           task,
            "plan":           "",
            "assigned_model": self.spec["specialist"],
            "result":         "",
            "quality_score":  0.0,
            "feedback":       feedback,
            "iterations":     0,
            "history":        history,
        }
        return await asyncio.to_thread(
            pipeline.invoke, state, {"recursion_limit": 100}
        )
```

---

### 4.6 · `daedalus/evaluator.py`

**Responsibility**: 5-dimension weighted scoring for any output type.
Writes detailed scores to MongoDB `scores` collection.

```python
async def evaluate_output(
    task:        str,
    result:      str,
    output_type: str,
    history:     list[dict],
    config:      dict,
    run_id:      str,
    agent_id:    str,
    iteration:   int,
) -> dict:
    """
    Returns:
    {
      "correctness":   0.0-1.0,
      "completeness":  0.0-1.0,
      "consistency":   0.0-1.0,
      "runnability":   0.0-1.0,
      "format":        0.0-1.0,
      "weighted_total":0.0-1.0,
      "feedback":      str,
      "retry_with":    "coder|reasoner|...|done"
    }
    """

def _weighted_total(scores: dict, weights: dict) -> float:
    """Apply config weights to dimension scores."""

async def evaluate_combined(
    goal: str, combined_result: str, agent_results: dict, config: dict
) -> dict:
    """
    System-level evaluation after all modules are merged.
    Extra dimension: interface_consistency (do modules connect?)
    """

EVALUATOR_SYSTEM_PROMPT = """
You are Daedalus Quality Evaluator. Score this output on 5 dimensions (0.0–1.0 each):

1. correctness   — Is it technically accurate and correct?
2. completeness  — Does it fully address all requirements?
3. consistency   — Is it internally consistent (no contradictions)?
4. runnability   — Would this actually run/work as-is? (code: does it compile?)
5. format        — Does it follow the required output format?

PRIOR ATTEMPT HISTORY: {history_block}

Output ONLY valid JSON:
{
  "correctness":  0.0,
  "completeness": 0.0,
  "consistency":  0.0,
  "runnability":  0.0,
  "format":       0.0,
  "feedback":     "<specific list of exactly what to fix>",
  "retry_with":   "<specialist|done>"
}
"""
```

---

### 4.7 · `daedalus/merger.py`

**Responsibility**: Detect and resolve interface conflicts between major agent outputs.
One LLM call per conflict pair. Logs all decisions.

```python
async def detect_conflicts(
    agent_results: dict[str, StepResult],
    dep_graph:     dict,
) -> list[BrokenInterface]:
    """
    LLM call: given all module outputs, identify interface conflicts.
    Returns list of BrokenInterface dicts.
    """

async def resolve_conflict(
    interface: BrokenInterface,
    result_a:  str,
    result_b:  str,
    run_id:    str,
) -> str:
    """
    LLM merger call for one specific conflict pair.
    Returns resolution description + canonical version to adopt.
    """
```

---

### 4.8 · `daedalus/repair.py`

**Responsibility**: Surgical repair cycle. Identifies which modules own broken interfaces
and re-runs only those. Tracks attempts. Triggers full re-plan after 2 failures.

```python
async def surgical_repair(
    run_state:  RunState,
    config:     dict,
) -> RunState:
    """
    3-strike rule:
    - Attempt 1: surgical (identify + re-run only broken modules)
    - Attempt 2: surgical (same)
    - Attempt 3: full re-decompose (planner called again)
    """

async def _identify_broken_owners(
    broken_interfaces: list[BrokenInterface],
    agent_specs:       list[AgentSpec],
) -> list[str]:
    """Map broken interface descriptions to owning agent_ids."""

async def _rerun_agents(
    agent_ids:   list[str],
    run_state:   RunState,
    config:      dict,
) -> dict[str, StepResult]:
    """Re-run only the specified agents, passing prior output as context."""
```

---

### 4.9 · `daedalus/assembler.py`

**Responsibility**: Combine all module outputs into a coherent final artifact.
For code: concatenate files, resolve duplicates. For docs: stitch sections.

```python
async def assemble_final(
    agent_results: dict[str, StepResult],
    goal:          str,
    preset:        str,
) -> str:
    """
    LLM assembly call: given all module outputs, produce final unified output.
    For SaaS: validates all --- FILE: --- blocks, removes duplicates,
    ensures consistent imports between files.
    """

def _deduplicate_files(file_blocks: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """
    If two modules defined app/models/user.py, keep the one with higher source score.
    """
```

---

### 4.10 · `daedalus/graph.py`

**Responsibility**: Define the top-level LangGraph graph for Daedalus.
Daedalus remains a separate compiled graph called as a sub-tool by SubAgent.

```python
from langgraph.graph import StateGraph, END
from daedalus.state import RunState

def build_daedalus_graph(config: dict):
    g = StateGraph(RunState)

    g.add_node("planner",          plan_node)
    g.add_node("human_review",     human_review_node)   # only if --plan-review
    g.add_node("execute_dag",      execute_dag_node)    # GlobalCoordinator.execute_dag()
    g.add_node("evaluate_combined",evaluate_combined_node)
    g.add_node("repair",           repair_node)         # surgical_repair()
    g.add_node("assemble",         assemble_node)
    g.add_node("report",           report_node)

    g.set_entry_point("planner")
    g.add_conditional_edges("planner", route_after_plan, {
        "review":   "human_review",
        "execute":  "execute_dag",
    })
    g.add_edge("human_review",     "execute_dag")
    g.add_edge("execute_dag",      "evaluate_combined")
    g.add_conditional_edges("evaluate_combined", route_after_eval, {
        "assemble": "assemble",
        "repair":   "repair",
    })
    g.add_conditional_edges("repair", route_after_repair, {
        "execute":  "execute_dag",   # surgical → re-run affected modules
        "replan":   "planner",       # full re-decompose
        "give_up":  "assemble",      # max attempts hit → accept best result
    })
    g.add_edge("assemble",         "report")
    g.add_edge("report",           END)

    return g.compile()
```

---

## ━━━ PART 5 · INFRASTRUCTURE LAYER ━━━

### 5.1 · `infra/redis_client.py`

```python
import os
from upstash_redis import Redis

_redis: Redis | None = None

def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis(
            url=os.getenv("UPSTASH_REDIS_REST_URL"),
            token=os.getenv("UPSTASH_REDIS_REST_TOKEN"),
        )
    return _redis

# Convenience wrappers
def sem_incr(run_id: str) -> int:   return get_redis().incr(f"run:{run_id}:sem")
def sem_decr(run_id: str) -> int:   return get_redis().decr(f"run:{run_id}:sem")
def sem_get(run_id: str)  -> int:   return int(get_redis().get(f"run:{run_id}:sem") or 0)

def freeze_agent(run_id: str, agent_id: str):
    get_redis().hset(f"run:{run_id}:modules", {agent_id: "frozen"})

def is_frozen(run_id: str, agent_id: str) -> bool:
    return get_redis().hget(f"run:{run_id}:modules", agent_id) == "frozen"

def incr_sys_iter(run_id: str) -> int:
    return get_redis().incr(f"run:{run_id}:sys_iter")

def incr_agent_iter(run_id: str, agent_id: str) -> int:
    return get_redis().incr(f"run:{run_id}:agent:{agent_id}:iter")

def set_agent_meta(run_id: str, agent_id: str, data: dict):
    get_redis().hset(f"run:{run_id}:agent:{agent_id}", data)

def expire_run(run_id: str, ttl_hours: int):
    """Set TTL on all run keys — called at run completion."""
    # Upstash REST doesn't support KEYS pattern; track key list manually
```

---

### 5.2 · `infra/mongo_client.py`

```python
import os
from motor.motor_asyncio import AsyncIOMotorClient

_client: AsyncIOMotorClient | None = None

def get_db():
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(os.getenv("MONGODB_URI"))
    return _client[os.getenv("MONGODB_DB", "Daedalus")]

async def insert_checkpoint(run_id: str, agent_id: str, data: dict):
    await get_db().checkpoints.insert_one({"run_id": run_id, "agent_id": agent_id, **data})

async def get_checkpoints(run_id: str) -> list[dict]:
    return await get_db().checkpoints.find({"run_id": run_id}).to_list(None)

async def log_decision(run_id: str, agent_id: str, data: dict):
    await get_db().decision_logs.insert_one({"run_id": run_id, "agent_id": agent_id, **data})

async def log_score(run_id: str, agent_id: str, iteration: int, scores: dict):
    await get_db().scores.insert_one({
        "run_id": run_id, "agent_id": agent_id, "iteration": iteration, **scores
    })

async def upsert_registry(run_id: str, spec: dict):
    await get_db().agent_registry.update_one(
        {"run_id": run_id, "agent_id": spec["agent_id"]},
        {"$set": spec}, upsert=True
    )

async def update_run_status(run_id: str, status: str, **kwargs):
    await get_db().runs.update_one(
        {"_id": run_id}, {"$set": {"status": status, **kwargs}}
    )
```

---

### 5.3 · `infra/semaphore.py`

```python
import asyncio, time

class GlobalSemaphore:
    """
    Redis-backed global LLM call semaphore.
    Fallback to asyncio.Semaphore if Redis unreachable.
    """
    def __init__(self, run_id: str, cap: int):
        self.run_id = run_id
        self.cap    = cap
        self._fallback = asyncio.Semaphore(cap)

    async def acquire(self):
        try:
            while True:
                current = sem_incr(self.run_id)
                if current <= self.cap:
                    return
                sem_decr(self.run_id)
                await asyncio.sleep(0.5)
        except Exception:
            await self._fallback.acquire()

    async def release(self):
        try:
            sem_decr(self.run_id)
        except Exception:
            self._fallback.release()

    async def __aenter__(self): await self.acquire(); return self
    async def __aexit__(self, *_): await self.release()
```

---

## ━━━ PART 6 · ASYNC EXECUTION MODEL ━━━

### The asyncio + LangGraph Hybrid Contract

```
LangGraph graph (sync nodes, manages state routing)
    │
    ├── plan_node (sync)        → calls async planner via asyncio.run()
    ├── execute_dag_node (sync) → calls GlobalCoordinator.execute_dag() via asyncio.run()
    │       │
    │       ├── asyncio.gather(major_agent_1, major_agent_2, ...)   ← parallel waves
    │       │       │
    │       │       ├── MajorAgent.run() [async]
    │       │       │       ├── LocalCoordinator.fragment_and_run() [async]
    │       │       │       │       ├── asyncio.gather(sub_agent_1, sub_agent_2, ...) ← parallel
    │       │       │       │       │       └── SubAgent.run() [async]
    │       │       │       │       │               └── asyncio.to_thread(pipeline.invoke) ← Daedalus
    │       │       │       │       └── merge_sub_results()
    │       │       │       └── evaluate_module() [async]
    │       │       └── freeze or retry
    │       └── resolve_conflicts() [async]  ← after all waves done
    └── evaluate_combined_node (sync) → calls async evaluator via asyncio.run()

Windows fix (in main.py before any asyncio usage):
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
```

### Why `asyncio.to_thread` for Daedalus?
Daedalus uses the sync `openai` client. asyncio.to_thread() runs it in a thread pool.
- Doesn't block the event loop
- Multiple sub-agents run "concurrently" (I/O wait time overlaps)
- No code changes needed in Daedalus itself

---

## ━━━ PART 7 · COMPLETE EXECUTION FLOW ━━━

```
USER: python main.py "Build a SaaS app with auth..."

main.py
  │
  ├─ parse_args() → --preset saas, --plan-review false, --resume false
  ├─ generate run_id = "run_" + uuid4()[:8]
  ├─ setup Windows event loop policy
  ├─ load config.yaml
  ├─ initialize MongoDB run document (status=running)
  ├─ build_daedalus_graph(config)
  └─ asyncio.run(graph.ainvoke(initial_run_state))

━━━ NODE: planner ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  LLM call (Hermes 405B):
    Input:  goal + preset + config thresholds
    Output: plan, agent_specs[], dep_graph{}
  Validate: no circular deps, threshold floors respected
  Write: MongoDB runs (plan snapshot)
  Rich: print plan panel + agent tree preview

━━━ NODE: execute_dag ━━━━━━━━━━━━━━━━━━━━━━━━━━
  GlobalCoordinator.execute_dag():
    1. Topological sort → waves:
       Wave 0: [schema_agent, docs_agent]      → asyncio.gather()
       Wave 1: [backend_agent, auth_agent]     → asyncio.gather()
       Wave 2: [frontend_agent]                → asyncio.gather()

    For each agent in wave:
      ├─ Check: is_frozen(run_id, agent_id)?  → skip if yes
      ├─ Check: Redis sys_iter <= max_system_iterations
      ├─ Acquire GlobalSemaphore (blocks if 5 LLM calls active)
      ├─ MongoDB: upsert_registry(status=running)
      │
      └─ MajorAgent.run():
          ├─ Assess complexity: fragment or direct?
          │
          ├─ [DIRECT] asyncio.to_thread(pipeline.invoke)
          │     Daedalus does: orchestrate → execute → evaluate → retry (up to 15)
          │     Returns: result string + score
          │
          └─ [FRAGMENT] LocalCoordinator.fragment_and_run()
              ├─ LLM decompose → sub-task AgentSpecs
              ├─ Check depth < max_recursion_depth
              ├─ asyncio.gather(SubAgent_1.run(), SubAgent_2.run(), ...)
              │     Each SubAgent: asyncio.to_thread(pipeline.invoke)
              └─ merge_sub_results() → combined module output

      After MajorAgent completes:
        ├─ evaluator.evaluate_output() → 5 dimension scores
        ├─ MongoDB: insert_checkpoint, log_score
        ├─ Redis: set_agent_meta(score, feedback)
        ├─ Score >= threshold? → freeze_agent(agent_id) → FROZEN
        ├─ Score < threshold AND iters < max_module_iterations? → retry
        └─ Score < threshold AND iters >= max_module_iterations? → accept best

    After all waves:
      GlobalCoordinator.resolve_conflicts() → Merger LLM call if needed

━━━ NODE: evaluate_combined ━━━━━━━━━━━━━━━━━━━
  evaluator.evaluate_combined():
    Input: goal + all module results
    Dimensions: correctness, completeness, consistency, runnability, format
    Extra: interface_consistency (do modules connect?)
  Write: MongoDB scores (combined entry)

  Route:
    combined_score >= threshold → "assemble"
    combined_score <  threshold AND repair_attempts < 2 → "repair"
    combined_score <  threshold AND repair_attempts >= 2 → "replan"(back to planner)
    system_iteration >= max_system_iterations → "assemble" (give_up)

━━━ NODE: repair ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  repair.surgical_repair():
    ├─ Identify broken interfaces (LLM call)
    ├─ Map to owning agent_ids
    ├─ Unfreeze only those agents in Redis
    ├─ MongoDB: repair_log entry
    ├─ incr repair_attempts
    └─ Route back to execute_dag (only unfrozen agents run)

━━━ NODE: assemble ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  assembler.assemble_final():
    ├─ Merge all frozen + active module outputs
    ├─ Deduplicate FILE blocks
    ├─ Resolve import conflicts
    └─ Write to outputs/workspace/{run_id}/final/

━━━ NODE: report ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  reporter.generate_report():
    ├─ Full agent tree (who ran, score, iterations)
    ├─ Repair history
    ├─ Total API calls, total latency
    ├─ Per-module scores
    ├─ Final combined score
    ├─ Write: output/run_{ts}.json
    ├─ MongoDB: runs (status=done, final_score)
    └─ Rich console: final summary panel
```

---

## ━━━ PART 8 · NEW `main.py` CLI CONTRACT ━━━

```python
python main.py "Build a SaaS task manager with JWT auth"
python main.py "Build a SaaS task manager" --preset saas
python main.py "Research latest AI papers" --preset research
python main.py "Write product docs" --preset docs
python main.py "Build a SaaS app" --plan-review     # human approval gate
python main.py "Build a SaaS app" --quiet            # suppress model noise
python main.py --resume run_a1b2c3d4                 # crash recovery
python main.py "Build a SaaS app" --threshold 0.90   # global threshold override
python main.py "Build a SaaS app" --max-depth 3      # override recursion depth
```

**argparse additions (extend existing):**
```python
parser.add_argument("--preset",      default="default", choices=["saas","docs","research","default"])
parser.add_argument("--plan-review", action="store_true")
parser.add_argument("--resume",      metavar="RUN_ID", help="Resume from checkpoint")
parser.add_argument("--threshold",   type=float, help="Override all thresholds globally")
parser.add_argument("--max-depth",   type=int,   help="Override max recursion depth")
```

---

## ━━━ PART 9 · REQUIREMENTS.TXT ADDITIONS ━━━

```
# Existing
openai>=1.0.0
langgraph>=0.2.0
langchain-core>=0.3.0
python-dotenv>=1.0.0
rich>=13.0.0

# Daedalus Phase 1 additions
upstash-redis>=1.0.0          # Upstash REST client (no local Redis daemon)
motor>=3.0.0                   # Async MongoDB (Motor = async PyMongo)
pymongo>=4.0.0                 # Sync MongoDB (for non-async contexts)
pyyaml>=6.0.0                  # config.yaml loading
duckduckgo-search>=5.0.0       # Web search for researcher agent
aiohttp>=3.9.0                 # Async HTTP for tool calls
asyncio-throttle>=1.0.0        # Optional: token bucket for rate limiting

# Phase 2 additions (add when ready)
# modal>=0.60.0                # Sandboxed code execution
# boto3>=1.34.0                # Cloudflare R2 (S3-compatible)
```

---

## ━━━ PART 10 · MONGODB ATLAS SETUP ━━━

### Collections to Create (auto-created on first insert, but index now):

```javascript
// Run in Atlas shell or Compass:

db.runs.createIndex({ "_id": 1 })
db.runs.createIndex({ "status": 1, "started_at": -1 })

db.checkpoints.createIndex({ "run_id": 1, "agent_id": 1 }, { unique: true })
db.checkpoints.createIndex({ "run_id": 1, "frozen": 1 })

db.decision_logs.createIndex({ "run_id": 1, "agent_id": 1 })
db.decision_logs.createIndex({ "run_id": 1, "timestamp": -1 })

db.scores.createIndex({ "run_id": 1, "agent_id": 1, "iteration": 1 })

db.agent_registry.createIndex({ "run_id": 1, "agent_id": 1 }, { unique: true })
db.agent_registry.createIndex({ "run_id": 1, "status": 1 })

db.conflicts.createIndex({ "run_id": 1 })
db.repair_log.createIndex({ "run_id": 1, "repair_attempt": 1 })
```

---

## ━━━ PART 11 · WEEK-BY-WEEK DELIVERY PLAN ━━━

### Week 1–2: Foundation + Planner
**Goal**: Run goal through Planner, get structured agent DAG, print it, stop before execution.

Files to create:
- `config.yaml` (complete schema)
- `daedalus/__init__.py`
- `daedalus/state.py` (all TypedDicts)
- `daedalus/planner.py` (plan_goal, validate_dag, tighten_thresholds)
- `infra/__init__.py`
- `infra/redis_client.py` (all wrappers)
- `infra/mongo_client.py` (all wrappers)
- `infra/semaphore.py` (GlobalSemaphore)
- `infra/workspace.py` (local file ops only)
- Update `requirements.txt`
- Update `main.py` (Windows fix, new argparse flags, run_id generation, planner call)

**Verification**: `python main.py "Build a SaaS app with auth"` →
prints structured agent DAG with dependencies, writes MongoDB run document, exits.

---

### Week 3–4: DAG Execution + Major/Sub Agents
**Goal**: Execute the DAG with real Daedalus calls, parallel waves, save results.

Files to create:
- `daedalus/coordinator.py` (GlobalCoordinator)
- `daedalus/local_coordinator.py` (LocalCoordinator)
- `daedalus/major_agent.py` (MajorAgent with direct + fragment paths)
- `daedalus/sub_agent.py` (SubAgent with asyncio.to_thread bridge)
- `daedalus/graph.py` (LangGraph graph, first 3 nodes only: planner→execute_dag→report)

**Verification**: Full DAG executes with real LLM calls. Agent results saved to MongoDB.
Rich console shows agent tree with live status updates.

---

### Week 5–6: Evaluator + Repair + Assembly
**Goal**: 5-dimension evaluation, surgical repair cycle, final assembly.

Files to create:
- `daedalus/evaluator.py` (5-dimension, weighted, history-aware)
- `daedalus/merger.py` (conflict detection + resolution)
- `daedalus/repair.py` (3-strike surgical repair)
- `daedalus/assembler.py` (merge all module outputs)
- `daedalus/reporter.py` (post-run report)
- Complete `daedalus/graph.py` (all nodes + routing)

**Verification**: Full end-to-end SaaS run completes. Surgical repair fires on failures.
Final zip output contains coherent multi-file project.

---

### Week 7+: Polish, Tuning, Crash Recovery
**Goal**: --resume works, Rich tree looks professional, thresholds tuned for SaaS.

Tasks:
- Implement `--resume {run_id}` in main.py
- Redis TTL expiry on all run keys
- Rich live agent tree (nested panels with status icons)
- Tune SaaS evaluation weights against real runs
- First complete end-to-end SaaS generation test
- GitHub push with proper branching: `feat/planner`, `feat/dag-execution`, etc.

---

## ━━━ PART 12 · PHASE 2 & 3 PREVIEWS ━━━

### Phase 2 — Before Hosting
- Modal.com: replace `asyncio.to_thread(subprocess)` with `modal.run(code_str)`
- Cloudflare R2: replace `outputs/workspace/` with `r2.put()`
- Coordinator gains: spawn refusal logic, mid-run reassignment
- Threshold config moves to MongoDB (no redeploy to change)

### Phase 3 — Multi-User SaaS
- Upstash QStash: durable task queue, replaces asyncio.Queue
- Railway/Render: host the orchestrator as an API
- Atlas Vector Search: semantic search over past runs (knowledge base)
- Web dashboard: live agent tree, human approval gate, manual agent kill
- User accounts + run isolation

---

## ━━━ SUMMARY: WHAT MAKES DAEDALUS DIFFERENT ━━━

| Capability | Daedalus (before) | Daedalus (after) |
|---|---|---|
| Task decomposition | None — one LLM for everything | Hierarchical DAG: major → sub |
| Parallelism | Sequential single agent | asyncio.gather() waves |
| Agent spawning | None | Runtime-spawned by coordinator |
| Failure handling | Retry same specialist | Surgical repair → frozen modules |
| Memory | Per-iteration only | History across all iterations |
| State persistence | Local JSON only | MongoDB + Redis |
| Crash recovery | None | --resume from checkpoint |
| Output quality | Single model pass | Multi-agent collaboration |
| Concurrency control | None | Redis semaphore (cap=5) |
| Conflict resolution | None | Merger LLM call |
| Recursion depth | 0 (flat) | 5 levels deep |
| Evaluation | 1 score | 5 weighted dimensions |
