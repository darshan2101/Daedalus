# Daedalus — Decisions & Known Issues Log

## Current Status: Redesign Phase 1 In Progress

**Decision Made:** Monolithic → Modular generation architecture redesign  
**Approach:** TDD-first, component-level feedback, circuit breaker health tracking  
**Timeline:** 5 days (Phase 1-4)  
**Blocker:** P1 (rate limit thundering herd) — now addressed by circuit breaker

---

## Phase 1: Foundation (Days 1-2)

### Tasks (Tests First)
1. **Create:** `tests/unit/test_circuit_breaker.py`
   - Circuit opens after 3 consecutive errors
   - Uses exponential backoff (180s × 2^n)
   - Redis schema matches expected keys
   
2. **Create:** `daedalus/model_health_schema.py`
   - Define `MODEL_HEALTH_SCHEMA` dict
   - Document backoff formula

3. **Create:** `daedalus/circuit_breaker.py` (synchronous Upstash)
   - `ModelHealthTracker` class
   - Methods: `get_state()`, `record_success()`, `record_error()`, `can_use_model()`
   - Use `infra.redis_client` (existing)

4. **Modify:** `kimiflow/agents.py`
   - Add `_call_with_circuit_breaker()` wrapper
   - Update all 7 role functions (orchestrator, coder, reasoner, drafter, creative, fast, evaluator)
   - Replace docstrings with 6-item checklists from `AGENT_INSTRUCTION_SETS.md`

### Verification Gate
- [ ] All tests pass: `pytest tests/unit/test_circuit_breaker.py -v`
- [ ] No regressions: `pytest tests/ -v --tb=short` (102 passed, 11 skipped baseline)
- [ ] Circuit breaker verified: opens after 3 errors, uses exponential backoff
- [ ] All 7 roles have 6-item checklists
- [ ] No vague language in docstrings

---

## Architectural Decisions Made

### Redesign: Modular Generation + TDD-First
- **Old:** Monolithic generation (50-72K chars), vague feedback, stuck at 0.85
- **New:** Modular (3-5K per component), specific feedback, 0.88+ achievable
- **Benefit:** 8.5x token efficiency, actionable feedback loops
- **Key:** Circuit breaker prevents provider cascades, component-level evaluation

### Circuit Breaker for Provider Health
- Tracks per-model: consecutive errors, circuit state, backoff multiplier
- Opens after 3 consecutive errors with exponential backoff (180s × 2^n)
- Synchronous Upstash (no async needed for health tracking)
- Integrates at agent call level via `_call_with_circuit_breaker()` wrapper

### TDD-First Component Generation
- Tests generated before implementation
- Implementation proven by passing tests
- Component-level evaluation gives specific feedback
- No vague "missing auth" — specific "TestJWTExpired failing"

### Instruction Sets: 6-Item Yes/No Checklists
- ORCHESTRATOR: Module decomposition checklist
- CODER: Implementation checklist (tests pass, error handling, conventions)
- REASONER: Integration checklist (data flows, errors consistent)
- DRAFTER: Test & docs checklist (independent tests, coverage >80%)
- EVALUATOR: Scoring checklist (all tests pass, docs complete)
- FAST: Health check checklist (compiles, tests run, no crashes)
- CREATIVE: Chaos testing checklist (failure scenarios handled)

---

## LangGraph as Primary, Inline as Fallback
LangGraph graph (`daedalus/graph.py`) is the primary execution path.
`GlobalCoordinator` (`daedalus/coordinator.py`) is the fallback — proven, stable.
Toggle: `config.runtime.use_langgraph`.

## DAG Scheduling — Kahn's Algorithm
`GlobalCoordinator.get_execution_waves()` computes topological waves.
`dep_graph` format: `{child_agent_id: [parent_agent_ids]}` (child depends on parents).
Used in both LangGraph execute_node and inline coordinator.

## Checkpoint-Based Resume
Every agent result is written to MongoDB `checkpoints` collection after completion.
Resume reloads from checkpoints, not from the runs document (runs doc may be stale).
Fresh `repair_attempts=0, system_iteration=0` on every resume session — intentional.

## Repair Strategy
Repair triggers when `system_score < threshold` AND `repair_attempts < max_repair_attempts`.
Targets `weakest_agents[]` from evaluator output; falls back to lowest quality_score agent.
Repair = unfreeze agent in Redis → re-runs in next execution wave.

## Agent Fragmentation
`MajorAgent` assesses complexity before executing.
Fragments if: 3+ distinct deliverables OR task > 1500 chars AND depth < max_recursion_depth.
Fragmentation spawns `LocalCoordinator` (`daedalus/local_coordinator.py`) for sub-agents.
`allow_fragmentation: false` in config skips the complexity check entirely (speed mode).

## Ollama Priority for Planner/Reasoner
Ollama tried first for planner and reasoner roles (configured in `infra.ollama_roles`).
Falls through to OpenRouter/Groq if Ollama unavailable or times out.

