"""Plumbing for the live e2e tests: a real server, a real game, a
throwaway repo — and a skip path that is instant and loud.

The live family exists because of the dev harness (0.12.0, dojo
docs/33): with `dev_warp` and `dev_teleport` a test can put Link at a
chosen place in the real world in seconds, which is what turns "we found
that bug on the sixth flight" into "that bug has a pin". Everything here
is the boring half of that: spawn `python -m ocarina --dev-tools`
against a temp repo, speak MCP over its pipes, and get out of the way.

**Skips, never failures.** These tests need hardware nobody's CI has: a
running Shipwright with Sail enabled, dialling in on port 43384. Three
gates, cheapest first:

1. `OCARINA_LIVE` is not set — skip instantly. This is what keeps the
   default `unittest discover` run green and fast; the live family is
   opt-in by construction, exactly as the real-o2r place-sense pins are.
2. The Sail port is already bound — some other ocarina (a flight in
   progress!) owns the game. Skip, loudly, and touch nothing.
3. No game dials in inside `CONNECT_TIMEOUT_S` — SoH isn't running. Skip.

Never a failure, because none of those says anything about the code
under test. A real failure here means the game WAS there and the
harness verb did the wrong thing.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

from ocarina.protocol import DEFAULT_PORT

REPO_ROOT = Path(__file__).resolve().parents[2]

#: How long to wait for SoH to dial in before deciding it isn't running.
#: Sail retries on a short cycle, so a game that IS up connects almost
#: at once; this is generous, and it is only ever paid when someone
#: asked for live tests.
CONNECT_TIMEOUT_S = float(os.environ.get("OCARINA_LIVE_CONNECT_S", 20.0))

ENV_FLAG = "OCARINA_LIVE"

#: The Sail port SoH dials in on. Overridable only so the skip gates
#: themselves can be exercised (and so a second bench can run on a
#: different port); the real one is the default.
LIVE_PORT = int(os.environ.get("OCARINA_LIVE_PORT", DEFAULT_PORT))

#: Where SoH's oot.o2r usually lives on this bench. The live tests want
#: the place sense on, because "arrival verified by the map" is the
#: whole point of a dev-warp test (docs/33 acceptance criterion 3) —
#: and because the digest's exact self-pose rides `place.*`.
DEFAULT_O2R = Path("/Users/aj/Code/Shipwright/oot.o2r")


def o2r_path() -> Path | None:
    """The collision source to hand the server, or None (place sense
    off, loudly, and the pose-checking tests skip)."""
    declared = os.environ.get("OCARINA_O2R")
    if declared:
        path = Path(declared)
        return path if path.exists() else None
    return DEFAULT_O2R if DEFAULT_O2R.exists() else None


def require_live() -> None:
    """Gate 1: the opt-in. Raises SkipTest with instructions."""
    if os.environ.get(ENV_FLAG, "").strip() not in ("1", "true", "yes", "on"):
        raise unittest.SkipTest(
            f"live tests drive the REAL game: set {ENV_FLAG}=1 (with "
            f"Shipwright running, Sail enabled, and no other ocarina "
            f"server holding port {LIVE_PORT}) to run them")


def require_free_sail_port(port: int = LIVE_PORT) -> None:
    """Gate 2: nobody else owns the game. A bound port means a live
    session (or another test run) is attached — never fight it."""
    # A just-stopped LiveServer (the previous test class) can hold the
    # port for a beat while its process exits — that is a wait, not a
    # skip. Only a port still bound after the grace window means a real
    # foreign owner.
    deadline = time.monotonic() + 6.0
    while True:
        probe = socket.socket()
        try:
            probe.bind(("127.0.0.1", port))
            return
        except OSError as e:
            if time.monotonic() >= deadline:
                raise unittest.SkipTest(
                    f"Sail port {port} is already bound ({e}) — another "
                    f"ocarina server (a flight in progress?) holds the "
                    f"game; stop it before running live tests")
            time.sleep(0.25)
        finally:
            probe.close()


#: The throwaway repo's machine: ONE idle leaf whose body reads state
#: and waits. A live test drives the world through the dev verbs, so the
#: autopilot's whole job is to exist — it must never press a button or
#: move Link, or the assertions would be racing it.
MACHINE_YAML = """\
# tests/live: the idle machine (see harness.py). Touches nothing.
version: 1
initial: stand_watch

nodes:
  stand_watch:
    behavior: stand_watch_v1
    transitions:
      - name: keep-standing
        on: behavior_done
        do: goto stand_watch
