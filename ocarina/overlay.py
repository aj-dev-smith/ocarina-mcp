"""Debug overlay: ocarina's beliefs rendered as floating labels over the
actors that hold them (the second-light wrap item, harness-backlog.md).

Second light's calibration channel was AJ typing room descriptions at the
mind and reconciling them against the digest by hand. This makes every
comparison visual: a label on a thing AJ can't see is an X-ray leak, no
label on a thing AJ can see is a coverage gap, and the NEAREST marker
sitting on the ceiling while a baba lunges is the masking finding, live.

Strictly a HUMAN debug instrument. It renders what the sensorium already
believes — official names, the digest's dist/above arithmetic, the
`nearest_enemy` slot-holder, novelty state — and feeds nothing back, so
it needs no fairness review. That one-way promise is rule zero here:
nothing in this module may write into senses, and the game-side op it
feeds (DojoOverlay.cpp) renders text without interpreting it.

Label truthfulness notes:
- Labels cover the actors the state op reports, minus NEVER_PRESENTED
  ids, ranked by debug interest and cut to LABEL_BUDGET — an actor with
  no label is an actor ocarina cannot currently see OR one the budget
  dropped, and `boundary()` exists so those two are never confused.
  THE BUDGET IS THE POINT OF THAT FUNCTION: the fourth flight's bug was
  a silent cap (the wire's nearest-12) reading as a complete world, and
  a debug layer that quietly caps its own labels reproduces that bug
  inside the very instrument built to catch it. The principle earned
  there: a debug layer must show the BOUNDARY of what it received, not
  only the contents.
- `dist`/`above` use the digest's own arithmetic (the dist_y negation
  included), via the same helpers, so the label can never disagree with
  the narration.
- The game-side renderer draws labels through walls (no z-buffer, no
  distance cull) BY DESIGN: the overlay shows beliefs, and X-ray beliefs
  are the bugs it exists to catch.
- Sight-gating (docs/22) renders as state: an actor the sensorium has
  never sighted shows a grey `unsighted` label. The acceptance test is
  visual — in second light's room 0 the ceiling skulltula must read
  unsighted with no NEAREST marker until AJ walks to the shaft and looks
  up.
"""

from __future__ import annotations

from .protocol import ACTORCAT_ENEMY
from .senses import (NEVER_PRESENTED, OFFICIAL_NAMES, SeenKinds, Sightings,
                     actor_name, census_truncated, nearest_enemy_slot)

#: The game side (DojoOverlay.cpp) REJECTS a push carrying more than 32
#: labels outright, so this is a hard wire limit, not a taste call. With
#: the census cap lifted to 256 an ordinary room can exceed it easily —
#: hence ranking (see _rank) rather than the census order, which would
#: hand the whole budget to whatever scenery stands nearest.
LABEL_BUDGET = 32

#: Colors are semantics, so they live here, not in C++: red marks the
#: single `nearest_enemy` slot-holder, amber marks a vocabulary gap
#: (unknown_0x____ — an instrument item, worth catching the eye), grey
#: marks a census actor the sensorium has never sighted (the label AJ
#: can see on a thing ocarina officially can't — sight-gating rendered
#: judgeable on sight), white is a named, sighted actor.
COLOR_NEAREST = [255, 90, 90]
COLOR_UNKNOWN = [255, 210, 80]
COLOR_UNSIGHTED = [140, 140, 140]
COLOR_NAMED = [240, 240, 240]


