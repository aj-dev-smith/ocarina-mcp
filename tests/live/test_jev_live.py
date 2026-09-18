"""Live: Jev over the real network (no game needed). Skipped unless
JEV_LIVE=1 AND a key is found (JEV_API in the environment, or the
ocarina checkout's .env). Pins the two facts the offline suite cannot:
the request shape the service actually accepts, and the answers the
probe measured on 2026-09-18 for the unambiguous scenes (a box open ->
advance; empty room -> idle; a baba in reach, head low -> cut).

A latency assertion would be a flake generator, so this reports the
median instead of asserting it; the number to expect from AJ's machine
is ~275 ms warm, ~650 ms on a fresh connection."""

import os
import statistics
import unittest
from pathlib import Path

from ocarina import jev, senses

KEY, SOURCE = jev.find_key(Path(__file__).resolve().parents[2] / ".env")


@unittest.skipUnless(os.environ.get("JEV_LIVE") == "1" and KEY,
                     "JEV_LIVE=1 and a JEV_API key are required")
class TestJevLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = jev.JevClient(KEY)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def test_request_shape_accepted_and_typed(self):
        j = self.client.ask(
            "Link has 3 of 3 hearts. No enemy is in view.",
            {"idle": {"type": "noul", "instructions": "Is there nothing for Link to do right now?"},
             "mood": {"type": "choice", "instructions": "Which best describes the situation?",
                      "criteria": {"calm": "nothing is happening", "tense": "a threat is present"}},
             "danger": {"type": "score", "instructions": "How dangerous is this?",
                        "criteria": ["safe: nothing can hurt Link", "risky: something might",
                                     "deadly: Link could die"]}})
        self.assertTrue(j.ok, j.error)
        self.assertGreater(j.noul("idle"), 0.5)
        self.assertEqual(j.choice("mood"), "calm")
        self.assertLess(j.score("danger"), 1.0)
        self.assertEqual(sorted(j.probabilities("mood")), ["calm", "tense"])
        self.assertIn("input_tokens", j.usage)

    def test_duel_scenes_from_the_probe(self):
        from importlib.util import spec_from_file_location, module_from_spec
        path = Path(__file__).resolve().parents[2].parent / "ocarina-flights" / "09-kokiri" / \
            "kokiri" / "machine" / "behaviors" / "judged.py"
        if not path.exists():
            self.skipTest(f"no flight repo at {path}")
        spec = spec_from_file_location("_judged_live", path)
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        base = {"hearts": 3.0, "hearts_max": 3.0, "enemies": 1, "player": {},
                "place": {"region": "ydan:r@30,0,70", "on_mesh": True}}
        low = dict(base, nearest_enemy={"kind": "deku_baba", "dist": 90.0, "above": 0.0,
                                        "bearing": 12, "moving": True, "reach": "walkable"})
        reared_close = dict(base, nearest_enemy={"kind": "deku_baba", "dist": 100.0, "above": 0.0,
                                                 "bearing": 12, "moving": True, "reach": "walkable"})
        lat = []
        j = self.client.ask(senses.narrate(low, extra=[mod._head_line({"pos": [0, 20, 0]})]),
                            mod.QUESTIONS)
        self.assertTrue(j.ok, j.error); lat.append(j.latency_ms)
        self.assertEqual(j.choice("move"), "cut", j.probabilities("move"))
        j = self.client.ask(senses.narrate(reared_close, extra=[mod._head_line({"pos": [0, 80, 0]})]),
                            mod.QUESTIONS)
        self.assertTrue(j.ok, j.error); lat.append(j.latency_ms)
        self.assertEqual(j.choice("move"), "back_off", j.probabilities("move"))
        self.assertGreater(j.noul("bite_risk"), 0.5)
        print(f"\n  jev live: median latency {statistics.median(lat):.0f} ms over {len(lat)} calls")


if __name__ == "__main__":
    unittest.main()
