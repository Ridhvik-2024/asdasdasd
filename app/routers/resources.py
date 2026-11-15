"""Water and shelter discovery endpoints."""
from fastapi import APIRouter

from .. import resources
from ..integrity import prov

router = APIRouter(tags=["resources"])


@router.get("/water")
def water(lat: float = None, lon: float = None, radius_km: float = 1500,
          min_lat: float = None, min_lon: float = None, max_lat: float = None, max_lon: float = None,
          min_certainty: str = None):
    near = {"lat": lat, "lon": lon} if lat is not None and lon is not None else None
    bbox = (min_lat, min_lon, max_lat, max_lon) if None not in (min_lat, min_lon, max_lat, max_lon) else None
    cands = resources.find_water(bbox=bbox, near=near, radius_km=radius_km, min_certainty=min_certainty)
    return {"count": len(cands), "candidates": cands,
            "provenance": prov(source="SWIM-consistent candidate regions (swim.psi.edu) + NAM stability logic [SIM]")}


@router.get("/shelters")
def shelters(lat: float = None, lon: float = None, radius_km: float = 1500):
    near = {"lat": lat, "lon": lon} if lat is not None and lon is not None else None
    out = resources.find_shelter(near=near, radius_km=radius_km)
    return {"count": len(out), "shelters": out,
            "provenance": prov(source="NAM curated 12-candidate shelter set [SIM] scoring")}


@router.get("/shelters/score")
def shelter_score(lat: float, lon: float, shielding: float = 70.0, thermal: float = 60.0,
                  access: float = 70.0):
    s = resources.score_shelter({"name": "custom candidate", "type": "user-defined",
                                 "lat": lat, "lon": lon, "shielding": shielding,
                                 "thermal": thermal, "access": access,
                                 "note": "user-supplied scores"})
    return s
