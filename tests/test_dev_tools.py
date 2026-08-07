"""The dev harness (0.12.0, dojo docs/33): the flag, the verbs, and the
three commitments that keep the SURFACE.md amendment honest.

Most of this file is about ABSENCE. A cheat family is only acceptable
because it cannot be reached from the play surface, cannot be hidden
once used, and cannot be pointed at a scored repo — so the tests that
matter most are the ones asserting that a server without the flag is
byte-identical to a server that never heard of dev mode.
"""

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ocarina import OCARINA_VERSION, dev, senses, server
from ocarina.events import EventLog
from ocarina.game import Game
from ocarina.identity import load_identity
from ocarina.machine import load_machine
from ocarina.runtime import MachineRuntime
from ocarina.server import TOOLS, ServerCore

from .stubgame import StubLink
from .test_stdio_smoke import StdioCase

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "save-file"
REPO_ROOT = Path(__file__).parent.parent


class DevCase(unittest.TestCase):
    """A server core with the dev harness on (subclasses flip it off)."""

    dev_mode = True

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = Path(self.tmp) / "save-file"
        shutil.copytree(FIXTURE_REPO, self.repo)
        self.link = StubLink()
        self.game = Game(self.link)
        self.log = EventLog(persist_path=self.repo / "journal" / "mechanical.jsonl")
        self.runtime = MachineRuntime(self.game, self.repo, self.log)
        self.runtime.load()
        self.dev = dev.DevTools(self.game) if self.dev_mode else None
        if self.dev is not None:
            self.dev.warp_timeout_s = 2.0
            self.dev.warp_poll_s = 0.02
            self.dev.staged_timeout_s = 1.0
        self.core = ServerCore(self.game, self.runtime, self.log,
                               dev_tools=self.dev)

    def tearDown(self):
        self.runtime.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def rpc(self, method, params=None, msg_id=1):
        return self.core.handle({"jsonrpc": "2.0", "id": msg_id,
                                 "method": method, "params": params or {}})

    def call_tool(self, name, arguments=None):
        return self.rpc("tools/call", {"name": name,
                                       "arguments": arguments or {}})["result"]

    def body(self, result):
        return json.loads(result["content"][0]["text"])

    def journal(self):
        path = self.log.persist_path
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]


class TestAbsenceHolds(DevCase):
    """Commitment 1, the half a test can prove: without the flag the
    verbs are not listed, not stubbed, and not dispatchable."""

    dev_mode = False

    def test_dev_tools_are_absent_from_the_list(self):
        tools = {t["name"] for t in self.rpc("tools/list")["result"]["tools"]}
        for name in dev.TOOL_NAMES:
            self.assertNotIn(name, tools)
        self.assertFalse([t for t in tools if t.startswith("dev_")])

    def test_the_default_surface_is_exactly_the_blessed_list(self):
        # Not "contains what we expect" — IS the constant. A dev bump
        # that leaked one verb into the default surface fails here.
        self.assertEqual(self.rpc("tools/list")["result"]["tools"], TOOLS)
        self.assertFalse([t for t in TOOLS if t["name"].startswith("dev_")])

    def test_calling_one_is_an_unknown_tool(self):
        # Not a NOT_YET, not a permission error: the server does not know
        # this verb, and says so in the same words it uses for a typo.
        result = self.call_tool("dev_warp", {"entrance": 0})
        self.assertTrue(result["isError"])
        self.assertIn("unknown tool", result["content"][0]["text"])
        self.assertEqual(self.link.dev_sent, [], "nothing reached the wire")

    def test_status_says_nothing_about_dev_mode(self):
        self.assertNotIn("dev_mode", self.body(self.call_tool("status")))

    def test_no_dev_marks_in_the_journal(self):
        self.assertFalse([e for e in self.journal()
                          if e["event"] in ("dev_mode", "dev_cheat")])

    def test_game_py_grows_nothing(self):
        # THE commitment (docs/33 #1): behaviors are written against Game,
        # so a cheat that is not on Game cannot be named by a behavior, a
        # guard, or any machine source — which is why MACHINE.md is
        # untouched by this version.
        for name in dir(Game):
            self.assertNotIn("teleport", name)
            self.assertNotIn("warp", name)
            self.assertFalse(name.startswith("dev"))
        source = (REPO_ROOT / "ocarina" / "game.py").read_text()
        self.assertNotIn("import dev", source)
        self.assertNotIn("from .dev", source)

    def test_the_behavior_path_never_imports_dev(self):
        # Importing what a behavior imports must not drag the dev module
        # into the process at all.
        probe = ("import sys, ocarina.game, ocarina.behavior;"
                 "print('ocarina.dev' in sys.modules)")
        out = subprocess.run([sys.executable, "-c", probe], cwd=REPO_ROOT,
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.stdout.strip(), "False", out.stderr)


