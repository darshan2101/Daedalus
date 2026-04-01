import pytest
from unittest.mock import patch, AsyncMock
from daedalus.evaluator import evaluate_run

@pytest.fixture
def mock_config():
    return {
        "thresholds": {"default": 0.82},
        "evaluation_weights": {
            "default": {
                "correctness": 1.0,
                "completeness": 0.0,
                "consistency": 0.0,
                "runnability": 0.0,
                "format": 0.0
            }
        }
    }

@pytest.fixture
def mock_state():
    return {
        "goal": "Test Goal",
        "preset": "default",
        "combined_result": "Result text",
        "agent_specs": []
    }

def test_evaluator_retry_on_failure(mock_state, mock_config):
    # First attempt fails, second succeeds
    responses = [Exception("LLM Timeout"), '{"dimensions": {"correctness": 0.9}, "breakdown": "ok", "weakest_agents": []}']
    
    with patch("daedalus.evaluator._call_with_fallback", side_effect=responses):
        state = evaluate_run("run_123", mock_state, mock_config)
    
    assert state["system_score"] == 0.9
    assert state["breakdown"] == "ok"

def test_evaluator_permanent_failure_first_run_uses_sentinel(mock_state, mock_config):
    # No system_score in state — first ever evaluation, both fail
    assert "system_score" not in mock_state
    responses = [Exception("Fail 1"), Exception("Fail 2")]
    
    with patch("daedalus.evaluator._call_with_fallback", side_effect=responses):
        state = evaluate_run("run_123", mock_state, mock_config)
    
    # Should be -1.0 sentinel, NOT 0.0
    assert state["system_score"] == -1.0
