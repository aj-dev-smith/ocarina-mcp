"""End-to-end smoke: the REAL server process over REAL pipes and sockets.

Everything else in this suite is in-process; a green suite there says
nothing about the stdio transport, the argparse wiring, or the Sail TCP
listener (docs/08: distrust a clean green until the plumbing itself has
been exercised). This boots `python -m ocarina` as a subprocess, drives
the MCP handshake over its stdin/stdout, and connects the ported fakegame
over TCP — the same three processes a real session has.
"""

import base64
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "save-file"
REPO_ROOT = Path(__file__).parent.parent


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class StdioCase(unittest.TestCase):
    """The three-process rig: a real `python -m ocarina` subprocess, a
    real MCP conversation over its pipes, and the ported fakegame ready
    to dial in over TCP. Subclasses add `EXTRA_ARGS` (the dev harness
    boots the same rig with `--dev-tools`) — one copy of the plumbing,
    so a transport fix can never fix only half the tests."""

    #: Extra argv for the server under test.
    EXTRA_ARGS: tuple = ()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = Path(self.tmp) / "save-file"
        shutil.copytree(FIXTURE_REPO, self.repo)
        # The fakegame's baba is in view from the first snapshot; without
        # this, sighting it fires the fixture machine's novel-actor wake
        # and freezes the world before autopilot ever runs (correct
        # behavior, but this test is the plumbing smoke, not the wake
        # test). Pre-mark the kind as seen this save file.
        seen = self.repo / ".ocarina" / "seen_kinds.json"
        seen.parent.mkdir(parents=True, exist_ok=True)
        seen.write_text('["deku_baba"]')
        self.port = free_port()
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "ocarina", "--repo", str(self.repo),
             "--port", str(self.port), *self.EXTRA_ARGS],
            cwd=REPO_ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1)
        # Responses are matched by id and kept in a dict, not a queue: as
        # of 0.10.0 a blocked resume() is answered out of order, and a
        # queue reader that drops non-matching messages would eat it.
        self.responses: dict = {}
        self.arrived = threading.Condition()
        threading.Thread(target=self._reader, daemon=True).start()
        self.next_id = 0
        self.fake = None

    def tearDown(self):
        if self.fake is not None:
            self.fake.running = False
        self.proc.stdin.close()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _reader(self):
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line)
            if msg.get("id") is None:
                continue                      # a notification (the channel push)
            with self.arrived:
                self.responses[msg["id"]] = msg
                self.arrived.notify_all()

    def send(self, method, params=None) -> int:
        self.next_id += 1
        self.proc.stdin.write(json.dumps(
            {"jsonrpc": "2.0", "id": self.next_id, "method": method,
             "params": params or {}}) + "\n")
        return self.next_id

    def wait_for(self, msg_id, timeout=10.0):
        deadline = time.monotonic() + timeout
        with self.arrived:
            while msg_id not in self.responses:
                if not self.arrived.wait(max(deadline - time.monotonic(), 0.0)):
                    raise AssertionError(f"no response to request {msg_id}")
            msg = self.responses.pop(msg_id)
        self.assertNotIn("error", msg, msg)
        return msg["result"]

    def rpc(self, method, params=None, timeout=10.0):
        return self.wait_for(self.send(method, params), timeout)

    def call_tool(self, name, arguments=None):
        result = self.rpc("tools/call", {"name": name,
                                         "arguments": arguments or {}})
        return json.loads(result["content"][0]["text"])

    def start_fake(self, timeout=10.0):
        """Dial the fakegame in over real TCP, like SoH does, and block
        until the server says it is connected."""
        from .fakegame import FakeGame
        self.fake = FakeGame(port=self.port)
        threading.Thread(target=self.fake.run, daemon=True).start()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.call_tool("status")["game_connected"]:
                return self.fake
            time.sleep(0.2)
        raise AssertionError("the fakegame never connected")

    def journal(self):
        path = self.repo / "journal" / "mechanical.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()]