class TestFlagOn(DevCase):
    def test_the_verbs_register(self):
        tools = {t["name"]: t for t in self.rpc("tools/list")["result"]["tools"]}
        for name in ("dev_teleport", "dev_warp"):
            self.assertIn(name, tools)
        self.assertEqual(tools["dev_teleport"]["inputSchema"]["required"],
                         ["x", "y", "z"])
        self.assertEqual(tools["dev_warp"]["inputSchema"]["required"],
                         ["entrance"])
        # The blessed surface is still all there, unchanged, underneath.
        self.assertEqual(self.rpc("tools/list")["result"]["tools"][:len(TOOLS)],
                         TOOLS)

    def test_status_reports_dev_mode(self):
        body = self.body(self.call_tool("status"))
        self.assertTrue(body["dev_mode"])
        self.assertEqual(body["ocarina_version"], OCARINA_VERSION)

    def test_teleport_returns_the_arrived_world_not_the_reply(self):
        # Asked for y=-40; the floor snapped it on arrival. The position
        # reported is the WORLD's, read after the reload — the op's own
        # reply is staging-time truth and proves nothing about what the
        # world became (docs/08).
        body = self.body(self.call_tool("dev_teleport",
                                        {"x": 12.5, "y": -40.0, "z": -3.0}))
        self.assertTrue(body["ok"], body)
        self.assertEqual(body["requested"], [12.5, -40.0, -3.0])
        self.assertEqual(body["pos"], [12.5, 0.0, -3.0])
        self.assertEqual(self.link.world["player"]["pos"], [12.5, 0.0, -3.0])
        self.assertEqual(body["loads"], 2, "a teleport IS a scene reload")
        self.assertIsInstance(body["waited_s"], float)

    def test_teleport_polls_the_staged_op(self):
        self.link.teleport_script = [{"status": "try_again"}]
        body = self.body(self.call_tool("dev_teleport",
                                        {"x": 1.0, "y": 2.0, "z": 3.0}))
        self.assertTrue(body["ok"], body)
        self.assertEqual(body["pos"], [1.0, 2.0, 3.0])
        self.assertEqual(len(self.link.dev_sent), 2, "one try_again round")

    def test_teleport_waits_for_the_world_to_re_enter_play(self):
        # The whole 0.12.2 shape: the op stages, the reload lands a few
        # reads later, and only then does the tool answer.
        self.link.warp_delay_polls = 3
        before = list(self.link.world["player"]["pos"])
        body = self.body(self.call_tool("dev_teleport",
                                        {"x": 5.0, "y": 6.0, "z": 7.0}))
        self.assertTrue(body["ok"], body)
        self.assertEqual(body["pos"], [5.0, 6.0, 7.0])
        self.assertEqual(body["loads"], 2)
        self.assertNotEqual(before, self.link.world["player"]["pos"])

    def test_teleport_times_out_naming_the_reload(self):
        # Staged, never arrived: the tool says what it last SAW and names
        # the likely cause (an instrument whose teleport is the old
        # in-place position write, which never ticks `loads`).
        self.dev.warp_timeout_s = 0.3
        self.link.warp_delay_polls = 10_000     # the reload never lands
        result = self.call_tool("dev_teleport", {"x": 1, "y": 2, "z": 3})
        self.assertTrue(result["isError"])
        text = result["content"][0]["text"]
        self.assertIn("never re-entered play", text)
        self.assertIn("`loads` counter is still 1", text)
        self.assertIn(dev.DEV_FW_PATCH, text)

    def test_teleport_refuses_an_instrument_without_loads(self):
        # No `loads` means no arrival to check, and an instrument that
        # old has the OLD teleport anyway — so this refuses instead of
        # trusting the echo, and nothing is sent (0.6.0, harder).
        del self.link.world["loads"]
        result = self.call_tool("dev_teleport", {"x": 1.0, "y": 2.0, "z": 3.0})
        self.assertTrue(result["isError"])
        text = result["content"][0]["text"]
        self.assertIn("no `loads` counter", text)
        self.assertIn("rebuild SoH", text)
        self.assertIn(dev.DEV_FW_PATCH, text)
        self.assertEqual(self.link.dev_sent, [], "nothing reached the wire")

    def test_teleport_sets_the_facing_through_the_respawn_record(self):
        body = self.body(self.call_tool(
            "dev_teleport", {"x": 1.0, "y": 2.0, "z": 3.0, "yaw": 0x4000}))
        self.assertTrue(body["ok"], body)
        self.assertEqual(self.link.dev_sent[0]["yaw"], 0x4000)
        self.assertEqual(body["yaw"], 0x4000)
        self.assertEqual(self.link.world["player"]["yaw"], 0x4000)

    def test_teleport_without_a_yaw_keeps_the_one_link_has(self):
        self.link.world["player"]["yaw"] = 0x1234
        body = self.body(self.call_tool("dev_teleport",
                                        {"x": 1.0, "y": 2.0, "z": 3.0}))
        self.assertNotIn("yaw", self.link.dev_sent[0])
        self.assertEqual(body["yaw"], 0x1234, "the record's resolved yaw")

    def test_teleport_refuses_a_non_integer_yaw(self):
        result = self.call_tool("dev_teleport",
                                {"x": 0, "y": 0, "z": 0, "yaw": "north"})
        self.assertTrue(result["isError"])
        self.assertIn("integer binang", result["content"][0]["text"])
        self.assertEqual(self.link.dev_sent, [])

    def test_an_instrument_that_echoed_no_yaw_says_so(self):
        self.link.teleport_script = [{"x": 1.0, "y": 2.0, "z": 3.0, "room": 0}]
        body = self.body(self.call_tool(
            "dev_teleport", {"x": 1.0, "y": 2.0, "z": 3.0, "yaw": 0x4000}))
        self.assertTrue(body["ok"], body)
        self.assertNotIn("yaw", body)
        self.assertIn("IGNORED", body["diagnostic"])
        self.assertIn(dev.DEV_FW_PATCH, body["diagnostic"])

    def test_teleport_surfaces_the_entrance_refusal_by_name(self):
        # -19: Link is standing somewhere whose entranceIndex is a
        # grotto/shop return sentinel, so there is no entrance to respawn
        # through and the whole op is meaningless. The game's words, as
        # they came.
        self.link.entrance_index = 0x7FFF
        result = self.call_tool("dev_teleport", {"x": 0, "y": 0, "z": 0})
        self.assertTrue(result["isError"])
        text = result["content"][0]["text"]
        self.assertIn("entrance out of range", text)
        self.assertIn("0x7FFF", text)

    def test_the_entrance_refusal_is_not_dressed_up_as_a_room_problem(self):
        # A -19 with a room argument in flight must not read as "the room
        # was the problem": only the -18 refusal earns that sentence.
        self.link.entrance_index = 0x7FFF
        result = self.call_tool("dev_teleport",
                                {"x": 0, "y": 0, "z": 0, "room": 1})
        text = result["content"][0]["text"]
        self.assertIn("entrance out of range", text)
        self.assertNotIn("asked for room", text)

    def test_teleport_refuses_non_numeric_coordinates(self):
        result = self.call_tool("dev_teleport", {"x": 1.0, "z": 3.0})
        self.assertTrue(result["isError"])
        self.assertIn("numeric x, y and z", result["content"][0]["text"])
        self.assertEqual(self.link.dev_sent, [])

    def test_teleport_passes_the_games_refusal_through_by_name(self):
        self.link.teleport_script = [
            {"status": "failure",
             "error": "a scene transition is already in progress"}]
        result = self.call_tool("dev_teleport", {"x": 0, "y": 0, "z": 0})
        self.assertTrue(result["isError"])
        self.assertIn("scene transition is already in progress",
                      result["content"][0]["text"])

    def test_warp_arrival_is_the_worlds_word(self):
        self.link.warp_delay_polls = 2      # the scene loads a few reads later
        body = self.body(self.call_tool("dev_warp", {"entrance": 0}))
        self.assertTrue(body["ok"])
        self.assertEqual(body["scene_from"], 85)
        self.assertEqual(body["scene"], 0)      # Inside the Deku Tree
        self.assertEqual(self.link.world["scene"], 0)
        self.assertEqual([p["entrance"] for p in self.link.dev_sent], [0])

    def test_warp_accepts_an_entrance_written_as_hex(self):
        # 0x272 = 626, Link's house — the form a human reads off
        # entrance_table.h. (529 is Kokiri Forest, where this stub
        # already is: a same-scene entrance is unobservable, which the
        # timeout test below is about.)
        body = self.body(self.call_tool("dev_warp", {"entrance": "0x272"}))
        self.assertTrue(body["ok"])
        self.assertEqual(self.link.dev_sent[0]["entrance"], 626)
        self.assertEqual(body["scene"], 52)

    def test_warp_refuses_a_non_index(self):
        result = self.call_tool("dev_warp", {"entrance": "the maze"})
        self.assertTrue(result["isError"])
        self.assertIn("integer entrance index", result["content"][0]["text"])
        self.assertEqual(self.link.dev_sent, [])

    def test_warp_times_out_honestly(self):
        # Accepted by the instrument, never arrived: the tool must say
        # what it last SAW, never claim the op's own success. (The two
        # timeout texts — loads and the old scene watch — are pinned in
        # TestWarpArrivalRidesTheLoadsCounter.)
        self.link.warp_script = [{"entrance": 0, "staged": True}]
        result = self.call_tool("dev_warp", {"entrance": 0})
        self.assertTrue(result["isError"])
        text = result["content"][0]["text"]
        self.assertIn("never re-entered play", text)
        self.assertIn("scene 85", text)

    def test_an_old_instrument_answers_loudly(self):
        self.link.warp_script = [{"status": "failure",
                                  "error": "unknown agent op 'warp'"}]
        result = self.call_tool("dev_warp", {"entrance": 0})
        self.assertTrue(result["isError"])
        self.assertIn("rebuild SoH", result["content"][0]["text"])
        self.assertIn(dev.DEV_PATCH, result["content"][0]["text"])

    def test_a_stuck_frame_hook_is_not_a_hang(self):
        self.dev.staged_timeout_s = 0.3
        self.link.teleport_script = [{"status": "try_again"}] * 50
        result = self.call_tool("dev_teleport", {"x": 0, "y": 0, "z": 0})
        self.assertTrue(result["isError"])
        self.assertIn("pending past", result["content"][0]["text"])

    def test_teleport_reports_the_room_it_ended_in(self):
        # Nobody asked for a room: the respawn record resolves it to the
        # one Link is in, and the reply says so — "where am I now" is the
        # question a live test asks next.
        body = self.body(self.call_tool("dev_teleport",
                                        {"x": 1.0, "y": 2.0, "z": 3.0}))
        self.assertEqual(body["room"], 0)
        self.assertNotIn("room_requested", body)
        self.assertNotIn("room", self.link.dev_sent[0])

    def test_a_disconnected_game_is_a_clean_error(self):
        self.link._connected = False
        result = self.call_tool("dev_teleport", {"x": 0, "y": 0, "z": 0})
        self.assertTrue(result["isError"])
        self.assertIn("game not connected", result["content"][0]["text"])


