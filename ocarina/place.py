"""The place sense: generated region graphs, the field localizer, and the
presentation layer — dojo docs/25, RATIFIED by AJ 2026-08-03 (the fifth
flight, docs/24, is the evidence base; `lab/navgraph/` was the prototype
and keeps the debug viewer + the o'clock regression).

The thesis, as blessed: regions (walkable surface, flood-filled) + typed
edges (climb columns; drop/jump stay unverified candidates), GENERATED
from the scene's own collision data, never authored. Topology for the
mind, raw polys for the body — the already-blessed two-audience split,
applied to space. Evocative names are the MIND's job (its knowledge
files); this module only guarantees identifiers are deterministic
(navgraph.py's geometry-derived names) so knowledge can accrue on them.

Deliberate absences — each is a ruling, not an oversight:

- NO multi-leg route planner. Cross-region routing is cognition and
  belongs to the mind over `oot://place` (docs/25, ruled: "the mind
  should route itself"). This module plans WITHIN a region (poly-level
  steering to a named edge — foot placement, motor) and refuses
  everything else. There is deliberately no plan() here to call.
- NO coordinates in the presented document. Judgments in eye-units and
  run-time; the quantized centroid inside a region NAME is an
  identifier, not a coordinate feed (the blessed naming scheme). Exact
  numbers live body-side — plus the player's OWN pose in the digest
  (the self-pose exemption: superhuman knowledge of OTHERS is where
  unfairness lives; confidence about SELF is an accessibility
  obligation).
- Candidate (drop/jump) edges are boundary-proximity guesses: presented
  as unverified, excluded from leg planning and from `traverse` by
  construction — the map does not vouch for them (the v6 void jump is
  the failure this kills).

Honesty gaps, flagged rather than hidden (the senses.py discipline):

- REVEAL GRAIN: the blessing is the game's own minimap grain (dungeon
  rooms reveal as entered; Map/Compass effects shelved with the
  principle recorded). v0 reveals the WHOLE scene graph at entry:
  region->room membership is not derivable from the collision header
  alone (rooms live in room files, and the wire does not carry the
  player's room id yet). This sense currently OVER-reveals topology and
  says so — loud here and in the backlog, with the follow-up named:
  `room` on the wire, region->room partition, gate the document.
- Localization is XZ point-in-poly with a foot tolerance over the
  COLLISION MESH ONLY — actor surfaces (the Deku Tree atrium's floor
  web, pushblocks, platforms) are not in it. As of 0.13.0 (docs/30
  order-of-work step 2, closing docs/28 learning 4) the fix carries a
  STANDING check: when Link's own y is more than STAND_TOL above the
  located floor he is airborne or actor-borne, NOT in that region — so
  `on_mesh` reads False with `region` absent, the routing verbs refuse
  with the height named instead of refusing from a wrong region, and
  the event anchors hold their last standing fix (the six false `fell`
  narrations can no longer even set up). Still open: WHICH surface Link
  is actually on (consulting the census for it is a design item), and a
  region whose floors stack in y can mis-pick under the standing band.
- `fell` is suppressed while a traverse leg is declared — the primitive
  verifies its own arrival and its failure is the louder story.

0.13.0, THE ROUTED WALK (dojo docs/30, RATIFIED by AJ 2026-08-07, all
open calls as recommended): the region is already the answer — a target
in another walkable component is not walk-reachable BY CONSTRUCTION, and
a same-region target already has `route_in_region`'s A*. This module
grows `resolve_walk` (the shared target-validation front end; all of
`game.walk_to`'s refusal grammar lives here, before any movement) and
clearance-aware routing (a combat-safety requirement, not a quality
knob — AJ's flight testimony: wall-scrape slowed Link enough to get hit.
The A* penalizes wall-adjacent polys and waypoints hold an ADAPTIVE
offset from region boundaries: the desired offset in open space, the
midline in pinches, never refusing a corridor Link physically fits —
the maze recon formula, `min(desired, (width - link_diameter) / 2)`).
The exception family is renamed Route*/the Traverse names aliased (open
call 5): one refusal family, one `except` clause, no graded body broken.
Fog coherence (docs/34, ratified as one story): when the discovery grain
lands in 0.14.0, refusals must degrade to "somewhere you haven't been"
instead of naming an undiscovered region — the naming here is the
pre-fog form.
"""

from __future__ import annotations

import math
import threading
import time
import zipfile
from pathlib import Path
from typing import Optional

from .collision import load_from_o2r
from .navgraph import distill
from .protocol import PLAYER_STATE1_ON_A_WALL

#: Scene id -> o2r scene directory name. Coverage leads the frontier
#: (SURFACE.md): this table is the frontier's neighborhood, extended one
#: region ahead of the player, forever. An id not listed here is a LOUD
#: per-scene diagnostic, never a silent blank map. Ids from Shipwright's
#: scene_table.h.
SCENE_DIRS = {
    0x00: "ydan",         # Inside the Deku Tree — the fifth flight's map
    0x11: "ydan_boss",    # Gohma's lair
    0x2D: "kokiri_shop",
    0x34: "link_home",
    0x51: "spot00",       # Hyrule Field
    0x55: "spot04",       # Kokiri Forest
    0x5B: "spot10",       # Lost Woods
}

#: Scenes whose maps are FOGGED (docs/34, the discovery grain — the
#: game's own photographed predicate: overworld minimaps reveal whole
#: at entry; dungeon pause maps reveal per visited room and fog the
#: floor enumeration itself). Overworld scenes and interiors (the game
#: shows no minimap indoors at all — judgment call recorded in docs/34)
#: reveal fully at entry; scenes listed here present only what presence
#: has earned.
DUNGEON_SCENES = {0x00, 0x11}     # ydan, ydan_boss

#: Judged-unit anchors. CHILD_LINK_HEIGHT is the eye-unit ("about twice
#: your height"); RUN_UNITS_PER_S calibrated on the fifth flight's ring
#: arc (1,816 units walked in 5-7 s). Judgments are presented truth;
#: exact numbers stay body-side.
CHILD_LINK_HEIGHT = 55.0
RUN_UNITS_PER_S = 300.0

#: An unplanned downward region change smaller than this is a step, not
#: a fall (distill's own DROP_MIN_DY is 40; a fall should clear a step).
FELL_MIN_DROP = 60.0

#: locate(): accept floors up to this far above the query y (steps,
#: mid-stride noise) — ported from the lab localizer.
FOOT_TOL = 60.0

