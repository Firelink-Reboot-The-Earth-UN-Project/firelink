"""
llm.py
------
The single place FireLink talks to a chat-completions LLM server.

One client (the OpenAI SDK) pointed at either hosted OpenAI (default) or any
OpenAI-compatible server via OPENAI_BASE_URL (Ollama, vLLM, LM Studio,
llama.cpp server, LocalAI).

Operations:
    complete_sms  — Help Agent path: tools-aware completion
    complete_json — Recommendation Agent path: JSON-mode completion
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field

from dotenv import load_dotenv
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

load_dotenv()


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict


@dataclass(frozen=True)
class LLMResult:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    """Lazy singleton client. Hosted OpenAI by default; OPENAI_BASE_URL
    redirects to any OpenAI-compatible server. Local servers ignore API
    keys, so a placeholder is used when none is set."""
    global _client
    if _client is not None:
        return _client

    base_url = os.getenv("OPENAI_BASE_URL") or None
    api_key = os.getenv("OPENAI_API_KEY")

    if not base_url:
        # the SDK also reads OPENAI_BASE_URL itself; an empty-string value
        # (e.g. docker-compose ${VAR:-} expansion) would yield a broken URL('')
        os.environ.pop("OPENAI_BASE_URL", None)

    if not base_url and not api_key:
        raise RuntimeError(
            "Neither OPENAI_API_KEY nor OPENAI_BASE_URL is set. "
            "Add one to backend/.env or export it in your shell."
        )

    if base_url and not api_key:
        _client = AsyncOpenAI(base_url=base_url, api_key="ollama")
    else:
        _client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    return _client


def _normalize_message(message) -> LLMResult | None:
    """Map an OpenAI chat message to an LLMResult.

    Returns None when the response is unusable: no text and no valid tool
    calls, or any tool call whose JSON arguments fail to parse.
    """
    tool_calls: list[ToolCall] = []
    for tc in message.tool_calls or []:
        if getattr(tc, "type", None) != "function":
            continue
        try:
            arguments = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            logger.warning("malformed tool arguments for %s", tc.function.name)
            return None
        tool_calls.append(ToolCall(name=tc.function.name, arguments=arguments))

    text = message.content
    if not tool_calls and not (text and text.strip()):
        return None
    return LLMResult(text=text, tool_calls=tool_calls)


async def complete_sms(
    model: str,
    system: str,
    user: str,
    tools: list[dict],
    max_tokens: int = 400,
) -> LLMResult:
    """Tools-aware completion for the Help Agent.

    Retries once when the response is unusable (empty content or malformed
    tool arguments), then raises.
    """
    client = get_client()

    for attempt in (1, 2):
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            tools=tools,
            max_tokens=max_tokens,
        )
        result = _normalize_message(response.choices[0].message)
        if result is not None:
            return result
        logger.warning("unusable LLM response on attempt %d (model=%s)", attempt, model)

    raise RuntimeError(f"LLM returned no usable content after 2 attempts (model={model})")


async def complete_json(
    model: str,
    system: str,
    user: str,
    temperature: float = 0.3,
) -> dict:
    """JSON-mode completion for the Recommendation Agent, with recovery
    parsing for markdown-fenced or prose-wrapped JSON."""

    client = get_client()

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=temperature,
    )

    raw = response.choices[0].message.content
    if not raw or not raw.strip():
        raise RuntimeError(f"LLM returned empty content for JSON request (model={model})")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise
