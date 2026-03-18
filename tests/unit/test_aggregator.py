import os
import pytest
from daedalus.aggregator import aggregate, _aggregate_docs, _aggregate_code
from daedalus.state import RunState

@pytest.fixture
def mock_state() -> RunState:
    return {
        "run_id": "test_run_123",
        "goal": "Test Goal",
        "preset": "docs",
        "agent_specs": [
            {"agent_id": "ag_1", "task": "Task 1", "depth": 0},
            {"agent_id": "ag_2", "task": "Task 2", "depth": 1},
            {"agent_id": "ag_missing", "task": "Task 3", "depth": 2},
        ],
        "agent_results": {
            "ag_1": {"result": "Output from agent 1"},
            "ag_2": {"result": "Output from agent 2\nWith multiple lines"}
        }
    }

def test_aggregate_docs(mock_state, tmp_path, monkeypatch):
    # Mock workspace dir
    monkeypatch.setattr("daedalus.aggregator.get_run_dir", lambda r: str(tmp_path))
    
    final_text, out_path = _aggregate_docs("test_run_123", mock_state)
    
    assert "Final Output: Test Goal" in final_text
    assert "## Task 1" in final_text
    assert "Output from agent 1" in final_text
    assert "## Task 2" in final_text
    assert "Output from agent 2" in final_text
    assert "Task 3" not in final_text # Missing result
    
    assert os.path.exists(out_path)
    with open(out_path, "r", encoding="utf-8") as f:
        assert f.read() == final_text
        
def test_aggregate_code(mock_state, tmp_path, monkeypatch):
    monkeypatch.setattr("daedalus.aggregator.get_run_dir", lambda r: str(tmp_path))
    
    # Modify state for code
    mock_state["preset"] = "code"
    
    file_block_1 = "Some text here\n--- FILE: src/main.py ---\nprint('hello')\n--- END FILE ---\nMore text"
    file_block_2 = "--- FILE: src/utils.py ---\ndef add(a,b): return a+b\n--- END FILE ---"
    
    # Overwrite main.py to test deduplication
    file_block_3 = "--- FILE: src/main.py ---\nprint('overwritten')\n--- END FILE ---"
    
    mock_state["agent_results"] = {
        "ag_1": {"result": file_block_1},
        "ag_2": {"result": file_block_2 + "\n\n" + file_block_3}
    }
    
    final_readme, out_dir = _aggregate_code("test_run_123", mock_state)
    
    # Check README content
    assert "Final Code: Test Goal" in final_readme
    assert "Some text here" in final_readme
    assert "More text" in final_readme
    
    # Check written files
    main_py_path = os.path.join(out_dir, "src", "main.py")
    utils_py_path = os.path.join(out_dir, "src", "utils.py")
    
    assert os.path.exists(main_py_path)
    assert os.path.exists(utils_py_path)
    
    with open(main_py_path, "r", encoding="utf-8") as f:
        # Should be overwritten by ag_2
        assert "print('overwritten')" in f.read()
        
    with open(utils_py_path, "r", encoding="utf-8") as f:
        assert "def add(a,b): return a+b" in f.read()

def test_aggregate_main_function(mock_state, tmp_path, monkeypatch):
    monkeypatch.setattr("daedalus.aggregator.get_run_dir", lambda r: str(tmp_path))
    
    # Test docs routing
    mock_state["preset"] = "docs"
    updated_state = aggregate("test_run_123", mock_state, {})
    
    assert "combined_result" in updated_state
    assert "output_path" in updated_state
    assert "Task 1" in updated_state["combined_result"]
    assert "FINAL.md" in updated_state["output_path"]
    
    # Test code routing
    mock_state["preset"] = "code"
    updated_state = aggregate("test_run_123", mock_state, {})
    
    assert "combined_result" in updated_state
    assert "output_path" in updated_state
    assert "final_code" in updated_state["output_path"]
