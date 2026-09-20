# FireLink — Run Guide

Wildfire evacuation intelligence platform. Backend (FastAPI + Kafka + Pinecone + OpenAI/Anthropic agents) + frontend (Next.js dashboard + chat).

This is the **monorepo run guide**. See `backend/README.md` and `frontend/README.md` for component-level details.

---

## Quick run (3 terminals)

Assumes first-time setup done (see below). For demo / fast restart:

```bash
# Terminal 1 — backend stack (rebuild + start)
cd backend
make up-build

# Terminal 2 — public tunnel for backend
ngrok http 8000
# copy the https://xxxx.ngrok-free.app URL → paste into frontend/.env.local
#   NEXT_PUBLIC_API_URL=https://xxxx.ngrok-free.app

# Terminal 3 — frontend:
cd frontend
npm run dev
```

---

## Local backend development (hybrid)

Faster loop when you're actively developing the backend: only zookeeper + Kafka run in Docker; the API, producers, and agent run natively from a Python venv with `uvicorn --reload`. Full-stack Docker (above) stays the default for demos and onboarding.

First time, from `backend/`:

```bash
make dev-venv
```

Add two host-only lines to `backend/.env` (containers ignore both — compose sets its own config):

```env
KAFKA_BOOTSTRAP=localhost:29092
DATABASE_URL=sqlite:///app/data/firelink.db
```

Daily loop — each in its own terminal, all from `backend/`:

```bash
make dev-infra           # once: zookeeper + kafka in Docker (host listener :29092)
make dev-api             # FastAPI, uvicorn --reload on :8000
make dev-calfire         # fire incidents → Kafka + SQLite (start when you need data)
make dev-noaa            # weather alerts → Kafka + SQLite
make dev-recommendation  # OpenAI advisory agent → Kafka
```

Notes:

- Host processes reach Kafka on `localhost:29092` — a HOST listener added by `docker-compose.dev.yml`; the base file's `kafka:9092` stays container-internal, so teammates running `make up` are unaffected.
- `DATABASE_URL` is CWD-relative: run from `backend/` and the DB lands at `backend/app/data/firelink.db` (gitignored, re-seeded by the producers on startup).
- `make dev-down` stops **all** containers in the compose project — run `make down` first when switching from a full-stack session.

---

## Repo layout

```
firelink/
├── backend/          # FastAPI, Kafka, agents, MCP server (docker-compose)
├── frontend/         # Next.js 16, TypeScript, Tailwind, Leaflet
├── docs/             # documentation for application and run guides
└── README.md         # this file
```

---

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Docker Desktop | running (full stack, or Kafka-only in local dev) | https://www.docker.com/products/docker-desktop |
| Docker Compose v2 | bundled with Docker Desktop | — |
| Node.js | ≥ 20 | `nvm install 20` or https://nodejs.org |
| npm | bundled with Node | — |
| Python 3 | ≥ 3.10 (host-side tools; runs the whole backend in local dev mode) | `brew install python` |
| make | preinstalled on macOS | — |

Verify:

```bash
docker --version
docker compose version
node --version
npm --version
python3 --version
```

---

## API keys you need

Create `backend/.env` (already gitignored — never commit):

```env
OPENAI_API_KEY=sk-proj-...
ANTHROPIC_API_KEY=sk-ant-...
PINECONE_API_KEY=pcsk-...
PINECONE_INDEX_NAME=rte-wildfire-data
```

Where each is used:

- `OPENAI_API_KEY` — recommendation agent (`gpt-4o-mini`) + Pinecone embeddings during ingest
- `ANTHROPIC_API_KEY` — Help Agent (Claude SMS replies + chat)
- `PINECONE_API_KEY` + `PINECONE_INDEX_NAME` — RAG vector store for wildfire knowledge PDFs

---

## First-time setup

Run from project root:

