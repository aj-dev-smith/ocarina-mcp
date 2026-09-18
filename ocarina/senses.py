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
- Dialogue text is on the wire as of 0.8.0 (docs/27) EXCEPT wide (JPN)
  text, which arrives as `text: null` + a `wide` flag — blind with a
  flag, never silently wrong. An instrument predating the 2026-08-04
  AgentLink patch carries no `message` block at all; the runtime diagnoses
  that loudly, once.
- The menu documents cover items and equipment only; map and quest
  subscreens stay honest not-yets (their substrates aren't on the wire).
- Drops (En_Item00) are named from their params as of 0.9.0, but only for
  the params curated in ITEM00_NAMES; anything else narrates as
  `dropped_item` — a real thing seen, not identified. The raw param is
  never presented: a number is not something a player saw.
- Census distance fields are REPAIRED when the wire sends them
  degenerate (both zero while the positions disagree) — see
  `normalize_census_distances`. That is an ocarina-side workaround for a
  wire bug, not a sense; it derives nothing the snapshot didn't already
  carry, and it is written to be deleted when the wire is fixed.
- The interval digest (0.10.0, docs/31) is COMPRESSION, not a sense: it
  tallies, quotes and two-endpoint-deltas narration that already passed
  curation on its way into the journal and the digest. It computes
  nothing about the world neither of those already presented. Its own
  gaps are flagged on `IntervalDigest` below.
- The 0.9.0 vocabulary pass (Kokiri route) named twelve actors from the
  id table AHEAD of eyewitness confirmation, which is the 0.3.0 order of
  operations (name, then have AJ look) but leaves a window where a name
  can be wrong in the confident direction. Flagged here until the first
  Kokiri flight confirms them.
"""

from __future__ import annotations

import json
import math
import threading
import time
from pathlib import Path

from .place import clock_bearing
from .protocol import (ACTOR_EN_ITEM00, ACTORCAT_ENEMY,
                       PLAYER_STATE1_CLIMBING_LADDER, PLAYER_STATE1_DEAD,
                       PLAYER_STATE1_ON_A_WALL)

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
    # 0.9.0, the Kokiri slate (dojo docs/28): the treehouse → Deku Tree
    # route narrated as unknown_0xNNNN before this pass, and the 40-rupee
    # hunt is all drops. Ids verified against actor_table.h; the names are
    # the mind's delegated interface ruling (the 2026-08-01 delegation, as
    # docs/28 open call 6 records for the shop catalog). EYEWITNESS
    # CONFIRMATION IS PENDING on the first Kokiri flight — that is the
    # 0.3.0 convention: name from the id table, then have AJ look.
    0x0163: "kokiri_child",    # En_Ko — the forest children (the spam source)
    0x016D: "mido",            # En_Md — the one standing in the gate
    0x0146: "saria",           # En_Sa
    0x003D: "shopkeeper",      # En_Ossan — the man behind the counter
    0x0004: "shop_item",       # En_GirlA — the item ON the shelf, one actor
                               # per slot (its params are the shop row)
    0x003E: "deku_tree",       # Bg_Treemouth — the mouth IS the tree, on sight
    0x0130: "rolling_boulder", # En_Goroiwa — the boulder in the corridor
    0x0141: "signpost",        # En_Kanban — readable since 0.8.0
    0x01B9: "gossip_stone",    # En_Gs
    0x014E: "rock",            # En_Ishi — the liftable ones
    0x0077: "tree",            # En_Wood02
    0x0009: "door",            # En_Door — the house doors. Same word as
                               # Door_Shutter (0x002E, the dungeon half):
                               # a player sees "a door" in both, and the
                               # vocabulary is what they saw, not the class.
}

#: Actors whose params carry the identity a sighted player reads off the
#: sprite — resolved by `actor_name(actor_id, params)`, never by id alone.
#: En_Item00's params are the Item00Type (z64actor.h), masked to 0xFF by
#: its own Init (z_en_item00.c:362). A player sees "a green rupee", not
#: "an item"; naming the drop is what closes the 0.3.0-era deferral.
#: Uncurated params fall back to `dropped_item` — honest and visible (the
#: raw param is never presented; a number is not something anyone saw).
ITEM00_NAMES = {
    0x00: "green_rupee",
    0x01: "blue_rupee",
    0x02: "red_rupee",
    0x03: "recovery_heart",
    0x04: "bomb_drop",
    0x05: "arrows",
    0x06: "heart_piece",
    0x07: "heart_container",
    0x08: "arrows",
    0x09: "arrows",
    0x0A: "arrows",
    0x0B: "bomb_drop",
    0x0C: "deku_nut",
    0x0D: "deku_stick",
    0x0E: "magic_jar",
    0x0F: "magic_jar",
    0x10: "deku_seeds",
    0x11: "small_key",
    0x13: "orange_rupee",
    0x14: "purple_rupee",
    0x15: "deku_shield",
    0x16: "hylian_shield",
    0x17: "zora_tunic",
    0x18: "goron_tunic",
    0x19: "bomb_drop",
    0x1A: "bombchu",
}
ITEM00_FALLBACK = "dropped_item"

#: Actors with NO sprite — a sighted player cannot see them, so narrating
#: their spawns is X-ray vision, worse than an unknown_0x____ (which at
#: least flags a real visible thing we couldn't name). Ids verified
#: against actor_table.h; closes the first-light "narrates Link himself
#: and loader actors" instrument item. Deliberately dropped, not
#: forgotten. (0x0015 En_Item00 was listed here as an open item until
#: 0.9.0 — drops are now named from their params, see ITEM00_NAMES.)
NEVER_PRESENTED = {
    0x0000,   # Player — Link is the viewer, not a sighting
    0x0023,   # En_Holl — invisible room-transition plane
    0x011B,   # Elf_Msg — invisible Navi-message trigger volume (9 in room 0)
    # 0.9.0, the Kokiri slate: two more sprite-less actors on the route.
    0x003B,   # En_River_Sound — an ambient-sound volume (the stream, the
              # waterfall); it is a SOUND, and sound is its own sense
    0x0173,   # Elf_Msg2 — the other invisible Navi-message trigger volume
}


#: Census prop kinds a routed walk treats as SOLID OBSTACLES (docs/30,
#: 0.13.0): the mesh knows floors, not the chest parked on one — these
#: are the standing, solid kinds a route must detour or refuse by name,
#: curated like OFFICIAL_NAMES and defaulting to NOT-an-obstacle (a
#: kokiri child is solid too, but walking up to a person is a behavior's
#: judgment, not a routing refusal). Values are XZ radii in units.
#:
#: HONESTY GAP, labelled per this file's discipline (docs/30 open call
#: 6, ratified "later — write the guess down"): the wire carries actor
#: POSITION, not collider dimensions, so every radius here is a GUESSED
#: per-kind constant, not a measured one. The clean fix is a wire rider
#: (collider radius/height per census entry — the 0.6.0 torrent
#: principle); the chest-pose commission (docs/28 learning 5) wants the
#: same patch. Until then a flight will price these guesses.
OBSTACLE_RADII = {
    0x000A: 30.0,   # treasure_chest — the wedge that named this feature
    0x0125: 20.0,   # bush
    0x0130: 55.0,   # rolling_boulder — corridor-filling (~90+ units of
                    # maze corridor); it MOVES, so the pre-walk check is
                    # a snapshot and the wedge reflex stays the mid-walk
                    # answer (docs/30 honest not-yet: moving obstacles)
    0x0141: 16.0,   # signpost
    0x01B9: 16.0,   # gossip_stone
    0x014E: 20.0,   # rock (the liftable ones)
    0x0077: 25.0,   # tree — the trunk, not the canopy
}


def _resolve_name(actor_id: int, params=None) -> tuple[str, bool]:
    """(name, curated) for a census actor. `curated` False means the name
    is a placeholder standing in for a vocabulary gap."""
    if actor_id == ACTOR_EN_ITEM00:
        name = (ITEM00_NAMES.get(int(params) & 0xFF)
                if params is not None else None)
        return (name, True) if name else (ITEM00_FALLBACK, False)
    name = OFFICIAL_NAMES.get(actor_id)
    return (name, True) if name else (f"unknown_0x{actor_id:04X}", False)


def actor_name(actor_id: int, params=None) -> str:
    """Official name, or an honest placeholder that flags the coverage gap.

    An `unknown_0x____` in the narration is an instrument item ("I couldn't
    see what that was"), never silently dropped — under-sensing is
    blindness, found by watching. `params` is the census actor's params
    field, needed for the actors whose identity rides there (drops); the
    fallback for an uncurated drop is `dropped_item` — vaguer than the
    truth, never wrong, and never the raw number.
    """
    return _resolve_name(actor_id, params)[0]


def actor_named(actor_id: int, params=None) -> bool:
    """False when actor_name() is standing in for a vocabulary gap — the
    debug overlay's amber, and the only honest way to ask now that a name
    can come from params rather than OFFICIAL_NAMES membership."""
    return _resolve_name(actor_id, params)[1]


#: Item id -> official name (z64item.h ItemID) — the item vocabulary
#: behind use_item and the oot://menu documents. Same discipline as
#: OFFICIAL_NAMES: the name carries what the pause screen's icon already
#: shows a player, and the table grows as items are acquired (docs/27;
#: seeded 2026-08-04 with what the save line has actually held).
ITEM_NAMES = {
    0x00: "deku_stick",
    0x01: "deku_nut",
    0x06: "fairy_slingshot",   # acquired 2026-08-07, tenth flight (ydan 2F chest)
    0x3B: "kokiri_sword",      # the B button has shown it since the ninth flight
}
ITEM_IDS = {name: item_id for item_id, name in ITEM_NAMES.items()}
ITEM_NONE = 0xFF

#: Inventory slots whose ammo array entry is meaningful (z64item.h
#: SlotID order: stick, nut, bomb, bow, ..., slingshot at 6, bombchu at
#: 8). Other slots reuse the array for unrelated state; presenting it
#: would be computed, not presented.
AMMO_SLOTS = (0, 1, 2, 3, 6, 8)


def item_name(item_id: int) -> str:
    """Official item name, or the honest unknown_0x__ placeholder."""
    return ITEM_NAMES.get(item_id, f"unknown_0x{item_id:02X}")


#: The equipment subscreen's vocabulary (z64item.h EquipmentType +
#: EquipValue*): nibble per type in the worn mask, bit per piece in the
#: owned mask. These names are the screen's own labels.
EQUIP_TYPES = ("sword", "shield", "tunic", "boots")
EQUIP_PIECES = {
    "sword": ("kokiri_sword", "master_sword", "biggoron_sword"),
    "shield": ("deku_shield", "hylian_shield", "mirror_shield"),
    "tunic": ("kokiri_tunic", "goron_tunic", "zora_tunic"),
    "boots": ("kokiri_boots", "iron_boots", "hover_boots"),
}


#: The Kokiri shop's shelves: official name -> (shop row / SI param, price,
#: description text id, buy-prompt text id). Transcribed from the game's own
#: tables — shopItemEntries (z_en_girla.c:166-271, plus SI_ARROWS_10 at :299)
#: filtered by sShopkeeperStores[0] (z_en_ossan.c:203-210), which is the
#: Kokiri store's eight slots.
#:
#: This is MECHANICS KNOWLEDGE of the ITEM_IDS class, ratified as such (dojo
#: docs/28 open call 6): it is the id table a `buy("deku_shield")` verb needs
#: to steer the shop's own UI, not knowledge of the world a player couldn't
#: have. A shopper reads the price off the sign; the text ids are the
#: server's private steering wire. Prices here are the base prices the table
#: declares — buy() still verifies the ACTUAL rupee delta off the wire and
#: refuses to claim success on a mismatch (SoH's shield-discount CVar can
#: move it), so this table can never quietly lie about what a purchase cost.
SHOP_CATALOG = {
    "deku_shield":    (0x0D, 40, 0x009F, 0x0089),
    "deku_nuts_5":    (0x00, 15, 0x00B2, 0x007F),
    "deku_nuts_10":   (0x04, 30, 0x00A2, 0x0087),
    "deku_stick":     (0x05, 10, 0x00A1, 0x0088),
    "deku_seeds_30":  (0x1D, 30, 0x00DF, 0x00DE),
    "arrows_10":      (0x2C, 20, 0x00A0, 0x008A),
    "arrows_30":      (0x01, 60, 0x00C1, 0x009B),
    "recovery_heart": (0x10, 10, 0x00AC, 0x0095),
}


def equipment_view(equips: dict) -> dict:
    """The equipment subscreen as a document: what is worn, what is
    owned, by name (docs/27; the masks ride the wire's `equips` block)."""
    worn_mask = int(equips.get("worn", 0))
    owned_mask = int(equips.get("owned", 0))
    worn, owned = {}, {}
    for t, tname in enumerate(EQUIP_TYPES):
        pieces = EQUIP_PIECES[tname]
        v = (worn_mask >> (t * 4)) & 0xF
        worn[tname] = pieces[v - 1] if 1 <= v <= len(pieces) else None
        owned[tname] = [pieces[b] for b in range(len(pieces))
                        if owned_mask & (1 << (t * 4 + b))]
    return {"worn": worn, "owned": owned}


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
    "dialogue": {               # the box itself, readable (docs/27; absent
                                # entity when no box, when the instrument
                                # predates the message block, or pre-decode)
        "text": str,            # decoded text, newlines kept (absent while
                                # the box is still opening, and for wide/JPN
                                # text the instrument cannot decode)
        "state": str,           # opening/displaying/awaiting_advance/choice
                                # /done/closing/other — the game's own box
                                # lifecycle, curated
        "text_id": int,         # the game's message id (stable identity)
        "choices": list,        # choice boxes only: the options, verbatim
        "choice_index": int,    # ditto — the LIVE cursor (dialogue_choose's
                                # verification channel)
    },
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
        "moving": bool,         # visibly in motion (census position
                                # deltas — the watching eye's own
                                # evidence, docs/30's escort rider;
                                # ABSENT until two samples can judge.
                                # NOT awake/asleep: a sleeping patrol
                                # that hasn't stirred reads False —
                                # activation state needs the game's own
                                # flag on the wire, backlog #3's
                                # remaining half)
        "reach": str,           # judged: walkable / across a gap /
                                # up a climb / down a drop — the ground
                                # under it, from where you stand
                                # (docs/30 rider, ratified; sight-gated
                                # by inheritance; ABSENT when the place
                                # sense can't vouch). Under the
                                # discovery grain (docs/34, 0.14.0) an
                                # enemy over undiscovered ground reads
                                # "somewhere you haven't been" — the
                                # rider inherits the fog
    },
    "place": {                  # the place sense (docs/25; absent entity
                                # when no map / no --o2r / pre-play)
        "region": str,          # stable region id (absent while off-mesh)
        "on_mesh": bool,        # False = you are not STANDING on mapped
                                # floor: nothing below you at all, or a
                                # floor far below (mid-air / an actor
                                # surface — the 0.13.0 standing gate,
                                # docs/28 learning 4)
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


class Motion:
    """Visible-movement memory behind `nearest_enemy.moving` (0.13.0,
    docs/30's escort rider — priced by the sixth flight: vine guards a
    probe measured as "stationary" were sleeping patrols, and one killed
    Link). Judged from consecutive census position deltas — the same
    evidence a watching eye takes, no actor internals — over a short
    window so a patrol's between-steps pause doesn't flicker the bit.
    Answers None (digest ABSENT) until two samples far enough apart in
    time exist to judge; a single glimpse cannot honestly say "still".

    Server-session state like Sightings: trails clear on scene change
    and leave with their actors. Mutated only via observe().
    """

    WINDOW_S = 0.7          # how far back the eye remembers
    MIN_SPAN_S = 0.15       # two samples closer than this can't judge
    EPS = 3.0               # XZ drift beyond this reads as motion
                            # (inside it is animation jitter)

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._scene = None
        self._trails: dict = {}      # actor key -> [(t, x, z), ...]

    def observe(self, state: dict) -> None:
        """Fold one raw snapshot in. Pre-play contributes nothing (the
        attract demo is not the world)."""
        if not state.get("save_loaded", False):
            return
        now = self._clock()
        scene = state.get("scene")
        if scene != self._scene:
            self._scene = scene
            self._trails.clear()
        seen = set()
        for a in state.get("actors") or []:
            key, pos = a.get("key"), a.get("pos")
            if key is None or not pos or len(pos) < 3:
                continue
            seen.add(key)
            trail = self._trails.setdefault(key, [])
            trail.append((now, float(pos[0]), float(pos[2])))
            while trail and trail[0][0] < now - self.WINDOW_S:
                trail.pop(0)
        for key in [k for k in self._trails if k not in seen]:
            del self._trails[key]

    def moving(self, key):
        """True/False when the window can judge `key`; None when it
        cannot (unknown actor, one sample, or samples too close in
        time — absence, never a guess)."""
        trail = self._trails.get(key)
        if not trail or trail[-1][0] - trail[0][0] < self.MIN_SPAN_S:
            return None
        _t, x, z = trail[-1]
        return any(math.hypot(x - px, z - pz) > self.EPS
                   for (_pt, px, pz) in trail[:-1])


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
        kind = actor_name(actor_id, a.get("params"))
        ev = {"event": "spawn", "kind": kind,
              "novel": 1 if seen.sight(kind) else 0}
        # A chest's lid state reads on sight; the wire carries the game's
        # own treasure flag (free play 2026-08-04: a body pressed A at an
        # already-open chest, twice, because nothing said so).
        if a.get("opened") is not None:
            ev["state"] = "open" if a["opened"] else "closed"
        events.append(ev)
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


#: How far apart the two positions must be before a zeroed distance pair
#: reads as the wire bug rather than the truth. One unit is far inside
#: Link's own body radius: nothing genuinely at his feet clears it, and
#: nothing the bug produces is ever that close.
DEGENERATE_DIST_EPSILON = 1.0


def normalize_census_distances(state: dict) -> dict:
    """Repair census entries whose wire distances are degenerate, deriving
    dist_xz/dist_y from the positions the same snapshot already carries.

    WORKAROUND FOR A WIRE BUG, 2026-08-07 (tenth flight; harness-backlog
    tenth-flight item 3): En_Hintnuts (0x0192) census entries arrive with
    `dist_xz == 0` and `dist_y == 0` while `pos` is good, so a scrub
    across the room reads as standing on Link — and, worse, wins the
    single `nearest_enemy` slot from whatever is genuinely nearest. The
    cause is wire-side and the game must diagnose it. This immunizes the
    WHOLE census against the class rather than the one actor id, because
    the flight bodies' hand-rolled pos arithmetic proves the class is
    what hurts. DELETE THIS FUNCTION when the wire is fixed.

    Derivation, not invention: the positions are already on the wire and
    are exactly what the distance fields are supposed to be computed
    from. Nothing moves unless BOTH distance fields are zero AND the two
    positions are materially apart (DEGENERATE_DIST_EPSILON) — an actor
    truly at Link's feet reports 0/0 honestly, and "correcting" that
    would be manufacturing a distance from float noise. An entry with no
    `pos`, or a snapshot with no player pos, is left exactly as it came:
    never guess.

    Mutates and returns `state`. It is applied ONCE, where the snapshot
    is first read (Game.state()), so behaviors, the digest, and the debug
    overlay all share one repaired census and cannot disagree about how
    far away a thing is — the overlay's whole value is that it renders
    the beliefs the narration holds.
    """
    ppos = (state.get("player") or {}).get("pos")
    if not ppos or len(ppos) < 3:
        return state
    px, py, pz = float(ppos[0]), float(ppos[1]), float(ppos[2])
    for a in state.get("actors") or []:
        if float(a.get("dist_xz") or 0.0) or float(a.get("dist_y") or 0.0):
            continue
        apos = a.get("pos")
        if not apos or len(apos) < 3:
            continue
        ax, ay, az = float(apos[0]), float(apos[1]), float(apos[2])
        dist_xz = math.hypot(ax - px, az - pz)
        # SIGN: the wire's dist_y is yDistToPlayer = player.y - actor.y
        # (Actor_HeightDiff, z_actor.c:1397) — NEGATIVE when the actor is
        # ABOVE Link, which is why digest() negates it into `above`. The
        # derived value must carry the identical convention; the opposite
        # sign would silently put every repaired actor on the wrong side
        # of Link's head. docs/08 §17, the field that has already caught
        # this repo twice.
        dist_y = py - ay
        if math.hypot(dist_xz, dist_y) <= DEGENERATE_DIST_EPSILON:
            continue                    # genuinely at Link: 0/0 is true
        a["dist_xz"] = dist_xz
        a["dist_y"] = dist_y
    return state


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


def digest(state: dict, sightings: Sightings, place: dict | None = None,
           motion: "Motion | None" = None, reach=None) -> dict:
    """Raw DojoLink snapshot -> the curated digest guards and the mind see.

    Behaviors see the raw snapshot server-side at 20 Hz; this is the
    narration. Must match SCHEMA exactly — the load-time path check is
    only as good as this function's fidelity to it. `sightings` is
    required, not defaulted: a call site that forgot it would be a call
    site quietly reinstating X-ray vision. `place` is the PlaceSense
    sample for this snapshot (docs/25), or None when the sense has
    nothing honest to say — absent entity, never a guess. `motion` and
    `reach` are the 0.13.0 riders (docs/30): the Motion tracker behind
    `nearest_enemy.moving`, and a callable(actor) -> judged string (the
    runtime wires it to PlaceSense.judge_reach) behind
    `nearest_enemy.reach`; either None leaves its field absent.
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
    # The dialogue entity (docs/27): present exactly when the wire's
    # `message` block is — an open box on an old instrument leaves it
    # ABSENT (the runtime diagnoses that loudly; the entity never
    # guesses). `text` absent while unreadable (box opening, wide/JPN).
    msg = state.get("message")
    if msg is not None:
        entity = {"state": str(msg.get("state", "other")),
                  "text_id": int(msg.get("text_id", -1))}
        if msg.get("text") is not None:
            entity["text"] = str(msg["text"])
        if "choices" in msg:
            entity["choices"] = list(msg.get("choices") or [])
            entity["choice_index"] = int(msg.get("choice_index", 0))
        out["dialogue"] = entity
    near = nearest_enemy_slot(state, sightings)
    if near is not None:
        out["nearest_enemy"] = {
            "kind": actor_name(near.get("id", -1), near.get("params")),
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
        # The 0.13.0 riders, both ABSENT rather than guessed when their
        # source can't judge. Sight-gated by inheritance: they annotate
        # the slot the sight predicate already filled, so neither can
        # leak an unseen actor — they can only stop lying about a seen
        # one (docs/30's fairness argument, verbatim).
        if motion is not None:
            judged = motion.moving(near.get("key"))
            if judged is not None:
                out["nearest_enemy"]["moving"] = judged
        if reach is not None:
            judged = reach(near)
            if judged is not None:
                out["nearest_enemy"]["reach"] = judged
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
    """One wire message (AgentLink agent_event or Sail hook) -> one curated
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
        return {"event": "despawn",
                "kind": actor_name(msg.get("id", -1), msg.get("params")),
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
        # The file-select screen presents the chosen slot; the wire's
        # `file` is that choice (0-based fileNum). Curation dropped it
        # through ten flights — the tenth's wrong-file hour was announced
        # at t=0 and stripped here (docs/29). An instrument predating the
        # field omits it: absent, never guessed, so a guard naming it
        # warns instead of silently passing the wrong line.
        ev = {"event": "environment", "cue": "game_loaded"}
        if "file" in msg:
            ev["file"] = msg["file"]
        return ev
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


# -- the interval digest: "while you were out" (0.10.0, dojo docs/31) --------

class IntervalDigest:
    """The wake pack's compression of the interval since the last wake.

    Blocking delivery (docs/31) means a wake pack lands after an interval
    the mind did not watch — forty seconds of autopilot, or forty
    minutes. The raw stream is already in the journal and `oot://events`;
    this is the same stream folded small enough to read: two-endpoint
    state deltas, repeat-collapsed tallies, and the firsts quoted whole.

    Fairness: every field here is a tally, a quote, or a delta over
    narration that ALREADY passed the curation rules on its way into the
    journal (events) or the digest (state). Nothing is computed about
    the world that neither of those presented. Honesty gaps, flagged:

    - Items SPENT have no producer: the wire narrates pickups, not
      purchases, so a purchase shows only as the `rupees` delta.
    - Distinct journal texts are quoted once per INTERVAL, not once per
      session: a line that fires every interval is quoted every interval.
      Within an interval its repeats collapse into the tallies, keyed by
      transition. (docs/31 says "first-time journal transitions"; read
      per-interval, because a session-scoped first would leave later
      intervals with an untexted `journal x3` and no way to drill down
      but the raw log.)
    - `ticks` is the LOGIC clock (gameplay_frames), so it counts game
      time and not the freeze; `wall_s` counts both. The pair is the
      point — they diverge exactly where cognition was free.
    - Tallies collapse on (event, kind, behavior, cue, transition). Two
      behavior_done records with different outcomes land in one bucket;
      the outcome is in `oot://events`, one query away.
    """

    #: Digest fields worth a two-endpoint delta. All are HUD counters a
    #: player watches change; the rest of the digest is "what is", which
    #: the pack's own `state` block already carries.
    DELTA_FIELDS = ("scene", "hearts", "hearts_max", "sticks", "nuts",
                    "rupees")

    #: What distinguishes one tally bucket from another inside a category.
    KEY_FIELDS = ("kind", "behavior", "cue", "transition")

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        """Start a fresh interval (called at each wake delivery)."""
        with self._lock:
            self._started = self._clock()
            self._first_state = None
            self._last_state = None
            self._first_frames = None
            self._last_frames = None
            self._tallies: dict = {}
            self._firsts: list = []
            self._quoted: set = set()
            self._trail: list = []
            self._items: dict = {}

    def note_state(self, digest: dict, frames=None) -> None:
        """Fold in one curated digest. The FIRST one folded is the
        interval's baseline — before the game connects there is no
        snapshot, so the first interval's "from" is the state at connect
        (docs/31), with no special case for it."""
        with self._lock:
            if self._first_state is None:
                self._first_state = dict(digest)
                self._first_frames = frames
            self._last_state = dict(digest)
            if frames is not None:
                self._last_frames = frames

    def note_event(self, ev: dict) -> None:
        """Fold in one recorded event — the EventLog observer hook, so
        this sees exactly what the journal saw, nothing more."""
        name = ev.get("event")
        with self._lock:
            if name == "spawn" and ev.get("novel"):
                self._firsts.append(dict(ev))       # a first sighting: verbatim
                return
            if name == "journal":
                text = ev.get("text")
                if text is not None and text not in self._quoted:
                    self._quoted.add(text)
                    self._firsts.append(dict(ev))
                    return
            if name == "pickup":
                kind = ev.get("kind") or "unknown"
                self._items[kind] = self._items.get(kind, 0) + 1
                return
            if name == "place" and ev.get("cue") == "region_entered":
                region = ev.get("region")
                if region and (not self._trail or self._trail[-1] != region):
                    self._trail.append(region)      # consecutive repeats collapse
                return
            key = (name,) + tuple(ev.get(f) for f in self.KEY_FIELDS)
            self._tallies[key] = self._tallies.get(key, 0) + 1

    def render(self) -> dict:
        """The `interval` section of a wake pack. Empty sections are
        absent rather than empty: nothing to say, said by not saying it
        (the digest's absent-entity idiom)."""
        with self._lock:
            out = {"wall_s": round(self._clock() - self._started, 1)}
            if self._first_frames is not None and self._last_frames is not None:
                out["ticks"] = self._last_frames - self._first_frames
            first, last = self._first_state or {}, self._last_state or {}
            delta = {f: {"from": first[f], "to": last[f]}
                     for f in self.DELTA_FIELDS
                     if f in first and f in last and first[f] != last[f]}
            if delta:
                out["delta"] = delta
            if self._items:
                out["items_gained"] = dict(self._items)
            if self._trail:
                out["region_trail"] = list(self._trail)
            events = []
            for key, count in self._tallies.items():
                entry = {"event": key[0]}
                entry.update({f: v for f, v in zip(self.KEY_FIELDS, key[1:])
                              if v is not None})
                entry["count"] = count
                events.append(entry)
            if events:
                out["events"] = events
            if self._firsts:
                out["firsts"] = [dict(e) for e in self._firsts]
            return out


def interval_lines(interval: dict) -> list:
    """The interval digest as text — templates over the rendered fields,
    for the channel push's body (the blocked call gets the JSON)."""
    if not interval:
        return []
    lines = [f"since the last wake: {interval.get('wall_s', 0)}s wall"
             + (f", {interval['ticks']} game ticks" if "ticks" in interval else "")]
    for field, span in (interval.get("delta") or {}).items():
        lines.append(f"  {field}: {span['from']} -> {span['to']}")
    for kind, count in (interval.get("items_gained") or {}).items():
        lines.append(f"  picked up: {kind} x{count}")
    trail = interval.get("region_trail")
    if trail:
        lines.append("  trail: " + " -> ".join(trail))
    for entry in interval.get("events") or []:
        label = " ".join(str(entry[f]) for f in IntervalDigest.KEY_FIELDS
                         if f in entry)
        lines.append(f"  {entry['event']}"
                     + (f" [{label}]" if label else "")
                     + f" x{entry['count']}")
    for ev in interval.get("firsts") or []:
        lines.append("  first: " + json.dumps(ev))
    return lines


# -- narration (the digest as sentences) -------------------------------------

def _bearing_word(clock) -> str:
    try:
        c = int(clock)
    except (TypeError, ValueError):
        return "somewhere"
    if c == 12:
        return "straight ahead"
    if c in (11, 1):
        return f"just off ahead at {c} o'clock"
    if c == 6:
        return "directly behind"
    if c in (5, 7):
        return f"behind at {c} o'clock"
    if c == 3:
        return "to the right"
    if c == 9:
        return "to the left"
    return f"at {c} o'clock"


def narrate(d: dict, extra: "list[str] | None" = None) -> str:
    """The curated digest rendered as a few plain sentences — the same
    facts, in the narration layer's own form.

    Built for Jev (jev.py, 2026-09-18) and measured before it was
    written: over the SAME digest, nested JSON had Jev answer the
    half-heart-with-a-baba-closing case "approach"; one sentence of
    narration had it answer "retreat". A text-native judge reads text.
    Templates over fields, never a new sense: every clause here is a
    digest field or an `extra` line the BODY supplies from what it
    legitimately holds (a baba's head height, an ammo count).

    Distances are reported in game units with no interpretation — the
    QUESTION carries the domain constants (sword reach, bite reach),
    the state carries the facts. Absent digest entities are absent
    sentences, not guesses.
    """
    parts: list = []
    hearts, hmax = d.get("hearts"), d.get("hearts_max")
    if hearts is not None and hmax:
        parts.append(f"Link has {hearts:g} of {hmax:g} hearts.")
    elif hearts is not None:
        parts.append(f"Link has {hearts:g} hearts.")
    player = d.get("player") or {}
    if player.get("dead"):
        parts.append("Link is dead.")
    elif player.get("climbing"):
        parts.append("Link is climbing.")
    elif player.get("on_wall"):
        parts.append("Link is on a wall.")
    place = d.get("place")
    if isinstance(place, dict):
        if place.get("on_mesh") is False:
            parts.append("Link is not standing on mapped ground.")
        if place.get("region"):
            parts.append(f"Link is in region {place['region']}"
                         + (f", heading {place['heading']}." if place.get("heading") else "."))
    n = d.get("enemies")
    e = d.get("nearest_enemy")
    if isinstance(e, dict):
        kind = str(e.get("kind", "enemy")).replace("_", " ")
        s = f"The nearest enemy is a {kind}, {float(e.get('dist', 0.0)):.0f} units away, " \
            f"{_bearing_word(e.get('bearing'))}"
        above = e.get("above")
        if above is not None:
            a = float(above)
            if abs(a) < 20:
                s += ", at Link's height"
            elif a > 0:
                s += f", {a:.0f} units above Link"
            else:
                s += f", {-a:.0f} units below Link"
        if "moving" in e:
            s += ", moving" if e["moving"] else ", not moving"
        if e.get("reach"):
            s += f"; the ground to it is {e['reach']}"
        parts.append(s + ".")
        if isinstance(n, int) and n > 1:
            parts.append(f"{n} enemies are in view.")
    elif isinstance(n, int) and n == 0:
        parts.append("No enemy is in view.")
    dlg = d.get("dialogue")
    if isinstance(dlg, dict):
        state = dlg.get("state", "other")
        text = dlg.get("text")
        s = f"A message box is open ({state})"
        if text:
            s += f': "{text}"'
        if dlg.get("choices"):
            s += f"; it offers the choices {dlg['choices']}, cursor on option {dlg.get('choice_index', 0)}"
        parts.append(s + ".")
    elif d.get("dialogue_open"):
        parts.append("A message box is open.")
    for line in extra or []:
        if line:
            parts.append(str(line).rstrip(".") + ".")
    return " ".join(parts)