def _rank(a: dict, nearest_key, named: bool) -> tuple:
    """Sort key: what a human debugging the sensorium most needs to see.

    Distance alone is the wrong axis — it is exactly what the wire's old
    nearest-12 cap used, and it spends the whole budget on the bushes at
    your feet while the enemy across the room goes unlabelled. Tiers:

      0  the `nearest_enemy` slot-holder — the single most bug-prone
         belief ocarina holds (second light's masking finding lived here)
      1  living enemies — the population the digest's enemy fields draw
         from, so a wrong label here is a wrong narration
      2  vocabulary gaps — unknown_0x____ is an instrument to-do, and
         seeing one is how it gets named
      3  everything else, nearest first
    """
    if a.get("key") == nearest_key:
        tier = 0
    elif a.get("cat") == ACTORCAT_ENEMY and (a.get("health") or 0) > 0:
        tier = 1
    elif not named:
        tier = 2
    else:
        tier = 3
    return (tier, float(a.get("dist_xz", 0.0)))


def boundary(state: dict, shown: int) -> list[list[str]]:
    """HUD fields describing what the overlay is NOT showing: labels
    drawn vs presentable, and whether the wire itself truncated.

    Without this, a missing label has two meanings — "ocarina cannot see
    it" and "the budget ran out" — and the first is a bug report while
    the second is noise. Rendering the boundary keeps the overlay's
    central promise ("no label = ocarina can't see it") honest under a
    cap. Ordered pairs: the HUD renders them in the order given.
    """
    actors = [a for a in (state.get("actors") or [])
              if a.get("key") is not None and a.get("id", -1) not in NEVER_PRESENTED]
    total = state.get("actor_count_total")
    dropped = len(actors) - shown
    fields = [["labels", f"{shown}/{len(actors)}"
                         + (f"  ({dropped} over budget)" if dropped > 0 else "")]]
    if total is not None:
        census = state.get("actors") or []
        fields.append(["census", f"{len(census)}/{total} on wire"])
    trunc = census_truncated(state)
    if trunc is not None:
        far = max((a.get("dist_xz", 0.0) for a in state.get("actors") or []),
                  default=0.0)
        # Loud on purpose: this is the state in which every other number
        # on screen is describing a partial world.
        fields.append(["TRUNCATED", f"wire stops at {far:.0f} units"])
    return fields


def labels(state: dict, seen: SeenKinds, sightings: Sightings) -> list[dict]:
    """Raw DojoLink snapshot -> the overlay label set (wire shape for the
    `overlay` op: key/text/color per label; a set replaces the whole set).

    Cut to LABEL_BUDGET by _rank. Pair every push with boundary() so the
    cut is visible rather than silent.
    """
    nearest_key = (nearest_enemy_slot(state, sightings) or {}).get("key")

    scored = []
    for a in state.get("actors") or []:
        actor_id = a.get("id", -1)
        key = a.get("key")
        if key is None or actor_id in NEVER_PRESENTED:
            # Sprite-less actors are invisible to AJ too — no label is the
            # correct render of "not in the sensorium".
            continue
        kind = actor_name(actor_id)
        # The digest's arithmetic, sign convention included (senses.digest):
        # above > 0 means over Link's head.
        dist = float(a.get("dist_xz", 0.0))
        above = -float(a.get("dist_y", 0.0))
        lines = [kind if seen.known(kind) else f"{kind} *novel*"]
        # Quantized to 10-unit steps: the label is for a human eye, and a
        # number that ticks every unit makes the whole overlay churn (the
        # game side only re-renders a label whose text changed).
        lines.append(f"dist {round(dist / 10) * 10:.0f} "
                     f"above {round(above / 10) * 10:+.0f}")
        unsighted = not sightings.sighted(key)
        if unsighted:
            lines.append("unsighted")
        if key == nearest_key:
            lines.append("NEAREST_ENEMY")
            color = COLOR_NEAREST
        elif unsighted:
            color = COLOR_UNSIGHTED
        elif actor_id not in OFFICIAL_NAMES:
            color = COLOR_UNKNOWN
        else:
            color = COLOR_NAMED
        scored.append((_rank(a, nearest_key, actor_id in OFFICIAL_NAMES),
                       {"key": key, "text": "\n".join(lines), "color": color}))
    scored.sort(key=lambda pair: pair[0])
    return [label for _, label in scored[:LABEL_BUDGET]]
