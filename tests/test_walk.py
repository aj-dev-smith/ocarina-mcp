"""The routed walk (dojo docs/30, 0.13.0): the refusal grammar, the
clearance shaping, census-prop obstacles, the reach/moving digest riders,
the standing gate on localization, and the crawl end-clustering fix.

Most tests run on the synthetic meshes test_place.py established (the
two-floor room, the atrium web) plus two new ones: a corridor at maze
scale (the clearance pins) and a crawl tunnel (the end-clustering pin).
Real-o2r pins are skipped when oot.o2r is absent on this machine.
"""

from __future__ import annotations

import math
import unittest
from pathlib import Path

from ocarina import senses
from ocarina.collision import CollisionMesh, Poly, SurfaceType
from ocarina.game import Game
from ocarina.navgraph import distill
from ocarina.place import (DESIRED_CLEARANCE, LINK_DIAMETER, STAND_TOL,
                           PlaceGraph, PlaceSense, RouteFailed, RouteRefused,
                           TraverseFailed, TraverseRefused)

from .stubgame import StubLink, baba_actor
from .test_place import (FLOOR_N, LOWER, UPPER, VINE, atrium_web_mesh,
                         sense_with_graph, state_at, two_floor_mesh)

O2R = Path("/Users/aj/Code/Shipwright/oot.o2r")


def corridor_mesh(width: float) -> CollisionMesh:
    """A straight corridor 600 long and `width` wide — the maze's shape
    in miniature (recon: circuits ~94-100 units, pinches down to 30,
    Link himself ~24 across)."""
    verts = [(0, 0, 0), (600, 0, 0), (600, 0, width), (0, 0, width)]
    mesh = CollisionMesh(min_bounds=(0, 0, 0), max_bounds=(600, 0, width))
    mesh.vertices = verts
    mesh.surface_types = [SurfaceType(data0=0, data1=0)]
    for i, t in enumerate([(0, 1, 2), (0, 2, 3)]):
        mesh.polys.append(Poly(index=i, type=0, va=t[0], vb=t[1], vc=t[2],
                               normal=FLOOR_N, dist=0))
    return mesh


def crawl_mesh() -> CollisionMesh:
    """Two floor slabs joined only by a crawl tunnel through a 20-unit
    wall: the sword crawlspace in miniature. The crawl-flagged polys are
    the entrance FACE quads (normals along the crawl direction), exactly
    as spot04 ships them — measured 2026-08-07."""
    verts = [
        (0, 0, 0), (200, 0, 0), (200, 0, 200), (0, 0, 200),          # 0-3 slab A
        (0, 0, 220), (200, 0, 220), (200, 0, 420), (0, 0, 420),      # 4-7 slab B
        (80, 0, 200), (120, 0, 200), (120, 24, 200), (80, 24, 200),  # 8-11 face A
        (80, 0, 220), (120, 0, 220), (120, 24, 220), (80, 24, 220),  # 12-15 face B
    ]
    mesh = CollisionMesh(min_bounds=(0, 0, 0), max_bounds=(200, 24, 420))
    mesh.vertices = verts
    mesh.surface_types = [
        SurfaceType(data0=0, data1=0),          # plain floor
        SurfaceType(data0=5 << 21, data1=0),    # wall type 5 -> crawlspace
    ]
    tris = [
        (0, (0, 1, 2), FLOOR_N), (0, (0, 2, 3), FLOOR_N),      # slab A
        (0, (4, 5, 6), FLOOR_N), (0, (4, 6, 7), FLOOR_N),      # slab B
        (1, (8, 9, 10), (0.0, 0.0, -1.0)),                     # face A
        (1, (8, 10, 11), (0.0, 0.0, -1.0)),
        (1, (13, 12, 15), (0.0, 0.0, 1.0)),                    # face B
        (1, (13, 15, 14), (0.0, 0.0, 1.0)),
    ]
    for i, (t, (a, b, c), n) in enumerate(tris):
        mesh.polys.append(Poly(index=i, type=t, va=a, vb=b, vc=c,
                               normal=n, dist=0))
    return mesh


class TestExceptionFamily(unittest.TestCase):
    def test_traverse_names_are_aliases_not_subclasses(self):
        # docs/30 open call 5, as recommended: ONE refusal family. A
        # graded body's `except TraverseRefused` must catch a walk_to
        # refusal and vice versa — identity, not inheritance.
        self.assertIs(TraverseRefused, RouteRefused)
        self.assertIs(TraverseFailed, RouteFailed)

    def test_one_except_clause_catches_both_verbs(self):
        try:
            raise RouteRefused("walk refusal")
        except TraverseRefused as e:
            self.assertIn("walk", str(e))


