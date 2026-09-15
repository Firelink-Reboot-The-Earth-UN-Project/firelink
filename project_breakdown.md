Create a clean system architecture diagram for a wildfire evacuation intelligence platform called EvacLink.

Project overview:
EvacLink is a community-powered wildfire evacuation map that helps residents report local hazards and urgent needs, while giving responders a shared intelligence dashboard for safer evacuation routing and triage. The MVP focuses on live map reporting, hazard-aware route calculation, and responder visibility. Offline mode is a future stretch feature.

Main user flows:
1. Resident opens the web app map.
2. Resident submits a report such as blocked road, fire nearby, heavy smoke, need evacuation help, or power/signal outage.
3. Frontend sends report to FastAPI backend.
4. Backend stores report in the database.
5. Backend updates the hazard layer and routing graph.
6. Routing engine calculates safer evacuation routes based on roads, shelters, fire/hazard data, and community reports.
7. Responder dashboard receives updated reports, route changes, and priority alerts.

Architecture layout:
Top layer: Frontend / User Interface
- React or Next.js web app
- Interactive map UI using Leaflet or Mapbox
- Resident view: submit reports, view route, view shelters
- Responder dashboard: verify reports, view hazards, monitor priority areas

Middle layer: Python FastAPI backend
- Report API: receives community reports
- Routing API: returns safest evacuation route
- Data Layer API: serves roads, shelters, fire points, and hazard layers
- WebSocket or polling updates for live dashboard refresh
- Risk scoring module: ranks hazards and assistance requests

Routing and intelligence layer:
- Road graph built from OpenStreetMap or local road data
- Routing engine using NetworkX or OSMnx
- Route cost function:
  - blocked road = remove or heavily penalize edge
  - fire nearby = high route penalty
  - heavy smoke = medium route penalty
  - verified responder report = higher confidence
  - repeated community reports = higher confidence

Database layer:
- PostgreSQL/PostGIS preferred
- SQLite acceptable for hackathon MVP
- Tables:
  - reports
  - road_edges
  - shelters
  - fire_points
  - hazard_zones
  - routes
  - users/devices optional

External data layer:
- Base map
- OpenStreetMap roads
- Shelter / safe destination points
- Fire points or fire perimeter data
- Optional: wind direction, evacuation zones, SDG&E resource centers, USGS terrain, USFS wildfire data

Visual design:
Use a modern clean diagram style with boxes and arrows.
Show data flowing from users to frontend, then to FastAPI backend, then to database and routing engine, then back to the frontend.
Use color-coded sections:
- Blue for frontend
- Green for backend
- Orange for routing/intelligence
- Purple for database
- Gray for external data sources
Include small icons for residents, firefighters/responders, map, database, roads, fire, shelters, and routing.
Make it suitable for a hackathon presentation slide.