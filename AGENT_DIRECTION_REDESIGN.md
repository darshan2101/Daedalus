# AGENT DIRECTION: DAEDALUS REDESIGN
## Complete Implementation Blueprint

**Authority:** Overseer  
**Status:** APPROVED - Proceed with redesign  
**Timeline:** 5 days (Phase 1-4)  
**Objective:** Transform from monolithic to modular generation with TDD-first approach

---

## YOUR MISSION (Agent)

Redesign Daedalus foundation from:
- **Monolithic generation** (50-72K char outputs) → **Modular generation** (3-5K per component)
- **Vague feedback** ("try again") → **Specific feedback** ("fix TestX on line Y")
- **No provider health tracking** → **Circuit breaker with exponential backoff**
- **Vague agent roles** → **6-item yes/no checklists per role**

**Result:** 8.5x token efficiency + 0.88+ scores achievable

---

## PHASE 1: FOUNDATION (Days 1-2)

### Task 1.1: Update Instruction Sets
**File to modify:** `kimiflow/agents.py` (lines ~200-346)

**What to do:**
Replace vague role instructions with 6-item checklists from `AGENT_INSTRUCTION_SETS.md`

Example: CODER role changes from:
```python
def coder_execute(plan: str, task: str, feedback: str = "") -> str:
    """Qwen3-Coder 480B → GPT-OSS 120B → GLM → Nemotron → Mistral → auto"""
    # ... generic system prompt
```

To:
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
    
    OUTPUT FORMAT:
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

**Files affected:**
- `kimiflow/agents.py` — Update all 7 role functions (orchestrator_plan, coder_execute, reasoner_execute, drafter_execute, creative_execute, fast_execute, evaluator_score)

**Verification:**
- Each role has explicit 6-item checklist in docstring
- Output schema is JSON with "status", "checklist", "blockers" fields
- No vague language like "write good code" remains

---

### Task 1.2: Create Circuit Breaker Infrastructure
**Files to create:**
- `daedalus/circuit_breaker.py` (NEW)
- `daedalus/model_health_schema.py` (NEW)

**What to do:**

**circuit_breaker.py:**
```python
import redis.asyncio as redis
import time
from typing import List
from models import OPENROUTER_KEY, GROQ_KEY

class ModelHealthTracker:
    """Tracks per-model: consecutive errors, circuit state, backoff"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def get_state(self, model: str) -> dict:
        """Get current health state for model"""
        key = f"model_state:{model}"
        state = await self.redis.get(key)
        if state:
            return json.loads(state)
        return self._default_state(model)
    
    async def record_success(self, model: str):
        """Reset error counter on success"""
        state = await self.get_state(model)
        state["consecutive_errors"] = 0
        state["status"] = "healthy"
        await self._save_state(model, state)
    
    async def record_error(self, model: str, error: str):
        """Track error, potentially open circuit"""
        state = await self.get_state(model)
        state["consecutive_errors"] += 1
        state["last_error_time"] = time.time()
        
        if state["consecutive_errors"] >= 3:
            # Open circuit with exponential backoff
            backoff_sec = 180 * (2 ** state["backoff_multiplier"])
            state["status"] = "circuit_open"
            state["circuit_open_until"] = time.time() + backoff_sec
            state["backoff_multiplier"] += 1
            print(f"  [circuit_breaker] {model} OPENED for {backoff_sec}s (attempt #{state['consecutive_errors']})")
        
        await self._save_state(model, state)
        return state["status"]
    
    async def can_use_model(self, model: str) -> bool:
        """Check if model is available (not circuit open)"""
        state = await self.get_state(model)
        if state["status"] == "circuit_open":
            if time.time() < state["circuit_open_until"]:
                return False
            else:
                # Circuit window closed, try again
                state["status"] = "degraded"
                await self._save_state(model, state)
        return True
    
    def _default_state(self, model: str) -> dict:
        return {
            "model": model,
            "status": "healthy",
            "consecutive_errors": 0,
            "last_error_time": None,
            "circuit_open_until": None,
            "backoff_multiplier": 1.0,
        }
    
    async def _save_state(self, model: str, state: dict):
        key = f"model_state:{model}"
        await self.redis.set(key, json.dumps(state), ex=86400)  # 24h TTL

# Global tracker
_health_tracker: ModelHealthTracker = None

async def init_health_tracker(redis_client):
    global _health_tracker
    _health_tracker = ModelHealthTracker(redis_client)

async def get_health_tracker() -> ModelHealthTracker:
    return _health_tracker
```

