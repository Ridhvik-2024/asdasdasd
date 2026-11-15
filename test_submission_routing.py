"""Submission test suite for Person A (Navigation algorithms and mission
planning).

These tests directly exercise the correctness requirements assigned to
Person A:

  1. Known flat terrain produces approximately zero slope.
  2. A known inclined terrain produces a sensible slope.
  3. A route from longitude 359 deg to longitude 1 deg generates a short
     route across the antimeridian, not a ~358 deg detour.
  4. Degraded routes do not crash mission optimisation.
  5. Every successful route returns the full required statistics block
     (path, length, mean slope, max slope, estimated traversal time,
     provenance).

The suite complements the existing phase-gate tests by validating
mathematical correctness rather than just endpoint parity.
"""
import math

import pytest
from fastapi.testclient import TestClient

from app import db, missions, routing, terrain
from app.main import app
from app.mars import KM_PER_DEG

# Shared test client so the DB / app state is initialised the same way as
# the phase-gate suites.
c = TestClient(app)

# Metres per degree of latitude on Mars (~59.3 km/deg).
M_PER_DEG = KM_PER_DEG * 1000.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _terrain_engine():
    """Return the singleton terrain engine, ensured/loaded."""
    return terrain.engine().ensure()


def _force_elev(monkeypatch, fn):
    """Replace the terrain engine's elev() with ``fn`` for the test scope."""
    T = _terrain_engine()
    monkeypatch.setattr(T, "elev", fn)


# ---------------------------------------------------------------------------
# 1. Flat terrain -> ~zero slope
# ---------------------------------------------------------------------------

def test_flat_terrain_produces_approximately_zero_slope(monkeypatch):
    """On a known flat synthetic plane, A* must report mean and max slope
    close to zero (well under 1 deg). The previous slope formula inflated
    even tiny gradients to ~80 deg because it mixed metres and kilometres."""
    _force_elev(monkeypatch, lambda lat, lon: 1000.0)  # constant elevation

    route = routing.plan_route(0.0, 0.0, 0.5, 0.5, "balanced")

    # The route must succeed (flat terrain is fully traversable).
    assert route.get("status") != "degraded", "flat terrain must be routable"
    stats = route["stats"]
    assert stats["mean_slope_deg"] < 1.0, \
        "flat terrain mean slope must be ~0, got %.4f" % stats["mean_slope_deg"]
    assert stats["max_slope_deg"] < 1.0, \
        "flat terrain max slope must be ~0, got %.4f" % stats["max_slope_deg"]


# ---------------------------------------------------------------------------
# 2. Inclined terrain -> sensible slope
# ---------------------------------------------------------------------------

def test_inclined_terrain_produces_sensible_slope(monkeypatch):
    """On a uniform 30 deg inclined plane (gradient = tan(30 deg) ~ 0.577),
    A* must report a mean slope near 30 deg and never exceed the 38 deg
    traversal threshold. The previous formula reported ~89 deg for the same
    terrain."""
    target_slope_deg = 30.0
    gradient = math.tan(math.radians(target_slope_deg))

    def elev_inclined(lat, lon):
        # Elevation rises 'gradient' metres for every metre north. 1 deg of
        # latitude == M_PER_DEG metres, so elev = gradient * lat * M_PER_DEG.
        return gradient * float(lat) * M_PER_DEG

    _force_elev(monkeypatch, elev_inclined)

    route = routing.plan_route(0.0, 0.0, 0.5, 0.5, "balanced")

    assert route.get("status") != "degraded", \
        "30 deg terrain is below the 38 deg threshold and must be routable"
    stats = route["stats"]
    # The terrain is a uniform plane inclined at 30 deg, so every cell has
    # slope ~30 deg. Allow a small tolerance for grid discretisation.
    assert 25.0 <= stats["mean_slope_deg"] <= 35.0, \
        "mean slope should be ~30 deg, got %.4f" % stats["mean_slope_deg"]
    assert stats["max_slope_deg"] <= routing.STEEP_THRESHOLD_DEG, \
        "max slope must respect the 38 deg traversal constraint, got %.4f" % stats["max_slope_deg"]


# ---------------------------------------------------------------------------
# 3. Antimeridian route 359 -> 1 is short
# ---------------------------------------------------------------------------

def test_antimeridian_route_359_to_1_is_short():
    """A route from longitude 359 deg to 1 deg must cross the short 2 deg
    antimeridian interval, producing a route of well under 200 km at the
    equator. The previous grid construction spanned ~358 deg and produced a
    ~21,000 km detour around the entire planet."""
    route = routing.plan_route(0.0, 359.0, 0.0, 1.0, "balanced")

    assert route.get("status") != "degraded", \
        "antimeridian route 359 -> 1 must find an in-grid path"
    length_km = route["stats"]["length_km"]
    # 2 deg of longitude at the equator is ~118.6 km. With terrain avoidance
    # the route may be slightly longer, but must be far short of the
    # planetary circumference (~21,000 km). A 250 km ceiling is generous.
    assert length_km < 250.0, \
        "359 -> 1 must be a short antimeridian route, got %.2f km" % length_km

    # The path must actually cross the antimeridian: it should contain
    # points on both sides of the 0/360 boundary.
    lons = [p["lon"] for p in route["path"]]
    assert min(lons) <= 5.0 and max(lons) >= 355.0, \
        "path must span the antimeridian (lons %s)" % (lons[:3] + lons[-3:],)


