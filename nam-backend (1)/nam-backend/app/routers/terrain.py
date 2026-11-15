"""Elevation and terrain services (grid, slope, profiles, patches, hazard)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import terrain
from ..integrity import with_sim

router = APIRouter(tags=["terrain"])
T = terrain.engine()


@router.get("/elevation")
def elevation(lat: float, lon: float):
    return {"lat": lat, "lon": lon, "elevation_m": round(T.ensure().elev(lat, lon), 1),
            "slope_deg": round(T.slope(lat, lon), 2),
            "provenance": T.prov()}


class ProfileIn(BaseModel):
    points: list  # [{lat, lon}, ...]
    samples: int = 180


@router.post("/elevation/profile")
def profile(p: ProfileIn):
    if len(p.points) < 2:
        raise HTTPException(400, "need >= 2 points")
    pts = [{"lat": x["lat"], "lon": x["lon"]} for x in p.points]
    return T.ensure().profile(pts, samples=p.samples)


@router.get("/terrain/patch")
def terrain_patch(lat: float, lon: float, radius_km: float = 20.0, n: int = 96):
    return T.ensure().patch(lat, lon, radius_km, n)


@router.get("/terrain/mesh")
def terrain_mesh(lat: float, lon: float, radius_km: float = 2.0, n: int = 64):
    return T.ensure().mesh(lat, lon, radius_km, n)


@router.get("/terrain/slope")
def slope(lat: float = None, lon: float = None,
          min_lat: float = None, min_lon: float = None,
          max_lat: float = None, max_lon: float = None):
    if lat is not None and lon is not None:
        T.ensure()
        return {"lat": lat, "lon": lon, "slope_deg": round(T.slope(lat, lon), 2),
                "provenance": T.prov()}
    if None not in (min_lat, min_lon, max_lat, max_lon):
        st = T.ensure().bbox_stats((min_lat, min_lon, max_lat, max_lon))
        return with_sim(st, note="regional slope stats from demo grid [SIM]")
    raise HTTPException(400, "provide lat+lon or a bbox")


@router.get("/terrain/hazard")
def hazard(min_lat: float, min_lon: float, max_lat: float, max_lon: float):
    st = T.ensure().bbox_stats((min_lat, min_lon, max_lat, max_lon))
    return with_sim(st, note="hazard score = f(mean slope, max slope) [SIM]")
