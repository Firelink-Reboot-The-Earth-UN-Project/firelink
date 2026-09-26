"""
rag_query.py
------------
Retrieval helpers for the Help Agent: loads mock user profiles from
mock_users.json and retrieves relevant fire-knowledge chunks from Pinecone.
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore

load_dotenv()

# ── Config ───────────────────────────────────────────────────────────────────

OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME       = os.getenv("PINECONE_INDEX_NAME", "firelink")
DOCS_NAMESPACE   = "docs"
TOP_K            = 5 # for RAG retrieval

# Resolve data files relative to this file: app/services/knowledge/rag_query.py
# parents[3] climbs to repo root (knowledge → services → app → root).
PROJECT_ROOT     = Path(__file__).resolve().parents[3]
MOCK_USERS_PATH  = PROJECT_ROOT / "app" / "data" / "mock_users.json"


def load_mock_users() -> dict:
    if not MOCK_USERS_PATH.exists():
        raise FileNotFoundError(
            f"mock_users.json not found at {MOCK_USERS_PATH}. "
            "Create it with at least one user profile."
        )

    with open(MOCK_USERS_PATH, "r") as f:
        users_list = json.load(f)

    return {user["phone"]: user for user in users_list}


def serialize_user_profile(profile: dict) -> str:
    name        = profile.get("name", "The user")
    zip_code    = profile.get("zip", "unknown ZIP")
    pets        = profile.get("pets", 0)
    has_vehicle = profile.get("has_vehicle", True)
    medical     = profile.get("medical_device", False)
    needs_ride  = profile.get("needs_ride", False)
    volunteer   = profile.get("volunteer", False)
    prep_done   = profile.get("prep_steps_complete", 0)
    prep_total  = profile.get("prep_steps_total", 5)

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


def retrieve_chunks(user_message: str) -> list[str]:
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        openai_api_key=OPENAI_API_KEY,
    )

    vector_store = PineconeVectorStore(
        index_name=INDEX_NAME,
        embedding=embeddings,
        namespace=DOCS_NAMESPACE,
    )

    results = vector_store.similarity_search(user_message, k=TOP_K)
    return [doc.page_content for doc in results]

