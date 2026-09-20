# FireLink Backend

Real-time wildfire evacuation pipeline. Kafka streams CAL FIRE + weather data,
SQLite caches it, an OpenAI agent emits advisories every 60s, and a multilingual
**Help Agent** answers simulated SMS by blending RAG knowledge (Pinecone PDFs),
live fire/weather context, the latest official advisory, and an LA-area shelter
list — all in a single Claude call.

## Stack

7 containers (orchestrated by `docker-compose.yml`):

| Service | Port | Purpose |
|---|---|---|
| `firelink-zookeeper` | — | Kafka coordinator |
| `firelink-kafka` | 9092 | Broker (`firelink.fire`, `firelink.weather`, `firelink.recommendations`) |
| `firelink-backend` | 8000 | FastAPI: CRUD + Help Agent + context |
| `firelink-calfire-producer` | — | Replays `app/data/fire_incidents.json` → Kafka |
| `firelink-noaa-producer` | — | Replays `app/data/weather_alerts.json` → Kafka |
| `firelink-recommendation-agent` | — | OpenAI `gpt-4o-mini`, every 60s |
| `firelink-mcp-server` | 8001 | FastMCP `get_context` tool |

In local dev mode only zookeeper + kafka run in Docker; the Python services
run on the host from `backend/.venv` — see "Local development" below.

## Prerequisites

- Docker Desktop running (full stack, or Kafka-only in local dev mode)
- `backend/.env` with these keys:

      OPENAI_API_KEY=...         # recommendation-agent + Pinecone embeddings
      ANTHROPIC_API_KEY=...      # Help Agent (Claude SMS reply)
      PINECONE_API_KEY=...
      PINECONE_INDEX_NAME=...    # e.g. rte-wildfire-data

## Quick start: full test path

    make check          # confirms Docker + Compose available
    make up-build       # builds images, starts all 7 containers
    # wait ~30s for kafka healthcheck to pass
    make ps             # all 7 containers should be Up
    make ingest         # one-shot: load docs/*.pdf → Pinecone (only needed once)
    make test           # runs test/smoke_test.py — checks make targets, REST, Help Agent

`make test` exits 0 if everything passes, 1 if anything fails. Per-check
PASS/FAIL lines tell you what broke.

## Local development (hybrid)

Active backend development without rebuilding images: only zookeeper + kafka
run in Docker (host listener `:29092` via `docker-compose.dev.yml`); the API,
producers, and agent run on the host from `backend/.venv`:

    make dev-venv           # once: create .venv + install requirements.txt
    make dev-infra          # zookeeper + kafka only
    make dev-api            # uvicorn --reload :8000
    make dev-calfire        # when you need incident data flowing
    make dev-noaa
    make dev-recommendation

Requires two extra lines in `backend/.env` (host-only; containers use their
own config):

    KAFKA_BOOTSTRAP=localhost:29092
    DATABASE_URL=sqlite:///app/data/firelink.db

Run everything from `backend/` — the SQLite path is CWD-relative (DB lands at
`app/data/firelink.db`, re-seeded by producers on startup). `make dev-down`
stops all containers in the compose project. See the repo README for the
full guide.

## What `make test` checks

Smoke test in `test/smoke_test.py`:

1. `make ps` lists all 7 firelink containers
2. `make health` returns `healthy`
3. `make topics` lists `firelink.fire` and `firelink.weather`
4. `GET /health` → 200
5. `GET /fire-incidents` → list
6. `GET /weather-alerts` → list
7. `GET /context/latest` → `{fire, weather, fetched_at}`
8. `OPENAI_API_KEY`, `PINECONE_API_KEY`, `ANTHROPIC_API_KEY` present
9. `POST /sms/inbound` returns a non-empty `reply` (uses first fixture from `app/data/sms_test_cases.json`)

The Help Agent check requires `make ingest` to have been run at least once
against the configured Pinecone index.

## Manual / interactive checks

