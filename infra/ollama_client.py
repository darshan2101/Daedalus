"""
infra/ollama_client.py
Ollama Cloud async client for Daedalus.

Uses the official ollama Python SDK's AsyncClient pointed at ollama.com.
No local Ollama installation needed — pure cloud API via https://ollama.com.

Auth: Bearer token via OLLAMA_API_KEY (create at https://ollama.com/settings/keys)
Rate limits: free tier has session limits.
Fallback: if Ollama cloud rate-limits or errors, caller falls through
to OpenRouter waterfall automatically.
"""

import os
import json
import asyncio
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

_OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
_OLLAMA_HOST = "https://ollama.com"

# Lazy-initialised AsyncClient
_async_client = None


def _get_async_client():
    """Return singleton Ollama AsyncClient pointed at ollama.com cloud."""
    global _async_client
    if _async_client is None:
        try:
            from ollama import AsyncClient
            _async_client = AsyncClient(
                host=_OLLAMA_HOST,
                headers={"Authorization": f"Bearer {_OLLAMA_API_KEY}"},
            )
        except ImportError:
            raise ImportError(
                "ollama package not installed. Run: pip install ollama>=0.4.0"
            )
    return _async_client


def is_configured() -> bool:
    """Return True if OLLAMA_API_KEY is set and non-empty."""
    return bool(_OLLAMA_API_KEY)


async def ollama_chat(
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout: float = 120.0,
) -> Optional[str]:
    """
    Call Ollama Cloud chat completion via the official SDK.

    Args:
        model:       Ollama cloud model name e.g. "deepseek-v3.1:671b"
        messages:    OpenAI-format message list [{role, content}]
        temperature: Sampling temperature
        max_tokens:  Max output tokens
        timeout:     Request timeout in seconds (cloud can be slow on large models)

    Returns:
        Response text string, or None if the call fails.
        None triggers caller to fall through to next provider.
    """
    if not is_configured():
        return None

    client = _get_async_client()

    try:
        response = await asyncio.wait_for(
            client.chat(
                model=model,
                messages=messages,
                options={
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
                stream=False,
            ),
            timeout=timeout,
        )
        content = response["message"]["content"]
        if content:
            return content
        return None

    except asyncio.TimeoutError:
        print(f"[Ollama] Timeout on {model} after {timeout}s -- falling through")
        return None
    except Exception as e:
        err = str(e).lower()
        if any(x in err for x in ["rate", "limit", "quota", "429", "503"]):
            print(f"[Ollama] Rate limit / capacity on {model} -- falling through")
        else:
            print(f"[Ollama] Error on {model}: {e} -- falling through")
        return None


async def ollama_chat_json(
    model: str,
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 4096,
    timeout: float = 120.0,
) -> Optional[dict]:
    """
    Call Ollama Cloud and parse JSON response.
    Used by planner and evaluator which expect structured JSON output.

    Returns:
        Parsed dict, or None on failure/parse error.
    """
    raw = await ollama_chat(model, messages, temperature, max_tokens, timeout)
    if raw is None:
        return None

    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON from within the response
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        print(f"[Ollama] JSON parse failed on {model} response -- falling through")
        return None


async def list_cloud_models() -> list[str]:
    """
    Fetch list of available cloud models from ollama.com/api/tags.
    Useful for health check and debugging.
    """
    if not is_configured():
        return []
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{_OLLAMA_HOST}/api/tags",
            headers={"Authorization": f"Bearer {_OLLAMA_API_KEY}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return [m["name"] for m in data.get("models", [])]
    except Exception as e:
        print(f"[Ollama] Could not list models: {e}")
        return []
