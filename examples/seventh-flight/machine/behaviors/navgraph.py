"""Fifth flight (2026-08-03): navigation legs compiled from the lab navgraph.

The mind holds a region graph distilled offline from this scene's collision
mesh (ocarina/lab/navgraph — parse, flood-fill, climb-column linking). These
bodies are that map COMPILED INTO WAYPOINTS by the mind at authoring time:
the graph itself stays lab-side; the body just walks the plan and verifies
it against local truth (scan_climbable at the wall, census distances, its
own y). Room 0's chest sits on region 2 — the spiral walkway that climbs
280->400 around the atrium — reached by the vine column the graph links
region 0 -> region 2 at (116, y0..280, -304).

Fall honesty: walk_ring carries its own expected-height table and aborts
the moment Link is materially below it — the hand-rolled ancestor of the
`fell` event this flight exists to argue for.
"""

import time

from ocarina.behavior import Behavior, BehaviorAbort
from ocarina.game import Game

ACTOR_EN_BOX = 0x000A          # the treasure chest

# Graph: vine column linking region 0 (ground floor) to region 2 (spiral).
VINE_BASE = (116.0, -304.0)

# Ground-floor approach, east of the central web hole (a bg actor the graph
# cannot know; radius ~150 around (30, 65) — never path over it).
GF_WAYPOINTS = [(250.0, 350.0), (330.0, 100.0), (250.0, -150.0)]

# Region 2's spiral, subsampled from poly centroids in ascending-y order
# (mid-walkway line). Third field: expected floor y, for the fall detector.
RING_WAYPOINTS = [
    (133.0, -372.0, 280.0),
    (240.0, -320.0, 290.0),
    (300.0, -256.0, 305.0),
    (348.0, -200.0, 318.0),
    (382.0, -130.0, 333.0),
    (400.0, -50.0, 350.0),
    (390.0, 40.0, 360.0),
    (380.0, 130.0, 360.0),
    (330.0, 230.0, 360.0),
    (260.0, 290.0, 360.0),
]

CHEST_NEAR_XZ = 160.0          # close enough to hand over to charge_chest
CHEST_NEAR_Y = 80.0
FELL_TOL = 120.0               # this far below the expected y = we fell
WAYPOINT_WITHIN = 45.0

CLIMB_MAGNITUDE = 80
GRAB_S = 12.0
CLIMB_S = 30.0
STALL_S = 3.0
GAIN = 5.0


def _walk_leg(game: Game, x: float, z: float, within: float, budget_s: float):
    """walk_to_point until arrival or genuine stall (climb.py's pattern)."""
    deadline = time.monotonic() + budget_s
    best = game.dist_to_point(x, z)
    while time.monotonic() < deadline:
        if game.dist_to_point(x, z) <= within:
            return
        game.walk_to_point(x, z, within=within, timeout=4.0)
        now = game.dist_to_point(x, z)
        if now < best - 20.0:
            best = now
        elif time.monotonic() > deadline - budget_s / 2:
            break
    if game.dist_to_point(x, z) > within * 2:
        raise BehaviorAbort(
            f"stalled {game.dist_to_point(x, z):.0f} from waypoint "
            f"({x:.0f}, {z:.0f})")


