"""StubLink: an in-process stand-in for GameLink, for offline unit tests.

Where the workshop's fakegame.py exercises the real TCP plumbing, this
answers Game's requests synchronously so runtime/executor/server tests
run in-process and deterministically. It faithfully models the one thing
freeze logic depends on: TWO counters — `frame` always advances,
`gameplay_frames` only while unpaused (workshop docs/08 §1).
"""

from __future__ import annotations

import base64

from ocarina.protocol import ACTORCAT_ENEMY


def frame_bytes(width: int, height: int) -> bytes:
    """A recognisable RGBA8 test frame: every pixel's red channel is its
    index, so a flipped/short/misaligned buffer shows up as wrong pixels
    rather than as a plausible picture."""
    out = bytearray()
    for i in range(width * height):
        out += bytes((i & 0xFF, 0x20, 0x80, 0xFF))
    return bytes(out)


def canned_frame(width: int, height: int, full: tuple | None = None) -> dict:
    """The `screenshot` op's success reply, exactly as AgentLink builds it."""
    fw, fh = full or (width, height)
    return {"format": "rgba8", "width": width, "height": height,
            "full_width": fw, "full_height": fh,
            "pixels": base64.b64encode(frame_bytes(width, height)).decode()}


def baba_actor(dist_xz: float = 300.0, health: int = 2,
               sighted: bool = True, key: int = 111,
               actor_id: int = 0x0055) -> dict:
    return {"id": actor_id, "cat": ACTORCAT_ENEMY, "params": 0, "key": key,
            "pos": [0.0, 0.0, dist_xz], "yaw": 0, "dist_xz": dist_xz,
            "dist_y": 0.0, "yaw_to_player": 0x8000, "health": health,
            "targeted": False, "frozen": 0, "drawn": sighted,
            "sighted": sighted}


