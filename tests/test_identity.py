"""The declared save-line identity (docs/32; 0.11.0).

The tenth flight's wrong-file hour, priced into tests: the repo
declares its line in identity.json, the RUNTIME judges every load and
every attach against it, journals the boot line unconditionally, and
refuses a mismatch with the first wake the runtime raises on its own
authority — identity transition, hold default, fail closed on broken
declarations and missing wire evidence alike.
"""

import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from ocarina import identity as identity_mod
from ocarina.events import EventLog
from ocarina.game import Game
from ocarina.runtime import MachineRuntime

from .stubgame import StubLink

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "save-file"

#: A world matching DECLARATION below: sword on B, slingshot on C-LEFT,
#: kokiri sword + deku shield owned (bit 0 and bit 4 of the owned mask),
#: sticks/nuts/slingshot in inventory with ammo, three hearts.
GOOD_WORLD = {
    "equips": {"b": 0x3B, "c_left": 0x06, "c_down": 0xFF, "c_right": 0xFF,
               "worn": 0x0011, "owned": 0x0011},
    "inventory": {"items": [0x00, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0x06],
                  "ammo": [5, 4, 0, 0, 0, 0, 30]},
}

DECLARATION = {
    "save_slot": 1,
    "save_name": "C",
    "fingerprint": {
        "_note": "monotone facts only",
        "health_capacity_at_least": 48,
        "b_item": "kokiri_sword",
        "c_buttons": {"c_left": "fairy_slingshot"},
        "inventory_items": ["fairy_slingshot"],
        "equipment_owned": {"sword": ["kokiri_sword"],
                            "shield": ["deku_shield"]},
    },
    "journal_only": ["rupees", "nuts"],
}


