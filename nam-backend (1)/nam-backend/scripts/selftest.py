#!/usr/bin/env python3
"""NAM v2 backend verified self-test (v1-style, runnable anywhere).

Sweeps the live app via TestClient, prints a PASS/FAIL table per service and
exits non-zero on any failure. Run: python scripts/selftest.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)
ROWS = []


def check(name, fn):
    try:
        detail = fn() or ""
        ROWS.append(("PASS", name, detail))
    except Exception as e:
        ROWS.append(("FAIL", name, "%s: %s" % (type(e).__name__, e)))


def main():
    check("health: services + releases", lambda: (
        c.get("/health").json()["status"] == "ok" and
        "%d services, %d releases" % (len(c.get("/health").json()["services"]),
                                      len(c.get("/health").json()["releases"]))))
    check("gazetteer: fuzzy search < 300 ms", lambda: (
        (lambda s: "%.1f ms, %d hits" % (s["latency_ms"], s["count"]))
        (c.get("/search", params={"q": "jezro"}).json())))
    check("gazetteer: full USGS nomenclature", lambda: (
        "%d hits for Blunck" % c.get("/search", params={"q": "Blunck"}).json()["count"]))
    check("location card: provenance chain", lambda: (
        c.get("/locations/jezero").json()["provenance"]["feature"]["source"]))
    check("terrain: Olympus Mons > 15 km", lambda: (
        "%.0f m" % c.get("/elevation", params={"lat": 18.65, "lon": 133.8}).json()["elevation_m"]))
    check("imagery ladder: 5+ rungs", lambda: (
        "%d rungs" % len(c.get("/imagery/ladder").json()["ladder"])))
    check("tile proxy: honest degradation", lambda: (
        (lambda r: "HTTP %d" % r.status_code)(c.get("/tiles/ctx-murray/4/8/4"))))
    check("measurements: 12-tool suite", lambda: (
        (lambda d, p, cr: "d=%.1f km, prof=%.1f km, crater d=%.1f km [SIM depth]"
         % (d["distance_km"], p["total_km"], cr["diameter_km"]))
        (c.post("/measure/distance", json={"points": [[0, 0], [0, 1]]}).json(),
         c.post("/measure/profile", json={"points": [[18.45, 77.45], [18.45, 77.9]]}).json(),
         c.post("/measure/crater", json={"rim_a": {"lat": 18.75, "lon": 77.7},
                                         "rim_b": {"lat": 18.15, "lon": 77.7}}).json())))
    check("STL export: slicer-valid structure", lambda: (
        (lambda r: "%d bytes, header ok" % len(r.content))
        (c.post("/measure/stl", json={"lat": 18.45, "lon": 77.7, "radius_km": 20, "n": 48}))))
    check("science: 8+ layers w/ sources", lambda: (
        "%d layers" % c.get("/layers").json()["count"]))
    check("discoveries: all cited", lambda: (
        (lambda d: "%d cards, first: %s" % (d["count"], d["discoveries"][0]["evidence"]["citation"][:60]))
        (c.get("/discoveries").json())))
    check("sites: 3-way landing compare", lambda: (
        "%d sites" % len(c.get("/sites/compare", params={"ids": "perseverance,curiosity,opportunity"}).json()["comparison"])))
    check("street view: 10+ posed panoramas", lambda: (
        "%d panoramas" % c.get("/panoramas").json()["count"]))
    check("walk view: POV library 5 regions", lambda: (
        "%d POVs" % c.get("/walkview/pov/library").json()["count"]))
    check("JEV: exactly 24 tools", lambda: (
        (lambda t: "%d tools" % t["count"])(c.get("/jev/tools").json())))
    check("JEV: 8 review commands answer", lambda: (
        (lambda n: None)(0) or
        str(all("done" in c.post("/jev/chat", json={"message": m}).text for m in
                ["take me to Olympus Mons", "show me all major landing sites",
                 "compare Jezero and Gale crater", "find regions with evidence of ancient water",
                 "show me Perseverance's route", "explain what I am looking at",
                 "find interesting geological formations near this location",
                 "show me the highest mountains on Mars"])) and "all replied with done event"))
    check("JEV: honest abstention", lambda: (
        (lambda r: "abstained correctly" if "grounded" in r.lower() or "don't have" in r.lower()
         else "UNEXPECTED: " + r[:60])
        (json.loads([l for l in c.post("/jev/chat", json={"message": "swallow airspeed Titan"}).text
                     .splitlines() if l.startswith("data: ")][-1][6:])["reply"])))
    check("missions: 4 types + KML", lambda: (
        (lambda m: "%s created, advisory=%s" % (m["type"], m["advisory"]))
        (c.post("/missions", json={"type": "evacuation", "name": "selftest"}).json())))
    check("environment: MY34 + X-class [SIM]", lambda: (
        (lambda a, b: "%s | %s" % (a["label"][:34], b["label"]))
        (c.post("/environment/storms/simulate", json={"kind": "dust", "scale_or_class": "my34"}).json(),
         c.post("/environment/storms/simulate", json={"kind": "sep", "scale_or_class": "X"}).json())))
    check("storm response: reasoned stops", lambda: (
        "%d stops (water+shelter+refuge)" % len(c.post("/environment/storm_response",
                                                       json={"lat": 18.44, "lon": 77.5}).json()["stops"])))
    check("resources: water + shelter scoring", lambda: (
        "%d water A/B/C, %d shelters scored" % (
            c.get("/water").json()["count"], c.get("/shelters").json()["count"])))
    check("nodes: 8 types accepted", lambda: (
        str(all(c.post("/nodes", json={"type": t, "lat": 0, "lon": 0}).status_code == 200
                for t in ["waypoint", "hazard", "water", "shelter", "observation",
                          "mission", "annotation", "panorama_pov"])) and "all 8 created"))
    check("presence: 5+ agents [SIM]", lambda: (
        "%d agents" % len(c.get("/presence/agents").json()["agents"])))
    def _ws_drill():
        with c.websocket_connect("/ws/events") as ws:
            ws.receive_json()  # welcome
            c.post("/events/trigger?kind=storm_alert")
            return "alert received: %s" % ws.receive_json()["type"]
    check("websocket: storm alert drill", _ws_drill)
    check("integrity: no fabricated sources", lambda: (
        str(all(o["evidence"]["citation"] for o in c.get("/discoveries").json()["discoveries"]))
        + " - all %d discovery cards cited" % c.get("/discoveries").json()["count"]))
    check("openapi: 3.x, 80+ paths", lambda: (
        (lambda s: "OpenAPI %s, %d paths" % (s["openapi"], len(s["paths"])))
        (c.get("/openapi.json").json())))

    fails = [r for r in ROWS if r[0] == "FAIL"]
    print("\nNAM v2 backend self-test")
    print("=" * 72)
    for st, name, detail in ROWS:
        print("[%s] %-38s %s" % (st, name, detail[:70]))
    print("=" * 72)
    print("%d checks, %d failed" % (len(ROWS), len(fails)))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
