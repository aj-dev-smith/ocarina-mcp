"""The blocking wake (0.10.0, dojo docs/31).

`resume()` unfreezes and BLOCKS until the next wake, which is its own
result; `await_wake()` listens without resuming. These tests run the
20 Hz loop on its own thread — the point of the feature is that the
world moves while a call is blocked, which a single-threaded tick loop
cannot exercise at all.
"""

import json
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from ocarina.events import EventLog
from ocarina.game import Game
from ocarina.runtime import MachineRuntime
from ocarina.server import ServerCore

from .stubgame import StubLink, baba_actor

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "save-file"


class BlockingCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = Path(self.tmp) / "save-file"
        shutil.copytree(FIXTURE_REPO, self.repo)
        self.link = StubLink()
        self.game = Game(self.link)
        self.log = EventLog(persist_path=self.repo / "journal" / "mechanical.jsonl")
        self.packs = []
        self.runtime = MachineRuntime(
            self.game, self.repo, self.log,
            wake_push=self.packs.append, wake_deadline_s=60.0)
        self.runtime.seen.sight("deku_baba")   # familiar: no novel wake
        diags = self.runtime.load()
        assert not [d for d in diags if d["level"] == "error"], diags
        self.tick_errors = []
        self._ticking = True
        self.ticker = threading.Thread(target=self._tick_loop, daemon=True)
        self.ticker.start()

    def tearDown(self):
        self._ticking = False
        self.ticker.join(timeout=5)
        self.runtime.stop()
        self.assertEqual(self.tick_errors, [])
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _tick_loop(self):
        while self._ticking:
            try:
                self.runtime.tick()
            except Exception as e:            # a dead loop must not read as a pass
                self.tick_errors.append(repr(e))
            time.sleep(0.01)

    # -- helpers -------------------------------------------------------------

    def hurt(self):
        """A half-heart bite: fires the fixture's health-drop wake."""
        self.link.world["health"] = 40
        self.link.push_wire({"type": "agent_event", "event": "health_change",
                             "amount": -8, "health": 40})

    def blocked(self, call):
        """Run a blocking verb on its own thread; returns (thread, out)
        where out is a one-slot list holding the result."""
        out = []
        thread = threading.Thread(target=lambda: out.append(call()), daemon=True)
        thread.start()
        self.until(lambda: self.runtime.status()["listener_blocked"],
                   "the call blocked")
        return thread, out

    def until(self, cond, msg, seconds=5.0):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if cond():
                return
            time.sleep(0.01)
        raise AssertionError(f"never reached: {msg}")


class TestBlockingResume(BlockingCase):
    def test_resume_blocks_and_returns_the_wake_pack(self):
        thread, out = self.blocked(lambda: self.runtime.resume_and_block())
        self.assertFalse(self.link.paused, "the world runs while we listen")
        self.hurt()
        thread.join(timeout=5)
        self.assertTrue(out, "the blocked resume never returned")
        pack = out[0]
        self.assertEqual(pack["transition"], "health-drop")
        self.assertEqual(pack["state"]["hearts"], 2.5)
        self.assertTrue(pack["frozen"])
        self.assertTrue(self.link.paused, "the game froze for the wake")
        status = self.runtime.status()
        self.assertTrue(status["wake_delivered"])
        self.assertFalse(status["listener_blocked"])

    def test_max_block_s_returns_no_wake_with_the_world_running(self):
        result = self.runtime.resume_and_block(max_block_s=0.05)
        self.assertTrue(result["no_wake"])
        self.assertGreaterEqual(result["elapsed_s"], 0.0)
        self.assertIn("await_wake()", result["note"])
        self.assertFalse(self.link.paused)
        self.until(lambda: self.runtime.executor.active_behavior is not None,
                   "the machine kept playing after the cap")
        self.assertFalse(self.runtime.status()["listener_blocked"])

    def test_heartbeat_override_still_stores(self):
        self.runtime.resume_and_block(max_sleep=12.0, max_block_s=0.01)
        self.assertEqual(self.runtime.heartbeat_s, 12.0)


