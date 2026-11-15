"""JEV endpoints: 24-tool registry, SSE chat with tool-activity trace,
explain-view, benchmark."""
import asyncio
import json
import math

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import db
from ..jev import llm, router as jev_router, tools as jev_tools
from ..jev.tools import TOOLS

router = APIRouter(prefix="/jev", tags=["jev"])

_ORIG_RUN_TOOL = jev_tools.run_tool
run_tool = _ORIG_RUN_TOOL

_PRIORITY_KEYS = ("id", "tool", "args", "ok", "error", "code", "detail",
                  "provenance", "stats", "result")


def _invoke_tool(name, args, ctx):
    fn = run_tool if run_tool is not _ORIG_RUN_TOOL else jev_tools.run_tool
    return fn(name, args, ctx)


class ToolResults(dict):
    """Stores each tool invocation under a unique invocation ID while keeping
    backward-compatible tool-name lookup for response composers."""

    def __init__(self):
        super().__init__()
        self._seq = 0
        self._invocations = []
        self._by_tool = {}
        self._latest_ok_by_tool = {}

    def next_id(self, tool, requested_id=None):
        if requested_id and requested_id != tool and not super().__contains__(requested_id):
            return requested_id
        if requested_id and requested_id != tool and super().__contains__(requested_id):
            suffix = 2
            cid = "%s_%d" % (requested_id, suffix)
            while super().__contains__(cid) or cid == tool:
                suffix += 1
                cid = "%s_%d" % (requested_id, suffix)
            return cid
        self._seq += 1
        cid = "call_%d" % self._seq
        while super().__contains__(cid) or cid == tool:
            self._seq += 1
            cid = "call_%d" % self._seq
        return cid

    def record(self, tool, args, raw_result, inv_id=None):
        cid = self.next_id(tool, inv_id)
        if raw_result is None:
            raw_result = {"error": "empty_tool_result", "detail": "tool returned None"}
        ok = not (isinstance(raw_result, dict) and "error" in raw_result)
        if ok:
            err = None
        else:
            code = raw_result.get("error", "tool_error")
            detail = raw_result.get("detail") or str(code)
            err = {"code": code, "error": code, "detail": detail}
        entry = {
            "id": cid,
            "tool": tool,
            "args": dict(args) if isinstance(args, dict) else {},
            "ok": ok,
            "result": raw_result,
            "error": err,
        }
        super().__setitem__(cid, entry)
        self._invocations.append(entry)
        self._by_tool.setdefault(tool, []).append(entry)
        if ok:
            self._latest_ok_by_tool[tool] = raw_result
        return entry

    def __getitem__(self, key):
        if super().__contains__(key):
            return super().__getitem__(key)
        if key in self._latest_ok_by_tool:
            return self._latest_ok_by_tool[key]
        if key in self._by_tool:
            return self._by_tool[key][-1]["result"]
        raise KeyError(key)

    def get(self, key, default=None):
        if super().__contains__(key):
            return super().__getitem__(key)
        if key in self._latest_ok_by_tool:
            return self._latest_ok_by_tool[key]
        if key in self._by_tool:
            return self._by_tool[key][-1]["result"]
        return default

    @property
    def invocations(self):
        return list(self._invocations)

    def for_tool(self, tool, only_ok=False):
        entries = self._by_tool.get(tool, [])
        if only_ok:
            return [e for e in entries if e["ok"]]
        return list(entries)

    def results_for_tool(self, tool, only_ok=True):
        return [e["result"] for e in self.for_tool(tool, only_ok=only_ok)]

    def errors(self):
        return [e for e in self._invocations if not e["ok"]]


def execute_step(results, step, map_context=None, inv_id=None):
    """Execute one planned step safely without aborting subsequent steps."""
    tool_name = (step or {}).get("tool") or ""
    raw_args = (step or {}).get("args")
    cid = inv_id or results.next_id(tool_name, (step or {}).get("id"))
    if raw_args is None:
        step_args = {}
        bad_args = False
    elif isinstance(raw_args, dict):
        step_args = raw_args
        bad_args = False
    else:
        step_args = {}
        bad_args = True

    if bad_args:
        raw = {"error": "invalid_arguments",
               "detail": "tool arguments must be an object",
               "fail_closed": True}
    else:
        try:
            raw = _invoke_tool(tool_name, step_args, {"map_context": map_context or {}})
        except Exception as exc:
            raw = {"error": "tool_execution_failed",
                   "detail": "%s: %s" % (type(exc).__name__, exc)}
    return results.record(tool_name, step_args, raw, inv_id=cid)


