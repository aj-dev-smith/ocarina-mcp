"""Live e2e: the routed walk against the REAL game (0.13.0, docs/30 —
"development happens against the dev harness": these pins land BEFORE
the acceptance flight, so the flight is acceptance, not discovery).

walk_to and reachable are BEHAVIOR-layer verbs, not MCP tools, so the
harness drives them the way the bench itself would: a probe behavior in
the throwaway repo reads its target from `walk_target.json`, runs the
verb, and writes `walk_result.json` — position before/after and elapsed
time measured INSIDE the body, which is exactly how docs/30's criterion
1 wants zero-movement refusals witnessed. The test warps Link to known
ground with the dev verbs (docs/33), points the probe, and reads the
file.

Skipped instantly unless OCARINA_LIVE=1; see harness.py for the gates.
Needs the o2r (no place sense, no routed walk — the probe says so and
the tests skip).
"""

import json
import math
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from . import harness

#: ENTR_KOKIRI_FOREST_OUTSIDE_KNOW_IT_ALL_HOUSE (spawn 5) — ground
#: level, in-bounds by construction (the third router lesson, 2026-08-07:
#: entrance spawns are where the GAME puts players; a lab-elected floor
#: point can be a mesh lip outside the fence).
KOKIRI_GROUND = 618
KOKIRI_FOREST_SCENE = 85

#: The sword-crawlspace tunnel interior — its own region since the
#: end-clustering fix, and NOT the village floor region: a guaranteed
#: cross-region target from anywhere in the village (the cliff case).
TUNNEL_INTERIOR = (-780.0, 1220.0)

MACHINE_YAML = """\
# tests/live walk family: stand_watch + the walk probe (see module doc).
version: 1
initial: stand_watch

nodes:
  stand_watch:
    behavior: stand_watch_v1
    transitions:
      - name: keep-standing
        on: behavior_done
        do: goto stand_watch
  walk_probe:
    behavior: walk_probe_v1
    transitions:
      - name: probe-done
        on: behavior_done
        do: goto stand_watch
"""

PROBE_BEHAVIOR = '''\
"""tests/live walk probe: run walk_to/reachable per walk_target.json,
write walk_result.json. Measurements (moved, elapsed) taken in-body."""

import json
import math
import time
from pathlib import Path

from ocarina.behavior import Behavior
from ocarina.place import RouteFailed, RouteRefused

HERE = Path(__file__).resolve().parent


def _probe(game, ctx):
    spec = json.loads((HERE / "walk_target.json").read_text())
    out = {"mode": spec.get("mode", "walk")}
    p0 = game.pos()
    t0 = time.time()
    try:
        if out["mode"] == "query":
            out["refusal"] = game.reachable(spec["x"], spec["z"])
        else:
            out["result"] = game.walk_to(spec["x"], spec["z"])
    except RouteRefused as e:
        out["refused"] = str(e)
    except RouteFailed as e:
        out["failed"] = str(e)
    except Exception as e:                      # noqa: BLE001 — the file
        out["error"] = f"{type(e).__name__}: {e}"   # IS the error channel
    out["elapsed_s"] = round(time.time() - t0, 3)
    p1 = game.pos()
    out["moved"] = (round(math.hypot(p1[0] - p0[0], p1[2] - p0[2]), 2)
                    if p0 and p1 else None)
    out["pos"] = list(p1) if p1 else None
    (HERE / "walk_result.json").write_text(json.dumps(out))


BEHAVIORS = {
    "walk_probe_v1": Behavior(
        name="walk_probe", version=1,
        description="live-harness routed-walk probe: one verb, one result file",
        body=_probe, success=lambda game, initial, events: True,
        timeout_s=120.0,
        grade="harness fixture; never graded"),
}
'''


def setUpModule():
    harness.require_live()