class TestAwaitWake(BlockingCase):
    def parked_wake(self):
        """Fire a wake with nobody listening: it parks frozen, its
        default armed (the crash-recovery path)."""
        self.hurt()
        self.until(lambda: self.packs, "the wake parked")
        self.assertTrue(self.link.paused)
        self.assertFalse(self.runtime.status()["wake_delivered"])

    def test_parked_wake_comes_back_at_once(self):
        self.parked_wake()
        started = time.monotonic()
        pack = self.runtime.await_wake(max_block_s=5.0)
        self.assertLess(time.monotonic() - started, 1.0, "it blocked instead")
        self.assertEqual(pack["transition"], "health-drop")
        self.assertTrue(self.runtime.status()["wake_delivered"])
        self.assertTrue(self.link.paused, "await_wake does not unfreeze")

    def test_await_wake_blocks_then_returns_without_resuming(self):
        node = self.runtime.current
        thread, out = self.blocked(lambda: self.runtime.await_wake())
        self.assertEqual(self.runtime.current, node, "no side effect")
        self.hurt()
        thread.join(timeout=5)
        self.assertEqual(out[0]["transition"], "health-drop")

    def test_unanswered_delivered_wake_is_a_loud_error(self):
        self.parked_wake()
        self.runtime.await_wake(max_block_s=1.0)     # now holding the ball
        result = self.runtime.await_wake(max_block_s=1.0)
        self.assertFalse(result["ok"])
        self.assertIn("holding the ball", result["error"])
        self.assertIn("health-drop", result["error"])

    def test_second_awaiter_is_refused_never_queued(self):
        thread, out = self.blocked(
            lambda: self.runtime.await_wake(max_block_s=2.0))
        for result in (self.runtime.await_wake(max_block_s=5.0),
                       self.runtime.resume_and_block(max_block_s=5.0)):
            self.assertFalse(result["ok"])
            self.assertIn("one awaiter at a time", result["error"])
        thread.join(timeout=5)
        self.assertTrue(out[0]["no_wake"])


class TestSeveredBlock(BlockingCase):
    def test_severed_block_plays_on_and_await_wake_recovers_the_wake(self):
        arms = []
        thread, out = self.blocked(
            lambda: self.runtime.resume_and_block(on_arm=arms.append))
        self.assertTrue(arms, "the awaiter was handed to the caller")

        self.runtime.cancel_awaiter(arms[0])
        thread.join(timeout=5)
        self.assertEqual(out, [None], "a severed block has no answer to write")

        # The machine IS the autopilot: it plays on (docs/31 ruling 2).
        self.until(lambda: self.runtime.executor.active_behavior is not None,
                   "the machine kept playing after the block was severed")
        self.assertFalse(self.link.paused)

        # The next wake parks frozen with its default armed — today's
        # machinery, demoted to crash recovery.
        self.hurt()
        self.until(lambda: self.packs, "the wake fired with nobody listening")
        status = self.runtime.status()
        self.assertTrue(status["frozen"])
        self.assertFalse(status["wake_delivered"])
        self.assertEqual(status["pending_wake"], "health-drop")

        pack = self.runtime.await_wake(max_block_s=1.0)
        self.assertEqual(pack["transition"], "health-drop")

    def test_a_wake_that_crosses_the_severance_stays_collectable(self):
        # The cancellation and the wake land together: nobody heard the
        # pack, so it must go back on the hook rather than count as
        # delivered (which would freeze the world behind a "holding the
        # ball" error nobody could answer).
        arms = []
        thread, out = self.blocked(
            lambda: self.runtime.resume_and_block(on_arm=arms.append))
        awaiter = arms[0]
        awaiter.severed = True          # cancelled, mid-delivery
        self.hurt()
        thread.join(timeout=5)
        self.assertEqual(out, [None])
        self.until(lambda: self.runtime.status()["frozen"], "the wake parked")
        self.assertFalse(self.runtime.status()["wake_delivered"])
        self.assertEqual(self.runtime.await_wake(max_block_s=1.0)["transition"],
                         "health-drop")


class TestIntervalInThePack(BlockingCase):
    def test_pack_carries_the_interval_and_it_resets_at_each_wake(self):
        self.until(lambda: self.runtime.executor.active_behavior is not None,
                   "autopilot running (so the interval has a baseline)")
        thread, out = self.blocked(lambda: self.runtime.resume_and_block())
        self.hurt()
        thread.join(timeout=5)
        first = out[0]["interval"]
        self.assertEqual(first["delta"]["hearts"], {"from": 3.0, "to": 2.5})
        self.assertIn({"event": "damage_taken", "count": 1}, first["events"])
        self.assertGreaterEqual(first["wall_s"], 0.0)
        self.assertIn("ticks", first)

        # A second wake, on a different transition (health-drop's cooldown
        # is still running): sighting a kind this save file has never seen.
        thread, out = self.blocked(lambda: self.runtime.resume_and_block())
        self.link.world["actors"] = [baba_actor(actor_id=0x0037, key=77)]
        thread.join(timeout=5)
        second = out[0]["interval"]
        self.assertEqual(out[0]["transition"], "novel-actor")
        tallied = {e["event"] for e in second.get("events", [])}
        self.assertNotIn("damage_taken", tallied, "the interval did not reset")
        self.assertEqual([f["kind"] for f in second["firsts"]], ["skulltula"])


