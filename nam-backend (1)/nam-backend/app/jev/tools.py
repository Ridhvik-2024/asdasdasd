"""The full 24-tool JEV registry with typed JSON schemas and fail-closed
argument validation. Deterministic services compute; the model decides."""
from .. import environment, missions, nodes, resources, routing, seeds, terrain
from ..integrity import SIM, prov
from ..mars import hav_km

T = terrain.engine()


def _s(props, req=None):
    d = {"type": "object", "properties": props, "additionalProperties": False}
    if req:
        d["required"] = req
    return d


TOOLS = [
    {"name": "search_planetary_location", "description": "Search the Mars gazetteer by name, type, tags or raw coordinates (lat,lon).",
     "parameters": _s({"q": {"type": "string"}, "type": {"type": "string"}, "limit": {"type": "integer"}}, ["q"])},
    {"name": "get_current_map_context", "description": "Read the client camera state, visible layers and picked object, enriched with server-side context (elevation, region, nearest features).",
     "parameters": _s({})},
    {"name": "search_nasa_datasets", "description": "Search the catalog of NASA/USGS/Caltech datasets and connectors by topic.",
     "parameters": _s({"topic": {"type": "string"}}, ["topic"])},
    {"name": "get_location_observations", "description": "Scientific observations and discoveries near a location, with citations.",
     "parameters": _s({"lat": {"type": "number"}, "lon": {"type": "number"}, "radius_km": {"type": "number"}}, ["lat", "lon"])},
    {"name": "activate_map_layer", "description": "Return a client directive to activate a science/imagery layer by id.",
     "parameters": _s({"layer_id": {"type": "string"}}, ["layer_id"])},
    {"name": "compare_geological_layers", "description": "Compare two map layers over an optional bbox.",
     "parameters": _s({"layer_a": {"type": "string"}, "layer_b": {"type": "string"}, "bbox": {"type": "array", "items": {"type": "number"}}}, ["layer_a", "layer_b"])},
    {"name": "get_elevation_profile", "description": "Elevation profile along a polyline of [lat,lon] points.",
     "parameters": _s({"points": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}}, "samples": {"type": "integer"}}, ["points"])},
    {"name": "analyze_terrain", "description": "Terrain statistics for a bbox [min_lat,min_lon,max_lat,max_lon]: elevation range, slope, roughness, hazard.",
     "parameters": _s({"bbox": {"type": "array", "items": {"type": "number"}}}, ["bbox"])},
    {"name": "identify_hazards", "description": "Identify terrain and environmental hazards around a point.",
     "parameters": _s({"lat": {"type": "number"}, "lon": {"type": "number"}, "radius_km": {"type": "number"}})},
    {"name": "find_scientific_targets", "description": "Rank scientific targets (cited observations, POVs, water, shelters) near a point.",
     "parameters": _s({"lat": {"type": "number"}, "lon": {"type": "number"}, "radius_km": {"type": "number"}})},
    {"name": "create_mission", "description": "Create a mission (route|area|evacuation|survey) with ordered stops.",
     "parameters": _s({"type": {"type": "string", "enum": ["route", "area", "evacuation", "survey"]},
                       "name": {"type": "string"}, "objective": {"type": "string"},
                       "stops": {"type": "array"}}, ["type", "name"])},
    {"name": "generate_route", "description": "Terrain-aware A* route between two [lat,lon] points with a cost preset (balanced|terrain|speed).",
     "parameters": _s({"from": {"type": "array", "items": {"type": "number"}},
                       "to": {"type": "array", "items": {"type": "number"}},
                       "preset": {"type": "string", "enum": ["balanced", "terrain", "speed"]}}, ["from", "to"])},
    {"name": "optimize_route", "description": "Order a mission's stops into an efficient route.",
     "parameters": _s({"mission_id": {"type": "string"}, "preset": {"type": "string"}}, ["mission_id"])},
    {"name": "add_waypoint", "description": "Add a waypoint to an existing mission.",
     "parameters": _s({"mission_id": {"type": "string"}, "lat": {"type": "number"}, "lon": {"type": "number"}}, ["mission_id", "lat", "lon"])},
    {"name": "explain_route", "description": "Explain a stored mission route: terrain stats, stops with reasons, provenance.",
     "parameters": _s({"mission_id": {"type": "string"}}, ["mission_id"])},
    {"name": "export_mission", "description": "Export a mission as KML (opens in Google Earth Mars mode).",
     "parameters": _s({"mission_id": {"type": "string"}}, ["mission_id"])},
    {"name": "add_node", "description": "Create a spatial node (waypoint|hazard|water|shelter|observation|mission|annotation|panorama_pov).",
     "parameters": _s({"type": {"type": "string"}, "lat": {"type": "number"}, "lon": {"type": "number"},
                       "radius_km": {"type": "number"}, "props": {"type": "object"}}, ["type", "lat", "lon"])},
    {"name": "add_stop", "description": "Add an ordered stop with an activity and a stated reason to a mission.",
     "parameters": _s({"mission_id": {"type": "string"}, "lat": {"type": "number"}, "lon": {"type": "number"},
                       "activity": {"type": "string"}, "reason": {"type": "string"}}, ["mission_id", "lat", "lon"])},
    {"name": "plan_area", "description": "Create an area mission over a bbox with an objective.",
     "parameters": _s({"name": {"type": "string"}, "bbox": {"type": "array", "items": {"type": "number"}},
                       "objective": {"type": "string"}}, ["name", "bbox"])},
    {"name": "plan_storm_response", "description": "Plan an evacuation/response: route with at least two reasoned stops (water cache, shelter pickup) plus a radiation estimate [SIM].",
     "parameters": _s({"lat": {"type": "number"}, "lon": {"type": "number"},
                       "severity": {"type": "string"}, "destination": {"type": "array", "items": {"type": "number"}}}, ["lat", "lon"])},
    {"name": "find_water", "description": "SWIM-consistent water-ice candidates near a point (certainty classes, depth-to-ice, stability).",
     "parameters": _s({"lat": {"type": "number"}, "lon": {"type": "number"},
                       "radius_km": {"type": "number"}, "min_certainty": {"type": "string"}})},
    {"name": "find_shelter", "description": "Scored shelter candidates near a point (shielding, thermal, access, composite index).",
     "parameters": _s({"lat": {"type": "number"}, "lon": {"type": "number"}, "radius_km": {"type": "number"}})},
    {"name": "assess_radiation", "description": "Estimate GCR + SEP dose for a stay (RAD-anchored) [SIM].",
     "parameters": _s({"lat": {"type": "number"}, "lon": {"type": "number"},
                       "duration_sols": {"type": "number"}, "shielding": {"type": "string", "enum": ["suit", "hab", "none"]}}, ["lat", "lon"])},
    {"name": "simulate_storm", "description": "Simulate a dust storm (local|regional|ped|my34) or SEP event (M|X) [SIM].",
     "parameters": _s({"kind": {"type": "string", "enum": ["dust", "sep"]},
                       "scale_or_class": {"type": "string"},
                       "lat": {"type": "number"}, "lon": {"type": "number"}}, ["kind"])},
]

