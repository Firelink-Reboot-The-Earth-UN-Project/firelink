"""
Help Agent — unified conversational SMS handler.

Blends:
  - User profile (mock_users.json)
  - Latest fire + weather context (Kafka via context_service)
  - Latest official advisory (Kafka firelink.recommendations)
  - RAG chunks (Pinecone, top-K)
  - Open shelter list (shelters.json)

into a single LLM prompt and returns an SMS-shaped reply in the user's
language.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from app.services.context_service import (
    get_latest_context,
    get_latest_recommendation,
)
from app.services.dispatch_service import notify_dispatch
from app.services.knowledge.rag_query import (
    PROJECT_ROOT,
    load_mock_users,
    retrieve_chunks,
    serialize_user_profile,
)
from app.services.llm import complete_sms

logger = logging.getLogger(__name__)

SHELTERS_PATH = PROJECT_ROOT / "app" / "data" / "shelters.json"

HELP_MODEL = os.getenv("HELP_MODEL") or "gpt-4o"
MAX_TOKENS = 400

SYSTEM_PROMPT = """You are FireLink, an informative, multilingual emergency assistant for the 2025 Eaton Fire in Los Angeles.
Be calm, brief, and specific. Lead with the action, not the explanation. SMS only: 1-3 short sentences, plain text, no markdown, no bullet points.

Language rule: ALWAYS respond in the same language as the USER MESSAGE. If the user mixes languages, use the dominant language. Never switch languages.