```bash
cd backend

# 1. Verify Docker available
make check

# 2. Build images, start all 7 containers
make up-build
# wait ~30s — Kafka healthcheck must pass before backend boots

# 3. Confirm all containers healthy
make ps
# expect 7 firelink-* containers, all "Up"

# 4. Confirm API live
make health
# {"status":"healthy","service":"FireLink API"}

# 5. One-time: load wildfire PDFs into Pinecone
make ingest
```

Then frontend (separate terminal):

```bash
cd frontend
npm install        # first time only
npm run dev        # http://localhost:3000
```

---

## Daily run (after first-time setup)

```bash
# terminal 1 — backend
cd backend
make up            # reuses built images

# terminal 2 — frontend
cd frontend
npm run dev
```

Stop everything:

```bash
cd backend
make down          # stop containers, keep volumes (SQLite preserved)
```

Nuke state (wipes SQLite + volumes):

```bash
make clean
```

---

## URLs

| What | URL |
|---|---|
| Frontend dashboard | http://localhost:3000 |
| Demo ZIP page | http://localhost:3000/dashboard/91001 |
| Backend API | http://localhost:8000 |
| Backend health | http://localhost:8000/health |
| OpenAPI docs | http://localhost:8000/docs |
| Live context endpoint | http://localhost:8000/context/latest |
| MCP server | http://localhost:8001 |

---

## Frontend → backend wiring

Frontend reads `NEXT_PUBLIC_API_URL`. Default: `http://localhost:8000`.

To override, create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Restart `npm run dev` after env changes — Next.js bakes env at startup.

---

## Exposing backend via ngrok (share with phone, demo to others, webhook testing)

```bash
# 1. Install
npm i -g ngrok

# 2. Sign up at https://dashboard.ngrok.com/signup
#    Grab token at https://dashboard.ngrok.com/get-started/your-authtoken
ngrok config add-authtoken <YOUR_TOKEN>

# 3. Tunnel (keep running in its own terminal)
ngrok http 8000
# copy the https://xxxx.ngrok-free.app URL it prints

# 4. Point frontend at tunnel
echo 'NEXT_PUBLIC_API_URL=https://xxxx.ngrok-free.app' > frontend/.env.local

# 5. Restart frontend
cd frontend && npm run dev
```

Free-tier URL changes every ngrok restart. Reserve a static domain in the ngrok dashboard and run:

```bash
ngrok http 8000 --domain=your-name.ngrok-free.app
```

The frontend already sends `ngrok-skip-browser-warning: true` (see `frontend/src/lib/api.ts`), bypassing the free-tier interstitial.

If you want CORS to accept calls from a tunneled frontend too (e.g. mobile testing), add origins via env in `backend/docker-compose.yml`:

```yaml
- CORS_ORIGINS=http://localhost:3000,https://your-frontend.ngrok-free.app
```

Then restart backend: `make down && make up`.

---

## Common Makefile targets (run from `backend/`)

| Command | What |
|---|---|
| `make help` | List all targets |
| `make up` | Start containers |
| `make up-build` | Rebuild images, then start |
| `make down` | Stop containers |
| `make clean` | Stop + wipe volumes |
| `make ps` | Container status |
| `make logs` | Tail backend logs |
| `make logs-all` | Tail every container |
| `make logs-calfire` | Tail CAL FIRE producer |
| `make logs-noaa` | Tail NOAA producer |
| `make logs-recommendation` | Tail recommendation agent |
| `make logs-mcp` | Tail MCP server |
| `make stream-fire` | Live Kafka topic: `firelink.fire` |
| `make stream-weather` | Live Kafka topic: `firelink.weather` |
| `make stream-recommendations` | Live Kafka topic: `firelink.recommendations` |
| `make topics` | List Kafka topics |
| `make context` | Pretty-print `/context/latest` |
| `make health` | Hit `/health` from inside container |
| `make ingest` | Load `docs/*.pdf` → Pinecone (one-shot) |
| `make sms` | Interactive SMS simulator (Help Agent) |
| `make sms-replay` | Batch replay `test/sms_test_cases.json` |
| `make test` | Smoke test: containers + REST + Help Agent |
| `make dev-venv` | Local dev: create `backend/.venv` + install requirements |
| `make dev-infra` | Local dev: start zookeeper + kafka only (host listener `:29092`) |
| `make dev-down` | Local dev: stop Docker containers |
| `make dev-api` | Local dev: FastAPI via `uvicorn --reload` (`:8000`) |
| `make dev-calfire` | Local dev: CAL FIRE producer on host |
| `make dev-noaa` | Local dev: NOAA producer on host |
| `make dev-recommendation` | Local dev: recommendation agent on host |
| `make frontend-install` | `npm install` in frontend |
| `make frontend-dev` | `npm run dev` in frontend |
| `make frontend-build` | Production build |
| `make frontend-start` | Production server |
| `make frontend-lint` | ESLint |

