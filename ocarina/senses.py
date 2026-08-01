"""The sensorium: the curated state digest, its schema, and the event
grammar — the narration layer's two big artifacts (SURFACE.md open
question 5; MACHINE.md names it this file's open question too).

THIS IS v0 SCAFFOLDING, and says so. The digest schema is "the single
largest curation artifact; expect it to grow one region ahead of the
player forever" (SURFACE.md). What is here is the smallest honest
sensorium for the Kokiri Forest / Deku Tree frontier, built from what the
DojoLink wire already carries. Every field must pass the curation rules:

- **Presented, not computed** — each field answers "what audiovisual
  presentation is this the text form of?" (noted per field below).
- **Official names from first sighting** (SURFACE.md naming principle,
  2026-08-01) — the name is the text form of the visual gestalt.
- **Vocabulary, not grammar** — the event categories below are the closed
  grammar; new regions add cue/kind values, never categories, without
  review.

Known v0 honesty gaps, flagged rather than hidden:
- `spawn` is emitted from OnActorInit, which fires for the whole room at
  scene load — that is "entered the world", not "came into view". A
  sighted player does not see through walls; visibility gating is
  frontier curation work. (Filed here so watching Expedition Zero can
  price it.)
- `sfx`/`bgm_change`/`telegraph` categories exist in the grammar but have
  NO producers yet — the DojoLink patch does not tap the audio or
  actionFunc hooks. Senses before the frontier crosses them.
- Scene is a numeric id, not a place name. Naming places is the same
  principle as naming actors; the table just doesn't exist yet.
"""

from __future__ import annotations

import json
from pathlib import Path

from .protocol import (ACTORCAT_ENEMY, PLAYER_STATE1_CLIMBING_LADDER,
                       PLAYER_STATE1_DEAD, PLAYER_STATE1_ON_A_WALL)

# -- official names (the open vocabulary; grows one region ahead) ------------

#: Actor id -> official name. The name carries no more game knowledge than
#: the sprite already gave a sighted player (SURFACE.md).
OFFICIAL_NAMES = {
    0x0055: "deku_baba",
    0x00C7: "withered_deku_baba",
    0x0013: "keese",           # all variants; params select fly/perch/fire/ice
    0x0037: "skulltula",
    0x0095: "skullwalltula",
}


def actor_name(actor_id: int) -> str:
    """Official name, or an honest placeholder that flags the coverage gap.

    An `unknown_0x____` in the narration is an instrument item ("I couldn't
    see what that was"), never silently dropped — under-sensing is
    blindness, found by watching.
    """
    return OFFICIAL_NAMES.get(actor_id, f"unknown_0x{actor_id:04X}")


# -- the state digest --------------------------------------------------------

#: The digest schema. Guards' `state.*` paths are load-checked against
#: this (machine.py step 3), so the schema being explicit is what makes
#: the check worth anything. Leaves are types; dicts nest. A nullable
#: entity (nearest_enemy) is absent from the digest when not present and
#: resolves to ABSENT in guards.
SCHEMA = {
    "scene": int,               # where we are (numeric id; naming pending)
    "hearts": float,            # the heart HUD
    "hearts_max": float,        # ditto
    "sticks": int,              # the item HUD counter
    "nuts": int,                # ditto
    "rupees": int,              # ditto
    "dialogue_open": bool,      # a text box is on screen
    "player": {
        "climbing": bool,       # Link visibly on a vine/ladder
        "on_wall": bool,        # climbing, mounting, or hanging
        "dead": bool,           # the death animation
    },
    "nearest_enemy": {          # the closest visible living enemy
        "kind": str,            # official name (the visual gestalt as text)
        "dist": float,          # apparent distance, xz — a PROJECTION
        "above": float,         # height over Link (docs/08 §17: read it)
    },
    "enemies": int,             # living enemies in view
}


def check_path(path: tuple) -> str | None:
    """None if `path` names a schema field; else the diagnostic string."""
    node = SCHEMA
    for i, part in enumerate(path):
        if not isinstance(node, dict):
            return (f"state.{'.'.join(path[:i])} is a leaf field; "
                    f"it has no {part!r}")
        if part not in node:
            known = ", ".join(sorted(node))
            where = "state" if i == 0 else f"state.{'.'.join(path[:i])}"
            return f"{where} has no field {part!r} (known: {known})"
        node = node[part]
    return None


