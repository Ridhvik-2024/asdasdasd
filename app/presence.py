"""Presence simulation: crews, rovers, habitats with position ticks [SIM]."""
import math

from . import seeds
from .mars import hav_km, validate_coords

_state: dict = {}
_t = 0.0


def _agent_position(agent, t):
    loop = agent.get("loop") or []
    speed = agent.get("speed_km_sol", 0)
    if not loop or speed <= 0:
        return {"lat": agent["lat"], "lon": agent["lon"] % 360.0, "status": "stationary [SIM]"}
    seglen = []
    total = 0.0
    for i in range(len(loop)):
        a = loop[i]; b = loop[(i + 1) % len(loop)]
        d = hav_km(a[0], a[1], b[0], b[1])
        seglen.append(d); total += d
    if total <= 0.0:
        return {"lat": agent["lat"], "lon": agent["lon"] % 360.0, "status": "stationary [SIM]"}
    pos = (t * speed) % total
    acc = 0.0
    for i, d in enumerate(seglen):
        if pos <= acc + d:
            a = loop[i]; b = loop[(i + 1) % len(loop)]
            f = (pos - acc) / d if d > 0 else 0.0
            dlon = ((b[1] - a[1] + 180.0) % 360.0) - 180.0
            lon = round((a[1] + dlon * f) % 360.0, 5) % 360.0
            return {"lat": round(a[0] + (b[0] - a[0]) * f, 5),
                    "lon": lon,
                    "status": "moving [SIM]"}
        acc += d
    return {"lat": agent["lat"], "lon": agent["lon"] % 360.0, "status": "moving [SIM]"}


def agents(t=None):
    global _t
    if t is not None:
        _t = t
    out = []
    for a in seeds.presence_agents():
        pos = _agent_position(a, _t)
        out.append({"id": a["id"], "name": a["name"], "kind": a["kind"], "role": a.get("role"),
                    **pos, "provenance": {"source": "NAM presence simulation [SIM]"}})
    return out


def agent(aid):
    for a in agents():
        if a["id"] == aid:
            return a
    return None


def near(lat, lon, radius_km=200):
    lat, lon = validate_coords(lat, lon)
    if isinstance(radius_km, bool) or not isinstance(radius_km, (int, float)):
        raise ValueError("radius_km must be a finite number")
    radius_km = float(radius_km)
    if not math.isfinite(radius_km) or radius_km < 0.0:
        raise ValueError("radius_km must be >= 0")
    out = []
    for a in agents():
        d = hav_km(lat, lon, a["lat"], a["lon"])
        if d <= radius_km:
            out.append(dict(a, distance_km=round(d, 1)))
    out.sort(key=lambda a: a["distance_km"])
    return out


def tick(dt_sols=1.0):
    global _t
    if isinstance(dt_sols, bool) or not isinstance(dt_sols, (int, float)) or not math.isfinite(float(dt_sols)):
        raise ValueError("dt_sols must be a finite number")
    _t += float(dt_sols)
    return agents()
