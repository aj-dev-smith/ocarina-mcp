"""Kokiri flight bodies (ninth flight, 2026-08-05, docs/28 acceptance).

Opening legs: out of Link's house, down off the balcony, onto the
forest floor. House doors are En_Door 0x0009 (named `door` as of
0.9.0); the exit is judged by SCENE, not region — leaving a scene is
the one arrival the map can't misread. The balcony descent is a
walk-off: traverse rightly refuses descending grabs (docs/25), and the
drop is ~180 units — well under harm, measured on the distilled map
(balcony y=100, floor y=-80 at the ladder base).
"""

import math
import time

from ocarina.behavior import Behavior, BehaviorAbort

EN_DOOR = 0x0009        # house doors
EN_HOLL = 0x0023        # transition planes
SHUTTER = 0x002E        # dungeon shutters (none expected here)

SCENE_LINK_HOME = 52    # 0x34
SCENE_KOKIRI = 85       # 0x55

BALCONY = "spot04:r@-30,100,1100"
FLOOR = "spot04:r@-100,10,220"
LADDER_TOP = (-29.0, 1044.0)    # distiller stand point at the ladder head


def _region(game):
    s = game.place.sample(game.state()) if game.place else None
    return (s or {}).get("region")


def _clear_boxes(game):
    # Fresh file: every Navi trigger in the game is armed. Bounded blind
    # clearing (the free-play discipline); dialogue lands in oot://dialogue
    # either way, so blind-advanced text is still READ, just not waited on.
    for _ in range(12):
        if game.state().get("msg_mode", 0) == 0:
            return
        game.press("A")
        game.wait(0.5)
    raise BehaviorAbort("a message box would not clear after 12 advances")


def _door_probe_body(game, ctx):
    ids = {EN_DOOR: "door", EN_HOLL: "plane", SHUTTER: "shutter"}
    rows = []
    for a in game.state().get("actors") or []:
        if a.get("id") in ids:
            p = a.get("pos") or [0, 0, 0]
            rows.append(f"{ids[a['id']]}@({p[0]:.0f},{p[1]:.0f},{p[2]:.0f})"
                        f"yaw={a.get('yaw', 0):#06x}d{a.get('dist_xz', 0):.0f}")
    me = game.pos() or (0, 0, 0)
    raise BehaviorAbort(
        f"me=({me[0]:.0f},{me[1]:.0f},{me[2]:.0f}) :: "
        + ("; ".join(rows) if rows else "NO door-family actors in census"))


# The house exit is NOT an actor (door_probe_v1 measured an empty
# census): it is a collision exit plane, exit_index 2, two polys with
# centroids (12,0,-163)/(-12,0,-189). Walking through it changes scene.
EXIT_PLANE = (0.0, -185.0)


def _leave_house_body(game, ctx):
    for attempt in range(3):
        _clear_boxes(game)
        for _ in range(80):
            if game.state().get("scene") == SCENE_KOKIRI:
                game.pad_clear()
                return
            q = game.pos()
            if q is None:          # mid-load: hands off the pad
                game.pad_clear()
                game.wait(0.5)
                continue
            game.walk_bearing(game.world_yaw_to_point(*EXIT_PLANE),
                              seconds=0.2, magnitude=100)
        game.pad_clear()
    q = game.pos() or (0, 0, 0)
    raise BehaviorAbort(
        f"walked at the exit plane 3 rounds, still in scene "
        f"{game.state().get('scene')} at ({q[0]:.0f},{q[2]:.0f})")


def _outside(game, initial, events):
    return game.state().get("scene") == SCENE_KOKIRI


def _descend_balcony_body(game, ctx):
    _clear_boxes(game)
    r = _region(game)
    if r == FLOOR:
        return
    if r != BALCONY:
        raise BehaviorAbort(f"not on the balcony — the map says {r}")
    game.walk_to_point(*LADDER_TOP, within=20.0, timeout=15.0)
    game.pad_clear()
    game.wait(0.3)
    # walk off toward the ladder line; Link either grabs the ladder
    # (walk-off auto-mount) or drops the ~180 units — both end on FLOOR
    bearing = game.world_yaw_to_point(-29.0, 960.0)
    game.walk_bearing(bearing, seconds=0.9, magnitude=80)
    if game.state().get("player", {}).get("climbing"):
        # ride the ladder down: hold stick down until the floor
        for _ in range(30):
            game.pad(stick=(0, -127))
            game.wait(0.3)
            if not game.state().get("player", {}).get("climbing"):
                break
        game.pad_clear()
    game.wait(1.5)
    q = game.pos()
    if q is None:
        raise BehaviorAbort("no position after the descent")
    if _region(game) != FLOOR:
        raise BehaviorAbort(
            f"descended to y={q[1]:.0f} but the map says {_region(game)}")


def _on_floor(game, initial, events):
    return _region(game) == FLOOR


# The crawl hole to the sword training area. oot://place shows it as
# unlinked columns: spot04:crawl@-780,120,1060 and @-780,120,1080 (the
# near mouth), @-780,120,1360/1380 (the far end), with the tunnel floor
# distilled as ledge r@-780,120,1220. Approach is up the west hill.
CRAWL_HOLE = (-785.0, 1046.0)
# A*-routed on the collision mesh (18 polys, ~3950 units): south through
# the village, around the SW corner, up the ramp at x~-650 (y 0->120),
# then north along the terrace. v1's straight-west guess ground the
# cliff directly under the hole (AJ eyewitness).
HILL_WAYPOINTS = ((0.0, 700.0), (-50.0, 250.0), (-300.0, -250.0),
                  (-560.0, -320.0), (-660.0, -120.0), (-620.0, 300.0),
                  (-810.0, 700.0), (-820.0, 950.0))


