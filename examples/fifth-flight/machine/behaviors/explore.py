"""wander_scan: explore on the geometry sense.

Each leg scans a fan around Link, scores every bearing by how open it is
(a miss beats any hit), skips bearings that point at a living enemy
within engagement-ish range, and walks the best one briefly before
re-scanning. Camera drift is handled by walk_bearing itself. Never
presses A (a grab near vines would yank Link up a wall mid-wander).

Success is RELATIVE displacement (capability, not location — the
workshop naming rule): did we actually go somewhere, wherever that was.
"""

import math

from ocarina.behavior import Behavior
from ocarina.protocol import ACTORCAT_ENEMY

_OPEN = 600.0          # score for a ray that hit nothing
_AVOID_DIST = 250.0    # enemies closer than this veto their bearing
_AVOID_CONE = 0x2000   # +/- how much of the fan an enemy vetoes


def _yaw_diff(a: int, b: int) -> int:
    return abs((((a - b) & 0xFFFF) + 0x8000) % 0x10000 - 0x8000)


def _enemy_bearings(game):
    out = []
    for actor in game.state().get("actors") or []:
        if actor.get("cat") == ACTORCAT_ENEMY and (actor.get("health") or 0) > 0 \
                and actor.get("dist_xz", 1e9) <= _AVOID_DIST \
                and abs(actor.get("dist_y", 0.0)) < 200.0:
            out.append((int(actor.get("yaw_to_player", 0)) + 0x8000) & 0xFFFF)
    return out


def _wander_body(game, ctx):
    start = game.pos()
    for leg in range(6):
        threats = _enemy_bearings(game)
        best_yaw, best_score = None, -1.0
        for ray in game.scan(rays=16, length=500):
            yaw = int(ray.get("yaw", 0)) & 0xFFFF
            if any(_yaw_diff(yaw, t) < _AVOID_CONE for t in threats):
                continue
            score = _OPEN if not ray.get("hit") else float(ray.get("dist", 0.0))
            if score > best_score:
                best_yaw, best_score = yaw, score
        if best_yaw is None:      # threats everywhere: stand still this leg
            game.wait(0.5)
            continue
        game.walk_bearing(best_yaw, seconds=1.2)
    game.pad_clear()


def _wander_success(game, initial, events):
    p0 = (initial.get("player") or {}).get("pos")
    p1 = game.pos()
    if not p0 or not p1:
        return False
    return math.hypot(p1[0] - p0[0], p1[2] - p0[2]) >= 100.0


def _wander_body_v2(game, ctx):
    """v2: heading PERSISTENCE. v1 re-picked the most open bearing every
    leg; once in open space the bearing behind you is open too, so it
    pinballed and netted ~0 displacement (first field trial, 2026-08-01).
    Keep the current heading until it is blocked within 200 or vetoed by
    a threat; only then re-pick."""
    heading = None
    for leg in range(8):
        threats = _enemy_bearings(game)
        scored = {}
        for ray in game.scan(rays=16, length=500):
            yaw = int(ray.get("yaw", 0)) & 0xFFFF
            if any(_yaw_diff(yaw, t) < _AVOID_CONE for t in threats):
                continue
            scored[yaw] = _OPEN if not ray.get("hit") else float(ray.get("dist", 0.0))
        if not scored:
            game.wait(0.5)
            continue
        if heading is not None:
            nearest = min(scored, key=lambda y: _yaw_diff(y, heading))
            if _yaw_diff(nearest, heading) <= 0x1000 and scored[nearest] >= 200.0:
                heading = nearest
            else:
                heading = max(scored, key=scored.get)
        else:
            heading = max(scored, key=scored.get)
        game.walk_bearing(heading, seconds=1.2)
    game.pad_clear()


BEHAVIORS = {
    "wander_scan_v1": Behavior(
        name="wander_scan", version=1,
        description="scan a fan, walk the most open bearing, avoid close "
                    "enemies; repeat 6 legs",
        body=_wander_body, success=_wander_success, timeout_s=25.0,
        grade="RETIRED after one field trial: leg 1 success, leg 2 "
              "pinballed to 0 net — open space behind reads as open ahead",
        notes=["2026-08-01 first light: 1/2 legs; oscillation postmortem "
               "-> v2 heading persistence"]),
    "wander_scan_v2": Behavior(
        name="wander_scan", version=2,
        description="v1 + heading persistence: commit to a bearing until "
                    "blocked (<200) or threat-vetoed",
        body=_wander_body_v2, success=_wander_success, timeout_s=25.0,
        grade="untested — field trial pending; success = moved >= 100 units net"),
}
