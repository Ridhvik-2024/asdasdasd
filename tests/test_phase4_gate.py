"""Phase 4 gate (v2.2 operations - missions and environment)."""
from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)


def _mk_mission(mtype, stops):
    m = c.post("/missions", json={"type": mtype, "name": "gate-%s" % mtype,
                                  "objective": "gate test", "stops": stops}).json()
    return m["id"]


def test_mission_roundtrip_all_four_types():
    for mtype in ("route", "area", "evacuation", "survey"):
        mid = _mk_mission(mtype, [{"lat": 18.44, "lon": 77.45, "activity": "ingest",
                                   "reason": "landing floor"}])
        m = c.get("/missions/" + mid).json()
        assert m["type"] == mtype and m["advisory"] is True and "[SIM]" in m["advisory_label"]


def test_route_with_stats_and_presets():
    mid = _mk_mission("route", [])
    c.post("/missions/%s/stops" % mid, json={"lat": 18.44, "lon": 77.45, "activity": "a", "reason": "r1"})
    c.post("/missions/%s/stops" % mid, json={"lat": 18.44, "lon": 77.6, "activity": "b", "reason": "r2"})
    r = c.post("/missions/%s/route" % mid, json={"from_lat": 18.44, "from_lon": 77.45,
                                                 "to_lat": 18.44, "to_lon": 77.65,
                                                 "preset": "balanced"}).json()
    assert r["stats"]["length_km"] > 8 and "[SIM]" in r["provenance"]["source"]
    for preset in ("terrain", "speed"):
        r2 = c.post("/measure/route_distance", json={"from_lat": 18.44, "from_lon": 77.45,
                                                     "to_lat": 18.44, "to_lon": 77.65,
                                                     "preset": preset}).json()
        assert r2["cost_preset"] == preset and "[SIM]" in r2["provenance"]["source"]


def test_optimize_reorders_stops():
    mid = _mk_mission("survey", [])
    c.post("/missions/%s/stops" % mid, json={"lat": 18.44, "lon": 77.45, "activity": "y", "reason": "near"})
    c.post("/missions/%s/stops" % mid, json={"lat": 18.6, "lon": 77.9, "activity": "x", "reason": "far"})
    c.post("/missions/%s/stops" % mid, json={"lat": 18.47, "lon": 77.6, "activity": "z", "reason": "mid"})
    opt = c.post("/missions/%s/optimize" % mid, json={"preset": "balanced"}).json()
    assert len(opt["stops"]) == 3
    assert [round(s["lon"], 1) for s in opt["stops"]] == [77.5, 77.6, 77.9], \
        "nearest-neighbor should visit near -> mid -> far"


def test_kml_export():
    mid = _mk_mission("route", [{"lat": 18.44, "lon": 77.45}, {"lat": 18.44, "lon": 77.6}])
    r = c.get("/missions/%s/kml" % mid)
    assert r.status_code == 200
    body = r.text
    assert "LineString" in body and "kml" in r.headers.get("content-type", "")
    assert "Placemark" in body and "[SIM]" in body


def test_mission_compare_and_notes():
    a = _mk_mission("route", [])
    b = _mk_mission("route", [])
    cm = c.get("/missions/%s/compare" % a, params={"other_id": b}).json()
    assert "a" in cm and "b" in cm
    n = c.put("/missions/%s/notes" % a, json={"note": "backup route"}).json()
    assert n["notes"] == "backup route"


def test_storm_sims_labelled_sim():
    dust = c.post("/environment/storms/simulate", json={"kind": "dust", "scale_or_class": "my34"}).json()
    assert "[SIM]" in dust["label"] and dust["tau_peak"] >= 4.0
    assert dust["severity_class"] == "MY34-class"
    sep = c.post("/environment/storms/simulate", json={"kind": "sep", "scale_or_class": "X"}).json()
    assert "[SIM]" in sep["label"] and sep["severity"] == "X"
    m = c.post("/environment/storms/simulate", json={"kind": "sep", "scale_or_class": "M"}).json()
    assert m["severity"] == "M"


def test_documented_storm_catalog():
    cat = c.get("/environment/storms").json()["catalog"]
    ids = {x["id"] for x in cat}
    assert {"my34-2018-pede", "my25-2001-pede", "sep-2017-09-10"} <= ids


def test_radiation_advisory():
    r = c.get("/environment/radiation", params={"lat": -4.6, "lon": 137.4,
                                                "duration_sols": 2, "shielding": "suit"}).json()
    assert r["sim"] is True and r["advisory"].startswith("Simulation")
    assert 0.05 < r["gcr_dose_equiv_msv_per_sol"] < 1.0
    hab = c.get("/environment/radiation", params={"lat": -4.6, "lon": 137.4,
                                                  "duration_sols": 2, "shielding": "hab"}).json()
    assert hab["gcr_total_msv"] < r["gcr_total_msv"], "hab shielding must reduce dose"


def test_storm_response_plan():
    p = c.post("/environment/storm_response", json={"lat": 18.44, "lon": 77.5,
                                                    "severity": "X"}).json()
    kinds = [s["kind"] for s in p["stops"]]
    assert "water_cache" in kinds and "shelter_pickup" in kinds
    assert len(p["stops"]) >= 2 and p["radiation_estimate"]["sim"] is True
    assert p["provenance"]["sim"] is True


def test_water_and_shelters():
    w = c.get("/water", params={"lat": 45, "lon": 190, "radius_km": 3000}).json()
    top = w["candidates"][0]
    assert top["certainty"] in ("A", "B", "C")
    assert top["depth_to_ice_category"] and "stable" in top["stability"]
    s = c.get("/shelters", params={"lat": 45, "lon": 190, "radius_km": 6000}).json()
    assert s["count"] >= 5
    comp = [x["composite_index"] for x in s["shelters"]]
    assert comp == sorted(comp, reverse=True), "shelters sorted by composite index"
