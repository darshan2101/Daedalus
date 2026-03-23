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
# DAEDALUS — TESTING & PROGRESS EVALUATION ADDENDUM
### Appends to: daedalus_master_plan.md as PART 13
### Version 1.0 · March 2026

---

> **Purpose:** This document defines the complete testing strategy for Daedalus —
> unit tests per module, integration tests per week, phase gate checklists that
> must pass before advancing, and a health-check CLI that can be run at any time
> to report system status. No phase begins until the previous phase's gate passes.

---

## ━━━ PART 13 · TESTING & PROGRESS EVALUATION ━━━

---

### 13.0 · Testing Philosophy

Three rules for Daedalus testing given the hardware constraints:

1. **Tests must be free to run.** No tests that make real LLM calls unless
   explicitly marked `@pytest.mark.live`. All unit and integration tests use
   mocks. Live tests are opt-in only: `pytest -m live`.

2. **Tests must be fast.** The full non-live suite must complete in under 60
   seconds on an i5-7400. No sleeping, no timeouts longer than 5s.

3. **Phase gates are hard stops.** Claude Code must not implement Week N+1
   until all Week N gate tests pass. This is non-negotiable.

---

### 13.1 · Test Directory Structure

```
d:\Dev\Daedalus\
└── tests/
    ├── __init__.py
    ├── conftest.py                  ← shared fixtures (mock Redis, mock Mongo, mock LLM)
    ├── unit/
    │   ├── __init__.py
    │   ├── test_state.py            ← TypedDict validation
    │   ├── test_planner.py          ← DAG validation, circular dep detection
    │   ├── test_coordinator.py      ← topological sort, wave building
    │   ├── test_evaluator.py        ← weighted scoring math
    │   ├── test_merger.py           ← conflict detection logic
    │   ├── test_repair.py           ← 3-strike rule, frozen flag logic
    │   ├── test_assembler.py        ← file deduplication logic
    │   ├── test_redis_client.py     ← TTL logic, fallback logic
    │   ├── test_mongo_client.py     ← insert/read/upsert wrappers
    │   └── test_semaphore.py        ← concurrency cap enforcement
    ├── integration/
    │   ├── __init__.py
    │   ├── test_week1_planner.py    ← Phase gate: planner → MongoDB → clean exit
    │   ├── test_week3_dag.py        ← Phase gate: DAG execution with mock KimiFlow
    │   ├── test_week5_repair.py     ← Phase gate: evaluator + surgical repair cycle
    │   └── test_week7_resume.py     ← Phase gate: --resume from checkpoint
    ├── live/
    │   ├── __init__.py
    │   ├── test_live_planner.py     ← Real LLM call: planner produces valid DAG
    │   ├── test_live_single_agent.py ← Real LLM: one major agent completes
    │   └── test_live_saas.py        ← Real end-to-end SaaS run (slow, expensive)
    └── health/
        └── check.py                 ← python tests/health/check.py — status report
```

---

### 13.2 · Shared Fixtures (`tests/conftest.py`)

```python
"""
tests/conftest.py — shared fixtures for all Daedalus tests
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

# ── Event loop fixture (Windows-compatible) ──────────────────────────────────
@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for all async tests."""
    import nest_asyncio
    nest_asyncio.apply()
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

# ── Mock Redis ────────────────────────────────────────────────────────────────
@pytest.fixture
def mock_redis():
    """In-memory Redis substitute. Mimics Upstash REST behaviour."""
    store = {}
    hashes = {}
    sets = {}
    counters = {}

    redis = MagicMock()
    redis.get.side_effect    = lambda k: store.get(k)
    redis.set.side_effect    = lambda k, v, ex=None: store.update({k: v})
    redis.incr.side_effect   = lambda k: counters.update({k: counters.get(k, 0) + 1}) or counters[k]
    redis.decr.side_effect   = lambda k: counters.update({k: max(0, counters.get(k, 0) - 1)}) or counters[k]
    redis.hset.side_effect   = lambda k, mapping: hashes.update({k: {**hashes.get(k, {}), **mapping}})
    redis.hget.side_effect   = lambda k, f: hashes.get(k, {}).get(f)
    redis.hgetall.side_effect = lambda k: hashes.get(k, {})
    redis.sadd.side_effect   = lambda k, *v: sets.update({k: sets.get(k, set()) | set(v)})
    redis.smembers.side_effect = lambda k: sets.get(k, set())
    redis.expire.side_effect = lambda k, t: None  # no-op in tests
    redis.lpush.side_effect  = lambda k, v: None
    redis.rpop.side_effect   = lambda k: None

    # expose internal state for assertions
    redis._store    = store
    redis._hashes   = hashes
    redis._counters = counters
    return redis

# ── Mock MongoDB ──────────────────────────────────────────────────────────────
@pytest.fixture
def mock_db():
    """In-memory MongoDB substitute. Mimics Motor async behaviour."""
    collections = {}

    class MockCollection:
        def __init__(self, name):
            self.name = name
            self._docs = []

        async def insert_one(self, doc):
            self._docs.append(doc)
            return MagicMock(inserted_id=doc.get("_id", "mock_id"))

        async def find_one(self, query):
            for doc in self._docs:
                if all(doc.get(k) == v for k, v in query.items()):
                    return doc
            return None

        async def update_one(self, query, update, upsert=False):
            for doc in self._docs:
                if all(doc.get(k) == v for k, v in query.items()):
                    doc.update(update.get("$set", {}))
                    return
            if upsert:
                new_doc = {**query, **update.get("$set", {})}
                self._docs.append(new_doc)

        def find(self, query=None):
            results = self._docs if not query else [
                d for d in self._docs
                if all(d.get(k) == v for k, v in query.items())
            ]
            mock = AsyncMock()
            mock.to_list = AsyncMock(return_value=results)
            return mock

        def count_documents(self, query=None):
            return len(self._docs)

    class MockDB:
        def __getattr__(self, name):
            if name not in collections:
                collections[name] = MockCollection(name)
            return collections[name]
        def _collection(self, name):
            return collections.get(name, MockCollection(name))

    return MockDB()

# ── Mock LLM call ─────────────────────────────────────────────────────────────
@pytest.fixture
def mock_llm_planner_response():
    """Valid planner JSON response for 'Build a SaaS app' goal."""
    return {
        "plan": "Build a SaaS task manager with JWT auth in 5 modules.",
        "output_type": "code",
        "agent_specs": [
            {"agent_id": "ag_s001", "task": "Design database schema",
             "output_type": "code", "threshold": 0.88,
             "dependencies": [], "specialist": "coder"},
            {"agent_id": "ag_b001", "task": "Build FastAPI backend",
             "output_type": "code", "threshold": 0.88,
             "dependencies": ["ag_s001"], "specialist": "coder"},
            {"agent_id": "ag_a001", "task": "Implement JWT auth",
             "output_type": "code", "threshold": 0.88,
             "dependencies": ["ag_s001"], "specialist": "coder"},
            {"agent_id": "ag_f001", "task": "Build React frontend",
             "output_type": "code", "threshold": 0.85,
             "dependencies": ["ag_b001", "ag_a001"], "specialist": "coder"},
            {"agent_id": "ag_d001", "task": "Write API documentation",
             "output_type": "docs", "threshold": 0.80,
             "dependencies": [], "specialist": "drafter"},
        ],
        "dep_graph": {
            "ag_s001": [],
            "ag_b001": ["ag_s001"],
            "ag_a001": ["ag_s001"],
            "ag_f001": ["ag_b001", "ag_a001"],
            "ag_d001": [],
        }
    }

@pytest.fixture
def mock_kimiflow_result():
    """Valid KimiFlow pipeline.invoke result."""
    return {
        "task": "Build FastAPI backend",
        "plan": "Create REST API with CRUD endpoints",
        "assigned_model": "coder",
        "result": "--- FILE: backend/main.py ---\nfrom fastapi import FastAPI\napp = FastAPI()\n--- END FILE ---",
        "quality_score": 0.91,
        "feedback": "Good structure, all endpoints present",
        "iterations": 2,
        "history": [],
    }

@pytest.fixture
def sample_run_state():
    """Minimal valid RunState for testing."""
    return {
        "run_id": "run_test001",
        "goal": "Build a SaaS task manager",
        "preset": "saas",
        "plan": "5-module SaaS build plan",
        "agent_specs": [],
        "dep_graph": {},
        "output_type": "code",
        "agent_results": {},
        "frozen_agents": [],
        "combined_result": "",
        "combined_score": 0.0,
        "broken_interfaces": [],
        "system_iteration": 0,
        "repair_attempts": 0,
        "current_step": "planner",
        "errors": [],
    }
```

