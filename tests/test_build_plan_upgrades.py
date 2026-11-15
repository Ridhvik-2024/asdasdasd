"""Tests for NAM v2 Complete Build Plan backend upgrades."""
from fastapi.testclient import TestClient

from app.main import app

C = TestClient(app)


def test_terrain_rasters_and_compact_grid():
    for mode in ("mars-relief", "mdim21", "ctx-murray", "mola-color", "mola-shaded",
                 "themis-day", "themis-night", "sim3292-geology",
                 "swim-probability", "depth-to-ice", "heightmap"):
        r = C.get(f"/terrain/raster/{mode}.png")
        assert r.status_code == 200, mode
        assert r.headers["content-type"] == "image/png"
        assert "[SIM]" in r.headers.get("x-nam-provenance", "")
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
        assert len(r.content) > 2000

    assert C.get("/terrain/raster/does-not-exist.png").status_code == 404

    g = C.get("/terrain/elevation_grid?step=4")
    assert g.status_code == 200
    body = g.json()
    assert body["rows"] == 90 and body["cols"] == 180
    assert body["max_m"] > 15000 and body["min_m"] < -4000
    assert "provenance" in body


def test_landmark_flyovers():
    r = C.get("/terrain/flyovers")
    assert r.status_code == 200
    body = r.json()
    ids = {f["id"] for f in body["flyovers"]}
    assert {"olympus-mons", "valles-marineris", "hellas", "gale", "jezero", "arsia-mons"} <= ids
    detail = C.get("/terrain/flyovers/valles-marineris")
    assert detail.status_code == 200
    assert len(detail.json()["flyover"]["keyframes"]) >= 3
    assert C.get("/terrain/flyovers/unknown-id").status_code == 404


def test_scientific_database_catalogs():
    ds = C.get("/datasets").json()
    assert ds["count"] >= 12
    assert C.get("/datasets?q=CTX").json()["count"] >= 1

    orb = C.get("/science/orbiters").json()
    assert orb["count"] >= 8
    assert any(o["id"] == "mro" for o in orb["orbiters"])

    inst = C.get("/science/instruments").json()
    assert inst["count"] >= 13
    assert any(i["id"] == "hirise" for i in inst["instruments"])

    st = C.get("/science/spectral_targets").json()
    assert st["count"] >= 16
    jezero_st = C.get("/science/spectral_targets?lat=18.44&lon=77.45&radius_km=200").json()
    assert jezero_st["count"] >= 2

    unavail = C.get("/science/unavailable_sources").json()
    assert unavail["count"] >= 7
    for u in unavail["unavailable_sources"]:
        assert u["access_path"].startswith("https://")

    cat = C.get("/science/catalog").json()
    assert cat["counts"]["orbiters"] >= 8
    assert cat["counts"]["instruments"] >= 13
    assert cat["counts"]["spectral_targets"] >= 16
    assert cat["counts"]["unavailable_sources"] >= 7


def test_path_radiation_and_storm_classification_and_delete():
    # Path radiation baseline
    pts = [{"lat": 18.44, "lon": 77.45}, {"lat": 19.0, "lon": 78.2}, {"lat": 19.5, "lon": 79.0}]
    r = C.post("/environment/radiation/path", json={"points": pts, "speed_km_sol": 10.0, "shielding": "suit"})
    assert r.status_code == 200
    body = r.json()
    assert body["sim"] is True
    assert body["total_length_km"] > 50
    assert body["total_msv"] > 0
    assert len(body["segments"]) == 2

    # With active X-class SEP storm
    st = C.post("/environment/storms/simulate", json={"kind": "sep", "scale_or_class": "X", "broadcast": False}).json()
    sid = st["scenario_id"]
    r_sep = C.post("/environment/radiation/path", json={
        "points": pts, "speed_km_sol": 10.0, "shielding": "suit", "storm_id": sid
    }).json()
    assert r_sep["sep_total_msv"] > 0
    assert r_sep["total_msv"] > body["total_msv"]

    # Delete storm scenario
    assert C.delete(f"/environment/storms/{sid}").status_code == 200
    assert C.get(f"/environment/storms/{sid}").status_code == 404

    # Classify storms
    cd = C.get("/environment/storms/classify?kind=dust&tau=5.0").json()
    assert "MY34" in cd["severity_class"]
    cs = C.get("/environment/storms/classify?kind=sep&peak_msv_sol=3.5").json()
    assert "X-class" in cs["severity_class"]

    # Validation
    assert C.post("/environment/radiation/path", json={"points": [{"lat": 0, "lon": 0}]}).status_code == 400


def test_mission_profile_share_and_plan_change_ws():
    with C.websocket_connect("/ws/events") as ws:
        welcome = ws.receive_json()
        assert welcome["type"] == "welcome"

        m = C.post("/missions", json={
            "type": "survey",
            "name": "Jezero Delta Traverse",
            "objective": "Sample phyllosilicates & carbonates",
            "stops": [
                {"lat": 18.44, "lon": 77.45, "activity": "sample", "reason": "delta front"},
                {"lat": 18.60, "lon": 77.65, "activity": "drill", "reason": "rim carbonate"},
            ],
        }).json()
        mid = m["id"]

        # Verify plan_change broadcast arrives on /ws/events
        evt = ws.receive_json()
        assert evt["type"] == "plan_change"
        assert evt["mission_id"] == mid

    # Mission profile + path radiation
    prof = C.get(f"/missions/{mid}/profile")
    assert prof.status_code == 200
    pb = prof.json()
    assert pb["mission_id"] == mid
    assert pb["profile"]["total_km"] > 5
    assert pb["radiation"]["total_msv"] > 0

    # Mission share link persists in share_links table
    sh = C.post(f"/missions/{mid}/share")
    assert sh.status_code == 200
    sid = sh.json()["share_id"]
    fetched = C.get(f"/share/{sid}")
    assert fetched.status_code == 200
    assert fetched.json()["mission_id"] == mid

    assert C.delete(f"/missions/{mid}").status_code == 200


def test_streetview_historical_compare_and_raw_connector():
    cmp_r = C.get("/sites/Perseverance/compare")
    assert cmp_r.status_code == 200
    cb = cmp_r.json()
    assert cb["rover"] == "Perseverance"
    assert cb["earlier"]["id"] != cb["later"]["id"]
    assert cb["delta"]["sol_delta"] is not None and cb["delta"]["sol_delta"] > 0

    raw = C.get("/panoramas/raw?rover=perseverance&limit=5")
    assert raw.status_code == 200
    rb = raw.json()
    assert rb["status"] in ("live", "degraded")
    assert "provenance" in rb
    if rb["status"] == "degraded":
        assert rb["official_access_path"].startswith("https://mars.nasa.gov/")
        assert len(rb["curated_panoramas"]) >= 1
