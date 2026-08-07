import unittest

from ocarina import senses
from ocarina.game import Game
from ocarina.protocol import ACTORCAT_ENEMY

from .stubgame import StubLink


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
        # 0x01B9 held this role until 0.9.0 named it (gossip_stone); the
        # vocabulary grows one region ahead, so this test needs an id the
        # frontier has genuinely not reached.
        events = self.spawns(enemy_actor(0x0FFF, key=0x0FFF))
        self.assertEqual(events[0]["kind"], "unknown_0x0FFF")

    def test_onactorinit_no_longer_narrates(self):
        self.assertIsNone(senses.translate(
            {"event": "OnActorInit", "actorId": 0x0055}))

    def test_game_loaded_carries_the_file_slot(self):
        """The wire has sent `file` (0-based fileNum) since first light;
        curation dropped it and the tenth flight paid an hour on the
        wrong save line (docs/29). The slot is the file-select screen's
        own presentation."""
        ev = senses.translate({"event": "load_game", "file": 1})
        self.assertEqual(ev["cue"], "game_loaded")
        self.assertEqual(ev["file"], 1)

    def test_game_loaded_omits_file_on_an_old_instrument(self):
        # Absent, never guessed — a guard naming `file` must warn, not
        # silently compare a made-up value.
        ev = senses.translate({"event": "load_game"})
        self.assertEqual(ev["cue"], "game_loaded")
        self.assertNotIn("file", ev)


def scrub_actor(pos, dist_xz=0.0, dist_y=0.0, key=5, **extra):
    """An En_Hintnuts census entry as the wire actually sends it (tenth
    flight, 2026-08-07): `pos` good, both distance fields zero."""
    a = {"id": 0x0192, "cat": ACTORCAT_ENEMY, "health": 2, "sighted": True,
         "key": key, "pos": list(pos) if pos is not None else None,
         "dist_xz": dist_xz, "dist_y": dist_y}
    if pos is None:
        del a["pos"]
    a.update(extra)
    return a