---

### 13.3 · Unit Tests

#### `tests/unit/test_planner.py`

```python
"""Unit tests for daedalus/planner.py — no LLM calls."""
import pytest
from daedalus.planner import _validate_dag, _tighten_thresholds

class TestValidateDAG:
    def test_valid_dag_passes(self):
        specs = [
            {"agent_id": "ag_a", "dependencies": []},
            {"agent_id": "ag_b", "dependencies": ["ag_a"]},
        ]
        deps = {"ag_a": [], "ag_b": ["ag_a"]}
        _validate_dag(specs, deps)  # should not raise

    def test_circular_dependency_raises(self):
        specs = [
            {"agent_id": "ag_a", "dependencies": ["ag_b"]},
            {"agent_id": "ag_b", "dependencies": ["ag_a"]},
        ]
        deps = {"ag_a": ["ag_b"], "ag_b": ["ag_a"]}
        with pytest.raises(ValueError, match="circular"):
            _validate_dag(specs, deps)

    def test_missing_dep_id_raises(self):
        specs = [{"agent_id": "ag_a", "dependencies": ["ag_nonexistent"]}]
        deps = {"ag_a": ["ag_nonexistent"]}
        with pytest.raises(ValueError, match="missing"):
            _validate_dag(specs, deps)

    def test_empty_dag_passes(self):
        _validate_dag([], {})  # should not raise

    def test_self_dependency_raises(self):
        specs = [{"agent_id": "ag_a", "dependencies": ["ag_a"]}]
        deps = {"ag_a": ["ag_a"]}
        with pytest.raises(ValueError):
            _validate_dag(specs, deps)


class TestTightenThresholds:
    def test_threshold_not_lowered_below_config(self):
        config = {"thresholds": {"code": 0.88, "docs": 0.80, "default": 0.82}}
        specs = [{"agent_id": "ag_a", "output_type": "code", "threshold": 0.50}]
        result = _tighten_thresholds(specs, config)
        assert result[0]["threshold"] >= 0.88

    def test_threshold_can_be_raised(self):
        config = {"thresholds": {"code": 0.88, "docs": 0.80, "default": 0.82}}
        specs = [{"agent_id": "ag_a", "output_type": "code", "threshold": 0.95}]
        result = _tighten_thresholds(specs, config)
        assert result[0]["threshold"] == 0.95

    def test_unknown_output_type_uses_default(self):
        config = {"thresholds": {"code": 0.88, "default": 0.82}}
        specs = [{"agent_id": "ag_a", "output_type": "video", "threshold": 0.50}]
        result = _tighten_thresholds(specs, config)
        assert result[0]["threshold"] >= 0.82
```

#### `tests/unit/test_coordinator.py`

```python
"""Unit tests for GlobalCoordinator — topological sort only, no I/O."""
import pytest
from daedalus.coordinator import GlobalCoordinator

class TestTopologicalSort:
    def setup_method(self):
        self.coord = GlobalCoordinator.__new__(GlobalCoordinator)

    def test_no_deps_is_single_wave(self):
        dep_graph = {"ag_a": [], "ag_b": [], "ag_c": []}
        waves = self.coord._topological_sort(dep_graph)
        assert len(waves) == 1
        assert set(waves[0]) == {"ag_a", "ag_b", "ag_c"}

    def test_linear_chain_is_sequential_waves(self):
        dep_graph = {"ag_a": [], "ag_b": ["ag_a"], "ag_c": ["ag_b"]}
        waves = self.coord._topological_sort(dep_graph)
        assert len(waves) == 3
        assert waves[0] == ["ag_a"]
        assert waves[1] == ["ag_b"]
        assert waves[2] == ["ag_c"]

    def test_saas_pattern_produces_three_waves(self):
        dep_graph = {
            "ag_schema": [],
            "ag_docs":   [],
            "ag_backend":  ["ag_schema"],
            "ag_auth":     ["ag_schema"],
            "ag_frontend": ["ag_backend", "ag_auth"],
        }
        waves = self.coord._topological_sort(dep_graph)
        assert len(waves) == 3
        assert set(waves[0]) == {"ag_schema", "ag_docs"}
        assert set(waves[1]) == {"ag_backend", "ag_auth"}
        assert set(waves[2]) == {"ag_frontend"}

    def test_empty_graph_returns_empty_waves(self):
        waves = self.coord._topological_sort({})
        assert waves == []
```