Use only the information provided in the user message. If you cannot answer from that information, reply (in the user's language):
"I don't have specific guidance for that. Please call 911 if you are in immediate danger."

Tool policy:
- If the user is in active life-threatening danger right now (trapped, injured, fire at the door, smoke inhalation, medical crisis, cannot evacuate), CALL notify_dispatch immediately.
- Do NOT produce a text reply when calling the tool.
"""

NOTIFY_DISPATCH_TOOL = {
    "type": "function",
    "function": {
        "name": "notify_dispatch",
        "description": (
            "Notify emergency dispatch (911) for an active, life-threatening situation. "
            "Call ONLY when the user reports immediate danger right now: trapped, injured, "
            "burned, unconscious, fire inside or at the door, smoke inhalation, medical "
            "crisis, surrounded by flames, or unable to evacuate. "
            "Do NOT call for information questions, status checks, shelter inquiries, "
            "evacuation-zone questions, or past-tense reports."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "user_phone": {
                    "type": "string",
                    "description": "User's phone number in E.164 format.",
                },
                "emergency_type": {
                    "type": "string",
                    "description": "Short label such as 'trapped', 'medical', 'fire_at_residence', 'injured'.",
                },
                "details": {
                    "type": "string",
                    "description": "One-sentence factual summary of the situation in English.",
                },
            },
            "required": ["user_phone", "emergency_type", "details"],
        },
    },
}


def load_shelters() -> list[dict]:
    if not SHELTERS_PATH.exists():
        return []
    with open(SHELTERS_PATH, "r") as f:
        return json.load(f)


def serialize_shelters(shelters: list[dict]) -> str:
    if not shelters:
        return "No shelter data available."
    lines = []
    for s in shelters:
        flags = []
        if s.get("has_pet_area"):
            flags.append("pet-friendly")
        if s.get("accessible"):
            flags.append("ADA-accessible")
        flags_str = ", ".join(flags) if flags else "no extra amenities"
        status = "OPEN" if s.get("open") else "CLOSED"
        lines.append(
            f"- [{status}] {s['name']} — {s['address']} (capacity {s.get('capacity', '?')}; {flags_str})"
        )
    return "\n".join(lines)


def serialize_fire(fire_records: list[dict]) -> str:
    if not fire_records:
        return "No recent fire data available."
    latest = fire_records[-1]
    return (
        f"{latest.get('name', 'Fire')} — "
        f"{latest.get('acres', '?')} acres, "
        f"containment {latest.get('containment', '?')}%, "
        f"status: {latest.get('status', 'unknown')}, "
        f"as of {latest.get('timestamp', 'unknown')}."
    )


def serialize_weather(weather_records: list[dict]) -> str:
    if not weather_records:
        return "No recent weather data available."
    latest = weather_records[-1]
    return (
        f"{latest.get('event', 'Weather')} ({latest.get('severity', '?')}) — "
        f"wind {latest.get('wind_mph', '?')} mph, "
        f"humidity {latest.get('humidity_pct', '?')}%, "
        f"area: {latest.get('area', 'unknown')}, "
        f"as of {latest.get('timestamp', 'unknown')}."
    )


def serialize_advisory(advisory: dict | None) -> str:
    if not advisory:
        return "No official advisory issued yet."
    return (
        f"Risk: {advisory.get('risk_level', 'unknown')}. "
        f"Advisory: {advisory.get('advisory', 'n/a')} "
        f"(reason: {advisory.get('reasoning', 'n/a')})"
    )


def build_user_prompt(
    phone: str,
    profile_text: str,
    fire_text: str,
    weather_text: str,
    advisory_text: str,
    shelter_text: str,
    rag_text: str,
    user_message: str,
) -> str:
    return f"""CONTEXT
USER PHONE: {phone}

USER PROFILE:
{profile_text}

LATEST FIRE STATUS:
{fire_text}

LATEST WEATHER:
{weather_text}

LATEST OFFICIAL ADVISORY:
{advisory_text}

NEARBY SHELTERS:
{shelter_text}

RELEVANT KNOWLEDGE:
{rag_text}

USER MESSAGE:
"{user_message}"
"""


async def _retrieve_chunks_async(message: str) -> list[str]:
    return await asyncio.to_thread(retrieve_chunks, message)


async def handle_sms(phone: str, user_message: str) -> dict:
    """Full Help-Agent pipeline for one inbound SMS.

    Returns:
        {
            "reply": str,              # SMS reply text
            "is_emergency": bool,      # whether dispatch was triggered
            "dispatch": dict | None,   # full dispatch JSON (frontend payload) or None
        }
    """
    # 1. User profile
    try:
        users = load_mock_users()
        profile = users.get(phone)
        profile_text = (
            serialize_user_profile(profile)
            if profile
            else "User profile unknown. No personalization available."
        )
    except FileNotFoundError as e:
        logger.warning("mock_users missing: %s", e)
        profile_text = "User profile unavailable."

    # 2. Fire + weather context, advisory, RAG, shelters — fan out
    fire_weather_task = asyncio.create_task(get_latest_context())
    advisory_task = asyncio.create_task(get_latest_recommendation())
    rag_task = asyncio.create_task(_retrieve_chunks_async(user_message))

    fire_records: list[dict] = []
    weather_records: list[dict] = []
    advisory: dict | None = None
    chunks: list[str] = []

    try:
        ctx = await fire_weather_task
        fire_records = ctx.get("fire", [])
        weather_records = ctx.get("weather", [])
    except Exception as e:
        logger.warning("fire/weather context unavailable: %s", e)

    try:
        advisory = await advisory_task
    except Exception as e:
        logger.warning("advisory unavailable: %s", e)

    try:
        chunks = await rag_task
    except Exception as e:
        logger.warning("RAG retrieval failed: %s", e)

    shelters = load_shelters()

    rag_text = (
        "\n\n".join(f"[Source {i+1}]:\n{c}" for i, c in enumerate(chunks))
        if chunks
        else "No knowledge chunks retrieved."
    )

    user_prompt = build_user_prompt(
        phone=phone,
        profile_text=profile_text,
        fire_text=serialize_fire(fire_records),
        weather_text=serialize_weather(weather_records),
        advisory_text=serialize_advisory(advisory),
        shelter_text=serialize_shelters(shelters),
        rag_text=rag_text,
        user_message=user_message,
    )

    result = await complete_sms(
        model=HELP_MODEL,
        system=SYSTEM_PROMPT,
        user=user_prompt,
        tools=[NOTIFY_DISPATCH_TOOL],
        max_tokens=MAX_TOKENS,
    )

    tool_call = next(
        (tc for tc in result.tool_calls if tc.name == "notify_dispatch"),
        None,
    )
    if tool_call is not None:
        dispatch = notify_dispatch(
            user_phone=tool_call.arguments.get("user_phone", phone),
            emergency_type=tool_call.arguments.get("emergency_type", "unspecified"),
            details=tool_call.arguments.get("details", user_message),
        )
        ack = (
            f"Emergency dispatch notified. Units en route, ETA ~{dispatch['eta_minutes']} min. "
            f"Incident #{dispatch['incident_id']}. Stay on the line if safe."
        )
        return {"reply": ack, "is_emergency": True, "dispatch": dispatch}

    return {"reply": result.text or "", "is_emergency": False, "dispatch": None}
