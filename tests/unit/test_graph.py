"""Unit tests for daedalus/graph.py — routing logic, no real LLM calls."""
import pytest


class TestGraphRouting:
    """Test the conditional edge routing functions."""

    def test_route_after_eval_passes(self):
        """Score above threshold routes to 'done'."""
        from daedalus.graph import route_after_eval
        state = {
            "config": {"thresholds": {"system": 0.85}, "runtime": {"max_repair_attempts": 3}},
            "system_score": 0.90,
            "repair_attempts": 0,
        }
        assert route_after_eval(state) == "done"

    def test_route_after_eval_fails(self):
        """Score below threshold routes to 'repair'."""
        from daedalus.graph import route_after_eval
        state = {
            "config": {"thresholds": {"system": 0.85}, "runtime": {"max_repair_attempts": 3}},
            "system_score": 0.70,
            "repair_attempts": 0,
        }
        assert route_after_eval(state) == "repair"

    def test_route_after_eval_max_attempts_exhausted(self):
        """Even failing score returns 'done' when max attempts reached."""
        from daedalus.graph import route_after_eval
        state = {
            "config": {"thresholds": {"system": 0.85}, "runtime": {"max_repair_attempts": 3}},
            "system_score": 0.50,
            "repair_attempts": 3,  # at max
        }
        assert route_after_eval(state) == "done"

    def test_route_after_repair_loops_back(self):
        """When should_repair is True, routes back to 'execute'."""
        from daedalus.graph import route_after_repair
        state = {"should_repair": True}
        assert route_after_repair(state) == "execute"

    def test_route_after_repair_done(self):
        """When should_repair is False, routes to 'done'."""
        from daedalus.graph import route_after_repair
        state = {"should_repair": False}
        assert route_after_repair(state) == "done"


class TestGraphBuild:
    """Test that graph construction succeeds without errors."""

    def test_build_daedalus_graph_compiles(self):
        """build_daedalus_graph returns a compiled graph."""
        from daedalus.graph import build_daedalus_graph
        config = {"thresholds": {"system": 0.85}, "runtime": {"max_repair_attempts": 3}}
        graph = build_daedalus_graph(config)
        assert graph is not None

    def test_build_resume_graph_compiles(self):
        """build_resume_graph returns a compiled graph without plan node."""
        from daedalus.graph import build_resume_graph
        config = {"thresholds": {"system": 0.85}, "runtime": {"max_repair_attempts": 3}}
        graph = build_resume_graph(config)
        assert graph is not None


class TestGraphState:
    """Test DaedalusGraphState type is valid."""

    def test_graph_state_keys(self):
        """DaedalusGraphState has all expected keys."""
        from daedalus.graph import DaedalusGraphState
        expected = [
            "run_id", "goal", "preset", "config",
            "plan", "agent_specs", "dep_graph", "output_type",
            "agent_results", "frozen_agents", "combined_result",
            "system_score", "breakdown", "weakest_agents",
            "broken_interfaces", "system_iteration", "repair_attempts",
            "current_step", "errors", "should_repair", "done",
        ]
        annotations = DaedalusGraphState.__annotations__
        for key in expected:
            assert key in annotations, f"Missing key: {key}"
