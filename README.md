# NAM v2 — Navigation Assistant of Mars (Google Earth for Mars)

**Full-stack Google Earth for Mars platform** delivering all phases of the
NAM v2 Complete Build Plan: a **React + TypeScript + Vite + Three.js** interactive
planetary client paired with a **FastAPI** backend (105 OpenAPI 3.1 endpoints,
24 JEV AI tools, SSE streaming, and real-time `/ws/events` + `/ws/presence` WebSockets).

| Build phase | Release gate | Scope | Gate test |
|---|---|---|---|
| 1 | `v2.0` — The Google Earth Core | 3D IAU Mars ellipsoid globe + 5 projections (3D, 2D Flat, N/S Polar, Columbus 2.5D), 1–10× terrain exaggeration, Mars24 sun & sol animator, landmark flyovers, split-screen layer compare, 2,055-feature USGS gazetteer search & location cards, 12-tool Mars Trek measurement suite (incl. binary STL) | `tests/test_phase1_gate.py` |
| 2 | `v2.1` — Street View + Walk View + Scientific Explorer | 20-layer science registry, cited discovery browser, 3-way landing-site compare, 360° rover panorama viewer + traverse walking + orbital inset + historical compare + Perseverance raw-image connector, Three.js First-Person Walk View (WASD + POV library + heading-matched photos), full scientific catalogs (orbiters, instruments, spectral targets, datasets, unavailable sources) | `tests/test_phase2_gate.py` |
| 3 | `v2.2` — JEV AI + Missions + Environment + Real-Time | 24 typed JEV tools, SSE chat drawer with inline tool trace & globe-control intents, explain-what-I-am-looking-at, A* 4-type mission planner + 2-opt optimize + route profile/radiation + KML/GeoJSON/CSV/share, RAD-anchored point & path radiation, MY34/SEP storm sim & evacuation drill, SWIM water ice, 12 scored shelters, 8-type spatial nodes, live presence & WebSockets | `tests/test_phase3_gate.py`–`test_phase5_gate.py` |
| 4 | `v2.3+` — Hardening, Deep Audit & Complete Build Plan | Mars24 solar geometry, antimeridian/polar-safe geodesy & filtering, atomic bookmarks, path radiation integration, landmark flyovers, scientific catalogs, planetary SIM rasters, and full interactive web client (`client/`) | `tests/test_technical_review_fixes.py`, `tests/test_deep_audit_fixes.py`, `tests/test_build_plan_upgrades.py` |

Current status: **118/118 pytest tests passing**, **26/26 self-test checks passing** (`scripts/selftest.py`), **36/36 14-category Build Plan inventory checks EXISTS** (`scripts/audit_inventory.py`), and TypeScript + Vite client production build green.

---

## Quickstart

```bash
./run.sh                       # venv + deps + seeds + client build + uvicorn on :8000
# Dev mode (live reload):
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
cd client && npm install && npm run dev   # Vite on :5173 proxying API & WS to :8000
```

Then open `http://localhost:8000/` (production build) or `http://localhost:5173/` (Vite dev), plus `/docs` (Swagger UI), `/openapi.json` (OpenAPI 3.1), and `/health`.

```bash
.venv/bin/python scripts/selftest.py         # 26-check end-to-end backend self-test
.venv/bin/python scripts/audit_inventory.py  # 14-category Build Plan inventory verification
.venv/bin/python -m pytest tests/ -q         # full 118-test regression & phase-gate suite
docker compose up --build                    # multi-stage container build (client + backend)
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
tests/                  five phase-gate suites + routing, spatial & JEV submission suites
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
NAM_TILE_TTL_HOURS, NAM_CTX_TILE_TEMPLATE, NAM_LLM_BASE_URL, NAM_LLM_MODEL,
NAM_API_KEY, NAM_CORS_ORIGINS`.

## Endpoint tour (87 OpenAPI paths)

- **Core geo**: `/search`, `/locations/{id}`, `/landing_sites`, `/bookmarks`,
  `/share`, `/elevation`, `/elevation/profile`, `/terrain/{patch,mesh,slope,hazard}`,
  `/imagery/ladder`, `/tiles/{layer}/{z}/{x}/{y}`, `/tiles/cache/invalidate`, `/connectors/status`,
  `/measure/{distance,path_distance,route_distance,profile,crater,area,slope,
  elevation_difference,solar,terrain_download,stl}`
- **Science & experience**: `/layers`, `/layers/compare`, `/discoveries`,
  `/sites`, `/sites/compare`, `/panoramas…`, `/traverses…`,
  `/imagery/linkage`, `/sites/{rover}/timeline`, `/walkview/{init,patch,pov,imagery}`
- **JEV**: `/jev/tools`, `/jev/chat` (SSE), `/jev/explain`, `/jev/benchmark`, `/jev/logs`
- **Operations**: `/missions…` (CRUD, route, optimize, kml, geojson, csv, compare),
  `/environment/{radiation,storms,storms/simulate,storm_response}`,
  `/water`, `/shelters`
- **Realtime**: `/nodes…`, `/presence…`, `/events/trigger`, `/events/history`,
  `WS /ws/events?since_id=`, `WS /ws/presence`

## The gate demo (backend equivalent)

Space-to-surface journey, all through the API:
`/search?q=Olympus Mons` → fly intent → `/measure/crater` on Jezero rims →
`/measure/profile` across the delta → `/measure/stl` of a 20 km Valles Marineris
patch → `/panoramas` into the Sol 911 Street View pose → `/walkview/init` at the
delta front → `/discoveries` for cited paleolake evidence → `/jev/chat`
("explain what I am looking at") → `simulate my34` → `storm_response` with
water-cache and shelter-pickup stops → storm alert over `/ws/events` in <1 s.
