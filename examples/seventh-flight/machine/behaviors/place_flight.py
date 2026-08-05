"""Sixth-flight bodies: the place-sense acceptance (ocarina 0.7.0, dojo
docs/25 step 6). The map is the blessed surface now — these bodies hold
NO coordinates, no waypoint tables, no expected-height tables: every
number that steered their fifth-flight ancestors (goto_vine_v1's
GF_WAYPOINTS, walk_ring_v1's height table) lives server-side behind
named legs. Route choice stays here, in the mind's artifact, as a
SEQUENCE OF NAMES read off oot://place.

refusal_probe_v1 exercises the refusal semantics deliberately —
refused-before-movement is a designed feature and gets flown like one.
ascend_to_3f_v1 is the mission: two legs the map vouches for,
GF -> ring -> 3F, a floor no flight has ever stood on.
"""

import math
import time

from ocarina.behavior import Behavior, BehaviorAbort
from ocarina.place import TraverseFailed, TraverseRefused

VINE_GF_RING = "vine@120,0,-300"      # the fifth flight's column, now a name
VINE_RING_3F = "vine@340,360,270"     # 12 heights up to ydan:r@-10,800,-20
RING_REGION = "ydan:r@250,340,30"     # the spiral walkway, leg 1's landing
RING_CX, RING_CZ = 250.0, 30.0        # the name IS the centroid, read off it
TOP_REGION = "ydan:r@-10,800,-20"     # 3F, the mission's destination
THIRD_FLOOR_Y = 780.0                 # success floor: 3F is y=800

# One of the map's 143 drop/jump guesses — refusing it is the point.
A_CANDIDATE = "drop?r@-10,800,-20->r@-200,-910,120"
NON_ADJACENT = "ydan:r@-10,800,-20"   # 3F straight from GF: no linked edge
A_DESCENT = "vine@100,-940,0"         # the B1 vine, downward from GF


def _expect_refusal(game, target, expect_fragment):
    try:
        game.traverse(target, timeout_s=10.0)
    except TraverseRefused as e:
        if expect_fragment not in str(e):
            raise BehaviorAbort(
                f"{target}: refused, but with the wrong story: {e}")
        return
    raise BehaviorAbort(f"{target}: NOT refused — it moved or claimed ok")


def _refusal_body(game, ctx):
    _expect_refusal(game, A_CANDIDATE, "UNVERIFIED candidate")
    _expect_refusal(game, NON_ADJACENT, "not adjacent")
    _expect_refusal(game, A_DESCENT, "not built yet")


def _did_not_move(game, initial, events):
    """Success = all three refusals held AND Link never moved a muscle."""
    p0 = (initial.get("player") or {}).get("pos")
    p1 = game.pos()
    if not p0 or not p1:
        return False
    return (abs(p1[0] - p0[0]) < 5.0 and abs(p1[2] - p0[2]) < 5.0)


SKULLWALLTULA = 0x0095    # guards the long vine; contact knocks Link off
CLIMB_TRIES = 3           # knock-offs cost 0.5 heart each; stay above critical
DODGE_NEAR = 130.0        # start weaving when a wall spider is this close (3D)


def _spiders(game):
    """Census positions of every skullwalltula (probe-verified: in this
    room they are stationary guards, so present pos IS the hazard map)."""
    return [a["pos"] for a in game.actors(actor_id=SKULLWALLTULA)
            if a.get("pos")]


def _spider_probe(game, ctx):
    """Diagnostic (census_probe lineage): watch the wall spiders' patrol
    for 15 s and report each one's envelope — y range and horizontal
    offset from the ring->3F climb line at (340, 270). The v3 gate
    measured gap-from-Link and could never open (a spider parked 90 up
    the wall is always near the man beneath it); the RIGHT gate needs
    the patrol's shape, and arguing is not measuring (docs/08)."""
    seen = {}
    t_end = time.time() + 15.0
    while time.time() < t_end:
        for a in game.actors(actor_id=SKULLWALLTULA):
            p = a.get("pos")
            if not p:
                continue
            k = a.get("key")
            off = math.hypot(p[0] - 340.0, p[2] - 270.0)
            rec = seen.setdefault(k, [p[1], p[1], off, off, 0])
            rec[0] = min(rec[0], p[1])
            rec[1] = max(rec[1], p[1])
            rec[2] = min(rec[2], off)
            rec[3] = max(rec[3], off)
            rec[4] += 1
        game.wait(0.5)
    parts = [f"{k}: y {r[0]:.0f}..{r[1]:.0f}, line-off {r[2]:.0f}..{r[3]:.0f} "
             f"({r[4]} samples)" for k, r in sorted(seen.items())]
    raise BehaviorAbort("; ".join(parts) if parts
                        else "no skullwalltula in the census")