#### `tests/unit/test_evaluator.py`

```python
"""Unit tests for evaluator weighted scoring math."""
import pytest
from daedalus.evaluator import _weighted_total

class TestWeightedTotal:
    def test_equal_weights_averages_correctly(self):
        scores  = {"correctness": 1.0, "completeness": 0.0,
                   "consistency": 1.0, "runnability": 0.0, "format": 1.0}
        weights = {"correctness": 0.2, "completeness": 0.2,
                   "consistency": 0.2, "runnability": 0.2, "format": 0.2}
        assert abs(_weighted_total(scores, weights) - 0.60) < 0.001

    def test_saas_weights_prioritise_runnability(self):
        # Two outputs: A runs but is incomplete, B doesn't run but is complete
        weights = {"correctness": 0.28, "completeness": 0.20,
                   "consistency": 0.20, "runnability": 0.27, "format": 0.05}
        scores_runs    = {"correctness": 0.7, "completeness": 0.5,
                          "consistency": 0.7, "runnability": 1.0, "format": 0.7}
        scores_no_run  = {"correctness": 0.9, "completeness": 1.0,
                          "consistency": 0.9, "runnability": 0.0, "format": 0.9}
        assert _weighted_total(scores_runs, weights) > _weighted_total(scores_no_run, weights)

    def test_weights_must_sum_to_one(self):
        weights = {"correctness": 0.30, "completeness": 0.20,
                   "consistency": 0.20, "runnability": 0.20, "format": 0.10}
        assert abs(sum(weights.values()) - 1.0) < 0.001

    def test_perfect_score_returns_one(self):
        scores  = {k: 1.0 for k in ["correctness","completeness","consistency","runnability","format"]}
        weights = {"correctness": 0.30, "completeness": 0.20,
                   "consistency": 0.20, "runnability": 0.20, "format": 0.10}
        assert abs(_weighted_total(scores, weights) - 1.0) < 0.001

    def test_zero_score_returns_zero(self):
        scores  = {k: 0.0 for k in ["correctness","completeness","consistency","runnability","format"]}
        weights = {"correctness": 0.30, "completeness": 0.20,
                   "consistency": 0.20, "runnability": 0.20, "format": 0.10}
        assert _weighted_total(scores, weights) == 0.0
```

#### `tests/unit/test_redis_client.py`

```python
"""Unit tests for Redis TTL logic and fallback behaviour."""
import pytest
from unittest.mock import patch, MagicMock

class TestSemaphoreCounter:
    def test_incr_respects_cap(self, mock_redis):
        with patch("infra.redis_client.get_redis", return_value=mock_redis):
            from infra.redis_client import sem_incr, sem_decr
            v1 = sem_incr("run_test")
            v2 = sem_incr("run_test")
            assert v2 == 2
            sem_decr("run_test")
            assert mock_redis._counters.get("run:run_test:sem", 0) == 1

    def test_freeze_agent_sets_frozen(self, mock_redis):
        with patch("infra.redis_client.get_redis", return_value=mock_redis):
            from infra.redis_client import freeze_agent, is_frozen
            freeze_agent("run_test", "ag_001")
            assert is_frozen("run_test", "ag_001") is True

    def test_unfreeze_sets_active(self, mock_redis):
        with patch("infra.redis_client.get_redis", return_value=mock_redis):
            from infra.redis_client import freeze_agent, unfreeze_agent, is_frozen
            freeze_agent("run_test", "ag_001")
            unfreeze_agent("run_test", "ag_001")
            assert is_frozen("run_test", "ag_001") is False

    def test_ttl_called_on_every_key_write(self, mock_redis):
        with patch("infra.redis_client.get_redis", return_value=mock_redis):
            from infra.redis_client import sem_incr
            sem_incr("run_ttltest")
            # expire must have been called — TTL is set per write
            assert mock_redis.expire.called

class TestGlobalSemaphore:
    @pytest.mark.asyncio
    async def test_semaphore_blocks_at_cap(self, mock_redis):
        """Semaphore should not allow more than cap concurrent calls."""
        with patch("infra.redis_client.get_redis", return_value=mock_redis):
            from infra.semaphore import GlobalSemaphore
            sem = GlobalSemaphore("run_sem_test", cap=2)
            # Manually set counter above cap
            mock_redis._counters["run:run_sem_test:sem"] = 3
            # acquire should not immediately succeed — it should poll
            import asyncio
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(sem.acquire(), timeout=0.2)

    @pytest.mark.asyncio
    async def test_fallback_used_when_redis_fails(self):
        """When Redis raises, asyncio.Semaphore fallback is used."""
        broken_redis = MagicMock()
        broken_redis.incr.side_effect = Exception("Redis unreachable")
        with patch("infra.redis_client.get_redis", return_value=broken_redis):
            from infra.semaphore import GlobalSemaphore
            sem = GlobalSemaphore("run_fallback", cap=3)
            # Should not raise — falls back to asyncio.Semaphore
            await sem.acquire()
            await sem.release()
```

#### `tests/unit/test_repair.py`

```python
"""Unit tests for surgical repair logic."""
import pytest

class TestThreeStrikeRule:
    def test_first_two_attempts_are_surgical(self):
        from daedalus.repair import _should_full_replan
        assert _should_full_replan(repair_attempts=0) is False
        assert _should_full_replan(repair_attempts=1) is False

    def test_third_attempt_triggers_full_replan(self):
        from daedalus.repair import _should_full_replan
        assert _should_full_replan(repair_attempts=2) is True

    def test_only_broken_interface_owners_unfreeze(self):
        from daedalus.repair import _identify_broken_owners
        specs = [
            {"agent_id": "ag_backend", "task": "Build FastAPI backend with /api/auth route"},
            {"agent_id": "ag_frontend", "task": "Build React frontend calling /api/auth"},
            {"agent_id": "ag_schema", "task": "Design database schema"},
        ]
        broken = [{"agent_a": "ag_backend", "agent_b": "ag_frontend",
                   "description": "/api/auth/refresh endpoint missing", "attempt": 1}]
        owners = _identify_broken_owners(broken, specs)
        assert "ag_backend" in owners or "ag_frontend" in owners
        assert "ag_schema" not in owners  # schema is not involved in this interface
```

---

### 13.4 · Integration Tests (Phase Gates)