**model_health_schema.py:**
```python
MODEL_HEALTH_SCHEMA = {
    "model": "z-ai/glm-4.5-air:free",
    "status": "healthy|degraded|circuit_open",
    "consecutive_errors": 0,
    "last_error_time": 1711891200,  # timestamp
    "circuit_open_until": 1711891380,  # timestamp (180s base)
    "backoff_multiplier": 1.0,  # 1x, 2x, 4x, 8x...
}

# Exponential backoff formula:
# backoff_sec = 180 * (2 ** backoff_multiplier)
# Attempt 1: 180s (3 min)
# Attempt 2: 360s (6 min)
# Attempt 3: 720s (12 min)
# etc.
```

**Verification:**
- Circuit breaker tracks 3+ consecutive errors
- Opens circuit with exponential backoff (180s × 2^n)
- Closes circuit after window expires
- Logs when circuit opens/closes

---

### Task 1.3: Create Component Generator Skeleton
**File to create:**
- `daedalus/component_generator.py` (NEW)

**What to do:**

```python
import json
from typing import Dict, List, Optional
from kimiflow.agents import orchestrator_plan, coder_execute, reasoner_execute, drafter_execute, evaluator_score

class ComponentGenerator:
    """Orchestrates generation of a single module"""
    
    def __init__(self, config: dict):
        self.config = config
        self.modules_completed = []
        self.modules_in_progress = []
    
    async def generate_module(self, module_spec: dict) -> dict:
        """
        Generate a single module end-to-end:
        1. Generate tests (TDD first)
        2. Generate implementation
        3. Validate tests pass
        4. Score component
        5. Provide feedback if needed
        
        module_spec = {
            "name": "auth-gateway",
            "responsibility": "Validate JWT tokens",
            "success_criteria": [
                "TestValidJWT: Valid token returns 200 with claims",
                "TestExpiredJWT: Expired token returns 401",
                ...
            ]
        }
        """
        module_name = module_spec["name"]
        print(f"\n📦 Generating module: {module_name}")
        
        # Step 1: Generate tests
        print(f"  1️⃣  Generating tests...")
        tests = await self._generate_tests(module_spec)
        
        # Step 2: Generate implementation
        print(f"  2️⃣  Generating implementation...")
        implementation = await self._generate_implementation(module_spec, tests)
        
        # Step 3: Validate tests
        print(f"  3️⃣  Running tests...")
        test_results = await self._run_tests(module_name, tests, implementation)
        
        # Step 4: Score
        print(f"  4️⃣  Evaluating...")
        score = await self._evaluate_module(module_name, implementation, test_results)
        
        # Step 5: Feedback
        if score < 0.85:
            print(f"  ⚠️  Score {score} < 0.85, requesting fixes...")
            feedback = await self._generate_feedback(module_name, test_results, score)
            return {
                "status": "partial",
                "module": module_name,
                "score": score,
                "test_results": test_results,
                "feedback": feedback,
                "action": "fix"
            }
        else:
            print(f"  ✅ Score {score} ≥ 0.85, module complete")
            self.modules_completed.append(module_name)
            return {
                "status": "complete",
                "module": module_name,
                "score": score,
                "test_results": test_results,
                "files": [
                    f"internal/{module_name}/{module_name}.go",
                    f"internal/{module_name}/{module_name}_test.go"
                ]
            }
    
    async def _generate_tests(self, module_spec: dict) -> str:
        """DRAFTER generates tests from success_criteria"""
        task = f"Write unit tests for {module_spec['name']}\n\nSuccess criteria:\n" + \
                "\n".join(f"- {c}" for c in module_spec["success_criteria"])
        # Call drafter_execute for test generation
        tests = await drafter_execute("", task)
        return tests
    
    async def _generate_implementation(self, module_spec: dict, tests: str) -> str:
        """CODER generates implementation from tests"""
        task = f"Implement {module_spec['name']} module in Go\n\n" + \
                f"Responsibility: {module_spec['responsibility']}\n\n" + \
                f"Tests (you must pass these):\n{tests}"
        # Call coder_execute with tests as guide
        implementation = await coder_execute("", task)
        return implementation
    
    async def _run_tests(self, module_name: str, tests: str, impl: str) -> dict:
        """FAST: Quick test validation"""
        # This is mock — actual would run `go test`
        # For now, ask FAST to validate tests would pass
        task = f"Do these tests pass for this code?\n\nTests:\n{tests}\n\nCode:\n{impl}"
        result = await fast_execute("", task)
        # Parse result for pass/fail counts
        return {"total": 4, "passed": 4, "failed": 0}
    
    async def _evaluate_module(self, module_name: str, implementation: str, test_results: dict) -> float:
        """EVALUATOR scores the module 0-1.0"""
        task = f"Score this Go module {module_name} against the 6-item CODER checklist"
        result = await evaluator_score(task, implementation)
        return result.get("score", 0.0)
    
    async def _generate_feedback(self, module_name: str, test_results: dict, score: float) -> str:
        """Extract actionable feedback for fixing"""
        failing_tests = [t for t in test_results if not t.get("passed")]
        if failing_tests:
            return f"Failing tests: {failing_tests}. Fix the implementation to pass these."
        return "Module incomplete. Review checklist and address gaps."
```

