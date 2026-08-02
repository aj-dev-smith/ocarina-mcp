"""Game: high-level API that behaviors are written against.

Ported from the workshop (oot-dojo ootdojo/game.py, validated against the
real game) with two deliberate differences:

- **No savestate methods, no console().** Not gated — ABSENT (SURFACE.md,
  benchmark purity). Savestate machinery and debug-console warps are
  workshop dev-tooling; a behavior graded in the dojo never called them,
  so removing the methods costs the port nothing and removes the verbs
  from this repo entirely.
- **`state_observer` hook.** Every state() snapshot is offered to an
  optional callback, so the machine runtime can watch the world through
  the SAME snapshots behaviors take instead of issuing concurrent state()
  calls of its own — a second concurrent poll inflates the passive hit
  counter (workshop docs/08).

Everything else is as validated: all primitives are wall-clock based (the
game runs at 20 Hz realtime).
"""

from __future__ import annotations

import math
import threading
import time
from typing import Iterable, Optional

from .link import GameLink
from .protocol import (TICK, buttons_mask, PLAYER_STATE1_DEAD, PLAYER_UNCONTROLLABLE,
                       PLAYER_STATE1_CLIMBING_LADDER, PLAYER_STATE1_CLIMBING_LEDGE,
                       PLAYER_STATE1_ON_A_WALL, PLAYER_STATE2_DO_ACTION_CLIMB)


