"""Brainviz: the one-way debug sidecar.

Covers the spigot, not the app: topology JSON carries the declared
structure, the SSE stream relays recorded events with backlog and
status, the viewer file is served from disk, and one-way is enforced
at the method level. The viewer HTML itself is exercised by eyeballs
(the overlay precedent — a debug view is verified by looking at it).
"""

import http.client
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from ocarina.brainviz import Brainviz, topology
from ocarina.events import EventLog
from ocarina.game import Game
from ocarina.runtime import MachineRuntime

from .stubgame import StubLink

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "save-file"


class BrainvizCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = Path(self.tmp) / "save-file"
        shutil.copytree(FIXTURE_REPO, self.repo)
        self.viewer = Path(self.tmp) / "viewer.html"
        self.viewer.write_text("<title>brainviz test</title>")
        self.link = StubLink()
        self.game = Game(self.link)
        self.log = EventLog()
        self.runtime = MachineRuntime(self.game, self.repo, self.log)
        diags = self.runtime.load()
        assert not [d for d in diags if d["level"] == "error"], diags
        self.viz = Brainviz(self.runtime, self.log,
                            viewer_path=self.viewer, port=0)
        self.url = self.viz.start()

    def tearDown(self):
        self.viz.stop()
        self.runtime.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def get(self, path, timeout=5.0):
        conn = http.client.HTTPConnection("127.0.0.1", self.viz.port,
                                          timeout=timeout)
        conn.request("GET", path)
        return conn, conn.getresponse()


class TestTopology(BrainvizCase):
    def test_topology_json_carries_declared_structure(self):
        doc = topology(self.runtime.machine)
        self.assertEqual(doc["hash"], self.runtime.machine.source_hash)
        nodes = {n["name"]: n for n in doc["nodes"]}
        # The fixture machine: explore (interior) wrapping navigate_field
        # and kill_baba (leaves) — see tests/fixtures/save-file.
        self.assertIn("explore", nodes)
        self.assertIn("navigate_field", nodes)
        leaf = nodes["navigate_field"]
        self.assertEqual(leaf["parent"], "explore")
        self.assertEqual(leaf["behavior"]["name"], "walk_about_v1")
        self.assertGreater(leaf["behavior"].get("loc", 0), 0,
                           "behavior body size drives node scale")
        # Transitions keep their guard sources and actions: the viewer
        # derives goto edges and wake beams from these.
        trans = {t["name"]: t for t in leaf["transitions"]}
        self.assertIn("baba-in-reach", trans)
        self.assertEqual(trans["baba-in-reach"]["kind"], "state")
        self.assertIn("state.nearest_enemy", trans["baba-in-reach"]["guard"])
        self.assertIn({"verb": "goto", "arg": "kill_baba"},
                      trans["baba-in-reach"]["do"])

    def test_topology_over_http(self):
        conn, resp = self.get("/topology")
        try:
            self.assertEqual(resp.status, 200)
            doc = json.loads(resp.read())
            self.assertEqual(doc["hash"], self.runtime.machine.source_hash)
            self.assertEqual(doc["initial"], self.runtime.machine.initial)
        finally:
            conn.close()


class TestViewerAndOneWay(BrainvizCase):
    def test_viewer_served_from_disk_per_request(self):
        conn, resp = self.get("/")
        try:
            self.assertEqual(resp.status, 200)
            self.assertIn(b"brainviz test", resp.read())
        finally:
            conn.close()
        # Edit-and-refresh: the file is read per request, no restart.
        self.viewer.write_text("<title>edited</title>")
        conn, resp = self.get("/")
        try:
            self.assertIn(b"edited", resp.read())
        finally:
            conn.close()

    def test_post_refused_everywhere(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.viz.port, timeout=5.0)
        try:
            conn.request("POST", "/stream", body="{}")
            self.assertEqual(conn.getresponse().status, 405)
        finally:
            conn.close()

    def test_unknown_path_404s(self):
        conn, resp = self.get("/nope")
        try:
            self.assertEqual(resp.status, 404)
        finally:
            conn.close()


class TestStream(BrainvizCase):
    def read_sse(self, resp, want, seconds=5.0):
        """Read SSE frames until one named `want` arrives; returns its
        parsed data."""
        event = None
        while True:
            line = resp.fp.readline()
            if not line:
                raise AssertionError(f"stream closed before {want!r} arrived")
            line = line.decode("utf-8").rstrip("\n")
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: ") and event == want:
                return json.loads(line[len("data: "):])

    def test_stream_backlog_status_and_live_relay(self):
        # Events recorded BEFORE the browser connects arrive as backlog…
        self.log.record({"event": "journal", "text": "before connect"})
        conn, resp = self.get("/stream")
        try:
            backlog = self.read_sse(resp, "backlog")
            self.assertIn("before connect",
                          [e.get("text") for e in backlog])
            status = self.read_sse(resp, "status")
            self.assertEqual(status["current_node"], self.runtime.current)
            self.assertIn("guard_edges", status)
            # …and events recorded after arrive live.
            self.log.record({"event": "journal", "text": "live line"})
            ev = self.read_sse(resp, "ev")
            self.assertEqual(ev["text"], "live line")
        finally:
            conn.close()

    def test_slow_client_never_blocks_recording(self):
        # A connected-but-unread stream (backgrounded tab) fills its
        # queue; record() must stay drop-oldest, never block or raise.
        conn, resp = self.get("/stream")
        try:
            self.read_sse(resp, "backlog")
            for i in range(1200):        # queue maxsize is 500
                self.log.record({"event": "journal", "text": f"flood {i}"})
        finally:
            conn.close()


class TestObserverContract(unittest.TestCase):
    def test_raising_observer_never_propagates(self):
        log = EventLog()
        seen = []
        log.observers.append(lambda ev: 1 / 0)
        log.observers.append(seen.append)
        ev = log.record({"event": "journal", "text": "still recorded"})
        self.assertEqual(ev["text"], "still recorded")
        self.assertEqual(len(seen), 1, "later observers still run")


if __name__ == "__main__":
    unittest.main()
