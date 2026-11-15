"""Seed loader + curated/full gazetteer search + region context."""
import difflib
import json
import re
from functools import lru_cache

from . import config
from .mars import hav_km, norm_lat, norm_lon, validate_coords

_STATE = {}


def _load(name):
    p = config.SEEDS_DIR / name
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def init():
    if _STATE:
        return _STATE
    _STATE["features"] = _load("gazetteer_curated.json")
    _STATE["landing"] = _load("landing_sites.json")
    _STATE["layers"] = _load("science_layers.json")
    _STATE["observations"] = _load("observations.json")
    _STATE["panoramas"] = _load("panoramas.json")
    _STATE["povs"] = _load("povs.json")
    _STATE["shelters"] = _load("shelters.json")
    _STATE["water"] = _load("water.json")
    _STATE["storms"] = _load("storm_events.json")
    _STATE["datasets"] = _load("datasets.json")
    _STATE["presence"] = _load("presence_agents.json")
    _STATE["hirise"] = _load("hirise_insets.json")
    _STATE["rover_regions"] = _load("rover_regions.json")
    _STATE["orbiters"] = _load("orbiters.json")
    _STATE["instruments"] = _load("instruments.json")
    _STATE["spectral_targets"] = _load("spectral_targets.json")
    _STATE["unavailable_sources"] = _load("unavailable_sources.json")
    _STATE["flyovers"] = _load("flyovers.json")
    full = []
    if config.USGS_FULL_PATH.exists():
        try:
            full = json.loads(config.USGS_FULL_PATH.read_text(encoding="utf-8"))
        except Exception:
            full = []
    _STATE["usgs_full"] = full
    # For a uniquely named match, use the official catalogue center and size
    # rather than the approximate (and occasionally incorrect) curated values.
    official = {}
    for feature in full:
        official.setdefault(feature.get("name", "").casefold(), []).append(feature)
    for feature in _STATE["features"]:
        matches = official.get(feature.get("name", "").casefold(), [])
        if len(matches) == 1:
            entry = matches[0]
            for key in ("lat", "lon", "diameter_km", "url", "approval", "approval_date"):
                if key in entry:
                    feature[key] = entry[key]
            feature["src"] = entry.get("src", feature.get("src"))
    return _STATE


REGIONS = [
    ({"min_lat": -30, "max_lat": 30, "min_lon": 250, "max_lon": 275}, "Tharsis",
     "Vast volcanic rise hosting Olympus Mons and the Tharsis Montes chain."),
    ({"min_lat": -18, "max_lat": -4, "min_lon": 265, "max_lon": 320}, "Valles Marineris",
     "The great equatorial canyon system with interior layered deposits."),
    ({"min_lat": -55, "max_lat": -30, "min_lon": 50, "max_lon": 90}, "Hellas rim region",
     "Deep impact basin with some of the highest, most cratered rims."),
    ({"min_lat": 30, "max_lat": 55, "min_lon": 100, "max_lon": 130}, "Utopia region",
     "Northern lowlands; broad plains over buried ice-rich terrain."),
    ({"min_lat": 38, "max_lat": 52, "min_lon": 180, "max_lon": 215}, "Arcadia region",
     "Smooth northern plains; prime shallow-ice candidate terrain."),
    ({"min_lat": -25, "max_lat": 0, "min_lon": 345, "max_lon": 360}, "Meridiani region",
     "Hematite-bearing plains along the equator; Opportunity's traverse."),
    ({"min_lat": -8, "max_lat": 25, "min_lon": 130, "max_lon": 155}, "Elysium region",
     "Second volcanic province with recent flood lavas and InSight's site."),
    ({"min_lat": 10, "max_lat": 30, "min_lon": 300, "max_lon": 330}, "Chryse/Ares region",
     "Outflow-channel mouths draining the southern highlands into Chryse."),
]


