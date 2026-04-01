import pytest
import argparse
from unittest.mock import patch, AsyncMock, MagicMock
from main import main_async

@pytest.mark.asyncio
async def test_resume_resets_repair_attempts():
    """C1 fix: resume runs should reset repair_attempts and system_iteration."""
    with patch("argparse.ArgumentParser.parse_args") as mock_args:
        # Mock resume command
        mock_args.return_value = argparse.Namespace(
            resume="run_123", goal=[], preset="default", plan_review=False, 
            threshold=None, max_depth=None, quiet=False, verbose=False
        )
        
        # Mock database returning a previously exhausted run
        mock_run = {
            "run_id": "run_123",
            "goal": "Test Goal",
            "preset": "default",
            "repair_attempts": 2, # Exhausted in previous run
            "system_iteration": 2,
        }
        
        with patch("main.load_config", return_value={"thresholds": {"default": 0.85}, "runtime": {"max_recursion_depth": 5, "use_langgraph": True}}):
            with patch("infra.mongo_client.get_db") as mock_db_getter:
                mock_db = MagicMock()
                mock_db.runs.find_one = AsyncMock(return_value=mock_run)
                mock_db_getter.return_value = mock_db
                
                with patch("infra.mongo_client.get_checkpoints", new_callable=AsyncMock, return_value=[]):
                    with patch("infra.mongo_client.update_run_status", new_callable=AsyncMock):
                        # Mock the graph to intercept state before execution
                        with patch("daedalus.graph.build_resume_graph") as mock_build:
                            mock_graph = MagicMock()
                            mock_graph.ainvoke = AsyncMock(return_value={"system_score": 0.95})
                            mock_build.return_value = mock_graph
                            
                            with patch("daedalus.assembler.parse_and_zip", return_value="test.zip"):
                                await main_async()
                                
                                # Verify graph_state passed into ainvoke successfully reset the budgets
                                graph_state = mock_graph.ainvoke.call_args[0][0]
                                assert graph_state["repair_attempts"] == 0
                                assert graph_state["system_iteration"] == 0
