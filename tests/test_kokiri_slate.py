"""0.9.0 (dojo docs/28, the Kokiri slate): equip, buy, and the route's
vocabulary.

`equip` rides a new staged op (equip_gear) that is a mechanical twin of
assign_c; `buy` adds NO wire op at all — it drives En_Ossan's message-box
state machine with the same nudge-and-verify mechanic dialogue_choose
established. So the shop tests script BOXES, not memory: FakeShop answers
the tool's own inputs with the boxes the real shop would put on screen,
and every assertion is about what the tool did in response to what the
wire said.

The two live unknowns these tests cannot price (docs/28) are the nudge
timing against En_Ossan's stickAccumX thresholds, and whether
Player_SetEquipmentData mid-gameplay behaves with an item already out.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from ocarina import senses, server
from ocarina.events import EventLog
from ocarina.game import Game
from ocarina.protocol import ACTOR_EN_GIRLA, ACTOR_EN_ITEM00, BTN_A
from ocarina.runtime import MachineRuntime
from ocarina.server import ServerCore

from .stubgame import StubLink

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "save-file"


class SlateCase(unittest.TestCase):
    """Server core over StubLink, with buy's live-tuned waits shrunk to
    test speed (the constants are the thing tuning will move; the phases
    are the thing tests can pin)."""

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
        self._slow = {name: getattr(server, name) for name in
                      ("_NUDGE_HOLD_S", "_NUDGE_GAP_S", "_BUY_POLL_S",
                       "_BUY_BOX_TIMEOUT_S", "_BUY_OUTCOME_TIMEOUT_S")}
        for name, fast in (("_NUDGE_HOLD_S", 0.0), ("_NUDGE_GAP_S", 0.0),
                           ("_BUY_POLL_S", 0.0), ("_BUY_BOX_TIMEOUT_S", 0.05),
                           ("_BUY_OUTCOME_TIMEOUT_S", 0.3)):
            setattr(server, name, fast)

    def tearDown(self):
        for name, value in self._slow.items():
            setattr(server, name, value)
        self.runtime.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call_tool(self, name, arguments=None):
        return self.core.handle(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": name, "arguments": arguments or {}}})["result"]

    def tool_body(self, result):
        return json.loads(result["content"][0]["text"])

    def error(self, result):
        self.assertTrue(result["isError"], result["content"][0]["text"])
        return result["content"][0]["text"]

    def pads(self):
        return [r for r in self.link.requests if r.get("op") == "pad"]


# -- ITEM 1: equip -----------------------------------------------------------


class TestEquip(SlateCase):
    def arm(self, worn=0x00, owned=0x33, b=0xFF):
        self.link.world["equips"] = {"b": b, "c_left": 0xFF, "c_down": 0xFF,
                                     "c_right": 0xFF, "worn": worn,
                                     "owned": owned}

    def test_name_maps_to_row_and_value(self):
        self.arm()
        result = self.call_tool("equip", {"item": "hylian_shield"})
        self.assertFalse(result["isError"], result["content"][0]["text"])
        self.assertEqual(self.link.equips_sent,
                         [{"type": "agent", "op": "equip_gear",
                           "equip_type": 1, "value": 2}])
        body = self.tool_body(result)
        self.assertEqual(body["equipped"], "hylian_shield")
        self.assertEqual(body["slot"], "shield")
        self.assertEqual(body["worn"]["shield"], "hylian_shield")

    def test_sword_row_maps_to_type_zero(self):
        self.arm()
        result = self.call_tool("equip", {"item": "kokiri_sword"})
        self.assertFalse(result["isError"], result["content"][0]["text"])
        self.assertEqual(self.link.equips_sent[0]["equip_type"], 0)
        self.assertEqual(self.link.equips_sent[0]["value"], 1)

    def test_not_owned_refuses_before_the_op(self):
        self.arm(owned=0x01)     # kokiri sword only
        text = self.error(self.call_tool("equip", {"item": "deku_shield"}))
        self.assertIn("not owned", text)
        self.assertIn("shield row holds nothing", text)
        self.assertEqual(self.link.equips_sent, [])

    def test_unknown_gear_names_the_four_rows(self):
        self.arm()
        text = self.error(self.call_tool("equip", {"item": "mirror_shield_2"}))
        self.assertIn("unknown gear", text)
        for row in ("sword", "shield", "tunic", "boots"):
            self.assertIn(row, text)
        self.assertIn("hover_boots", text)
        self.assertEqual(self.link.equips_sent, [])

    def test_worn_mask_mismatch_is_not_a_success(self):
        self.arm()
        # The op claims success and writes nothing: the wire is the proof,
        # and here the wire disagrees with the op's own answer.
        original = self.link.request

        def request(payload, timeout=5.0):
            res = original(payload, timeout)
            if payload.get("op") == "equip_gear":
                self.link.world["equips"]["worn"] = 0x00
            return res
        self.link.request = request
        text = self.error(self.call_tool("equip", {"item": "deku_shield"}))
        self.assertIn("equip did not take", text)
        self.assertIn("shield row", text)

    def test_sword_without_b_is_a_half_commit(self):
        self.arm()
        original = self.link.request

        def request(payload, timeout=5.0):
            res = original(payload, timeout)
            if payload.get("op") == "equip_gear":
                self.link.world["equips"]["b"] = senses.ITEM_NONE
            return res
        self.link.request = request
        text = self.error(self.call_tool("equip", {"item": "kokiri_sword"}))
        self.assertIn("B button is still empty", text)

    def test_named_refusal_passes_through(self):
        self.arm()
        self.link.equip_script = [
            {"status": "failure",
             "error": "that equipment cannot be worn at this age"}]
        text = self.error(self.call_tool("equip", {"item": "hylian_shield"}))
        self.assertIn("cannot be worn at this age", text)

    def test_old_instrument_names_the_rebuild(self):
        self.arm()
        self.link.equip_script = [
            {"status": "failure", "error": "unknown agent op: equip_gear"}]
        text = self.error(self.call_tool("equip", {"item": "hylian_shield"}))
        self.assertIn("rebuild SoH", text)
        self.assertIn("2026-08-05", text)

    def test_no_equips_block_reads_blind(self):
        text = self.error(self.call_tool("equip", {"item": "deku_shield"}))
        self.assertIn("predates the equipment sense", text)
        self.assertEqual(self.link.equips_sent, [])


# -- ITEM 2: buy -------------------------------------------------------------

FACING = server.SHOP_FACING_BOX
GET_ITEM_BOX = 0x0043       # any "You got a ...!" box; the id is not steered


class FakeShop:
    """A miniature En_Ossan driven by the tool's own inputs.

    Two shelves either side of the shopkeeper; a stick nudge from the
    facing box enters one, further nudges walk it, and walking off the end
    returns to the shopkeeper — the loop buy() has to survive to reach an
    item on the far shelf. Every cursor move re-issues the slot's
    description box, which is the real game's behaviour
    (z_en_ossan.c:1287,1360) and the only reason cursor position is
    observable at all.
    """

    def __init__(self, link, right, left, outcome="fanfare", deduct=None,
                 hello=None):
        self.link, self.right, self.left = link, right, left
        self.outcome = outcome
        self.deduct = deduct
        self.side, self.index = None, 0
        self.phase = "hello" if hello else "browse"
        self.chose_continue = None
        link.pad_hook = self.on_pad
        link.world.setdefault("rupees", 100)
        link.world["actors"] = [
            {"id": ACTOR_EN_GIRLA, "params": senses.SHOP_CATALOG[name][0],
             "key": 900 + i, "cat": 6, "dist_xz": 90.0, "dist_y": 0.0,
             "health": 0, "sighted": True, "drawn": True}
            for i, name in enumerate(right + left)]
        self.show(hello if hello else FACING)

    # -- boxes ---------------------------------------------------------------

    def show(self, text_id, state="awaiting_advance", choices=None):
        msg = {"text": f"the box for 0x{text_id:X}", "state": state,
               "text_id": text_id}
        if choices is not None:
            msg["choices"], msg["choice_index"] = choices, 0
        self.link.world["msg_mode"] = 6
        self.link.world["message"] = msg

    def close(self):
        self.link.world["msg_mode"] = 0
        self.link.world.pop("message", None)

    def slots(self):
        return self.right if self.side == 1 else self.left

    def show_slot(self):
        name = self.slots()[self.index]
        self.show(senses.SHOP_CATALOG[name][2])

    # -- inputs --------------------------------------------------------------

    def on_pad(self, payload, link):
        if payload.get("clear"):
            return
        if payload.get("buttons", 0) & BTN_A:
            self.on_a()
            return
        stick = payload.get("stick") or [0, 0]
        if stick[0]:
            self.on_stick(1 if stick[0] > 0 else -1)

    def on_stick(self, direction):
        if self.phase != "browse":
            return
        if self.side is None:
            self.side, self.index = direction, 0
            if not self.slots():
                return                      # empty shelf: stay put
            self.show_slot()
            return
        self.index += 1
        if self.index >= len(self.slots()):
            self.side = None
            self.show(FACING)
        else:
            self.show_slot()

    def on_a(self):
        msg = self.link.world.get("message") or {}
        if self.phase == "hello":
            self.phase = "browse"
            self.show(FACING)
        elif self.phase == "browse" and self.side is not None:
            name = self.slots()[self.index]
            if name in getattr(self, "sold_out", ()):    # A does nothing
                return
            self.phase = "prompt"
            self.show(senses.SHOP_CATALOG[name][3], state="choice",
                      choices=["Buy", "No thanks"])
        elif self.phase == "prompt":
            if msg.get("choice_index", 0) != 0:
                self.phase = "browse"
                self.show_slot()
                return
            self.settle()
        elif self.phase == "getitem":
            self.pay()
            self.phase = "continue"
            self.show(server.SHOP_CONTINUE_BOX, state="choice",
                      choices=["Yes", "No"])
        elif self.phase == "continue":
            self.chose_continue = msg.get("choice_index", 0)
            self.phase = "done"
            self.close()
        elif self.phase in ("quick", "refused"):
            self.phase = "browse"
            self.show_slot()

    # -- the five endings ----------------------------------------------------

    def price(self):
        return senses.SHOP_CATALOG[self.slots()[self.index]][1]

    def pay(self):
        amount = self.price() if self.deduct is None else self.deduct
        self.link.world["rupees"] -= amount

    def settle(self):
        if self.outcome == "fanfare":
            self.phase = "getitem"
            self.show(GET_ITEM_BOX, state="done")
        elif self.outcome == "quick":
            self.pay()
            self.phase = "quick"
            self.show(server.SHOP_QUICK_BUY_BOXES[0])
        elif self.outcome == "need_rupees":
            self.phase = "refused"
            self.show(server.SHOP_NEED_RUPEES_BOX)
        elif self.outcome == "cant_get":
            self.phase = "refused"
            self.show(server.SHOP_CANT_GET_BOX)


class TestBuy(SlateCase):
    RIGHT = ["deku_shield", "deku_nuts_5"]
    LEFT = ["arrows_10", "recovery_heart"]

    def shop(self, **kw):
        self.link.world["rupees"] = kw.pop("rupees", 100)
        shop = FakeShop(self.link, kw.pop("right", self.RIGHT),
                        kw.pop("left", self.LEFT), **kw)
        return shop

    def test_fanfare_path_pays_and_leaves(self):
        shop = self.shop()
        result = self.call_tool("buy", {"item": "deku_shield"})
        self.assertFalse(result["isError"], result["content"][0]["text"])
        body = self.tool_body(result)
        self.assertEqual(body["item"], "deku_shield")
        self.assertEqual(body["price"], 40)
        self.assertEqual((body["rupees_before"], body["rupees_after"]),
                         (100, 60))
        self.assertEqual(body["path"], "fanfare")
        # It rode the get-item box (the A that commits the deduction) and
        # answered the continue-shopping question with "leave".
        self.assertEqual(shop.phase, "done")
        self.assertEqual(shop.chose_continue, 1)

    def test_keep_shopping_answers_yes(self):
        shop = self.shop()
        result = self.call_tool("buy", {"item": "deku_shield",
                                        "keep_shopping": True})
        self.assertFalse(result["isError"], result["content"][0]["text"])
        self.assertEqual(shop.chose_continue, 0)
        self.assertTrue(self.tool_body(result)["kept_shopping"])

    def test_quick_buy_path(self):
        self.shop(outcome="quick")
        result = self.call_tool("buy", {"item": "deku_nuts_5"})
        self.assertFalse(result["isError"], result["content"][0]["text"])
        body = self.tool_body(result)
        self.assertEqual(body["path"], "quick_buy")
        self.assertEqual(body["spent"], 15)

    def test_need_rupees_box_is_an_error(self):
        self.shop(outcome="need_rupees")
        text = self.error(self.call_tool("buy", {"item": "deku_shield"}))
        self.assertIn("cannot afford", text)
        self.assertIn("0x85", text)

    def test_cant_get_now_box_is_an_error(self):
        self.shop(outcome="cant_get")
        text = self.error(self.call_tool("buy", {"item": "deku_shield"}))
        self.assertIn("cannot take this now", text)
        self.assertIn("0x86", text)

    def test_sold_out_slot_refuses_selection(self):
        shop = self.shop()
        shop.sold_out = ("deku_shield",)
        text = self.error(self.call_tool("buy", {"item": "deku_shield"}))
        self.assertIn("slot refused selection", text)

    def test_walks_to_the_far_shelf_through_the_shopkeeper(self):
        shop = self.shop()
        result = self.call_tool("buy", {"item": "recovery_heart"})
        self.assertFalse(result["isError"], result["content"][0]["text"])
        self.assertEqual(self.tool_body(result)["spent"], 10)
        # It really turned around: both stick directions were used.
        xs = [r["stick"][0] for r in self.pads() if r.get("stick")]
        self.assertTrue(any(x > 0 for x in xs) and any(x < 0 for x in xs))
        self.assertEqual(shop.chose_continue, 1)

    def test_item_never_found_quotes_the_last_box(self):
        # Stocked in the census, but no shelf slot ever shows its box.
        shop = self.shop(right=["deku_shield"], left=["deku_shield"])
        shop.link.world["actors"].append(
            {"id": ACTOR_EN_GIRLA, "params": senses.SHOP_CATALOG["arrows_30"][0],
             "key": 999, "cat": 6, "dist_xz": 90.0, "dist_y": 0.0,
             "health": 0, "sighted": True, "drawn": True})
        text = self.error(self.call_tool("buy", {"item": "arrows_30"}))
        self.assertIn("never reached arrows_30", text)
        self.assertIn("says:", text)

    def test_unknown_item_names_the_catalog(self):
        self.shop()
        text = self.error(self.call_tool("buy", {"item": "master_sword"}))
        self.assertIn("unknown shop item", text)
        self.assertIn("deku_shield", text)
        self.assertEqual(self.pads(), [])

    def test_not_stocked_here_refuses_before_input(self):
        self.shop()
        text = self.error(self.call_tool("buy", {"item": "arrows_30"}))
        self.assertIn("not sold in this shop", text)
        self.assertEqual(self.pads(), [])

    def test_insufficient_rupees_refuses_before_input(self):
        self.shop(rupees=39)
        text = self.error(self.call_tool("buy", {"item": "deku_shield"}))
        self.assertIn("insufficient rupees (have 39, need 40)", text)
        self.assertEqual(self.pads(), [])

    def test_not_talking_to_a_shopkeeper(self):
        self.shop()
        self.link.world["msg_mode"] = 0
        self.link.world.pop("message", None)
        text = self.error(self.call_tool("buy", {"item": "deku_shield"}))
        self.assertIn("not talking to a shopkeeper", text)
        self.assertEqual(self.pads(), [])

    def test_hello_box_is_advanced_to_the_item_board(self):
        shop = self.shop(hello=0x0100)
        result = self.call_tool("buy", {"item": "deku_shield"})
        self.assertFalse(result["isError"], result["content"][0]["text"])
        self.assertEqual(shop.phase, "done")

    def test_rupee_delta_mismatch_is_never_ok(self):
        # A discount (or a price this table has wrong): the purchase went
        # through, so the tool must not pretend otherwise — but it must
        # not claim the catalog's price either.
        self.shop(deduct=20)
        text = self.error(self.call_tool("buy", {"item": "deku_shield"}))
        self.assertIn("the wallet does not agree", text)
        self.assertIn("20 rupees left it", text)

    def test_old_instrument_reads_blind(self):
        self.shop()
        self.link.world["msg_mode"] = 6
        self.link.world.pop("message", None)
        text = self.error(self.call_tool("buy", {"item": "deku_shield"}))
        self.assertIn("predates the dialogue sense", text)


class TestShopCatalog(unittest.TestCase):
    def test_kokiri_rows_are_the_games_own_numbers(self):
        # Transcribed from z_en_girla.c's shopItemEntries, filtered by
        # z_en_ossan.c's sShopkeeperStores[0]. The deku shield is the row
        # the whole slate turns on (Mido reads the worn mask).
        self.assertEqual(senses.SHOP_CATALOG["deku_shield"],
                         (0x0D, 40, 0x009F, 0x0089))
        self.assertEqual(len(senses.SHOP_CATALOG), 8)
        params = [row[0] for row in senses.SHOP_CATALOG.values()]
        self.assertEqual(len(set(params)), len(params))


# -- ITEMS 3 & 4: the vocabulary --------------------------------------------


class TestVocabulary(unittest.TestCase):
    def test_kokiri_route_names(self):
        for actor_id, name in ((0x0163, "kokiri_child"), (0x016D, "mido"),
                               (0x0146, "saria"), (0x003D, "shopkeeper"),
                               (0x0004, "shop_item"), (0x003E, "deku_tree"),
                               (0x0130, "rolling_boulder"),
                               (0x0141, "signpost"), (0x01B9, "gossip_stone"),
                               (0x014E, "rock"), (0x0077, "tree")):
            self.assertEqual(senses.actor_name(actor_id), name)

    def test_both_door_actors_are_doors(self):
        self.assertEqual(senses.actor_name(0x0009), "door")
        self.assertEqual(senses.actor_name(0x002E), "door")

    def test_sprite_less_actors_stay_unnarrated(self):
        self.assertIn(0x003B, senses.NEVER_PRESENTED)    # En_River_Sound
        self.assertIn(0x0173, senses.NEVER_PRESENTED)    # Elf_Msg2

    def test_unknown_still_flags_the_gap(self):
        self.assertEqual(senses.actor_name(0x0FFF), "unknown_0x0FFF")
        self.assertFalse(senses.actor_named(0x0FFF))


class TestDropNaming(unittest.TestCase):
    def test_curated_params(self):
        for params, name in ((0x00, "green_rupee"), (0x01, "blue_rupee"),
                             (0x02, "red_rupee"), (0x03, "recovery_heart"),
                             (0x0C, "deku_nut"), (0x11, "small_key")):
            self.assertEqual(senses.actor_name(ACTOR_EN_ITEM00, params), name)
            self.assertTrue(senses.actor_named(ACTOR_EN_ITEM00, params))

    def test_uncurated_param_falls_back_without_leaking_the_number(self):
        name = senses.actor_name(ACTOR_EN_ITEM00, 0x12)   # ITEM00_FLEXIBLE
        self.assertEqual(name, "dropped_item")
        self.assertFalse(senses.actor_named(ACTOR_EN_ITEM00, 0x12))
        self.assertNotIn("0x12", name)

    def test_no_params_is_still_a_drop_not_an_unknown(self):
        self.assertEqual(senses.actor_name(ACTOR_EN_ITEM00), "dropped_item")

    def test_spawn_narrates_the_drop_by_name(self):
        class NoSeen:
            def sight(self, kind):
                return True
        fresh = [{"id": ACTOR_EN_ITEM00, "key": 5, "sighted": True,
                  "params": 0x02}]
        events = senses.spawn_events(fresh, NoSeen())
        self.assertEqual(events[0]["kind"], "red_rupee")

    def test_high_bits_do_not_defeat_the_lookup(self):
        # En_Item00 masks its own params to 0xFF in Init; a census read
        # before that (or a spawn-param variant) must not read as unknown.
        self.assertEqual(senses.actor_name(ACTOR_EN_ITEM00, 0x8003),
                         "recovery_heart")


if __name__ == "__main__":
    unittest.main()
