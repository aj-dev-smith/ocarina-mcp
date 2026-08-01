"""A stand-in for Ship of Harkinian: speaks Sail+DojoLink over TCP and
simulates one room with Link and a Deku Baba at 20 Hz.

Ported from the workshop (oot-dojo ootdojo/fakegame.py) for plumbing tests
ONLY — its combat constants are invented (never tune against it).

Exists so the dojo plumbing (framing, request/response, savestates, trials)
can be exercised end-to-end before the real build is up. The combat model is
crude but honest to the failure modes: blind approach eats contact damage;
baiting the lunge does not.
"""

from __future__ import annotations

import json
import math
import random
import socket
import threading
import time

from ocarina.protocol import (ACTOR_EN_DEKUBABA, ACTORCAT_ENEMY, BTN_B, BTN_Z,
                       DEFAULT_PORT, PLAYER_STATE1_DEAD)

TICK = 1.0 / 20.0

BABA_IDLE, BABA_WINDUP, BABA_LUNGE, BABA_RECOVER = range(4)


class FakeGame:
    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT):
        self.host, self.port = host, port
        self.lock = threading.Lock()
        self.reset_world()
        self.savestates: dict[int, dict] = {}
        self.pad_buttons = 0
        self.stick = (0, 0)
        self.pad_active = False
        self.frame = 0
        # TWO counters, deliberately (docs/08 §1): `frame` is the outer
        # GameState_Update loop and keeps running while gameplay is frozen;
        # `gameplay_frames` is the logic clock inside Play_Update and is the
        # only one that can observe a pause. The fake models the difference
        # so that code measuring a freeze can be tested at all — get this
        # wrong against the real game and a pause produces a false PASS.
        self.gameplay_frames = 0
        self.paused = False
        self.running = True
        self.b_was_down = False
        self.pending_events: list = []
        # Agent HUD store. Enough of DojoHud.cpp's contract to test the
        # pusher offline: panel names are validated, sets replace, ticker
        # appends. Nothing is drawn — that half only the real game can prove.
        self.hud_panels: dict[str, list] = {p: [] for p in
                                            ("warden", "navigator", "strategist", "dojo")}
        self.hud_ticker: list[str] = []

    def reset_world(self) -> None:
        self.player = {"x": 0.0, "z": 0.0, "health": 48}  # 3 hearts
        self.baba = {"x": 0.0, "z": 300.0, "health": 2, "state": BABA_IDLE,
                     "timer": 0, "alive": True}
        self.slash_cooldown = 0

    # -- snapshot / restore ------------------------------------------------

    def snapshot(self) -> dict:
        with self.lock:
            return json.loads(json.dumps({"player": self.player, "baba": self.baba}))

    def restore(self, snap: dict) -> None:
        with self.lock:
            self.player = json.loads(json.dumps(snap["player"]))
            self.baba = json.loads(json.dumps(snap["baba"]))

    # -- simulation --------------------------------------------------------

    def sim_loop(self) -> None:
        while self.running:
            time.sleep(TICK)
            with self.lock:
                self._step()

    def _step(self) -> None:
        self.frame += 1          # outer loop: runs even while frozen
        if self.paused:
            return
        self.gameplay_frames += 1
        p, b = self.player, self.baba

        if p["health"] <= 0:
            return

        # Player movement (stick magnitude ~ walk speed; ~9 units/tick full tilt)
        if self.pad_active:
            sx, sy = self.stick
            mag = math.hypot(sx, sy)
            if mag > 15:
                speed = 9.0 * min(mag, 100) / 100.0
                # stick +y walks toward +z (camera behind Link, facing the baba)
                p["x"] += speed * sx / max(mag, 1)
                p["z"] += speed * sy / max(mag, 1)

        if self.slash_cooldown > 0:
            self.slash_cooldown -= 1

        # Slash on B press edge
        b_down = bool(self.pad_active and (self.pad_buttons & BTN_B))
        if b_down and not self.b_was_down and self.slash_cooldown == 0:
            self.slash_cooldown = 8
            if b["alive"] and self._dist() < 120:
                vulnerable = b["state"] in (BABA_RECOVER, BABA_IDLE)
                b["health"] -= 2 if vulnerable else 1
                if b["health"] <= 0:
                    b["alive"] = False
                    # The real DojoLink forwards OnEnemyDefeat here. The fake
                    # must too, or it cannot validate kill-event predicates —
                    # and "baba gone from the actor list" is exactly the
                    # ambiguous signal that let a fleeing skill score a win.
                    self.pending_events.append(
                        {"type": "dojo_event", "event": "enemy_defeat",
                         "id": ACTOR_EN_DEKUBABA, "params": 0})
        self.b_was_down = b_down

        # Baba brain
        if not b["alive"]:
            return
        d = self._dist()
        b["timer"] -= 1
        if b["state"] == BABA_IDLE and d < 160:
            b["state"], b["timer"] = BABA_WINDUP, 6
        elif b["state"] == BABA_WINDUP and b["timer"] <= 0:
            b["state"], b["timer"] = BABA_LUNGE, 6
            # Lunge: snap toward player; contact damage if close.
            if d < 130:
                p["health"] -= 8  # one heart = 16; half-heart bites twice
        elif b["state"] == BABA_LUNGE and b["timer"] <= 0:
            b["state"], b["timer"] = BABA_RECOVER, 24  # ~1.2 s vulnerable window
        elif b["state"] == BABA_RECOVER and b["timer"] <= 0:
            b["state"] = BABA_IDLE

    def _dist(self) -> float:
        return math.hypot(self.player["x"] - self.baba["x"],
                          self.player["z"] - self.baba["z"])

    # -- protocol ----------------------------------------------------------

    def state_json(self) -> dict:
        with self.lock:
            p, b = self.player, self.baba
            dead = p["health"] <= 0
            actors = []
            if b["alive"]:
                dx, dz = b["x"] - p["x"], b["z"] - p["z"]
                dist = math.hypot(dx, dz)
                # effective dist shrinks during lunge (head extends toward player)
                if b["state"] == BABA_LUNGE:
                    dist = max(30.0, dist - 90.0)
                yaw_to_player = int((math.atan2(-dx, -dz) / math.pi) * 0x8000) & 0xFFFF
                actors.append({
                    "id": ACTOR_EN_DEKUBABA, "cat": ACTORCAT_ENEMY, "params": 0,
                    "pos": [b["x"], 0.0, b["z"]], "yaw": 0,
                    "dist_xz": dist, "dist_y": 0.0,
                    "yaw_to_player": yaw_to_player,
                    "health": max(b["health"], 0), "targeted": False, "frozen": 0,
                })
            return {
                "save_loaded": True, "scene": 85, "health": max(p["health"], 0),
                "health_capacity": 48, "magic": 0, "rupees": 0, "is_child": True,
                "msg_mode": 0, "paused": self.paused, "frame": self.frame,
                "gameplay_frames": self.gameplay_frames,
                "player": {"pos": [p["x"], 0.0, p["z"]], "yaw": 0,
                           "speed_xz": 0.0,
                           "state_flags1": PLAYER_STATE1_DEAD if dead else 0,
                           "state_flags2": 0, "invincibility": 0},
                "actors": actors, "actor_count_total": len(actors),
            }

    def handle_hud(self, payload: dict) -> dict:
        sub = payload.get("sub", "set")
        if sub == "get":
            return {"panels": dict(self.hud_panels), "ticker": list(self.hud_ticker),
                    "visible": True, "draws": 0}
        if sub == "clear":
            self.hud_panels = {p: [] for p in self.hud_panels}
            self.hud_ticker = []
            return {}
        if sub == "show":
            return {}
        if sub != "set":
            return {"status": "failure", "error": f"unknown hud sub {sub}"}
        for name, fields in (payload.get("panels") or {}).items():
            if name not in self.hud_panels:
                return {"status": "failure", "error": f"unknown hud panel {name}"}
            self.hud_panels[name] = [[str(k), str(v)] for k, v in fields]
        self.hud_ticker.extend(payload.get("ticker") or [])
        del self.hud_ticker[:-128]
        return {}

    def handle(self, payload: dict) -> dict:
        res = {"type": "result", "id": payload.get("id"), "status": "success"}
        if payload.get("type") == "command":
            return res
        if payload.get("type") != "dojo":
            res["status"] = "failure"
            return res

        op = payload.get("op")
        if op == "state":
            res.update(self.state_json())
        elif op == "pad":
            if payload.get("clear"):
                self.pad_active, self.pad_buttons, self.stick = False, 0, (0, 0)
            else:
                self.pad_buttons = payload.get("buttons", 0)
                s = payload.get("stick", [0, 0])
                self.stick = (s[0], s[1])
                self.pad_active = True
        elif op == "savestate":
            slot, sub = payload.get("slot"), payload.get("sub")
            if sub == "save":
                self.savestates[slot] = self.snapshot()
            elif sub == "load":
                if slot in self.savestates:
                    self.restore(self.savestates[slot])
                else:
                    res["status"] = "failure"
                    res["error"] = "state slot empty"
        elif op == "hud":
            res.update(self.handle_hud(payload))
        elif op == "pause":
            self.paused = bool(payload.get("on", True))
        elif op == "tick":
            # Frame-advance while frozen: only the logic clock moves.
            if self.paused:
                self.gameplay_frames += int(payload.get("n", 1))
        elif op == "events":
            pass  # accepted, no-op in the fake
        else:
            res["status"] = "failure"
            res["error"] = f"unknown op {op}"
        return res

    # -- client loop (the game connects OUT to the dojo, like Sail does) ---

    def run(self) -> None:
        threading.Thread(target=self.sim_loop, daemon=True).start()
        sock = socket.create_connection((self.host, self.port))
        buf = b""
        while self.running:
            data = sock.recv(4096)
            if not data:
                break
            buf += data
            while b"\0" in buf:
                raw, buf = buf.split(b"\0", 1)
                if not raw.strip():
                    continue
                payload = json.loads(raw.decode())
                response = self.handle(payload)
                sock.sendall(json.dumps(response).encode() + b"\0")
                # Flush queued events unsolicited, as DojoLink's PushEvent does.
                with self.lock:
                    queued, self.pending_events = self.pending_events, []
                for ev in queued:
                    ev = dict(ev, frame=self.frame)
                    sock.sendall(json.dumps(ev).encode() + b"\0")
