"""Mission planning suite: route/area/evacuation/survey with ordered stops,
KML export, optimization and comparison. All generated plans are advisory."""
import uuid

from . import db, routing
from .integrity import SIM


def create(mtype, name, objective=None, stops=None):
    mid = "mission-" + uuid.uuid4().hex[:8]
    if mtype not in ("route", "area", "evacuation", "survey"):
        raise ValueError("type must be one of route|area|evacuation|survey")
    db.ex("INSERT INTO missions (id,type,name,objective,advisory) VALUES (?,?,?,?,1)",
          (mid, mtype, name, objective or ""))
    for i, s in enumerate(stops or []):
        add_stop(mid, s["lat"], s["lon"], s.get("activity", "observe"),
                 s.get("reason", ""), ord_=i + 1)
    return get(mid)


def add_stop(mid, lat, lon, activity="observe", reason="", ord_=None):
    m = get(mid)
    if not m:
        return None
    if ord_ is None:
        rows = db.q("SELECT COALESCE(MAX(ord),0)+1 AS nxt FROM mission_stops WHERE mission_id=?", (mid,))
        ord_ = rows[0]["nxt"]
    db.ex("INSERT INTO mission_stops (mission_id,ord,lat,lon,activity,reason) VALUES (?,?,?,?,?,?)",
          (mid, ord_, lat, lon, activity, reason))
    return get(mid)


def add_waypoint(mid, lat, lon):
    return add_stop(mid, lat, lon, activity="waypoint", reason="routed waypoint")


def get(mid):
    rows = db.q("SELECT * FROM missions WHERE id=?", (mid,))
    if not rows:
        return None
    m = rows[0]
    stops = db.q("SELECT * FROM mission_stops WHERE mission_id=? ORDER BY ord", (mid,))
    routes = db.q("SELECT id,preset,length_km,stats_json,created FROM routes WHERE mission_id=?", (mid,))
    return {
        "id": m["id"], "type": m["type"], "name": m["name"], "objective": m["objective"],
        "status": m["status"], "notes": m["notes"],
        "advisory": bool(m["advisory"]),
        "advisory_label": "Simulated plan - advisory only " + SIM,
        "stops": [{"ord": s["ord"], "lat": s["lat"], "lon": s["lon"],
                   "activity": s["activity"], "reason": s["reason"]} for s in stops],
        "routes": [{"id": r["id"], "preset": r["preset"], "length_km": r["length_km"],
                    "stats": db.uj(r["stats_json"], {}), "created": r["created"]} for r in routes],
        "provenance": {"source": "NAM mission planner [SIM] - validated plan object with provenance"},
    }


def list_missions():
    rows = db.q("SELECT id,type,name,status,created FROM missions ORDER BY created DESC")
    return rows


def attach_route(mid, route, preset="balanced"):
    rid = "route-" + uuid.uuid4().hex[:8]
    # Successful routes carry stats.length_km; degraded routes carry a top-level
    # length_km of None and a "status": "degraded" marker. Normalise both shapes
    # so the persisted row is consistent.
    if route.get("status") == "degraded":
        stats = {
            "length_km": None,
            "status": "degraded",
            "degraded": True,
            "note": route.get("note", "degraded fallback"),
        }
        length_km = None
    else:
        stats = route.get("stats") or {}
        length_km = stats.get("length_km")
    db.ex("INSERT INTO routes (id,mission_id,preset,length_km,stats_json,path_json) VALUES (?,?,?,?,?,?)",
          (rid, mid, preset, length_km, db.j(stats), db.j(route.get("path", []))))
    db.ex("UPDATE missions SET status='planned' WHERE id=?", (mid,))
    return rid


def route_for(mid, lat1, lon1, lat2, lon2, preset="balanced"):
    m = get(mid)
    if not m:
        return None
    route = routing.plan_route(lat1, lon1, lat2, lon2, preset)
    rid = attach_route(mid, route, preset)
    return {"route_id": rid, **route}


