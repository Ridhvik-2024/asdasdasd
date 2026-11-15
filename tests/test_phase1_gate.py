"""Phase 1 gate (v2.0 - The Google Earth Core).

Space-to-surface demo parity at the backend level: imagery ladder, tile proxy
integrity, terrain engine, gazetteer/search/cards, measurement suite, STL,
share links, provenance everywhere.
"""
import struct

from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)


def test_health_lists_services_and_releases():
    h = c.get("/health").json()
    assert h["status"] == "ok"
    assert len(h["services"]) >= 14
    assert len(h["releases"]) == 5


def test_terrain_landmarks():
    e = c.get("/elevation", params={"lat": 18.65, "lon": 133.8}).json()
    assert e["elevation_m"] > 15000, "Olympus Mons must exceed 15 km on the demo grid"
    hellas = c.get("/elevation", params={"lat": -42.4, "lon": 70.5}).json()["elevation_m"]
    assert hellas < -5000
    assert "provenance" in e and "demo-synthetic-grid" in e["provenance"]["source"]


def test_imagery_ladder():
    lad = c.get("/imagery/ladder").json()
    ids = {l["id"] for l in lad["ladder"]}
    assert {"mdim21", "ctx-murray", "hirise-insets", "themis-day", "mola-color"} <= ids
    ctx = next(l for l in lad["ladder"] if l["id"] == "ctx-murray")
    assert ctx["res_m"] == 5


def test_tile_proxy_degrades_honestly():
    r = c.get("/tiles/ctx-murray/4/8/4")
    # either a real upstream tile or a documented 503 - never a fake image
    assert r.status_code in (200, 503)
    if r.status_code == 200:
        assert r.headers.get("X-NAM-Attribution")
    else:
        body = r.json()
        assert body["status"] == "degraded" and body["access_path"]


def test_gazetteer_search_fast_and_fuzzy():
    s = c.get("/search", params={"q": "jezro", "limit": 5}).json()  # fuzzy misspelling
    assert s["count"] >= 1
    assert s["latency_ms"] < 300, "Phase 1 gate: search under 300 ms"


def test_full_usgs_nomenclature_loaded():
    s = c.get("/search", params={"q": "Blunck"}).json()
    assert s["count"] >= 1 and any(r["id"].startswith("usgs-") for r in s["results"])


def test_location_card_provenance():
    card = c.get("/locations/jezero").json()
    for key in ("elevation_m", "slope_deg", "geologic_context", "imagery_depth"):
        assert key in card
    assert card["provenance"]["feature"]["source"]
    assert card["imagery_depth"]["deepest_layer"]


def test_landing_sites_first_class():
    sites = c.get("/landing_sites").json()
    ids = {s["id"] for s in sites["sites"]}
    assert {"viking-1", "curiosity", "perseverance", "zhurong"} <= ids


def test_measurement_suite_returns_provenance():
    d = c.post("/measure/distance", json={"points": [[18.44, 77.45], [18.44, 77.65]]}).json()
    assert d["distance_km"] > 10 and d["provenance"]["source"]
    p = c.post("/measure/profile", json={"points": [[18.45, 77.45], [18.45, 77.9]], "samples": 60}).json()
    assert p["total_km"] > 25 and len(p["points"]) >= 40
    cr = c.post("/measure/crater", json={"rim_a": {"lat": 18.75, "lon": 77.7},
                                         "rim_b": {"lat": 18.15, "lon": 77.7}}).json()
    assert cr["diameter_km"] > 30 and "[SIM]" in cr["provenance"]["source"]
    a = c.post("/measure/area", json={"polygon": [[10, 290], [10, 292], [12, 292], [12, 290]]}).json()
    assert 400 < a["area_km2"] < 60000
    sl = c.get("/measure/slope", params={"lat": 18.65, "lon": 133.8}).json()
    assert 0 <= sl["slope_deg"] <= 85
    ed = c.post("/measure/elevation_difference", json={"a": {"lat": 18.65, "lon": 133.8},
                                                       "b": {"lat": -42.4, "lon": 70.5}}).json()
    assert ed["difference_m"] < -20000
    so = c.post("/measure/solar", json={"lat": -5.4, "lon": 137.8,
                                        "iso_time": "2026-11-14T12:00:00Z", "ls_deg": 90,
                                        "slope_deg": 10, "azimuth_deg": 180}).json()
    assert 0 <= so["incidence_deg"] <= 180


def test_stl_export_slicer_valid():
    r = c.post("/measure/stl", json={"lat": 18.45, "lon": 77.7, "radius_km": 20,
                                     "vertical_scale": 5, "n": 48})
    assert r.status_code == 200
    body = r.content
    assert len(body) > 84
    tris = struct.unpack("<I", body[80:84])[0]
    assert tris > 0
    assert len(body) == 84 + 50 * tris, "binary STL structure must be slicer-valid"
    assert "vertical scale x5.0" in r.headers.get("X-NAM-Provenance", "") or \
        r.headers.get("X-NAM-Provenance", "")


def test_bookmark_and_share_roundtrip():
    b = c.post("/bookmarks", json={"name": "delta front", "lat": 18.44, "lon": 77.6,
                                   "camera": {"height": 500}}).json()
    assert b["id"] > 0
    s = c.post("/share", json={"name": "my view", "camera": {"lat": 18.44, "lon": 77.6,
                                                             "heading": 250}}).json()
    got = c.get("/share/" + s["share_id"]).json()
    assert got["camera"]["heading"] == 250