def _goto_crawl_body(game, ctx):
    _clear_boxes(game)
    # start at the NEAREST waypoint (sixth-flight leg skipping):
    # retry-safety means routing from where you ARE
    q = game.pos() or (0.0, 0.0, 0.0)
    start = min(range(len(HILL_WAYPOINTS)),
                key=lambda i: math.hypot(HILL_WAYPOINTS[i][0] - q[0],
                                         HILL_WAYPOINTS[i][1] - q[2]))
    for wx, wz in HILL_WAYPOINTS[start:]:
        _walk_smart(game, wx, wz, timeout=15.0, within=45.0)
    _walk_smart(game, *CRAWL_HOLE, timeout=15.0, within=25.0)
    q = game.pos()
    if q is None:
        raise BehaviorAbort("no position at the end of the walk")
    d = math.hypot(q[0] - CRAWL_HOLE[0], q[2] - CRAWL_HOLE[1])
    if d > 70.0 or q[1] < 60.0:
        near = [r for r in game.scan(rays=12, length=60.0)
                if r.get("hit")]
        walls = "; ".join(f"y{r['yaw']:#06x}d{r['dist']:.0f}" for r in near[:6])
        raise BehaviorAbort(
            f"stopped {d:.0f} from the hole at "
            f"({q[0]:.0f},{q[1]:.0f},{q[2]:.0f}), region {_region(game)}; "
            f"nearby walls: {walls or 'none within 60'}")


def _at_hole(game, initial, events):
    q = game.pos()
    return (q is not None and q[1] >= 60.0
            and math.hypot(q[0] - CRAWL_HOLE[0], q[2] - CRAWL_HOLE[1]) <= 70.0)


CRAWL_FLAGS = 48    # WALL_FLAG_CRAWLSPACE = (1<<4)|(1<<5)


def _crawl_probe_body(game, ctx):
    # v1 looked for an OPENING at crawl height — wrong predicate: the
    # mouth is a crawl-FLAGGED wall poly (the game's own marker).
    q = game.pos() or (0, 0, 0)
    rays = [r for r in game.scan(rays=36, length=100.0, height=12.0)
            if r.get("hit") and (r.get("wall_flags", 0) & CRAWL_FLAGS)]
    rows = "; ".join(
        f"yaw={r['yaw']:#06x}d{r['dist']:.0f}@"
        f"({r['pos'][0]:.0f},{r['pos'][2]:.0f})" for r in rays[:8])
    raise BehaviorAbort(
        f"me=({q[0]:.0f},{q[1]:.0f},{q[2]:.0f}) region {_region(game)} :: "
        + (f"crawl walls: {rows}" if rays
           else "NO crawl-flagged wall within 100"))


def _crawl_through_body(game, ctx):
    _clear_boxes(game)
    rays = [r for r in game.scan(rays=36, length=60.0, height=12.0)
            if r.get("hit") and (r.get("wall_flags", 0) & CRAWL_FLAGS)]
    if not rays:
        raise BehaviorAbort("no crawl-flagged wall within 60 units")
    r0 = min(rays, key=lambda r: r["dist"])
    hx, hy, hz = r0["pos"]

    # square up ~14 units off the face, then A to enter (A snaps to the
    # centerline; the entry window is ~8 units)
    entered = False
    for attempt in range(8):
        game.walk_to_point(hx, hz - 14.0, within=5.0, timeout=8.0)
        game.pad_clear()
        game.wait(0.3)
        bearing = game.world_yaw_to_point(hx, hz)
        game.walk_bearing(bearing, seconds=0.25, magnitude=40)
        game.pad_clear()
        game.wait(0.2)
        game.press("A")
        game.wait(1.4)
        q = game.pos()
        if q is not None and q[2] > hz + 2.0:
            entered = True
            break
    if not entered:
        q = game.pos() or (0, 0, 0)
        raise BehaviorAbort(
            f"pressed A 8 times at the crawl wall (face z={hz:.0f}), "
            f"never entered; at ({q[0]:.0f},{q[2]:.0f})")

    # crawl: hold stick forward in bursts; flip if we're backing out
    sign, last, stall = 127, None, 0
    for _ in range(60):
        game.pad(stick=(0, sign))
        game.wait(0.4)
        q = game.pos()
        if q is None:
            continue
        if q[2] > 1390.0:
            break
        if last is not None:
            dz = q[2] - last
            if dz < -3.0:
                sign = -sign
                stall = 0
            elif abs(dz) < 2.0:
                stall += 1
                if stall >= 10:
                    game.pad_clear()
                    raise BehaviorAbort(
                        f"crawl stalled at z={q[2]:.0f} for 4s")
            else:
                stall = 0
        last = q[2]
    game.pad_clear()
    game.wait(1.0)


def _through_tunnel(game, initial, events):
    q = game.pos()
    return q is not None and q[2] > 1390.0


