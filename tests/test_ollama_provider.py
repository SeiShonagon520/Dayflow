"""
Unit tests for Ollama / Local LLM support in core/llm_provider.py
"""
from core.llm_provider import DayflowBackendProvider


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