class LiveWalkCase(unittest.TestCase):
    """One server, one game, one throwaway repo with the probe machine."""

    @classmethod
    def setUpClass(cls):
        harness.require_live()
        harness.require_free_sail_port()
        cls.tmp = tempfile.mkdtemp()
        cls.repo = harness.make_repo(Path(cls.tmp))
        behaviors = cls.repo / "machine" / "behaviors"
        (cls.repo / "machine" / "machine.yaml").write_text(MACHINE_YAML)
        (behaviors / "walk_probe.py").write_text(PROBE_BEHAVIOR)
        (behaviors / "walk_target.json").write_text("{}")
        cls.behaviors = behaviors
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

    # -- plumbing ----------------------------------------------------------

    def warp_to_ground(self):
        body = self.server.call("dev_warp", {"entrance": KOKIRI_GROUND})
        self.assertTrue(body["ok"], body)
        self.assertEqual(self.server.state()["scene"], KOKIRI_FOREST_SCENE)

    def probe(self, x: float, z: float, mode: str = "walk",
              timeout: float = 90.0) -> dict:
        """Point the probe and wait for its result file."""
        result_path = self.behaviors / "walk_result.json"
        if result_path.exists():
            result_path.unlink()
        (self.behaviors / "walk_target.json").write_text(
            json.dumps({"x": x, "z": z, "mode": mode}))
        self.server.call("force_state", {"node": "walk_probe"})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if result_path.exists():
                out = json.loads(result_path.read_text())
                if "error" in out:
                    raise AssertionError(f"probe errored: {out['error']}")
                self._skip_if_senseless(out)
                return out
            time.sleep(0.25)
        raise AssertionError(f"no probe result within {timeout:.0f}s")

    def _skip_if_senseless(self, out: dict) -> None:
        text = out.get("refused") or out.get("refusal") or ""
        if "--o2r" in text:
            self.skipTest("server has no place sense (start with --o2r / "
                          "OCARINA_O2R) — the routed walk cannot run")
        if "no map for scene" in text:
            self.skipTest(f"scene unmapped for the place sense: {text}")

    def elect_walkable_target(self) -> tuple:
        """A same-region point 100-250 units from Link with honest
        clearance, elected from the distilled map — the TEST doing mesh
        math is dev tooling, exactly what docs/30 makes contraband in
        scored play and legal here."""
        from ocarina.collision import load_from_o2r
        from ocarina.navgraph import distill
        from ocarina.place import PlaceGraph
        o2r = harness.o2r_path()
        if o2r is None:
            self.skipTest("no oot.o2r on this machine")
        pg = PlaceGraph("spot04", distill(load_from_o2r(
            str(o2r),
            "scenes/shared/spot04_scene/spot04_sceneCollisionHeader_008918")))
        place = self.server.state().get("place") or {}
        if "x" not in place:
            self.skipTest("no place.* in the digest — no --o2r server-side")
        hit = pg.locate(place["x"], place["y"], place["z"])
        self.assertIsNotNone(hit, "Link is off the map at an entrance spawn?")
        rid = hit[0]["id"]
        best = None
        for pi in pg._region_polys[rid]:
            cen = pg.polys[pi]["cen"]
            d = math.hypot(cen[0] - place["x"], cen[2] - place["z"])
            if not 100.0 <= d <= 250.0:
                continue
            clr, _ = pg.wall_distance(rid, cen[0], cen[2])
            if clr < 20.0:
                continue
            if best is None or d < best[0]:
                best = (d, cen)
        if best is None:
            self.skipTest("no clear same-region target near this spawn")
        return best[1][0], best[1][2]

    # -- the pins ----------------------------------------------------------

    def test_1_the_cliff_refused_cold_with_zero_movement(self):
        # docs/30 acceptance criterion 1, as a pin: cross-region target
        # refused in under 0.5 s with zero movement measured — position
        # sampled before and after, in the body itself.
        self.warp_to_ground()
        out = self.probe(*TUNNEL_INTERIOR)
        self.assertIn("refused", out, out)
        self.assertIn("target is in", out["refused"])
        self.assertIn("ways out", out["refused"].lower())
        self.assertLessEqual(out["moved"], 2.0,
                             "a refusal must not move Link at all")
        self.assertLess(out["elapsed_s"], 0.5,
                        "the refusal must be instant, not a timeout")

    def test_2_reachable_agrees_with_the_walk(self):
        self.warp_to_ground()
        out = self.probe(*TUNNEL_INTERIOR, mode="query")
        self.assertIsNotNone(out["refusal"], "the cliff must query as refused")
        self.assertIn("target is in", out["refusal"])
        self.assertLessEqual(out["moved"], 2.0, "reachable is a QUERY")
        tx, tz = self.elect_walkable_target()
        out2 = self.probe(tx, tz, mode="query")
        self.assertIsNone(out2["refusal"],
                          f"elected target should be walkable: {out2}")
        self.assertLessEqual(out2["moved"], 2.0)

    def test_3_a_routed_walk_arrives_map_verified(self):
        self.warp_to_ground()
        tx, tz = self.elect_walkable_target()
        out = self.probe(tx, tz, timeout=90.0)
        self.assertIn("result", out, out)
        self.assertTrue(out["result"]["ok"], out)
        self.assertGreaterEqual(out["moved"], 60.0,
                                "the walk was supposed to actually walk")
        px, _, pz = out["pos"]
        self.assertLess(math.hypot(px - tx, pz - tz), 45.0,
                        "Link is not where walk_to claims he arrived")


if __name__ == "__main__":
    unittest.main()
