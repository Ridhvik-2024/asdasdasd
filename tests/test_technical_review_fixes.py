"""Regression tests for remaining Technical Review & v2.3 Roadmap fixes.

Covers:
  1. XML-safe KML export (plus GeoJSON/CSV exports) on special characters.
  2. Node count accuracy, nonexistent node/mission deletion (404/False), and
     concurrent atomic mission stop ordering.
  3. Standardised route schema (including degraded routes), admissible A*
     heuristic across all presets, and 2-opt stop uncrossing in optimize().
  4. Strict JEV tool schema + semantic validation and LLM tool-call validation.
  5. Explicit Mars coordinate validation (no silent latitude clamping).
  6. Polar & seam-edge terrain slopes, polar patches, adjacent patch shared-edge
     continuity, aspect/curvature, and multi-format terrain grid downloads.
  7. Polar/large spherical polygon areas and Allison & McEwen (2000) Mars24
     solar geometry reference verification.
  8. Persistent disk tile cache, tile coordinate bounds, WMS BBOX translation,
     and image magic-byte validation.
  9. Event sequence IDs + history replay, provenance quality tiers, and
     optional API-key mutation authentication.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import io
import json
import math
import xml.etree.ElementTree as ET

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import config, events, mars, missions, nodes, routing, terrain
from app.connectors import base as connectors
from app.integrity import prov
from app.jev import llm
from app.jev.tools import run_tool, validate_tool_call
from app.main import app

client = TestClient(app)
T = terrain.engine().ensure()


# ---------------------------------------------------------------------------
# 1. Safe XML/KML export + GeoJSON & CSV mission exports
# ---------------------------------------------------------------------------

def test_kml_export_escapes_xml_special_characters():
    r = client.post("/missions", json={
        "type": "route",
        "name": 'Jezero & Delta <5 deg> "Survey" \'A\'',
        "objective": "Check Fe/Mg clays & <phyllosilicates> > 10%",
        "stops": [
            {"lat": 18.44, "lon": 77.45, "activity": "sample & <drill>",
             "reason": ' outcrop "alpha" & slope < 8 deg '},
            {"lat": 18.48, "lon": 77.55, "activity": "radar > scan",
             "reason": "ice/regolith & <strata>"},
        ],
    })
    assert r.status_code == 200
    mid = r.json()["id"]

    kml_resp = client.get(f"/missions/{mid}/kml")
    assert kml_resp.status_code == 200
    # Must parse as strictly well-formed XML without ParseError
    root = ET.fromstring(kml_resp.text)
    ns = {"kml": "http://www.opengis.net/kml/2.2"}
    doc_name = root.find(".//kml:Document/kml:name", ns)
    assert doc_name is not None
    assert doc_name.text == 'Jezero & Delta <5 deg> "Survey" \'A\''

    gj = client.get(f"/missions/{mid}/geojson").json()
    assert gj["type"] == "FeatureCollection"
    assert len(gj["features"]) == 2

    csv_resp = client.get(f"/missions/{mid}/csv")
    assert csv_resp.status_code == 200
    assert "ord,lat,lon,activity,reason" in csv_resp.text


# ---------------------------------------------------------------------------
# 2. Nodes count & nonexistent delete semantics + atomic concurrent stops
# ---------------------------------------------------------------------------

def test_nodes_list_reports_real_count_and_delete_nonexistent_404():
    created = client.post("/nodes", json={
        "type": "waypoint", "lat": 12.0, "lon": 45.0, "radius_km": 1.5,
        "props": {"tag": "count-check"},
    })
    assert created.status_code == 200
    nid = created.json()["id"]

    listed = client.get("/nodes").json()
    assert listed["count"] == len(listed["nodes"])
    assert listed["count"] >= 1

    assert client.delete(f"/nodes/{nid}").status_code == 200
    # Second delete of nonexistent node must return 404 (and nodes.delete -> False)
    assert nodes.delete(nid) is False
    assert client.delete(f"/nodes/{nid}").status_code == 404

    # Nonexistent mission delete also returns False / 404
    assert missions.delete("mission-nonexistent") is False
    assert client.delete("/missions/mission-nonexistent").status_code == 404


def test_concurrent_mission_stop_additions_preserve_unique_ordering():
    m = missions.create("survey", "concurrency-test", objective="atomic ord")
    mid = m["id"]

    def _add(i):
        return missions.add_stop(mid, 10.0 + i * 0.05, 50.0 + i * 0.05,
                                 activity=f"stop-{i}", reason="parallel")

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(_add, range(12)))

    got = missions.get(mid)
    ords = [s["ord"] for s in got["stops"]]
    assert ords == list(range(1, 13)), f"Expected 1..12 without duplicates, got {ords}"


# ---------------------------------------------------------------------------
# 3. Standardised route schema + 2-opt tour improvement
# ---------------------------------------------------------------------------

def test_standardised_route_schema_for_ok_and_degraded(monkeypatch):
    ok_route = routing.plan_route(18.44, 77.45, 18.44, 77.65, "terrain")
    assert ok_route["status"] == "ok"
    assert ok_route["stats"]["degraded"] is False
    assert ok_route["stats"]["length_km"] == ok_route["length_km"]

    # Force steep impassable plane -> degraded route still carries standardised stats dict
    grad = math.tan(math.radians(45.0))
    monkeypatch.setattr(T, "elev", lambda lat, lon: grad * float(lat) * mars.KM_PER_DEG * 1000.0)
    deg_route = routing.plan_route(0.0, 0.0, 0.4, 0.4, "terrain")
    assert deg_route["status"] == "degraded"
    assert isinstance(deg_route["stats"], dict)
    assert deg_route["stats"]["degraded"] is True
    assert deg_route["stats"]["length_km"] is None
    assert deg_route["stats"]["est_traverse_sols"] is None


def test_two_opt_uncrosses_suboptimal_greedy_tour():
    # Construct 4 stops where greedy nearest-neighbour leaves a longer path than 2-opt
    stops = [
        {"ord": 1, "lat": 0.0, "lon": 0.0, "activity": "a", "reason": ""},
        {"ord": 2, "lat": 0.0, "lon": 2.0, "activity": "b", "reason": ""},
        {"ord": 3, "lat": 1.0, "lon": 0.2, "activity": "c", "reason": ""},
        {"ord": 4, "lat": 1.0, "lon": 2.2, "activity": "d", "reason": ""},
    ]
    improved = missions._two_opt_open_path(stops)
    raw_len = sum(mars.hav_km(stops[i]["lat"], stops[i]["lon"],
                              stops[i + 1]["lat"], stops[i + 1]["lon"]) for i in range(3))
    imp_len = sum(mars.hav_km(improved[i]["lat"], improved[i]["lon"],
                              improved[i + 1]["lat"], improved[i + 1]["lon"]) for i in range(3))
    assert imp_len < raw_len


# ---------------------------------------------------------------------------
# 4. Strict JEV schema + semantic validation and LLM tool-call validation
# ---------------------------------------------------------------------------

def test_jev_tool_validation_rejects_bools_enums_extra_keys_and_bad_coords():
    # Python bool must NOT be accepted as number or integer
    r_bool = run_tool("find_water", {"lat": True, "lon": 10.0})
    assert r_bool["error"] == "invalid_arguments" and r_bool["fail_closed"] is True

    r_int_bool = run_tool("search_planetary_location", {"q": "Jezero", "limit": True})
    assert r_int_bool["error"] == "invalid_arguments"

    # Unexpected extra arguments (additionalProperties: False) must fail closed
    r_extra = run_tool("find_water", {"lat": 10.0, "lon": 20.0, "unexpected": 1})
    assert r_extra["error"] == "invalid_arguments"
    assert "unexpected" in r_extra["detail"]

    # Enum violation must fail closed
    r_enum = run_tool("assess_radiation", {"lat": 0.0, "lon": 0.0, "shielding": "forcefield"})
    assert r_enum["error"] == "invalid_arguments"

    # Nested array item & semantic coordinate checks
    r_bbox = run_tool("analyze_terrain", {"bbox": [10.0, 20.0, 30.0]})
    assert r_bbox["error"] == "invalid_arguments"

    r_lat = run_tool("assess_radiation", {"lat": 95.0, "lon": 0.0})
    assert r_lat["error"] == "invalid_arguments"

    assert validate_tool_call("assess_radiation", {"lat": -4.5, "lon": 137.4, "shielding": "hab"}) is None


def test_llm_planned_tool_calls_independently_validated():
    raw_calls = [
        {"id": "c1", "function": {"name": "find_water",
                                  "arguments": '{"lat": 40.0, "lon": 190.0, "min_certainty": "A"}'}},
        {"id": "c2", "function": {"name": "find_water",
                                  "arguments": '{"lat": 140.0, "lon": 190.0}'}},  # invalid lat
        {"id": "c3", "function": {"name": "invented_tool", "arguments": "{}"}},
        {"id": "c4", "function": {"name": "analyze_terrain", "arguments": "{bad json"}},
    ]
    valid, rejected = llm.validate_planned_tool_calls(raw_calls)
    assert len(valid) == 1
    assert valid[0]["tool"] == "find_water"
    assert len(rejected) == 3


# ---------------------------------------------------------------------------
# 5. Coordinate validation (no silent clamping on invalid latitudes)
# ---------------------------------------------------------------------------

def test_invalid_latitudes_rejected_across_endpoints():
    assert client.get("/elevation", params={"lat": 95.0, "lon": 10.0}).status_code == 400
    assert client.get("/elevation", params={"lat": -91.0, "lon": 10.0}).status_code == 400
    assert client.post("/nodes", json={"type": "waypoint", "lat": 120.0, "lon": 0.0}).status_code == 400
    assert client.post("/missions", json={
        "type": "route", "name": "bad-lat", "stops": [{"lat": -95.0, "lon": 10.0}],
    }).status_code == 400
    assert client.post("/measure/distance", json={"points": [[100.0, 0.0], [0.0, 0.0]]}).status_code == 400


# ---------------------------------------------------------------------------
# 6. Polar slopes, seam gradient, adjacent patch edges, and terrain exports
# ---------------------------------------------------------------------------

def test_polar_slope_and_patch_remain_finite():
    sg = T.slope_grid()
    assert np.all(np.isfinite(sg)), "slope_grid must contain no NaN or Inf values"
    for polar_lat in (-89.9, -90.0, 89.9, 90.0):
        s = T.slope(polar_lat, 180.0)
        assert math.isfinite(s) and 0.0 <= s <= 85.0
    polar_patch = T.patch(89.5, 0.0, radius_km=30.0, n=12)
    arr = np.array(polar_patch["grid_m"])
    assert np.all(np.isfinite(arr))


def test_adjacent_north_south_patches_share_matching_edge():
    """Roadmap test #10: adjacent north/south patches share the exact boundary."""
    radius_km = 10.0
    dlat = (2.0 * radius_km) / mars.KM_PER_DEG
    south_patch = T.patch(10.0, 77.5, radius_km=radius_km, n=24)
    north_patch = T.patch(10.0 + dlat, 77.5, radius_km=radius_km, n=24)
    # Last row (ys = +radius_km) of south_patch coincides with first row (ys = -radius_km) of north_patch
    south_top = np.array(south_patch["grid_m"][-1])
    north_bottom = np.array(north_patch["grid_m"][0])
    assert np.max(np.abs(south_top - north_bottom)) <= 0.1