class TestWarpArrivalRidesTheLoadsCounter(DevCase):
    """The first live pass's seam #1 (2026-08-07 evening): an entrance
    leading back into the CURRENT scene performs the whole reload, and
    the scene id never moves — so the arrival watch was blind to it and
    timed out on a warp that had already worked. Arrival is now the
    instrument's `loads` counter (every play-state init ticks it), with
    the old scene watch kept as a loudly-diagnosed fallback."""

    def test_a_same_scene_warp_arrives(self):
        # 529 is Kokiri Forest — where the stub already is.
        self.link.warp_delay_polls = 2
        body = self.body(self.call_tool("dev_warp", {"entrance": 529}))
        self.assertTrue(body["ok"], body)
        self.assertEqual((body["scene_from"], body["scene"]), (85, 85))
        self.assertTrue(body["same_scene"])
        self.assertEqual(body["arrival"], "loads")
        self.assertEqual(body["loads"], 2)
        self.assertNotIn("diagnostic", body)

    def test_a_cross_scene_warp_still_reports_both_ends(self):
        body = self.body(self.call_tool("dev_warp", {"entrance": 0}))
        self.assertTrue(body["ok"], body)
        self.assertEqual((body["scene_from"], body["scene"]), (85, 0))
        self.assertEqual(body["arrival"], "loads")
        self.assertNotIn("same_scene", body, "only said when they match")

    def test_the_loads_path_times_out_naming_the_counter(self):
        self.link.warp_script = [{"entrance": 0, "staged": True}]
        result = self.call_tool("dev_warp", {"entrance": 0})
        self.assertTrue(result["isError"])
        text = result["content"][0]["text"]
        self.assertIn("never re-entered play", text)
        self.assertIn("`loads` counter is still 1", text)

    def test_an_old_instrument_falls_back_and_says_so(self):
        # No `loads` on the wire: arrival is the scene id again, and the
        # reply carries the diagnostic (0.6.0 — never silently obeyed).
        del self.link.world["loads"]
        body = self.body(self.call_tool("dev_warp", {"entrance": 0}))
        self.assertTrue(body["ok"], body)
        self.assertEqual(body["scene"], 0)
        self.assertEqual(body["arrival"], "scene_change")
        self.assertIn("no `loads` counter", body["diagnostic"])
        self.assertIn(dev.DEV_ROOM_PATCH, body["diagnostic"])
        self.assertNotIn("loads", body)

    def test_an_old_instruments_same_scene_timeout_names_the_missing_field(self):
        del self.link.world["loads"]
        result = self.call_tool("dev_warp", {"entrance": 529})
        self.assertTrue(result["isError"])
        text = result["content"][0]["text"]
        self.assertIn("still scene 85", text)
        self.assertIn("`loads` counter", text)
        self.assertIn("already in", text)      # the same-scene caveat
        self.assertIn(dev.DEV_ROOM_PATCH, text)


