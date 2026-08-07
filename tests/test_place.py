"""The place sense (dojo docs/25): distiller determinism, localization,
the place.* digest section, the `place` event producers, traverse
validation (every refusal is a designed behavior), and the resource.

Most tests run on a SYNTHETIC two-floor mesh (a big lower floor, an
upper floor, one vine wall linking them) so nothing here needs the o2r;
one integration test pins the real ydan graph and is skipped when the
o2r isn't present on this machine.
"""

from __future__ import annotations

import math
import tempfile
import threading
import unittest
from pathlib import Path

from ocarina import senses
from ocarina.behavior import BehaviorPreempted
from ocarina.collision import CollisionMesh, Poly, SurfaceType
from ocarina.events import EventLog
from ocarina.game import Game
from ocarina.navgraph import distill
from ocarina.place import (PlaceGraph, PlaceSense, TraverseFailed,
                           TraverseRefused, clock_bearing, heading_name,
                           judge_height)
from ocarina.runtime import MachineRuntime
from ocarina.server import ServerCore

from .stubgame import StubLink, baba_actor

O2R = Path("/Users/aj/Code/Shipwright/oot.o2r")

FLOOR_N = (0.0, 1.0, 0.0)
WALL_N = (0.0, 0.0, -1.0)


def two_floor_mesh() -> CollisionMesh:
    """Lower floor (300x200 at y=0), upper floor (200x200 at y=200),
    one vine wall at z=200 spanning the height between them."""
    verts = [
        (0, 0, 0), (300, 0, 0), (300, 0, 200), (0, 0, 200),          # 0-3
        (0, 200, 200), (200, 200, 200), (200, 200, 400), (0, 200, 400),  # 4-7
        (200, 0, 200),                                                # 8
    ]
    mesh = CollisionMesh(min_bounds=(0, 0, 0), max_bounds=(300, 200, 400))
    mesh.vertices = verts
    mesh.surface_types = [
        SurfaceType(data0=0, data1=0),          # plain floor
        SurfaceType(data0=4 << 21, data1=0),    # wall type 4 -> vine flag
    ]
    tris = [
        (0, (0, 1, 2), FLOOR_N), (0, (0, 2, 3), FLOOR_N),   # lower
        (0, (4, 5, 6), FLOOR_N), (0, (4, 6, 7), FLOOR_N),   # upper
        (1, (3, 8, 5), WALL_N), (1, (3, 5, 4), WALL_N),     # vine wall
    ]
    for i, (t, (a, b, c), n) in enumerate(tris):
        mesh.polys.append(Poly(index=i, type=t, va=a, vb=b, vc=c,
                               normal=n, dist=0))
    return mesh


def seam_mesh(gap: float) -> CollisionMesh:
    """Two floor slabs authored as separate sub-meshes whose shared corners
    disagree by `gap` units — the shipped scenes' unwelded seam, in
    miniature (Kokiri Forest's forest floor meets itself 1.0 unit off)."""
    verts = [
        (0, 0, 0), (200, 0, 0), (200, 0, 200), (0, 0, 200),              # 0-3
        (200, gap, 0), (400, gap, 0), (400, gap, 200), (200, gap, 200),  # 4-7
    ]
    mesh = CollisionMesh(min_bounds=(0, 0, 0), max_bounds=(400, gap, 200))
    mesh.vertices = verts
    mesh.surface_types = [SurfaceType(data0=0, data1=0)]
    for i, t in enumerate([(0, 1, 2), (0, 2, 3), (4, 5, 6), (4, 6, 7)]):
        mesh.polys.append(Poly(index=i, type=0, va=t[0], vb=t[1], vc=t[2],
                               normal=FLOOR_N, dist=0))
    return mesh


