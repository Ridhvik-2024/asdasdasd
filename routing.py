"""Terrain-aware A* routing (balanced / terrain / speed cost presets).

[SIM] note: difficulty derives from the 0.5 deg demo grid gradient; the
production path refines this with MOLA regional products and HiRISE DTMs.

Correctness notes (v2.3 navigation core):
  * Slope is computed with consistent units: elevation differences (m) over
    horizontal distances (m), so slope = atan(dh / dd). The previous formula
    mixed metres and kilometres and inflated slopes by ~1000x.
  * Longitudes are unwrapped across the 0/360 boundary so a route from
    lon=359 to lon=1 traverses the short 2 deg interval, not ~358 deg.
  * The 38 deg terrain threshold is a hard traversal constraint: cells above
    it are excluded from the A* neighbour expansion instead of receiving a
    large finite penalty.
"""
import heapq
import math

from . import terrain
from .integrity import prov, with_sim
from .mars import KM_PER_DEG, hav_km

PRESETS = {
    "balanced": {"slope": 1.0, "dist": 1.0},
    "terrain": {"slope": 2.4, "dist": 1.0},
    "speed": {"slope": 0.55, "dist": 1.15},
}

# Terrain steeper than this is treated as impassable for traversal.
STEEP_THRESHOLD_DEG = 38.0

# Horizontal distance per degree of latitude / longitude, in metres.
M_PER_DEG = KM_PER_DEG * 1000.0  # ~59300 m/deg


def _speed_model(slope_deg, preset):
    """Traverse-speed model [SIM]: km per sol. Calibrated against published
    rover progress (Opportunity ~45 km / ~5000 sols; driving-day maxima
    ~0.1 km/sol); conservative over rough terrain."""
    base = {"balanced": 0.12, "terrain": 0.08, "speed": 0.20}[preset]
    return max(0.02, base * math.exp(-slope_deg / 20.0))


def _unwrap_lons(lon1, lon2):
    """Return (lon1, lon2_unwrapped) such that |lon2_unwrapped - lon1| <= 180.

    Longitudes are east 0-360. If the shortest great-circle path crosses the
    antimeridian, the second longitude is shifted by +/-360 so the grid can
    be built in a continuous frame without wrapping around the entire planet.
    """
    lon1 = float(lon1) % 360.0
    lon2 = float(lon2) % 360.0
    dlon_signed = ((lon2 - lon1 + 180.0) % 360.0) - 180.0  # in [-180, 180]
    return lon1, lon1 + dlon_signed


