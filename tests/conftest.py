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