## Upstash Redis (not self-hosted)
Chosen for free tier compatibility — REST API, no connection overhead.
`infra/semaphore.py` provides fallback asyncio.Semaphore if Upstash unreachable.
Now extended for circuit breaker state tracking (synchronous operations).

## SaaS Preset Contract Enforcement
Planner prompt enforces: when agents share an API boundary (frontend↔backend, auth↔backend),
BOTH agents' task descriptions must specify exact endpoint path, method, auth requirement.
This reduces interface breakage caught by evaluator.

## Wave Delay Stagger (P1 — Implemented)
`coordinator.py` wave execution loop staggers agent task creation using
`asyncio.sleep(wave_delay_seconds)` between agents at index > 0 within a wave.
Config key: `runtime.wave_delay_seconds` (default 0, set to 5).
Prevents thundering herd at T=0 without touching model assignments.
Files touched: `config.yaml`, `daedalus/coordinator.py` ✅ Implemented

## P1 — Model De-synchronization (Implemented)
Groq limits confirmed from console: llama-3.3-70b-versatile RPD=1K TPM=12K.
Go benchmark exposed invalid OpenRouter model strings (400/404) wasting retries.
Invalid strings removed: `groq/llama-3.1-8b-instant`, `qwen/qwen3-32b:free`,
`meta-llama/llama-4-scout-17b-16e-instruct:free`, `z-ai/glm-4-flash:free`.
Primary assignments after P1:
- ORCHESTRATOR: `__groq__`
- CODER: `z-ai/glm-4.5-air:free`
- REASONER: `__groq__:llama-3.1-8b-instant` (separate RPD bucket)
- DRAFTER: `google/gemma-3-27b-it:free`
- EVALUATOR: `nvidia/nemotron-3-super-120b-a12b:free`
- FAST: `nvidia/nemotron-3-nano-30b-a3b:free`
`openrouter/free` demoted to last-resort fallback in all lists.
Files touched: `models.py` ✅ Implemented

## P3 — Multi-Model Groq Direct Routing (Implemented)
`__groq__` sentinel in `agents.py` extended to support prefix syntax `__groq__:model-name`.
Bare `__groq__` → `GROQ_MODEL` (llama-3.3-70b-versatile). Prefixed → specified model.
REASONER reassigned to `__groq__:llama-3.1-8b-instant` — separate RPD bucket from ORCHESTRATOR.
Test suite advanced to 93 passed, 11 skipped. Zero regressions.
Files touched: `kimiflow/agents.py`, `models.py`, `tests/unit/test_kimiflow_agents.py` ✅ Implemented

## P3 Extension — Provider Expansion (Cerebras, Scaleway, Nvidia NIM)
Three new providers confirmed live. All use same OpenAI-compatible client pattern as Groq.
Sentinel pattern: `__cerebras__`, `__scaleway__:model`, `__nvidia__:model`.

Dead models — never add:
- Cerebras: `llama-3.3-70b` (404), `gpt-oss-120b` (404), `zai-glm-4.7` (404)
- Scaleway: `qwen3.5-397b-a17b` (None content), `devstral-2` (422)
- Nvidia NIM: `meta/llama-4-scout-17b-16e-instruct` (404), `deepseek-ai/deepseek-r1` (EOL)

Approved role assignments (pending implementation after Phase 1-4 redesign complete):
- ORCHESTRATOR: `__groq__` → `__nvidia__:meta/llama-3.3-70b-instruct` → `__scaleway__:llama-3.3-70b-instruct` → OpenRouter
- CODER: `z-ai/glm-4.5-air:free` → `__cerebras__:qwen-3-235b-a22b-instruct-2507` → `__nvidia__:qwen/qwen2.5-coder-32b-instruct` → `__scaleway__:qwen3-coder-30b-a3b-instruct` → `__groq__:llama-3.1-8b-instant` → OpenRouter
- REASONER: `__groq__:llama-3.1-8b-instant` → `__cerebras__:llama3.1-8b` → `__nvidia__:meta/llama-4-maverick-17b-128e-instruct` → `__scaleway__:llama-3.1-8b-instruct` → OpenRouter
- EVALUATOR: `nvidia/nemotron-3-super-120b-a12b:free` → `__scaleway__:gpt-oss-120b` → `__cerebras__:qwen-3-235b-a22b-instruct-2507` → `__groq__` → OpenRouter
- DRAFTER: `google/gemma-3-27b-it:free` → `__scaleway__:mistral-small-3.2-24b-instruct-2506` → `__scaleway__:llama-3.3-70b-instruct` → `__groq__:llama-3.1-8b-instant` → OpenRouter
- FAST: `nvidia/nemotron-3-nano-30b-a3b:free` → `__cerebras__:llama3.1-8b` → `__scaleway__:llama-3.1-8b-instruct` → `__groq__:llama-3.1-8b-instant` → OpenRouter

## Error Handling — Per-Error-Type Provider Gating
TPD/daily limit → set `_provider_disabled = True`, session kill, print log line.
TPM/RPM 429 → skip this model only, provider stays live, `continue` to next model.
Applies to all providers: Groq, Cerebras, Scaleway, Nvidia NIM.
Detection: daily kill = "tokens per day" / "TPD" / "per day" / "daily" in error string.
TPM skip = `isinstance(e, openai.RateLimitError)` AND no daily-kill string matched.