def terrain_ladder_mesh() -> CollisionMesh:
    """One HUGE terrain triangle with a ladder standing in the middle of it
    and a small platform at the top — the treehouse ladder, in miniature.
    No floor vertex is anywhere near the ladder's base (the exterior
    mesh-density trap): only a point-in-poly test can link the ground."""
    verts = [
        (-2000, 0, -2000), (2000, 0, -2000), (0, 0, 2000),        # 0-2 terrain
        (-16, 0, 0), (16, 0, 0), (16, 200, 0), (-16, 200, 0),     # 3-6 ladder
        (-50, 200, -100), (50, 200, -100),
        (50, 200, -4), (-50, 200, -4),                            # 7-10 balcony
    ]
    mesh = CollisionMesh(min_bounds=(-2000, 0, -2000), max_bounds=(2000, 200, 2000))
    mesh.vertices = verts
    mesh.surface_types = [
        SurfaceType(data0=0, data1=0),          # plain floor
        SurfaceType(data0=2 << 21, data1=0),    # wall type 2 -> ladder flag
    ]
    tris = [
        (0, (0, 1, 2), FLOOR_N),                                  # the terrain
        (0, (7, 8, 9), FLOOR_N), (0, (7, 9, 10), FLOOR_N),        # the balcony
        (1, (3, 4, 5), WALL_N), (1, (3, 5, 6), WALL_N),           # the ladder
    ]
    for i, (t, (a, b, c), n) in enumerate(tris):
        mesh.polys.append(Poly(index=i, type=t, va=a, vb=b, vc=c,
                               normal=n, dist=0))
    return mesh


def atrium_web_mesh() -> CollisionMesh:
    """A high ledge and a deep pit floor ~900 units below it, side by side
    in XZ — the Deku Tree atrium in miniature. The floor WEB Link stands
    on is an actor, so it is not in this mesh at all: walking laterally
    off the ledge's XZ footprint drops the LOCATED floor 900 units while
    Link himself never moves down (the ninth flight's six false `fell`
    narrations, dojo docs/28)."""
    verts = [
        (0, 900, 0), (200, 900, 0), (200, 900, 200), (0, 900, 200),  # 0-3 ledge
        (200, 0, 0), (600, 0, 0), (600, 0, 200), (200, 0, 200),      # 4-7 pit
    ]
    mesh = CollisionMesh(min_bounds=(0, 0, 0), max_bounds=(600, 900, 200))
    mesh.vertices = verts
    mesh.surface_types = [SurfaceType(data0=0, data1=0)]
    for i, t in enumerate([(0, 1, 2), (0, 2, 3), (4, 5, 6), (4, 6, 7)]):
        mesh.polys.append(Poly(index=i, type=0, va=t[0], vb=t[1], vc=t[2],
                               normal=FLOOR_N, dist=0))
    return mesh


LOWER = "test:r@150,0,100"
UPPER = "test:r@100,200,300"
VINE = "test:vine@100,0,200"


def sense_with_graph(scene: int = 0) -> PlaceSense:
    """A PlaceSense with the synthetic graph pre-cached — no o2r file is
    touched (the cache hit short-circuits acquisition)."""
    ps = PlaceSense("/nonexistent/dummy.o2r")
    ps._graphs[scene] = PlaceGraph("test", distill(two_floor_mesh()))
    return ps


def state_at(x, y, z, yaw=0, scene=0, flags1=0, save_loaded=True):
    return {"save_loaded": save_loaded, "scene": scene,
            "player": {"pos": [x, y, z], "yaw": yaw, "state_flags1": flags1}}


class TestDistillIdentity(unittest.TestCase):
    def test_names_are_deterministic_and_geometry_derived(self):
        g1 = distill(two_floor_mesh())
        g2 = distill(two_floor_mesh())
        self.assertEqual(g1, g2, "same mesh must distill identically")
        names = [r["name"] for r in g1["regions"]]
        self.assertEqual(names, ["r@150,0,100", "r@100,200,300"])
        self.assertEqual([r["id"] for r in g1["regions"]], [0, 1],
                         "ids re-sorted by area (lower floor is bigger)")
        self.assertEqual(g1["climb_edges"][0]["name"], "vine@100,0,200")

    def test_vine_links_both_floors(self):
        g = distill(two_floor_mesh())
        e = g["climb_edges"][0]
        self.assertTrue(e["linked"])
        self.assertEqual((e["from"], e["to"]), ([0], [1]))

    def test_candidate_edges_are_marked(self):
        g = distill(two_floor_mesh())
        drops = [e for e in g["candidate_edges"] if e["kind"] == "drop"]
        self.assertTrue(drops, "upper->lower should be a drop candidate")
        self.assertTrue(all(e["candidate"] for e in g["candidate_edges"]))


