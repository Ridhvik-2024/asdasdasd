"""Elevation and terrain services (grid, slope, aspect, curvature, profiles, patches, hazard)."""
import math

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from .. import seeds, terrain
from ..integrity import prov, with_sim
from ..mars import validate_coords, validate_lat, validate_lon

router = APIRouter(tags=["terrain"])
T = terrain.engine()


def _check_coords(lat: float, lon: float):
    try:
        return validate_coords(lat, lon)
    except ValueError as e:
        raise HTTPException(400, str(e))


def _check_bbox(min_lat: float, min_lon: float, max_lat: float, max_lon: float):
    try:
        validate_lat(min_lat)
        validate_lat(max_lat)
        validate_lon(min_lon)
        validate_lon(max_lon)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/elevation")
def elevation(lat: float, lon: float):
    vlat, vlon = _check_coords(lat, lon)
    T.ensure()
    return {"lat": lat, "lon": vlon, "elevation_m": round(T.elev(vlat, vlon), 1),
            "slope_deg": round(T.slope(vlat, vlon), 2),
            "aspect_deg": round(T.aspect(vlat, vlon), 1),
            "provenance": T.prov()}


class ProfileIn(BaseModel):
    points: list  # [{lat, lon}, ...]
    samples: int = 180


@router.post("/elevation/profile")
def profile(p: ProfileIn):
    if len(p.points) < 2:
        raise HTTPException(400, "need >= 2 points")
    pts = []
    for x in p.points:
        vlat, vlon = _check_coords(x["lat"], x["lon"])
        pts.append({"lat": vlat, "lon": vlon})
    return T.ensure().profile(pts, samples=p.samples)


@router.get("/terrain/patch")
def terrain_patch(lat: float, lon: float, radius_km: float = 20.0, n: int = 96):
    vlat, vlon = _check_coords(lat, lon)
    if not math.isfinite(radius_km) or radius_km <= 0:
        raise HTTPException(400, "radius_km must be > 0")
    return T.ensure().patch(vlat, vlon, radius_km, n)


@router.get("/terrain/mesh")
def terrain_mesh(lat: float, lon: float, radius_km: float = 2.0, n: int = 64):
    vlat, vlon = _check_coords(lat, lon)
    if not math.isfinite(radius_km) or radius_km <= 0:
        raise HTTPException(400, "radius_km must be > 0")
    return T.ensure().mesh(vlat, vlon, radius_km, n)


@router.get("/terrain/slope")
def slope(lat: float = None, lon: float = None,
          min_lat: float = None, min_lon: float = None,
          max_lat: float = None, max_lon: float = None):
    if lat is not None and lon is not None:
        vlat, vlon = _check_coords(lat, lon)
        T.ensure()
        return {"lat": lat, "lon": vlon, "slope_deg": round(T.slope(vlat, vlon), 2),
                "aspect_deg": round(T.aspect(vlat, vlon), 1),
                "curvature_per_km": round(T.curvature(vlat, vlon), 6),
                "provenance": T.prov()}
    if None not in (min_lat, min_lon, max_lat, max_lon):
        _check_bbox(min_lat, min_lon, max_lat, max_lon)
        st = T.ensure().bbox_stats((min_lat, min_lon, max_lat, max_lon))
        return with_sim(st, note="regional slope stats from demo grid [SIM]")
    raise HTTPException(400, "provide lat+lon or a bbox")


@router.get("/terrain/hazard")
def hazard(min_lat: float, min_lon: float, max_lat: float, max_lon: float):
    _check_bbox(min_lat, min_lon, max_lat, max_lon)
    st = T.ensure().bbox_stats((min_lat, min_lon, max_lat, max_lon))
    return with_sim(st, note="hazard score = f(mean slope, max slope) [SIM]")


RASTER_MODES = {
    "mars-relief", "mdim21", "ctx-murray", "hirise-insets",
    "mola-color", "mola-shaded", "themis-day", "themis-night",
    "sim3292-geology", "swim-probability", "depth-to-ice", "heightmap",
}


@router.get("/terrain/raster/{mode}.png")
def terrain_raster(mode: str):
    key = mode.lower().strip()
    if key not in RASTER_MODES:
        raise HTTPException(404, f"unknown raster mode {mode}; valid: {sorted(RASTER_MODES)}")
    png = T.ensure().render_raster_png(key)
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-NAM-Provenance": f"demo-synthetic-grid [SIM] raster:{key}",
        },
    )


@router.get("/terrain/elevation_grid")
def elevation_grid(step: int = 2):
    if step < 1 or step > 10:
        raise HTTPException(400, "step must be between 1 and 10")
    return T.ensure().elevation_grid_compact(step=step)


@router.get("/terrain/flyovers")
def list_flyovers():
    items = seeds.flyovers()
    return {
        "count": len(items),
        "flyovers": items,
        "provenance": prov("USGS Gazetteer / NASA JPL landmark flyover camera paths"),
    }


@router.get("/terrain/flyovers/{fid}")
def get_flyover(fid: str):
    item = seeds.flyover(fid)
    if not item:
        raise HTTPException(404, "flyover not found")
    return {"flyover": item, "provenance": prov(item.get("src", "USGS Gazetteer"))}