**Verification:**
- Component generator orchestrates test → impl → validate → evaluate
- Returns JSON with status, score, test_results, feedback
- Clear "complete" vs "partial" states

---

### Task 1.4: Create Test Validator
**File to create:**
- `daedalus/test_validator.py` (NEW)

**What to do:**

```python
import subprocess
import json
from typing import Dict, List

class TestValidator:
    """Runs tests and extracts specific feedback"""
    
    async def validate_module(self, module_name: str, test_file: str, impl_file: str) -> dict:
        """
        Run tests for a module and return:
        {
            "status": "passing|partial|failing",
            "test_results": [
                {
                    "name": "TestValidJWT",
                    "status": "pass|fail",
                    "error": "expected 401, got 200"
                }
            ],
            "coverage": 87,
            "feedback": "TestExpiredJWT failing: expected 401, got 200 on line 45"
        }
        """
        # This is pseudo-code — actual would run `go test -v` and parse output
        pass
    
    async def extract_failures(self, test_output: str) -> List[Dict]:
        """Parse test output and extract failing test cases"""
        failures = []
        # Parse test output for FAIL lines
        for line in test_output.split('\n'):
            if 'FAIL:' in line or 'AssertionError' in line:
                failures.append({
                    "test": line.split()[1] if len(line.split()) > 1 else "unknown",
                    "error": line.strip()
                })
        return failures
    
    async def get_coverage(self, coverage_output: str) -> float:
        """Extract coverage percentage"""
        # Parse `go test -cover` output
        pass
```

**Verification:**
- Validator runs tests and captures output
- Extracts specific failures ("test X got Y, expected Z")
- Reports coverage percentage

---

## PHASE 2: MODULAR GENERATION ENGINE (Days 2-3)

### Task 2.1: Implement Orchestrator Component Decomposition
**Modify:** `daedalus/planner.py`

**Change:** After generating agent_specs, add module decomposition

```python
async def plan_goal(goal: str, preset: str, config: dict) -> dict:
    # ... existing planner code ...
    agent_specs = ... # current agent specs
    
    # NEW: Decompose each agent's work into modules
    modules = await decompose_into_modules(goal, agent_specs)
    
    return {
        "agent_specs": agent_specs,
        "modules": modules,  # NEW: list of {name, responsibility, success_criteria}
        "execution_type": "modular"  # Signal to graph.py to use ComponentGenerator
    }

async def decompose_into_modules(goal: str, agent_specs: list) -> list:
    """Break agent tasks into independently testable modules"""
    system = """
    You are a module decomposer. Break the goal into independent modules.
    
    Each module should:
    - Have single responsibility
    - Be testable independently
    - Have clear success criteria
    
    Output JSON:
    {
        "modules": [
            {
                "name": "auth-gateway",
                "responsibility": "Validate JWT tokens",
                "success_criteria": ["TestX: ...", "TestY: ..."]
            }
        ]
    }
    """
    result = await orchestrator_plan(goal)
    # Parse and return modules
    return result.get("modules", [])
```

### Task 2.2: Integrate Circuit Breaker into agents.py
**Modify:** `kimiflow/agents.py` (add circuit breaker wrapper)

```python
from daedalus.circuit_breaker import get_health_tracker

async def _call_with_circuit_breaker(model_list, system, user, temperature=0.7):
    """
    Wrapper around _call_with_fallback that tracks provider health.
    Prevents cascading failures by pausing models after 3 consecutive errors.
    """
    tracker = await get_health_tracker()
    
    for model in model_list:
        # Check circuit status
        can_use = await tracker.can_use_model(model)
        if not can_use:
            continue  # Skip, circuit is open
        
        try:
            result = await _call_with_fallback([model], system, user, temperature)
            await tracker.record_success(model)
            return result
        except Exception as e:
            status = await tracker.record_error(model, str(e))
            if status == "circuit_open":
                print(f"  [⚠️  circuit_breaker] {model} PAUSED after 3 errors")
            continue
    
    raise RuntimeError(f"All models failed. Check circuit breaker status.")

# Update all role functions to use circuit breaker:
async def coder_execute(plan: str, task: str, feedback: str = "") -> str:
    # ... build system prompt ...
    return await _call_with_circuit_breaker(CODER_MODELS, system, task)
```

---

## PHASE 3: INTEGRATION (Days 3-4)

### Task 3.1: Wire Modular Generation into graph.py
**Modify:** `daedalus/graph.py` (execute_node)