TOOL_INDEX = {t["name"]: t for t in TOOLS}


def _validate(name, args):
    spec = TOOL_INDEX.get(name)
    if not spec:
        return "unknown tool"
    params = spec["parameters"]
    for r in params.get("required", []):
        if r not in args:
            return "missing required argument: %s" % r
    types = {"string": str, "number": (int, float), "integer": int,
             "array": list, "object": dict, "boolean": bool}
    for k, v in args.items():
        ps = params.get("properties", {}).get(k)
        tname = (ps or {}).get("type")
        if tname in types and not isinstance(v, types[tname]):
            return "argument %s must be %s" % (k, tname)
    return None


def run_tool(name, args, ctx=None):
    """Execute a tool; fail closed on schema violations."""
    if name not in TOOL_INDEX:
        return {"error": "unknown_tool", "detail": "tool not registered", "fail_closed": True}
    err = _validate(name, args)
    if err:
        return {"error": "invalid_arguments", "detail": err, "fail_closed": True}
    ctx = ctx or {}
    try:
        return _dispatch(name, args, ctx)
    except Exception as e:
        return {"error": "tool_execution_failed", "detail": "%s: %s" % (type(e).__name__, e)}


def _dispatch(name, a, ctx):
    if name == "search_planetary_location":
        return {"results": seeds.search(a["q"], type_=a.get("type"), limit=min(a.get("limit") or 8, 20))}
    if name == "get_current_map_context":
        return _map_context(ctx)
    if name == "search_nasa_datasets":
        topic = a["topic"].lower()
        hits = [d for d in seeds.datasets()
                if topic in (d["name"] + " " + d["org"] + " " + (d.get("note") or "")).lower()]
        return {"datasets": hits or seeds.datasets()[:5], "provenance": prov(source="NAM dataset catalog (PDS/USGS/Caltech published entries)")}
    if name == "get_location_observations":
        obs = seeds.observations(lat=a["lat"], lon=a["lon"], radius_km=a.get("radius_km", 400))
        return {"observations": obs, "provenance": prov(source="cited discovery catalog")}
    if name == "activate_map_layer":
        lay = seeds.layer(a["layer_id"])
        if not lay:
            return {"error": "unknown_layer", "layer_id": a["layer_id"]}
        return {"intent": {"action": "activate_layer", "layer_id": lay["id"]}, "layer": lay,
                "provenance": prov(source=lay["source"], url=lay.get("url"))}
    if name == "compare_geological_layers":
        la, lb = seeds.layer(a["layer_a"]), seeds.layer(a["layer_b"])
        stats = T.bbox_stats(tuple(a["bbox"])) if a.get("bbox") and len(a["bbox"]) == 4 else None
        return {"layer_a": la, "layer_b": lb, "bbox_stats": stats,
                "provenance": prov(source="NAM layer comparison over demo terrain [SIM]")}
    if name == "get_elevation_profile":
        pts = [{"lat": p[0], "lon": p[1]} for p in a["points"]]
        return T.profile(pts, samples=a.get("samples", 160))
    if name == "analyze_terrain":
        st = T.bbox_stats(tuple(a["bbox"]))
        st["provenance"] = prov(source="terrain analysis over demo grid [SIM]",
                                note="production: MOLA 4 ppd + HiRISE DTMs")
        return st
    if name == "identify_hazards":
        lat, lon = a.get("lat"), a.get("lon")
        if lat is None:
            lat, lon = 0.0, 0.0
        st = T.bbox_stats((lat - 1, lon - 1, lat + 1, lon + 1))
        hazards = []
        if st["max_slope_deg"] > 25:
            hazards.append("steep slopes up to %.1f deg [SIM]" % st["max_slope_deg"])
        if st["mean_elev_m"] > 8000:
            hazards.append("high-altitude site: thin atmosphere, higher radiation [SIM]")
        storms = environment.active_storms()
        for s in storms:
            hazards.append("active simulated %s: %s" % (s["kind"], s["label"]))
        return {"hazards": hazards or ["no major terrain hazards identified in this patch [SIM]"],
                "terrain": st, "provenance": prov(source="NAM hazard identification [SIM]")}
    if name == "find_scientific_targets":
        lat, lon = a["lat"], a["lon"]
        radius = a.get("radius_km", 500)
        targets = []
        for o in seeds.observations(lat=lat, lon=lon, radius_km=radius, limit=6):
            targets.append({"kind": "cited_discovery", "id": o["id"], "title": o["title"],
                            "distance_km": o.get("distance_km"), "citation": o["evidence"]["citation"]})
        for p in seeds.pov_library():
            d = hav_km(lat, lon, p["lat"], p["lon"])
            if d <= radius:
                targets.append({"kind": "pov", "id": p["id"], "title": p["name"], "distance_km": round(d, 1)})
        return {"targets": targets, "provenance": prov(source="NAM scientific target ranking (cited evidence)")}
    if name == "create_mission":
        m = missions.create(a["type"], a["name"], a.get("objective"), a.get("stops"))
        return {"mission": m, "provenance": m["provenance"]}
    if name == "generate_route":
        r = routing.plan_route(a["from"][0], a["from"][1], a["to"][0], a["to"][1], a.get("preset", "balanced"))
        return r
    if name == "optimize_route":
        m = missions.optimize(a["mission_id"], a.get("preset", "balanced"))
        if not m:
            return {"error": "mission_not_found_or_too_few_stops"}
        return {"mission": m, "provenance": m["provenance"]}
    if name == "add_waypoint":
        m = missions.add_waypoint(a["mission_id"], a["lat"], a["lon"])
        return {"mission": m} if m else {"error": "mission_not_found"}
    if name == "explain_route":
        m = missions.get(a["mission_id"])
        if not m:
            return {"error": "mission_not_found"}
        explanation = ("Mission %s (%s) has %d stops. " % (m["name"], m["type"], len(m["stops"]))
                       + " ".join("Stop %d at (%.2f, %.2f): %s - %s." % (s["ord"], s["lat"], s["lon"], s["activity"], s["reason"] or "no reason stated")
                                  for s in m["stops"]))
        if m["routes"]:
            r = m["routes"][0]
            explanation += " Route: %.1f km, preset %s, est. %.1f sols traverse [SIM]." % (
                r["length_km"] or 0, r["preset"], (r.get("stats") or {}).get("est_traverse_sols", 0))
        return {"mission": m, "explanation": explanation + " " + SIM, "provenance": m["provenance"]}
    if name == "export_mission":
        kml = missions.kml(a["mission_id"])
        if kml is None:
            return {"error": "mission_not_found"}
        return {"mission_id": a["mission_id"], "format": "kml", "bytes": len(kml.encode()),
                "content": kml, "note": "opens in Google Earth Mars mode (east 0-360 longitudes)"}
    if name == "add_node":
        n = nodes.create(a["type"], a["lat"], a["lon"], a.get("radius_km"), a.get("props"), created_by="jev")
        return {"node": n}
    if name == "add_stop":
        m = missions.add_stop(a["mission_id"], a["lat"], a["lon"], a.get("activity", "observe"), a.get("reason", ""))
        return {"mission": m} if m else {"error": "mission_not_found"}
    if name == "plan_area":
        bbox = a["bbox"]
        m = missions.create("area", a["name"], a.get("objective"),
                            [{"lat": bbox[0], "lon": bbox[1]}, {"lat": bbox[2], "lon": bbox[3]}])
        st = T.bbox_stats(tuple(bbox))
        return {"mission": m, "area_terrain": st, "provenance": m["provenance"]}
    if name == "plan_storm_response":
        dest = a.get("destination") or None
        return environment.storm_response(a["lat"], a["lon"], destination=dest, severity=a.get("severity", "M"))
    if name == "find_water":
        return {"candidates": resources.find_water(near={"lat": a.get("lat", 0), "lon": a.get("lon", 0)},
                                                   radius_km=a.get("radius_km", 1500),
                                                   min_certainty=a.get("min_certainty")),
                "provenance": prov(source="SWIM-consistent candidates (swim.psi.edu)")}
    if name == "find_shelter":
        return {"shelters": resources.find_shelter(near={"lat": a.get("lat", 0), "lon": a.get("lon", 0)},
                                                   radius_km=a.get("radius_km", 1500)),
                "provenance": prov(source="NAM curated shelter set [SIM]")}
    if name == "assess_radiation":
        return environment.radiation(a["lat"], a["lon"], a.get("duration_sols", 1.0),
                                     a.get("shielding", "suit"))
    if name == "simulate_storm":
        scen = environment.simulate_storm(a["kind"], a.get("scale_or_class"), a.get("lat"), a.get("lon"))
        from ..events import hub
        hub.broadcast("events", {"type": "storm_alert", "scenario": scen})
        return scen
    return {"error": "unhandled_tool", "name": name}


def _map_context(ctx):
    mc = ctx.get("map_context") or {}
    center = mc.get("center") or {"lat": 0.0, "lon": 0.0}
    lat, lon = center.get("lat", 0.0), center.get("lon", 0.0)
    st = T.bbox_stats((lat - 0.5, lon - 0.5, lat + 0.5, lon + 0.5))
    near = seeds.nearest(lat, lon, radius_km=250, limit=5)
    obs = seeds.observations(lat=lat, lon=lon, radius_km=300, limit=4)
    layers = [seeds.layer(lid) for lid in (mc.get("layers_active") or [])]
    return {
        "client_context": mc,
        "center_terrain": st,
        "nearest_features": near,
        "nearest_cited_observations": [{"id": o["id"], "title": o["title"], "citation": o["evidence"]["citation"]} for o in obs],
        "active_layers": [l for l in layers if l],
        "provenance": prov(source="map context from client + demo terrain grid [SIM] + gazetteer"),
    }
