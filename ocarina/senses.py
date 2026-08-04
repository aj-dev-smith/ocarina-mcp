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

World senses are SIGHT-GATED as of 0.5.0 (dojo docs/22, blessed by AJ
2026-08-02): `spawn` narrates an actor's first sighting, and the enemy
fields cover only enemies the player has sighted this scene. "Sighted"
is the game's own Z-target attention visibility predicate, computed
wire-side per census actor (on screen + the focus-to-focus occlusion
line test targeting itself uses) — the OoT team's ruling on "can the
player see this", exposed rather than reinvented. Narration is
suppressed entirely until `save_loaded` (the attract demo is not the
world; AJ's ruling, same pass).

Known honesty gaps, flagged rather than hidden:
- Sight is camera-based, not eye-based: Link's back can be to a thing
  the camera shows. Ruled correct (what the camera shows is what a real
  player knows), recorded here because it is a judgment call.
- Object permanence is approximated as scene-lifetime keys: an actor
  pointer reused within one scene after an unload would inherit sighted
  state. Rare, accepted, and visible in the journal if it ever narrates
  strangely.
- An instrument without the sighted bits (pre-2026-08-02 patch) reads
  as BLIND — no spawns, no enemy fields. Loud by design (the runtime
  diagnoses it); the silent alternative is X-ray vision coming back
  unannounced.
- `sfx`/`bgm_change`/`telegraph` categories exist in the grammar but have
  NO producers yet — the DojoLink patch does not tap the audio or
  actionFunc hooks. Senses before the frontier crosses them. The enemy-
  BGM cue (battle music on proximity, no sight test — the game's own
  fair unseen-enemy channel) is the next producer to build.
- Scene is a numeric id, not a place name. Naming places is the same
  principle as naming actors; the table just doesn't exist yet.
"""

from __future__ import annotations

import json
from pathlib import Path

from .place import clock_bearing
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
    # Second light, 2026-08-01: named from AJ's eyewitness sightings in
    # Deku Tree room 0, ids verified against Shipwright's actor_table.h.
    0x0018: "fairy",           # En_Elf — first light's mystery actor was Navi
    0x002E: "door",            # Door_Shutter, the dungeon doors
    0x000F: "spider_web",      # Bg_Ydan_Sp — the web over the atrium floor hole
    0x0125: "bush",            # En_Kusa, the cuttable shrubs
    0x000A: "treasure_chest",  # En_Box — the gestalt is instant on sight
}

#: Actors with NO sprite — a sighted player cannot see them, so narrating
#: their spawns is X-ray vision, worse than an unknown_0x____ (which at
#: least flags a real visible thing we couldn't name). Ids verified
#: against actor_table.h; closes the first-light "narrates Link himself
#: and loader actors" instrument item. Deliberately dropped, not
#: forgotten (0x0015 En_Item00 drops stay narratable but unnamed for now:
#: a sighted player sees "a heart", not "an item" — needs param-aware
#: naming).
NEVER_PRESENTED = {
    0x0000,   # Player — Link is the viewer, not a sighting
    0x0023,   # En_Holl — invisible room-transition plane
    0x011B,   # Elf_Msg — invisible Navi-message trigger volume (9 in room 0)
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
    "nearest_enemy": {          # the closest living enemy in view
        "kind": str,            # official name (the visual gestalt as text)
        "dist": float,          # apparent distance, xz — a PROJECTION
        "above": float,         # height over Link (docs/08 §17: read it)
        "bearing": int,         # clock-face vs Link's facing, 12 = ahead
                                # (docs/25 rider: a sighted player calls
                                # directions clock-face; raw pos/yaw stay
                                # body-side — the wire carried them since
                                # first light, the gap was curation)
    },
    "place": {                  # the place sense (docs/25; absent entity
                                # when no map / no --o2r / pre-play)
        "region": str,          # stable region id (absent while off-mesh)
        "on_mesh": bool,        # False = the map has no floor under you
        "x": float,             # exact self-pose: the self-pose exemption
        "y": float,             # (knowledge of OTHERS is where unfairness
        "z": float,             # lives; confidence about SELF is an
        "facing": int,          # accessibility obligation — AJ, docs/25)
        "heading": str,         # 8-wind judged form (n/ne/e/... ; north=-z)
    },
    "enemies": int,             # living enemies in view
}                               # "in view" = ever-sighted this scene (Sightings)


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


def living_enemies(state: dict) -> list:
    """The raw living enemies in the snapshot, before any sight gate."""
    return [a for a in (state.get("actors") or [])
            if a.get("cat") == ACTORCAT_ENEMY and (a.get("health") or 0) > 0]


class Sightings:
    """Ever-sighted actor keys — the object permanence behind the enemy
    fields and spawn narration (docs/22, blessed 2026-08-02: the wire's
    `sighted` bit is the Z-target attention predicate; persistence is
    actor-key lifetime). Once a player has seen a thing they can track
    it — you can't unsee the baba by backing away from it — so gating
    the enemy fields on this-frame sight would make them flicker with
    every camera swing; keys accumulate instead, clearing on scene
    change (the server-side stand-in for actor-key lifetime; the
    pointer-reuse caveat is in the module docstring).

    Server-session state, deliberately NOT persisted to the save-file
    repo: this is what the player currently holds in view-memory, not
    save-file knowledge — SeenKinds carries the durable half. Mutated
    only via observe(); reads are set-membership.
    """

    def __init__(self):
        self._scene = None
        self._keys: set = set()

    def observe(self, state: dict) -> list:
        """Fold one raw snapshot in; returns the census actors sighted
        for the FIRST time (census order) for the caller to narrate.
        Pre-play snapshots (attract demo: save_loaded false) contribute
        nothing — the demo is not the world (AJ, 2026-08-02)."""
        if not state.get("save_loaded", False):
            return []
        scene = state.get("scene")
        if scene != self._scene:
            self._scene = scene
            self._keys.clear()
        fresh = []
        for a in state.get("actors") or []:
            key = a.get("key")
            if key is None or not a.get("sighted", False):
                continue
            if key not in self._keys:
                self._keys.add(key)
                fresh.append(a)
        return fresh

    def sighted(self, key) -> bool:
        return key in self._keys


def spawn_events(fresh: list, seen: SeenKinds) -> list:
    """First-sighting census actors -> the `spawn` events to narrate.
    This replaces the old OnActorInit translation: an event per actor
    coming INTO VIEW, not per actor entering the world at room load.
    NEVER_PRESENTED still applies — the attention predicate projects
    position only, so an invisible trigger volume can be "on screen"."""
    events = []
    for a in fresh:
        actor_id = a.get("id", -1)
        if actor_id in NEVER_PRESENTED:
            continue
        kind = actor_name(actor_id)
        events.append({"event": "spawn", "kind": kind,
                       "novel": 1 if seen.sight(kind) else 0})
    return events


def census_carries_sight(state: dict):
    """True/False: do this snapshot's census actors carry the `sighted`
    bit; None when there is no census to judge. False means the
    instrument predates sight-gating and the world senses are blind —
    the runtime turns that into a loud diagnostic, once."""
    actors = state.get("actors") or []
    if not actors:
        return None
    return any("sighted" in a for a in actors)


def census_truncated(state: dict):
    """`(sent, total)` when the wire dropped actors from this snapshot's
    census, else None (None also when the instrument reports no total).

    The wire sends `actor_count_total` alongside a nearest-first census.
    Until 2026-08-02 nothing read it, so a capped census was
    indistinguishable from a complete world — and it was capped at 12,
    which in an ordinary room meant live enemies the player was looking
    straight at never reached the sight predicate (fourth flight; the
    cap is now a runaway guard at 256). That silence is the docs/08
    false signal in its purest form: absence of evidence rendered as
    evidence of absence. The runtime turns a truthy answer here into a
    loud diagnostic, the same way a census without `sighted` bits reads
    as blind-and-saying-so rather than quietly X-ray.
    """
    actors = state.get("actors")
    total = state.get("actor_count_total")
    if actors is None or total is None:
        return None
    return (len(actors), total) if total > len(actors) else None


def in_view_enemies(state: dict, sightings: Sightings) -> list:
    """Living enemies the player has sighted (ever, this scene) — the
    population behind both the `enemies` count and the `nearest_enemy`
    slot, so a guard can still read absence of the slot as "no enemy in
    view"."""
    return [a for a in living_enemies(state)
            if sightings.sighted(a.get("key"))]


def nearest_enemy_slot(state: dict, sightings: Sightings) -> dict | None:
    """The raw actor holding the single `nearest_enemy` slot (min dist_xz
    over the in-view enemies), or None. Shared with the debug overlay so
    its NEAREST marker can never diverge from the slot the digest
    actually fills (the divergence would be a debug instrument lying
    about the thing it exists to check)."""
    enemies = in_view_enemies(state, sightings)
    if not enemies:
        return None
    return min(enemies, key=lambda a: a.get("dist_xz", float("inf")))


def digest(state: dict, sightings: Sightings, place: dict | None = None) -> dict:
    """Raw DojoLink snapshot -> the curated digest guards and the mind see.

    Behaviors see the raw snapshot server-side at 20 Hz; this is the
    narration. Must match SCHEMA exactly — the load-time path check is
    only as good as this function's fidelity to it. `sightings` is
    required, not defaulted: a call site that forgot it would be a call
    site quietly reinstating X-ray vision. `place` is the PlaceSense
    sample for this snapshot (docs/25), or None when the sense has
    nothing honest to say — absent entity, never a guess.
    """
    player = state.get("player") or {}
    flags1 = player.get("state_flags1", 0)
    enemies = in_view_enemies(state, sightings)
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
    if place is not None:
        out["place"] = dict(place)
    near = nearest_enemy_slot(state, sightings)
    if near is not None:
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
        # The bearings rider (docs/25): clock-face relative to Link's
        # facing — the form a sighted player calls directions in. Omitted
        # (ABSENT) if the instrument doesn't carry positions.
        ppos, apos = player.get("pos"), near.get("pos")
        if ppos and apos and player.get("yaw") is not None:
            out["nearest_enemy"]["bearing"] = clock_bearing(
                float(ppos[0]), float(ppos[2]), int(player["yaw"]),
                float(apos[0]), float(apos[2]))
    return out


# -- the event grammar -------------------------------------------------------

#: The closed grammar (SURFACE.md): world categories + machine events.
#: A new category is a rare, reviewed change — vocabulary is open, this
#: tuple is not. (`place` added 2026-08-03 under exactly that review:
#: dojo docs/25 open call 5, ratified — `environment` is the world
#: changing; `place` is YOUR relationship to the world changing, and a
#: journal that can't distinguish them attaches blame badly. Cues:
#: region_entered, fell.)
WORLD_EVENTS = ("telegraph", "sfx", "bgm_change", "environment", "spawn",
                "despawn", "damage_taken", "damage_dealt", "actor_state",
                "pickup", "ui", "place")
MACHINE_EVENTS = ("entered", "exited", "behavior_done", "behavior_aborted",
                  "wake", "journal", "directive", "escalation", "diagnostic")
ALL_EVENTS = WORLD_EVENTS + MACHINE_EVENTS

#: The machine events transitions may match on. The rest are record-only
#: (a transition on `entered` firing a goto that emits `entered` is an
#: infinite loop inside one tick); `on:` naming one is a load error.
DISPATCHED_MACHINE_EVENTS = ("behavior_done", "behavior_aborted")
DISPATCHABLE_EVENTS = WORLD_EVENTS + DISPATCHED_MACHINE_EVENTS


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

    def known(self, kind: str) -> bool:
        """Non-mutating peek: has `kind` been sighted this save file? The
        debug overlay reads this without claiming a sighting — only a
        narrated spawn (sight) may consume novelty."""
        return kind in self._seen

    def sight(self, kind: str) -> bool:
        """True if this is the first sighting of `kind` this save file."""
        if kind in self._seen:
            return False
        self._seen.add(kind)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(sorted(self._seen)), encoding="utf-8")
        return True


def translate(msg: dict):
    """One wire message (DojoLink dojo_event or Sail hook) -> one curated
    world event, or None to drop it. (Spawn narration no longer lives
    here — it is census-driven; see Sightings/spawn_events.)

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
        # No longer a presentation: init fires for the whole room at
        # load ("entered the world"). `spawn` now narrates first
        # SIGHTINGS, via Sightings.observe + spawn_events (docs/22,
        # blessed 2026-08-02). Dropped deliberately, not forgotten.
        return None
    if name == "actor_kill":
        # Redundant with enemy_defeat for enemies; not a presentation for
        # props. Dropped deliberately, not forgotten.
        return None
    if name in ("frame", "stray_response", "hook_unknown"):
        return None
    return None