def region_context(lat, lon):
    lat, lon = norm_lat(lat), norm_lon(lon)
    for box, name, desc in REGIONS:
        if box["min_lat"] <= lat <= box["max_lat"] and box["min_lon"] <= lon <= box["max_lon"]:
            return {"region": name, "description": desc,
                    "provenance": {"source": "NAM physiographic context heuristic over published regional geology",
                                   "note": "coarse regional attribution"}}
    if lat > 55:
        return {"region": "Northern polar region", "description": "Layered ice deposits and circumpolar plains.",
                "provenance": {"source": "NAM physiographic context heuristic"}}
    if lat < -55:
        return {"region": "Southern polar region", "description": "CO2/water layered ice cap and southern highlands.",
                "provenance": {"source": "NAM physiographic context heuristic"}}
    if lat > 0:
        return {"region": "Northern lowlands", "description": "Low, smooth volcanic and sedimentary plains.",
                "provenance": {"source": "NAM physiographic context heuristic"}}
    return {"region": "Southern highlands", "description": "Ancient cratered crust with valley networks.",
            "provenance": {"source": "NAM physiographic context heuristic"}}


def _norm(entry):
    e = dict(entry)
    e["lat"] = norm_lat(e["lat"])
    e["lon"] = norm_lon(e["lon"])
    return e


def features():
    init()
    return _STATE["features"] + _STATE["usgs_full"]


COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[,; ]\s*(-?\d+(?:\.\d+)?)\s*$")


def search(qq, type_=None, limit=12):
    """Fuzzy gazetteer search over curated + full USGS nomenclature."""
    init()
    q0 = (qq or "").strip().lower()
    out = []
    m = COORD_RE.match(qq or "")
    if m:
        lat, lon = validate_coords(float(m.group(1)), float(m.group(2)))
        near = nearest(lat, lon, radius_km=300, limit=limit)
        return [{"kind": "coordinates", "lat": lat, "lon": lon,
                 "nearest": near,
                 "provenance": {"source": "coordinate query, nearest features from gazetteer"}}]
    # Accept the common "Gale Crater" form for catalogue entries named "Gale".
    without_crater = re.sub(r"\s+crater$", "", q0).strip()
    for f in features():
        name = f.get("name", "").lower()
        if type_ and type_.lower() not in (f.get("type") or "").lower():
            continue
        score = 0.0
        if q0 == name or (without_crater != q0 and without_crater == name and "crater" in (f.get("type") or "").lower()):
            score = 1.0
        elif q0 and q0 in name:
            score = 0.92 - 0.002 * abs(len(name) - len(q0))
        else:
            toks = q0.split()
            if toks and all(t in name for t in toks):
                score = 0.85
            else:
                r = difflib.SequenceMatcher(None, q0, name).ratio()
                if r > 0.66:
                    score = r * 0.8
        if score > 0:
            out.append((score, _norm(f)))
    for ls in _STATE["landing"]:
        name = ls.get("name", "").lower()
        if q0 and (q0 in name or q0 in ls.get("mission", "").lower()):
            out.append((0.95, dict(_norm(ls), kind="landing_site")))
    out.sort(key=lambda t: -t[0])
    # Suppress exact curated/USGS duplicates without hiding genuinely distinct
    # named features or mission sites sharing a name.
    unique = []
    for score, feature in out:
        duplicate = any(feature.get("name", "").casefold() == other.get("name", "").casefold()
                        and feature.get("kind") != "landing_site" and other.get("kind") != "landing_site"
                        and hav_km(feature["lat"], feature["lon"], other["lat"], other["lon"]) < 1
                        for _, other in unique)
        if not duplicate:
            unique.append((score, feature))
        if len(unique) >= max(1, min(limit, 100)):
            break
    return [{"score": round(score, 3), **feature} for score, feature in unique]


def by_id(fid):
    init()
    for f in features():
        if f.get("id") == fid:
            return _norm(f)
    for ls in _STATE["landing"]:
        if ls["id"] == fid:
            return dict(_norm(ls), kind="landing_site")
    return None


def nearest(lat, lon, radius_km=200, limit=8):
    init()
    scored = []
    for f in features():
        d = hav_km(lat, lon, f["lat"], f["lon"])
        if d <= radius_km:
            scored.append((d, _norm(f)))
    scored.sort(key=lambda t: t[0])
    out = []
    for d, f in scored[:limit]:
        f["distance_km"] = round(d, 1)
        out.append(f)
    return out


def landing_sites():
    init()
    return [_norm(x) for x in _STATE["landing"]]


def layers():
    init()
    return _STATE["layers"]


def layer(lid):
    init()
    for l in _STATE["layers"]:
        if l["id"] == lid:
            return l
    return None


def observations(q=None, instrument=None, lat=None, lon=None, radius_km=400, limit=20):
    init()
    out = []
    for o in _STATE["observations"]:
        o = _norm(o)
        if instrument and instrument.lower() not in (o.get("instrument") or "").lower():
            continue
        if q:
            ql = q.lower()
            hay = (o["title"] + " " + o["summary"] + " " + " ".join(o.get("tags", []))).lower()
            if ql not in hay:
                continue
        if lat is not None:
            d = hav_km(lat, lon, o["lat"], o["lon"])
            if d > radius_km:
                continue
            o["distance_km"] = round(d, 1)
        out.append(o)
    out.sort(key=lambda o: o.get("distance_km", 0))
    return out[:limit]


def observation(oid):
    init()
    for o in _STATE["observations"]:
        if o["id"] == oid:
            return _norm(o)
    return None


def panoramas():
    init()
    return [_norm(p) for p in _STATE["panoramas"]]


def panorama(pid):
    for p in panoramas():
        if p["id"] == pid:
            return p
    return None


def panoramas_near(lat, lon, radius_km=100):
    out = []
    for p in panoramas():
        d = hav_km(lat, lon, p["lat"], p["lon"])
        if d <= radius_km:
            out.append(dict(p, distance_km=round(d, 1)))
    out.sort(key=lambda p: p["distance_km"])
    return out


def traverse(rover):
    pts = [p for p in panoramas() if p["rover"].lower() == rover.lower()]
    pts.sort(key=lambda p: (p.get("sol") or 0))
    return pts


def rover_timeline(rover):
    pts = traverse(rover)
    return [{"sol": p.get("sol"), "date": p.get("date"), "title": p["title"],
             "id": p["id"], "credit": p["credit"]} for p in pts]


def pov_library():
    init()
    return [_norm(p) for p in _STATE["povs"]]


def pov_nearest(lat, lon):
    best, bd = None, None
    for p in pov_library():
        d = hav_km(lat, lon, p["lat"], p["lon"])
        if bd is None or d < bd:
            best, bd = p, d
    if best:
        best = dict(best, distance_km=round(bd, 1))
    return best


def shelters_all():
    init()
    return [_norm(s) for s in _STATE["shelters"]]


def water_all():
    init()
    return [_norm(w) for w in _STATE["water"]]


def storms_catalog():
    init()
    return _STATE["storms"]


def datasets():
    init()
    return _STATE["datasets"]


def presence_agents():
    init()
    return _STATE["presence"]


def hirise_insets():
    init()
    return _STATE["hirise"]


def rover_region(lat, lon):
    init()
    for rover, r in _STATE["rover_regions"].items():
        b = r["bbox"]
        if b[0] <= lat <= b[2] and b[1] <= lon <= b[3]:
            return {"rover": rover, "site": r["site"]}
    return None


def orbiters():
    init()
    return _STATE["orbiters"]


def instruments(q=None, mission=None):
    init()
    out = []
    for inst in _STATE["instruments"]:
        if mission and mission.lower() not in (inst.get("mission") or "").lower():
            continue
        if q:
            hay = f"{inst['name']} {inst['mission']} {inst['kind']} {inst['measures']}".lower()
            if q.lower() not in hay:
                continue
        out.append(inst)
    return out


def spectral_targets(q=None, mineral=None, lat=None, lon=None, radius_km=600):
    init()
    out = []
    for t in _STATE["spectral_targets"]:
        t = _norm(t)
        if mineral and mineral.lower() not in (t.get("mineral_class") or "").lower():
            continue
        if q:
            hay = f"{t['name']} {t['mineral_class']} {t['instrument']} {t['note']}".lower()
            if q.lower() not in hay:
                continue
        if lat is not None and lon is not None:
            d = hav_km(lat, lon, t["lat"], t["lon"])
            if d > radius_km:
                continue
            t["distance_km"] = round(d, 1)
        out.append(t)
    if lat is not None:
        out.sort(key=lambda x: x.get("distance_km", 0))
    return out


def unavailable_sources():
    init()
    return _STATE["unavailable_sources"]


def flyovers():
    init()
    return _STATE["flyovers"]


def flyover(fid):
    init()
    for f in _STATE["flyovers"]:
        if f["id"] == fid:
            return f
    return None

