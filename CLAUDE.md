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

- Tests: `python3 -m unittest discover -s tests -t .` (322; includes a
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
  **Wake delivery (0.10.0, the blocking wake — dojo docs/31, built and
  LIVE-VERIFIED 2026-08-07):** `resume()` unfreezes and BLOCKS; the
  next wake pack comes back as that call's tool result, with the
  `interval` "while you were out" digest. One call is one act of
  living: the world only runs while someone is listening, so a missed
  wake is structurally impossible. Plain `claude mcp add` is all the
  registration needed — no flag, no Monitor. If a `resume()` is ever
  severed (Esc, timeout, crash), re-attach with `await_wake()` —
  NEVER a second `resume()`, which re-runs the current node's body
  (docs/28). `max_block_s` on either verb returns an honest
  `{no_wake: true}` with the world still running. Historical paths,
  both still functional: channel push (needs
  `claude --dangerously-load-development-channels server:ocarina`;
  live-verified same day, now an optional nicety — a flag-loaded
  session gets the wake both ways) and the journal Monitor doorbell
  (ONE Monitor, `persistent: true`, on
  `tail -F -n 0 <repo>/journal/mechanical.jsonl | grep --line-buffered
  '"event": "wake"\|"event": "escalation"'` — `-n 0` and
  `--line-buffered` load-bearing; never ad-hoc background tails).
  Neither is needed when the mind holds the blocking call.
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

## State of play (server at 0.14.2; the nav program BUILT, LIVE-VERIFIED, and ACCEPTANCE-FLOWN — the eleventh flight ran the maze)

- **SLINGSHOT SCHOOL (2026-08-12 evening, dojo docs/36 — no version
  bump; server ran stock 0.14.2).** An eyewitness session with AJ:
  save-across-quit VERIFIED end to end (identity check passed cold
  five days after the maze flight's save; wire vs AJ's eyes vs
  docs/35, every surviving claim matched), then the bench's **first
  slingshot kills** (Z-locked; ammo ledger exact, 14 seeds spent and
  accounted) and the **manual-aim probe** (manual_shot v1→v10 in
  `../ocarina-flights/09-kokiri/kokiri/machine/behaviors/demo.py`,
  post-mortems in-file): `camera_yaw` IS the live aim-yaw sense
  (closed loop to ~0.1°; `facing` freezes in aim mode), the draw is
  a sustained C-hold with release-as-trigger, first person PERSISTS
  after firing (exit hygiene on the body), aim pitch is NOT on the
  wire (+y aims DOWN — AJ eyewitness), and a dormant baba's "small
  mode" is armor whose kill window the census already carries (head
  pos[1] flat 14–14 at 252 out, rose +32 at 141 — backlog #3's
  activation-distance evidence, measured live). TWO harness items
  filed in harness-backlog: **timeout_s never preempts a busy body**
  (a 90 s body ran 4+ min — real bug) and the **`player.aim` rider**
  (mode/yaw/pitch; fairness-clean self-knowledge). AJ's standing
  commission for next session: **GOHMA** ("I wanna watch you beat
  ghoma") — tree mouth → 3F (shoot_guard_v1's moment) → web dive →
  B1 sticks/fire → 2-3-1 scrubs → the fight. File C still holds the
  village-floor save (SoH closed before an in-dungeon save; seeds
  restored to 30 on next boot).

- **THE ELEVENTH FLIGHT — THE MAZE (2026-08-07 late night, dojo
  docs/35: the docs/30 + docs/34 acceptance mission, FLOWN).** Flag
  off, file C (AJ hand-picked; identity verified in 1 s — the machine
  was parked so the slot-0 masher couldn't repeat the blind boot),
  AJ watching, nine blocking-wake acts of living, eight mid-flight
  hot-swaps. Deku Tree atrium → out the mouth (3.6 s) → the trail by
  reachable()-elected hops (v1's straight-line hops post-mortemed
  in-file) → village → the ninth flight's crawl bodies → the training
  area. docs/30 criteria: 1 ✓ (refused in 1 ms, 0.00 units moved,
  regions + all three legs out named, journal-verbatim), 2 ✓ + 7 ✓
  (maze_run.json: corridor polyline vs wall-crossing chord; routed
  legs held 18–49 units of wall at full speed), 3 ✓ (collector with
  NO blacklist, reachable() election, rupees 9→14), 4 ✓ (bush refused
  by name before contact, screenshot witness), 8 ✓✓ (the journaled
  gate + a mid-run hold + the counterexample priced: all three
  0.25-heart scratches were gate-skipped movements), 6 ✓ with audit
  notes, 5 PARTIAL (two candidates journaled as instrument
  diagnostics, neither confirmed — still open). docs/34 rode along
  (fogged ydan at boot; earned regions re-presented). Instrument
  findings filed in docs/35: census is loaded-room-only (met in the
  field), prop radii want wire collider sizes, seam-flap hysteresis,
  crawl entry wants the centerline (the place doc's own edge name
  carries it). Closed with a game-native save. Remaining from the
  program: criterion 5's confirmed false refusal, and docs/34
  criterion 6's fresh-start example (needs a fresh file, not C).

- **0.14.2 — THE DUNGEON-ITEMS RIDER (2026-08-07, later the same
  night, autonomous — docs/34 criterion 4 closed and LIVE-VERIFIED).**
  The wire grows `dungeon_items` (map/compass/boss_key/small_keys for
  the CURRENT dungeon by the game's own `gSaveContext.mapIndex`;
  ABSENT outside dungeon-indexed scenes — Map_Init's own case list,
  never a wrong row) and the `give_dungeon_item` op; ocarina grows
  `dev_give_item` (--dev-tools, journaled, scored-refused, dungeon
  items ONLY — the phase-2 slate stays evidence-first), whose reply
  carries the row read back after the grant (the read-back is the
  proof — the wallet-delta rule). 0.14.0's Map widening now runs live:
  the live pin granted the Map in a fogged ydan and `oot://place`
  widened to outline entries carrying no legs. The whole live suite
  ran green with ZERO skips (11 tests, ~24 s, cold start): the room
  pin now establishes Kokiri itself instead of skipping when the boot
  save wakes elsewhere, and the fresh-entry fog cap counts
  presence-earned regions only (a boot line owning the Map adds
  outlines legitimately — the ratified widening, not a leak). No
  contract touch: the dev family's "successors" clause covers the
  verb; the widening presentation was ratified in docs/34. Tests
  437 → 444. Criterion 4's dev rider is CLOSED; the remaining filed
  instrument riders are room tables (room-grain reveal), the enemy
  awake/asleep flag (backlog #3's open half), and Compass chest
  markers (deferred: the census sees only the loaded room).

- **0.14.1 — THE LIVE PASS (2026-08-07, the same night; AJ's "just go
  for it").** SoH launched from the CLI (Sail on test port 43390; the
  session's registered server kept 43384), the harness booted the game
  ITSELF — every throwaway live repo's machine now opens on first
  light's boot_from_title (A/START only, slot 0 by construction) and
  `await_game` holds tests until PLAY state — and all TEN live tests
  ran green from a cold start: the dev family re-verified, the walk
  family (cliff refused cold with zero movement in-body; reachable
  agreeing both directions; a routed walk arriving map-verified) and
  the discovery family (fresh-entry fog + warp-out/warp-back holds)
  verified on first-ever run. One server-side fix rode home, the live
  run's own find: walk_to's arrival verdict over-read region identity
  at a region seam (village floor meets the Know-It-All plateau) —
  DISTANCE is now arrival, region is diagnosis, and the reply's
  `region` names where the map says Link IS. Harness lessons pinned
  in tests/live: the boot gate (racing the attract demo wedged every
  warp), patient retry on transition-in-progress, spawn-settle before
  probing, ensure_mapped_ground (test_3's elected target walked Link
  through the Know-It-All open-doorway load trigger into an unmapped
  interior — each class establishes its ground, never inherits it).
  **Remaining before scored claims: the maze acceptance flight, flag
  off — docs/30 criteria 1–8 + docs/34's in one mission (needs AJ).**

- **0.14.0 — THE DISCOVERY GRAIN (built 2026-08-07, late the same
  night, right after 0.13.0 — dojo docs/34's ratified slate,
  complete).** Knowledge in the head is fair; geometry in the hand
  must be earned. `oot://place` now implements its blessed reveal
  grain: overworld/interiors whole at entry; DUNGEON_SCENES (ydan,
  ydan_boss) presence-gated — unvisited regions ABSENT, frontier legs
  "destination unknown" (edge names kept; traversing one IS
  exploration), `region_discovered` cue once per save line, discovery
  persisted per line (`ocarina/discovery.py` →
  `.ocarina/place_discovered.json`) and SEEDED from existing journals.
  Refusals + the reach rider inherit the fog ("somewhere you haven't
  been"); self never fogged. Honest gaps, loud in the document: room
  grain (no room table in scene collision — v1 fogs at REGION grain,
  under-revealing; region→room bindings observed off the wire's `room`
  field) and `dungeon_items` (Map widening built, waiting on the wire
  rider — CLOSED by 0.14.2 the same night, live). Tests 421 → 437;
  live family
  (`tests/live/test_discovery_live.py`, criteria 1+5) RUN and GREEN
  the same night (see 0.14.1). **The maze acceptance flight now covers
  docs/30 AND docs/34.**

- **0.13.0 — ROUTE-AWARE WALKING (built 2026-08-07, late the same
  night, in an autonomous session while AJ was mobile — dojo docs/30's
  ratified slate, complete).** The region is the answer:
  `game.walk_to(x, z)` routes inside the current region and REFUSES
  everything else before movement, by name, in milliseconds
  (`resolve_walk` in place.py holds the whole grammar — off-mesh,
  target off map, target in another region + the legs out, no path,
  blocked by a census prop at your N o'clock); `game.reachable` is the
  refusal with the walk removed (the election filter two flight bodies
  reinvented as blacklists). Clearance is combat-safety: A* penalizes
  wall-adjacent polys and waypoints hold the adaptive offset
  min(desired, (width − 24)/2) — midline in pinches, squeezes
  reported, a corridor Link fits never refused. Riders landed with it:
  the STANDING gate (docs/28 learning 4 CLOSED — on an actor surface
  on_mesh goes False and refusals name the height instead of the wrong
  region), `nearest_enemy.reach` + `nearest_enemy.moving` (escort
  riders; moving is census deltas — awake/asleep still needs a wire
  flag, backlog #3's open half), `game.actors(sighted=True)`, and the
  distiller's crawl end-clustering FIX (crawl faces probe along their
  own normals; spot04's sword tunnel and ydan's B1 crawls all link —
  the tunnel interior is its own region, village ↔ tunnel ↔ training).
  Exceptions renamed Route*/aliased Traverse* (one family). Contract
  bump: SURFACE.md place bullet + MACHINE.md "The routed walk", both
  per docs/30's ratified Contract impact. Tests 379 → 421 (real-o2r
  pins: the crawl link, maze-region clearance).
  `tests/live/test_walk_live.py`: a walk probe behavior carries
  walk_to/reachable results out via walk_result.json with
  zero-movement + elapsed measured in-body — RUN and GREEN the same
  night (see 0.14.1; the run found the seam-arrival fix).
  **Next: the maze acceptance flight, flag off — docs/30 criteria 1–8
  and docs/34's in one mission (needs AJ).**

- **THE NAV PROGRAM (2026-08-07 — FULLY RATIFIED, all three docs,
  all open calls as recommended: AJ, late that night, "ok both fully
  ratified with your recommended approaches").** The nav conversation
  (AJ's flight testimony: wall-grinding, corner slides, the house
  table, the boulder maze) produced a three-doc program, built in
  order: **docs/33** the dev harness (0.12.0 — BUILT and
  LIVE-VERIFIED the same night, see below); **docs/30** route-aware
  walking (0.13.0 — BUILT the same night, see above; live pins
  pending; the training-area maze is the acceptance mission);
  **docs/34** the discovery grain (0.14.0 — BUILT the same night, see
  above; the whole three-doc program landed within a day of its
  ratification). AJ's fairness line,
  now doctrine: knowledge in the head is fair; geometry in the hand
  must be earned. In flight same night: **0.12.1** — the wire grows
  a `loads` play-state-init counter + current `room` on the state
  payload and an optional `room` arg on the teleport op (fixes the
  live-found same-scene warp timeout and the cross-room teleport
  glitch; the `room` field doubles as docs/34's presence signal).

- **0.11.0 — BOOT IDENTITY (2026-08-07 evening, dojo docs/32:
  designed, all four open calls ratified by AJ, and built in one
  sitting — the same day as 0.10.0 and the tenth flight).** Backlog
  #1 closed. The repo may declare its save line in **`identity.json`
  at the repo root** (monotone-facts-only fingerprint — owned gear,
  B/C assignments, inventory, heart-capacity floor; volatiles in
  `journal_only`, read every boot and asserted never; provenance
  dating every claim). The **RUNTIME judges** — not the machine — on
  every `load_game` (the slot rides the event's `file` field, which
  senses.py now presents on the `game_loaded` cue) AND on every
  attach to an already-loaded world (the rehydrate gap the tenth
  flight's wrong-file hour began under). Fail closed: broken
  declaration, missing wire blocks, or a load event without `file`
  all refuse — the mismatch is the bench's first RUNTIME-initiated
  wake (transition `identity`, hold default, freeze-confirmed,
  through the blocking verbs like any wake). No declaration = check
  OFF with one loud diagnostic (the --o2r pattern). The boot line
  (B/C, gear, inventory with ammo, hearts, counters) journals on
  EVERY load unconditionally — the tenth flight's tell sat unread
  for an hour. The 09-kokiri machine-side prototype (lock.json +
  identity.py + gate nodes + root slot guard, exercised that morning
  by fakewake) is RETIRED by AJ's ruling — one owner of the check —
  its lock content promoted to that repo's identity.json. Contract
  touch: both SURFACE.md and MACHINE.md amended per docs/32's
  ratified calls. Backlog #2 re-statused with source evidence: the
  equips.worn "nibble-order bug" theory is unsupported (SoH's own
  enum/shifts/masks match equipment_view's decode); the live
  null-rows sighting needs one read against a real game. Tests
  306 → 322. **LIVE-VERIFIED the same evening, every path:** the
  blind boot loaded the OLD line AGAIN (slot 0 — the tenth flight's
  exact fraud, reproduced by accident) and was refused in ~1 second
  (`loaded slot 0, declaration is slot 1 (C)` + four named diffs,
  frozen, pack through the blocking verb); AJ hand-picked file C and
  the journal answered `identity verified against identity.json
  (save C, slot 1)`. The wrong-file hour is now a wrong-file second.
  That live pass also CLOSED backlog #2: the old line's owned rows
  read tunic/boots-only while file C's parse in full through the
  same decode — the tenth flight's "null rows" were TRUTH about a
  save genuinely missing its sword/shield owned bits (docs/29
  corrected in harness-backlog), and equip()'s "not owned" refusal
  was right all along.

- **0.10.0 — THE BLOCKING WAKE (2026-08-07, dojo docs/31: designed,
  ratified, built by an Opus 5 agent, reviewed, and live-verified in
  one session — the same day as the tenth flight).** The morning's
  fakewake experiment finally live-verified the channel flag; AJ's
  verdict ("I kind of hate the flag") turned the session into the
  replacement: wake delivery as a plain blocking MCP call, portable
  to any client. `resume(max_sleep?, max_block_s?)` unfreezes and
  BLOCKS, the next wake pack returning as its tool result — the
  world only runs while someone is listening, so ten flights of
  dropped pushes become structurally impossible, not mitigated.
  `await_wake(max_block_s?)` graduates from spec-only to built as
  the re-attach verb (a severed block must never be re-armed with
  resume() — docs/28's re-runs-the-body finding). One awaiter at a
  time; severed block = machine plays on, next wake parks frozen
  with its default armed; `max_block_s` expiry returns an honest
  `{no_wake: true}`. The pack grew the **interval digest** ("while
  you were out": two-endpoint state deltas, repeat-collapsed event
  tallies, per-interval firsts quoted verbatim, wall + game clocks —
  compression of already-curated narration, never a new sense;
  `IntervalDigest` in senses.py flags its own gaps in-file). Blocking
  verbs run on their own server thread so status/ping/cancel never
  starve; MCP cancellation severs cleanly, including the
  cancel-before-arm and cancel-crossing-a-wake races. Contract bump:
  SURFACE.md amended (docs/31 ratified all four open calls as
  recommended; the mini-harness deferred to its own design pass).
  Tests 263 → 288. LIVE-VERIFIED same day, this session: blocking
  resume returned a real fakewake identity-mismatch pack (interval
  included, 63.9 s blocked), the flag-loaded session ALSO got the
  channel push (both-ways confirmed), and both verbs' `no_wake` cap
  answered honestly. **Screenshot rode the same bump** (backlog #5,
  built by a second worktree agent the same session, merged on top):
  the AgentLink `screenshot` op reads framebuffer 0 (Metal's deferred
  blit is the tested-in-build path — AJ runs Metal; GL implemented,
  unexercised), raw RGBA8 box-averaged to `max_width` (default 640,
  both sizes always reported), PNG'd ocarina-side in stdlib
  `screenshot.py`, returned as a real MCP image block with the
  overlay's labels in frame (beliefs ON truth, `includes_debug_overlay`
  stated). Needs the SoH rebuild; live-unexercised. Tests 288 → 306.

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

1. **Boot identity verification — CLOSED and LIVE-VERIFIED (0.11.0,
   2026-08-07 evening, dojo docs/32).** identity.json + the runtime
   check + the identity wake; the same evening the blind boot loaded
   the wrong line AGAIN and was refused in a second, then file C
   verified clean. (The old #1 — the
   heal loop — is OFF the backlog by AJ's ruling (2026-08-07): a
   heal/retreat loop is a simple behavior for any run to write, not
   harness work; ignore the stale "standing opener" lines in the
   flight entries above.)
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
   name — do the same with actor wake state.) **Half landed in 0.13.0:**
   `nearest_enemy.moving` (census deltas, the watching eye's own
   evidence) ships; the awake/asleep flag itself still needs the
   wire-side patch — a sleeping patrol that hasn't stirred yet still
   reads `moving: false`, which is exactly the sixth flight's trap.
4. **Obstacle-aware ascend** — promote the sixth flight's retired
   spider-slalom (in `examples/sixth-flight/.../place_flight.py`) into
   traverse; straight-up is not enough on guarded walls. The ranged
   answer (kill the guard) now means TAKING the real slingshot first —
   it is behind the 2F door (the ring chest was the Dungeon Map;
   docs/26 erratum) — and with `save_game` live, what we take now
   KEEPS.
5. **Screenshot on the wire — BUILT 2026-08-07** (same session as
   0.10.0, by a worktree agent; live-unexercised — needs the SoH
   rebuild, then a real `screenshot()` against the running game).
   The four-flights-running pain (AJ's eyes resolving what probes
   argued about) now has a tool: framebuffer 0 with the overlay's
   labels on it, real pixels as an MCP image block. Metal is the
   tested-in-build path (AJ's live backend); GL is implemented but
   unexercised. Requires a Shipwright built after 2026-08-07;
   an older one answers loudly, never silently.
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
(two experiments + the channels reference doc): every flight had
registered ocarina with plain `claude mcp add`, which never loads it
as a CHANNEL, so its pushes were silently dropped by documented
research-preview behavior — that is the whole mystery of AJ typing
"wake" by hand (second light's round-trip was drive.py, a custom
client, which is why it worked). The flag was live-verified the same
morning — and AJ's verdict on it ("I kind of hate the flag") produced
0.10.0's blocking wake the same afternoon, which retires the question
entirely; see the 0.10.0 state-of-play entry and rule 7.

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
5. **No practice tools on the PLAY surface, ever** (amended by AJ,
   2026-08-07 — dojo docs/33, the dev harness). Absent all the way
   down at the layer that plays: `game.py` has no savestate methods
   and no `console()`, behaviors and machine source can never name a
   practice verb, game-native saves only. AMENDMENT: under an
   explicit `--dev-tools` server flag, a `dev_*` MCP tool family
   (warp, teleport, successors) exists for harness development and
   live e2e testing (`tests/live/`) — server-layer only, never
   behavior-reachable, every use journaled permanently (boot banner +
   per-call events), refused outright on repos declaring
   `"scored": true` in identity.json. Savestates stay absent in EVERY
   mode. The SURFACE.md Benchmark-purity bullet carries the same
   amendment at the 0.12.0 build (docs/33 has the ratified text).
   Scored play requires the flag off, and the journal proves it.
6. **The machine is source in the save-file repo.** Ocarina runs it;
   `reload_machine()` validates + hot-swaps; connect rehydrates from the
   repo. The server's live state is never the only copy. The 20 Hz leaves
   are called **behaviors** — never "skills", which means Claude Code
   SKILL.md artifacts only.
7. **Wake transport is the blocking call** (0.10.0, dojo docs/31,
   ratified by AJ and live-verified 2026-08-07). Freeze-confirmed
   first, always; then the pack returns as the result of the blocked
   `resume()`/`await_wake()` — plain MCP, portable to any client, no
   research preview. One awaiter at a time (loud error, never a
   queue); a severed block leaves the machine playing on (it is the
   autopilot) and the next wake parks frozen with its default armed —
   pending_wake demoted from normal path to crash recovery. Wake
   defaults are unchanged: blocking guarantees a LISTENING mind hears
   every wake; defaults remain the answer to a dead one. Channels
   survive as an optional Claude Code nicety (the push carries the
   same single-sourced pack; requires the
   `--dangerously-load-development-channels server:ocarina` flag —
   research preview, allowlist, silently dropped without it, which
   was the whole ten-flight missed-wake mystery). Scored play
   specifies the blocking path. Resources cannot be subscribed to.
8. **Not-yet-built surface stays honest.** Tools/resources awaiting
   instrument work (file-select/death/save-screen UI navigation,
   ocarina note entry) are registered and return explicit not-yet
   errors naming what they wait on (`NOT_YET` in server.py). Never
   quietly stub one. (0.8.0 graduated dialogue text; 0.9.0 equip and
   buy; 2026-08-07 screenshot.)
