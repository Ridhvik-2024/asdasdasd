"""Environment endpoints: radiation, storm catalog, simulations, response plans."""
from typing import Optional, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import environment
from ..events import hub

router = APIRouter(prefix="/environment", tags=["environment"])


@router.get("/radiation")
def radiation(lat: float, lon: float, duration_sols: float = 1.0, shielding: str = "suit",
              storm_id: str = None):
    storm = environment.storm_by_id(storm_id) if storm_id else None
    try:
        return environment.radiation(lat, lon, duration_sols, shielding, storm)
    except ValueError as e:
        raise HTTPException(400, str(e))


class PathRadiationIn(BaseModel):
    points: list
    speed_km_sol: float = 12.0
    shielding: str = "suit"
    storm_id: Optional[str] = None


@router.post("/radiation/path")
def radiation_path(r: PathRadiationIn):
    storm = environment.storm_by_id(r.storm_id) if r.storm_id else None
    try:
        return environment.radiation_path(r.points, r.speed_km_sol, r.shielding, storm)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/storms")
def storm_catalog():
    return {"catalog": environment.catalog(),
            "note": "documented historical events; simulated scenarios carry [SIM]"}


@router.get("/storms/classify")
def storm_classify(kind: str = "dust", tau: float = None, radius_km: float = None,
                   peak_msv_sol: float = None):
    try:
        return environment.classify_storm(kind, tau=tau, radius_km=radius_km, peak_msv_sol=peak_msv_sol)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/storms/active")
def active():
    return {"active_simulations": environment.active_storms(),
            "provenance": {"source": "NAM storm simulator [SIM]"}}


@router.get("/storms/{sid}")
def storm_get(sid: str):
    s = environment.storm_by_id(sid)
    if not s:
        raise HTTPException(404, "unknown simulated storm id")
    return s


@router.delete("/storms/{sid}")
def storm_delete(sid: str):
    if not environment.delete_storm(sid):
        raise HTTPException(404, "unknown simulated storm id")
    return {"deleted": sid}


class StormSimIn(BaseModel):
    kind: str = "dust"          # dust | sep
    scale_or_class: str = "local"  # local|regional|ped|my34  |  M|X
    lat: Optional[float] = None
    lon: Optional[float] = None
    broadcast: bool = True


@router.post("/storms/simulate")
def storm_simulate(s: StormSimIn):
    try:
        scen = environment.simulate_storm(s.kind, s.scale_or_class, s.lat, s.lon)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if s.broadcast:
        hub.broadcast("events", {"type": "storm_alert", "scenario": scen})
    return scen


class ResponseIn(BaseModel):
    lat: float
    lon: float
    severity: str = "X"
    destination: Optional[Union[list, dict]] = None


@router.post("/storm_response")
def storm_response(r: ResponseIn):
    try:
        return environment.storm_response(r.lat, r.lon, destination=r.destination, severity=r.severity)
    except ValueError as e:
        raise HTTPException(400, str(e))
