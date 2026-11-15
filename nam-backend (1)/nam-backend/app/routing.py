"""Terrain-aware A* routing (balanced / terrain / speed cost presets).

[SIM] note: difficulty derives from the 0.5 deg demo grid gradient; the
production path refines this with MOLA regional products and HiRISE DTMs.
"""
import heapq
import math

from . import terrain
from .integrity import prov, with_sim

PRESETS = {
    "balanced": {"slope": 1.0, "dist": 1.0},
    "terrain": {"slope": 2.4, "dist": 1.0},
    "speed": {"slope": 0.55, "dist": 1.15},
}


def _speed_model(slope_deg, preset):
    """Traverse-speed model [SIM]: km per sol. Calibrated against published
    rover progress (Opportunity ~45 km / ~5000 sols; driving-day maxima
    ~0.1 km/sol); conservative over rough terrain."""
    base = {"balanced": 0.12, "terrain": 0.08, "speed": 0.20}[preset]
    return max(0.02, base * math.exp(-slope_deg / 20.0))


def plan_route(lat1, lon1, lat2, lon2, preset="balanced"):
    if preset not in PRESETS:
        preset = "balanced"
    T = terrain.engine().ensure()
    pad_lat = abs(lat2 - lat1) * 0.25 + 0.4
    pad_lon = abs(((lon2 - lon1 + 180) % 360) - 180) * 0.25 + 0.4
    min_lat = min(lat1, lat2) - pad_lat
    max_lat = max(lat1, lat2) + pad_lat
    min_lon = min(lon1, lon2) - pad_lon
    max_lon = max(lon1, lon2) + pad_lon

    span_lat = max_lat - min_lat
    span_lon = max_lon - min_lon
    cells = 200
    step = max(span_lat, span_lon) / cells
    step = max(step, 0.05)
    nl = int(max(4, min(260, round(span_lat / step) + 1)))
    nc = int(max(4, min(260, round(span_lon / step) + 1)))

    lats = [min_lat + i * step for i in range(nl)]
    lons = [min_lon + j * step for j in range(nc)]
    KM = 59.3
    # cost grid from slope + base distance
    elev = {}
    slope = {}
    for i in range(nl):
        for j in range(nc):
            elev[(i, j)] = T.elev(lats[i], lons[j])
    for i in range(nl):
        for j in range(nc):
            dy = KM * step
            dx = KM * step * math.cos(math.radians(lats[i]))
            dz = 0.0
            if i > 0 and i < nl - 1:
                dz = (elev[(i + 1, j)] - elev[(i - 1, j)]) / 2000.0 * dy
            if j > 0 and j < nc - 1:
                dzy = (elev[(i, j + 1)] - elev[(i, j - 1)]) / 2000.0 * dx
                dz = math.hypot(dz, dzy)
            slope[(i, j)] = math.degrees(math.atan(abs(dz) / max(0.1, dy * 0.001)))

    def idx(lat, lon):
        i = int(round((lat - min_lat) / step)); i = max(0, min(nl - 1, i))
        j = int(round(((lon - min_lon) % 360 - (min_lon % 360)) / step)) % nc
        return (i, j)

    start = idx(lat1, lon1)
    goal = idx(lat2, lon2)

    def h(a, b):
        ay, ax = a; by, bx = b
        dlat = (lats[ay] - lats[by]) * KM
        dlon = ((lons[ax] - lons[bx] + 180) % 360 - 180) * KM * math.cos(math.radians(lats[ay]))
        return math.hypot(dlat, dlon)

    w = PRESETS[preset]
    gscore = {start: 0.0}
    came = {}
    open_heap = [(h(start, goal), 0.0, start)]
    closed = set()
    found = False
    while open_heap:
        f, g, cur = heapq.heappop(open_heap)
        if cur in closed:
            continue
        closed.add(cur)
        if cur == goal:
            found = True
            break
        ci, cj = cur
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                if di == 0 and dj == 0:
                    continue
                ni, nj = ci + di, cj + dj
                if not (0 <= ni < nl and 0 <= nj < nc):
                    continue
                nb = (ni, nj)
                move_km = h(cur, nb)
                s = slope[nb]
                if s > 38.0:
                    cost = move_km * 25.0          # impassable-class wall
                else:
                    cost = move_km * w["dist"] * (1.0 + w["slope"] * (s / 30.0) ** 2)
                ng = g + cost
                if ng < gscore.get(nb, float("inf")):
                    gscore[nb] = ng
                    came[nb] = cur
                    heapq.heappush(open_heap, (ng + h(nb, goal), ng, nb))
    if not found:
        # fallback straight line path (honest about degraded routing)
        path_pts = [{"lat": lat1, "lon": lon1}, {"lat": lat2, "lon": lon2}]
        return {"path": path_pts, "length_km": None, "status": "degraded",
                "note": "no in-grid route found (grid too coarse for these endpoints)",
                "sim": True,
                "provenance": {"source": "NAM A* degraded fallback [SIM]",
                               "note": "straight line shown; no in-grid route"}}

    nodes = []
    cur = goal
    while cur != start:
        nodes.append(cur)
        cur = came[cur]
    nodes.append(start)
    nodes.reverse()

    path = []
    length = 0.0
    slopes = []
    prev = None
    for (i, j) in nodes:
        pt = {"lat": round(lats[i], 5), "lon": round(lons[j] % 360.0, 5),
              "elev_m": round(elev[(i, j)], 1)}
        if prev is not None:
            from .mars import hav_km
            length += hav_km(prev["lat"], prev["lon"], pt["lat"], pt["lon"])
        slopes.append(slope[(i, j)])
        path.append(pt)
        prev = pt

    mean_slope = sum(slopes) / len(slopes) if slopes else 0.0
    est_sols = length / max(0.02, _speed_model(mean_slope, preset))
    stats = {
        "length_km": round(length, 2),
        "mean_slope_deg": round(mean_slope, 2),
        "max_slope_deg": round(max(slopes) if slopes else 0.0, 2),
        "elevation_gain_m": round(sum(max(0, path[i + 1]["elev_m"] - path[i]["elev_m"]) for i in range(len(path) - 1)), 1),
        "elevation_loss_m": round(sum(max(0, path[i]["elev_m"] - path[i + 1]["elev_m"]) for i in range(len(path) - 1)), 1),
        "est_traverse_sols": round(est_sols, 1),
        "cost_preset": preset,
    }
    return {"path": path, "stats": stats, "sim": True,
            "provenance": {"source": "NAM A* over demo terrain grid [SIM]",
                           "cost_preset": preset,
                           "note": "difficulty from 0.5 deg demo grid; refine with MOLA "
                                   "regional products / HiRISE DTMs in production; advisory [SIM]"}}

