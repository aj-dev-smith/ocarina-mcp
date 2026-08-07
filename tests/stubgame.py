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
        #: Called with (payload, self) on every pad op — how a test scripts
        #: a shop: the game answers a stick nudge or an A press by moving
        #: the message box on, exactly as En_Ossan's state machine does.
        self.pad_hook = None
        # Mutable world the tests poke at; merged into every state reply.
        self.world = {
            "save_loaded": True, "scene": 85, "health": 48,
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

    def request(self, payload: dict, timeout: float = 5.0) -> dict:
        self.requests.append(payload)
        self.frame += 1
        if not self.paused:
            self.gameplay_frames += 1
        res = {"type": "result", "status": "success"}
        op = payload.get("op")
        if op == "state":
            res.update(self.world)
            res["paused"] = self.paused
            res["frame"] = self.frame
            res["gameplay_frames"] = self.gameplay_frames
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
        # events / tick / hud: accepted, no-op
        return res
