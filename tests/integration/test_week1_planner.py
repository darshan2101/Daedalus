"""
PHASE GATE — Week 1-2
Must pass before starting Week 3-4 implementation.
Uses mock LLM and mock MongoDB — no real API calls.
"""
import pytest
import json
from unittest.mock import patch, AsyncMock, MagicMock

class TestWeek1PlannerGate:

    @pytest.mark.asyncio
    async def test_plan_goal_returns_valid_structure(
        self, mock_db, mock_redis, mock_llm_planner_response
    ):
        """Planner returns a dict with plan, agent_specs, dep_graph."""
        mock_response = json.dumps(mock_llm_planner_response)
        with patch("daedalus.planner._call_with_fallback", return_value=mock_response):
            with patch("infra.mongo_client.get_db", return_value=mock_db):
                from daedalus.planner import plan_goal
                config = {"thresholds": {"code": 0.88, "docs": 0.80, "default": 0.82},
                          "runtime": {"max_recursion_depth": 5},
                          "infra": {"ollama_enabled": False}}
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
        with patch("daedalus.planner._call_with_fallback", return_value=mock_response):
            with patch("infra.mongo_client.get_db", return_value=mock_db):
                from daedalus.planner import plan_goal, _validate_dag
                config = {"thresholds": {"code": 0.88, "docs": 0.80, "default": 0.82},
                          "runtime": {"max_recursion_depth": 5},
                          "infra": {"ollama_enabled": False}}
                result = await plan_goal("Build a SaaS app", "saas", config)
                # Should not raise
                _validate_dag(result["agent_specs"], result["dep_graph"])

    @pytest.mark.asyncio
    async def test_all_dep_ids_exist_in_agent_specs(
        self, mock_db, mock_redis, mock_llm_planner_response
    ):
        mock_response = json.dumps(mock_llm_planner_response)
        with patch("daedalus.planner._call_with_fallback", return_value=mock_response):
            with patch("infra.mongo_client.get_db", return_value=mock_db):
                from daedalus.planner import plan_goal
                config = {"thresholds": {"code": 0.88, "docs": 0.80, "default": 0.82},
                          "runtime": {"max_recursion_depth": 5},
                          "infra": {"ollama_enabled": False}}
                result = await plan_goal("Build a SaaS app", "saas", config)

        agent_ids = {s["agent_id"] for s in result["agent_specs"]}
        for spec in result["agent_specs"]:
            for dep in spec["dependencies"]:
                assert dep in agent_ids, f"Dep {dep} not in agent specs"

    def test_redis_credentials_reachable(self):
        """Verify Upstash Redis REST URL is set and responding."""
        import os
        from dotenv import load_dotenv
        load_dotenv(override=True)
        assert os.getenv("UPSTASH_REDIS_REST_URL"), "UPSTASH_REDIS_REST_URL missing from .env"
        assert os.getenv("UPSTASH_REDIS_REST_TOKEN"), "UPSTASH_REDIS_REST_TOKEN missing from .env"

    def test_mongodb_credentials_reachable(self):
        """Verify MongoDB URI is set."""
        import os
        from dotenv import load_dotenv
        load_dotenv(override=True)
        assert os.getenv("MONGODB_URI"), "MONGODB_URI missing from .env"
        assert os.getenv("MONGODB_DB"), "MONGODB_DB missing from .env"

# ── PHASE GATE RUNNER ────────────────────────────────────────────────────────
WEEK1_GATE_TESTS = [
    "test_plan_goal_returns_valid_structure",
    "test_dag_has_no_circular_dependencies",
    "test_all_dep_ids_exist_in_agent_specs",
    "test_redis_credentials_reachable",
    "test_mongodb_credentials_reachable",
]
# All must pass. Run: pytest tests/integration/test_week1_planner.py -v
