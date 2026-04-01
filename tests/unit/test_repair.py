import pytest
from daedalus.state import RunState
from daedalus.repair import repair_if_needed

@pytest.fixture
def mock_config():
    return {
        "thresholds": {"system": 0.85},
        "runtime": {"max_repair_attempts": 3}
    }

@pytest.fixture
def mock_state() -> RunState:
    return {
        "run_id": "test_run_123",
        "system_score": 0.70,
        "repair_attempts": 0,
        "weakest_agents": ["ag_1"],
        "agent_results": {
            "ag_1": {"quality_score": 0.5},
            "ag_2": {"quality_score": 0.9}
        }
    }

def test_repair_pass(mock_state, mock_config):
    # If score is high enough, no repair needed
    mock_state["system_score"] = 0.90
    needs_repair, state = repair_if_needed("test_run_123", mock_state, mock_config)
    assert not needs_repair
    assert state["repair_attempts"] == 0

def test_repair_max_attempts(mock_state, mock_config):
    # If max attempts reached, give up
    mock_state["repair_attempts"] = 3
    needs_repair, state = repair_if_needed("test_run_123", mock_state, mock_config)
    assert not needs_repair
    assert state["repair_attempts"] == 3

def test_repair_triggers_and_unfreezes(mock_state, mock_config, monkeypatch):
    unfrozen = []
    def mock_unfreeze(run_id, agent_id):
        unfrozen.append(agent_id)
        
    import daedalus.repair
    monkeypatch.setattr(daedalus.repair, "unfreeze_agent", mock_unfreeze)
    
    needs_repair, state = repair_if_needed("test_run_123", mock_state, mock_config)
    
    assert needs_repair
    assert state["repair_attempts"] == 1
    assert unfrozen == ["ag_1"]

def test_repair_fallback_weakest(mock_state, mock_config, monkeypatch):
    mock_state["weakest_agents"] = []
    
    unfrozen = []
    def mock_unfreeze(run_id, agent_id):
        unfrozen.append(agent_id)
        
    import daedalus.repair
    monkeypatch.setattr(daedalus.repair, "unfreeze_agent", mock_unfreeze)
    
    needs_repair, state = repair_if_needed("test_run_123", mock_state, mock_config)
    
    assert needs_repair
    # Should pick ag_1 because it has the lowest quality_score (0.5 vs 0.9)
    assert unfrozen == ["ag_1"]
def test_repair_context_filtering(mock_state, mock_config, monkeypatch):
    mock_state["weakest_agents"] = ["ag_1"]
    mock_state["broken_interfaces"] = [
        {"agent_a": "ag_1", "agent_b": "ag_2", "description": "Conflict involving ag_1"},
        {"agent_a": "ag_2", "agent_b": "ag_3", "description": "Irrelevant conflict"}
    ]
    
    monkeypatch.setattr("daedalus.repair.unfreeze_agent", lambda x, y: None)
    
    needs_repair, state = repair_if_needed("test_run_123", mock_state, mock_config)
    
    assert needs_repair
    assert "repair_context" in state
    assert state["repair_context"]["ag_1"] == ["Conflict involving ag_1"]
    assert "ag_2" not in state["repair_context"]

def test_repair_includes_evaluator_feedback(mock_state, mock_config, monkeypatch):
    mock_state["weakest_agents"] = ["ag_1"]
    mock_state["breakdown"] = "Missing feature X"
    mock_state["broken_interfaces"] = []
    
    monkeypatch.setattr("daedalus.repair.unfreeze_agent", lambda x, y: None)
    
    needs_repair, state = repair_if_needed("test_run_123", mock_state, mock_config)
    
    assert needs_repair
    assert "ag_1" in state["repair_context"]
    assert any("SYSTEM EVALUATOR FEEDBACK: Missing feature X" in c for c in state["repair_context"]["ag_1"])

def test_repair_if_needed_skips_on_sentinel(mock_state, mock_config):
    """C1 fix: sentinel score of -1.0 must skip repair phase."""
    mock_state["system_score"] = -1.0
    needs_repair, state = repair_if_needed("test_run_123", mock_state, mock_config)
    assert not needs_repair
    assert state.get("repair_attempts", 0) == 0

def test_repair_includes_goal_constraint(mock_state, mock_config, monkeypatch):
    """H1 fix: repair context includes global constraint to prevent language drift."""
    mock_state["weakest_agents"] = ["ag_1"]
    mock_state["breakdown"] = ""
    mock_state["broken_interfaces"] = []
    mock_state["goal"] = "Build a Rust pipeline"
    
    monkeypatch.setattr("daedalus.repair.unfreeze_agent", lambda x, y: None)
    
    needs_repair, state = repair_if_needed("test_run_123", mock_state, mock_config)
    
    assert needs_repair
    assert "ag_1" in state["repair_context"]
    assert any("GLOBAL CONSTRAINT: The entire system goal is: 'Build a Rust pipeline'" in c for c in state["repair_context"]["ag_1"])
