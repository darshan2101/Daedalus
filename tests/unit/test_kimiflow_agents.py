"""Unit tests for multi-provider direct routing via sentinels.

Covers: __groq__, __cerebras__, __scaleway__, __nvidia__
Each provider supports bare (where default model exists) and prefixed (__provider__:model) forms.
"""
import pytest
import openai
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def reset_provider_flags():
    """Reset all provider session-kill flags before every test."""
    import kimiflow.agents as agents_mod
    agents_mod._groq_disabled = False
    agents_mod._cerebras_disabled = False
    agents_mod._scaleway_disabled = False
    agents_mod._nvidia_disabled = False
    yield
    agents_mod._groq_disabled = False
    agents_mod._cerebras_disabled = False
    agents_mod._scaleway_disabled = False
    agents_mod._nvidia_disabled = False


# ── GROQ ─────────────────────────────────────────────────────────────────────

class TestGroqRouting:

    @patch("kimiflow.agents._call", return_value="groq default")
    def test_bare_groq_routes_to_default_model(self, mock_call):
        """Case 1: '__groq__' bare → GROQ_MODEL (backward compat)."""
        from kimiflow.agents import _call_with_fallback, GROQ_BASE, GROQ_KEY, GROQ_MODEL

        result = _call_with_fallback(["__groq__"], "sys", "usr")

        assert result == "groq default"
        mock_call.assert_called_once_with(
            GROQ_BASE, GROQ_KEY, GROQ_MODEL, "sys", "usr", 0.7
        )

    @patch("kimiflow.agents._call", return_value="groq 8b")
    def test_prefixed_groq_routes_to_specified_model(self, mock_call):
        """Case 2: '__groq__:llama-3.1-8b-instant' → 'llama-3.1-8b-instant'."""
        from kimiflow.agents import _call_with_fallback, GROQ_BASE, GROQ_KEY

        result = _call_with_fallback(["__groq__:llama-3.1-8b-instant"], "sys", "usr")

        assert result == "groq 8b"
        mock_call.assert_called_once_with(
            GROQ_BASE, GROQ_KEY, "llama-3.1-8b-instant", "sys", "usr", 0.7
        )

    @patch("kimiflow.agents._call")
    def test_groq_tpd_disables_session(self, mock_call):
        """Case 3: Groq TPD error → _groq_disabled = True, session killed."""
        import kimiflow.agents as agents_mod
        from kimiflow.agents import _call_with_fallback

        mock_call.side_effect = [
            Exception("tokens per day limit reached"),  # Groq TPD
            "openrouter fallback",                       # OpenRouter succeeds
        ]

        result = _call_with_fallback(
            ["__groq__", "meta-llama/llama-3.3-70b-instruct:free"], "sys", "usr"
        )

        assert result == "openrouter fallback"
        assert agents_mod._groq_disabled is True

    @patch("kimiflow.agents._call")
    def test_groq_tpm_429_does_not_disable(self, mock_call):
        """Case 4: Groq TPM 429 → provider stays live, falls to next model."""
        import kimiflow.agents as agents_mod
        from kimiflow.agents import _call_with_fallback

        mock_call.side_effect = [
            openai.RateLimitError(
                message="Rate limit exceeded: 100K TPM",
                response=MagicMock(status_code=429),
                body=None,
            ),
            "openrouter fallback",
        ]

        result = _call_with_fallback(
            ["__groq__", "meta-llama/llama-3.3-70b-instruct:free"], "sys", "usr"
        )

        assert result == "openrouter fallback"
        assert agents_mod._groq_disabled is False  # NOT killed


# ── CEREBRAS ─────────────────────────────────────────────────────────────────

