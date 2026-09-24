# FireLink - A SMS-first wildfire communication and community-intelligence platform
Firelink explores how communities can access guidance for wildfire coordination when connectivity, device access, or emergency information systems are constrained. Our project combines a simulated SMS experience, a web dashboard, replayed wildfire and weather records, retrieval-assisted guidance, and an event-streaming backend. Out goal is to provide guidance and foster community understanding during urgent situations. 

## Project Background Information
FireLink began at the 2026 United Nations–UC San Diego(UCSD) Reboot the Earth Hackathon, where the original project received first place. It is now being developed from a hackathon prototype into a maintainable open-source MVP and systems-research platform.

## Team Overview

This is a **24-hour hackathon MVP** for a wildfire evacuation intelligence platform. The project is split into **Backend** and **Frontend** teams.

Note: This is an ongoing project development. Currently, it replays historical and stimuted data, does not contact emergency services, and must not be relied upon for evacuation orders or immediate safety decisions. 

## Project Objectives
- Provide a low-barrier, SMS-oriented interface for wildfire information.
- Present concise, localized, and multilingual guidance.
- Preserve the source, timestamp, and simulation status of operational data.
- Continue operating in defined degraded modes when optional AI services fail.
- Explore resilient communication, distributed systems, local AI, and agent interoperability without making them requirements for the core MVP.
- Develop toward open-source and Digital Public Goods best practices.

# Getting Started

**Make sure both backend AND frontend are running for the app to work!**

### Requirements
- Docker Desktop with Docker Compose v2
- Node.js 20 or newer with npm
- Python 3.10 or newer for host-side utilities
- Make
### Configure the backend
Create backend/.env and provide the credentials required by the current hosted implementation:
```
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
PINECONE_API_KEY=
PINECONE_INDEX_NAME=
```
Note: Never commit .env or API credentials.

### Terminal 1: Start Backend

```bash
cd backend
make check
make up-build
```
Note: The first build may take several minutes while Docker downloads images and installs dependencies.

Backend ready: http://localhost:8000/docs

### Terminal 2: Start Frontend

```bash
cd firelink/frontend
npm install
npm start
```

Frontend ready: http://localhost:3000

---

## 🗂️ Project Structure

```
firelink/
├── README.md                       # Project overview and quick start
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI application entry point
│   │   ├── core/                   # Database and Kafka configuration
│   │   ├── data/                   # Replay, community and mock data
│   │   ├── models/                 # SQLAlchemy database models
│   │   ├── schemas/                # Pydantic request and response models
│   │   ├── repository/             # Database access layer
│   │   ├── routes/                 # REST and simulated-SMS endpoints
│   │   ├── services/
│   │   │   ├── agents/             # Help and recommendation agents
│   │   │   ├── knowledge/          # RAG ingestion and retrieval
│   │   │   ├── producers/          # Fire and weather Kafka producers
│   │   │   ├── context_service.py  # Kafka context retrieval
│   │   │   ├── community_service.py
│   │   │   └── dispatch_service.py # Mock dispatch behavior
│   │   ├── mcp_server.py           # Experimental MCP interface
│   │   ├── run_agent.py
│   │   └── run_producer.py
│   ├── docs/                       # Preparedness documents for RAG
│   ├── test/                       # Smoke test and SMS CLI
│   ├── docker-compose.yml          # Local service orchestration
│   ├── Dockerfile
│   ├── Dockerfile.mcp
│   ├── Makefile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/                    # Next.js routes and ZIP dashboards
│   │   ├── components/             # Dashboard, fire, resource and chat UI
│   │   ├── lib/                    # API client, types and data adapters
│   │   └── data/                   # Frontend demonstration data
│   ├── package.json
│   └── README.md
└── docs/
    ├── architecture-breakdown.md   # Current full-stack architecture
    └── streaming-pipeline.md       # Kafka and data-flow documentation
```

---

## 🔌 API Endpoints (Quick Reference)

| Method  | Endpoint           | Purpose                    |
| ------- | ------------------ | -------------------------- |
| `GET`   | `/health`          | Health check               |
| `POST`  | `/reports`         | Create incident report     |
| `GET`   | `/reports`         | List all reports           |
| `GET`   | `/reports/{id}`    | Get single report          |
| `PATCH` | `/reports/{id}`    | Update report (resolve)    |
| `GET`   | `/layers/shelters` | Get evacuation shelters    |
| `GET`   | `/layers/fire`     | Get fire reports (GeoJSON) |
| `GET`   | `/risk/grid`       | Get risk heatmap data      |
| `POST`  | `/route`           | Compute evacuation route   |

**Full API Docs**: http://localhost:8000/docs

---

## 📊 Database Schema

### Report Table