def optimize(mid, preset="balanced"):
    """Nearest-neighbor ordering of stops over A* leg lengths.

    A leg may come back degraded (no in-grid route found). Degraded legs are
    recorded honestly with ``length_km`` and ``est_sols`` set to None; they
    never contribute to the summed mission length, and the resulting stats
    block carries a ``degraded_legs`` count so callers can distinguish a
    complete measurement from a partial one.
    """
    m = get(mid)
    if not m or len(m["stops"]) < 2:
        return None
    stops = list(m["stops"])
    remaining = stops[1:]
    order = [stops[0]]
    while remaining:
        cur = order[-1]
        best, bd = None, None
        for s in remaining:
            from .mars import hav_km
            d = hav_km(cur["lat"], cur["lon"], s["lat"], s["lon"])
            if bd is None or d < bd:
                best, bd = s, d
        order.append(best)
        remaining.remove(best)
    length = 0.0
    legs = []
    degraded_legs = 0
    for i in range(len(order) - 1):
        a, b = order[i], order[i + 1]
        leg = routing.plan_route(a["lat"], a["lon"], b["lat"], b["lon"], preset)
        if leg.get("status") == "degraded":
            # Degraded leg: no measured length, no slope stats, no traversal
            # time. Record it honestly and never report a length for it.
            degraded_legs += 1
            legs.append({
                "from": [a["lat"], a["lon"]],
                "to": [b["lat"], b["lon"]],
                "length_km": None,
                "est_sols": None,
                "status": "degraded",
                "note": leg.get("note", "degraded fallback"),
            })
            continue
        leg_stats = leg.get("stats") or {}
        leg_len = leg_stats.get("length_km")
        if leg_len is not None:
            length += leg_len
        legs.append({
            "from": [a["lat"], a["lon"]],
            "to": [b["lat"], b["lon"]],
            "length_km": leg_len,
            "est_sols": leg_stats.get("est_traverse_sols"),
        })
    db.ex("DELETE FROM mission_stops WHERE mission_id=?", (mid,))
    for i, s in enumerate(order):
        db.ex("INSERT INTO mission_stops (mission_id,ord,lat,lon,activity,reason) VALUES (?,?,?,?,?,?)",
              (mid, i + 1, s["lat"], s["lon"], s["activity"], s["reason"]))
    rid = "route-" + uuid.uuid4().hex[:8]
    # If every leg degraded, there is no measured route at all: report None
    # rather than a misleading 0 km "plan".
    total_length = round(length, 2) if degraded_legs < len(legs) else None
    stats = {
        "length_km": total_length,
        "cost_preset": preset,
        "legs": legs,
        "optimized": True,
        "degraded_legs": degraded_legs,
        "total_legs": len(legs),
    }
    db.ex("INSERT INTO routes (id,mission_id,preset,length_km,stats_json,path_json) VALUES (?,?,?,?,?,?)",
          (rid, mid, preset, total_length, db.j(stats), db.j(order)))
    return get(mid)


def kml(mid):
    m = get(mid)
    if not m:
        return None
    from . import terrain
    T = terrain.engine().ensure()
    coords = []
    if m["routes"]:
        path = db.uj(db.q("SELECT path_json FROM routes WHERE mission_id=? ORDER BY created DESC LIMIT 1",
                          (mid,))[0]["path_json"], [])
        for p in path:
            coords.append("%.5f,%.5f,%.0f" % (p["lon"], p["lat"], p.get("elev_m", 0)))
    else:
        for s in m["stops"]:
            coords.append("%.5f,%.5f,%.0f" % (s["lon"], s["lat"], T.elev(s["lat"], s["lon"])))
    placemarks = []
    for s in m["stops"]:
        placemarks.append(
            "    <Placemark><name>%d. %s</name><description>%s</description>"
            "<Point><coordinates>%.5f,%.5f</coordinates></Point></Placemark>"
            % (s["ord"], s["activity"], s["reason"] or "advisory stop [SIM]",
               s["lon"], s["lat"]))
    kml_doc = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
  <name>%s</name>
  <description>%s | NAM mission plan [SIM] - advisory; coordinates east 0-360</description>
  <Placemark><name>%s route</name><LineString><tessellate>1</tessellate><coordinates>
    %s
  </coordinates></LineString></Placemark>
%s
</Document></kml>""" % (m["name"], m.get("objective") or "", m["name"],
                        "\n    ".join(coords), "\n".join(placemarks))
    return kml_doc


def compare(mid_a, mid_b):
    a, b = get(mid_a), get(mid_b)
    if not a or not b:
        return None
    def stats(m):
        r = m["routes"][0] if m["routes"] else None
        return {"stops": len(m["stops"]), "length_km": (r or {}).get("length_km"),
                "est_sols": ((r or {}).get("stats") or {}).get("est_traverse_sols"),
                "type": m["type"]}
    return {"a": {"id": a["id"], **stats(a)}, "b": {"id": b["id"], **stats(b)},
            "provenance": {"source": "NAM mission comparison [SIM]"}}


def delete(mid):
    db.ex("DELETE FROM mission_stops WHERE mission_id=?", (mid,))
    db.ex("DELETE FROM routes WHERE mission_id=?", (mid,))
    db.ex("DELETE FROM missions WHERE id=?", (mid,))
    return True


def annotate(mid, note):
    db.ex("UPDATE missions SET notes=? WHERE id=?", (note, mid))
    return get(mid)
