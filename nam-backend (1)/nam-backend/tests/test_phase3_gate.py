"""Phase 3 gate (v2.2 AI - the JEV intelligent explorer)."""
import json

from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)

REQUIRED_TOOLS = [
    "search_planetary_location", "get_current_map_context", "search_nasa_datasets",
    "get_location_observations", "activate_map_layer", "compare_geological_layers",
    "get_elevation_profile", "analyze_terrain", "identify_hazards",
    "find_scientific_targets", "create_mission", "generate_route", "optimize_route",
    "add_waypoint", "explain_route", "export_mission", "add_node", "add_stop",
    "plan_area", "plan_storm_response", "find_water", "find_shelter",
    "assess_radiation", "simulate_storm",
]

REVIEW_COMMANDS = [
    ("take me to Olympus Mons", ["Olympus Mons"]),
    ("show me all major landing sites", ["Viking 1", "Perseverance"]),
    ("compare Jezero and Gale crater", ["Jezero", "Gale"]),
    ("find regions with evidence of ancient water", ["water"]),
    ("show me Perseverance's route", ["Perseverance"]),
    ("explain what I am looking at", ["Center"]),
    ("find interesting geological formations near this location", ["delta"]),
    ("show me the highest mountains on Mars", ["Olympus Mons"]),
]


def _last_done(text):
    done = [l for l in text.splitlines() if l.startswith("data: ")][-1]
    return json.loads(done[6:])


def test_all_24_tools_registered_with_schemas():
    t = c.get("/jev/tools").json()
    assert t["count"] == 24
    names = {x["name"] for x in t["tools"]}
    assert set(REQUIRED_TOOLS) == names
    for x in t["tools"]:
        assert x["parameters"]["type"] == "object"


def test_fail_closed_on_bad_args():
    from app.jev.tools import run_tool
    res = run_tool("find_water", {"lat": "not-a-number", "lon": 0})
    assert res["error"] == "invalid_arguments" and res["fail_closed"]
    res2 = run_tool("nope", {})
    assert res2["error"] == "unknown_tool"


def test_review_commands_execute():
    for msg, needles in REVIEW_COMMANDS:
        r = c.post("/jev/chat", json={"message": msg, "map_context": {"center": {"lat": 18.44, "lon": 77.5}}})
        assert r.status_code == 200
        types = [json.loads(l[6:])["type"] for l in r.text.splitlines() if l.startswith("data: ")]
        assert "tool_start" in types, "chat must show tool-activity trace: %s" % msg
        done = _last_done(r.text)
        assert done["type"] == "done"
        for needle in needles:
            assert needle.lower() in done["reply"].lower(), "%s -> %s" % (msg, done["reply"][:120])


def test_fly_to_intent():
    r = c.post("/jev/chat", json={"message": "take me to Olympus Mons"})
    done = _last_done(r.text)
    assert any(i["action"] == "fly_to" and i["label"] == "Olympus Mons" for i in done["intents"])


def test_explain_view_cites_provenance():
    e = c.post("/jev/explain", json={"map_context": {"center": {"lat": 18.44, "lon": 77.5},
                                                     "layers_active": ["ctx-murray", "paleolakes"]}}).json()
    assert "Region:" in e["explanation"]
    assert "gazetteer" in e["explanation"].lower()
    assert e["provenance"]["source"]


def test_honest_abstention_on_unknown_topics():
    r = c.post("/jev/chat", json={"message": "airspeed velocity of an unladen swallow on Titan"})
    done = _last_done(r.text)
    assert "grounded" in done["reply"].lower() or "abstain" in done["reply"].lower() \
        or "don't have" in done["reply"].lower(), "JEV must abstain rather than invent"


def test_benchmark_and_adapter_status():
    b = c.get("/jev/benchmark").json()
    assert "adapter" in b and "fallback" in b["adapter"]
    assert b["adapter"]["fallback"]


def test_sse_stream_events_protocol():
    r = c.post("/jev/chat", json={"message": "find me water"})
    kinds = [json.loads(l[6:])["type"] for l in r.text.splitlines() if l.startswith("data: ")]
    assert kinds[0] == "start" and kinds[-1] == "done"
    assert "tool_start" in kinds and "tool_result" in kinds and "delta" in kinds
