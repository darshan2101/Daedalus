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
