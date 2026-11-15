"""JEV endpoints: 24-tool registry, SSE chat with tool-activity trace,
explain-view, benchmark."""
import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import db
from ..jev import llm, router as jev_router
from ..jev.tools import TOOLS, run_tool

router = APIRouter(prefix="/jev", tags=["jev"])


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
        results = {}
        if planned and planned.get("steps"):
            llm_planned = True
            steps = planned["steps"]
        else:
            plan, composer = jev_router.plan_for(c.message, c.map_context)
            steps = plan.steps
        for step in steps:
            yield _sse({"type": "tool_start", "tool": step["tool"], "args": step["args"]})
            res = run_tool(step["tool"], step["args"], {"map_context": c.map_context})
            results[step["tool"]] = res
            summary_keys = [k for k in res.keys()][:6] if isinstance(res, dict) else []
            yield _sse({"type": "tool_result", "tool": step["tool"],
                        "ok": "error" not in res, "keys": summary_keys})
        if llm_planned:
            answer = llm.chat_with_llm(c.message, c.map_context, _slim(results)) or \
                "The local model could not produce an answer; tool outputs above are grounded and complete."
            citations = ["tool outputs: " + ", ".join(results.keys())]
            intents = planned.get("intents", [])
        else:
            answer = composer(results)
            citations = [s for s in _citations_from(results)]
            intents = plan.intents
        # stream the answer in small chunks (token-stream shim; real LLM streams natively)
        chunks = [answer[i:i + 90] for i in range(0, len(answer), 90)]
        for chn in chunks:
            yield _sse({"type": "delta", "text": chn})
            await asyncio.sleep(0.01)
        db.ex("INSERT INTO chat_logs (role,content) VALUES (?,?)", ("jev", answer))
        yield _sse({"type": "done", "reply": answer, "citations": citations,
                    "intents": intents, "engine": "local-llm" if llm_planned else "deterministic-router"})

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


def _slim(results):
    out = {}
    for k, v in results.items():
        s = json.dumps(v)
        out[k] = v if len(s) < 4000 else json.loads(s[:4000].rsplit(",", 1)[0] + "}")
    return out


def _citations_from(results):
    cits = []
    for tool, res in results.items():
        if isinstance(res, dict):
            p = res.get("provenance") or res.get("anchor")
            if p:
                cits.append("%s: %s" % (tool, p if isinstance(p, str) else p.get("source", "")))
            if "observations" in res:
                cits += [o["evidence"]["citation"] for o in res["observations"][:3]
                         if "evidence" in o]
    return cits or ["NAM deterministic services [SIM]"]