class TestTeleportCrossesARoom(DevCase):
    """Seam #2: rooms only load through the door/holl actors, so a
    teleport across a room boundary left the destination's geometry
    unloaded (Kokiri Forest is three rooms). The room now rides the
    respawn record, and the reload loads it like any door does."""

    def test_the_room_argument_is_optional_in_the_schema(self):
        tools = {t["name"]: t for t in self.rpc("tools/list")["result"]["tools"]}
        schema = tools["dev_teleport"]["inputSchema"]
        self.assertEqual(schema["required"], ["x", "y", "z"])
        self.assertEqual(schema["properties"]["room"]["type"], "integer")
        self.assertIn("respawn record",
                      schema["properties"]["room"]["description"])
        self.assertEqual(schema["properties"]["yaw"]["type"], "integer")
        self.assertIn("binang", schema["properties"]["yaw"]["description"])

    def test_the_room_rides_the_wire_and_comes_back(self):
        body = self.body(self.call_tool(
            "dev_teleport", {"x": 1.0, "y": 2.0, "z": 3.0, "room": 2}))
        self.assertTrue(body["ok"], body)
        self.assertEqual(self.link.dev_sent[0]["room"], 2)
        self.assertEqual((body["room_requested"], body["room"]), (2, 2))
        self.assertEqual(self.link.world["room"], 2)
        self.assertNotIn("diagnostic", body)

    def test_an_impossible_room_is_the_games_refusal_by_name(self):
        result = self.call_tool("dev_teleport",
                                {"x": 0, "y": 0, "z": 0, "room": 7})
        self.assertTrue(result["isError"])
        text = result["content"][0]["text"]
        self.assertIn("no room 7", text)
        self.assertIn("valid rooms are 0-2", text)   # the game's own range
        self.assertIn("asked for room 7", text)
        self.assertEqual(self.link.world["room"], 0, "nothing moved")

    def test_a_non_integer_room_is_refused_before_the_wire(self):
        result = self.call_tool("dev_teleport",
                                {"x": 0, "y": 0, "z": 0, "room": "the shop"})
        self.assertTrue(result["isError"])
        self.assertIn("integer room number", result["content"][0]["text"])
        self.assertEqual(self.link.dev_sent, [])

    def test_an_old_instrument_that_ignored_the_room_says_so(self):
        # An instrument that drops the unknown key and teleports anyway
        # produces the exact glitch the argument exists to prevent, so
        # the silence is what has to be caught (0.6.0).
        self.link.teleport_script = [{"x": 1.0, "y": 2.0, "z": 3.0}]
        del self.link.world["room"]
        body = self.body(self.call_tool(
            "dev_teleport", {"x": 1.0, "y": 2.0, "z": 3.0, "room": 1}))
        self.assertTrue(body["ok"], body)
        self.assertNotIn("room", body)
        self.assertIn("IGNORED", body["diagnostic"])
        self.assertIn(dev.DEV_FW_PATCH, body["diagnostic"])


