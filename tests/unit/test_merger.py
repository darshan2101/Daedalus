"""Unit tests for daedalus/merger.py — no real LLM calls."""
import pytest
import json
from unittest.mock import patch, AsyncMock


class TestDetectConflicts:
    @pytest.mark.asyncio
    async def test_no_conflicts_returns_empty(self):
        """When LLM returns empty list, detect_conflicts returns []."""
        with patch("daedalus.merger._call_llm", new_callable=AsyncMock, return_value="[]"):
            from daedalus.merger import detect_conflicts
            result = await detect_conflicts(
                {"ag_a": {"result": "code A"}, "ag_b": {"result": "code B"}},
                {"ag_a": [], "ag_b": ["ag_a"]},
            )
        assert result == []

    @pytest.mark.asyncio
    async def test_single_agent_returns_empty(self):
        """Cannot have conflicts with a single agent."""
        from daedalus.merger import detect_conflicts
        result = await detect_conflicts(
            {"ag_a": {"result": "code A"}},
            {"ag_a": []},
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_conflicts_parsed_correctly(self):
        """Valid conflict JSON is parsed into BrokenInterface dicts."""
        mock_response = json.dumps([
            {
                "agent_a": "ag_backend",
                "agent_b": "ag_frontend",
                "description": "User model field 'email' vs 'user_email'"
            }
        ])
        with patch("daedalus.merger._call_llm", new_callable=AsyncMock, return_value=mock_response):
            from daedalus.merger import detect_conflicts
            result = await detect_conflicts(
                {
                    "ag_backend": {"result": "class User: email: str"},
                    "ag_frontend": {"result": "fetch user_email from API"},
                },
                {"ag_backend": [], "ag_frontend": ["ag_backend"]},
            )
        assert len(result) == 1
        assert result[0]["agent_a"] == "ag_backend"
        assert result[0]["agent_b"] == "ag_frontend"
        assert "attempt" in result[0]

    @pytest.mark.asyncio
    async def test_malformed_json_returns_empty(self):
        """If LLM returns garbage, detect_conflicts returns [] gracefully."""
        with patch("daedalus.merger._call_llm", new_callable=AsyncMock, return_value="NOT VALID JSON"):
            from daedalus.merger import detect_conflicts
            result = await detect_conflicts(
                {"ag_a": {"result": "X"}, "ag_b": {"result": "Y"}},
                {"ag_a": [], "ag_b": []},
            )
        assert result == []


class TestResolveConflict:
    @pytest.mark.asyncio
    async def test_resolution_returns_canonical_agent(self, mock_db):
        """resolve_conflict returns a dict with canonical_agent."""
        mock_resolution = json.dumps({
            "canonical_agent": "ag_backend",
            "resolution": "Frontend should use 'email' not 'user_email'",
            "patched_output": "fetch email from API"
        })
        with patch("daedalus.merger._call_llm", new_callable=AsyncMock, return_value=mock_resolution):
            with patch("daedalus.merger.get_db", return_value=mock_db):
                from daedalus.merger import resolve_conflict
                result = await resolve_conflict(
                    {"agent_a": "ag_backend", "agent_b": "ag_frontend",
                     "description": "field name mismatch", "attempt": 0},
                    "class User: email: str",
                    "fetch user_email from API",
                    "run_test_resolve",
                )
        assert result["canonical_agent"] == "ag_backend"
        assert "patched_output" in result

    @pytest.mark.asyncio
    async def test_resolution_logged_to_mongodb(self, mock_db):
        """resolve_conflict writes an entry to conflicts collection."""
        mock_resolution = json.dumps({
            "canonical_agent": "ag_a",
            "resolution": "Use version A",
            "patched_output": ""
        })
        with patch("daedalus.merger._call_llm", new_callable=AsyncMock, return_value=mock_resolution):
            with patch("daedalus.merger.get_db", return_value=mock_db):
                from daedalus.merger import resolve_conflict
                await resolve_conflict(
                    {"agent_a": "ag_a", "agent_b": "ag_b",
                     "description": "test conflict", "attempt": 0},
                    "output A", "output B", "run_log_test",
                )
        assert len(mock_db.conflicts._docs) >= 1
        assert mock_db.conflicts._docs[0]["run_id"] == "run_log_test"


class TestDetectAndResolveAll:
    @pytest.mark.asyncio
    async def test_no_conflicts_passes_through(self):
        """When no conflicts, agent_results are returned unchanged."""
        with patch("daedalus.merger.detect_conflicts", new_callable=AsyncMock, return_value=[]):
            from daedalus.merger import detect_and_resolve_all
            results = {"ag_a": {"result": "X"}, "ag_b": {"result": "Y"}}
            broken, updated = await detect_and_resolve_all(results, {}, "run_test")
        assert broken == []
        assert updated == results

    @pytest.mark.asyncio
    async def test_patched_output_applied(self, mock_db):
        """When resolution has patched_output, it's applied to the losing agent."""
        conflict = {"agent_a": "ag_a", "agent_b": "ag_b",
                     "description": "mismatch", "attempt": 0}
        resolution = {
            "canonical_agent": "ag_a",
            "resolution": "Use A's version",
            "patched_output": "PATCHED_B"
        }
        with patch("daedalus.merger.detect_conflicts", new_callable=AsyncMock, return_value=[conflict]):
            with patch("daedalus.merger.resolve_conflict", new_callable=AsyncMock, return_value=resolution):
                from daedalus.merger import detect_and_resolve_all
                results = {
                    "ag_a": {"result": "original_A"},
                    "ag_b": {"result": "original_B"},
                }
                broken, updated = await detect_and_resolve_all(results, {}, "run_patch_test")
        assert updated["ag_b"]["result"] == "PATCHED_B"
        assert updated["ag_a"]["result"] == "original_A"  # canonical unchanged
