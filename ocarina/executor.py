"""BehaviorExecutor: runs one behavior body at a time on its own thread.

Ported from the workshop's SkillExecutor (outcome judging, thread
discipline, the finish()-after-thread-exit rule) plus the ONE deliberate
extension MACHINE.md blesses: **preemption at game-op boundaries**. The
workshop executor's docstring called interruptible bodies "a future
skill-API concern" — it bit, and this is the answer.

Bodies are blocking and are never killed. preempt() sets a flag; the
body's next `game.*` call raises BehaviorPreempted. Deterministic 20 Hz
bodies touch the game every tick, so preemption latency is <= 1 tick and
bodies need no changes. `game.wait()` is additionally chunked so a body
sleeping out a long animation notices within a tick too.

Outcome semantics mirror the dojo deliberately (timeout after the fact,
success predicate over collected events, death/damage from health): a
behavior graded in the workshop runs here unmodified.
"""

from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Optional

from .behavior import Behavior, BehaviorAbort, BehaviorPreempted
from .game import Game
from .link import LinkError
from .protocol import TICK

#: Everything behavior_done can say (MACHINE.md; vocabulary-not-grammar
#: says details ride in `detail`, not in new outcomes).
OUTCOMES = ("success", "failure", "damage", "death", "timeout", "abort", "error")


@dataclass
class BehaviorRun:
    behavior: str
    outcome: str          # one of OUTCOMES, or "preempted"
    duration_s: float
    health_start: int
    health_end: int
    detail: str = ""
    swings: int = 0
    hits: int = 0
    events: list = field(default_factory=list)
    #: Set when the run ended by preemption: the transition (or verb) that
    #: left the leaf. The runtime emits behavior_aborted, not behavior_done.
    preempted_by: Optional[str] = None


class _PreemptableGame:
    """The Game handed to bodies: same API, but every call first checks the
    preemption flag. Non-callable attributes pass through untouched."""

    def __init__(self, game: Game, flag: threading.Event, reason: list):
        self._game = game
        self._flag = flag
        self._reason = reason      # single-element list; executor fills it

    def _check(self) -> None:
        if self._flag.is_set():
            raise BehaviorPreempted(self._reason[0] if self._reason else "preempted")

    def wait(self, seconds: float) -> None:
        # Chunked so a sleeping body notices preemption within a tick.
        deadline = time.monotonic() + seconds
        while True:
            self._check()
            left = deadline - time.monotonic()
            if left <= 0:
                return
            time.sleep(min(TICK, left))

    def __getattr__(self, name):
        attr = getattr(self._game, name)
        if not callable(attr):
            return attr

        def guarded(*args, **kwargs):
            self._check()
            return attr(*args, **kwargs)
        return guarded


class BehaviorExecutor:
    def __init__(self, game: Game):
        self.game = game
        self._thread: Optional[threading.Thread] = None
        self._behavior: Optional[Behavior] = None
        self._initial: Optional[dict] = None
        self._started_at: float = 0.0
        self._body_error: Optional[tuple] = None    # (outcome, detail)
        self._preempt_flag = threading.Event()
        self._preempt_reason: list = []
        self.events: list = []    # events observed while this behavior runs

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def collecting(self) -> bool:
        """True from start() until finish() returns the run. Wider than
        `busy`: events that arrive between the body exiting and the
        outcome being judged still belong to this behavior."""
        return self._behavior is not None

    @property
    def active_behavior(self) -> Optional[str]:
        return self._behavior.full_name if self._behavior else None

    def start(self, behavior: Behavior) -> bool:
        """Take ownership and launch the body. False if already busy."""
        if self.busy or self._behavior is not None:
            return False
        game = self.game
        try:
            game.pad_clear()
            game.reset_instruments()
            self._initial = game.state()
        except LinkError:
            return False
        self._behavior = behavior
        self._body_error = None
        self.events = []
        self._preempt_flag.clear()
        self._preempt_reason = []
        # Long composites (traverse) poll these so preemption lands
        # mid-op — the wrapper below only checks at call boundaries.
        game._preempt_event = self._preempt_flag
        game._preempt_reason = self._preempt_reason
        self._started_at = time.monotonic()
        wrapped = _PreemptableGame(game, self._preempt_flag, self._preempt_reason)
        self._thread = threading.Thread(
            target=self._run_body, args=(wrapped,), daemon=True,
            name=f"behavior:{behavior.full_name}")
        self._thread.start()
        return True

    def preempt(self, reason: str) -> bool:
        """Flag the running body; its next game.* call raises. True if there
        was a body to preempt."""
        if not self.collecting:
            return False
        self._preempt_reason.append(reason)
        self._preempt_flag.set()
        return True

    def _run_body(self, wrapped) -> None:
        try:
            self._behavior.body(wrapped, self._initial)
        except BehaviorPreempted as e:
            self._body_error = ("preempted", e.reason)
        except BehaviorAbort as e:
            self._body_error = ("abort", e.reason)
        except LinkError as e:
            self._body_error = ("error", f"link lost mid-behavior: {e}")
        except Exception:
            self._body_error = ("error", traceback.format_exc(limit=3))
        finally:
            try:
                self.game.pad_clear()
            except LinkError:
                pass

    def note_event(self, event: dict) -> None:
        """The runtime feeds events here while collecting; success
        predicates read them."""
        self.events.append(event)

    def finish(self) -> Optional[BehaviorRun]:
        """Judge and return the run once the body thread has exited; None
        while still running (or idle). Judging calls game.state(), which
        must not race a still-running body — hence the thread-exit gate."""
        if self._behavior is None or self.busy:
            return None
        behavior, initial = self._behavior, self._initial
        duration = time.monotonic() - self._started_at
        game = self.game

        outcome, detail = "failure", ""
        preempted_by = None
        if self._body_error is not None:
            outcome, detail = self._body_error
            if outcome == "preempted":
                preempted_by, detail = detail, f"preempted by {detail}"
        health_start = initial.get("health", 0)
        health_end = health_start
        try:
            final = game.state()
            health_end = final.get("health", health_start)
            if outcome == "failure":
                if duration > behavior.timeout_s:
                    outcome, detail = "timeout", \
                        f"body ran {duration:.1f}s > cap {behavior.timeout_s}s"
                elif behavior.success(game, initial, list(self.events)):
                    outcome = "success"
            if outcome not in ("success", "preempted"):
                if game.is_dead():
                    outcome = "death"
                elif health_end < health_start and outcome == "failure":
                    outcome = "damage"
            elif health_end < health_start:
                detail = (detail + " " if detail else "") + \
                    f"took {health_start - health_end} damage"
        except LinkError as e:
            outcome, detail = "error", f"link lost judging outcome: {e}"

        run = BehaviorRun(behavior=behavior.full_name, outcome=outcome,
                          duration_s=duration, health_start=health_start,
                          health_end=health_end, detail=detail,
                          swings=game.swings, hits=game.hits,
                          events=list(self.events), preempted_by=preempted_by)
        self._behavior = self._initial = self._thread = None
        self.events = []
        return run