class TestTheMarkIsPermanent(DevCase):
    """Commitment 2: dev use is structurally un-hideable."""

    def test_every_call_journals_its_arguments(self):
        self.call_tool("dev_teleport", {"x": 1.0, "y": 2.0, "z": 3.0})
        marks = [e for e in self.journal() if e["event"] == "dev_cheat"]
        self.assertEqual(len(marks), 1)
        self.assertEqual(marks[0]["tool"], "dev_teleport")
        self.assertEqual(marks[0]["args"], {"x": 1.0, "y": 2.0, "z": 3.0})

    def test_a_failed_call_still_leaves_its_mark(self):
        # The mark goes down BEFORE the op runs, so a refusal, a crash or
        # a pulled cable cannot erase the fact that a cheat was attempted.
        self.link.warp_script = [{"status": "failure", "error": "nope"}]
        result = self.call_tool("dev_warp", {"entrance": 626})
        self.assertTrue(result["isError"])
        marks = [e for e in self.journal() if e["event"] == "dev_cheat"]
        self.assertEqual([m["args"] for m in marks], [{"entrance": 626}])

    def test_a_refused_argument_still_leaves_its_mark(self):
        self.call_tool("dev_warp", {"entrance": "the maze"})
        self.assertTrue([e for e in self.journal() if e["event"] == "dev_cheat"])

    def test_the_banner_journals_on_every_attach(self):
        # The rehydrate path is where a mark gets lost: a server that was
        # already up when the game dialled in must still mark that world.
        self.runtime.dev_banner = dev.banner_event("connect")
        self.runtime.tick()
        banners = [e for e in self.journal() if e["event"] == "dev_mode"]
        self.assertEqual(len(banners), 1)
        self.assertEqual(banners[0]["cue"], "enabled")
        self.assertEqual(banners[0]["at"], "connect")
        self.assertEqual(banners[0]["tools"], list(dev.TOOL_NAMES))

    def test_no_banner_without_the_flag(self):
        self.runtime.tick()
        self.assertFalse([e for e in self.journal() if e["event"] == "dev_mode"])

    def test_the_machine_cannot_react_to_a_dev_event(self):
        # The banner and the marks are journal-only: they never go
        # through the runtime's event dispatch, and machine.py validates
        # every `on:` against DISPATCHABLE_EVENTS at load — so no
        # transition can even be WRITTEN against a cheat (commitment 1,
        # from the other end).
        for name in ("dev_mode", "dev_cheat"):
            self.assertNotIn(name, senses.DISPATCHABLE_EVENTS)


