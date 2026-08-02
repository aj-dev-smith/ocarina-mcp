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
- Labels cover exactly the actors the state op reports (the nearest 12
  across the census categories) minus NEVER_PRESENTED ids — an actor with
  no label is an actor ocarina cannot currently see, which is itself
  information.
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

from .senses import (NEVER_PRESENTED, OFFICIAL_NAMES, SeenKinds, Sightings,
                     actor_name, nearest_enemy_slot)

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


def labels(state: dict, seen: SeenKinds, sightings: Sightings) -> list[dict]:
    """Raw DojoLink snapshot -> the overlay label set (wire shape for the
    `overlay` op: key/text/color per label; a set replaces the whole set).
    """
    nearest_key = (nearest_enemy_slot(state, sightings) or {}).get("key")

    out = []
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
        out.append({"key": key, "text": "\n".join(lines), "color": color})
    return out