def _slalom_leg(game, target, deadline, start_side):
    """Hand-rolled guarded climb: the probe showed three STATIONARY wall
    spiders (zero patrol in 30 samples — v3's wait-for-an-opening could
    never open), with the door guard 52 units off the climb line at
    y 678. A human weaves on the vines; this is the weave. Approach and
    grab are traverse's own validated recipe; geometry comes from the
    map's leg resolution (names in, body-side numbers — the blessed
    split). BACKLOG: this wants to be traverse's obstacle-aware ascend.
    While ON a wall the stick is wall-relative (up = up), so raw pad
    sticks steer the climb: (0, 80) up, (±70, 15) a rising sidestep."""
    leg = game.place.resolve_traverse(game.state(), target)
    for (wx, wz) in leg["waypoints"]:
        game.walk_to_point(wx, wz, within=55.0, timeout=20.0)
    bx, bz = leg["at"]
    # THE CHEST GUARDS THE BASE (AJ's screenshot: treasure_chest dist 40
    # above +0 dead ahead, the vine column rising behind it). The named
    # base point is UNDER the chest: walking to it wedges, grabbing past
    # it reaches only the patch's margins, and a margin grip climbs off
    # the vines and falls ("a literal edge case"). So do it the human
    # way: stand BESIDE the chest, grab the margin, then sidestep back
    # to the column's center ON the wall — over the chest — and climb.
    yaw_out = game.world_yaw_to_point(bx, bz,
                                      from_pos=(RING_CX, 0.0, RING_CZ))
    rad = yaw_out / 0x8000 * math.pi
    ox, oz = math.sin(rad), math.cos(rad)     # outward (into the wall)
    txv, tzv = oz, -ox                        # along the wall
    # Two-hop approach so the straight line cannot clip the chest:
    # first well clear of the wall, then in to the stand point.
    for back, along in ((80.0, 55.0), (12.0, 42.0)):
        sx = bx + start_side * along * txv - back * ox
        sz = bz + start_side * along * tzv - back * oz
        game.walk_to_point(sx, sz, within=18.0, timeout=15.0)
    grab_deadline = time.time() + 12.0
    while time.time() < grab_deadline and not game.climbing():
        game.walk_bearing(yaw_out, seconds=0.3)
    if not game.climbing():
        raise TraverseFailed(f"never got a grip on {target} from "
                             f"side {start_side}")

    # Recenter on the wall before climbing: measure drift toward the
    # column's center line and let the measurement pick the stick sign
    # (stick-x handedness on a wall is not worth guessing).
    recenter = -start_side * 70
    for _ in range(8):
        here = game.pos()
        if here is None or not game.climbing():
            break
        off = math.hypot(here[0] - bx, here[2] - bz)
        if off < 15.0:
            break
        game.pad(stick=(recenter, 20))
        game.wait(0.3)
        now = game.pos() or here
        if math.hypot(now[0] - bx, now[2] - bz) >= off - 1.0:
            recenter = -recenter
    game.pad_clear()

    side = start_side
    while time.time() < deadline and (game.climbing()
                                      or game.mounting_ledge()):
        here = game.pos()
        if here is None:
            break
        threat, t_d = None, 1e9
        for p in _spiders(game):
            d = math.hypot(math.hypot(p[0] - here[0], p[2] - here[2]),
                           p[1] - here[1])
            if d < t_d:
                t_d, threat = d, p
        # Weave only when the guard is genuinely AHEAD: close in 3D and
        # inside the band just above Link. v4's first cut dodged at the
        # base (guard +90 overhead) and slid off the patch edge in 3/3
        # attempts before ever climbing — straight up is the right move
        # until the guard is near.
        if (threat is not None and t_d < DODGE_NEAR
                and threat[1] > here[1] - 20.0
                and threat[1] - here[1] < 70.0):
            # A guard ahead-and-above: rising sidestep, and let the gap
            # itself pick the direction — if it shrank, flip sides.
            gap0 = math.hypot(threat[0] - here[0], threat[2] - here[2])
            game.pad(stick=(side * 70, 15))
            game.wait(0.35)
            now = game.pos() or here
            gap1 = math.hypot(threat[0] - now[0], threat[2] - now[2])
            lat = math.hypot(now[0] - here[0], now[2] - here[2])
            if gap1 <= gap0 + 2.0 or lat < 3.0:
                side = -side
        else:
            game.pad(stick=(0, 80))
            game.wait(0.2)
    game.pad_clear()
    game.wait(0.6)
    here = game.pos()
    hit = leg["graph"].locate(*here) if here else None
    if hit is None or hit[0]["id"] not in leg["to_rids"]:
        got = leg["graph"].region_name(hit[0]) if hit else "OFF THE MAP"
        raise TraverseFailed(f"left the wall in {got}, not the linked "
                             f"region")


