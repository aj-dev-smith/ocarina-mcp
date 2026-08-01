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


if __name__ == "__main__":
    unittest.main()
