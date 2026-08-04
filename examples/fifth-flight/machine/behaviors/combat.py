"""Combat behaviors — ported from the dojo corpus for second light.

Provenance: oot-dojo fixtures/dev-run/skills/deku_baba.py, v4 (the
champion killer: 19/20 kills, 50% accuracy, 4.8 swings/trial over n=20
graded arena trials) plus its `_baba_killed` predicate. Body and
constants byte-identical to the graded original; only the import lines
changed (ootdojo -> ocarina, Skill -> Behavior), per the equivalence
rule. Field caveat, per docs/20: the grade was earned in a one-baba
arena — this room has three and walls; a field trial is an observation,
not a grade.
"""

from __future__ import annotations

import time

# Absolute, not relative: behavior modules are loaded by path from the
# save-file repo, so there is no parent package to resolve `..` against.
from ocarina.behavior import Behavior
from ocarina.game import Game
from ocarina.protocol import ACTOR_EN_DEKUBABA, TICK

KILL_CHECK_RANGE = 700.0
Y_STRIKE = 42.0       # hits <= 39.9, misses >= 44.1; split the difference
STRIKE_DIST = 115.0   # a hit landed at 107.9
HOLD_DIST = 150.0     # 142 was damage-free over 6s; 120 was not


def _baba_killed(game: Game, initial: dict, events: list) -> bool:
    """Success = a Deku Baba actually died, proven by a kill event.

    POSTMORTEM (dojo, first real-game session): the original predicate
    was "no babas visible" — a visibility check, not a kill check; a
    body that fled the room scored a perfect record. Require the
    engine's own positive evidence instead.
    """
    for e in events:
        if e.get("type") != "dojo_event":
            continue
        if e.get("event") in ("enemy_defeat", "actor_kill") and e.get("id") == ACTOR_EN_DEKUBABA:
            return True
    return False


def _v4_body(game: Game, initial: dict) -> None:
    deadline = time.monotonic() + 12.0
    while time.monotonic() < deadline:
        target = game.nearest(ACTOR_EN_DEKUBABA)
        if target is None or target["dist_xz"] > KILL_CHECK_RANGE:
            return
        dist = target["dist_xz"]
        head_y = target["pos"][1]

        if head_y <= Y_STRIKE:
            # Vulnerable window is open: close if needed, then cut.
            if dist > STRIKE_DIST:
                game.walk_toward(target, seconds=0.15)
            else:
                game.slash()
                game.wait(3 * TICK)
        else:
            # Reared and dangerous. Do not stand here — back out to the range
            # measured safe, and wait there instead.
            if dist < HOLD_DIST:
                game.walk_away(target, seconds=0.15)
            else:
                game.wait(TICK)


DEKU_BABA_V4 = Behavior(
    name="deku_baba",
    version=4,
    description="Strike on the low-head window; retreat to safe range while it rears.",
    body=_v4_body,
    success=_baba_killed,
    timeout_s=15.0,
    grade="CHAMPION KILLER: 19/20 kills, 50% accuracy, 4.8 swings/trial, "
          "~12s. Bitten in 11/20. Kills the baba and collects Deku "
          "Nuts — it does NOT yield a Deku Stick. Use when the goal "
          "is a dead baba.",
    notes=[
        "Ported to second light 2026-08-01 from the dojo corpus, imports only.",
        "Dojo lineage: v3 proved the pos.y hypothesis (10% -> 30% accuracy) "
        "but loitered at strike range through the reared phase; v4 = v3 + "
        "retreat to HOLD_DIST while reared.",
    ],
)

# ---------------------------------------------------------------------------
# approach_baba v1 — authored live, second light 2026-08-01
# ---------------------------------------------------------------------------
#
# The gap it fills: wander_scan_v2 is an avoider (open-bearing seeking +
# enemy veto) and walked out the front door when sent to find babas;
# deku_baba_v4 only engages within 700. Nothing walked TOWARD an enemy.
# v1 is the naive inverse of the wander's veto: re-acquire nearest baba
# every step, walk straight at it, stop inside v4's engage range. No
# pathfinding — a wall between Link and the baba stalls it, which it
# detects (no progress in 4s) and aborts honestly rather than grinding
# into geometry. UNGRADED: field-flown only, never dojo-trialed.

APPROACH_STOP = 550.0     # inside v4's KILL_CHECK_RANGE (700) with margin
PROGRESS_STEP = 25.0      # closing less than this in 4s counts as stalled


def _approach_body(game: Game, initial: dict) -> None:
    from ocarina.behavior import BehaviorAbort
    deadline = time.monotonic() + 20.0
    best = None
    stall_until = time.monotonic() + 4.0
    while time.monotonic() < deadline:
        target = game.nearest(ACTOR_EN_DEKUBABA)
        if target is None:
            return                      # nothing to approach; judge decides
        dist = target["dist_xz"]
        if dist <= APPROACH_STOP:
            return                      # in engage range; judge confirms
        if best is None or dist < best - PROGRESS_STEP:
            best = dist
            stall_until = time.monotonic() + 4.0
        elif time.monotonic() > stall_until:
            raise BehaviorAbort(f"no approach progress, stalled near {dist:.0f}")
        game.walk_toward(target, seconds=0.25)
        game.wait(TICK)
    raise BehaviorAbort("approach deadline with baba still out of range")


def _in_engage_range(game: Game, initial: dict, events: list) -> bool:
    """Success = a live baba is inside v4's engage range NOW. Positive,
    present-tense evidence — not 'the body returned'."""
    target = game.nearest(ACTOR_EN_DEKUBABA)
    return target is not None and target["dist_xz"] <= 600.0


APPROACH_BABA_V1 = Behavior(
    name="approach_baba",
    version=1,
    description="Walk straight at the nearest deku baba; stop inside engage range.",
    body=_approach_body,
    success=_in_engage_range,
    timeout_s=25.0,
    grade="UNGRADED (field-authored, second light). Naive straight-line "
          "approach: no pathfinding, aborts honestly when stalled by "
          "geometry. Use to hand off to deku_baba_v4; expect failure in "
          "rooms where the baba is around a corner.",
    notes=[
        "Authored live 2026-08-01 to close the seek gap the exit-walking "
        "incident exposed. Send to the dojo before trusting its grade.",
    ],
)

BEHAVIORS = {b.full_name: b for b in (DEKU_BABA_V4, APPROACH_BABA_V1)}
