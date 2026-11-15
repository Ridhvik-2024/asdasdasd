#!/usr/bin/env python3
"""Generate the demo global elevation grid (0.5 deg, 720x360) used by the
terrain engine in place of the (large) real MOLA MEGDR product.

HONESTY: this grid is a synthetic approximation of Mars topography built from
published landmark geometry (Olympus Mons, Hellas, Valles Marineris, the
north-south dichotomy, ...). The elevation service labels its source as
"demo-synthetic-grid [SIM]" and documents the swap path to the real MOLA MEGDR
4 ppd product. Do NOT present these values as measured MOLA data.
"""
import numpy as np
from pathlib import Path

NLON, NLAT = 720, 360
lons = np.linspace(0.25, 359.75, NLON)          # east 0-360, cell centers
lats = np.linspace(-89.75, 89.75, NLAT)
LON, LAT = np.meshgrid(lons, lats)
E = np.zeros((NLAT, NLON))

KM_PER_DEG = 59.3  # Mars


def sig(x):
    return 1.0 / (1.0 + np.exp(-x))


def gauss_m(lat0, lon0, sig_km, amp_m):
    """Gaussian topography anomaly, amplitude in meters, sigma in km."""
    dlat = (LAT - lat0) * KM_PER_DEG
    dlon = ((LON - lon0 + 180) % 360 - 180) * KM_PER_DEG * np.cos(np.radians(lat0))
    r2 = (dlon ** 2 + dlat ** 2) / (sig_km ** 2)
    return amp_m * np.exp(-0.5 * r2)


def ring_m(lat0, lon0, r_km, w_km, amp_m):
    dlat = (LAT - lat0) * KM_PER_DEG
    dlon = ((LON - lon0 + 180) % 360 - 180) * KM_PER_DEG * np.cos(np.radians(lat0))
    r = np.sqrt(dlon ** 2 + dlat ** 2)
    return amp_m * np.exp(-0.5 * ((r - r_km) / w_km) ** 2)


def upsample(a, H, W):
    kh, kw = a.shape
    yi = np.linspace(0, kh - 1, H)
    xi = np.linspace(0, kw - 1, W)
    y0 = np.floor(yi).astype(int); y1 = np.clip(y0 + 1, 0, kh - 1); wy = yi - y0
    x0 = np.floor(xi).astype(int); x1 = np.clip(x0 + 1, 0, kw - 1); wx = xi - x0
    rows = a[:, x0] * (1 - wx) + a[:, x1] * wx          # (kh, W)
    return rows[y0, :] * (1 - wy[:, None]) + rows[y1, :] * wy[:, None]


# --- planetary dichotomy: northern lowlands vs southern highlands
s = sig((LAT + 2.0) / 6.0)
E += -2000 + 3200 * s
# Tharsis bulge
E += gauss_m(5, 253, 1500, 4500)
# major volcanic shields (summit heights above local datum)
E += gauss_m(18.65, 133.8, 280, 17500)   # Olympus Mons (~21.9 km above datum w/ bulge+caldera)
E += gauss_m(18.65, 133.8, 30, 2500)     # Olympus caldera complex
E += gauss_m(11.8, 255.9, 90, 12000)     # Ascraeus
E += gauss_m(0.8, 247.0, 70, 10500)      # Pavonis
E += gauss_m(-8.35, 240.0, 90, 12500)    # Arsia
E += gauss_m(25.0, 147.2, 120, 9000)     # Elysium Mons
E += gauss_m(40.5, 250.1, 250, 4000)     # Alba Mons
E += gauss_m(32.1, 150.2, 40, 4000)      # Hecates Tholus
E += gauss_m(24.6, 263.3, 25, 3500)      # Ceraunius Tholus
E += gauss_m(13.5, 262.5, 30, 3000)      # Tharsis Tholus
# impact basins
E += gauss_m(-42.4, 70.5, 650, -4200)    # Hellas outer
E += gauss_m(-42.4, 70.5, 250, -1200)    # Hellas inner floor
E += ring_m(-42.4, 70.5, 1100, 90, 1500)
E += gauss_m(-50.0, 318.0, 300, -3500)   # Argyre
E += ring_m(-50.0, 318.0, 380, 25, 900)
E += gauss_m(13.0, 87.5, 330, -2000)     # Isidis
E += gauss_m(46.7, 117.5, 600, -2200)    # Utopia
# craters of interest
E += gauss_m(-5.4, 137.8, 60, -2600)     # Gale depression
E += ring_m(-5.4, 137.8, 70, 7, 900)     # Gale rim
E += gauss_m(-5.3, 137.7, 18, 2600)      # Aeolis Mons (central mound)
E += gauss_m(18.45, 77.7, 18, -3600)     # Jezero floor (~-2.4 km)
E += ring_m(18.45, 77.7, 22, 3, 500)     # Jezero rim
E += gauss_m(-14.6, 175.5, 75, -900)     # Gusev
E += gauss_m(-2.28, 354.5, 11, -350)     # Endeavour
# Valles Marineris trench along a polyline
path = [(267, -6.0), (275, -7.5), (285, -8.5), (295, -10.5), (305, -12.5), (313, -14.0)]
D, W_ = 5000, 55.0
plats = np.array([p[1] for p in path]); plons = np.array([p[0] for p in path])
seg = np.zeros((NLAT, NLON))
for i in range(len(path) - 1):
    t = np.linspace(0, 1, 60)
    px = plons[i] + (plons[i + 1] - plons[i]) * t
    py = plats[i] + (plats[i + 1] - plats[i]) * t
    dlat = (LAT[:, :, None] - py[None, None, :]) * KM_PER_DEG
    dlon = ((LON[:, :, None] - px[None, None, :] + 180) % 360 - 180) * KM_PER_DEG * np.cos(np.radians(py))[None, None, :]
    d = np.sqrt(dlon ** 2 + dlat ** 2).min(axis=2)
    seg = np.maximum(seg, D * np.exp(-0.5 * (d / W_) ** 2))
E -= seg
# polar ice domes
E += 800 * np.exp(-((90 - LAT) / 8.0) ** 2)
E += 400 * np.exp(-((-90 - LAT) / 8.0) ** 2)
# Medusae Fossae subtle depression
E += gauss_m(-3.0, 165.0, 200, -300)

# --- deterministic fractal relief
rng = np.random.default_rng(20261114)
noise = np.zeros((NLAT, NLON))
for k, weight in ((2, 1.0), (4, 0.5), (8, 0.25), (16, 0.12), (32, 0.06), (64, 0.03)):
    a = rng.random((k, 2 * k))
    noise += weight * (upsample(a, NLAT, NLON) - 0.5)
E += noise * 900.0
E += noise * 700.0 * sig(-LAT)   # rougher southern highlands

E = np.clip(E, -8200, 21500).astype(np.float32)
out = Path(__file__).resolve().parents[1] / "data" / "seeds" / "demo_grid.npz"
out.parent.mkdir(parents=True, exist_ok=True)
np.savez_compressed(out, elev=E, lats=lats.astype(np.float32), lons=lons.astype(np.float32))
print("demo grid written:", out, E.shape, "range m:", float(E.min()), float(E.max()))
