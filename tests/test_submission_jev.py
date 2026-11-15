"""Submission tests - Person C scope: JEV AI and tool orchestration.

Covers the five must-fix areas:

1. Geological comparison: each location reads its OWN analyze_terrain result
   (the old composer read one shared tool key for both locations).
2. Repeated tool executions: every invocation is preserved separately with a
   unique id and its own arguments, instead of results[tool] = res letting the
   second run overwrite the first.
3. Rover-name extraction works for Perseverance, Curiosity, Opportunity and
   Spirit in both word orders ("X's route" and "route of X").
4. _slim() structured truncation: oversized tool outputs stay valid JSON
   instead of being sliced-and-reconstructed into malformed JSON.
5. Partial failure: one failed tool preserves the error, never overwrites a
   successful result, does not block independent subsequent tools, and the
   final reply acknowledges the missing information.
"""
import json
import re

import pytest
from fastapi.testclient import TestClient

from app.jev import router as jev_router
from app.jev.tools import run_tool
from app.main import app
from app.routers import jev as jev_api

client = TestClient(app)

ALL_ROVERS = ["Perseverance", "Curiosity", "Opportunity", "Spirit"]
ROVER_MESSAGES = {
    "Perseverance": ["show me Perseverance's route", "route taken by Perseverance"],
    "Curiosity": ["show me Curiosity's route", "route of Curiosity"],
    "Opportunity": ["show me Opportunity's route", "route of Opportunity"],
    "Spirit": ["show me Spirit's route", "route followed by Spirit"],
}

_ELEV_RE = re.compile(r"mean elev (-?[\d.]+) m")


# ------------------------------------------------------------------ helpers

def _sse_events(text):
    return [json.loads(line[6:]) for line in text.splitlines()
            if line.startswith("data: ")]


def _done(text):
    return [e for e in _sse_events(text) if e["type"] == "done"][-1]


def _run_plan(message, map_context=None):
    """Plan a message and execute its steps through the shared executor."""
    plan, composer = jev_router.plan_for(message, map_context or {})
    invocations = []
    events = list(jev_api.execute_steps(plan.steps,
                                        {"map_context": map_context or {}},
                                        trace=invocations))
    return plan, composer, invocations, events, jev_api._build_view(invocations)


def _terrain_for(loc):
    bbox = [loc["lat"] - 0.5, loc["lon"] - 0.5, loc["lat"] + 0.5, loc["lon"] + 0.5]
    return run_tool("analyze_terrain", {"bbox": bbox})


# ------------------------------------------- 1. geological comparison fix

def test_compare_locations_report_their_own_terrain_stats():
    r = client.post("/jev/chat", json={"message": "compare Jezero and Gale crater"})
    assert r.status_code == 200
    reply = _done(r.text)["reply"]
    assert "Jezero" in reply and "Gale" in reply

    # the engine really produces different statistics for the two bboxes
    ta = _terrain_for(jev_router._loc("Jezero"))
    tb = _terrain_for(jev_router._loc("Gale"))
    assert "error" not in ta and "error" not in tb
    assert ta["mean_elev_m"] != tb["mean_elev_m"]

    # both numbers appear in the reply, in order, each matching its own location
    elevs = [float(x) for x in _ELEV_RE.findall(reply)]
    assert len(elevs) == 2, reply
    assert elevs[0] != elevs[1], "the two locations must not share one terrain result"
    assert abs(elevs[0] - ta["mean_elev_m"]) < 1.0, \
        "first number must be Jezero's own result, got %s vs %.1f" % (elevs[0], ta["mean_elev_m"])
    assert abs(elevs[1] - tb["mean_elev_m"]) < 1.0, \
        "second number must be Gale's own result, got %s vs %.1f" % (elevs[1], tb["mean_elev_m"])

    # the trace shows two separately identified invocations of the same tool
    results = [e for e in _sse_events(r.text)
               if e["type"] == "tool_result" and e["tool"] == "analyze_terrain"]
    assert len(results) == 2
    assert results[0]["id"] != results[1]["id"]


# ------------------------------------ 2. repeated tool executions preserved

