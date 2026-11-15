"""Regression tests for deep feature-by-feature audit fixes.

Covers all 8 audit findings:
  1. Antimeridian-aware _in_bbox in app/resources.py (bbox queries on /water & /shelters).
  2. JEV explain_route handling degraded routes & None stats cleanly without TypeError.
  3. JEV plan_storm_response & environment.storm_response destination normalization
     (accepts [lat, lon] or {"lat": ..., "lon": ...} with validation).
  4. JEV find_water & find_shelter global search when lat/lon omitted + bbox support.
  5. JEV compare_geological_layers returning {"error": "unknown_layer", ...} on unknown IDs.
  6. Published MOLA volcano heights attached per volcano before sorting + widened Tharsis bbox.
  7. Shortest-path antimeridian longitude interpolation in app/presence.py.
  8. Coordinate validation (400 on out-of-range/NaN/Inf), atomic POST /bookmarks, and
     404 on DELETE /bookmarks/{bid} for nonexistent IDs across remaining routers.
"""
from concurrent.futures import ThreadPoolExecutor
import math

from fastapi.testclient import TestClient

from app import environment, mars, missions, presence, resources, routing, terrain
from app.jev import router as jev_router
from app.jev.tools import run_tool
from app.main import app

client = TestClient(app)
T = terrain.engine().ensure()


# ---------------------------------------------------------------------------
# 1. Antimeridian-aware _in_bbox & /water, /shelters bbox filtering
# ---------------------------------------------------------------------------

def test_resources_in_bbox_normal_antimeridian_and_full_globe():
    assert resources._in_bbox(45.0, 190.0, (35.0, 180.0, 50.0, 220.0)) is True
    assert resources._in_bbox(45.0, 338.0, (35.0, 180.0, 50.0, 220.0)) is False

    # Antimeridian-crossing bbox: [350, 360) U [0, 10]
    assert resources._in_bbox(10.0, 359.0, (0.0, 350.0, 20.0, 10.0)) is True
    assert resources._in_bbox(10.0, 5.0, (0.0, 350.0, 20.0, 10.0)) is True
    assert resources._in_bbox(10.0, 180.0, (0.0, 350.0, 20.0, 10.0)) is False
    # Negative west longitude equivalent (-10..+10)
    assert resources._in_bbox(10.0, 355.0, (0.0, -10.0, 20.0, 10.0)) is True
    assert resources._in_bbox(10.0, 5.0, (0.0, -10.0, 20.0, 10.0)) is True
    assert resources._in_bbox(10.0, 180.0, (0.0, -10.0, 20.0, 10.0)) is False

    # Full longitude span
    assert resources._in_bbox(45.0, 190.0, (-90.0, 0.0, 90.0, 360.0)) is True
    assert resources._in_bbox(45.0, 190.0, (-90.0, -180.0, 90.0, 180.0)) is True


def test_water_and_shelter_bbox_endpoints():
    # Arcadia (45, 190) and Erebus (45, 210) lie inside [35..50, 180..220]
    r = client.get("/water", params={
        "min_lat": 35.0, "min_lon": 180.0, "max_lat": 50.0, "max_lon": 220.0,
    })
    assert r.status_code == 200
    ids = {c["id"] for c in r.json()["candidates"]}
    assert ids == {"w-arcadia", "w-erebus"}

    # Antimeridian-crossing bbox covering Deuteronilus (38.5, 338) & Protonilus (42, 330)
    r_anti = client.get("/water", params={
        "min_lat": 30.0, "min_lon": 325.0, "max_lat": 50.0, "max_lon": 10.0,
    })
    assert r_anti.status_code == 200
    anti_ids = {c["id"] for c in r_anti.json()["candidates"]}
    assert {"w-deuteronilus", "w-protonilus"} <= anti_ids
    assert "w-arcadia" not in anti_ids

    # Shelter bbox query via Python and HTTP
    sh_py = resources.find_shelter(bbox=(-15.0, 235.0, 5.0, 290.0))
    sh_ids = {s["id"] for s in sh_py}
    assert {"sh-arsia-skylight", "sh-tractus-catena", "sh-hebes-alcove", "sh-candor-alcove"} <= sh_ids
    assert "sh-korolev" not in sh_ids

    r_sh = client.get("/shelters", params={
        "min_lat": -15.0, "min_lon": 235.0, "max_lat": 5.0, "max_lon": 290.0,
    })
    assert r_sh.status_code == 200
    assert {s["id"] for s in r_sh.json()["shelters"]} == sh_ids


