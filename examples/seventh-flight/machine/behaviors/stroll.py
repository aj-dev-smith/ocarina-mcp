"""Free-play body (2026-08-04, AJ's "do whatever you want" session): the
slingshot chest, second acquisition. The fifth flight opened this chest
and lost the prize with its unsaved process; this body re-runs only the
SAFE leg — GF -> ring by named traverse — and hands off to the proven
ring_walk -> open_chest chain. It stops a full leg short of the 3F
guard wall that ended the sixth flight.

Route choice is the mind's (docs/25): one name, read off oot://place.
Steering, the hole in the floor, grabbing, arrival — all the server's.
The fifth flight's GF_WAYPOINTS replay is unsafe from an arbitrary
start (its line from mid-room crosses the web hole's no-go radius);
traverse routes on the mesh, and the hole has no polys.
"""

import math

from ocarina.behavior import Behavior, BehaviorAbort
from ocarina.place import TraverseFailed, TraverseRefused

VINE_GF_RING = "vine@120,0,-300"     # the fifth flight's column, by name
RING_REGION = "ydan:r@250,340,30"    # the spiral walkway
GF_REGION = "ydan:r@30,0,70"         # ground floor — landing here = we fell

DOOR_SHUTTER = 0x002E                # Door_Shutter, the dungeon doors


def _region(game):
    s = game.place.sample(game.state()) if game.place else None
    return (s or {}).get("region")


def _goto_ring_body(game, ctx):
    # A fresh save re-arms every Navi trigger on the route; clear boxes
    # BLIND (bounded) and retry the leg instead of waking per lecture.
    # The blindness is backlog #5's honesty cost, recorded here.
    last = None
    for _ in range(3):
        for _ in range(12):
            if game.state().get("msg_mode", 0) == 0:
                break
            game.press("A")
            game.wait(0.5)
        try:
            if _region(game) != RING_REGION:
                game.traverse(VINE_GF_RING, timeout_s=90.0)
                game.wait(0.5)
            return
        except TraverseFailed as e:
            if "message box" in str(e):
                last = e
                continue
            raise BehaviorAbort(str(e))
        except TraverseRefused as e:
            raise BehaviorAbort(str(e))
    raise BehaviorAbort(f"boxes kept coming: {last}")


def _on_ring(game, initial, events):
    return _region(game) == RING_REGION and not game.on_a_wall()


def _enter_door_body(game, ctx):
    """First door body on the bench (free play, 2026-08-04). Doors are the
    one edge type the region graph carries no links for, so this is a
    body-with-eyes job: the census gives the door's live position, the
    approach is the chest saga's contact-walk discipline (slow steps, A
    only while stationary), and arrival is judged by the map — success is
    standing in a region that is neither the ring nor the floor we'd hit
    if we fell. The fall detector aborts loudly instead of letting a
    void-step read as a stall."""
    doors = [a for a in game.actors(actor_id=DOOR_SHUTTER)
             if abs(-float(a.get("dist_y", 0.0))) < 80.0]
    doors.sort(key=lambda a: a.get("dist_xz", 1e9))
    if not doors:
        raise BehaviorAbort("no level door in the census from here")
    pos = doors[0].get("pos")
    if not pos or len(pos) < 3:
        raise BehaviorAbort("door entry carries no position")
    dx, dz = float(pos[0]), float(pos[2])
    d0 = float(doors[0].get("dist_xz", 0.0))
    # 450, not 300: the guard is against crossing ROOMS blind — the leap
    # landing sits ~306 from the 2F door across one flat region, and v1's
    # 300 refused it (free play, first live run).
    if d0 > 450.0:
        raise BehaviorAbort(
            f"door is {d0:.0f} out — too far to walk at blind, plan legs")

    here = _region(game)

    game.walk_to_point(dx, dz, within=40.0, timeout=25.0)
    p = game.pos()
    if p is not None and p[1] < 300.0:
        raise BehaviorAbort(f"left the walkway on approach — y={p[1]:.0f}")

    best = 1e9
    for attempt in range(4):
        # A modal box (Navi, get-item) eats the A press AND freezes the
        # pad — clear it BLIND, bounded. The blindness is the honesty
        # cost of dialogue text not being on the wire (backlog #5); the
        # abort names it if the box will not die.
        for _ in range(12):
            if game.state().get("msg_mode", 0) == 0:
                break
            game.press("A")
            game.wait(0.5)
        else:
            raise BehaviorAbort(
                "a message box would not clear after 12 blind advances")
        bearing = game.world_yaw_to_point(dx, dz)
        stall = 0
        while stall < 4:
            game.walk_bearing(bearing, seconds=0.12, magnitude=32)
            q = game.pos()
            if q is None:
                break
            if q[1] < 300.0:
                raise BehaviorAbort(f"fell at the door — y={q[1]:.0f}")
            d = math.hypot(dx - q[0], dz - q[2])
            if d < best - 2.0:
                best, stall = d, 0
            else:
                stall += 1
        game.pad_clear()
        game.wait(0.25)
        game.press("A")
        # The shutter's open animation walks Link through and the room
        # loads; give it real time before reading the map.
        game.wait(2.5)
        # v1's false success (free play, first live run): "not the ring,
        # not GF" is also true of the NEAR side of the door. Through
        # means a region that is none of ring/GF/where this approach
        # started.
        if _region(game) not in (RING_REGION, GF_REGION, here, None):
            return
    raise BehaviorAbort(
        f"pressed A at the door 4 times from ~{best:.0f} out; "
        f"still in {_region(game)}")


