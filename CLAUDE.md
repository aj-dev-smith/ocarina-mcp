# ocarina — session orientation

You are in the ocarina repo: the MCP server piece of OoT Bench.
**`SURFACE.md` and `MACHINE.md` are BLESSED (AJ, 2026-08-01)** — the
contract is in force, ratified-in-place clarifications included (see
MACHINE.md's status block), and the server has flown **five times**.
First light (0.1.0, 2026-08-01) proved the server flies: boot via a
behavior, geometry-sense wandering, the channel wake path, a live
hot-swap. Second light (0.2.x–0.3.0, same day) proved the **loop**:
three wakes answered by a watching client, three brain surgeries
mid-run, a dojo-graded killer ported import-lines-only (3 field kills,
zero damage), the first mind-authored behavior, and AJ's fairness
ruling live-editing the sensorium's obligations. The third flight
(2026-08-02) was the sight-gating verification pass: 0.5.0's
sighting-narrated world confirmed on sight in room 0. The fourth
(2026-08-02 evening) was **the first flight with no rig in the middle** —
ocarina registered as an MCP server in Claude Code, the mind playing
through `mcp__ocarina__*` tool calls end to end — and it found the
census cap that three verification passes had missed. The fifth
(2026-08-03) was **the first navigation by a mind-side map**: a region
graph distilled offline from the scene's collision mesh (`lab/navgraph/`,
built the same afternoon from a design conversation with AJ), compiled
into waypoints, flown to the exact chest the fourth flight failed three
ways to reach — and the chest opened. Session records:
`../oot-dojo/docs/20-first-light-2026-08-01.md`, `docs/21-second-light-
2026-08-01.md`, `docs/22-sight-gating-2026-08-02.md` (design →
ratification → verification, one file), `docs/23-fourth-flight-
2026-08-02.md`, and `docs/24-fifth-flight-2026-08-03.md` (the nav design
conversation + the lab + the flight, one file — read it before touching
anything navigation-shaped).

**Read first:** `SURFACE.md` and `MACHINE.md`, then
`../oot-dojo/docs/19-senses-and-the-machine-2026-07-31.md` (the substance)
and docs/20 + docs/21 + docs/22 (what is built and what it did). The workshop's
`../oot-dojo/CLAUDE.md` maps the validated internals these modules were
ported from; its `docs/08-false-signals.md` discipline applies here
fully — both flights caught its classics live (the dist_y sign; the
silently-never-fires transition shape, twice).

## Operating this repo

- Tests: `python3 -m unittest discover -s tests -t .` (120; includes a
  subprocess-over-real-pipes smoke test with the ported fakegame).
- Run: `python3 -m ocarina --repo <save-file-repo>` — the repo declares
  the machine under `machine/`; SoH connects in over Sail (43384; SoH's
  own config persists Sail enabled, so launching the game auto-connects).
  `examples/first-light/`, `examples/second-light/`,
  `examples/fourth-flight/` and `examples/fifth-flight/` are working
  save-file repos; second-light carries the seek→hunt clearing loop and
  the session-fossil commentary, fourth-flight adds the looking organ,
  sight-honest seeking, the census probe, and ocarina's first climb;
  fifth-flight (the same repo, kept playing) adds the navgraph-steered
  bodies, the locate probe, and the journal of both MCP-direct flights.
- **`lab/navgraph/`** — the place-sense feasibility lab (2026-08-03,
  fifth flight): stdlib pipeline that parses scene collision out of
  SoH's `oot.o2r`, flood-fills it into a region graph with typed climb
  edges, bakes a self-contained HTML debug viewer (elevation slices,
  click-to-route A*, region-level leg planning), and localizes live
  positions (`locate.py`). Read its README first; `test_ring.py` is the
  regression ("the o'clock test"). Lab only — nothing consumes it on the
  blessed surface yet.
- **Playing it directly (fourth flight, the current best way):** register
  ocarina as an MCP server and drive it from a Claude Code session —
  `claude mcp add ocarina --env PYTHONPATH=$PWD -- python3 -m ocarina
  --repo <flight-dir>/<repo>`, then restart the session so the
  `mcp__ocarina__*` tools appear. No FIFO, no drive.py. The mind reads
  `oot://state` / `oot://events` and acts through the real tool surface.
  A `tail -f` on the repo's `journal/mechanical.jsonl` (filtering the
  `stand_watch` idle loop) is the live commentary channel.
