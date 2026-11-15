"""NAM v2 backend assembly: FastAPI app with lifespan-managed realtime loops."""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, events, presence
from .routers import (environment, gazetteer, health, imagery, jev, measurements,
                      missions, nodes, panoramas, resources, science, terrain,
                      walkview, ws)


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