DOOR_PLATFORM = "ydan:r@-320,400,340"    # region 21: flat y=400, the 2F door
# Arc waypoints along the ring's top stretch, LAB-VALIDATED 2026-08-04
# (locate.py: region 11, floor y 360-400, mid-walkway). The first guess
# at this arc put a waypoint over region 14's 230-unit drop — the
# validate-before-walking lesson (open_chest v7) catching its second
# body. The walkway BREAKS at ~104.5 deg: a ~100-unit measured gap
# (uniform across radii, lab-sampled at 1-degree grain), then the door
# platform. The crossing is the vanilla run-jump: full-speed sprint on
# a fixed world bearing; the edge auto-jumps, a short landing becomes a
# ledge-grab (climb up, never press A — z_player.c fact 2).
ARC_WAYPOINTS = [(254.0, 385.0), (64.0, 454.0)]
GAP_RUNUP = (30.0, 445.0)       # ring top, ~15 deg of runway before the edge
GAP_AIM = (-188.0, 376.0)       # interior of the door platform, past the gap


def _leap_gap_body(game, ctx):
    for (x, z) in ARC_WAYPOINTS:
        game.walk_to_point(x, z, within=45.0, timeout=20.0)
        p = game.pos()
        if p is not None and p[1] < 340.0:
            raise BehaviorAbort(f"left the walkway on the arc — y={p[1]:.0f}")
    game.walk_to_point(*GAP_RUNUP, within=25.0, timeout=15.0)
    game.pad_clear()
    game.wait(0.3)
    bearing = game.world_yaw_to_point(*GAP_AIM)
    game.walk_bearing(bearing, seconds=1.6, magnitude=127)
    game.wait(1.5)
    if game.on_a_wall() or game.mounting_ledge():
        game.pad(stick=(0, 127))
        game.wait(1.2)
        game.pad_clear()
        game.wait(0.5)
    p = game.pos()
    if p is None or p[1] < 340.0:
        raise BehaviorAbort(
            f"fell in the gap — y={(p[1] if p else -1):.0f}; "
            f"re-run goto_ring to retry")
    r = _region(game)
    if r != DOOR_PLATFORM:
        raise BehaviorAbort(
            f"landed at y={p[1]:.0f} but the map says {r}, "
            f"not the door platform")


def _on_platform(game, initial, events):
    p = game.pos()
    return (_region(game) == DOOR_PLATFORM
            and p is not None and p[1] >= 390.0)


ENTRANCE = (0.0, 480.0)     # GF, south side — where the babas hunt from


