"""Per-room trace store — holds last 50 AgentTrace dicts and fans out to SSE subscribers.

Usage:
    store_trace(room_id, trace_dict)   # called from ws.py on dm_stream_end
    get_traces(room_id, limit=20)      # REST endpoint
    subscribe(room_id) -> Queue        # SSE handler creates a queue
    unsubscribe(room_id, queue)        # SSE handler cleans up on disconnect
"""

from __future__ import annotations

import asyncio
from collections import deque

# ---------------------------------------------------------------------------
# In-memory stores (module-level singletons — one process, no persistence needed)
# ---------------------------------------------------------------------------

# Newest traces first (appendleft). maxlen=50 evicts the oldest automatically.
_traces: dict[str, deque[dict]] = {}

# One asyncio.Queue per SSE connection. Multiple consumers per room are supported.
_subscribers: dict[str, list[asyncio.Queue[dict]]] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def store_trace(room_id: str, trace_dict: dict) -> None:
    """Store a trace and push it to all live SSE subscribers for the room."""
    if room_id not in _traces:
        _traces[room_id] = deque(maxlen=50)
    _traces[room_id].appendleft(trace_dict)  # newest first

    for q in list(_subscribers.get(room_id, [])):
        try:
            q.put_nowait(trace_dict)
        except asyncio.QueueFull:
            pass  # slow consumer — drop rather than block


def get_traces(room_id: str, limit: int = 20) -> list[dict]:
    """Return the most recent `limit` traces (newest first)."""
    d = _traces.get(room_id, deque())
    return list(d)[:limit]


def subscribe(room_id: str) -> asyncio.Queue[dict]:
    """Register a new SSE consumer; returns its dedicated queue."""
    q: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)
    _subscribers.setdefault(room_id, []).append(q)
    return q


def unsubscribe(room_id: str, q: asyncio.Queue[dict]) -> None:
    """Remove an SSE consumer queue when the connection closes."""
    try:
        _subscribers.get(room_id, []).remove(q)
    except ValueError:
        pass
