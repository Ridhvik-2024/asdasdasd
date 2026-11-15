"""The JEV tool registry with typed JSON schemas and fail-closed
argument + semantic validation. Deterministic services compute; the model decides."""
import math

from .. import environment, missions, nodes, resources, routing, seeds, terrain
from ..integrity import SIM, prov
from ..mars import hav_km, validate_coords

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
     "parameters": _s({"mission_id": {"type": "string"},
                       "preset": {"type": "string", "enum": ["balanced", "terrain", "speed"]}}, ["mission_id"])},
    {"name": "add_waypoint", "description": "Add a waypoint to an existing mission.",
     "parameters": _s({"mission_id": {"type": "string"}, "lat": {"type": "number"}, "lon": {"type": "number"}}, ["mission_id", "lat", "lon"])},
    {"name": "explain_route", "description": "Explain a stored mission route: terrain stats, stops with reasons, provenance.",
     "parameters": _s({"mission_id": {"type": "string"}}, ["mission_id"])},
    {"name": "export_mission", "description": "Export a mission as KML (opens in Google Earth Mars mode).",
     "parameters": _s({"mission_id": {"type": "string"}}, ["mission_id"])},
    {"name": "add_node", "description": "Create a spatial node (waypoint|hazard|water|shelter|observation|mission|annotation|panorama_pov).",
     "parameters": _s({"type": {"type": "string", "enum": list(nodes.NODE_TYPES)},
                       "lat": {"type": "number"}, "lon": {"type": "number"},
                       "radius_km": {"type": "number"}, "props": {"type": "object"}}, ["type", "lat", "lon"])},
    {"name": "add_stop", "description": "Add an ordered stop with an activity and a stated reason to a mission.",
     "parameters": _s({"mission_id": {"type": "string"}, "lat": {"type": "number"}, "lon": {"type": "number"},
                       "activity": {"type": "string"}, "reason": {"type": "string"}}, ["mission_id", "lat", "lon"])},
    {"name": "plan_area", "description": "Create an area mission over a bbox with an objective.",
     "parameters": _s({"name": {"type": "string"}, "bbox": {"type": "array", "items": {"type": "number"}},
                       "objective": {"type": "string"}}, ["name", "bbox"])},
    {"name": "plan_storm_response", "description": "Plan an evacuation/response: route with at least two reasoned stops (water cache, shelter pickup) plus a radiation estimate [SIM].",
     "parameters": _s({"lat": {"type": "number"}, "lon": {"type": "number"},
                       "severity": {"type": "string"},
                       "destination": {"oneOf": [
                           {"type": "array", "items": {"type": "number"}},
                           {"type": "object",
                            "properties": {"lat": {"type": "number"}, "lon": {"type": "number"}},
                            "required": ["lat", "lon"], "additionalProperties": False},
                       ]}}, ["lat", "lon"])},
    {"name": "find_water", "description": "SWIM-consistent water-ice candidates globally, near a point, or within a bbox (certainty classes, depth-to-ice, stability).",
     "parameters": _s({"lat": {"type": "number"}, "lon": {"type": "number"},
                       "radius_km": {"type": "number"},
                       "bbox": {"type": "array", "items": {"type": "number"}},
                       "min_certainty": {"type": "string", "enum": ["A", "B", "C"]}})},
    {"name": "find_shelter", "description": "Scored shelter candidates globally, near a point, or within a bbox (shielding, thermal, access, composite index).",
     "parameters": _s({"lat": {"type": "number"}, "lon": {"type": "number"},
                       "radius_km": {"type": "number"},
                       "bbox": {"type": "array", "items": {"type": "number"}}})},
    {"name": "assess_radiation", "description": "Estimate GCR + SEP dose for a stay (RAD-anchored) [SIM].",
     "parameters": _s({"lat": {"type": "number"}, "lon": {"type": "number"},
                       "duration_sols": {"type": "number"}, "shielding": {"type": "string", "enum": ["suit", "hab", "none"]}}, ["lat", "lon"])},
    {"name": "simulate_storm", "description": "Simulate a dust storm (local|regional|ped|my34) or SEP event (M|X) [SIM].",
     "parameters": _s({"kind": {"type": "string", "enum": ["dust", "sep"]},
                       "scale_or_class": {"type": "string"},
                       "lat": {"type": "number"}, "lon": {"type": "number"}}, ["kind"])},
]

# Route decisions are deterministic; the configured model can extract literal
# place names but cannot supply route geometry or resource coordinates.
TOOLS.append({
    "name": "plan_resource_route",
    "description": "Plan an advisory Mars route between named places, considering water and shelter candidates, synthetic terrain, and radiation [SIM].",
    "parameters": _s({"message": {"type": "string"},
                      "places": {"type": "array", "items": {"type": "string"}},
                      "preference": {"type": "string", "enum": ["none", "water", "shelter", "both"]},
                      "max_detour_km": {"type": "number"},
                      "speed_km_sol": {"type": "number"},
                      "preset": {"type": "string", "enum": ["balanced", "terrain", "speed"]}}),
})