## O4 — Skip Re-detecting Resolved Conflicts on Resume
`merger.py` `detect_and_resolve_all` loads previously resolved pairs from MongoDB and
skips re-running conflict detection on them. Prevents redundant LLM calls on resume.
Verified in zip + unit test. ✅ Implemented

---

## All Fixes Applied (session record)

| Fix | File | Status |
|-----|------|--------|
| Bug 1: Recursion formula `1+(max_retries*2)+3` | `sub_agent.py` line 88 | ✅ Verified in zip |
| Bug 1b: Default value `max_module_iterations=5` | `sub_agent.py` line 72 | ✅ Verified in zip |
| Bug 2: Threshold epsilon `score >= threshold - 0.005` | `graph.py` route_after_eval | ✅ Verified in zip |
| Bug 3: Patch validation two separate guards | `merger.py` | ✅ Verified in zip |
| N1: Agent freeze on resume | `main.py` | ✅ Verified in zip |
| N2: JSON sanitization `_sanitize_json_escapes()` | `merger.py` line 17 | ✅ Code present, live unverified |
| N3: Score preservation on resume | `main.py` lines 183, 204 | ✅ Code present, live unverified |
| N4: Merger gate on `any_agent_ran` | `graph.py` merge_node | ✅ Verified in live run |
| O4: Skip re-detecting resolved conflicts from DB | `merger.py` detect_and_resolve_all | ✅ Verified in zip + test |
| P1: wave_delay_seconds stagger | `config.yaml`, `coordinator.py` | ✅ Implemented |
| P1: model de-sync + invalid string removal | `models.py` | ✅ Implemented |
| Phase 1: Circuit breaker + instruction sets | `daedalus/circuit_breaker.py, daedalus/model_health_schema.py, kimiflow/agents.py, tests/unit/test_circuit_breaker.py` | ✅ Verified 107 passed |
| P3: `__groq__:model` prefix routing | `kimiflow/agents.py` | ✅ Implemented, 93 passed |
| P3: REASONER → `__groq__:llama-3.1-8b-instant` | `models.py` | ✅ Implemented |
| Dead model removed: `openai/gpt-oss-120b:free` | `models.py` | ✅ Applied |

---

## Known Issues / Watch Points

### LangGraph Exception → Silent State Loss
If LangGraph fails mid-execution, fallback reloads state from MongoDB + checkpoints.
Watch: checkpoint reload in fallback path must happen before GlobalCoordinator init.
Fix already in place (main.py): reloads from DB then checkpoints before fallback.

### Merger Conflict Cap
`max_merger_conflicts: 5` — only top 5 conflicts resolved for speed.
On complex multi-agent runs, minor interface conflicts may survive into final output.

### Windows ProactorEventLoop
`main.py` top: sets `WindowsProactorEventLoopPolicy` + `nest_asyncio.apply()`.
Required for Windows dev environments — do not remove.

### MongoDB `_id` vs `run_id` Legacy
Resume path checks both `run_id` field and `_id` (legacy runs stored run_id as `_id`).
New runs always use `run_id` field. Keep dual-check in resume path.

### Score Sentinel -1.0
`system_score: -1.0` = fresh run, not yet evaluated (distinct from 0.0 = evaluated and failed).
Repair check: `if score < 0: return False` — do not attempt repair before first evaluation.
N3 fix: on resume, preserve existing system_score with -1.0 for fresh starts.

### Circuit Breaker State Persistence
Circuit breaker state stored in Redis with 24h TTL. On process restart, state reloads from Redis.
Watch: TTL must not expire during long-running benchmarks.

### UX1 — Score Display Sentinel
`System score: 0.00` displays when sentinel is `-1.0` (not yet evaluated).
Should display `N/A`. Backlog.

---

## Open Verification Items
| ID | What needs verifying | How |
|----|----------------------|-----|
| N2 | JSON sanitization path actually triggered | Full run hitting malformed JSON from merger |
| N3 | Score preservation on resume | Run with successful evaluation, then resume |
| O3 | Epsilon boundary (Bug 2) | Run where score lands within 0.005 of threshold |
| Phase 2 | TDD engine + modular component generator | Not started |
| Phase2 | Modular generation end-to-end | Benchmark goal → modules → components |

---

## Active Development Areas
- [x] **Phase 1:** Circuit breaker + instruction sets (DONE)
- [ ] **Phase 2:** TDD engine + modular component generator (IN PROGRESS)
- [ ] **Phase 3:** Full pipeline integration
- [ ] **Phase 4:** Comprehensive benchmark + validation
- [ ] P3 extension: Cerebras + Scaleway + Nvidia NIM sentinels (pending Phase 1-4 complete)
- [ ] P2: Payload scoping — large agent outputs (81K chars) exhaust TPM
- [ ] Phase 2: Modal.com integration
- [ ] Phase 2: Cloudflare R2 for workspace storage
