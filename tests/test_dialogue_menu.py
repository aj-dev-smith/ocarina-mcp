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

from ocarina import senses
from ocarina.events import EventLog
from ocarina.game import Game
from ocarina.place import TraverseFailed
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


class TestDialogueChoose(DialogueCase):
    def test_choose_nudges_to_target_and_confirms(self):
        self.open_box(CHOICE_BOX)
        result = self.call_tool("dialogue_choose", {"option": 1})
        self.assertFalse(result["isError"], result["content"][0]["text"])
        body = self.tool_body(result)
        self.assertEqual(body["chose"], 1)
        self.assertEqual(body["label"], "No")
        # The cursor really moved (the stub models the game's own
        # stick handling), and A confirmed it.
        self.assertEqual(self.link.world["message"]["choice_index"], 1)
        pads = [r for r in self.link.requests if r.get("op") == "pad"]
        self.assertTrue(any(r.get("stick", [0, 0])[1] < 0 for r in pads))

    def test_choose_current_option_needs_no_nudge(self):
        self.open_box(CHOICE_BOX)
        result = self.call_tool("dialogue_choose", {"option": 0})
        self.assertFalse(result["isError"])
        sticks = [r for r in self.link.requests
                  if r.get("op") == "pad" and r.get("stick") not in (None, [0, 0])]
        self.assertEqual(sticks, [])

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
            {"status": "failure", "error": "unknown dojo op: save"}]
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
        self.assertEqual(assigns, [{"type": "dojo", "op": "assign_c",
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