def _goto_entrance_body(game, ctx):
    """Walk home to the entrance stretch of GF (free play 2026-08-04,
    take two: the clearing loop starved mid-room — the babas live by
    the entrance and the sight predicate can't reach them from the vine
    wall). Same region, so this is one mesh-safe walk, with the fall
    guard the web hole demands."""
    game.walk_to_point(*ENTRANCE, within=60.0, timeout=30.0)
    p = game.pos()
    if p is None or p[1] < -50.0:
        raise BehaviorAbort(
            f"left GF walking home — y={(p[1] if p else -1):.0f}")


def _at_entrance(game, initial, events):
    p = game.pos()
    if p is None:
        return False
    return abs(p[0] - ENTRANCE[0]) < 80 and abs(p[2] - ENTRANCE[1]) < 80


def _door_census_body(game, ctx):
    """Diagnostic (probe.py lineage): print every door-family actor with
    WORLD pos + yaw — the census carries them, census_probe just doesn't
    print them. Doors are scene-wide transition actors, so this is the
    scene's door map in one journal line."""
    ids = {0x0023: "door", 0x002E: "shutter", 0x011B: "plane"}
    rows = []
    for a in game.state().get("actors") or []:
        if a.get("id") in ids:
            p = a.get("pos") or [0, 0, 0]
            rows.append(
                f"{ids[a['id']]}@({p[0]:.0f},{p[1]:.0f},{p[2]:.0f})"
                f"yaw={a.get('yaw', 0):#06x}d{a.get('dist_xz', 0):.0f}")
    me = game.pos() or (0, 0, 0)
    raise BehaviorAbort(
        f"me=({me[0]:.0f},{me[1]:.0f},{me[2]:.0f}) :: " + "; ".join(rows))


def _through_door(game, initial, events):
    # Excludes the door PLATFORM too — v1 called the near side of the
    # door "through" (the false success the eyewitness caught).
    r = _region(game)
    p = game.pos()
    return (r is not None
            and r not in (RING_REGION, GF_REGION, DOOR_PLATFORM)
            and p is not None and p[1] > 340.0)


BEHAVIORS = {
    "goto_ring_v1": Behavior(
        name="goto_ring", version=1,
        description="GF -> ring by the named vine leg; region-checked "
                    "arrival, skip if already there",
        body=_goto_ring_body, success=_on_ring, timeout_s=120.0,
        grade="UNGRADED (field-authored, free play 2026-08-04). "
              "ascend_to_3f_v5's leg 1, alone.",
        notes=["Hands off to ring_walk/open_chest — the fifth flight's "
               "chain — via the goto_ring machine node."]),
    "enter_door_v1": Behavior(
        name="enter_door", version=1,
        description="walk to the nearest level shutter door (census pos) "
                    "and open it with A; success = the map says we stand "
                    "in a region that is neither the ring nor the floor",
        body=_enter_door_body, success=_through_door, timeout_s=60.0,
        grade="UNGRADED (field-authored, free play 2026-08-04). First "
              "door body; doors are the graph's missing edge type.",
        notes=["Both outcomes wake — new ground is the mind's to read.",
               "Fall detector aborts on y < 300; a void-step must never "
               "read as a stall."]),
    "leap_gap_v1": Behavior(
        name="leap_gap", version=1,
        description="walk the ring's validated top arc, then sprint-jump "
                    "the measured 100-unit walkway gap to the 2F door "
                    "platform; ledge-grab recovery; map-judged landing",
        body=_leap_gap_body, success=_on_platform, timeout_s=90.0,
        grade="UNGRADED (field-authored, free play 2026-08-04). First "
              "deliberate jump on the bench.",
        notes=["A missed jump lands on GF (~400 drop) — abort says so "
               "and the retry is goto_ring, not a blind re-leap."]),
    "goto_entrance_v1": Behavior(
        name="goto_entrance", version=1,
        description="walk back to GF's entrance stretch (the babas' "
                    "ground) and hand off to the seek chain",
        body=_goto_entrance_body, success=_at_entrance, timeout_s=45.0,
        grade="UNGRADED (field-authored, free play 2026-08-04 take two)"),
    "door_census_v1": Behavior(
        name="door_census", version=1,
        description="journal every door/shutter/transition-plane actor "
                    "with world pos + yaw",
        body=_door_census_body,
        success=lambda game, initial, events: False,
        timeout_s=10.0,
        grade="diagnostic; holds no pad, always aborts (the abort IS "
              "the report)"),
}
