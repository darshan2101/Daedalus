"""Unit tests for GlobalCoordinator — topological sort only, no I/O."""
import pytest
from daedalus.coordinator import GlobalCoordinator

class TestTopologicalSort:
    def test_no_deps_is_single_wave(self):
        state = {
            "run_id": "test",
            "agent_specs": [
                {"agent_id": "ag_1", "task": "t1"},
                {"agent_id": "ag_2", "task": "t2"}
            ],
            "dep_graph": {}
        }
        coord = GlobalCoordinator(state, {})
        waves = coord.get_execution_waves()
        assert len(waves) == 1
        assert len(waves[0]) == 2

    def test_linear_chain_is_sequential_waves(self):
        state = {
            "run_id": "test",
            "agent_specs": [
                {"agent_id": "ag_1", "task": "t1"},
                {"agent_id": "ag_2", "task": "t2"}
            ],
            "dep_graph": {"ag_2": ["ag_1"]} # ag_2 depends on ag_1
        }
        coord = GlobalCoordinator(state, {})
        waves = coord.get_execution_waves()
        assert len(waves) == 2
        assert waves[0][0]["agent_id"] == "ag_1"
        assert waves[1][0]["agent_id"] == "ag_2"

    def test_saas_pattern_produces_three_waves(self):
        # schema -> auth -> (backend, frontend) -> docs
        state = {
            "run_id": "test",
            "agent_specs": [
                {"agent_id": "ag_sc", "task": "schema"},
                {"agent_id": "ag_au", "task": "auth"},
                {"agent_id": "ag_be", "task": "backend"},
                {"agent_id": "ag_fe", "task": "frontend"},
                {"agent_id": "ag_dc", "task": "docs"}
            ],
            "dep_graph": {
                "ag_au": ["ag_sc"],
                "ag_be": ["ag_au"],
                "ag_fe": ["ag_au"],
                "ag_dc": ["ag_be", "ag_fe"]
            }
        }
        coord = GlobalCoordinator(state, {})
        waves = coord.get_execution_waves()
        assert len(waves) == 4
        assert waves[0][0]["agent_id"] == "ag_sc"
        assert waves[1][0]["agent_id"] == "ag_au"
        assert len(waves[2]) == 2
        assert waves[3][0]["agent_id"] == "ag_dc"

    def test_empty_graph_returns_empty_waves(self):
        state = {"run_id": "test", "agent_specs": [], "dep_graph": {}}
        coord = GlobalCoordinator(state, {})
        waves = coord.get_execution_waves()
        assert waves == []

@pytest.mark.asyncio
async def test_coordinator_preserves_previous_good_result_on_error(monkeypatch):
    """C2 fix: agent errors should not overwrite previously successful outputs."""
    from unittest.mock import AsyncMock
    
    # Setup state with existing good result
    state = {
        "run_id": "test",
        "agent_results": {
            "ag_1": {"agent_id": "ag_1", "status": "done", "result": "good output", "quality_score": 0.95}
        },
        "agent_specs": [{"agent_id": "ag_1", "task": "t1"}],
        "dep_graph": {}
    }
    
    # Mock MajorAgent to return an error unconditionally
    class MockMajorAgent:
        def __init__(self, *args, **kwargs): pass
        async def run(self):
            return {"agent_id": "ag_1", "status": "error", "result": "", "quality_score": 0.0}
            
    monkeypatch.setattr("daedalus.major_agent.MajorAgent", MockMajorAgent)
    monkeypatch.setattr("infra.mongo_client.update_run_status", AsyncMock())
    monkeypatch.setattr("infra.redis_client.is_frozen", lambda *args: False)
    monkeypatch.setattr("infra.redis_client.freeze_agent", lambda *args: None)
    monkeypatch.setattr("daedalus.merger.detect_and_resolve_all", AsyncMock(return_value=([], state["agent_results"])))
    monkeypatch.setattr("daedalus.aggregator.aggregate", lambda r, s, c: s)
    monkeypatch.setattr("daedalus.evaluator.evaluate_run", lambda r, s, c: s)
    monkeypatch.setattr("daedalus.repair.repair_if_needed", lambda r, s, c: (False, s))
    
    coord = GlobalCoordinator(state, {})
    await coord.run()
    
    # Assert previous good result is preserved
    assert state["agent_results"]["ag_1"]["status"] == "done"
    assert state["agent_results"]["ag_1"]["result"] == "good output"

@pytest.mark.asyncio
async def test_wave_delay_stagger_execution(monkeypatch):
    """Verify wave_delay_seconds calls asyncio.sleep between agent creations within a wave."""
    from unittest.mock import AsyncMock, patch, MagicMock
    
    state = {
        "run_id": "test_run",
        "dep_graph": {
            "ag_1": [],
            "ag_2": [],
            "ag_3": []
        },
        "agent_specs": [
            {"agent_id": "ag_1", "task": "Task 1", "role": "coder"},
            {"agent_id": "ag_2", "task": "Task 2", "role": "coder"},
            {"agent_id": "ag_3", "task": "Task 3", "role": "coder"}
        ]
    }
    
    config = {
        "runtime": {"wave_delay_seconds": 5}
    }
    
    monkeypatch.setattr("daedalus.coordinator.update_run_status", AsyncMock())
    monkeypatch.setattr("infra.redis_client.is_frozen", lambda *args: False)
    monkeypatch.setattr("infra.redis_client.freeze_agent", lambda *args: None)
    monkeypatch.setattr("daedalus.merger.detect_and_resolve_all", AsyncMock(return_value=([], {})))
    monkeypatch.setattr("daedalus.aggregator.aggregate", lambda r, s, c: s)
    monkeypatch.setattr("daedalus.evaluator.evaluate_run", lambda r, s, c: s)
    monkeypatch.setattr("daedalus.repair.repair_if_needed", lambda r, s, c: (False, s))
    
    mock_major_instance = MagicMock()
    mock_major_instance.run = AsyncMock(return_value={"status": "done", "quality_score": 1.0, "result": "mock"})
    monkeypatch.setattr("daedalus.major_agent.MajorAgent", MagicMock(return_value=mock_major_instance))

    from daedalus.coordinator import GlobalCoordinator
    coord = GlobalCoordinator(state, config)
    
    # We patch inside coordinator so we intercept exactly its sleep calls
    with patch("daedalus.coordinator.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await coord.run()
        
        # 1 wave of 3 agents.
        # Index 0 gets no sleep. Index 1 gets sleep(5). Index 2 gets sleep(5).
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(5)