TOOL_INDEX = {t["name"]: t for t in TOOLS}


def _is_num(v):
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(float(v))


def _is_int(v):
    return not isinstance(v, bool) and isinstance(v, int)


def _validate_schema_value(val, schema, path):
    """Recursive JSON-schema validator (types, bool/int separation, enums,
    oneOf, nested arrays, and additionalProperties=False)."""
    if "oneOf" in (schema or {}):
        errs = [_validate_schema_value(val, sub, path) for sub in schema["oneOf"]]
        if all(e is not None for e in errs):
            return "argument %s did not match allowed schema (%s)" % (path, "; ".join(errs))
        return None
    tname = (schema or {}).get("type")
    if tname == "string":
        if not isinstance(val, str):
            return "argument %s must be string" % path
    elif tname == "number":
        if not _is_num(val):
            return "argument %s must be a finite number" % path
    elif tname == "integer":
        if not _is_int(val):
            return "argument %s must be integer" % path
    elif tname == "boolean":
        if not isinstance(val, bool):
            return "argument %s must be boolean" % path
    elif tname == "array":
        if not isinstance(val, list):
            return "argument %s must be array" % path
        item_schema = schema.get("items")
        if item_schema:
            for idx, item in enumerate(val):
                err = _validate_schema_value(item, item_schema, "%s[%d]" % (path, idx))
                if err:
                    return err
    elif tname == "object":
        if not isinstance(val, dict):
            return "argument %s must be object" % path
        props = schema.get("properties")
        if props is not None:
            for r in schema.get("required", []):
                if r not in val:
                    return "missing required argument: %s" % (r if not path else "%s.%s" % (path, r))
            if schema.get("additionalProperties") is False:
                for k in val:
                    if k not in props:
                        return "unexpected argument: %s" % (k if not path else "%s.%s" % (path, k))
            for k, v in val.items():
                if k in props:
                    err = _validate_schema_value(v, props[k], k if not path else "%s.%s" % (path, k))
                    if err:
                        return err
    if "enum" in (schema or {}) and val not in schema["enum"]:
        return "argument %s must be one of %s" % (path, "|".join(str(x) for x in schema["enum"]))
    return None


def _validate_semantics(name, args):
    """Domain/semantic validation for Mars coordinates, bboxes, points, and bounds."""
    if "lat" in args and (args["lat"] < -90.0 or args["lat"] > 90.0):
        return "argument lat must be in [-90, 90]"
    if "radius_km" in args and args["radius_km"] <= 0:
        return "argument radius_km must be > 0"
    if "duration_sols" in args and args["duration_sols"] <= 0:
        return "argument duration_sols must be > 0"
    if "limit" in args and args["limit"] < 1:
        return "argument limit must be >= 1"
    if "samples" in args and args["samples"] < 2:
        return "argument samples must be >= 2"
    if "bbox" in args:
        bb = args["bbox"]
        if len(bb) != 4:
            return "argument bbox must have 4 elements [min_lat, min_lon, max_lat, max_lon]"
        if bb[0] < -90.0 or bb[0] > 90.0 or bb[2] < -90.0 or bb[2] > 90.0:
            return "argument bbox latitudes must be in [-90, 90]"
    for pair_key in ("from", "to", "destination"):
        if pair_key in args:
            pt = args[pair_key]
            if isinstance(pt, dict):
                if "lat" not in pt or "lon" not in pt:
                    return "argument %s must contain lat and lon" % pair_key
                if not _is_num(pt["lat"]) or not _is_num(pt["lon"]):
                    return "argument %s lat/lon must be finite numbers" % pair_key
                if pt["lat"] < -90.0 or pt["lat"] > 90.0:
                    return "argument %s.lat must be in [-90, 90]" % pair_key
            else:
                if len(pt) != 2:
                    return "argument %s must be [lat, lon]" % pair_key
                if pt[0] < -90.0 or pt[0] > 90.0:
                    return "argument %s[0] (lat) must be in [-90, 90]" % pair_key
    if "points" in args:
        pts = args["points"]
        if len(pts) < 2:
            return "argument points must contain at least 2 [lat, lon] pairs"
        for idx, pt in enumerate(pts):
            if len(pt) != 2:
                return "argument points[%d] must be [lat, lon]" % idx
            if pt[0] < -90.0 or pt[0] > 90.0:
                return "argument points[%d][0] (lat) must be in [-90, 90]" % idx
    if "stops" in args:
        for idx, st in enumerate(args["stops"]):
            if not isinstance(st, dict) or "lat" not in st or "lon" not in st:
                return "argument stops[%d] must be an object with lat and lon" % idx
            if not _is_num(st["lat"]) or not _is_num(st["lon"]):
                return "argument stops[%d] lat/lon must be finite numbers" % idx
            if st["lat"] < -90.0 or st["lat"] > 90.0:
                return "argument stops[%d].lat must be in [-90, 90]" % idx
    for non_empty in ("q", "topic", "layer_id", "layer_a", "layer_b", "name", "mission_id"):
        if non_empty in args and not args[non_empty].strip():
            return "argument %s must be non-empty" % non_empty
    return None


