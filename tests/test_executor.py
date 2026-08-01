import time
import unittest

from ocarina.behavior import Behavior, BehaviorAbort
from ocarina.executor import BehaviorExecutor
from ocarina.game import Game

from .stubgame import StubLink


def make(body, success=lambda g, i, e: True, timeout_s=5.0):
    return Behavior(name="t", version=1, description="test", body=body,
                    success=success, timeout_s=timeout_s)


def finish_within(executor, seconds=2.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        run = executor.finish()
        if run is not None:
            return run
        time.sleep(0.01)
    raise AssertionError("behavior never finished")


class TestExecutor(unittest.TestCase):
    def setUp(self):
        self.link = StubLink()
        self.game = Game(self.link)
        self.executor = BehaviorExecutor(self.game)

    def test_success(self):
        self.assertTrue(self.executor.start(make(lambda g, c: g.state() and None)))
        run = finish_within(self.executor)
        self.assertEqual(run.outcome, "success")
        self.assertFalse(self.executor.collecting)

    def test_success_predicate_reads_events(self):
        def needs_kill(game, initial, events):
            return any(e.get("event") == "enemy_defeat" for e in events)
        self.executor.start(make(lambda g, c: g.wait(0.05), success=needs_kill))
        self.executor.note_event({"event": "enemy_defeat", "id": 0x55})
        run = finish_within(self.executor)
        self.assertEqual(run.outcome, "success")
        # And without the event it is a failure, not a success.
        self.executor.start(make(lambda g, c: None, success=needs_kill))
        self.assertEqual(finish_within(self.executor).outcome, "failure")

    def test_abort(self):
        def body(game, ctx):
            raise BehaviorAbort("bad vibes")
        run = self.executor.start(make(body)) and finish_within(self.executor)
        self.assertEqual(run.outcome, "abort")
        self.assertEqual(run.detail, "bad vibes")

    def test_timeout(self):
        self.executor.start(make(lambda g, c: g.wait(0.1), timeout_s=0.01))
        run = finish_within(self.executor)
        self.assertEqual(run.outcome, "timeout")

    def test_error(self):
        def body(game, ctx):
            raise RuntimeError("boom")
        self.executor.start(make(body))
        run = finish_within(self.executor)
        self.assertEqual(run.outcome, "error")
        self.assertIn("boom", run.detail)

    def test_preempt_mid_body(self):
        def body(game, ctx):
            while True:            # a real 20 Hz body: touches the game each tick
                game.state()
                game.wait(0.01)
        self.executor.start(make(body))
        time.sleep(0.05)
        self.assertTrue(self.executor.busy)
        self.assertTrue(self.executor.preempt("transition nightfall-reflex"))
        run = finish_within(self.executor)
        self.assertEqual(run.outcome, "preempted")
        self.assertEqual(run.preempted_by, "transition nightfall-reflex")

    def test_preempt_interrupts_wait(self):
        # A body sleeping out a long animation still notices within ~a tick.
        def body(game, ctx):
            game.wait(30.0)
        self.executor.start(make(body))
        time.sleep(0.02)
        started = time.monotonic()
        self.executor.preempt("reload")
        run = finish_within(self.executor)
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(run.outcome, "preempted")

    def test_busy_refuses_second_start(self):
        self.executor.start(make(lambda g, c: g.wait(0.2)))
        self.assertFalse(self.executor.start(make(lambda g, c: None)))
        self.executor.preempt("test over")
        finish_within(self.executor)


if __name__ == "__main__":
    unittest.main()
