"""Imagery ladder registry, tile proxy with cache, connector status.

External imagery is reached ONLY through this proxy: cache, attribute,
degrade honestly. The client never calls upstream tile servers directly.
"""
import struct

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from .. import config
from ..connectors import base as connectors
from ..integrity import degraded, prov
from ..seeds import layers as _layers

router = APIRouter(tags=["imagery"])

LADDER = [
    {"level": 0, "id": "mdim21", "title": "Viking MDIM 2.1 global color", "res_m": 232,
     "use": "planetary zoom-out", "attribution": "USGS/NASA Viking"},
    {"level": 1, "id": "themis-day", "title": "THEMIS day IR", "res_m": 100,
     "use": "global thermal", "attribution": "ASU/NASA"},
    {"level": 1, "id": "themis-night", "title": "THEMIS night IR", "res_m": 100,
     "use": "thermal anomalies/bedrock", "attribution": "ASU/NASA"},
    {"level": 2, "id": "ctx-murray", "title": "Caltech Murray Lab Global CTX Mosaic", "res_m": 5,
     "use": "default surface layer (99.5% coverage, 88S-88N)", "attribution": "Caltech/MSSS/NASA JPL"},
    {"level": 3, "id": "hirise-insets", "title": "HiRISE deep-zoom insets", "res_m": 0.3,
     "use": "supported locations only", "attribution": "NASA/JPL/University of Arizona"},
    {"level": None, "id": "mola-color", "title": "MOLA color elevation", "res_m": 463,
     "use": "topography overlay", "attribution": "NASA MOLA"},
    {"level": None, "id": "mola-shaded", "title": "MOLA shaded relief", "res_m": 463,
     "use": "terrain readability", "attribution": "USGS/OpenPlanetaryMap"},
    {"level": None, "id": "sim3292-geology", "title": "USGS Geologic Map SIM 3292", "res_m": None,
     "use": "interactive geology", "attribution": "USGS (Tanaka et al. 2014)"},
]


@router.get("/imagery/ladder")
def imagery_ladder():
    return {"ladder": LADDER,
            "policy": "client fetches tiles only from /tiles/{layer}/{z}/{x}/{y}; "
                      "proxy caches, attributes and degrades honestly",
            "provenance": prov(source="NAM imagery ladder registry",
                               note="published resolutions; verified at connector time")}


@router.get("/tiles/{layer}/{z}/{x}/{y}")
def tile(layer: str, z: int, x: int, y: int):
    c = connectors.get("ctx-murray") if layer.startswith("ctx") else connectors.get(layer)
    if not c:
        # transparent passthrough for USGS-hosted layers by name
        c = connectors.get("usgs-wms")
    if not c:
        raise HTTPException(404, "unknown layer")
    if not config.ALLOW_UPSTREAM:
        body = degraded("tile:" + layer, "NAM_ALLOW_UPSTREAM=0 (offline mode)",
                        c["url"] + " (access path; cache hit expected in production)")
        body["attribution"] = c["attribution"]
        return Response(content=__import__("json").dumps(body), media_type="application/json", status_code=503)
    template = c.get("template")
    if not template or "{z}" not in template:
        body = degraded("tile:" + layer,
                        "tile URL template not yet verified for this layer (connector-time verification pending)",
                        c["url"])
        body["attribution"] = c["attribution"]
        return Response(content=__import__("json").dumps(body), media_type="application/json", status_code=503)
    url = template.format(z=z, x=x, y=y)
    try:
        data, cached = connectors.fetch_bytes(url)
    except Exception as e:
        _stats = connectors._stats
        _stats["errors"] += 1
        body = degraded("tile:" + layer,
                        "upstream fetch failed: %s" % type(e).__name__,
                        c["url"] + " - documented access path; not faked")
        body["attribution"] = c["attribution"]
        return Response(content=__import__("json").dumps(body), media_type="application/json", status_code=503)
    headers = {
        "X-NAM-Cache": "hit" if cached else "miss",
        "X-NAM-Attribution": c["attribution"],
        "Cache-Control": "public, max-age=86400",
    }
    media = "image/jpeg" if url.endswith((".jpg", ".jpeg")) else "image/png"
    return Response(content=data, media_type=media, headers=headers)


@router.get("/tiles/stats")
def tile_stats():
    return {"stats": connectors._stats, "provenance": prov(source="tile proxy counters")}


@router.get("/connectors/status")
def connectors_status():
    return connectors.status()


@router.post("/connectors/{name}/verify")
def connector_verify(name: str):
    c = connectors.verify(name)
    if not c:
        raise HTTPException(404, "unknown connector")
    return {"connector": c, "provenance": prov(source="connector live verification",
                                               note="HEAD check at build/gate time")}


class LayerActivate(BaseModel):
    layer_id: str


@router.post("/imagery/activate")
def activate_layer(l: LayerActivate):
    lay = next((x for x in _layers() if x["id"] == l.layer_id), None)
    if not lay:
        raise HTTPException(404, "unknown layer")
    return {"activated": lay["id"], "layer": lay,
            "provenance": prov(source=lay["source"], url=lay.get("url"),
                               attribution=lay.get("attribution"))}


def _unused(x=struct):  # keep import referenced for extension
    return x
