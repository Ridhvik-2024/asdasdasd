"""Health and platform status."""
from pathlib import Path
import time

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from .. import config, db

router = APIRouter(tags=["health"])
_STARTED = time.time()
_CLIENT_INDEX = config.ROOT / "client" / "dist" / "index.html"


@router.get("/health")
def health():
    return {
        "status": "ok",
        "name": "NAM v2 backend - Navigation Assistant of Mars",
        "version": config.VERSION,
        "uptime_s": round(time.time() - _STARTED, 1),
        "db": "sqlite (%s)" % config.DB_PATH.name,
        "integrity": {
            "provenance_required": True,
            "sim_labels_enforced": True,
            "degradation": "honest, documented access paths",
            "coordinates": "lat degrees (south negative), lon EAST 0-360",
        },
        "releases": config.RELEASES,
        "services": {
            "gazetteer": "ok", "elevation": "ok", "imagery": "tile-proxy",
            "measurements": "ok", "science": "ok", "panoramas": "ok",
            "walkview": "ok", "jev": "ok", "missions": "ok",
            "environment": "ok", "resources": "ok", "nodes": "ok",
            "presence": "ok", "realtime": "ws:/ws/events,/ws/presence",
        },
    }


@router.get("/")
def root(request: Request):
    accept = (request.headers.get("accept") or "").lower()
    if "text/html" in accept and _CLIENT_INDEX.exists():
        return FileResponse(_CLIENT_INDEX)
    return {
        "name": "NAM v2 - Navigation Assistant of Mars (Google Earth for Mars)",
        "docs": "/docs",
        "openapi": "/openapi.json (OpenAPI 3.1)",
        "health": "/health",
        "client": "NAM atlas (client/), served at / for browsers",
    }
