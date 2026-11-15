"""Walk View: first-person exploration backend.

Astronaut camera init, terrain mesh patches, POV library with nearest-POV
lookup, nearby rover imagery matched to heading. Terrain shading derives from
elevation data; sky is a clearly-labelled neutral sky where no imagery exists.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from .. import seeds, terrain
from ..integrity import prov, with_sim
from ..mars import bearing, hav_km

router = APIRouter(tags=["walkview"])
T = terrain.engine()


class WalkInit(BaseModel):
    lat: float
    lon: float
    eye_height_m: float = 1.7
    heading_deg: float = 0.0
    fov_deg: float = 75.0


@router.post("/walkview/init")
def walk_init(w: WalkInit):
    elev = T.ensure().elev(w.lat, w.lon)
    pov = seeds.pov_nearest(w.lat, w.lon)
    pans = seeds.panoramas_near(w.lat, w.lon, radius_km=40)
    sky = "real imagery available" if pans else "neutral sky [SIM] (no ground imagery available at this location)"
    return with_sim({
        "camera": {"lat": w.lat, "lon": w.lon, "eye_height_m": w.eye_height_m,
                   "heading_deg": w.heading_deg, "fov_deg": w.fov_deg},
        "ground_elevation_m": round(elev, 1),
        "terrain_relief": {"source": "MOLA-derived terrain patch (Walk View mesh endpoint)",
                           "vertical_exaggeration_available": True},
        "sky": sky,
        "nearest_pov": pov,
        "nearest_panoramas": pans[:5],
        "note": "stand on the surface, turn toward targets, and get the closest real "
                "photograph of your heading",
    }, note="Walk View camera state; advisory [SIM] where imagery is absent")


@router.get("/walkview/patch")
def walk_patch(lat: float, lon: float, radius_km: float = 2.0, n: int = 64):
    return T.ensure().mesh(lat, lon, radius_km, n)


@router.get("/walkview/pov")
def nearest_pov(lat: float, lon: float):
    pov = seeds.pov_nearest(lat, lon)
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
    pans = seeds.panoramas_near(lat, lon, radius_km)
    for p in pans:
        p["bearing_deg"] = round(bearing(lat, lon, p["lat"], p["lon"]), 1)
        if heading_deg is not None:
            diff = abs((p["bearing_deg"] - heading_deg + 180) % 360 - 180)
            p["heading_match_deg"] = round(diff, 1)
    pans.sort(key=lambda p: p.get("heading_match_deg", 0) if heading_deg is not None else p["distance_km"])
    return {"count": len(pans), "imagery": pans,
            "provenance": prov(source="NAM panorama catalogue, heading-matched")}
