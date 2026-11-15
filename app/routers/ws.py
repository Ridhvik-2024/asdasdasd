"""WebSocket channels: /ws/events and /ws/presence with bounded rates,
sequence IDs, and reconnection history replay."""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .. import events, presence

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/events")
async def ws_events(ws: WebSocket, since_id: int = None):
    await ws.accept()
    q = events.hub.subscribe("events")
    try:
        await ws.send_json({"type": "welcome", "channel": "events",
                            "carries": ["storm_alert", "plan_change", "telemetry_tick"],
                            "integrity": "simulated payloads carry [SIM]"})
        if since_id is not None:
            for missed in events.hub.since("events", after_id=since_id):
                await ws.send_json(missed)
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
async def ws_presence(ws: WebSocket, since_id: int = None):
    await ws.accept()
    q = events.hub.subscribe("presence")
    try:
        await ws.send_json({"type": "welcome", "channel": "presence",
                            "carries": ["presence_update [SIM] at bounded rate"]})
        if since_id is not None:
            for missed in events.hub.since("presence", after_id=since_id):
                await ws.send_json(missed)
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


@router.get("/events/history")
def event_history(channel: str = "events", after_id: int = 0, limit: int = 50):
    items = events.hub.since(channel, after_id=after_id, limit=limit)
    return {"channel": channel, "count": len(items), "events": items}


@router.post("/events/trigger")
async def trigger(kind: str = "storm_alert", payload: dict = None):
    """Demo drill trigger: storm alert reaches connected clients (and JEV
    consumers) within ~1 s; plan_change supported too."""
    evt = {"type": kind, "payload": payload or {"note": "drill"}, "sim": True}
    delivered = events.hub.broadcast("events", evt)
    return {"triggered": evt, "delivered": delivered, "counters": events.hub.counters,
            "note": "rate-limited per kind (bounded rates); simulated events carry [SIM]"}
