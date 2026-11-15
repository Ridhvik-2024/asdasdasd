"""JEV endpoints: tool registry, SSE chat with tool-activity trace,
explain-view, benchmark."""
import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import db
from ..jev import llm, resource_route, router as jev_router
from ..jev.tools import TOOLS, run_tool

router = APIRouter(prefix="/jev", tags=["jev"])


@router.get("/tools")
def tools_list():
    return {"count": len(TOOLS), "tools": TOOLS,
            "note": "JSON-schema-constrained tools, including the resource-aware route planner"}


class RoutePlanIn(BaseModel):
    message: str = ""
    places: list = []
    resource_preference: str = "both"
    max_detour_km: float = 250.0
    speed_km_sol: float = 0.12
    preset: str = "balanced"
    use_model: bool = True


@router.post("/route-plan")
def resource_route_plan(request: RoutePlanIn):
    """Plan an advisory [SIM] route; the local model only extracts place names."""
    try:
        return resource_route.plan(places=request.places, message=request.message,
                                   preference=request.resource_preference,
                                   max_detour_km=request.max_detour_km,
                                   speed_km_sol=request.speed_km_sol,
                                   preset=request.preset, use_model=request.use_model)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


class ChatIn(BaseModel):
    message: str
    map_context: dict = {}


def _sse(obj):
    return "data: %s\n\n" % json.dumps(obj, ensure_ascii=False)