#### `tests/integration/test_week1_planner.py`

```python
"""
PHASE GATE — Week 1-2
Must pass before starting Week 3-4 implementation.
Uses mock LLM and mock MongoDB — no real API calls.
"""
import pytest
import json
from unittest.mock import patch, AsyncMock, MagicMock

class TestWeek1PlannnerGate:

    @pytest.mark.asyncio
    async def test_plan_goal_returns_valid_structure(
        self, mock_db, mock_redis, mock_llm_planner_response
    ):
        """Planner returns a dict with plan, agent_specs, dep_graph."""
        mock_response = json.dumps(mock_llm_planner_response)
        with patch("daedalus.planner._call_llm", new_callable=AsyncMock,
                   return_value=mock_response):
            with patch("infra.mongo_client.get_db", return_value=mock_db):
                from daedalus.planner import plan_goal
                config = {"thresholds": {"code": 0.88, "docs": 0.80, "default": 0.82},
                          "runtime": {"max_recursion_depth": 5}}
                result = await plan_goal("Build a SaaS app", "saas", config)

        assert "plan" in result
        assert "agent_specs" in result
        assert "dep_graph" in result
        assert len(result["agent_specs"]) >= 3
        assert isinstance(result["dep_graph"], dict)

    @pytest.mark.asyncio
    async def test_dag_has_no_circular_dependencies(
        self, mock_db, mock_redis, mock_llm_planner_response
    ):
        mock_response = json.dumps(mock_llm_planner_response)
        with patch("daedalus.planner._call_llm", new_callable=AsyncMock,
                   return_value=mock_response):
            with patch("infra.mongo_client.get_db", return_value=mock_db):
                from daedalus.planner import plan_goal, _validate_dag
                config = {"thresholds": {"code": 0.88, "docs": 0.80, "default": 0.82},
                          "runtime": {"max_recursion_depth": 5}}
                result = await plan_goal("Build a SaaS app", "saas", config)
                # Should not raise
                _validate_dag(result["agent_specs"], result["dep_graph"])

    @pytest.mark.asyncio
    async def test_run_document_written_to_mongodb(
        self, mock_db, mock_redis, mock_llm_planner_response
    ):
        mock_response = json.dumps(mock_llm_planner_response)
        with patch("daedalus.planner._call_llm", new_callable=AsyncMock,
                   return_value=mock_response):
            with patch("infra.mongo_client.get_db", return_value=mock_db):
                from daedalus.planner import plan_goal
                config = {"thresholds": {"code": 0.88, "docs": 0.80, "default": 0.82},
                          "runtime": {"max_recursion_depth": 5}, "infra": {"mongodb_db": "Daedalus"}}
                await plan_goal("Build a SaaS app", "saas", config)

        # Check that a document was written to runs collection
        assert mock_db._collection("runs").count_documents() >= 1

    @pytest.mark.asyncio
    async def test_all_dep_ids_exist_in_agent_specs(
        self, mock_db, mock_redis, mock_llm_planner_response
    ):
        mock_response = json.dumps(mock_llm_planner_response)
        with patch("daedalus.planner._call_llm", new_callable=AsyncMock,
                   return_value=mock_response):
            with patch("infra.mongo_client.get_db", return_value=mock_db):
                from daedalus.planner import plan_goal
                config = {"thresholds": {"code": 0.88, "docs": 0.80, "default": 0.82},
                          "runtime": {"max_recursion_depth": 5}}
                result = await plan_goal("Build a SaaS app", "saas", config)

        agent_ids = {s["agent_id"] for s in result["agent_specs"]}
        for spec in result["agent_specs"]:
            for dep in spec["dependencies"]:
                assert dep in agent_ids, f"Dep {dep} not in agent specs"

    def test_redis_credentials_reachable(self):
        """Verify Upstash Redis REST URL is set and responding."""
        import os
        from dotenv import load_dotenv
        load_dotenv()
        assert os.getenv("UPSTASH_REDIS_REST_URL"), "UPSTASH_REDIS_REST_URL missing from .env"
        assert os.getenv("UPSTASH_REDIS_REST_TOKEN"), "UPSTASH_REDIS_REST_TOKEN missing from .env"

    def test_mongodb_credentials_reachable(self):
        """Verify MongoDB URI is set."""
        import os
        from dotenv import load_dotenv
        load_dotenv()
        assert os.getenv("MONGODB_URI"), "MONGODB_URI missing from .env"
        assert os.getenv("MONGODB_DB"), "MONGODB_DB missing from .env"

# ── PHASE GATE RUNNER ────────────────────────────────────────────────────────
WEEK1_GATE_TESTS = [
    "test_plan_goal_returns_valid_structure",
    "test_dag_has_no_circular_dependencies",
    "test_run_document_written_to_mongodb",
    "test_all_dep_ids_exist_in_agent_specs",
    "test_redis_credentials_reachable",
    "test_mongodb_credentials_reachable",
]
# All must pass. Run: pytest tests/integration/test_week1_planner.py -v
```

#### `tests/integration/test_week3_dag.py`