class IdentityCase(unittest.TestCase):
    """Runtime-level cases. The fixture repo carries no identity.json;
    each test that opts in writes one before constructing the runtime."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = Path(self.tmp) / "save-file"
        shutil.copytree(FIXTURE_REPO, self.repo)
        self.link = StubLink()
        self.game = Game(self.link)
        self.log = EventLog(persist_path=self.repo / "journal" / "mechanical.jsonl")
        self.packs = []
        self.runtime = None

    def tearDown(self):
        if self.runtime is not None:
            self.runtime.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def declare(self, declaration=DECLARATION):
        (self.repo / "identity.json").write_text(json.dumps(declaration))

    def start(self):
        self.runtime = MachineRuntime(
            self.game, self.repo, self.log,
            wake_push=self.packs.append, wake_deadline_s=60.0)
        self.runtime.load()
        return self.runtime

    def tick_until(self, cond, seconds=2.0, msg="condition"):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.runtime.tick()
            if cond():
                return
            time.sleep(0.01)
        raise AssertionError(f"never reached: {msg}")

    def diagnostics(self):
        return [e["text"] for e in self.log.tail(n=0, category="diagnostic")]

    def wakes(self):
        return self.log.tail(n=0, category="wake")

    def push_load(self, slot=1, with_file=True):
        msg = {"type": "agent_event", "event": "load_game"}
        if with_file:
            msg["file"] = slot
        self.link.push_wire(msg)


class TestRuntimeIdentity(IdentityCase):

    # -- no declaration: check off, loudly, boot line regardless ------------

    def test_no_declaration_is_off_and_loud(self):
        self.start()
        self.assertTrue(any("boot verification is OFF" in d
                            for d in self.diagnostics()))
        self.link.world.update(GOOD_WORLD)
        self.push_load(slot=0)      # any slot: nothing is declared
        self.tick_until(lambda: any(d.startswith("boot: ")
                                    for d in self.diagnostics()),
                        msg="the unconditional boot line")
        self.assertFalse(self.wakes())
        self.assertIsNone(self.runtime._wake)
        line = next(d for d in self.diagnostics() if d.startswith("boot: "))
        # The line is the recognise-at-a-glance identity: buttons, gear,
        # inventory with ammo, hearts, counters.
        self.assertIn("kokiri_sword on B", line)
        self.assertIn("fairy_slingshot x30", line)
        self.assertIn("3.0/3.0 hearts", line)

    # -- the verified path ---------------------------------------------------

    def test_matching_load_verifies(self):
        self.declare()
        self.link.world.update(GOOD_WORLD)
        self.start()
        self.assertTrue(any("boot verification is ON" in d
                            for d in self.diagnostics()))
        self.push_load(slot=1)
        self.tick_until(lambda: any("identity verified" in d
                                    for d in self.diagnostics()),
                        msg="verified")
        verified = next(d for d in self.diagnostics() if "identity verified" in d)
        self.assertIn("save C", verified)
        self.assertNotIn("slot unverifiable", verified)
        self.assertFalse(self.wakes())

    def test_attach_without_load_verifies_fingerprint_only(self):
        # The rehydrate gap: a reconnect never fires load_game, so the
        # slot is honestly unverifiable and the pack says so.
        self.declare()
        self.link.world.update(GOOD_WORLD)
        self.start()
        self.tick_until(lambda: any("identity verified" in d
                                    for d in self.diagnostics()),
                        msg="verified at attach")
        verified = next(d for d in self.diagnostics() if "identity verified" in d)
        self.assertIn("slot unverifiable this attach", verified)

    # -- refusals ------------------------------------------------------------

    def wake_reason(self):
        self.assertTrue(self.wakes(), "expected an identity wake")
        wake = self.wakes()[0]
        self.assertEqual(wake["transition"], "identity")
        return wake["reason"]

    def test_slot_mismatch_wakes(self):
        self.declare()
        self.link.world.update(GOOD_WORLD)
        self.start()
        self.push_load(slot=0)      # the tenth flight's exact fraud
        self.tick_until(lambda: self.wakes(), msg="mismatch wake")
        reason = self.wake_reason()
        self.assertIn("WRONG SAVE FILE", reason)
        self.assertIn("loaded slot 0", reason)
        self.assertIn("slot 1", reason)
        # Runtime-initiated: frozen with the hold default armed.
        self.assertIsNotNone(self.runtime._wake)
        self.assertEqual(self.runtime._wake.default.verb, "hold")
        # The push carries the same single-sourced pack.
        self.assertEqual(self.packs[0]["transition"], "identity")
        self.assertIn("interval", self.packs[0])

    def test_fingerprint_mismatch_names_the_diff(self):
        self.declare()
        world = {"equips": dict(GOOD_WORLD["equips"]),
                 "inventory": {"items": [0x00, 0x01], "ammo": [5, 4]}}
        world["equips"]["c_left"] = 0xFF        # slingshot gone from C too
        self.link.world.update(world)
        self.start()
        self.push_load(slot=1)
        self.tick_until(lambda: self.wakes(), msg="mismatch wake")
        reason = self.wake_reason()
        self.assertIn("fairy_slingshot is NOT in the inventory", reason)
        self.assertIn("C-LEFT holds nothing", reason)

    def test_missing_wire_blocks_fail_closed(self):
        # The stub's default world carries no equips/inventory at all —
        # an instrument predating the senses reads as blind, never as
        # agreement.
        self.declare()
        self.start()
        self.push_load(slot=1)
        self.tick_until(lambda: self.wakes(), msg="cannot-verify wake")
        reason = self.wake_reason()
        self.assertIn("CANNOT VERIFY", reason)
        self.assertIn("equips", reason)
        self.assertIn("Absence of evidence is not a pass", reason)

    def test_broken_declaration_fails_closed(self):
        (self.repo / "identity.json").write_text("{not json")
        self.link.world.update(GOOD_WORLD)
        self.start()
        self.assertTrue(any("UNUSABLE" in d for d in self.diagnostics()))
        self.push_load(slot=1)
        self.tick_until(lambda: self.wakes(), msg="cannot-verify wake")
        self.assertIn("CANNOT VERIFY", self.wake_reason())

    def test_load_without_file_field_refuses_when_slot_declared(self):
        self.declare()
        self.link.world.update(GOOD_WORLD)
        self.start()
        self.push_load(with_file=False)
        self.tick_until(lambda: self.wakes(), msg="no-file wake")
        self.assertIn("no `file` field", self.wake_reason())

    # -- the cycle: resume, then a fresh load re-arms ------------------------

    def test_resume_then_next_load_rechecks(self):
        self.declare()
        self.link.world.update(GOOD_WORLD)
        self.start()
        self.push_load(slot=0)
        self.tick_until(lambda: self.wakes(), msg="first wake")
        self.runtime.resume()
        self.assertIsNone(self.runtime._wake)
        # Same wrong world, no new load: judged once per arm, no re-fire.
        for _ in range(5):
            self.runtime.tick()
            time.sleep(0.01)
        self.assertEqual(len(self.wakes()), 1)
        # A fresh load re-arms — and this one matches.
        self.push_load(slot=1)
        self.tick_until(lambda: any("identity verified" in d
                                    for d in self.diagnostics()),
                        msg="second load verified")
        self.assertEqual(len(self.wakes()), 1)


class TestBlockedDelivery(IdentityCase):
    """End to end, fakewake-style: the identity_mismatch pack is the
    return value of a blocked listener (docs/31's transport carrying
    docs/32's refusal)."""

    def test_wrong_file_pack_returns_through_await_wake(self):
        import threading
        self.declare()
        self.link.world.update(GOOD_WORLD)
        self.start()
        errors, out = [], []
        ticking = [True]

        def loop():
            while ticking[0]:
                try:
                    self.runtime.tick()
                except Exception as e:
                    errors.append(repr(e))
                time.sleep(0.01)

        ticker = threading.Thread(target=loop, daemon=True)
        ticker.start()
        try:
            listener = threading.Thread(
                target=lambda: out.append(self.runtime.await_wake()),
                daemon=True)
            listener.start()
            deadline = time.monotonic() + 5
            while (not self.runtime.status()["listener_blocked"]
                   and time.monotonic() < deadline):
                time.sleep(0.01)
            self.push_load(slot=0)
            listener.join(timeout=5)
        finally:
            ticking[0] = False
            ticker.join(timeout=5)
        self.assertEqual(errors, [])
        self.assertTrue(out, "the blocked await_wake never returned")
        pack = out[0]
        self.assertEqual(pack["transition"], "identity")
        self.assertIn("WRONG SAVE FILE", pack["reason"])
        self.assertIn("loaded slot 0", pack["reason"])
        self.assertIn("interval", pack)
        self.assertTrue(self.link.paused, "the world froze for the refusal")


class TestLoadIdentity(unittest.TestCase):
    """Unit-level: the parser's load-time validation."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, content):
        (self.tmp / "identity.json").write_text(
            content if isinstance(content, str) else json.dumps(content))

    def test_absent_is_none(self):
        self.assertIsNone(identity_mod.load_identity(self.tmp))

    def test_good_declaration_parses(self):
        self.write(DECLARATION)
        ident = identity_mod.load_identity(self.tmp)
        self.assertFalse(ident.broken)
        self.assertEqual(ident.save_slot, 1)
        self.assertEqual(ident.save_name, "C")
        self.assertEqual(ident.label(), "identity.json (save C, slot 1)")

    def test_malformed_json_is_broken(self):
        self.write("{not json")
        ident = identity_mod.load_identity(self.tmp)
        self.assertTrue(ident.broken)
        self.assertIn("unreadable", ident.problems[0])

    def test_missing_fingerprint_is_broken(self):
        self.write({"save_slot": 1})
        ident = identity_mod.load_identity(self.tmp)
        self.assertTrue(ident.broken)
        self.assertIn("fingerprint", ident.problems[0])

    def test_unknown_fingerprint_key_is_broken(self):
        bad = dict(DECLARATION)
        bad["fingerprint"] = dict(DECLARATION["fingerprint"], nuts=4)
        self.write(bad)
        ident = identity_mod.load_identity(self.tmp)
        self.assertTrue(ident.broken)
        self.assertIn("'nuts'", ident.problems[0])
        # Underscore keys are commentary, never problems.
        self.assertNotIn("_note", "".join(ident.problems))

    def test_bad_slot_type_is_broken(self):
        self.write(dict(DECLARATION, save_slot="C"))
        ident = identity_mod.load_identity(self.tmp)
        self.assertTrue(ident.broken)
        self.assertIn("save_slot", ident.problems[0])


if __name__ == "__main__":
    unittest.main()
