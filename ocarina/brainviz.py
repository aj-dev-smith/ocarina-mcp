"""Brainviz: the brain viewer's spigot — a one-way debug sidecar.

The human debug organ for the MACHINE, the way overlay.py is the human
debug organ for the SENSORIUM: it renders what ocarina believes and
does, and by construction nothing flows back. Where the overlay pushes
labels into the game window, brainviz serves a local HTTP port a browser
sits on next to the game:

    GET /          the viewer app (lab/brainviz/viewer.html, read from
                   disk per request — edit, refresh, no server restart)
    GET /topology  the loaded machine as graph JSON (nodes, scopes,
                   transitions, behavior sizes)
    GET /stream    Server-Sent Events: a backlog of recent journal
                   events, then every event as it is recorded, with a
                   ~1 Hz status snapshot (current node, frozen, guard
                   edge truth) riding between them

One-way is structural, not disciplinary: every endpoint is a GET, SSE
cannot carry anything upstream, and nothing here is readable by the
sensorium, the machine, or the mind's tool surface. Off by default;
`--brainviz PORT` turns it on. A viewer crash, a slow browser, or no
browser at all must never touch the 20 Hz loop — event fan-out is
drop-oldest per client, and all serving happens on the HTTP threads.

The browser survives server restarts (EventSource auto-reconnects and
the viewer re-fetches /topology), which the sixth flight's two mid-run
/mcp restarts made a requirement, not a nicety.
"""

from __future__ import annotations

import inspect
import json
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

#: Where the viewer app lives, relative to the repo checkout. Lab-side
#: on purpose: the app is dev tooling in the ydan_viewer.html house
#: style (one self-contained file, no build step), not blessed surface.
_DEFAULT_VIEWER = Path(__file__).resolve().parent.parent / "lab" / "brainviz" / "viewer.html"

#: Journal events replayed to a freshly connected viewer, so a browser
#: opened mid-flight gets a ticker and dwell heat instead of a blank
#: brain.
_BACKLOG = 150


def topology(machine) -> dict:
    """The loaded machine as graph JSON. Everything the viewer draws is
    declared structure: nodes with their scope parent, transitions with
    kind/guard/actions (the viewer derives edges from `goto` args and
    wake beams from `wake` verbs), and behavior size for node scale."""
    nodes = []
    for name, node in machine.nodes.items():
        entry = {
            "name": name,
            "parent": node.parent,
            "transitions": [_transition(t) for t in node.transitions],
        }
        if node.is_leaf:
            entry["behavior"] = _behavior(node.behavior, machine.behaviors.get(node.behavior))
        else:
            entry["initial"] = node.initial
            entry["children"] = list(node.children)
        nodes.append(entry)
    return {
        "hash": machine.source_hash,
        "initial": machine.initial,
        "nodes": nodes,
        "root_transitions": [_transition(t) for t in machine.root_transitions],
    }


def _transition(t) -> dict:
    out = {
        "name": t.name,
        "kind": t.kind,                      # "event" (on/where) | "state" (when)
        "do": [{"verb": a.verb, "arg": a.arg} for a in t.do],
    }
    if t.on is not None:
        out["on"] = t.on
    if t.guard is not None:
        out["guard"] = t.guard.src
    if t.default is not None:
        out["default"] = {"verb": t.default.verb, "arg": t.default.arg}
    if t.cooldown_s:
        out["cooldown_s"] = t.cooldown_s
    return out


def _behavior(full_name: Optional[str], behavior) -> Optional[dict]:
    if full_name is None:
        return None
    out = {"name": full_name}
    if behavior is None:
        return out
    out["version"] = behavior.version
    out["description"] = behavior.description
    out["grade"] = behavior.grade
    out["timeout_s"] = behavior.timeout_s
    try:
        # Body size drives node scale in the viewer: the brain visibly
        # grows as behaviors buy senses (open_chest v1→v5). Best-effort —
        # a body whose source is unreadable just renders default-sized.
        out["loc"] = len(inspect.getsource(behavior.body).splitlines())
    except (OSError, TypeError):
        pass
    return out


