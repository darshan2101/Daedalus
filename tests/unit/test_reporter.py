"""Unit tests for daedalus/reporter.py"""
import os
import json
import pytest
from unittest.mock import patch

@pytest.fixture
def mock_run_data():
    return {
        "_id": "run_test_123",
        "status": "completed",
        "goal": "Test API",
        "preset": "default",
        "system_score": 0.95,
        "dimensions": {
            "correctness": 1.0,
            "completeness": 0.9,
            "consistency": 1.0,
            "runnability": 0.9,
            "format": 1.0
        },
        "breakdown": "Looks solid.",
        "weakest_agents": [],
        "broken_interfaces": [],
        "system_iteration": 2,
        "repair_attempts": 1,
        "agent_specs": [{"agent_id": "ag_1"}, {"agent_id": "ag_2"}],
        "errors": []
    }

@pytest.mark.asyncio
async def test_generate_report_success(mock_run_data, tmp_path):
    out_dir = str(tmp_path)
    
    # Mock get_run
    with patch("daedalus.reporter.get_run", return_value=mock_run_data):
        from daedalus.reporter import generate_report
        json_path, md_path = await generate_report("run_test_123", output_dir=out_dir)
        
        assert json_path is not None
        assert md_path is not None
        assert os.path.exists(json_path)
        assert os.path.exists(md_path)
        
        # Verify JSON
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert data["run_id"] == "run_test_123"
            assert data["evaluation"]["system_score"] == 0.95
            assert data["execution"]["iterations"] == 2
            assert data["execution"]["agents_spawned"] == 2
            
        # Verify Markdown
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "# Daedalus Run Report: `run_test_123`" in content
            assert "**System Score**: `0.95`" in content
            assert "- **Correctness**: 1.0" in content
            assert "- **Agents Spawned**: 2" in content

@pytest.mark.asyncio
async def test_generate_report_not_found(tmp_path):
    out_dir = str(tmp_path)
    
    with patch("daedalus.reporter.get_run", return_value=None):
        from daedalus.reporter import generate_report
        json_path, md_path = await generate_report("run_missing", output_dir=out_dir)
        
        assert json_path is None
        assert md_path is None