def _crawl_back_body(game, ctx):
    # Southbound: maze -> village terrace. Far mouth face is at
    # z~1380 facing the maze; enter and crawl until z < 1050.
    _clear_boxes(game)
    _wait_boulder_pass(game)
    game.walk_to_point(-780.0, 1400.0, within=15.0, timeout=25.0,
                       magnitude=110)
    rays = [r for r in game.scan(rays=36, length=60.0, height=12.0)
            if r.get("hit") and (r.get("wall_flags", 0) & CRAWL_FLAGS)]
    if not rays:
        raise BehaviorAbort("no crawl-flagged wall within 60 units")
    r0 = min(rays, key=lambda r: r["dist"])
    hx, hy, hz = r0["pos"]
    entered = False
    for attempt in range(8):
        game.walk_to_point(hx, hz + 14.0, within=5.0, timeout=8.0)
        game.pad_clear()
        game.wait(0.3)
        bearing = game.world_yaw_to_point(hx, hz)
        game.walk_bearing(bearing, seconds=0.25, magnitude=40)
        game.pad_clear()
        game.wait(0.2)
        game.press("A")
        game.wait(1.4)
        q = game.pos()
        if q is not None and q[2] < hz - 2.0:
            entered = True
            break
    if not entered:
        q = game.pos() or (0, 0, 0)
        raise BehaviorAbort(
            f"pressed A 8 times at the return crawl wall (face "
            f"z={hz:.0f}), never entered; at ({q[0]:.0f},{q[2]:.0f})")
    sign, last, stall = 127, None, 0
    for _ in range(60):
        game.pad(stick=(0, sign))
        game.wait(0.4)
        q = game.pos()
        if q is None:
            continue
        if q[2] < 1050.0:
            break
        if last is not None:
            dz = q[2] - last
            if dz > 3.0:
                sign = -sign
                stall = 0
            elif abs(dz) < 2.0:
                stall += 1
                if stall >= 10:
                    game.pad_clear()
                    raise BehaviorAbort(
                        f"return crawl stalled at z={q[2]:.0f} for 4s")
            else:
                stall = 0
        last = q[2]
    game.pad_clear()
    game.wait(1.0)


def _back_on_terrace(game, initial, events):
    q = game.pos()
    return q is not None and q[2] < 1050.0


EN_KUSA = 0x0125
SHIELD_PRICE = 40


def _farm_shield_fund_body(game, ctx):
    # Cut bushes (first sword work on the bench), collect what drops,
    # until the shield is funded. Drops are En_Item00 — walk over them
    # only while they exist in census (phantom-drop lesson: re-check
    # every approach, give each drop ONE bounded try).
    cut = 0
    failed = []      # v2: unreachable bushes blacklist — v1's continue
    #                  re-elected the same nearest bush forever (the
    #                  collect_rupees v2 disease, caught by AJ's eyes
    #                  at the treehouse wall)
    while game.state().get("rupees", 0) < SHIELD_PRICE:
        bushes = [a for a in game.actors(actor_id=EN_KUSA)
                  if not any(math.hypot((a.get("pos") or (0, 0, 0))[0] - fx,
                                        (a.get("pos") or (0, 0, 0))[2] - fz)
                             < 25.0 for fx, fz in failed)]
        if not bushes:
            break
        b = min(bushes, key=lambda a: a.get("dist_xz", 1e9))
        p = b.get("pos") or (0, 0, 0)
        _clear_boxes(game)
        if not _walk_smart(game, p[0], p[2], timeout=12.0, within=18.0):
            failed.append((p[0], p[2]))
            continue
        bearing = game.world_yaw_to_point(p[0], p[2])
        game.walk_bearing(bearing, seconds=0.15, magnitude=40)
        game.pad_clear()
        game.wait(0.2)
        game.slash()
        game.wait(0.8)
        cut += 1
        # sweep any drops this bush left (one try each, close range)
        for _ in range(3):
            drops = [d for d in game.actors(actor_id=EN_ITEM00)
                     if d.get("dist_xz", 1e9) < 120.0]
            if not drops:
                break
            d0 = min(drops, key=lambda a: a.get("dist_xz", 1e9))
            dp = d0.get("pos") or (0, 0, 0)
            _walk_smart(game, dp[0], dp[2], timeout=6.0, within=8.0)
            game.wait(0.4)
        if cut >= 40:
            break
    r = game.state().get("rupees", 0)
    if r < SHIELD_PRICE:
        raise BehaviorAbort(
            f"cut {cut} bushes ({len(failed)} unreachable), rupees at "
            f"{r}/{SHIELD_PRICE} — need another patch or another source")


def _shield_funded(game, initial, events):
    return game.state().get("rupees", 0) >= SHIELD_PRICE


# Exit planes dumped from the spot04 collision (exit_index polys):
#   2 -> the Deku Tree (mission endpoint)   4 -> Link's house
#   7 -> Lost Woods    3 -> Hyrule Field bridge (probable)
#   5,9,10,11,6 -> the village buildings
TARGET_DOOR = (-452.0, -573.0)     # current candidate: exit 10


def _enter_building_body(game, ctx):
    _clear_boxes(game)
    tx, tz = TARGET_DOOR
    for attempt in range(3):
        _walk_smart(game, tx, tz, timeout=30.0, within=30.0)
        bearing = game.world_yaw_to_point(tx, tz)
        game.walk_bearing(bearing, seconds=2.0, magnitude=90)
        game.pad_clear()
        game.wait(2.0)
        if game.state().get("scene") != SCENE_KOKIRI:
            return
    q = game.pos() or (0, 0, 0)
    raise BehaviorAbort(
        f"walked into the door plane at ({tx:.0f},{tz:.0f}) 3 times, "
        f"still scene {game.state().get('scene')} at "
        f"({q[0]:.0f},{q[2]:.0f})")


def _inside_building(game, initial, events):
    return game.state().get("scene") != SCENE_KOKIRI


