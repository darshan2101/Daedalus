# Daedalus — Project Instructions & Architecture

## Code Style
- No verbose comments. Line changes only, no explanations of intent.
- No change lists, no guides, no walkthroughs.
- Output: full function or precise line-level diff — nothing in between.
- Assume full codebase familiarity. Never re-explain what was done.

## My Role in This Project
I am the strict reviewer holding the leash on the Antigravity agent. The user runs manual tests and pastes logs. I review everything the agent produces before it proceeds. The user does not evaluate code quality — that is my job.

### What I need from agent each round:
1. **Full run logs** (not summaries — paste the entire execution)
2. **Agent's plan/reasoning BEFORE it acts** (catch bad intent before bad execution)
3. **Relevant output files when run completes** (diffs, test results, benchmarks, generated code)

### My review criteria (non-negotiable):
- **A fix that introduces a regression is worse than no fix**
- **"It worked on the happy path" is not validation** — edge cases matter
- **Every code change must have a stated invariant it preserves**
- **If the agent touches a file it wasn't asked to touch, that's a flag**
- **Score going down after repair = merger or repair engine is the suspect first**
- **Vague plans get rejected before execution, not debugged after**

---

## Standing Rules — Non-Negotiable

**Rule 1: No fabrication, no editorializing.**
Walkthrough/summary must contain only what the run log directly proves. Unexercised criteria are marked UNVERIFIED. Words like "airtight", "robust", "complete" are banned until I sign off. Agent reports facts. I draw conclusions.

**Rule 2: Cleanup before commencing.**
Every temp script, debug file, throwaway test created during a fix must be deleted and confirmed deleted before the next task begins. Agent lists what it created and deleted at the end of every block.

**Rule 3: Manual run is ground truth.**
Unit tests passing is hygiene, not verification. The manual run log is the only thing that counts. If the manual run shows a hole, the agent's self-assessment is wrong by definition.

**Rule 4: Deviation from stress test criteria is a failure.**
If stated pass criteria say "all 5 agents skip" and one runs, the test failed. Agent documents it as failure, investigates, does not proceed until criteria are met cleanly.

**Rule 5: Test must be written and shown in full BEFORE production code is written.**
Always. No exceptions. Production code first = rejected.

**Rule 6: Every claimed change requires diff or proof.**
Text claims without diffs are rejected. Overseer requires code visibility.

**Rule 7: No regressions on baseline test suite.**
Any fix that reduces passed test count is rolled back. Baseline: 102 passed, 11 skipped (current).

---

## Architecture

```
User Goal
  → Planner (Ollama nemotron-3-super) → agent DAG + dep_graph
  → GlobalCoordinator → topological waves (asyncio.gather)
    → MajorAgent (complexity check → direct or fragment)
      → LocalCoordinator (sub-agents if fragment)
      → sub_agent.py → KimiFlow pipeline (plan→execute→evaluate loop)
  → Merger (conflict detection + parallel resolution)
  → Aggregator (FILE blocks → final_code/)
  → Evaluator (5-dimension weighted score)
  → Repair (unfreeze weakest + inject context)
  → Assembler (ZIP)
  → Reporter (Markdown + JSON summary)
```

**LangGraph state machine:** plan → execute → merge → aggregate → evaluate → repair(loop) → done
**KimiFlow pipeline nodes:** plan(1) → execute(2) → evaluate(3) — router is a conditional edge, NOT a node

## File Map
```
main.py                    ← entry, CLI, phase orchestration, resume logic
config.yaml                ← all runtime/threshold/infra knobs
models.py                  ← LLM provider chains per role
daedalus/
  state.py                 ← RunState, AgentSpec, StepResult TypedDicts
  planner.py               ← goal → agent_specs + dep_graph
  graph.py                 ← LangGraph state machine (primary path)
  coordinator.py           ← GlobalCoordinator, Kahn waves (fallback + wave stagger)
  local_coordinator.py     ← sub-agent wave runner (NOT where thundering herd is)
  major_agent.py           ← complexity check + fragmentation decision
  sub_agent.py             ← LLM call, quality score, retry, recursion limit
  merger.py                ← conflict detection, resolve_conflict(), O4 skip logic
  evaluator.py             ← 5-dimension weighted score
  repair.py                ← repair_if_needed: unfreeze weakest agents
  assembler.py             ← parse_and_zip
  reporter.py              ← report generation
  aggregator.py            ← FILE blocks → final_code/
  circuit_breaker.py       ← Model health tracking, exponential backoff (REDESIGN)
  model_health_schema.py   ← State schema for circuit breaker (REDESIGN)
  component_generator.py   ← Modular generation orchestration (REDESIGN)
  test_validator.py        ← Test execution and feedback extraction (REDESIGN)
infra/
  mongo_client.py          ← Motor async, checkpoints/runs/scores
  redis_client.py          ← Upstash REST, freeze/unfreeze, semaphore
  ollama_client.py         ← AsyncClient wrapper
  semaphore.py             ← global concurrency cap
  workspace.py             ← file I/O for agent outputs
kimiflow/
  agents.py                ← _call_with_fallback(), _call_with_circuit_breaker(), _parse_json()
  pipeline.py
tests/
  unit/                    ← one file per module
  integration/             ← week-based integration tests
  live/
```

## Key Invariants — Never Break
1. `dep_graph` format: `{child_id: [parent_ids]}` — child depends on listed parents
2. `system_score = -1.0` sentinel = not yet evaluated (≠ 0.0 = evaluated and failed)
3. Resume always reloads agent_results from `checkpoints` collection, not `runs`
4. Repair targets `weakest_agents[]` from evaluator first; lowest quality_score fallback
5. Router is a conditional EDGE in LangGraph, NOT a node — recursion formula uses node count only
6. `parse_and_zip` is called AFTER graph completes — never inside a node
7. Thundering herd fix is in `coordinator.py` (wave launch) NOT `local_coordinator.py`
8. Patch imports at usage site: `daedalus.merger.get_db` not `infra.mongo_client.get_db`
9. Circuit breaker preserves all model state on every call (no lost tracking)
10. Component generator must not modify existing agent execution until fully integrated

## Infrastructure
| Service | Status | Purpose |
|---------|--------|---------|
| OpenRouter | Active | Free model waterfall, primary |
| Groq | Active | llama-3.3-70b-versatile, fast fallback |
| Ollama Cloud | Active | nemotron-3-super for planning — KEY WAS ROTATED, NOW WORKING |
| Upstash Redis | Active | huge-parrot-75854.upstash.io — freeze flags, semaphores, circuit breaker state |
| MongoDB Atlas M0 | Active | Daedalus DB — checkpoints, runs, scores, conflicts |

Repo: `github.com/darshan2101/Daedalus` | Local: `d:\Dev\Daedalus\`

## Current Project Status

### Phase 1: Foundation (Days 1-2) — IN PROGRESS
**Decision:** Use Upstash (synchronous) for circuit breaker

**Tasks:**
1. ✅ Tests written first (test_circuit_breaker.py)
2. ⏳ Create model_health_schema.py
3. ⏳ Implement circuit_breaker.py (synchronous, Upstash)
4. ⏳ Update agents.py with circuit breaker wrapper
5. ⏳ Update instruction sets in agents.py (6-item checklists)

**Verification gate:** All 5 steps complete + pytest passes + no regressions