# ---------------------------------------------------------------------------
# 2. JEV explain_route on degraded routes (no TypeError on None stats)
# ---------------------------------------------------------------------------

def test_jev_explain_route_handles_degraded_and_normal_routes(monkeypatch):
    # Normal route first
    m_ok = missions.create("route", "normal-explain", stops=[
        {"lat": 18.44, "lon": 77.45, "activity": "start", "reason": "base"},
        {"lat": 18.44, "lon": 77.65, "activity": "sample", "reason": "delta"},
    ])
    missions.route_for(m_ok["id"], 18.44, 77.45, 18.44, 77.65, "balanced")
    ok_res = run_tool("explain_route", {"mission_id": m_ok["id"]})
    assert "error" not in ok_res
    assert "km" in ok_res["explanation"] and "sols" in ok_res["explanation"]

    # Force impassable steep plane -> degraded route with None stats
    grad = math.tan(math.radians(45.0))
    monkeypatch.setattr(T, "elev", lambda lat, lon: grad * float(lat) * mars.KM_PER_DEG * 1000.0)
    m_deg = missions.create("route", "steep-explain", stops=[
        {"lat": 0.0, "lon": 0.0, "activity": "start", "reason": "cliff base"},
        {"lat": 0.4, "lon": 0.4, "activity": "summit", "reason": "cliff top"},
    ])
    deg_route = missions.route_for(m_deg["id"], 0.0, 0.0, 0.4, 0.4, "terrain")
    assert deg_route["status"] == "degraded"

    res = run_tool("explain_route", {"mission_id": m_deg["id"]})
    assert "error" not in res, res
    assert "degraded" in res["explanation"].lower()
    assert "[SIM]" in res["explanation"]

    # Optimized mission where all legs are degraded -> length_km is None
    missions.optimize(m_deg["id"], "terrain")
    res_opt = run_tool("explain_route", {"mission_id": m_deg["id"]})
    assert "error" not in res_opt, res_opt
    assert "degraded" in res_opt["explanation"].lower()


# ---------------------------------------------------------------------------
# 3. plan_storm_response & environment.storm_response destination normalization
# ---------------------------------------------------------------------------

