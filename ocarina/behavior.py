"""Behavior: the 20 Hz leaf of the machine.

The workshop's `Skill` dataclass, renamed (MACHINE.md: "skills" means
Claude Code SKILL.md artifacts only, always). A behavior graded in the
workshop dojo runs here unmodified — that equivalence is the point of the
dojo and this interface must never break it.

A behavior is a plain Python object: metadata + a body function + a
success predicate. Behavior modules are authored by the mind during play,
live in the save-file repo under `machine/behaviors/`, and are loaded by
path (behaviorsource.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Behavior:
    name: str
    version: int
    description: str
    # body(game, ctx) -> None. `ctx` is the state snapshot at entry. Raise
    # BehaviorAbort to bail early. Blocking; never killed — preemption
    # arrives as BehaviorPreempted raised from the next game.* call.
    body: Callable
    # success(game, initial_state, events) -> bool, judged after body returns.
    # `events` is every game event seen during the run. Prefer POSITIVE
    # evidence (an enemy_defeat event, an inventory increase) over absence of
    # the target: an actor that merely left the snapshot — because Link
    # walked out of the room, or the room unloaded — is indistinguishable
    # from a kill if you only ask "is it still there?", so a body that flees
    # scores a perfect record.
    success: Callable
    # Hard wall-clock cap per run.
    timeout_s: float = 15.0
    # Free-form notes from the author (postmortems accumulate here).
    notes: list = field(default_factory=list)
    # One line written for a READER choosing between behaviors: what it
    # achieves, how often, and what it costs. Prose, not numbers-in-a-schema,
    # because what matters differs per behavior — a killer is graded on
    # kills, a collector on what it collects, a dodge on damage.
    grade: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.name}_v{self.version}"


class BehaviorAbort(Exception):
    """Raised inside a behavior body to abort with a reason."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class BehaviorPreempted(Exception):
    """Raised INTO a behavior body — from its next game.* call — when a
    transition leaves its leaf, force_state jumps, or reload_machine swaps.

    Bodies need no changes to be preemptable (MACHINE.md: deterministic
    20 Hz bodies touch the game every tick, so latency is <= 1 tick) and
    should not catch this. The executor journals `behavior_aborted` with
    the preempting transition as the reason.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason
