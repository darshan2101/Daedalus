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
        with pytest.raises(ValueError, match="[Cc]ircular"):
            _validate_dag(specs, deps)

    def test_missing_dep_id_raises(self):
        specs = [{"agent_id": "ag_a", "dependencies": ["ag_nonexistent"]}]
        deps = {"ag_a": ["ag_nonexistent"]}
        with pytest.raises(ValueError, match="[Uu]nknown"):
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

    def test_modular_output_type_uses_default_threshold(self):
        config = {"thresholds": {"code": 0.88, "default": 0.82}}
        specs = [{"agent_id": "ag_a", "output_type": "modular", "threshold": 0.50}]
        result = _tighten_thresholds(specs, config)
        assert result[0]["threshold"] >= 0.82