class TestStdioSmoke(StdioCase):
    def test_full_stack(self):
        # 1. MCP handshake over the real pipes.
        init = self.rpc("initialize", {"protocolVersion": "2025-06-18"})
        self.assertEqual(init["serverInfo"]["name"], "ocarina")
        self.assertIn("claude/channel", init["capabilities"]["experimental"])

        # 2. The machine rehydrated from the repo before any game exists.
        status = self.call_tool("status")
        self.assertTrue(status["machine_loaded"])
        self.assertEqual(status["current_node"], "navigate_field")
        self.assertFalse(status["game_connected"])

        # 3. The fakegame dials in over real TCP, like SoH does.
        self.start_fake()
        self.assertTrue(self.call_tool("status")["game_connected"])

        # 4. The sensorium reads the live world through the wire. The
        #    enemy fields are sight-gated: the baba enters the digest only
        #    after the runtime's next sightings fold, so allow it a tick.
        deadline = time.monotonic() + 5
        digest = {}
        while time.monotonic() < deadline and "nearest_enemy" not in digest:
            result = self.rpc("resources/read", {"uri": "oot://state"})
            digest = json.loads(result["contents"][0]["text"])
            time.sleep(0.1)
        self.assertEqual(digest["hearts"], 3.0)
        self.assertEqual(digest["nearest_enemy"]["kind"], "deku_baba")

        # 4b. A staged main-thread op over the real pipes: equip polls the
        #     instrument through its try_again round and then verifies the
        #     worn mask off the wire (docs/28).
        equipped = self.call_tool("equip", {"item": "hylian_shield"})
        self.assertTrue(equipped["ok"], equipped)
        self.assertEqual(equipped["worn"]["shield"], "hylian_shield")
        self.assertEqual(self.fake.worn, 0x21)

        # 4c. The screenshot sense end to end: raw RGBA8 over the TCP wire,
        #     PNG'd server-side, handed back as a real MCP image block. The
        #     fake's native window is 8x6 and the default cap is 640, so
        #     this one comes back native and claims no downscale.
        result = self.rpc("tools/call",
                          {"name": "screenshot", "arguments": {"max_width": 4}})
        self.assertFalse(result["isError"], result)
        image, note = result["content"]
        self.assertEqual(image["mimeType"], "image/png")
        png = base64.b64decode(image["data"])
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        body = json.loads(note["text"])
        self.assertEqual((body["width"], body["height"]), (4, 3))
        self.assertEqual(body["downscaled_from"], "8x6")

        # 5. Autopilot: the fixture behavior runs against the fake at 20 Hz
        #    and the loop transition keeps it running.
        deadline = time.monotonic() + 10
        saw_behavior = False
        while time.monotonic() < deadline and not saw_behavior:
            status = self.call_tool("status")
            saw_behavior = status["behavior_running"] is not None
            time.sleep(0.1)
        self.assertTrue(saw_behavior, "no behavior ever ran end-to-end")

        # 5b. The blocking wake over the real pipes (0.10.0): resume()
        #     blocks, other requests are still served while it does, and
        #     the wake pack comes back as that call's own result.
        resume_id = self.send("tools/call",
                              {"name": "resume",
                               "arguments": {"max_block_s": 20}})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.call_tool("status")["listener_blocked"]:
                break
            time.sleep(0.1)
        self.assertTrue(self.call_tool("status")["listener_blocked"],
                        "resume() did not block")
        with self.fake.lock:
            self.fake.player["health"] = 40
            self.fake.pending_events.append(
                {"type": "agent_event", "event": "health_change",
                 "amount": -8, "health": 40})
        result = self.wait_for(resume_id, timeout=20)
        pack = json.loads(result["content"][0]["text"])
        self.assertEqual(pack["transition"], "health-drop")
        self.assertTrue(pack["frozen"], "the game froze before delivery")
        self.assertEqual(pack["state"]["hearts"], 2.5)
        self.assertIn("interval", pack)
        self.assertTrue(self.call_tool("status")["wake_delivered"])

        # 6. The mechanical journal persisted into the save-file repo.
        events = self.journal()
        self.assertTrue(any(e["event"] == "entered" for e in events))
        # …and carries no dev mark: this server ran the default surface.
        self.assertFalse([e for e in events
                          if e["event"] in ("dev_mode", "dev_cheat")])
        self.assertNotIn("dev_mode", self.call_tool("status"))


if __name__ == "__main__":
    unittest.main()
