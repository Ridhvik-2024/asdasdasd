# NAM v2 Backend — Navigation Assistant of Mars

**Google Earth for Mars, backend-only build.** One FastAPI monorepo delivering the
entire v2 target specification in five sequential, cumulative build phases, each
closing at a verified release gate:

| Build phase | Release gate | Scope | Gate test |
|---|---|---|---|
| 1 | `v2.0.0-backend` — The Google Earth Core | terrain engine, imagery ladder + tile proxy, full-gazetteer search + location cards, 12-tool measurement suite (incl. 3D-print STL), integrity layer | `tests/test_phase1_gate.py` |
| 2 | `v2.1.0-backend` — Street View + Scientific Explorer | science layer registry, cited discovery browser, landing-site compare, rover panoramas/traverses/orbital-ground linkage, Walk View (mesh patches + POV library) | `tests/test_phase2_gate.py` |
| 3 | `v2.2.0-backend-ai` — JEV intelligent explorer | 24 typed tools, deterministic intent router, OpenAI-compatible LLM adapter (llama.cpp), retrieval, SSE chat with tool trace, explain-view, benchmark | `tests/test_phase3_gate.py` |
| 4 | `v2.2.1-backend-missions` — Missions + environment | A* routing (3 presets), mission suite (route/area/evacuation/survey, KML, optimize, compare), radiation + SEP/dust storms (MY34), storm-response planner, water/shelter discovery | `tests/test_phase4_gate.py` |
| 5 | `v2.2.2-backend-live` — Real-time + closing | nodes (8 types), presence simulation, WebSocket channels (`/ws/events`, `/ws/presence`) with bounded rates, storm drill, integrity audit | `tests/test_phase5_gate.py` |

Current status: **48/48 gate tests passing** (`python -m pytest tests/ -q`).

---

## Quickstart

```bash
./run.sh                       # venv + deps + seeds + uvicorn on :8000
# or manually:
pip install -r requirements.txt
python scripts/make_seeds.py && python scripts/make_demo_grid.py
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then: `http://localhost:8000/docs` (Swagger UI), `/openapi.json` (OpenAPI 3.1),
`/health`.

```bash
python scripts/selftest.py     # 25-check verified self-test sweep, exit code honest
python -m pytest tests/ -q     # the five phase gates
docker compose up --build      # containerized run (optional PostGIS service included)
```

## Architecture

```
app/
  main.py               FastAPI assembly + lifespan realtime loops
  config.py             env-driven configuration
  integrity.py          provenance builder, [SIM] labelling, honest degradation
  mars.py               IAU ellipsoid geodesy, subsolar/solar geometry
  terrain.py            global DEM engine: sampling, slope, profiles, patches,
                        meshes, hazard, crater scaling, binary STL export
  db.py                 SQLite DAO (reference laptop); PostGIS schema in infra/
  seeds.py              seed loader, full-gazetteer fuzzy search, region context
  routing.py            terrain-aware A* (balanced / terrain / speed presets)
  environment.py        RAD-anchored radiation, SEP + dust sims, storm response
  resources.py          SWIM-consistent water logic + shelter scoring
  missions.py           mission objects, stops, KML, optimize, compare
  nodes.py / presence.py  8-type spatial nodes; crew/rover/habitat presence [SIM]
  events.py             bounded-rate broadcast hub for the WebSocket channels
  connectors/base.py    discover / fetch / cache / attribute / degrade
  jev/
    tools.py            the 24-tool registry, JSON-schema validated, fail-closed
    router.py           deterministic intent router (always-available fallback)
    llm.py              llama.cpp / OpenAI-compatible adapter (optional)
    retrieval.py        TF-IDR retrieval over the cited knowledge base
  routers/              health, gazetteer, terrain, imagery, measurements,
                        science, panoramas, walkview, jev, missions,
                        environment, resources, nodes, ws
data/seeds/             curated JSON seeds + 0.5-deg demo DEM (npz)
data/usgs_gazetteer_full.json   2,055 IAU-approved features (official KMZ)
scripts/                seed/DEM generators, gazetteer connector, selftest
tests/                  the five phase-gate suites
```

## The 24 JEV tools

`search_planetary_location, get_current_map_context, search_nasa_datasets,
get_location_observations, activate_map_layer, compare_geological_layers,
get_elevation_profile, analyze_terrain, identify_hazards,
find_scientific_targets, create_mission, generate_route, optimize_route,
add_waypoint, explain_route, export_mission, add_node, add_stop, plan_area,
plan_storm_response, find_water, find_shelter, assess_radiation, simulate_storm`