class TestResolveWalk(unittest.TestCase):
    def setUp(self):
        self.ps = sense_with_graph()
        self.lower = state_at(150, 2, 100)

    def test_same_region_routes_to_the_exact_target(self):
        route = self.ps.resolve_walk(self.lower, 250, 150)
        self.assertEqual(route["region"], LOWER)
        wx, wz = route["waypoints"][-1]
        self.assertLess(math.hypot(wx - 250, wz - 150), 1.0,
                        "the polyline must end AT the target")

    def test_waypoints_stay_in_the_region(self):
        route = self.ps.resolve_walk(self.lower, 250, 150)
        g = self.ps.graph_for(0)
        for (x, z) in route["waypoints"]:
            hit = g.locate(x, 5, z)
            self.assertIsNotNone(hit)
            self.assertEqual(hit[0]["id"], route["rid"])

    def test_the_cliff_refused_by_name(self):
        # THE headline case (docs/30 acceptance criterion 1): a target
        # in another walkable component, refused with the target's
        # region named, the legs out of yours named, zero movement.
        with self.assertRaises(RouteRefused) as cm:
            self.ps.resolve_walk(self.lower, 100, 300)   # the upper floor
        text = str(cm.exception)
        self.assertIn(UPPER, text, "names the target's region")
        self.assertIn(LOWER, text, "names YOUR region")
        self.assertIn(VINE, text, "names the legs out")
        self.assertIn("cross-region routing is yours", text)

    def test_a_ledge_above_is_named_not_voided(self):
        # A target on a floor ABOVE Link's level localizes with an open
        # ceiling so the refusal can name the region instead of calling
        # real geometry "off the map".
        ps = PlaceSense("/nonexistent/dummy.o2r")
        ps._graphs[0] = PlaceGraph("test", distill(atrium_web_mesh()))
        g = ps.graph_for(0)
        ledge = g.region_name(g.locate(100, 1000, 100)[0])
        with self.assertRaises(RouteRefused) as cm:
            ps.resolve_walk(state_at(400, 2, 100), 100, 100)
        self.assertIn(ledge, str(cm.exception))

    def test_target_off_the_map(self):
        with self.assertRaises(RouteRefused) as cm:
            self.ps.resolve_walk(self.lower, 5000, 5000)
        self.assertIn("OFF THE MAP", str(cm.exception))

    def test_you_off_the_map(self):
        with self.assertRaises(RouteRefused) as cm:
            self.ps.resolve_walk(state_at(1000, 0, 1000), 150, 100)
        self.assertIn("OFF THE MAP here", str(cm.exception))

    def test_standing_above_the_floor_refuses_with_the_height(self):
        # docs/28 learning 4: on an actor surface the OLD localizer put
        # Link in the region far below and refused from there — a lie.
        ps = PlaceSense("/nonexistent/dummy.o2r")
        ps._graphs[0] = PlaceGraph("test", distill(atrium_web_mesh()))
        with self.assertRaises(RouteRefused) as cm:
            ps.resolve_walk(state_at(400, 900, 100), 500, 100)
        text = str(cm.exception)
        self.assertIn("ABOVE the mapped floor", text)
        self.assertIn("900", text)

    def test_refuses_without_o2r(self):
        ps = PlaceSense(None)
        with self.assertRaises(RouteRefused) as cm:
            ps.resolve_walk(self.lower, 150, 100)
        self.assertIn("--o2r", str(cm.exception))
        self.assertIn("the routed walk", str(cm.exception))


