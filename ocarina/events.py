"""The event log: ring buffer, always recording.

State answers *what is*; the log answers *what happened*; neither is
derivable from the other (SURFACE.md). The timeline interleaves world
events and machine events so postmortems can attach blame to nodes.
Persisted, this stream IS the mechanical journal (`oot://journal/
mechanical`) — one artifact, written as JSON lines into the save-file
repo so the server's live state is never the only copy.

Timestamps: `t` is `gameplay_frames` when the world clock is known — the
logic clock, the only counter that can observe a freeze (workshop docs/08
§1) — plus `wall`, the ISO wall-clock instant, because the mechanical
journal outlives sessions and frames reset with the game.
"""

from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional


class EventLog:
    def __init__(self, persist_path: Optional[Path | str] = None,
                 capacity: int = 4000):
        self._ring: deque = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._seq = 0
        self.persist_path = Path(persist_path) if persist_path else None
        #: Best-effort mirrors (brainviz's SSE fan-out). Called with the
        #: stored event OUTSIDE the lock, after ring + journal; must not
        #: mutate it, must not block, and a raising observer is dropped
        #: from the flow for that event, never propagated — the log is
        #: on the 20 Hz path and a debug passenger cannot take it down.
        self.observers: list = []

    def record(self, event: dict, frames: Optional[int] = None) -> dict:
        """Stamp and append. Returns the stored event (a copy)."""
        if "event" not in event:
            raise ValueError(f"events need an 'event' key: {event!r}")
        ev = dict(event)
        with self._lock:
            self._seq += 1
            ev["seq"] = self._seq
            if frames is not None:
                ev["t"] = frames
            ev["wall"] = datetime.now().isoformat(timespec="seconds")
            self._ring.append(ev)
            if self.persist_path is not None:
                try:
                    self.persist_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.persist_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(ev) + "\n")
                except OSError:
                    # The ring still has it; a full disk must not take the
                    # machine down. Visible in the next status() read.
                    pass
        for observe in list(self.observers):
            try:
                observe(ev)
            except Exception:
                pass
        return ev

    def tail(self, n: int = 30, category: Optional[str] = None,
             kind: Optional[str] = None, since_t: Optional[int] = None) -> list:
        """Most recent events, oldest first, optionally filtered — the
        query surface behind `oot://events` (last N, by category, by
        actor kind, since t)."""
        with self._lock:
            out = list(self._ring)
        if category is not None:
            out = [e for e in out if e.get("event") == category]
        if kind is not None:
            out = [e for e in out if e.get("kind") == kind or e.get("actor") == kind]
        if since_t is not None:
            out = [e for e in out if e.get("t", -1) >= since_t]
        return out[-n:] if n > 0 else out