def _climb_guarded(game, target, timeout_s):
    """Weave past the stationary guards, retrying after knock-offs —
    each grab is cheap, and the map-verified arrival keeps every
    attempt honest."""
    last = None
    for i in range(CLIMB_TRIES):
        try:
            # Alternate the opening dodge side per attempt — one bad
            # patch edge must not eat every retry.
            _slalom_leg(game, target, time.time() + timeout_s,
                        1 if i % 2 == 0 else -1)
            return
        except TraverseFailed as e:
            last = e
            game.pad_clear()
            game.wait(1.0)
    raise BehaviorAbort(f"{target}: {CLIMB_TRIES} climbs failed, "
                        f"last: {last}")


def _region(game):
    """Where the map says Link is standing, by name (None off-mesh)."""
    s = game.place.sample(game.state()) if game.place else None
    return (s or {}).get("region")


def _ascend_body(game, ctx):
    """Route by name from WHEREVER Link is — v1 replayed leg 1
    unconditionally, so a mid-route retry asked to climb DOWN the first
    vine and got refused (sixth flight: the ring-walk stall left Link on
    the ring with no body able to resume). Reading place.region and
    skipping legs already behind us is the mind's half of the docs/25
    split: the route is cognition, and cognition starts from the truth."""
    try:
        here = _region(game)
        if here not in (RING_REGION, TOP_REGION):
            game.traverse(VINE_GF_RING, timeout_s=90.0)
            game.wait(0.5)
        if _region(game) != TOP_REGION:
            # Plain named traverse again (v5): the server now aims grabs
            # at floor-touching base segments, which moved the climb line
            # to the long unguarded vine span around the shaft — away
            # from both the chest and the spiders. Retries stay: a
            # knock-off is cheap and the arrival check is honest.
            last = None
            for _ in range(CLIMB_TRIES):
                try:
                    game.traverse(VINE_RING_3F, timeout_s=150.0)
                    break
                except TraverseFailed as e:
                    last = e
                    game.wait(1.0)
            else:
                raise BehaviorAbort(str(last))
    except (TraverseRefused, TraverseFailed) as e:
        raise BehaviorAbort(str(e))


def _on_3f(game, initial, events):
    now = game.pos()
    return (now is not None and now[1] >= THIRD_FLOOR_Y
            and not game.on_a_wall())


BEHAVIORS = {
    "refusal_probe_v1": Behavior(
        name="refusal_probe", version=1,
        description="attempt three illegal traversals (candidate edge, "
                    "non-adjacent region, descent) and require clean "
                    "refusals with zero movement",
        body=_refusal_body, success=_did_not_move, timeout_s=30.0,
        grade="UNGRADED (field-authored, sixth flight). The v6 void-jump "
              "lesson flown as a test: validation is a service.",
        notes=["Success predicate checks Link's pos against entry — "
               "refused-before-movement, measured, not assumed."]),
    "spider_probe_v1": Behavior(
        name="spider_probe", version=1,
        description="diagnostic: 15 s watch of skullwalltula patrol "
                    "envelopes vs the ring->3F climb line; always aborts "
                    "with the measurements in detail",
        body=_spider_probe, success=lambda g, i, e: False, timeout_s=25.0,
        grade="UNGRADED diagnostic (census_probe lineage, sixth flight).",
        notes=["Data rides the abort detail into the wake — the probe's "
               "whole point is the mind reading it."]),
    "ascend_to_3f_v5": Behavior(
        name="ascend_to_3f", version=5,
        description="GF -> ring -> 3F by named traverse legs off "
                    "oot://place, skipping legs place.region says are "
                    "already behind us; climb retries on failure",
        body=_ascend_body, success=_on_3f, timeout_s=300.0,
        grade="UNGRADED (field-authored, sixth flight). v1 not "
              "retry-safe; v2 bitten off by the vine guard; v3 waited "
              "for a patrol that never moves; v4 chased the sheet "
              "centroid into the chest and the vine gap. v5 is plain "
              "traverse again — the fixes it forced (message-box guard, "
              "wedge reflex, base-segment grabs) all moved SERVER-side, "
              "which is the shape the contract wants.",
        notes=["Route = the mind's leg sequence; steering, grabbing, "
               "climbing, arrival-verification = the server's traverse.",
               "The retired spider-slalom (_slalom_leg/_climb_guarded) "
               "stays in-file as the fallback if a guard ever parks on "
               "the new line."]),
}
