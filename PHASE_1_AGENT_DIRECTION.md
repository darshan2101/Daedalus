# PHASE 1 EXECUTION DIRECTION
## For Agent - Copy/Paste to Agent Chat

---

**DECISION MADE: Use Upstash (Synchronous)**

Your `implementation_plan.md` is solid. One decision needed:

**Redis Client:** Use Upstash (synchronous) instead of redis.asyncio.

**Why:** Upstash already integrated, synchronous sufficient for health tracking, keeps infrastructure consistent.

**Changes to blueprint:**
- Circuit breaker uses `infra.redis_client` (existing Upstash client)
- `ModelHealthTracker` methods stay synchronous (no `async`)
- All storage/retrieval via `redis_client.set()` and `redis_client.get()`
- Circuit breaker integrates at agent call level (not async wrapper)

---

## PHASE 1 EXECUTION (Tests First)

Follow your `implementation_plan.md` exactly. Do these in order:

### Step 1: Create test file FIRST
**File:** `tests/unit/test_circuit_breaker.py` (NEW)

Tests must verify:
- ☐ Circuit opens after 3 consecutive errors
- ☐ Circuit stays open before timeout window
- ☐ Exponential backoff escalates (180s → 360s → 720s...)
- ☐ Success resets error counter
- ☐ Redis schema matches expected keys

Mock the Redis client (don't use real Redis in unit tests).

**Run:** `pytest tests/unit/test_circuit_breaker.py -v`
Should FAIL initially (code doesn't exist). ✓

### Step 2: Create model health schema
**File:** `daedalus/model_health_schema.py` (NEW)

Simple dict defining:
```python
MODEL_HEALTH_SCHEMA = {
    "model": "z-ai/glm-4.5-air:free",
    "status": "healthy|degraded|circuit_open",
    "consecutive_errors": 0,
    "last_error_time": 1711891200,
    "circuit_open_until": 1711891380,
    "backoff_multiplier": 1.0,
}
```

Include formula comment: `backoff_sec = 180 * (2 ** backoff_multiplier)`

### Step 3: Create circuit breaker (synchronous Upstash)
**File:** `daedalus/circuit_breaker.py` (NEW)

Implement `ModelHealthTracker` class with:
```python
def __init__(self, redis_client):  # Takes upstash Redis instance
def get_state(self, model: str) -> dict:
def record_success(self, model: str) -> None:
def record_error(self, model: str, error: str) -> dict:
def can_use_model(self, model: str) -> bool:
def _default_state(self, model: str) -> dict:
def _save_state(self, model: str, state: dict) -> None:
```

Key implementation notes:
- **Synchronous** (no async/await)
- Use `self.redis.get(key)` and `self.redis.set(key, value, ex=86400)`
- Handle Redis errors gracefully (print, return default)
- Open circuit after 3 errors with exponential backoff

**Run:** `pytest tests/unit/test_circuit_breaker.py -v`
Should PASS now. ✓

**Run full suite:** `pytest tests/ -v --tb=short`
Verify no regressions. ✓

### Step 4: Update agents.py with circuit breaker wrapper
**File:** `kimiflow/agents.py` (MODIFY)

Add at top:
```python
from daedalus.circuit_breaker import get_health_tracker
```

Create new wrapper function (before `_call_with_fallback`):
```python
def _call_with_circuit_breaker(model_list, system, user, temperature=0.7):
    """
    Wrapper that skips models in circuit_open state.
    Calls _call_with_fallback for available models.
    Records success/error to health tracker.
    """
    tracker = get_health_tracker()
    
    for model in model_list:
        if not tracker.can_use_model(model):
            continue
        
        try:
            result = _call_with_fallback([model], system, user, temperature)
            tracker.record_success(model)
            return result
        except Exception as e:
            tracker.record_error(model, str(e))
            continue
    
    raise RuntimeError(f"All models failed.")
```

Update all 7 role functions to use circuit breaker.

Example change in `coder_execute()`:
```python
# OLD:
# return _call_with_fallback(CODER_MODELS, system, task, temperature=0.7)

# NEW:
return _call_with_circuit_breaker(CODER_MODELS, system, task, temperature=0.7)
```

Apply same pattern to:
- `orchestrator_plan()`
- `reasoner_execute()`
- `drafter_execute()`
- `creative_execute()`
- `fast_execute()`
- `evaluator_score()`

**Run:** `pytest tests/ -v --tb=short`
Verify all tests pass. ✓

### Step 5: Update instruction sets in agents.py
**File:** `kimiflow/agents.py` (MODIFY docstrings)

Replace vague role docstrings with 6-item checklists from `AGENT_INSTRUCTION_SETS.md`.

Example for CODER role:
```python
def coder_execute(plan: str, task: str, feedback: str = "") -> str:
    """
    CODER ROLE — Build production-ready code modules
    
    CHECKLIST (verify each):
    ☐ All test cases from spec are implemented
    ☐ All tests pass (0 failures, 0 errors)
    ☐ Error handling is explicit (not hidden in defer/panic)
    ☐ Code follows language conventions (Go: godoc, no globals, error wrapping)
    ☐ No hardcoded values (use config, flags, or parameters)
    ☐ Test coverage is >80% (most functions have unit tests)
    
    OUTPUT FORMAT (JSON):
    {
      "module": "auth-gateway",
      "status": "complete|partial|failed",
      "test_results": {"total": 4, "passed": 4, "coverage": 87},
      "checklist": {...},
      "files": [...],
      "blockers": [],
      "next_module": "user-service"
    }
    """
```

Do this for all 7 roles. Copy checklists from `AGENT_INSTRUCTION_SETS.md`.

**Run:** `pytest tests/ -v --tb=short`
Verify all tests pass. ✓

---

## VERIFICATION GATE — Phase 1 Complete

Before reporting "Phase 1 complete", verify:

- [ ] `test_circuit_breaker.py` exists, all tests pass
- [ ] `model_health_schema.py` exists, schema documented
- [ ] `circuit_breaker.py` exists, synchronous, uses Upstash
- [ ] `agents.py` updated: circuit breaker wrapper added to all 7 roles
- [ ] `agents.py` docstrings: 6-item checklists for all 7 roles
- [ ] Full pytest suite passes: `pytest tests/ -v --tb=short`
- [ ] No regressions (compare to baseline 102 passed, 11 skipped)

**Report format when complete:**
```
Phase 1 Complete ✓

Files created:
- tests/unit/test_circuit_breaker.py
- daedalus/model_health_schema.py
- daedalus/circuit_breaker.py

Files modified:
- kimiflow/agents.py (added circuit breaker wrapper + updated docstrings)

Test results:
- pytest tests/ -v: [X passed, Y skipped]
- No regressions from baseline

Circuit breaker verified:
- Opens after 3 errors ✓
- Uses exponential backoff ✓
- Integrated into all 7 agent roles ✓

Instruction sets verified:
- All 7 roles have 6-item checklists ✓
- No vague language remaining ✓

Ready for Phase 2 approval.
```

---

## STANDING RULES
1. Tests before code (done ✓)
2. One phase at a time (not starting Phase 2)
3. Diffs on every claim (show your changes)
4. No assumptions (ask if unclear)

**Go execute Phase 1. Report when complete.**