def test_plan_storm_response_accepts_list_and_dict_destination():
    # Tool call with list [lat, lon] (matches JSON schema)
    res_list = run_tool("plan_storm_response", {
        "lat": 18.44, "lon": 77.5, "severity": "X", "destination": [45.0, 190.0],
    })
    assert "error" not in res_list, res_list
    assert res_list["destination"] == {"lat": 45.0, "lon": 190.0}
    assert res_list["stops"][-1]["kind"] == "refuge"
    assert res_list["stops"][-1]["lat"] == 45.0 and res_list["stops"][-1]["lon"] == 190.0

    # Tool call with dict {"lat": ..., "lon": ...}
    res_dict = run_tool("plan_storm_response", {
        "lat": 18.44, "lon": 77.5, "severity": "M", "destination": {"lat": 42.0, "lon": -30.0},
    })
    assert "error" not in res_dict, res_dict
    assert res_dict["destination"] == {"lat": 42.0, "lon": 330.0}

    # Direct Python call with list [lat, lon]
    py_res = environment.storm_response(18.44, 77.5, destination=[45.0, -170.0], severity="M")
    assert py_res["destination"] == {"lat": 45.0, "lon": 190.0}

    # HTTP endpoint accepts both [lat, lon] and {"lat": ..., "lon": ...}
    r1 = client.post("/environment/storm_response", json={
        "lat": 18.44, "lon": 77.5, "destination": [45.0, 190.0],
    })
    assert r1.status_code == 200 and r1.json()["destination"] == {"lat": 45.0, "lon": 190.0}

    r2 = client.post("/environment/storm_response", json={
        "lat": 18.44, "lon": 77.5, "destination": {"lat": 45.0, "lon": 190.0},
    })
    assert r2.status_code == 200 and r2.json()["destination"] == {"lat": 45.0, "lon": 190.0}

    # Invalid destination coordinates fail closed / return 400
    bad_tool = run_tool("plan_storm_response", {
        "lat": 18.44, "lon": 77.5, "destination": [999.0, 190.0],
    })
    assert bad_tool["error"] == "invalid_arguments" and bad_tool["fail_closed"] is True
    assert client.post("/environment/storm_response", json={
        "lat": 18.44, "lon": 77.5, "destination": [999.0, 190.0],
    }).status_code == 400
    assert client.post("/environment/storm_response", json={
        "lat": 18.44, "lon": 77.5, "destination": [45.0],
    }).status_code == 400


# ---------------------------------------------------------------------------
# 4. JEV find_water & find_shelter global search (no default 0,0) + bbox
# ---------------------------------------------------------------------------

def test_jev_find_water_and_shelter_global_and_bbox():
    # Without coordinates, must search globally (not 1500 km around 0,0)
    w_all = run_tool("find_water", {})
    assert "error" not in w_all
    assert len(w_all["candidates"]) >= 8
    ids = {c["id"] for c in w_all["candidates"]}
    assert {"w-arcadia", "w-deuteronilus", "w-utopia"} <= ids

    w_a = run_tool("find_water", {"min_certainty": "A"})
    assert len(w_a["candidates"]) >= 2
    assert all(c["certainty"] == "A" for c in w_a["candidates"])

    w_bbox = run_tool("find_water", {"bbox": [35.0, 180.0, 50.0, 220.0]})
    assert {c["id"] for c in w_bbox["candidates"]} == {"w-arcadia", "w-erebus"}

    sh_all = run_tool("find_shelter", {})
    assert "error" not in sh_all
    assert len(sh_all["shelters"]) == 12

    sh_bbox = run_tool("find_shelter", {"bbox": [-15.0, 235.0, 5.0, 290.0]})
    assert "sh-arsia-skylight" in {s["id"] for s in sh_bbox["shelters"]}
    assert "sh-korolev" not in {s["id"] for s in sh_bbox["shelters"]}


# ---------------------------------------------------------------------------
# 5. JEV compare_geological_layers flags unknown layer IDs
# ---------------------------------------------------------------------------

def test_jev_compare_geological_layers_rejects_unknown_layers():
    r1 = run_tool("compare_geological_layers", {
        "layer_a": "nonexistent-layer", "layer_b": "paleolakes",
    })
    assert r1["error"] == "unknown_layer"
    assert r1["missing_layers"] == ["nonexistent-layer"]

    r2 = run_tool("compare_geological_layers", {
        "layer_a": "paleolakes", "layer_b": "nope-layer",
    })
    assert r2["error"] == "unknown_layer"
    assert r2["missing_layers"] == ["nope-layer"]

    r_both = run_tool("compare_geological_layers", {
        "layer_a": "bad-a", "layer_b": "bad-b",
    })
    assert r_both["error"] == "unknown_layer"
    assert r_both["missing_layers"] == ["bad-a", "bad-b"]

    r_ok = run_tool("compare_geological_layers", {
        "layer_a": "sim3292-geology", "layer_b": "paleolakes",
    })
    assert "error" not in r_ok
    assert r_ok["layer_a"]["id"] == "sim3292-geology"
    assert r_ok["layer_b"]["id"] == "paleolakes"