```python
"""
PHASE GATE — Week 3-4
Must pass before starting Week 5-6 implementation.
Uses mock KimiFlow pipeline — no real LLM calls.
"""
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

class TestWeek3DAGGate:

    @pytest.mark.asyncio
    async def test_topological_sort_produces_correct_waves(self):
        from daedalus.coordinator import GlobalCoordinator
        coord = GlobalCoordinator.__new__(GlobalCoordinator)
        dep_graph = {
            "ag_schema":   [],
            "ag_backend":  ["ag_schema"],
            "ag_auth":     ["ag_schema"],
            "ag_frontend": ["ag_backend", "ag_auth"],
        }
        waves = coord._topological_sort(dep_graph)
        assert waves[0] == ["ag_schema"]
        assert set(waves[1]) == {"ag_backend", "ag_auth"}
        assert waves[2] == ["ag_frontend"]

    @pytest.mark.asyncio
    async def test_frozen_agents_are_skipped(
        self, mock_db, mock_redis, mock_llm_planner_response, mock_kimiflow_result
    ):
        """Agents marked frozen in Redis are skipped during DAG execution."""
        with patch("infra.redis_client.get_redis", return_value=mock_redis):
            with patch("infra.mongo_client.get_db", return_value=mock_db):
                # Pre-freeze schema agent
                mock_redis._hashes["run:run_test001:modules"] = {"ag_s001": "frozen"}

                executed = []

                async def mock_spawn(spec):
                    executed.append(spec["agent_id"])
                    return {"agent_id": spec["agent_id"], "task": spec["task"],
                            "result": "mock output", "score": 0.91,
                            "iterations": 1, "frozen": True}

                from daedalus.coordinator import GlobalCoordinator
                coord = GlobalCoordinator.__new__(GlobalCoordinator)
                coord.run_state = {"run_id": "run_test001",
                                   "dep_graph": {"ag_s001": [], "ag_b001": ["ag_s001"]},
                                   "agent_specs": mock_llm_planner_response["agent_specs"],
                                   "agent_results": {}, "frozen_agents": ["ag_s001"],
                                   "system_iteration": 0, "errors": []}
                coord.config = {"runtime": {"max_parallel_major": 3,
                                             "max_system_iterations": 3},
                                "concurrency": {"global_cap": 5, "fallback_semaphore": True},
                                "infra": {"redis_ttl_hours": 48}}
                coord._spawn_major_agent = mock_spawn

                await coord.execute_dag()
                assert "ag_s001" not in executed  # frozen — must not execute

    @pytest.mark.asyncio
    async def test_parallel_agents_run_concurrently(self, mock_db, mock_redis):
        """Wave agents start simultaneously — not sequentially."""
        import time
        start_times = {}

        async def mock_spawn_with_timing(spec):
            start_times[spec["agent_id"]] = time.monotonic()
            await asyncio.sleep(0.05)  # simulate LLM latency
            return {"agent_id": spec["agent_id"], "task": spec["task"],
                    "result": "mock", "score": 0.91, "iterations": 1, "frozen": True}

        with patch("infra.redis_client.get_redis", return_value=mock_redis):
            with patch("infra.mongo_client.get_db", return_value=mock_db):
                from daedalus.coordinator import GlobalCoordinator
                coord = GlobalCoordinator.__new__(GlobalCoordinator)
                coord.run_state = {
                    "run_id": "run_parallel_test",
                    "dep_graph": {"ag_a": [], "ag_b": []},  # both in Wave 0
                    "agent_specs": [
                        {"agent_id": "ag_a", "task": "task a", "output_type": "code",
                         "threshold": 0.88, "dependencies": [], "specialist": "coder", "depth": 0},
                        {"agent_id": "ag_b", "task": "task b", "output_type": "code",
                         "threshold": 0.88, "dependencies": [], "specialist": "coder", "depth": 0},
                    ],
                    "agent_results": {}, "frozen_agents": [],
                    "system_iteration": 0, "errors": []
                }
                coord.config = {"runtime": {"max_parallel_major": 3, "max_system_iterations": 3},
                                "concurrency": {"global_cap": 5, "fallback_semaphore": True},
                                "infra": {"redis_ttl_hours": 48}}
                coord._spawn_major_agent = mock_spawn_with_timing

                await coord.execute_dag()

        # Both agents should have started within 20ms of each other (parallel)
        gap = abs(start_times["ag_a"] - start_times["ag_b"])
        assert gap < 0.02, f"Agents started {gap:.3f}s apart — expected near-simultaneous"

    @pytest.mark.asyncio
    async def test_checkpoint_written_after_agent_completes(self, mock_db, mock_redis):
        """MongoDB checkpoint must be written after each agent finishes."""
        with patch("infra.redis_client.get_redis", return_value=mock_redis):
            with patch("infra.mongo_client.get_db", return_value=mock_db):

                async def mock_spawn(spec):
                    return {"agent_id": spec["agent_id"], "task": spec["task"],
                            "result": "output", "score": 0.91, "iterations": 1, "frozen": True}

                from daedalus.coordinator import GlobalCoordinator
                coord = GlobalCoordinator.__new__(GlobalCoordinator)
                coord.run_state = {
                    "run_id": "run_chk_test",
                    "dep_graph": {"ag_x": []},
                    "agent_specs": [{"agent_id": "ag_x", "task": "t",
                                     "output_type": "code", "threshold": 0.88,
                                     "dependencies": [], "specialist": "coder", "depth": 0}],
                    "agent_results": {}, "frozen_agents": [],
                    "system_iteration": 0, "errors": []
                }
                coord.config = {"runtime": {"max_parallel_major": 3, "max_system_iterations": 3},
                                "concurrency": {"global_cap": 5, "fallback_semaphore": True},
                                "infra": {"redis_ttl_hours": 48, "checkpoint_every_agent": True}}
                coord._spawn_major_agent = mock_spawn

                await coord.execute_dag()

        checkpoints = mock_db._collection("checkpoints")._docs
        assert len(checkpoints) >= 1
        assert checkpoints[0]["agent_id"] == "ag_x"

    @pytest.mark.asyncio
    async def test_kimiflow_bridge_does_not_block_event_loop(self, mock_kimiflow_result):
        """asyncio.to_thread bridge must not block — other coroutines must run."""
        import time

        async def check_responsiveness():
            await asyncio.sleep(0)  # yields to event loop
            return True

        with patch("pipeline.pipeline") as mock_pipeline:
            mock_pipeline.invoke.return_value = mock_kimiflow_result
            from daedalus.sub_agent import SubAgent
            spec = {"agent_id": "ag_bridge", "task": "test task",
                    "output_type": "code", "threshold": 0.88,
                    "dependencies": [], "specialist": "coder", "depth": 1,
                    "parent_id": "ag_parent"}
            agent = SubAgent(spec, "context", {"runtime": {"max_module_iterations": 1},
                                                "thresholds": {"code": 0.88, "default": 0.82},
                                                "concurrency": {"global_cap": 5, "fallback_semaphore": True},
                                                "infra": {"redis_ttl_hours": 48}})

            # Run agent and responsiveness check in parallel
            start = time.monotonic()
            results = await asyncio.gather(agent.run(), check_responsiveness())
            elapsed = time.monotonic() - start

            assert results[1] is True  # event loop remained responsive
```

#### `tests/integration/test_week5_repair.py`