"""

IDLE_BEHAVIOR = '''\
"""tests/live: the idle body. Reads the world, presses nothing."""

from ocarina.behavior import Behavior


def _stand(game, ctx):
    game.state()
    game.wait(0.5)


BEHAVIORS = {
    "stand_watch_v1": Behavior(
        name="stand_watch", version=1,
        description="live-harness idle: observe, touch nothing",
        body=_stand, success=lambda game, initial, events: True,
        timeout_s=5.0,
        grade="harness fixture; never graded, never presses a button"),
}
'''


def make_repo(root: Path) -> Path:
    """Build a throwaway save-file repo under `root` and return it.

    It declares NO identity.json on purpose: a dev repo declaring
    nothing runs with the boot check off and one loud diagnostic (the
    ratified no-declaration path), and it can never be mistaken for a
    scored line — which is the repo the flag refuses.
    """
    repo = Path(root) / "live-repo"
    (repo / "machine" / "behaviors").mkdir(parents=True, exist_ok=True)
    (repo / "machine" / "machine.yaml").write_text(MACHINE_YAML)
    (repo / "machine" / "behaviors" / "idle.py").write_text(IDLE_BEHAVIOR)
    return repo


class LiveServer:
    """A real `python -m ocarina --dev-tools` subprocess, spoken to over
    its stdio pipes. Same plumbing as the stdio smoke test (responses
    matched by id, because a blocked wake verb answers out of order)."""

    def __init__(self, repo: Path, port: int = LIVE_PORT,
                 extra_args: tuple | None = None):
        self.repo = Path(repo)
        self.port = port
        if extra_args is None:
            o2r = o2r_path()
            extra_args = ("--o2r", str(o2r)) if o2r else ()
        self.extra_args = tuple(extra_args)
        self.proc: subprocess.Popen | None = None
        self.responses: dict = {}
        self.arrived = threading.Condition()
        self.next_id = 0

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> "LiveServer":
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "ocarina", "--repo", str(self.repo),
             "--port", str(self.port), "--dev-tools", *self.extra_args],
            cwd=REPO_ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1)
        threading.Thread(target=self._reader, daemon=True).start()
        time.sleep(0.3)
        if self.proc.poll() is not None:
            raise unittest.SkipTest(
                f"the server exited at once (rc={self.proc.returncode}): "
                f"{(self.proc.stderr.read() or '').strip()}")
        self.rpc("initialize", {"protocolVersion": "2025-06-18"})
        return self

    def stop(self) -> None:
        if self.proc is None:
            return
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    # -- MCP ---------------------------------------------------------------

    def _reader(self) -> None:
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("id") is None:
                continue                       # a notification
            with self.arrived:
                self.responses[msg["id"]] = msg
                self.arrived.notify_all()

    def send(self, method: str, params=None) -> int:
        self.next_id += 1
        self.proc.stdin.write(json.dumps(
            {"jsonrpc": "2.0", "id": self.next_id, "method": method,
             "params": params or {}}) + "\n")
        return self.next_id

    def rpc(self, method: str, params=None, timeout: float = 30.0) -> dict:
        msg_id = self.send(method, params)
        deadline = time.monotonic() + timeout
        with self.arrived:
            while msg_id not in self.responses:
                if not self.arrived.wait(max(deadline - time.monotonic(), 0.0)):
                    raise AssertionError(f"no response to {method} in {timeout}s")
            msg = self.responses.pop(msg_id)
        if "error" in msg:
            raise AssertionError(f"{method} failed: {msg['error']}")
        return msg["result"]

    def call(self, name: str, arguments=None, timeout: float = 60.0) -> dict:
        """A tool call that must succeed; returns its JSON body."""
        result = self.rpc("tools/call",
                          {"name": name, "arguments": arguments or {}},
                          timeout=timeout)
        text = result["content"][0]["text"]
        if result.get("isError"):
            raise AssertionError(f"{name} refused: {text}")
        return json.loads(text)

    def call_raw(self, name: str, arguments=None, timeout: float = 60.0) -> dict:
        """A tool call that may refuse; returns the raw MCP result."""
        return self.rpc("tools/call",
                        {"name": name, "arguments": arguments or {}},
                        timeout=timeout)

    def read(self, uri: str) -> dict:
        result = self.rpc("resources/read", {"uri": uri})
        return json.loads(result["contents"][0]["text"])

    # -- the world ---------------------------------------------------------

    def await_game(self, timeout: float = CONNECT_TIMEOUT_S) -> dict:
        """Gate 3: wait for SoH to dial in. Skips if it never does."""
        deadline = time.monotonic() + timeout
        status = {}
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise unittest.SkipTest(
                    f"the server exited while waiting for the game "
                    f"(rc={self.proc.returncode})")
            status = self.call("status")
            if status.get("game_connected"):
                return status
            time.sleep(0.5)
        raise unittest.SkipTest(
            f"no game connected on port {self.port} within {timeout:.0f}s — "
            f"launch Shipwright (Sail enabled) and load a save file, then "
            f"re-run with {ENV_FLAG}=1")

    def state(self) -> dict:
        """The curated digest — what the world says it is, which is the
        only thing a live assertion may trust (never the op's claim)."""
        return self.read("oot://state")

    def journal(self) -> list:
        path = self.repo / "journal" / "mechanical.jsonl"
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out
