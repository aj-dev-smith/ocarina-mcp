import unittest

from ocarina import senses
from ocarina.protocol import ACTORCAT_ENEMY


def enemy_actor(actor_id=0x0055, dist_xz=100.0, dist_y=0.0, health=2):
    return {"id": actor_id, "cat": ACTORCAT_ENEMY, "health": health,
            "dist_xz": dist_xz, "dist_y": dist_y}


class TestDigest(unittest.TestCase):
    def test_above_sign_matches_its_name(self):
        """dist_y on the wire is player.y - actor.y (Actor_HeightDiff):
        negative for an actor overhead. `above` must read positive-up —
        caught live on 2026-08-01 against the room-0 skulltula (the wire
        said -1073 for 1072 up). The docs/08 §17 field, again. (A
        descended skulltula here — the ceiling one is now out of view,
        see TestSightHeightBound.)"""
        state = {"health": 48, "health_capacity": 48,
                 "actors": [enemy_actor(0x0037, dist_xz=301.0, dist_y=-120.0)]}
        enemy = senses.digest(state)["nearest_enemy"]
        self.assertEqual(enemy["kind"], "skulltula")
        self.assertEqual(enemy["above"], 120.0,
                         "an actor overhead must read as above > 0")

    def test_no_enemies_means_no_nearest(self):
        digest = senses.digest({"health": 48, "health_capacity": 48, "actors": []})
        self.assertNotIn("nearest_enemy", digest)
        self.assertEqual(digest["enemies"], 0)


class TestSightHeightBound(unittest.TestCase):
    """The interim vertical sight bound (second light's masking finding,
    2026-08-01): the room-0 ceiling skulltula at above +1081 held the
    single nearest_enemy slot while the baba AJ was facing appeared
    nowhere in the narration. X-ray info displaces fair info."""

    def digest(self, *actors):
        return senses.digest({"actors": list(actors)})

    def test_ceiling_lurker_cannot_mask_the_enemy_in_view(self):
        # The live second-light room: skulltula nearer in xz, but 1081
        # up a shaft no sighted player has looked into yet.
        d = self.digest(enemy_actor(0x0095, dist_xz=61.0, dist_y=-1081.0),
                        enemy_actor(0x0055, dist_xz=250.0, dist_y=0.0))
        self.assertEqual(d["nearest_enemy"]["kind"], "deku_baba")
        self.assertEqual(d["enemies"], 1,
                         "the count must agree with the slot on what "
                         "'in view' means")

    def test_only_out_of_view_enemies_reads_as_clear(self):
        d = self.digest(enemy_actor(0x0095, dist_xz=61.0, dist_y=-1081.0))
        self.assertNotIn("nearest_enemy", d)
        self.assertEqual(d["enemies"], 0)

    def test_bound_is_inclusive_and_symmetric(self):
        # At exactly the bound: in view. Sign of dist_y is irrelevant —
        # the bound is vertical distance, up or down.
        at = senses.SIGHT_HEIGHT_BOUND
        for dist_y in (at, -at):
            d = self.digest(enemy_actor(dist_y=dist_y))
            self.assertIn("nearest_enemy", d)
        for dist_y in (at + 1, -(at + 1)):
            d = self.digest(enemy_actor(dist_y=dist_y))
            self.assertNotIn("nearest_enemy", d)


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