# Shop candidate doors, pond-adjacent (spot04 exit polys). The o2r
# scene header doesn't give exit->scene cheaply; this is empirical —
# enter, read the scene, back out if wrong.
SHOP_DOOR = (853.0, -405.0)    # exit 5 = THE SHOP (scene 0x2D, confirmed)
#                                (exit 9 (1082,605) was the twins'
#                                 house, scene 0x27)

EN_OSSAN = 0x003D              # shopkeeper (official name)


def _talk_to_shopkeeper_body(game, ctx):
    # Walk up to the counter, face the shopkeeper, A until the shop
    # dialogue opens. buy() owns everything after that; this body's
    # whole job is ending with dialogue_open true.
    _clear_boxes(game)
    k = game.nearest(EN_OSSAN)
    if k is None:
        raise BehaviorAbort("no shopkeeper in the census")
    p = k.get("pos") or (0, 0, 0)
    for attempt in range(6):
        q = game.pos() or (0, 0, 0)
        if math.hypot(p[0] - q[0], p[2] - q[2]) > 65.0:
            _walk_smart(game, p[0], p[2], timeout=8.0, within=55.0)
        game.pad_clear()
        bearing = game.world_yaw_to_point(p[0], p[2])
        game.walk_bearing(bearing, seconds=0.15, magnitude=30)
        game.pad_clear()
        game.wait(0.2)
        game.press("A")
        game.wait(1.2)
        if game.state().get("dialogue_open"):
            return
    q = game.pos() or (0, 0, 0)
    raise BehaviorAbort(
        f"pressed A 6 times at the counter, no dialogue; at "
        f"({q[0]:.0f},{q[2]:.0f}), shopkeeper at ({p[0]:.0f},{p[2]:.0f})")


def _talking(game, initial, events):
    return bool(game.state().get("dialogue_open"))


# -- the Deku Tree leg ------------------------------------------------------
SHOP_EXIT = (-20.0, 180.0)     # kokiri_shop exit polys ~(7,167)/(-47,193)
SCENE_YDAN = 0x00
EN_MD = 0x016D                 # Mido — checks sword AND shield equipped

# Mesh A* (spot04 collision, vertex-index adjacency, steep-penalized)
# from the shop door east up the trail; last two points are the flat
# meadow floor. TRAIL_END stops ~150 short of the exit plane at
# (4170,-1340) — the mission says STOP at the mouth, not enter.
TRAIL_WAYPOINTS = (
    (1232.0, -399.0),
    (1400.0, -94.0),
    (1783.0, 103.0),
    (2125.0, -77.0),
    (2454.0, -483.0),
    (2762.0, -593.0),
    (2942.0, -841.0),
    (3298.0, -1374.0),
    (3700.0, -1350.0),
    (4020.0, -1335.0),
)
TRAIL_END = TRAIL_WAYPOINTS[-1]


def _leave_shop_body(game, ctx):
    _clear_boxes(game)
    for _ in range(20):
        if game.state().get("scene") == SCENE_KOKIRI:
            game.pad_clear()
            return
        _walk_smart(game, SHOP_EXIT[0], SHOP_EXIT[1], timeout=3.0,
                    within=8.0)
    game.pad_clear()
    raise BehaviorAbort(
        f"smart-walked the shop exit plane, still in scene "
        f"{game.state().get('scene')}")


def _goto_deku_mouth_body(game, ctx):
    # Box hygiene at every waypoint (Mido's block dialogue and any
    # kokiri greeting freeze the pad); Mido himself is an actor, not
    # mesh — when he's near, face him and talk until he steps aside.
    for wx, wz in TRAIL_WAYPOINTS:
        _clear_boxes(game)
        sc = game.state().get("scene")
        if sc == SCENE_YDAN:
            raise BehaviorAbort(
                "crossed INTO the Deku Tree — overshot the mouth")
        if sc != SCENE_KOKIRI:
            raise BehaviorAbort(f"unexpected scene {sc} on the trail")
        _walk_smart(game, wx, wz, timeout=20.0, within=30.0)
        md = game.nearest(EN_MD)
        if md is not None and md.get("dist_xz", 1e9) < 150.0:
            p = md.get("pos") or (0, 0, 0)
            for _ in range(3):
                _clear_boxes(game)
                game.pad_clear()
                b = game.world_yaw_to_point(p[0], p[2])
                game.walk_bearing(b, seconds=0.2, magnitude=40)
                game.pad_clear()
                game.wait(0.2)
                game.press("A")
                game.wait(1.2)
                if game.state().get("msg_mode", 0) != 0:
                    _clear_boxes(game)
                    break
    _clear_boxes(game)
    q = game.pos() or (0, 0, 0)
    d = math.hypot(TRAIL_END[0] - q[0], TRAIL_END[1] - q[2])
    if d > 80.0:
        raise BehaviorAbort(
            f"trail walk ended {d:.0f} from the mouth at "
            f"({q[0]:.0f},{q[2]:.0f})")


def _at_mouth(game, initial, events):
    q = game.pos()
    if q is None:
        return False
    return (game.state().get("scene") == SCENE_KOKIRI
            and math.hypot(TRAIL_END[0] - q[0],
                           TRAIL_END[1] - q[2]) <= 80.0)


# -- inside the tree: the room-0 clear --------------------------------------
from ocarina.protocol import ACTOR_EN_DEKUBABA

DEKU_MOUTH_PLANE = (4170.0, -1340.0)