#: How far Link's own y may sit ABOVE the located floor and still count
#: as STANDING on it (docs/28 learning 4, fixed 0.13.0). Ordinary jumps
#: peak well under this; the atrium web hangs ~940 over the B2 floor.
#: Above it, the fix is airborne-or-actor-borne: not a place judgment.
STAND_TOL = 80.0

#: Link's collision cylinder is ~24 units across (maze recon, docs/30).
LINK_DIAMETER = 24.0

#: The offset a routed walk tries to hold from region boundaries — the
#: combat-safety requirement (docs/30 amendment: wall-scrape slowdown is
#: what turned "boulder nearby" into "boulder hit"). ADAPTIVE by the
#: recon formula min(desired, (width - link_diameter) / 2): held in open
#: space, the midline in pinches, and a corridor Link fits is NEVER
#: refused (a fixed 30-unit rule refuses the acceptance course itself).
DESIRED_CLEARANCE = 30.0

#: A* cost multiplier cap for polys closer to a wall than the desired
#: clearance (cost grows linearly toward this as clearance drops to 0).
WALL_GRAZE_PENALTY = 2.0

#: A corridor narrower than this around a waypoint is presented as "a
#: squeeze" — presentable truth: a sighted player sees narrowness
#: (docs/30 maze recon; Link himself is ~24 across).
SQUEEZE_WIDTH = 36.0


class RouteRefused(Exception):
    """The request is illegal BY THE MAP (off-mesh, unknown name, a
    different region, non-adjacent, candidate edge) or unsupported:
    refused cleanly before any movement. Never approximated — silent
    approximation of an illegal request is the v6 failure wearing a
    helpful face. Renamed from TraverseRefused at 0.13.0 (docs/30 open
    call 5: one refusal family for traverse AND walk_to); the Traverse
    name is aliased below, so every graded body's `except` still fits."""


class RouteFailed(Exception):
    """The route was legal but did not complete (grab never took,
    stalled, wedged, arrived somewhere else). Movement may have
    happened. Renamed from TraverseFailed at 0.13.0; alias below."""


#: The pre-0.13.0 names, aliased not subclassed: one family, one class
#: identity, so `except TraverseRefused` and `except RouteRefused` catch
#: exactly the same refusals (docs/30 open call 5, as recommended).
TraverseRefused = RouteRefused
TraverseFailed = RouteFailed


# -- judgments (the presented forms) ------------------------------------------

def judge_height(dy: float) -> str:
    n = abs(dy) / CHILD_LINK_HEIGHT
    if n < 0.6:
        return "a step"
    if n < 1.5:
        return "about your height"
    if n < 2.5:
        return "about twice your height"
    return f"about {round(n)} times your height"


def judge_size(area: float) -> str:
    side = math.sqrt(max(area, 0.0))
    if side < 150:
        return "a ledge"
    if side < 350:
        return "a small chamber"
    if side < 800:
        return "a room"
    return "a great hall"


def judge_run(units: float) -> str:
    s = units / RUN_UNITS_PER_S
    if s < 2:
        return "a few steps"
    if s < 6:
        return "a short run"
    return f"about a {round(s)}-second run"


def judge_elevation(dy: float) -> str:
    """Another floor's height relative to YOURS — route-agnostic but
    honest about which way is up."""
    if abs(dy) < 30:
        return "your level"
    updown = "above you" if dy > 0 else "below you"
    return f"{judge_height(dy)} {updown}"


#: Facing, presented. Binary yaw 0 = +z, 0x4000 = +x; the map convention
#: (lab viewer, the o'clock test) puts NORTH at -z, so yaw 0 faces south
#: and increasing yaw turns counterclockwise (south -> east).
_HEADINGS = ("s", "se", "e", "ne", "n", "nw", "w", "sw")


def heading_name(yaw: int) -> str:
    return _HEADINGS[round(((int(yaw) & 0xFFFF) / 0x2000)) % 8]


def clock_bearing(px: float, pz: float, pyaw: int, ax: float, az: float) -> int:
    """Clock-face bearing of a point relative to Link's facing — the
    docs/25 bearings rider's presented form (a sighted player calls
    directions clock-face; raw pos/yaw stay body-side). 12 = dead
    ahead; increasing yaw turns LEFT (game.py stick math), so a
    relative yaw of +0x4000 is 9 o'clock."""
    world = int(math.atan2(ax - px, az - pz) / math.pi * 0x8000) & 0xFFFF
    rel = (world - int(pyaw)) & 0xFFFF
    hour = (12 - round(rel * 12 / 0x10000)) % 12
    return 12 if hour == 0 else hour


# -- the graph, wrapped for field use -----------------------------------------

def _bary_xz(pt, a, b, c):
    (px, pz) = pt
    v0 = (c[0] - a[0], c[2] - a[2])
    v1 = (b[0] - a[0], b[2] - a[2])
    v2 = (px - a[0], pz - a[2])
    d00 = v0[0] * v0[0] + v0[1] * v0[1]
    d01 = v0[0] * v1[0] + v0[1] * v1[1]
    d11 = v1[0] * v1[0] + v1[1] * v1[1]
    d20 = v2[0] * v0[0] + v2[1] * v0[1]
    d21 = v2[0] * v1[0] + v2[1] * v1[1]
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-9:
        return False
    u = (d11 * d20 - d01 * d21) / den
    v = (d00 * d21 - d01 * d20) / den
    return u >= -0.02 and v >= -0.02 and (u + v) <= 1.02


def _plane_y(pt, a, b, c):
    u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    w = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    nx = u[1] * w[2] - u[2] * w[1]
    ny = u[2] * w[0] - u[0] * w[2]
    nz = u[0] * w[1] - u[1] * w[0]
    if abs(ny) < 1e-9:
        return (a[1] + b[1] + c[1]) / 3
    return a[1] - (nx * (pt[0] - a[0]) + nz * (pt[1] - a[2])) / ny