| Goal | Command |
|---|---|
| Latest Kafka context (10 of each) | `make context` |
| List Kafka topics | `make topics` |
| Live fire stream | `make stream-fire` |
| Live weather stream | `make stream-weather` |
| Live recommendations stream | `make stream-recommendations` |
| Backend logs | `make logs` |
| All container logs | `make logs-all` |
| Recommendation agent logs | `make logs-recommendation` |
| MCP server logs | `make logs-mcp` |
| Interactive SMS chat | `make sms` |
| Batch-replay SMS fixtures | `make sms-replay` |

## SMS simulator

`make sms` opens a REPL that POSTs each line to `/sms/inbound`:

    $ make sms
    Phone (E.164, e.g. +16195550001): +16195550003
    you> Where is the nearest open shelter that takes pets?
    sms> Pasadena Civic Auditorium at 300 E Green St, Pasadena — open and pet-friendly...
    you> ¿Necesito evacuar ahora?
    sms> ...

`make sms-replay` walks every entry in `app/data/sms_test_cases.json` (English
and Spanish cases covering Q&A, shelter lookup, status, and preparedness) and
prints `phone | message | reply` for each.

Override the API target with `FIRELINK_URL` (default `http://localhost:8000`).

Hit endpoints directly:

    curl http://localhost:8000/health
    curl http://localhost:8000/fire-incidents | jq '.[0]'
    curl http://localhost:8000/weather-alerts | jq '.[0]'
    curl http://localhost:8000/context/latest | jq .fetched_at
    curl http://localhost:8000/agents/recommendations/latest | jq .

    curl -X POST http://localhost:8000/sms/inbound \
      -H 'Content-Type: application/json' \
      -d '{"phone":"+16195550001","message":"Smoke under my door, what do I do?"}' \
      | jq .reply

## Lifecycle

| Goal | Command |
|---|---|
| Start (no rebuild) | `make up` |
| Rebuild + start | `make up-build` |
| Stop (keep data) | `make down` |
| Stop + wipe SQLite volume | `make clean` |

`make clean` does **not** clear Pinecone vectors — those are external. Re-run
`make ingest` only if you want to repopulate the index.

## Troubleshooting

**Container name conflict on `make up-build`** — another compose project is
holding the `firelink-*` names. Run:

    docker compose -p <other-project-name> down

or force-remove by name (`docker rm -f firelink-zookeeper firelink-kafka ...`).

**`make ingest` fails with Pinecone metadata error** — the configured index
must accept 1536-dim vectors (OpenAI `text-embedding-3-small`). If you swapped
indexes mid-run, recreate it.

**`make test` Help-Agent step fails with `connection error`** — backend isn't
ready. Wait for `make ps` to show `firelink-backend` as healthy, then rerun.

**Kafka unhealthy / producers can't connect** — Kafka takes 15-30s to come up
after `make up-build`. Watch `make logs-all` until you see
`Kafka connected (attempt 1)` from the producers.

**Host process can't reach Kafka (local dev)** — `make dev-infra` running and
healthy? Host processes must use `localhost:29092` (`KAFKA_BOOTSTRAP` in
`backend/.env`); `kafka:9092` and `localhost:9092` are container-only.

**`unable to open database file` (local dev)** — run from `backend/`, not the
repo root; `DATABASE_URL` is CWD-relative.

## Layout

    app/
      core/           # database.py, kafka.py
      data/           # fire_incidents.json, weather_alerts.json,
                      # mock_users.json, shelters.json, sms_test_cases.json
      models/         # SQLAlchemy ORM
      schemas/        # Pydantic request/response (incl. sms.py)
      repository/     # CRUD
      routes/         # /context, /fire-incidents, /weather-alerts,
                      # /agents/recommendations, /sms
      services/
        context_service.py  # latest fire/weather + advisory readers
        producers/          # CAL FIRE + NOAA Kafka producers
        agents/
          recommendation_agent.py   # OpenAI gpt-4o-mini, every 60s
          help_agent.py             # unified SMS handler (Claude)
        knowledge/                  # ingest.py + rag_query.py helpers
      mcp_server.py   # FastMCP get_context tool
      main.py         # FastAPI entry point
    docs/             # source PDFs for ingest
    test/             # smoke_test.py + sms_cli.py
