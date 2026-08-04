"""climb_ladder: ocarina's first vertical movement.

Authored live, fourth flight 2026-08-02. Room 0's chest sits +360 above
Link and every door is above or below him; the mind found a ladder at
bearing 0xC000, 131 units out, by calling the `scan` tool itself. No
ocarina behavior had ever climbed anything (the dojo's climb_vines_v4
and follow_wall are unported), so this is written from z_player.c's
three facts, quoted in game.py's climbing section:

1. THE CLIMB IS NOT CAMERA-RELATIVE. Player_Action_8084BF1C reads the
   stick directly with no Camera_GetInputDirYaw term, so stick-up climbs
   up wherever the camera points. stick_for_world_yaw must NOT be
   applied while on the wall — it would rotate "up" into "sideways".
   Hence raw game.pad(stick=(0, +mag)) here, the one place in this repo
   that bypasses the bearing helpers on purpose.
2. PRESSING A LETS GO (func_8083FBC0, unconditional on A's press edge).
   This body never presses A. Nothing may be added to it that does.
3. THE GRAB NEEDS FORWARD MOTION. Player_ActionHandler_5 gates on
   linearVelocity > 0, shape yaw within 0x3000 of facing into the wall,
   and yDistToLedge >= 79 — so you cannot grab by standing against a
   ladder, you have to still be walking into it. The approach therefore
   keeps walking until `climbing` goes true, rather than stopping at
   contact and then trying to mount.
"""

import time

from ocarina.behavior import Behavior, BehaviorAbort
from ocarina.game import Game

CLIMB_MAGNITUDE = 80      # >= 67 saturates the climb speed; 80 matches walking
GRAB_S = 12.0             # budget for reaching the wall and getting a grip
CLIMB_S = 22.0            # budget for the ascent itself
STALL_S = 3.0             # no height gained in this long on the wall = stuck
GAIN = 5.0                # units of y that count as "still going up"


#: Widening sweep. v1 scanned once at 400 and aborted — but the climbable
#: surface is rarely where you happen to be standing, and after any
#: errand Link is somewhere else. Room 0 has a ladder AND a vine wall
#: ~500 units out; neither is visible from everywhere.
SCAN_LENGTHS = (400.0, 900.0, 1500.0)
TRAVEL_S = 24.0           # budget for crossing the room to the climbable
TRAVEL_WITHIN = 85.0      # close enough that the grab approach can take over


def _find_climbable(game: Game):
    """Nearest climbable face from a widening scan, or None."""
    for length in SCAN_LENGTHS:
        rays = game.scan_climbable(rays=24, length=length)
        if rays:
            return min(rays, key=lambda r: r.get("dist", 1e9))
    return None


def _travel_to(game: Game, x: float, z: float) -> None:
    """Cross to (x, z). walk_to_point re-aims but gives up after its own
    timeout, so call it repeatedly and watch for genuine stalling —
    honest failure beats holding the stick into a wall forever."""
    deadline = time.monotonic() + TRAVEL_S
    best = game.dist_to_point(x, z)
    while time.monotonic() < deadline:
        if game.dist_to_point(x, z) <= TRAVEL_WITHIN:
            return
        game.walk_to_point(x, z, within=TRAVEL_WITHIN, timeout=4.0)
        now = game.dist_to_point(x, z)
        if now < best - 20.0:
            best = now
        elif now > best - 20.0 and time.monotonic() > deadline - TRAVEL_S / 2:
            break
    if game.dist_to_point(x, z) > TRAVEL_WITHIN * 2:
        raise BehaviorAbort(
            f"could not cross to the climbable: stalled {game.dist_to_point(x, z):.0f} away")


def _climbable_bearing(game: Game):
    """Nearest climbable face, as (world_yaw_to_it, distance)."""
    rays = game.scan_climbable(rays=24, length=400)
    if not rays:
        return None
    best = min(rays, key=lambda r: r.get("dist", 1e9))
    pos = best.get("pos") or []
    if len(pos) < 3:
        return None
    return game.world_yaw_to_point(pos[0], pos[2]), float(best.get("dist", 0.0))


