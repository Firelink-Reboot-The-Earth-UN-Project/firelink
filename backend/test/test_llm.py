"""Unit tests for app/services/llm.py.

Fake responses only — no network, no running stack, no API keys needed.
Run from backend/:
    make unit
"""

from __future__ import annotations

import asyncio
import json
import os
from types import SimpleNamespace

import pytest

from app.services import llm
from app.services.agents import base_agent, help_agent


# ── fakes mirroring the openai SDK response shape ──────────────────────


class FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class FakeToolCall:
    def __init__(self, name, arguments, type="function"):
        self.type = type
        self.function = FakeFunction(name, arguments)


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


def fake_response(content=None, tool_calls=None):
    message = FakeMessage(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.kwargs = None

    async def create(self, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))


@pytest.fixture
def fake_client(monkeypatch):
    """Install a FakeClient as the llm singleton; returns it for assertions."""

    def install(*responses):
        client = FakeClient(responses)
        monkeypatch.setattr(llm, "_client", client)
        return client

    return install


@pytest.fixture
def fresh_client(monkeypatch):
    monkeypatch.setattr(llm, "_client", None)


DISPATCH_ARGS = json.dumps(
    {
        "user_phone": "+16195550001",
        "emergency_type": "trapped",
        "details": "fire at the door",
    }
)


# ── _normalize_message ─────────────────────────────────────────────────


def test_normalize_valid_tool_call():
    result = llm._normalize_message(
        FakeMessage(tool_calls=[FakeToolCall("notify_dispatch", DISPATCH_ARGS)])
    )
    assert result.text is None
    assert len(result.tool_calls) == 1
    call = result.tool_calls[0]
    assert call.name == "notify_dispatch"
    assert call.arguments == json.loads(DISPATCH_ARGS)


def test_normalize_tool_call_with_empty_arguments_string():
    result = llm._normalize_message(
        FakeMessage(tool_calls=[FakeToolCall("notify_dispatch", "")])
    )
    assert result.tool_calls[0].arguments == {}


def test_normalize_text_only():
    result = llm._normalize_message(FakeMessage(content="Evacuate now."))
    assert result.text == "Evacuate now."
    assert result.tool_calls == []


def test_normalize_valid_tool_call_alongside_text_keeps_both():
    result = llm._normalize_message(
        FakeMessage(
            content="hold on",
            tool_calls=[FakeToolCall("notify_dispatch", DISPATCH_ARGS)],
        )
    )
    assert result.text == "hold on"
    assert len(result.tool_calls) == 1


def test_normalize_malformed_arguments_returns_none():
    result = llm._normalize_message(
        FakeMessage(tool_calls=[FakeToolCall("notify_dispatch", "{oops")])
    )
    assert result is None


@pytest.mark.parametrize("content", ["", "   ", None])
def test_normalize_empty_content_without_tool_calls_returns_none(content):
    assert llm._normalize_message(FakeMessage(content=content)) is None


def test_normalize_skips_non_function_tool_calls():
    result = llm._normalize_message(
        FakeMessage(
            content="hi",
            tool_calls=[FakeToolCall("something_else", "{}", type="custom")],
        )
    )
    assert result.text == "hi"
    assert result.tool_calls == []


# ── complete_sms ───────────────────────────────────────────────────────


def test_complete_sms_passes_request_kwargs(fake_client):
    client = fake_client(
        fake_response(tool_calls=[FakeToolCall("notify_dispatch", DISPATCH_ARGS)])
    )
    tools = [
        {"type": "function", "function": {"name": "notify_dispatch", "parameters": {"type": "object"}}}
    ]

    result = asyncio.run(llm.complete_sms("granite4.2:8b", "sys", "user prompt", tools))

    assert client.chat.completions.calls == 1
    kwargs = client.chat.completions.kwargs
    assert kwargs["model"] == "granite4.2:8b"
    assert kwargs["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "user prompt"},
    ]
    assert kwargs["tools"] == tools
    assert kwargs["max_tokens"] == 400
    assert result.tool_calls[0].arguments["emergency_type"] == "trapped"


def test_complete_sms_custom_max_tokens(fake_client):
    client = fake_client(fake_response(content="reply"))
    asyncio.run(llm.complete_sms("m", "s", "u", [], max_tokens=150))
    assert client.chat.completions.kwargs["max_tokens"] == 150


