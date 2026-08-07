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

import base64
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
                                            ("warden", "navigator", "strategist", "agent")}
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
        # The screenshot op (2026-08-07 AgentLink patch): a tiny canned
        # window, big enough for the wire's shape and the PNG round trip,
        # small enough to keep the fixture readable. Native is 8x6 and the
        # default cap folds it to 4x3, so the downscale reporting is
        # exercised over real pipes too.
        self.screen_size = (8, 6)
        self.shot_pending = False
        # The dev harness ops (docs/33; --dev-tools only). Both are
        # STAGED, like save/equip_gear. The entrance "table" holds real
        # indices (soh entrance_table.h) against this fake's one room,
        # so a test reads like the live one: 529 is Kokiri Forest, which
        # is where the fake already is (the same-scene case a scene
        # comparison genuinely cannot observe), 0 is Inside the Deku
        # Tree, 626 is Link's house. `warp_delay_s = None` is the honest
        # never-arrives path (the op accepts, the world does not move).
        # `loads` and `room` are the DEV_ROOM_PATCH half (the same
        # evening's live pass): loads ticks on EVERY play-state init, so
        # a warp back into the current scene is observable, and teleport
        # takes an optional room because rooms only load through door
        # actors.
        self.scene = 85
        self.entrance_table = {529: 85, 0: 0, 626: 52}
        self.warp_delay_s = 0.5
        self.warps: list = []
        self.teleports: list = []
        self.teleport_rooms: list = []  # the room arg per teleport (or None)
        self.teleport_pending = False
        self.warp_pending = False
        self._warp_at = None
        self._warp_scene = None
        self.loads = 1
        self.room = 0
        self.yaw = 0
        self.rooms = (0, 1, 2)          # like Kokiri Forest's three
        # The DEV_FW_PATCH half (0.12.2): teleport rides the game's own
        # Farore's Wind respawn path, so it STAGES a real scene reload
        # like a warp — the reply is the respawn record's word at staging
        # time and the world arrives a beat later with `loads` ticked.
        # `entrance_index` is the save's current entranceIndex; outside
        # the table it is the -19 refusal (a grotto/shop return, with no
        # entrance to respawn through).
        self._teleport_at = None
        self._teleport_to = None        # (pos, room, yaw)
        self.entrance_index = 529
        self.entrance_max = 1556        # the game's ENTR_MAX

    def reset_world(self) -> None:
        self.player = {"x": 0.0, "y": 0.0, "z": 0.0, "health": 48}  # 3 hearts
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
        # A staged warp becomes the new scene a beat later, like a real
        # scene load: the op's "staged" answer is never the arrival.
        if self._warp_at is not None and time.time() >= self._warp_at:
            self.scene, self._warp_at = self._warp_scene, None
            # Play state init: the counter ticks whether or not the scene
            # id is a different number, and the arrival room is 0.
            self.loads += 1
            self.room = 0
        # A staged teleport lands the same way — it IS a scene reload,
        # through the respawn record rather than the entrance table.
        if self._teleport_at is not None and time.time() >= self._teleport_at:
            pos, room, yaw = self._teleport_to
            self._teleport_at, self._teleport_to = None, None
            self.player["x"], self.player["z"] = pos[0], pos[2]
            self.player["y"] = max(pos[1], 0.0)      # the fake's floor
            self.room, self.yaw = room, yaw
            self.loads += 1
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
                        {"type": "agent_event", "event": "enemy_defeat",
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
                "save_loaded": True, "scene": self.scene,
                "loads": self.loads, "room": self.room,
                "health": max(p["health"], 0),
                "health_capacity": 48, "magic": 0, "rupees": 0, "is_child": True,
                "msg_mode": 0, "paused": self.paused, "frame": self.frame,
                "gameplay_frames": self.gameplay_frames,
                "player": {"pos": [p["x"], p.get("y", 0.0), p["z"]],
                           "yaw": self.yaw,
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

    def render_frame(self, max_width: int) -> dict:
        """The screenshot op's success reply: raw RGBA8, base64, plus BOTH
        sizes so a downscaled frame can never read as native."""
        w, h = self.screen_size
        factor = 1
        if max_width and w > max_width:
            factor = -(-w // max_width)
            while factor > 1 and (w // factor == 0 or h // factor == 0):
                factor -= 1
        # A red ramp across the frame — a flipped or misaligned buffer shows
        # up as wrong pixels rather than as a plausible picture.
        src = [bytes((i & 0xFF, 0x20, 0x80, 0xFF)) for i in range(w * h)]
        out = bytearray()
        for y in range(h // factor):
            for x in range(w // factor):
                acc = [0, 0, 0, 0]
                for sy in range(factor):
                    for sx in range(factor):
                        px = src[(y * factor + sy) * w + x * factor + sx]
                        for c in range(4):
                            acc[c] += px[c]
                out += bytes(v // (factor * factor) for v in acc)
        return {"format": "rgba8", "width": w // factor, "height": h // factor,
                "full_width": w, "full_height": h,
                "pixels": base64.b64encode(bytes(out)).decode()}

    def handle(self, payload: dict) -> dict:
        res = {"type": "result", "id": payload.get("id"), "status": "success"}
        if payload.get("type") == "command":
            return res
        if payload.get("type") != "agent":
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
        elif op == "screenshot":
            # Staged like the others: capture lives on the frame hook, and
            # the real Metal path defers a frame, so the first poll always
            # answers try_again. Downscaling is the instrument's job (the
            # wire carries raw RGBA), so the fake box-averages too.
            if not self.shot_pending:
                self.shot_pending = True
                res["status"] = "try_again"
            else:
                self.shot_pending = False
                res.update(self.render_frame(payload.get("max_width", 0)))
        elif op == "teleport":
            # The dev harness's respawn-path teleport (docs/33, rebuilt
            # 0.12.2). STAGED like save/equip_gear — the respawn record is
            # written on the frame hook — so the first poll answers
            # try_again, and the success reply is STAGING-time truth: the
            # requested position plus the room and yaw actually written.
            # Arrival is a scene reload away, which is what the ocarina
            # side polls the world's `loads` counter for.
            coords = [payload.get(k) for k in ("x", "y", "z")]
            room, yaw = payload.get("room"), payload.get("yaw")
            if self._warp_at is not None or self._teleport_at is not None:
                res["status"] = "failure"
                res["error"] = "a scene transition is already in progress"
            elif not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                         for v in coords):
                res["status"] = "failure"
                res["error"] = "teleport needs numeric x, y and z"
            elif not 0 <= self.entrance_index < self.entrance_max:
                # -19: no entrance to respawn through (a grotto or shop
                # return sentinel), so the whole op is meaningless here.
                res["status"] = "failure"
                res["code"] = -19
                res["error"] = (
                    f"entrance out of range: the current entrance index "
                    f"0x{self.entrance_index:04X} is outside the entrance "
                    f"table (0-{self.entrance_max - 1})")
            elif room is not None and (not isinstance(room, int)
                                       or isinstance(room, bool)
                                       or room not in self.rooms):
                # The room refusal is BY NAME, with the range: only the
                # game knows how many rooms this scene has.
                res["status"] = "failure"
                res["code"] = -18
                res["error"] = (f"no room {room} in this scene "
                                f"(valid rooms are 0-{max(self.rooms)})")
            elif not self.teleport_pending:
                self.teleport_pending = True
                res["status"] = "try_again"
            else:
                self.teleport_pending = False
                with self.lock:
                    self.teleports.append([float(v) for v in coords])
                    self.teleport_rooms.append(room)
                    # Room and yaw default to where Link is; both go into
                    # the respawn record, which is what the reply echoes.
                    resolved_room = self.room if room is None else room
                    resolved_yaw = self.yaw if yaw is None else int(yaw)
                    self._teleport_to = ([float(v) for v in coords],
                                         resolved_room, resolved_yaw)
                    self._teleport_at = time.time() + (self.warp_delay_s or 0.0)
                    res.update({"x": float(coords[0]), "y": float(coords[1]),
                                "z": float(coords[2]), "room": resolved_room,
                                "yaw": resolved_yaw})
        elif op == "warp":
            # Staged too, and answering only that the transition was
            # REQUESTED: arrival is a scene load away, which is what the
            # ocarina side polls the world for.
            entrance = payload.get("entrance")
            if self._warp_at is not None or self._teleport_at is not None:
                res["status"] = "failure"
                res["error"] = "a scene transition is already in progress"
            elif (not isinstance(entrance, int) or isinstance(entrance, bool)
                    or not 0 <= entrance < 1556):
                res["status"] = "failure"
                res["error"] = "entrance must be an index in [0, 1556)"
            elif entrance not in self.entrance_table:
                res["status"] = "failure"
                res["error"] = f"no such entrance 0x{entrance:04X}"
            elif not self.warp_pending:
                self.warp_pending = True
                res["status"] = "try_again"
            else:
                self.warp_pending = False
                with self.lock:
                    self.warps.append(entrance)
                    if self.warp_delay_s is not None:
                        self._warp_scene = self.entrance_table[entrance]
                        self._warp_at = time.time() + self.warp_delay_s
                res.update({"entrance": entrance, "staged": True})
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
