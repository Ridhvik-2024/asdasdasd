"""Spatial-engine submission tests (Person B scope).

Covers the five required planetary-boundary and provenance behaviours:

1. Terrain detail changes smoothly between neighbouring coordinates.
2. Elevation interpolation works across 0/360.
3. A small antimeridian bounding box returns a small region.
4. Polygon area crossing the antimeridian is sensible.
5. Walk View reports the correct terrain source.

These tests are written to FAIL on the pre-fix code and PASS after the fixes
in app/terrain.py, app/mars.py and app/routers/walkview.py.
"""
import math

import numpy as np
from fastapi.testclient import TestClient

from app import mars, terrain
from app.main import app

T = terrain.engine().ensure()
c = TestClient(app)


# --------------------------------------------------------------------------- 1
def test_detail_smooth_between_neighbouring_coordinates():
    """_detail() must be a spatially continuous field, not per-coordinate noise.

    The previous implementation hashed a fresh seed from every (lat, lon) and
    evaluated noise at a fixed lattice position, so points ~60 m apart could
    swing by the full +/-amplitude (~140 m). A continuous field changes by a
    tiny fraction of that over the same step.
    """
    cell_m = 500.0  # amplitude saturates at 140 m
    lat, lon = 18.44, 77.45
    a = T._detail(lat, lon, cell_m)

    # determinism: identical input -> identical output
    assert T._detail(lat, lon, cell_m) == a

    # neighbouring coordinates (~60 m apart) must blend, not jump.
    # Old code could differ by up to ~140 m here; new code is sub-metre.
    for dlat, dlon in [(0.001, 0.0), (0.0, 0.001), (0.001, 0.001), (-0.001, 0.001)]:
        b = T._detail(lat + dlat, lon + dlon, cell_m)
        assert abs(b - a) < 5.0, "detail jump too large for %.4f deg step: %.4f" % (
            dlat or dlon, abs(b - a))

    # an even finer step (~6 m) must be even smoother
    assert abs(T._detail(lat + 0.0001, lon, cell_m) - a) < 1.0

    # and the field must genuinely vary over a few hundred metres (not constant)
    samples = [T._detail(lat + i * 0.0005, lon, cell_m) for i in range(40)]
    assert max(samples) - min(samples) > 0.05, "detail must vary spatially"


def test_detail_continuous_across_antimeridian():
    """Detail noise is longitude-periodic, so the 0/360 seam is continuous."""
    cell_m = 500.0
    # a point just west of the seam and the same point expressed east of 360
    west = T._detail(18.44, 359.999, cell_m)
    east = T._detail(18.44, -0.001, cell_m)  # normalises to 359.999
    assert abs(west - east) < 1e-9


# --------------------------------------------------------------------------- 2
def test_elevation_interpolation_wraps_at_0_360():
    """elev() must interpolate across the 0/360 seam, not extrapolate past the
    final grid column. Two points straddling the seam by 0.02 deg (~1.2 km)
    must produce nearly equal elevations (both interpolate the same two
    boundary columns); the pre-fix extrapolation produced unrelated values."""
    lat = 18.44
    e_west = T.elev(lat, 359.99)
    e_east = T.elev(lat, 0.01)
    assert abs(e_west - e_east) < 100.0, (
        "seam discontinuity: elev(359.99)=%.2f elev(0.01)=%.2f" % (e_west, e_east))

    # exactly at the seam both representations agree
    assert T.elev(lat, 360.0) == T.elev(lat, 0.0)

    # full periodicity: lon and lon+360 are the same point
    for lon in (0.0, 0.3, 133.8, 359.9):
        assert T.elev(lat, lon) == T.elev(lat, lon - 360.0)
        assert T.elev(lat, lon) == T.elev(lat, lon + 360.0)


def test_elevation_landmarks_unchanged_by_wrap_fix():
    """The longitude-wrap fix must not perturb interior sampling."""
    assert T.elev(18.65, 133.8) > 15000, "Olympus Mons still > 15 km"
    assert T.elev(-42.4, 70.5) < -5000, "Hellas still < -5 km"


def test_slope_wraps_at_seam():
    """slope() picks the containing cell with periodic longitude indexing."""
    # a longitude just below 360 must not fall off the end of the grid
    s = T.slope(18.44, 359.9)
    assert 0.0 <= s <= 85.0
    assert T.slope(18.44, 359.9) == T.slope(18.44, -0.1)


