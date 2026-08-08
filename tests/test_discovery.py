"""The discovery grain (dojo docs/34, 0.14.0): the per-line ledger, the
fogged document with its frontier presentation, refusal/reach coherence
with the routed walk, the region_discovered cue, journal seeding, and
the no-re-fog guarantee.

Runs on test_place.py's synthetic two-floor mesh. Scene 0 is ydan's id
(FOGGED under DUNGEON_SCENES); scene 0x55 is Kokiri Forest's (overworld:
full reveal at entry).
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from ocarina.discovery import Discovery
from ocarina.navgraph import distill
from ocarina.place import (SCENE_DIRS, PlaceGraph, PlaceSense, RouteRefused)

from .test_place import (LOWER, UPPER, VINE, sense_with_graph, state_at,
                         two_floor_mesh)

OVERWORLD = 0x55


class LedgerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = self.tmp / ".ocarina" / "place_discovered.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestDiscoveryStore(LedgerCase):
    def test_discover_is_first_time_once_and_persists(self):
        d = Discovery(self.path)
        self.assertTrue(d.discover(0, LOWER, room=0))
        self.assertFalse(d.discover(0, LOWER, room=0), "second visit")
        self.assertTrue(d.known(0, LOWER))
        # A NEW server session over the same repo re-presents, never
        # re-fogs (docs/34: discovery is save state).
        d2 = Discovery(self.path)
        self.assertTrue(d2.known(0, LOWER))
        self.assertFalse(d2.discover(0, LOWER),
                         "a restart must not re-award discovery")

    def test_room_binding_is_recorded(self):
        d = Discovery(self.path)
        d.discover(0, LOWER, room=2)
        self.assertEqual(Discovery(self.path).room_of(LOWER), 2)

    def test_scenes_do_not_bleed(self):
        d = Discovery(self.path)
        d.discover(0, LOWER)
        self.assertFalse(d.known(OVERWORLD, LOWER))

    def test_seeds_from_journal_fossils(self):
        journal = self.tmp / "journal" / "mechanical.jsonl"
        journal.parent.mkdir(parents=True)
        lines = [
            {"event": "place", "cue": "region_entered",
             "region": "ydan:r@30,0,70"},
            {"event": "place", "cue": "fell", "region": "ydan:r@-620,-820,0"},
            {"event": "place", "cue": "region_entered",
             "region": "spot04:r@-100,10,220"},
            {"event": "spawn", "kind": "deku_baba"},          # not place
            {"event": "place", "cue": "region_entered",
             "region": "nowhere:r@0,0,0"},                    # unknown scene
        ]
        journal.write_text("\n".join(json.dumps(l) for l in lines)
                           + "\nnot json\n")
        d = Discovery(self.path, journal=journal, scene_dirs=SCENE_DIRS)
        self.assertEqual(d.seeded_from_journal, 3)
        self.assertTrue(d.known(0x00, "ydan:r@30,0,70"))
        self.assertTrue(d.known(0x00, "ydan:r@-620,-820,0"),
                        "a fell landing proves presence too")
        self.assertTrue(d.known(0x55, "spot04:r@-100,10,220"))

    def test_an_existing_ledger_is_never_reseeded(self):
        Discovery(self.path).discover(0, LOWER)
        journal = self.tmp / "journal" / "mechanical.jsonl"
        journal.parent.mkdir(parents=True)
        journal.write_text(json.dumps(
            {"event": "place", "cue": "region_entered",
             "region": "ydan:r@30,0,70"}))
        d = Discovery(self.path, journal=journal, scene_dirs=SCENE_DIRS)
        self.assertEqual(d.seeded_from_journal, 0,
                         "the ledger is the record once it exists")


class FoggedSenseCase(LedgerCase):
    """A place sense over the two-floor mesh with a real ledger, in the
    fogged scene (0 = ydan's id)."""

    def setUp(self):
        super().setUp()
        self.ps = sense_with_graph()
        self.ps.discovery = Discovery(self.path)
        self.lower = state_at(150, 2, 100)
        self.upper = state_at(100, 205, 300)

    def visit(self, state):
        return self.ps.fold(state)


class TestFoggedDocument(FoggedSenseCase):
    def test_fresh_scene_presents_presence_only(self):
        self.visit(self.lower)
        body = self.ps.document(self.lower)
        names = [r["region"] for r in body["regions"]]
        self.assertEqual(names, [LOWER],
                         "only the region Link has stood in")
        self.assertNotIn(UPPER, str(body), "ABSENT means absent — no leak")
        ways = body["regions"][0]["ways"]
        self.assertTrue(any("destination unknown" in w for w in ways),
                        f"the vine up must present as a frontier: {ways}")
        self.assertTrue(any(VINE in w for w in ways),
                        "the edge NAME stays — the wall is visible, and "
                        "traverse needs a name to explore it by")
        self.assertTrue(any("DISCOVERY GRAIN" in n for n in body["notes"]))
        self.assertTrue(any("RETARGETED" in n for n in body["notes"]))

    def test_presence_reveals_and_stays_revealed(self):
        self.visit(self.lower)
        self.visit(self.upper)                     # stand on the upper floor
        body = self.ps.document(self.upper)
        names = {r["region"] for r in body["regions"]}
        self.assertEqual(names, {LOWER, UPPER})
        lower = next(r for r in body["regions"] if r["region"] == LOWER)
        self.assertTrue(any(UPPER in w for w in lower["ways"]),
                        "a discovered destination is named again")
        # A fresh sense + fresh ledger over the SAME repo re-presents
        # (docs/34: re-entry re-presents from the repo, never re-fogs).
        ps2 = sense_with_graph()
        ps2.discovery = Discovery(self.path)
        body2 = ps2.document(self.lower)
        self.assertEqual({r["region"] for r in body2["regions"]},
                         {LOWER, UPPER})

    def test_self_is_never_fogged(self):
        # Even before any fold has run, the region Link STANDS IN is
        # presented — the docs/25 self-vs-others line.
        body = self.ps.document(self.lower)
        self.assertEqual(body["you"]["region"], LOWER)
        here = next(r for r in body["regions"] if r["region"] == LOWER)
        self.assertTrue(here.get("you_are_here"))

    def test_dungeon_map_widens_to_outline_only(self):
        self.visit(self.lower)
        st = dict(self.lower)
        st["dungeon_items"] = {"map": True}
        body = self.ps.document(st)
        upper = next((r for r in body["regions"] if r["region"] == UPPER),
                     None)
        self.assertIsNotNone(upper, "the map reveals existence")
        self.assertIn("outline", upper)
        self.assertNotIn("ways", upper,
                         "region detail stays presence-gated (open call 3)")

    def test_without_the_wire_rider_the_gap_is_loud(self):
        self.visit(self.lower)
        body = self.ps.document(self.lower)
        self.assertTrue(any("dungeon_items" in n for n in body["notes"]),
                        "no wire field = say so, never silently unwidened")


class TestOverworldReveal(LedgerCase):
    def setUp(self):
        super().setUp()
        self.ps = PlaceSense("/nonexistent/dummy.o2r")
        self.ps._graphs[OVERWORLD] = PlaceGraph("test",
                                                distill(two_floor_mesh()))
        self.ps.discovery = Discovery(self.path)

    def test_entry_reveals_the_whole_scene(self):
        st = state_at(150, 2, 100, scene=OVERWORLD)
        body = self.ps.document(st)
        names = {r["region"] for r in body["regions"]}
        self.assertEqual(names, {LOWER, UPPER},
                         "overworld: the whole coarse map at entry")
        self.assertFalse(any("destination unknown" in w
                             for r in body["regions"]
                             for w in r["ways"]))
        self.assertTrue(any("reveals whole at entry" in n
                            for n in body["notes"]))

    def test_no_discovery_narration_in_the_overworld(self):
        evs = self.ps.fold(state_at(150, 2, 100, scene=OVERWORLD))
        self.assertNotIn("region_discovered", [e["cue"] for e in evs],
                         "nothing to earn where entry reveals everything")


class TestFogCoherence(FoggedSenseCase):
    def test_walk_refusal_does_not_name_the_undiscovered(self):
        self.visit(self.lower)
        with self.assertRaises(RouteRefused) as cm:
            self.ps.resolve_walk(self.lower, 100, 300)   # the upper floor
        text = str(cm.exception)
        self.assertIn("somewhere you haven't been", text)
        self.assertNotIn(UPPER, text, "the fog must hold in refusals")
        self.assertIn(VINE, text, "the visible way out is still named")

    def test_walk_refusal_names_the_discovered(self):
        self.visit(self.lower)
        self.visit(self.upper)
        with self.assertRaises(RouteRefused) as cm:
            self.ps.resolve_walk(self.lower, 100, 300)
        self.assertIn(UPPER, str(cm.exception),
                      "toward a discovered region, the name returns")

    def test_reach_rider_inherits_the_fog(self):
        self.visit(self.lower)
        judged = self.ps.judge_reach(self.lower, {"pos": [100.0, 202.0, 300.0]})
        self.assertEqual(judged, "somewhere you haven't been")
        self.visit(self.upper)
        judged = self.ps.judge_reach(self.lower, {"pos": [100.0, 202.0, 300.0]})
        self.assertEqual(judged, "up a climb")

    def test_region_discovered_fires_once_per_line(self):
        evs = self.visit(self.lower)
        self.assertEqual([e["cue"] for e in evs],
                         ["region_discovered", "region_entered"])
        self.visit(self.upper)
        evs = self.visit(state_at(160, 2, 110))          # back to lower
        self.assertNotIn("region_discovered", [e["cue"] for e in evs],
                         "discovery is once per save line, not per entry")


if __name__ == "__main__":
    unittest.main()
