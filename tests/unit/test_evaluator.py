import pytest
from daedalus.state import RunState
from daedalus.evaluator import evaluate_run
import daedalus.evaluator

@pytest.fixture
def mock_state() -> RunState:
    return {
        "run_id": "test_run_123",
        "goal": "Test Goal",
        "preset": "docs",
        "agent_specs": [
            {"agent_id": "ag_1", "task": "Task 1", "specialist": "reasoner"},
            {"agent_id": "ag_2", "task": "Task 2", "specialist": "coder"}
        ],
        "combined_result": "Here is the final combined output..."
    }

def test_evaluate_run_success(mock_state, monkeypatch):
    # Mock LLM response to simulate a perfect valid JSON return
    mock_json_str = '''
    {
      "system_score": 0.92,
      "breakdown": "The response was quite good, missing a minor detail.",
      "weakest_agents": ["ag_2"]
    }
    '''
    
    # We patch inside the module where _call_with_fallback was imported
    monkeypatch.setattr(daedalus.evaluator, "_call_with_fallback", lambda models, sys, user: mock_json_str)
    
    updated_state = evaluate_run("test_run_123", mock_state, {})
    
    assert updated_state.get("system_score") == 0.92
    assert "quite good" in updated_state.get("breakdown", "")
    assert updated_state.get("weakest_agents") == ["ag_2"]

def test_evaluate_run_empty_weakest_agents(mock_state, monkeypatch):
    mock_json_str = '''
    {
      "system_score": 0.98,
      "breakdown": "Excellent.",
      "weakest_agents": []
    }
    '''
    monkeypatch.setattr(daedalus.evaluator, "_call_with_fallback", lambda models, sys, user: mock_json_str)
    
    updated_state = evaluate_run("test_run_123", mock_state, {})
    assert updated_state.get("system_score") == 0.98
    assert updated_state.get("weakest_agents") == []

def test_evaluate_run_json_error(mock_state, monkeypatch):
    # If the LLM returns garbage
    monkeypatch.setattr(daedalus.evaluator, "_call_with_fallback", lambda models, sys, user: "Sorry, I cannot help with that.")
    
    updated_state = evaluate_run("test_run_123", mock_state, {})
    
    # Should safely fail and assign 0.0
    assert updated_state.get("system_score") == 0.0
    assert updated_state.get("weakest_agents") == []