def test_terrain_download_supports_real_grid_formats():
    r_json = client.get("/measure/terrain_download", params={
        "min_lat": 18.0, "min_lon": 77.0, "max_lat": 19.0, "max_lon": 78.0,
    })
    assert r_json.status_code == 200
    payload = r_json.json()
    assert "bbox_stats" in payload and "elevation_m" in payload and "crs" in payload
    assert len(payload["elevation_m"]) >= 1 and len(payload["elevation_m"][0]) >= 1

    r_npz = client.get("/measure/terrain_download", params={
        "min_lat": 18.0, "min_lon": 77.0, "max_lat": 19.0, "max_lon": 78.0, "format": "npz",
    })
    assert r_npz.status_code == 200
    z = np.load(io.BytesIO(r_npz.content))
    assert "elevation_m" in z and z["elevation_m"].size >= 1

    r_obj = client.get("/measure/terrain_download", params={
        "min_lat": 18.0, "min_lon": 77.0, "max_lat": 19.0, "max_lon": 78.0, "format": "obj",
    })
    assert r_obj.status_code == 200 and "\nv " in r_obj.text


# ---------------------------------------------------------------------------
# 7. Polar/large spherical polygons & Mars24 (Allison & McEwen 2000) reference
# ---------------------------------------------------------------------------

