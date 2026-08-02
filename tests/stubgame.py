"""StubLink: an in-process stand-in for GameLink, for offline unit tests.

Where the workshop's fakegame.py exercises the real TCP plumbing, this
answers Game's requests synchronously so runtime/executor/server tests
run in-process and deterministically. It faithfully models the one thing
freeze logic depends on: TWO counters — `frame` always advances,
`gameplay_frames` only while unpaused (workshop docs/08 §1).
"""

from __future__ import annotations

from ocarina.protocol import ACTORCAT_ENEMY


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
        """Tests inject wire messages (dojo_event / hook shapes) here."""
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
        # pad / events / tick / hud: accepted, no-op
        return res