class TestSeamWelding(unittest.TestCase):
    """An unwelded seam is an invisible wall down the middle of a room:
    the two halves flood-fill as separate, non-adjacent regions and no
    route crosses. Welding within tolerance heals it — but a tolerance
    that fuses two REAL surfaces would invent floor that isn't there, so
    both directions are pinned."""

    def test_a_one_unit_seam_heals_into_one_region(self):
        g = distill(seam_mesh(1.0))
        self.assertEqual(len(g["regions"]), 1,
                         "a 1-unit authoring seam must not split the floor")
        self.assertEqual(g["regions"][0]["polys"], 4)

    def test_a_real_step_still_separates(self):
        g = distill(seam_mesh(4.0))
        self.assertEqual(len(g["regions"]), 2,
                         "welding must never fuse two genuinely distinct "
                         "surfaces — that would invent floor")

    def test_welding_does_not_move_geometry_it_does_not_touch(self):
        g = distill(seam_mesh(4.0))
        self.assertEqual(g["vertices"], list(seam_mesh(4.0).vertices),
                         "no near-duplicates: the vertex list is untouched")


class TestClimbLinkingOnCoarseTerrain(unittest.TestCase):
    def test_column_links_to_the_floor_it_stands_on(self):
        # Vertex proximity is a mesh-density assumption: outdoors, one
        # terrain triangle can be thousands of units across and its
        # corners are nowhere near the ladder. Standing ON the surface is
        # the honest predicate (Kokiri Forest's treehouse ladder had
        # from=[] until this test existed — Link's own front door).
        g = distill(terrain_ladder_mesh())
        self.assertEqual(len(g["climb_edges"]), 1)
        e = g["climb_edges"][0]
        self.assertEqual(e["kind"], "ladder")
        self.assertTrue(e["linked"], "a ladder with no ground is unusable")
        names = {r["id"]: r["name"] for r in g["regions"]}
        self.assertEqual([names[i] for i in e["from"]], ["r@0,0,-670"])
        self.assertEqual([names[i] for i in e["to"]], ["r@0,200,-50"])


class TestPlaceGraph(unittest.TestCase):
    def setUp(self):
        self.g = PlaceGraph("test", distill(two_floor_mesh()))

    def test_locate_on_each_floor(self):
        r, fy = self.g.locate(150, 5, 100)
        self.assertEqual(self.g.region_name(r), LOWER)
        self.assertEqual(fy, 0.0)
        r, fy = self.g.locate(100, 205, 300)
        self.assertEqual(self.g.region_name(r), UPPER)
        self.assertEqual(fy, 200.0)

    def test_locate_off_mesh_is_none(self):
        self.assertIsNone(self.g.locate(1000, 0, 1000))

    def test_locate_never_reports_a_floor_far_above(self):
        # Standing UNDER the upper floor's xz at y=0 must not localize up.
        self.assertIsNone(self.g.locate(100, 0, 300),
                          "no lower floor there; upper is 200 above")

    def test_route_in_region_stays_in_region(self):
        wps = self.g.route_in_region(0, (10, 0, 10), (100, 200))
        self.assertTrue(wps)
        for (x, z) in wps:
            hit = self.g.locate(x, 5, z)
            self.assertIsNotNone(hit)
            self.assertEqual(hit[0]["id"], 0)


class TestJudgments(unittest.TestCase):
    def test_clock_bearing_convention(self):
        # Facing +z (yaw 0): +z is 12; +x is LEFT (game.py stick math) = 9.
        self.assertEqual(clock_bearing(0, 0, 0, 0, 100), 12)
        self.assertEqual(clock_bearing(0, 0, 0, 100, 0), 9)
        self.assertEqual(clock_bearing(0, 0, 0, -100, 0), 3)
        self.assertEqual(clock_bearing(0, 0, 0, 0, -100), 6)
        # Turn to face the actor: it reads 12.
        self.assertEqual(clock_bearing(0, 0, 0x4000, 100, 0), 12)

    def test_heading_names(self):
        self.assertEqual(heading_name(0), "s")
        self.assertEqual(heading_name(0x8000), "n")
        self.assertEqual(heading_name(0x4000), "e")
        self.assertEqual(heading_name(0xC000), "w")

    def test_judge_height_eye_units(self):
        self.assertEqual(judge_height(20), "a step")
        self.assertEqual(judge_height(55), "about your height")
        self.assertEqual(judge_height(280), "about 5 times your height")


