## **APP ANALYSIS (Frontend + Backend)**

### What is Firelink?

Wildfire intelligence platform built as monorepo (backend + frontend in one) with Python/FastAPI streaming backend, Next.js dashboard frontend. Scenario is built around real 2025 Eaton fire in LA, with 199 real calfire updates + Open-Meteo weather observations replayed through Kafka.

### Overall Architecture (High-Level):
- Data(JSON) → Kafka Producers → Kafka Topics → FastAPI reads → AI Agents → REST API → Next.js dashboard (fetches from `/context` , `/sms` , and `/community` )

```mermaid
flowchart LR
    subgraph Data["Raw Data"]
        FJ[fire_incidents.json]
        WJ[weather_alerts.json]
    end

    subgraph Kafka["Kafka"]
        CP[calfire-producer]
        NP[noaa-producer]
        TF[(firelink.fire)]
        TW[(firelink.weather)]
        TR[(firelink.recommendations)]
    end

    subgraph Backend["FastAPI Backend & Agents"]
        CTX[context_service<br/>last 10 msgs / topic]
        RA[Recommendation Agent<br/>GPT-4o-mini · every 60s]
        HA[Help Agent<br/>LLM + RAG]
        API[REST API<br/>/context · /sms · /community · /agents]
    end

    RAG[(Pinecone<br/>RAG chunks)]
    MCP[MCP Server<br/>get_context · notify_dispatch]
    DASH[Next.js Dashboard<br/>fire · needs · community · resources · chat]

    FJ --> CP --> TF
    WJ --> NP --> TW
    TF --> CTX
    TW --> CTX
    CTX --> RA --> TR --> CTX
    CTX --> API
    CTX --> HA
    RAG --> HA
    HA --> API
    CTX --> MCP
    API --> DASH
```


### Backend
- Running `make up build` builds images and starts 7 docker containers
    1. firelink-backend: FastAPI server (port 8000) - CRUD + Help Agent + context
    2. firelink-recommendation-agent: uses the configured chat model (default OpenAI `gpt-4o-mini`) to emit a summarized advisory every minute (runs script `app.run_agent recommendation` )
    3. firelink-calfire-producer: replays `fire_incidents.json` → Kafka every 10s (runs script `app.run_producer.py calfire` )
    4. firelink-noaa-producer: replays `weather_alerts.json` → Kafka every 10s (runs script `app.run_producer.py noaa` )
    5. firelink-mcp-server: uses `Dockerfile.mcp`  (port 8001), runs FastMCP server exposing `get_context` amd `notify_dispatch`  tools
    6. firelink-kafka: broker (depends on zookeeper) with 3 topics (firelink.fire, firelink.weather, firelink.recommendations)
    7. firelink-zookeeper: kafka coordinator

**FastAPI breakdown (see `localhost:8000/docs` for endpoint docs)**
- **/health →** basic liveness check, returns `{status, service}`
- **/community/{zip}** → calls `get_community` which essentially just loads, parses, and returns json from `data/community/...` which contains synthetic data on zip, stats, households (anonymous ids), events, and resources
- **/context/latest →** calls `get_latest_context` which fetches last 10 messages per topic from Kafka to build live snapshot
- **/fire-incidents/… →** located within `app/routes/fire_incidents.py` , full CRUD (`GET /` paginated list, `GET /{id}`, `POST /`, `PATCH /{id}`, `DELETE /{id}`) via `FireIncidentRepository`, backed by the SQLite/SQLAlchemy DB (`core/database.py`)
- **/weather-alerts/… →** located within `app/routes/weather_alerts.py` , same CRUD shape as fire-incidents, via `WeatherAlertRepository`
- **/agents/recommendations/latest (`app/routes/agents/recommendation.py` ) →** calls `get_latest_recommendation` which reads the most recent message off the `firelink.recommendations` Kafka topic (published every 60s by the Recommendation Agent) and returns the `{advisory, reasoning, risk_level}` JSON, 404 if nothing's been published yet
- **/sms/inbound →** calls `handle_sms` (from help agent) passing in user phone and message, returns an SMS-shaped reply; 503 if RAG/user data files are missing, 502 on agent failure

**Agents**
- Base Agent (`services/agents/base_agent.py`) → calls the configured model (default `gpt-4o-mini`, overridable via `RECOMMENDATION_MODEL`) through the shared provider layer (`services/llm.py`), passes in context (JSON snapshot of latest fire incidents / weather conditions), and returns JSON. Also has connect_producer method which creates the kafka producer
- Help Agent (`services/agents/help_agent.py`) → single LLM call (default `gpt-4o`, overridable via `HELP_MODEL`) which fuses 6 context sources into one SMS-style reply, always in the user's language:
    - User profile (`mock_users.json`, via `knowledge/rag_query.py`)
    - Live fire + weather context from Kafka (`context_service.get_latest_context`)
    - Latest advisory from Kafka recommendations topic (`context_service.get_latest_recommendation`)
    - RAG chunks from Pinecone (top-K, via `knowledge/rag_query.retrieve_chunks`)
    - Open shelter list (`app/data/shelters.json`)
    - System prompt instructing calm, brief, 1–3 sentence plain-text replies
    - Exposes `notify_dispatch` as a function tool call — if the model detects active life-threatening danger it calls the tool instead of replying with text, which hits `services/dispatch_service.py` (mock 911 dispatch)
