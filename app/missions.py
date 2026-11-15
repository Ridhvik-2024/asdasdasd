"""Mission planning suite: route/area/evacuation/survey with ordered stops,
KML/GeoJSON/CSV export, optimization and comparison. All generated plans are advisory."""
import csv
import io
import uuid
from xml.sax.saxutils import escape as _xml_escape

from . import db, routing
from .integrity import SIM
from .mars import hav_km, validate_coords

MISSION_TYPES = ("route", "area", "evacuation", "survey")
_XML_ENTITIES = {'"': "&quot;", "'": "&apos;"}


def _esc(val):
    return _xml_escape("" if val is None else str(val), _XML_ENTITIES)


def create(mtype, name, objective=None, stops=None):
    if mtype not in MISSION_TYPES:
        raise ValueError("type must be one of route|area|evacuation|survey")
    if not str(name or "").strip():
        raise ValueError("mission name must be non-empty")
    validated_stops = []
    for s in (stops or []):
        lat, lon = validate_coords(s["lat"], s["lon"])
        validated_stops.append({
            "lat": lat,
            "lon": lon,
            "activity": s.get("activity", "observe"),
            "reason": s.get("reason", ""),
        })
    mid = "mission-" + uuid.uuid4().hex[:8]
    with db.tx():
        db.ex("INSERT INTO missions (id,type,name,objective,advisory) VALUES (?,?,?,?,1)",
              (mid, mtype, str(name).strip(), objective or ""))
        for i, s in enumerate(validated_stops):
            db.ex("INSERT INTO mission_stops (mission_id,ord,lat,lon,activity,reason) VALUES (?,?,?,?,?,?)",
                  (mid, i + 1, s["lat"], s["lon"], s["activity"], s["reason"]))
    return get(mid)


def add_stop(mid, lat, lon, activity="observe", reason="", ord_=None):
    lat, lon = validate_coords(lat, lon)
    with db.tx():
        rows = db.q("SELECT id FROM missions WHERE id=?", (mid,))
        if not rows:
            return None
        if ord_ is None:
            nxt = db.q("SELECT COALESCE(MAX(ord),0)+1 AS nxt FROM mission_stops WHERE mission_id=?", (mid,))
            ord_ = nxt[0]["nxt"]
        db.ex("INSERT INTO mission_stops (mission_id,ord,lat,lon,activity,reason) VALUES (?,?,?,?,?,?)",
              (mid, int(ord_), lat, lon, activity, reason))
    return get(mid)


def add_waypoint(mid, lat, lon):
    return add_stop(mid, lat, lon, activity="waypoint", reason="routed waypoint")


def get(mid):
    rows = db.q("SELECT * FROM missions WHERE id=?", (mid,))
    if not rows:
        return None
    m = rows[0]
    stops = db.q("SELECT * FROM mission_stops WHERE mission_id=? ORDER BY ord, id", (mid,))
    routes = db.q("SELECT id,preset,length_km,stats_json,path_json,created FROM routes WHERE mission_id=? ORDER BY rowid", (mid,))
    return {
        "id": m["id"], "type": m["type"], "name": m["name"], "objective": m["objective"],
        "status": m["status"], "notes": m["notes"],
        "advisory": bool(m["advisory"]),
        "advisory_label": "Simulated plan - advisory only " + SIM,
        "stops": [{"ord": s["ord"], "lat": s["lat"], "lon": s["lon"],
                   "activity": s["activity"], "reason": s["reason"]} for s in stops],
        "routes": [{"id": r["id"], "preset": r["preset"], "length_km": r["length_km"],
                    "stats": db.uj(r["stats_json"], {}), "path": db.uj(r["path_json"], []),
                    "created": r["created"]} for r in routes],
        "provenance": {"source": "NAM mission planner [SIM] - validated plan object with provenance"},
    }


def list_missions():
    rows = db.q("SELECT id,type,name,status,created FROM missions ORDER BY created DESC")
    return rows


def attach_route(mid, route, preset="balanced"):
    rid = "route-" + uuid.uuid4().hex[:8]
    if route.get("status") == "degraded":
        base_stats = route.get("stats") or {}
        stats = {
            **base_stats,
            "length_km": None,
            "status": "degraded",
            "degraded": True,
            "note": route.get("note", "degraded fallback"),
        }
        length_km = None
    else:
        stats = route.get("stats") or {}
        length_km = stats.get("length_km")
    with db.tx():
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


def _two_opt_open_path(order):
    """Improve an open-path tour (anchored at order[0]) via 2-opt segment reversals."""
    n = len(order)
    if n < 4:
        return order

    def _path_len(seq):
        return sum(
            hav_km(seq[k]["lat"], seq[k]["lon"], seq[k + 1]["lat"], seq[k + 1]["lon"])
            for k in range(len(seq) - 1)
        )

    best = list(order)
    best_d = _path_len(best)
    improved = True
    while improved:
        improved = False
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                cand = best[:i] + list(reversed(best[i:j + 1])) + best[j + 1:]
                d = _path_len(cand)
                if d + 1e-6 < best_d:
                    best, best_d = cand, d
                    improved = True
    return best