class StubLink:
    def __init__(self):
        self._connected = True
        self.paused = False
        self.frame = 0
        self.gameplay_frames = 0
        self._events: list = []
        self.requests: list = []
        self.saves = 0                  # completed `save` ops (docs/27)
        self.save_script: list = []     # queued save-op replies for tests
        self.equips_sent: list = []     # equip_gear payloads seen (docs/28)
        self.equip_script: list = []    # queued equip_gear replies for tests
        #: The canned frame the `screenshot` op hands back: a 4x3 RGBA8
        #: window with a distinguishable first pixel, base64'd exactly as
        #: the instrument does. `screenshot_script` queues replies for the
        #: failure paths (unknown op, backend refusal, short payload).
        self.screenshot_size = (4, 3)
        self.screenshot_script: list = []
        #: The dev harness ops (docs/33, `--dev-tools` only): staged like
        #: save/equip_gear and scriptable for the refusal paths. The
        #: entrance table holds real indices (soh entrance_table.h)
        #: against this stub's one world; `warp_delay_polls` is how many
        #: state reads pass before the scene actually becomes the new
        #: one, so the arrival poll is exercised rather than assumed.
        self.dev_sent: list = []
        self.teleport_script: list = []
        self.warp_script: list = []
        self.give_script: list = []
        #: The dungeonItems row for the current dungeon (the docs/34
        #: rider): present on state replies only in dungeon-indexed
        #: scenes, exactly like the real payload. small_keys -1 is the
        #: game's "counter never started".
        self.dungeon_items = {"map": False, "compass": False,
                              "boss_key": False, "small_keys": -1}
        self.entrance_table = {529: 85, 0: 0, 626: 52}
        self.warp_delay_polls = 1
        self.floor_y = 0.0              # a teleport below the floor snaps up
        self._warp_pending = None       # (scene, polls_left)
        #: The DEV_FW_PATCH half (0.12.2): teleport rides the game's own
        #: Farore's Wind respawn path, so it STAGES a scene reload like a
        #: warp — the reply is the respawn record's word at staging time
        #: (requested position, resolved room and yaw), and the world
        #: arrives `warp_delay_polls` state reads later with `loads`
        #: ticked. `entrance_index` is the save's current entranceIndex:
        #: put it outside the table to model the -19 refusal (Link
        #: standing in a grotto/shop return, with no entrance to respawn
        #: through).
        self._teleport_pending = None   # (pos, room, yaw, polls_left)
        self.entrance_index = 529
        self.entrance_max = 1556        # the game's ENTR_MAX
        #: The DEV_ROOM_PATCH half (the evening live pass): the state
        #: carries `loads` (bumped on EVERY play-state init, same-scene
        #: reloads included) and `room`, and teleport takes a room. A
        #: test models an OLD instrument by deleting `world["loads"]` /
        #: `world["room"]` — the counter is only bumped if it is there,
        #: so the deletion stays deleted.
        self.rooms = (0, 1, 2)          # this stub's one scene's rooms
        #: Called with (payload, self) on every pad op — how a test scripts
        #: a shop: the game answers a stick nudge or an A press by moving
        #: the message box on, exactly as En_Ossan's state machine does.
        self.pad_hook = None
        # Mutable world the tests poke at; merged into every state reply.
        self.world = {
            "save_loaded": True, "scene": 85, "loads": 1, "room": 0,
            "health": 48,
            "health_capacity": 48, "sticks": 0, "nuts": 0, "rupees": 0,
            "msg_mode": 0, "camera_yaw": 0, "focus_actor": 0,
            "player": {"pos": [0.0, 0.0, 0.0], "yaw": 0, "speed_xz": 0.0,
                       "state_flags1": 0, "state_flags2": 0},
            "actors": [],
        }

    # -- GameLink surface ----------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected

    def drain_events(self) -> list:
        out, self._events = self._events, []
        return out

    def push_wire(self, msg: dict) -> None:
        """Tests inject wire messages (agent_event / hook shapes) here."""
        self._events.append(msg)

    def _dungeon_indexed(self) -> bool:
        """The real payload's predicate (Map_Init's dungeon case list):
        scenes 0x00-0x10 plus the boss arenas 0x11-0x18 — contiguous, so
        one range here."""
        scene = self.world.get("scene")
        return isinstance(scene, int) and 0 <= scene <= 0x18

    def _stage_teleport(self, payload: dict) -> tuple:
        """Write the respawn record and start the reload clock. Returns
        the (position, room, yaw) it resolved — room and yaw default to
        where Link is, which is what the real op does."""
        pos = [float(payload.get(k, 0.0)) for k in ("x", "y", "z")]
        pos[1] = max(pos[1], self.floor_y)      # the game's floor snap
        room = payload.get("room")
        if room is None:
            room = self.world.get("room", 0)
        yaw = payload.get("yaw")
        if yaw is None:
            yaw = self.world["player"].get("yaw", 0)
        self._teleport_pending = (pos, room, yaw, self.warp_delay_polls)
        return pos, room, yaw

    def request(self, payload: dict, timeout: float = 5.0) -> dict:
        self.requests.append(payload)
        self.frame += 1
        if not self.paused:
            self.gameplay_frames += 1
        res = {"type": "result", "status": "success"}
        op = payload.get("op")
        if op == "state":
            if self._warp_pending is not None:
                # The scene load lands a few reads later: an arrival that
                # were instant would let a broken poll pass.
                scene, left = self._warp_pending
                if left <= 0:
                    self.world["scene"], self._warp_pending = scene, None
                    # Play state init: the counter ticks even when the
                    # entrance led back into the scene we were in.
                    if "loads" in self.world:
                        self.world["loads"] += 1
                    if "room" in self.world:
                        self.world["room"] = 0
                else:
                    self._warp_pending = (scene, left - 1)
            if self._teleport_pending is not None:
                # A teleport is a scene reload too now: the world becomes
                # the respawn record a few reads later, and the play-state
                # counter ticks exactly as it does for a door.
                pos, room, yaw, left = self._teleport_pending
                if left <= 0:
                    self._teleport_pending = None
                    self.world["player"]["pos"] = list(pos)
                    self.world["player"]["yaw"] = yaw
                    if "loads" in self.world:
                        self.world["loads"] += 1
                    if "room" in self.world:
                        self.world["room"] = room
                else:
                    self._teleport_pending = (pos, room, yaw, left - 1)
            res.update(self.world)
            res["paused"] = self.paused
            res["frame"] = self.frame
            res["gameplay_frames"] = self.gameplay_frames
            if self._dungeon_indexed():
                res["dungeon_items"] = dict(self.dungeon_items)
        elif op == "pause":
            self.paused = bool(payload.get("on", True))
        elif op == "scan":
            res["rays"] = []
        elif op == "pad":
            # Choice-cursor model (docs/27): a vertical stick nudge moves
            # message.choice_index the way Message_HandleChoiceSelection
            # does — up (y+) decrements, down (y-) increments, clamped.
            stick = payload.get("stick")
            msg = self.world.get("message")
            if (not payload.get("clear") and stick and msg
                    and isinstance(msg.get("choice_index"), int)):
                top = max(len(msg.get("choices") or []) - 1, 0)
                if stick[1] <= -30:
                    msg["choice_index"] = min(top, msg["choice_index"] + 1)
                elif stick[1] >= 30:
                    msg["choice_index"] = max(0, msg["choice_index"] - 1)
            if self.pad_hook is not None:
                self.pad_hook(payload, self)
        elif op == "save":
            # Scriptable: tests queue {"status": ...} dicts; default saves.
            scripted = self.save_script.pop(0) if self.save_script else {"saved": True}
            res.update(scripted)
            if res.get("status") == "success" or "status" not in scripted:
                self.saves += 1
        elif op == "screenshot":
            scripted = (self.screenshot_script.pop(0)
                        if self.screenshot_script else None)
            if scripted is not None:
                res.update(scripted)
            else:
                w, h = self.screenshot_size
                res.update(canned_frame(w, h))
        elif op == "assign_c":
            item, button = payload.get("item"), payload.get("button")
            key = ("c_left", "c_down", "c_right")[button]
            self.world.setdefault("equips", {})[key] = item
            res["item"], res["button"] = item, button
        elif op == "equip_gear":
            # The staged gear commit (docs/28). Scriptable like `save`;
            # the default models the game's own write: the worn mask's
            # nibble for the row, plus the B button on the sword row.
            self.equips_sent.append(dict(payload))
            scripted = (self.equip_script.pop(0) if self.equip_script
                        else {"equipped": True})
            res.update(scripted)
            if scripted.get("status", "success") == "success":
                equips = self.world.setdefault("equips", {})
                t, v = payload["equip_type"], payload["value"]
                worn = int(equips.get("worn", 0))
                equips["worn"] = (worn & ~(0xF << (t * 4))) | (v << (t * 4))
                if t == 0:
                    equips["b"] = (0x3B, 0x3C, 0x3D)[v - 1]
        elif op == "teleport":
            self.dev_sent.append(dict(payload))
            scripted = (self.teleport_script.pop(0) if self.teleport_script
                        else None)
            room = payload.get("room")
            if scripted is not None:
                res.update(scripted)
                if res.get("status", "success") == "success":
                    # A scripted success is still a STAGED reload: the op
                    # answers now, the world arrives later.
                    self._stage_teleport(payload)
            elif not 0 <= self.entrance_index < self.entrance_max:
                # -19: the save's entranceIndex is a grotto/shop return
                # sentinel, so there is no entrance to respawn through.
                res["status"] = "failure"
                res["code"] = -19
                res["error"] = (
                    f"entrance out of range: the current entrance index "
                    f"0x{self.entrance_index:04X} is outside the entrance "
                    f"table (0-{self.entrance_max - 1})")
            elif room is not None and room not in self.rooms:
                res["status"] = "failure"
                res["code"] = -18
                res["error"] = (f"no room {room} in this scene "
                                f"(valid rooms are 0-{max(self.rooms)})")
            else:
                pos, resolved_room, yaw = self._stage_teleport(payload)
                # Staging-time truth: the requested position (the floor
                # snap happens on arrival, in the world) plus the room and
                # yaw actually written into the respawn record.
                res.update({"x": float(payload.get("x", 0.0)),
                            "y": float(payload.get("y", 0.0)),
                            "z": float(payload.get("z", 0.0)),
                            "room": resolved_room, "yaw": yaw})
        elif op == "give_dungeon_item":
            self.dev_sent.append(dict(payload))
            scripted = self.give_script.pop(0) if self.give_script else None
            if scripted is not None:
                res.update(scripted)
            elif payload.get("item") not in ("map", "compass", "boss_key"):
                res["status"] = "failure"
                res["error"] = "bad args"
            elif not self._dungeon_indexed():
                res["status"] = "failure"
                res["code"] = -20
                res["error"] = ("not in a dungeon-indexed scene — no "
                                "dungeonItems row applies here")
            else:
                self.dungeon_items[payload["item"]] = True
                res["dungeon_index"] = self.world["scene"]
        elif op == "warp":
            self.dev_sent.append(dict(payload))
            scripted = self.warp_script.pop(0) if self.warp_script else None
            entrance = payload.get("entrance")
            if scripted is not None:
                res.update(scripted)
            elif entrance not in self.entrance_table:
                res["status"] = "failure"
                res["error"] = f"no such entrance {entrance}"
            else:
                self._warp_pending = (self.entrance_table[entrance],
                                      self.warp_delay_polls)
                res.update({"entrance": entrance, "staged": True})
        # events / tick / hud: accepted, no-op
        return res