def plan_route(lat1, lon1, lat2, lon2, preset="balanced"):
    if preset not in PRESETS:
        preset = "balanced"
    T = terrain.engine().ensure()

    # Unwrap longitudes so the grid spans the shortest longitudinal interval.
    lon1_u, lon2_u = _unwrap_lons(lon1, lon2)

    pad_lat = abs(lat2 - lat1) * 0.25 + 0.4
    pad_lon = abs(lon2_u - lon1_u) * 0.25 + 0.4
    min_lat = min(lat1, lat2) - pad_lat
    max_lat = max(lat1, lat2) + pad_lat
    min_lon = min(lon1_u, lon2_u) - pad_lon
    max_lon = max(lon1_u, lon2_u) + pad_lon

    span_lat = max_lat - min_lat
    span_lon = max_lon - min_lon
    cells = 200
    step = max(span_lat, span_lon) / cells
    step = max(step, 0.05)
    nl = int(max(4, min(260, round(span_lat / step) + 1)))
    nc = int(max(4, min(260, round(span_lon / step) + 1)))

    lats = [min_lat + i * step for i in range(nl)]
    # Longitudes live in the unwrapped frame; they are normalised back to
    # [0, 360) only when emitted or when sampled against the terrain grid.
    lons = [min_lon + j * step for j in range(nc)]

    # ----- elevation samples (normalise lon for the terrain engine) -----
    elev = {}
    for i in range(nl):
        for j in range(nc):
            elev[(i, j)] = T.elev(lats[i], lons[j] % 360.0)

    # ----- slope grid: slope = atan(dh / dd) with dh and dd both in metres -----
    # For interior cells we use centred differences over two cell spans; for
    # edge cells we fall back to one-sided differences so boundary slopes are
    # not artificially zero.
    slope = {}
    for i in range(nl):
        dlat_m = M_PER_DEG * step
        dlon_m = M_PER_DEG * step * math.cos(math.radians(lats[i]))
        for j in range(nc):
            # dh/dy (latitude direction), dimensionless
            if 0 < i < nl - 1:
                dz_dy = (elev[(i + 1, j)] - elev[(i - 1, j)]) / (2.0 * dlat_m)
            elif nl > 1 and i == 0:
                dz_dy = (elev[(1, j)] - elev[(0, j)]) / dlat_m
            elif nl > 1 and i == nl - 1:
                dz_dy = (elev[(nl - 1, j)] - elev[(nl - 2, j)]) / dlat_m
            else:
                dz_dy = 0.0
            # dh/dx (longitude direction), dimensionless. The unwrapped
            # longitude frame is spatially continuous, so neighbours j-1 / j+1
            # are the correct horizontal neighbours even across the antimeridian.
            if 0 < j < nc - 1:
                dz_dx = (elev[(i, j + 1)] - elev[(i, j - 1)]) / (2.0 * dlon_m)
            elif nc > 1 and j == 0:
                dz_dx = (elev[(i, 1)] - elev[(i, 0)]) / dlon_m
            elif nc > 1 and j == nc - 1:
                dz_dx = (elev[(i, nc - 1)] - elev[(i, nc - 2)]) / dlon_m
            else:
                dz_dx = 0.0
            gradient = math.hypot(dz_dy, dz_dx)  # rise/run, dimensionless
            slope[(i, j)] = math.degrees(math.atan(gradient))

    def idx(lat, lon):
        i = int(round((lat - min_lat) / step))
        i = max(0, min(nl - 1, i))
        # Match the requested longitude to the unwrapped frame. The grid may
        # span [358, 362] when crossing the antimeridian, so a request for
        # lon=1 must be interpreted as lon=361 within the grid.
        target = float(lon) % 360.0
        while target < min_lon - 1e-9:
            target += 360.0
        while target > max_lon + 1e-9:
            target -= 360.0
        j = int(round((target - min_lon) / step))
        j = max(0, min(nc - 1, j))
        return (i, j)

    start = idx(lat1, lon1)
    goal = idx(lat2, lon2)

    KM = KM_PER_DEG  # great-circle heuristic uses km

    def h(a, b):
        ay, ax = a; by, bx = b
        dlat = (lats[ay] - lats[by]) * KM
        # Longitudes are continuous in the unwrapped frame, so no modulo wrap
        # is needed here (and applying one would reintroduce the antimeridian
        # bug for grids that legitimately span >180 deg, which padded local
        # grids never do).
        dlon = (lons[ax] - lons[bx]) * KM * math.cos(math.radians(lats[ay]))
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
                s = slope[nb]
                # The 38 deg threshold is a hard traversal constraint, not a
                # finite penalty: steep cells are excluded from neighbour
                # expansion so A* cannot plan through them.
                if s > STEEP_THRESHOLD_DEG:
                    continue
                move_km = h(cur, nb)
                cost = move_km * w["dist"] * (1.0 + w["slope"] * (s / 30.0) ** 2)
                ng = g + cost
                if ng < gscore.get(nb, float("inf")):
                    gscore[nb] = ng
                    came[nb] = cur
                    heapq.heappush(open_heap, (ng + h(nb, goal), ng, nb))
    if not found:
        # Fallback straight-line path. We are deliberately honest about the
        # degraded status: there is no measured length, no slope statistics
        # and no estimated traversal time, because no in-grid route was found.
        path_pts = [{"lat": lat1, "lon": float(lon1) % 360.0},
                    {"lat": lat2, "lon": float(lon2) % 360.0}]
        return {"path": path_pts, "length_km": None, "status": "degraded",
                "note": "no in-grid route found (grid too coarse or terrain "
                        "impassable for these endpoints)",
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
            length += hav_km(prev["lat"], prev["lon"], pt["lat"], pt["lon"])
        slopes.append(slope[(i, j)])
        path.append(pt)
        prev = pt

    mean_slope = sum(slopes) / len(slopes) if slopes else 0.0
    max_slope = max(slopes) if slopes else 0.0
    est_sols = length / max(0.02, _speed_model(mean_slope, preset))
    stats = {
        "length_km": round(length, 2),
        "mean_slope_deg": round(mean_slope, 2),
        "max_slope_deg": round(max_slope, 2),
        "elevation_gain_m": round(sum(max(0, path[i + 1]["elev_m"] - path[i]["elev_m"]) for i in range(len(path) - 1)), 1),
        "elevation_loss_m": round(sum(max(0, path[i]["elev_m"] - path[i + 1]["elev_m"]) for i in range(len(path) - 1)), 1),
        "est_traverse_sols": round(est_sols, 1),
        "cost_preset": preset,
    }
    return {"path": path, "length_km": stats["length_km"], "stats": stats,
            "sim": True,
            "provenance": {"source": "NAM A* over demo terrain grid [SIM]",
                           "cost_preset": preset,
                           "note": "difficulty from 0.5 deg demo grid; refine with MOLA "
                                   "regional products / HiRISE DTMs in production; advisory [SIM]"}}