class TestCerebrasRouting:

    @patch("kimiflow.agents._call", return_value="cerebras default")
    def test_bare_cerebras_routes_to_default_model(self, mock_call):
        """Case 5: '__cerebras__' bare → CEREBRAS_MODEL."""
        from kimiflow.agents import _call_with_fallback, CEREBRAS_BASE, CEREBRAS_KEY, CEREBRAS_MODEL

        result = _call_with_fallback(["__cerebras__"], "sys", "usr")

        assert result == "cerebras default"
        mock_call.assert_called_once_with(
            CEREBRAS_BASE, CEREBRAS_KEY, CEREBRAS_MODEL, "sys", "usr", 0.7
        )

    @patch("kimiflow.agents._call", return_value="cerebras qwen")
    def test_prefixed_cerebras_routes_to_specified_model(self, mock_call):
        """Case 6: '__cerebras__:qwen-3-235b' → specified model."""
        from kimiflow.agents import _call_with_fallback, CEREBRAS_BASE, CEREBRAS_KEY

        result = _call_with_fallback(
            ["__cerebras__:qwen-3-235b-a22b-instruct-2507"], "sys", "usr"
        )

        assert result == "cerebras qwen"
        mock_call.assert_called_once_with(
            CEREBRAS_BASE, CEREBRAS_KEY,
            "qwen-3-235b-a22b-instruct-2507", "sys", "usr", 0.7
        )

    @patch("kimiflow.agents._call")
    def test_cerebras_tpd_disables_session(self, mock_call):
        """Case 7: Cerebras TPD → _cerebras_disabled = True."""
        import kimiflow.agents as agents_mod
        from kimiflow.agents import _call_with_fallback

        mock_call.side_effect = [
            Exception("daily request limit reached"),
            "fallback ok",
        ]

        result = _call_with_fallback(
            ["__cerebras__", "meta-llama/llama-3.3-70b-instruct:free"], "sys", "usr"
        )

        assert result == "fallback ok"
        assert agents_mod._cerebras_disabled is True

    @patch("kimiflow.agents._call")
    def test_cerebras_tpm_429_does_not_disable(self, mock_call):
        """Case 8: Cerebras TPM 429 → provider stays live."""
        import kimiflow.agents as agents_mod
        from kimiflow.agents import _call_with_fallback

        mock_call.side_effect = [
            openai.RateLimitError(
                message="Rate limit: 500 TPM exceeded",
                response=MagicMock(status_code=429),
                body=None,
            ),
            "fallback ok",
        ]

        result = _call_with_fallback(
            ["__cerebras__", "meta-llama/llama-3.3-70b-instruct:free"], "sys", "usr"
        )

        assert result == "fallback ok"
        assert agents_mod._cerebras_disabled is False


# ── SCALEWAY ─────────────────────────────────────────────────────────────────

class TestScalewayRouting:

    @patch("kimiflow.agents._call", return_value="scaleway llama")
    def test_prefixed_scaleway_routes_to_specified_model(self, mock_call):
        """Case 9: '__scaleway__:llama-3.3-70b-instruct' → specified model."""
        from kimiflow.agents import _call_with_fallback, SCALEWAY_BASE, SCALEWAY_KEY

        result = _call_with_fallback(
            ["__scaleway__:llama-3.3-70b-instruct"], "sys", "usr"
        )

        assert result == "scaleway llama"
        mock_call.assert_called_once_with(
            SCALEWAY_BASE, SCALEWAY_KEY,
            "llama-3.3-70b-instruct", "sys", "usr", 0.7
        )

    @patch("kimiflow.agents._call", return_value="openrouter fallback")
    def test_scaleway_disabled_skips(self, mock_call):
        """Case 10: _scaleway_disabled → skips, falls through."""
        import kimiflow.agents as agents_mod
        from kimiflow.agents import _call_with_fallback, OPENROUTER_BASE, OPENROUTER_KEY

        agents_mod._scaleway_disabled = True

        result = _call_with_fallback(
            ["__scaleway__:llama-3.3-70b-instruct", "meta-llama/llama-3.3-70b-instruct:free"],
            "sys", "usr"
        )

        assert result == "openrouter fallback"
        mock_call.assert_called_once_with(
            OPENROUTER_BASE, OPENROUTER_KEY,
            "meta-llama/llama-3.3-70b-instruct:free", "sys", "usr", 0.7
        )


# ── NVIDIA ───────────────────────────────────────────────────────────────────

