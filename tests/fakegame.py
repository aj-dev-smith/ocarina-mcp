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
        # Overlay store. Enough of DojoOverlay.cpp's contract to test the
        # pusher offline: labels validated, a set replaces the whole set.
        # `applies` here bumps on set — the real "did the main thread turn
        # it into nametags" half only the real game can prove.
        self.overlay_labels: list[dict] = []
        self.overlay_applies = 0
        # docs/27 instrument state: C-button assignments (ITEM_NONE empty),
        # nut count, and the staged-save round trip.
        self.equips_c = [0xFF, 0xFF, 0xFF]
        self.nuts = 5
        self.saves = 0
        self.save_pending = False
        # docs/28 instrument state: the equipment masks and the staged
        # equip_gear round trip. worn 0x11 / owned 0x33 = a Kokiri sword
        # and a Deku shield worn, with the second sword/shield row owned
        # too (so a test can equip something not already on).
        self.equip_b = 0x3B
        self.worn = 0x11
        self.owned = 0x33
        self.equip_pending = False

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
                    "key": 0xBABA, "pos": [b["x"], 0.0, b["z"]], "yaw": 0,
                    "dist_xz": dist, "dist_y": 0.0,
                    "yaw_to_player": yaw_to_player,
                    "health": max(b["health"], 0), "targeted": False, "frozen": 0,
                    # The clearing is open ground; the baba is in view from
                    # the start (sight bits per the 2026-08-02 instrument).
                    "drawn": True, "sighted": True,
                })
            state = {
                "save_loaded": True, "scene": 85, "health": max(p["health"], 0),
                "health_capacity": 48, "magic": 0, "rupees": 0, "is_child": True,
                "msg_mode": 0, "paused": self.paused, "frame": self.frame,
                "gameplay_frames": self.gameplay_frames,
                "player": {"pos": [p["x"], 0.0, p["z"]], "yaw": 0,
                           "speed_xz": 0.0,
                           "state_flags1": PLAYER_STATE1_DEAD if dead else 0,
                           "state_flags2": 0, "invincibility": 0},
                "actors": actors, "actor_count_total": len(actors),
                # The 2026-08-04 instrument blocks (docs/27). Sticks and
                # nuts in slots 0/1, everything else empty; equips mirror
                # what assign_c wrote.
                "pause": {"state": 0, "page": 0},
                "equips": {"b": self.equip_b, "c_left": self.equips_c[0],
                           "c_down": self.equips_c[1],
                           "c_right": self.equips_c[2],
                           "worn": self.worn, "owned": self.owned},
                "inventory": {"items": [0x00, 0x01] + [0xFF] * 22,
                              "ammo": [3, self.nuts] + [0] * 14},
            }
            return state

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

    def handle_overlay(self, payload: dict) -> dict:
        sub = payload.get("sub", "set")
        if sub == "get":
            return {"labels": [dict(l) for l in self.overlay_labels],
                    "applies": self.overlay_applies,
                    "resolved": len(self.overlay_labels), "missing": 0}
        if sub == "clear":
            self.overlay_labels = []
            self.overlay_applies += 1
            return {}
        if sub != "set":
            return {"status": "failure", "error": f"unknown overlay sub {sub}"}
        labels = payload.get("labels")
        if not isinstance(labels, list) or len(labels) > 32:
            return {"status": "failure",
                    "error": "overlay requires 'labels' (at most 32)"}
        for label in labels:
            if (not isinstance(label, dict)
                    or not isinstance(label.get("key"), int) or label["key"] < 0
                    or not isinstance(label.get("text"), str)):
                return {"status": "failure",
                        "error": "each label needs an unsigned 'key' and string 'text'"}
            color = label.get("color")
            if color is not None and (not isinstance(color, list) or len(color) != 3):
                return {"status": "failure", "error": "label 'color' must be [r, g, b]"}
        self.overlay_labels = [dict(l) for l in labels]
        self.overlay_applies += 1
        return {"labels_staged": len(labels)}

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
        elif op == "overlay":
            res.update(self.handle_overlay(payload))
        elif op == "pause":
            self.paused = bool(payload.get("on", True))
        elif op == "tick":
            # Frame-advance while frozen: only the logic clock moves.
            if self.paused:
                self.gameplay_frames += int(payload.get("n", 1))
        elif op == "events":
            pass  # accepted, no-op in the fake
        elif op == "save":
            # The real op stages onto the frame hook and answers try_again
            # first; the fake models one round of that so the poll loop's
            # try_again path is exercised over real pipes.
            if not self.save_pending:
                self.save_pending = True
                res["status"] = "try_again"
            else:
                self.save_pending = False
                self.saves += 1
                res["saved"] = True
        elif op == "assign_c":
            button = payload.get("button", -1)
            if not 0 <= button <= 2:
                res["status"] = "failure"
                res["error"] = "button must be 0 (C-left), 1 (C-down), or 2 (C-right)"
            else:
                self.equips_c[button] = payload.get("item")
                res["item"] = payload.get("item")
                res["button"] = button
        elif op == "equip_gear":
            # The staged gear commit (docs/28), modelled to the same shape
            # as the real op: one try_again round, then the subscreen's own
            # gates, then the masked write. Refusals are NAMED — the
            # ocarina side passes them through untouched, so the exact
            # wording is the game side's to own.
            t, v = payload.get("equip_type", -1), payload.get("value", -1)
            if not (0 <= t <= 3 and 1 <= v <= 3):
                res["status"] = "failure"
                res["error"] = ("equip_type must be 0-3 (sword, shield, "
                                "tunic, boots) and value 1-3")
            elif t == 0 and v == 3:
                res["status"] = "failure"
                res["error"] = "the biggoron sword is not equippable here"
            elif not (self.owned & (1 << (t * 4 + v - 1))):
                res["status"] = "failure"
                res["error"] = "that equipment is not owned"
            elif not self.equip_pending:
                self.equip_pending = True
                res["status"] = "try_again"
            else:
                self.equip_pending = False
                self.worn = (self.worn & ~(0xF << (t * 4))) | (v << (t * 4))
                if t == 0:
                    self.equip_b = (0x3B, 0x3C, 0x3D)[v - 1]
                res["equipped"] = True
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