class TestClearance(unittest.TestCase):
    def _graph(self, width):
        return PlaceGraph("test", distill(corridor_mesh(width)))

    def test_a_pinch_routes_the_midline_and_is_never_refused(self):
        # The adaptive formula's floor: a 30-unit corridor (Link is 24
        # across) — a fixed 30-unit clearance rule would refuse the
        # acceptance course itself (docs/30 maze recon).
        g = self._graph(30.0)
        rid = g.locate(300, 5, 15)[0]["id"]
        wps = g.route_in_region(rid, (20, 0, 15), (580, 15))
        self.assertTrue(wps, "a corridor Link fits must never be refused")
        for (x, z) in wps:
            self.assertGreater(z, 9.0, f"waypoint ({x:.0f},{z:.0f}) scrapes")
            self.assertLess(z, 21.0, f"waypoint ({x:.0f},{z:.0f}) scrapes")

    def test_open_corridor_holds_the_desired_offset(self):
        g = self._graph(100.0)
        rid = g.locate(300, 5, 50)[0]["id"]
        wps = g.route_in_region(rid, (20, 0, 50), (580, 50))
        for (x, z) in wps:
            d, _q = g.wall_distance(rid, x, z)
            self.assertGreaterEqual(
                d, DESIRED_CLEARANCE - 1.0,
                f"waypoint ({x:.0f},{z:.0f}) is {d:.0f} from a wall — the "
                f"walk must hold clearance in open space (criterion 7)")

    def test_nudges_never_leave_the_region(self):
        g = self._graph(30.0)
        rid = g.locate(300, 5, 15)[0]["id"]
        for (x, z) in g.route_in_region(rid, (20, 0, 15), (580, 15)):
            hit = g.locate(x, 5, z)
            self.assertIsNotNone(hit)
            self.assertEqual(hit[0]["id"], rid)

    def test_squeezes_are_presented(self):
        ps = PlaceSense("/nonexistent/dummy.o2r")
        ps._graphs[0] = PlaceGraph("test", distill(corridor_mesh(30.0)))
        route = ps.resolve_walk(state_at(20, 0, 15), 580, 15)
        self.assertTrue(route["squeezes"],
                        "a 30-unit corridor around a 24-unit Link is a "
                        "squeeze a sighted player would see")
        self.assertLess(route["squeezes"][0]["width"], 36.0)

    def test_wide_room_reports_no_squeeze(self):
        route = sense_with_graph().resolve_walk(state_at(150, 2, 100),
                                                250, 150)
        self.assertEqual(route["squeezes"], [])


class TestPropObstacles(unittest.TestCase):
    def _game(self, chest_pos, link_pos=(150.0, 2.0, 20.0)):
        link = StubLink()
        link.world["scene"] = 0
        link.world["player"]["pos"] = list(link_pos)
        link.world["actors"] = [{
            "id": 0x000A, "cat": 0, "params": 0, "key": 7,
            "pos": list(chest_pos), "dist_xz": 100.0, "dist_y": 0.0,
            "health": 0, "sighted": True, "drawn": True, "opened": False,
        }]
        game = Game(link)
        game.place = sense_with_graph()
        return game, link

    def test_a_chest_on_the_path_refuses_by_name_and_clock(self):
        game, link = self._game(chest_pos=(150.0, 2.0, 100.0))
        with self.assertRaises(RouteRefused) as cm:
            game.walk_to(150, 180)
        text = str(cm.exception)
        self.assertIn("blocked by a treasure_chest", text)
        self.assertIn("o'clock", text)
        self.assertIn("guesses", text, "the radius guess is labelled")
        pads = [r for r in link.requests if r.get("op") == "pad"]
        self.assertEqual(pads, [], "the refusal must precede all movement")

    def test_a_chest_on_the_target_says_so(self):
        game, _link = self._game(chest_pos=(150.0, 2.0, 180.0))
        with self.assertRaises(RouteRefused) as cm:
            game.walk_to(150, 180)
        self.assertIn("sitting on the target", str(cm.exception))

    def test_a_prop_off_the_path_does_not_block(self):
        game, _link = self._game(chest_pos=(280.0, 2.0, 190.0))
        self.assertIsNone(game.reachable(140, 40))

    def test_a_prop_on_another_floor_does_not_block(self):
        game, _link = self._game(chest_pos=(150.0, 2.0, 100.0))
        game.link.world["actors"][0]["dist_y"] = -400.0   # far above
        self.assertIsNone(game.reachable(150, 180))

    def test_reachable_returns_the_refusal_and_never_moves(self):
        game, link = self._game(chest_pos=(150.0, 2.0, 100.0))
        why = game.reachable(150, 180)
        self.assertIn("blocked by a treasure_chest", why)
        why2 = game.reachable(100, 300)                   # the cliff
        self.assertIn("not walk-reachable", why2)
        pads = [r for r in link.requests if r.get("op") == "pad"]
        self.assertEqual(pads, [], "reachable is a QUERY: zero movement")

    def test_walk_to_refuses_with_no_place_sense_before_any_io(self):
        game = Game(link=None)     # any link touch would explode — none may
        with self.assertRaises(RouteRefused):
            game.walk_to(100, 100)
        self.assertIn("--o2r", game.reachable(100, 100))