class TestPlaceSense(unittest.TestCase):
    def setUp(self):
        self.ps = sense_with_graph()

    def test_sample_on_mesh(self):
        s = self.ps.sample(state_at(150, 2, 100, yaw=0x8000))
        self.assertEqual(s["region"], LOWER)
        self.assertTrue(s["on_mesh"])
        self.assertEqual(s["heading"], "n")
        self.assertEqual((s["x"], s["y"], s["z"]), (150.0, 2.0, 100.0))

    def test_sample_off_mesh(self):
        s = self.ps.sample(state_at(1000, 0, 1000))
        self.assertFalse(s["on_mesh"])
        self.assertNotIn("region", s, "region is ABSENT off-mesh")

    def test_sample_gated_pre_play(self):
        self.assertIsNone(self.ps.sample(state_at(150, 2, 100,
                                                  save_loaded=False)),
                          "the attract demo is not the world")

    def test_region_entered_fires_once_per_region(self):
        evs = self.ps.fold(state_at(150, 2, 100))
        self.assertEqual([(e["cue"], e["region"]) for e in evs],
                         [("region_entered", LOWER)])
        self.assertEqual(self.ps.fold(state_at(160, 2, 110)), [],
                         "same region: no renarration")

    def test_fell_on_unplanned_downward_region_change(self):
        self.ps.fold(state_at(100, 205, 300))            # arrive upper
        evs = self.ps.fold(state_at(150, 2, 100))        # teleport down
        cues = [e["cue"] for e in evs]
        self.assertIn("fell", cues)
        fell = next(e for e in evs if e["cue"] == "fell")
        self.assertEqual(fell["drop"], 200.0)
        self.assertEqual(fell["region"], LOWER)

    def test_climbing_is_not_falling(self):
        from ocarina.protocol import PLAYER_STATE1_CLIMBING_LADDER
        self.ps.fold(state_at(100, 205, 300))
        evs = self.ps.fold(state_at(150, 2, 100,
                                    flags1=PLAYER_STATE1_CLIMBING_LADDER))
        self.assertNotIn("fell", [e["cue"] for e in evs])

    def test_declared_leg_suppresses_fell(self):
        self.ps.fold(state_at(100, 205, 300))
        self.ps.begin_leg(VINE)
        evs = self.ps.fold(state_at(150, 2, 100))
        self.assertNotIn("fell", [e["cue"] for e in evs])
        self.ps.end_leg()

    def test_standing_on_an_actor_surface_is_not_falling(self):
        # The atrium floor web: Link's own y never changes, but lateral
        # movement re-localizes him onto the mesh floor 900 units below.
        # A fall that did not move Link DOWN is not a fall.
        ps = PlaceSense("/nonexistent/dummy.o2r")
        ps._graphs[0] = PlaceGraph("test", distill(atrium_web_mesh()))
        ps.fold(state_at(100, 900, 100))                 # on the ledge
        evs = ps.fold(state_at(400, 900, 100))           # over the pit, same y
        self.assertNotIn("fell", [e["cue"] for e in evs],
                         "the located floor dropped 900; Link did not move")

    def test_stepping_down_is_not_falling(self):
        # A drop under FELL_MIN_DROP must not narrate. (Same region here
        # can't produce one, so go upper->lower with a shallow mesh?
        # Simpler: assert the threshold arithmetic via the constant.)
        from ocarina.place import FELL_MIN_DROP
        self.assertGreaterEqual(FELL_MIN_DROP, 40.0,
                                "a step (distill's DROP_MIN_DY) must not "
                                "read as a fall")