class Brainviz:
    """The sidecar. Construct with the runtime and its log, `start()`
    once at boot; everything else is pulled by the browser."""

    def __init__(self, runtime, log, viewer_path: Optional[Path] = None,
                 host: str = "127.0.0.1", port: int = 43385):
        self.runtime = runtime
        self.log = log
        self.viewer_path = Path(viewer_path) if viewer_path else _DEFAULT_VIEWER
        self.host = host
        self.port = port
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._clients: set = set()          # per-connection event queues
        self._clients_lock = threading.Lock()

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> str:
        """Bind, subscribe to the log, serve on a daemon thread. Returns
        the URL. Raises OSError if the port is taken — a boot-time flag
        deserves a boot-time failure, not a silent dead viewer."""
        viz = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):
                viz._route(self)

            def do_POST(self):        # one-way, structurally
                self.send_error(405, "brainviz is one-way: GET only")

            do_PUT = do_DELETE = do_PATCH = do_POST

            def log_message(self, *args):   # stderr belongs to diagnostics
                pass

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self.port = self._httpd.server_address[1]     # resolve port 0
        self.log.observers.append(self._on_event)
        threading.Thread(target=self._httpd.serve_forever,
                         daemon=True, name="brainviz").start()
        return f"http://{self.host}:{self.port}/"

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        try:
            self.log.observers.remove(self._on_event)
        except ValueError:
            pass

    # -- the event mirror ----------------------------------------------------

    def _on_event(self, ev: dict) -> None:
        """EventLog observer: fan the recorded event out to every
        connected viewer. Runs on whatever thread recorded — usually the
        20 Hz loop — so it must be O(clients) queue puts and can never
        block: a full queue (browser asleep, tab backgrounded) drops its
        oldest, and the backlog-on-reconnect covers the gap."""
        with self._clients_lock:
            clients = list(self._clients)
        for q in clients:
            try:
                q.put_nowait(ev)
            except queue.Full:
                try:
                    q.get_nowait()
                    q.put_nowait(ev)
                except (queue.Empty, queue.Full):
                    pass

    def _status(self) -> dict:
        """The ~1 Hz snapshot riding the stream between events: what the
        viewer cannot derive from the event flow — frozen state, the
        running behavior, and the live truth of every in-scope `when`
        guard (the smoldering-reflex display)."""
        status = self.runtime.status()
        status["guard_edges"] = self.runtime.guard_edges()
        return status

    # -- routing -------------------------------------------------------------

    def _route(self, handler: BaseHTTPRequestHandler) -> None:
        path = handler.path.split("?", 1)[0]
        try:
            if path == "/":
                self._serve_viewer(handler)
            elif path == "/topology":
                self._serve_topology(handler)
            elif path == "/stream":
                self._serve_stream(handler)
            else:
                handler.send_error(404)
        except OSError:
            pass          # browser went away (or the socket died); its right

    def _serve_viewer(self, handler) -> None:
        try:
            body = self.viewer_path.read_bytes()
        except OSError:
            handler.send_error(404, f"viewer app not found at {self.viewer_path}")
            return
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(body)

    def _serve_topology(self, handler) -> None:
        machine = self.runtime.machine       # swapped atomically on reload
        if machine is None:
            body = json.dumps({"error": "no machine loaded",
                               "diagnostics": [d.as_dict()
                                               for d in self.runtime.diagnostics]})
        else:
            body = json.dumps(topology(machine))
        raw = body.encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(raw)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(raw)

    def _serve_stream(self, handler) -> None:
        """SSE: backlog, then live events, with a status snapshot at
        least once a second. Runs on this connection's own HTTP thread;
        the loop is the client's heartbeat and dies with the socket."""
        q: queue.Queue = queue.Queue(maxsize=500)
        with self._clients_lock:
            self._clients.add(q)
        try:
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream")
            handler.send_header("Cache-Control", "no-store")
            handler.send_header("Connection", "close")   # a stream has no length
            handler.end_headers()
            _sse(handler, "backlog", self.log.tail(_BACKLOG))
            _sse(handler, "status", self._status())
            last_status = time.monotonic()
            while self._httpd is not None:
                try:
                    ev = q.get(timeout=1.0)
                    _sse(handler, "ev", ev)
                except queue.Empty:
                    pass
                now = time.monotonic()
                if now - last_status >= 1.0:
                    _sse(handler, "status", self._status())
                    last_status = now
        finally:
            with self._clients_lock:
                self._clients.discard(q)


def _sse(handler, event: str, data) -> None:
    payload = f"event: {event}\ndata: {json.dumps(data)}\n\n"
    handler.wfile.write(payload.encode("utf-8"))
    handler.wfile.flush()
