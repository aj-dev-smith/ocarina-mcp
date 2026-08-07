"""The dev harness: cheats behind `--dev-tools` (0.12.0, dojo docs/33).

Flights should be acceptance, not discovery. Ten of them found bugs the
322-test suite could not, because the missing rung of the pyramid is
"repeatable verification against the REAL game at a chosen world state" —
and the only way to reach a chosen world state was to play Link there,
with AJ on the camera. This module is that rung: warp to the maze,
teleport to the corridor mouth, assert, repeat, in minutes.

AJ ratified the direction and the SURFACE.md rule amendment the same
evening (docs/33). What keeps the amendment honest is three structural
commitments, and this module implements the first two:

1. **Cheats are for the harness developer, never for the player.** The
   `dev_*` verbs live HERE, at the server/MCP layer, held by the server
   only when the flag is on. `game.py` grows nothing — no behavior can
   call them, no guard can see them, no machine source can name them,
   and MACHINE.md is untouched. That is why this module talks to
   `game.link` directly for the two dev ops instead of asking Game for
   a method: the wire is not the contract behaviors are written
   against, and Game is.

   (Reads are a different matter: `game.state()` is the ordinary play
   surface, and using it keeps census normalization and the runtime's
   state observer fed — a dev read that bypassed them would give this
   module a private, second belief about the world.)

2. **Dev use is structurally un-hideable.** `banner_event()` is
   journaled on every boot and every attach under the flag; the server
   journals `{"event": "dev_cheat", "tool": ..., "args": ...}` BEFORE
   dispatching any dev verb, so even a call that fails leaves its mark;
   `status()` reports `dev_mode`. The journal is the flight record, so
   a repo that ever ran under the flag carries it in its fossil
   permanently, and an audit is one grep.

3. **Scored repos refuse the flag** — `scored_refusal()`, called by
   main() before any connection is made.

Deliberately absent, permanently: savestates. The amendment does not
reopen that door in any mode (SURFACE.md, Benchmark purity).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from .identity import IDENTITY_FILENAME, load_identity
from .link import LinkError

#: The AgentLink patch that adds the `teleport` and `warp` ops. An
#: instrument built before it answers "unknown agent op", which is
#: surfaced by name (the 0.6.0 pattern: never silently obeyed).
DEV_PATCH = "2026-08-07"

#: The follow-up patch, from the first live pass the same evening (the
#: two seams that pass found): the state payload carries `loads` (a
#: play-state-init counter — a SAME-scene reload increments it, which a
#: scene comparison cannot see) and `room`, and `teleport` takes an
#: optional `room` that performs a real room change first. An instrument
#: without them still works, in a diminished way that says so out loud
#: rather than quietly: warp arrival falls back to watching the scene id
#: (blind to a same-scene reload), and a cross-room teleport cannot be
#: asked for at all.
DEV_ROOM_PATCH = "2026-08-07 (evening)"

#: The third patch, from the same day's second live pass (0.12.2): a raw
#: position write leaves the CAMERA wedged in the geometry it was looking
#: through, so `teleport` was rebuilt on the game's own Farore's Wind
#: respawn machinery. It now STAGES a real scene reload — room, camera
#: and actors all handled by the game, exactly as a door does — answers
#: at staging time with the respawn record's resolved room and yaw, and
#: takes an optional `yaw`. Arrival is the `loads` counter, like warp.
DEV_FW_PATCH = "2026-08-07 (late evening)"

#: Said whenever this session is running against a pre-DEV_ROOM_PATCH
#: instrument, in the reply itself — an old instrument is diagnosed
#: loudly, never silently obeyed (0.6.0).
NO_LOADS_DIAGNOSTIC = (
    f"this instrument's state carries no `loads` counter, so arrival was "
    f"judged by the scene id CHANGING — the pre-{DEV_ROOM_PATCH} fallback, "
    f"which cannot see a warp back into the scene Link is already in. "
    f"Rebuild SoH with the {DEV_ROOM_PATCH} AgentLink patch.")

#: Why dev_teleport REFUSES on such an instrument rather than falling
#: back. Warp can degrade honestly (a scene id is a weaker predicate, but
#: it is a predicate); teleport cannot. An instrument with no `loads`
#: predates DEV_ROOM_PATCH and therefore also DEV_FW_PATCH, so its
#: teleport is the OLD one — an in-room position write, camera left in
#: the geometry — and its success reply is an echo of the request with
#: nothing to check it against. Trusting that echo would report a
#: full-fidelity arrival that never happened, which is the one thing a
#: harness verb may never do (docs/08).
NO_LOADS_TELEPORT_REFUSAL = (
    f"this instrument's state carries no `loads` counter, so it predates "
    f"the {DEV_ROOM_PATCH} patch — and therefore the {DEV_FW_PATCH} "
    f"teleport too, which rides the game's own Farore's Wind respawn path "
    f"(a real scene reload). Its older teleport wrote a position in place "
    f"and left the camera in the geometry, and its reply is an echo this "
    f"session has no way to check against an arrival the instrument cannot "
    f"report. REFUSED, and nothing was sent: rebuild SoH with the "
    f"{DEV_FW_PATCH} AgentLink patch.")

#: How long the dev verbs wait for the world to actually become the new
#: place. Both ops answer as soon as the transition is STAGED; arrival is
#: a scene load away, and a scene load is seconds, not frames.
WARP_TIMEOUT_S = 15.0
WARP_POLL_S = 0.25

#: How long a staged op may sit in try_again before we call the game
#: stalled (Game._poll_staged_op's clock, same reasoning: the frame hook
#: runs at 20 Hz, so seconds of try_again means frames aren't running).
STAGED_TIMEOUT_S = 3.0
STAGED_POLL_S = 0.1


def _tool(name, description, properties=None, required=None):
    return {"name": name, "description": description,
            "inputSchema": {"type": "object",
                            "properties": properties or {},
                            "required": required or []}}


#: The phase-1 slate (docs/33). Phase 2 (give_item, set_health,
#: set_time) lands with the first live test that needs it — the slate
#: grows evidence-first, like the sensorium does.
TOOLS = [
    _tool("dev_teleport",
          "DEV HARNESS (--dev-tools, journaled): put Link at a place in "
          "the current scene through the game's own Farore's Wind "
          "respawn machinery — a full-fidelity arrival. Every teleport "
          "is a REAL scene reload: the room loads, its actors respawn, "
          "temp flags ride the respawn record and the camera arrives "
          "WITH Link, exactly as a door transition does (a raw position "
          "write left the camera wedged in the geometry, which is why "
          "this rides the respawn path instead). Blocks until the world "
          "re-enters play, and returns the position the world holds "
          "after arrival plus the room and yaw the respawn record "
          "actually took. Use dev_warp to change scenes.",
          {"x": {"type": "number"}, "y": {"type": "number"},
           "z": {"type": "number"},
           "room": {"type": "integer",
                    "description": "Room to arrive in — it rides the "
                                   "respawn record, so the destination's "
                                   "geometry and actors load like any "
                                   "door transition (Kokiri Forest is "
                                   "three rooms). Omit to stay in the "
                                   "room Link is in."},
           "yaw": {"type": "integer",
                   "description": "Link's facing on arrival, as an int16 "
                                  "binang (the game's own angle unit: "
                                  "0x4000 is a quarter turn). Written "
                                  "into the respawn record. Omit to keep "
                                  "the yaw Link has now."}},
          ["x", "y", "z"]),
    _tool("dev_warp",
          "DEV HARNESS (--dev-tools, journaled): travel through the "
          "game's own entrance table — a full-fidelity arrival (scene "
          "load, rooms, actors spawned properly). Blocks until the world "
          "actually re-enters play (a warp back into the CURRENT scene "
          "counts: it is a real reload), and returns what the world says "
          "it became, not what the op claimed.",
          {"entrance": {"type": "integer",
                        "description": "Entrance index (the game's own "
                                       "entrance table)."}},
          ["entrance"]),
]

TOOL_NAMES = tuple(t["name"] for t in TOOLS)

#: The one-line startup shout (the --o2r pattern) and the journal
#: banner's own text. Said on stderr at boot AND carried in every
#: banner event, so neither the operator nor the fossil can miss it.
STARTUP_TEXT = (
    "DEV MODE: --dev-tools is ON, so the dev_* harness verbs "
    f"({', '.join(TOOL_NAMES)}) are registered. Every call is journaled "
    "as a dev_cheat event, and status() reports dev_mode. Scored play "
    "requires this flag OFF (SURFACE.md, Benchmark purity).")


def banner_event(at: str = "boot") -> dict:
    """The journal's dev-mode banner. Written unconditionally on every
    boot and every attach under the flag — the mark is not a courtesy,
    it is what makes the amendment auditable."""
    return {"event": "dev_mode", "cue": "enabled", "at": at,
            "tools": list(TOOL_NAMES), "text": STARTUP_TEXT}


def cheat_event(tool: str, args: dict) -> dict:
    """One dev call, with its arguments, for the permanent record."""
    return {"event": "dev_cheat", "tool": tool, "args": dict(args or {})}


def scored_refusal(repo: Path | str) -> Optional[str]:
    """Why `--dev-tools` must not run against this repo, or None.

    Commitment 3: a save-file repo declares `"scored": true` in
    identity.json and the server refuses to START under the flag — loud,
    named, before any connection. Flight repos stay flight repos.

    Fails closed on a declaration it cannot read: a file that will not
    parse cannot prove it is NOT scored, and "I could not tell" must
    never resolve to "go ahead" (the identity check's own rule).
    """
    ident = load_identity(repo)
    if ident is None:
        return None                      # declares nothing: no refusal
    if ident.scored is True:
        return (f"{ident.path} declares \"scored\": true — this is a "
                f"scored save line ({ident.label()}), and a scored repo "
                f"refuses the dev harness (dojo docs/33, commitment 3). "
                f"Do dev work on a dev repo, or drop the declaration if "
                f"this line is not scored.")
    if ident.scored_problem is not None:
        return (f"{ident.path}: {ident.scored_problem} — a repo whose "
                f"'scored' declaration cannot be read cannot prove it is "
                f"not scored, so --dev-tools refuses it.")
    if not ident.readable:
        return (f"{ident.path} could not be parsed "
                f"({'; '.join(ident.problems)}) — a repo whose "
                f"{IDENTITY_FILENAME} is unreadable cannot prove it is "
                f"not scored, so --dev-tools refuses it. Fix the file (or "
                f"remove it) before doing dev work here.")
    return None


class DevTools:
    """The dev verbs, held by the server only under `--dev-tools`.

    Never reachable from a behavior: nothing in `game.py` refers to this
    class, and nothing hands it to the executor. Constructed with the
    Game purely so world READS go through the same normalized snapshots
    everything else sees; the two dev OPS go straight down the link.
    """

    def __init__(self, game):
        self.game = game
        self.link = game.link
        # Instance-level clocks so a test can shorten them; the module
        # constants are the live values.
        self.warp_timeout_s = WARP_TIMEOUT_S
        self.warp_poll_s = WARP_POLL_S
        self.staged_timeout_s = STAGED_TIMEOUT_S

    def call(self, name: str, args: dict) -> dict:
        handler = {"dev_teleport": self.teleport,
                   "dev_warp": self.warp}.get(name)
        if handler is None:
            return {"ok": False, "error": f"unknown dev tool {name!r}"}
        return handler(args or {})

    # -- the verbs ---------------------------------------------------------

    def teleport(self, args: dict) -> dict:
        if not self.link.connected:
            return {"ok": False, "error": "game not connected"}
        try:
            x, y, z = (float(args[k]) for k in ("x", "y", "z"))
        except (KeyError, TypeError, ValueError):
            return {"ok": False,
                    "error": "dev_teleport needs numeric x, y and z "
                             f"(got {json.dumps(args, default=str)})"}
        room = None
        if args.get("room") is not None:
            room = _as_int(args.get("room"))
            if room is None:
                return {"ok": False,
                        "error": f"dev_teleport's room must be an integer "
                                 f"room number (got {args.get('room')!r})"}
        yaw = None
        if args.get("yaw") is not None:
            yaw = _as_int(args.get("yaw"))
            if yaw is None:
                return {"ok": False,
                        "error": f"dev_teleport's yaw must be an integer "
                                 f"binang, the game's own angle unit "
                                 f"(got {args.get('yaw')!r})"}
        # A teleport is a scene reload now (DEV_FW_PATCH), so arrival is
        # the same predicate warp uses: the world re-entering play. Read
        # the counter BEFORE staging anything — and refuse outright if
        # this instrument has none, because the alternative is trusting
        # an echo (NO_LOADS_TELEPORT_REFUSAL).
        before = self.game.state()
        scene_from, loads_from = before.get("scene"), before.get("loads")
        if loads_from is None:
            return {"ok": False, "error": NO_LOADS_TELEPORT_REFUSAL}
        payload = {"type": "agent", "op": "teleport", "x": x, "y": y, "z": z}
        if room is not None:
            payload["room"] = room
        if yaw is not None:
            payload["yaw"] = yaw
        res = self._op(payload)
        if not res.get("ok"):
            # The game refuses BY NAME — an out-of-range room (-18: it
            # knows the scene's room count and we do not) or an entrance
            # index outside the table (-19: Link is standing in a
            # grotto/shop return, so there is no entrance to respawn
            # through). Carry its words; add which room we asked for when
            # the room is what it refused, so the line reads whole.
            if room is not None and res.get("code") != -19:
                res = {**res, "error": f"{res.get('error')} "
                                       f"(dev_teleport asked for room {room})"}
            return res
        # The reply is STAGING-time truth: the respawn record's word,
        # including the room and yaw it resolved (defaults filled in from
        # where Link is). It is not an arrival, and it is not a position
        # read — so the position we report is the WORLD's, after the load
        # (docs/08: an op replying success proves staging, nothing more).
        arrived, last, waited, unread = self._watch_arrival(
            lambda st: st.get("loads") not in (None, loads_from))
        if arrived is None:
            last = last or before
            tail = (f" The last state read failed: {unread}" if unread else "")
            return {"ok": False,
                    "error": f"the teleport to ({x:g}, {y:g}, {z:g}) was "
                             f"staged, but the world never re-entered play "
                             f"within {self.warp_timeout_s:.0f}s — the `loads` "
                             f"counter is still {last.get('loads')} (scene "
                             f"{last.get('scene')}). Every teleport is a real "
                             f"scene reload through the game's respawn path, "
                             f"so an instrument predating the {DEV_FW_PATCH} "
                             f"AgentLink patch (whose teleport wrote a "
                             f"position in place) never ticks it — rebuild "
                             f"SoH; so does a game that stopped processing "
                             f"frames." + tail}
        out = {"ok": True, "requested": [x, y, z],
               "pos": (arrived.get("player") or {}).get("pos"),
               "waited_s": waited}
        if room is not None:
            out["room_requested"] = room
        resolved_room = res.get("room")
        final = resolved_room if resolved_room is not None else arrived.get("room")
        if final is not None:
            out["room"] = final
        if res.get("yaw") is not None:
            out["yaw"] = res["yaw"]
        if arrived.get("loads") is not None:
            out["loads"] = arrived["loads"]
        notes = []
        if room is not None and resolved_room is None:
            notes.append(
                f"this instrument echoed no resolved room, so its teleport is "
                f"not the {DEV_FW_PATCH} respawn teleport and the room "
                f"argument may have been IGNORED — if that was a cross-room "
                f"move, the destination's actors are not loaded. Rebuild SoH.")
        elif room is not None and final is not None and final != room:
            notes.append(f"asked for room {room}, the respawn record took "
                         f"room {final}")
        if yaw is not None and res.get("yaw") is None:
            notes.append(
                f"this instrument echoed no resolved yaw, so the facing may "
                f"have been IGNORED — rebuild SoH with the {DEV_FW_PATCH} "
                f"AgentLink patch.")
        if scene_from is not None and arrived.get("scene") not in (None,
                                                                  scene_from):
            notes.append(f"the world came back in scene {arrived['scene']}, "
                         f"not {scene_from} — a teleport reloads the scene it "
                         f"is already in; this one did not")
        if notes:
            out["diagnostic"] = " ".join(notes)
        return out

    def warp(self, args: dict) -> dict:
        if not self.link.connected:
            return {"ok": False, "error": "game not connected"}
        entrance = _as_int(args.get("entrance"))
        if entrance is None:
            return {"ok": False,
                    "error": f"dev_warp needs an integer entrance index "
                             f"(got {args.get('entrance')!r})"}
        # Arrival is "the world entered play again", not "the scene id
        # changed": an entrance leading back into the CURRENT scene
        # performs the whole reload, and the first live pass sat watching
        # a scene id that was never going to move (2026-08-07). The
        # instrument's `loads` counter is the honest predicate — it ticks
        # on every play-state init, same scene or not. An instrument
        # without it falls back to the old watch AND says so.
        before = self.game.state()
        scene_from, loads_from = before.get("scene"), before.get("loads")
        res = self._op({"type": "agent", "op": "warp", "entrance": entrance})
        if not res.get("ok"):
            return res
        # The op is STAGED: it answers when the transition is requested,
        # not when the world is that place. Arrival is the world's word,
        # never the op's (docs/08 — an op replying success proves
        # staging, the same lesson the HUD's `draws` counter taught).
        if loads_from is None:
            def has_arrived(st):
                return st.get("scene") not in (None, scene_from)
        else:
            def has_arrived(st):
                return st.get("loads") not in (None, loads_from)
        arrived, last, waited, unread = self._watch_arrival(has_arrived)
        if arrived is not None:
            scene, loads = arrived.get("scene"), arrived.get("loads")
            out = {"ok": True, "entrance": entrance,
                   "scene": scene, "scene_from": scene_from,
                   "pos": (arrived.get("player") or {}).get("pos"),
                   "waited_s": waited,
                   "arrival": "scene_change" if loads_from is None else "loads"}
            if scene == scene_from:
                # Present only in the case worth remarking on: the world
                # genuinely reloaded and came back the same place.
                out["same_scene"] = True
            if arrived.get("room") is not None:
                out["room"] = arrived["room"]
            if loads is not None:
                out["loads"] = loads
            if loads_from is None:
                out["diagnostic"] = NO_LOADS_DIAGNOSTIC
            return out
        last = last or before
        scene, loads = last.get("scene"), last.get("loads")
        tail = (f" The last state read failed: {unread}" if unread else "")
        if loads_from is None:
            return {"ok": False,
                    "error": f"entrance {entrance} (0x{entrance:04X}) was "
                             f"accepted, but the scene never changed within "
                             f"{self.warp_timeout_s:.0f}s — still scene "
                             f"{scene}. This instrument's state carries no "
                             f"`loads` counter, so a warp back INTO the scene "
                             f"Link is already in is invisible to this watch "
                             f"(rebuild SoH with the {DEV_ROOM_PATCH} "
                             f"AgentLink patch); so is a wrong entrance "
                             f"index, or a game that stopped processing "
                             f"frames." + tail}
        return {"ok": False,
                "error": f"entrance {entrance} (0x{entrance:04X}) was "
                         f"accepted, but the world never re-entered play "
                         f"within {self.warp_timeout_s:.0f}s — the `loads` "
                         f"counter is still {loads} (scene {scene}). (A wrong "
                         f"entrance index, or a game that stopped processing "
                         f"frames.)" + tail}

    # -- the wire ----------------------------------------------------------

    def _watch_arrival(self, has_arrived):
        """Poll the world until `has_arrived(state)` — the one arrival
        watch behind both dev verbs, because since DEV_FW_PATCH both of
        them stage a real scene load and neither may believe its own op.

        Returns `(arrived_state | None, last_state_read | None, waited_s,
        last_unread_error)`. A read that RAISES is not an answer: a scene
        load is the one moment the instrument can go quiet, so the loop
        keeps asking and only reports the silence if it is all we ever
        got.
        """
        started = time.monotonic()
        deadline = started + self.warp_timeout_s
        last, unread = None, None
        while time.monotonic() < deadline:
            time.sleep(self.warp_poll_s)
            try:
                st = self.game.state()
            except LinkError as e:
                unread = str(e)
                continue
            last = st
            if has_arrived(st):
                return st, st, round(time.monotonic() - started, 1), unread
        return None, last, round(time.monotonic() - started, 1), unread

    def _op(self, payload: dict) -> dict:
        """Drive one STAGED main-thread op to its verdict.

        Both dev ops ride the instrument's staged protocol — the Sail
        thread cannot touch game state, so the op answers `try_again`
        until the frame hook has run its gates and either performed or
        refused BY NAME. This is `Game._poll_staged_op`'s loop, copied
        rather than called: `game.py` grows nothing, in any mode, and a
        few duplicated lines are a cheap price for a structural promise
        (docs/33 commitment 1). Keep the two in sync by hand.

        An instrument that predates these ops answers "unknown agent
        op"; that is surfaced by name, never retried into a hang (the
        0.6.0 rule: an old instrument answers loudly, never silently).
        """
        deadline = time.monotonic() + self.staged_timeout_s
        while True:
            res = self.link.request(payload)
            status = res.get("status")
            if status == "success":
                return {"ok": True, **{k: v for k, v in res.items()
                                       if k not in ("type", "id", "status")}}
            err = str(res.get("error", ""))
            if "unknown agent op" in err or "unknown op" in err:
                return {"ok": False,
                        "error": f"this instrument predates the "
                                 f"{payload['op']!r} dev op — rebuild SoH "
                                 f"with the {DEV_PATCH} AgentLink patch "
                                 f"(dojo docs/33)"}
            if status != "try_again":
                out = {"ok": False, "error": err or f"{payload['op']} failed"}
                if res.get("code") is not None:
                    # The game's own refusal code (-18 room out of range,
                    # -19 entrance out of range) rides along: the caller
                    # says the words, but WHICH refusal it is decides how
                    # much of our own context belongs in the sentence.
                    out["code"] = res["code"]
                return out
            if time.monotonic() > deadline:
                return {"ok": False,
                        "error": f"{payload['op']} request pending past "
                                 f"{self.staged_timeout_s:.0f}s — is the "
                                 f"game processing frames?"}
            time.sleep(STAGED_POLL_S)


def _as_int(value) -> Optional[int]:
    """An index from JSON (an entrance, a room number): an integer, or a
    string a human would write it as ("0x0311"). Anything else is a
    refusal, not a guess."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip(), 0)
        except ValueError:
            return None
    return None
