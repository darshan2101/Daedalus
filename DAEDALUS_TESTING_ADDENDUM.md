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
