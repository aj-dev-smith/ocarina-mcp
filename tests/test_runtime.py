import shutil
import tempfile
import time
import unittest
from pathlib import Path

from ocarina.events import EventLog
from ocarina.game import Game
from ocarina.runtime import MachineRuntime

from .stubgame import StubLink, baba_actor

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "save-file"


class RuntimeCase(unittest.TestCase):
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
        diags = self.runtime.load()
        assert not [d for d in diags if d["level"] == "error"], diags

    def tearDown(self):
        self.runtime.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def tick_until(self, cond, seconds=2.0, msg="condition"):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.runtime.tick()
            if cond():
                return
            time.sleep(0.01)
        raise AssertionError(f"never reached: {msg}")

    def events(self, category=None):
        return self.log.tail(n=0, category=category)


class TestAutopilot(RuntimeCase):
    def test_load_enters_initial_chain(self):
        self.assertEqual(self.runtime.current, "navigate_field")
        entered = [e["node"] for e in self.events("entered")]
        self.assertEqual(entered, ["explore", "navigate_field"])

    def test_behavior_runs_and_loops(self):
        self.tick_until(lambda: self.runtime.executor.active_behavior == "walk_about_v1",
                        msg="behavior started")
        self.tick_until(lambda: self.events("behavior_done"), msg="behavior_done")
        done = self.events("behavior_done")[0]
        self.assertEqual(done["outcome"], "success")
        # keep-going loops the leaf: a fresh run starts.
        self.tick_until(lambda: len(self.events("behavior_done")) >= 2,
                        msg="second run (the explicit loop)")


class TestWhenTransitions(RuntimeCase):
    def test_when_fires_on_edge_and_preempts(self):
        # Sighting a novel kind now wakes the mind (novel-actor); this
        # test is about the when-edge, so the kind is already familiar.
        self.runtime.seen.sight("deku_baba")
        self.tick_until(lambda: self.runtime.executor.active_behavior == "walk_about_v1",
                        msg="walking")
        self.link.world["actors"] = [baba_actor(dist_xz=300.0)]
        self.tick_until(lambda: self.runtime.current == "kill_baba",
                        msg="baba-in-reach fired")
        # The walking body was preempted at the boundary and journaled as such.
        self.tick_until(lambda: self.events("behavior_aborted"), msg="behavior_aborted")
        aborted = self.events("behavior_aborted")[0]
        self.assertEqual(aborted["behavior"], "walk_about_v1")
        self.assertIn("baba-in-reach", aborted["reason"])

    def test_kill_loop_success_path(self):
        self.runtime.seen.sight("deku_baba")     # familiar kind: no novel wake
        self.link.world["actors"] = [baba_actor()]
        self.tick_until(lambda: self.runtime.current == "kill_baba", msg="engaged")
        self.tick_until(lambda: self.runtime.executor.active_behavior == "kill_baba_v1",
                        msg="fighting")
        # The kill lands: wire event arrives while the body runs, then the
        # baba leaves the world before the body returns.
        self.link.push_wire({"type": "agent_event", "event": "enemy_defeat",
                             "id": 0x0055, "params": 0})
        self.link.world["actors"] = []
        self.tick_until(lambda: any(e["outcome"] == "success"
                                    for e in self.events("behavior_done")),
                        msg="kill judged success")
        self.tick_until(lambda: self.runtime.current == "navigate_field",
                        msg="baba-done goto")
        journal = [e for e in self.events("journal") if "baba down" in e["text"]]
        self.assertTrue(journal, "the journal action templated from the event")

    def test_when_hysteresis_needs_a_fresh_edge(self):
        # A dedicated one-leaf machine whose `when` self-loops, so the
        # transition never leaves scope: it must fire exactly once while
        # the condition HOLDS true, and again only after false-then-true.
        import textwrap
        (self.repo / "machine" / "machine.yaml").write_text(textwrap.dedent("""\
            version: 1
            initial: watch
            nodes:
              watch:
                behavior: watch_v1
                transitions:
                  - name: close
                    when: state.nearest_enemy.dist <= 800
                    do: goto watch
                  - name: done
                    on: behavior_done
                    do: goto watch
            """))
        (self.repo / "machine" / "behaviors" / "watch.py").write_text(textwrap.dedent("""\
            from ocarina.behavior import Behavior
            BEHAVIORS = {"watch_v1": Behavior(
                name="watch", version=1, description="wait, not poll",
                body=lambda game, ctx: game.wait(30.0),
                success=lambda game, initial, events: True, timeout_s=60.0)}
            """))
        self.assertTrue(self.runtime.reload()["ok"])

        def fires():
            return [e for e in self.events("entered")
                    if "transition close" in e.get("reason", "")]

        self.link.world["actors"] = [baba_actor(dist_xz=300.0)]
        self.tick_until(lambda: fires(), seconds=3.0, msg="first edge fires")
        for _ in range(8):                    # condition still true: no refire
            time.sleep(0.02)
            self.runtime.tick()
        self.assertEqual(len(fires()), 1, "held-true condition refired")

        self.link.world["actors"] = [baba_actor(dist_xz=900.0)]
        self.tick_until(lambda: True, seconds=0.3, msg="")   # let a sweep see false
        for _ in range(8):
            time.sleep(0.02)
            self.runtime.tick()
        self.link.world["actors"] = [baba_actor(dist_xz=300.0)]
        self.tick_until(lambda: len(fires()) >= 2, seconds=3.0,
                        msg="fresh false->true edge fires again")