def _goto_vine_body(game: Game, ctx) -> None:
    """Cross the ground floor east of the web hole, then climb the graph's
    region-0 -> region-2 vine column. Grab/ascend rules are climb.py's
    three z_player.c facts (no camera term, never press A, grab needs
    forward velocity) — see that file's header."""
    for (x, z) in GF_WAYPOINTS:
        _walk_leg(game, x, z, within=70.0, budget_s=20.0)
    _walk_leg(game, VINE_BASE[0], VINE_BASE[1], within=85.0, budget_s=20.0)

    # Probe verifies graph: the wall face from up close, graph as fallback.
    rays = game.scan_climbable(rays=24, length=300)
    if rays:
        face = min(rays, key=lambda r: r.get("dist", 1e9))
        pos = face.get("pos") or []
        tx, tz = (pos[0], pos[2]) if len(pos) >= 3 else VINE_BASE
    else:
        tx, tz = VINE_BASE
    bearing = game.world_yaw_to_point(tx, tz)

    deadline = time.monotonic() + GRAB_S
    while time.monotonic() < deadline and not game.climbing():
        game.walk_bearing(bearing, seconds=0.3)
    if not game.climbing():
        raise BehaviorAbort(
            f"walked into the vine wall at ({tx:.0f}, {tz:.0f}) for "
            f"{GRAB_S:.0f}s, never got a grip")

    start_y = (game.pos() or (0.0, 0.0, 0.0))[1]
    best_y = start_y
    stall_until = time.monotonic() + STALL_S
    deadline = time.monotonic() + CLIMB_S
    while time.monotonic() < deadline:
        if not (game.climbing() or game.mounting_ledge()):
            break
        game.pad(stick=(0, CLIMB_MAGNITUDE))
        game.wait(0.2)
        y = (game.pos() or (0.0, best_y, 0.0))[1]
        if y > best_y + GAIN:
            best_y, stall_until = y, time.monotonic() + STALL_S
        elif time.monotonic() > stall_until:
            game.pad_clear()
            raise BehaviorAbort(
                f"stuck on the vine at +{best_y - start_y:.0f} for {STALL_S:.0f}s")
    game.pad_clear()
    game.wait(0.6)


def _on_ring(game: Game, initial: dict, events: list) -> bool:
    """Success = off the wall at the walkway's height (graph: region 2
    starts at y 280; accept a small mount shortfall)."""
    now = game.pos()
    return (now is not None and now[1] >= 250.0 and not game.climbing())


def _chest(game: Game):
    boxes = game.actors(actor_id=ACTOR_EN_BOX)
    if not boxes:
        return None, None
    t = boxes[0]
    return float(t.get("dist_xz", 1e9)), -float(t.get("dist_y", 0.0))


def _walk_ring_body(game: Game, ctx) -> None:
    """Walk region 2's spiral by compiled waypoints until the chest is
    near and near-level. Never steers at the chest itself: on an annulus
    the straight line is the void (fourth flight, three falls)."""
    for i, (x, z, ey) in enumerate(RING_WAYPOINTS):
        dist, above = _chest(game)
        if dist is not None and dist <= CHEST_NEAR_XZ and abs(above) <= CHEST_NEAR_Y:
            return                      # close and level — hand to charge
        _walk_leg(game, x, z, within=WAYPOINT_WITHIN, budget_s=16.0)
        pos = game.pos()
        if pos is not None and pos[1] < ey - FELL_TOL:
            raise BehaviorAbort(
                f"FELL: at waypoint {i} ({x:.0f}, {z:.0f}) floor should be "
                f"~{ey:.0f}, Link is at {pos[1]:.0f}")
    dist, above = _chest(game)
    if dist is None:
        raise BehaviorAbort("walked the ring; chest no longer in the census")
    if dist > CHEST_NEAR_XZ or abs(above) > CHEST_NEAR_Y:
        raise BehaviorAbort(
            f"walked all waypoints; chest still at {dist:.0f} ^{above:+.0f}")


def _chest_close(game: Game, initial: dict, events: list) -> bool:
    dist, above = _chest(game)
    return (dist is not None and dist <= CHEST_NEAR_XZ
            and above is not None and abs(above) <= CHEST_NEAR_Y)


ATRIUM_CENTER = (30.0, 65.0)   # graph: region 0's centroid — "inward" on the ring
FRONT_OFF = 42.0               # stand this far in front of the chest face
TRILAT_STEP = 60.0             # tangential sidestep between distance readings