def test_same_tool_executed_twice_retains_both_results():
    plan, composer, invocations, events, view = _run_plan("compare Jezero and Gale crater")
    assert len(invocations) == 2
    first, second = invocations
    assert first["id"] != second["id"]
    assert first["args"]["bbox"] != second["args"]["bbox"], "each invocation keeps its own arguments"
    assert "error" not in first["result"] and "error" not in second["result"]
    assert first["result"]["mean_elev_m"] != second["result"]["mean_elev_m"]

    # each invocation stays retrievable under its own id
    assert view[first["id"]] is first["result"]
    assert view[second["id"]] is second["result"]
    # composer-facing alias still works and points at the first invocation
    assert view["analyze_terrain"] is first["result"]

    # tool_start/tool_result events carry the invocation ids
    started = [e["id"] for e in events if e["type"] == "tool_start"]
    finished = [e["id"] for e in events if e["type"] == "tool_result"]
    assert started == [first["id"], second["id"]] == finished


def test_same_tool_executed_three_times_all_results_survive():
    steps = [
        {"tool": "analyze_terrain", "args": {"bbox": [10.0, 20.0, 11.0, 21.0]}},
        {"tool": "analyze_terrain", "args": {"bbox": [-40.0, 100.0, -39.0, 101.0]}},
        {"tool": "analyze_terrain", "args": {"bbox": [0.0, 300.0, 1.0, 301.0]}},
    ]
    invocations = []
    list(jev_api.execute_steps(steps, {"map_context": {}}, trace=invocations))
    assert len(invocations) == 3
    ids = [i["id"] for i in invocations]
    assert len(set(ids)) == 3, ids
    means = [i["result"]["mean_elev_m"] for i in invocations]
    assert len(set(means)) == 3, "all three results must survive and stay distinct"
    assert [i["id"] for i in invocations] == ["analyze_terrain#1", "analyze_terrain#2",
                                              "analyze_terrain#3"]


# --------------------------------------- 3. rover-name extraction for all 4

@pytest.mark.parametrize("rover", ALL_ROVERS)
def test_rover_name_extracted_for_all_four_rovers(rover):
    for msg in ROVER_MESSAGES[rover]:
        plan, composer = jev_router.plan_for(msg)
        assert any(s["tool"] == "activate_map_layer"
                   and s["args"].get("layer_id") == "rover-traverses" for s in plan.steps), msg
        reply = composer({})
        first_line = reply.splitlines()[0]
        assert first_line.startswith("%s traverse" % rover), \
            "%s -> %r (router must not substitute another rover)" % (msg, first_line)
        for other in ALL_ROVERS:
            if other != rover:
                assert not first_line.startswith("%s traverse" % other), msg


def test_route_of_curiosity_does_not_fall_back_to_perseverance():
    """Regression for the group(1)-assumption bug: route-before-rover phrasing."""
    r = client.post("/jev/chat", json={"message": "route of Curiosity"})
    reply = _done(r.text)["reply"]
    first_line = reply.splitlines()[0]
    assert first_line.startswith("Curiosity traverse"), reply[:120]


# ----------------------------- 4. oversized tool outputs -> valid JSON only

def test_slim_oversized_output_is_structurally_truncated_and_valid():
    oversized = {
        "mean_elev_m": 1234.5,
        "payload": ["x" * 900] * 40,                       # ~36 KB list
        "blob": '{"broken": "json,' + "y" * 8000,          # quotes/braces/commas inside
        "nested": {"deep": [{"more": "z" * 7000}]},
        "provenance": {"source": "s" * 6000},
    }
    out = jev_api._slim({"analyze_terrain#1": oversized})
    s = json.dumps(out)                    # must not raise
    reparsed = json.loads(s)               # must be valid, parseable JSON
    assert len(s) < jev_api._SLIM_CHAR_BUDGET + 1000, "output must be size-bounded"
    kept = reparsed["analyze_terrain#1"]
    assert kept["mean_elev_m"] == 1234.5, "small fields survive truncation"
    assert "truncated" in s, "truncation must be marked honestly"


def test_slim_small_values_pass_through_unchanged_and_never_crash():
    small = {"a": 1, "b": ["ok"], "c": {"nested": True}}
    assert jev_api._slim(small) == small
    junk = {"weird": object()}             # not JSON-serialisable
    out = jev_api._slim(junk)
    json.dumps(out)                        # still valid JSON, no exception
    # a nasty string that used to break slice-and-reconstruct truncation
    nasty = {"k": "x,y{z\"}" * 3000}
    json.loads(json.dumps(jev_api._slim(nasty)))


