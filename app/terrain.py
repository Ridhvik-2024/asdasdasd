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


def _detail_noise(lat, lon, seed, octaves=4, gain=0.5, lacunarity=2.0,
                  cells_equator=360):
    """Spatially continuous, longitude-periodic value-noise fBm in [-0.5, 0.5].

    Unlike the previous _detail() implementation (which hashed a fresh seed
    from every coordinate and sampled at a fixed lattice point, producing
    unrelated values for neighbouring coordinates), this is sampled at the
    real geographic position so adjacent coordinates blend smoothly.

    Longitude is sampled on a cylindrical lattice that wraps every 360 deg,
    so the detail field is continuous across the 0/360 seam. Latitude uses a
    linear (clamped) lattice. The result is deterministic: the same
    (lat, lon, seed) always yields the same value.
    """
    lat = float(lat)
    lon = float(lon) % 360.0
    out = 0.0
    norm = 0.0
    amp, freq = 1.0, 1.0
    for o in range(octaves):
        period = int(cells_equator * freq)  # integer cells spanning 360 deg
        x = lon / 360.0 * period
        y = (lat + 90.0) / 180.0 * (cells_equator / 2.0) * freq
        xi = int(math.floor(x))
        yi = int(math.floor(y))
        tx = x - xi
        ty = y - yi
        tx = tx * tx * (3 - 2 * tx)
        ty = ty * ty * (3 - 2 * ty)
        x0 = xi % period          # wrap longitude lattice (antimeridian seam)
        x1 = (xi + 1) % period
        s = int(seed) + o * 2654435761
        v00 = _hash01(x0, yi, s)
        v10 = _hash01(x1, yi, s)
        v01 = _hash01(x0, yi + 1, s)
        v11 = _hash01(x1, yi + 1, s)
        a = v00 * (1 - tx) + v10 * tx
        b = v01 * (1 - tx) + v11 * tx
        out += amp * (a * (1 - ty) + b * ty)
        norm += amp
        amp *= gain
        freq *= lacunarity
    return out / norm - 0.5


class TerrainEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self._loaded = False
        self.grid = None
        self._lats = None
        self._lons = None
        self._slope = None
        self._raster_cache = {}

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
        """Bilinear elevation, with periodic longitude wrapping at 0/360.

        Longitude is sampled on the periodic 0.5 deg lattice so a point just
        below 360 deg interpolates against the wrapped first column (0 deg side)
        instead of extrapolating past the final grid column. Latitude is clamped
        to the supported range (no pole extrapolation).
        """
        self.ensure()
        lat, lon = float(lat), float(lon) % 360.0
        LATS, LONS = self._lats, self._lons
        nlat, nlon = len(LATS), len(LONS)
        # latitude: linear lattice, clamped to valid rows (no extrapolation)
        dlat = LATS[1] - LATS[0]
        fy = (lat - LATS[0]) / dlat
        yi = int(math.floor(fy))
        yi = max(0, min(yi, nlat - 2))
        wy = max(0.0, min(1.0, fy - yi))
        # longitude: periodic lattice. fx wraps into [0, nlon) so the seam
        # between the last and first column is interpolated, not extrapolated.
        dlon = LONS[1] - LONS[0]
        fx = ((lon - LONS[0]) / dlon) % nlon
        xi = int(math.floor(fx)) % nlon
        xj = (xi + 1) % nlon
        wx = fx - math.floor(fx)
        row0 = self.grid[yi, xi] * (1 - wx) + self.grid[yi, xj] * wx
        row1 = self.grid[yi + 1, xi] * (1 - wx) + self.grid[yi + 1, xj] * wx
        return float(row0 * (1 - wy) + row1 * wy)

    def _detail(self, lat, lon, cell_m, seed_extra=""):
        """Procedural sub-grid relief, amplitude tied to cell size.

        Spatially continuous value-noise fBm sampled at the real geographic
        position (longitude-periodic) so neighbouring coordinates blend
        smoothly instead of receiving unrelated random values. The previous
        implementation hashed a fresh seed from every (lat, lon) and evaluated
        noise at a fixed lattice position, which broke local continuity.
        """
        amp = min(0.35 * max(cell_m, 1.0), 140.0)
        if amp < 1.0:
            return 0.0
        seed = zlib.crc32(("nam-detail|%s" % seed_extra).encode())
        return float(_detail_noise(lat, lon, seed) * amp)

    def elev_full(self, lat, lon, cell_m):
        return self.elev(lat, lon) + self._detail(lat, lon, cell_m)

    # ------------------------------------------------------------- slopes
    def _gradients_m(self):
        """Meridional (sy = dz/dy) and zonal (sx = dz/dx) dimensionless gradients.

        Uses periodic central differences along longitude so the 0/360 seam has
        the exact same second-order stencil as interior columns, and guards
        polar latitudes where cos(lat) -> 0 so zonal gradients stay finite.
        """
        self.ensure()
        dlat_deg = float(self._lats[1] - self._lats[0])
        dlon_deg = float(self._lons[1] - self._lons[0])
        gy = np.gradient(self.grid, axis=0)
        # Periodic central difference across the 0/360 longitude seam:
        gx = (np.roll(self.grid, -1, axis=1) - np.roll(self.grid, 1, axis=1)) / 2.0
        dlat_m = KM_PER_DEG * 1000.0 * abs(dlat_deg)
        cos_lat = np.cos(np.radians(self._lats))
        dlon_m = KM_PER_DEG * 1000.0 * abs(dlon_deg) * np.maximum(cos_lat, 1e-3)
        sy = gy / dlat_m
        sx = np.where(cos_lat[:, None] > 1e-6, gx / dlon_m[:, None], 0.0)
        return sy, sx

    def slope_grid(self):
        self.ensure()
        if self._slope is not None:
            return self._slope
        sy, sx = self._gradients_m()
        self._slope = np.degrees(np.arctan(np.sqrt(sx ** 2 + sy ** 2)))
        return self._slope

    def aspect(self, lat, lon):
        """Downslope compass aspect in degrees [0, 360) (0=N, 90=E, 180=S, 270=W)."""
        self.ensure()
        sy, sx = self._gradients_m()
        lat = float(lat)
        yi = int(np.clip(np.searchsorted(self._lats, lat) - 1, 0, len(self._lats) - 2))
        nlon = len(self._lons)
        dlon = self._lons[1] - self._lons[0]
        fx = ((float(lon) % 360.0 - self._lons[0]) / dlon) % nlon
        xi = int(math.floor(fx)) % nlon
        dz_dy = float(sy[yi, xi])
        dz_dx = float(sx[yi, xi])
        if abs(dz_dx) < 1e-12 and abs(dz_dy) < 1e-12:
            return 0.0
        # Downslope vector is (-dz_dx east, -dz_dy north)
        return (math.degrees(math.atan2(-dz_dx, -dz_dy)) + 360.0) % 360.0

    def curvature(self, lat, lon):
        """Laplacian surface curvature (1/km) — positive convex, negative concave."""
        self.ensure()
        dlat_km = KM_PER_DEG * abs(float(self._lats[1] - self._lats[0]))
        lat = float(lat)
        yi = int(np.clip(np.searchsorted(self._lats, lat) - 1, 1, len(self._lats) - 2))
        nlon = len(self._lons)
        dlon_deg = float(self._lons[1] - self._lons[0])
        fx = ((float(lon) % 360.0 - self._lons[0]) / dlon_deg) % nlon
        xi = int(math.floor(fx)) % nlon
        dlon_km = max(0.05, KM_PER_DEG * abs(dlon_deg) * math.cos(math.radians(self._lats[yi])))
        c = self.grid[yi, xi]
        d2y = ((self.grid[yi + 1, xi] - 2.0 * c + self.grid[yi - 1, xi]) / 1000.0) / (dlat_km ** 2)
        d2x = ((self.grid[yi, (xi + 1) % nlon] - 2.0 * c + self.grid[yi, (xi - 1) % nlon]) / 1000.0) / (dlon_km ** 2)
        return float(d2x + d2y)

    def slope(self, lat, lon):
        self.ensure()
        sg = self.slope_grid()
        lat = float(lat)
        yi = int(np.clip(np.searchsorted(self._lats, lat) - 1, 0, len(self._lats) - 2))
        lon = float(lon) % 360.0
        nlon = len(self._lons)
        dlon = self._lons[1] - self._lons[0]
        # periodic longitude: pick the cell containing lon, wrapping at 0/360
        fx = ((lon - self._lons[0]) / dlon) % nlon
        xi = int(math.floor(fx)) % nlon
        return float(sg[yi, xi])

    def slope_full(self, lat, lon, cell_m):
        base = self.slope(lat, lon)
        detail = abs(self._detail(lat, lon, cell_m, "d")) / max(cell_m, 1.0)
        return float(min(85.0, base + math.degrees(math.atan(detail))))

    def bbox_stats(self, bbox):
        """bbox = (min_lat, min_lon, max_lat, max_lon), longitudes east 0-360.

        Handles antimeridian-crossing boxes: when min_lon > max_lon (after
        normalisation to 0-360) the region wraps across the 0/360 seam and is
        taken as the union of [min_lon, 360) and [0, max_lon] rather than the
        huge swapped span the previous longitude swap produced.
        """
        self.ensure()
        min_lat, min_lon, max_lat, max_lon = bbox
        min_lat, max_lat = float(min(min_lat, max_lat)), float(max(min_lat, max_lat))
        min_lon = float(min_lon) % 360.0
        max_lon = float(max_lon) % 360.0
        LATS, LONS = self._lats, self._lons
        nlon = len(LONS)
        crosses = min_lon > max_lon
        i0 = int(np.clip(np.searchsorted(LATS, min_lat), 0, len(LATS) - 1))
        i1 = int(np.clip(np.searchsorted(LATS, max_lat) + 1, 1, len(LATS)))
        if not crosses:
            j0 = int(np.clip(np.searchsorted(LONS, min_lon), 0, nlon - 1))
            j1 = int(np.clip(np.searchsorted(LONS, max_lon) + 1, 1, nlon))
            sub = self.grid[i0:i1, j0:j1]
            sub_s = self.slope_grid()[i0:i1, j0:j1]
        else:
            # union of [min_lon, 360) and [0, max_lon] across the seam
            ja = int(np.clip(np.searchsorted(LONS, min_lon), 0, nlon - 1))
            jb = int(np.clip(np.searchsorted(LONS, max_lon) + 1, 1, nlon))
            sub = np.concatenate(
                [self.grid[i0:i1, ja:], self.grid[i0:i1, :jb]], axis=1)
            sub_s = np.concatenate(
                [self.slope_grid()[i0:i1, ja:], self.slope_grid()[i0:i1, :jb]],
                axis=1)
        if sub.size == 0:
            sub = np.array([[self.grid[int(np.argmin(abs(self._lats - min_lat))), 0]]])
            sub_s = np.array([[self.slope(min_lat, min_lon)]])
        mean_slope = float(sub_s.mean()); max_slope = float(sub_s.max())
        hazard = min(100.0, mean_slope * 9.0 + max_slope * 1.2)
        return {
            "bbox": [float(min_lat), float(min_lon), float(max_lat), float(max_lon)],
            "crosses_antimeridian": bool(crosses),
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
        cell_m = (radius_km * 2000.0) / n
        xs = np.linspace(-radius_km, radius_km, n)
        ys = np.linspace(-radius_km, radius_km, n)
        grid = np.zeros((n, n), dtype=np.float64)
        for i in range(n):
            row_lat = max(-90.0, min(90.0, float(lat) + ys[i] / KM_PER_DEG))
            cos_r = max(1e-3, math.cos(math.radians(row_lat)))
            for j in range(n):
                row_lon = (float(lon) + xs[j] / (KM_PER_DEG * cos_r)) % 360.0
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
                    ux, uy, uz = tri[3] - tri[0], tri[4] - tri[1], tri[5] - tri[2]
                    vx, vy, vz = tri[6] - tri[0], tri[7] - tri[1], tri[8] - tri[2]
                    nx = uy * vz - uz * vy
                    ny = uz * vx - ux * vz
                    nz = ux * vy - uy * vx
                    nlen = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
                    buf += struct.pack("<3f", nx / nlen, ny / nlen, nz / nlen)
                    buf += struct.pack("<3f", tri[0], tri[1], tri[2])
                    buf += struct.pack("<3f", tri[3], tri[4], tri[5])
                    buf += struct.pack("<3f", tri[6], tri[7], tri[8])
                    buf += struct.pack("<H", 0)
        return bytes(buf)

    def export_bbox(self, bbox):
        """Extract sub-grid elevation dataset, coordinate axes, CRS and stats for a bbox."""
        self.ensure()
        st = self.bbox_stats(bbox)
        min_lat, min_lon, max_lat, max_lon = st["bbox"]
        LATS, LONS = self._lats, self._lons
        nlon = len(LONS)
        i0 = int(np.clip(np.searchsorted(LATS, min_lat), 0, len(LATS) - 1))
        i1 = int(np.clip(np.searchsorted(LATS, max_lat) + 1, 1, len(LATS)))
        if not st["crosses_antimeridian"]:
            j0 = int(np.clip(np.searchsorted(LONS, min_lon), 0, nlon - 1))
            j1 = int(np.clip(np.searchsorted(LONS, max_lon) + 1, 1, nlon))
            sub_lons = LONS[j0:j1]
            sub = self.grid[i0:i1, j0:j1]
        else:
            ja = int(np.clip(np.searchsorted(LONS, min_lon), 0, nlon - 1))
            jb = int(np.clip(np.searchsorted(LONS, max_lon) + 1, 1, nlon))
            sub_lons = np.concatenate([LONS[ja:], LONS[:jb]])
            sub = np.concatenate([self.grid[i0:i1, ja:], self.grid[i0:i1, :jb]], axis=1)
        sub_lats = LATS[i0:i1]
        return {
            "crs": "IAU:49900 (Mars 2000 east-positive planetocentric 0-360)",
            "resolution_deg": float(LATS[1] - LATS[0]),
            "bbox_stats": st,
            "lats": [round(float(x), 4) for x in sub_lats],
            "lons": [round(float(x), 4) for x in sub_lons],
            "elevation_m": [[round(float(v), 1) for v in row] for row in sub],
            "provenance": self.prov(),
        }

    def elevation_grid_compact(self, step=2):
        """Downsampled global elevation matrix (N-to-S, 0-360E) for client 3D & cursor sampling."""
        self.ensure()
        st = max(1, min(int(step), 10))
        sub = self.grid[::-st, ::st]
        lats = self._lats[::-st]
        lons = self._lons[::st]
        return {
            "rows": int(sub.shape[0]),
            "cols": int(sub.shape[1]),
            "step_deg": round(float(self._lats[1] - self._lats[0]) * st, 3),
            "min_m": round(float(sub.min()), 1),
            "max_m": round(float(sub.max()), 1),
            "lats": [round(float(x), 3) for x in lats],
            "lons": [round(float(x), 3) for x in lons],
            "grid_m": [[round(float(v), 1) for v in row] for row in sub],
            "provenance": self.prov(),
        }

    @staticmethod
    def _encode_png_rgb(rgb: np.ndarray) -> bytes:
        """Pure-Python + zlib RGB PNG encoder (zero Pillow dependency)."""
        h, w, c = rgb.shape
        assert c == 3
        raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(h))

        def chunk(tag: bytes, data: bytes) -> bytes:
            return (
                struct.pack("!I", len(data))
                + tag
                + data
                + struct.pack("!I", zlib.crc32(tag + data) & 0xFFFFFFFF)
            )

        ihdr = struct.pack("!IIBBBBB", w, h, 8, 2, 0, 0, 0)
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, level=6))
            + chunk(b"IEND", b"")
        )

    @staticmethod
    def _ramp(t: np.ndarray, stops) -> np.ndarray:
        """Piecewise linear RGB color ramp over normalized array t in [0, 1]."""
        t = np.clip(t, 0.0, 1.0)
        xs = np.array([s[0] for s in stops], dtype=np.float64)
        rs = np.array([s[1][0] for s in stops], dtype=np.float64)
        gs = np.array([s[1][1] for s in stops], dtype=np.float64)
        bs = np.array([s[1][2] for s in stops], dtype=np.float64)
        r = np.interp(t, xs, rs)
        g = np.interp(t, xs, gs)
        b = np.interp(t, xs, bs)
        return np.stack([r, g, b], axis=-1)

    def render_raster_png(self, mode: str = "mars-relief") -> bytes:
        """Generate and cache a 720x360 equirectangular Mars layer PNG [SIM]."""
        self.ensure()
        key = (mode or "mars-relief").lower().strip()
        if key in self._raster_cache:
            return self._raster_cache[key]

        # Flip N->S so row 0 is +90 deg North and col 0..719 is 0..360 deg East
        E = self.grid[::-1, :]
        lats = self._lats[::-1]
        lons = self._lons
        LON, LAT = np.meshgrid(lons, lats)

        # Hillshade from periodic zonal + meridional gradients
        gy = np.gradient(E, axis=0)
        gx = (np.roll(E, -1, axis=1) - np.roll(E, 1, axis=1)) / 2.0
        # Light from NW azimuth 315 deg, altitude 38 deg
        scale = 1.0 / 2600.0
        nx, ny, nz = -gx * scale, gy * scale, np.ones_like(E)
        nlen = np.sqrt(nx * nx + ny * ny + nz * nz)
        lx, ly, lz = -0.55, 0.55, 0.628
        shade = np.clip((nx * lx + ny * ly + nz * lz) / nlen, 0.25, 1.25)

        # Subtle deterministic multi-frequency surface albedo variation
        albedo_var = (
            0.06 * np.sin(np.radians(LON * 3.0 + 18.0)) * np.cos(np.radians(LAT * 2.5))
            + 0.04 * np.cos(np.radians(LON * 7.0 - LAT * 5.0))
            + 0.03 * np.sin(np.radians(LON * 13.0 + LAT * 9.0))
        )

        # Normalize elevation for palettes
        e_norm = np.clip((E + 8200.0) / 30000.0, 0.0, 1.0)

        if key == "heightmap":
            g8 = np.clip(e_norm * 255.0, 0, 255).astype(np.uint8)
            rgb = np.stack([g8, g8, g8], axis=-1)
        elif key in ("mars-relief", "mdim21"):
            # Realistic Martian rusty color palette modulated by albedo provinces + polar caps
            base = self._ramp(
                e_norm,
                [
                    (0.00, (110, 62, 42)),   # Hellas floor
                    (0.18, (148, 82, 52)),   # Northern lowlands
                    (0.32, (182, 102, 62)),  # Mid-elevation plains
                    (0.50, (198, 120, 74)),  # Highlands & bright dust
                    (0.72, (214, 146, 98)),  # Tharsis rise
                    (0.92, (226, 178, 142)), # High shields
                    (1.00, (238, 206, 182)), # Olympus summit
                ],
            )
            # Dark basaltic albedo features (Syrtis Major, Acidalia, Margaritifer, Valles Marineris)
            dark = np.zeros_like(E)
            for la0, lo0, s_la, s_lo, strength in [
                (9.0, 69.0, 11.0, 12.0, 0.34),    # Syrtis Major
                (45.0, 338.0, 13.0, 20.0, 0.25),  # Acidalia
                (-10.0, 290.0, 6.0, 24.0, 0.28),  # Valles Marineris & Margaritifer
                (-18.0, 170.0, 12.0, 28.0, 0.20), # Terra Cimmeria/Sirenum dark band
                (-2.0, 354.0, 8.0, 14.0, 0.22),   # Meridiani
            ]:
                dlon = ((LON - lo0 + 180.0) % 360.0) - 180.0
                dark += strength * np.exp(-0.5 * (((LAT - la0) / s_la) ** 2 + (dlon / s_lo) ** 2))
            # Bright dusty regions (Arabia, Tharsis, Elysium, Amazonis)
            bright = np.zeros_like(E)
            for la0, lo0, s_la, s_lo, strength in [
                (20.0, 30.0, 16.0, 22.0, 0.16),   # Arabia Terra
                (16.0, 205.0, 15.0, 24.0, 0.14),  # Amazonis
                (6.0, 250.0, 18.0, 22.0, 0.12),   # Tharsis dust
            ]:
                dlon = ((LON - lo0 + 180.0) % 360.0) - 180.0
                bright += strength * np.exp(-0.5 * (((LAT - la0) / s_la) ** 2 + (dlon / s_lo) ** 2))
            mod = np.clip(1.0 - dark + bright + albedo_var, 0.55, 1.28) * (0.45 + 0.65 * shade)
            rgb_f = base * mod[:, :, None]
            # Polar ice caps (north + south layered deposits)
            cap_edge_n = 80.5 + 2.2 * np.sin(np.radians(LON * 3.0)) + 1.1 * np.cos(np.radians(LON * 5.0))
            cap_edge_s = -82.0 + 2.5 * np.cos(np.radians(LON * 2.0 + 40.0))
            cap = np.clip((LAT - cap_edge_n) / 3.0, 0.0, 1.0) + np.clip((cap_edge_s - LAT) / 3.0, 0.0, 1.0)
            cap = np.clip(cap, 0.0, 1.0)
            ice_col = np.array([235.0, 232.0, 228.0]) * (0.75 + 0.25 * shade[:, :, None])
            rgb_f = rgb_f * (1.0 - cap[:, :, None]) + ice_col * cap[:, :, None]
            rgb = np.clip(rgb_f, 0, 255).astype(np.uint8)
        elif key in ("ctx-murray", "hirise-insets"):
            # Crisp panchromatic orbital mosaic look [SIM fallback]
            gray = (128.0 + 75.0 * (shade - 0.72) + 28.0 * (e_norm - 0.35) + 18.0 * albedo_var)
            gray = np.clip(gray, 22, 240)
            rgb = np.stack([gray * 1.02, gray * 0.99, gray * 0.95], axis=-1).astype(np.uint8)
        elif key == "mola-color":
            base = self._ramp(
                e_norm,
                [
                    (0.00, (36, 36, 148)),   # deep blue (-8 km)
                    (0.14, (40, 120, 212)),  # azure
                    (0.24, (46, 194, 190)),  # cyan
                    (0.34, (78, 198, 92)),   # green
                    (0.46, (226, 222, 68)),  # yellow
                    (0.58, (238, 132, 42)),  # orange
                    (0.76, (206, 46, 42)),   # crimson
                    (0.92, (218, 152, 186)), # alpine pink
                    (1.00, (248, 248, 250)), # white summit
                ],
            )
            rgb = np.clip(base * (0.55 + 0.55 * shade[:, :, None]), 0, 255).astype(np.uint8)
        elif key == "mola-shaded":
            g = np.clip((48.0 + 178.0 * shade + 24.0 * (e_norm - 0.3)), 18, 245)
            rgb = np.stack([g, g, g], axis=-1).astype(np.uint8)
        elif key == "themis-day":
            t = np.clip(0.55 * shade + 0.25 * e_norm + 0.20 * (1.0 - np.abs(LAT) / 90.0), 0.0, 1.0)
            base = self._ramp(
                t,
                [
                    (0.0, (24, 18, 34)),
                    (0.3, (96, 36, 46)),
                    (0.6, (198, 96, 42)),
                    (0.85, (244, 184, 72)),
                    (1.0, (255, 244, 196)),
                ],
            )
            rgb = np.clip(base, 0, 255).astype(np.uint8)
        elif key == "themis-night":
            slope_n = np.clip(self.slope_grid()[::-1, :] / 8.0, 0.0, 1.0)
            t = np.clip(0.52 * slope_n + 0.28 * (1.0 - np.abs(LAT) / 95.0) + 0.20 * shade, 0.0, 1.0)
            base = self._ramp(
                t,
                [
                    (0.0, (12, 18, 42)),
                    (0.32, (46, 34, 98)),
                    (0.62, (36, 134, 178)),
                    (0.85, (142, 224, 210)),
                    (1.0, (248, 244, 178)),
                ],
            )
            rgb = np.clip(base, 0, 255).astype(np.uint8)
        elif key == "sim3292-geology":
            # Stratigraphic province visualization (Noachian / Hesperian / Amazonian / Volcanic / Polar)
            rgb_f = np.zeros((E.shape[0], E.shape[1], 3), dtype=np.float64)
            # Base: Southern Noachian highlands
            rgb_f[:] = np.array([186.0, 132.0, 82.0])
            # Northern Amazonian lowlands
            north = (LAT > -2.0) & (E < 0.0)
            rgb_f[north] = np.array([218.0, 196.0, 142.0])
            # Hesperian transition / ridged plains
            hesp = ((LAT >= -25.0) & (LAT <= 15.0) & (E >= -1500.0) & (E <= 1800.0)) | (E < -3200.0)
            rgb_f[hesp] = np.array([154.0, 172.0, 114.0])
            # Deep basins (Hellas, Argyre, Isidis)
            basin = E < -4000.0
            rgb_f[basin] = np.array([86.0, 146.0, 154.0])
            # Volcanic provinces (Tharsis, Olympus, Elysium)
            volc = E > 3600.0
            rgb_f[volc] = np.array([196.0, 82.0, 108.0])
            # Polar layered deposits
            polar = np.abs(LAT) > 78.0
            rgb_f[polar] = np.array([224.0, 228.0, 244.0])
            rgb = np.clip(rgb_f * (0.55 + 0.50 * shade[:, :, None]), 0, 255).astype(np.uint8)
        elif key in ("swim-probability", "depth-to-ice"):
            # Mid-to-high latitude subsurface water-ice stability heuristic (SWIM-consistent [SIM])
            lat_abs = np.abs(LAT)
            prob = np.clip((lat_abs - 26.0) / 34.0, 0.0, 1.0)
            # Boost known SWIM mid-latitude zones (Arcadia, Utopia, Deuteronilus, Phlegra)
            for la0, lo0, s_la, s_lo, boost in [
                (45.0, 190.0, 10.0, 22.0, 0.35),
                (46.0, 114.0, 10.0, 22.0, 0.28),
                (39.0, 336.0, 9.0, 18.0, 0.30),
                (-42.0, 85.0, 10.0, 20.0, 0.22),
            ]:
                dlon = ((LON - lo0 + 180.0) % 360.0) - 180.0
                prob += boost * np.exp(-0.5 * (((LAT - la0) / s_la) ** 2 + (dlon / s_lo) ** 2))
            prob = np.clip(prob * np.where(E > 4500.0, 0.35, 1.0), 0.0, 1.0)
            stops = (
                [
                    (0.0, (42, 34, 34)),
                    (0.25, (34, 62, 104)),
                    (0.55, (36, 152, 208)),
                    (0.80, (92, 224, 242)),
                    (1.0, (226, 250, 255)),
                ]
                if key == "swim-probability"
                else [
                    (0.0, (38, 30, 32)),
                    (0.30, (62, 52, 146)),
                    (0.60, (36, 134, 232)),
                    (0.82, (46, 218, 222)),
                    (1.0, (214, 252, 255)),
                ]
            )
            base = self._ramp(prob, stops)
            rgb = np.clip(base * (0.58 + 0.48 * shade[:, :, None]), 0, 255).astype(np.uint8)
        else:
            # Default fallback: mars-relief
            return self.render_raster_png("mars-relief")

        data = self._encode_png_rgb(rgb)
        self._raster_cache[key] = data
        return data

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
