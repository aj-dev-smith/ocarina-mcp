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
#: 0.6.0: CENSUS HONESTY + a budgeted overlay (fourth flight, dojo
#: docs/23; AJ's ruling 2026-08-02 — "raise it VERY high... it's up to
#: YOU to design the machine in a way that works off the information
#: that you need"). The instrument's census was capped at the nearest 12
#: actors, invisible until 0.5.0 moved the sensorium's spine onto it: in
#: Deku Tree room 0 that sent 12 of 29 with the wire stopping at ~310
#: units, so live babas in plain view never reached the sight predicate,
#: and because it was a RANK cap its radius SHRANK as clutter rose
#: (walking in let bushes evict the enemies). Instrument-side the cap is
#: now 256, above OoT's own ACTOR_NUMBER_MAX — a runaway guard, not a
#: budget; curation belongs upstairs where the fairness rules can see it.
#: Ocarina-side: senses.census_truncated() + a per-scene runtime
#: diagnostic, so a partial world can never again read as a whole one
#: (the wire always sent actor_count_total; nothing read it). The debug
#: overlay now RANKS labels — nearest_enemy slot-holder, living enemies,
#: vocabulary gaps, then distance — and cuts to the game side's hard
#: 32-label limit, pairing every push with overlay.boundary() on the HUD
#: so a missing label never silently means "budget exceeded". That last
#: part is the flight's general lesson: a debug layer must show the
#: BOUNDARY of what it received, not only the contents. No contract touch.
OCARINA_VERSION = "0.6.0"

#: The machine's on-disk format version (machine.yaml `version:` key).
MACHINE_FORMAT_VERSION = 1