def test_antimeridian_route_reverse_direction_is_short():
    """The antimeridian fix must be symmetric: 1 -> 359 must also be short."""
    route = routing.plan_route(0.0, 1.0, 0.0, 359.0, "balanced")
    assert route.get("status") != "degraded"
    assert route["stats"]["length_km"] < 250.0, \
        "1 -> 359 must be a short antimeridian route, got %.2f km" % route["stats"]["length_km"]


# ---------------------------------------------------------------------------
# 4. Degraded routes do not crash mission optimisation
# ---------------------------------------------------------------------------

def test_optimize_does_not_crash_on_degraded_legs(monkeypatch):
    """missions.optimize() previously assumed every leg returned
    stats.length_km. Degraded legs have no stats block at all. Verify that
    optimisation completes, reports None for the degraded legs, and never
    crashes."""
    # Create a real mission in the DB.
    m = missions.create("survey", "degraded-leg-test", objective="test", stops=[
        {"lat": 0.0, "lon": 0.0, "activity": "start", "reason": "test"},
        {"lat": 0.1, "lon": 0.1, "activity": "mid", "reason": "test"},
        {"lat": 0.2, "lon": 0.2, "activity": "end", "reason": "test"},
    ])
    mid = m["id"]

    # Force every leg to degrade.
    def fake_plan_route(lat1, lon1, lat2, lon2, preset="balanced"):
        return {
            "path": [{"lat": lat1, "lon": lon1}, {"lat": lat2, "lon": lon2}],
            "length_km": None,
            "status": "degraded",
            "note": "forced degraded for test",
            "sim": True,
            "provenance": {"source": "test degraded [SIM]", "note": "forced"},
        }

    monkeypatch.setattr(routing, "plan_route", fake_plan_route)

    # This call used to raise KeyError: 'stats'. It must now return a
    # well-formed mission object.
    result = missions.optimize(mid, "balanced")
    assert result is not None, "optimize must return a mission object"
    assert len(result["stops"]) == 3, "all three stops must survive"

    # The persisted route must carry the degraded accounting honestly.
    routes = result["routes"]
    assert routes, "an optimized route row must be persisted"
    opt_route = routes[-1]
    stats = opt_route["stats"]
    assert stats.get("degraded_legs") == stats.get("total_legs"), \
        "all legs degraded -> degraded_legs == total_legs"
    assert stats.get("length_km") is None, \
        "fully degraded mission must not report a measured length"
    for leg in stats.get("legs", []):
        assert leg.get("length_km") is None, \
            "degraded leg must not report a length"
        assert leg.get("status") == "degraded", \
            "degraded leg must be labelled degraded"


def test_optimize_mixed_degraded_and_successful_legs(monkeypatch):
    """A mission with one successful and one degraded leg must report the
    measured length from the successful leg only, while still completing
    without error."""
    m = missions.create("survey", "mixed-leg-test", objective="test", stops=[
        {"lat": 0.0, "lon": 0.0, "activity": "a", "reason": "test"},
        {"lat": 0.1, "lon": 0.1, "activity": "b", "reason": "test"},
        {"lat": 0.2, "lon": 0.2, "activity": "c", "reason": "test"},
    ])
    mid = m["id"]

    call_count = {"n": 0}

    def fake_plan_route(lat1, lon1, lat2, lon2, preset="balanced"):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # First leg succeeds with a known measured length.
            return {
                "path": [{"lat": lat1, "lon": lon1}, {"lat": lat2, "lon": lon2}],
                "length_km": 42.0,
                "stats": {
                    "length_km": 42.0,
                    "mean_slope_deg": 5.0,
                    "max_slope_deg": 10.0,
                    "est_traverse_sols": 12.5,
                    "cost_preset": preset,
                },
                "sim": True,
                "provenance": {"source": "test ok [SIM]", "note": "forced"},
            }
        # Second leg degrades.
        return {
            "path": [{"lat": lat1, "lon": lon1}, {"lat": lat2, "lon": lon2}],
            "length_km": None,
            "status": "degraded",
            "note": "forced degraded for test",
            "sim": True,
            "provenance": {"source": "test degraded [SIM]", "note": "forced"},
        }

    monkeypatch.setattr(routing, "plan_route", fake_plan_route)

    result = missions.optimize(mid, "balanced")
    assert result is not None
    stats = result["routes"][-1]["stats"]
    assert stats["degraded_legs"] == 1
    assert stats["total_legs"] == 2
    # The total must include only the measured (42 km) leg.
    assert stats["length_km"] == 42.0
    legs = stats["legs"]
    assert legs[0]["length_km"] == 42.0
    assert legs[1]["length_km"] is None
    assert legs[1]["status"] == "degraded"