def _enter_deku_body(game, ctx):
    _clear_boxes(game)
    for _ in range(12):
        if game.state().get("scene") == SCENE_YDAN:
            # let any entry camera sweep finish before the next body
            game.wait(2.0)
            _clear_boxes(game)
            game.pad_clear()
            return
        _walk_smart(game, DEKU_MOUTH_PLANE[0], DEKU_MOUTH_PLANE[1],
                    timeout=4.0, within=10.0)
    game.pad_clear()
    raise BehaviorAbort(
        f"walked the mouth plane, still scene {game.state().get('scene')}")


def _in_deku(game, initial, events):
    return game.state().get("scene") == SCENE_YDAN


def _seek_baba_body(game, ctx):
    # Elector: is there a baba left? Abort IS the report when the room
    # reads clear — the mind verifies before celebrating.
    game.wait(0.5)
    _clear_boxes(game)
    babas = game.actors(actor_id=ACTOR_EN_DEKUBABA)
    if not babas:
        raise BehaviorAbort("no deku baba in the census — room reads clear")


def _baba_present(game, initial, events):
    return game.nearest(ACTOR_EN_DEKUBABA) is not None


def _enter_shop_body(game, ctx):
    # v2 fix folded in: clear boxes EVERY attempt, not just at entry —
    # a kokiri child talked to Link 4 s into v1's walk and the body
    # ground against a frozen pad for 100 s (box hygiene at every
    # interaction boundary, the flight-notes lesson, now paid for).
    tx, tz = SHOP_DOOR
    for attempt in range(3):
        _clear_boxes(game)
        _walk_smart(game, tx, tz, timeout=30.0, within=30.0)
        _clear_boxes(game)
        bearing = game.world_yaw_to_point(tx, tz)
        game.walk_bearing(bearing, seconds=2.0, magnitude=90)
        game.pad_clear()
        game.wait(2.0)
        if game.state().get("scene") != SCENE_KOKIRI:
            return
    q = game.pos() or (0, 0, 0)
    raise BehaviorAbort(
        f"walked into the shop-candidate door at ({tx:.0f},{tz:.0f}) "
        f"3 times, still scene {game.state().get('scene')} at "
        f"({q[0]:.0f},{q[2]:.0f})")


# every small kokiri house shares the template: exit plane ~(0,0,-260)
HOUSE_EXIT = (0.0, -262.0)


def _leave_building_body(game, ctx):
    # v2: the farm-cycle entry can leave Link parked ON a chest lid
    # (props are not in the mesh — scan showed y=26 in a wall pocket,
    # v1's straight bearing ground there for 3 rounds). Smart-walk via
    # the room centre first, then out the plane in short legs with a
    # scene check between each.
    _clear_boxes(game)
    _walk_smart(game, 0.0, -140.0, timeout=12.0, within=30.0)
    for _ in range(20):
        if game.state().get("scene") == SCENE_KOKIRI:
            game.pad_clear()
            return
        _walk_smart(game, HOUSE_EXIT[0], HOUSE_EXIT[1],
                    timeout=3.0, within=8.0)
    game.pad_clear()
    raise BehaviorAbort(
        f"smart-walked at the house exit plane, still in scene "
        f"{game.state().get('scene')}")


def _finish_get_item(game):
    # The get-item box appears at the END of the chest animation (~3s
    # after A) — wait for it, then clear it, or the next walk starts
    # into a pad the box is about to freeze.
    for _ in range(16):
        if game.state().get("msg_mode", 0) != 0:
            _clear_boxes(game)
            game.wait(0.3)
            return
        game.wait(0.5)


def _sweep_chests_body(game, ctx):
    # Open every closed chest in the scene (front = plain yaw, the v4
    # lesson). Abort IS the report: chests found/opened, rupee delta.
    start = game.state().get("rupees", 0)
    opened = 0
    total = len(game.actors(actor_id=EN_BOX))
    for _ in range(8):
        closed = [c for c in game.actors(actor_id=EN_BOX)
                  if not c.get("opened")]
        if not closed:
            break
        chest = min(closed, key=lambda a: a.get("dist_xz", 1e9))
        _clear_boxes(game)   # a get-item box freezes the pad (docs/26)
        p = chest.get("pos") or (0, 0, 0)
        yaw = chest.get("yaw", 0)
        ang = (yaw & 0xFFFF) / 65536.0 * 2.0 * math.pi
        nx, nz = math.sin(ang), math.cos(ang)
        rx, rz = nz, -nx
        _walk_smart(game, p[0] + (nx + rx) * 55.0,
                    p[2] + (nz + rz) * 55.0, timeout=10.0, within=20.0)
        _walk_smart(game, p[0] + nx * 40.0, p[2] + nz * 40.0,
                    timeout=10.0, within=10.0)
        got = False
        for _ in range(5):
            bearing = game.world_yaw_to_point(p[0], p[2])
            game.walk_bearing(bearing, seconds=0.2, magnitude=32)
            game.pad_clear()
            game.wait(0.25)
            game.press("A")
            game.wait(1.6)
            _clear_boxes(game)
            fresh = [c for c in game.actors(actor_id=EN_BOX)
                     if c.get("pos") and
                     math.hypot(c["pos"][0] - p[0],
                                c["pos"][2] - p[2]) < 30.0]
            if fresh and fresh[0].get("opened"):
                got = True
                opened += 1
                _finish_get_item(game)
                break
        if not got:
            break
    now = game.state().get("rupees", 0)
    raise BehaviorAbort(
        f"chest sweep: {total} chests in scene, opened {opened}, "
        f"rupees {start} -> {now}")