def _climb_body_v2(game: Game, ctx) -> None:
    """v2: find a climbable anywhere in the room, WALK to it, then climb.

    v1 assumed the climbable was already underfoot and aborted with "no
    climbable surface within 400 units" the moment Link had done anything
    else first — which, in a room where the chest is on a ledge, is
    always. Room 0 turned out to hold both a ladder and a vine wall, each
    invisible from most of the floor.
    """
    face = _find_climbable(game)
    if face is None:
        raise BehaviorAbort(
            f"no climbable surface anywhere within {SCAN_LENGTHS[-1]:.0f} units")
    pos = face.get("pos") or []
    if len(pos) < 3:
        raise BehaviorAbort("climbable ray carried no position")
    kind = "vine" if face.get("is_vine") else "ladder"
    _travel_to(game, pos[0], pos[2])

    # Re-acquire from up close: the bearing that mattered from across the
    # room is not the bearing that grabs.
    face = _find_climbable(game) or face
    pos = face.get("pos") or pos
    bearing = game.world_yaw_to_point(pos[0], pos[2])
    dist = game.dist_to_point(pos[0], pos[2])
    del kind

    # Walk into it and KEEP walking — the grab needs velocity (fact 3).
    deadline = time.monotonic() + GRAB_S
    while time.monotonic() < deadline and not game.climbing():
        game.walk_bearing(bearing, seconds=0.3)
    if not game.climbing():
        raise BehaviorAbort(
            f"walked into the climbable at {dist:.0f} for {GRAB_S:.0f}s, "
            f"never got a grip (wrong facing, or a ledge too low to grab)")

    # On the wall: raw stick up, no camera term (fact 1), no A (fact 2).
    start_y = (game.pos() or (0.0, 0.0, 0.0))[1]
    best_y = start_y
    stall_until = time.monotonic() + STALL_S
    deadline = time.monotonic() + CLIMB_S
    while time.monotonic() < deadline:
        if not (game.climbing() or game.mounting_ledge()):
            break                      # topped out, or fell off
        game.pad(stick=(0, CLIMB_MAGNITUDE))
        game.wait(0.2)
        y = (game.pos() or (0.0, best_y, 0.0))[1]
        if y > best_y + GAIN:
            best_y, stall_until = y, time.monotonic() + STALL_S
        elif time.monotonic() > stall_until:
            game.pad_clear()
            raise BehaviorAbort(
                f"stuck on the wall at +{best_y - start_y:.0f} for {STALL_S:.0f}s")
    game.pad_clear()
    game.wait(0.6)                     # let the ledge mount finish


def _gained_height(game: Game, initial: dict, events: list) -> bool:
    """Success = Link is materially higher than he started AND off the
    wall. Positive present-tense evidence, and it rejects the failure
    that matters: clinging halfway up a ladder is not a climb."""
    start = ((initial.get("player") or {}).get("pos") or [0.0, 0.0, 0.0])[1]
    now = game.pos()
    if now is None:
        return False
    return (now[1] - start) >= 150.0 and not game.climbing()


BEHAVIORS = {
    "climb_ladder_v1": Behavior(
        name="climb_ladder", version=1,
        description="scan for the nearest ladder/vine face, walk into it "
                    "until the grab takes, then hold stick-up to the top",
        body=_climb_body_v2, success=_gained_height, timeout_s=90.0,
        grade="UNGRADED (field-authored, fourth flight — ocarina's first "
              "climb of anything). Takes the NEAREST climbable face, which "
              "the dojo's own backlog says is the wrong policy: prefer the "
              "TALLEST (climb_vines picks nearest and reaches the top in "
              "2/5 tries). Fine here — room 0 offers one ladder.",
        notes=["Never presses A: A releases the wall unconditionally.",
               "Uses raw stick, not stick_for_world_yaw — the climb is not "
               "camera-relative (z_player.c Player_Action_8084BF1C)."]),
}