class TestDegenerateCensusDistances(SightedCase):
    """The En_Hintnuts wire bug (harness-backlog tenth-flight item 3):
    dist_xz == 0 and dist_y == 0 while `pos` is good, so a scrub across
    the room reads as standing on Link. Hardened by deriving the pair
    from the positions the same snapshot already carries — applied ONCE,
    where Game.state() first reads the census, so the digest, the
    overlay, and behaviors can never disagree about a distance."""

    def link_with(self, *actors, player_pos=(0.0, 0.0, 0.0)):
        link = StubLink()
        if player_pos is None:
            link.world["player"] = {"yaw": 0, "state_flags1": 0,
                                    "state_flags2": 0}
        else:
            link.world["player"]["pos"] = list(player_pos)
        link.world["actors"] = list(actors)
        return link

    def test_degenerate_distance_is_derived_by_the_time_the_digest_reads_it(self):
        # THE BUG, end to end: 300 units away on the wire's own positions,
        # 0/0 in the distance fields. Pre-fix this digest says dist 0.0.
        st = Game(self.link_with(scrub_actor([0.0, 0.0, 300.0]))).state()
        enemy = self.digest(st)["nearest_enemy"]
        self.assertAlmostEqual(enemy["dist"], 300.0, places=3)

    def test_derived_dist_y_keeps_the_wire_sign_convention(self):
        """The wire's dist_y is player.y - actor.y (Actor_HeightDiff):
        NEGATIVE when the actor is above Link, which the digest negates
        into `above`. A derived value with the opposite sign would put
        every repaired actor on the wrong side of Link's head — docs/08
        §17, the field this repo has been burned on before. Pinned in
        BOTH directions, on the raw field and on the digest's `above`."""
        # Actor 100 units OVERHEAD: wire convention is dist_y = -100.
        overhead = scrub_actor([0.0, 100.0, 300.0], key=1)
        senses.normalize_census_distances(
            {"player": {"pos": [0.0, 0.0, 0.0]}, "actors": [overhead]})
        self.assertAlmostEqual(overhead["dist_y"], -100.0, places=3)

        # Actor 100 units BELOW: wire convention is dist_y = +100.
        below = scrub_actor([0.0, -100.0, 300.0], key=2)
        senses.normalize_census_distances(
            {"player": {"pos": [0.0, 0.0, 0.0]}, "actors": [below]})
        self.assertAlmostEqual(below["dist_y"], 100.0, places=3)

        # And the same two through the digest's `above` (positive = up).
        st = Game(self.link_with(scrub_actor([0.0, 100.0, 300.0]))).state()
        self.assertAlmostEqual(self.digest(st)["nearest_enemy"]["above"],
                               100.0, places=3)

    def test_an_actor_truly_at_link_stays_zero(self):
        # 0/0 with coincident positions is the TRUTH, not the bug — a
        # "repair" here would be inventing a distance out of noise.
        at_link = scrub_actor([0.0, 0.0, 0.0])
        st = Game(self.link_with(at_link)).state()
        self.assertEqual(st["actors"][0]["dist_xz"], 0.0)
        self.assertEqual(st["actors"][0]["dist_y"], 0.0)
        self.assertEqual(self.digest(st)["nearest_enemy"]["dist"], 0.0)

    def test_an_entry_without_a_position_is_left_alone(self):
        # Nothing to derive from: leave it exactly as it came (never guess).
        st = Game(self.link_with(scrub_actor(None))).state()
        self.assertEqual(st["actors"][0]["dist_xz"], 0.0)
        self.assertNotIn("pos", st["actors"][0])

    def test_a_snapshot_without_a_player_position_is_left_alone(self):
        st = Game(self.link_with(scrub_actor([0.0, 0.0, 300.0]),
                                 player_pos=None)).state()
        self.assertEqual(st["actors"][0]["dist_xz"], 0.0)

    def test_healthy_distances_are_never_rewritten(self):
        # The repair must be invisible on a working wire: a good entry
        # keeps the game's own numbers, projection quirks included.
        good = scrub_actor([0.0, 0.0, 300.0], dist_xz=250.0, dist_y=-40.0)
        st = Game(self.link_with(good)).state()
        self.assertEqual(st["actors"][0]["dist_xz"], 250.0)
        self.assertEqual(st["actors"][0]["dist_y"], -40.0)

    def test_only_the_degenerate_entries_move(self):
        # Whole-census immunity, one entry at a time: the bugged scrub is
        # repaired, the baba beside it is untouched.
        bugged = scrub_actor([0.0, 0.0, 400.0], key=1)
        fine = scrub_actor([0.0, 0.0, 100.0], dist_xz=100.0, key=2)
        st = Game(self.link_with(bugged, fine)).state()
        self.assertAlmostEqual(st["actors"][0]["dist_xz"], 400.0, places=3)
        self.assertEqual(st["actors"][1]["dist_xz"], 100.0)
        # ...and the slot goes to the genuinely nearer one, which is the
        # whole point: pre-fix the scrub's phantom 0 stole the slot.
        self.assertEqual(self.digest(st)["nearest_enemy"]["dist"], 100.0)


class TestInstrumentHonesty(unittest.TestCase):
    def test_census_carries_sight_detection(self):
        self.assertIsNone(senses.census_carries_sight({"actors": []}))
        old_wire = {"actors": [{"id": 0x0055, "key": 1}]}
        self.assertIs(senses.census_carries_sight(old_wire), False)
        new_wire = {"actors": [{"id": 0x0055, "key": 1, "sighted": False}]}
        self.assertIs(senses.census_carries_sight(new_wire), True)

    def test_census_truncation_detection(self):
        # The fourth flight's bug: 12 of 29 actors on the wire read as a
        # complete world because nothing compared the two numbers.
        self.assertIsNone(senses.census_truncated({"actors": [{}], "actor_count_total": 1}))
        self.assertEqual(senses.census_truncated({"actors": [{}] * 12,
                                                  "actor_count_total": 29}),
                         (12, 29))

    def test_census_truncation_unknown_without_a_total(self):
        # An instrument that never reports a total cannot be judged — say
        # nothing rather than claim completeness (docs/08: the confident
        # wrong answer is worse than the absent one).
        self.assertIsNone(senses.census_truncated({"actors": [{}] * 12}))


