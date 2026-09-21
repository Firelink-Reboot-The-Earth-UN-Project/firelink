#!/usr/bin/env python3
"""
FireLink smoke test.

Assumes the docker-compose stack is already up (`make up` or `make up-build`).
Runs through the make targets and key REST endpoints; fails loud if anything
is missing — including the RAG endpoint and its required API keys.

Run:
    make test
or:
    python3 test/smoke_test.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("FIRELINK_URL", "http://localhost:8000")

results: list[tuple[str, bool, str | None]] = []


# ── .env loader (so RAG key check sees the same env make would)
def load_dotenv() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# ── runner
def run_check(name: str, fn) -> None:
    try:
        fn()
        print(f"  PASS  {name}")
        results.append((name, True, None))
    except Exception as e:
        print(f"  FAIL  {name}: {e}")
        results.append((name, False, str(e)))


# ── helpers
def sh(cmd: str) -> str:
    out = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if out.returncode != 0:
        raise RuntimeError(
            f"`{cmd}` exit {out.returncode}: {(out.stderr or out.stdout).strip()}"
        )
    return out.stdout


def http_get(path: str, timeout: int = 10) -> str:
    url = f"{BASE_URL}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            if r.status != 200:
                raise RuntimeError(f"GET {path} → {r.status}")
            return r.read().decode()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GET {path} → HTTP {e.code}: {e.read().decode(errors='ignore')[:200]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"GET {path} → connection error: {e.reason}")


def http_post(path: str, body: dict, timeout: int = 60) -> str:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if r.status != 200:
                raise RuntimeError(f"POST {path} → {r.status}")
            return r.read().decode()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"POST {path} → HTTP {e.code}: {e.read().decode(errors='ignore')[:200]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"POST {path} → connection error: {e.reason}")


# ── container / make-target checks
def check_ps() -> None:
    out = sh("make ps")
    required = [
        "firelink-backend",
        "firelink-kafka",
        "firelink-zookeeper",
        "firelink-calfire-producer",
        "firelink-noaa-producer",
        "firelink-mcp-server",
        "firelink-recommendation-agent",
    ]
    missing = [c for c in required if c not in out]
    if missing:
        raise RuntimeError(f"missing containers: {missing}")


def check_health_make() -> None:
    out = sh("make health")
    if "healthy" not in out:
        raise RuntimeError(f"unexpected output: {out!r}")


def check_topics() -> None:
    out = sh("make topics")
    required = ["firelink.fire", "firelink.weather"]
    missing = [t for t in required if t not in out]
    if missing:
        raise RuntimeError(f"missing topics: {missing}. saw: {out.strip()!r}")


# ── REST endpoint checks
def check_health_endpoint() -> None:
    data = json.loads(http_get("/health"))
    if data.get("status") != "healthy":
        raise RuntimeError(f"unexpected: {data}")


def check_fire_incidents() -> None:
    data = json.loads(http_get("/fire-incidents"))
    if not isinstance(data, list):
        raise RuntimeError(f"expected list, got {type(data).__name__}")


def check_weather_alerts() -> None:
    data = json.loads(http_get("/weather-alerts"))
    if not isinstance(data, list):
        raise RuntimeError(f"expected list, got {type(data).__name__}")


def check_context() -> None:
    data = json.loads(http_get("/context/latest"))
    for key in ("fire", "weather", "fetched_at"):
        if key not in data:
            raise RuntimeError(f"missing key '{key}' in context payload")


# ── Help-Agent SMS checks (loud failure when keys are missing)
# Embeddings still run on OpenAI (text-embedding-3-small), so OPENAI_API_KEY
# stays required even when the chat models run locally via OPENAI_BASE_URL.
HELP_AGENT_KEYS = ("OPENAI_API_KEY", "PINECONE_API_KEY")


def check_help_agent_keys() -> None:
    missing = [k for k in HELP_AGENT_KEYS if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"required Help-Agent env vars missing: {missing}")


def check_sms_endpoint() -> None:
    fixture = REPO_ROOT / "app" / "data" / "sms_test_cases.json"
    cases = json.loads(fixture.read_text())
    if not cases:
        raise RuntimeError(f"no test cases in {fixture}")
    case = cases[0]
    body = http_post(
        "/sms/inbound",
        {"phone": case["phone"], "message": case["message"]},
    )
    data = json.loads(body)
    reply = data.get("reply")
    if not reply:
        raise RuntimeError(f"empty reply: {data}")


# ── main
def main() -> int:
    load_dotenv()

    print("FireLink smoke test")
    print(f"BASE_URL = {BASE_URL}")
    print("=" * 50)

    print("Containers / make targets")
    run_check("make ps lists all firelink containers", check_ps)
    run_check("make health returns healthy", check_health_make)
    run_check("make topics lists firelink.fire / firelink.weather", check_topics)

    print("REST endpoints")
    run_check("GET /health", check_health_endpoint)
    run_check("GET /fire-incidents", check_fire_incidents)
    run_check("GET /weather-alerts", check_weather_alerts)
    run_check("GET /context/latest", check_context)

    print("Help Agent / SMS pipeline (Pinecone + LLM provider)")
    run_check("Help-Agent API keys present in env", check_help_agent_keys)
    run_check("POST /sms/inbound returns non-empty reply", check_sms_endpoint)

    print("=" * 50)
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    failed = total - passed
    print(f"{passed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