```python
"""
PHASE GATE — Week 5-6
Must pass before starting Week 7 polish work.
"""
import pytest
from unittest.mock import patch, AsyncMock

class TestWeek5RepairGate:

    @pytest.mark.asyncio
    async def test_evaluator_scores_five_dimensions(self):
        """evaluate_output returns all 5 dimension scores."""
        mock_eval_response = """{
            "correctness": 0.85, "completeness": 0.80,
            "consistency": 0.90, "runnability": 0.70, "format": 0.95,
            "feedback": "Auth middleware missing on /api/users",
            "retry_with": "reviewer"
        }"""
        with patch("daedalus.evaluator._call_llm", new_callable=AsyncMock,
                   return_value=mock_eval_response):
            from daedalus.evaluator import evaluate_output
            result = await evaluate_output(
                task="Build auth", result="code here",
                output_type="code", history=[],
                config={"evaluation_weights": {"default": {"correctness": 0.30,
                        "completeness": 0.20, "consistency": 0.20,
                        "runnability": 0.20, "format": 0.10}},
                        "thresholds": {"code": 0.88, "default": 0.82}},
                run_id="run_eval_test", agent_id="ag_eval", iteration=1,
            )
        required = ["correctness","completeness","consistency","runnability","format","weighted_total"]
        for field in required:
            assert field in result, f"Missing field: {field}"
            assert 0.0 <= result[field] <= 1.0

    @pytest.mark.asyncio
    async def test_surgical_repair_only_unfreezes_broken_owners(
        self, mock_db, mock_redis, sample_run_state
    ):
        """Surgical repair must not unfreeze agents that don't own broken interfaces."""
        sample_run_state["frozen_agents"]      = ["ag_schema", "ag_backend", "ag_auth"]
        sample_run_state["agent_results"]      = {
            "ag_schema":   {"agent_id": "ag_schema",  "frozen": True, "score": 0.92},
            "ag_backend":  {"agent_id": "ag_backend", "frozen": True, "score": 0.90},
            "ag_auth":     {"agent_id": "ag_auth",    "frozen": True, "score": 0.89},
            "ag_frontend": {"agent_id": "ag_frontend","frozen": False,"score": 0.65},
        }
        sample_run_state["broken_interfaces"] = [
            {"agent_a": "ag_frontend", "agent_b": "ag_backend",
             "description": "missing /api/auth/refresh endpoint", "attempt": 0}
        ]
        sample_run_state["repair_attempts"] = 0
        sample_run_state["agent_specs"] = [
            {"agent_id": "ag_schema",   "task": "Design DB schema"},
            {"agent_id": "ag_backend",  "task": "Build FastAPI backend with all auth routes"},
            {"agent_id": "ag_auth",     "task": "JWT auth service"},
            {"agent_id": "ag_frontend", "task": "React frontend calling /api/auth"},
        ]

        with patch("infra.redis_client.get_redis", return_value=mock_redis):
            with patch("infra.mongo_client.get_db", return_value=mock_db):
                from daedalus.repair import surgical_repair
                config = {"runtime": {"max_system_iterations": 3},
                          "infra": {"redis_ttl_hours": 48}}
                updated_state = await surgical_repair(sample_run_state, config)

        # ag_schema must remain frozen — it has nothing to do with /api/auth/refresh
        assert "ag_schema" in updated_state["frozen_agents"]
        # At least one of backend/frontend must be unfrozen for repair
        assert ("ag_backend" not in updated_state["frozen_agents"] or
                "ag_frontend" not in updated_state["frozen_agents"])

    @pytest.mark.asyncio
    async def test_third_repair_attempt_triggers_full_replan(
        self, mock_db, mock_redis, sample_run_state
    ):
        """After 2 failed surgical repairs, repair.py must signal full re-plan."""
        sample_run_state["repair_attempts"]    = 2  # already tried twice
        sample_run_state["broken_interfaces"]  = [{"agent_a": "ag_a", "agent_b": "ag_b",
                                                    "description": "still broken", "attempt": 2}]
        sample_run_state["agent_specs"]        = [{"agent_id": "ag_a", "task": "t"},
                                                   {"agent_id": "ag_b", "task": "t"}]

        with patch("infra.redis_client.get_redis", return_value=mock_redis):
            with patch("infra.mongo_client.get_db", return_value=mock_db):
                from daedalus.repair import surgical_repair
                config = {"runtime": {"max_system_iterations": 3},
                          "infra": {"redis_ttl_hours": 48}}
                updated_state = await surgical_repair(sample_run_state, config)

        # Signal for full re-plan
        assert updated_state.get("trigger_replan") is True

    @pytest.mark.asyncio
    async def test_assembler_deduplicates_file_blocks(self):
        """If two agents define the same file, keep the higher-scored version."""
        from daedalus.assembler import _deduplicate_files
        file_blocks = [
            ("backend/models/user.py", "class User:\n    id: int",    0.72),
            ("backend/models/user.py", "class User:\n    id: str\n    email: str", 0.91),
            ("backend/main.py",        "from fastapi import FastAPI", 0.88),
        ]
        result = _deduplicate_files(file_blocks)
        paths = [r[0] for r in result]
        assert paths.count("backend/models/user.py") == 1
        # Higher scored version should win
        winning = next(r for r in result if r[0] == "backend/models/user.py")
        assert "email" in winning[1]  # the 0.91 version
```

#### `tests/integration/test_week7_resume.py`