# ---------------------------------------------------------------------------
# 6. Published volcano heights stay matched to volcano name + widened Tharsis bbox
# ---------------------------------------------------------------------------

def test_highest_mountains_published_heights_match_volcano_names(monkeypatch):
    plan, compose = jev_router.plan_for("show me the highest mountains on Mars")
    assert plan.steps[0]["tool"] == "analyze_terrain"
    assert plan.steps[0]["args"]["bbox"] == [-15.0, 220.0, 45.0, 265.0]

    reply = compose({})
    for name, pub_km in jev_router.PUBLISHED_MOUNTAIN_HEIGHTS_KM.items():
        matching = [ln for ln in reply.splitlines() if ln.startswith(f"- {name}:")]
        assert len(matching) == 1, f"Missing line for {name} in:\n{reply}"
        assert f"(published ~{pub_km:.1f} km)" in matching[0], (
            f"Wrong published height for {name}: {matching[0]}"
        )

    # Even if synthetic grid elevations are inverted, published heights stay bound to volcano name
    monkeypatch.setattr(T, "elev", lambda lat, lon: -float(lat) * 100.0)
    _, compose_inv = jev_router.plan_for("show me the highest mountains on Mars")
    reply_inv = compose_inv({})
    for name, pub_km in jev_router.PUBLISHED_MOUNTAIN_HEIGHTS_KM.items():
        matching = [ln for ln in reply_inv.splitlines() if ln.startswith(f"- {name}:")]
        assert len(matching) == 1
        assert f"(published ~{pub_km:.1f} km)" in matching[0]


# ---------------------------------------------------------------------------
# 7. Antimeridian longitude interpolation in presence._agent_position
# ---------------------------------------------------------------------------

def test_presence_antimeridian_longitude_interpolation():
    # Loop crossing 0/360 seam: (0, 359) <-> (0, 1) (2 deg = ~118.6 km each way)
    agent = {
        "id": "seam-rover",
        "name": "Seam-1",
        "kind": "rover",
        "lat": 0.0,
        "lon": 359.0,
        "loop": [[0.0, 359.0], [0.0, 1.0]],
        "speed_km_sol": mars.hav_km(0.0, 359.0, 0.0, 1.0),  # 1 sol per leg
    }
    # Midpoint of leg 0 (359 -> 1) should be at 0.0 deg, NOT 180.0 deg
    mid_fwd = presence._agent_position(agent, 0.5)
    assert mid_fwd["lon"] == 0.0
    # Quarter points stay near seam
    q1 = presence._agent_position(agent, 0.25)
    q3 = presence._agent_position(agent, 0.75)
    assert 359.0 <= q1["lon"] < 360.0
    assert 0.0 <= q3["lon"] <= 1.0

    # Midpoint of return leg (1 -> 359) should also be at 0.0 deg, NOT 180.0 deg
    mid_rev = presence._agent_position(agent, 1.5)
    assert mid_rev["lon"] == 0.0

    # Zero-length loop must not raise ZeroDivisionError
    stationary_loop = {
        "id": "dup", "lat": 10.0, "lon": 20.0,
        "loop": [[10.0, 20.0], [10.0, 20.0]], "speed_km_sol": 5.0,
    }
    pos = presence._agent_position(stationary_loop, 2.0)
    assert pos["lat"] == 10.0 and pos["lon"] == 20.0


# ---------------------------------------------------------------------------
# 8. Coordinate validation across remaining routers + atomic/404 bookmarks
# ---------------------------------------------------------------------------