def validate_tool_call(name, args):
    """Validate a tool name and argument dict against JSON schema + Mars semantics.
    Returns None when valid, or an error string describing the violation."""
    spec = TOOL_INDEX.get(name)
    if not spec:
        return "unknown tool"
    if not isinstance(args, dict):
        return "tool arguments must be an object"
    err = _validate_schema_value(args, spec["parameters"], "")
    if err:
        return err
    return _validate_semantics(name, args)


def _validate(name, args):
    return validate_tool_call(name, args)


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
        missing = [lid for lid, obj in ((a["layer_a"], la), (a["layer_b"], lb)) if not obj]
        if missing:
            return {
                "error": "unknown_layer",
                "missing_layers": missing,
                "detail": "unknown layer id(s): %s" % ", ".join(missing),
            }
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
        mc_center = (ctx.get("map_context") or {}).get("center") or {}
        lat = a.get("lat")
        lon = a.get("lon")
        if lat is None:
            lat = mc_center.get("lat", 0.0)
        if lon is None:
            lon = mc_center.get("lon", 0.0)
        st = T.bbox_stats((max(-90.0, lat - 1), lon - 1, min(90.0, lat + 1), lon + 1))
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
        mc_center = (ctx.get("map_context") or {}).get("center") or {}
        lat = a.get("lat") if a.get("lat") is not None else mc_center.get("lat", 0.0)
        lon = a.get("lon") if a.get("lon") is not None else mc_center.get("lon", 0.0)
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
    if name == "plan_resource_route":
        from . import resource_route
        return resource_route.plan(places=a.get("places"), message=a.get("message", ""),
                                   preference=a.get("preference", "both"),
                                   max_detour_km=a.get("max_detour_km", 250),
                                   speed_km_sol=a.get("speed_km_sol", 0.12),
                                   preset=a.get("preset", "balanced"),
                                   use_model=bool(a.get("message")))
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
            r = m["routes"][-1]
            st = r.get("stats") or {}
            preset = r.get("preset") or st.get("cost_preset") or "balanced"
            length_km = r.get("length_km")
            if length_km is None:
                length_km = st.get("length_km")
            est_sols = st.get("est_traverse_sols")
            is_degraded = (
                r.get("status") == "degraded"
                or st.get("status") == "degraded"
                or bool(st.get("degraded"))
            )
            degraded_legs = st.get("degraded_legs") or 0
            total_legs = st.get("total_legs") or 0
            if is_degraded or length_km is None:
                note = st.get("note") or r.get("note") or "no in-grid route found"
                explanation += (
                    " Route (degraded, preset %s): no complete in-grid route (%s) [SIM]."
                    % (preset, note)
                )
            else:
                parts = ["%.1f km" % length_km, "preset %s" % preset]
                if est_sols is not None:
                    parts.append("est. %.1f sols traverse" % est_sols)
                else:
                    leg_sols = [
                        lg["est_sols"] for lg in (st.get("legs") or [])
                        if isinstance(lg, dict) and lg.get("est_sols") is not None
                    ]
                    if leg_sols:
                        parts.append("est. %.1f sols traverse" % sum(leg_sols))
                    else:
                        parts.append("est. traverse sols unavailable")
                if degraded_legs > 0:
                    parts.append("%d of %d leg(s) degraded" % (degraded_legs, total_legs))
                explanation += " Route: %s [SIM]." % ", ".join(parts)
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
        raw_dest = a.get("destination")
        dest = None
        if raw_dest is not None:
            if isinstance(raw_dest, dict):
                dlat, dlon = validate_coords(raw_dest["lat"], raw_dest["lon"])
            else:
                dlat, dlon = validate_coords(raw_dest[0], raw_dest[1])
            dest = {"lat": dlat, "lon": dlon}
        return environment.storm_response(a["lat"], a["lon"], destination=dest, severity=a.get("severity", "M"))
    if name == "find_water":
        near = ({"lat": a["lat"], "lon": a["lon"]}
                if (a.get("lat") is not None and a.get("lon") is not None) else None)
        bbox = tuple(a["bbox"]) if a.get("bbox") is not None else None
        return {"candidates": resources.find_water(bbox=bbox, near=near,
                                                   radius_km=a.get("radius_km", 1500),
                                                   min_certainty=a.get("min_certainty")),
                "provenance": prov(source="SWIM-consistent candidates (swim.psi.edu)")}
    if name == "find_shelter":
        near = ({"lat": a["lat"], "lon": a["lon"]}
                if (a.get("lat") is not None and a.get("lon") is not None) else None)
        bbox = tuple(a["bbox"]) if a.get("bbox") is not None else None
        return {"shelters": resources.find_shelter(bbox=bbox, near=near,
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