Every call is JSON-schema validated and **fails closed** on malformed arguments.
The deterministic intent router answers the review's eight canonical commands
("take me to Olympus Mons", "compare Jezero and Gale crater", "explain what I am
looking at", ...) and emits globe-control intents (`fly_to`, `activate_layer`)
for the client. Set `NAM_LLM_BASE_URL` to a llama.cpp OpenAI-compatible server
(3B-class GGUF Q4_K_M, CPU, ~3 GB RAM) to swap the planner/composer to the
local model behind the identical SSE protocol.

## Integrity rules (enforced at the service layer)

- Every scientific value carries **provenance** (source / mission / instrument /
  resolution / date / url).
- Unavailable services **degrade honestly** with documented access paths —
  the tile proxy returns documented 503s, never fake imagery.
- All simulations and estimates carry the **[SIM]** label and are advisory
  (terrain grid, dose models, storm scenarios, presence feed, shelter scores).
- The AI **cites tool outputs or abstains** — verified by an abstention test.
- Coordinates: latitude degrees (south negative), **longitude EAST 0-360**.

### Data honesty notes

- The shipped DEM is a **synthetic 0.5-deg approximation** built from published
  landmark geometry (Olympus ~21 km, Hellas ~-7.5 km, Valles Marineris trench,
  dichotomy). It is labelled `demo-synthetic-grid [SIM]` everywhere; the
  production swap is MOLA MEGDR 4 ppd (463 m/cell) plus HiRISE DTMs.
- Sub-grid relief is deterministic procedural detail, labelled [SIM].
- The gazetteer is **real**: `scripts/fetch_usgs_gazetteer.py` downloads the
  official USGS/IAU center-points KMZ (2,055 approved Mars features) with
  approval dates and per-feature URLs; the curated 58-feature seed covers
  landmark landmarks offline.
- Panorama records point to NASA/JPL-published galleries with credits; asset
  IDs are marked for verification at connector time rather than invented.
- Discovery cards cite real publications (Science, Nature Geoscience, JGR) or
  NASA mission pages; URLs are restricted to a domain allow-list in the audit.

## Configuration

See `.env.example`: `NAM_PORT, NAM_DATA_DIR, NAM_DB_PATH, NAM_ALLOW_UPSTREAM,
NAM_TILE_TTL_HOURS, NAM_CTX_TILE_TEMPLATE, NAM_LLM_BASE_URL, NAM_LLM_MODEL`.

## Endpoint tour (≈95 routes)

- **Core geo**: `/search`, `/locations/{id}`, `/landing_sites`, `/bookmarks`,
  `/share`, `/elevation`, `/elevation/profile`, `/terrain/{patch,mesh,slope,hazard}`,
  `/imagery/ladder`, `/tiles/{layer}/{z}/{x}/{y}`, `/connectors/status`,
  `/measure/{distance,path_distance,route_distance,profile,crater,area,slope,
  elevation_difference,solar,terrain_download,stl}`
- **Science & experience**: `/layers`, `/layers/compare`, `/discoveries`,
  `/sites`, `/sites/compare`, `/panoramas…`, `/traverses…`,
  `/imagery/linkage`, `/sites/{rover}/timeline`, `/walkview/{init,patch,pov,imagery}`
- **JEV**: `/jev/tools`, `/jev/chat` (SSE), `/jev/explain`, `/jev/benchmark`, `/jev/logs`
- **Operations**: `/missions…` (CRUD, route, optimize, kml, compare),
  `/environment/{radiation,storms,storms/simulate,storm_response}`,
  `/water`, `/shelters`
- **Realtime**: `/nodes…`, `/presence…`, `/events/trigger`,
  `WS /ws/events`, `WS /ws/presence`

## The gate demo (backend equivalent)

Space-to-surface journey, all through the API:
`/search?q=Olympus Mons` → fly intent → `/measure/crater` on Jezero rims →
`/measure/profile` across the delta → `/measure/stl` of a 20 km Valles Marineris
patch → `/panoramas` into the Sol 911 Street View pose → `/walkview/init` at the
delta front → `/discoveries` for cited paleolake evidence → `/jev/chat`
("explain what I am looking at") → `simulate my34` → `storm_response` with
water-cache and shelter-pickup stops → storm alert over `/ws/events` in <1 s.
