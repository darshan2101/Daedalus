# REDESIGN: FROM MONOLITHIC TO MODULAR GENERATION
## Daedalus Foundation Rewrite

**Authority:** Overseer  
**Status:** ARCHITECTURAL REDESIGN  
**Timeline:** Days, not hours  
**Impact:** Foundation for sustainable 0.88+ scores

---

## THE PROBLEM (Current State)

### Monolithic Generation
```
Goal: "Build 3 Go microservices with auth gateway"
    ↓
Agent generates 50-72K chars in ONE output
    ↓
Evaluator receives wall of text
    ↓
Evaluator can't give specific feedback ("missing something")
    ↓
Agent regenerates ENTIRE 50K output
    ↓
Token waste: 150-200K per iteration
    ↓
Stuck at 0.85 (local optimum)
```

### Why Feedback Fails
```
Evaluator says: "Auth gateway missing from services"
Agent thinks: "Maybe I misunderstood. Let me write all 3 services again"
Result: Same 3 services, still no auth integration
Reason: Problem isn't the services, it's the ARCHITECTURE (how they talk to gateway)
```

### Token Waste Per Iteration
- Agent writes 50K chars
- Evaluator receives truncated 15K (loses context)
- Says "try again"
- Agent writes 50K chars again
- **Burned 100K tokens on same problem**

---

## THE SOLUTION (Modular Generation)

### Component-First
```
Goal: "Build 3 Go microservices with auth gateway"
    ↓
Break into MODULES:
  1. auth-gateway (handler.go, validator.go, tests)
  2. user-service (handler.go, storage.go, tests)
  3. notification-service (handler.go, kafka.go, tests)
  4. shared (config.go, error.go, logger.go, tests)
    ↓
Agent generates MODULE 1: ~3-5K chars + tests
    ↓
Evaluator receives SCOPED input: auth-gateway only
    ↓
Evaluator gives SPECIFIC feedback: "TestJWTExpired failing, fix line 45"
    ↓
Agent fixes MODULE 1: ~500 chars of changes
    ↓
Next module
    ↓
Token efficiency: 30-40K per complete goal (vs 150K monolithic)
```

### Why This Works
1. **Scoped evaluation:** Each module evaluated in isolation, focused feedback
2. **Fast iteration:** Fix one module at a time, not rebuild everything
3. **Test-driven:** Tests are generated first, guide implementation
4. **Token efficient:** Smaller outputs, smaller evaluations
5. **Actionable feedback:** "Line 45 in auth-gateway/validator.go" not "missing something"

---

## ARCHITECTURAL CHANGES

### Current Flow
```
Goal
  ↓
Planner (DAG)
  ↓
MajorAgent (complexity check)
  ↓
SubAgent (execute)
  ↓
Evaluator (monolithic scoring)
  ↓
Repair (unfreeze, retry)
```

### New Flow
```
Goal
  ↓
Planner (MODULAR DAG — list of modules, not agents)
  ↓
ComponentGenerator (for each module)
  ├─ TestGenerator (TDD first)
  ├─ ImplementationGenerator (code from tests)
  ├─ TestValidator (run tests, report pass/fail)
  └─ TestFeedback (if failing, targeted fix)
  ↓
Evaluator (component-level, not monolithic)
  ↓
CircuitBreaker (provider health tracking)
  ↓
Done (or next module)
```

### Key Differences
- **No monolithic outputs:** Each output is a focused component
- **TDD-first:** Tests generated, validated BEFORE implementation
- **Component-level feedback:** Not "failed" but "test X failing"
- **No repair loops:** Feedback is actionable at component level
- **Circuit breaker:** Tracks provider health, pauses failing models

---

## TOKEN EFFICIENCY EXAMPLE

### Monolithic Approach
```
Goal: "User service with 3 endpoints, PostgreSQL, tests"

Iteration 1:
  Agent output: 45K chars (user.go, user_test.go, storage.go, etc.)
  Evaluator input: 45K chars
  Feedback: "Failing tests for CreateUser"
  Tokens: 45K + 45K = 90K

Iteration 2:
  Agent regenerates: 45K chars (rewrites most of it)
  Evaluator input: 45K chars again
  Feedback: "Tests still failing, missing error handling"
  Tokens: 45K + 45K = 90K

Total: 180K tokens for one service
```

### Modular Approach
```
Goal: "User service with 3 endpoints, PostgreSQL, tests"

Module: CreateUser
  TestGen: 2K (3 test cases)
  ImplGen: 1.5K (handler + validator)
  Eval: 2K
  Tokens: 5.5K

  Test fails: TestCreateUserWithDuplicate
  Fix: 500 chars in validator.go
  Re-eval: 1.5K
  Tokens: 7K total for this module

3 endpoints × 7K = 21K tokens total

Total: 21K tokens for one service (vs 180K monolithic)
```

**Savings: 8.5x token efficiency**