class TestIntervalDigest(unittest.TestCase):
    """"While you were out" (0.10.0, docs/31): the wake pack's
    compression of the interval the mind did not watch."""

    def setUp(self):
        self.now = 1000.0
        self.interval = senses.IntervalDigest(clock=lambda: self.now)

    def render(self, *events, elapsed=0.0):
        for ev in events:
            self.interval.note_event(ev)
        self.now += elapsed
        return self.interval.render()

    def test_tallies_collapse_by_event_and_key(self):
        out = self.render(*[{"event": "behavior_done", "behavior": "stand_watch",
                             "outcome": "success"} for _ in range(41)],
                          {"event": "behavior_done", "behavior": "walk_about"})
        self.assertIn({"event": "behavior_done", "behavior": "stand_watch",
                       "count": 41}, out["events"])
        self.assertIn({"event": "behavior_done", "behavior": "walk_about",
                       "count": 1}, out["events"])

    def test_novel_sightings_are_quoted_verbatim_repeats_counted(self):
        out = self.render({"event": "spawn", "kind": "deku_baba", "novel": 1,
                           "state": "closed", "seq": 7},
                          {"event": "spawn", "kind": "deku_baba", "novel": 0},
                          {"event": "spawn", "kind": "deku_baba", "novel": 0})
        self.assertEqual(out["firsts"],
                         [{"event": "spawn", "kind": "deku_baba", "novel": 1,
                           "state": "closed", "seq": 7}])
        self.assertIn({"event": "spawn", "kind": "deku_baba", "count": 2},
                      out["events"])

    def test_first_journal_text_quoted_repeats_counted(self):
        out = self.render({"event": "journal", "transition": "baba-done",
                           "text": "baba down after 4.0s"},
                          {"event": "journal", "transition": "baba-done",
                           "text": "baba down after 4.0s"},
                          {"event": "journal", "transition": "baba-done",
                           "text": "baba down after 9.0s"})
        texts = [e["text"] for e in out["firsts"]]
        self.assertEqual(texts, ["baba down after 4.0s", "baba down after 9.0s"])
        self.assertIn({"event": "journal", "transition": "baba-done",
                       "count": 1}, out["events"])

    def test_pickups_read_as_items_not_as_a_tally(self):
        out = self.render({"event": "pickup", "kind": "green_rupee"},
                          {"event": "pickup", "kind": "green_rupee"},
                          {"event": "pickup", "kind": "health"})
        self.assertEqual(out["items_gained"], {"green_rupee": 2, "health": 1})
        self.assertNotIn("events", out)

    def test_region_trail_collapses_consecutive_repeats(self):
        def entered(region):
            return {"event": "place", "cue": "region_entered", "region": region}
        out = self.render(entered("ydan:r@30,0,70"), entered("ydan:r@30,0,70"),
                          entered("ydan:r@10,0,40"), entered("ydan:r@30,0,70"))
        self.assertEqual(out["region_trail"],
                         ["ydan:r@30,0,70", "ydan:r@10,0,40", "ydan:r@30,0,70"])

    def test_state_delta_carries_only_what_changed(self):
        self.interval.note_state({"hearts": 3.0, "rupees": 23, "scene": 85},
                                 frames=100)
        self.interval.note_state({"hearts": 3.0, "rupees": 40, "scene": 85},
                                 frames=180)
        self.interval.note_state({"hearts": 2.5, "rupees": 40, "scene": 85},
                                 frames=923)
        out = self.render(elapsed=41.2)
        self.assertEqual(out["delta"], {"hearts": {"from": 3.0, "to": 2.5},
                                        "rupees": {"from": 23, "to": 40}})
        self.assertEqual(out["wall_s"], 41.2)
        self.assertEqual(out["ticks"], 823)

    def test_reset_starts_a_fresh_interval(self):
        self.render({"event": "damage_taken", "hearts": 0.5})
        self.interval.note_state({"hearts": 2.5}, frames=10)
        self.interval.reset()
        self.interval.note_state({"hearts": 2.5}, frames=20)
        out = self.render(elapsed=1.0)
        self.assertEqual(out, {"wall_s": 1.0, "ticks": 0})

    def test_empty_interval_says_nothing_but_the_clock(self):
        self.assertEqual(self.render(elapsed=0.5), {"wall_s": 0.5})

    def test_lines_render_every_section(self):
        self.interval.note_state({"hearts": 3.0}, frames=0)
        self.interval.note_state({"hearts": 2.5}, frames=60)
        out = self.render({"event": "damage_taken", "hearts": 0.5},
                          {"event": "spawn", "kind": "keese", "novel": 1},
                          {"event": "pickup", "kind": "health"},
                          {"event": "place", "cue": "region_entered",
                           "region": "ydan:r@30,0,70"},
                          elapsed=12.0)
        text = "\n".join(senses.interval_lines(out))
        self.assertIn("12.0s wall", text)
        self.assertIn("60 game ticks", text)
        self.assertIn("hearts: 3.0 -> 2.5", text)
        self.assertIn("picked up: health x1", text)
        self.assertIn("trail: ydan:r@30,0,70", text)
        self.assertIn("damage_taken x1", text)
        self.assertIn('"kind": "keese"', text)
        self.assertEqual(senses.interval_lines({}), [])


if __name__ == "__main__":
    unittest.main()