class TestScoredRepoRefusesTheFlag(unittest.TestCase):
    """Commitment 3: a scored repo refuses --dev-tools, loudly, before
    any connection is made."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = Path(self.tmp) / "save-file"
        shutil.copytree(FIXTURE_REPO, self.repo)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def declare(self, body: dict) -> None:
        (self.repo / "identity.json").write_text(json.dumps(body))

    def run_main(self, *extra):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = server.main(["--repo", str(self.repo), *extra])
        return code, err.getvalue()

    def test_scored_true_refuses(self):
        self.declare({"scored": True, "save_slot": 1, "save_name": "C",
                      "fingerprint": {}})
        code, err = self.run_main("--dev-tools")
        self.assertEqual(code, 2)
        self.assertIn("REFUSING", err)
        self.assertIn(str(self.repo), err)          # names the repo
        self.assertIn("scored", err)                # names the declaration
        self.assertIn("slot 1", err)

    def test_scored_false_is_no_refusal(self):
        self.declare({"scored": False, "fingerprint": {}})
        self.assertIsNone(dev.scored_refusal(self.repo))

    def test_no_declaration_is_no_refusal(self):
        self.assertIsNone(dev.scored_refusal(self.repo))

    def test_a_declaration_without_the_key_is_no_refusal(self):
        self.declare({"save_slot": 0, "fingerprint": {}})
        self.assertIsNone(dev.scored_refusal(self.repo))
        self.assertIsNone(load_identity(self.repo).scored)

    def test_an_unreadable_declaration_fails_closed(self):
        (self.repo / "identity.json").write_text("{ not json")
        refusal = dev.scored_refusal(self.repo)
        self.assertIsNotNone(refusal)
        self.assertIn("cannot prove it is not scored", refusal)

    def test_a_nonsense_scored_value_fails_closed(self):
        self.declare({"scored": "yes", "fingerprint": {}})
        refusal = dev.scored_refusal(self.repo)
        self.assertIsNotNone(refusal)
        self.assertIn("true or false", refusal)

    def test_the_scored_repo_runs_normally_without_the_flag(self):
        # The refusal is about the FLAG, not about the repo: a scored
        # line is exactly the repo a real flight runs.
        self.declare({"scored": True, "fingerprint": {}})
        port = _free_port()
        out = subprocess.run(
            [sys.executable, "-m", "ocarina", "--repo", str(self.repo),
             "--port", str(port)],
            cwd=REPO_ROOT, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_the_refusal_exits_nonzero_through_the_real_entry_point(self):
        self.declare({"scored": True, "fingerprint": {}})
        out = subprocess.run(
            [sys.executable, "-m", "ocarina", "--repo", str(self.repo),
             "--port", str(_free_port()), "--dev-tools"],
            cwd=REPO_ROOT, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, timeout=60)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("REFUSING", out.stderr)
        self.assertEqual(out.stdout, "", "stdout is the MCP pipe: keep it clean")

    def test_the_flag_shouts_and_banners_at_boot(self):
        out = subprocess.run(
            [sys.executable, "-m", "ocarina", "--repo", str(self.repo),
             "--port", str(_free_port()), "--dev-tools"],
            cwd=REPO_ROOT, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("DEV MODE", out.stderr)
        self.assertEqual(out.stdout, "", "stdout is the MCP pipe: keep it clean")
        journal = [json.loads(line) for line in
                   (self.repo / "journal" / "mechanical.jsonl").read_text().splitlines()]
        banners = [e for e in journal if e["event"] == "dev_mode"]
        self.assertEqual([b["at"] for b in banners], ["boot"])
        self.assertIn("dev_cheat", banners[0]["text"])


class TestDevOverRealPipes(StdioCase):
    """The dev harness through the whole stack: a real server process
    under `--dev-tools`, a real MCP conversation, and the fakegame
    answering both staged ops over real TCP. The in-process tests above
    prove the logic; this proves the argparse wiring, the registration,
    and the journal that lands in the repo."""

    EXTRA_ARGS = ("--dev-tools",)

    def test_the_dev_verbs_end_to_end(self):
        self.rpc("initialize", {"protocolVersion": "2025-06-18"})
        tools = {t["name"] for t in self.rpc("tools/list")["tools"]}
        self.assertIn("dev_teleport", tools)
        self.assertIn("dev_warp", tools)
        self.assertTrue(self.call_tool("status")["dev_mode"])

        fake = self.start_fake()

        # Teleport: staged (one try_again round over the pipes), a real
        # reload, and the position is the ARRIVED world's — the fake
        # floors at y=0, so a request below it comes back snapped.
        loads_before = fake.loads
        body = self.call_tool("dev_teleport", {"x": 40.0, "y": -12.0, "z": 70.0})
        self.assertTrue(body["ok"], body)
        self.assertEqual(body["pos"], [40.0, 0.0, 70.0])
        self.assertEqual(fake.teleports, [[40.0, -12.0, 70.0]])
        self.assertEqual(fake.player["z"], 70.0)
        self.assertGreater(fake.loads, loads_before, "a teleport reloads")
        self.assertEqual(body["loads"], fake.loads)

        # Warp: the op stages, and only the WORLD says it arrived. 0 is
        # Inside the Deku Tree; the fake starts in Kokiri Forest (85).
        body = self.call_tool("dev_warp", {"entrance": 0})
        self.assertTrue(body["ok"], body)
        self.assertEqual((body["scene_from"], body["scene"]), (85, 0))
        self.assertEqual(fake.warps, [0])
        digest = self.rpc("resources/read", {"uri": "oot://state"})
        self.assertEqual(json.loads(digest["contents"][0]["text"])["scene"], 0)

        # Seam #1 over real pipes: entrance 0 leads back into the scene
        # the world is NOW in, so the scene id cannot show the reload —
        # the loads counter can.
        body = self.call_tool("dev_warp", {"entrance": 0})
        self.assertTrue(body["ok"], body)
        self.assertTrue(body["same_scene"])
        self.assertEqual(body["arrival"], "loads")
        self.assertEqual(fake.warps, [0, 0])

        # Seam #2: the room rides the wire into the respawn record, and
        # the reply says which room the world came back in. The yaw rides
        # the same record.
        body = self.call_tool("dev_teleport",
                              {"x": 0.0, "y": 0.0, "z": 0.0, "room": 2,
                               "yaw": 0x4000})
        self.assertTrue(body["ok"], body)
        self.assertEqual((body["room_requested"], body["room"]), (2, 2))
        self.assertEqual(body["yaw"], 0x4000)
        self.assertEqual(fake.teleport_rooms, [None, 2])
        self.assertEqual((fake.room, fake.yaw), (2, 0x4000))

        # The permanent record: banner at boot AND at the attach, one
        # mark per call, arguments included.
        journal = self.journal()
        self.assertEqual([e["at"] for e in journal if e["event"] == "dev_mode"],
                         ["boot", "connect"])
        marks = [e for e in journal if e["event"] == "dev_cheat"]
        self.assertEqual([m["tool"] for m in marks],
                         ["dev_teleport", "dev_warp", "dev_warp",
                          "dev_teleport"])
        self.assertEqual(marks[1]["args"], {"entrance": 0})
        self.assertEqual(marks[3]["args"]["room"], 2)
        self.assertEqual(marks[3]["args"]["yaw"], 0x4000)


class TestLiveHarnessRepo(unittest.TestCase):
    """tests/live builds its own throwaway repo. It only runs against
    the real game, so nothing else would catch it rotting — load its
    machine here, offline, every time the suite runs."""

    def test_the_live_repos_machine_loads_clean(self):
        from .live import harness
        tmp = tempfile.mkdtemp()
        try:
            repo = harness.make_repo(Path(tmp))
            machine, diags = load_machine(repo)
            self.assertIsNotNone(machine)
            self.assertEqual([d.as_dict() for d in diags
                              if d.level == "error"], [])
            self.assertIsNone(load_identity(repo),
                              "a dev repo declares nothing (check OFF)")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def _free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


if __name__ == "__main__":
    unittest.main()