def test_oversized_result_through_executor_and_llm_trace(monkeypatch):
    def fake_run_tool(name, args, ctx=None):
        return {"tool": name, "rows": [{"v": "q" * 800} for _ in range(30)]}

    monkeypatch.setattr(jev_api, "run_tool", fake_run_tool)
    invocations = []
    list(jev_api.execute_steps(
        [{"tool": "analyze_terrain", "args": {}, "id": "analyze_terrain#1"}],
        {"map_context": {}}, trace=invocations))
    assert invocations[0]["ok"] is True
    trace = jev_api._llm_trace(invocations)
    s = json.dumps(trace)
    assert len(s) < 2 * jev_api._SLIM_CHAR_BUDGET
    entry = json.loads(s)[0]               # the model receives valid JSON
    assert entry["id"] == "analyze_terrain#1"
    assert entry["args"] == {} and entry["ok"] is True


# --------------------------------------- 5. one failed tool, one successful

def test_failed_tool_preserved_alongside_successful_tool():
    good = {"tool": "analyze_terrain", "args": {"bbox": [18.0, 77.0, 19.0, 78.0]}}
    bad_tool = {"tool": "no_such_tool", "args": {}}
    bad_args = {"tool": "analyze_terrain", "args": {"bbox": "not-a-bbox"}}

    # failure first, success second: independent tools still execute
    invocations = []
    list(jev_api.execute_steps([bad_tool, good], {"map_context": {}}, trace=invocations))
    assert invocations[0]["ok"] is False
    assert invocations[0]["result"]["error"] == "unknown_tool"
    assert invocations[1]["ok"] is True and "error" not in invocations[1]["result"]
    view = jev_api._build_view(invocations)
    assert "error" not in view["analyze_terrain"]

    # success first, failure second: the failure must NOT overwrite the success
    invocations2 = []
    list(jev_api.execute_steps([good, bad_args], {"map_context": {}}, trace=invocations2))
    assert invocations2[0]["ok"] is True
    assert invocations2[1]["ok"] is False
    assert invocations2[1]["result"]["error"] == "invalid_arguments"
    view2 = jev_api._build_view(invocations2)
    assert "error" not in view2["analyze_terrain"], "late failure overwrote a successful result"
    assert "error" in view2[invocations2[1]["id"]], "error must be preserved under its own id"

    # failure then success of the SAME tool: alias resolves to the success,
    # the error stays available under the failed invocation's id
    invocations3 = []
    list(jev_api.execute_steps([bad_args, good], {"map_context": {}}, trace=invocations3))
    view3 = jev_api._build_view(invocations3)
    assert "error" in view3[invocations3[0]["id"]]
    assert "error" not in view3[invocations3[1]["id"]]
    assert "error" not in view3["analyze_terrain"]


def test_tool_crash_does_not_kill_remaining_steps(monkeypatch):
    def boom(name, args, ctx=None):
        if name == "explode":
            raise RuntimeError("wheel fell off")
        return {"ok": True, "tool": name}

    monkeypatch.setattr(jev_api, "run_tool", boom)
    steps = [{"tool": "explode", "args": {}},
             {"tool": "analyze_terrain", "args": {}}]
    invocations = []
    list(jev_api.execute_steps(steps, {"map_context": {}}, trace=invocations))
    assert invocations[0]["ok"] is False
    assert invocations[0]["result"]["error"] == "tool_execution_failed"
    assert invocations[1]["ok"] is True, "an independent tool after a crash must still run"


def test_failure_note_acknowledges_missing_information():
    invocations = []
    list(jev_api.execute_steps(
        [{"tool": "no_such_tool", "args": {}},
         {"tool": "analyze_terrain", "args": {"bbox": [0.0, 0.0, 1.0, 1.0]}}],
        {"map_context": {}}, trace=invocations))
    note = jev_api._failure_note(invocations)
    assert note is not None
    assert "missing" in note.lower() and "no_such_tool#1" in note
    # no failures -> no note
    assert jev_api._failure_note([i for i in invocations if i["ok"]]) is None


def test_chat_with_failed_tool_acknowledges_gap_in_reply():
    r = client.post("/jev/chat", json={"message": "activate layer no-such-layer-xyz"})
    assert r.status_code == 200
    events = _sse_events(r.text)
    failed = [e for e in events if e["type"] == "tool_result" and e.get("ok") is False]
    assert failed and failed[0]["error"] == "unknown_layer"
    reply = _done(r.text)["reply"]
    low = reply.lower()
    assert "failed" in low or "missing" in low, "reply must acknowledge the missing information"
    assert "activate_map_layer#1" in reply, "the failed invocation must be named"
