"""Live e2e: the discovery grain against the REAL game (0.14.0,
docs/34 — acceptance criteria 1 and 5 as pins, run under the dev
harness so the flight is acceptance, not discovery).

The throwaway repo starts DARK (no ledger, no journal), so warping into
the Deku Tree is a fresh line's first entry: the document must present
the entrance regions presence earned and nothing more, frontier legs
unnamed. Warp out and back must re-present the earned map from the
repo, never re-fog (the grotto note, docs/34).

Skipped instantly unless OCARINA_LIVE=1; needs the o2r (a fogged
document requires a map to fog).
"""

import shutil
import tempfile
import time
import unittest
from pathlib import Path

from . import harness

INSIDE_THE_DEKU_TREE = 0
OUTSIDE_THE_DEKU_TREE = 521
DEKU_TREE_SCENE = 0

#: The whole of ydan distills to ~50 regions (fifth flight). A fresh
#: entry that presents more than a handful has no fog at all.
FRESH_ENTRY_REGION_CAP = 6


def setUpModule():
    harness.require_live()


class LiveDiscoveryCase(unittest.TestCase):
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

    def place_doc(self) -> dict:
        body = self.server.read("oot://place")
        if "error" in body:
            if "--o2r" in body["error"]:
                self.skipTest("server has no place sense (--o2r)")
            raise AssertionError(f"oot://place errored: {body['error']}")
        return body

    def warp(self, entrance: int) -> None:
        body = self.server.call("dev_warp", {"entrance": entrance})
        self.assertTrue(body["ok"], body)
        time.sleep(1.0)          # a couple of runtime ticks: the standing
                                 # fix is what discovers the arrival region

    def test_fresh_entry_is_fogged_and_reentry_holds(self):
        # Criterion 1 (region-grain form): a dark line's first entry
        # presents presence only.
        self.warp(INSIDE_THE_DEKU_TREE)
        self.assertEqual(self.server.state()["scene"], DEKU_TREE_SCENE)
        body = self.place_doc()
        # Outline entries don't count against the fog: since the
        # dungeon-items rider the boot save's own Dungeon Map (slot 0 is
        # an old line that took the ring chest) legitimately widens the
        # document — that is the RATIFIED widening, not a reveal leak.
        # The cap is on what PRESENCE earned.
        names = {r["region"] for r in body["regions"] if "outline" not in r}
        self.assertTrue(names, "Link is standing somewhere — present it")
        self.assertLessEqual(
            len(names), FRESH_ENTRY_REGION_CAP,
            f"a fresh entry presented {len(names)} regions — that is the "
            f"whole-scene reveal, not fog: {sorted(names)}")
        self.assertTrue(any("DISCOVERY GRAIN" in n for n in body["notes"]))
        journal = self.server.journal()
        self.assertTrue(
            [e for e in journal if e.get("cue") == "region_discovered"],
            "first presence must journal region_discovered")

        # Criterion 5: leave, come back — the earned map re-presents
        # from the repo, never re-fogs, and discovery is not re-awarded.
        discovered_before = len(
            [e for e in self.server.journal()
             if e.get("cue") == "region_discovered"])
        self.warp(OUTSIDE_THE_DEKU_TREE)
        self.assertNotEqual(self.server.state()["scene"], DEKU_TREE_SCENE)
        self.warp(INSIDE_THE_DEKU_TREE)
        body2 = self.place_doc()
        names2 = {r["region"] for r in body2["regions"]
                  if "outline" not in r}
        self.assertTrue(names.issubset(names2),
                        f"re-entry re-fogged: had {sorted(names)}, "
                        f"now {sorted(names2)}")
        rediscovered = [
            e for e in self.server.journal()
            if e.get("cue") == "region_discovered"][discovered_before:]
        self.assertEqual(
            [e for e in rediscovered if e.get("region") in names], [],
            "re-entering known ground must not re-award discovery")

    def test_the_dungeon_map_widens_to_outlines_and_no_further(self):
        # Criterion 4 (docs/34): the Dungeon Map grant (dev_give_item,
        # the criterion's own named rider) widens oot://place to outline
        # grade — existence and rough placement of regions presence has
        # not earned — and NO further: an outline entry carries no legs.
        # The boot save is slot 0, an OLD line that may already own the
        # ydan Map (the ring chest — docs/26 erratum), so the
        # nothing-outlined-before assertion runs only when the row says
        # the Map is genuinely absent.
        self.warp(INSIDE_THE_DEKU_TREE)
        # oot://state is the curated digest and rightly carries no raw
        # dungeonItems row — the honest witnesses here are all blessed:
        # the place document names a missing rider itself, and the grant
        # verb's reply carries the raw row read back as its proof.
        before = self.place_doc()
        if any("no dungeon_items on the wire" in n for n in before["notes"]):
            self.skipTest(
                "no dungeon_items on the wire — the instrument predates "
                "the 2026-08-07 dungeon-items rider; rebuild SoH")
        had_outlines = any("outline" in r for r in before["regions"])
        body = self.server.call("dev_give_item", {"item": "map"})
        self.assertTrue(body["ok"], body)
        self.assertTrue(body["now"]["map"],
                        "the read-back is the proof of the grant")
        for key in ("compass", "boss_key", "small_keys"):
            self.assertIn(key, body["now"],
                          f"the wire row is missing {key!r}")
        self.assertEqual(body["dungeon_index"], DEKU_TREE_SCENE)

        after = self.place_doc()
        outlined = [r for r in after["regions"] if "outline" in r]
        self.assertTrue(
            outlined,
            "Map owned: unvisited regions must appear as outlines "
            "(ydan is ~50 regions and presence has earned a handful)")
        if not had_outlines:
            # The line did not own the Map before this grant, so the
            # widening we see is the grant's own doing — criterion 4's
            # cause-and-effect form, not just its end state.
            self.assertGreater(len(outlined), 0)
        for entry in outlined:
            self.assertNotIn(
                "ways", entry,
                "outline grade must carry no legs — detail stays "
                "presence-gated (docs/34 open call 3)")
        self.assertTrue(any("outline grade" in n for n in after["notes"]),
                        after["notes"])


if __name__ == "__main__":
    unittest.main()