def _open_chest_body(game: Game, ctx) -> None:
    """charge_chest_v1 got to 45 out, level, and A did nothing: a chest
    opens only from its FRONT face, and the arc walk arrives at its side.
    The census carries distance but no bearing (harness backlog #3), so
    fix the chest by trilateration — two distance readings a sidestep
    apart — and let the graph break the tie: of the two circle
    intersections, the chest is the one nearer the OUTER wall, and its
    front faces INWARD (toward the atrium center the graph gave us).
    Then approach from in front, in stop-press-A bursts (A while moving
    is a roll)."""
    p1 = game.pos()
    d1, _ = _chest(game)
    if p1 is None or d1 is None:
        raise BehaviorAbort("no player or no chest on the wire")
    cx, cz = ATRIUM_CENTER
    import math
    rx, rz = p1[0] - cx, p1[2] - cz
    rlen = math.hypot(rx, rz) or 1.0
    tx, tz = -rz / rlen, rx / rlen          # tangent: along the arc
    game.walk_to_point(p1[0] + tx * TRILAT_STEP, p1[2] + tz * TRILAT_STEP,
                       within=20.0, timeout=6.0)
    p2 = game.pos()
    d2, _ = _chest(game)
    if p2 is None or d2 is None:
        raise BehaviorAbort("lost the chest between readings")
    ex_x, ex_z = p2[0] - p1[0], p2[2] - p1[2]
    d = math.hypot(ex_x, ex_z)
    if d < 15.0:
        raise BehaviorAbort(f"sidestep only moved {d:.0f} units; cannot trilaterate")
    ex_x, ex_z = ex_x / d, ex_z / d
    a = (d1 * d1 - d2 * d2 + d * d) / (2 * d)
    h = math.sqrt(max(0.0, d1 * d1 - a * a))
    mx, mz = p1[0] + a * ex_x, p1[2] + a * ex_z
    cands = [(mx - h * ex_z, mz + h * ex_x), (mx + h * ex_z, mz - h * ex_x)]
    chest = max(cands, key=lambda c: math.hypot(c[0] - cx, c[1] - cz))
    inx, inz = cx - chest[0], cz - chest[1]
    ilen = math.hypot(inx, inz) or 1.0
    front = (chest[0] + inx / ilen * FRONT_OFF, chest[1] + inz / ilen * FRONT_OFF)
    game.walk_to_point(front[0], front[1], within=16.0, timeout=10.0)

    bearing = game.world_yaw_to_point(chest[0], chest[1])
    deadline = time.monotonic() + 12.0
    while time.monotonic() < deadline:
        if game.state().get("msg_mode", 0) != 0:
            return                          # it opened
        game.walk_bearing(bearing, seconds=0.2)
        game.pad_clear()
        game.wait(0.15)
        game.press("A")
        game.wait(0.3)
    dist, above = _chest(game)
    raise BehaviorAbort(
        f"trilaterated chest at ({chest[0]:.0f}, {chest[1]:.0f}), stood in "
        f"front, pressed A; still shut (now {dist:.0f} out ^{above:+.0f})")


def _msg_open(game: Game, initial: dict, events: list) -> bool:
    return game.state().get("msg_mode", 0) != 0


