"""In-process publish/subscribe for live screens, and a per-key rate limiter.

SlipCast runs as one API process, so a dictionary of queues is enough. Routers run in a
thread pool, so messages are handed to each subscriber's event loop thread-safely.
"""

import asyncio
import threading
import time
from collections import defaultdict, deque


class Broker:
    def __init__(self) -> None:
        self._subs: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = defaultdict(set)
        self._lock = threading.Lock()

    def subscribe(self, project_id: str, queue: asyncio.Queue | None = None) -> asyncio.Queue:
        """Pass the same queue for several projects to hear all of them (the Control Room does)."""
        queue = queue or asyncio.Queue(maxsize=100)
        with self._lock:
            self._subs[project_id].add((asyncio.get_running_loop(), queue))
        return queue

    def unsubscribe(self, project_id: str, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subs[project_id] = {s for s in self._subs[project_id] if s[1] is not queue}
            if not self._subs[project_id]:
                del self._subs[project_id]

    def listeners(self, project_id: str) -> int:
        with self._lock:
            return len(self._subs.get(project_id, ()))

    def publish(self, project_id: str, message: dict) -> None:
        with self._lock:
            targets = list(self._subs.get(project_id, ()))
        message = {**message, "project_id": project_id}
        for loop, queue in targets:
            try:
                loop.call_soon_threadsafe(_offer, queue, message)
            except RuntimeError:  # that subscriber's loop has closed
                pass


def _offer(queue: asyncio.Queue, message: dict) -> None:
    if queue.full():  # a stalled screen only ever needs the newest "something changed"
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    queue.put_nowait(message)


broker = Broker()


class RateLimiter:
    """Sliding one-minute window, counted in events, per API key."""

    def __init__(self) -> None:
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, count: int, per_minute: int) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) + count > per_minute:
                return False
            hits.extend([now] * count)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()