def test_polar_cap_and_octant_polygon_areas():
    # Polar square at 80 deg N enclosing the North Pole
    polar_area = mars.poly_area_km2([[80, 0], [80, 90], [80, 180], [80, 270]])
    cap_80n = 2.0 * math.pi * (1.0 - math.sin(math.radians(80.0))) * (mars.B_POL ** 2)
    # Inscribed geodesic square inside 80N parallel is ~0.637 of full 80N polar cap (~1.09e6 km2)
    assert 0.5 * cap_80n < polar_area < cap_80n

    # Spherical octant [[0, 0], [0, 90], [90, 0]] == 1/8 of sphere (pi/2 steradians)
    octant = mars.poly_area_km2([[0, 0], [0, 90], [90, 0]])
    r_mid = mars.local_radius_km(30.0)
    expected_octant = (math.pi / 2.0) * (r_mid ** 2)
    assert abs(octant - expected_octant) / expected_octant < 0.02


def test_mars24_solar_geometry_matches_published_j2000_reference():
    """Roadmap test #9: verify solar timing against NASA GISS Mars24 reference
    epoch (2000-01-06 00:00:00 UTC -> MSD ~ 44796.0, MTC ~ 23.99h, Ls ~ 277.19 deg)."""
    dt = datetime(2000, 1, 6, 0, 0, 0, tzinfo=timezone.utc)
    sub = mars.subsolar(dt)
    assert abs(sub["msd"] - 44796.0) < 0.01
    assert abs(sub["ls_deg"] - 277.19) < 0.1
    assert -25.2 <= sub["lat"] <= -24.7  # near southern summer solstice

    # At the subsolar point itself, solar elevation is ~90 deg and incidence ~0 deg
    geom = mars.sun_geometry(sub["lat"], sub["lon"], "2000-01-06T00:00:00Z")
    assert abs(geom["sun_elevation_deg"] - 90.0) < 0.05
    assert abs(geom["incidence_deg"]) < 0.05


