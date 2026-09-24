"""
rag_query.py
------------
Called every time a user sends an SMS to FireLink.
Takes the user's phone number + message, retrieves relevant fire
knowledge from Pinecone, injects their profile from mock_users.json,
and returns a Claude-generated SMS response.

Usage (standalone test):
    python rag_query.py

Designed to be imported by your Twilio SMS webhook (future item)
    from rag_query import query_agent
    response = query_agent(phone_number="+16195550001", user_message="There's smoke outside")

Compatibility:
    - Uses same INDEX_NAME, DOCS_NAMESPACE, embeddings model as ingest.py
    - Requires Pinecone index to already be populated by ingest.py

Requirements:
    pip install langchain langchain-openai langchain-pinecone anthropic pinecone-client python-dotenv
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
import anthropic

load_dotenv()

# ── Config (must match ingest.py exactly) ─────────────────────────────────────

OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME       = os.getenv("PINECONE_INDEX_NAME", "emberlink")
DOCS_NAMESPACE   = "docs"               # same namespace used in ingest.py
TOP_K            = 5                    # number of chunks to retrieve
MOCK_USERS_PATH  = Path("./mock_users.json")

# ── Step 1: Load mock users ───────────────────────────────────────────────────

def load_mock_users() -> dict:
    """
    Load mock_users.json and index users by phone number for O(1) lookup.

    mock_users.json structure:
    [
        {
            "phone": "+16195550001",
            "name": "Maria",
            "zip": "92103",
            "pets": 2,
            "has_vehicle": false,
            "medical_device": true,
            "prep_steps_complete": 2,
            "prep_steps_total": 5,
            "needs_ride": true,
            "volunteer": false
        },
        ...
    ]

    Returns a dict keyed by phone number:
    { "+16195550001": { ...profile... }, ... }
    """
    if not MOCK_USERS_PATH.exists():
        raise FileNotFoundError(
            f"mock_users.json not found at {MOCK_USERS_PATH}. "
            "Create it with at least one user profile."
        )

    with open(MOCK_USERS_PATH, "r") as f:
        users_list = json.load(f)

    # Index by phone number for fast lookup
    return {user["phone"]: user for user in users_list}


# ── Step 2: Serialize user profile → natural language ────────────────────────

def serialize_user_profile(profile: dict) -> str:
    """
    Convert a user profile dict into a natural language string.

    Why: Claude works on text, not JSON. A sentence gives Claude
    the user's context in a form it can reason about naturally.

    Example output:
    "Maria lives in ZIP 92103. She has 2 pets, no vehicle, uses a
    medical device, needs a ride to evacuate, and has completed
    2 of 5 preparedness steps."
    """
    name        = profile.get("name", "The user")
    zip_code    = profile.get("zip", "unknown ZIP")
    pets        = profile.get("pets", 0)
    has_vehicle = profile.get("has_vehicle", True)
    medical     = profile.get("medical_device", False)
    needs_ride  = profile.get("needs_ride", False)
    volunteer   = profile.get("volunteer", False)
    prep_done   = profile.get("prep_steps_complete", 0)
    prep_total  = profile.get("prep_steps_total", 5)

    # Build each clause conditionally so unknown fields stay silent
    vehicle_str  = "has a vehicle" if has_vehicle else "has no vehicle"
    medical_str  = "uses a medical device" if medical else "no medical device"
    ride_str     = "needs a ride to evacuate" if needs_ride else "can self-evacuate"
    volunteer_str = "is a registered volunteer" if volunteer else ""
    pets_str     = f"has {pets} pet{'s' if pets != 1 else ''}" if pets > 0 else "no pets"

    parts = [
        f"{name} lives in ZIP {zip_code}.",
        f"They {pets_str}, {vehicle_str}, {medical_str}, and {ride_str}.",
        f"They have completed {prep_done} of {prep_total} preparedness steps.",
    ]
    if volunteer_str:
        parts.append(f"{name} {volunteer_str}.")

    return " ".join(parts)


# ── Step 3: Retrieve relevant chunks from Pinecone ────────────────────────────

def retrieve_chunks(user_message: str) -> list[str]:
    """
    Embed the user's message and search Pinecone for the most
    semantically similar chunks in the docs namespace.

    How it works:
    1. user_message is converted to a 1536-dim vector (same model as ingest.py)
    2. Pinecone finds the TOP_K stored vectors closest by cosine similarity
    3. Returns the original text of those chunks

    These chunks are the fire protocol knowledge the AI agent uses
    to answer — it cannot go outside them.
    """
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",     # must match ingest.py
        openai_api_key=OPENAI_API_KEY
    )

    vector_store = PineconeVectorStore(
        index_name=INDEX_NAME,
        embedding=embeddings,
        namespace=DOCS_NAMESPACE            # must match ingest.py
    )

    # similarity_search returns Document objects sorted by relevance
    results = vector_store.similarity_search(user_message, k=TOP_K)

    # Extract just the text content from each Document
    chunks = [doc.page_content for doc in results]

    return chunks


# ── Step 4: Build the Claude prompt ──────────────────────────────────────────

def build_prompt(user_profile_str: str, chunks: list[str], user_message: str) -> str:
    """
    Assemble the full prompt Claude receives.

    Structure:
    - USER PROFILE: personalized context injected from mock_users.json
    - RELEVANT KNOWLEDGE: top chunks retrieved from Pinecone
    - USER MESSAGE: what the person actually texted in
    - Instruction: keep response short, calm, SMS-friendly

    The strict instruction "Only use the information below" enforces
    RAG-only behavior — Claude cannot hallucinate outside the chunks.
    """
    chunks_text = "\n\n".join(
        f"[Source {i+1}]:\n{chunk}" for i, chunk in enumerate(chunks)
    )

    prompt = f"""You are EmberLink, a calm emergency wildfire assistant responding via SMS.