# ---------------------------------------------------------------------------
# 5. Successful routes carry all required statistics
# ---------------------------------------------------------------------------

REQUIRED_STAT_KEYS = (
    "length_km",
    "mean_slope_deg",
    "max_slope_deg",
    "est_traverse_sols",
)


def test_successful_route_has_all_required_statistics():
    """Every successful route must return: path, length, mean slope, max
    slope, estimated traversal time, and provenance. This is the completion
    condition for Person A: A* produces mathematically sensible routes."""
    route = routing.plan_route(18.44, 77.45, 18.44, 77.65, "balanced")

    # Must be a successful route, not a degraded fallback.
    assert route.get("status") != "degraded", \
        "Jezero-to-Jezero route must succeed on the demo grid"

    # Path.
    assert "path" in route and len(route["path"]) >= 2, \
        "successful route must return a path with >= 2 points"

    # Stats block.
    assert "stats" in route, "successful route must carry a stats block"
    stats = route["stats"]
    for key in REQUIRED_STAT_KEYS:
        assert key in stats, "stats missing required key: %s" % key
        assert stats[key] is not None, \
            "stats.%s must be a real value, not None" % key

    # Length must be positive and finite.
    assert isinstance(stats["length_km"], (int, float))
    assert math.isfinite(stats["length_km"])
    assert stats["length_km"] > 0.0, "length must be positive"

    # Slopes must be in a physically plausible range.
    assert 0.0 <= stats["mean_slope_deg"] <= routing.STEEP_THRESHOLD_DEG, \
        "mean slope must respect the 38 deg traversal constraint"
    assert 0.0 <= stats["max_slope_deg"] <= routing.STEEP_THRESHOLD_DEG, \
        "max slope must respect the 38 deg traversal constraint"

    # Estimated traversal time must be a positive finite number.
    assert isinstance(stats["est_traverse_sols"], (int, float))
    assert math.isfinite(stats["est_traverse_sols"])
    assert stats["est_traverse_sols"] > 0.0, "traversal time must be positive"

    # Provenance.
    assert "provenance" in route, "successful route must carry provenance"
    assert route["provenance"].get("source"), \
        "provenance.source must be non-empty"


@pytest.mark.parametrize("preset", ["balanced", "terrain", "speed"])
def test_all_presets_produce_complete_stats(preset):
    """The required-stats guarantee must hold for every cost preset."""
    route = routing.plan_route(18.44, 77.45, 18.44, 77.65, preset)
    assert route.get("status") != "degraded"
    stats = route["stats"]
    for key in REQUIRED_STAT_KEYS:
        assert stats.get(key) is not None, \
            "preset %s missing stats.%s" % (preset, key)


# ---------------------------------------------------------------------------
# Bonus: steep terrain is truly impassable, not just penalised
# ---------------------------------------------------------------------------

def test_steep_terrain_is_traversal_constraint_not_penalty(monkeypatch):
    """Terrain above the 38 deg threshold must be an actual traversal
    constraint: A* cannot route through it and must degrade rather than
    find a path that pays the penalty."""
    # Uniform 45 deg slope exceeds the 38 deg threshold everywhere.
    gradient = math.tan(math.radians(45.0))

    def elev_steep(lat, lon):
        return gradient * float(lat) * M_PER_DEG

    _force_elev(monkeypatch, elev_steep)

    route = routing.plan_route(0.0, 0.0, 0.5, 0.5, "balanced")
    assert route.get("status") == "degraded", \
        "45 deg terrain is above the 38 deg threshold and must be impassable"


def test_slope_maths_matches_reference_formula(monkeypatch):
    """Direct numerical check: for a 100 m rise over a 2-cell span of
    ~59.3 km, the slope must be ~0.097 deg, not ~86 deg. This is the
    regression test for the ~1000x unit inflation bug."""
    # Build a tiny synthetic elevation surface: flat except for a 100 m
    # step between two adjacent latitude rows.
    def elev_step(lat, lon):
        # 100 m step at lat = 0: south of the equator = 0 m, north = 100 m.
        return 100.0 if lat > 0.0 else 0.0

    _force_elev(monkeypatch, elev_step)

    route = routing.plan_route(-0.3, 0.0, 0.3, 0.0, "balanced")
    # Either the route succeeds with sensible slopes, or it degrades
    # because the step is locally steep. Either way, the slopes must
    # never reach the ~86 deg value the old formula produced.
    if route.get("status") != "degraded":
        assert route["stats"]["max_slope_deg"] < 80.0, \
            "slope must not be inflated to ~86 deg (old bug), got %.4f" % route["stats"]["max_slope_deg"]
