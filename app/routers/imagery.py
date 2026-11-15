"""Imagery ladder registry, tile proxy with persistent cache, WMS/XYZ adapters,
magic-byte content verification, and connector status."""
import json

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

# Known USGS Astrogeology WMS layer identifiers corresponding to NAM ladder IDs
WMS_LAYER_MAP = {
    "mdim21": "MARS_viking_mdim21_ClrMosaic_global_232m",
    "themis-day": "MARS_themis_dayir_mosaic_global_100m",
    "themis-night": "MARS_themis_nightir_mosaic_global_100m",
    "mola-color": "MARS_mola_colorized_shaded_relief_global_463m",
    "mola-shaded": "MARS_mola_shaded_relief_global_463m",
    "sim3292-geology": "MARS_sim3292_geology",
}


def _validate_tile_xyz(z: int, x: int, y: int):
    """Validate tile zoom and slippy/equirectangular (x, y) indices."""
    if z < 0 or z > 24:
        raise HTTPException(400, "zoom level z must be in [0, 24]")
    # Allow both 1:1 Web-Mercator (2^z x 2^z) and 2:1 equirectangular CRS:84 (2^(z+1) x 2^z)
    max_x = 1 << (z + 1)
    max_y = 1 << z
    if x < 0 or x >= max_x or y < 0 or y >= max_y:
        raise HTTPException(400, "tile coordinates (x=%d, y=%d) out of range for z=%d" % (x, y, z))


def _xyz_to_crs84_bbox(z: int, x: int, y: int) -> str:
    """Convert equirectangular/global tile (z, x, y) into CRS:84 BBOX (min_lon,min_lat,max_lon,max_lat)."""
    nx = max(1, 1 << z)
    ny = max(1, 1 << z)
    lon0 = (x / nx) * 360.0 - 180.0
    lon1 = ((x + 1) / nx) * 360.0 - 180.0
    lat1 = 90.0 - (y / ny) * 180.0
    lat0 = 90.0 - ((y + 1) / ny) * 180.0
    return "%.6f,%.6f,%.6f,%.6f" % (lon0, lat0, lon1, lat1)


@router.get("/imagery/ladder")
def imagery_ladder():
    return {"ladder": LADDER,
            "policy": "client fetches tiles only from /tiles/{layer}/{z}/{x}/{y}; "
                      "proxy caches, attributes and degrades honestly",
            "provenance": prov(source="NAM imagery ladder registry",
                               note="published resolutions; verified at connector time")}


@router.get("/tiles/{layer}/{z}/{x}/{y}")
def tile(layer: str, z: int, x: int, y: int):
    _validate_tile_xyz(z, x, y)
    c = connectors.get("ctx-murray") if layer.startswith("ctx") else connectors.get(layer)
    wms_layer = WMS_LAYER_MAP.get(layer)
    if not c and wms_layer:
        c = connectors.get("usgs-wms")
    if not c:
        c = connectors.get("usgs-wms")
    if not c:
        raise HTTPException(404, "unknown layer")

    if not config.ALLOW_UPSTREAM:
        body = degraded("tile:" + layer, "NAM_ALLOW_UPSTREAM=0 (offline mode)",
                        c["url"] + " (access path; cache hit expected in production)")
        body["attribution"] = c["attribution"]
        return Response(content=json.dumps(body), media_type="application/json", status_code=503)

    template = c.get("template")
    if template and "{z}" in template:
        url = template.format(z=z, x=x, y=y)
    elif template and "{bbox}" in template and wms_layer:
        url = template.format(layer=wms_layer, bbox=_xyz_to_crs84_bbox(z, x, y), w=256, h=256)
    else:
        body = degraded("tile:" + layer,
                        "tile URL template not yet verified for this layer (connector-time verification pending)",
                        c["url"])
        body["attribution"] = c["attribution"]
        return Response(content=json.dumps(body), media_type="application/json", status_code=503)

    try:
        data, cached = connectors.fetch_bytes(url)
    except Exception as e:
        connectors._stats["errors"] += 1
        body = degraded("tile:" + layer,
                        "upstream fetch failed: %s" % type(e).__name__,
                        c["url"] + " - documented access path; not faked")
        body["attribution"] = c["attribution"]
        return Response(content=json.dumps(body), media_type="application/json", status_code=503)

    media = connectors.detect_image_media_type(data)
    if not media:
        connectors._stats["errors"] += 1
        body = degraded("tile:" + layer,
                        "upstream payload failed image magic-byte validation",
                        c["url"] + " - documented access path; non-image response rejected")
        body["attribution"] = c["attribution"]
        return Response(content=json.dumps(body), media_type="application/json", status_code=503)

    headers = {
        "X-NAM-Cache": "hit" if cached else "miss",
        "X-NAM-Attribution": c["attribution"],
        "Cache-Control": "public, max-age=86400",
    }
    return Response(content=data, media_type=media, headers=headers)


@router.get("/tiles/stats")
def tile_stats():
    return {"stats": connectors._stats, "provenance": prov(source="tile proxy counters")}


@router.post("/tiles/cache/invalidate")
def invalidate_tile_cache(url: str = None):
    connectors.invalidate_cache(url)
    return {"invalidated": url or "all", "stats": connectors._stats}


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