@router.post("/chat")
async def chat(c: ChatIn):
    """SSE stream: plan -> tool activity trace -> streamed answer -> done.

    With a local LLM configured the model plans and writes; otherwise the
    deterministic intent router plans and the composer writes. Both paths
    emit the same event protocol."""
    db.ex("INSERT INTO chat_logs (role,content) VALUES (?,?)", ("user", c.message))
    plan = None
    composer = None
    llm_planned = False

    async def make_gen():
        nonlocal plan, composer, llm_planned
        yield _sse({"type": "start", "engine": llm.describe()})
        planned = None if jev_router.is_resource_route_request(c.message) else await asyncio.to_thread(llm.plan_with_llm, c.message, c.map_context)
        invocations = []
        if planned and planned.get("steps"):
            llm_planned = True
            # A model tool call cannot introduce route names, coordinates or
            # assumptions of its own. Re-extract only from the user's text.
            steps = [({**step, "args": {"message": c.message,
                                      "preference": jev_router._route_preference(c.message)}}
                      if step.get("tool") == "plan_resource_route" else step)
                     for step in planned["steps"]]
        else:
            plan, composer = jev_router.plan_for(c.message, c.map_context)
            steps = plan.steps
        # Execute the plan. Every invocation is preserved separately (its own
        # id + its own arguments) instead of results[tool] = res, which let a
        # repeated execution overwrite the first result. A failing step records
        # its error and never blocks independent subsequent tools.
        iterator = iter(execute_steps(steps, {"map_context": c.map_context}, trace=invocations))
        sentinel = object()
        while True:
            ev = await asyncio.to_thread(next, iterator, sentinel)
            if ev is sentinel:
                break
            yield _sse(ev)
        view = _build_view(invocations)
        failure_note = _failure_note(invocations)
        if llm_planned:
            answer = await asyncio.to_thread(llm.chat_with_llm, c.message, c.map_context, _llm_trace(invocations)) or \
                "The local model could not produce an answer; tool outputs above are grounded and complete."
            citations = ["tool invocations: " + ", ".join(inv["id"] for inv in invocations)]
            intents = planned.get("intents", [])
        else:
            answer = composer(view) or ""
            citations = [s for s in _citations_from(invocations)]
            intents = plan.intents
        route_invocation = next((inv for inv in invocations if inv["tool"] == "plan_resource_route" and inv["ok"]), None)
        route_engine = None
        if route_invocation:
            route = route_invocation["result"]
            # Never allow generated prose to invent route metrics or omit warnings.
            answer = jev_router.summarize_resource_route(route)
            route_engine = route.get("engine")
            citations = ["NAM synthetic DEM and A* [SIM]", "SWIM-consistent water candidates [SIM]", "NAM shelter and radiation models [SIM]"]
            if route.get("status") == "ok" and len(route.get("path", [])) >= 2:
                intents = list(intents) + [{"action": "show_route", "path": route["path"], "stops": route["stops"]}]
        if failure_note:
            # partial failure: the answer must honestly acknowledge missing information
            answer = "%s\n%s" % (answer, failure_note)
        # stream the answer in small chunks (token-stream shim; real LLM streams natively)
        chunks = [answer[i:i + 90] for i in range(0, len(answer), 90)]
        for chn in chunks:
            yield _sse({"type": "delta", "text": chn})
            await asyncio.sleep(0.01)
        db.ex("INSERT INTO chat_logs (role,content) VALUES (?,?)", ("jev", answer))
        yield _sse({
            "type": "done",
            "reply": answer,
            "citations": citations,
            "intents": intents,
            "engine": route_engine or ("local-llm" if llm_planned else "deterministic-router"),
            "invocations": [
                {"id": inv["id"], "tool": inv["tool"], "args": inv["args"],
                 "ok": inv["ok"],
                 "error": None if inv["ok"] else inv["result"]}
                for inv in invocations
            ],
            "errors": [
                {"id": inv["id"], "tool": inv["tool"], "args": inv["args"],
                 "error": inv["result"]}
                for inv in invocations if not inv["ok"]
            ],
        })

    return StreamingResponse(make_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class ExplainIn(BaseModel):
    map_context: dict = {}


@router.post("/explain")
def explain(e: ExplainIn):
    return jev_router.explain_view({"map_context": e.map_context})


@router.get("/benchmark")
def benchmark():
    return llm.benchmark()


@router.get("/examples")
def review_examples():
    return {
        "commands": [
            "Fly to Jezero crater and tell me what Perseverance found there.",
            "Show me the best water-ice candidates in Arcadia Planitia.",
            "Compare Jezero crater, Gale crater, and Meridiani Planum as landing sites.",
            "Plan an evacuation route from Jezero during an X-class solar particle event.",
            "What are the tallest volcanoes on Mars?",
            "Find the highest-scoring radiation shelters near Tharsis.",
            "Measure the distance from Viking 1 to Perseverance.",
            "Explain what is known about recurring slope lineae on Mars.",
        ]
    }


@router.get("/logs")
def logs(limit: int = 20):
    rows = db.q("SELECT ts,role,content FROM chat_logs ORDER BY id DESC LIMIT ?", (min(limit, 100),))
    return {"logs": rows}


# ------------------------------------------------------------ execution core

_SLIM_CHAR_BUDGET = 4000
_TRUNCATION_MARK = "...[truncated to keep valid JSON]"


def _json_size(value):
    """Serialised length of *value*, or None when it is not JSON-serialisable."""
    try:
        return len(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError):
        return None


def _slim_value(value, budget=_SLIM_CHAR_BUDGET):
    """Structured truncation of any JSON-serialisable value.

    The old implementation sliced the serialised JSON text and tried to
    re-balance the remainder, which can cut inside a string or escape and
    produce malformed JSON (or crash on json.loads). Instead the structure is
    trimmed: dicts key by key, lists item by item, and only whole strings are
    cut - a cut string is still valid JSON. Truncation is marked so consumers
    know data was reduced. The result always serialises and reparses cleanly."""
    try:
        budget = max(int(budget), 64)
    except (TypeError, ValueError):
        budget = _SLIM_CHAR_BUDGET
    size = _json_size(value)
    if size is None:
        return _TRUNCATION_MARK
    if size <= budget:
        return value
    if isinstance(value, dict):
        out, left, kept = {}, budget - 2, 0
        for k, v in value.items():
            key = k if isinstance(k, str) else str(k)
            piece = _slim_value(v, max(64, left - len(json.dumps(key, ensure_ascii=False)) - 2))
            need = _json_size({key: piece})
            if kept > 0 and (need or 0) - 2 > left:
                out["_truncated"] = "%d of %d keys omitted" % (len(value) - kept, len(value))
                return out
            out[key] = piece
            left -= need
            kept += 1
        return out
    if isinstance(value, (list, tuple)):
        out, left = [], budget - 2
        for item in value:
            piece = _slim_value(item, max(64, left))
            need = _json_size(piece)
            if need is None or need > left:
                out.append(_TRUNCATION_MARK)
                return out
            out.append(piece)
            left -= need + 1
        return out
    if isinstance(value, str):
        keep = max(0, budget - len(_TRUNCATION_MARK) - 2)
        return value[:keep] + _TRUNCATION_MARK
    if isinstance(value, bytes):
        return _TRUNCATION_MARK
    return value        # numbers / bools / None are always kept whole


def _slim(results, max_chars=_SLIM_CHAR_BUDGET):
    """Truncate a {key: result} mapping to a bounded, always-valid-JSON view."""
    return {k: _slim_value(v, max_chars) for k, v in (results or {}).items()}


def _next_invocation_id(step, counters, taken):
    """Unique id per invocation: the plan-provided id or <tool>#<n> by
    execution order per tool; never two invocations under one id."""
    tool = step["tool"]
    counters[tool] = counters.get(tool, 0) + 1
    inv_id = step.get("id") or ("%s#%d" % (tool, counters[tool]))
    candidate, suffix = inv_id, 1
    while candidate in taken:          # safety net against colliding plan ids
        suffix += 1
        candidate = "%s#%d" % (inv_id, suffix)
    taken.add(candidate)
    return candidate


def execute_steps(steps, ctx, trace=None):
    """Execute tool-call steps in order, preserving every invocation separately.

    Yields SSE-ready event dicts (tool_start before each run, tool_result
    after). Each executed step is appended to *trace* as
    {"id", "tool", "args", "result", "ok"}, so running the same tool twice
    keeps two records with their own ids and arguments instead of the second
    overwriting the first. A failed step preserves its error, never overwrites
    a successful result, and never blocks independent subsequent tools."""
    counters, taken = {}, set()
    for step in steps:
        step = step or {}
        tool = step.get("tool")
        if not tool:
            continue
        raw_args = step.get("args")
        bad_args = raw_args is not None and not isinstance(raw_args, dict)
        args = raw_args if isinstance(raw_args, dict) else {}
        inv_id = _next_invocation_id(step, counters, taken)
        yield {"type": "tool_start", "id": inv_id, "tool": tool, "args": args}
        if bad_args:
            res = {"error": "invalid_arguments",
                   "detail": "tool arguments must be an object",
                   "fail_closed": True}
        else:
            try:
                res = run_tool(tool, args, ctx or {})
            except Exception as e:      # hard guarantee: one crash never kills the run
                res = {"error": "tool_execution_failed",
                       "detail": "%s: %s" % (type(e).__name__, e)}
        ok = not _is_error(res)
        yield {"type": "tool_result", "id": inv_id, "tool": tool, "ok": ok,
               "error": None if ok else res.get("error"),
               "keys": [k for k in res.keys()][:6] if isinstance(res, dict) else []}
        if trace is not None:
            trace.append({"id": inv_id, "tool": tool, "args": args,
                          "result": res, "ok": ok})


def _is_error(res):
    return isinstance(res, dict) and "error" in res


def _build_view(invocations):
    """Composer-facing results view.

    Results are addressable by their unique invocation id
    ("analyze_terrain#1", "analyze_terrain#2", ...). For backwards
    compatibility each tool name is also an alias: it resolves to the first
    successful invocation of that tool, or to its first invocation when every
    run failed - so a late failure can never overwrite a successful result."""
    view, best = {}, {}
    for inv in invocations:
        view[inv["id"]] = inv["result"]
        cur = best.get(inv["tool"])
        if cur is None or (not cur["ok"] and inv["ok"]):
            best[inv["tool"]] = inv
    for tool, inv in best.items():
        view[tool] = inv["result"]
    return view


def _failure_note(invocations):
    """Honest acknowledgement of partial failure: missing data stays missing."""
    failed = [i for i in invocations if not i["ok"]]
    if not failed:
        return None
    parts = []
    for f in failed[:3]:
        detail = ""
        if isinstance(f["result"], dict):
            detail = str(f["result"].get("detail") or f["result"].get("error") or "")
        parts.append("%s: %s" % (f["id"], detail or "failed"))
    more = " (+%d more)" % (len(failed) - 3) if len(failed) > 3 else ""
    return ("Note: %d of %d tool call(s) failed [%s%s]; that information is missing "
            "from this answer and nothing was invented to fill the gap. Every other "
            "statement above comes from successful, grounded tool outputs."
            % (len(failed), len(invocations), "; ".join(parts), more))


def _llm_trace(invocations):
    """Per-invocation trace for the model: id, tool, args and result-or-error,
    with each result structurally slimmed so the prompt stays valid JSON."""
    entries = []
    for inv in invocations:
        e = {"id": inv["id"], "tool": inv["tool"], "args": inv["args"], "ok": inv["ok"]}
        if inv["ok"]:
            e["result"] = _slim_value(inv["result"], _SLIM_CHAR_BUDGET)
        else:
            e["error"] = inv["result"] if isinstance(inv["result"], dict) else str(inv["result"])
        entries.append(e)
    return entries


def _citations_from(invocations):
    cits = []
    seen = set()
    for inv in invocations:
        if isinstance(inv, dict) and not inv.get("ok", True):
            continue
        res = inv.get("result") if isinstance(inv, dict) else None
        if not isinstance(res, dict):
            continue
        p = res.get("provenance") or res.get("anchor")
        if p:
            entry = "%s: %s" % (inv.get("tool", "?"),
                                p if isinstance(p, str) else p.get("source", ""))
            if entry not in seen:
                seen.add(entry)
                cits.append(entry)
        if "observations" in res:
            for o in res["observations"][:3]:
                if "evidence" in o:
                    cit = o["evidence"]["citation"]
                    if cit not in seen:
                        seen.add(cit)
                        cits.append(cit)
    return cits or ["NAM deterministic services [SIM]"]
