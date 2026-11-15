"""NAM v2 backend assembly: FastAPI app with lifespan-managed realtime loops,
configurable CORS policy, and optional API-key authentication for mutations."""
import asyncio
from contextlib import asynccontextmanager
import hmac

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, events, presence
from .routers import (environment, gazetteer, health, imagery, jev, measurements,
                      missions, nodes, panoramas, resources, science, terrain,
                      walkview, ws)

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Read-only / stateless computation POST endpoints that do not mutate shared state:
_STATELESS_POST_PREFIXES = (
    "/measure/",
    "/elevation/profile",
    "/environment/radiation/path",
    "/layers/compare",
    "/walkview/init",
    "/jev/explain",
    "/jev/route-plan",
)


def _extract_token(request: Request) -> str:
    hdr = request.headers.get("X-API-Key")
    if hdr:
        return hdr.strip()
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    events.hub.attach_loop(loop)
    task = loop.create_task(_telemetry())
    yield
    task.cancel()


async def _telemetry():
    import time
    n = 0
    while True:
        try:
            n += 1
            events.hub.broadcast("events", {"type": "telemetry_tick", "seq": n, "t": time.time(),
                                            "payload": {"sol_clock": "simulated [SIM] tick"}})
            agents = presence.agents()
            events.hub.broadcast("presence", {"type": "presence_update", "agents": agents, "sim": True})
        except Exception:
            pass
        await asyncio.sleep(5.0)


app = FastAPI(
    title="NAM v2 Backend - Navigation Assistant of Mars",
    description="Google Earth for Mars, backend-only build: core geo services, science and "
                "experience services, the JEV AI engine, environment and presence, and "
                "real-time channels. Every scientific value carries provenance; simulated "
                "values carry [SIM]; unavailable services degrade honestly.",
    version=config.VERSION,
    lifespan=lifespan,
)


@app.middleware("http")
async def api_key_mutation_guard(request: Request, call_next):
    """When config.API_KEY (NAM_API_KEY) is configured, require a valid key on
    all state-mutating endpoints while keeping public read/measurement routes open."""
    expected = config.API_KEY
    if expected and request.method in _MUTATING_METHODS:
        path = request.url.path
        if not path.startswith(_STATELESS_POST_PREFIXES):
            provided = _extract_token(request)
            if not provided or not hmac.compare_digest(provided, expected):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "valid X-API-Key or Bearer token required for mutating operation"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-NAM-Attribution", "X-NAM-Cache", "X-NAM-Vertical-Scale", "X-NAM-Provenance"],
)

app.include_router(health.router)
app.include_router(gazetteer.router)
app.include_router(terrain.router)
app.include_router(imagery.router)
app.include_router(measurements.router)
app.include_router(science.router)
app.include_router(panoramas.router)
app.include_router(walkview.router)
app.include_router(jev.router)
app.include_router(missions.router)
app.include_router(environment.router)
app.include_router(resources.router)
app.include_router(nodes.router)
app.include_router(ws.router)

_CLIENT_ASSETS = config.ROOT / "client" / "dist" / "assets"
if _CLIENT_ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=str(_CLIENT_ASSETS)), name="client-assets")

_NASA_PUBLIC = config.ROOT / "client" / "dist" / "nasa"
if not _NASA_PUBLIC.exists():
    _NASA_PUBLIC = config.ROOT / "client" / "public" / "nasa"
if _NASA_PUBLIC.exists():
    app.mount("/nasa", StaticFiles(directory=str(_NASA_PUBLIC)), name="nasa-assets")

# Static assets for the primary NAM atlas and its locally bundled Cesium runtime.
for _name in ("nam", "cesium"):
    _directory = config.ROOT / "client" / "dist" / _name
    if _directory.exists():
        app.mount(f"/{_name}", StaticFiles(directory=str(_directory)), name=f"client-{_name}")
