"""Terrain engine: demo global elevation grid + procedural local detail.

HONESTY: the shipped grid is a synthetic 0.5 deg approximation of Mars built
from published landmark geometry (see scripts/make_demo_grid.py). The service
labels every value source as "demo-synthetic-grid [SIM]" and documents the
production swap: real MOLA MEGDR 4 ppd (463 m/cell) or HiRISE DTM patches.
Local detail below grid resolution is deterministic procedural fractal noise,
also labelled [SIM].
"""
import math
import struct
import threading
import zlib

import numpy as np

from . import config
from .mars import KM_PER_DEG

M_PER_ROW = KM_PER_DEG * 1000.0  # meters per 1 deg latitude (grid index step is 0.5 deg)


def _hash01(ix, iy, seed):
    h = (int(ix) * 374761393 + int(iy) * 668265263 + int(seed) * 974634721) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    h ^= h >> 16
    return (h & 0xFFFF) / 65535.0


def _fbm(seed, ys, xs, octaves=4, gain=0.55):
    """Deterministic value-noise fBm on integer lattice coords [0..n)."""
    out = np.zeros(len(ys), dtype=np.float64)
    amp, freq = 1.0, 1.0
    for o in range(octaves):
        fx = xs * freq
        fy = ys * freq
        x0 = np.floor(fx).astype(np.int64); y0 = np.floor(fy).astype(np.int64)
        tx = fx - x0; ty = fy - y0
        tx = tx * tx * (3 - 2 * tx); ty = ty * ty * (3 - 2 * ty)
        v00 = np.array([_hash01(int(x), int(y), seed + o) for x, y in zip(x0, y0)])
        v10 = np.array([_hash01(int(x) + 1, int(y), seed + o) for x, y in zip(x0, y0)])
        v01 = np.array([_hash01(int(x), int(y) + 1, seed + o) for x, y in zip(x0, y0)])
        v11 = np.array([_hash01(int(x) + 1, int(y) + 1, seed + o) for x, y in zip(x0, y0)])
        a = v00 * (1 - tx) + v10 * tx
        b = v01 * (1 - tx) + v11 * tx
        out += amp * (a * (1 - ty) + b * ty)
        amp *= gain
        freq *= 2.0
    return out - 0.5


class TerrainEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self._loaded = False
        self.grid = None
        self._lats = None
        self._lons = None
        self._slope = None

    def _load(self):
        with self._lock:
            if self._loaded:
                return
            z = np.load(config.GRID_PATH)
            self.grid = z["elev"].astype(np.float64)
            self._lats = z["lats"].astype(np.float64)
            self._lons = z["lons"].astype(np.float64)
            self._loaded = True

    def ensure(self):
        if not self._loaded:
            self._load()
        return self

    # ------------------------------------------------------------- sampling
    def elev(self, lat, lon):
        self.ensure()
        lat, lon = float(lat), float(lon) % 360.0
        LATS, LONS = self._lats, self._lons
        yi = (np.searchsorted(LATS, lat) - 1)
        yi = int(np.clip(yi, 0, len(LATS) - 2))
        lat0, lat1 = LATS[yi], LATS[yi + 1]
        wy = (lat - lat0) / (lat1 - lat0)
        xi = int(np.clip(np.searchsorted(LONS, lon) - 1, 0, len(LONS) - 2))
        lon0, lon1 = LONS[xi], LONS[xi + 1]
        wx = (lon - lon0) / (lon1 - lon0)
        row0 = self.grid[yi, xi] * (1 - wx) + self.grid[yi, xi + 1] * wx
        row1 = self.grid[yi + 1, xi] * (1 - wx) + self.grid[yi + 1, xi + 1] * wx
        return float(row0 * (1 - wy) + row1 * wy)

    def _detail(self, lat, lon, cell_m, seed_extra=""):
        """Procedural sub-grid relief, amplitude tied to cell size."""
        amp = min(0.35 * max(cell_m, 1.0), 140.0)
        if amp < 1.0:
            return 0.0
        seed = zlib.crc32(("%.3f|%.3f|%s" % (lat, lon, seed_extra)).encode())
        v = _fbm(seed, np.array([77.0]), np.array([133.0]), octaves=3)[0]
        return float(v * amp)

    def elev_full(self, lat, lon, cell_m):
        return self.elev(lat, lon) + self._detail(lat, lon, cell_m)

    # ------------------------------------------------------------- slopes
    def slope_grid(self):
        self.ensure()
        if self._slope is not None:
            return self._slope
        gy, gx = np.gradient(self.grid)
        dlat_m = KM_PER_DEG * 1000.0 * 0.5
        dlon_m = KM_PER_DEG * 1000.0 * 0.5 * np.cos(np.radians(self._lats))
        sx = gx / dlon_m[:, None]
        sy = gy / dlat_m
        self._slope = np.degrees(np.arctan(np.sqrt(sx ** 2 + sy ** 2)))
        return self._slope

    def slope(self, lat, lon):
        self.ensure()
        sg = self.slope_grid()
        lat = float(lat)
        yi = int(np.clip(np.searchsorted(self._lats, lat) - 1, 0, len(self._lats) - 2))
        lon = float(lon) % 360.0
        xi = int(np.clip(np.searchsorted(self._lons, lon) - 1, 0, len(self._lons) - 2))
        return float(sg[yi, xi])

    def slope_full(self, lat, lon, cell_m):
        base = self.slope(lat, lon)
        detail = abs(self._detail(lat, lon, cell_m, "d")) / max(cell_m, 1.0)
        return float(min(85.0, base + math.degrees(math.atan(detail))))

    def bbox_stats(self, bbox):
        """bbox = (min_lat, min_lon, max_lat, max_lon)."""
        self.ensure()
        min_lat, min_lon, max_lat, max_lon = bbox
        min_lat, max_lat = min(min_lat, max_lat), max(min_lat, max_lat)
        if min_lon > max_lon:
            min_lon, max_lon = max_lon, min_lon
        i0 = int(np.clip(np.searchsorted(self._lats, min_lat), 0, len(self._lats) - 1))
        i1 = int(np.clip(np.searchsorted(self._lats, max_lat) + 1, 1, len(self._lats)))
        j0 = int(np.clip(np.searchsorted(self._lons, min_lon), 0, len(self._lons) - 1))
        j1 = int(np.clip(np.searchsorted(self._lons, max_lon) + 1, 1, len(self._lons)))
        sub = self.grid[i0:i1, j0:j1]
        sub_s = self.slope_grid()[i0:i1, j0:j1]
        if sub.size == 0:
            sub = np.array([[self.grid[int(np.argmin(abs(self._lats - min_lat))), 0]]])
            sub_s = np.array([[self.slope(min_lat, min_lon)]])
        mean_slope = float(sub_s.mean()); max_slope = float(sub_s.max())
        hazard = min(100.0, mean_slope * 9.0 + max_slope * 1.2)
        return {
            "bbox": [float(min_lat), float(min_lon), float(max_lat), float(max_lon)],
            "mean_elev_m": float(sub.mean()), "min_elev_m": float(sub.min()),
            "max_elev_m": float(sub.max()), "relief_m": float(sub.max() - sub.min()),
            "mean_slope_deg": mean_slope, "max_slope_deg": max_slope,
            "roughness_m": float(np.sqrt(((sub - sub.mean()) ** 2).mean())),
            "hazard_score": round(hazard, 1),
        }

    def crater_depth(self, d_km):
        """Depth estimate from published depth/diameter scaling [SIM]."""
        d = float(d_km)
        if d < 7.0:
            depth = 0.30 * d ** 0.55
            regime = "simple"
        else:
            depth = 0.36 * d ** 0.42
            regime = "complex"
        return {"diameter_km": d, "estimated_depth_m": round(depth * 1000.0, 1),
                "regime": regime,
                "provenance": {"source": "Garvin-et-al-style depth/diameter scaling [SIM]",
                               "note": "derived estimate, not a measurement"}}

    # ------------------------------------------------------------- profiles & patches
    def profile(self, points, samples=180):
        from .mars import dest_pt, hav_km
        self.ensure()
        pts = [(float(p["lat"]), float(p["lon"])) for p in points]
        segs = []
        total = 0.0
        for i in range(len(pts) - 1):
            d = hav_km(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
            segs.append(d)
            total += d
        series = []
        acc = 0.0
        n = max(int(samples), 2)
        for i in range(len(pts) - 1):
            d = segs[i]
            n_i = max(2, int(round(n * d / total)) if total > 0 else 2)
            for k in range(n_i):
                t = k / (n_i - 1) if n_i > 1 else 0.0
                az = None
                if d > 1e-9:
                    from .mars import bearing
                    az = bearing(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
                    lat, lon = dest_pt(pts[i][0], pts[i][1], d * t, az)
                else:
                    lat, lon = pts[i]
                series.append((acc + d * t, lat, lon))
            acc += d
        series.append((total, pts[-1][0], pts[-1][1]))
        out = []
        for dist, lat, lon in series:
            e = self.elev(lat, lon)
            out.append({"dist_km": round(dist, 4), "lat": round(lat, 5),
                        "lon": round(lon, 5), "elev_m": round(e, 1)})
        gains = [out[i + 1]["elev_m"] - out[i]["elev_m"] for i in range(len(out) - 1)]
        return {
            "total_km": round(total, 4),
            "points": out,
            "elevation_gain_m": round(sum(g for g in gains if g > 0), 1),
            "elevation_loss_m": round(sum(-g for g in gains if g < 0), 1),
            "min_elev_m": min(p["elev_m"] for p in out),
            "max_elev_m": max(p["elev_m"] for p in out),
            "provenance": self.prov(),
        }

    def patch(self, lat, lon, radius_km, n=96):
        self.ensure()
        n = int(max(8, min(n, 160)))
        dlat = (radius_km * 2.0) / KM_PER_DEG
        dlon = dlat / max(0.2, math.cos(math.radians(lat)))
        cell_m = (radius_km * 2000.0) / n
        xs = np.linspace(-radius_km, radius_km, n)
        ys = np.linspace(-radius_km, radius_km, n)
        grid = np.zeros((n, n), dtype=np.float64)
        for i in range(n):
            row_lat = float(lat) + ys[i] / KM_PER_DEG
            for j in range(n):
                row_lon = float(lon) + xs[j] / (KM_PER_DEG * math.cos(math.radians(row_lat)))
                grid[i, j] = self.elev_full(row_lat, row_lon, cell_m)
        return {
            "center": {"lat": float(lat), "lon": float(lon) % 360.0},
            "radius_km": float(radius_km), "n": n, "cell_size_m": round(cell_m, 2),
            "grid_m": [[round(float(v), 1) for v in row] for row in grid],
            "provenance": self.prov(cell_m),
        }

    def mesh(self, lat, lon, radius_km, n=64):
        p = self.patch(lat, lon, radius_km, n)
        g = np.array(p["grid_m"], dtype=np.float64)
        n = p["n"]
        z0 = float(g.min())
        verts = []
        for i in range(n):
            for j in range(n):
                x = (j / (n - 1)) * 2 * p["radius_km"] * 1000.0 - p["radius_km"] * 1000.0
                y = ((n - 1 - i) / (n - 1)) * 2 * p["radius_km"] * 1000.0 - p["radius_km"] * 1000.0
                verts.append([round(x, 1), round(y, 1), round(float(g[i, j]) - z0, 1)])
        idx = []
        for i in range(n - 1):
            for j in range(n - 1):
                a = i * n + j; b = a + 1; c = a + n; d = c + 1
                idx += [a, b, c, b, d, c]
        return {"center": p["center"], "radius_km": p["radius_km"], "n": n,
                "cell_size_m": p["cell_size_m"], "vertices_local_m": verts,
                "indices": idx, "base_elev_m": round(z0, 1),
                "provenance": p["provenance"]}

    def stl_bytes(self, lat, lon, radius_km, vertical_scale=5.0, n=96):
        p = self.patch(lat, lon, radius_km, n)
        g = np.array(p["grid_m"], dtype=np.float64)
        z0 = float(g.min())
        n = p["n"]
        cell_mm = p["cell_size_m"] * 1000.0
        tris = (n - 1) * (n - 1) * 2
        header = ("NAM terrain export [SIM]: demo grid + procedural detail; "
                  "vertical scale x%.1f; patch %.0f km" % (vertical_scale, radius_km))
        buf = bytearray()
        buf += header.encode("ascii")[:80].ljust(80, b" ")
        buf += struct.pack("<I", tris)
        vs = vertical_scale * 1000.0
        for i in range(n - 1):
            for j in range(n - 1):
                x0 = j * cell_mm; x1 = (j + 1) * cell_mm
                y0 = ((n - 1 - i)) * cell_mm; y1 = ((n - 1 - (i + 1))) * cell_mm
                z00 = (float(g[i, j]) - z0) * vs
                z01 = (float(g[i, j + 1]) - z0) * vs
                z10 = (float(g[i + 1, j]) - z0) * vs
                z11 = (float(g[i + 1, j + 1]) - z0) * vs
                for tri in ((x0, y0, z00, x1, y0, z01, x0, y1, z10),
                            (x1, y0, z01, x1, y1, z11, x0, y1, z10)):
                    buf += struct.pack("<3f", 0.0, 0.0, 0.0)
                    buf += struct.pack("<3f", tri[0], tri[1], tri[2])
                    buf += struct.pack("<3f", tri[3], tri[4], tri[5])
                    buf += struct.pack("<3f", tri[6], tri[7], tri[8])
                    buf += struct.pack("<H", 0)
        return bytes(buf)

    def prov(self, cell_m=None):
        from .integrity import prov
        res = "%d m/cell" % int(cell_m) if cell_m else "0.5 deg global (~29.7 km/cell)"
        return prov(
            source="demo-synthetic-grid + procedural detail [SIM] (production: MOLA MEGDR 4 ppd / HiRISE DTMs)",
            resolution=res,
            note="Synthetic approximation built from published landmark geometry; "
                 "not measured MOLA data. Swap path documented in README.",
        )


_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = TerrainEngine()
    return _engine
