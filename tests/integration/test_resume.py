import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from main import main_async

@pytest.mark.asyncio
async def test_resume_restores_agent_results():
    # Mocking arguments for resume
    import argparse
    with patch("argparse.ArgumentParser.parse_args") as mock_args:
        mock_args.return_value = argparse.Namespace(
            resume="run_123", goal=[], preset="default", plan_review=False, 
            threshold=None, max_depth=None, quiet=False, verbose=False
        )
        
        # Mocking MongoDB
        mock_run = {
            "run_id": "run_123",
            "goal": "Test Goal",
            "preset": "default"
        }
        mock_checkpoints = [
            {"agent_id": "ag_1", "task": "task 1", "result": "res 1", "score": 0.9}
        ]
        
        with patch("infra.mongo_client.get_db") as mock_db_getter:
            mock_db = MagicMock()
            mock_db.runs.find_one = AsyncMock(return_value=mock_run)
            mock_db_getter.return_value = mock_db
            
            with patch("infra.mongo_client.get_checkpoints", new_callable=AsyncMock, return_value=mock_checkpoints):
                # We only want to test the resume bridge part, so we mock building the graph
                with patch("daedalus.graph.build_resume_graph") as mock_build:
                    mock_graph = MagicMock()
                    mock_graph.ainvoke = AsyncMock(return_value={"system_score": 0.95})
                    mock_build.return_value = mock_graph
                    
                    with patch("main.load_config", return_value={"thresholds": {"default": 0.85}, "runtime": {"max_recursion_depth": 5}}):
                        with patch("infra.mongo_client.update_run_status", new_callable=AsyncMock):
                            with patch("daedalus.assembler.parse_and_zip", return_value="test.zip"):
                                await main_async()
                                
                                # Verify graph_state passed to ainvoke
                                graph_state = mock_graph.ainvoke.call_args[0][0]
                                assert "ag_1" in graph_state["agent_results"]
                                assert graph_state["agent_results"]["ag_1"]["result"] == "res 1"