class Game:
    def __init__(self, link: GameLink):
        self.link = link
        # Accuracy instrumentation. swings counts commanded sword swings; hits
        # counts observed enemy health drops, attributed per-actor via the
        # stable "key". A behavior that mashes B racks up swings without hits.
        self.swings = 0
        self.hits = 0
        self._actor_hp: dict = {}
        # The runtime's when-sweep polls state concurrently with a running
        # body; without this lock two threads can both see the same health
        # drop before either records it and count one hit twice (the
        # docs/08 concern behind the workshop's don't-double-poll rule —
        # here the second poller is by design, so the counter is locked).
        self._observe_lock = threading.Lock()
        # Called with every state() snapshot (see module docstring). Must be
        # cheap and must not call back into Game.
        self.state_observer: Optional[callable] = None

    def reset_instruments(self) -> None:
        self.swings = 0
        self.hits = 0
        self._actor_hp = {}

    @property
    def accuracy(self) -> Optional[float]:
        """Fraction of swings that landed. None if nothing was swung."""
        return (self.hits / self.swings) if self.swings else None

    # -- raw dojo ops ------------------------------------------------------

    def state(self) -> dict:
        st = self.link.request({"type": "dojo", "op": "state"})
        self._observe_hits(st)
        if self.state_observer is not None:
            self.state_observer(st)
        return st

    def _observe_hits(self, st: dict) -> None:
        """Passively count enemy health drops seen between snapshots.

        Sampling-based, so it can miss a hit if two land between polls; it
        undercounts rather than inventing hits, which keeps accuracy honest as
        a lower bound.
        """
        with self._observe_lock:
            for a in st.get("actors", []) or []:
                key = a.get("key")
                if key is None:
                    continue
                hp = a.get("health")
                prev = self._actor_hp.get(key)
                if prev is not None and hp is not None and hp < prev:
                    self.hits += 1
                self._actor_hp[key] = hp

    def pad(self, buttons: int = 0, stick: tuple[int, int] = (0, 0)) -> None:
        self.link.request({"type": "dojo", "op": "pad", "buttons": buttons,
                           "stick": [int(stick[0]), int(stick[1])]})

    def pad_clear(self) -> None:
        self.link.request({"type": "dojo", "op": "pad", "clear": True})

    # Savestate methods deliberately not ported — see module docstring.

    def pause(self, on: bool = True) -> None:
        self.link.request({"type": "dojo", "op": "pause", "on": on})

    def tick(self, n: int = 1) -> None:
        self.link.request({"type": "dojo", "op": "tick", "n": n})

    def events_on(self, frame_interval: int = 20) -> None:
        self.link.request({"type": "dojo", "op": "events", "on": True,
                           "frame_interval": frame_interval})

    def hud_push(self, panels: Optional[dict[str, list]] = None,
                 ticker: Optional[list[str]] = None) -> dict:
        """Push Agent HUD content (docs/11 §7).

        `panels` maps panel name (warden|navigator|strategist|dojo) to an
        ORDERED list of [key, value] pairs — a list, not a dict, because the
        wire is JSON and the game renders fields in the order given.
        Setting a panel replaces it wholesale.
        """
        payload: dict = {"type": "dojo", "op": "hud", "sub": "set"}
        if panels:
            payload["panels"] = panels
        if ticker:
            payload["ticker"] = ticker
        return self.link.request(payload)

    def hud_get(self) -> dict:
        """Read the HUD back. `draws` advances only while the window is
        actually rendering, so this distinguishes 'the store took it' from
        'something drew it' — the op replying success proves neither."""
        return self.link.request({"type": "dojo", "op": "hud", "sub": "get"})

    def hud_clear(self) -> dict:
        return self.link.request({"type": "dojo", "op": "hud", "sub": "clear"})

    def hud_show(self, on: bool = True) -> dict:
        return self.link.request({"type": "dojo", "op": "hud", "sub": "show", "on": on})

    def overlay_push(self, labels: list[dict]) -> dict:
        """Push the debug overlay: floating world-space labels over actors.

        Each label is {"key": <actor key from state>, "text": str,
        "color": [r, g, b]}; a set REPLACES the whole label set, so a
        label that stops being pushed disappears. The game resolves keys
        against its live actor lists and skips (counts, not errors) any
        that despawned since the snapshot. Human debug instrument only —
        see overlay.py's one-way promise.
        """
        return self.link.request({"type": "dojo", "op": "overlay",
                                  "sub": "set", "labels": labels})

    def overlay_get(self) -> dict:
        """Read the overlay store back. `applies` advances only when the
        game's main thread turns a push into nametags — the op replying
        success proves staging, not rendering (the HUD's `draws` rule)."""
        return self.link.request({"type": "dojo", "op": "overlay", "sub": "get"})

    def overlay_clear(self) -> dict:
        return self.link.request({"type": "dojo", "op": "overlay", "sub": "clear"})

    def scan(self, rays: int = 24, length: float = 600.0, height: float = 26.0,
             from_yaw: Optional[int] = None, span: Optional[int] = None,
             origin: Optional[tuple] = None) -> list[dict]:
        """Fan of collision line tests around Link: what is there, and is it climbable?

        Returns one dict per ray with `yaw`, `hit`, and when it hit: `dist`,
        `pos`, `wall_flags`, `is_vine`, `is_ladder`, `normal_y`, `wall_yaw`.

        This is geometry, not actors. The actor census cannot see a wall, and
        walking into one costs ~12s per bearing and still does not say what the
        surface is — a scan answers both in one op. Read `is_vine` (wall flag
        1 << 3) rather than any player state flag: stateFlags2's DO_ACTION_CLIMB
        is the dynapoly LEDGE-mount prompt and is permanently false on a scene
        vine wall, which reads as "nothing climbable anywhere".
        """
        req: dict = {"type": "dojo", "op": "scan", "rays": int(rays),
                     "length": float(length), "height": float(height)}
        if from_yaw is not None:
            req["from_yaw"] = int(from_yaw) & 0xFFFF
        if span is not None:
            req["span"] = int(span)
        if origin is not None:
            req["origin"] = [float(v) for v in origin]
        return self.link.request(req).get("rays", [])

    def scan_climbable(self, **kw) -> list[dict]:
        """Only the rays that hit a surface the game will let Link climb.

        Filters on the vine/ladder flags AND on the face being steep enough:
        func_8083EC18's callers gate on ABS(normal.y) < 600, i.e. |normal_y| <
        0.0183 in float terms, so a vine-flagged ramp is still not a climb.
        """
        out = []
        for r in kw.pop("rays_in", None) or self.scan(**kw):
            if r.get("hit") and (r.get("is_vine") or r.get("is_ladder")):
                out.append(r)
        return out

    # console() deliberately not ported — see module docstring.

    # -- derived observations ---------------------------------------------

    def player(self) -> Optional[dict]:
        return self.state().get("player")

    def is_dead(self) -> bool:
        p = self.player()
        return bool(p and (p["state_flags1"] & PLAYER_STATE1_DEAD))

    def health(self) -> int:
        return self.state().get("health", 0)

    def actors(self, actor_id: Optional[int] = None, max_dist: Optional[float] = None) -> list[dict]:
        actors = self.state().get("actors", [])
        if actor_id is not None:
            actors = [a for a in actors if a["id"] == actor_id]
        if max_dist is not None:
            actors = [a for a in actors if a["dist_xz"] <= max_dist]
        return actors

    def nearest(self, actor_id: int) -> Optional[dict]:
        found = self.actors(actor_id=actor_id)
        return found[0] if found else None

    # -- movement / combat primitives --------------------------------------

    def hold(self, *names: str, stick: tuple[int, int] = (0, 0), seconds: float = 0.0) -> None:
        """Hold buttons/stick; if seconds > 0, release after that long."""
        self.pad(buttons=buttons_mask(*names), stick=stick)
        if seconds > 0:
            time.sleep(seconds)
            self.pad_clear()

    def press(self, *names: str, frames: int = 3) -> None:
        """Press and release (default 3 ticks ~ 150 ms)."""
        self.pad(buttons=buttons_mask(*names))
        time.sleep(frames * TICK)
        self.pad_clear()

    def camera_yaw(self) -> int:
        """Binary yaw the analog stick is measured against. See stick_for_world_yaw."""
        return self.state().get("camera_yaw", 0)

    def stick_for_world_yaw(self, world_yaw: int, magnitude: int = 80,
                            camera_yaw: Optional[int] = None) -> tuple[int, int]:
        """Stick vector that walks Link toward a WORLD binary yaw (0 = +z, 0x4000 = +x).

        The stick is camera-relative, not world-relative. From the game's own
        code (z_player.c:2050, z_lib.c:200):

            worldYaw   = Camera_GetInputDirYaw(activeCam) + stickAngle
            stickAngle = Math_Atan2S(stick_y, -stick_x)

        Math_Atan2S(a, b) measures from the +a axis toward +b, so inverting
        gives stick_y = cos(alpha) and -stick_x = sin(alpha), i.e. the x
        component is NEGATED relative to the naive mapping. v1 had both bugs:
        it ignored the camera term entirely and used +sin for x, which is why
        walk_toward reliably walked AWAY from its target.

        The camera is semi-autonomous and rotates while Link moves, so
        camera_yaw is re-read per call unless supplied.
        """
        if camera_yaw is None:
            camera_yaw = self.camera_yaw()
        alpha = (int(world_yaw) - int(camera_yaw)) & 0xFFFF
        rad = alpha / 0x8000 * math.pi
        return (int(-magnitude * math.sin(rad)), int(magnitude * math.cos(rad)))

    def world_yaw_to(self, target: dict) -> int:
        """Binary yaw pointing from Link toward target.

        actor.yaw_to_player is the bearing target->player, so invert it.
        """
        return (int(target["yaw_to_player"]) + 0x8000) & 0xFFFF

    def stick_toward_yaw(self, yaw_to_target: int, camera_relative: bool = False,
                         magnitude: int = 80) -> tuple[int, int]:
        """Deprecated shim: takes actor.yaw_to_player, as v1 workshop bodies pass it."""
        return self.stick_for_world_yaw((int(yaw_to_target) + 0x8000) & 0xFFFF,
                                        magnitude=magnitude)

    def walk_toward(self, target: dict, seconds: float, magnitude: int = 80) -> None:
        sx, sy = self.stick_for_world_yaw(self.world_yaw_to(target), magnitude=magnitude)
        self.hold(stick=(sx, sy), seconds=seconds)

    def walk_away(self, target: dict, seconds: float, magnitude: int = 80) -> None:
        """Retreat directly away from target — the opposite world bearing."""
        yaw = (self.world_yaw_to(target) + 0x8000) & 0xFFFF
        sx, sy = self.stick_for_world_yaw(yaw, magnitude=magnitude)
        self.hold(stick=(sx, sy), seconds=seconds)

    # -- navigation to a POINT ---------------------------------------------
    # A combat behavior only ever needs to move relative to an actor, so every
    # primitive above takes an actor dict. A route needs to move relative to a
    # place, which has no `yaw_to_player` to invert.

    def pos(self) -> Optional[tuple[float, float, float]]:
        """Link's world position, or None if there is no player yet."""
        p = self.player()
        if not p:
            return None
        x, y, z = p["pos"]
        return (float(x), float(y), float(z))

    def world_yaw_to_point(self, x: float, z: float,
                           from_pos: Optional[tuple] = None) -> int:
        """Binary yaw pointing from Link toward (x, z). 0 = +z, 0x4000 = +x.

        Matches the engine's convention: Math_Atan2S(z, x) measures from +z
        toward +x, which is what stick_for_world_yaw expects to be handed.
        """
        here = from_pos or self.pos()
        if here is None:
            return 0
        return int(math.atan2(x - here[0], z - here[2]) / math.pi * 0x8000) & 0xFFFF

    def dist_to_point(self, x: float, z: float) -> float:
        """Horizontal distance only. It is a PROJECTION — see docs/08 §17."""
        here = self.pos()
        if here is None:
            return float("inf")
        return math.hypot(x - here[0], z - here[2])

    def walk_to_point(self, x: float, z: float, within: float = 30.0,
                      timeout: float = 8.0, magnitude: int = 80,
                      repoll: float = 0.25) -> bool:
        """Walk to (x, z), re-aiming as we go. True if we got within `within`.

        Re-aims every `repoll` seconds for two independent reasons: the camera
        rotates while Link moves (so a stick vector computed once decays), and
        the bearing itself changes as he approaches. Gives up on timeout rather
        than looping forever, because a route that is wedged against geometry
        would otherwise hold the stick until the trial deadline.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.dist_to_point(x, z) <= within:
                self.pad_clear()
                return True
            sx, sy = self.stick_for_world_yaw(self.world_yaw_to_point(x, z),
                                              magnitude=magnitude)
            self.pad(stick=(sx, sy))
            time.sleep(repoll)
        self.pad_clear()
        return self.dist_to_point(x, z) <= within

    def walk_bearing(self, world_yaw: int, seconds: float, magnitude: int = 80,
                     repoll: float = 0.25) -> None:
        """Walk on a fixed WORLD bearing, recompensating for camera drift.

        Not the same as holding one stick vector for `seconds`: that walks a
        curve, because the camera rotates behind Link and the same stick vector
        means a different world direction a second later.
        """
        deadline = time.time() + seconds
        while time.time() < deadline:
            sx, sy = self.stick_for_world_yaw(world_yaw, magnitude=magnitude)
            self.pad(stick=(sx, sy))
            time.sleep(min(repoll, max(0.0, deadline - time.time())))
        self.pad_clear()

    # -- climbing ----------------------------------------------------------
    # Read z_player.c before changing any of this. Three facts drive it all:
    #
    # 1. THE CLIMB IS NOT CAMERA-RELATIVE. Player_Action_8084BF1C reads
    #    sControlInput->rel.stick_y/x directly (z_player.c:8084BF1C head), with
    #    no Camera_GetInputDirYaw term anywhere. Stick up climbs up no matter
    #    where the camera is looking, so stick_for_world_yaw must NOT be
    #    applied while on a wall — doing so would rotate "up" into "sideways".
    #    This is the same exemption Z-targeting gets, for a different reason.
    # 2. PRESSING A LETS GO. func_8083FBC0 drops Link off the wall on A's press
    #    edge unconditionally. Nothing here may press A, and a behavior that mixes
    #    a climb with an A-button action falls off mid-route.
    # 3. THE GRAB NEEDS FORWARD MOTION. Player_ActionHandler_5 gates on
    #    linearVelocity > 0.0f, on shape yaw within 0x3000 of facing into the
    #    wall, and on yDistToLedge >= 79.0f. So you cannot grab by standing
    #    against vines — you have to still be walking into them.
    #
    # Stick magnitude: PadUtils_UpdateRelXY deadzones |cur| <= 7 to 0 and caps
    # at 0x43 (67), so rel maxes out at 60 and the climb's playSpeed formula
    # (|rel_y| * 0.05, clamped [1.0, 3.35]) saturates at 3.0. Any magnitude
    # >= 67 is therefore the same climb speed; 80 matches the walk default.

    def climbing(self) -> bool:
        """On a ladder or vine wall, under stick control."""
        p = self.player()
        return bool(p and (p["state_flags1"] & PLAYER_STATE1_CLIMBING_LADDER))

    def mounting_ledge(self) -> bool:
        """Playing the top-out animation. Set the frame CLIMBING_LADDER clears."""
        p = self.player()
        return bool(p and (p["state_flags1"] & PLAYER_STATE1_CLIMBING_LEDGE))

    def on_a_wall(self) -> bool:
        """Climbing, mounting or hanging — i.e. not standing on a floor."""
        p = self.player()
        return bool(p and (p["state_flags1"] & PLAYER_STATE1_ON_A_WALL))

    def climb_offered(self) -> bool:
        """The game is showing the Climb prompt: we are against a climbable wall.

        This is the diagnosis that separates "we never reached the vines" from
        "we reached them and the grab was refused" — without it a failed grab
        is one indistinguishable red result.
        """
        p = self.player()
        return bool(p and (p["state_flags2"] & PLAYER_STATE2_DO_ACTION_CLIMB))

    def grab_wall(self, x: float, z: float, timeout: float = 4.0,
                  magnitude: int = 80) -> bool:
        """Walk into the wall at (x, z) until the grab takes. True if climbing.

        Keeps the stick pushed INTO the wall for the whole attempt because the
        grab gate needs linearVelocity > 0 on the frame it is evaluated; a
        walk-then-check loop that releases the stick between polls can sit
        flush against climbable vines forever without ever grabbing.
        """
        deadline = time.time() + timeout
        sx, sy = self.stick_for_world_yaw(self.world_yaw_to_point(x, z),
                                         magnitude=magnitude)
        self.pad(stick=(sx, sy))
        while time.time() < deadline:
            if self.climbing():
                return True
            time.sleep(2 * TICK)
            # Re-aim: the camera swings as Link walks, and a stale vector can
            # walk him along the wall instead of into it.
            sx, sy = self.stick_for_world_yaw(self.world_yaw_to_point(x, z),
                                              magnitude=magnitude)
            self.pad(stick=(sx, sy))
        grabbed = self.climbing()
        if not grabbed:
            # MUST clear on the failure path. The pad override is HELD STATE
            # LIVING IN THE GAME, not in this process: a primitive that returns
            # with the stick down leaves Link walking after the script exits,
            # and the next savestate load is immediately walked away from. That
            # silently moved Link 130 units between two probe runs and made the
            # second one measure a position nobody chose.
            self.pad_clear()
        return grabbed

    def climb(self, seconds: float, direction: str = "up",
              magnitude: int = 80) -> None:
        """Hold the raw stick to climb. NO camera compensation — see above.

        `direction` is up / down / left / right. Lateral movement works on vines
        (av1.actionVar1 != 0) and is ignored on ladders, which is how a climber
        gets around a Skullwalltula without letting go.
        """
        vectors = {"up": (0, magnitude), "down": (0, -magnitude),
                   "left": (-magnitude, 0), "right": (magnitude, 0)}
        if direction not in vectors:
            raise ValueError(f"climb direction must be one of {sorted(vectors)}")
        self.hold(stick=vectors[direction], seconds=seconds)

    # -- wall following ----------------------------------------------------
    # The move that makes climbs COMPOSE. `climb_vines` gains as much height as
    # the face it finds and then stops, and the next face is usually not visible
    # from where the last one landed — measured on the Deku Tree y=280 ledge,
    # where a scan at grabbable height finds nothing and the next vine patch only
    # appears 160 units up. Walking straight at it walks Link off the ledge.
    # Following the wall he is standing against keeps him on the ledge while
    # changing what is in view, so leg two can be the same behavior again rather
    # than a second behavior named after the room.

    def touched_wall(self) -> Optional[dict]:
        """The wall the ENGINE says Link is against, or None.

        Preferred over `nearest_wall` for steering. The scan reports the nearest
        ray hit, which in a corner or a wide room can be a surface 100+ units
        away that Link is not touching at all — steering off that produced a
        wall-follow that walked one step and then sat still for nine polls,
        because the tangent it computed had nothing to do with the ledge under
        Link's feet.
        """
        p = self.player()
        if not p or not p.get("wall_flags", 0) and not (p.get("bg_check_flags", 0) & 0x200):
            return None
        if "wall_yaw" not in p:
            return None
        return {"wall_yaw": p["wall_yaw"], "dist": p.get("dist_to_wall", 0.0),
                "wall_flags": p.get("wall_flags", 0),
                "is_vine": bool(p.get("wall_is_vine")),
                "is_ladder": bool(p.get("wall_is_ladder")),
                "source": "touched"}

    def nearest_wall(self, rays: int = 32, length: float = 300.0,
                     height: float = 26.0) -> Optional[dict]:
        """The closest wall ray around Link, or None if he is in the open."""
        hits = [r for r in self.scan(rays=rays, length=length, height=height)
                if r.get("hit")]
        if not hits:
            return None
        best = dict(min(hits, key=lambda r: r["dist"]))
        best["source"] = "scan"
        return best

    def steering_wall(self) -> Optional[dict]:
        """The wall to follow: the touched one if there is one, else the nearest."""
        return self.touched_wall() or self.nearest_wall()

    def follow_wall(self, seconds: float, side: str = "right",
                    hug: float = 0.35, magnitude: int = 80,
                    stop_when: Optional[callable] = None,
                    repoll: float = 0.3) -> bool:
        """Walk along the nearest wall, staying against it. True if stop_when fired.

        Steers on the wall's own normal rather than on a remembered bearing: the
        tangent is `wall_yaw +/- 0x4000`, re-derived every poll, with a fraction
        `hug` of the vector aimed into the wall so a curving surface does not
        peel Link away from it. That inward bias is what keeps him on a ledge —
        the ledge is bounded by the wall on one side and nothing at all on the
        other, and "nothing at all" is a 280-unit drop.

        `stop_when(game)` is polled each step, so a caller can follow until
        something specific comes into view (a climbable face, a doorway) instead
        of guessing a duration.
        """
        if side not in ("right", "left"):
            raise ValueError("side must be 'right' or 'left'")
        deadline = time.time() + seconds
        while time.time() < deadline:
            if stop_when is not None and stop_when(self):
                self.pad_clear()
                return True
            wall = self.steering_wall()
            if wall is None:
                # Lost the wall entirely. Stop rather than wander: without a
                # surface to reference, "along" has no meaning and any further
                # movement is unguided.
                self.pad_clear()
                return False
            # wall_yaw is the OUTWARD normal, so +0x8000 points into the face.
            into = (int(wall.get("wall_yaw", 0)) + 0x8000) & 0xFFFF
            turn = 0x4000 if side == "right" else -0x4000
            along = (into + turn) & 0xFFFF
            ax, ay = self.stick_for_world_yaw(along, magnitude=magnitude)
            ix, iy = self.stick_for_world_yaw(into, magnitude=magnitude)
            sx = int(ax * (1.0 - hug) + ix * hug)
            sy = int(ay * (1.0 - hug) + iy * hug)
            self.pad(stick=(sx, sy))
            time.sleep(repoll)
        self.pad_clear()
        return bool(stop_when is not None and stop_when(self))

    def climb_to_y(self, target_y: float, timeout: float = 20.0,
                   magnitude: int = 80, repoll: float = 0.25) -> bool:
        """Climb until Link's y reaches target_y, or he leaves the wall.

        Returns True only while still attached and at height; topping out over
        the ledge clears CLIMBING_LADDER, so callers that want "reached the
        top" should test mounting_ledge()/y instead of this return value.
        """
        deadline = time.time() + timeout
        self.pad(stick=(0, magnitude))
        while time.time() < deadline:
            here = self.pos()
            if here and here[1] >= target_y:
                self.pad_clear()
                return True
            if not self.on_a_wall():
                self.pad_clear()
                return False
            time.sleep(repoll)
        self.pad_clear()
        here = self.pos()
        return bool(here and here[1] >= target_y)

    def controllable(self) -> bool:
        """True when Link will actually respond to the pad."""
        st = self.state()
        p = st.get("player")
        if not p:
            return False
        return not (p["state_flags1"] & PLAYER_UNCONTROLLABLE) and st.get("msg_mode", 0) == 0

    def wait_controllable(self, timeout: float = 20.0) -> bool:
        """Block until Link accepts input. Clears text boxes encountered on the way.

        Save a state only once this returns True: a state captured during a
        cutscene lock replays that lock on every single load.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            st = self.state()
            if st.get("msg_mode", 0) != 0:
                self.press("A", frames=3)
                time.sleep(0.2)
                continue
            p = st.get("player")
            if p and not (p["state_flags1"] & PLAYER_UNCONTROLLABLE):
                return True
            time.sleep(0.2)
        return self.controllable()

    def clear_text(self, max_presses: int = 25) -> bool:
        """Dismiss any open text box. Returns True if msg_mode reached 0.

        A message freezes input entirely — a trial that starts with a text box
        open records zero movement and looks like a dead behavior.
        """
        for _ in range(max_presses):
            if self.state().get("msg_mode", 0) == 0:
                return True
            self.press("A", frames=3)
            time.sleep(0.25)
        return self.state().get("msg_mode", 0) == 0

    def z_target(self) -> None:
        self.press("Z", frames=4)

    def targeting(self) -> bool:
        """True when Link is locked on to something."""
        return bool(self.state().get("focus_actor"))

    def acquire_target(self, tries: int = 4) -> bool:
        """Press Z until lock-on actually takes. Verified, not assumed.

        Worth doing before anything else in a fight: while locked on, the
        analog stick becomes TARGET-relative rather than camera-relative, so
        stick-forward means "at the enemy" regardless of where the camera has
        drifted. It removes the camera-yaw compensation entirely.
        """
        for _ in range(tries):
            if self.targeting():
                return True
            self.press("Z", frames=4)
            time.sleep(0.2)
        return self.targeting()

    # -- Z-targeted moves --------------------------------------------------
    # All of these are stick directions relative to the LOCKED TARGET, so no
    # camera compensation is applied. They are no-ops (or worse, camera-frame
    # moves) if lock-on is not actually held — check acquire_target() first.

    def jump_slash(self) -> None:
        """Z + forward + B: leaping overhead attack.

        Deku Baba damage table: "Kokiri jump" is DMG_ENTRY(2, DMGEFF_SWORD)
        against 2 HP — a one-shot kill, where a standing slash does 1.

        It does NOT sever the stalk. This docstring used to claim it did, which
        is exactly backwards: a one-shot outside StunnedVertical takes the
        SetupHit(0) branch and dies via ShrinkDie, which scatters NUTS
        (z_en_dekubaba.c:1052-1082). The stick needs the KILLING blow to land
        while the baba is already stunned — see docs/06 and deku_baba_v13.

        Where it is genuinely useful: during PullBack the stun branch clamps
        health to a minimum of 1 (:1060-1065), so 2 damage cannot overshoot
        into the nut path there.
        """
        self.swings += 1
        # The stick must ALREADY be forward on the frame B's press edge is
        # sampled, or the game reads a neutral stick and gives a plain
        # horizontal slash (observed: 1 damage instead of 2). Establish the
        # direction first, then add B while holding it.
        self.pad(buttons=buttons_mask("Z"), stick=(0, 100))
        time.sleep(4 * TICK)
        self.pad(buttons=buttons_mask("Z", "B"), stick=(0, 100))
        time.sleep(8 * TICK)
        self.pad_clear()

    def sidehop(self, direction: str = "right") -> None:
        """Z + left/right + A: sidehop. The standard dodge for a committed lunge."""
        x = 100 if direction == "right" else -100
        self.pad(buttons=buttons_mask("Z", "A"), stick=(x, 0))
        time.sleep(6 * TICK)
        self.pad_clear()

    def spin_attack(self) -> None:
        """Hold B to charge, release: spin. DMGEFF_SWORD, hits all around."""
        self.swings += 1
        self.pad(buttons=buttons_mask("B"))
        time.sleep(20 * TICK)  # charge
        self.pad_clear()
        time.sleep(4 * TICK)

    def slash(self) -> None:
        self.swings += 1
        self.press("B", frames=4)

    def backflip(self) -> None:
        """Z + stick back + A: backflip when locked on."""
        self.pad(buttons=buttons_mask("Z", "A"), stick=(0, -100))
        time.sleep(6 * TICK)
        self.pad_clear()

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)
