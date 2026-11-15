"""LLM adapter for JEV: optional OpenAI-compatible local server (llama.cpp
serving a 3B-class GGUF Q4_K_M instruct model, CPU only, ~3 GB RAM).

When no endpoint is configured the deterministic intent router handles all
conversation (the plan-mandated fallback). Model-generated tool calls are
independently validated against JSON schema + Mars semantic constraints.
"""
import json

import httpx

from .. import config


def available():
    return bool(config.LLM_BASE_URL)


def describe():
    return {
        "adapter": "openai-compatible (llama.cpp) with JSON-schema + semantic tool validation",
        "configured": available(),
        "base_url": config.LLM_BASE_URL or None,
        "model": config.LLM_MODEL if available() else None,
        "fallback": "deterministic intent router (always active)",
        "budget": "target: ~3 GB RAM steady state, CPU only, first tool call < 10 s (benchmark at Phase 3 gate)",
    }


def validate_planned_tool_calls(calls):
    """Parse and validate OpenAI-style tool_calls from an LLM response.

    Returns (valid_steps, rejected_calls). Any malformed JSON, non-object
    arguments, unregistered tool, unexpected extra keys, invalid enum, or
    out-of-range Mars coordinates are rejected fail-closed instead of being
    forwarded blindly to execution.
    """
    from .tools import validate_tool_call

    valid_steps = []
    rejected = []
    for raw_call in (calls or []):
        if not isinstance(raw_call, dict):
            rejected.append({"call": raw_call, "error": "tool_call entry must be an object"})
            continue
        fn = raw_call.get("function") if isinstance(raw_call.get("function"), dict) else raw_call
        tool_name = fn.get("name") or raw_call.get("tool")
        raw_args = fn.get("arguments") if "arguments" in fn else raw_call.get("args", {})
        if isinstance(raw_args, str):
            try:
                parsed_args = json.loads(raw_args or "{}")
            except (TypeError, ValueError) as exc:
                rejected.append({"tool": tool_name, "error": "malformed JSON arguments: %s" % exc})
                continue
        else:
            parsed_args = raw_args
        if not isinstance(parsed_args, dict):
            rejected.append({"tool": tool_name, "error": "tool arguments must decode to an object"})
            continue
        err = validate_tool_call(tool_name, parsed_args)
        if err:
            rejected.append({"tool": tool_name, "args": parsed_args, "error": err})
            continue
        step = {"tool": tool_name, "args": parsed_args}
        if raw_call.get("id"):
            step["id"] = str(raw_call["id"])
        valid_steps.append(step)
    return valid_steps, rejected


def plan_with_llm(message, map_context, timeout_s=30.0):
    """Ask the local model to plan tool calls. Returns
    {"steps": [{"tool","args"}], "rejected": [...], "intents": [], "text": ...} or None."""
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
        msg_obj = data["choices"][0]["message"]
        calls = msg_obj.get("tool_calls") or []
        steps, rejected = validate_planned_tool_calls(calls)
        if calls and not steps:
            # Every model-proposed tool call failed validation: fall back to deterministic router.
            return None
        text = msg_obj.get("content") or ""
        return {"steps": steps, "rejected": rejected, "intents": [], "text": text}
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
    reachable = None
    status = "disabled"
    if available():
        status = "unavailable"
        try:
            with httpx.Client(timeout=3.0) as cl:
                r = cl.get(config.LLM_BASE_URL + "/models")
                r.raise_for_status()
                reachable = True
                data = r.json().get("data")
                if isinstance(data, list):
                    names = {str(item.get("id", "")) for item in data if isinstance(item, dict)}
                    status = "ready" if config.LLM_MODEL in names else "missing_model"
                else:
                    status = "unknown"
        except Exception:
            reachable = False
    return {"adapter": describe(), "endpoint_reachable": reachable, "model_status": status,
            "probe_ms": round((time.perf_counter() - t0) * 1000, 1),
            "note": "A local model interprets requests only when the model server and selected model are available."}


def extract_route_places(message, timeout_s=60.0):
    """Use the configured model only to extract literal place names from a request.

    Coordinates, resource locations, and route calculations never come from the
    model. Reject invented/non-literal names and malformed output; the caller
    can fall back to the explicit structured input or a simple parser.
    """
    if not available() or not isinstance(message, str) or not message.strip():
        return None
    body = {
        "model": config.LLM_MODEL,
        "messages": [
            {"role": "system", "content": (
                "Extract the ordered departure, intermediate destinations, and final destination "
                "from the user's Mars route request. Return only JSON: {\"places\":[\"...\",\"...\"]}. "
                "Copy each place name exactly from the input; never invent names or coordinates. "
                "Ignore water, shelter and route preferences. If fewer than two places are "
                "explicitly named, return an empty places array. At most five places.")},
            {"role": "user", "content": message},
        ],
        "temperature": 0,
        "max_tokens": 200,
        "response_format": {"type": "json_object"},
    }
    try:
        with httpx.Client(timeout=timeout_s) as client:
            response = client.post(config.LLM_BASE_URL + "/chat/completions", json=body)
            response.raise_for_status()
            text = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(text)
        places = parsed.get("places") if isinstance(parsed, dict) else None
        if not isinstance(places, list) or not 2 <= len(places) <= 5:
            return None
        if not all(isinstance(p, str) and 1 <= len(p.strip()) <= 120 for p in places):
            return None
        # Names must occur in the input in the same order. The model cannot
        # invent a stop or silently reverse an explicitly ordered journey.
        cursor = 0
        for place in places:
            position = message.casefold().find(place.strip().casefold(), cursor)
            if position < 0:
                return None
            cursor = position + len(place.strip())
        return [p.strip() for p in places]
    except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError):
        return None
