"""The debug overlay: labels must render the sensorium's beliefs — and
nothing else. The NEAREST marker in particular must sit on whatever actor
holds the digest's single nearest_enemy slot, because catching that slot
on the wrong actor (second light's ceiling-skulltula masking) is the
overlay's reason to exist; an overlay that disagreed with the digest
would be the debug instrument lying about the thing it checks."""

import shutil
import tempfile
import time
import unittest
from pathlib import Path

from ocarina import overlay, senses
from ocarina.protocol import ACTORCAT_ENEMY, ACTORCAT_PROP
from ocarina.senses import SeenKinds

from .stubgame import baba_actor
from .test_runtime import RuntimeCase


def enemy(key, actor_id=0x0055, dist=100.0, dist_y=0.0, health=2,
          cat=ACTORCAT_ENEMY, sighted=True):
    return {"id": actor_id, "cat": cat, "key": key, "dist_xz": dist,
            "dist_y": dist_y, "health": health, "sighted": sighted}


class LabelCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.seen = SeenKinds(Path(self.tmp) / "seen.json")
        self.sightings = senses.Sightings()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def labels(self, *actors):
        state = {"save_loaded": True, "scene": 85, "actors": list(actors)}
        self.sightings.observe(state)
        return overlay.labels(state, self.seen, self.sightings)

    def test_never_presented_actors_get_no_label(self):
        # A label on a thing AJ can't see would be the overlay committing
        # the exact leak it exists to catch.
        out = self.labels(enemy(1, actor_id=0x0000),   # Player
                          enemy(2, actor_id=0x011B),   # Elf_Msg trigger volume
                          enemy(3))
        self.assertEqual([l["key"] for l in out], [3])

    def test_actor_without_key_is_skipped(self):
        a = enemy(1)
        del a["key"]
        self.assertEqual(self.labels(a), [])

    def test_nearest_marker_sits_on_the_digest_slot_holder(self):
        # Second light's masking room: the ceiling skulltula is nearer in
        # xz but unsighted (the camera has never shown the shaft), so the
        # slot — and therefore the marker — belongs to the baba. The
        # skulltula keeps a label (the overlay renders beliefs, walls and
        # all), rendered grey `unsighted`: the acceptance visual from
        # docs/22.
        ceiling = enemy(1, actor_id=0x0095, dist=61.0, dist_y=-1073.0,
                        sighted=False)
        baba = enemy(2, dist=250.0)
        out = self.labels(ceiling, baba)
        marked = [l for l in out if "NEAREST_ENEMY" in l["text"]]
        self.assertEqual([l["key"] for l in marked], [2])
        self.assertEqual(marked[0]["color"], overlay.COLOR_NEAREST)
        by_key = {l["key"]: l for l in out}
        self.assertIn("unsighted", by_key[1]["text"])
        self.assertEqual(by_key[1]["color"], overlay.COLOR_UNSIGHTED)
        # Cross-check against the digest itself: same slot-holder.
        d = senses.digest({"actors": [ceiling, baba]}, self.sightings)
        self.assertEqual(d["nearest_enemy"]["kind"], "deku_baba")
        self.assertIn("deku_baba", marked[0]["text"])

    def test_sighted_actor_never_reads_unsighted(self):
        out = self.labels(enemy(1))
        self.assertNotIn("unsighted", out[0]["text"])
        self.assertNotEqual(out[0]["color"], overlay.COLOR_UNSIGHTED)

    def test_dead_enemy_never_holds_the_marker(self):
        dead_near = enemy(1, dist=10.0, health=0)
        live_far = enemy(2, dist=400.0)
        out = self.labels(dead_near, live_far)
        marked = [l for l in out if "NEAREST_ENEMY" in l["text"]]
        self.assertEqual([l["key"] for l in marked], [2])

    def test_prop_is_labeled_but_never_marked(self):
        chest = enemy(1, actor_id=0x000A, dist=5.0, cat=ACTORCAT_PROP)
        out = self.labels(chest)
        self.assertIn("treasure_chest", out[0]["text"])
        self.assertNotIn("NEAREST_ENEMY", out[0]["text"])

    def test_above_uses_the_digest_sign_convention(self):
        # dist_y is player.y - actor.y: NEGATIVE for an actor overhead.
        # Displayed quantized to 10s (label churn control), sign intact.
        out = self.labels(enemy(1, dist=61.0, dist_y=-1073.0))
        self.assertIn("above +1070", out[0]["text"])
        self.assertIn("dist 60", out[0]["text"])

    def test_unknown_id_flags_the_vocabulary_gap(self):
        out = self.labels(enemy(1, actor_id=0x0097, health=0))
        self.assertIn("unknown_0x0097", out[0]["text"])
        self.assertEqual(out[0]["color"], overlay.COLOR_UNKNOWN)

    def test_novelty_reads_without_consuming(self):
        out = self.labels(enemy(1))
        self.assertIn("*novel*", out[0]["text"])
        # The overlay must not claim the sighting: narration still gets
        # the novel=1 spawn later.
        self.assertFalse(self.seen.known("deku_baba"))
        self.seen.sight("deku_baba")
        out = self.labels(enemy(1))
        self.assertNotIn("*novel*", out[0]["text"])

    def test_wire_shape(self):
        for label in self.labels(enemy(1), enemy(2, actor_id=0x0097)):
            self.assertIsInstance(label["key"], int)
            self.assertIsInstance(label["text"], str)
            self.assertEqual(len(label["color"]), 3)


class TestRuntimePush(RuntimeCase):
    def pushes(self):
        return [r for r in self.link.requests if r.get("op") == "overlay"]

    def test_empty_world_still_pushes_the_empty_set(self):
        # An empty set REPLACES: it is how stale labels get cleared.
        t0 = time.monotonic()
        self.runtime.tick(now=t0)            # no snapshot yet -> no push
        self.runtime.tick(now=t0 + 0.3)      # sweep fetched state above
        self.assertEqual(self.pushes()[-1]["labels"], [])

    def test_labels_follow_beliefs_then_throttle_then_keepalive(self):
        self.link.world["actors"] = [baba_actor(dist_xz=250.0)]
        t0 = time.monotonic()
        self.runtime.tick(now=t0)
        self.runtime.tick(now=t0 + 0.3)
        label = self.pushes()[-1]["labels"][0]
        self.assertEqual(label["key"], 111)
        self.assertIn("deku_baba", label["text"])
        self.assertIn("NEAREST_ENEMY", label["text"])
        n = len(self.pushes())
        self.runtime.tick(now=t0 + 0.35)     # unchanged, under keepalive
        self.assertEqual(len(self.pushes()), n)
        self.runtime.tick(now=t0 + 1.5)      # keepalive rearms the 3s
        self.assertEqual(len(self.pushes()), n + 1)


if __name__ == "__main__":
    unittest.main()
