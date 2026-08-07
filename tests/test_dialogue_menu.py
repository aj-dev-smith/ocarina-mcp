"""0.8.0 (dojo docs/27): dialogue text on the wire, save_game, use_item.

Covers the digest's `dialogue` entity, the runtime's dialogue fold (ui
cues + the recent-texts ring + the old-instrument diagnostic), the three
graduated tools, the three graduated resources, and traverse's quoting
fail-fast. The wire shapes come from the 2026-08-04 DojoLink patch;
StubLink models the choice cursor and the staged save/assign_c ops.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from ocarina import senses, server
from ocarina.events import EventLog
from ocarina.game import Game
from ocarina.place import TraverseFailed
from ocarina.protocol import BTN_A
from ocarina.runtime import MachineRuntime
from ocarina.server import ServerCore

from .stubgame import StubLink

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "save-file"

NAVI_BOX = {"text": "Look at the wall!\nYou can climb vines.",
            "state": "awaiting_advance", "text_id": 0x0123}
CHOICE_BOX = {"text": "Would you like to save?",
              "state": "choice", "text_id": 0x0BB9,
              "choices": ["Yes", "No"], "choice_index": 0}


class DialogueCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = Path(self.tmp) / "save-file"
        shutil.copytree(FIXTURE_REPO, self.repo)
        self.link = StubLink()
        self.game = Game(self.link)
        self.log = EventLog(persist_path=self.repo / "journal" / "mechanical.jsonl")
        self.runtime = MachineRuntime(self.game, self.repo, self.log)
        self.runtime.load()
        self.core = ServerCore(self.game, self.runtime, self.log)

    def tearDown(self):
        self.runtime.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call_tool(self, name, arguments=None):
        return self.core.handle(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": name, "arguments": arguments or {}}})["result"]

    def tool_body(self, result):
        return json.loads(result["content"][0]["text"])

    def read(self, uri):
        result = self.core.handle(
            {"jsonrpc": "2.0", "id": 1, "method": "resources/read",
             "params": {"uri": uri}})["result"]
        return json.loads(result["contents"][0]["text"])

    def open_box(self, box):
        self.link.world["msg_mode"] = 6
        self.link.world["message"] = dict(box)

    def close_box(self):
        self.link.world["msg_mode"] = 0
        self.link.world.pop("message", None)


class TestDialogueDigest(DialogueCase):
    def test_entity_present_with_text(self):
        self.open_box(NAVI_BOX)
        body = self.read("oot://state")
        self.assertTrue(body["dialogue_open"])
        self.assertEqual(body["dialogue"]["text"], NAVI_BOX["text"])
        self.assertEqual(body["dialogue"]["state"], "awaiting_advance")
        self.assertNotIn("choices", body["dialogue"])

    def test_entity_absent_when_no_box(self):
        body = self.read("oot://state")
        self.assertFalse(body["dialogue_open"])
        self.assertNotIn("dialogue", body)

    def test_entity_absent_on_old_instrument(self):
        # msg_mode set, no message block: the entity never guesses.
        self.link.world["msg_mode"] = 6
        body = self.read("oot://state")
        self.assertTrue(body["dialogue_open"])
        self.assertNotIn("dialogue", body)

    def test_choice_box_carries_choices(self):
        self.open_box(CHOICE_BOX)
        body = self.read("oot://state")
        self.assertEqual(body["dialogue"]["choices"], ["Yes", "No"])
        self.assertEqual(body["dialogue"]["choice_index"], 0)

    def test_unreadable_text_is_absent_not_faked(self):
        self.open_box({"text": None, "state": "opening", "text_id": 7})
        body = self.read("oot://state")
        self.assertEqual(body["dialogue"]["state"], "opening")
        self.assertNotIn("text", body["dialogue"])


class TestDialogueFold(DialogueCase):
    def events(self, cue=None):
        evs = [e for e in self.log.tail(n=100) if e.get("event") == "ui"]
        return [e for e in evs if cue is None or e.get("cue") == cue]

    def tick(self):
        self.game.state()      # refresh _last_state via the observer
        self.runtime.tick()

    def test_opened_and_closed_cues(self):
        self.open_box(NAVI_BOX)
        self.tick()
        opened = self.events("dialogue_opened")
        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0]["text"], NAVI_BOX["text"])
        self.tick()    # standing box: no re-narration
        self.assertEqual(len(self.events("dialogue_opened")), 1)
        self.close_box()
        self.tick()
        self.assertEqual(len(self.events("dialogue_closed")), 1)

    def test_ring_feeds_the_resource(self):
        self.open_box(NAVI_BOX)
        self.tick()
        self.close_box()
        self.tick()
        body = self.read("oot://dialogue")
        self.assertFalse(body["open"])
        self.assertEqual(body["recent"][-1]["text"], NAVI_BOX["text"])
        self.assertEqual(body["recent"][-1]["text_id"], NAVI_BOX["text_id"])

    def test_box_sequence_lands_each_text(self):
        self.open_box(NAVI_BOX)
        self.tick()
        self.open_box({"text": "You got the Dungeon Map!",
                       "state": "done", "text_id": 0x0055})
        self.tick()
        recent = self.read("oot://dialogue")["recent"]
        self.assertEqual([e["text"] for e in recent[-2:]],
                         [NAVI_BOX["text"], "You got the Dungeon Map!"])

    def test_old_instrument_diagnoses_once(self):
        self.link.world["msg_mode"] = 6    # no message block
        self.tick()
        self.tick()
        diags = [e for e in self.log.tail(n=100)
                 if e.get("event") == "diagnostic"
                 and "predates the dialogue sense" in e.get("text", "")]
        self.assertEqual(len(diags), 1)


class FakeChoiceBox:
    """A choice box that answers the tool's own inputs — the dialogue-side
    twin of test_kokiri_slate's FakeShop, typewriter included.

    A fresh box reads "displaying" for `typing_frames` state polls, and
    while it does the game reads neither the stick nor the A: an A there
    only fast-forwards the text (Message_Update's TEXT_STATE_CHOICE gate).
    `eat_a` swallows that many SETTLED presses and re-issues the box —
    the ninth flight's "chose ok, still needed an advance" and the tenth
    flight's two further sightings, modelled.
    """

    def __init__(self, link, box, typing_frames=0, eat_a=0,
                 never_settles=False):
        self.link, self.box = link, dict(box)
        self.typing_frames, self.never_settles = typing_frames, never_settles
        self.eat_a = eat_a
        self.a_presses = self.fast_forwards = self.commits = 0
        self.chose = None
        self._link_request = link.request
        link.request = self.on_request
        link.pad_hook = self.on_pad
        self.show()

    def show(self):
        self.typing = float("inf") if self.never_settles else self.typing_frames
        msg = dict(self.box)
        msg["state"] = "displaying" if self.typing else self.box["state"]
        self.link.world["msg_mode"] = 6
        self.link.world["message"] = msg

    def settle(self):
        self.typing = 0
        (self.link.world.get("message") or {})["state"] = self.box["state"]

    def on_request(self, payload, link_timeout=5.0):
        op = payload.get("op")
        if op == "state" and self.typing:
            # Every state read is a frame: the box types itself out under
            # whoever is polling it.
            self.typing -= 1
            if not self.typing:
                self.settle()
            return self._link_request(payload, link_timeout)
        if op == "pad" and not payload.get("clear") and self.typing:
            frozen = (self.link.world.get("message") or {}).get("choice_index")
            res = self._link_request(payload, link_timeout)
            msg = self.link.world.get("message") or {}
            if frozen is not None:
                msg["choice_index"] = frozen         # the stick was eaten
            if payload.get("buttons", 0) & BTN_A:
                self.a_presses += 1
                self.fast_forwards += 1
                self.settle()                        # A only fast-forwards
            return res
        return self._link_request(payload, link_timeout)

    def on_pad(self, payload, link):
        if payload.get("clear") or not (payload.get("buttons", 0) & BTN_A):
            return
        if self.typing:
            return                  # handled in on_request: the box ate it
        self.a_presses += 1
        if self.eat_a:
            # The press landed as the box re-issued itself: lost, and the
            # choice is still on screen (typing again).
            self.eat_a -= 1
            self.show()
            return
        self.commits += 1
        self.chose = (link.world.get("message") or {}).get("choice_index", 0)
        link.world["msg_mode"] = 0
        link.world.pop("message", None)


class ChoiceBoxCase(DialogueCase):
    """dialogue_choose over a box that answers, with the live-tuned waits
    shrunk to test speed (SlateCase's discipline)."""

    FAST = {"_NUDGE_HOLD_S": 0.0, "_NUDGE_GAP_S": 0.0, "_BUY_POLL_S": 0.0,
            "_CHOOSE_BOX_TIMEOUT_S": 0.05, "_CHOOSE_COMMIT_TIMEOUT_S": 0.05}

    def setUp(self):
        super().setUp()
        self._slow = {name: getattr(server, name) for name in self.FAST}
        for name, fast in self.FAST.items():
            setattr(server, name, fast)

    def tearDown(self):
        for name, value in self._slow.items():
            setattr(server, name, value)
        super().tearDown()

    def fake_box(self, box=None, **kw):
        return FakeChoiceBox(self.link, box or CHOICE_BOX, **kw)


class TestDialogueChoose(ChoiceBoxCase):
    def test_choose_nudges_to_target_and_confirms(self):
        box = self.fake_box()
        result = self.call_tool("dialogue_choose", {"option": 1})
        self.assertFalse(result["isError"], result["content"][0]["text"])
        body = self.tool_body(result)
        self.assertEqual(body["chose"], 1)
        self.assertEqual(body["label"], "No")
        # The cursor really moved (the stub models the game's own
        # stick handling), and A confirmed it on that option.
        self.assertEqual(box.chose, 1)
        self.assertEqual(box.commits, 1)
        pads = [r for r in self.link.requests if r.get("op") == "pad"]
        self.assertTrue(any(r.get("stick", [0, 0])[1] < 0 for r in pads))

    def test_choose_current_option_needs_no_nudge(self):
        box = self.fake_box()
        result = self.call_tool("dialogue_choose", {"option": 0})
        self.assertFalse(result["isError"], result["content"][0]["text"])
        self.assertEqual(box.chose, 0)
        sticks = [r for r in self.link.requests
                  if r.get("op") == "pad" and r.get("stick") not in (None, [0, 0])]
        self.assertEqual(sticks, [])

    # -- the typewriter (docs/29: the choice that needed a second press) --

    def test_waits_out_the_typewriter_before_touching_the_box(self):
        box = self.fake_box(typing_frames=3)
        result = self.call_tool("dialogue_choose", {"option": 1})
        self.assertFalse(result["isError"], result["content"][0]["text"])
        # Nothing it nudged or pressed landed inside the typing window,
        # and the choice went through on the first press.
        self.assertEqual(box.fast_forwards, 0)
        self.assertEqual(box.a_presses, 1)
        self.assertEqual(box.chose, 1)

    def test_swallowed_a_is_retried_until_the_choice_lands(self):
        box = self.fake_box(typing_frames=1, eat_a=1)
        result = self.call_tool("dialogue_choose", {"option": 1})
        self.assertFalse(result["isError"], result["content"][0]["text"])
        self.assertEqual(box.a_presses, 2)      # the first press was eaten
        self.assertEqual(box.commits, 1)
        self.assertEqual(box.chose, 1)
        self.assertFalse(self.tool_body(result)["dialogue_open"])

    def test_box_that_never_settles_refuses_before_any_press(self):
        box = self.fake_box(never_settles=True)
        result = self.call_tool("dialogue_choose", {"option": 0})
        self.assertTrue(result["isError"])
        text = result["content"][0]["text"]
        self.assertIn("never finished typing", text)
        self.assertIn("0xBB9", text)              # it names the box it waited on
        self.assertEqual(box.a_presses, 0)

    def test_choice_that_never_commits_is_never_ok(self):
        box = self.fake_box(eat_a=5)
        result = self.call_tool("dialogue_choose", {"option": 0})
        self.assertTrue(result["isError"])
        text = result["content"][0]["text"]
        self.assertIn("still on screen", text)
        self.assertIn("Would you like to save?", text)     # it quotes the box
        self.assertEqual(box.a_presses, 2)                 # one retry, no more
        self.assertEqual(box.commits, 0)


class TestDialogueChooseRefusals(DialogueCase):
    def test_wrong_screen_errors(self):
        result = self.call_tool("dialogue_choose", {"option": 0})
        self.assertTrue(result["isError"])
        self.assertIn("no dialogue is open", result["content"][0]["text"])
        self.open_box(NAVI_BOX)    # a box, but not a choice box
        result = self.call_tool("dialogue_choose", {"option": 0})
        self.assertTrue(result["isError"])
        self.assertIn("no choice is being offered", result["content"][0]["text"])

    def test_out_of_range_errors(self):
        self.open_box(CHOICE_BOX)
        result = self.call_tool("dialogue_choose", {"option": 5})
        self.assertTrue(result["isError"])
        self.assertIn("out of range", result["content"][0]["text"])


class TestSaveGame(DialogueCase):
    def test_save_succeeds_and_is_verified(self):
        result = self.call_tool("save_game")
        self.assertFalse(result["isError"], result["content"][0]["text"])
        self.assertTrue(self.tool_body(result)["saved"])
        self.assertEqual(self.link.saves, 1)

    def test_save_polls_through_try_again(self):
        self.link.save_script = [{"status": "try_again"}]
        result = self.call_tool("save_game")
        self.assertFalse(result["isError"])
        self.assertEqual(self.link.saves, 1)

    def test_named_refusal_surfaces(self):
        self.link.save_script = [
            {"status": "failure",
             "error": "pause menu unavailable (cutscene, transition, "
                      "game over, or minigame)"}]
        result = self.call_tool("save_game")
        self.assertTrue(result["isError"])
        self.assertIn("pause menu unavailable", result["content"][0]["text"])
        self.assertEqual(self.link.saves, 0)

    def test_old_instrument_names_the_rebuild(self):
        self.link.save_script = [
            {"status": "failure", "error": "unknown agent op: save"}]
        result = self.call_tool("save_game")
        self.assertTrue(result["isError"])
        self.assertIn("rebuild SoH", result["content"][0]["text"])


class TestUseItem(DialogueCase):
    def arm_inventory(self):
        self.link.world["equips"] = {"b": 0x3B, "c_left": 0xFF,
                                     "c_down": 0xFF, "c_right": 0xFF,
                                     "worn": 0x11, "owned": 0x11}
        self.link.world["inventory"] = {
            "items": [0x00, 0x01] + [0xFF] * 22,
            "ammo": [3, 5] + [0] * 14}

    def test_assigns_then_presses(self):
        self.arm_inventory()
        result = self.call_tool("use_item", {"item": "deku_nut"})
        self.assertFalse(result["isError"], result["content"][0]["text"])
        body = self.tool_body(result)
        self.assertEqual(body["button"], "C_LEFT")
        self.assertEqual(body["ammo_before"], 5)
        # The assignment went through the instrument's own commit...
        assigns = [r for r in self.link.requests if r.get("op") == "assign_c"]
        self.assertEqual(assigns, [{"type": "agent", "op": "assign_c",
                                    "item": 0x01, "button": 0}])
        self.assertEqual(self.link.world["equips"]["c_left"], 0x01)
        # ...and a real C press followed.
        from ocarina.protocol import BTN_CLEFT
        pads = [r for r in self.link.requests if r.get("op") == "pad"]
        self.assertTrue(any(r.get("buttons", 0) & BTN_CLEFT for r in pads))

    def test_already_assigned_skips_assignment(self):
        self.arm_inventory()
        self.link.world["equips"]["c_right"] = 0x01
        result = self.call_tool("use_item", {"item": "deku_nut"})
        self.assertFalse(result["isError"])
        self.assertEqual(self.tool_body(result)["button"], "C_RIGHT")
        self.assertEqual([r for r in self.link.requests
                          if r.get("op") == "assign_c"], [])

    def test_unknown_item_names_the_vocabulary(self):
        result = self.call_tool("use_item", {"item": "megaton_hammer"})
        self.assertTrue(result["isError"])
        self.assertIn("deku_nut", result["content"][0]["text"])

    def test_old_instrument_named(self):
        # No equips block on the wire at all.
        result = self.call_tool("use_item", {"item": "deku_nut"})
        self.assertTrue(result["isError"])
        self.assertIn("rebuild SoH", result["content"][0]["text"])

    def test_refuses_while_uncontrollable(self):
        self.arm_inventory()
        self.link.world["equips"]["c_left"] = 0x01
        self.link.world["msg_mode"] = 6
        self.link.world["message"] = dict(NAVI_BOX)
        result = self.call_tool("use_item", {"item": "deku_nut"})
        self.assertTrue(result["isError"])
        self.assertIn("not controllable", result["content"][0]["text"])


class TestMenuDocuments(DialogueCase):
    def test_items_document(self):
        self.link.world["equips"] = {"b": 0x3B, "c_left": 0x01,
                                     "c_down": 0xFF, "c_right": 0xFF,
                                     "worn": 0x11, "owned": 0x11}
        self.link.world["inventory"] = {
            "items": [0x00, 0x01] + [0xFF] * 22,
            "ammo": [3, 5] + [0] * 14}
        body = self.read("oot://menu/items")
        self.assertEqual(body["items"],
                         [{"slot": 0, "item": "deku_stick", "ammo": 3},
                          {"slot": 1, "item": "deku_nut", "ammo": 5}])
        self.assertEqual(body["buttons"]["c_left"], "deku_nut")

    def test_equipment_document(self):
        self.link.world["equips"] = {"b": 0x3B, "c_left": 0xFF,
                                     "c_down": 0xFF, "c_right": 0xFF,
                                     "worn": 0x11, "owned": 0x11}
        body = self.read("oot://menu/equipment")
        self.assertEqual(body["worn"]["sword"], "kokiri_sword")
        self.assertEqual(body["worn"]["shield"], "deku_shield")
        self.assertIsNone(body["worn"]["tunic"])
        self.assertEqual(body["owned"]["sword"], ["kokiri_sword"])

    def test_old_instrument_reads_blind(self):
        self.assertIn("blind", self.read("oot://menu/items"))
        self.assertIn("blind", self.read("oot://menu/equipment"))


class TestTraverseQuote(unittest.TestCase):
    def test_fail_fast_quotes_the_box(self):
        link = StubLink()
        game = Game(link)
        link.world["msg_mode"] = 6
        link.world["message"] = dict(NAVI_BOX)
        with self.assertRaises(TraverseFailed) as ctx:
            game._check_message_box("mid-walk")
        text = str(ctx.exception)
        self.assertIn("message box", text)
        self.assertIn("dialogue_advance", text)
        self.assertIn("You can climb vines.", text)


class TestChestState(unittest.TestCase):
    def test_spawn_narrates_lid_state(self):
        # Free play 2026-08-04: a body pressed A at an already-open chest,
        # twice — the lid state reads on sight, so the narration carries it.
        class NoSeen:
            def sight(self, kind):
                return False
        fresh = [{"id": 0x000A, "key": 1, "sighted": True, "opened": True},
                 {"id": 0x0055, "key": 2, "sighted": True}]
        events = senses.spawn_events(fresh, NoSeen())
        self.assertEqual(events[0]["kind"], "treasure_chest")
        self.assertEqual(events[0]["state"], "open")
        self.assertNotIn("state", events[1])


class TestEquipmentView(unittest.TestCase):
    def test_full_masks(self):
        view = senses.equipment_view({"worn": 0x1121, "owned": 0x7113})
        self.assertEqual(view["worn"],
                         {"sword": "kokiri_sword", "shield": "hylian_shield",
                          "tunic": "kokiri_tunic", "boots": "kokiri_boots"})
        self.assertEqual(view["owned"]["sword"],
                         ["kokiri_sword", "master_sword"])
        self.assertEqual(view["owned"]["boots"],
                         ["kokiri_boots", "iron_boots", "hover_boots"])


if __name__ == "__main__":
    unittest.main()