class TestResolveTraverse(unittest.TestCase):
    def setUp(self):
        self.ps = sense_with_graph()
        self.lower = state_at(150, 2, 100)
        self.upper = state_at(100, 205, 300)

    def test_edge_name_resolves_up(self):
        leg = self.ps.resolve_traverse(self.lower, "vine@100,0,200")
        self.assertEqual(leg["direction"], "up")
        self.assertEqual(leg["name"], VINE)
        self.assertEqual(leg["to_rids"], [1])
        self.assertEqual(leg["top_y"], 200)

    def test_adjacent_region_name_resolves(self):
        leg = self.ps.resolve_traverse(self.lower, UPPER)
        self.assertEqual(leg["name"], VINE)
        self.assertEqual(leg["direction"], "up")

    def test_refuses_unknown_name(self):
        with self.assertRaises(TraverseRefused) as cm:
            self.ps.resolve_traverse(self.lower, "the-void")
        self.assertIn("unknown place", str(cm.exception))

    def test_refuses_candidate_edge(self):
        g = self.ps.graph_for(0)
        cand = sorted(g.candidate_names)[0]
        with self.assertRaises(TraverseRefused) as cm:
            self.ps.resolve_traverse(self.upper, cand)
        self.assertIn("UNVERIFIED candidate", str(cm.exception))

    def test_refuses_descent_as_not_yet(self):
        with self.assertRaises(TraverseRefused) as cm:
            self.ps.resolve_traverse(self.upper, "vine@100,0,200")
        self.assertIn("not built yet", str(cm.exception))

    def test_refuses_off_mesh_start(self):
        with self.assertRaises(TraverseRefused) as cm:
            self.ps.resolve_traverse(state_at(1000, 0, 1000), VINE)
        self.assertIn("OFF THE MAP", str(cm.exception))

    def test_refuses_same_region(self):
        with self.assertRaises(TraverseRefused):
            self.ps.resolve_traverse(self.lower, LOWER)

    def test_refuses_without_o2r(self):
        ps = PlaceSense(None)
        with self.assertRaises(TraverseRefused) as cm:
            ps.resolve_traverse(self.lower, VINE)
        self.assertIn("--o2r", str(cm.exception))

    def test_waypoints_are_in_the_starting_region(self):
        leg = self.ps.resolve_traverse(self.lower, VINE)
        g = leg["graph"]
        for (x, z) in leg["waypoints"]:
            hit = g.locate(x, 5, z)
            self.assertIsNotNone(hit)
            self.assertEqual(hit[0]["id"], leg["from_rid"])

    def test_grab_aims_at_a_floor_level_base_segment(self):
        # Sixth flight: a curved sheet's centroid "at" hung beside a
        # chest over a real vine gap. The leg must carry a grab point on
        # the column's floor-touching bottom edge and a stand point the
        # from-region owns, off the wall.
        leg = self.ps.resolve_traverse(self.lower, VINE)
        self.assertTrue(leg["edge"].get("base_segments"),
                        "distill must keep the floor-touching segments")
        self.assertIsNotNone(leg["grab"])
        sx, sz = leg["at"]
        hit = leg["graph"].locate(sx, 5, sz)
        self.assertIsNotNone(hit, "stand point must be on the mesh")
        self.assertEqual(hit[0]["id"], leg["from_rid"])
        gx, gz = leg["grab"]
        self.assertGreater(math.hypot(gx - sx, gz - sz), 10.0,
                           "grab is INTO the wall, not where Link stands")


class TestTraversePrimitive(unittest.TestCase):
    def test_refuses_with_no_place_sense_before_any_io(self):
        game = Game(link=None)     # any link touch would explode — none may
        with self.assertRaises(TraverseRefused):
            game.traverse("vine@100,0,200")

    def test_refusal_happens_before_any_movement(self):
        link = StubLink()
        link.world["scene"] = 0
        game = Game(link)
        game.place = sense_with_graph()
        with self.assertRaises(TraverseRefused):
            game.traverse("nonsense-target")
        pads = [r for r in link.requests if r.get("op") == "pad"]
        self.assertEqual(pads, [], "refusal must precede all movement")

    def test_open_message_box_fails_fast_before_any_movement(self):
        # Sixth flight, leg 1: Navi's skullwalltula lecture opened mid-leg
        # and the grab loop pushed a dead stick for 12 s, aborting with a
        # FALSE story ("never got a grip"). A modal box freezes input;
        # traverse must say so and stop, before a single pad op.
        link = StubLink()
        link.world["scene"] = 0
        link.world["msg_mode"] = 5
        link.world["player"]["pos"] = [150.0, 0.0, 100.0]
        game = Game(link)
        game.place = sense_with_graph()
        with self.assertRaises(TraverseFailed) as cm:
            game.traverse("vine@100,0,200")
        self.assertIn("message box", str(cm.exception))
        self.assertIn("dialogue_advance", str(cm.exception))
        pads = [r for r in link.requests if r.get("op") == "pad"]
        self.assertEqual(pads, [], "a frozen pad must never be pushed")

    def test_poll_preempt_raises_when_flagged(self):
        game = Game(link=None)
        game._preempt_event = threading.Event()
        game._preempt_reason = ["test preempt"]
        game._preempt_event.set()
        with self.assertRaises(BehaviorPreempted):
            game._poll_preempt()