def optimize(mid, preset="balanced"):
    """Nearest-neighbor + 2-opt tour ordering of stops over A* leg lengths.

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
            d = hav_km(cur["lat"], cur["lon"], s["lat"], s["lon"])
            if bd is None or d < bd:
                best, bd = s, d
        order.append(best)
        remaining.remove(best)
    order = _two_opt_open_path(order)

    length = 0.0
    legs = []
    degraded_legs = 0
    for i in range(len(order) - 1):
        a, b = order[i], order[i + 1]
        leg = routing.plan_route(a["lat"], a["lon"], b["lat"], b["lon"], preset)
        leg_stats = leg.get("stats") or {}
        if leg.get("status") == "degraded" or leg_stats.get("length_km") is None:
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
        leg_len = leg_stats.get("length_km")
        length += leg_len
        legs.append({
            "from": [a["lat"], a["lon"]],
            "to": [b["lat"], b["lon"]],
            "length_km": leg_len,
            "est_sols": leg_stats.get("est_traverse_sols"),
        })

    rid = "route-" + uuid.uuid4().hex[:8]
    total_length = round(length, 2) if degraded_legs < len(legs) else None
    stats = {
        "length_km": total_length,
        "cost_preset": preset,
        "legs": legs,
        "optimized": True,
        "degraded_legs": degraded_legs,
        "total_legs": len(legs),
    }
    with db.tx():
        db.ex("DELETE FROM mission_stops WHERE mission_id=?", (mid,))
        for i, s in enumerate(order):
            db.ex("INSERT INTO mission_stops (mission_id,ord,lat,lon,activity,reason) VALUES (?,?,?,?,?,?)",
                  (mid, i + 1, s["lat"], s["lon"], s["activity"], s["reason"]))
        db.ex("INSERT INTO routes (id,mission_id,preset,length_km,stats_json,path_json) VALUES (?,?,?,?,?,?)",
              (rid, mid, preset, total_length, db.j(stats), db.j(order)))
    return get(mid)


def kml(mid):
    """Export mission as valid XML/KML 2.2 with escaped user strings."""
    m = get(mid)
    if not m:
        return None
    from . import terrain
    T = terrain.engine().ensure()
    coords = []
    if m["routes"]:
        path = db.uj(db.q("SELECT path_json FROM routes WHERE mission_id=? ORDER BY rowid DESC LIMIT 1",
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
            % (s["ord"], _esc(s["activity"]), _esc(s["reason"] or "advisory stop [SIM]"),
               s["lon"], s["lat"]))
    safe_name = _esc(m["name"])
    safe_obj = _esc(m.get("objective") or "")
    kml_doc = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
  <name>%s</name>
  <description>%s | NAM mission plan [SIM] - advisory; coordinates east 0-360</description>
  <Placemark><name>%s route</name><LineString><tessellate>1</tessellate><coordinates>
    %s
  </coordinates></LineString></Placemark>
%s
</Document></kml>""" % (safe_name, safe_obj, safe_name,
                        "\n    ".join(coords), "\n".join(placemarks))
    return kml_doc


def geojson(mid):
    """Export mission stops and latest route path as a GeoJSON FeatureCollection."""
    m = get(mid)
    if not m:
        return None
    features = []
    for s in m["stops"]:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
            "properties": {"ord": s["ord"], "activity": s["activity"], "reason": s["reason"]},
        })
    if m["routes"]:
        path = db.uj(db.q("SELECT path_json FROM routes WHERE mission_id=? ORDER BY rowid DESC LIMIT 1",
                          (mid,))[0]["path_json"], [])
        if len(path) >= 2:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[p["lon"], p["lat"]] + ([p["elev_m"]] if "elev_m" in p else []) for p in path],
                },
                "properties": {"mission_id": m["id"], "route_id": m["routes"][-1]["id"],
                               "stats": m["routes"][-1]["stats"]},
            })
    return {
        "type": "FeatureCollection",
        "properties": {"id": m["id"], "name": m["name"], "type": m["type"],
                       "objective": m["objective"], "advisory": True,
                       "crs": "IAU:49900 (Mars east 0-360) [SIM]"},
        "features": features,
    }


def csv_stops(mid):
    """Export ordered mission stops as CSV."""
    m = get(mid)
    if not m:
        return None
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ord", "lat", "lon", "activity", "reason"])
    for s in m["stops"]:
        writer.writerow([s["ord"], s["lat"], s["lon"], s["activity"], s["reason"]])
    return buf.getvalue()


def compare(mid_a, mid_b):
    a, b = get(mid_a), get(mid_b)
    if not a or not b:
        return None
    def stats(m):
        r = m["routes"][-1] if m["routes"] else None
        st = (r or {}).get("stats") or {}
        return {"stops": len(m["stops"]), "length_km": (r or {}).get("length_km"),
                "est_sols": st.get("est_traverse_sols"),
                "mean_slope_deg": st.get("mean_slope_deg"),
                "max_slope_deg": st.get("max_slope_deg"),
                "degraded_legs": st.get("degraded_legs"),
                "type": m["type"]}
    return {"a": {"id": a["id"], **stats(a)}, "b": {"id": b["id"], **stats(b)},
            "provenance": {"source": "NAM mission comparison [SIM]"}}


def delete(mid):
    with db.tx():
        db.ex("DELETE FROM mission_stops WHERE mission_id=?", (mid,))
        db.ex("DELETE FROM routes WHERE mission_id=?", (mid,))
        deleted = db.ex_count("DELETE FROM missions WHERE id=?", (mid,))
    return deleted > 0


def annotate(mid, note):
    db.ex("UPDATE missions SET notes=? WHERE id=?", (note, mid))
    return get(mid)
