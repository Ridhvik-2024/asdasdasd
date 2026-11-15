"""LLM adapter for JEV: optional OpenAI-compatible local server (llama.cpp
serving a 3B-class GGUF Q4_K_M instruct model, CPU only, ~3 GB RAM).

When no endpoint is configured the deterministic intent router handles all
conversation (the plan-mandated fallback). The adapter returns the same
plan/step structure either way.
"""
import json

import httpx

from .. import config


def available():
    return bool(config.LLM_BASE_URL)


def describe():
    return {
        "adapter": "openai-compatible (llama.cpp) with JSON-schema-constrained tool calls",
        "configured": available(),
        "base_url": config.LLM_BASE_URL or None,
        "model": config.LLM_MODEL if available() else None,
        "fallback": "deterministic intent router (always active)",
        "budget": "target: ~3 GB RAM steady state, CPU only, first tool call < 10 s (benchmark at Phase 3 gate)",
    }


def plan_with_llm(message, map_context, timeout_s=30.0):
    """Ask the local model to plan tool calls. Returns
    {"steps": [{"tool","args"}], "intents": [], "text": ...} or None."""
    if not available():
        return None
    tools = [{"type": "function",
              "function": {"name": t["name"], "description": t["description"],
                           "parameters": t["parameters"]}}
             for t in _tool_list()]
    sys_prompt = (
        "You are JEV, the Intelligent Mars Explorer of NAM (Navigation Assistant of Mars). "
        "You control a Mars globe and answer with grounded tool outputs only; you never "
        "invent observations, coordinates or NASA findings - you cite tool outputs or abstain. "
        "All simulations are labelled [SIM] and advisory. Coordinates: lat (south negative), "
        "lon EAST 0-360.")
    body = {
        "model": config.LLM_MODEL,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": json.dumps({"message": message,
                                                    "map_context": map_context or {}})},
        ],
        "tools": tools,
        "temperature": 0.2,
    }
    try:
        with httpx.Client(timeout=timeout_s) as cl:
            r = cl.post(config.LLM_BASE_URL + "/chat/completions", json=body)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return None
    try:
        calls = data["choices"][0]["message"].get("tool_calls", [])
        steps = [{"tool": c["function"]["name"],
                  "args": json.loads(c["function"]["arguments"] or "{}")} for c in calls]
        text = data["choices"][0]["message"].get("content") or ""
        return {"steps": steps, "intents": [], "text": text}
    except Exception:
        return None


def chat_with_llm(message, map_context, tool_trace, timeout_s=60.0):
    """Second pass: generate the final natural-language answer given tool outputs."""
    if not available():
        return None
    body = {
        "model": config.LLM_MODEL,
        "messages": [
            {"role": "system", "content": "Answer the user's Mars question using ONLY the "
             "grounded tool outputs provided. Cite the provenance of factual claims. "
             "If the outputs do not answer the question, say so honestly. Label simulated "
             "values [SIM]."},
            {"role": "user", "content": json.dumps({
                "message": message,
                "map_context": map_context or {},
                "tool_outputs": tool_trace})},
        ],
        "temperature": 0.3,
    }
    try:
        with httpx.Client(timeout=timeout_s) as cl:
            r = cl.post(config.LLM_BASE_URL + "/chat/completions", json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
    except Exception:
        return None


def _tool_list():
    from .tools import TOOLS
    return TOOLS


def benchmark():
    import time
    t0 = time.perf_counter()
    ok = None
    if available():
        try:
            with httpx.Client(timeout=8.0) as cl:
                r = cl.get(config.LLM_BASE_URL + "/models")
                ok = r.status_code == 200
        except Exception:
            ok = False
    return {"adapter": describe(), "endpoint_reachable": ok,
            "probe_ms": round((time.perf_counter() - t0) * 1000, 1),
            "note": "with no endpoint configured, the deterministic router guarantees "
                    "sub-10 s first response with zero GPU"}
