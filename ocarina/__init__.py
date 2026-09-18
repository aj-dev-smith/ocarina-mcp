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
#: 0.7.0: THE PLACE SENSE (dojo docs/25, ratified by AJ 2026-08-03; the
#: fifth flight, docs/24, is the evidence base; minor digit = the
#: major-bump meaning in 0.x — this touches both contract files).
#: Region graphs distill from the scene's own collision data (the lab
#: pipeline ported: collision.py + navgraph.py + place.py) with
#: DETERMINISTIC geometry-derived names, so mind-side knowledge accrues
#: on stable identifiers. The digest grows `place.*` — region, on_mesh,
#: and EXACT self-pose x/y/z/facing/heading under the ratified self-pose
#: exemption (knowledge of others is where unfairness lives; confidence
#: about self is an accessibility obligation) — and the `nearest_enemy`
#: slot grows clock-face `bearing` (the rider; the wire carried actor
#: positions since first light — the gap was curation, priced by the
#: fifth flight at three behavior versions of trilateration). New
#: `place` event category (region_entered, fell — the rare reviewed
#: grammar change), `oot://place` (judgments over names, no raw
#: coordinates; v0 whole-scene reveal is a flagged honesty gap until
#: region->room membership exists), and `game.traverse()` — ONE named
#: leg, refusing everything the map does not vouch for BEFORE moving
#: (the v6 void jump, killed by construction); cross-region routing
#: stays the mind's, by ruling. locate_probe-class diagnostics retire,
#: subsumed by place.*; mind-side distillation of game data is ruled
#: CONTRABAND in scored play (the lab is dev tooling, like savestates).
#: 0.7.1: the acceptance flight's harvest (sixth flight, 2026-08-04) —
#: three traverse fixes, all found by play in one afternoon, none by 164
#: tests: (1) a modal message box freezes the pad, so traverse now fails
#: fast naming the real blocker instead of pushing a dead stick into a
#: false story (Navi's skullwalltula lecture ate a 12 s grab window);
#: (2) the wedge reflex — actors are not in the collision mesh, so a
#: mesh-clean route can still wedge on a treasure chest; position frozen
#: ~3 s while pushing now triggers a mesh-checked sidestep (never toward
#: the void) instead of a 20 s "stalled" misdiagnosis; (3) base-segment
#: grabs — a tall curved climb sheet's 3D centroid can hang beside a
#: chest over a genuine gap in the vines, so distill now keeps each
#: column's floor-touching bottom segments and resolve_traverse aims the
#: grab at the longest segment the from-region can stand beside. No
#: contract touch.
#: 0.8.0: THE SPOKEN WORD AND THE SAVED GAME (dojo docs/27, ratified by
#: AJ 2026-08-04) — three already-blessed promises implemented, no
#: contract touch. Dialogue text rides the state snapshot (the wire's
#: new `message` block, decoded box text + choices as data): the digest
#: grows a nullable `dialogue` entity, `ui` gets its first producers
#: (dialogue_opened/dialogue_closed), `oot://dialogue` goes live with a
#: recent-texts ring, traverse's message-box fail-fast now QUOTES the
#: box it fails on, and `dialogue_choose` graduates (stick-nudge until
#: the wire's live cursor matches — the choice is made with a player's
#: own inputs, verified, never a memory write). `save_game` graduates
#: via the game's own Play_PerformSave behind the pause-legality gate
#: (what the menu's Yes button calls, legal exactly when the menu would
#: be — puppeting the menu was rejected in review, docs/27 call 1).
#: `use_item(item)` graduates as programmatic C-button assignment (the
#: item subscreen's own commit, its own legality gates) + a real
#: C-button press, verified off the new `equips` wire block; inventory
#: on the wire graduates `oot://menu/items` and `oot://menu/equipment`
#: as documents. An instrument predating the 2026-08-04 AgentLink patch is
#: diagnosed loudly and read as blind, never silently.
#: 0.9.0: THE KOKIRI SLATE (dojo docs/28, ratified by AJ 2026-08-05) —
#: the two tools standing between the bench and its first overworld
#: route, plus the vocabulary that route needs. No contract touch: both
#: verbs were already registered and blessed, and implementing a
#: registered tool is not a surface change (the 0.8.0 precedent).
#: `equip(item)` graduates on the new `equip_gear` staged op — a
#: mechanical twin of assign_c running the equipment subscreen's own
#: gates and commit — refusing off the wire before it sends (unknown
#: name, not owned) and verifying the worn mask afterwards, which is the
#: exact predicate Mido's gate evaluates. `buy(item)` graduates with NO
#: wire change at all: the shop is a message-box state machine, so it is
#: dialogue_choose's nudge-and-verify generalized to the shelf cursor
#: (every cursor move re-issues that slot's description box, which is
#: what makes the cursor observable). buy owns the WHOLE purchase —
#: shelf, confirm, the get-item box whose A is what actually deducts the
#: rupees, and the continue-shopping question — because returning early
#: would leave a half-commit behind a stuck modal; it verifies the rupee
#: delta off the wire and refuses to claim success on a mismatch. The
#: vocabulary pass names the Kokiri route (kokiri_child, mido, saria,
#: shopkeeper, shop_item, deku_tree, rolling_boulder, signpost,
#: gossip_stone, rock, tree, house doors) and finally names DROPS from
#: their params (En_Item00: green/blue/red rupee, recovery heart and the
#: rest, `dropped_item` where the vocabulary still has a gap) — the
#: explicitly-deferred item, commissioned; the 40-rupee hunt is all
#: drops.
#: 0.10.0: THE BLOCKING WAKE (dojo docs/31, ratified by AJ 2026-08-07 the
#: afternoon the channel path finally live-verified — "I kind of hate the
#: flag"). Wake delivery stops being a Claude Code channel push and
#: becomes a plain blocking MCP tool call, portable to any client: a
#: contract bump, SURFACE.md amended. `resume(max_sleep?, max_block_s?)`
#: unfreezes and BLOCKS, returning the next wake pack as its own result —
#: one call is one act of living, and because the world only runs while
#: someone is listening, a wake CANNOT fire into silence (ten flights of
#: dropped pushes and hand-typed "wake"s become structurally impossible,
#: not mitigated). `await_wake(max_block_s?)` graduates from spec-only to
#: built as the re-attach verb: it listens without resuming (a severed
#: block must never be re-armed with resume(), which re-runs the current
#: node's body — docs/28), returns a parked wake at once, blocks while
#: the world runs, and errors loudly when a delivered wake is unanswered
#: (you are holding the ball, not waiting). One awaiter at a time, a loud
#: error, never a queue. A severed block (cancellation, dead client,
#: max_block_s) leaves the machine PLAYING ON — it is the autopilot — and
#: the next wake parks frozen with its default armed, which is today's
#: machinery demoted from normal path to crash recovery. The wake pack
#: grows an `interval` section: "while you were out" as state deltas,
#: repeat-collapsed event tallies, novel firsts quoted verbatim, and both
#: clocks — compression of narration that already passed curation, never
#: a new sense. Channels stay, demoted to an optional Claude Code nicety;
#: the push carries the same single-sourced pack. Riding the same bump:
#: SCREENSHOT graduates from NOT_YET (backlog #5, four flights of AJ's
#: eyes resolving what probes argued about) — the 2026-08-07 AgentLink
#: `screenshot` op reads framebuffer 0 (Metal's deferred blit + the GL
#: path; overlay labels included, deliberately: beliefs ON truth), the
#: wire carries raw RGBA8 box-averaged to `max_width` (default 640, both
#: sizes always reported — the 0.6.0 boundary lesson), and the PNG is
#: made ocarina-side in stdlib `screenshot.py`, returned as a real MCP
#: image block: actual pixels to the mind's vision, a debugging sense,
#: never a stream. An old instrument answers "rebuild SoH", never a
#: silent stub.
#: 0.12.0: THE DEV HARNESS (dojo docs/33, direction + rule amendment
#: ratified by AJ 2026-08-07). The missing rung of the test pyramid:
#: under an explicit `--dev-tools` server flag, a `dev_*` family
#: (`dev_warp` through the game's own entrance table, `dev_teleport`
#: in-scene) makes live e2e testing at a CHOSEN world state possible —
#: warp to the maze, teleport to the corridor mouth, assert, repeat, in
#: minutes instead of a flight. A contract bump: SURFACE.md's benchmark
#: purity bullet amended; MACHINE.md untouched, which is the design
#: property that keeps it honest. Three structural commitments, not
#: promises: (1) the verbs live at the server/MCP layer only — `game.py`
#: grows nothing, so no behavior, guard or machine can name a cheat in
#: ANY mode (`ocarina/dev.py` holds the wire calls and the server holds
#: it only under the flag); (2) dev use is un-hideable — a `dev_mode`
#: banner journals on every boot and attach, every call journals
#: `dev_cheat` with its arguments BEFORE it runs, and status() reports
#: dev_mode, so an audit is one grep of the repo's permanent record;
#: (3) a repo declaring `"scored": true` in identity.json REFUSES to
#: start under the flag, loudly, before any connection. Without the
#: flag the dev verbs are ABSENT — not registered, not NOT_YET-stubbed,
#: invisible; the default surface is byte-identical to 0.11.0's.
#: Savestates remain absent in every mode; that door is not reopened.
#: 0.12.1: the first live pass's two seams, fixed the same evening (no
#: contract touch — the dev harness is server-layer, and SURFACE.md's
#: amended purity bullet is unchanged). (1) `dev_warp` to an entrance
#: leading back into the CURRENT scene performs the whole reload, but
#: the arrival watch compared scene ids and sat there until it timed
#: out on a warp that had already worked; arrival is now the
#: instrument's `loads` counter (every play-state init ticks it, same
#: scene or not), with the old scene watch kept as a fallback that
#: DIAGNOSES itself in the reply and in the timeout error — an old
#: instrument is answered loudly, never silently (0.6.0). (2) rooms
#: only load through the door/holl actors, so a `dev_teleport` across a
#: room boundary left the destination's geometry and actors unloaded
#: (Kokiri Forest is three rooms); the verb takes an optional `room`
#: that makes the game perform a real room change first, surfaces the
#: game's out-of-range refusal by name, and reports the room the world
#: ended in. Both ride the same-evening AgentLink patch
#: (`dev.DEV_ROOM_PATCH`): `loads` and `room` on the state payload, a
#: `room` argument on the teleport op. tests/live grows the two pins.
#: 0.12.2: `dev_teleport` rebuilt on the game's own Farore's Wind
#: respawn machinery, from the second live pass of the same day (no
#: contract touch — the dev harness is server-layer). A raw position
#: write moved Link and left the CAMERA wedged in the geometry it was
#: looking through, which is not a world anyone can debug against; the
#: instrument's op now STAGES a real scene reload through the respawn
#: record, so the room loads, its actors respawn, temp flags ride along
#: and the camera arrives WITH Link — a door transition in all but
#: name. Ocarina follows: the op's success reply is staging-time truth
#: (the requested position plus the room and yaw the record resolved,
#: defaults filled from where Link is), arrival is the `loads` counter
#: exactly as it is for warp (one shared arrival watch behind both
#: verbs now), and the position reported is the world's after the load.
#: New optional `yaw` (int16 binang) sets the facing on arrival. The
#: game's -19 refusal — the save's entranceIndex is a grotto/shop
#: return sentinel, so there is no entrance to respawn through — is
#: surfaced by name like -18, without dressing it up as a room problem.
#: An instrument whose state carries no `loads` is REFUSED rather than
#: fallen back on (`dev.DEV_FW_PATCH`): it predates this teleport too,
#: so its reply is an echo with no arrival to check it against, and
#: trusting it would report a full-fidelity arrival that never
#: happened. Rides the same SoH rebuild as the screenshot blit gating,
#: which needed no ocarina change.
#: 0.13.0: ROUTE-AWARE WALKING (dojo docs/30, ratified by AJ 2026-08-07
#: with all open calls as recommended; built against the dev harness
#: per docs/33). A contract bump: SURFACE.md's place principle extends
#: one clause (within-region ROUTING is motor; refusals precede
#: movement) and MACHINE.md gains "The routed walk". The region is the
#: answer: `game.walk_to(x, z)` routes inside the current region and
#: refuses everything else BEFORE movement, by name, in milliseconds —
#: off-mesh, target off the map, target in another region (names it
#: and the legs out), no in-region path, blocked by a census prop
#: ("blocked by a treasure_chest at your 2 o'clock"; radii are
#: LABELLED guesses until the collider wire rider). `game.reachable`
#: is the same check with the walk removed — the election filter two
#: flight bodies independently reinvented as blacklists. Routing is
#: CLEARANCE-AWARE as a combat-safety requirement (wall-scrape
#: slowdown got Link hit on AJ's watch): A* penalizes wall-adjacent
#: polys, waypoints hold the adaptive offset min(desired,
#: (width - link_diameter)/2) — midline in pinches, never refusing a
#: corridor Link fits — and near-body-width corridors are reported as
#: squeezes. The exception family renames to RouteRefused/RouteFailed
#: with the Traverse names aliased (same classes; no graded body
#: breaks). Riders: the localizer gains the STANDING gate (docs/28
#: learning 4 closed — a floor far below Link is not the floor he is
#: on; on_mesh/region/events/refusals all stop lying on actor
#: surfaces); `nearest_enemy` gains judged `reach` (walkable / across
#: a gap / up a climb / down a drop) and the `moving` bit (census
#: deltas — NOT awake/asleep, which still needs the game's own flag:
#: backlog #3's wire half); `game.actors(sighted=True)` puts seek.py's
#: hand-rolled sight filter on the surface; and the distiller's crawl
#: end-clustering gap is FIXED (crawl faces probe along their own
#: normals — spot04's sword tunnel and ydan's B1 crawls all link;
#: `oot://place` says "crawl through to", though traverse still
#: refuses crawls as an honest not-yet). tests/live grows the walk
#: family: the cliff refused cold with zero movement measured in-body,
#: reachable agreeing with the walk, and a routed walk arriving
#: map-verified.
#: 0.14.0: THE DISCOVERY GRAIN (dojo docs/34, ratified by AJ
#: 2026-08-07 with all five open calls as recommended, together with
#: docs/30 as one story; built the same night). Knowledge in the head
#: is fair; geometry in the hand must be earned. `oot://place` now
#: implements its own blessed reveal grain: overworld scenes and
#: interiors reveal whole at entry (the game's own photographed
#: minimap predicate); DUNGEON_SCENES present only regions presence
#: has earned — unvisited regions ABSENT (not greyed), legs into
#: undiscovered space typed frontiers with "destination unknown" (edge
#: names kept — the wall is visible and traverse explores by name),
#: and first presence journals the new `region_discovered` place cue,
#: once per save line. Discovery is SAVE-LINE state
#: (ocarina/discovery.py -> .ocarina/place_discovered.json, the
#: SeenKinds pattern), seeded once from the journal for lines that
#: predate the ledger (open call 5: the fossil proves the presence),
#: re-presented on re-entry, never re-fogged. Fog coherence with the
#: routed walk: the cross-region refusal and the reach rider degrade
#: to "somewhere you haven't been" for undiscovered regions — still
#: instant, still zero movement; self is never fogged. The docs/25
#: honesty flag comes OFF for overworld and is RETARGETED for
#: dungeons: the game reveals whole ROOMS on entry, scene collision
#: carries no room table, so v1 reveals at region grain by presence —
#: under-revealing, never X-ray (the wire's `room` field is recorded
#: as an observed region->room binding for the day the game's own
#: room tables are read). Dungeon Map widening is implemented at
#: outline grade behind a `dungeon_items` wire field the instrument
#: does not carry yet (loud note until the rider lands); Compass
#: markers deferred (the census sees only the loaded room). tests/live
#: grows the discovery family (fresh entry fogged; warp-out/warp-back
#: re-presents, criterion 5) — UNRUN with the walk family, same
#: reason: SoH was down.
#: 0.14.1: THE LIVE PASS (2026-08-07, the same night, AJ's "just go
#: for it" — SoH launched from the CLI, boot clicked through by the
#: harness itself, all ten live tests green from a cold start). One
#: server-side fix rode home: walk_to's arrival verdict is DISTANCE
#: (plus the map's on-mesh word); region identity demoted to
#: diagnosis — a target within tolerance of a region seam legally
#: ends with Link localized to the neighbour (found live at the seam
#: where the village floor meets the Know-It-All plateau), and the
#: reply's `region` now names where the map says Link IS. Harness
#: lessons, all in tests/live: the boot gate (first light's
#: boot_from_title in the throwaway repos + await_game waiting for
#: PLAY state — racing the attract demo wedged every warp), the
#: patient retry on transition-in-progress (the world mid-reload is
#: not a verdict), spawn-settle before probing, and
#: ensure_mapped_ground (test_3's own elected target walked Link
#: through the Know-It-All Brothers' open-doorway load trigger into
#: an unmapped interior — each class now establishes its ground,
#: never inherits it).
#: 0.14.2: THE DUNGEON-ITEMS RIDER (2026-08-07, later the same night —
#: docs/34 criterion 4 closed, live). The instrument grows the
#: `dungeon_items` state field (map/compass/boss_key/small_keys for
#: the CURRENT dungeon, by the game's own gSaveContext.mapIndex —
#: ABSENT outside dungeon-indexed scenes, never a wrong row) and the
#: `give_dungeon_item` op; ocarina grows `dev_give_item` (--dev-tools,
#: journaled, dungeon items ONLY — the slate stays evidence-first),
#: whose reply carries the row read back after the grant: the
#: read-back is the proof, never the op's word. 0.14.0's "loud note
#: until the rider lands" path retires itself the moment the wire
#: carries the row. Live the same night: the Map grant widened
#: oot://place to outline entries carrying no legs (criterion 4's
#: cause-and-effect form), and the whole live suite ran green with
#: ZERO skips — including the room pin, which now establishes Kokiri
#: itself instead of skipping when the boot save wakes elsewhere
#: (this night it woke inside ydan). The fresh-entry fog cap counts
#: presence-earned regions only: a boot line that owns the Map
#: legitimately adds outlines, which is the ratified widening, not a
#: reveal leak. Tests 437 -> 444.
OCARINA_VERSION = "0.15.0"

#: The machine's on-disk format version (machine.yaml `version:` key).
MACHINE_FORMAT_VERSION = 1