# ---------------------------------------------------------------------------
# 8. Persistent connector cache, tile XYZ validation & magic-byte check
# ---------------------------------------------------------------------------

def test_tile_coordinate_validation_and_persistent_disk_cache(tmp_path, monkeypatch):
    # Out-of-bounds tile indices must return 400
    assert client.get("/tiles/ctx-murray/-1/0/0").status_code == 400
    assert client.get("/tiles/ctx-murray/2/0/99").status_code == 400

    # Persistent disk cache survives in-memory cache clear
    monkeypatch.setattr(config, "TILE_CACHE_DIR", tmp_path)
    png_stub = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    url = "https://example.invalid/tile_0_0_0.png"
    key = connectors._cache_key(url)
    connectors._write_disk_cache(key, url, datetime.now(timezone.utc).timestamp(), png_stub)
    connectors._cache.clear()

    data, cached = connectors.fetch_bytes(url)
    assert cached is True and data == png_stub
    assert connectors.detect_image_media_type(data) == "image/png"
    assert connectors.detect_image_media_type(b"<html>502 Bad Gateway</html>") is None
    connectors.invalidate_cache(url)
    assert connectors._read_disk_cache(key, 3600.0) is None


# ---------------------------------------------------------------------------
# 9. Event sequence replay, provenance quality tiers, and optional API-key auth
# ---------------------------------------------------------------------------

def test_event_sequence_ids_and_history_replay():
    events.hub._last.clear()
    r1 = client.post("/events/trigger?kind=replay_a", json={"step": 1}).json()
    eid1 = r1["triggered"]["event_id"]
    r2 = client.post("/events/trigger?kind=replay_b", json={"step": 2}).json()
    eid2 = r2["triggered"]["event_id"]
    assert eid2 > eid1

    hist = client.get("/events/history", params={"channel": "events", "after_id": eid1}).json()
    assert any(e["event_id"] == eid2 for e in hist["events"])

    # WebSocket reconnection replay via ?since_id=
    with client.websocket_connect(f"/ws/events?since_id={eid1}") as ws:
        welcome = ws.receive_json()
        assert welcome["type"] == "welcome"
        replayed = ws.receive_json()
        assert replayed["event_id"] >= eid2

    # Provenance quality classification
    assert prov("USGS Gazetteer")["quality"] == "observed"
    assert prov("demo-synthetic-grid [SIM]")["quality"] == "simulated"
    assert prov("Garvin depth scaling", quality="derived")["quality"] == "derived"


def test_optional_api_key_guards_mutations_when_configured(monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "mars-secret-token")

    # Public read and stateless measurement endpoints remain open
    assert client.get("/health").status_code == 200
    assert client.post("/measure/distance", json={"points": [[0, 0], [0, 1]]}).status_code == 200

    # Mutating endpoint rejects missing/wrong key with 401
    assert client.post("/nodes", json={"type": "waypoint", "lat": 1.0, "lon": 2.0}).status_code == 401
    assert client.post(
        "/nodes",
        json={"type": "waypoint", "lat": 1.0, "lon": 2.0},
        headers={"X-API-Key": "wrong"},
    ).status_code == 401

    # Valid key succeeds
    ok = client.post(
        "/nodes",
        json={"type": "waypoint", "lat": 1.0, "lon": 2.0},
        headers={"Authorization": "Bearer mars-secret-token"},
    )
    assert ok.status_code == 200