def digest(state: dict) -> dict:
    """Raw DojoLink snapshot -> the curated digest guards and the mind see.

    Behaviors see the raw snapshot server-side at 20 Hz; this is the
    narration. Must match SCHEMA exactly — the load-time path check is
    only as good as this function's fidelity to it.
    """
    player = state.get("player") or {}
    flags1 = player.get("state_flags1", 0)
    enemies = [a for a in (state.get("actors") or [])
               if a.get("cat") == ACTORCAT_ENEMY and (a.get("health") or 0) > 0]
    out = {
        "scene": state.get("scene", -1),
        "hearts": state.get("health", 0) / 16.0,
        "hearts_max": state.get("health_capacity", 0) / 16.0,
        "sticks": state.get("sticks", 0),
        "nuts": state.get("nuts", 0),
        "rupees": state.get("rupees", 0),
        "dialogue_open": state.get("msg_mode", 0) != 0,
        "player": {
            "climbing": bool(flags1 & PLAYER_STATE1_CLIMBING_LADDER),
            "on_wall": bool(flags1 & PLAYER_STATE1_ON_A_WALL),
            "dead": bool(flags1 & PLAYER_STATE1_DEAD),
        },
        "enemies": len(enemies),
    }
    if enemies:
        near = min(enemies, key=lambda a: a.get("dist_xz", float("inf")))
        out["nearest_enemy"] = {
            "kind": actor_name(near.get("id", -1)),
            "dist": float(near.get("dist_xz", 0.0)),
            # dist_y is yDistToPlayer = player.y - actor.y (Actor_HeightDiff,
            # z_actor.c:1397): NEGATIVE when the actor is above Link. Negate
            # so `above` means what it says — verified live against the
            # room-0 skulltula (1072 up, wire said -1073) on first light,
            # 2026-08-01. The workshop's probe_room negates it identically.
            "above": -float(near.get("dist_y", 0.0)),
        }
    return out


# -- the event grammar -------------------------------------------------------

#: The closed grammar (SURFACE.md): world categories + machine events.
#: A new category is a rare, reviewed change — vocabulary is open, this
#: tuple is not.
WORLD_EVENTS = ("telegraph", "sfx", "bgm_change", "environment", "spawn",
                "despawn", "damage_taken", "damage_dealt", "actor_state",
                "pickup", "ui")
MACHINE_EVENTS = ("entered", "exited", "behavior_done", "behavior_aborted",
                  "wake", "journal", "directive", "escalation", "diagnostic")
ALL_EVENTS = WORLD_EVENTS + MACHINE_EVENTS


class SeenKinds:
    """First-sighting tracker for the `novel` field on spawn events —
    "this save file" scoped (SURFACE.md machine example), so it persists
    in the save-file repo, not in server memory. The server's live state
    is never the only copy.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)
        try:
            self._seen = set(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            self._seen = set()

    def sight(self, kind: str) -> bool:
        """True if this is the first sighting of `kind` this save file."""
        if kind in self._seen:
            return False
        self._seen.add(kind)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(sorted(self._seen)), encoding="utf-8")
        return True


def translate(msg: dict, seen: SeenKinds):
    """One wire message (DojoLink dojo_event or Sail hook) -> one curated
    world event, or None to drop it.

    The translation IS curation: everything the wire carries that a
    player was never shown gets dropped here, and every category emitted
    must be in WORLD_EVENTS. Dropped-but-unknown message kinds are the
    caller's to count — a translator that silently eats a new wire event
    hides a sense that needs building.
    """
    name = msg.get("event")
    if name == "enemy_defeat":
        # Both baba death paths fire this (workshop docs/06): it proves a
        # kill. The visible presentation is the enemy's death burst.
        return {"event": "despawn", "kind": actor_name(msg.get("id", -1)),
                "cue": "defeated"}
    if name == "health_change":
        amount = msg.get("amount", 0)
        hearts_after = msg.get("health", 0) / 16.0
        if amount < 0:
            return {"event": "damage_taken", "hearts": -amount / 16.0,
                    "hearts_after": hearts_after}
        if amount > 0:
            return {"event": "pickup", "kind": "health",
                    "hearts_after": hearts_after}
        return None
    if name == "scene_init":
        return {"event": "environment", "cue": "scene_change",
                "scene": msg.get("scene", -1)}
    if name == "load_game":
        return {"event": "environment", "cue": "game_loaded"}
    if name == "OnActorInit":
        kind = actor_name(msg.get("actorId", -1))
        return {"event": "spawn", "kind": kind,
                "novel": 1 if seen.sight(kind) else 0}
    if name == "actor_kill":
        # Redundant with enemy_defeat for enemies; not a presentation for
        # props. Dropped deliberately, not forgotten.
        return None
    if name in ("frame", "stray_response", "hook_unknown"):
        return None
    return None