# --------------------------------------------------------------------------- 3
def test_small_antimeridian_bbox_returns_small_region():
    """A 2 deg x 20 deg box crossing the seam must select ~20 deg of longitude
    (the union of [350,360) and [0,10]), not the ~340 deg swapped span the old
    longitude swap produced."""
    st = T.bbox_stats((10.0, 350.0, 12.0, 10.0))
    assert st["crosses_antimeridian"] is True

    # rebuild the expected union directly from the grid and compare the stats
    LATS, LONS = T._lats, T._lons
    i0 = int(np.clip(np.searchsorted(LATS, 10.0), 0, len(LATS) - 1))
    i1 = int(np.clip(np.searchsorted(LATS, 12.0) + 1, 1, len(LATS)))
    ja = int(np.clip(np.searchsorted(LONS, 350.0), 0, len(LONS) - 1))
    jb = int(np.clip(np.searchsorted(LONS, 10.0) + 1, 1, len(LONS)))
    expect = np.concatenate([T.grid[i0:i1, ja:], T.grid[i0:i1, :jb]], axis=1)

    assert abs(st["mean_elev_m"] - float(expect.mean())) < 1e-6
    assert abs(st["min_elev_m"] - float(expect.min())) < 1e-6
    assert abs(st["max_elev_m"] - float(expect.max())) < 1e-6

    # the crossing box must be far smaller than the genuinely-large 340 deg box
    n_cross = expect.size
    j0h = int(np.clip(np.searchsorted(LONS, 10.0), 0, len(LONS) - 1))
    j1h = int(np.clip(np.searchsorted(LONS, 350.0) + 1, 1, len(LONS)))
    n_huge = T.grid[i0:i1, j0h:j1h].size
    assert n_cross < n_huge / 10, (
        "antimeridian box selected %d cells (huge=%d); swap bug still present"
        % (n_cross, n_huge))


def test_non_crossing_bbox_unchanged():
    """A normal bbox must keep behaving as before (no spurious wrap flag)."""
    st = T.bbox_stats((10.0, 100.0, 12.0, 102.0))
    assert st["crosses_antimeridian"] is False
    assert st["bbox"] == [10.0, 100.0, 12.0, 102.0]


# --------------------------------------------------------------------------- 4
def test_polygon_area_crossing_antimeridian_is_sensible():
    """A 2x2 deg box spanning 359 -> 1 must report ~2 deg of longitude, not
    ~358 deg. Pre-fix area was ~2.5e6 km2; correct is ~1.4e4 km2."""
    crossing = mars.poly_area_km2([[10, 359], [10, 1], [12, 1], [12, 359]])
    reference = mars.poly_area_km2([[10, 100], [10, 102], [12, 102], [12, 100]])

    # sensible absolute range for a 2x2 deg box near the equator
    assert 5_000.0 < crossing < 30_000.0, "crossing area %.1f km2 out of range" % crossing
    # the buggy value (~2.46e6 km2) must be impossible
    assert crossing < 100_000.0, "antimeridian area inflated: %.1f km2" % crossing
    # and it must match a non-crossing box of the same size and latitude
    assert abs(crossing - reference) < 0.25 * reference, (
        "crossing %.1f vs reference %.1f km2" % (crossing, reference))


def test_polygon_area_accepts_dict_points():
    """poly_area_km2 must keep accepting {lat, lon} dicts as well as tuples."""
    a = mars.poly_area_km2([{"lat": 10, "lon": 290}, {"lat": 10, "lon": 292},
                            {"lat": 12, "lon": 292}, {"lat": 12, "lon": 290}])
    assert 400.0 < a < 60_000.0  # matches the Phase 1 measurement-suite gate


# --------------------------------------------------------------------------- 5
def test_walkview_reports_synthetic_terrain_source():
    """Walk View init must NOT claim MOLA-derived terrain; the engine supplies
    synthetic terrain and the provenance must say so."""
    r = c.post("/walkview/init", json={"lat": 18.44, "lon": 77.45}).json()
    src = r["terrain_relief"]["source"]
    assert "MOLA-derived" not in src, "Walk View must not claim MOLA-derived terrain: %s" % src
    assert "synthetic" in src.lower(), "source must say synthetic: %s" % src
    assert "[SIM]" in src, "source must carry the [SIM] advisory label: %s" % src


def test_walkview_mesh_provenance_consistent():
    """The Walk View mesh endpoint must also label terrain as synthetic."""
    m = c.get("/walkview/patch", params={"lat": 18.44, "lon": 77.45,
                                         "radius_km": 2.0, "n": 16}).json()
    assert "[SIM]" in m["provenance"]["source"]
    assert "demo-synthetic-grid" in m["provenance"]["source"]