```python
Report(
    id: int,
    report_type: "fire_seen" | "blocked_road" | "heavy_smoke" | "assistance_needed" | "power_outage",
    latitude: float,
    longitude: float,
    note: str (optional),
    created_at: datetime,
    is_resolved: bool
)
```

### Shelter Table

```python
Shelter(
    id: int,
    name: str,
    latitude: float,
    longitude: float,
    capacity: int,
    description: str
)
```

---

## 🎯 Key Features & Implementation

### Risk Scoring Algorithm

Computes risk (0.0 to 1.0) based on proximity to:

- **Fires** (2km radius) - Weight: 1.0
- **Blocked Roads** (1.5km radius) - Weight: 0.8
- **Smoke** (1km radius) - Weight: 0.5

Uses **Haversine distance** formula for geographic calculations.

**Location**: `firelink/backend/app/services/risk_engine.py`

### Routing Algorithm (MVP)

Current: Mock routes between start → nearest shelter

Future improvements:

- Real OSM road networks (NetworkX/OSMnx)
- Dijkstra's algorithm for optimal paths
- Multi-shelter evacuation planning

**Location**: `firelink/backend/app/services/routing_engine.py`


## 🐛 Common Issues & Fixes

### Backend won't start

```
Error: Cannot find module 'app.main'
```

**Fix**: Make sure you're in `firelink/backend/` and venv is activated

### Frontend shows connection error

```
Cannot connect to backend. Is it running?
```

**Fix**: Start backend first (Terminal 1), wait 3 seconds, then refresh browser

### Database issues

```
Error: database is locked
```

**Fix**: Delete `firelink/backend/evaclink.db` and restart backend

### CORS errors in console

**Fix**: Backend CORS is pre-configured for `localhost:3000` and `localhost:5173`

---

## 📝 Seed Data

The database auto-seeds on first run with:

- **3 Shelters**: Highway 101, Santa Clara College, San Jose State
- **3 Fire Reports**: Simulated fire sightings with notes
- **3 Mock Reports**: Blocked roads, smoke, assistance requests

**Edit seed data**: `firelink/backend/seed/*.json`

---

## Project Roadmao

### For Backend Team

1. [ ] Define versioned event schemas with source, timestamp, freshness, verification, and simulation metadata
2. [ ] Build a persistent current-state service so user requests do not create Kafka consumers
3. [ ] Separate deterministic safety rules from AI explanation and translation
4. [ ] Add explicit degraded modes for unavailable or stale data, retrieval, and model services
5. [ ] Add unit, integration, contract, and failure tests with continuous integration
6. [ ] Evaluate Ollama and LocalAI behind a provider-independent interface
7. [ ] Integrate a real messaging provider only after the simulated workflow is safe and reproducible
8. [ ] Evaluate CoffeeAGNTCY/App SDK integration after the standalone core architecture is stable
9. [ ] Prepare licensing, ownership, privacy, documentation, and do-no-harm materials for Digital Public Goods assessment

---

## 💡 Tips for Success

✅ **DO**:

- Keep frontend and backend running simultaneously
- Test API changes in Swagger UI first
- Commit small, focused changes
- Document new endpoints in README
- Communicate between teams before major changes

❌ **DON'T**:

- Forget to activate venv before running backend
- Edit backend files without understanding impact on frontend
- Skip testing changes in API docs
- Leave console errors unresolved
- Commit without testing

---

## 📚 Resources

- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **React Docs**: https://react.dev/
- **Leaflet Docs**: https://leafletjs.com/
- **Haversine Formula**: https://en.wikipedia.org/wiki/Haversine_formula
- **GeoJSON Spec**: https://geojson.org/

---

## 🎓 Architecture Diagram

```
┌─────────────────────────────────────┐
│     Browser (React App)              │
│  MapView | ReportForm | RoutePanel  │
└──────────────┬──────────────────────┘
               │ HTTP/REST/WebSocket
┌──────────────▼──────────────────────┐
│     FastAPI Backend                  │
│  ┌────────────┐  ┌────────────────┐ │
│  │  Routers   │  │  Services      │ │
│  │  (APIs)    │  │  (Logic)       │ │
│  └──────┬─────┘  └────────┬───────┘ │
└─────────┼──────────────────┼────────┘
          │                  │
┌─────────▼──────────────────▼────────┐
│     SQLite Database                  │
│  ┌─────────────┐  ┌──────────────┐  │
│  │  Reports    │  │  Shelters    │  │
│  └─────────────┘  └──────────────┘  │
└──────────────────────────────────────┘
```

---

## 📞 Questions?

Check the relevant README:

- **Backend issues**: See `firelink/backend/README.md`
- **Frontend issues**: See `firelink/frontend/README.md`
- **Overall project**: See `firelink/README.md`
