"""Environmental analysis and simulation: radiation, SEP, dust storms [SIM].

Anchors: RAD-measured surface GCR at Gale (~0.2 mSv/day dose-equivalent,
Hassler et al. 2014, Science); RAD-observed September 2017 SEP; documented
dust events MY25 2001, MY28 2007, MY34 2018. All derived numbers are [SIM].
"""
import math
import uuid

from . import seeds
from .integrity import with_sim, prov
from .mars import validate_coords, validate_lat, validate_lon

# in-memory simulated scenarios
_SCENARIOS: dict = {}


def _normalize_destination(destination):
    """Normalize destination from [lat, lon] or {'lat': ..., 'lon': ...} with validation."""
    if destination is None:
        return {"lat": 45.0, "lon": 190.0}   # Arcadia Base default refuge
    if isinstance(destination, dict):
        if "lat" not in destination or "lon" not in destination:
            raise ValueError("destination must contain 'lat' and 'lon'")
        dlat, dlon = validate_coords(destination["lat"], destination["lon"])
        return {"lat": dlat, "lon": dlon}
    if isinstance(destination, (list, tuple)):
        if len(destination) != 2:
            raise ValueError("destination must be a 2-element [lat, lon] sequence")
        dlat, dlon = validate_coords(destination[0], destination[1])
        return {"lat": dlat, "lon": dlon}
    raise ValueError("destination must be [lat, lon] or {'lat': ..., 'lon': ...}")


def pressure_pa(elev_m):
    """Simple exponential atmosphere model [SIM]; ~636 Pa at datum."""
    return 636.0 * math.exp(-elev_m / 11100.0)


def radiation(lat, lon, duration_sols=1.0, shielding="suit", storm=None):
    lat, lon = validate_coords(lat, lon)
    if isinstance(duration_sols, bool) or not isinstance(duration_sols, (int, float)):
        raise ValueError("duration_sols must be a finite positive number")
    duration_sols = float(duration_sols)
    if not math.isfinite(duration_sols) or duration_sols <= 0.0:
        raise ValueError("duration_sols must be > 0 (got %r)" % duration_sols)
    from . import terrain
    T = terrain.engine().ensure()
    elev = T.elev(lat, lon)
    p = pressure_pa(elev)
    # anchor: ~0.2 mSv/day dose-equivalent GCR at Gale floor (RAD, Hassler 2014)
    p_gale = pressure_pa(-4500.0)
    gcr = 0.2 * (p_gale / p) ** 0.7
    shield_f = {"suit": 1.0, "hab": 0.45, "none": 1.15}.get(shielding, 1.0)
    gcr *= shield_f
    sep = 0.0
    sep_note = "no active SEP"
    if storm and storm.get("kind") == "sep":
        sev = {"M": {"peak": 0.8, "decay": 0.35}, "X": {"peak": 3.5, "decay": 0.30}}.get(
            storm.get("severity", "M"), {"peak": 0.8, "decay": 0.35})
        for s in range(max(1, int(math.ceil(duration_sols)))):
            sep += sev["peak"] * math.exp(-sev["decay"] * s) * shield_f
        sep_note = "SEP %s-class contribution included [SIM]" % storm.get("severity")
    total = gcr * duration_sols + sep
    return with_sim({
        "lat": lat, "lon": lon, "elevation_m": round(elev, 1),
        "surface_pressure_pa": round(p, 1),
        "gcr_dose_equiv_msv_per_sol": round(gcr, 3),
        "duration_sols": duration_sols, "shielding": shielding,
        "gcr_total_msv": round(gcr * duration_sols, 3),
        "sep_total_msv": round(sep, 3), "sep_note": sep_note,
        "total_msv": round(total, 3),
        "uncertainty_band_pct": 30,
        "anchor": "RAD surface GCR ~0.2 mSv/day at Gale (Hassler et al. 2014, Science); "
                  "Sept 2017 SEP observed by MSL/RAD",
    }, note="dose estimates are advisory [SIM] with +-30 percent band")


