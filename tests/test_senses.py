import unittest

from ocarina import senses
from ocarina.protocol import ACTORCAT_ENEMY


class TestDigest(unittest.TestCase):
    def test_above_sign_matches_its_name(self):
        """dist_y on the wire is player.y - actor.y (Actor_HeightDiff):
        negative for an actor overhead. `above` must read positive-up —
        caught live on 2026-08-01 against the room-0 skulltula (hangs
        ~1072 up; the wire said -1073). The docs/08 §17 field, again."""
        state = {"health": 48, "health_capacity": 48,
                 "actors": [{"id": 0x0037, "cat": ACTORCAT_ENEMY, "health": 2,
                             "dist_xz": 301.0, "dist_y": -1073.0}]}
        enemy = senses.digest(state)["nearest_enemy"]
        self.assertEqual(enemy["kind"], "skulltula")
        self.assertEqual(enemy["above"], 1073.0,
                         "an actor overhead must read as above > 0")

    def test_no_enemies_means_no_nearest(self):
        digest = senses.digest({"health": 48, "health_capacity": 48, "actors": []})
        self.assertNotIn("nearest_enemy", digest)
        self.assertEqual(digest["enemies"], 0)


class TestSpawnNarration(unittest.TestCase):
    """Second light (2026-08-01): names grown from AJ's eyewitness
    sightings; sprite-less actors dropped from the spawn stream."""

    class _Seen:
        def sight(self, kind):
            return True

    def spawn(self, actor_id):
        return senses.translate({"event": "OnActorInit", "actorId": actor_id},
                                self._Seen())

    def test_sighted_actors_carry_official_names(self):
        for actor_id, name in ((0x0125, "bush"), (0x0018, "fairy"),
                               (0x002E, "door"), (0x000F, "spider_web"),
                               (0x000A, "treasure_chest")):
            ev = self.spawn(actor_id)
            self.assertEqual(ev["kind"], name)
            self.assertEqual(ev["event"], "spawn")

    def test_spriteless_actors_are_never_presented(self):
        # Link himself, room-transition planes, Navi-message trigger
        # volumes: a sighted player cannot see any of them, so their
        # spawns must not narrate (X-ray vision otherwise).
        for actor_id in (0x0000, 0x0023, 0x011B):
            self.assertIsNone(self.spawn(actor_id))

    def test_unknown_still_flags_the_gap(self):
        ev = self.spawn(0x01B9)
        self.assertEqual(ev["kind"], "unknown_0x01B9")


if __name__ == "__main__":
    unittest.main()