def execute_steps(steps, map_context=None):
    """Execute a sequence of tool steps, preserving every invocation and error."""
    results = ToolResults()
    for step in (steps or []):
        execute_step(results, step, map_context=map_context)
    return results


def _acknowledge_failures(answer, results):
    failed = results.errors() if hasattr(results, "errors") else []
    if not failed:
        return answer
    low = (answer or "").lower()
    ack_terms = ("unavailable", "missing", "incomplete", "failed", "could not")
    has_ack = any(t in low for t in ack_terms)
    if has_ack and all(f["tool"].lower() in low for f in failed):
        return answer
    parts = [
        "%s [%s] (%s)" % (
            f["tool"],
            f["id"],
            (f.get("error") or {}).get("detail") or (f.get("error") or {}).get("code", "failed"),
        )
        for f in failed
    ]
    note = ("Note: Some information is missing or incomplete because %d tool call(s) failed: %s."
            % (len(failed), "; ".join(parts)))
    return ("%s\n%s" % ((answer or "").rstrip(), note)).strip()


@router.get("/tools")
def tools_list():
    return {"count": len(TOOLS), "tools": TOOLS,
            "note": "16 tools carried from NAM v1 + 8 Phase 3 tools; JSON-schema-constrained, fail closed"}


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
        planned = llm.plan_with_llm(c.message, c.map_context)
        results = ToolResults()
        if planned and planned.get("steps"):
            llm_planned = True
            steps = planned["steps"]
        else:
            plan, composer = jev_router.plan_for(c.message, c.map_context)
            steps = plan.steps
        for step in steps:
            tool_name = (step or {}).get("tool") or ""
            step_args = (step or {}).get("args") if isinstance((step or {}).get("args"), dict) else {}
            cid = results.next_id(tool_name, (step or {}).get("id"))
            yield _sse({"type": "tool_start", "id": cid, "tool": tool_name, "args": step_args})
            inv = execute_step(results, step, map_context=c.map_context, inv_id=cid)
            raw = inv["result"]
            summary_keys = [k for k in raw.keys()][:6] if isinstance(raw, dict) else []
            evt = {"type": "tool_result", "id": inv["id"], "tool": tool_name,
                   "ok": inv["ok"], "keys": summary_keys}
            if not inv["ok"]:
                evt["error"] = inv["error"]
            yield _sse(evt)
        if llm_planned:
            slimmed = _slim(results)
            fallback_msg = (
                "The local model could not produce an answer; some tool calls failed so "
                "available outputs are partial."
                if results.errors()
                else "The local model could not produce an answer; tool outputs above are grounded and complete."
            )
            answer = llm.chat_with_llm(c.message, c.map_context, slimmed) or fallback_msg
            citations = ["tool outputs: " + ", ".join("%s (%s)" % (i["tool"], i["id"]) for i in results.invocations)]
            intents = planned.get("intents", [])
        else:
            answer = composer(results)
            citations = [s for s in _citations_from(results)]
            intents = plan.intents
        answer = _acknowledge_failures(answer, results)
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
            "engine": "local-llm" if llm_planned else "deterministic-router",
            "invocations": [
                {"id": inv["id"], "tool": inv["tool"], "args": inv["args"],
                 "ok": inv["ok"], "error": inv["error"]}
                for inv in results.invocations
            ],
            "errors": [
                {"id": inv["id"], "tool": inv["tool"], "args": inv["args"], "error": inv["error"]}
                for inv in results.errors()
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


@router.get("/logs")
def logs(limit: int = 20):
    rows = db.q("SELECT ts,role,content FROM chat_logs ORDER BY id DESC LIMIT ?", (min(limit, 100),))
    return {"logs": rows}


def _normalize_json_value(val):
    if val is None or isinstance(val, (bool, int, str)):
        return val
    if isinstance(val, float):
        return val if math.isfinite(val) else None
    if hasattr(val, "item") and callable(getattr(val, "item")):
        try:
            return _normalize_json_value(val.item())
        except Exception:
            return str(val)
    if isinstance(val, dict):
        return {str(k): _normalize_json_value(v) for k, v in val.items()}
    if isinstance(val, (list, tuple, set)):
        return [_normalize_json_value(x) for x in val]
    return str(val)


def _truncate_str(s, max_str):
    if len(s) <= max_str:
        return s
    if max_str <= 24:
        return s[:max(1, max_str)] + "..."
    omitted = len(s) - max_str
    return "%s ...[truncated %d chars]" % (s[:max_str], omitted)


def _truncate_struct(val, *, depth, max_depth, max_items, max_keys, max_str, max_key_len=80):
    if val is None or isinstance(val, (bool, int)):
        return val
    if isinstance(val, float):
        return val if math.isfinite(val) else None
    if isinstance(val, str):
        return _truncate_str(val, max_str)
    if isinstance(val, (list, tuple)):
        if depth >= max_depth:
            return []
        return [
            _truncate_struct(
                x,
                depth=depth + 1,
                max_depth=max_depth,
                max_items=max_items,
                max_keys=max_keys,
                max_str=max_str,
                max_key_len=max_key_len,
            )
            for x in val[:max_items]
        ]
    if isinstance(val, dict):
        if depth >= max_depth:
            return {"_truncated": True, "_keys_count": len(val)}
        ordered_keys = [k for k in _PRIORITY_KEYS if k in val] + [
            k for k in val.keys() if k not in _PRIORITY_KEYS
        ]
        kept_keys = ordered_keys[:max_keys]
        out = {}
        for k in kept_keys:
            ks = _truncate_str(str(k), max_key_len)
            out[ks] = _truncate_struct(
                val[k],
                depth=depth + 1,
                max_depth=max_depth,
                max_items=max_items,
                max_keys=max_keys,
                max_str=max_str,
                max_key_len=max_key_len,
            )
        if depth == 0 or len(ordered_keys) > max_keys:
            out["_truncated"] = True
        if len(ordered_keys) > max_keys:
            out["_omitted_keys"] = len(ordered_keys) - max_keys
        return out
    return _truncate_str(str(val), max_str)


_SLIM_TIERS = (
    (5, 25, 40, 600, 120),
    (4, 10, 20, 250, 80),
    (3, 5, 12, 120, 60),
    (2, 2, 6, 48, 40),
)


def _slim_one(val, max_chars=4000):
    norm = _normalize_json_value(val)
    raw_json = json.dumps(norm, ensure_ascii=False)
    if len(raw_json) < max_chars:
        return norm
    for max_depth, max_items, max_keys, max_str, max_key_len in _SLIM_TIERS:
        cand = _truncate_struct(
            norm,
            depth=0,
            max_depth=max_depth,
            max_items=max_items,
            max_keys=max_keys,
            max_str=max_str,
            max_key_len=max_key_len,
        )
        if len(json.dumps(cand, ensure_ascii=False)) <= max_chars:
            return cand
    if isinstance(norm, str):
        budget = max(1, max_chars - 32)
        return _truncate_str(norm, budget)
    if isinstance(norm, list):
        return []
    summary = {"_truncated": True}
    if isinstance(norm, dict):
        for k in ("id", "tool", "ok"):
            if k in norm and isinstance(norm[k], (bool, int, float, str)) and len(str(norm[k])) <= 64:
                summary[k] = norm[k]
    if len(json.dumps(summary, ensure_ascii=False)) <= max_chars:
        return summary
    return {"_truncated": True}


def _slim(results, max_chars=4000):
    """Structurally truncate oversized tool outputs while preserving valid JSON."""
    if not isinstance(results, dict):
        return _slim_one(results, max_chars=max_chars)
    out = {}
    for k, v in dict.items(results):
        key_str = _truncate_str(str(k), 120)
        out[key_str] = _slim_one(v, max_chars=max_chars)
    return out


def _citations_from(results):
    cits = []
    seen = set()
    for key, val in dict.items(results):
        if isinstance(val, dict) and "tool" in val and ("result" in val or "error" in val):
            if not val.get("ok", True):
                continue
            tool = val["tool"]
            res = val.get("result")
        else:
            tool = key
            res = val
            if isinstance(res, dict) and "error" in res:
                continue
        if isinstance(res, dict):
            p = res.get("provenance") or res.get("anchor")
            if p:
                entry = "%s: %s" % (tool, p if isinstance(p, str) else p.get("source", ""))
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