class TestNvidiaRouting:

    @patch("kimiflow.agents._call", return_value="nvidia llama")
    def test_prefixed_nvidia_routes_to_specified_model(self, mock_call):
        """Case 11: '__nvidia__:meta/llama-3.3-70b-instruct' → specified model."""
        from kimiflow.agents import _call_with_fallback, NVIDIA_BASE, NVIDIA_KEY

        result = _call_with_fallback(
            ["__nvidia__:meta/llama-3.3-70b-instruct"], "sys", "usr"
        )

        assert result == "nvidia llama"
        mock_call.assert_called_once_with(
            NVIDIA_BASE, NVIDIA_KEY,
            "meta/llama-3.3-70b-instruct", "sys", "usr", 0.7
        )

    @patch("kimiflow.agents._call", return_value="openrouter fallback")
    def test_nvidia_disabled_skips(self, mock_call):
        """Case 12: _nvidia_disabled → skips, falls through."""
        import kimiflow.agents as agents_mod
        from kimiflow.agents import _call_with_fallback, OPENROUTER_BASE, OPENROUTER_KEY

        agents_mod._nvidia_disabled = True

        result = _call_with_fallback(
            ["__nvidia__:meta/llama-3.3-70b-instruct", "meta-llama/llama-3.3-70b-instruct:free"],
            "sys", "usr"
        )

        assert result == "openrouter fallback"
        mock_call.assert_called_once_with(
            OPENROUTER_BASE, OPENROUTER_KEY,
            "meta-llama/llama-3.3-70b-instruct:free", "sys", "usr", 0.7
        )


# ── CROSS-PROVIDER ───────────────────────────────────────────────────────────

class TestCrossProvider:

    @patch("kimiflow.agents._call", return_value="openrouter last resort")
    def test_all_providers_disabled_falls_to_openrouter(self, mock_call):
        """Case 13: All providers disabled → OpenRouter only."""
        import kimiflow.agents as agents_mod
        from kimiflow.agents import _call_with_fallback, OPENROUTER_BASE, OPENROUTER_KEY

        agents_mod._groq_disabled = True
        agents_mod._cerebras_disabled = True
        agents_mod._scaleway_disabled = True
        agents_mod._nvidia_disabled = True

        result = _call_with_fallback(
            [
                "__groq__",
                "__cerebras__",
                "__scaleway__:llama-3.3-70b-instruct",
                "__nvidia__:meta/llama-3.3-70b-instruct",
                "openrouter/free",
            ],
            "sys", "usr"
        )

        assert result == "openrouter last resort"
        mock_call.assert_called_once_with(
            OPENROUTER_BASE, OPENROUTER_KEY,
            "openrouter/free", "sys", "usr", 0.7
        )

    @patch("kimiflow.agents._call", return_value="or response")
    def test_non_sentinel_routes_to_openrouter(self, mock_call):
        """Case 14: Non-sentinel string → OpenRouter path untouched."""
        from kimiflow.agents import _call_with_fallback, OPENROUTER_BASE, OPENROUTER_KEY

        result = _call_with_fallback(
            ["nvidia/nemotron-3-super-120b-a12b:free"], "sys", "usr"
        )

        assert result == "or response"
        mock_call.assert_called_once_with(
            OPENROUTER_BASE, OPENROUTER_KEY,
            "nvidia/nemotron-3-super-120b-a12b:free", "sys", "usr", 0.7
        )


# ── _parse_json ───────────────────────────────────────────────────────────────

class TestParseJson:
    """_parse_json must survive the common malformed outputs from real models."""

    def test_clean_json_parses(self):
        from kimiflow.agents import _parse_json
        result = _parse_json('{"score": 0.85, "feedback": "good", "retry_with": "done"}')
        assert result["score"] == 0.85

    def test_markdown_fenced_json_parses(self):
        from kimiflow.agents import _parse_json
        raw = '```json\n{"score": 0.7, "feedback": "ok"}\n```'
        result = _parse_json(raw)
        assert result["score"] == 0.7

    def test_literal_newline_in_feedback_parses(self):
        """scaleway/gpt-oss-120b returns multiline feedback — this was failing."""
        from kimiflow.agents import _parse_json
        raw = '{"score": 0.6, "feedback": "Line one.\nLine two.\nLine three.", "retry_with": "coder"}'
        result = _parse_json(raw)
        assert result["score"] == 0.6
        assert "Line one" in result["feedback"]

    def test_literal_tab_in_feedback_parses(self):
        from kimiflow.agents import _parse_json
        raw = '{"score": 0.5, "feedback": "col1\tcol2", "retry_with": "coder"}'
        result = _parse_json(raw)
        assert result["score"] == 0.5

    def test_trailing_prose_after_json_parses(self):
        from kimiflow.agents import _parse_json
        raw = 'Here is my evaluation:\n{"score": 0.9, "feedback": "pass"}\n\nNote: looks good.'
        result = _parse_json(raw)
        assert result["score"] == 0.9

    def test_truly_malformed_returns_zero_score(self):
        from kimiflow.agents import _parse_json
        result = _parse_json("not json at all")
        assert result["score"] == 0.0
        assert "malformed" in result["feedback"].lower()
