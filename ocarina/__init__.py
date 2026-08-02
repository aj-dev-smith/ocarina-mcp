"""ocarina — the instrument you play Hyrule through.

A stdio MCP server exposing Ocarina of Time (via Ship of Harkinian) as a
fair, bounded tool surface. The contract is SURFACE.md + MACHINE.md
(BLESSED, AJ 2026-08-01); this package implements them exactly.

Internals are ported from the OoT Bench workshop (../oot-dojo), where they
were validated against the real game — see MACHINE.md "Provenance".
"""

#: Server version. Semver with benchmark meaning (SURFACE.md, Versioning):
#: a diff touching SURFACE.md or MACHINE.md is a major bump, full stop.
#: 0.x = building toward the first complete implementation of the blessed
#: contract; 1.0.0 is "the surface is fully implemented as blessed".
#: 0.2.0: the MACHINE.md clarification pass (2026-08-01) — the six
#: post-first-light rulings ratified into the contract, and `on:` event
#: names now validated at load. In 0.x, the minor digit carries the
#: major-bump meaning.
#: 0.2.1: two guard-layer bugfixes toward the ratified absence contract —
#: `not in` no longer fires on an absent entity, and a guard that raises
#: (e.g. ZeroDivisionError) warns instead of killing the 20 Hz loop.
#: 0.2.2: the validator read MACHINE.md's journal sentence as banning the
#: VERB on `when` transitions; the contract only restricts the templating.
#: Plain-text journal/wake/hold on a state trigger now load; `{field}`
#: templates on a `when` transition are the load error (all verbs).
#: 0.3.0: the sensorium grew from second light's eyewitness pass — five
#: official names (fairy, door, spider_web, bush, treasure_chest; ids
#: verified against Shipwright's actor_table.h) and sprite-less actors
#: (Player, En_Holl, Elf_Msg) dropped from spawn narration. Gap-fills
#: inside the claimed frontier, no contract touch.
#: 0.4.0: the debug overlay (second light's wrap item) — the runtime
#: pushes floating world-space labels over actors showing the sensorium's
#: beliefs (name, the digest's dist/above, the nearest_enemy slot-holder,
#: novelty), rendered by the new `overlay` dojo op in the Shipwright
#: patch. Human debug instrument, one-way by construction; no contract
#: touch.
#: 0.4.1: interim vertical sight bound on the digest's enemy fields —
#: second light's masking finding (X-ray info displaces fair info: the
#: ceiling skulltula held the nearest_enemy slot while the baba AJ was
#: facing appeared nowhere). Enemies beyond 400 units vertical are out
#: of view for both the slot and the count; slot selection is now the
#: shared nearest_enemy_slot() so the overlay's NEAREST marker cannot
#: diverge. Interim heuristic under the delegated interface ruling; real
#: line-of-sight gating is the pending design pass. No contract touch.
#: 0.5.0: SIGHT-GATED NARRATION (dojo docs/22, blessed by AJ 2026-08-02;
#: minor digit = the major-bump meaning in 0.x). The instrument's census
#: now carries drawn/sighted bits — "sighted" is the game's own Z-target
#: attention visibility predicate (on screen + focus-to-focus occlusion
#: line test). `spawn` narrates first sightings, not room loads; the
#: enemy fields cover ever-sighted-this-scene enemies (object
#: permanence, so camera swings don't flicker the slot); narration is
#: suppressed pre-play (attract demo, save_loaded gate); the overlay
#: renders never-sighted census actors grey `unsighted`. Retires 0.4.1's
#: interim vertical bound. An old instrument without the bits reads as
#: blind, loudly diagnosed — never silently X-ray.
OCARINA_VERSION = "0.5.0"

#: The machine's on-disk format version (machine.yaml `version:` key).
MACHINE_FORMAT_VERSION = 1
