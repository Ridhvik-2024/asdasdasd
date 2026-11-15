"""Real-time event hub with bounded rates (WebSocket backends)."""
import asyncio
import time

MIN_INTERVALS = {           # seconds between broadcasts of the same kind
    ("events", "telemetry_tick"): 4.0,
    ("presence", "presence_update"): 1.8,
}


class Hub:
    def __init__(self):
        self._subs: dict = {}
        self._last: dict = {}
        self._loop = None
        self.counters = {"events": 0, "presence": 0, "dropped": 0}

    def attach_loop(self, loop):
        self._loop = loop

    def subscribe(self, channel):
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subs.setdefault(channel, []).append(q)
        return q

    def unsubscribe(self, channel, q):
        if q in self._subs.get(channel, []):
            self._subs[channel].remove(q)

    def _push(self, channel, event):
        for q in list(self._subs.get(channel, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                self.counters["dropped"] += 1

    def broadcast(self, channel, event):
        """Thread-safe broadcast; per-kind bounded rate."""
        key = (channel, event.get("type"))
        min_iv = MIN_INTERVALS.get(key, 0.0)
        now = time.monotonic()
        if min_iv and now - self._last.get(key, 0.0) < min_iv:
            self.counters["dropped"] += 1
            return False
        self._last[key] = now
        self.counters[channel] = self.counters.get(channel, 0) + 1
        if self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(self._push, channel, event)
                return True
            except RuntimeError:
                pass
        self._push(channel, event)
        return True


hub = Hub()
