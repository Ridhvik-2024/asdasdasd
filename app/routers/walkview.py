"""Walk View: first-person exploration backend.

Astronaut camera init, terrain mesh patches, POV library with nearest-POV
lookup, nearby rover imagery matched to heading. Terrain shading derives from
elevation data; sky is a clearly-labelled neutral sky where no imagery exists.
"""
import math

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import seeds, terrain
from ..integrity import prov, with_sim
from ..mars import bearing, hav_km, validate_coords

router = APIRouter(tags=["walkview"])
T = terrain.engine()


def _check_coords(lat: float, lon: float):
    try:
        return validate_coords(lat, lon)
    except ValueError as e:
        raise HTTPException(400, str(e))


class WalkInit(BaseModel):
    lat: float
    lon: float
    eye_height_m: float = 1.7
    heading_deg: float = 0.0
    fov_deg: float = 75.0


@router.post("/walkview/init")
def walk_init(w: WalkInit):
    vlat, vlon = _check_coords(w.lat, w.lon)
    if not math.isfinite(w.eye_height_m) or w.eye_height_m < 0.0:
        raise HTTPException(400, "eye_height_m must be a non-negative finite number")
    if not math.isfinite(w.heading_deg):
        raise HTTPException(400, "heading_deg must be finite")
    if not math.isfinite(w.fov_deg) or w.fov_deg <= 0.0 or w.fov_deg >= 180.0:
        raise HTTPException(400, "fov_deg must be in (0, 180)")
    elev = T.ensure().elev(vlat, vlon)
    pov = seeds.pov_nearest(vlat, vlon)
    pans = seeds.panoramas_near(vlat, vlon, radius_km=40)
    sky = "real imagery available" if pans else "neutral sky [SIM] (no ground imagery available at this location)"
    return with_sim({
        "camera": {"lat": vlat, "lon": vlon, "eye_height_m": w.eye_height_m,
                   "heading_deg": w.heading_deg, "fov_deg": w.fov_deg},
        "ground_elevation_m": round(elev, 1),
        "terrain_relief": {"source": "NAM synthetic terrain patch (Walk View mesh endpoint) [SIM]",
                           "note": "demo-synthetic-grid + procedural detail; not measured MOLA data. "
                                   "Production swap to MOLA MEGDR 4 ppd / HiRISE DTMs documented in terrain provenance.",
                           "vertical_exaggeration_available": True},
        "sky": sky,
        "nearest_pov": pov,
        "nearest_panoramas": pans[:5],
        "note": "stand on the surface, turn toward targets, and get the closest real "
                "photograph of your heading",
    }, note="Walk View camera state; advisory [SIM] where imagery is absent")


@router.get("/walkview/patch")
def walk_patch(lat: float, lon: float, radius_km: float = 2.0, n: int = 64):
    vlat, vlon = _check_coords(lat, lon)
    if not math.isfinite(radius_km) or radius_km <= 0.0:
        raise HTTPException(400, "radius_km must be a positive finite number")
    return T.ensure().mesh(vlat, vlon, radius_km, n)


@router.get("/walkview/pov")
def nearest_pov(lat: float, lon: float):
    vlat, vlon = _check_coords(lat, lon)
    pov = seeds.pov_nearest(vlat, vlon)
    if not pov:
        return with_sim({"nearest": None}, note="POV library empty")
    return {"nearest_pov": pov,
            "provenance": prov(source="NAM curated POV library (Jezero, Gale, Meridiani, Gusev, Elysium)")}


@router.get("/walkview/pov/library")
def pov_library():
    return {"count": len(seeds.pov_library()), "povs": seeds.pov_library(),
            "provenance": prov(source="NAM curated POV library")}


@router.get("/walkview/imagery")
def nearby_imagery(lat: float, lon: float, heading_deg: float = None, radius_km: float = 40):
    vlat, vlon = _check_coords(lat, lon)
    if not math.isfinite(radius_km) or radius_km <= 0.0:
        raise HTTPException(400, "radius_km must be a positive finite number")
    if heading_deg is not None and not math.isfinite(heading_deg):
        raise HTTPException(400, "heading_deg must be finite")
    pans = seeds.panoramas_near(vlat, vlon, radius_km)
    for p in pans:
        p["bearing_deg"] = round(bearing(vlat, vlon, p["lat"], p["lon"]), 1)
        if heading_deg is not None:
            diff = abs((p["bearing_deg"] - heading_deg + 180) % 360 - 180)
            p["heading_match_deg"] = round(diff, 1)
    pans.sort(key=lambda p: p.get("heading_match_deg", 0) if heading_deg is not None else p["distance_km"])
    return {"count": len(pans), "imagery": pans,
            "provenance": prov(source="NAM panorama catalogue, heading-matched")}
