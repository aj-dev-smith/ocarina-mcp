# ocarina — session orientation

You are in the ocarina repo: the MCP server piece of OoT Bench.
**`SURFACE.md` and `MACHINE.md` are BLESSED (AJ, 2026-08-01)** — the
contract is in force, ratified-in-place clarifications included (see
MACHINE.md's status block), and the server has flown **ten times**.
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
ways to reach — and the chest opened. The sixth (2026-08-04) was the
**place-sense acceptance flight** (0.7.0 → 0.7.1): the first mission
ordered entirely in region-graph names, the first mid-flight patches to
the server itself (three traverse fixes no test had caught), and the
bench's **first death** — the vine guards a probe measured as
stationary were sleeping patrols, and Link died parked at 0.5 hearts
inside one's wake-up radius. 3F remains unreached; the mission is open.
The seventh (2026-08-04, AJ's **free-play session** — "do whatever you
want"): the ring chest re-taken by named traverse, the bench's first
deliberate JUMP (the 2F walkway gap, lab-measured), its first DOOR, a
full video-take run for AJ's recording — and its second death (the
health-critical wake's HOLD default fired while the mind deliberated;
a freeze is not indefinite shelter). The chest's prize was AJ's
eyewitness correction: the DUNGEON MAP, not the slingshot. The eighth
(2026-08-04, same evening) built and acceptance-flew **0.8.0**. The
ninth (2026-08-05, dojo docs/28) built **0.9.0** (equip, buy,
dialogue_choose live) in the morning and acceptance-flew it on a
FRESH save file the same day: treehouse → sword via the crawlspace →
40 rupees (an autonomous money loop) → the first live BUY → shield
equipped → the trail → stopped at the Deku Tree's mouth as ordered —
then, extended by AJ, INTO the tree and room 0 cleared (two babas,
zero damage, deku_baba_v4 byte-identical to its dojo grading). Three
game-native saves; no deaths. The tenth (2026-08-07, dojo docs/29,
same file-C line): **the SLINGSHOT taken** — the 2F target open since
the sixth flight's death. It opened with an hour on the WRONG save
file (the blind boot body accepted the old line; caught by AJ's
"CAN you check?" shield question — boot identity verification is now
backlog #1 material), then ran file C clean: three babas, the ring
chain, the bench's **first crouch-shield duel win** (the scrub's
surrender box read live; its clue taught roll-landing), AJ's live
commissions (the ACTION-BUTTON sense and the RUMBLE channel — a
closed door read as mesh fins cost the mind twenty minutes AJ's eyes
fixed in one sentence), the first traverse of a fresh vine leg, the
chest, two saves. ITEM_NAMES grew (fairy_slingshot, kokiri_sword);
`use_item` put the slingshot on C-LEFT. The return-and-shoot family
(exit.py: pit-priced retries; shoot_guard_v1, Z-lock + C-LEFT — the
sixth flight's killers finally in range) is authored but UNFLOWN —
the standing next-session opener, ahead of even the heal loop.
See the state of play below.
Session records:
`../oot-dojo/docs/20-first-light-2026-08-01.md`, `docs/21-second-light-
2026-08-01.md`, `docs/22-sight-gating-2026-08-02.md` (design →
ratification → verification, one file), `docs/23-fourth-flight-
2026-08-02.md`, `docs/24-fifth-flight-2026-08-03.md` (the nav design
conversation + the lab + the flight, one file — read it before touching
anything navigation-shaped), `docs/25-the-place-sense-2026-08-03.md`
(the ratified design), `docs/26-sixth-flight-2026-08-04.md` (the
acceptance flight — read it before touching traverse; carries the
Dungeon Map erratum), and `docs/27-dialogue-and-saving-2026-08-04.md`
(0.8.0: designed, ratified, built, and acceptance-flown in one day —
also the only written record of the seventh session's evidence), and
`docs/29-tenth-flight-2026-08-07.md` (the slingshot flight: the
wrong-file postmortem, the two AJ commissions, the honesty audit, and
the unflown exit/shoot family — read it before the next session).

**Read first:** `SURFACE.md` and `MACHINE.md`, then
`../oot-dojo/docs/19-senses-and-the-machine-2026-07-31.md` (the substance)
and docs/20 + docs/21 + docs/22 (what is built and what it did). The workshop's
`../oot-dojo/CLAUDE.md` maps the validated internals these modules were
ported from; its `docs/08-false-signals.md` discipline applies here
fully — both flights caught its classics live (the dist_y sign; the
silently-never-fires transition shape, twice).

## Operating this repo

- Tests: `python3 -m unittest discover -s tests -t .` (241; includes a
  subprocess-over-real-pipes smoke test with the ported fakegame, and
  real-o2r place-sense pins that skip if oot.o2r is absent).
- Run: `python3 -m ocarina --repo <save-file-repo> --o2r
  /Users/aj/Code/Shipwright/oot.o2r` — without `--o2r` the place sense
  is off (loud diagnostic, `place.*` absent, traverse refuses). The
  repo declares the machine under `machine/`; SoH connects in over Sail (43384; SoH's
  own config persists Sail enabled, so launching the game auto-connects).
  `examples/first-light/`, `examples/second-light/`,
  `examples/fourth-flight/`, `examples/fifth-flight/` and
  `examples/sixth-flight/` are working save-file repos; second-light
  carries the seek→hunt clearing loop and the session-fossil
  commentary, fourth-flight adds the looking organ, sight-honest
  seeking, the census probe, and ocarina's first climb; fifth-flight
  (the same repo, kept playing) adds the navgraph-steered bodies, the
  locate probe, and the journal of both MCP-direct flights;
  sixth-flight (still the same line) adds the place-flight bodies
  (refusal probe, spider probe, ascend_to_3f v1→v5 with post-mortems
  in-file) and the acceptance flight's full journal, death included;
  seventh-flight (the same line, through the free-play session and the
  0.8.0 acceptance) adds the free-play bodies (goto_ring by name,
  leap_gap, enter_door with the blind-box discipline, door_census,
  goto_entrance), the chest-already-open guard, and the journal
  carrying the second death, the first game-native save, and the first
  dialogue ever read.
- **`lab/brainviz/`** — the brain viewer (2026-08-04): `--brainviz
  43385` serves a live force-directed view of the running machine
  (active node, edges pulsing by outcome, armed `when` guards, the
  Mind orb that wake beams climb while the world freezes, a
  repeat-collapsing journal ticker). One-way by construction — the
  overlay pattern pointed at a browser: `ocarina/brainviz.py` is the
  spigot (GET-only HTTP + SSE on a daemon thread, fed by an
  `EventLog.observers` mirror), `lab/brainviz/viewer.html` is the whole
  app (self-contained, read per request — edit, refresh, no restart).
  Read its README first. Survives server restarts; replays fossils via
  the backlog. Lab-grade: no contract change rides with it.
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
  **Wake delivery (proven by in-session experiment, 2026-08-07):** a
  channel push does NOT start a turn in an idle session — it queues
  until the next turn. A Monitor event line DOES re-invoke an idle
  session. So arm exactly ONE Monitor at flight start as the alarm
  clock (`persistent: true`):
  `tail -F -n 0 <repo>/journal/mechanical.jsonl | grep --line-buffered
  '"event": "wake"\|"event": "escalation"'`
  — one notification per wake record; the queued channel pack renders
  in the turn the monitor starts. NEVER ad-hoc background tails: a
  backgrounded `tail -f` never exits so never notifies (that is the
  missed-frozen-game failure), and unfiltered tails wake on
  stand_watch chatter (that is the spurious-wake storm). `-n 0` and
  `--line-buffered` are both load-bearing.
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

## State of play after the ninth flight (server at 0.9.0; equip, buy, and dialogue_choose LIVE)

- **0.9.0 + THE NINTH FLIGHT (2026-08-05, dojo docs/28 — built in the
  morning, acceptance-flown on a FRESH save file the same day; the
  session record + honesty audit are the last two sections of
  docs/28, read them before citing this flight).** The slate:
  `equip(item)` (worn-mask verified, sword half-commit check),
  `buy(item)` (the seven-phase purchase owning shelf → confirm →
  fanfare → continue-shopping; wallet delta is the proof), and
  dialogue_choose's first LIVE choice (the 0x6B continue-shopping
  box). The flight (repo `../ocarina-flights/09-kokiri/`, journal
  included): fresh file "C", treehouse → sword (first CRAWL, found
  via the game's own crawlspace wall flags; get-item cutscene frozen
  by our own chest-`opened` wake, diagnosed live) → 40 rupees (bushes,
  Mido's chests, then an AUTONOMOUS money loop: farm → dry →
  house-cycle → farm) → first live buy (deku_shield; the select-A ate
  by the description box's typing animation — retry from the settled
  box ran clean; server fix owed in buy phase 4) → shield equipped →
  trail (mesh-A* waypoints; Mido never fired a box with sword+shield
  worn) → STOPPED at the mouth as ordered → extended by AJ: room 0
  CLEARED (two babas, zero damage, deku_baba_v4 ported byte-identical
  from second-light). Three game-native saves, no deaths. Runtime
  findings, all recorded in docs/28 + harness-backlog: the spurious
  force_state/reload wake (old body's abort dispatches on the NEW
  node, {detail} unresolved — 4 sightings); resume-after-wake re-runs
  the current node's body; the place sense reads THROUGH the atrium
  floor web (an actor surface, not mesh — six false `fell`
  narrations mid-fight); the unreachable-target blacklist was
  field-reinvented TWICE (collect_rupees v3, farm_shield_fund v2) —
  it wants to be a surface primitive; box hygiene is needed at EVERY
  interaction boundary (a kokiri greeting froze a body's pad for
  100 s). AJ's mid-flight verdict, now a commissioned backlog
  proposal: in-region navigation is blind — route-aware walking over
  the already-loaded mesh, refusals before movement. **The honesty
  audit matters for public claims: scene/actor-table lookups and
  mind-side mesh A* were used (legal in an acceptance flight,
  contraband in scored play), and the baba killer was a prior-run
  port.**

- **0.8.0 + THE SEVENTH AND EIGHTH FLIGHTS (2026-08-04, dojo docs/27 —
  designed, ratified, built, and acceptance-flown in one day).** The
  seventh was AJ's free-play session ("do whatever you want"): the ring
  chest re-taken by ONE named traverse (start-position independent —
  traverse obsoletes waypoint replay inside a mapped scene), the
  bench's first deliberate JUMP (the 2F walkway gap, lab-measured at
  ~100 units, 2-for-2), its first DOOR (enter_door_v1, with the blind
  12×A box-clearing discipline and a false-success caught by AJ's
  eyes), a scene door map by probe, a full video-take run — and the
  SECOND DEATH: the health-critical wake's HOLD default fired (~5 min)
  while the mind explained architecture, and the scrubs finished Link.
  A freeze is NOT indefinite shelter; health-critical needs a retreat
  REFLEX, not a hold. AJ's eyewitness also corrected the record: the
  ring chest holds the DUNGEON MAP (docs/26 erratum), not the
  slingshot. The eighth built docs/27's slate and flew it: **dialogue
  text on the wire** (the `message` block; digest `dialogue` entity;
  `ui` category's first producers; `oot://dialogue` with a recent ring;
  traverse QUOTES the box it fails on; `dialogue_choose` stick-nudge
  verified), **`save_game`** (Play_PerformSave behind the player's own
  pause gate — the bench's first game-native save landed live), and
  **`use_item(item)`** (the item subscreen's own C-assignment commit +
  a real C press; nuts 5→4 on first use — the verb the scrub ambush
  lacked). `oot://menu/items` + `oot://menu/equipment` are documents;
  map/quest stay NOT_YET. Mid-session, AJ's eyewitness commissioned an
  extra sense in under an hour: En_Box census entries carry the game's
  own treasure flag as **`opened`** (a body had pressed A at an
  already-open chest, twice) — spawn narration now says open/closed
  and open_chest_v5 refuses in 0.1 s by name. The first dialogue
  ocarina ever read was Navi saying its name: "Look, look, Claude! You
  can see down below this web using [C-Up]!" Tests 164 → 192. NO
  contract touch (everything implemented was already blessed).
  Live-unexercised: `dialogue_choose` awaits a natural choice box.
  **The heal-loop conversation (docs/26 felt-gap #1) is still the
  standing next-session opener, now with two deaths behind it, and 3F
  is still open.**

- **0.7.1 + THE SIXTH FLIGHT (2026-08-04, dojo docs/26 — the
  acceptance flight, flown the morning after 0.7.0 was built).** The
  place sense passed every acceptance check on first exercise
  (distiller diagnostic, region_entered narration, exact self-pose,
  first live bearing, oot://place, all three refusal classes held with
  measured zero movement) — and then the mission (3F by named legs)
  found three traverse bugs 164 tests had not, all fixed SERVER-side
  mid-flight (two /mcp restarts, a first): (1) a modal message box
  freezes the pad — traverse now fails fast naming it (dialogue text is
  now a MOTOR gap); (2) actors are not in the collision mesh — a
  mesh-clean route can wedge on a chest; wedged ~3 s now triggers a
  mesh-checked sidestep, distinct from the honest 20 s stall; (3) a
  curved climb sheet's centroid "at" hung beside that chest over a real
  gap in the vines — distill now keeps floor-touching BASE SEGMENTS and
  resolve_traverse aims grabs at them (generated maps need motor-grade
  grain, not just topology). The mission was NOT completed: the spider
  probe's "stationary" vine guards were SLEEPING patrols (activation
  distance — a 15 s envelope from a floor below is an artifact), and
  the run ended in the bench's FIRST DEATH, parked at 0.5 hearts inside
  a guard's wake-up radius. Zero material cost (game-native save, no
  items held; world reset to the boot save); the lesson priced in
  docs/26. Behavior patterns worth keeping: region-aware leg skipping
  (v2 — retry-safety means routing from where you ARE) and probes that
  ride BehaviorAbort detail into wakes (spider_probe). **Next session
  opens with the heal-loop conversation (docs/26 felt-gap #1) and the
  3F mission still open.**

- **0.7.0 — THE PLACE SENSE (2026-08-03, dojo docs/25: drafted,
  ratified by AJ, and BUILT in one session; contract bump — both
  SURFACE.md and MACHINE.md amended).** The lab pipeline ported
  (`collision.py`/`navgraph.py`/`place.py`) with DETERMINISTIC
  geometry-derived names (`ydan:r@30,0,70`; pinned in
  `lab/navgraph/test_ring.py` test 3). Digest grows `place.*` (region,
  on_mesh, exact self-pose under the ratified self-vs-others fairness
  line) and `nearest_enemy.bearing` (clock-face; NO wire patch was
  needed — the wire carried actor pos since first light, the gap was
  curation). New `place` event category (region_entered, fell),
  `oot://place` (judgments over names, no coordinates; v0 whole-scene
  reveal is a FLAGGED honesty gap — the blessed grain is the game's
  minimap and needs region→room membership), and `game.traverse()`:
  ONE named leg, all refusals BEFORE movement (off-mesh, candidates,
  non-adjacent; descent/crawl are honest not-yets), map-verified
  arrival, mid-op preemption polling. Cross-region routing stays the
  MIND's, by ruling. Mind-side distillation of game data is now
  CONTRABAND in scored play (lab = dev tooling, like savestates); the
  server needs `--o2r <path to SoH's oot.o2r>` or the place sense is
  off, loudly. **Flown and ACCEPTED the next morning — see the 0.7.1
  entry above and dojo docs/26.**

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
sixth flight ranked this list by felt pain, docs/26 has the reasoning;
0.8.0 CLOSED the old #5 — dialogue text — and the save_game half of
#4's compound interest):

1. **Boot identity verification.** (Promoted after the tenth flight's
   wrong-file hour; harness-backlog, tenth-flight wrap item 1.) The
   old #1 — the heal loop — is OFF the backlog by AJ's ruling
   (2026-08-07): a heal/retreat loop is a simple behavior for any run
   to write, not harness work; ignore the stale "standing opener"
   lines in the flight entries above.
2. **Descent.** `traverse` rightly refuses climbing down, but the
   refusal left Link COMMITTED to the ring with no path back but
   falling — a one-way map is a trap the mind walks into knowingly.
   Descending grabs need their own sequence (docs/25's honest not-yet,
   now with a body count).
3. **Enemy activation state in the census.** The spider probe measured
   three vine guards as stationary over 30 samples — they were ASLEEP
   (activation distance), and one of them killed Link. A sighted player
   sees a skullwalltula start to move; the census carries positions but
   not awake/asleep, and that gap manufactured a false belief with
   fatal consequences. (The chest `opened` bit is this item's pattern
   landed for props: the game's own flag, on the census, refusals by
   name — do the same with actor wake state.)
4. **Obstacle-aware ascend** — promote the sixth flight's retired
   spider-slalom (in `examples/sixth-flight/.../place_flight.py`) into
   traverse; straight-up is not enough on guarded walls. The ranged
   answer (kill the guard) now means TAKING the real slingshot first —
   it is behind the 2F door (the ring chest was the Dungeon Map;
   docs/26 erratum) — and with `save_game` live, what we take now
   KEEPS.
5. **Screenshot on the wire.** Two AJ screenshots resolved in seconds
   what probes argued about for minutes (the chest at the vine base;
   the gap in the vines) — and the eighth flight's chest impasse was
   again resolved by AJ's eyes. Four flights running.
6. `bgm_change` producer (enemy battle music on proximity — the game's
   own fair unseen-enemy channel), and **sight-gating for behaviours**
   (`game.actors()` is raw; seek.py filters the `sighted` bit by hand —
   that discipline wants to live in the surface).
7. **Room-clear chain hygiene** (eighth flight): fetch_item chases
   phantom drops — it walked Link into the atrium web hole TWICE (the
   `fell` sense narrated both; a voidout costs half a heart). The
   no-drop path needs an exit that doesn't wander. Related:
   `dialogue_choose` is built but live-unexercised (first scrub or
   shop), and the blind 12×A discipline in the free-play bodies can now
   be made sighted (read the ring, journal the text, then advance).

Then: prop pose/facing + affordance text (En_Box front = rot_y +
0x8000; the A-icon's action text is presented truth); the removed
`overhead-lurker` reflex is rebuildable per its own in-file condition;
attacker identity on `damage_taken` (needs a wire-side patch;
nearest-enemy-at-freeze is the documented workaround); Object_Kankyo
filter; En_Item00 param-aware naming; the absence-semantics foot-gun
lint (deferred); dojo-trial `approach_baba_v1`/`v2`, `climb_ladder_v1`,
the fifth-flight navgraph family, the sixth-flight place-flight family,
and now the seventh-flight free-play family (all UNGRADED). The old
"real idle-session channel delivery" question was ANSWERED 2026-08-07
by in-session experiment: a channel push alone never starts an idle
turn (it queues — this is why AJ had to type "wake" by hand), and a
Monitor event line does re-invoke an idle session. The one-monitor
flight convention is recorded in "Playing it directly" above; its
first live-flight exercise is still pending.

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
