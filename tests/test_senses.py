import unittest

from ocarina import senses
from ocarina.protocol import ACTORCAT_ENEMY


def enemy_actor(actor_id=0x0055, dist_xz=100.0, dist_y=0.0, health=2,
                sighted=True, key=1):
    return {"id": actor_id, "cat": ACTORCAT_ENEMY, "health": health,
            "dist_xz": dist_xz, "dist_y": dist_y, "sighted": sighted,
            "key": key}


def world(*actors, scene=85, save_loaded=True, **extra):
    state = {"save_loaded": save_loaded, "scene": scene,
             "actors": list(actors)}
    state.update(extra)
    return state


class SightedCase(unittest.TestCase):
    def setUp(self):
        self.sightings = senses.Sightings()

    def digest(self, state):
        self.sightings.observe(state)
        return senses.digest(state, self.sightings)


class TestDigest(SightedCase):
    def test_above_sign_matches_its_name(self):
        """dist_y on the wire is player.y - actor.y (Actor_HeightDiff):
        negative for an actor overhead. `above` must read positive-up —
        caught live on 2026-08-01 against the room-0 skulltula (the wire
        said -1073 for 1072 up). The docs/08 §17 field, again. (A
        descended, sighted skulltula here — the ceiling one is the
        unsighted case in TestSightGating.)"""
        state = world(enemy_actor(0x0037, dist_xz=301.0, dist_y=-120.0),
                      health=48, health_capacity=48)
        enemy = self.digest(state)["nearest_enemy"]
        self.assertEqual(enemy["kind"], "skulltula")
        self.assertEqual(enemy["above"], 120.0,
                         "an actor overhead must read as above > 0")

    def test_no_enemies_means_no_nearest(self):
        digest = self.digest(world(health=48, health_capacity=48))
        self.assertNotIn("nearest_enemy", digest)
        self.assertEqual(digest["enemies"], 0)


class TestSightGating(SightedCase):
    """The enemy fields cover only sighted enemies (docs/22, blessed
    2026-08-02). Second light's masking finding is the acceptance case:
    the ceiling skulltula held the single nearest_enemy slot while the
    baba AJ was facing appeared nowhere — X-ray info displaces fair
    info."""

    def test_unsighted_lurker_cannot_mask_the_enemy_in_view(self):
        # The live second-light room: skulltula nearer in xz, 1081 up a
        # shaft the camera has never shown; baba visibly in front.
        d = self.digest(world(
            enemy_actor(0x0095, dist_xz=61.0, dist_y=-1081.0,
                        sighted=False, key=1),
            enemy_actor(0x0055, dist_xz=250.0, key=2)))
        self.assertEqual(d["nearest_enemy"]["kind"], "deku_baba")
        self.assertEqual(d["enemies"], 1,
                         "the count must agree with the slot on what "
                         "'in view' means")

    def test_only_unsighted_enemies_reads_as_clear(self):
        d = self.digest(world(enemy_actor(sighted=False)))
        self.assertNotIn("nearest_enemy", d)
        self.assertEqual(d["enemies"], 0)

    def test_object_permanence_across_camera_swings(self):
        # Sighted once, then the camera turns away (wire bit drops):
        # still fair knowledge at its live position. You can't unsee it.
        self.digest(world(enemy_actor(key=7)))
        d = self.digest(world(enemy_actor(key=7, sighted=False,
                                          dist_xz=180.0)))
        self.assertEqual(d["nearest_enemy"]["dist"], 180.0)

    def test_scene_change_clears_sightings(self):
        self.digest(world(enemy_actor(key=7), scene=85))
        d = self.digest(world(enemy_actor(key=7, sighted=False), scene=86))
        self.assertNotIn("nearest_enemy", d)

    def test_preplay_snapshots_contribute_nothing(self):
        # The attract demo is not the world (AJ, 2026-08-02).
        fresh = self.sightings.observe(world(enemy_actor(),
                                             save_loaded=False))
        self.assertEqual(fresh, [])
        self.assertFalse(self.sightings.sighted(1))


class TestSpawnNarration(SightedCase):
    """`spawn` narrates first SIGHTINGS (docs/22) — the old OnActorInit
    room-load burst is gone. Names and NEVER_PRESENTED carry over from
    second light's eyewitness pass."""

    class _Seen:
        def __init__(self):
            self.claimed = []

        def sight(self, kind):
            self.claimed.append(kind)
            return True

    def spawns(self, *actors):
        fresh = self.sightings.observe(world(*actors))
        return senses.spawn_events(fresh, self._Seen())

    def test_first_sighting_narrates_once(self):
        events = self.spawns(enemy_actor(key=1))
        self.assertEqual(events, [{"event": "spawn", "kind": "deku_baba",
                                   "novel": 1}])
        self.assertEqual(self.spawns(enemy_actor(key=1)), [],
                         "an already-sighted key must not re-narrate")

    def test_unsighted_actor_in_the_room_narrates_nothing(self):
        self.assertEqual(self.spawns(enemy_actor(sighted=False)), [])

    def test_sighted_actors_carry_official_names(self):
        for actor_id, name in ((0x0125, "bush"), (0x0018, "fairy"),
                               (0x002E, "door"), (0x000F, "spider_web"),
                               (0x000A, "treasure_chest")):
            events = self.spawns(enemy_actor(actor_id, key=actor_id))
            self.assertEqual(events[0]["kind"], name)
            self.assertEqual(events[0]["event"], "spawn")

    def test_spriteless_actors_are_never_presented(self):
        # Link himself, room-transition planes, Navi-message trigger
        # volumes: the attention predicate projects position only, so an
        # invisible volume can be "sighted" — the curation filter must
        # still drop it.
        for actor_id in (0x0000, 0x0023, 0x011B):
            self.assertEqual(self.spawns(enemy_actor(actor_id,
                                                     key=actor_id)), [])

    def test_unknown_still_flags_the_gap(self):
        events = self.spawns(enemy_actor(0x01B9, key=0x01B9))
        self.assertEqual(events[0]["kind"], "unknown_0x01B9")

    def test_onactorinit_no_longer_narrates(self):
        self.assertIsNone(senses.translate(
            {"event": "OnActorInit", "actorId": 0x0055}))


class TestInstrumentHonesty(unittest.TestCase):
    def test_census_carries_sight_detection(self):
        self.assertIsNone(senses.census_carries_sight({"actors": []}))
        old_wire = {"actors": [{"id": 0x0055, "key": 1}]}
        self.assertIs(senses.census_carries_sight(old_wire), False)
        new_wire = {"actors": [{"id": 0x0055, "key": 1, "sighted": False}]}
        self.assertIs(senses.census_carries_sight(new_wire), True)


if __name__ == "__main__":
    unittest.main()