- `tools/drive.py` is the hand-drive rig: spawns the server, does the
  MCP handshake, relays JSON commands from a FIFO, logs all traffic
  (wake packs included) to `traffic.jsonl`. It is how a Claude session
  plays the mind's role until real idle-channel delivery is exercised.
  Flight convention (used for the third flight): copy drive.py AND a
  copy of the save-file repo into a scratch flight dir side by side
  (drive.py resolves the repo relative to itself) — never run an
  `examples/` repo in place, or the live journal/seen-kinds mutate the
  committed fossil.
- Module map: `machine.py` (parse + the five validation steps),
  `guards.py` (AST whitelist + `state.*` chains + ABSENT semantics),
  `senses.py` (the digest/schema/event grammar + OFFICIAL_NAMES and
  NEVER_PRESENTED — THE growing curation artifact), `overlay.py` (the
  human debug overlay: sensorium beliefs as world-space labels, pushed by
  the runtime to the Shipwright `overlay` op — one-way, never feeds the
  sensorium), `runtime.py` (20 Hz loop, dispatch, edges, freeze-confirmed
  wakes), `executor.py` (+ the blessed preemption extension),
  `server.py` (stdio MCP + channel push).
  `protocol/link/game/miniyaml/behavior*` are ports.

## State of play after the fifth flight (server at 0.6.0; the lab unblessed)

