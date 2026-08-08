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
        names = {r["region"] for r in body["regions"]}
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
        names2 = {r["region"] for r in body2["regions"]}
        self.assertTrue(names.issubset(names2),
                        f"re-entry re-fogged: had {sorted(names)}, "
                        f"now {sorted(names2)}")
        rediscovered = [
            e for e in self.server.journal()
            if e.get("cue") == "region_discovered"][discovered_before:]
        self.assertEqual(
            [e for e in rediscovered if e.get("region") in names], [],
            "re-entering known ground must not re-award discovery")


if __name__ == "__main__":
    unittest.main()
