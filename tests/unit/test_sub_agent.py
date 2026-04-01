import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from daedalus.sub_agent import run_agent_task

@pytest.mark.asyncio
async def test_run_agent_task_injects_repair_context():
    agent = {
        "agent_id": "ag_1",
        "task": "Original task",
        "specialist": "coder",
        "threshold": 0.88,
        "dependencies": []
    }
    config = {"runtime": {"max_module_iterations": 1}}
    state = {
        "repair_context": {"ag_1": ["Fix this conflict"]},
        "agent_results": {}
    }
    
    mock_pipeline = MagicMock()
    mock_pipeline.invoke.return_value = {
        "quality_score": 0.9,
        "result": "Fixed code",
        "feedback": "good",
        "iterations": 1
    }
    
    with patch("daedalus.sub_agent.pipeline", mock_pipeline):
        with patch("daedalus.sub_agent.write_agent_output"), \
             patch("daedalus.sub_agent.insert_checkpoint", new_callable=AsyncMock), \
             patch("daedalus.sub_agent.log_decision", new_callable=AsyncMock):
            
            result = await run_agent_task("run_123", agent, config, state)
            
    # Verify the prompt injected into the pipeline
    invoked_args = mock_pipeline.invoke.call_args[0][0]
    assert "CRITICAL" in invoked_args["task"]
    assert "Fix this conflict" in invoked_args["task"]
    assert "Original task" in invoked_args["task"]
    assert invoked_args["threshold"] == 0.88

