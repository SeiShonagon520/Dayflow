"""
Unit tests for Ollama / Local LLM support in core/llm_provider.py
"""
import pytest
import httpx

from core.llm_provider import DayflowBackendProvider, get_ollama_models


def test_ollama_url_normalization():
    """Test that Ollama URLs are normalized to include /v1."""
    p1 = DayflowBackendProvider(api_base_url="http://localhost:11434")
    assert p1.is_ollama is True
    assert p1.api_base_url == "http://localhost:11434/v1"
    assert p1.timeout == 180.0

    p2 = DayflowBackendProvider(api_base_url="http://127.0.0.1:11434/v1")
    assert p2.is_ollama is True
    assert p2.api_base_url == "http://127.0.0.1:11434/v1"

    # Cloud OpenAI / non-Ollama URL shouldn't be altered
    p3 = DayflowBackendProvider(api_base_url="https://api.openai.com/v1", timeout=60.0)
    assert p3.is_ollama is False
    assert p3.api_base_url == "https://api.openai.com/v1"
    assert p3.timeout == 60.0


def test_ollama_headers():
    """Test headers generation for Ollama (allows fallback dummy key)."""
    p_no_key = DayflowBackendProvider(api_base_url="http://localhost:11434", api_key="")
    assert "Authorization" in p_no_key.headers
    assert p_no_key.headers["Authorization"] == "Bearer ollama"

    p_with_key = DayflowBackendProvider(api_base_url="http://localhost:11434", api_key="my-key")
    assert p_with_key.headers["Authorization"] == "Bearer my-key"


import asyncio


def test_get_ollama_models_mocked(monkeypatch):
    """Test get_ollama_models parsing from /api/tags response."""
    class MockResponse:
        status_code = 200
        def json(self):
            return {
                "models": [
                    {"name": "qwen2.5-vl:7b"},
                    {"name": "minicpm-v:latest"},
                    {"name": "llava:latest"}
                ]
            }

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url):
            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    models = asyncio.run(get_ollama_models("http://localhost:11434"))
    assert models == ["qwen2.5-vl:7b", "minicpm-v:latest", "llava:latest"]


def test_get_ollama_models_offline(monkeypatch):
    """Test get_ollama_models handles connection failure gracefully."""
    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url):
            raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    models = asyncio.run(get_ollama_models("http://localhost:11434"))
    assert models == []
