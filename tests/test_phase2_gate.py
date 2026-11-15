"""Phase 2 gate (v2.1 - Mars Street View and the Scientific Explorer)."""
from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)


def test_science_layers_registry_complete():
    layers = c.get("/layers").json()
    assert layers["count"] >= 8, "Phase 2 gate: 8+ science layers active"
    for l in layers["layers"]:
        assert l["source"] and l["title"] and l["category"]
    ids = {l["id"] for l in layers["layers"]}
    assert {"sim3292-geology", "swim-probability", "paleolakes", "valley-networks"} <= ids


def test_layer_compare():
    r = c.post("/layers/compare", json={"layer_a": "sim3292-geology",
                                        "layer_b": "paleolakes",
                                        "bbox": [17.9, 77.2, 19.0, 78.2]}).json()
    assert r["layer_a"]["title"] and r["layer_b"]["title"] and r["bbox_stats"]


def test_discovery_cards_carry_evidence():
    d = c.get("/discoveries").json()
    assert d["count"] >= 12
    for o in d["discoveries"]:
        ev = o["evidence"]
        assert ev["citation"], "every discovery card must show its evidence"
    by_id = c.get("/discoveries/jezero-delta-phyllosilicates").json()["discovery"]
    assert "Ehlmann" in by_id["evidence"]["citation"]


def test_landing_site_compare_three():
    r = c.get("/sites/compare", params={"ids": "perseverance,curiosity,opportunity"}).json()
    assert len(r["comparison"]) == 3
    for s in r["comparison"]:
        assert "elevation_m" in s and "local_terrain" in s


def test_panorama_catalog_poses_and_credits():
    p = c.get("/panoramas").json()
    assert p["count"] >= 10, "Phase 2 gate: at least 10 panoramas ingested"
    for x in p["panoramas"]:
        assert x["credit"] and x["source_url"] and x["pose_confidence"]


def test_traverse_navigation():
    trv = c.get("/traverses/Perseverance").json()
    assert len(trv["points"]) >= 3
    first = trv["points"][0]
    nb = c.get("/panoramas/%s/neighbors" % first["id"]).json()
    assert len(nb["adjacent"]) >= 1
    nxt = nb["adjacent"][0]
    assert nxt["id"] != first["id"] and "bearing_deg" in nxt


def test_orbital_to_ground_linkage():
    lk = c.get("/imagery/linkage", params={"lat": 18.44, "lon": 77.5}).json()
    assert lk["nearest_ground_photographs"], "one click from CTX view to ground photos"
    assert lk["footprint"]["deepest_layer"]


def test_historical_timeline():
    tl = c.get("/sites/Perseverance/timeline").json()
    assert len(tl["timeline"]) >= 3 and all("credit" in x for x in tl["timeline"])


def test_walkview_patch_and_pov():
    patch = c.get("/walkview/patch", params={"lat": 18.44, "lon": 77.6, "radius_km": 2, "n": 32}).json()
    assert patch["n"] == 32 and len(patch["indices"]) > 0 and patch["base_elev_m"] is not None
    init = c.post("/walkview/init", json={"lat": 18.44, "lon": 77.62, "eye_height_m": 1.7,
                                          "heading_deg": 250}).json()
    assert init["camera"]["eye_height_m"] == 1.7 and init["ground_elevation_m"] is not None
    pov = c.get("/walkview/pov", params={"lat": 18.44, "lon": 77.6}).json()
    assert pov["nearest_pov"]["name"] and pov["nearest_pov"]["distance_km"] <= 5
    lib = c.get("/walkview/pov/library").json()
    regions = {p["region"] for p in lib["povs"]}
    assert {"Jezero", "Gale", "Meridiani", "Gusev", "Elysium"} <= regions


def test_heading_matched_imagery():
    im = c.get("/walkview/imagery", params={"lat": 18.44, "lon": 77.62, "heading_deg": 250}).json()
    assert im["count"] >= 1
    first = im["imagery"][0]
    assert "heading_match_deg" in first or "bearing_deg" in first