def test_complete_sms_retries_once_on_malformed_arguments(fake_client):
    client = fake_client(
        fake_response(tool_calls=[FakeToolCall("notify_dispatch", "{oops")]),
        fake_response(tool_calls=[FakeToolCall("notify_dispatch", DISPATCH_ARGS)]),
    )
    result = asyncio.run(llm.complete_sms("m", "s", "u", []))
    assert client.chat.completions.calls == 2
    assert result.tool_calls[0].arguments["emergency_type"] == "trapped"


def test_complete_sms_retries_once_on_empty_response(fake_client):
    client = fake_client(
        fake_response(content=""),
        fake_response(content="Use Route 2."),
    )
    result = asyncio.run(llm.complete_sms("m", "s", "u", []))
    assert client.chat.completions.calls == 2
    assert result.text == "Use Route 2."


def test_complete_sms_raises_after_two_unusable_responses(fake_client):
    fake_client(fake_response(content=""), fake_response(content=None))
    with pytest.raises(RuntimeError, match="no usable content"):
        asyncio.run(llm.complete_sms("m", "s", "u", []))


# ── complete_json ──────────────────────────────────────────────────────


def test_complete_json_clean(fake_client):
    fake_client(fake_response(content='{"advisory": "Go now", "risk_level": "HIGH"}'))
    data = asyncio.run(llm.complete_json("m", "s", "u"))
    assert data == {"advisory": "Go now", "risk_level": "HIGH"}


def test_complete_json_markdown_fenced(fake_client):
    fake_client(fake_response(content='```json\n{"advisory": "Fenced"}\n```'))
    data = asyncio.run(llm.complete_json("m", "s", "u"))
    assert data["advisory"] == "Fenced"


def test_complete_json_wrapped_in_prose(fake_client):
    fake_client(fake_response(content='Here you go: {"advisory": "Prose"} hope that helps'))
    data = asyncio.run(llm.complete_json("m", "s", "u"))
    assert data["advisory"] == "Prose"


def test_complete_json_garbage_raises(fake_client):
    fake_client(fake_response(content="no json here at all"))
    with pytest.raises(json.JSONDecodeError):
        asyncio.run(llm.complete_json("m", "s", "u"))


def test_complete_json_empty_content_raises(fake_client):
    fake_client(fake_response(content=""))
    with pytest.raises(RuntimeError, match="empty content"):
        asyncio.run(llm.complete_json("m", "s", "u"))


def test_complete_json_request_kwargs(fake_client):
    client = fake_client(fake_response(content='{"advisory": "x"}'))
    asyncio.run(llm.complete_json("m", "s", "u", temperature=0.1))
    kwargs = client.chat.completions.kwargs
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["temperature"] == 0.1
    assert kwargs["model"] == "m"


# ── get_client ─────────────────────────────────────────────────────────


def test_get_client_is_a_singleton(fresh_client, monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert llm.get_client() is llm.get_client()


def test_get_client_local_server_without_key_uses_placeholder(fresh_client, monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1/")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = llm.get_client()
    assert str(client.base_url).startswith("http://localhost:11434/v1")
    assert client.api_key == "ollama"


def test_get_client_custom_base_url_with_real_key(fresh_client, monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    client = llm.get_client()
    assert str(client.base_url).startswith("https://api.example.com/v1")
    assert client.api_key == "sk-test"


def test_get_client_ignores_empty_base_url(fresh_client, monkeypatch):
    # docker-compose ${VAR:-} expands unset vars to empty strings
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    client = llm.get_client()
    assert str(client.base_url).startswith("https://api.openai.com/v1")


def test_get_client_missing_config_raises(fresh_client, monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        llm.get_client()


# ── agent contracts (schema shape + env-overridable models) ────────────


def test_notify_dispatch_tool_uses_openai_function_schema():
    tool = help_agent.NOTIFY_DISPATCH_TOOL
    assert tool["type"] == "function"
    fn = tool["function"]
    assert fn["name"] == "notify_dispatch"
    assert fn["description"]
    params = fn["parameters"]
    assert params["type"] == "object"
    assert set(params["required"]) == {"user_phone", "emergency_type", "details"}
    assert set(params["properties"]) == {"user_phone", "emergency_type", "details"}


def test_agent_models_resolve_from_env_or_default():
    assert help_agent.HELP_MODEL == (os.getenv("HELP_MODEL") or "gpt-4o")
    assert base_agent.BaseAgent.model == (os.getenv("RECOMMENDATION_MODEL") or "gpt-4o-mini")
