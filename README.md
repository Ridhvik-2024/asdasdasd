# NAM — Navigation Assistance for Mars

NAM is a Mars atlas with a FastAPI backend. The **only active interface** is the home page and Cesium atlas from `NAM (1).zip`, extended with backend-powered field tools in matching atlas panels. The app is served as a single site: browser requests for the API use the same origin as the frontend.

> **Important:** NAM is an exploration and demonstration application, not a navigation, engineering, medical, or mission-safety system. Terrain, routing, environmental models, shelter scores, and simulated presence are advisory **[SIM]** data.

## Contents

- [Get started](#get-started)
- [Using the atlas](#using-the-atlas)
- [What is connected](#what-is-connected)
- [Configuration](#configuration)
- [Data, imagery, and scientific limitations](#data-imagery-and-scientific-limitations)
- [Architecture and API](#architecture-and-api)
- [Deployment and security](#deployment-and-security)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)

## Get started

### Requirements

- Python 3.10+ with `venv` and pip.
- Node.js 22+ and npm (for the frontend build).
- A browser with WebGL. Network access is needed to install dependencies and to use external imagery and fonts.

From the repository root:

```bash
./run.sh
```

The script creates `.venv`, installs Python dependencies, installs frontend dependencies with `npm ci`, builds the atlas, and starts FastAPI on port 8000. Open **http://localhost:8000/**. The first build copies Cesium's runtime to `client/public/cesium/` and bundles the frontend into `client/dist/`; both directories are generated and ignored by Git.

To stop the server, press `Ctrl+C`. By default the SQLite database is stored at `data/nam.db`, which is ignored by Git and persists between launches.

### Manual start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd client
npm ci
npm run build
cd ..
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

To use a different port, set `NAM_PORT` before running `./run.sh`. When running Uvicorn directly, pass `--port` yourself.

### Development mode

Start the backend in one terminal:

```bash
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Then start Vite in a second terminal:

```bash
cd client
npm ci
npm run dev
```

Open **http://localhost:5173/**. Vite proxies API and WebSocket requests to the backend. Set `NAM_BACKEND_URL` in the Vite process if the backend is elsewhere; it is a server-side proxy target, not a browser URL.

### Docker

```bash
docker compose up --build
```

Open **http://localhost:8000/**. Compose persists the SQLite data directory with a bind mount. The Compose file also defines an optional PostGIS service; the application still uses SQLite by default and does not automatically switch to PostGIS. Use `docker compose up --build backend` to start only the application. The supplied credentials for the optional database are local-development defaults, not production credentials.

## Using the atlas

1. Select **Enter the Atlas** or the planet on the landing page. Drag the globe to rotate; scroll the mouse wheel or use trackpad pinch to zoom. The **+ / −** buttons also zoom. You can move as close as 250 m above the ellipsoid, but magnification does not add detail beyond the resolution of the selected imagery. Cesium uses the Mars ellipsoid for the camera projection as well as the globe.
2. Use the top-right **Search** icon to find names in the backend gazetteer or enter `latitude, longitude` (for example, `18.4, 77.7`). Choose a result to fly there. The existing **Places** panel offers featured landmarks.
3. Click the surface to inspect a point. The inspector displays its coordinates and backend elevation/slope estimates [SIM]. Use **Save bookmark** to store it in the backend database.
4. Use **Plan a traverse** on the left rail and click points on Mars. Right-click to finish; the panel offers a local GeoJSON sketch export. The sketch is an approximate surface route, not a safety assessment.
5. Open **Science & mission tools** on the left rail for the backend-powered tools below. They are part of this same atlas, not a separate application. Select a surface point or create a traverse first when a tool asks for one.
6. The original NAM layer manager, Mars Trek data catalogue, custom tile service input, map image export, and map overview controls remain available.

## What is connected

| Atlas tool | Backend functionality exposed in this UI |
| --- | --- |
| Search & inspector | Search the bundled USGS/mission catalogue or enter coordinates. Choose a suggestion to mark and center the catalogue point; the marker is not a feature outline. Use `/` as a search shortcut. The inspector includes simulated terrain estimates and saved bookmarks. |
| Measurements | Sketch distance, elevation profile, crater diameter estimate, area, elevation difference, terrain route preview, solar angles, and synthetic STL download. Uses the current sketch or selected point as indicated. |
| Science | Cited discoveries and source links, catalogue listings, and two-site landing comparison. |
| Rover panoramas | Curated panorama catalogue, globe locations, credits and links to NASA source galleries. |
| Missions & routes | Save the current sketch as mission stops; list, display, plan, optimize, profile, delete, and export saved missions as GeoJSON, KML, or CSV. Mission planning is [SIM]. |
| Environment & resources | Point radiation estimate, dust/SEP simulations, storm response summary, water and shelter candidates, simulated presence, and spatial-node listing/creation. |
| Bookmarks | List, fly to, and delete saved locations. |
| JEV | Ask questions, or open the resource-aware route planner. The planner can extract place names with a local model and computes advisory routes with candidate water and shelters using backend data. See below. |

The atlas does **not** implement every backend endpoint as a graphical control. For example, the old separate React workspace, first-person walk-view renderer, split-screen comparison, and 360° panorama renderer are not part of this single-UI build. Panorama source links open external galleries instead; backend services remain available through the API. An assistant request to activate a layer not supported by this atlas reports that limitation rather than pretending it was applied.


## Local AI and resource-aware route planning

The **JEV resource route planner** accepts a request such as `from Jezero to Gale`, explicit start and destination names (or `latitude, longitude`), or 2–5 points from the atlas traverse sketch. Choose whether to consider water, shelters, or both, an estimated detour budget, and an assumed travel speed. It draws successful routes directly on the NAM globe, offers GeoJSON export, and reports the stops, route length, estimated travel time, radiation estimate, sources and limitations.

### Enable the small local model

The model and its weights are **not bundled** in the repository. Install [Ollama](https://ollama.com/) on the machine running the backend, then in separate terminals:

```bash
ollama serve                    # if Ollama is not already running
ollama pull qwen2.5:1.5b        # one-time model download, roughly 1 GB
./run.sh                        # defaults to the local Ollama API and this model
```

The model server must stay running while using JEV. The atlas displays whether the selected model is available. You can also ask in JEV chat, for example, “plan a route from Jezero to Gale with water and shelter”; chat uses a 250 km estimated detour budget and 0.12 km/sol unless you use the route planner controls to choose other values. Route requests phrased in natural language use the model to extract ordered place names; if it is unavailable, a limited `from A [via B] to C` parser is used and the result explicitly says so. Explicit place fields and sketch points do not need a language model. The general JEV chat also attempts the configured OpenAI-compatible tool-calling model and labels the engine used; if it cannot produce valid tool calls, it falls back to the deterministic router.

You can use another OpenAI-compatible local server by exporting `NAM_LLM_BASE_URL` (include its `/v1` prefix) and `NAM_LLM_MODEL` before starting the backend. For example, the default is `http://127.0.0.1:11434/v1` and `qwen2.5:1.5b`. Set `NAM_LLM_BASE_URL` to an empty string to disable the model. A configured server need not be local, so use a trusted endpoint if changing this setting.

For Docker, opt into the separate Ollama container and pull the model into its named volume:

```bash
docker compose -f docker-compose.yml -f docker-compose.ai.yml --profile ai up -d --build backend model
docker compose -f docker-compose.yml -f docker-compose.ai.yml exec model ollama pull qwen2.5:1.5b
```

The model is downloaded by Ollama, not committed to Git or the application image. The CPU-only model may take substantial memory and time, especially on its first request. The Docker and model setup require access to their respective registries.

### How the planner makes decisions

1. It extracts literal place names in order, or accepts explicitly supplied names/coordinates. It resolves names against the backend gazetteer and refuses low-confidence or ambiguous matches; the model does **not** supply coordinates.
2. It searches the bundled water-ice and shelter catalogues and considers at most one of each requested type across the journey. It enumerates candidate placements and both within-leg orders, prefers satisfying the requested resource types, then ranks by estimated great-circle detour and candidate quality. The detour budget screens this approximation, **not** the final A* route.
3. It computes each chosen leg with the backend A* over the synthetic terrain grid, connects the selected endpoints, and estimates radiation along a sampled route using the entered speed and rover shielding. A failed leg produces a degraded result, not a fabricated continuous route. The model never calculates route geometry, resource availability, or safety.
4. It warns when requested candidates do not fit the budget. Candidate ice is not confirmed accessible water, shelters are unverified, and no weather, mobility, energy, extraction, communications, or operational safety is guaranteed. All results are advisory **[SIM]**.

The sparse demo resource catalogues do not cover every region. Great-circle detour screening may exclude a candidate that would be useful in a more detailed network; conversely, an included candidate does not prove practical access. The final terrain path can exceed the screening detour budget. Do not use these results for real mission decisions.

## Configuration

Settings come from environment variables; `.env.example` is a reference and is **not automatically loaded**. For example:

```bash
export NAM_PORT=8000
export NAM_ALLOW_UPSTREAM=0
./run.sh
```

| Variable | Purpose |
| --- | --- |
| `NAM_PORT` | Port used by `run.sh` (default `8000`). |
| `NAM_DATA_DIR` | Data root, including `seeds/` (default `data/`). |
| `NAM_DB_PATH` | SQLite database path (default `data/nam.db`). Its parent directory must exist. |
| `NAM_TILE_CACHE_DIR`, `NAM_TILE_TTL_HOURS` | Backend tile cache location and expiry. |
| `NAM_ALLOW_UPSTREAM` | `1` allows backend connectors to fetch external data; `0` disables backend upstream requests. This does **not** disable direct browser requests to Mars Trek in the atlas. |
| `NAM_CTX_TILE_TEMPLATE` | Optional CTX tile template for the backend connector. |
| `NAM_LLM_BASE_URL`, `NAM_LLM_MODEL` | Model endpoint and model for JEV; default `http://127.0.0.1:11434/v1` and `qwen2.5:1.5b`. Set the URL to an empty string to disable it. If unavailable, JEV falls back as described above. |
| `NAM_API_KEY` | When set, mutating API requests require `X-API-Key` or a Bearer token. |
| `NAM_CORS_ORIGINS` | Comma-separated browser origins permitted by the backend CORS policy. Default `*`; restrict it in deployed environments. |
| `NAM_BACKEND_URL` | Vite development proxy target, default `http://127.0.0.1:8000`. |

**API-key limitation:** the atlas currently has no key-entry mechanism. With `NAM_API_KEY` configured, browser mutations such as bookmarks, missions, storm simulations, and JEV chat will be rejected unless an authenticated reverse proxy or another authorized client supplies the key. Do not embed a shared secret in frontend code.

## Data, imagery, and scientific limitations

- The packaged elevation grid is a **synthetic 0.5-degree demonstration DEM [SIM]**, not a measured high-resolution MOLA or HiRISE terrain model. Elevations, slopes, derived routes, profiles, STL meshes, and hazard estimates must not be treated as operational data.
- Water and shelter candidates, radiation estimates, storms, response planning, and presence include approximations or simulation. The interface marks these as advisory [SIM].
- The gazetteer combines a bundled USGS/IAU dataset, curated features, and mission landing sites. The backend uses degrees latitude and east-positive longitude normalized to 0–360; the atlas displays familiar east/west longitudes as appropriate.
- Search uses a bundled snapshot of 2,055 USGS named Mars features plus curated features and 10 mission sites. It is not a live, exhaustive inventory of every Martian object or newly named feature. Coordinates are official catalogue centers when available; similarly named results should be checked individually. Unique exact USGS matches override older approximate curated coordinates. A point marker is not an actual feature boundary, and catalogue centers may not coincide with a specific summit, rim, lander or rover. Enter coordinates for places not in the snapshot.
- The atlas starts with the bundled Viking mosaic shared by the landing page and atlas, and attempts to switch to NASA/JPL Mars Trek imagery in the background when accessible. In **Layers → Base map**, select **CTX high-resolution mosaic** to request the Mars Trek Caltech beta CTX mosaic (nominal ~5 m/px; uncontrolled, with gaps). THEMIS day/night IR and TES dust, thermal inertia and albedo have also been added as optional overlays. These are remote NASA tiles, not bundled imagery; provider/CORS/network availability and regional coverage determine whether they load. If a selected remote base fails its probe, the app returns to bundled Viking and reports the failure. Overlay errors are reported without claiming full coverage. The zoom limit does not imply new source imagery or real 3D terrain. Custom tile templates must be Mars equirectangular / EPSG:104905-compatible. The NASA WMTS catalogue and capabilities provide formats, matrix sizes, levels and product information.
- Cesium is installed locally from npm. External imagery, source galleries, and web fonts still depend on third-party availability. Panoramas in the catalogue have credited source links and may use approximate poses; their presence does not imply a verified local 360° image asset.
- Each source, model, or publication has its own terms and attribution requirements. Consult the source links before reuse.

## Architecture and API

```text
client/index.html             NAM home, globe and panel markup
client/public/nam/            Original atlas assets, CSS, globe/home scripts, backend tool panels
client/scripts/               Cesium runtime copy for local build
client/vite.config.ts         Local dev server and same-origin backend proxy
app/main.py                   FastAPI assembly, static mounts and realtime lifecycle
app/routers/                  API routes
app/jev/                      JEV tools, deterministic routing and optional LLM adapter
app/mars.py, app/terrain.py   Coordinate, solar and terrain calculations
app/missions.py, app/routing.py  Advisory mission and route planning
app/environment.py            Radiation and storm simulations
app/db.py                     SQLite persistence
data/seeds/                   Curated source data and synthetic demo DEM
scripts/                      Seed/DEM generation and USGS gazetteer import
```

The repository also retains the earlier React client source under `client/src/` for reference. It is **not an entry point, built UI, or served workspace** in this version.

Explore the API at **`/docs`** or `/openapi.json`; check `/health` for service status. Representative endpoints:

- Geography and data: `/search`, `/locations/{id}`, `/location/card`, `/bookmarks`, `/landing_sites`, `/layers`, `/discoveries`, `/datasets`.
- Terrain and measurements: `/elevation`, `/terrain/*`, `/measure/*`.
- Imagery: `/imagery/ladder`, `/tiles/*`, `/panoramas`, `/traverses/*`, `/walkview/*`.
- Operations: `/missions`, `/missions/{id}/*`, `/environment/*`, `/water`, `/shelters`, `/nodes`, `/presence/*`.
- Assistant and realtime: `/jev/chat` (SSE), `/jev/route-plan`, `/jev/benchmark`, `/jev/tools`, `/events/*`, `/ws/events`, `/ws/presence`.

Some API capabilities have no corresponding atlas control; use `/docs` to inspect request and response schemas. Backend mutations can modify persistent data. Back up the SQLite database before replacing or migrating it.

## Deployment and security

The default configuration is intended for local development: CORS defaults to `*`, and an empty `NAM_API_KEY` permits unauthenticated mutations. Before publishing, put the application behind HTTPS and appropriate authentication, restrict CORS and network access, protect the database and API key, and review external service terms. The browser must reach the same public origin for both frontend and API; if using a reverse proxy, forward the API paths and WebSocket upgrades as well as static assets. `0.0.0.0` is a server bind address, not a URL to put in browser code.

## Verification

Before the test files were removed as requested, the regression suite was run three times on isolated SQLite databases: **122 passed on each run**. The production client build and browser checks also passed for the home-to-atlas transition, zoom buttons, wheel and Ctrl-wheel pinch, search and terrain inspection, traverse selection, measurements, mission creation/routing/profile, discoveries and site comparison, panorama catalogue, environment simulation and resources, bookmarks, and JEV. These checks do not prove every browser, network, external provider, API endpoint, or device gesture will work. The former test suite and test-only scripts are not included in this delivery. The resource-aware planner was additionally checked with a mock OpenAI-compatible model server, deterministic fallback, missing-resource and degraded-route cases, plus a browser route-planning flow. No actual Ollama model was available in the build environment, so real-model inference still requires local setup and verification. Search selection/centering, corrected coordinates, overlays, zoom and remote-basemap fallback were also browser-checked. NASA's published WMTS capabilities were consulted for the new map products, but the sandbox cannot directly reach NASA's tile server; actual live tile rendering must be verified on a network with access to Mars Trek.

## Troubleshooting

- **Blank or unavailable globe:** enable WebGL and try a current browser. The atlas displays an error if Cesium or the globe cannot initialize. Check that `client/dist/cesium/` exists after building and that `/cesium/Cesium.js` is reachable.
- **Map tiles do not load:** the atlas begins with the bundled Viking mosaic; if it cannot load, an error and Retry button appear instead of an endless spinner. Check your connection to this site and retry. The bundled mosaic is global imagery, not high-resolution terrain.
- **No frontend at `/`:** run `cd client && npm ci && npm run build` and restart FastAPI. The production root returns the page to browser requests that accept HTML.
- **API calls fail in Vite:** make sure FastAPI is running on port 8000 or set `NAM_BACKEND_URL` before `npm run dev`.
- **Saving or JEV returns 401:** check `NAM_API_KEY` and the authentication limitation above.
- **Nothing appears in measurement results:** select a point or sketch the required number of waypoints first. API errors are shown in the panel.
- **Generated client files missing after a clean checkout:** run `npm ci` and `npm run build` in `client/`; generated files and local databases are intentionally not tracked.