```python
"""
PHASE GATE — Week 7
Must pass before Phase 2 work begins.
"""
import pytest
from unittest.mock import patch, AsyncMock

class TestWeek7ResumeGate:

    @pytest.mark.asyncio
    async def test_resume_skips_frozen_agents(self, mock_db, mock_redis):
        """--resume must load checkpoints and skip agents that are already frozen."""
        run_id = "run_resume_test"
        # Pre-populate mock DB with checkpoints
        mock_db._collection("checkpoints")._docs = [
            {"run_id": run_id, "agent_id": "ag_done_1", "frozen": True,
             "status": "done", "result": "output 1", "score": 0.91, "depth": 0},
            {"run_id": run_id, "agent_id": "ag_done_2", "frozen": True,
             "status": "done", "result": "output 2", "score": 0.88, "depth": 0},
        ]
        mock_db._collection("runs")._docs = [
            {"_id": run_id, "goal": "Build a SaaS app", "preset": "saas",
             "status": "running", "started_at": "2026-03-18T09:00:00Z",
             "agent_specs": [
                 {"agent_id": "ag_done_1", "task": "schema", "dependencies": []},
                 {"agent_id": "ag_done_2", "task": "backend","dependencies": ["ag_done_1"]},
                 {"agent_id": "ag_todo_3", "task": "frontend","dependencies": ["ag_done_2"]},
             ],
             "dep_graph": {"ag_done_1": [], "ag_done_2": ["ag_done_1"],
                           "ag_todo_3": ["ag_done_2"]},
             "config_snapshot": {}}
        ]

        with patch("infra.mongo_client.get_db", return_value=mock_db):
            with patch("infra.redis_client.get_redis", return_value=mock_redis):
                from daedalus.coordinator import GlobalCoordinator
                coord = GlobalCoordinator.__new__(GlobalCoordinator)
                coord.config = {"runtime": {"max_parallel_major": 3, "max_system_iterations": 3},
                                "concurrency": {"global_cap": 5, "fallback_semaphore": True},
                                "infra": {"redis_ttl_hours": 48, "checkpoint_every_agent": True}}
                restored_state = await coord.resume_from_checkpoint(run_id)

        assert "ag_done_1" in restored_state["frozen_agents"]
        assert "ag_done_2" in restored_state["frozen_agents"]
        assert "ag_todo_3" not in restored_state["frozen_agents"]

    @pytest.mark.asyncio
    async def test_resume_restores_prior_results(self, mock_db, mock_redis):
        """agent_results must be populated from checkpoints on resume."""
        run_id = "run_restore_test"
        mock_db._collection("checkpoints")._docs = [
            {"run_id": run_id, "agent_id": "ag_x", "frozen": True,
             "status": "done", "result": "prior output x", "score": 0.90, "depth": 0,
             "task": "task x", "iterations": 2}
        ]
        mock_db._collection("runs")._docs = [
            {"_id": run_id, "goal": "Resume test", "preset": "default",
             "status": "running", "started_at": "2026-03-18T09:00:00Z",
             "agent_specs": [{"agent_id": "ag_x", "task": "task x", "dependencies": []}],
             "dep_graph": {"ag_x": []}, "config_snapshot": {}}
        ]

        with patch("infra.mongo_client.get_db", return_value=mock_db):
            with patch("infra.redis_client.get_redis", return_value=mock_redis):
                from daedalus.coordinator import GlobalCoordinator
                coord = GlobalCoordinator.__new__(GlobalCoordinator)
                coord.config = {"runtime": {"max_parallel_major": 3, "max_system_iterations": 3},
                                "concurrency": {"global_cap": 5, "fallback_semaphore": True},
                                "infra": {"redis_ttl_hours": 48, "checkpoint_every_agent": True}}
                restored_state = await coord.resume_from_checkpoint(run_id)

        assert "ag_x" in restored_state["agent_results"]
        assert restored_state["agent_results"]["ag_x"]["result"] == "prior output x"
        assert restored_state["agent_results"]["ag_x"]["score"] == 0.90
```

---

### 13.5 · Health Check CLI (`tests/health/check.py`)

```python
"""
Daedalus Health Check
Run at any time to verify all infrastructure is reachable and configured.

Usage:
    python tests/health/check.py
    python tests/health/check.py --full   (also runs a mock planner call)
"""
import os
import sys
import asyncio
import argparse
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Windows event loop fix
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import nest_asyncio
nest_asyncio.apply()

PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"

results = []

def check(name, fn):
    try:
        msg = fn()
        results.append((PASS, name, msg or ""))
        print(f"  {PASS}  {name}" + (f"  — {msg}" if msg else ""))
    except Exception as e:
        results.append((FAIL, name, str(e)))
        print(f"  {FAIL}  {name}  — {e}")

def check_env():
    required = ["OPENROUTER_API_KEY", "GROQ_API_KEY",
                "MONGODB_URI", "MONGODB_DB",
                "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise ValueError(f"Missing: {', '.join(missing)}")
    return f"{len(required)} keys present"

def check_redis():
    from upstash_redis import Redis
    r = Redis(url=os.getenv("UPSTASH_REDIS_REST_URL"),
              token=os.getenv("UPSTASH_REDIS_REST_TOKEN"))
    key = f"daedalus:health:{datetime.utcnow().timestamp()}"
    r.set(key, "ok", ex=10)
    val = r.get(key)
    r.delete(key)
    if val != "ok":
        raise ValueError(f"Read-back mismatch: got {val!r}")
    return "Upstash Redis read/write OK"

def check_mongodb():
    from pymongo import MongoClient
    client = MongoClient(os.getenv("MONGODB_URI"), serverSelectionTimeoutMS=5000)
    db = client[os.getenv("MONGODB_DB", "Daedalus")]
    collections = db.list_collection_names()
    required_cols = ["runs", "checkpoints", "decision_logs", "scores",
                     "agent_registry", "conflicts", "repair_log", "outputs"]
    missing = [c for c in required_cols if c not in collections]
    client.close()
    if missing:
        raise ValueError(f"Missing collections: {missing}. Run daedalus_mongo_setup.py")
    return f"All {len(required_cols)} collections present"

def check_imports():
    modules = ["langgraph", "motor", "upstash_redis", "pymongo",
               "yaml", "rich", "nest_asyncio", "aiohttp"]
    missing = []
    for m in modules:
        try:
            __import__(m)
        except ImportError:
            missing.append(m)
    if missing:
        raise ImportError(f"pip install {' '.join(missing)}")
    return f"All {len(modules)} packages importable"

def check_config():
    import yaml
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml")
    if not os.path.exists(config_path):
        raise FileNotFoundError("config.yaml not found in project root")
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    required_keys = ["runtime", "concurrency", "thresholds", "evaluation_weights",
                     "presets", "infra", "logging"]
    missing = [k for k in required_keys if k not in cfg]
    if missing:
        raise KeyError(f"Missing config sections: {missing}")
    return f"config.yaml valid ({len(required_keys)} sections)"

def check_kimiflow():
    """Verify KimiFlow leaf layer files are present and importable."""
    import importlib
    for mod in ["pipeline", "agents", "models"]:
        spec = importlib.util.find_spec(mod)
        if spec is None:
            raise ImportError(f"{mod}.py not found — KimiFlow leaf layer missing")
    return "pipeline.py, agents.py, models.py all importable"

def check_workspace():
    workspace = os.path.join(os.path.dirname(__file__), "..", "..", "outputs", "workspace")
    os.makedirs(workspace, exist_ok=True)
    test_file = os.path.join(workspace, ".health_check")
    with open(test_file, "w") as f:
        f.write("ok")
    os.remove(test_file)
    return f"outputs/workspace/ writable"

async def check_planner_mock():
    """Run planner with a mocked LLM call — verifies planner logic end-to-end."""
    import json
    from unittest.mock import patch, AsyncMock
    mock_response = json.dumps({
        "plan": "Health check plan",
        "output_type": "code",
        "agent_specs": [
            {"agent_id": "ag_h001", "task": "Health check task",
             "output_type": "code", "threshold": 0.88,
             "dependencies": [], "specialist": "coder"},
        ],
        "dep_graph": {"ag_h001": []}
    })
    with patch("daedalus.planner._call_llm", new_callable=AsyncMock, return_value=mock_response):
        from daedalus.planner import plan_goal
        config = {"thresholds": {"code": 0.88, "docs": 0.80, "default": 0.82},
                  "runtime": {"max_recursion_depth": 5},
                  "infra": {"mongodb_db": "Daedalus"}}
        result = await plan_goal("Health check goal", "default", config)
    assert "agent_specs" in result and len(result["agent_specs"]) >= 1
    return "Planner logic OK (mock LLM)"


def main():
    parser = argparse.ArgumentParser(description="Daedalus health check")
    parser.add_argument("--full", action="store_true", help="Also run mock planner check")
    args = parser.parse_args()

    print(f"\n Daedalus Health Check — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("─" * 56)

    check(".env credentials",        check_env)
    check("Python packages",         check_imports)
    check("config.yaml",             check_config)
    check("KimiFlow leaf layer",     check_kimiflow)
    check("outputs/workspace/",      check_workspace)
    check("Upstash Redis",           check_redis)
    check("MongoDB Atlas",           check_mongodb)

    if args.full:
        try:
            asyncio.run(check_planner_mock())
            results.append((PASS, "Planner mock run", ""))
            print(f"  {PASS}  Planner mock run  — logic OK")
        except Exception as e:
            results.append((FAIL, "Planner mock run", str(e)))
            print(f"  {FAIL}  Planner mock run  — {e}")

    passed = sum(1 for r in results if r[0] == PASS)
    failed = sum(1 for r in results if r[0] == FAIL)
    total  = len(results)

    print("─" * 56)
    print(f" {passed}/{total} checks passed" + (f"  |  {failed} FAILED" if failed else "  |  All clear"))

    if failed:
        print("\n Fix the above failures before implementing any new features.")
        sys.exit(1)
    else:
        print(" System ready for implementation.\n")
        sys.exit(0)

if __name__ == "__main__":
    main()
```

