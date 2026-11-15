"""Mission suite endpoints (route/area/evacuation/survey, KML/GeoJSON/CSV, optimize, profile, share)."""
import json
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from .. import db, environment, missions, terrain
from ..events import hub

router = APIRouter(prefix="/missions", tags=["missions"])


class MissionIn(BaseModel):
    type: str
    name: str
    objective: str = ""
    stops: list = []


@router.post("")
def create_mission(m: MissionIn):
    try:
        res = missions.create(m.type, m.name, m.objective, m.stops)
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(400, str(e))
    hub.broadcast("events", {"type": "plan_change", "action": "created", "mission_id": res["id"], "name": res["name"], "sim": True})
    return res


@router.get("")
def list_missions():
    items = missions.list_missions()
    return {"count": len(items), "missions": items,
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
    try:
        m = missions.add_stop(mid, s.lat, s.lon, s.activity, s.reason)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not m:
        raise HTTPException(404, "unknown mission")
    hub.broadcast("events", {"type": "plan_change", "action": "stop_added", "mission_id": mid, "sim": True})
    return m


class RouteIn(BaseModel):
    from_lat: float
    from_lon: float
    to_lat: float
    to_lon: float
    preset: str = "balanced"


@router.post("/{mid}/route")
def attach_route(mid: str, r: RouteIn):
    try:
        res = missions.route_for(mid, r.from_lat, r.from_lon, r.to_lat, r.to_lon, r.preset)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not res:
        raise HTTPException(404, "unknown mission")
    hub.broadcast("events", {"type": "plan_change", "action": "route_attached", "mission_id": mid, "sim": True})
    return res


class OptimizeIn(BaseModel):
    preset: str = "balanced"


@router.post("/{mid}/optimize")
def optimize(mid: str, o: OptimizeIn):
    m = missions.optimize(mid, o.preset)
    if not m:
        raise HTTPException(404, "unknown mission or too few stops")
    hub.broadcast("events", {"type": "plan_change", "action": "optimized", "mission_id": mid, "sim": True})
    return m


@router.get("/{mid}/profile")
def mission_profile(mid: str, samples: int = 120, speed_km_sol: float = 12.0,
                    shielding: str = "rover"):
    m = missions.get(mid)
    if not m:
        raise HTTPException(404, "unknown mission")
    pts = []
    if m.get("routes"):
        path = m["routes"][-1].get("path") or []
        if len(path) >= 2:
            pts = [{"lat": p["lat"], "lon": p["lon"]} for p in path]
    if len(pts) < 2 and len(m.get("stops") or []) >= 2:
        pts = [{"lat": s["lat"], "lon": s["lon"]} for s in m["stops"]]
    if len(pts) < 2:
        raise HTTPException(400, "mission needs at least 2 stops or a planned route for a profile")
    T = terrain.engine().ensure()
    prof = T.profile(pts, samples=samples)
    rad = environment.radiation_path(pts, speed_km_sol=speed_km_sol, shielding=shielding)
    slopes = [round(T.slope(p["lat"], p["lon"]), 2) for p in prof["points"]]
    return {
        "mission_id": mid,
        "mission_name": m["name"],
        "profile": prof,
        "slope_summary": {
            "mean_slope_deg": round(sum(slopes) / max(len(slopes), 1), 2),
            "max_slope_deg": max(slopes) if slopes else 0.0,
        },
        "radiation": rad,
        "advisory": True,
    }


@router.post("/{mid}/share")
def share_mission(mid: str):
    m = missions.get(mid)
    if not m:
        raise HTTPException(404, "unknown mission")
    pts = [{"lat": s["lat"], "lon": s["lon"]} for s in (m.get("stops") or [])]
    if not pts and m.get("routes") and m["routes"][-1].get("path"):
        pts = m["routes"][-1]["path"]
    center_lat = sum(p["lat"] for p in pts) / len(pts) if pts else 18.44
    center_lon = sum(p["lon"] for p in pts) / len(pts) if pts else 77.45
    sid = "msh-" + uuid.uuid4().hex[:8]
    payload = {
        "kind": "mission_share",
        "mission_id": mid,
        "name": m["name"],
        "camera": {"lat": round(center_lat, 4), "lon": round(center_lon, 4), "altitude_km": 1200},
        "mission": m,
    }
    db.ex("INSERT INTO share_links (id,payload_json) VALUES (?,?)", (sid, db.j(payload)))
    return {"share_id": sid, "url": f"/share/{sid}", "mission_id": mid, "payload": payload}


@router.get("/{mid}/kml")
def kml(mid: str):
    doc = missions.kml(mid)
    if doc is None:
        raise HTTPException(404, "unknown mission")
    return Response(content=doc, media_type="application/vnd.google-earth.kml+xml",
                    headers={"Content-Disposition": 'attachment; filename="%s.kml"' % mid})


@router.get("/{mid}/geojson")
def geojson_export(mid: str):
    doc = missions.geojson(mid)
    if doc is None:
        raise HTTPException(404, "unknown mission")
    return doc


@router.get("/{mid}/csv")
def csv_export(mid: str):
    doc = missions.csv_stops(mid)
    if doc is None:
        raise HTTPException(404, "unknown mission")
    return Response(content=doc, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="%s_stops.csv"' % mid})


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
    hub.broadcast("events", {"type": "plan_change", "action": "annotated", "mission_id": mid, "sim": True})
    return m


@router.delete("/{mid}")
def delete_mission(mid: str):
    if not missions.delete(mid):
        raise HTTPException(404, "unknown mission")
    hub.broadcast("events", {"type": "plan_change", "action": "deleted", "mission_id": mid, "sim": True})
    return {"deleted": True}
