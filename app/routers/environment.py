"""Environment endpoints: radiation, storm catalog, simulations, response plans."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import environment
from ..events import hub

router = APIRouter(prefix="/environment", tags=["environment"])


@router.get("/radiation")
def radiation(lat: float, lon: float, duration_sols: float = 1.0, shielding: str = "suit",
              storm_id: str = None):
    storm = environment.storm_by_id(storm_id) if storm_id else None
    return environment.radiation(lat, lon, duration_sols, shielding, storm)


@router.get("/storms")
def storm_catalog():
    return {"catalog": environment.catalog(),
            "note": "documented historical events; simulated scenarios carry [SIM]"}


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


class StormSimIn(BaseModel):
    kind: str = "dust"          # dust | sep
    scale_or_class: str = "local"  # local|regional|ped|my34  |  M|X
    lat: float = None
    lon: float = None
    broadcast: bool = True


@router.post("/storms/simulate")
def storm_simulate(s: StormSimIn):
    scen = environment.simulate_storm(s.kind, s.scale_or_class, s.lat, s.lon)
    if s.broadcast:
        hub.broadcast("events", {"type": "storm_alert", "scenario": scen})
    return scen


class ResponseIn(BaseModel):
    lat: float
    lon: float
    severity: str = "X"
    destination: list = None


@router.post("/storm_response")
def storm_response(r: ResponseIn):
    dest = {"lat": r.destination[0], "lon": r.destination[1]} if r.destination else None
    return environment.storm_response(r.lat, r.lon, destination=dest, severity=r.severity)