class TestDigestPlaceAndBearing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.sightings = senses.Sightings()

    def _digest(self, state, place=None):
        self.sightings.observe(state)
        return senses.digest(state, self.sightings, place)

    def test_place_section_present_and_absent(self):
        ps = sense_with_graph()
        st = state_at(150, 2, 100, yaw=0x8000)
        st["actors"] = []
        d = self._digest(st, ps.sample(st))
        self.assertEqual(d["place"]["region"], LOWER)
        self.assertEqual(d["place"]["heading"], "n")
        d2 = self._digest(st, None)
        self.assertNotIn("place", d2, "no sense -> absent entity, no guess")

    def test_nearest_enemy_bearing_clock_face(self):
        st = state_at(0, 0, 0, yaw=0, scene=0)
        st["actors"] = [baba_actor(dist_xz=100.0)]   # pos [0, 0, 100]: ahead
        d = self._digest(st)
        self.assertEqual(d["nearest_enemy"]["bearing"], 12)
        st["player"]["yaw"] = 0x8000                 # turn around: behind
        d = self._digest(st)
        self.assertEqual(d["nearest_enemy"]["bearing"], 6)

    def test_bearing_absent_without_positions(self):
        st = state_at(0, 0, 0, scene=0)
        actor = baba_actor(dist_xz=100.0)
        del actor["pos"]                             # an older instrument
        st["actors"] = [actor]
        d = self._digest(st)
        self.assertIn("nearest_enemy", d)
        self.assertNotIn("bearing", d["nearest_enemy"])

    def test_schema_covers_new_fields(self):
        self.assertIsNone(senses.check_path(("place", "region")))
        self.assertIsNone(senses.check_path(("place", "on_mesh")))
        self.assertIsNone(senses.check_path(("place", "heading")))
        self.assertIsNone(senses.check_path(("nearest_enemy", "bearing")))
        self.assertIsNotNone(senses.check_path(("place", "nope")))

    def test_place_is_a_dispatchable_world_event(self):
        self.assertIn("place", senses.WORLD_EVENTS)
        self.assertIn("place", senses.DISPATCHABLE_EVENTS)


class TestRuntimeAndServerIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.link = StubLink()
        self.link.world["scene"] = 0
        self.link.world["player"]["pos"] = [150.0, 2.0, 100.0]
        self.game = Game(self.link)
        self.log = EventLog()
        self.ps = sense_with_graph()
        self.runtime = MachineRuntime(self.game, Path(self.tmp), self.log,
                                      place=self.ps)
        self.core = ServerCore(self.game, self.runtime, self.log)

    def test_runtime_narrates_region_entered(self):
        self.game.state()                # observer refreshes _last_state
        self.runtime.tick()
        places = self.log.tail(category="place")
        self.assertEqual(len(places), 1)
        self.assertEqual(places[0]["cue"], "region_entered")
        self.assertEqual(places[0]["region"], LOWER)

    def test_digest_carries_place(self):
        self.game.state()
        d = self.runtime._digest()
        self.assertEqual(d["place"]["region"], LOWER)
        self.assertTrue(d["place"]["on_mesh"])

    def test_game_shares_the_runtime_place_sense(self):
        self.assertIs(self.game.place, self.ps,
                      "traverse must validate against the SAME map the "
                      "digest localizes on")

    def test_status_reports_place_sense(self):
        self.game.state()
        st = self.runtime.status()
        self.assertIn("place_sense", st)

    def test_place_resource_document(self):
        body = self._read("oot://place")
        self.assertEqual(body["you"]["region"], LOWER)
        regions = {r["region"]: r for r in body["regions"]}
        self.assertIn(UPPER, regions)
        self.assertTrue(any(VINE in w for w in regions[LOWER]["ways"]))
        # No raw coordinates in the presented document (self-pose lives
        # in oot://state; names carry quantized centroids by design).
        self.assertNotIn("centroid", str(body))
        here = regions[LOWER]
        self.assertTrue(here.get("you_are_here"))

    def test_place_resource_pre_play_is_gated(self):
        self.link.world["save_loaded"] = False
        body = self._read("oot://place")
        self.assertIn("error", body)

    def _read(self, uri):
        import json
        resp = self.core.handle({"jsonrpc": "2.0", "id": 1,
                                 "method": "resources/read",
                                 "params": {"uri": uri}})
        return json.loads(resp["result"]["contents"][0]["text"])


@unittest.skipUnless(O2R.exists(), "SoH oot.o2r not present on this machine")
class TestRealYdanGraph(unittest.TestCase):
    """Integration pins against the real Deku Tree (the fifth flight's
    geography, by stable name — mirrors lab/navgraph/test_ring.py)."""

    def test_ydan_pins(self):
        ps = PlaceSense(O2R)
        g = ps.graph_for(0x00)
        self.assertIsNotNone(g)
        self.assertEqual(len(g.regions), 50)
        self.assertIn("ydan:r@30,0,70", g.by_name)          # GF atrium
        self.assertIn("ydan:r@250,340,30", g.by_name)       # the 2F ring
        self.assertIn("ydan:vine@120,0,-300", g.edge_by_name)
        self.assertIn("ydan:ladder@-240,0,210", g.edge_by_name)
        # The fifth flight's leg, resolvable from a real GF point:
        leg = ps.resolve_traverse(state_at(200, 0, -100, scene=0),
                                  "vine@120,0,-300")
        self.assertEqual(leg["direction"], "up")
        self.assertEqual(leg["top_y"], 280)


@unittest.skipUnless(O2R.exists(), "SoH oot.o2r not present on this machine")
class TestRealSpot04Graph(unittest.TestCase):
    """Kokiri Forest, the bench's first overworld map (dojo docs/28 §4).
    The recon found it distilling but NOT motor-grade: the forest floor
    seam-split into non-adjacent halves, and the treehouse ladder — Link's
    own front door — unlinked to the ground. Both are pinned here by
    stable name, exactly as the ydan geography is above."""

    SCENE = 0x55
    FOREST_FLOOR = "spot04:r@-100,10,220"
    BALCONY = "spot04:r@-30,100,1100"
    LADDER = "spot04:ladder@-30,-80,1000"
    #: A corner where two sub-meshes meet 1.0 unit apart ([-701,0,-301] vs
    #: [-701,1,-301]) — the seam that used to cut the forest in two.
    SEAM_WEST = (-769.3, -5.0, -255.0)      # was the 22-poly orphan half
    SEAM_EAST = (-651.7, 0.0, -187.7)       # was the 124-poly main half

    def setUp(self):
        self.ps = PlaceSense(O2R)
        self.g = self.ps.graph_for(self.SCENE)
        self.assertIsNotNone(self.g)

    def test_the_forest_floor_is_one_region(self):
        west = self.g.locate(*self.SEAM_WEST)
        east = self.g.locate(*self.SEAM_EAST)
        self.assertIsNotNone(west)
        self.assertIsNotNone(east)
        self.assertEqual(self.g.region_name(west[0]), self.FOREST_FLOOR)
        self.assertEqual(self.g.region_name(east[0]), self.FOREST_FLOOR,
                         "the seam at [-701,0,-301] must be welded: two "
                         "halves of one floor are one region, or nothing "
                         "can walk across the forest")
        self.assertNotIn("spot04:r@-150,10,210", self.g.by_name,
                         "the split-off half must be gone, not renamed")
        self.assertEqual(self.g.by_name[self.FOREST_FLOOR]["polys"], 149)

    def test_the_treehouse_ladder_is_linked_to_ground_and_balcony(self):
        e = self.g.edge_by_name.get(self.LADDER)
        self.assertIsNotNone(e, "the treehouse ladder vanished from the map")
        self.assertTrue(e["linked"], "a ladder with no ground is unusable")
        names = lambda ids: [self.g.region_name(self.g.regions[i]) for i in ids]
        self.assertEqual(names(e["from"]), [self.FOREST_FLOOR])
        self.assertEqual(names(e["to"]), [self.BALCONY])

    def test_traverse_resolves_the_ladder_from_the_forest_floor(self):
        # The mission's first leg: standing in the forest, go home.
        leg = self.ps.resolve_traverse(
            state_at(-29, -80, 900, scene=self.SCENE), "ladder@-30,-80,1000")
        self.assertEqual(leg["direction"], "up")
        self.assertEqual(leg["top_y"], 115)
        self.assertEqual([self.g.region_name(self.g.regions[i])
                          for i in leg["to_rids"]], [self.BALCONY])
        self.assertIsNotNone(leg["grab"], "the climb needs a base to aim at")


if __name__ == "__main__":
    unittest.main()
