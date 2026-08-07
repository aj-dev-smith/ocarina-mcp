"""The declared save-line identity: parse, observe, judge (0.11.0).

The tenth flight opened with an hour on the WRONG save file:
boot_from_title_v1 is blind by construction — it presses A/START until
`save_loaded` and accepts whatever line the file-select cursor sat on —
and nothing downstream asked which file that was. The tell (boot
nuts=4, the old line's exact count) sat unread in raw snapshots from
t=0. Dojo docs/32 is the design; AJ ratified all four open calls
2026-08-07: `identity.json` at the repo root, check-off-with-diagnostic
for repos that declare nothing, the check owned by the RUNTIME (the
first wake the runtime raises on its own authority), and the 09-kokiri
machine-side prototype retired the day this landed.

Ported, not rewritten (rule 3): observe/presented/judge are the
09-kokiri prototype's `machine/behaviors/identity.py` bodies
(2026-08-07, written after the tenth flight and exercised the same
morning by tools/fakewake.py), re-anchored server-side. What moved in
the port:

- Validation moved to LOAD time: a malformed identity.json, a missing
  `fingerprint` block, or a fingerprint key outside FINGERPRINT_KEYS
  is a load-time problem the runtime journals and then FAILS CLOSED
  on (a lock that quietly asserts something nobody checks is worse
  than no lock at all — the prototype's rule, moved earlier).
- The settle wait moved out: the prototype's `_settled_state` blocked
  inside a behavior body; the runtime's fold waits across ticks
  instead. Nothing in this module blocks or presses anything.
- The slot check moved in: the prototype split it into a machine-yaml
  `where:` guard, which ABSENT semantics fail OPEN (an instrument
  that stops carrying `file` sails past). `judge_slot` is code, so it
  can refuse on missing evidence.

Fingerprint discipline (the lockfile's own charter): MONOTONE facts
only — things this line cannot lose. Volatile counters live in
`journal_only`: read and journaled every boot, asserted never (nuts=4
is exactly the kind of fact that must be READ and must not be a gate).
`equips.worn` is excluded on principle, not just suspicion: worn gear
is volatile (the mind re-equips at will), so it never belongs in a
monotone fingerprint. (Backlog #2's nibble-order theory is separately
unsupported by source — docs/32 §4 records the evidence.)

0.12.0 (docs/33) parks one more declaration here, deliberately: a repo
may say `"scored": true`, which is what `--dev-tools` refuses to start
against. It is NOT a fingerprint fact and no part of the identity check
reads it — identity.json is simply the one place a repo already says
what this line IS, and a second declaration file would split identity.

Read-only in the benchmark sense: this module reads state dicts and
the repo's own identity.json. No .sav is ever opened, at any point,
for any reason. It observes and it judges; choosing the file stays a
human act.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .senses import AMMO_SLOTS, ITEM_NONE, equipment_view, item_name

#: The declaration, hand-authored at the repo root (docs/32 ratified
#: call 1) — bumped in the same commit as the flight that earned it.
IDENTITY_FILENAME = "identity.json"

#: Wire key -> the button's own label on the HUD.
BUTTONS = (("b", "B"), ("c_left", "C-LEFT"),
           ("c_down", "C-DOWN"), ("c_right", "C-RIGHT"))

#: The equipment rows, in subscreen order (senses.EQUIP_TYPES).
EQUIP_ROWS = ("sword", "shield", "tunic", "boots")

#: Fingerprint keys this verifier knows how to check. A key outside
#: this set is a load-time problem, not a shrug.
FINGERPRINT_KEYS = ("health_capacity_at_least", "b_item", "c_buttons",
                    "inventory_items", "equipment_owned")


@dataclass
class Identity:
    """One parsed identity.json. Non-empty `problems` means the repo
    OPTED IN and the declaration is unusable — which is fail-closed
    territory (cannot-verify), never a silent pass."""
    path: Path
    save_slot: Optional[int] = None
    save_name: Optional[str] = None
    fingerprint: dict = field(default_factory=dict)
    journal_only: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    #: The dev-harness gate (0.12.0, docs/33 commitment 3): a repo that
    #: declares itself scored refuses `--dev-tools` outright. It lives
    #: here because identity.json is already the repo's
    #: declaration-of-what-this-line-is (ratified call 3) — a second
    #: declaration file would split identity. Nothing in the identity
    #: CHECK reads it; it is not a fingerprint fact.
    scored: Optional[bool] = None
    scored_problem: Optional[str] = None
    #: Did the file parse as a JSON object at all? A declaration nobody
    #: can read cannot answer the scored question either — which is
    #: refusal territory for the flag, not a shrug.
    readable: bool = True

    @property
    def broken(self) -> bool:
        return bool(self.problems)

    def label(self) -> str:
        """How the declaration names itself in journal lines and packs."""
        bits = []
        if self.save_name is not None:
            bits.append(f"save {self.save_name}")
        if self.save_slot is not None:
            bits.append(f"slot {self.save_slot}")
        return f"identity.json ({', '.join(bits)})" if bits else "identity.json"


def load_identity(repo: Path) -> Optional[Identity]:
    """Parse `<repo>/identity.json`. None = the repo declares nothing
    (the check is OFF; the caller owes the loud diagnostic). A file
    that exists but cannot be used comes back with `problems` — opted
    in and broken, which fails closed downstream."""
    path = Path(repo) / IDENTITY_FILENAME
    if not path.exists():
        return None
    ident = Identity(path=path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        ident.problems.append(f"{path.name} unreadable: {type(e).__name__}: {e}")
        ident.readable = False
        return ident
    if not isinstance(raw, dict):
        ident.problems.append(f"{path.name} is not a JSON object")
        ident.readable = False
        return ident

    scored = raw.get("scored")
    if scored is None or isinstance(scored, bool):
        ident.scored = scored
    else:
        ident.scored_problem = (f"'scored' must be true or false, got "
                                f"{scored!r}")
        ident.problems.append(ident.scored_problem)

    slot = raw.get("save_slot")
    if slot is not None and not isinstance(slot, int):
        ident.problems.append(f"save_slot must be an integer (0-based "
                              f"fileNum), got {slot!r}")
    else:
        ident.save_slot = slot
    name = raw.get("save_name")
    if name is not None and not isinstance(name, str):
        ident.problems.append(f"save_name must be a string, got {name!r}")
    else:
        ident.save_name = name

    fingerprint = raw.get("fingerprint")
    if not isinstance(fingerprint, dict):
        ident.problems.append(f"{path.name} carries no 'fingerprint' block")
        return ident
    for key in fingerprint:
        if key.startswith("_"):
            continue
        if key not in FINGERPRINT_KEYS:
            ident.problems.append(
                f"fingerprint key {key!r} is outside the checkable "
                f"vocabulary {FINGERPRINT_KEYS} — a declaration nobody "
                f"checks is worse than none (teach identity.py or drop "
                f"the key)")
    ident.fingerprint = fingerprint

    journal_only = raw.get("journal_only", [])
    if not isinstance(journal_only, list):
        ident.problems.append(f"journal_only must be a list, got "
                              f"{journal_only!r}")
    else:
        ident.journal_only = journal_only
    return ident


def observe(st: dict) -> tuple[dict, list]:
    """(facts, missing). `facts` is the loaded line's identity, decoded
    into the screen's own names; `missing` names every wire field the
    verdict would have needed and did not get — an instrument that
    predates a block reads as blind, never as agreement."""
    missing: list = []
    equips = st.get("equips")
    inventory = st.get("inventory")

    if not st.get("save_loaded"):
        missing.append("save_loaded is false (no file is loaded — still "
                       "on the title or file-select screen)")
    if equips is None:
        missing.append("state['equips'] (instrument predates the equipment "
                       "sense — rebuild SoH with the 2026-08-04 AgentLink patch)")
    if inventory is None:
        missing.append("state['inventory'] (instrument predates the item sense)")
    if st.get("health_capacity") is None:
        missing.append("state['health_capacity']")

    buttons = None
    owned = None
    if equips is not None:
        buttons = {}
        for key, _label in BUTTONS:
            value = equips.get(key)
            buttons[key] = (None if value in (None, ITEM_NONE)
                            else item_name(value))
        # The worn mask is NOT read: volatile, so never fingerprint
        # material (docs/32 §4). Ownership, the B/C assignments and the
        # inventory are the honest fingerprint.
        if "owned" not in equips:
            missing.append("state['equips']['owned'] (the owned-gear mask)")
        else:
            owned = equipment_view(equips)["owned"]

    items = None
    if inventory is not None:
        items = []
        slots = inventory.get("items") or []
        ammo = inventory.get("ammo") or []
        for slot, item in enumerate(slots):
            if item == ITEM_NONE:
                continue
            entry = {"slot": slot, "item": item_name(item)}
            if slot in AMMO_SLOTS and slot < len(ammo):
                entry["ammo"] = ammo[slot]
            items.append(entry)

    health = st.get("health")
    capacity = st.get("health_capacity")
    facts = {
        "buttons": buttons,
        "owned": owned,
        "items": items,
        "health_capacity": capacity,
        "hearts": None if health is None else health / 16.0,
        "hearts_max": None if capacity is None else capacity / 16.0,
        "rupees": st.get("rupees"),
        "scene": st.get("scene"),
    }
    return facts, missing


def presented(facts: dict) -> str:
    """The one legible boot line. Everything a human needs to recognise
    the file at a glance, counters INCLUDED — the counters are exactly
    the tell that went unread, and journaling them is not the same as
    asserting them (journal_only)."""
    parts: list = []

    buttons = facts.get("buttons")
    if buttons is None:
        parts.append("no equips block on the wire")
    else:
        held = [f"{buttons[key]} on {label}" for key, label in BUTTONS
                if buttons.get(key)]
        parts.append(", ".join(held) if held else "nothing on B or C")

    owned = facts.get("owned")
    if owned is None:
        parts.append("no owned-gear mask on the wire")
    else:
        pieces = [p for row in EQUIP_ROWS for p in (owned.get(row) or [])]
        parts.append("owned " + ", ".join(pieces) if pieces else "owning no gear")

    items = facts.get("items")
    if items is None:
        parts.append("no inventory block on the wire")
    else:
        carried = [i["item"] + (f" x{i['ammo']}" if "ammo" in i else "")
                   for i in items]
        parts.append("carrying " + ", ".join(carried) if carried
                     else "carrying nothing")

    hearts, hearts_max = facts.get("hearts"), facts.get("hearts_max")
    parts.append(f"{hearts:.1f}/{hearts_max:.1f} hearts"
                 if hearts is not None and hearts_max is not None
                 else "hearts unknown")
    parts.append(f"{facts.get('rupees')} rupees")
    parts.append(f"scene {facts.get('scene')}")
    return "boot: " + "; ".join(parts)


def judge(identity: Identity, facts: dict) -> list:
    """Every way the observed line differs from the declared
    fingerprint, named. Empty list means the fingerprint matched.
    Assumes a usable declaration (`identity.broken` is the caller's
    refusal, before judging) and complete evidence (`observe`'s
    `missing` is the caller's refusal too)."""
    fingerprint = identity.fingerprint
    buttons = facts.get("buttons") or {}
    diffs: list = []

    floor = fingerprint.get("health_capacity_at_least")
    if floor is not None:
        capacity = facts.get("health_capacity")
        if capacity is None:
            diffs.append(f"health_capacity absent; declaration expects at "
                         f"least {floor}")
        elif capacity < floor:
            diffs.append(f"health_capacity {capacity} ({capacity / 16.0:.1f} "
                         f"hearts), declaration expects at least {floor} "
                         f"({floor / 16.0:.1f} hearts)")

    expected_b = fingerprint.get("b_item")
    if expected_b is not None and buttons.get("b") != expected_b:
        diffs.append(f"B holds {buttons.get('b') or 'nothing'}, "
                     f"declaration expects {expected_b}")

    for key, expected in (fingerprint.get("c_buttons") or {}).items():
        if buttons.get(key) != expected:
            label = key.upper().replace("_", "-")
            diffs.append(f"{label} holds {buttons.get(key) or 'nothing'}, "
                         f"declaration expects {expected}")

    carried = {i["item"] for i in (facts.get("items") or [])}
    for name in fingerprint.get("inventory_items") or []:
        if name not in carried:
            diffs.append(f"{name} is NOT in the inventory, and the "
                         f"declaration says this line owns it")

    owned = facts.get("owned") or {}
    for row, pieces in (fingerprint.get("equipment_owned") or {}).items():
        have = owned.get(row) or []
        for piece in pieces:
            if piece not in have:
                diffs.append(f"{piece} is NOT owned, and the declaration "
                             f"says this line owns it (the {row} row shows "
                             f"{', '.join(have) or 'nothing'})")
    return diffs


def judge_slot(identity: Identity, seen_slot: Optional[int]) -> Optional[str]:
    """The slot half of the verdict. `seen_slot` is the `file` field of
    the last game_loaded event THIS connection, or None if no load has
    been seen (an attach to an already-loaded world — the slot is
    event-borne, not in state(), so it is honestly unverifiable there).
    Returns a diff line, or None for match/unverifiable-declared."""
    if identity.save_slot is None:
        return None
    if seen_slot is None:
        return None      # the caller says "slot unverifiable this attach"
    if seen_slot != identity.save_slot:
        return (f"loaded slot {seen_slot}, declaration is slot "
                f"{identity.save_slot}"
                + (f" ({identity.save_name})" if identity.save_name else ""))
    return None


# `journal_only` is deliberately not interpreted: the boot line already
# reads every volatile the prototype listed (item ammo rides `carrying`,
# rupees/hearts/scene ride the tail), so the list's job is documentary —
# it marks, in the declaration itself, which facts are READ-not-ASSERTED
# so nobody promotes one into the fingerprint in a later bump.