---

## Troubleshooting

**Backend container restart-looping**
- `make logs` — check stack trace
- Most common: missing env key in `backend/.env`
- Kafka not yet healthy — wait 30s and retry

**Recommendation agent restarting**
- Needs `OPENAI_API_KEY`
- `make logs-recommendation` to confirm

**Frontend can't reach backend**
- Confirm backend up: `curl http://localhost:8000/health`
- Check `NEXT_PUBLIC_API_URL` — restart `npm run dev` after changing
- Browser devtools → Network tab → check actual URL hit

**CORS error in browser**
- Backend `CORS_ORIGINS` env defaults to `http://localhost:3000`
- If frontend on different origin, edit `backend/docker-compose.yml` `CORS_ORIGINS`, then `make down && make up`

**`make ingest` fails**
- Pinecone index must exist with name matching `PINECONE_INDEX_NAME`
- Create at https://app.pinecone.io with embedding dimension matching the OpenAI embedding model used

**Port already in use**
- 8000, 8001, 9092, 3000 must be free
- `lsof -i :8000` to find offender
- Kill with `kill <pid>` or change port mapping in `docker-compose.yml`

**Nothing in Kafka topics**
- Producers seed from `app/data/*.json` on startup
- `make logs-calfire` / `make logs-noaa` to confirm replay
- `make clean && make up-build` to fully reset

**SQLite stale data**
- `make clean` (wipes volume) then `make up-build`
- Local dev: delete `backend/app/data/firelink.db` and restart the producers

**Host process can't reach Kafka (local dev)**
- `make dev-infra` must be up — `docker compose ps` should show kafka healthy
- Host processes must use `localhost:29092` (`KAFKA_BOOTSTRAP` in `backend/.env`) — `kafka:9092` and `localhost:9092` are container-only

**`unable to open database file` (local dev)**
- `DATABASE_URL` is CWD-relative — run `make dev-*` targets from `backend/`, not the repo root

---

## Production build (frontend)

```bash
cd frontend
npm run build
npm run start    # http://localhost:3000
```

Set `NEXT_PUBLIC_API_URL` in environment before `npm run build` — Next.js bakes public env at build time.

---

## Security checklist before pushing to git

- [ ] `backend/.env` is in `.gitignore` (already is — `git check-ignore backend/.env` should print the path)
- [ ] No keys hardcoded in source (`git grep -E 'sk-(proj|ant)-|pcsk-'` returns nothing)
- [ ] Rotate any key that ever touched a public commit, no exceptions
- [ ] `ssh-key-2026-05-09.key.pub` is a public key — safe to commit, but private counterpart must never be

---

## Component docs

- `backend/README.md` — service-by-service architecture, Kafka topics, agent internals
- `frontend/README.md` — Next.js app routes, dashboard wiring
- `docs/architecture-breakdown.md` — full-stack overview (backend endpoints/agents + frontend routes/structure)
- `docs/streaming-pipeline.md` — real-time data pipeline: data sources, Kafka internals, context retrieval
- `backend/docs/` — wildfire knowledge PDFs ingested into Pinecone