class TestReachRider(unittest.TestCase):
    def setUp(self):
        self.ps = sense_with_graph()

    def _reach(self, state, apos):
        return self.ps.judge_reach(state, {"pos": list(apos)})

    def test_same_region_is_walkable(self):
        self.assertEqual(self._reach(state_at(150, 2, 100), (250, 2, 150)),
                         "walkable")

    def test_linked_leg_up_is_a_climb(self):
        self.assertEqual(self._reach(state_at(150, 2, 100), (100, 202, 300)),
                         "up a climb")

    def test_linked_leg_down_is_a_drop(self):
        self.assertEqual(self._reach(state_at(100, 205, 300), (150, 2, 100)),
                         "down a drop")

    def test_no_leg_is_across_a_gap(self):
        ps = PlaceSense("/nonexistent/dummy.o2r")
        ps._graphs[0] = PlaceGraph("test", distill(atrium_web_mesh()))
        judged = ps.judge_reach(state_at(100, 902, 100),
                                {"pos": [400.0, 2.0, 100.0]})
        self.assertEqual(judged, "across a gap")

    def test_off_map_actor_is_absent(self):
        self.assertIsNone(self._reach(state_at(150, 2, 100),
                                      (5000, 0, 5000)))

    def test_link_not_standing_is_absent(self):
        ps = PlaceSense("/nonexistent/dummy.o2r")
        ps._graphs[0] = PlaceGraph("test", distill(atrium_web_mesh()))
        self.assertIsNone(ps.judge_reach(state_at(400, 900, 100),
                                         {"pos": [500.0, 2.0, 100.0]}))


class TestMotion(unittest.TestCase):
    def setUp(self):
        self.now = [0.0]
        self.motion = senses.Motion(clock=lambda: self.now[0])

    def _state(self, pos, key=111):
        return {"save_loaded": True, "scene": 0,
                "actors": [{"key": key, "pos": list(pos)}]}

    def test_single_sample_cannot_judge(self):
        self.motion.observe(self._state((0, 0, 0)))
        self.assertIsNone(self.motion.moving(111))

    def test_still_reads_false(self):
        for t in (0.0, 0.25, 0.5):
            self.now[0] = t
            self.motion.observe(self._state((100, 0, 100)))
        self.assertIs(self.motion.moving(111), False)

    def test_drift_reads_true(self):
        for t, x in ((0.0, 100), (0.25, 106), (0.5, 112)):
            self.now[0] = t
            self.motion.observe(self._state((x, 0, 100)))
        self.assertIs(self.motion.moving(111), True)

    def test_animation_jitter_is_not_motion(self):
        for t, x in ((0.0, 100.0), (0.25, 101.5), (0.5, 100.5)):
            self.now[0] = t
            self.motion.observe(self._state((x, 0, 100)))
        self.assertIs(self.motion.moving(111), False)

    def test_scene_change_clears(self):
        self.motion.observe(self._state((0, 0, 0)))
        self.now[0] = 0.3
        st = self._state((0, 0, 0))
        st["scene"] = 5
        self.motion.observe(st)
        self.assertIsNone(self.motion.moving(111),
                          "one sample in the new scene cannot judge")

    def test_unknown_key_is_absent(self):
        self.assertIsNone(self.motion.moving(999))


class TestDigestRiders(unittest.TestCase):
    def test_moving_and_reach_ride_the_nearest_enemy(self):
        sightings = senses.Sightings()
        now = [0.0]
        motion = senses.Motion(clock=lambda: now[0])
        st = {"save_loaded": True, "scene": 0, "health": 48,
              "health_capacity": 48, "player": {"pos": [0.0, 0.0, 0.0],
                                                "yaw": 0, "state_flags1": 0},
              "actors": [baba_actor(dist_xz=200.0)]}
        sightings.observe(st)
        for t, z in ((0.0, 200.0), (0.3, 208.0)):
            now[0] = t
            st["actors"][0]["pos"] = [0.0, 0.0, z]
            motion.observe(st)
        out = senses.digest(st, sightings, motion=motion,
                            reach=lambda a: "walkable")
        self.assertIs(out["nearest_enemy"]["moving"], True)
        self.assertEqual(out["nearest_enemy"]["reach"], "walkable")

    def test_riders_absent_when_sources_cannot_judge(self):
        sightings = senses.Sightings()
        st = {"save_loaded": True, "scene": 0, "health": 48,
              "health_capacity": 48, "player": {"pos": [0.0, 0.0, 0.0],
                                                "yaw": 0, "state_flags1": 0},
              "actors": [baba_actor(dist_xz=200.0)]}
        sightings.observe(st)
        motion = senses.Motion()
        motion.observe(st)                      # one sample: cannot judge
        out = senses.digest(st, sightings, motion=motion,
                            reach=lambda a: None)
        self.assertNotIn("moving", out["nearest_enemy"])
        self.assertNotIn("reach", out["nearest_enemy"])

    def test_schema_carries_the_riders(self):
        self.assertIsNone(senses.check_path(("nearest_enemy", "moving")))
        self.assertIsNone(senses.check_path(("nearest_enemy", "reach")))