EN_BOX = 0x000A
EN_ITEM00 = 0x0015
BOULDER = 0x0130


def _wait_boulder_pass(game, near=150.0, timeout_polls=50):
    # Wait for the boulder to PASS (dist falls below `near`, then
    # rises) and move out behind it — a full lap of clearance.
    closest = 1e9
    for _ in range(timeout_polls):
        b = game.nearest(BOULDER)
        if b is None:
            return
        d = b.get("dist_xz", 1e9)
        if d < closest:
            closest = d
        elif closest < near and d > closest + 25.0:
            return
        game.wait(0.4)


def _walk_smart(game, x, z, timeout=20.0, within=10.0):
    # Maze-grade walking: short segments with stall detection; on a
    # wedge, sidestep perpendicular (alternating sides) and retry —
    # the 0.7.1 traverse sidestep, mind-side.
    deadline = time.time() + timeout
    side, best = 1, 1e9
    while time.time() < deadline:
        q = game.pos()
        if q is None:
            game.wait(0.4)
            continue
        d = math.hypot(x - q[0], z - q[2])
        if d <= within:
            game.pad_clear()
            return True
        game.walk_to_point(x, z, within=within, timeout=2.0,
                           magnitude=110)
        q2 = game.pos()
        if q2 is None:
            continue
        d2 = math.hypot(x - q2[0], z - q2[2])
        if d2 <= within:
            game.pad_clear()
            return True
        if d2 > best - 6.0:      # wedged: sidestep and flip sides
            bearing = (game.world_yaw_to_point(x, z)
                       + side * 0x4000) & 0xFFFF
            game.walk_bearing(bearing, seconds=0.8, magnitude=95)
            side = -side
        best = min(best, d2)
    game.pad_clear()
    return False


def _collect_rupees_body(game, ctx):
    # Sweep every placed collectible (En_Item00) in the maze; the
    # census names them (0.9.0 param-aware naming). Abort IS the
    # report: what was here, what we picked up, rupees after.
    start = game.state().get("rupees", 0)
    seen = len(game.actors(actor_id=EN_ITEM00))
    grabbed = 0
    failed = []      # unreachable items: blacklist, don't re-elect
    for _ in range(16):
        items = [a for a in game.actors(actor_id=EN_ITEM00)
                 if a.get("pos") and not any(
                     math.hypot(a["pos"][0] - fx, a["pos"][2] - fz) < 15
                     for fx, fz in failed)]
        if not items:
            break
        it = min(items, key=lambda a: a.get("dist_xz", 1e9))
        p = it["pos"]
        _wait_boulder_pass(game)
        reached = _walk_smart(game, p[0], p[2], timeout=14.0,
                              within=10.0)
        game.wait(0.5)
        still = [a for a in game.actors(actor_id=EN_ITEM00)
                 if a.get("pos") and
                 math.hypot(a["pos"][0] - p[0],
                            a["pos"][2] - p[2]) < 12.0]
        if still or not reached:
            failed.append((p[0], p[2]))
        else:
            grabbed += 1
    now = game.state().get("rupees", 0)
    raise BehaviorAbort(
        f"maze sweep: {seen} placed items at start, grabbed {grabbed}, "
        f"{len(failed)} unreachable, rupees {start} -> {now}")


def _open_chest_body(game, ctx):
    # Sword alley: a boulder patrols the trench — don't linger. Walk to
    # the chest FRONT (En_Box front = yaw + 0x8000), A from up close.
    chests = game.actors(actor_id=EN_BOX)
    if not chests:
        rows = "; ".join(
            f"{a.get('id'):#06x}d{a.get('dist_xz', 0):.0f}"
            for a in sorted(game.actors(),
                            key=lambda a: a.get("dist_xz", 1e9))[:8])
        raise BehaviorAbort(f"no treasure_chest in census; nearest: {rows}")
    chest = min(chests, key=lambda a: a.get("dist_xz", 1e9))
    if chest.get("opened"):
        raise BehaviorAbort("the chest is already open (census flag)")
    p = chest.get("pos") or (0, 0, 0)
    yaw = chest.get("yaw", 0)
    # v3 used yaw+0x8000 per the backlog note — AJ's eyes say that put
    # Link square on the BACK. The front is at plain yaw.
    front = yaw & 0xFFFF
    ang = front / 65536.0 * 2.0 * math.pi
    nx, nz = math.sin(ang), math.cos(ang)
    fx = p[0] + nx * 45.0
    fz = p[2] + nz * 45.0
    # chests are actors, not mesh: a straight walk wedges on the box
    # (v2 stalled 34 units behind it). Go around: side -> front corner.
    rx, rz = nz, -nx
    side = (p[0] + rx * 60.0, p[2] + rz * 60.0)
    corner = (p[0] + (nx + rx) * 55.0, p[2] + (nz + rz) * 55.0)

    _clear_boxes(game)
    # The boulder laps the trench faster than the walk: "far right now"
    # is no shelter (it clipped us twice). Wait for it to PASS — dist
    # falling below 150 then rising — and follow BEHIND it: a full lap
    # of clearance. If it never comes near in 20s, just go.
    closest, passed = 1e9, False
    for _ in range(50):
        b = game.nearest(0x0130)
        if b is None:
            break
        d = b.get("dist_xz", 1e9)
        if d < closest:
            closest = d
        elif closest < 150.0 and d > closest + 25.0:
            passed = True
            break
        game.wait(0.4)
    game.walk_to_point(side[0], side[1], within=25.0, timeout=12.0,
                       magnitude=110)
    game.walk_to_point(corner[0], corner[1], within=20.0, timeout=12.0,
                       magnitude=110)
    if not game.walk_to_point(fx, fz, within=14.0, timeout=15.0,
                              magnitude=110):
        q = game.pos() or (0, 0, 0)
        raise BehaviorAbort(
            f"could not reach the chest front ({fx:.0f},{fz:.0f}); "
            f"at ({q[0]:.0f},{q[2]:.0f})")
    for attempt in range(6):
        bearing = game.world_yaw_to_point(p[0], p[2])
        game.walk_bearing(bearing, seconds=0.2, magnitude=32)
        game.pad_clear()
        game.wait(0.25)
        game.press("A")
        game.wait(2.0)
        fresh = game.actors(actor_id=EN_BOX)
        fresh = min(fresh, key=lambda a: a.get("dist_xz", 1e9)) if fresh else None
        if fresh and fresh.get("opened"):
            # get-item cutscene + text ride the ring; advance through
            game.wait(2.0)
            _clear_boxes(game)
            return
    raise BehaviorAbort("pressed A 6 times at the chest front, "
                        "opened flag never flipped")