class PlaceGraph:
    """One scene's distilled graph plus the field operations: localization
    (ported from the lab's locate.py) and within-region poly routing
    (ported from the lab viewer/o'clock test A*). Pure/read-only after
    construction."""

    def __init__(self, scene_name: str, graph: dict):
        self.scene = scene_name
        self.raw = graph
        V = graph["vertices"]
        self.polys = {}
        for p in graph["floor_polys"]:
            a, b, c = (tuple(V[k]) for k in p["v"])
            cen = ((a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3,
                   (a[2] + b[2] + c[2]) / 3)
            self.polys[p["i"]] = {"i": p["i"], "r": p["r"], "adj": p["adj"],
                                  "tri": (a, b, c), "cen": cen}
        self.regions = {r["id"]: r for r in graph["regions"]}
        self.by_name = {self.region_name(r): r for r in graph["regions"]}
        self.climb_edges = graph["climb_edges"]
        self.edge_by_name = {self.edge_name(e): e for e in self.climb_edges}
        self.candidate_names = {f"{scene_name}:{e['name']}"
                                for e in graph.get("candidate_edges", [])}
        self._region_polys: dict = {}
        for pi, p in self.polys.items():
            self._region_polys.setdefault(p["r"], []).append(pi)
        # Region boundary segments (edges owned by exactly one floor poly)
        # — the wall-distance oracle behind clearance-aware routing
        # (docs/30: clearance is a combat-safety requirement). Distilled
        # graphs have carried these since 0.7.0; an old graph without
        # them routes as before, with no clearance shaping.
        self._boundaries = {int(k): v for k, v in
                            (graph.get("region_boundaries") or {}).items()}
        self._clearance: dict = {}      # rid -> {poly id -> wall distance}

    def region_name(self, r: dict) -> str:
        return f"{self.scene}:{r['name']}"

    def edge_name(self, e: dict) -> str:
        return f"{self.scene}:{e['name']}"

    def locate(self, x: float, y: float, z: float):
        """Best floor poly under (x, y, z) -> (region dict, floor_y), or
        None when no floor exists below within tolerance (the void,
        mid-fall, unmapped space)."""
        best = None
        for p in self.polys.values():
            a, b, c = p["tri"]
            if not _bary_xz((x, z), a, b, c):
                continue
            fy = _plane_y((x, z), a, b, c)
            if fy > y + FOOT_TOL:
                continue
            if best is None or fy > best[1]:
                best = (p, fy)
        if best is None:
            return None
        return self.regions[best[0]["r"]], best[1]

    def legs_from(self, rid: int) -> list:
        """The LINKED climb legs out of a region — the only edges the map
        vouches for. Candidates are deliberately not here (presentation
        shows them as unverified; routing and traverse never see them)."""
        out = []
        for e in self.climb_edges:
            if not e["linked"]:
                continue
            if rid in e["from"]:
                for t in e["to"]:
                    out.append({"edge": e, "direction": "up", "to": t})
            if rid in e["to"]:
                for f in e["from"]:
                    out.append({"edge": e, "direction": "down", "to": f})
        return out

    @staticmethod
    def _seg_dist_xz(seg, x: float, z: float) -> float:
        """XZ distance from (x, z) to one boundary segment [a, b]."""
        a, b = seg
        ax, az, bx, bz = a[0], a[2], b[0], b[2]
        dx, dz = bx - ax, bz - az
        den = dx * dx + dz * dz
        if den < 1e-12:
            return math.hypot(x - ax, z - az)
        t = max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / den))
        return math.hypot(x - (ax + t * dx), z - (az + t * dz))

    def wall_distance(self, rid: int, x: float, z: float):
        """(distance, closest boundary point) from (x, z) to region
        `rid`'s nearest boundary segment, or (inf, None) when the graph
        carries no boundaries (pre-0.7.0 shape) — corridor width around
        a point is about twice this, which is what the adaptive
        clearance formula and the squeeze judgment both read."""
        best, best_pt = math.inf, None
        for seg in self._boundaries.get(rid) or ():
            a, b = seg
            ax, az, bx, bz = a[0], a[2], b[0], b[2]
            dx, dz = bx - ax, bz - az
            den = dx * dx + dz * dz
            if den < 1e-12:
                qx, qz = ax, az
            else:
                t = max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / den))
                qx, qz = ax + t * dx, az + t * dz
            d = math.hypot(x - qx, z - qz)
            if d < best:
                best, best_pt = d, (qx, qz)
        return best, best_pt

    def polys_near(self, rid: int, x: float, z: float, radius: float) -> set:
        """Region polys whose centroid lies within XZ `radius` of
        (x, z) — the block set for a census-prop detour (game.walk_to)."""
        out = set()
        for pi in self._region_polys.get(rid, ()):
            cen = self.polys[pi]["cen"]
            if math.hypot(cen[0] - x, cen[2] - z) <= radius:
                out.add(pi)
        return out

    def _clearance_of(self, rid: int) -> dict:
        """poly id -> XZ distance from its centroid to the region's
        nearest boundary segment; computed once per region, cached."""
        cache = self._clearance.get(rid)
        if cache is None:
            segs = self._boundaries.get(rid) or ()
            cache = {}
            for pi in self._region_polys.get(rid, ()):
                cen = self.polys[pi]["cen"]
                cache[pi] = min((self._seg_dist_xz(s, cen[0], cen[2])
                                 for s in segs), default=math.inf)
            self._clearance[rid] = cache
        return cache

    def hold_clearance(self, rid: int, x: float, z: float, y_ref: float):
        """Nudge (x, z) away from region `rid`'s nearest boundary until
        it holds DESIRED_CLEARANCE — or until the midline, whichever
        comes first: the adaptive offset (docs/30 maze recon,
        `min(desired, (width - link_diameter) / 2)`) implemented as
        hill-climbing on wall distance, so a pinch converges to its
        middle and is never refused. Every step is locate-checked
        against the region: the nudge can never leave the floor it is
        smoothing (the v6 lesson, applied to route shaping)."""
        px, pz = x, z
        for _ in range(10):
            d, q = self.wall_distance(rid, px, pz)
            if q is None or d >= DESIRED_CLEARANCE or d <= 1e-6:
                break
            ux, uz = (px - q[0]) / d, (pz - q[1]) / d
            step = min(DESIRED_CLEARANCE - d, 8.0)
            cx, cz = px + ux * step, pz + uz * step
            hit = self.locate(cx, y_ref + FOOT_TOL, cz)
            if hit is None or hit[0]["id"] != rid:
                break
            d2, _ = self.wall_distance(rid, cx, cz)
            if d2 <= d + 0.25:
                break                     # the midline (or a pocket): done
            px, pz = cx, cz
        return px, pz

    def squeezes_along(self, rid: int, waypoints) -> list:
        """The waypoints whose corridor is near Link's own diameter —
        presentable truth (a sighted player sees narrowness), reported
        so the walk can say "a squeeze" instead of silently threading
        it. Width is judged as twice the wall distance (the midline
        approximation the clearance hold converges to)."""
        out = []
        for (x, z) in waypoints:
            d, q = self.wall_distance(rid, x, z)
            if q is not None and d * 2.0 < SQUEEZE_WIDTH:
                out.append({"at": (round(x, 1), round(z, 1)),
                            "width": round(d * 2.0, 1)})
        return out

    def route_in_region(self, rid: int, start, goal_xz,
                        blocked=frozenset()) -> list:
        """Poly-centroid waypoints from `start` (x, y, z) to the region
        poly nearest `goal_xz`, staying inside region `rid`. This is the
        motor half of the cognition/motor line: steering inside a known
        region is foot placement, not route choice.

        Clearance-aware since 0.13.0 (docs/30): wall-adjacent polys cost
        extra (WALL_GRAZE_PENALTY) and every waypoint is nudged to hold
        the adaptive offset from the region boundary — wall-scrape
        slowdown is a combat-safety hazard, not an aesthetic one.
        `blocked` polys are avoided entirely (the census-prop detour;
        the start poly is exempt — Link routes from wherever he stands)."""
        import heapq
        members = self._region_polys.get(rid) or []
        if not members:
            return []

        def xz_dist(cen, pt):
            return math.hypot(cen[0] - pt[0], cen[2] - pt[1])

        si = min(members, key=lambda i: xz_dist(self.polys[i]["cen"],
                                                (start[0], start[2])))
        open_members = [i for i in members if i not in blocked or i == si]
        if not open_members:
            return []
        gi = min(open_members,
                 key=lambda i: xz_dist(self.polys[i]["cen"], goal_xz))
        goal = self.polys[gi]["cen"]
        clearance = self._clearance_of(rid)

        def step_cost(j, base: float) -> float:
            clr = clearance.get(j, math.inf)
            if clr < DESIRED_CLEARANCE:
                base *= 1.0 + WALL_GRAZE_PENALTY * (
                    (DESIRED_CLEARANCE - clr) / DESIRED_CLEARANCE)
            return base

        g = {si: 0.0}
        came = {}
        pq = [(math.dist(self.polys[si]["cen"], goal), si)]
        closed = set()
        path = None
        while pq:
            _, cur = heapq.heappop(pq)
            if cur == gi:
                path = [cur]
                while cur in came:
                    cur = came[cur]
                    path.append(cur)
                path.reverse()
                break
            if cur in closed:
                continue
            closed.add(cur)
            for nb in self.polys[cur]["adj"]:
                if self.polys.get(nb, {}).get("r") != rid or nb in blocked:
                    continue
                t = g[cur] + step_cost(
                    nb, math.dist(self.polys[cur]["cen"], self.polys[nb]["cen"]))
                if t < g.get(nb, math.inf):
                    g[nb] = t
                    came[nb] = cur
                    heapq.heappush(pq, (t + math.dist(self.polys[nb]["cen"], goal), nb))
        if path is None:
            return []
        # Simplify: unsmoothed centroid polylines zigzag (lab v0 note);
        # keep a waypoint only when it moves ~a body-length. Then hold
        # clearance on the survivors (each carries its poly's y as the
        # locate reference for the nudge's stay-in-region check).
        points = [(self.polys[i]["cen"][0], self.polys[i]["cen"][2],
                   self.polys[i]["cen"][1]) for i in path]
        kept = []
        for pt in points:
            if not kept or math.hypot(pt[0] - kept[-1][0],
                                      pt[1] - kept[-1][1]) >= 60.0:
                kept.append(pt)
        if points and (not kept or kept[-1] != points[-1]):
            kept.append(points[-1])
        return [self.hold_clearance(rid, px, pz, py) for (px, pz, py) in kept]


