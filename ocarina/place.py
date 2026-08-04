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
- Localization is XZ point-in-poly with a foot tolerance: Link mid-air
  over a lower floor localizes to that floor. `on_mesh` is honest about
  "no floor below at all" (the void, unmapped space), not about
  airborne-over-floor.
- `fell` is suppressed while a traverse leg is declared — the primitive
  verifies its own arrival and its failure is the louder story.
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


class TraverseRefused(Exception):
    """The request is illegal BY THE MAP (off-mesh, unknown name,
    non-adjacent, candidate edge) or unsupported: refused cleanly before
    any movement. Never approximated — silent approximation of an
    illegal request is the v6 failure wearing a helpful face."""


class TraverseFailed(Exception):
    """The leg was legal but did not complete (grab never took, stalled
    on the wall, arrived somewhere else). Movement may have happened."""


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

    def route_in_region(self, rid: int, start, goal_xz) -> list:
        """Poly-centroid waypoints from `start` (x, y, z) to the region
        poly nearest `goal_xz`, staying inside region `rid`. This is the
        motor half of the cognition/motor line: steering inside a known
        region is foot placement, not route choice."""
        import heapq
        members = self._region_polys.get(rid) or []
        if not members:
            return []

        def xz_dist(cen, pt):
            return math.hypot(cen[0] - pt[0], cen[2] - pt[1])

        si = min(members, key=lambda i: xz_dist(self.polys[i]["cen"],
                                                (start[0], start[2])))
        gi = min(members, key=lambda i: xz_dist(self.polys[i]["cen"], goal_xz))
        goal = self.polys[gi]["cen"]
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
                if self.polys.get(nb, {}).get("r") != rid:
                    continue
                t = g[cur] + math.dist(self.polys[cur]["cen"], self.polys[nb]["cen"])
                if t < g.get(nb, math.inf):
                    g[nb] = t
                    came[nb] = cur
                    heapq.heappush(pq, (t + math.dist(self.polys[nb]["cen"], goal), nb))
        if path is None:
            return []
        # Simplify: unsmoothed centroid polylines zigzag (lab v0 note);
        # keep a waypoint only when it moves ~a body-length.
        points = [(self.polys[i]["cen"][0], self.polys[i]["cen"][2]) for i in path]
        out = []
        for pt in points:
            if not out or math.hypot(pt[0] - out[-1][0], pt[1] - out[-1][1]) >= 60.0:
                out.append(pt)
        if points and (not out or out[-1] != points[-1]):
            out.append(points[-1])
        return out


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
        self._prev = None                # (scene, rid, floor_y) last ON-MESH fix
        self._prev_region_narrated = None
        self._leg = None                 # declared traverse leg (edge name)

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
        if hit is not None:
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
            if (not region.get("sliver")
                    and full != self._prev_region_narrated):
                self._prev_region_narrated = full
                events.append({"event": "place", "cue": "region_entered",
                               "region": full,
                               "desc": judge_size(region["area"])})
            if (prev is not None and prev[0] == scene and prev[1] != rid
                    and floor_y < prev[2] - FELL_MIN_DROP
                    and not on_wall and not prev[3]
                    and leg is None):
                events.append({"event": "place", "cue": "fell",
                               "region": full,
                               "drop": round(prev[2] - floor_y, 1),
                               "desc": f"dropped {judge_height(prev[2] - floor_y)}"})
            self._prev = (scene, rid, floor_y, on_wall)
        return events

    # -- traverse support -------------------------------------------------------

    def begin_leg(self, edge_name: str) -> None:
        with self._lock:
            self._leg = edge_name

    def end_leg(self) -> None:
        with self._lock:
            self._leg = None

    def resolve_traverse(self, state: dict, target: str) -> dict:
        """Validate a traverse request against the map — ALL refusal
        semantics live here, before any movement (docs/25: refusal is a
        clean error, never best-effort approximation). Returns the leg:
        {graph, edge, direction, from_rid, to_rids, waypoints, at}."""
        if self.o2r_path is None:
            raise TraverseRefused(
                "place sense not available: the server was started without "
                "--o2r, so there is no map to validate against — traverse "
                "refuses rather than guesses")
        scene = (state or {}).get("scene", -1)
        graph = self.graph_for(scene)
        if graph is None:
            raise TraverseRefused(
                f"no map for scene 0x{scene:02X} (see the journal "
                f"diagnostic) — traverse refuses rather than guesses")
        player = (state or {}).get("player") or {}
        pos = player.get("pos")
        if not pos:
            raise TraverseRefused("no player in the snapshot")
        x, y, z = (float(v) for v in pos)
        hit = graph.locate(x, y, z)
        if hit is None:
            raise TraverseRefused(
                "you are OFF THE MAP here (no floor below within "
                "tolerance: the void, mid-air, or unmapped space) — get "
                "onto known floor before traversing")
        region, _floor_y = hit
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

        regions = []
        for r in sorted(graph.regions.values(), key=lambda r: r["y_min"]):
            if r.get("sliver"):
                continue
            name = graph.region_name(r)
            ways = []
            for leg in graph.legs_from(r["id"]):
                e = leg["edge"]
                to = graph.regions[leg["to"]]
                ways.append(
                    f"{e['kind']} {'up' if leg['direction'] == 'up' else 'down'} "
                    f"to {graph.region_name(to)} — "
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

        unlinked = [graph.edge_name(e) for e in graph.climb_edges
                    if not e["linked"]]
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
                "REVEAL GRAIN honesty gap (docs/25): this document currently "
                "shows the whole scene at entry; the blessed grain is the "
                "game's own minimap (rooms as entered) and lands when "
                "region->room membership exists — over-revealing, loudly",
            ],
        }
        if slivers:
            body["notes"].append(f"{slivers} sliver region(s) hidden "
                                 f"(connectivity plumbing, not places)")
        if unlinked:
            body["unlinked_columns"] = unlinked
            body["notes"].append("unlinked climb columns are instrument "
                                 "gaps: visible, not traversable")
        return body