def _open_chest_v3_body(game: Game, ctx) -> None:
    """v2 post-mortem: two readings + an inward-facing assumption put the
    front point ~110 up-arc (the spiral's rise explains the -11). v3:
    (1) THREE distance readings from three known positions, least-squares
    for the chest fix — no intersection tie-break to get wrong; (2) no
    facing assumption at all — visit all four compass front-points,
    stop, face the fix, press A at each. The A prompt only exists at the
    true front, so three sides cost seconds and the fourth opens it."""
    import math
    readings = []

    def read():
        p = game.pos()
        d, _ = _chest(game)
        if p is None or d is None:
            raise BehaviorAbort("no player or no chest on the wire")
        readings.append((p[0], p[2], d))

    read()
    cx, cz = ATRIUM_CENTER
    rx, rz = readings[0][0] - cx, readings[0][1] - cz
    rlen = math.hypot(rx, rz) or 1.0
    tx, tz = -rz / rlen, rx / rlen
    for step in (TRILAT_STEP, -2 * TRILAT_STEP):
        game.walk_to_point(readings[-1][0] + tx * step,
                           readings[-1][1] + tz * step,
                           within=20.0, timeout=6.0)
        read()

    # Least squares via circle-difference linearization: for readings
    # (xi, zi, di), subtracting pairs of circle equations gives linear
    # rows A [x z]^T = b. Three readings -> two rows, solvable directly.
    (x1, z1, d1), (x2, z2, d2), (x3, z3, d3) = readings
    a11, a12 = 2 * (x2 - x1), 2 * (z2 - z1)
    b1 = d1 * d1 - d2 * d2 + x2 * x2 - x1 * x1 + z2 * z2 - z1 * z1
    a21, a22 = 2 * (x3 - x1), 2 * (z3 - z1)
    b2 = d1 * d1 - d3 * d3 + x3 * x3 - x1 * x1 + z3 * z3 - z1 * z1
    det = a11 * a22 - a12 * a21
    if abs(det) < 1e-6:
        raise BehaviorAbort(
            f"readings colinear, no fix: {[(f'{x:.0f}',f'{z:.0f}',f'{d:.0f}') for x,z,d in readings]}")
    chest = ((b1 * a22 - b2 * a12) / det, (a11 * b2 - a21 * b1) / det)

    tried = []
    for ang in (0.0, 90.0, 180.0, 270.0):
        ox = math.cos(math.radians(ang)) * FRONT_OFF
        oz = math.sin(math.radians(ang)) * FRONT_OFF
        fx, fz = chest[0] + ox, chest[1] + oz
        game.walk_to_point(fx, fz, within=14.0, timeout=7.0)
        bearing = game.world_yaw_to_point(chest[0], chest[1])
        for _ in range(3):
            game.walk_bearing(bearing, seconds=0.15)
            game.pad_clear()
            game.wait(0.15)
            game.press("A")
            game.wait(0.35)
            if game.state().get("msg_mode", 0) != 0:
                return
        tried.append(f"{ang:.0f}deg")
    dist, above = _chest(game)
    raise BehaviorAbort(
        f"fix ({chest[0]:.0f}, {chest[1]:.0f}) from readings "
        f"{[(f'{x:.0f}',f'{z:.0f}',f'{d:.0f}') for x,z,d in readings]}; "
        f"pressed A on sides {tried}; still shut ({dist:.0f} out ^{above:+.0f})")


def _open_chest_v4_body(game: Game, ctx) -> None:
    """v3 post-mortem: the fix was tight ((338, 254), residuals < 5) but
    no side produced the Open prompt from a ~30-40 unit press distance —
    the prompt wants CONTACT with the front face. v4: at eight bearings,
    walk INTO the chest until the census distance stops shrinking (that's
    the base of the box), then stop and press A. The fix is baked from
    v3's journaled readings; re-verified from here before use."""
    import math
    chest = (338.0, 254.0)
    d, _ = _chest(game)
    if d is None:
        raise BehaviorAbort("no chest on the wire")
    p = game.pos()
    if p is not None:
        est = math.hypot(chest[0] - p[0], chest[1] - p[2])
        if abs(est - d) > 40.0:
            raise BehaviorAbort(
                f"baked fix disagrees with the wire: census {d:.0f}, "
                f"fix-to-Link {est:.0f} — refusing to press A at a ghost")

    tried = []
    for ang in (0, 45, 90, 135, 180, 225, 270, 315):
        ox = math.cos(math.radians(ang)) * 60.0
        oz = math.sin(math.radians(ang)) * 60.0
        game.walk_to_point(chest[0] + ox, chest[1] + oz, within=18.0, timeout=7.0)
        bearing = game.world_yaw_to_point(chest[0], chest[1])
        best = 1e9
        stall = 0
        while stall < 3:
            game.walk_bearing(bearing, seconds=0.2)
            d, _ = _chest(game)
            if d is None:
                break
            if d < best - 4.0:
                best, stall = d, 0
            else:
                stall += 1
        game.pad_clear()
        game.wait(0.2)
        for _ in range(3):
            game.press("A")
            game.wait(0.35)
            if game.state().get("msg_mode", 0) != 0:
                return
        tried.append(f"{ang}deg@{best:.0f}")
    raise BehaviorAbort(
        f"pressed A at contact on all eight bearings ({', '.join(tried)}); "
        f"still shut")


