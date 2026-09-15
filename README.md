# FireLink - Wildfire Evacuation Intelligence Platform

## 🚨 Quick Start (5 minutes)

**Make sure both backend AND frontend are running for the app to work!**

### Terminal 1: Start Backend

```bash
cd firelink/backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

✅ Backend ready: http://localhost:8000/docs

### Terminal 2: Start Frontend

```bash
cd firelink/frontend
npm install
npm start
```

✅ Frontend ready: http://localhost:3000

---

## 📋 Team Overview

This is a **24-hour hackathon MVP** for a wildfire evacuation intelligence platform. The project is split into **Backend** and **Frontend** teams.

### What is FireLink?

FireLink helps communities respond to wildfires by:

- **Real-time incident reporting** - Users report fires, blocked roads, smoke, etc.
- **Risk scoring** - Computes evacuation danger based on hazard proximity
- **Smart routing** - Calculates safest evacuation routes to shelters
- **Interactive visualization** - Shows all hazards and routes on a live map

---

## 👥 Team Structure

### 🔧 Backend Team (Python/FastAPI)

**Focus**: API endpoints, risk engine, routing logic, database

**Key Files**:

- `firelink/backend/app/main.py` - Main API app
- `firelink/backend/app/services/risk_engine.py` - Risk scoring algorithm
- `firelink/backend/app/services/routing_engine.py` - Route computation
- `firelink/backend/app/routers/` - API endpoints

**Responsibilities**:

- Implement risk scoring algorithm improvements
- Add real OSM routing (replace mock routes)
- Add WebSocket support for live updates
- Connect to real fire/hazard data sources
- Performance optimization

**API Docs**: http://localhost:8000/docs (Swagger UI)

### 🎨 Frontend Team (React/TypeScript)

**Focus**: UI/UX, map visualization, user interactions

**Key Files**:

- `firelink/frontend/src/components/` - React components
- `firelink/frontend/src/api/client.ts` - Backend communication
- `firelink/frontend/src/App.tsx` - Main app logic

**Responsibilities**:

- Improve map styling and interactivity
- Add animations and transitions
- Enhance form UX and validation
- Add real-time updates with WebSockets
- Responsive design for mobile
- Accessibility improvements

---

## 🗂️ Project Structure

```
firelink/
├── README.md                 ← Main project guide
├── .gitignore
├── backend/                  ← Python/FastAPI backend
│   ├── README.md            ← Backend setup & API docs
│   ├── requirements.txt      ← Python dependencies
│   └── app/
│       ├── main.py          ← FastAPI app
│       ├── models.py        ← Database models
│       ├── schemas.py       ← Pydantic schemas
│       ├── database.py      ← DB configuration
│       ├── routers/         ← API endpoints
│       │   ├── reports.py
│       │   ├── routing.py
│       │   ├── risk.py
│       │   └── layers.py
│       ├── services/        ← Business logic
│       │   ├── risk_engine.py
│       │   ├── routing_engine.py
│       │   └── data_loader.py
│       └── seed/            ← Initial data
│           ├── shelters.json
│           ├── fire_points.json
│           └── mock_reports.json
└── frontend/                 ← React/TypeScript frontend
    ├── README.md            ← Frontend setup & guide
    ├── package.json         ← Node dependencies
    ├── public/
    │   └── index.html
    └── src/
        ├── App.tsx          ← Main component
        ├── components/      ← React components
        ├── api/             ← Backend client
        └── types/           ← TypeScript types
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

### Frontend Map

Built with **Leaflet.js** displaying:

- Shelter markers (blue)
- Incident reports (colored by type)
- Risk heatmap (red overlay)
- Evacuation routes (green line)
- User's selected location (green)

**Location**: `firelink/frontend/src/components/MapView.tsx`

---

## 🔄 Development Workflow

### 1. Backend Development

```bash
cd firelink/backend
source venv/bin/activate
python -m uvicorn app.main:app --reload
```

- Edit files in `app/`
- Server auto-reloads on changes
- Check http://localhost:8000/docs for API testing

### 2. Frontend Development

```bash
cd firelink/frontend
npm start
```

- Edit files in `src/`
- Browser auto-reloads on changes
- Check console for errors

### 3. Testing Changes

1. Backend makes changes → test in Swagger UI
2. Frontend makes changes → see live in browser
3. Both communicate via HTTP → check network tab

---

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

## 🚀 Next Steps

### For Backend Team

1. [ ] Improve risk scoring algorithm
2. [ ] Add NetworkX/OSMnx for real routing
3. [ ] Add WebSocket support for live updates
4. [ ] Integrate real fire data (USGS/CalFire API)
5. [ ] Add authentication & user roles
6. [ ] Database indexing & optimization

### For Frontend Team

1. [ ] Enhance map styling & markers
2. [ ] Add animations & transitions
3. [ ] Improve form validation & UX
4. [ ] Add WebSocket integration
5. [ ] Responsive mobile design
6. [ ] Dark mode support

### For DevOps

1. [ ] Docker setup (backend + frontend)
2. [ ] CI/CD pipeline (GitHub Actions)
3. [ ] Deployment (AWS/Azure/Heroku)
4. [ ] Environment configuration
5. [ ] Database migration scripts

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

---

**Built for emergency response. Let's save lives! 🚀**
