"""Mission suite endpoints (route/area/evacuation/survey, KML, optimize)."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from .. import missions

router = APIRouter(prefix="/missions", tags=["missions"])


class MissionIn(BaseModel):
    type: str
    name: str
    objective: str = ""
    stops: list = []


@router.post("")
def create_mission(m: MissionIn):
    try:
        return missions.create(m.type, m.name, m.objective, m.stops)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("")
def list_missions():
    return {"missions": missions.list_missions(),
            "note": "all plans advisory [SIM]"}


@router.get("/{mid}")
def get_mission(mid: str):
    m = missions.get(mid)
    if not m:
        raise HTTPException(404, "unknown mission")
    return m


class StopIn(BaseModel):
    lat: float
    lon: float
    activity: str = "observe"
    reason: str = ""


@router.post("/{mid}/stops")
def add_stop(mid: str, s: StopIn):
    m = missions.add_stop(mid, s.lat, s.lon, s.activity, s.reason)
    if not m:
        raise HTTPException(404, "unknown mission")
    return m


class RouteIn(BaseModel):
    from_lat: float
    from_lon: float
    to_lat: float
    to_lon: float
    preset: str = "balanced"


@router.post("/{mid}/route")
def attach_route(mid: str, r: RouteIn):
    res = missions.route_for(mid, r.from_lat, r.from_lon, r.to_lat, r.to_lon, r.preset)
    if not res:
        raise HTTPException(404, "unknown mission")
    if res.get("path") and res["path"]:
        pass
    return res


class OptimizeIn(BaseModel):
    preset: str = "balanced"


@router.post("/{mid}/optimize")
def optimize(mid: str, o: OptimizeIn):
    m = missions.optimize(mid, o.preset)
    if not m:
        raise HTTPException(404, "unknown mission or too few stops")
    return m


@router.get("/{mid}/kml")
def kml(mid: str):
    doc = missions.kml(mid)
    if doc is None:
        raise HTTPException(404, "unknown mission")
    return Response(content=doc, media_type="application/vnd.google-earth.kml+xml",
                    headers={"Content-Disposition": 'attachment; filename="%s.kml"' % mid})


@router.get("/{mid}/compare")
def compare(mid: str, other_id: str = None):
    if not other_id:
        raise HTTPException(400, "provide ?other_id=")
    res = missions.compare(mid, other_id)
    if not res:
        raise HTTPException(404, "unknown mission id(s)")
    return res


class NoteIn(BaseModel):
    note: str


@router.put("/{mid}/notes")
def annotate(mid: str, n: NoteIn):
    m = missions.annotate(mid, n.note)
    if not m:
        raise HTTPException(404, "unknown mission")
    return m


@router.delete("/{mid}")
def delete_mission(mid: str):
    return {"deleted": missions.delete(mid)}
