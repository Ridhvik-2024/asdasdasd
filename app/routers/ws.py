"""WebSocket channels: /ws/events and /ws/presence with bounded rates.

Events carried: storm alerts, presence updates, plan changes, telemetry ticks.
Rate limiting is enforced per event kind in the hub (bounded rates target).
"""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .. import events, presence

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/events")
async def ws_events(ws: WebSocket):
    await ws.accept()
    q = events.hub.subscribe("events")
    try:
        await ws.send_json({"type": "welcome", "channel": "events",
                            "carries": ["storm_alert", "plan_change", "telemetry_tick"],
                            "integrity": "simulated payloads carry [SIM]"})
        while True:
            try:
                evt = await asyncio.wait_for(q.get(), timeout=10.0)
                await ws.send_json(evt)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "heartbeat", "channel": "events"})
    except WebSocketDisconnect:
        pass
    finally:
        events.hub.unsubscribe("events", q)


@router.websocket("/ws/presence")
async def ws_presence(ws: WebSocket):
    await ws.accept()
    q = events.hub.subscribe("presence")
    try:
        await ws.send_json({"type": "welcome", "channel": "presence",
                            "carries": ["presence_update [SIM] at bounded rate"]})
        # immediate snapshot so clients have current state on connect
        await ws.send_json({"type": "presence_update", "agents": presence.agents(), "sim": True})
        while True:
            try:
                evt = await asyncio.wait_for(q.get(), timeout=10.0)
                await ws.send_json(evt)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "heartbeat", "channel": "presence"})
    except WebSocketDisconnect:
        pass
    finally:
        events.hub.unsubscribe("presence", q)


@router.post("/events/trigger")
async def trigger(kind: str = "storm_alert", payload: dict = None):
    """Demo drill trigger: storm alert reaches connected clients (and JEV
    consumers) within ~1 s; plan_change supported too."""
    evt = {"type": kind, "payload": payload or {"note": "drill"}, "sim": True}
    events.hub.broadcast("events", evt)
    return {"triggered": evt, "counters": events.hub.counters,
            "note": "rate-limited per kind (bounded rates); simulated events carry [SIM]"}