# -- the sense -----------------------------------------------------------------

class PlaceSense:
    """Server-side place service: per-scene generate-and-cache, the
    digest's `place.*` sample, the `place` event producers
    (region_entered / fell), traverse validation, and the `oot://place`
    document. Thread-shared between the 20 Hz runtime tick and behavior
    threads (game.traverse), hence the lock."""

    def __init__(self, o2r_path: Optional[Path | str] = None):
        self.o2r_path = Path(o2r_path) if o2r_path else None
        self._lock = threading.Lock()
        self._graphs: dict = {}          # scene id -> PlaceGraph | None (failed)
        self._entries: Optional[dict] = None   # scene dir -> o2r entry name
        self._diags: list = []
        self._warned: set = set()        # one-shot diagnostic keys
        self._prev = None                # (scene, rid, floor_y, on_wall, y)
                                         # — the last ON-MESH fix
        self._prev_region_narrated = None
        self._leg = None                 # declared traverse leg (edge name)
        #: The discovery ledger (docs/34, 0.14.0) — attached by the
        #: runtime (it owns the save-file repo). None = fog OFF (the
        #: pre-0.14.0 whole-scene reveal), which is what standalone and
        #: test construction get unless they attach one.
        self.discovery = None

    # -- diagnostics (drained into the journal by the runtime) --------------

    def _diag(self, key, text: str) -> None:
        with self._lock:
            if key is not None:
                if key in self._warned:
                    return
                self._warned.add(key)
            self._diags.append(text)

    def drain_diagnostics(self) -> list:
        with self._lock:
            out, self._diags = self._diags, []
            return out

    # -- graph acquisition ---------------------------------------------------

    def _entry_for(self, scene_dir: str) -> Optional[str]:
        if self._entries is None:
            with zipfile.ZipFile(self.o2r_path) as z:
                names = z.namelist()
            self._entries = {}
            for n in names:
                if "_sceneCollisionHeader_" in n and n.split("/")[-2].endswith("_scene"):
                    self._entries.setdefault(n.split("/")[-2][:-len("_scene")], n)
        return self._entries.get(scene_dir)

    def graph_for(self, scene: int) -> Optional[PlaceGraph]:
        """The scene's graph, generated on first need and cached. Every
        failure mode is a loud diagnostic, once per scene — a missing map
        must never read as an empty world."""
        with self._lock:
            if scene in self._graphs:
                return self._graphs[scene]
        if self.o2r_path is None:
            self._diag("no-o2r", "place sense OFF: server started without "
                       "--o2r (the collision source); place.* is absent, "
                       "oot://place is empty, traverse refuses")
            with self._lock:
                self._graphs[scene] = None
            return None
        scene_dir = SCENE_DIRS.get(scene)
        graph = None
        if scene_dir is None:
            self._diag(("scene", scene),
                       f"place sense has NO MAP for scene 0x{scene:02X} — "
                       f"the coverage table (place.SCENE_DIRS) stops one "
                       f"region ahead of the frontier; extend it before "
                       f"playing here")
        else:
            try:
                entry = self._entry_for(scene_dir)
                if entry is None:
                    self._diag(("entry", scene),
                               f"place sense: no collision header for "
                               f"{scene_dir!r} in {self.o2r_path}")
                else:
                    t0 = time.monotonic()
                    mesh = load_from_o2r(str(self.o2r_path), entry)
                    graph = PlaceGraph(scene_dir, distill(mesh))
                    unlinked = sum(1 for e in graph.climb_edges if not e["linked"])
                    self._diag(None,
                               f"place sense distilled {scene_dir}: "
                               f"{len(graph.regions)} regions, "
                               f"{len(graph.climb_edges)} climb columns "
                               f"({unlinked} UNLINKED — instrument gaps, "
                               f"amber in the lab viewer) in "
                               f"{time.monotonic() - t0:.2f}s")
            except Exception as e:      # a bad parse must not kill the loop
                self._diag(("gen", scene),
                           f"place sense FAILED to distill {scene_dir}: "
                           f"{type(e).__name__}: {e}")
        with self._lock:
            self._graphs[scene] = graph
        return graph

    # -- the digest sample (place.*) ------------------------------------------

    def sample(self, state: dict) -> Optional[dict]:
        """The `place.*` digest section, or None (absent entity) when the
        sense has nothing honest to say. Self-pose is exact by ruling
        (docs/25: the self-pose exemption). Pre-play is gated like all
        narration (the attract demo is not the world)."""
        if not state or not state.get("save_loaded", False):
            return None
        player = state.get("player") or {}
        pos = player.get("pos")
        if not pos:
            return None
        graph = self.graph_for(state.get("scene", -1))
        if graph is None:
            return None
        x, y, z = (float(v) for v in pos)
        yaw = int(player.get("yaw", 0)) & 0xFFFF
        out = {"on_mesh": False, "x": x, "y": y, "z": z,
               "facing": yaw, "heading": heading_name(yaw)}
        hit = graph.locate(x, y, z)
        # STANDING gate (0.13.0, docs/28 learning 4): a floor far below
        # Link is not the floor he is ON — mid-air, or an actor surface
        # (the atrium web hangs ~940 over the B2 floor). on_mesh False +
        # region absent is the honest answer; naming the region below
        # him was the lie the six false narrations grew from.
        if hit is not None and y - hit[1] <= STAND_TOL:
            out["on_mesh"] = True
            out["region"] = graph.region_name(hit[0])
        return out

    # -- the event producers (the `place` category) ----------------------------

    def fold(self, state: dict) -> list:
        """One snapshot -> the `place` events to narrate: region_entered
        on non-sliver region change (arrival included), `fell` on an
        unplanned downward region change. Climbing is not falling; a
        declared traverse leg suppresses `fell` (the primitive verifies
        its own arrival)."""
        if not state or not state.get("save_loaded", False):
            return []
        player = state.get("player") or {}
        pos = player.get("pos")
        if not pos:
            return []
        scene = state.get("scene", -1)
        graph = self.graph_for(scene)
        if graph is None:
            return []
        x, y, z = (float(v) for v in pos)
        hit = graph.locate(x, y, z)
        # Not STANDING on the located floor (mid-air, or an actor
        # surface like the atrium web): no place judgment at all —
        # narrating the floor far below Link is how the ninth flight's
        # false stories started. The anchors keep the last standing fix,
        # so a genuine fall still narrates on LANDING.
        if hit is not None and y - hit[1] > STAND_TOL:
            hit = None
        flags1 = player.get("state_flags1", 0)
        on_wall = bool(flags1 & PLAYER_STATE1_ON_A_WALL)  # climbing != falling
        events = []
        with self._lock:
            prev, leg = self._prev, self._leg
            if hit is None:
                # Off-mesh: keep the last on-mesh fix as the fall anchor.
                return []
            region, floor_y = hit
            rid, full = region["id"], graph.region_name(region)
            # Presence is discovery (docs/34, 0.14.0): a standing fix in
            # a fogged scene earns the region for this save line, once,
            # with its own cue — the journal's exploration record. The
            # wire's `room` rides along as an observed binding for the
            # future room-grain reveal. Overworld scenes reveal whole at
            # entry, so nothing to earn there; slivers are plumbing, not
            # places.
            if (self.discovery is not None and scene in DUNGEON_SCENES
                    and not region.get("sliver")
                    and self.discovery.discover(scene, full,
                                                state.get("room"))):
                events.append({"event": "place", "cue": "region_discovered",
                               "region": full,
                               "desc": "first time here, this save line"})
            if (not region.get("sliver")
                    and full != self._prev_region_narrated):
                self._prev_region_narrated = full
                events.append({"event": "place", "cue": "region_entered",
                               "region": full,
                               "desc": judge_size(region["area"])})
            # A fall moves LINK down, not just the floor under him. The
            # located floor dropping is necessary but not sufficient: on
            # an actor surface (the atrium's floor web) a lateral step
            # re-localizes to the mesh floor far below while Link stands
            # still — six false narrations on the ninth flight (docs/28).
            if (prev is not None and prev[0] == scene and prev[1] != rid
                    and floor_y < prev[2] - FELL_MIN_DROP
                    and y < prev[4] - FELL_MIN_DROP
                    and not on_wall and not prev[3]
                    and leg is None):
                events.append({"event": "place", "cue": "fell",
                               "region": full,
                               "drop": round(prev[2] - floor_y, 1),
                               "desc": f"dropped {judge_height(prev[2] - floor_y)}"})
            self._prev = (scene, rid, floor_y, on_wall, y)
        return events

    # -- the reach rider (docs/30, ratified) ------------------------------------

    def judge_reach(self, state: dict, actor: dict):
        """The judged `reach` vocabulary for a presented actor — is the
        GROUND UNDER IT walkable from where Link stands? Returns
        "walkable" / "across a gap" / "up a climb" / "down a drop", or
        None when the sense has nothing honest to say (no map, Link not
        standing on the mesh, the actor over nothing mapped). This is
        the text form of the glance a sighted player takes before
        electing a target: judged words only, no numbers, and it
        annotates only entities the digest already presents — so it is
        sight-gated by inheritance and cannot leak an unseen actor.
        A flying enemy is judged by the floor beneath it: honest — the
        walk can reach UNDER it, which is what election needs."""
        if not state or not state.get("save_loaded", False):
            return None
        graph = self.graph_for(state.get("scene", -1))
        if graph is None:
            return None
        player = state.get("player") or {}
        ppos, apos = player.get("pos"), actor.get("pos")
        if not ppos or not apos or len(apos) < 3:
            return None
        x, y, z = (float(v) for v in ppos)
        hit = graph.locate(x, y, z)
        if hit is None or y - hit[1] > STAND_TOL:
            return None
        rid = hit[0]["id"]
        ahit = graph.locate(float(apos[0]), float(apos[1]) + FOOT_TOL,
                            float(apos[2]))
        if ahit is None:
            return None
        arid = ahit[0]["id"]
        if arid == rid:
            return "walkable"
        # Fog coherence (docs/34): the rider may only reference
        # discovered ground — toward undiscovered space the judgment is
        # honest about the mind's OWN map, not the world's.
        if self._fogged(state.get("scene", -1),
                        graph.region_name(ahit[0])):
            return "somewhere you haven't been"
        for leg in graph.legs_from(rid):
            if leg["to"] == arid:
                return ("up a climb" if leg["direction"] == "up"
                        else "down a drop")
        return "across a gap"

    def _fogged(self, scene: int, region_name: str) -> bool:
        """True when `region_name` may not be NAMED to the mind
        (docs/34): a fogged scene, a ledger attached, no presence
        earned. Overworld scenes and ledger-less construction (tests,
        standalone) are never fogged — the pre-0.14.0 reveal."""
        return (self.discovery is not None and scene in DUNGEON_SCENES
                and not self.discovery.known(scene, region_name))

    # -- traverse support -------------------------------------------------------

    def begin_leg(self, edge_name: str) -> None:
        with self._lock:
            self._leg = edge_name

    def end_leg(self) -> None:
        with self._lock:
            self._leg = None

    def _routing_fix(self, state: dict, verb: str):
        """The shared target-validation FRONT END (docs/30: one refusal
        family for both routing verbs): map available, player present,
        Link localized AND standing. Returns (graph, region, (x, y, z))
        or raises RouteRefused with the verb named."""
        if self.o2r_path is None:
            raise RouteRefused(
                f"place sense not available: the server was started without "
                f"--o2r, so there is no map to validate against — {verb} "
                f"refuses rather than guesses")
        scene = (state or {}).get("scene", -1)
        graph = self.graph_for(scene)
        if graph is None:
            raise RouteRefused(
                f"no map for scene 0x{scene:02X} (see the journal "
                f"diagnostic) — {verb} refuses rather than guesses")
        player = (state or {}).get("player") or {}
        pos = player.get("pos")
        if not pos:
            raise RouteRefused("no player in the snapshot")
        x, y, z = (float(v) for v in pos)
        hit = graph.locate(x, y, z)
        if hit is None:
            raise RouteRefused(
                "you are OFF THE MAP here (no floor below within "
                "tolerance: the void, mid-air, or unmapped space) — get "
                "onto known floor first")
        region, floor_y = hit
        if y - floor_y > STAND_TOL:
            # docs/28 learning 4, fixed 0.13.0: refusing FROM the floor
            # far below Link would name a region he is not in — refuse
            # with the height instead, so the story is true.
            raise RouteRefused(
                f"you are {y - floor_y:.0f} units ABOVE the mapped floor — "
                f"standing on something the map cannot see (an actor "
                f"surface?) or mid-air; the map cannot vouch for a route "
                f"from here")
        return graph, region, (x, y, z)

    def resolve_walk(self, state: dict, x: float, z: float,
                     blocked=frozenset()) -> dict:
        """Validate a routed-walk request (docs/30) — ALL of walk_to's
        map refusals live here, BEFORE any movement, each in
        milliseconds with a reason instead of 12 s of wall-grinding:
        no map / you off the map or not standing / target off the map /
        target in another region (the cliff — names the region and the
        legs out of yours) / no path inside the region. Returns
        {graph, rid, region, waypoints, squeezes, target}; `waypoints`
        end at the exact target. `blocked` polys are detoured (the
        census-prop pass in game.walk_to). Fog note (docs/34, ratified
        as one story): when the discovery grain lands, the cross-region
        refusal must stop naming an UNDISCOVERED region and degrade to
        "somewhere you haven't been" — still instant, still zero
        movement."""
        graph, region, pos = self._routing_fix(state, "the routed walk")
        rid = region["id"]
        tx, tz = float(x), float(z)
        # Localize the target at Link's own level first (a walk stays
        # level-ish by construction); if nothing is there, look with an
        # open ceiling so a ledge ABOVE still gets NAMED in the refusal
        # rather than reading as the void.
        hit = graph.locate(tx, pos[1], tz)
        if hit is None:
            hit = graph.locate(tx, 1e12, tz)
            if hit is None:
                raise RouteRefused(
                    f"target ({tx:.0f}, {tz:.0f}) is OFF THE MAP — the "
                    f"void, or space the map does not cover; there is "
                    f"nothing there to walk to")
        target_region = hit[0]
        if target_region["id"] != rid:
            legs = graph.legs_from(rid)
            known = sorted({graph.edge_name(l["edge"]) for l in legs})
            ways = ", ".join(known) if known else "no linked edges"
            # Fog coherence (docs/34, ratified with docs/30 as one
            # story): an UNDISCOVERED region is never named — the
            # refusal stays instant and zero-movement, but degrades to
            # "somewhere you haven't been". Edge names stay: the wall
            # is visible from where Link stands; its far side is not.
            if self._fogged((state or {}).get("scene", -1),
                            graph.region_name(target_region)):
                raise RouteRefused(
                    f"target is somewhere you haven't been — not "
                    f"walk-reachable from here: regions are separate "
                    f"walkable components by construction. The ways out "
                    f"from here: {ways} (traversing a leg is how space "
                    f"is earned — the frontier is in oot://place)")
            raise RouteRefused(
                f"target is in {graph.region_name(target_region)}, not "
                f"{graph.region_name(region)} — not walk-reachable: "
                f"regions are separate walkable components by "
                f"construction. The ways out from here: {ways} "
                f"(cross-region routing is yours, over oot://place)")
        waypoints = graph.route_in_region(rid, pos, (tx, tz),
                                          blocked=blocked)
        if not waypoints:
            raise RouteRefused(
                f"no path inside {graph.region_name(region)} from where "
                f"you stand to ({tx:.0f}, {tz:.0f}) — a pinched or "
                f"degenerate component: as much an instrument diagnostic "
                f"as a refusal")
        if math.hypot(waypoints[-1][0] - tx, waypoints[-1][1] - tz) > 1.0:
            waypoints = waypoints + [(tx, tz)]
        return {"graph": graph, "rid": rid,
                "region": graph.region_name(region),
                "waypoints": waypoints,
                "squeezes": graph.squeezes_along(rid, waypoints),
                "target": (tx, tz)}

    def resolve_traverse(self, state: dict, target: str) -> dict:
        """Validate a traverse request against the map — ALL refusal
        semantics live here, before any movement (docs/25: refusal is a
        clean error, never best-effort approximation). Returns the leg:
        {graph, edge, direction, from_rid, to_rids, waypoints, at}."""
        graph, region, (x, y, z) = self._routing_fix(state, "traverse")
        rid = region["id"]

        name = target if ":" in target else f"{graph.scene}:{target}"
        if name in graph.candidate_names:
            raise TraverseRefused(
                f"{name} is an UNVERIFIED candidate edge (a drop/jump "
                f"proximity guess): traverse refuses candidates by "
                f"construction — the map does not vouch for them")
        edge = graph.edge_by_name.get(name)
        to_rids = None
        if edge is None:
            # Maybe a region name: legal iff adjacent via a linked edge.
            target_region = graph.by_name.get(name)
            if target_region is None:
                legs = graph.legs_from(rid)
                known = sorted({graph.edge_name(l["edge"]) for l in legs})
                raise TraverseRefused(
                    f"unknown place {target!r} — regions and climb columns "
                    f"are named in oot://place (from here: "
                    f"{', '.join(known) if known else 'no linked edges'})")
            if target_region["id"] == rid:
                raise TraverseRefused(f"already in {name}")
            options = [l for l in graph.legs_from(rid)
                       if l["to"] == target_region["id"]]
            if not options:
                raise TraverseRefused(
                    f"{name} is not adjacent to "
                    f"{graph.region_name(region)}: no linked edge connects "
                    f"them. Cross-region routing is yours — plan it "
                    f"region-by-region over oot://place")
            leg = options[0]
            edge, direction = leg["edge"], leg["direction"]
            to_rids = [leg["to"]]
        else:
            if rid in edge["from"]:
                direction, to_rids = "up", list(edge["to"])
            elif rid in edge["to"]:
                direction, to_rids = "down", list(edge["from"])
            else:
                raise TraverseRefused(
                    f"{name} does not touch {graph.region_name(region)} "
                    f"(it links regions {edge['from']} -> {edge['to']})")
            if not edge["linked"]:
                raise TraverseRefused(
                    f"{name} is UNLINKED (an instrument gap: the distiller "
                    f"could not attach both ends to floor) — not "
                    f"traversable until the graph closes it")
        if direction == "down":
            raise TraverseRefused(
                f"descending {name} is not built yet (climbing DOWN needs "
                f"its own grab sequence; the fifth flight only ever "
                f"climbed up) — an honest not-yet, not a refusal of the "
                f"map. Do not walk off the edge instead: that is a fall")
        if edge["kind"] == "crawl":
            raise TraverseRefused(
                f"crawling {name} is not built yet (crawlspace entry "
                f"needs its own body) — an honest not-yet")
        # Aim the grab at a FLOOR-TOUCHING base segment, not at "at":
        # a tall curved sheet's 3D centroid can hang mid-air over
        # unreachable floor (sixth flight: the ring->3F vine sheet's
        # centroid sat beside a treasure chest parked over a real gap
        # in the vines — three behavior versions chased it). Pick the
        # longest bottom segment whose 40-unit-out stand point the
        # from-region owns; grab = its midpoint, walked to from the
        # stand. Falls back to "at" for old graphs without segments.
        at = edge["at"]
        stand, grab = (at[0], at[2]), None
        if direction == "up":
            best = None
            for a, b in edge.get("base_segments") or []:
                seg_len = math.hypot(a[0] - b[0], a[2] - b[2])
                if seg_len < 1e-6:
                    continue
                mx, mz = (a[0] + b[0]) / 2.0, (a[2] + b[2]) / 2.0
                my = (a[1] + b[1]) / 2.0
                ux, uz = (b[0] - a[0]) / seg_len, (b[2] - a[2]) / seg_len
                for sgn in (1.0, -1.0):
                    sx, sz = mx + sgn * 40.0 * uz, mz - sgn * 40.0 * ux
                    h = graph.locate(sx, my, sz)
                    if h is not None and h[0]["id"] == rid:
                        if best is None or seg_len > best[0]:
                            best = (seg_len, (sx, sz), (mx, mz))
                        break
            if best is not None:
                stand, grab = best[1], best[2]
        waypoints = graph.route_in_region(rid, (x, y, z), stand)
        return {"graph": graph, "edge": edge, "name": graph.edge_name(edge),
                "direction": direction, "from_rid": rid, "to_rids": to_rids,
                "waypoints": waypoints, "at": stand, "grab": grab,
                "top_y": edge["y_hi"]}

    # -- presentation (oot://place) ---------------------------------------------

    def status_line(self, state: Optional[dict]) -> str:
        if self.o2r_path is None:
            return "off (no --o2r)"
        if not state:
            return "waiting for a snapshot"
        scene = state.get("scene", -1)
        with self._lock:
            graph = self._graphs.get(scene)
        if graph is None:
            return (f"no map for scene 0x{scene:02X}"
                    if scene in self._graphs or scene not in SCENE_DIRS
                    else "map not yet generated")
        return f"{graph.scene} ({len(graph.regions)} regions)"

    def document(self, state: Optional[dict]) -> dict:
        """The `oot://place` body: the scene's graph as judgments over
        stable names — the minimap rebuilt per the UI principle. No raw
        coordinates (names carry quantized centroids by the blessed
        scheme; that is identity, not a coordinate feed)."""
        if self.o2r_path is None:
            return {"error": "place sense off: server started without --o2r"}
        if not state:
            return {"error": "no game snapshot yet"}
        if not state.get("save_loaded", False):
            return {"error": "pre-play (attract demo / title): the world "
                             "has not started"}
        scene = state.get("scene", -1)
        graph = self.graph_for(scene)
        if graph is None:
            return {"error": f"no map for scene 0x{scene:02X} — see the "
                             f"journal diagnostic"}
        you = self.sample(state) or {}
        you_y = you.get("y")
        here = you.get("region")

        # The discovery grain (docs/34, 0.14.0): overworld scenes and
        # interiors reveal whole at entry (the game's own photographed
        # minimap predicate); DUNGEON_SCENES present only what presence
        # has earned, with legs into undiscovered space as typed
        # frontiers — "destination unknown". Self is never fogged.
        fogged_scene = (self.discovery is not None
                        and scene in DUNGEON_SCENES)
        items = (state or {}).get("dungeon_items") or {}
        has_map = bool(items.get("map"))

        def revealed(name: str) -> bool:
            return (not fogged_scene or name == here
                    or self.discovery.known(scene, name))

        regions = []
        outlined = 0
        for r in sorted(graph.regions.values(), key=lambda r: r["y_min"]):
            if r.get("sliver"):
                continue
            name = graph.region_name(r)
            if not revealed(name):
                # The Dungeon Map widens to OUTLINE grade only (docs/34
                # open call 3, ratified: the paper map shows shapes,
                # not vines) — existence and rough placement; ways and
                # detail stay presence-gated.
                if has_map:
                    entry = {"region": name, "size": judge_size(r["area"]),
                             "outline": "from the Dungeon Map — never "
                                        "stood in; ways and detail are "
                                        "presence-gated"}
                    if you_y is not None:
                        entry["elevation"] = judge_elevation(r["y_min"] - you_y)
                    regions.append(entry)
                    outlined += 1
                continue
            ways = []
            for leg in graph.legs_from(r["id"]):
                e = leg["edge"]
                to = graph.regions[leg["to"]]
                to_name = graph.region_name(to)
                updown = "up" if leg["direction"] == "up" else "down"
                if not revealed(to_name):
                    # The frontier: the wall is visible from here (kind,
                    # height, its geometric name for traverse); its far
                    # side is not. Traversing it IS exploration.
                    if e["kind"] == "crawl":
                        ways.append(f"crawl through — destination unknown "
                                    f"({graph.edge_name(e)})")
                    else:
                        ways.append(
                            f"{e['kind']} {updown} — destination unknown — "
                            f"{judge_height(e['y_hi'] - e['y_lo'])} of "
                            f"climb ({graph.edge_name(e)})")
                elif e["kind"] == "crawl":
                    # A crawl is horizontal — "up/down" would be the
                    # linker's bookkeeping leaking into narration.
                    # (Linked since 0.13.0's end-clustering fix; still
                    # an honest not-yet to traverse.)
                    ways.append(f"crawl through to {to_name} "
                                f"({graph.edge_name(e)})")
                else:
                    ways.append(
                        f"{e['kind']} {updown} to {to_name} — "
                        f"{judge_height(e['y_hi'] - e['y_lo'])} of climb "
                        f"({graph.edge_name(e)})")
            entry = {
                "region": name,
                "size": judge_size(r["area"]),
                "ways": ways,
            }
            if you_y is not None:
                entry["elevation"] = judge_elevation(r["y_min"] - you_y)
            if r["y_max"] - r["y_min"] > 60:
                entry["slope"] = (f"the floor itself rises "
                                  f"{judge_height(r['y_max'] - r['y_min'])} "
                                  f"end to end")
            if name == here:
                entry["you_are_here"] = True
            regions.append(entry)

        unlinked = []
        for e in graph.climb_edges:
            if e["linked"]:
                continue
            if fogged_scene and not any(
                    revealed(graph.region_name(graph.regions[rid]))
                    for rid in (list(e["from"]) + list(e["to"]))):
                continue        # an instrument gap in undiscovered space
                                # would name geometry presence hasn't earned
            unlinked.append(graph.edge_name(e))
        slivers = sum(1 for r in graph.regions.values() if r.get("sliver"))
        body = {
            "scene": graph.scene,
            "scene_id": scene,
            "you": {"region": here, "on_mesh": you.get("on_mesh", False),
                    "heading": you.get("heading")},
            "regions": regions,
            "candidates": {
                "count": len(graph.raw.get("candidate_edges", [])),
                "note": "drop/jump guesses the map does NOT vouch for — "
                        "never traversable via traverse; a drop you can "
                        "SEE is knowledge you may act on with a body, at "
                        "your own risk",
            },
            "notes": [
                "names are stable identifiers (geometry-derived); calling "
                "places what you like is your job, in your knowledge files",
            ],
        }
        if fogged_scene:
            body["notes"].append(
                "DISCOVERY GRAIN (docs/34): this scene is fogged — regions "
                "appear as you stand in them, frontier legs read "
                "'destination unknown', and traversing one is how space "
                "is earned; discovery persists with this save line")
            body["notes"].append(
                "RETARGETED honesty gap (docs/25 -> docs/34): the game "
                "reveals whole ROOMS on entry; scene collision carries no "
                "room table, so this document under-reveals at region "
                "grain until the game's own room tables are read — "
                "conservative, never X-ray")
            if not items:
                body["notes"].append(
                    "Dungeon Map/Compass widening awaits the instrument: "
                    "no dungeon_items on the wire yet")
            elif has_map:
                body["notes"].append(
                    f"{outlined} region(s) at outline grade from the "
                    f"Dungeon Map")
            if items.get("compass"):
                body["notes"].append(
                    "Compass markers are deferred: the census carries only "
                    "the loaded room's actors, so cross-room chest markers "
                    "await a wire rider")
        else:
            body["notes"].append(
                "this scene reveals whole at entry — the game's own "
                "overworld-minimap predicate (docs/34, photographed "
                "2026-08-07)")
        if slivers:
            body["notes"].append(f"{slivers} sliver region(s) hidden "
                                 f"(connectivity plumbing, not places)")
        if unlinked:
            body["unlinked_columns"] = unlinked
            body["notes"].append("unlinked climb columns are instrument "
                                 "gaps: visible, not traversable")
        return body
