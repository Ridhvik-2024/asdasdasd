"""Real-time event hub with bounded rates, monotonic sequence IDs, and
ring-buffer replay for reconnecting WebSocket clients."""
import asyncio
from collections import deque
import threading
import time

MIN_INTERVALS = {           # seconds between broadcasts of the same kind
    ("events", "telemetry_tick"): 4.0,
    ("presence", "presence_update"): 1.8,
}
HISTORY_LIMIT = 200


class Hub:
    def __init__(self):
        self._lock = threading.Lock()
        self._subs: dict = {}
        self._last: dict = {}
        self._seq: dict = {}
        self._history: dict = {}
        self._loop = None
        self.counters = {"events": 0, "presence": 0, "dropped": 0}

    def attach_loop(self, loop):
        self._loop = loop

    def subscribe(self, channel):
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        with self._lock:
            self._subs.setdefault(channel, []).append(q)
        return q

    def unsubscribe(self, channel, q):
        with self._lock:
            subs = self._subs.get(channel, [])
            if q in subs:
                subs.remove(q)

    def since(self, channel, after_id=0, limit=50):
        """Return buffered events on *channel* with event_id > after_id."""
        with self._lock:
            hist = list(self._history.get(channel, ()))
        filtered = [e for e in hist if e.get("event_id", 0) > int(after_id)]
        return filtered[-max(1, min(int(limit), HISTORY_LIMIT)):]

    def _push(self, channel, event):
        with self._lock:
            subs = list(self._subs.get(channel, []))
        for q in subs:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                self.counters["dropped"] += 1

    def broadcast(self, channel, event):
        """Thread-safe broadcast; per-kind bounded rate + monotonic event_id."""
        key = (channel, event.get("type"))
        min_iv = MIN_INTERVALS.get(key, 0.0)
        now = time.monotonic()
        with self._lock:
            if min_iv and now - self._last.get(key, 0.0) < min_iv:
                self.counters["dropped"] += 1
                return False
            self._last[key] = now
            nxt_id = self._seq.get(channel, 0) + 1
            self._seq[channel] = nxt_id
            event.setdefault("event_id", nxt_id)
            event.setdefault("ts", round(time.time(), 3))
            enriched = dict(event)
            buf = self._history.get(channel)
            if buf is None:
                buf = deque(maxlen=HISTORY_LIMIT)
                self._history[channel] = buf
            buf.append(enriched)
            self.counters[channel] = self.counters.get(channel, 0) + 1

        if self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(self._push, channel, enriched)
                return True
            except RuntimeError:
                pass
        self._push(channel, enriched)
        return True


hub = Hub()