class TestStandingGates(unittest.TestCase):
    def setUp(self):
        self.ps = PlaceSense("/nonexistent/dummy.o2r")
        self.ps._graphs[0] = PlaceGraph("test", distill(atrium_web_mesh()))

    def test_sample_above_the_floor_is_not_on_mesh(self):
        s = self.ps.sample(state_at(400, 900, 100))    # web over the pit
        self.assertFalse(s["on_mesh"])
        self.assertNotIn("region", s,
                         "the region 900 below Link is not where he is")

    def test_hovering_narrates_nothing_landing_narrates_the_fall(self):
        self.ps.fold(state_at(100, 900, 100))          # on the ledge
        self.assertEqual(self.ps.fold(state_at(400, 900, 100)), [],
                         "over the pit at ledge height: no place events")
        evs = self.ps.fold(state_at(400, 2, 100))      # now he lands
        cues = [e["cue"] for e in evs]
        self.assertIn("region_entered", cues)
        self.assertIn("fell", cues, "a real fall still narrates on landing")


class TestSightedActorsView(unittest.TestCase):
    def test_sighted_filter(self):
        link = StubLink()
        link.world["actors"] = [baba_actor(sighted=True, key=1),
                                baba_actor(sighted=False, key=2)]
        game = Game(link)
        self.assertEqual(len(game.actors()), 2, "default stays raw")
        seen = game.actors(sighted=True)
        self.assertEqual([a["key"] for a in seen], [1])


class TestCrawlEndClustering(unittest.TestCase):
    def test_both_faces_link_the_two_slabs(self):
        g = distill(crawl_mesh())
        crawls = [e for e in g["climb_edges"] if e["kind"] == "crawl"]
        self.assertEqual(len(crawls), 2, "one edge per entrance face")
        for e in crawls:
            self.assertTrue(e["linked"],
                            f"{e['name']} unlinked — the end-clustering gap")
            self.assertTrue(e["from"] and e["to"])
            self.assertNotEqual(e["from"], e["to"])


@unittest.skipUnless(O2R.exists(), "oot.o2r not present on this machine")
class TestRealO2rPins(unittest.TestCase):
    SPOT04 = "scenes/shared/spot04_scene/spot04_sceneCollisionHeader_008918"

    @classmethod
    def setUpClass(cls):
        from ocarina.collision import load_from_o2r
        cls.graph = distill(load_from_o2r(str(O2R), cls.SPOT04))
        cls.pg = PlaceGraph("spot04", cls.graph)

    def test_the_sword_crawlspace_links_village_to_training(self):
        # docs/30 maze recon: the tunnel's ends were unlinked — "fix it
        # in this pass". The tunnel interior is its own region, so the
        # link is village <-> tunnel <-> training area, one edge per
        # entrance face.
        names = {r["id"]: r["name"] for r in self.graph["regions"]}
        pairs = set()
        for e in self.graph["climb_edges"]:
            if e["kind"] != "crawl":
                continue
            self.assertTrue(e["linked"], f"{e['name']} still unlinked")
            for f in e["from"]:
                for t in e["to"]:
                    pairs.add(frozenset((names[f], names[t])))
        self.assertIn(frozenset(("r@-100,10,220", "r@-780,120,1220")), pairs,
                      "village <-> tunnel interior")
        self.assertIn(frozenset(("r@-470,130,1770", "r@-780,120,1220")), pairs,
                      "tunnel interior <-> training area")

    def test_training_area_routes_hold_body_scale_clearance(self):
        # Criterion 7's floor at map level: a route across the maze
        # region keeps every waypoint at least Link's own radius off the
        # walls (the recon's narrowest pinch is 30 units — midline 15).
        maze = self.pg.by_name.get("spot04:r@-470,130,1770")
        self.assertIsNotNone(maze, "the training-area region moved?")
        rid = maze["id"]
        polys = [self.pg.polys[i] for i in self.pg._region_polys[rid]]
        start = min(polys, key=lambda p: p["cen"][2])["cen"]
        goal = max(polys, key=lambda p: p["cen"][2])["cen"]
        wps = self.pg.route_in_region(rid, start, (goal[0], goal[2]))
        self.assertTrue(wps, "the maze region must be routable end to end")
        for (x, z) in wps:
            d, _ = self.pg.wall_distance(rid, x, z)
            self.assertGreater(
                d, LINK_DIAMETER / 2.0 - 1.0,
                f"waypoint ({x:.0f},{z:.0f}) is {d:.1f} from a wall — "
                f"scrape at body scale")


if __name__ == "__main__":
    unittest.main()
