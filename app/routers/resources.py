"""Water and shelter discovery endpoints."""
import math

from fastapi import APIRouter, HTTPException

from .. import resources
from ..integrity import prov
from ..mars import validate_coords, validate_lat, validate_lon

router = APIRouter(tags=["resources"])


def _parse_spatial_filters(lat, lon, radius_km, min_lat, min_lon, max_lat, max_lon):
    near = None
    if lat is not None or lon is not None:
        try:
            if lat is not None:
                validate_lat(lat)
            if lon is not None:
                validate_lon(lon)
        except ValueError as e:
            raise HTTPException(400, str(e))
        if lat is None or lon is None:
            raise HTTPException(400, "provide both lat and lon for proximity search")
        vlat, vlon = validate_coords(lat, lon)
        near = {"lat": vlat, "lon": vlon}

    if not math.isfinite(radius_km) or radius_km <= 0.0:
        raise HTTPException(400, "radius_km must be a positive finite number")

    bbox = None
    bbox_vals = (min_lat, min_lon, max_lat, max_lon)
    if any(v is not None for v in bbox_vals):
        try:
            if min_lat is not None:
                validate_lat(min_lat)
            if max_lat is not None:
                validate_lat(max_lat)
            if min_lon is not None:
                validate_lon(min_lon)
            if max_lon is not None:
                validate_lon(max_lon)
        except ValueError as e:
            raise HTTPException(400, str(e))
        if any(v is None for v in bbox_vals):
            raise HTTPException(400, "provide all four bbox parameters: min_lat, min_lon, max_lat, max_lon")
        bbox = bbox_vals
    return near, bbox


@router.get("/water")
def water(lat: float = None, lon: float = None, radius_km: float = 1500,
          min_lat: float = None, min_lon: float = None, max_lat: float = None, max_lon: float = None,
          min_certainty: str = None):
    near, bbox = _parse_spatial_filters(lat, lon, radius_km, min_lat, min_lon, max_lat, max_lon)
    try:
        cands = resources.find_water(bbox=bbox, near=near, radius_km=radius_km, min_certainty=min_certainty)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"count": len(cands), "candidates": cands,
            "provenance": prov(source="SWIM-consistent candidate regions (swim.psi.edu) + NAM stability logic [SIM]")}


@router.get("/shelters")
def shelters(lat: float = None, lon: float = None, radius_km: float = 1500,
             min_lat: float = None, min_lon: float = None, max_lat: float = None, max_lon: float = None):
    near, bbox = _parse_spatial_filters(lat, lon, radius_km, min_lat, min_lon, max_lat, max_lon)
    try:
        out = resources.find_shelter(bbox=bbox, near=near, radius_km=radius_km)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"count": len(out), "shelters": out,
            "provenance": prov(source="NAM curated 12-candidate shelter set [SIM] scoring")}


@router.get("/shelters/score")
def shelter_score(lat: float, lon: float, shielding: float = 70.0, thermal: float = 60.0,
                  access: float = 70.0):
    try:
        vlat, vlon = validate_coords(lat, lon)
        s = resources.score_shelter({"name": "custom candidate", "type": "user-defined",
                                     "lat": vlat, "lon": vlon, "shielding": shielding,
                                     "thermal": thermal, "access": access,
                                     "note": "user-supplied scores"})
    except ValueError as e:
        raise HTTPException(400, str(e))
    return s