Only use the information provided below to answer. Do not add information not present here.
If you cannot answer from the provided knowledge, say: "I don't have specific guidance for that. Please call 911 if you are in immediate danger."

USER PROFILE:
{user_profile_str}

RELEVANT KNOWLEDGE:
{chunks_text}

USER MESSAGE:
"{user_message}"

Respond in 1-3 short sentences. Be direct, calm, and actionable. No bullet points — this is an SMS."""

    return prompt


# ── Step 5: Call Claude ───────────────────────────────────────────────────────

def call_claude(prompt: str) -> str:
    """
    Send the assembled prompt to Claude and return the SMS response.

    Uses claude-sonnet-4-20250514 — fast and accurate enough for
    emergency guidance. max_tokens=300 keeps responses SMS-length.
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    return message.content[0].text


# ── Main entrypoint: called by Twilio webhook ─────────────────────────────────

def query_agent(phone_number: str, user_message: str) -> str:
    """
    Full RAG pipeline for one incoming SMS.

    Args:
        phone_number: E.164 format e.g. "+16195550001"
        user_message: raw text the user sent

    Returns:
        SMS response string from Claude

    Flow:
        1. Look up user profile from mock_users.json
        2. Serialize profile → natural language string
        3. Embed user message → search Pinecone → get top 5 chunks
        4. Build prompt: profile + chunks + message
        5. Call Claude → return SMS response
    """
    # 1. Load and look up user
    users = load_mock_users()
    profile = users.get(phone_number)

    if profile:
        user_profile_str = serialize_user_profile(profile)
    else:
        # Unknown number — generic profile, no personalization
        user_profile_str = "User profile unknown. No personalization available."

    # 2. Retrieve relevant fire knowledge chunks from Pinecone
    chunks = retrieve_chunks(user_message)

    # 3. Build the full prompt
    prompt = build_prompt(user_profile_str, chunks, user_message)

    # 4. Call Claude and return response
    response = call_claude(prompt)

    return response


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_cases = [
        {
            "phone": "+16195550001",
            "message": "There's smoke coming under my door, what do I do?"
        },
        {
            "phone": "+16195550002",
            "message": "Should I evacuate now or wait?"
        },
        {
            "phone": "+16195550003",
            "message": "I have pets and no car, how do I get out?"
        }
    ]

    for test in test_cases:
        print(f"\n{'='*50}")
        print(f"Phone:   {test['phone']}")
        print(f"Message: {test['message']}")
        print(f"{'='*50}")
        response = query_agent(
            phone_number=test["phone"],
            user_message=test["message"]
        )
        print(f"EmberLink: {response}")