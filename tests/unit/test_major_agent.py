"""Unit tests for daedalus/major_agent.py — no real LLM calls."""
import pytest
import json
from unittest.mock import patch, AsyncMock, MagicMock
import daedalus.local_coordinator


class TestMajorAgentRouting:
    """Test that MajorAgent correctly routes to direct vs fragment."""

    def _make_spec(self, depth=0, task="Build a REST API backend"):
        return {
            "agent_id": "ag_test",
            "task": task,
            "output_type": "code",
            "threshold": 0.88,
            "dependencies": [],
            "specialist": "coder",
            "depth": depth,
            "parent_id": None,
        }

    def _make_state(self):
        return {
            "run_id": "run_major_test",
            "goal": "Build something",
            "preset": "default",
            "agent_specs": [],
            "dep_graph": {},
            "agent_results": {},
            "frozen_agents": [],
            "current_step": "executing",
            "errors": [],
        }

    def _make_config(self, max_depth=5):
        return {
            "runtime": {
                "max_recursion_depth": max_depth,
                "max_module_iterations": 1,
            },
            "thresholds": {"code": 0.88, "default": 0.82},
        }

    @pytest.mark.asyncio
    async def test_short_task_always_direct(self):
        """Tasks < 200 chars should always go direct, skipping LLM assessment."""
        mock_result = {
            "agent_id": "ag_test", "task": "short task",
            "result": "output", "quality_score": 0.91,
            "iterations": 1, "status": "done",
        }
        with patch("daedalus.major_agent.run_agent_task", new_callable=AsyncMock, return_value=mock_result):
            from daedalus.major_agent import MajorAgent
            agent = MajorAgent(self._make_spec(task="Short task"), self._make_config(), self._make_state())
            result = await agent.run()
        assert result["agent_id"] == "ag_test"
        assert result["quality_score"] == 0.91

    @pytest.mark.asyncio
    async def test_max_depth_forces_direct(self):
        """At max_depth - 1, must always go direct regardless of complexity."""
        mock_result = {
            "agent_id": "ag_test", "task": "deep task",
            "result": "output", "quality_score": 0.90,
            "iterations": 1, "status": "done",
        }
        with patch("daedalus.major_agent.run_agent_task", new_callable=AsyncMock, return_value=mock_result):
            from daedalus.major_agent import MajorAgent
            # depth=4, max_depth=5 → at limit, forced direct
            agent = MajorAgent(
                self._make_spec(depth=4, task="X" * 300),
                self._make_config(max_depth=5),
                self._make_state(),
            )
            result = await agent.run()
        assert result["quality_score"] == 0.90

    @pytest.mark.asyncio
    async def test_complexity_direct_route(self):
        """When LLM says should_fragment=false, MajorAgent goes direct."""
        llm_response = json.dumps({
            "should_fragment": False,
            "reason": "Single focused task",
            "sub_tasks": []
        })
        mock_result = {
            "agent_id": "ag_test", "task": "t",
            "result": "direct output", "quality_score": 0.92,
            "iterations": 1, "status": "done",
        }
        with patch("daedalus.major_agent._call_complexity_llm", new_callable=AsyncMock, return_value=llm_response):
            with patch("daedalus.major_agent.run_agent_task", new_callable=AsyncMock, return_value=mock_result):
                from daedalus.major_agent import MajorAgent
                agent = MajorAgent(
                    self._make_spec(task="A" * 900),  # > 800 chars to trigger LLM
                    self._make_config(), self._make_state(),
                )
                result = await agent.run()
        assert result["result"] == "direct output"

    @pytest.mark.asyncio
    async def test_complexity_fragment_route(self):
        """When LLM says should_fragment=true, MajorAgent delegates to LocalCoordinator."""
        llm_response = json.dumps({
            "should_fragment": True,
            "reason": "Multiple deliverables",
            "sub_tasks": [
                {"task": "sub-task 1", "specialist": "coder"},
                {"task": "sub-task 2", "specialist": "coder"},
            ]
        })
        mock_local_result = {
            "agent_id": "ag_test", "task": "t",
            "result": "merged sub output", "quality_score": 0.89,
            "iterations": 1, "status": "done",
        }
        with patch("daedalus.major_agent._call_complexity_llm", new_callable=AsyncMock, return_value=llm_response):
            with patch("daedalus.local_coordinator.LocalCoordinator.run_sub_tasks",
                       new_callable=AsyncMock, return_value=mock_local_result):
                from daedalus.major_agent import MajorAgent
                agent = MajorAgent(
                    self._make_spec(task="A" * 900),
                    self._make_config(), self._make_state(),
                )
                result = await agent.run()
        assert result["result"] == "merged sub output"

    @pytest.mark.asyncio
    async def test_fragment_failure_falls_back_to_direct(self):
        """If LocalCoordinator raises, MajorAgent falls back to direct execution."""
        llm_response = json.dumps({
            "should_fragment": True,
            "reason": "Complex",
            "sub_tasks": [{"task": "sub", "specialist": "coder"}]
        })
        mock_result = {
            "agent_id": "ag_test", "task": "t",
            "result": "fallback output", "quality_score": 0.85,
            "iterations": 1, "status": "done",
        }
        with patch("daedalus.major_agent._call_complexity_llm", new_callable=AsyncMock, return_value=llm_response):
            with patch("daedalus.major_agent.run_agent_task", new_callable=AsyncMock, return_value=mock_result):
                with patch("daedalus.local_coordinator.LocalCoordinator.run_sub_tasks",
                           new_callable=AsyncMock, side_effect=RuntimeError("depth exceeded")):
                    from daedalus.major_agent import MajorAgent
                    agent = MajorAgent(
                        self._make_spec(task="A" * 900),
                        self._make_config(), self._make_state(),
                    )
                    result = await agent.run()
        # Should have fallen back to direct
        assert result["result"] == "fallback output"

    @pytest.mark.asyncio
    async def test_complexity_llm_error_defaults_direct(self):
        """If complexity LLM fails, default to direct execution."""
        mock_result = {
            "agent_id": "ag_test", "task": "t",
            "result": "direct after error", "quality_score": 0.90,
            "iterations": 1, "status": "done",
        }
        with patch("daedalus.major_agent._call_complexity_llm", new_callable=AsyncMock, side_effect=Exception("LLM down")):
            with patch("daedalus.major_agent.run_agent_task", new_callable=AsyncMock, return_value=mock_result):
                from daedalus.major_agent import MajorAgent
                agent = MajorAgent(
                    self._make_spec(task="A" * 900),
                    self._make_config(), self._make_state(),
                )
                result = await agent.run()
        assert result["result"] == "direct after error"
