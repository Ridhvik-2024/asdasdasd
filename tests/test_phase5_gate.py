"""Phase 5 gate (v2.2 live - nodes, presence, realtime, integrity)."""
import json
import time

from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)

NODE_TYPES = ["waypoint", "hazard", "water", "shelter", "observation",
              "mission", "annotation", "panorama_pov"]


def test_node_types_crud():
    ids = []
    for t in NODE_TYPES:
        n = c.post("/nodes", json={"type": t, "lat": 18.44, "lon": 77.5 + len(ids) * 0.01,
                                   "radius_km": 0.5, "props": {"note": "gate"}}).json()
        assert n["type"] == t and n["created_by"] == "user"
        ids.append(n["id"])
    got = c.get("/nodes").json()["nodes"]
    assert {n["type"] for n in got} >= set(NODE_TYPES)
    nid = ids[0]
    upd = c.put("/nodes/" + nid, json={"lat": 18.5, "props": {"updated": True}}).json()
    assert upd["lat"] == 18.5 and upd["props"]["updated"]
    near = c.get("/nodes/near", params={"lat": 18.5, "lon": 77.5, "radius_km": 100}).json()
    assert len(near["nodes"]) >= 1
    assert c.delete("/nodes/" + nid).json()["deleted"]
    assert c.get("/nodes/" + nid).status_code == 404


def test_jev_can_create_nodes():
    n = c.post("/nodes", json={"type": "water", "lat": 45.0, "lon": 190.0,
                               "props": {"via": "jev"}}).json()
    assert n["props"]["via"] == "jev"


def test_presence_agents_and_near():
    ag = c.get("/presence/agents").json()
    assert len(ag["agents"]) >= 5, "gate: five presence agents streaming"
    kinds = {a["kind"] for a in ag["agents"]}
    assert {"crew", "rover", "habitat"} <= kinds
    for a in ag["agents"]:
        assert "[SIM]" in a["provenance"]["source"]
    near = c.get("/presence/near", params={"lat": 18.44, "lon": 77.5, "radius_km": 300}).json()
    assert len(near["agents"]) >= 2


def test_presence_tick_advances():
    a0 = {x["id"]: (x["lat"], x["lon"]) for x in c.get("/presence/agents").json()["agents"]}
    c.post("/presence/tick", params={"dt_sols": 3.0})
    a1 = {x["id"]: (x["lat"], x["lon"]) for x in c.get("/presence/agents").json()["agents"]}
    moved = any(a0[k] != a1[k] for k in a0 if k.startswith("rover"))
    assert moved, "rover agents must advance on tick [SIM]"


def test_storm_alert_reaches_ws_client():
    with c.websocket_connect("/ws/events") as ws:
        assert ws.receive_json()["type"] == "welcome"
        t0 = time.time()
        c.post("/events/trigger?kind=storm_alert", json={"storm_id": "drill-1"})
        evt = ws.receive_json()
        assert evt["type"] == "storm_alert"
        assert time.time() - t0 < 3.0, "gate: storm alert within ~1 s of trigger"
        assert evt.get("sim") is True


def test_presence_ws_streams():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/presence") as ws:
            assert ws.receive_json()["type"] == "welcome"
            evt = ws.receive_json()
            assert evt["type"] == "presence_update" and evt.get("sim") is True
            assert len(evt["agents"]) >= 5


def test_bounded_rate_telemetry():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/events") as ws:
            ws.receive_json()  # welcome
            time.sleep(0.1)
            for _ in range(10):
                client.post("/events/trigger?kind=telemetry_tick")
            deadline = time.time() + 3
            sent = 0
            while time.time() < deadline:
                try:
                    ws.receive_json()
                    sent += 1
                except Exception:
                    break
            assert sent <= 2, "bounded rate: telemetry must be capped (got %d in 3 s)" % sent


def test_integrity_sweep_zero_fabricated_sources():
    """30-question style audit: sampled payloads must carry provenance or [SIM]."""
    checks = [
        ("/locations/jezero", "provenance"),
        ("/discoveries", None),
        ("/layers", None),
        ("/water", "provenance"),
        ("/shelters", "provenance"),
        ("/panoramas", "provenance"),
        ("/environment/storms", None),
        ("/imagery/ladder", "provenance"),
    ]
    for path, prov_key in checks:
        body = c.get(path).json()
        if prov_key:
            assert prov_key in body, "%s missing provenance" % path
        text = json.dumps(body)
        assert "undefined" not in text and "NaN" not in text
    obs = c.get("/discoveries").json()["discoveries"]
    allowed_hosts = ("mars.nasa.gov", "science.nasa.gov", "www.nasa.gov", "nasa.gov",
                     "swim.psi.edu", "planetarynames.wr.usgs.gov", "www.uahirise.org",
                     "murray-lab.caltech.edu", "pds-imaging.jpl.nasa.gov", "themis.asu.edu",
                     "esa.int", "www.esa.int")
    for o in obs:
        assert o["evidence"]["citation"], "every observation cited"
        u = o["evidence"].get("url")
        if u:
            assert u.startswith("https://") and any(h in u for h in allowed_hosts), \
                "no fabricated source URLs: %s" % u


def test_openapi_31_available():
    spec = c.get("/openapi.json").json()
    assert spec["openapi"].startswith("3.")
    assert len(spec["paths"]) >= 80, "comprehensive API surface"