def test_coordinate_validation_across_remaining_routers():
    # /environment/*
    assert client.get("/environment/radiation", params={"lat": 999, "lon": 0}).status_code == 400
    assert client.get("/environment/radiation", params={"lat": "nan", "lon": 0}).status_code == 400
    assert client.get("/environment/radiation", params={"lat": 0, "lon": "inf"}).status_code == 400
    assert client.get("/environment/radiation", params={"lat": 0, "lon": 0, "duration_sols": -1}).status_code == 400
    assert client.post("/environment/storms/simulate", json={"kind": "dust", "lat": 999, "lon": 0}).status_code == 400
    assert client.post("/environment/storm_response", json={"lat": -95, "lon": 0}).status_code == 400

    # /water, /shelters, /shelters/score
    assert client.get("/water", params={"lat": 999, "lon": 0}).status_code == 400
    assert client.get("/water", params={"lat": "nan", "lon": 0}).status_code == 400
    assert client.get("/water", params={"lat": 10}).status_code == 400
    assert client.get("/water", params={"min_lat": 999, "min_lon": 0, "max_lat": 10, "max_lon": 10}).status_code == 400
    assert client.get("/shelters", params={"lat": -91, "lon": 10}).status_code == 400
    assert client.get("/shelters", params={"min_lat": -95, "min_lon": 0, "max_lat": 10, "max_lon": 10}).status_code == 400
    assert client.get("/shelters/score", params={"lat": 120, "lon": 10}).status_code == 400

    # /panoramas/near & /imagery/linkage
    assert client.get("/panoramas/near", params={"lat": 999, "lon": 0}).status_code == 400
    assert client.get("/panoramas/near", params={"lat": 0, "lon": "nan"}).status_code == 400
    assert client.get("/imagery/linkage", params={"lat": -99, "lon": 0}).status_code == 400

    # /walkview/*
    assert client.post("/walkview/init", json={"lat": 999, "lon": 0}).status_code == 400
    assert client.get("/walkview/patch", params={"lat": 999, "lon": 0}).status_code == 400
    assert client.get("/walkview/patch", params={"lat": 0, "lon": 0, "radius_km": -5}).status_code == 400
    assert client.get("/walkview/pov", params={"lat": -95, "lon": 0}).status_code == 400
    assert client.get("/walkview/imagery", params={"lat": 999, "lon": 0}).status_code == 400
    assert client.get("/walkview/imagery", params={"lat": 0, "lon": 0, "heading_deg": "nan"}).status_code == 400

    # /discoveries & /layers/compare
    assert client.get("/discoveries", params={"lat": 999, "lon": 0}).status_code == 400
    assert client.get("/discoveries", params={"lat": "nan", "lon": 0}).status_code == 400
    assert client.get("/discoveries", params={"lat": 18.44}).status_code == 400
    assert client.post("/layers/compare", json={
        "layer_a": "sim3292-geology", "layer_b": "paleolakes", "bbox": [999, 0, 10, 10],
    }).status_code == 400

    # /bookmarks & /share & /presence/near
    assert client.post("/bookmarks", json={"name": "bad", "lat": 999, "lon": 0}).status_code == 400
    assert client.post("/share", json={"name": "bad", "camera": {"lat": 999, "lon": 0}}).status_code == 400
    assert client.get("/presence/near", params={"lat": 999, "lon": 0}).status_code == 400


def test_bookmarks_atomic_create_and_delete_404():
    def _create(i):
        resp = client.post("/bookmarks", json={
            "name": f"bm-atomic-{i}", "lat": 10.0 + i * 0.1, "lon": 50.0 + i * 0.1,
            "camera": {"height": 100 + i},
        })
        assert resp.status_code == 200
        return i, resp.json()

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(_create, range(12)))

    ids = set()
    for i, body in results:
        assert body["name"] == f"bm-atomic-{i}", f"Race condition returned wrong bookmark: {body}"
        ids.add(body["id"])
    assert len(ids) == 12

    # First delete returns 200; deleting again (or nonexistent id) returns 404
    bid = next(iter(ids))
    assert client.delete(f"/bookmarks/{bid}").status_code == 200
    assert client.delete(f"/bookmarks/{bid}").status_code == 404
    assert client.delete("/bookmarks/99999999").status_code == 404
