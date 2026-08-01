"""End-to-end smoke: the REAL server process over REAL pipes and sockets.

Everything else in this suite is in-process; a green suite there says
nothing about the stdio transport, the argparse wiring, or the Sail TCP
listener (docs/08: distrust a clean green until the plumbing itself has
been exercised). This boots `python -m ocarina` as a subprocess, drives
the MCP handshake over its stdin/stdout, and connects the ported fakegame
over TCP — the same three processes a real session has.
"""

import json
import queue
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


class TestStdioSmoke(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = Path(self.tmp) / "save-file"
        shutil.copytree(FIXTURE_REPO, self.repo)
        self.port = free_port()
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "ocarina", "--repo", str(self.repo),
             "--port", str(self.port)],
            cwd=REPO_ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1)
        self.inbox: queue.Queue = queue.Queue()
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
            if line:
                self.inbox.put(json.loads(line))

    def rpc(self, method, params=None, timeout=10.0):
        self.next_id += 1
        msg_id = self.next_id
        self.proc.stdin.write(json.dumps(
            {"jsonrpc": "2.0", "id": msg_id, "method": method,
             "params": params or {}}) + "\n")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                msg = self.inbox.get(timeout=deadline - time.monotonic())
            except queue.Empty:
                break
            if msg.get("id") == msg_id:
                self.assertNotIn("error", msg, msg)
                return msg["result"]
            # a notification or stale message; keep looking
        raise AssertionError(f"no response to {method}")

    def call_tool(self, name, arguments=None):
        result = self.rpc("tools/call", {"name": name,
                                         "arguments": arguments or {}})
        return json.loads(result["content"][0]["text"])

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
        from .fakegame import FakeGame
        self.fake = FakeGame(port=self.port)
        threading.Thread(target=self.fake.run, daemon=True).start()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status = self.call_tool("status")
            if status["game_connected"]:
                break
            time.sleep(0.2)
        self.assertTrue(status["game_connected"])

        # 4. The sensorium reads the live world through the wire.
        result = self.rpc("resources/read", {"uri": "oot://state"})
        digest = json.loads(result["contents"][0]["text"])
        self.assertEqual(digest["hearts"], 3.0)
        self.assertEqual(digest["nearest_enemy"]["kind"], "deku_baba")

        # 5. Autopilot: the fixture behavior runs against the fake at 20 Hz
        #    and the loop transition keeps it running.
        deadline = time.monotonic() + 10
        saw_behavior = False
        while time.monotonic() < deadline and not saw_behavior:
            status = self.call_tool("status")
            saw_behavior = status["behavior_running"] is not None
            time.sleep(0.1)
        self.assertTrue(saw_behavior, "no behavior ever ran end-to-end")

        # 6. The mechanical journal persisted into the save-file repo.
        journal = self.repo / "journal" / "mechanical.jsonl"
        self.assertTrue(journal.exists())
        events = [json.loads(l) for l in journal.read_text().splitlines()]
        self.assertTrue(any(e["event"] == "entered" for e in events))


if __name__ == "__main__":
    unittest.main()
