"""Unit tests for daedalus/local_coordinator.py — no real LLM calls."""
import pytest
from unittest.mock import patch, AsyncMock


class TestLocalCoordinator:
    def _make_parent_spec(self, depth=0):
        return {
            "agent_id": "ag_parent",
            "task": "Build a full backend service",
            "output_type": "code",
            "threshold": 0.88,
            "dependencies": [],
            "specialist": "coder",
            "depth": depth,
            "parent_id": None,
        }

    def _make_state(self):
        return {
            "run_id": "run_local_test",
            "goal": "Build something",
            "preset": "default",
            "agent_specs": [],
            "dep_graph": {},
            "agent_results": {},
            "frozen_agents": [],
            "current_step": "executing",
            "errors": [],
        }

    def _make_config(self, max_depth=5, max_sub=3):
        return {
            "runtime": {
                "max_recursion_depth": max_depth,
                "max_parallel_sub": max_sub,
                "max_module_iterations": 1,
            },
            "thresholds": {"code": 0.88, "default": 0.82},
        }

    @pytest.mark.asyncio
    async def test_depth_guard_raises_at_max(self):
        """LocalCoordinator raises RuntimeError when depth >= max_recursion_depth."""
        from daedalus.local_coordinator import LocalCoordinator
        coord = LocalCoordinator(
            self._make_parent_spec(depth=4),  # depth 4 → sub would be 5 → at limit
            self._make_config(max_depth=5),
            self._make_state(),
        )
        with pytest.raises(RuntimeError, match="Max recursion depth"):
            await coord.run_sub_tasks([{"task": "sub", "specialist": "coder"}])

    @pytest.mark.asyncio
    async def test_sub_specs_built_correctly(self):
        """_build_sub_specs creates proper AgentSpec dicts."""
        from daedalus.local_coordinator import LocalCoordinator
        coord = LocalCoordinator(
            self._make_parent_spec(depth=0),
            self._make_config(),
            self._make_state(),
        )
        sub_tasks = [
            {"task": "Build models", "specialist": "coder"},
            {"task": "Build routes", "specialist": "coder"},
        ]
        specs = coord._build_sub_specs(sub_tasks, "ag_parent", 1)
        assert len(specs) == 2
        assert specs[0]["agent_id"] == "ag_parent_s00"
        assert specs[1]["agent_id"] == "ag_parent_s01"
        assert specs[0]["depth"] == 1
        assert specs[0]["parent_id"] == "ag_parent"

    @pytest.mark.asyncio
    async def test_parallel_execution_merges_results(self):
        """Sub-agents run in parallel and results are merged."""
        mock_results = [
            {"agent_id": "ag_parent_s00", "task": "t1", "result": "output 1",
             "quality_score": 0.90, "iterations": 1, "status": "done"},
            {"agent_id": "ag_parent_s01", "task": "t2", "result": "output 2",
             "quality_score": 0.88, "iterations": 2, "status": "done"},
        ]

        call_count = 0
        async def mock_run_agent(run_id, spec, config, state):
            nonlocal call_count
            result = mock_results[call_count]
            call_count += 1
            return result

        with patch("daedalus.local_coordinator.run_agent_task", side_effect=mock_run_agent):
            from daedalus.local_coordinator import LocalCoordinator
            coord = LocalCoordinator(
                self._make_parent_spec(depth=0),
                self._make_config(),
                self._make_state(),
            )
            result = await coord.run_sub_tasks([
                {"task": "t1", "specialist": "coder"},
                {"task": "t2", "specialist": "coder"},
            ])

        assert result["agent_id"] == "ag_parent"
        assert "output 1" in result["result"]
        assert "output 2" in result["result"]
        assert result["quality_score"] == pytest.approx(0.88, abs=0.01)
        assert result["status"] == "done"

    @pytest.mark.asyncio
    async def test_merge_handles_empty_results(self):
        """Merging zero sub-results returns a failed StepResult."""
        from daedalus.local_coordinator import LocalCoordinator
        coord = LocalCoordinator(
            self._make_parent_spec(), self._make_config(), self._make_state(),
        )
        result = coord._merge_sub_results([])
        assert result["status"] == "failed"
        assert result["quality_score"] == 0.0

    @pytest.mark.asyncio
    async    def test_partial_failure_marked_failed(self):
        """If some sub-agents fail, merged status is 'failed' (not 'partial')."""
        from daedalus.local_coordinator import LocalCoordinator
        coord = LocalCoordinator(
            self._make_parent_spec(), self._make_config(), self._make_state(),
        )
        sub_results = [
            {"agent_id": "s00", "result": "ok", "quality_score": 0.90,
             "iterations": 1, "status": "done"},
            {"agent_id": "s01", "result": "fail", "quality_score": 0.40,
             "iterations": 1, "status": "failed"},
        ]
        result = coord._merge_sub_results(sub_results)
        assert result["status"] == "failed"