class TestWakes(RuntimeCase):
    def hurt(self):
        self.link.world["health"] = 40
        self.link.push_wire({"type": "agent_event", "event": "health_change",
                             "amount": -8, "health": 40})

    def test_wake_freezes_and_pushes(self):
        self.tick_until(lambda: self.runtime.executor.active_behavior, msg="walking")
        self.hurt()
        self.tick_until(lambda: self.packs, msg="wake pack pushed")
        pack = self.packs[0]
        self.assertEqual(pack["transition"], "health-drop")
        self.assertTrue(pack["frozen"])
        self.assertTrue(self.link.paused, "the game is actually frozen")
        self.assertEqual(pack["state"]["hearts"], 2.5)
        self.assertTrue(pack["events"], "the pack carries the event tail")
        self.assertTrue(self.runtime.status()["frozen"])

    def test_resume_unfreezes_and_restarts_autopilot(self):
        self.hurt()
        self.tick_until(lambda: self.packs, msg="wake")
        result = self.runtime.resume()
        self.assertTrue(result["ok"])
        self.assertFalse(self.link.paused)
        self.tick_until(lambda: self.runtime.executor.active_behavior,
                        msg="autopilot restarted")

    def test_wake_deadline_takes_default(self):
        self.runtime.wake_deadline_s = 0.01
        self.hurt()
        self.tick_until(lambda: self.packs, msg="wake")
        time.sleep(0.05)
        self.tick_until(lambda: not self.runtime.status()["frozen"],
                        msg="deadline default applied")
        self.assertFalse(self.link.paused)
        texts = [e["text"] for e in self.events("diagnostic")]
        self.assertTrue(any("taking default" in t for t in texts))

    def test_wake_cooldown_consumed(self):
        self.runtime.wake_deadline_s = 0.01
        self.hurt()
        self.tick_until(lambda: self.packs, msg="first wake")
        time.sleep(0.05)
        self.tick_until(lambda: not self.runtime.status()["frozen"], msg="resumed")
        self.hurt()   # within health-drop's 5s cooldown
        for _ in range(5):
            self.runtime.tick()
        self.assertEqual(len(self.packs), 1, "cooldown consumed at match time")

    def test_novel_actor_wake_once_per_kind(self):
        # Spawn narration is census-driven now (docs/22): an actor IN the
        # room but unsighted narrates nothing; sighting it wakes.
        lurker = baba_actor(actor_id=0x0037, key=201, sighted=False)
        self.link.world["actors"] = [lurker]
        for _ in range(5):
            self.runtime.tick()
            time.sleep(0.01)
        self.assertFalse(self.packs, "unsighted actor must not narrate")
        self.link.world["actors"] = [dict(lurker, sighted=True)]
        self.tick_until(lambda: self.packs, msg="novel wake on sighting")
        self.assertEqual(self.packs[0]["transition"], "novel-actor")
        self.runtime.resume()
        # A second individual of a now-familiar kind: spawn, not novel.
        self.link.world["actors"] = [baba_actor(actor_id=0x0037, key=202)]
        for _ in range(5):
            self.runtime.tick()
            time.sleep(0.01)
        self.assertEqual(len(self.packs), 1, "second sighting is not novel")


class TestReload(RuntimeCase):
    def test_reload_carries_node_by_name(self):
        yaml_path = self.repo / "machine" / "machine.yaml"
        yaml_path.write_text(yaml_path.read_text().replace(
            "cooldown_s: 30", "cooldown_s: 60"))
        old_hash = self.runtime.machine.source_hash
        result = self.runtime.reload()
        self.assertTrue(result["ok"])
        self.assertNotEqual(result["hash"], old_hash)
        self.assertEqual(result["current"], "navigate_field")

    def test_reload_refuses_broken_machine_and_keeps_old(self):
        yaml_path = self.repo / "machine" / "machine.yaml"
        yaml_path.write_text(yaml_path.read_text().replace(
            "do: goto kill_baba", "do: goto nowhere"))
        old = self.runtime.machine
        result = self.runtime.reload()
        self.assertFalse(result["ok"])
        self.assertIs(self.runtime.machine, old, "old machine untouched")
        self.assertTrue(any("nowhere" in d["msg"]
                            for d in result["diagnostics"]))

    def test_force_state_unknown_node(self):
        result = self.runtime.force_state("gohma_lair")
        self.assertFalse(result["ok"])
        self.assertIn("unknown node", result["error"])


if __name__ == "__main__":
    unittest.main()