class TestServerBlockingSurface(BlockingCase):
    """The same contract through the MCP surface, including the
    cancellation that severs a block."""

    def setUp(self):
        super().setUp()
        self.core = ServerCore(self.game, self.runtime, self.log)
        self.notifications = []
        self.core.notify = lambda method, params: self.notifications.append(
            (method, params))

    def call(self, name, arguments=None, msg_id=1):
        return self.core.handle({"jsonrpc": "2.0", "id": msg_id,
                                 "method": "tools/call",
                                 "params": {"name": name,
                                            "arguments": arguments or {}}})

    def body(self, response):
        return json.loads(response["result"]["content"][0]["text"])

    def test_await_wake_is_a_registered_tool_not_a_not_yet(self):
        from ocarina.server import NOT_YET, TOOLS
        self.assertIn("await_wake", {t["name"] for t in TOOLS})
        self.assertNotIn("await_wake", NOT_YET)

    def test_blocking_resume_returns_the_pack_and_status_answers_mid_block(self):
        out = []
        thread = threading.Thread(
            target=lambda: out.append(self.call("resume", msg_id=7)),
            daemon=True)
        thread.start()
        self.until(lambda: self.runtime.status()["listener_blocked"], "blocked")
        # The core still serves other verbs while one call is blocked.
        self.assertTrue(self.body(self.call("status", msg_id=8))["machine_loaded"])
        self.hurt()
        thread.join(timeout=5)
        pack = self.body(out[0])
        self.assertEqual(out[0]["id"], 7)
        self.assertEqual(pack["transition"], "health-drop")
        self.assertIn("interval", pack)
        # The channel push carries the same single-sourced pack.
        method, params = self.notifications[0]
        self.assertEqual(method, "notifications/claude/channel")
        self.assertIn("since the last wake:", params["content"])

    def test_cancellation_severs_the_block_and_writes_no_response(self):
        out = []
        thread = threading.Thread(
            target=lambda: out.append(self.call("await_wake", msg_id=11)),
            daemon=True)
        thread.start()
        self.until(lambda: self.runtime.status()["listener_blocked"], "blocked")
        self.assertIsNone(self.core.handle(
            {"jsonrpc": "2.0", "method": "notifications/cancelled",
             "params": {"requestId": 11, "reason": "user pressed Esc"}}))
        thread.join(timeout=5)
        self.assertEqual(out, [None], "a cancelled request gets no response")
        self.assertFalse(self.runtime.status()["listener_blocked"])
        # And the machine plays on, so the next wake parks for await_wake.
        self.hurt()
        self.until(lambda: self.runtime.status()["frozen"], "wake parked")
        self.assertEqual(self.body(self.call("await_wake"))["transition"],
                         "health-drop")

    def test_cancellation_arriving_before_the_arm_still_severs(self):
        self.core.handle({"jsonrpc": "2.0", "method": "notifications/cancelled",
                          "params": {"requestId": 12}})
        self.assertIsNone(self.call("await_wake", msg_id=12))

    def test_second_blocking_call_is_a_clean_tool_error(self):
        out = []
        thread = threading.Thread(
            target=lambda: out.append(
                self.call("await_wake", {"max_block_s": 2.0}, msg_id=21)),
            daemon=True)
        thread.start()
        self.until(lambda: self.runtime.status()["listener_blocked"], "blocked")
        busy = self.call("resume", {"max_block_s": 5.0}, msg_id=22)["result"]
        self.assertTrue(busy["isError"])
        self.assertIn("one awaiter at a time", busy["content"][0]["text"])
        thread.join(timeout=5)

    def test_sever_all_releases_a_blocked_call_when_the_client_goes(self):
        out = []
        thread = threading.Thread(
            target=lambda: out.append(self.call("resume", msg_id=31)),
            daemon=True)
        thread.start()
        self.until(lambda: self.runtime.status()["listener_blocked"], "blocked")
        self.core.sever_all()
        thread.join(timeout=5)
        self.assertEqual(out, [None])


if __name__ == "__main__":
    unittest.main()
