"""MachineRuntime: the live machine — SURFACE.md's "what ocarina runs".

The repo declares; the server runs; reload() is the only bridge. This
module owns the 20 Hz loop: draining the wire, translating it through the
sensorium, dispatching transitions (innermost-out, first match wins,
cooldowns consumed at match time), sweeping `when` guards on the
false→true edge, running leaf behaviors on the executor, and the wake
cycle (preempt → freeze-confirmed → channel push → resume/deadline).

Freeze machinery is ported from the workshop warden (docs/08 §14: the
pause op's reply cannot be trusted; prove the logic clock stopped).

Machine events recorded here but deliberately NOT dispatched to
transitions: `entered`/`exited`/`wake`/`journal`/`diagnostic` — a
transition on `entered` firing a goto that emits `entered` is an infinite
loop inside one tick. `behavior_done` and `behavior_aborted` ARE
dispatched; that is how loops and completion handling work (MACHINE.md).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import overlay, senses
from .events import EventLog
from .executor import BehaviorExecutor
from .game import Game
from .guards import eval_guard
from .link import LinkError
from .machine import Action, Machine, Transition, load_machine

#: Machine events transitions may match on — senses.py owns the
#: vocabulary; machine.py rejects `on:` names outside it at load.
_DISPATCHED_MACHINE_EVENTS = senses.DISPATCHED_MACHINE_EVENTS


def _from_wire(msg: dict) -> Optional[dict]:
    """Normalize a message drained from GameLink (ported from the
    workshop's bus.from_game): dojo_event passes through; Sail's native
    hook feed flattens so the hook type is the event name."""
    if msg.get("type") == "dojo_event":
        return dict(msg)
    if msg.get("type") == "hook":
        hook = msg.get("hook") or {}
        ev = {k: v for k, v in hook.items() if k != "type"}
        ev["event"] = hook.get("type", "hook_unknown")
        return ev
    return None    # a stray response; counted, not narrated


@dataclass
class _PendingWake:
    """One in-flight wake. The game is frozen for as long as this exists.
    Holds the freeze receipt (`gameplay_frames` at pause): the wake's own
    success and the stopped-time claim are separate assertions, measured
    separately (docs/08 §13)."""
    transition: str
    reason: str
    default: Optional[Action]
    deadline: float
    frames_at_pause: Optional[int]
    paused: bool
    started: float


class MachineRuntime:
    def __init__(self, game: Game, repo: Path | str, log: EventLog,
                 wake_push: Optional[Callable[[dict], None]] = None,
                 tick_s: float = 0.05, wake_deadline_s: float = 300.0,
                 place=None):
        self.game = game
        self.repo = Path(repo)
        self.log = log
        self.wake_push = wake_push
        self.tick_s = tick_s
        self.wake_deadline_s = wake_deadline_s
        #: The place sense (place.PlaceSense) or None. Shared with the
        #: Game so behaviors' traverse() validates against the same map
        #: the digest localizes on — two maps would be two beliefs.
        self.place = place
        if place is not None:
            game.place = place

        self.machine: Optional[Machine] = None
        self.diagnostics: list = []
        self.current: Optional[str] = None      # always a leaf when set
        self.directive: Optional[str] = None
        self.heartbeat_s: Optional[float] = None  # resume(max_sleep) stores it;
                                                  # the heartbeat wake itself is
                                                  # machine content (navi ships it)
        self.executor = BehaviorExecutor(game)
        self.seen = senses.SeenKinds(self.repo / ".ocarina" / "seen_kinds.json")
        self.sightings = senses.Sightings()
        self._sight_warned = False
        self._truncation_warned_scene = object()   # sentinel: no scene judged yet
        # The dialogue fold's state (docs/27): open/closed edge, the last
        # box narrated (so 20 Hz doesn't re-narrate a standing box), the
        # recent-texts ring oot://dialogue serves, and the once-only
        # old-instrument / wide-text diagnostics.
        self._dialogue_open_prev = False
        self._dialogue_last_key = None
        self._dialogue_recent: list = []
        self._dialogue_blind_warned = False
        self._dialogue_wide_warned = False

        self._lock = threading.RLock()
        self._cooldowns: dict = {}      # transition name -> monotonic last-match
        self._edges: dict = {}          # when-transition name -> last value
        self._warned: set = set()       # (transition, warning) journaled once
        self._wake: Optional[_PendingWake] = None
        self._pending_start = False     # start current leaf's behavior when free
        self._last_state: Optional[dict] = None
        self._last_state_at = 0.0
        self.overlay_enabled = True     # human debug labels; see overlay.py
        self._overlay_last: Optional[list] = None
        self._overlay_pushed_at = 0.0
        self._was_connected = False
        self._stopping = False
        self.wakes = 0
        self.freeze_failures = 0
        self.dropped_wire = 0           # wire messages the sensorium dropped
        game.state_observer = self._observe_state

    # -- observation ---------------------------------------------------------

    def _observe_state(self, st: dict) -> None:
        # Called from whichever thread ran game.state() — behaviors at
        # 20 Hz, or our own sweep. Assignment is atomic; readers copy.
        self._last_state = st
        self._last_state_at = time.monotonic()

    def _frames(self) -> Optional[int]:
        st = self._last_state
        return st.get("gameplay_frames") if st else None

    def _digest(self) -> dict:
        st = self._last_state or {}
        sample = self.place.sample(st) if self.place is not None else None
        return senses.digest(st, self.sightings, sample)

    # -- loading (the reload_machine bridge) ---------------------------------

    def load(self) -> list:
        """Initial load + first entry. Returns diagnostics as dicts."""
        with self._lock:
            machine, diags = load_machine(self.repo)
            self.diagnostics = diags
            if machine is not None:
                self.machine = machine
                self._record({"event": "diagnostic",
                              "text": f"machine loaded ({machine.source_hash})"})
                self._enter(machine.initial, reason="initial")
            return [d.as_dict() for d in diags]

    def reload(self) -> dict:
        """Validate + hot-swap (MACHINE.md semantics): on failure the old
        machine keeps running untouched; on success the running behavior is
        preempted, and the current node carries over BY NAME if it still
        exists, else the machine drops to initial — either way, journaled."""
        with self._lock:
            machine, diags = load_machine(self.repo)
            result = {"ok": machine is not None,
                      "diagnostics": [d.as_dict() for d in diags]}
            if machine is None:
                self._record({"event": "diagnostic",
                              "text": f"reload_machine REFUSED "
                                      f"({sum(1 for d in diags if d.level == 'error')} "
                                      f"errors); old machine untouched"})
                return result

            self.diagnostics = diags
            old_current = self.current
            self.executor.preempt("machine reloaded")
            self.machine = machine
            self._cooldowns.clear()
            self._edges.clear()
            self._warned.clear()
            if old_current is not None and old_current in machine.nodes:
                self.current = None    # re-enter cleanly below
                self._enter(old_current, reason="reload (node carried by name)")
            else:
                self.current = None
                self._enter(machine.initial,
                            reason=f"reload ({old_current!r} gone; dropped to initial)")
            result["hash"] = machine.source_hash
            result["current"] = self.current
            return result

    # -- the loop ------------------------------------------------------------

    def run(self) -> None:
        while not self._stopping:
            self.tick()
            time.sleep(self.tick_s)

    def stop(self) -> None:
        self._stopping = True
        with self._lock:
            if self._wake is not None:
                self._record({"event": "diagnostic",
                              "text": "runtime stopping with a wake in flight — unfreezing"})
                self._unfreeze(self._wake)
                self._wake = None
            self.executor.preempt("runtime stopping")

    def tick(self, now: Optional[float] = None) -> None:
        if now is None:
            now = time.monotonic()
        with self._lock:
            self._tick_connection()
            self._drain_wire()
            self._fold_sightings()
            self._fold_place()
            self._fold_dialogue()
            self._finish_behavior()
            self._push_overlay(now)
            if self._wake is not None:
                self._service_wake(now)
                return
            if self.machine is None or self.current is None:
                return
            if self.game.link.connected:
                self._sweep_when(now)
                self._maybe_start_behavior()

    def _push_overlay(self, now: float) -> None:
        """Keep the game's debug labels current with the sensorium's
        beliefs. Runs above the wake gate deliberately: a frozen world
        with the mind thinking is exactly when AJ leans in to inspect
        what ocarina believes, and the game-side store drops labels 3s
        after the last push, so the keepalive must keep flowing.

        Push on change (rate-capped) or as a 1 s keepalive. Never raises:
        the overlay is a passenger, and a display glitch must not touch
        the 20 Hz loop.
        """
        if not self.overlay_enabled or not self.game.link.connected:
            self._overlay_last = None
            return
        if self._last_state is None:
            return
        labels = overlay.labels(self._last_state, self.seen, self.sightings)
        age = now - self._overlay_pushed_at
        if age < 0.2 or (labels == self._overlay_last and age < 1.0):
            return
        try:
            self.game.overlay_push(labels)
            # The boundary rides with every push: what the labels do NOT
            # cover is as much a debug fact as what they do (overlay.py).
            # Best-effort and separate — a HUD failure must never cost the
            # labels, which are the primary instrument.
            try:
                self.game.hud_push(panels={"dojo": overlay.boundary(
                    self._last_state, len(labels))})
            except LinkError:
                pass
        except LinkError:
            return
        self._overlay_last = labels
        self._overlay_pushed_at = now

    def _tick_connection(self) -> None:
        connected = self.game.link.connected
        if connected == self._was_connected:
            return
        self._was_connected = connected
        self._record({"event": "diagnostic",
                      "text": "game connected" if connected else "game disconnected"})
        if connected:
            try:
                self.game.events_on(frame_interval=0)   # real events only
            except LinkError:
                pass

    def _drain_wire(self) -> None:
        # Pre-play (attract demo, title screen): the world hasn't started,
        # so world events don't narrate (AJ, 2026-08-02). load_game is the
        # boundary itself and always passes. Suppression needs a snapshot
        # SAYING save_loaded is false — no snapshot yet is "unknown", and
        # censoring on unknown would eat real events in the connect window.
        st = self._last_state
        save_loaded = st.get("save_loaded", True) if st else True
        for msg in self.game.link.drain_events():
            ev = _from_wire(msg)
            if ev is None:
                self.dropped_wire += 1
                continue
            curated = senses.translate(ev)
            if curated is None:
                if ev.get("event") != "frame":
                    self.dropped_wire += 1
                continue
            if not save_loaded and ev.get("event") != "load_game":
                self.dropped_wire += 1
                continue
            self._record(curated)
            if self.executor.collecting:
                # Success predicates were written against the raw wire
                # shape in the workshop; feed them the raw event.
                self.executor.note_event(ev)
            self._dispatch(curated)

    def _fold_sightings(self) -> None:
        """Census-driven spawn narration (docs/22): fold the freshest
        snapshot into the sighted set and narrate first sightings.
        Idempotent per actor key, so re-reading an unchanged snapshot
        narrates nothing."""
        st = self._last_state
        if st is None:
            return
        if (senses.census_carries_sight(st) is False
                and st.get("save_loaded") and not self._sight_warned):
            self._sight_warned = True
            self._record({"event": "diagnostic",
                          "text": "census carries no `sighted` bits — this "
                                  "instrument predates sight-gating (rebuild SoH "
                                  "with the current dojo patch); world senses are "
                                  "BLIND, deliberately, rather than X-ray"})
        # A truncated census means the world senses are working from a
        # partial world — say so, per scene, with the numbers. Per scene
        # rather than once per session because each room is its own
        # judgment: a cap that never bit in a corridor can bite hard in a
        # crowded hall, and one early warning must not buy silence for
        # the rest of the session.
        truncated = senses.census_truncated(st)
        if truncated is not None and st.get("scene") != self._truncation_warned_scene:
            self._truncation_warned_scene = st.get("scene")
            sent, total = truncated
            self._record({"event": "diagnostic",
                          "text": f"census TRUNCATED: {sent} of {total} actors "
                                  f"on the wire (farthest sent "
                                  f"{max((a.get('dist_xz', 0.0) for a in st.get('actors') or []), default=0.0):.0f}) "
                                  f"— the world senses are judging a partial "
                                  f"world, and anything beyond that radius "
                                  f"cannot be sighted, counted or narrated"})
        for ev in senses.spawn_events(self.sightings.observe(st), self.seen):
            self._record(ev)
            self._dispatch(ev)

    def _fold_place(self) -> None:
        """The place sense's narration (docs/25): region_entered on
        non-sliver region change, fell on an unplanned downward one —
        plus its diagnostics (distillation stats, missing maps, unlinked
        columns) into the journal, where an instrument gap belongs."""
        if self.place is None:
            return
        st = self._last_state
        if st is not None:
            for ev in self.place.fold(st):
                self._record(ev)
                self._dispatch(ev)
        for text in self.place.drain_diagnostics():
            self._record({"event": "diagnostic", "text": text})

    def _fold_dialogue(self) -> None:
        """The dialogue sense's narration (docs/27): a `ui` cue per box —
        `dialogue_opened` with the text once it is readable (the wire
        sends text null while the box is still opening), `dialogue_closed`
        on close — plus the recent-texts ring oot://dialogue serves. The
        `ui` category has existed in the grammar since it was written;
        these are its first producers. Every box lands in the ring even
        when a body advances it blind — that is how the Dungeon Map
        mislabel (two flights of blind get-item boxes) becomes
        impossible to repeat."""
        st = self._last_state
        if st is None or not st.get("save_loaded", False):
            return
        box_open = st.get("msg_mode", 0) != 0
        msg = st.get("message")
        if box_open and msg is None:
            # An open box with no message block: the instrument predates
            # the dialogue sense. Blind with a diagnostic, never silent.
            if not self._dialogue_blind_warned:
                self._dialogue_blind_warned = True
                self._record({"event": "diagnostic",
                              "text": "a message box is open but the wire "
                                      "carries no `message` block — this "
                                      "instrument predates the dialogue sense "
                                      "(rebuild SoH with the 2026-08-04 dojo "
                                      "patch); dialogue is BLIND, deliberately, "
                                      "rather than silent"})
            self._dialogue_open_prev = box_open
            return
        if box_open and msg is not None:
            if msg.get("wide") and not self._dialogue_wide_warned:
                self._dialogue_wide_warned = True
                self._record({"event": "diagnostic",
                              "text": "wide-text (JPN) message boxes cannot be "
                                      "decoded — dialogue text absent for this "
                                      "language, flagged not faked"})
            if msg.get("text") is not None:
                key = (msg.get("text_id"), msg.get("text"))
                if key != self._dialogue_last_key:
                    self._dialogue_last_key = key
                    entry = {"text_id": msg.get("text_id"),
                             "text": msg.get("text"),
                             "scene": st.get("scene")}
                    ev = {"event": "ui", "cue": "dialogue_opened",
                          "text": msg.get("text")}
                    if "choices" in msg:
                        entry["choices"] = msg.get("choices")
                        ev["choices"] = msg.get("choices")
                    self._dialogue_recent.append(entry)
                    del self._dialogue_recent[:-20]
                    self._record(ev)
                    self._dispatch(ev)
        if not box_open and self._dialogue_open_prev:
            self._dialogue_last_key = None
            ev = {"event": "ui", "cue": "dialogue_closed"}
            self._record(ev)
            self._dispatch(ev)
        self._dialogue_open_prev = box_open

    def dialogue_recent(self) -> list:
        """The recent-texts ring (newest last) for oot://dialogue."""
        with self._lock:
            return [dict(e) for e in self._dialogue_recent]

    def _finish_behavior(self) -> None:
        run = self.executor.finish()
        if run is None:
            return
        if run.preempted_by is not None:
            self._record({"event": "behavior_aborted", "behavior": run.behavior,
                          "reason": run.preempted_by,
                          "duration_s": round(run.duration_s, 1)})
            self._dispatch({"event": "behavior_aborted", "behavior": run.behavior,
                            "reason": run.preempted_by})
            return
        ev = {"event": "behavior_done", "behavior": run.behavior,
              "outcome": run.outcome, "duration_s": round(run.duration_s, 1),
              "detail": run.detail}
        self._record(ev)
        self._dispatch(ev)

    # -- dispatch (MACHINE.md semantics) --------------------------------------

    def _scope(self) -> list:
        if self.machine is None or self.current is None:
            return []
        return self.machine.scope(self.current)

    def _dispatch(self, event: dict, now: Optional[float] = None) -> None:
        """Innermost-out, first match wins, cooldowns consumed at match."""
        name = event.get("event")
        if name in senses.MACHINE_EVENTS and name not in _DISPATCHED_MACHINE_EVENTS:
            return
        if now is None:
            now = time.monotonic()
        for t in self._scope():
            if t.kind != "event" or t.on != name:
                continue
            if self._cooling(t, now):
                continue
            if t.guard is not None:
                fields = {k: v for k, v in event.items()
                          if k not in ("event", "seq", "t", "wall")}
                ok, warn = self._eval(t, fields)
                if warn or not ok:
                    continue
            self._cooldowns[t.name] = now
            self._fire(t, event)
            return

    def _sweep_when(self, now: float) -> None:
        """The 20 Hz `when` sweep: false→true edges only; prior value is
        false on scope entry (a condition already true on arrival fires
        immediately). Natural hysteresis: no refire until false again."""
        # Polling bodies keep _last_state fresh at 20 Hz; a body that is
        # merely waiting out an animation does not, and a sweep reading a
        # stale snapshot is a reflex layer watching a photograph. Poll
        # whenever the snapshot is older than a couple of ticks (Game's hit
        # counter is locked against the concurrent observation).
        if not self.executor.collecting or now - self._last_state_at > 0.1:
            try:
                self.game.state()       # observer refreshes _last_state
            except LinkError:
                return
        digest = self._digest()

        fired_transition = None
        for t in self._scope():
            if t.kind != "state":
                continue
            ok, warn = self._eval(t, {}, digest)
            prev = self._edges.get(t.name, False)
            self._edges[t.name] = ok
            if warn or not ok or prev:
                continue
            if self._cooling(t, now):
                continue
            if fired_transition is None:      # first match wins per sweep,
                fired_transition = t          # but every edge still updates
        if fired_transition is not None:
            self._cooldowns[fired_transition.name] = now
            self._fire(fired_transition, {"event": "when", "when": fired_transition.guard.src})

    def _cooling(self, t: Transition, now: float) -> bool:
        last = self._cooldowns.get(t.name)
        return last is not None and (now - last) < t.cooldown_s

    def _eval(self, t: Transition, fields: dict, digest: Optional[dict] = None):
        if digest is None:
            digest = self._digest()
        ok, warn = eval_guard(t.guard, fields, digest)
        if warn and (t.name, warn) not in self._warned:
            # Once per (transition, warning): a typo'd field must show up
            # in the journal instead of producing a transition that looks
            # armed and never fires (ported rules.py behavior).
            self._warned.add((t.name, warn))
            self._record({"event": "diagnostic",
                          "text": f"transition {t.name!r}: {warn} — no match"})
        return ok, warn

    def _fire(self, t: Transition, event: dict) -> None:
        for action in t.do:
            self._act(t, action, event)

    def _act(self, t: Transition, action: Action, event: dict) -> None:
        if action.verb == "journal":
            self._record({"event": "journal", "transition": t.name,
                          "text": _template(action.arg, event)})
        elif action.verb == "hold":
            self._record({"event": "journal", "transition": t.name,
                          "text": f"hold: {_template(action.arg, event)}"})
        elif action.verb == "goto":
            self._enter(action.arg, reason=f"transition {t.name}")
        elif action.verb == "wake":
            self._begin_wake(t, _template(action.arg, event), event)

    # -- node entry ------------------------------------------------------------

    def _enter(self, target: str, reason: str) -> None:
        """Enter a node (interior: descends via initial chains to a leaf),
        emitting exited/entered machine events and preempting a running
        behavior at the boundary."""
        machine = self.machine
        old_chain = []
        if self.current is not None:
            old_chain = machine.ancestors(self.current)[::-1] + [self.current]
        new_chain = machine.ancestors(target)[::-1] + machine.descend(target)

        if self.executor.collecting:
            self.executor.preempt(reason)

        for name in reversed([n for n in old_chain if n not in new_chain]):
            self._record({"event": "exited", "node": name})
        for name in [n for n in new_chain if n not in old_chain]:
            self._record({"event": "entered", "node": name, "reason": reason})
        # Re-entering the current leaf is an explicit loop (MACHINE.md):
        # same chain, but the behavior restarts.
        if old_chain and old_chain == new_chain:
            self._record({"event": "entered", "node": new_chain[-1],
                          "reason": f"{reason} (loop)"})

        self.current = new_chain[-1]
        self._pending_start = True
        # Prior value is taken as false on scope entry: drop edge state for
        # transitions no longer (or newly) in scope.
        in_scope = {t.name for t in self._scope() if t.kind == "state"}
        for name in list(self._edges):
            if name not in in_scope:
                del self._edges[name]

    def _maybe_start_behavior(self) -> None:
        if not self._pending_start or self.executor.collecting:
            return
        machine, current = self.machine, self.current
        behavior = machine.behaviors.get(machine.nodes[current].behavior)
        if behavior is None:      # validated at load; belt and braces
            return
        if self.executor.start(behavior):
            self._pending_start = False

    # -- the wake cycle --------------------------------------------------------

    def _begin_wake(self, t: Transition, reason: str, event: dict) -> None:
        if self._wake is not None:
            self._record({"event": "diagnostic",
                          "text": f"[{t.name}] wake skipped — "
                                  f"{self._wake.transition} is already awake"})
            return
        self.wakes += 1
        # Preempt first: a body left running against a frozen world burns
        # its wall clock into a timeout it didn't earn.
        self.executor.preempt(f"wake {t.name}")
        frames, paused = self._freeze()
        pack = {
            "reason": reason,
            "transition": t.name,
            "node": self.current,
            "directive": self.directive,
            "state": self._digest(),
            "events": self.log.tail(15),
            "trigger": {k: v for k, v in event.items() if k not in ("seq", "wall")},
            "frozen": paused,
        }
        self._wake = _PendingWake(
            transition=t.name, reason=reason, default=t.default,
            deadline=time.monotonic() + self.wake_deadline_s,
            frames_at_pause=frames, paused=paused, started=time.monotonic())
        self._record({"event": "wake", "transition": t.name, "reason": reason,
                      "frozen": paused})
        if self.wake_push is not None:
            try:
                self.wake_push(pack)
            except Exception as e:
                self._record({"event": "diagnostic",
                              "text": f"wake push failed: {type(e).__name__}: {e}"})

    def _service_wake(self, now: float) -> None:
        wake = self._wake
        if now < wake.deadline:
            return
        # No usable answer arrived: the transition's declared non-wake
        # default is what we do (MACHINE.md's ported rule).
        default = wake.default or Action("hold", "no default")
        self._record({"event": "diagnostic",
                      "text": f"wake [{wake.transition}] deadline "
                              f"({self.wake_deadline_s:.0f}s) — taking default: "
                              f"{default.verb} {default.arg}"})
        self._wake = None
        self._unfreeze(wake)
        if default.verb == "goto":
            self._enter(default.arg, reason=f"wake default ({wake.transition})")
        else:
            self._record({"event": "journal", "transition": wake.transition,
                          "text": f"{default.verb}: {default.arg}"})
        self._pending_start = True

    def resume(self, max_sleep: Optional[float] = None) -> dict:
        """The resume() tool: unfreeze, back to autopilot."""
        with self._lock:
            if max_sleep is not None:
                self.heartbeat_s = float(max_sleep)
            if self._wake is None:
                return {"ok": True, "note": "nothing was frozen; autopilot already running"}
            wake = self._wake
            self._wake = None
            self._unfreeze(wake)
            self._record({"event": "diagnostic",
                          "text": f"resume after wake [{wake.transition}] "
                                  f"({time.monotonic() - wake.started:.1f}s frozen)"})
            self._pending_start = True
            return {"ok": True, "resumed_from": wake.transition,
                    "current": self.current}

    # -- verbs from the surface ------------------------------------------------

    def force_state(self, node: str) -> dict:
        with self._lock:
            if self.machine is None:
                return {"ok": False, "error": "no machine loaded"}
            if node not in self.machine.nodes:
                known = ", ".join(sorted(self.machine.nodes))
                return {"ok": False, "error": f"unknown node {node!r} (known: {known})"}
            self._enter(node, reason="force_state")
            return {"ok": True, "current": self.current}

    def set_directive(self, text: str) -> dict:
        with self._lock:
            self.directive = text
            self._record({"event": "directive", "text": text})
            return {"ok": True}

    def escalate(self, reason: str) -> dict:
        with self._lock:
            self._record({"event": "escalation", "reason": reason})
            if self.wake_push is not None:
                try:
                    self.wake_push({"escalation": reason, "node": self.current,
                                    "state": self._digest()})
                except Exception:
                    pass
            return {"ok": True, "note": "journaled; escalation reaches the "
                                        "human via the session transcript for now"}

    # -- stopped time (ported from the workshop warden, docs/08 §14) -----------

    def _freeze(self):
        if not self.game.link.connected:
            return None, False
        try:
            frames, attempts = self._freeze_confirmed()
        except LinkError as e:
            self._record({"event": "diagnostic",
                          "text": f"could not freeze for wake: {e}"})
            return None, False
        if frames is None:
            self.freeze_failures += 1
            self._record({"event": "diagnostic",
                          "text": f"freeze did NOT engage after {attempts} attempts — "
                                  f"the mind will think at wall clock and the world "
                                  f"will move under it"})
            return None, True    # still 'paused' as far as unfreeze is concerned
        if attempts > 1:
            self._record({"event": "diagnostic",
                          "text": f"freeze took {attempts} attempts"})
        return frames, True

    def _freeze_confirmed(self, attempts: int = 6):
        """Pause, and prove it by watching the LOGIC clock stop. The op's
        reply cannot be trusted (Sail answers success for ops that do
        nothing); measure `gameplay_frames`, never `frame`."""
        for attempt in range(1, attempts + 1):
            self.game.pause(True)
            first = self.game.state().get("gameplay_frames")
            time.sleep(0.15)
            settled = self.game.state()
            frames = settled.get("gameplay_frames")
            if first is None or frames is None:
                return frames, attempt
            if frames == first and settled.get("paused"):
                return frames, attempt
            time.sleep(0.25)
        return None, attempts

    def _unfreeze(self, wake: _PendingWake) -> None:
        """Unpause, and separately check whether the freeze actually held —
        the stopped-time claim and the wake's own outcome are different
        assertions and get different journal lines (docs/08 §13)."""
        if not wake.paused:
            return
        try:
            frames_now = self.game.state().get("gameplay_frames")
            self.game.pause(False)
        except LinkError as e:
            self._record({"event": "diagnostic",
                          "text": f"could not unfreeze after wake: {e} — "
                                  f"the game may be left frozen"})
            return
        if wake.frames_at_pause is None or frames_now is None:
            return
        drift = frames_now - wake.frames_at_pause
        if drift:
            self.freeze_failures += 1
            elapsed = time.monotonic() - wake.started
            self._record({"event": "diagnostic",
                          "text": f"stopped-time claim FAILED: gameplay_frames "
                                  f"advanced {drift} during a {elapsed:.1f}s wake "
                                  f"— cognition was not free"})

    # -- views -----------------------------------------------------------------

    def _record(self, event: dict) -> None:
        self.log.record(event, frames=self._frames())

    def status(self) -> dict:
        with self._lock:
            errors = sum(1 for d in self.diagnostics if d.level == "error")
            warnings = sum(1 for d in self.diagnostics if d.level == "warning")
            return {
                "game_connected": self.game.link.connected,
                "machine_loaded": self.machine is not None,
                "machine_hash": self.machine.source_hash if self.machine else None,
                "machine_diagnostics": {"errors": errors, "warnings": warnings},
                "current_node": self.current,
                "behavior_running": self.executor.active_behavior,
                "directive": self.directive,
                "frozen": self._wake is not None,
                "pending_wake": self._wake.transition if self._wake else None,
                "wakes": self.wakes,
                "freeze_failures": self.freeze_failures,
                "heartbeat_s": self.heartbeat_s,
                "place_sense": (self.place.status_line(self._last_state)
                                if self.place is not None else "not constructed"),
            }

    def place_view(self) -> dict:
        """oot://place — the scene graph as judgments over stable names.
        Refreshes the snapshot first when connected so `you_are_here`
        is current, not a photograph."""
        if self.place is None:
            return {"error": "place sense not constructed"}
        if self.game.link.connected:
            try:
                self.game.state()      # observer refreshes _last_state
            except LinkError:
                pass
        return self.place.document(self._last_state)

    def guard_edges(self) -> dict:
        """Brainviz read (one-way, debug): the current truth value of
        every in-scope `when` guard — the _sweep_when edge state. This is
        the armed-reflex display: a guard sitting True is holding its
        hysteresis, a guard flipping False→True is about to fire."""
        with self._lock:
            return dict(self._edges)

    def machine_view(self) -> dict:
        """oot://machine — declared vs LIVE as two columns (the conjunction
        discipline: 'repo says armed' != 'server confirms armed')."""
        with self._lock:
            declared_machine, declared_diags = load_machine(self.repo)
            declared = {
                "valid": declared_machine is not None,
                "hash": declared_machine.source_hash if declared_machine else None,
                "diagnostics": [d.as_dict() for d in declared_diags],
            }
            live = {
                "loaded": self.machine is not None,
                "hash": self.machine.source_hash if self.machine else None,
                "current": self.current,
                "behavior_running": self.executor.active_behavior,
                "nodes": self._node_tree() if self.machine else None,
            }
            declared["in_sync"] = bool(
                declared["hash"] and declared["hash"] == live["hash"])
            return {"declared": declared, "live": live}

    def _node_tree(self) -> dict:
        def render(name: str) -> dict:
            node = self.machine.nodes[name]
            out = {"transitions": [t.name for t in node.transitions]}
            if node.is_leaf:
                out["behavior"] = node.behavior
            else:
                out["initial"] = node.initial
                out["children"] = {c: render(c) for c in node.children}
            return out
        top = [n for n, node in self.machine.nodes.items() if node.parent is None]
        return {"initial": self.machine.initial,
                "root_transitions": [t.name for t in self.machine.root_transitions],
                "nodes": {n: render(n) for n in top}}


class _MissingField:
    """Absent fields render as the literal {name} whatever the format spec,
    so a typo is visible in the journal instead of crashing the action."""

    def __init__(self, key: str):
        self.key = key

    def __format__(self, spec: str) -> str:
        return "{" + self.key + "}"


def _template(template: str, event: dict) -> str:
    class _Fields(dict):
        def __missing__(self, key):
            return _MissingField(key)
    try:
        return template.format_map(_Fields(event))
    except ValueError as e:
        return f"{template} (template error: {e})"
