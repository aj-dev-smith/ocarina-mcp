"""Live e2e: the dev harness against the REAL game (0.12.0, docs/33;
teleport's truth model rewritten for 0.12.2).

These are the first tests in the family the dev harness exists for.
They assert the two verbs do what they claim — and they assert it off
the WORLD, never off the op's own reply: BOTH verbs only stage a
transition, and only `oot://state` can say the world became that place
(docs/08's oldest rule, the one the HUD's `draws` counter taught).

Skipped instantly unless OCARINA_LIVE=1; see harness.py and README.md
for the three gates. Nothing here is scored play: the server runs under
--dev-tools against a throwaway repo, and its journal says so.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from . import harness

#: Entrance indices from soh's entrance_table.h. A cross-scene warp is
#: observable as a scene change, so that test picks a target that is NOT
#: where Link already is; the same-scene test below picks the opposite.
KOKIRI_FOREST_FROM_LINKS_HOUSE = 529
INSIDE_THE_DEKU_TREE = 0
LINKS_HOUSE = 626

#: Scene ids the same-scene warp test knows an entrance back INTO.
KOKIRI_FOREST_SCENE = 85
DEKU_TREE_SCENE = 0

#: Kokiri Forest is three rooms (0/1/2) — the scene the cross-room
#: teleport pin uses, because that shape is exactly what broke: rooms
#: only load through the door/holl actors, so a teleport across one
#: without the room argument leaves the destination unloaded.
KOKIRI_ROOMS = (0, 1, 2)


def setUpModule():
    harness.require_live()


class LiveDevCase(unittest.TestCase):
    """One server, one game, one throwaway repo for the whole class."""

    @classmethod
    def setUpClass(cls):
        harness.require_live()
        harness.require_free_sail_port()
        cls.tmp = tempfile.mkdtemp()
        cls.repo = harness.make_repo(Path(cls.tmp))
        cls.server = harness.LiveServer(cls.repo).start()
        try:
            cls.server.await_game()
        except BaseException:
            cls.server.stop()
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def pose(self) -> dict:
        """Link's exact position, off the wire. Rides `place.*`, which
        needs the server's --o2r; without it there is no honest
        position sense to check the reply against, so the test says so
        and skips rather than asserting something weaker."""
        place = self.server.state().get("place")
        if place is None or "x" not in place:
            self.skipTest("no place sense (start with --o2r / OCARINA_O2R) — "
                          "nothing to cross-check the reply against")
        return place

    def counters(self) -> dict:
        """The world's `room` and `loads`, read back through a dev verb.

        The curated digest carries neither, on purpose: a room number
        and a load count are harness plumbing, not narration, and the
        play surface is not where they belong. So the honest reading is
        the dev reply's own — a teleport to where Link already stands.
        Since 0.12.2 that is not free: every teleport is a real scene
        reload through the respawn path, so this READ costs a load (and
        bumps the very counter it reports). Call it at the edges of a
        test, never in a loop.

        An instrument predating the respawn teleport REFUSES rather than
        answering, and these tests SKIP on that: nothing here may say
        anything about the code under test (harness.py's discipline)."""
        here = self.pose()
        result = self.server.call_raw("dev_teleport", {"x": here["x"],
                                                       "y": here["y"],
                                                       "z": here["z"]})
        text = result["content"][0]["text"]
        if result.get("isError"):
            if "rebuild SoH" in text:
                self.skipTest(
                    f"this instrument predates the respawn-path teleport "
                    f"(ocarina.dev.DEV_FW_PATCH) — rebuild SoH; until then "
                    f"there is nothing here to test: {text}")
            raise AssertionError(f"dev_teleport refused: {text}")
        body = json.loads(text)
        missing = [f for f in ("loads", "room") if body.get(f) is None]
        if missing:
            self.skipTest(
                f"this instrument's reply carries no {', '.join(missing)} — "
                f"rebuild SoH with the room/loads AgentLink patch "
                f"(ocarina.dev.DEV_ROOM_PATCH); until then a same-scene "
                f"reload is invisible and a cross-room teleport cannot be "
                f"asked for")
        return body


class TestDevWarpArrives(LiveDevCase):
    def test_warp_lands_where_the_world_says_it_landed(self):
        before = self.server.state()["scene"]
        entrance = (KOKIRI_FOREST_FROM_LINKS_HOUSE if before == 0
                    else INSIDE_THE_DEKU_TREE)
        body = self.server.call("dev_warp", {"entrance": entrance})
        self.assertTrue(body["ok"], body)
        # The assertion that matters: a FRESH read of the world, not the
        # tool's word for it.
        after = self.server.state()["scene"]
        self.assertNotEqual(after, before, "the scene never changed")
        self.assertEqual(after, body["scene"],
                         "the tool reported an arrival the world disagrees with")


class TestDevWarpReloadsTheSameScene(LiveDevCase):
    """The seam the first live pass found (2026-08-07 evening): an
    entrance leading back into the scene Link is ALREADY in performs the
    whole reload — and the arrival watch, comparing scene ids, sat there
    until it timed out on a warp that had already worked. The pin is the
    world re-entering play (`loads`), not the scene id moving."""

    def test_a_warp_back_into_the_current_scene_is_seen_as_an_arrival(self):
        before_loads = self.counters()["loads"]
        scene = self.server.state()["scene"]
        entrance = {KOKIRI_FOREST_SCENE: KOKIRI_FOREST_FROM_LINKS_HOUSE,
                    DEKU_TREE_SCENE: INSIDE_THE_DEKU_TREE}.get(scene)
        if entrance is None:
            self.skipTest(
                f"no entrance back into scene {scene} is known here — put "
                f"Link in Kokiri Forest ({KOKIRI_FOREST_SCENE}) or inside "
                f"the Deku Tree ({DEKU_TREE_SCENE}) and re-run")
        body = self.server.call("dev_warp", {"entrance": entrance})
        self.assertTrue(body["ok"], body)
        self.assertEqual(body["arrival"], "loads",
                         "arrival was judged the old, scene-id way")
        self.assertTrue(body.get("same_scene"),
                        "the whole point of this pin is the same-scene case")
        # And the world's own word, freshly read, on both halves: the
        # scene is where it was, and the world genuinely re-entered play.
        self.assertEqual(self.server.state()["scene"], scene)
        self.assertGreater(self.counters()["loads"], before_loads,
                           "the reload never happened")


class TestDevTeleportCrossesARoom(LiveDevCase):
    """The other seam: rooms only load through the door/holl actors, so
    a teleport across a room boundary left the destination's geometry
    and actors unloaded — Kokiri Forest is three rooms, which is how it
    was found. The room now rides the respawn record, and the reload
    loads it exactly as a door transition would."""

    def test_the_room_argument_is_the_room_the_world_ends_in(self):
        room_before = self.counters()["room"]
        scene = self.server.state()["scene"]
        if scene != KOKIRI_FOREST_SCENE or room_before not in KOKIRI_ROOMS:
            self.skipTest(
                f"this pin knows one scene's rooms: put Link in Kokiri "
                f"Forest (scene {KOKIRI_FOREST_SCENE}, rooms "
                f"{KOKIRI_ROOMS}) — the world is in scene {scene}, room "
                f"{room_before}")
        target = next(r for r in KOKIRI_ROOMS if r != room_before)
        here = self.pose()
        home = {"x": here["x"], "y": here["y"], "z": here["z"]}
        try:
            # Link's own position, a different room: the pin is about the
            # ROOM the world holds, and choosing a plausible position
            # inside another room would need a map this test has no
            # business carrying.
            body = self.server.call("dev_teleport", {**home, "room": target})
            self.assertTrue(body["ok"], body)
            self.assertEqual(body["room_requested"], target)
            self.assertEqual(body["room"], target,
                             "the respawn record disagrees with the request")
            self.assertEqual(self.counters()["room"], target,
                             "a fresh read says the world is in another room")
        finally:
            self.server.call_raw("dev_teleport", {**home, "room": room_before})


class TestDevTeleportMoves(LiveDevCase):
    """The truth model, rewritten for 0.12.2: the reply is the RESPAWN
    RECORD's word at staging time (requested position, resolved room and
    yaw), arrival is a real scene reload, and what a test may assert
    afterwards is that the world Link arrived in is NEAR the request —
    the FW path places him at the recorded position and physics settles
    him onto the floor from there."""

    def test_teleport_moves_link_and_the_world_arrives_near_the_request(self):
        start = self.pose()
        home = (start["x"], start["y"], start["z"])
        # 50 units along z, in the room Link is already in: the room the
        # respawn record takes defaults to the one he is in, so this pin
        # needs no map.
        target = {"x": home[0], "y": home[1], "z": home[2] + 50.0}
        try:
            body = self.server.call("dev_teleport", target)
            self.assertTrue(body["ok"], body)
            self.assertEqual(body["requested"],
                             [target["x"], target["y"], target["z"]])
            after = self.pose()
            # NEAR, not exact, and deliberately so. The respawn path puts
            # Link at the recorded position, then the game does what it
            # does on any door arrival: snap to the floor, nudge him out
            # of a wall or a prop the target happened to sit in (a
            # ~10-unit push-out was observed live 2026-08-07). "Arrived
            # about where I asked, within physics" is the verb's honest
            # contract; exactness on arbitrary ground is not.
            for axis, value in (("x", target["x"]), ("z", target["z"])):
                self.assertAlmostEqual(
                    after[axis], value, delta=25.0,
                    msg=f"the world's {axis} is nowhere near the request")
            self.assertAlmostEqual(
                after["y"], target["y"], delta=40.0,
                msg="Link settled somewhere far from the floor he asked for")
            moved = abs(after["z"] - home[2])
            self.assertGreater(moved, 1.0, "Link did not move at all")
            # And the reply's own claims about the reload, cross-checked
            # against the world it left behind.
            self.assertIsNotNone(body.get("loads"), body)
            self.assertIn("room", body)
        finally:
            self.server.call_raw("dev_teleport",
                                 {"x": home[0], "y": home[1], "z": home[2]})

    def test_the_reply_carries_the_records_resolved_room_and_yaw(self):
        here = self.pose()
        home = {"x": here["x"], "y": here["y"], "z": here["z"]}
        facing = 0x4000                       # a quarter turn, in binang
        try:
            body = self.server.call("dev_teleport", {**home, "yaw": facing})
            self.assertTrue(body["ok"], body)
            self.assertEqual(body["yaw"], facing,
                             "the respawn record did not take the yaw")
            self.assertIn("room", body, "no resolved room in the reply")
            self.assertNotIn("diagnostic", body, body.get("diagnostic"))
        finally:
            self.server.call_raw("dev_teleport", home)


class TestTheMarkIsPermanentLive(LiveDevCase):
    def test_the_repos_journal_carries_the_banner_and_every_cheat(self):
        self.server.call("dev_teleport", dict(zip("xyz", (
            self.pose()["x"], self.pose()["y"], self.pose()["z"]))))
        journal = self.server.journal()
        banners = [e for e in journal if e["event"] == "dev_mode"]
        self.assertTrue(banners, "no dev_mode banner in the journal")
        self.assertIn("boot", [b.get("at") for b in banners])
        self.assertIn("connect", [b.get("at") for b in banners],
                      "the attach is exactly where a mark gets lost")
        marks = [e for e in journal if e["event"] == "dev_cheat"]
        self.assertTrue(marks, "no dev_cheat mark for calls that were made")
        self.assertTrue(all("args" in m for m in marks))
        self.assertTrue(self.server.call("status")["dev_mode"])


if __name__ == "__main__":
    unittest.main()