- **THE FIFTH FLIGHT (2026-08-03, dojo docs/24; no version bump — the
  server ran stock 0.6.0 throughout).** A design conversation on
  navigation senses (how a text-native mind "sees" 3D space) produced
  the **place graph** thesis: regions + typed edges (walk/climb/drop/
  jump/crawl/door/swim), *generated* from collision data, never
  authored; topology for the mind, raw polys for the body; narrative is
  templates over fields; naming is the mind's job. The lab
  (`lab/navgraph/`) proved it the same afternoon: the whole Deku Tree is
  2,321 polys → 50 recognizable regions, the vertical spine
  (B2→B1→GF→ring→3F) reconstructed from wall flags automatically, and
  the "o'clock problem" (chest across the void at 6 o'clock) closed by
  construction — the void has no polys, so A* can only walk the
  perimeter. Then the flight: the mind localized off `locate_probe` +
  the graph, compiled waypoints into bodies, and opened the fourth
  flight's unreachable chest. Navigation took one try; the OPENING took
  six versions, each buying a missing sense (see top open items).
  Fairness rulings proposed in-conversation, NOT yet blessed: entry
  reveals minimap-grade topology (the game's own predicate, twice
  over); presented judgments for the mind, raw numbers body-side (the
  already-blessed two-audience split); sounds cross occlusion; patterns
  are knowledge. **The next session's first task is the docs-lineage
  design doc putting the place sense up for AJ's blessing.**

- **0.6.0** — CENSUS HONESTY + a budgeted overlay (fourth flight, dojo
  docs/23). The instrument's census was capped at the **nearest 12
  actors** — harmless until 0.5.0 moved the sensorium's spine onto it,
  after which room 0 sent 12 of 29 actors with the wire stopping at ~310
  units and live babas in plain sight never reached the sight predicate.
  It was a RANK cap, so its radius shrank as clutter rose: walking
  deeper into the room let bushes evict the enemies. AJ's ruling — the
  wire carries the torrent, curation happens upstairs where the fairness
  rules can see it — put `kMaxActors` at 256 (above OoT's own
  ACTOR_NUMBER_MAX; a runaway guard, not a budget). **Requires a
  Shipwright built after 2026-08-02**; an older one is diagnosed loudly,
  never silently obeyed. Ocarina-side: `senses.census_truncated()` + a
  per-scene runtime diagnostic (the wire always sent
  `actor_count_total`; nothing read it). The overlay now RANKS labels
  (slot-holder → living enemies → vocabulary gaps → distance) and cuts
  to the game side's hard 32-label limit, pairing every push with
  `overlay.boundary()` on the HUD. Flight lesson, generalised: **a debug
  layer must show the BOUNDARY of what it received, not only the
  contents.**

- **0.2.0** — the six pending judgment calls ratified into MACHINE.md
  (AJ delegating the ruling to the mind as the surface's primary user);
  plus `on:` event names now validated at load against the dispatchable
  set.
- **0.2.1** — adversarial testing of the fresh rulings found two real
  bugs: `not in` fired on absent entities (container's reflected `==`
  defeats the sentinel; membership chains now compile to an
  ABSENT-aware helper) and a raising guard (ZeroDivisionError) could
  silently kill the 20 Hz thread (`eval_guard` now warns, never raises).
- **0.2.2** — the validator over-read MACHINE.md: plain-text
  journal/wake/hold on `when` transitions now load; `{field}` templates
  on a `when` transition are the load error (no event to resolve).
- **0.3.0** — the sensorium grew from AJ's eyewitness pass: official
  names `fairy` (first light's unknown_0x0018 was Navi), `door`,
  `spider_web`, `bush`, `treasure_chest`; sprite-less actors (Player,
  En_Holl, Elf_Msg) dropped from spawn narration via NEVER_PRESENTED.
- **0.5.0** — SIGHT-GATED NARRATION (2026-08-02; dojo docs/22 ratified
  by AJ same day, all four open calls as recommended). The census now
  carries `drawn`/`sighted` bits — "sighted" is the game's own Z-target
  attention visibility predicate (on screen + the focus-to-focus
  occlusion line test targeting uses, `z_actor.c` Attention_Find).
  `spawn` narrates first sightings (the doorway census burst is gone);
  the enemy fields cover ever-sighted-this-scene enemies (object
  permanence — camera swings don't flicker the slot); narration is
  suppressed pre-play (`save_loaded` gate closes the attract-demo
  item); the overlay renders never-sighted census actors grey
  `unsighted` (the acceptance visual). An instrument without the bits
  reads as blind with a loud diagnostic, never silently X-ray.
  EYEWITNESS-VERIFIED same day (AJ, room-0 live pass): arrival narrated
  as sightings with no census burst, bushes narrated a minute later as
  the view swept them, and the ceiling skulltula never entered journal
  or slot — the baba in view held `nearest_enemy` from arrival.
- **0.4.1** — interim vertical sight bound (2026-08-02): enemies beyond
  400 units vertical out of view for slot and count; slot selection
  unified into `nearest_enemy_slot()`. Retired by 0.5.0 the same day.
- **0.4.0** — the debug overlay (second light's wrap item), built and
  eyewitness-verified 2026-08-02: the runtime pushes world-space labels
  over every actor ocarina can see (name/unknown, digest dist/above,
  red NEAREST_ENEMY on the slot-holder, amber vocabulary gaps, novelty)
  via a new `overlay` dojo op riding SoH's nametag system. One-way by
  construction — labels render beliefs, never feed the sensorium. Three
  visual-pass fixes landed the same day: per-label diffing + in-place
  text rewrite (full re-register read as flicker), 10-unit display
  quantization, and deferred vtx-buffer retirement in nametag.cpp (a
  freed buffer still referenced by an in-flight display list rendered
  one frame of garbage triangles — a latent stock-SoH race our update
  rate made visible).

**Top open items** (details in `../oot-dojo/harness-backlog.md`; the
fifth flight re-ranked this list with field evidence):

1. **THE PLACE SENSE — now design-ready.** The fourth flight raised it;
   the fifth flight PROVED the shape in the lab and flew it: region
   graph generated from collision data, `place.*` digest section,
   `oot://place`, a `goto` service that **refuses off-mesh targets by
   construction** (v6 hardcoded a staging point past the walkway's inner
   edge and Link auto-jumped into the void — validation must be a
   service, not a discipline), and the `fell` event (walk_ring_v1
   carries the hand-rolled ancestor: an expected-height table). Write
   the design doc, get AJ's blessing, then promote the lab. The floor
   fan survives as the ground-truth probe that verifies graph beliefs,
   not as the primary survey instrument.
2. **Actor bearings in the digest** — promoted by cost: the fifth flight
   worked around the gap by trilateration (three census distances from
   three known positions; fixed the chest 5 units off its actor-entry
   truth) and it cost three behavior versions. Bearings would have cost
   zero.
3. **Prop pose/facing + interaction affordances — new, from the chest
   saga.** A sighted player sees which way a chest faces (the latch) and
   whether the A-icon reads "Open"; ocarina carries neither, and both
   took AJ's eyes to resolve live. Learned and recorded: **En_Box front
   = rot_y + 0x8000** (navgraph.py). The A-icon's action text is
   presented truth (the UI principle) and belongs on the wire. Related:
   **fine motor** — movement primitives need speed as a first-class
   parameter (the body had two gaits, sprint and stop; analog magnitude
   32 is what finally opened the chest) — and **screenshot as
   escalation** earned its rank (two of AJ's screenshots resolved in
   seconds what probes argued about for minutes).
4. `bgm_change` producer (enemy battle music on proximity — the game's
   own fair unseen-enemy channel; the boulder-maze walkthrough in the
   docs/24 conversation also promotes the sfx producer generally:
   rumble trend is how a hearing player navigates occluded hazards).
5. **Sight-gating for behaviours, not just narration.** `game.actors()`
   is raw; sight-gating governs what the MIND is told, not what the
   HANDS reach for. `examples/fourth-flight/machine/behaviors/seek.py`
   filters on the wire's `sighted` bit by hand — that discipline wants
   to live in the surface, not in each body.

Then: the removed `overhead-lurker` reflex is rebuildable per its own
in-file condition; attacker identity on `damage_taken` (needs a
wire-side patch; nearest-enemy-at-freeze is the documented workaround);
Object_Kankyo filter; En_Item00 param-aware naming; the
absence-semantics foot-gun lint (deferred); dojo-trial
`approach_baba_v1`/`v2`, `climb_ladder_v1`, and now the whole
fifth-flight navgraph family (all UNGRADED); dialogue text onto the
wire (the fifth flight advanced the get-item box BLIND — three
`dialogue_advance` calls without reading a word); `save_game`'s NOT_YET
was hit live (the opened chest died with the process — pause-menu
navigation is now a felt gap, not a listed one). Still unexercised:
**real idle-session channel delivery** — flights four and five drove
synchronously and read wakes from the journal, so a wake pack has still
never woken an idle Claude session on its own.

## Rules for this repo

1. **The surface is the contract.** SURFACE.md + MACHINE.md are blessed;
   code implements them exactly. A change to either file is a major
   version bump (SURFACE.md, Versioning) and needs AJ's blessing —
   never edit them as a side effect of an implementation convenience.
   (Precedent: AJ may delegate a ruling explicitly, as with the
   2026-08-01 clarification pass — the delegation is recorded in the
   file when so.)
2. **The north star is the narration layer.** Ocarina is an
   audio-description track for a player with an unusual sensory profile.
   Curation rules live in SURFACE.md ("presented, not computed"; the UI
   principle; official names; vocabulary-not-grammar). Every new sense
   field must pass them — and second light added the sharper corollary:
   unfair information doesn't just leak, it *displaces* fair information
   (single-slot senses especially). `senses.py` documents its honesty
   gaps in-file; keep doing that.
3. **Internals are ported, not rewritten.** Ported modules carry their
   provenance headers; keep diffs against the workshop originals
   reviewable. The behavior interface must never break dojo-graded
   bodies — that equivalence is the point, and second light proved it
   (deku_baba_v4 ran unmodified but for import lines).
4. **Stdlib-only.**
5. **No practice tools on this surface, ever.** Not gated — absent, all
   the way down: `game.py` has no savestate methods and no `console()`.
   Game-native saves only.
6. **The machine is source in the save-file repo.** Ocarina runs it;
   `reload_machine()` validates + hot-swaps; connect rehydrates from the
   repo. The server's live state is never the only copy. The 20 Hz leaves
   are called **behaviors** — never "skills", which means Claude Code
   SKILL.md artifacts only.
7. **Wake transport is MCP channels** (freeze-confirmed first, then push;
   round-tripped live with a watching client as of second light — 3
   wakes, 0 freeze failures). A long-poll `await_wake` fallback exists
   in the spec for non-Claude clients but is not built. Platform facts:
   channels work over local stdio; delivery queues until idle; resources
   cannot be subscribed to. Real idle-session delivery remains
   unexercised (the rig listens; an idle Claude session hasn't).
8. **Not-yet-built surface stays honest.** Tools/resources awaiting
   instrument work (dialogue text, menu navigation, screenshot) are
   registered and return explicit not-yet errors naming what they wait
   on (`NOT_YET` in server.py). Never quietly stub one.