CHEST_POS = (333.0, 253.0)     # ydan_room_0 actor entry: (333, 360, 253)
CHEST_YAW = 0x20B6             # rot_y from the same entry; front = +46 deg


def _open_chest_v5_body(game: Game, ctx) -> None:
    """The room's actor list (static data; the chest is sighted and its
    latch is visible to any sighted player) gives pos (333, 360, 253) and
    facing 0x20B6. Trilateration (v3) was 5 units off — the geometry was
    never the problem past v2. v5 stands on the exact front point, still,
    and presses A slowly: if this fails with the A-icon reading 'Open'
    on AJ's screen, the button path is the bug, not the stance."""
    import math
    # AJ, eyewitness (2026-08-03): the latch faces the LEDGE — toward the
    # atrium center. En_Box's front is OPPOSITE dir(rot_y); v5 walked to
    # the hinges. Record the convention: front bearing = rot_y + 0x8000.
    # v6, AJ: "JUST off center" — lateral error. v7, AJ: v6's 80-unit
    # standoff point was PAST THE WALKWAY'S INNER EDGE (radius ~288 vs
    # edge ~300) and Link auto-jumped into the void — the mind hardcoded
    # a waypoint its own map calls off-mesh. LESSON, permanent: validate
    # every authored point against the graph before a body walks at it.
    # v7: the proven-safe 42 standoff, tight arrival, and a cross-track-
    # guarded contact walk with re-staging retries for centering.
    # Free play 2026-08-04 (AJ's eyewitness): this body pressed A at an
    # ALREADY-OPEN chest, twice — the map was collected in a previous
    # life and the save carried the treasure flag. The census now carries
    # the game's own `opened` bit on En_Box; check it before walking a
    # single step. This is the chest's activation-state sense: an open
    # lid reads on sight.
    for a in game.actors(actor_id=0x000A):
        if a.get("opened"):
            raise BehaviorAbort(
                "the chest is already OPEN (census `opened` bit) — its "
                "prize was collected in a previous life; nothing to do")

    yaw_rad = (CHEST_YAW + 0x8000) / 32768.0 * math.pi
    sin_f, cos_f = math.sin(yaw_rad), math.cos(yaw_rad)
    fx = CHEST_POS[0] + sin_f * FRONT_OFF
    fz = CHEST_POS[1] + cos_f * FRONT_OFF

    for attempt in range(3):
        game.walk_to_point(fx, fz, within=9.0, timeout=12.0)
        bearing = game.world_yaw_to_point(CHEST_POS[0], CHEST_POS[1])
        # v8, AJ: "you need SMALLER steps" — full-run bursts are ~27 units
        # and the target is 40 out; Link was parallel parking at highway
        # speed. Analog magnitude 32 = slow walk, ~8 units per burst.
        best = 1e9
        stall = 0
        off_line = False
        while stall < 4:
            game.walk_bearing(bearing, seconds=0.12, magnitude=32)
            p = game.pos()
            if p is not None:
                # cross-track: distance from the front line (chest + t*dir)
                rx, rz = p[0] - CHEST_POS[0], p[2] - CHEST_POS[1]
                cross = abs(rx * cos_f - rz * sin_f)
                if cross > 16.0:
                    off_line = True
                    break
            d, _ = _chest(game)
            if d is None:
                break
            if d < best - 2.0:
                best, stall = d, 0
            else:
                stall += 1
        game.pad_clear()
        game.wait(0.5)
        if off_line or best > 38.0:
            continue                    # back to the staging point, retry
        for i in range(4):
            game.press("A", frames=6)
            game.wait(0.5)
            if game.state().get("msg_mode", 0) != 0:
                return
    p = game.pos()
    d, above = _chest(game)
    raise BehaviorAbort(
        f"stood on the actor-data front point ({fx:.0f}, {fz:.0f}), faced "
        f"the latch, pressed A x5 (6-tick holds); still shut. Link at "
        f"({p[0]:.0f}, {p[1]:.0f}, {p[2]:.0f}), chest {d:.0f} out "
        f"^{above:+.0f}. If the A-icon read 'Open', the button path is "
        f"the bug; if it never did, the stance is.")