```python
async def execute_node(state: RunState) -> dict:
    """
    MODIFIED: Check execution_type
    - If "modular": use ComponentGenerator
    - If "monolithic": use existing MajorAgent
    """
    exec_type = state.get("execution_type", "monolithic")
    
    if exec_type == "modular":
        return await execute_modular(state)
    else:
        return await execute_monolithic(state)  # existing code

async def execute_modular(state: RunState) -> dict:
    """Execute goal by generating modules sequentially"""
    from daedalus.component_generator import ComponentGenerator
    
    generator = ComponentGenerator(config)
    modules = state.get("modules", [])
    results = []
    
    for module_spec in modules:
        result = await generator.generate_module(module_spec)
        results.append(result)
        
        if result["status"] == "partial":
            # Try to fix this module before moving to next
            # ... feedback loop ...
            pass
        
        # Move to next module
    
    return {
        "modules": results,
        "overall_status": "complete" if all(r["status"] == "complete" for r in results) else "partial"
    }
```

### Task 3.2: Test Full Pipeline
**Create:** `tests/unit/test_component_generator.py`

```python
import pytest
from daedalus.component_generator import ComponentGenerator
from daedalus.circuit_breaker import ModelHealthTracker

@pytest.mark.asyncio
async def test_component_generation():
    """End-to-end: generate module, validate tests pass"""
    module_spec = {
        "name": "auth-gateway",
        "responsibility": "Validate JWT",
        "success_criteria": [
            "TestValidJWT returns 200",
            "TestExpiredJWT returns 401"
        ]
    }
    
    generator = ComponentGenerator({})
    result = await generator.generate_module(module_spec)
    
    assert result["status"] in ["complete", "partial"]
    assert "score" in result
    assert "test_results" in result

@pytest.mark.asyncio
async def test_circuit_breaker_opens():
    """Circuit opens after 3 consecutive errors"""
    tracker = ModelHealthTracker(None)
    
    # Simulate 3 errors
    await tracker.record_error("test-model", "error 1")
    await tracker.record_error("test-model", "error 2")
    state = await tracker.record_error("test-model", "error 3")
    
    assert state["status"] == "circuit_open"
    
    # Model should be unavailable
    can_use = await tracker.can_use_model("test-model")
    assert not can_use
```

---

## PHASE 4: VALIDATION (Day 5)

### Task 4.1: Run Comprehensive Benchmark
**What to do:**

```bash
python main.py "Build 3 Go microservices with auth gateway" --preset saas

# Measure:
# - Token count (target: <50K vs baseline 150-200K)
# - Score trajectory (should improve per module)
# - Time to 0.88 (should be 1-2 modules vs 3-5 repairs)
# - Circuit breaker activations (should log pauses)
```

### Task 4.2: Analyze Results
**Report:**
- Token efficiency: 8.5x? (50K vs 150K baseline)
- Score trajectory: Improving? (not flat at 0.85)
- Feedback specificity: Actionable? ("fix TestX" not "try again")
- Test coverage: >75% per module?

---

## STANDING RULES

1. **Tests before code:** Unit test for circuit breaker before implementing it
2. **One phase at a time:** Phase 1 complete + verified before Phase 2 starts
3. **Diffs on every claim:** Show changes for each file modification
4. **No assumptions:** If unclear on any instruction set checklist, ask first
5. **Log-driven:** If benchmark shows issue, analyze log before fixing

---

## VERIFICATION GATES

### After Phase 1 (Days 1-2)
- [ ] Instruction sets have 6-item checklists (no vague language)
- [ ] Circuit breaker implemented (tracks errors, opens after 3)
- [ ] Component generator skeleton functional
- [ ] Test validator runs and extracts specific failures
- [ ] All unit tests pass

### After Phase 2 (Days 2-3)
- [ ] Module decomposition working (goal → modules list)
- [ ] Circuit breaker integrated into _call_with_circuit_breaker
- [ ] All role functions use circuit breaker wrapper
- [ ] End-to-end module generation works (test → impl → validate → score)

### After Phase 3 (Days 3-4)
- [ ] graph.py routes to modular generation
- [ ] Pipeline executes modules sequentially
- [ ] Each module produces JSON with status, score, test_results
- [ ] Feedback loop works (failing tests → targeted fixes)

### After Phase 4 (Day 5)
- [ ] Benchmark run completes
- [ ] Token efficiency measured (<50K target)
- [ ] Score trajectory analyzed (improving per module?)
- [ ] Report generated with all metrics

---

## FILES YOU CONTROL (Overseer)

**For monitoring/approval:**
- Check diffs after each phase
- Approve before next phase begins
- Request changes if checklist seems vague
- Validate benchmark results

---

## NEXT STEPS

1. You approve this direction
2. Agent begins Phase 1 (days 1-2)
3. You review Phase 1 completion
4. Proceed to Phase 2, etc.

**Ready for agent to start?**