def simulate_storm(kind="dust", scale_or_class=None, lat=None, lon=None):
    if lat is not None:
        lat = validate_lat(lat)
    if lon is not None:
        lon = validate_lon(lon)
    kind = (kind or "dust").lower()
    s = str(scale_or_class or "").lower()
    if kind == "dust":
        cfg = {
            "local": {"tau": 1.5, "radius_km": 300, "days": 8,
                      "label": "local dust storm (tau ~1.5)"},
            "regional": {"tau": 3.0, "radius_km": 1800, "days": 25,
                         "label": "regional dust storm (tau ~3)"},
            "ped": {"tau": 4.5, "radius_km": 6000, "days": 60,
                    "label": "planet-encircling dust event"},
            "my34": {"tau": 5.0, "radius_km": 9999, "days": 90,
                     "label": "MY34-class planet-encircling event (2018 analog)"},
        }.get(s or "local", {"tau": 1.5, "radius_km": 300, "days": 8, "label": "local dust storm"})
        scen = {
            "scenario_id": "storm-" + uuid.uuid4().hex[:8],
            "kind": "dust", "scale": s or "local", "label": cfg["label"] + " [SIM]",
            "tau_peak": cfg["tau"], "affected_radius_km": cfg["radius_km"],
            "duration_sols": cfg["days"], "origin": {"lat": lat, "lon": lon},
            "timeline": [
                {"sol": 0, "tau": round(cfg["tau"] * 0.3, 2)},
                {"sol": cfg["days"] // 3, "tau": round(cfg["tau"], 2)},
                {"sol": cfg["days"], "tau": round(cfg["tau"] * 0.2, 2)},
            ],
            "effects": ["solar-array output reduced", "visibility degraded",
                        "dust loading on hardware"],
            "documented_analogs": [e for e in seeds.storms_catalog() if e["kind"] == "dust"],
            "severity_class": "MY34-class" if (s or "") == "my34" else (s or "local"),
        }
    else:  # sep
        sev = "X" if s.startswith("x") else "M"
        scen = {
            "scenario_id": "storm-" + uuid.uuid4().hex[:8],
            "kind": "sep", "severity": sev, "label": "%s-class solar particle event [SIM]" % sev,
            "peak_dose_rate_msv_per_sol": 3.5 if sev == "X" else 0.8,
            "decay_per_sol": 0.3 if sev == "X" else 0.35,
            "origin": {"lat": lat, "lon": lon},
            "documented_analogs": [e for e in seeds.storms_catalog() if e["kind"] == "sep"],
            "severity_class": sev,
        }
    scen = with_sim(scen, note="storm scenario generation is advisory [SIM]")
    _SCENARIOS[scen["scenario_id"]] = scen
    return scen


def radiation_path(points, speed_km_sol=12.0, shielding="suit", storm=None):
    """Integrate RAD-anchored GCR + optional SEP dose along a multi-point path [SIM]."""
    from . import terrain
    from .mars import hav_km
    if not points or len(points) < 2:
        raise ValueError("need at least 2 points for path radiation assessment")
    if isinstance(speed_km_sol, bool) or not isinstance(speed_km_sol, (int, float)) or not math.isfinite(speed_km_sol) or speed_km_sol <= 0:
        raise ValueError("speed_km_sol must be a positive finite number")
    pts = []
    for p in points:
        if isinstance(p, dict):
            lat, lon = validate_coords(p["lat"], p["lon"])
        elif isinstance(p, (list, tuple)) and len(p) == 2:
            lat, lon = validate_coords(p[0], p[1])
        else:
            raise ValueError("each point must be {lat, lon} or [lat, lon]")
        pts.append((lat, lon))
    T = terrain.engine().ensure()
    p_gale = pressure_pa(-4500.0)
    shield_f = {"suit": 1.0, "rover": 0.65, "hab": 0.45, "lava_tube": 0.08, "none": 1.15}.get(shielding, 1.0)
    total_km = 0.0
    total_sols = 0.0
    total_gcr = 0.0
    total_sep = 0.0
    segments = []
    sep_cfg = None
    if storm and storm.get("kind") == "sep":
        sep_cfg = {"M": {"peak": 0.8, "decay": 0.35}, "X": {"peak": 3.5, "decay": 0.30}}.get(
            storm.get("severity", "M"), {"peak": 0.8, "decay": 0.35}
        )
    t_sol = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        d_km = hav_km(a[0], a[1], b[0], b[1])
        dur = max(0.01, d_km / float(speed_km_sol)) if d_km > 0 else 0.0
        mid_lat = 0.5 * (a[0] + b[0])
        # shortest arc midpoint longitude
        dlon = ((b[1] - a[1] + 180.0) % 360.0) - 180.0
        mid_lon = (a[1] + 0.5 * dlon) % 360.0
        elev = T.elev(mid_lat, mid_lon)
        pres = pressure_pa(elev)
        gcr_rate = 0.2 * (p_gale / pres) ** 0.7 * shield_f
        gcr_seg = gcr_rate * dur
        sep_seg = 0.0
        if sep_cfg and dur > 0:
            # integrate peak * exp(-decay * t) dt from t_sol to t_sol + dur
            lam = sep_cfg["decay"]
            sep_seg = (sep_cfg["peak"] * shield_f / lam) * (
                math.exp(-lam * t_sol) - math.exp(-lam * (t_sol + dur))
            )
        t_sol += dur
        total_km += d_km
        total_sols += dur
        total_gcr += gcr_seg
        total_sep += sep_seg
        segments.append({
            "segment": i + 1,
            "length_km": round(d_km, 2),
            "duration_sols": round(dur, 3),
            "mid_elev_m": round(elev, 1),
            "surface_pressure_pa": round(pres, 1),
            "gcr_msv": round(gcr_seg, 4),
            "sep_msv": round(sep_seg, 4),
            "total_msv": round(gcr_seg + sep_seg, 4),
        })
    return with_sim({
        "total_length_km": round(total_km, 2),
        "speed_km_sol": float(speed_km_sol),
        "total_duration_sols": round(total_sols, 3),
        "shielding": shielding,
        "gcr_total_msv": round(total_gcr, 3),
        "sep_total_msv": round(total_sep, 3),
        "total_msv": round(total_gcr + total_sep, 3),
        "uncertainty_band_pct": 30,
        "segments": segments,
        "anchor": "RAD surface GCR ~0.2 mSv/day at Gale (Hassler et al. 2014, Science); "
                  "elevation-scaled exponential atmosphere [SIM]",
    }, note="path dose integration is advisory [SIM] with +-30 percent band")


def classify_storm(kind="dust", tau=None, radius_km=None, peak_msv_sol=None):
    """Deterministic severity classification for dust and SEP events."""
    k = (kind or "dust").lower().strip()
    if k == "dust":
        t = float(tau if tau is not None else 1.5)
        r = float(radius_km if radius_km is not None else 300.0)
        if t >= 4.5 or r >= 5000:
            cls, desc = "MY34-class / planet-encircling", "Global dust event severely attenuating solar power for months."
        elif t >= 2.5 or r >= 1200:
            cls, desc = "regional", "Regional dust storm reducing visibility and solar flux over 1000+ km."
        else:
            cls, desc = "local", "Localized dust storm / frontal plume lasting several sols."
        return with_sim({
            "kind": "dust", "tau": t, "radius_km": r,
            "severity_class": cls, "summary": desc,
            "analogs": [e["name"] for e in seeds.storms_catalog() if e["kind"] == "dust"],
        }, note="severity classification heuristic anchored on MY25/MY28/MY34 [SIM]")
    elif k == "sep":
        p = float(peak_msv_sol if peak_msv_sol is not None else 0.8)
        if p >= 2.5:
            cls, desc = "X-class severe SEP", "Immediate shelter-in-place or rapid evacuation to shielded refuge recommended."
        elif p >= 0.5:
            cls, desc = "M-class moderate SEP", "Elevated particle flux; limit unshielded EVA duration."
        else:
            cls, desc = "minor SEP enhancement", "Low-level energetic particle enhancement; monitor RAD telemetry."
        return with_sim({
            "kind": "sep", "peak_msv_sol": p,
            "severity_class": cls, "summary": desc,
            "analogs": [e["name"] for e in seeds.storms_catalog() if e["kind"] == "sep"],
        }, note="SEP classification heuristic anchored on MSL/RAD Sept 2017 event [SIM]")
    raise ValueError("kind must be 'dust' or 'sep'")


def delete_storm(sid):
    return _SCENARIOS.pop(sid, None) is not None


def storm_by_id(sid):
    return _SCENARIOS.get(sid)


def active_storms():
    return list(_SCENARIOS.values())


def catalog():
    return seeds.storms_catalog()


def storm_response(origin_lat, origin_lon, destination=None, severity="M"):
    """Deterministic storm-response planner: evacuation route + reasoned stops
    (water cache, shelter pickup) + radiation estimate. Used by JEV tool
    plan_storm_response and the mission planner UI. [SIM]"""
    from . import routing, resources, terrain
    from .mars import hav_km
    origin_lat, origin_lon = validate_coords(origin_lat, origin_lon)
    dest = _normalize_destination(destination)
    T = terrain.engine().ensure()
    shelters = resources.find_shelter(near={"lat": origin_lat, "lon": origin_lon}, radius_km=3000)
    water = resources.find_water(near={"lat": origin_lat, "lon": origin_lon}, radius_km=3000)
    shelter_pick = shelters[0] if shelters else None
    water_pick = water[0] if water else None

    stops = []
    waypoints = [{"lat": origin_lat, "lon": origin_lon}]
    if water_pick:
        stops.append({"stop": 1, "kind": "water_cache", "lat": water_pick["lat"], "lon": water_pick["lon"],
                      "activity": "collect water-ice", "reason":
                      "top-certainty SWIM-consistent cache on the way out (%s)" % water_pick["certainty"]})
        waypoints.append({"lat": water_pick["lat"], "lon": water_pick["lon"]})
    if shelter_pick:
        stops.append({"stop": len(stops) + 1, "kind": "shelter_pickup", "lat": shelter_pick["lat"], "lon": shelter_pick["lon"],
                      "activity": "shelter during peak flux", "reason":
                      "highest composite-index shelter near route (composite %.1f)" % shelter_pick["composite_index"]})
        waypoints.append({"lat": shelter_pick["lat"], "lon": shelter_pick["lon"]})
    stops.append({"stop": len(stops) + 1, "kind": "refuge", "lat": dest["lat"], "lon": dest["lon"],
                  "activity": "hold at refuge", "reason": "destination refuge with habitat shielding"})
    waypoints.append({"lat": dest["lat"], "lon": dest["lon"]})

    # route legs between waypoints
    legs = []
    total = 0.0
    for i in range(len(waypoints) - 1):
        a, b = waypoints[i], waypoints[i + 1]
        if hav_km(a["lat"], a["lon"], b["lat"], b["lon"]) < 0.5:
            continue
        leg = routing.plan_route(a["lat"], a["lon"], b["lat"], b["lon"], preset="speed")
        legs.append(leg)
        if leg.get("stats") and leg["stats"].get("length_km") is not None:
            total += leg["stats"]["length_km"]
    rad = radiation(origin_lat, origin_lon, duration_sols=2.0, shielding="suit",
                    storm={"kind": "sep", "severity": severity})
    plan = {
        "plan_id": "response-" + uuid.uuid4().hex[:8],
        "type": "evacuation",
        "origin": {"lat": origin_lat, "lon": origin_lon},
        "destination": dest,
        "stops": stops,
        "legs": [{
            "from": leg["path"][0] if leg["path"] else None,
            "to": leg["path"][-1] if leg["path"] else None,
            "path": leg.get("path", []),
            "stats": leg.get("stats"),
        } for leg in legs],
        "total_length_km": round(total, 1),
        "radiation_estimate": rad,
        "advisory": True,
        "provenance": with_sim({
            "source": "NAM deterministic storm-response planner [SIM]",
            "components": ["A* routing", "SWIM-derived water candidates",
                           "curated shelter scoring", "RAD-anchored dose model"],
        }, note="simulated evacuation plan; advisory only"),
    }
    return plan