BEHAVIORS = {
    "open_chest_v5": Behavior(
        name="open_chest", version=5,
        description="stand on the exact front point from the room's actor "
                    "entry, face the latch, press A slowly x5",
        body=_open_chest_v5_body, success=_msg_open, timeout_s=45.0,
        grade="UNGRADED (field-authored, fifth flight). Separates stance "
              "from button-path with AJ reading the A-icon as witness.",
        notes=["Chest pose from ydan_room_0 static data — the sighted "
               "chest's visible facing, in text form."]),
    "open_chest_v4": Behavior(
        name="open_chest", version=4,
        description="walk into the chest to contact on eight bearings, "
                    "press A at each — prompt needs front-face contact",
        body=_open_chest_v4_body, success=_msg_open, timeout_s=150.0,
        grade="UNGRADED (field-authored, fifth flight, after v3's fix was "
              "right but its press distance was not).",
        notes=["Contact = census distance stops shrinking while walking in."]),
    "open_chest_v3": Behavior(
        name="open_chest", version=3,
        description="three-reading least-squares chest fix, then press A "
                    "from all four compass sides — no facing assumption",
        body=_open_chest_v3_body, success=_msg_open, timeout_s=90.0,
        grade="UNGRADED (field-authored, fifth flight, after v2's front "
              "guess landed up-arc).",
        notes=["A only while stationary: A while moving is a roll."]),
    "open_chest_v2": Behavior(
        name="open_chest", version=2,
        description="trilaterate the chest from two census distances, walk "
                    "to its inward-facing front, stop-and-press A",
        body=_open_chest_body, success=_msg_open, timeout_s=60.0,
        grade="UNGRADED (field-authored, fifth flight). The bearings gap "
              "(backlog #3) worked around by trilateration + the graph's "
              "outer-wall/inward-front priors.",
        notes=["A only while stationary: A while moving is a roll."]),
    "goto_vine_v1": Behavior(
        name="goto_vine", version=1,
        description="cross the ground floor east of the web hole and climb "
                    "the graph's region-0 -> region-2 vine column",
        body=_goto_vine_body, success=_on_ring, timeout_s=110.0,
        grade="UNGRADED (field-authored, fifth flight). First body steered "
              "by an offline nav graph; local scan verifies the wall face "
              "before the grab.",
        notes=["Grab/ascend rules are climb.py's: no camera term on the "
               "wall, never press A, keep walking into the wall to grab."]),
    "walk_ring_v1": Behavior(
        name="walk_ring", version=1,
        description="follow the spiral walkway's compiled waypoints until "
                    "the chest is near and level; abort loudly on any fall",
        body=_walk_ring_body, success=_chest_close, timeout_s=150.0,
        grade="UNGRADED (field-authored, fifth flight). Carries its own "
              "expected-height table — the hand-rolled `fell` detector.",
        notes=["Never steers at the chest: on an annulus the straight "
               "line is the void."]),
}