---

## WHAT CHANGES IN THE CODE

### File Structure (New)
```
daedalus/
  modular_generation.py          ← NEW: Component generation engine
  component_generator.py         ← NEW: Generates test + impl for each module
  test_validator.py              ← NEW: Runs tests, extracts feedback
  instruction_sets.py            ← MODIFIED: Detailed role definitions
  circuit_breaker.py             ← NEW: Provider health tracking + backoff
  
kimiflow/
  agents.py                       ← MODIFIED: Uses modular generation
  module_executor.py             ← NEW: Executes single component
  tdd_generator.py               ← NEW: Test-first generation
```

### Agent Changes
- **Remove:** Direct calls to `coder_execute()`, `drafter_execute()` with full task
- **Add:** Calls to `generate_module()` which returns {tests, impl, feedback}
- **Add:** Circuit breaker check before each model call
- **Add:** Component-level validation (tests pass/fail)

### Evaluator Changes
- **Remove:** Evaluating 50K char monolithic output
- **Add:** Evaluating 3-5K char focused component
- **Change:** Feedback format from "try again" to "fix component X, test Y failing"

---

## IMPLEMENTATION PHASES

### Phase 1: Foundation (Days 1-2)
- Redesign agent instruction sets (3-6 question checklists per role)
- Build component generation skeleton
- Build test validator
- Implement circuit breaker + Redis schema

### Phase 2: TDD Engine (Days 2-3)
- Implement test-first generation
- Implement test runner (capture pass/fail)
- Integrate with component generator

### Phase 3: Integration (Days 3-4)
- Integrate modular generation into graph.py/coordinator.py
- Test with small goals (single module first)
- Benchmark against old approach

### Phase 4: Validation (Day 5)
- Run benchmark with modular approach
- Measure token efficiency + scores
- Compare to monolithic baseline

---

## VALIDATION CRITERIA

### For Modular Approach to be Success

✅ **Token efficiency:** <50K tokens per typical 3-service goal  
✅ **Score trajectory:** Improves each module iteration (not flat at 0.85)  
✅ **Feedback quality:** Specific ("test X failing") not vague ("missing auth")  
✅ **Test coverage:** All modules have unit tests, passing or explicitly failing  
✅ **Component isolation:** Can fix one module without regenerating others  
✅ **Provider health:** Circuit breaker prevents 3+ consecutive failures per model  

### Comparison Metrics
| Metric | Current | Target |
|--------|---------|--------|
| Tokens per goal | 150-200K | <50K |
| Iterations to 0.88 | 3-5 (stuck) | 1-2 |
| Feedback specificity | Vague | Specific |
| Test coverage | ~30% | >75% |
| Repair effectiveness | Low | High |

---

## KEY ARCHITECTURAL PRINCIPLES

### 1. Modular Components
- Each module: 1-5K chars (single responsibility)
- Can be evaluated, fixed, tested independently
- Fit within token budgets for evaluation

### 2. TDD-First
- Tests generated BEFORE implementation
- Tests define success criteria (not vague "good enough")
- Implementation proven by passing tests

### 3. Detailed Instructions
- Each role has 6-item yes/no checklist
- No vague language ("write good code")
- Specific deliverables (test coverage, error handling, docs)

### 4. Component-Level Feedback
- Feedback targets specific file/function/test
- Not "try again" but "fix TestX on line Y"
- Agent can act on feedback immediately

### 5. Circuit Breaker Health
- Track per-model: consecutive errors, last error time, TPM status
- Pause model for exponential backoff if 3+ errors
- Resume after cooldown, reset counter
- Prevents cascading failures

---

## WHAT HAPPENS TO P1-P4 FIXES?

**Answer: Still apply them, but AFTER redesign.**

Current sequence:
1. Redesign foundation (modular generation + detailed instructions) — Days 1-4
2. Apply P1-P4 fixes (Groq bucket, JSON parser, etc.) — Hours 1-2
3. Run comprehensive benchmark — Hours 2-3
4. Iterate on instruction sets based on results — Days 5+

**Why order matters:**
- P1-P4 fixes are foundation hygiene (circuit breaker is part of redesign)
- Modular generation is architecture (affects how feedback flows)
- Can't fully validate modular approach without P1-P4 in place

---

## AGENT'S ROLE IN THIS

You (as overseer) define:
- ✅ Architecture (modular, TDD-first, component-level feedback)
- ✅ Role instruction sets (detailed checklists)
- ✅ Validation criteria (token efficiency, test coverage)

Agent executes:
- Implements component generator
- Builds test validator
- Implements circuit breaker
- Integrates into graph.py/coordinator.py
- Runs benchmarks

You review:
- Diffs for each phase
- Benchmark results
- Instruction set quality

---

## NEXT DOCUMENT

AGENT_INSTRUCTION_SETS.md — Detailed role definitions (6-item checklists per role, applied to Go microservices example)