- Recommendation Agent (`services/agents/recommendation_agent.py) → subclasses BaseAgent, calling `get_latest_context` (from Kafka weather/fire topics), passing to LLM, and passing the JSON recommendation to the Kafka firelink.recommendations topic every **60s**

**Local / open-source models (provider layer)**
- All chat-LLM calls go through `services/llm.py` — one OpenAI SDK client pointed at hosted OpenAI (default) or any OpenAI-compatible server via `OPENAI_BASE_URL` (Ollama, vLLM, LM Studio, llama.cpp server, LocalAI)
- Config (see `backend/.env.example`): `OPENAI_BASE_URL`, `HELP_MODEL` (default `gpt-4o`), `RECOMMENDATION_MODEL` (default `gpt-4o-mini`). Embeddings stay on OpenAI (`text-embedding-3-small`, Pinecone 1536-dim index) — `OPENAI_API_KEY` remains required
- To run the chat models fully local with Ollama:
    1. `ollama pull qwen3.5:27b` — recommended: solid function-calling + JSON output. Avoid `deepseek-r1` for the Help Agent (reasoning models are not tool-trained and emit think traces, bad for SMS latency); `llama3.2:3b` / `granite4.1:3b` work for smoke tests but are weaker at tool reliability
    2. Set `OPENAI_BASE_URL=http://localhost:11434/v1` (hybrid dev-mode) or `http://host.docker.internal:11434/v1` (full docker-compose — `extra_hosts` is already wired in `docker-compose.yml`), and point `HELP_MODEL` / `RECOMMENDATION_MODEL` at the Ollama model name
    3. Local servers ignore API keys; a placeholder is used automatically when `OPENAI_API_KEY` is unset

**Knowledge / RAG (`services/knowledge`)**
- `ingest.py` → chunks and embeds source docs (see `backend/docs/comprehensive_guide.pdf`, `redcross-wildfire-checklist.pdf`) into Pinecone
- `rag_query.py` → loads mock user profiles and retrieves top-K relevant chunks from Pinecone for the Help Agent's prompt

**MCP Server**
- exposes `get_context` and `notify_dispatch` as MCP tools (streamable http on port 8001) so external client can pull context
- Uses FastMCP
- Note when running locally, we use stdio (since everything runs on same machine). HTTP+SSE is considered legacy now. **Streamable HTTP** is the new standard. See these [docs](https://gofastmcp.com/v2/clients/transports) for more info.

### Frontend (Next.js, App Router + TypeScript + Tailwind)
- Runs on port 3000 (`npm run dev`)
- Two top-level routes:
    - `/` → static marketing/landing page, links into the demo dashboard (`/dashboard/91001`)
    - `/dashboard/[zip]/...` → the actual product, scoped per ZIP code
- `dashboard/[zip]/layout.tsx` wraps every dashboard page with `DashboardHeader`, `DashboardBottomNav` (tab bar: Fire / Needs / Community / Resources / Chat), and `DashboardAutoRefresh` (polling refresh)
- `dashboard/[zip]/page.tsx` just redirects to `/dashboard/[zip]/fire` — there's no dashboard "index", Fire is the default tab
- Tabs (each a route segment under `dashboard/[zip]/`):
    - **fire/** → live fire conditions, alert timeline, growth chart (components in `components/fire/`)
    - **needs/** → aggregated community needs (`NeedsNowSection`, `NeedsTable`, filterable via `NeedsFilterClient`)
    - **households/** → anonymized household list/cards (`HouseholdsListClient`, `HouseholdCard`) — no names/phone numbers/addresses by design
    - **resources/** → shelters, emergency actions, nearby resources, SMS command reference, safety disclaimer (components in `components/resources/`)
    - **chat/** → `ChatClient`, an SMS-style chat UI that calls `POST /sms/inbound` for replies and polls `GET /agents/recommendations/latest` for the current advisory banner
- Data layer (`src/lib/`):
    - `api.ts` → thin fetch wrapper (`apiGet`/`apiPost`) pointed at `NEXT_PUBLIC_API_URL` (defaults to `localhost:8000`), with Next.js ISR revalidation (30s default) on GETs and no-store on POSTs
    - `data.ts` → `getCommunityData(zip)` calls `GET /community/{zip}` and **falls back to bundled `mockData.ts`** if the backend 404s or is unreachable, so the dashboard never shows an empty state during a demo
    - `types.ts` → shared privacy-safe types (`CommunityDashboardData`, `AnonymousHousehold`, `NeedItem`, `ResourceItem`, etc.) mirroring the backend's `/community/{zip}` response shape
    - `mockData.ts` → fallback/demo data keyed by ZIP
    - `dashboardFilters.ts` / `dashboardSemantic.ts` / `semanticStyles.ts` / `fireConditionsAdapter.ts` → presentation-layer helpers (filtering, status-to-style mapping, adapting raw fire records for the UI)
- Notable libs: `leaflet` / `react-leaflet` (map on `LiveEatonMap`), `recharts` (fire growth chart)