def _chest_open(game, initial, events):
    chests = game.actors(actor_id=EN_BOX)
    return bool(chests) and any(a.get("opened") for a in chests)


BEHAVIORS = {
    "door_probe_v1": Behavior(
        name="door_probe", version=1,
        description="journal every door/plane/shutter actor with world "
                    "pos + yaw (abort IS the report)",
        body=_door_probe_body,
        success=lambda game, initial, events: False,
        timeout_s=10.0,
        grade="diagnostic; holds no pad, always aborts"),
    "leave_house_v1": Behavior(
        name="leave_house", version=1,
        description="walk through the house exit plane (collision exit "
                    "2, no actor, no A); success = the SCENE is Kokiri "
                    "Forest",
        body=_leave_house_body, success=_outside, timeout_s=60.0,
        grade="UNGRADED (field-authored, ninth flight). v1 door-census "
              "approach falsified by door_probe_v1: the exit is a "
              "collision plane. Scene-judged arrival."),
    "descend_balcony_v1": Behavior(
        name="descend_balcony", version=1,
        description="balcony -> forest floor: walk off at the ladder "
                    "head (auto-mount rides it down, a plain drop is "
                    "~180 units, both safe); map-judged landing",
        body=_descend_balcony_body, success=_on_floor, timeout_s=45.0,
        grade="UNGRADED (field-authored, ninth flight). First descent "
              "body on the bench — the honest not-yet, done by eye."),
    "goto_crawl_v3": Behavior(
        name="goto_crawl", version=3,
        description="anywhere on the floor -> the crawl hole mouth via "
                    "the SW ramp (A*-routed waypoints, nearest-first "
                    "leg skipping, wedge-sidestepping)",
        body=_goto_crawl_body, success=_at_hole, timeout_s=180.0,
        grade="UNGRADED (field-authored, ninth flight). v1 walked "
              "straight west into the cliff under the hole — the ramp "
              "is across the village; caught by AJ's eyes, routed by "
              "A* on the collision mesh. v3 starts at the nearest "
              "waypoint and uses _walk_smart."),
    "crawl_probe_v2": Behavior(
        name="crawl_probe", version=2,
        description="scan fan at crawl height reporting crawl-FLAGGED "
                    "walls (wall_flags & 48, the game's own crawlspace "
                    "marker); abort IS the report",
        body=_crawl_probe_body,
        success=lambda game, initial, events: False,
        timeout_s=15.0,
        grade="diagnostic; holds no pad, always aborts. v1 looked for "
              "an opening in the mesh — the mouth is a flagged wall."),
    "open_chest_v4": Behavior(
        name="open_chest", version=4,
        description="nearest census chest: refuse if already open, "
                    "wait for the boulder to PASS then follow behind "
                    "it, walk to the chest front (yaw+0x8000), A until "
                    "the game's own opened flag flips",
        body=_open_chest_body, success=_chest_open, timeout_s=90.0,
        grade="UNGRADED (field-authored, ninth flight). open_chest_v5 "
              "lineage (opened-flag refusal). v1 checked the boulder "
              "was far at t0 — it laps faster than the walk; two hits. "
              "v2 followed behind it but wedged on the chest's back "
              "(actors are not mesh, docs/26). v3 went side->corner->"
              "front but the backlog's front formula (yaw+0x8000) is "
              "BACKWARDS — 6 A-presses into the back panel, AJ "
              "eyewitness. v4: front = plain yaw."),
    "collect_rupees_v3": Behavior(
        name="collect_rupees", version=3,
        description="sweep every placed En_Item00 in reach (boulder-"
                    "timed, wedge-sidestepping walks, unreachable-item "
                    "blacklist); abort IS the report",
        body=_collect_rupees_body,
        success=lambda game, initial, events: False,
        timeout_s=150.0,
        grade="diagnostic-collector hybrid; always aborts with the "
              "sweep report. v1 walked straight lines in a maze (AJ "
              "eyewitness: wall-grinding); v2 sidestepped but "
              "re-elected the same unreachable item forever (AJ "
              "eyewitness again); v3 blacklists failures."),
    "leave_building_v2": Behavior(
        name="leave_building", version=2,
        description="smart-walk out through the shared small-house "
                    "exit plane (~(0,0,-260) in every kokiri_home "
                    "scene) via the room centre — v1 wedged on a "
                    "chest lid; success = back in Kokiri Forest",
        body=_leave_building_body, success=_outside, timeout_s=60.0,
        grade="UNGRADED (field-authored, ninth flight). leave_house_v1 "
              "generalised — all small houses share the template."),
    "enter_building_v1": Behavior(
        name="enter_building", version=1,
        description="walk into the exit plane at TARGET_DOOR (edit the "
                    "constant + reload to retarget); success = scene "
                    "changed",
        body=_enter_building_body, success=_inside_building,
        timeout_s=120.0,
        grade="UNGRADED (field-authored, ninth flight). leave_house_v1 "
              "lineage, outdoor side."),
    "enter_shop_v2": Behavior(
        name="enter_shop", version=2,
        description="walk into the shop-candidate exit plane at "
                    "SHOP_DOOR (edit the constant + reload to try the "
                    "next candidate); box hygiene every attempt; "
                    "success = scene changed",
        body=_enter_shop_body, success=_inside_building,
        timeout_s=120.0,
        grade="UNGRADED (field-authored, ninth flight). "
              "enter_building_v1 lineage, shop-candidate probe. v1 "
              "walked 100 s against a pad frozen by a kokiri child's "
              "greeting (cleared boxes only at entry); v2 clears at "
              "every attempt boundary."),
    "talk_to_shopkeeper_v1": Behavior(
        name="talk_to_shopkeeper", version=1,
        description="approach the counter and open the shop dialogue "
                    "(buy() owns the purchase from there); success = "
                    "dialogue open",
        body=_talk_to_shopkeeper_body, success=_talking,
        timeout_s=90.0,
        grade="UNGRADED (field-authored, ninth flight)."),
    "leave_shop_v1": Behavior(
        name="leave_shop", version=1,
        description="walk out the kokiri_shop exit plane (~(-20,180)); "
                    "success = back in Kokiri Forest",
        body=_leave_shop_body, success=_outside, timeout_s=90.0,
        grade="UNGRADED (field-authored, ninth flight). "
              "leave_building_v2 lineage."),
    "goto_deku_mouth_v1": Behavior(
        name="goto_deku_mouth", version=1,
        description="walk the mesh-routed trail east from the shop to "
                    "the Deku Tree's mouth, talking Mido aside "
                    "(sword+shield equipped); STOPS ~150 short of the "
                    "exit plane — entering ydan is a failure",
        body=_goto_deku_mouth_body, success=_at_mouth, timeout_s=300.0,
        grade="UNGRADED (field-authored, ninth flight). The mission "
              "endpoint leg."),
    "enter_deku_v1": Behavior(
        name="enter_deku", version=1,
        description="walk through the Deku Tree's mouth plane at "
                    "(4170,-1340); success = scene is ydan",
        body=_enter_deku_body, success=_in_deku, timeout_s=90.0,
        grade="UNGRADED (field-authored, ninth flight)."),
    "seek_baba_v1": Behavior(
        name="seek_baba", version=1,
        description="elector: succeed if a deku baba is in the census, "
                    "abort-report 'room reads clear' when none",
        body=_seek_baba_body, success=_baba_present, timeout_s=20.0,
        grade="UNGRADED (field-authored, ninth flight). Abort IS the "
              "report."),
    "sweep_chests_v3": Behavior(
        name="sweep_chests", version=3,
        description="open every closed chest in the scene (front = "
                    "plain yaw; wait for + clear each get-item box); "
                    "abort IS the report (opened count + rupee delta)",
        body=_sweep_chests_body,
        success=lambda game, initial, events: False,
        timeout_s=180.0,
        grade="diagnostic-collector hybrid; always aborts with the "
              "report. v1 lost the pad to chest 1's get-item box "
              "(modal box freezes the pad, docs/26 #1); v2's loop-top "
              "clear ran BEFORE the box existed (it appears ~3s after "
              "A, at the end of the animation) — v3 waits for it."),
    "farm_shield_fund_v2": Behavior(
        name="farm_shield_fund", version=2,
        description="cut bushes and collect drops until rupees >= 40 "
                    "(the Deku Shield fund); bounded phantom-drop "
                    "discipline; unreachable-bush blacklist; aborts "
                    "with the tally if the patch runs dry",
        body=_farm_shield_fund_body, success=_shield_funded,
        timeout_s=300.0,
        grade="UNGRADED (field-authored, ninth flight). First sword "
              "work on the bench. v1 re-elected an unreachable bush "
              "forever (5 min at the treehouse wall, AJ's eyes); v2 "
              "blacklists walk failures like collect_rupees v3."),
    "crawl_back_v1": Behavior(
        name="crawl_back", version=1,
        description="maze -> village terrace through the crawl, "
                    "southbound (mirror of crawl_through_v1); success "
                    "= z back below 1050",
        body=_crawl_back_body, success=_back_on_terrace, timeout_s=90.0,
        grade="UNGRADED (field-authored, ninth flight)."),
    "crawl_through_v1": Behavior(
        name="crawl_through", version=1,
        description="enter the crawl-flagged wall with A (snaps to the "
                    "centerline), crawl north holding stick forward, "
                    "auto-flipping if backing out; success = z past the "
                    "far mouth (1390)",
        body=_crawl_through_body, success=_through_tunnel,
        timeout_s=90.0,
        grade="UNGRADED (field-authored, ninth flight). The bench's "
              "first crawl."),
}