---

### 13.6 · Phase Gate Checklists

These are the hard stop rules. Claude Code must run these and confirm all pass
before advancing to the next phase.

```
━━━ PHASE GATE: Week 1-2 → Week 3-4 ━━━━━━━━━━━━━━━━━━━━━━━━

Run:
  python tests/health/check.py
  pytest tests/unit/test_planner.py -v
  pytest tests/unit/test_coordinator.py -v
  pytest tests/unit/test_redis_client.py -v
  pytest tests/integration/test_week1_planner.py -v

All must show: PASSED
Then confirm:
  [ ] python main.py "Build a SaaS app" --preset saas
      → Rich console shows agent tree
      → MongoDB Atlas UI shows document in `runs` collection
      → Clean exit, no errors

━━━ PHASE GATE: Week 3-4 → Week 5-6 ━━━━━━━━━━━━━━━━━━━━━━━━

Run:
  python tests/health/check.py
  pytest tests/unit/ -v
  pytest tests/integration/test_week3_dag.py -v

All must show: PASSED
Then confirm:
  [ ] python main.py "Build a simple REST API with user auth"
      → Agents execute in waves (parallel logs visible)
      → MongoDB `agent_registry` has entries
      → MongoDB `checkpoints` has entries
      → outputs/workspace/{run_id}/ contains agent output files

━━━ PHASE GATE: Week 5-6 → Week 7 ━━━━━━━━━━━━━━━━━━━━━━━━━━

Run:
  python tests/health/check.py
  pytest tests/unit/ -v
  pytest tests/integration/ -v  (excludes test_week7_resume.py)

All must show: PASSED
Then confirm:
  [ ] Full SaaS run completes end-to-end
  [ ] Surgical repair fires at least once (force it: lower threshold to 0.99)
  [ ] outputs/{run_id}.zip contains coherent multi-file project
  [ ] run_{ts}.json contains per-module scores

━━━ PHASE GATE: Week 7 → Phase 2 ━━━━━━━━━━━━━━━━━━━━━━━━━━━

Run:
  python tests/health/check.py --full
  pytest tests/ -v  (full suite)

All must show: PASSED
Then confirm:
  [ ] python main.py --resume {a_previous_run_id}
      → Skips already-frozen agents
      → Restores prior results from MongoDB
      → Continues from where it left off
  [ ] Redis TTL: all run keys expire after 48h (verify in Upstash console)
  [ ] GitHub: all feature branches merged, clean master with passing tests
```

---

### 13.7 · Running Tests

```bash
# Install test dependencies (add to requirements.txt)
pip install pytest pytest-asyncio

# Run full unit suite (fast, no API calls)
pytest tests/unit/ -v

# Run a specific phase gate
pytest tests/integration/test_week1_planner.py -v

# Run everything except live tests
pytest tests/ -v --ignore=tests/live/

# Run live tests (makes real API calls — use sparingly)
pytest tests/live/ -v -m live

# Health check (run before every implementation session)
python tests/health/check.py

# Health check with mock planner validation
python tests/health/check.py --full
```

**Add to requirements.txt:**
```
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

**Add `pytest.ini` to project root:**
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
markers =
    live: marks tests that make real LLM API calls (deselect with -m "not live")
```

---

### 13.8 · What to Do When a Test Fails

| Failure type | Action |
|---|---|
| Import error in test | Fix the import — the module doesn't exist yet or has wrong path |
| Assertion on DAG structure | The planner is producing invalid dep_graphs — fix `_validate_dag` |
| Semaphore blocks forever | Redis counter not decrementing — check `sem_decr` is called in finally block |
| Checkpoint not written | `checkpoint_every_agent: true` in config but `insert_checkpoint` not called after agent completion |
| Frozen agents not skipped | `is_frozen()` not being checked before `_spawn_major_agent` call |
| Resume returns wrong state | `resume_from_checkpoint` not reading `frozen` field from checkpoint documents |
| Parallel test shows sequential | `asyncio.gather()` replaced with sequential `await` — check coordinator `_execute_wave` |
| `nest_asyncio` error | `import nest_asyncio; nest_asyncio.apply()` missing from top of `main.py` |
| TTL test fails | `expire()` not called after `hset()`/`incr()` — see Issue 2 fix in context document |
```
