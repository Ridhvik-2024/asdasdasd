"""Person C submission tests — JEV AI correctness and tool orchestration."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from app.jev import llm, router as jev_router, tools as jev_tools
from app.main import app
from app.routers import jev as jev_endpoint

client = TestClient(app)


def _parse_sse(raw_text):
    return [
        json.loads(line[6:])
        for line in raw_text.splitlines()
        if line.startswith("data: ")
    ]


def _done_event(raw_text):
    events = _parse_sse(raw_text)
    assert events and events[-1]["type"] == "done"
    return events[-1]


# ---------------------------------------------------------------------------
# 1. Geological comparisons: distinct terrain statistics for both locations
# ---------------------------------------------------------------------------

def test_compare_two_locations_distinguishes_terrain_statistics():
    resp = client.post("/jev/chat", json={"message": "compare Jezero and Gale crater"})
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    done = events[-1]
    reply = done["reply"]

    # Both analyze_terrain calls must execute with distinct IDs and distinct bboxes
    starts = [e for e in events if e["type"] == "tool_start" and e["tool"] == "analyze_terrain"]
    assert len(starts) == 2
    assert starts[0]["id"] != starts[1]["id"]
    assert starts[0]["args"]["bbox"] != starts[1]["args"]["bbox"]

    # Compute ground-truth terrain stats directly from the tool for each bbox
    jezero_stats = jev_tools.run_tool("analyze_terrain", starts[0]["args"])
    gale_stats = jev_tools.run_tool("analyze_terrain", starts[1]["args"])
    assert round(jezero_stats["mean_elev_m"]) != round(gale_stats["mean_elev_m"])
    assert round(jezero_stats["mean_slope_deg"], 1) != round(gale_stats["mean_slope_deg"], 1)

    expected_jezero = "Jezero - mean elev %.0f m, mean slope %.1f deg" % (
        jezero_stats["mean_elev_m"], jezero_stats["mean_slope_deg"]
    )
    expected_gale = "Gale - mean elev %.0f m, mean slope %.1f deg" % (
        gale_stats["mean_elev_m"], gale_stats["mean_slope_deg"]
    )
    assert expected_jezero in reply
    assert expected_gale in reply


def test_compare_olympus_mons_and_hellas_extreme_elevation_contrast():
    resp = client.post("/jev/chat", json={"message": "compare Olympus Mons with Hellas"})
    assert resp.status_code == 200
    done = _done_event(resp.text)
    reply = done["reply"]

    m = re.search(
        r"Olympus Mons - mean elev (-?\d+) m, mean slope ([\d.]+) deg;\s*"
        r"Hellas - mean elev (-?\d+) m, mean slope ([\d.]+) deg",
        reply,
    )
    assert m is not None, f"Unexpected comparison format: {reply}"
    olympus_elev, olympus_slope = int(m.group(1)), float(m.group(2))
    hellas_elev, hellas_slope = int(m.group(3)), float(m.group(4))
    assert olympus_elev > 15000
    assert hellas_elev < -4000
    assert olympus_elev != hellas_elev
    assert olympus_slope != hellas_slope


# ---------------------------------------------------------------------------
# 2. Repeated tool executions: preserve every invocation with ID and args
# ---------------------------------------------------------------------------

def test_repeated_tool_executions_retained_separately_and_compatible():
    bboxes = [
        [17.9, 77.2, 18.9, 78.2],    # Jezero
        [-5.9, 137.3, -4.9, 138.3],  # Gale
        [18.15, 133.3, 19.15, 134.3],  # Olympus Mons
    ]
    steps = [{"tool": "analyze_terrain", "args": {"bbox": bb}} for bb in bboxes]
    results = jev_endpoint.execute_steps(steps)

    # All three invocations survive under distinct invocation IDs
    assert len(results) == 3
    ids = list(results.keys())
    assert len(set(ids)) == 3
    for idx, cid in enumerate(ids):
        inv = results[cid]
        assert inv["id"] == cid
        assert inv["tool"] == "analyze_terrain"
        assert inv["args"] == {"bbox": bboxes[idx]}
        assert inv["ok"] is True
        assert inv["error"] is None
        assert "mean_elev_m" in inv["result"]

    elevs = [results[cid]["result"]["mean_elev_m"] for cid in ids]
    assert len({round(e, 1) for e in elevs}) == 3, "Each bbox must retain its own distinct result"

    # Backward compatibility with single-tool composers expecting results.get(tool_name)
    compat = results.get("analyze_terrain")
    assert isinstance(compat, dict) and "mean_elev_m" in compat
    assert len(results.for_tool("analyze_terrain")) == 3


def test_repeated_tool_executions_in_chat_sse_and_llm_path(monkeypatch):
    captured_trace = {}

    def fake_plan(message, map_context, timeout_s=30.0):
        return {
            "steps": [
                {"tool": "analyze_terrain", "args": {"bbox": [17.9, 77.2, 18.9, 78.2]}},
                {"tool": "analyze_terrain", "args": {"bbox": [-5.9, 137.3, -4.9, 138.3]}},
            ],
            "intents": [],
            "text": "",
        }

    def fake_chat(message, map_context, tool_trace, timeout_s=60.0):
        captured_trace.update(tool_trace)
        return "Synthesized comparison from two distinct terrain invocations [SIM]."

    monkeypatch.setattr(llm, "plan_with_llm", fake_plan)
    monkeypatch.setattr(llm, "chat_with_llm", fake_chat)

    resp = client.post("/jev/chat", json={"message": "compare two patches"})
    assert resp.status_code == 200
    done = _done_event(resp.text)

    assert len(done["invocations"]) == 2
    assert done["invocations"][0]["id"] != done["invocations"][1]["id"]
    assert done["invocations"][0]["args"] != done["invocations"][1]["args"]
    assert len(captured_trace) == 2
    trace_vals = list(captured_trace.values())
    assert trace_vals[0]["args"]["bbox"] == [17.9, 77.2, 18.9, 78.2]
    assert trace_vals[1]["args"]["bbox"] == [-5.9, 137.3, -4.9, 138.3]
    assert trace_vals[0]["result"]["mean_elev_m"] != trace_vals[1]["result"]["mean_elev_m"]


# ---------------------------------------------------------------------------
# 3. Rover name extraction: all four rovers across both phrasing orders
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "rover,expected_landmark",
    [
        ("Perseverance", "Jezero"),
        ("Curiosity", "Gale"),
        ("Opportunity", "Victoria crater"),
        ("Spirit", "Husband Hill"),
    ],
)
@pytest.mark.parametrize(
    "template",
    [
        "show me %s's route",
        "show the route of %s",
        "what was the traverse for %s?",
    ],
)
def test_all_four_rover_names_extracted_consistently(rover, expected_landmark, template):
    query = template % rover
    assert jev_router.extract_rover_name(query) == rover

    resp = client.post("/jev/chat", json={"message": query})
    assert resp.status_code == 200
    done = _done_event(resp.text)
    reply = done["reply"]

    assert reply.startswith("%s traverse" % rover), f"Query {query!r} produced wrong rover reply: {reply}"
    assert expected_landmark.lower() in reply.lower()


# ---------------------------------------------------------------------------
# 4. _slim() structured JSON truncation: valid JSON on oversized tool outputs
# ---------------------------------------------------------------------------

def test_slim_preserves_valid_json_on_oversized_outputs():
    oversized = {
        "call_1": {
            "id": "call_1",
            "tool": "export_mission",
            "args": {"mission_id": "m-1"},
            "ok": True,
            # Huge single string with no commas, quotes, escapes and unicode — broke old slice logic
            "result": {
                "mission_id": "m-1",
                "format": "kml",
                "content": '<kml xmlns="http://www.opengis.net/kml/2.2">'
                           + ('<Placemark><name>Stop "Alpha" \\ Mars</name></Placemark>' * 400)
                           + "</kml>",
            },
            "error": None,
        },
        "call_2": {
            "id": "call_2",
            "tool": "get_elevation_profile",
            "args": {"points": [[0, 0], [10, 10]], "samples": 1500},
            "ok": True,
            # Huge nested list of dicts/numbers — broke old rsplit(",") + "}" logic
            "result": {
                "total_km": 592.4,
                "samples": [
                    {"idx": i, "lat": i * 0.01, "lon": i * 0.01, "elev_m": -1200.5 + i}
                    for i in range(1500)
                ],
                "provenance": {"source": "demo terrain [SIM]"},
            },
            "error": None,
        },
        "call_3": {
            "id": "call_3",
            "tool": "analyze_terrain",
            "args": {"bbox": [0, 0, 1, 1]},
            "ok": True,
            "result": {"mean_elev_m": -1500.0, "mean_slope_deg": 1.2},
            "error": None,
        },
    }

    slimmed = jev_endpoint._slim(oversized)
    serialized = json.dumps(slimmed, ensure_ascii=False)
    reparsed = json.loads(serialized)

    assert set(reparsed.keys()) == {"call_1", "call_2", "call_3"}
    for k in ("call_1", "call_2", "call_3"):
        entry_json = json.dumps(reparsed[k], ensure_ascii=False)
        assert len(entry_json) <= 4000
        assert json.loads(entry_json) == reparsed[k]

    # Small output must remain untouched; oversized entries must retain core metadata
    assert reparsed["call_3"]["result"]["mean_elev_m"] == -1500.0
    assert reparsed["call_1"]["tool"] == "export_mission"
    assert reparsed["call_1"]["_truncated"] is True
    assert reparsed["call_2"]["tool"] == "get_elevation_profile"
    assert reparsed["call_2"]["_truncated"] is True


def test_chat_handles_oversized_tool_output_with_llm(monkeypatch):
    received_payloads = []

    def fake_plan(message, map_context, timeout_s=30.0):
        return {
            "steps": [{"tool": "get_elevation_profile",
                       "args": {"points": [[0.0, 0.0], [20.0, 20.0]], "samples": 1200}}],
            "intents": [],
            "text": "",
        }

    def fake_chat(message, map_context, tool_trace, timeout_s=60.0):
        # Verify the trace passed into the LLM serializes cleanly as valid JSON
        dumped = json.dumps(tool_trace)
        received_payloads.append(json.loads(dumped))
        return "Elevation profile summarized cleanly [SIM]."

    monkeypatch.setattr(llm, "plan_with_llm", fake_plan)
    monkeypatch.setattr(llm, "chat_with_llm", fake_chat)

    resp = client.post("/jev/chat", json={"message": "profile from 0,0 to 20,20"})
    assert resp.status_code == 200
    done = _done_event(resp.text)
    assert "summarized cleanly" in done["reply"]
    assert len(received_payloads) == 1


# ---------------------------------------------------------------------------
# 5. Partial tool failure handling: preserve error, keep successes, continue,
#    and acknowledge missing information without misleading numbers
# ---------------------------------------------------------------------------

def test_partial_failure_does_not_overwrite_success_and_executes_subsequent_tools():
    real_run_tool = jev_tools.run_tool
    calls = []

    def flaky_run_tool(name, args, ctx=None):
        calls.append((name, args))
        if name == "find_scientific_targets":
            return {"error": "upstream_unavailable", "detail": "target index offline"}
        return real_run_tool(name, args, ctx)

    orig = jev_endpoint.run_tool
    jev_endpoint.run_tool = flaky_run_tool
    try:
        resp = client.post(
            "/jev/chat",
            json={
                "message": "find interesting geological formations near this location",
                "map_context": {"center": {"lat": 18.44, "lon": 77.5}},
            },
        )
    finally:
        jev_endpoint.run_tool = orig

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    done = events[-1]
    reply = done["reply"]

    # Both tools were attempted in order: first failed, second still executed and succeeded
    assert [c[0] for c in calls] == ["find_scientific_targets", "get_location_observations"]
    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert len(tool_results) == 2
    assert tool_results[0]["tool"] == "find_scientific_targets" and tool_results[0]["ok"] is False
    assert tool_results[1]["tool"] == "get_location_observations" and tool_results[1]["ok"] is True

    # Error is preserved in done metadata; successful observation output is present; missing info acknowledged
    assert len(done["errors"]) == 1
    assert done["errors"][0]["tool"] == "find_scientific_targets"
    assert "delta" in reply.lower()  # from successful get_location_observations near Jezero
    assert "missing" in reply.lower() or "failed" in reply.lower() or "unavailable" in reply.lower()
    assert "find_scientific_targets" in reply


def test_failed_second_invocation_of_same_tool_preserves_first_success(monkeypatch):
    real_run_tool = jev_tools.run_tool
    call_count = {"n": 0}

    def second_terrain_fails(name, args, ctx=None):
        if name == "analyze_terrain":
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("DEM tile read timeout")
        return real_run_tool(name, args, ctx)

    monkeypatch.setattr(jev_tools, "run_tool", second_terrain_fails)

    # 1) Check execute_steps directly: 1st analyze_terrain succeeds, 2nd fails, 3rd tool succeeds
    steps = [
        {"tool": "analyze_terrain", "args": {"bbox": [17.9, 77.2, 18.9, 78.2]}},
        {"tool": "analyze_terrain", "args": {"bbox": [-5.9, 137.3, -4.9, 138.3]}},
        {"tool": "find_water", "args": {"lat": 45.0, "lon": 190.0, "radius_km": 2000}},
    ]
    res = jev_endpoint.execute_steps(steps)
    assert res["call_1"]["ok"] is True
    assert res["call_2"]["ok"] is False
    assert "DEM tile read timeout" in res["call_2"]["error"]["detail"]
    assert res["call_3"]["ok"] is True
    assert len(res["call_3"]["result"]["candidates"]) >= 1
    # Compatible lookup must retain call_1's valid terrain stats, NOT overwrite with call_2's error
    assert "error" not in res.get("analyze_terrain")
    assert res.get("analyze_terrain")["mean_elev_m"] == res["call_1"]["result"]["mean_elev_m"]

    # 2) Check end-to-end /jev/chat comparison with partial failure on second location
    call_count["n"] = 0
    resp = client.post("/jev/chat", json={"message": "compare Jezero and Gale crater"})
    assert resp.status_code == 200
    done = _done_event(resp.text)
    reply = done["reply"]

    # Jezero stats are reported accurately; Gale is NOT fabricated as 0 m / 0.0 deg
    assert "Jezero - mean elev 177 m" in reply
    assert "Gale - mean elev 0 m" not in reply
    assert "missing" in reply.lower() and "incomplete" in reply.lower()
    assert len(done["errors"]) == 1
    assert done["errors"][0]["id"] == "call_2"
