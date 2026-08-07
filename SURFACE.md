# SURFACE.md — ocarina's tool/resource contract

**STATUS: BLESSED (AJ, 2026-08-01)** — captured from the 2026-07-31
design sessions, hardened 2026-08-01 (AJ participating and ratifying
throughout; full record: `../oot-dojo/docs/19`, with docs/17–18 for
context). This file and `MACHINE.md` are the contract; tool code
implements them exactly. A change to either file is a major version bump
and needs AJ's blessing (see Versioning).

**Amended 2026-08-03 (ocarina 0.7.0): THE PLACE SENSE** — dojo docs/25,
ratified by AJ the same day (the fifth flight, docs/24, is the evidence
base). Adds the place principle pair below, the `oot://place` resource,
the `place` event category, the `place.*` digest section, the bearings
rider, and the `traverse` behavior primitive (MACHINE.md).

**Amended 2026-08-07 (ocarina 0.10.0): THE BLOCKING WAKE** — dojo
docs/31, ratified by AJ the same day ("lets implement"; the fakewake
channel verification that morning is the evidence base). `resume()`
now BLOCKS and returns the next wake pack; `await_wake()` is promoted
from spec-only to built (the re-attach verb); the wake pack gains the
interval digest; channels demote to an optional Claude Code transport.
See "The wake" below.

## The goal (AJ, verbatim in spirit)

1. Enable inputs via the behavior machine.
2. Give the fairest possible representation of what ten-year-old AJ got
   via his senses, in an optimized way.

**North star:** ocarina is the **narration layer** — an audio-description
track; accessibility engineering for a player with an unusual sensory
profile (perfect structured text, no continuous video). The game already
computes every event; detection is free via GameInteractor hooks.
**Curation is the work.**

## Principles (each one is a fairness rule)

- **Presented, not computed.** Expose what the game presents to a player,
  never what it merely computes. Telegraph pose: yes. Internal frame
  counter: no. Every field must answer "what audiovisual presentation is
  this the text form of?"
- **The UI principle.** Anything a UI developer on the OoT team built,
  ocarina rebuilds as a resource (structured view) + tools (the actions).
  One document per screen, mirroring the game's own information
  architecture. Verbs are context-legal, not context-mounted: wrong-screen
  calls return clean errors.
- **Sound is an information channel.** The sound team's work as event
  text: howls, stingers, BGM shifts, the low-health alarm.
- **Official names, no discovery system.** (Decided 2026-08-01, AJ —
  supersedes docs/19's identification gating.) Actors carry their
  official names from first sighting: the name is the text form of the
  visual gestalt — ten-year-old AJ saw it and knew "skeleton" instantly,
  and the proper noun carries no more game knowledge than the sprite
  already gave a sighted player. Z-targeting and asking Navi yields
  *additional* tips as dialogue text, which the mind may choose to store
  in its knowledge files — depth is earned; identity is free.
- **Vocabulary, not grammar.** Events are a small closed grammar with open
  vocabulary. New regions add cue values; a new category is a rare,
  reviewed change.
- **Senses rich, wakes minimal.** That night exists = sense (always
  provided). That night matters = knowledge (earned in play).
- **Self vs others** (docs/25, AJ 2026-08-03). Superhuman knowledge of
  OTHERS is where unfairness lives; confidence about SELF is an
  accessibility obligation — a sighted player has continuous visual
  self-localization the text channel lacks. Exact self-pose
  (`place.x/y/z/facing`) is compensation, not superpower; everything
  mind-facing about the WORLD stays judgments in eye-units, with exact
  numbers body-side only (the two-audience split, applied to space).
- **The place sense is generated, never authored** (docs/25). Region
  graphs distill from the scene's own collision data; identifiers are
  deterministic (geometry-derived) so mind-side knowledge accrues on
  them; evocative names are the mind's job. Cross-region ROUTING is
  cognition (the mind's, over `oot://place`); within-region steering
  and single named legs are motor (`traverse`, MACHINE.md), and
  traverse refuses anything the map does not vouch for — off-mesh,
  unverified candidates — BEFORE moving. Corollary (ruled 2026-08-03):
  mind-side distillation of game data files is CONTRABAND in scored
  play, exactly as savestates are — the lab pipeline is dev tooling.
- **No pad verb. Ever.** The mind acts only by machine states; behaviors
  act at 20 Hz inside the server.
- **Benchmark purity.** No savestate/load, no trial-drill, no merge-gate
  tools on this surface — not gated, ABSENT. Game-native saving only
  (it's a menu function). Crash recovery = relaunch + load last save,
  like a human. (Savestate machinery exists only as dev tooling in the
  workshop repo, for instrument validation.)
- **Coverage leads the frontier.** Sense completeness is required one
  region ahead of the player, not globally.

## What ocarina runs

One thing: a **hierarchical state machine defined as source in the
save-file repo** — on-disk format specified in `MACHINE.md`. Interior
nodes = modes; transitions = guarded triggers, event-triggered (`on` +
`where`) or state-triggered (`when`, watched at 20 Hz, firing on the
false→true edge) — validated: whitelisted guard expressions, load-checked
`state.*` paths, cooldowns, mandatory defaults, reachability. Guards read
the curated sensorium, so "presented, not computed" binds the machine
layer too. Leaves = **behaviors**, deterministic 20 Hz scripts, preempted
at game-op boundaries when a transition leaves them. Wake transitions
(`wake_mind`) freeze the game and deliver the wake pack as the return
value of the blocked `resume()`/`await_wake()` call (0.10.0; a channel
push rides along for flag-loaded Claude Code sessions). The repo
declares; the server runs; `reload_machine` is the only bridge.
On connect, the server rehydrates from the repo — live state is never the
only copy.

## Tools (draft)

Machine + mind verbs:
| tool | purpose |
|---|---|
| `status()` | server version, game connection, machine loaded/hash, current node |
| `reload_machine()` | validate + hot-swap the machine from repo source; returns diagnostics |
| `force_state(node)` | jump the machine now |
| `set_directive(text)` | standing intent (feeds wake packs, HUD, telemetry) |
| `resume(max_sleep?, max_block_s?)` | unfreeze and BLOCK; returns the next wake pack (0.10.0). Optional heartbeat override; optional block cap returning honest `no_wake` |
| `await_wake(max_block_s?)` | listen WITHOUT resuming (0.10.0): returns a parked wake immediately, blocks if the world is running, errors if a delivered wake is unanswered. The re-attach verb after a severed block — never re-arm with `resume()` (it re-runs the node's body) |
| `escalate(reason)` | up the ladder (ultimately to the human; journaled) |

UI verbs (per the UI principle; the mind chooses, the server does the
button mechanics):
| tool | screen |
|---|---|
| `create_file(name)` | file select — the naming ceremony |
| `continue_game()` / `save_and_quit()` | death & save screens |
| `save_game()` | game-native save (benchmark-legal: it's a menu function) |
| `dialogue_choose(option)` / `dialogue_advance()` | text boxes |
| `equip(item)` / `use_item(...)` | pause subscreens |
| `buy(item)` | shops |
| `play_song(name)` | the ocarina interface (note entry is UI mechanics; choosing the song is the game) |

Senses (active):
| tool | purpose |
|---|---|
| `scan(...)` | collision fan — geometry sense |
| `screenshot()` | vision on demand; a debugging sense, never a stream |

## Resources (draft)

- `oot://state` — the full queryable game-state JSON: what a player sees
  and (gameplay-relevant) hears at this instant. Topological digest for
  the mind; behaviors see raw values server-side at 20 Hz.
- `oot://events` — the event log, queryable (last N, by category/actor,
  since t). See below.
- `oot://dialogue` — current/recent text verbatim, choices as data.
- `oot://menu/items|equipment|map|quest` — the pause subscreens as
  documents (songs learned live in quest).
- `oot://place` — the place sense (docs/25): this scene's region graph
  as judgments over stable names — regions with judged sizes and
  elevations, typed climb edges with judged heights, drop/jump
  candidates honestly marked unverified, `you_are_here`. No raw
  coordinates (names carry quantized centroids as IDENTITY, by the
  blessed scheme). Reveal grain: the blessed grain is the game's own
  minimap (dungeon rooms as entered; Map/Compass shelved with the
  principle recorded — the items simulate the human player's benefit,
  never the full lab-grade graph); v0 reveals whole-scene at entry, a
  documented honesty gap flagged in the document itself until
  region→room membership exists.
- `oot://machine` — declared vs LIVE machine, as two columns (the
  conjunction discipline: "repo says armed" ≠ "server confirms armed").
- `oot://journal/mechanical` — the persisted event timeline.

## The event log

State answers *what is*; the log answers *what happened*; neither is
derivable from the other (a howl leaves no trace in state; a poll misses a
lunge). Ring buffer, always recording. **Every wake pack automatically
carries its recent tail** — the mind never wakes into a contextless
present. The timeline **interleaves world events and machine events**
(`nightfall` → `entered: navigate_field_night` → `telegraph: stalchild` →
`damage_taken`) so postmortems can attach blame to nodes.

Grammar (closed, ~a dozen categories; vocabulary open):
`telegraph`, `sfx`, `bgm_change`, `environment`, `spawn`, `despawn`,
`damage_taken`, `damage_dealt`, `actor_state`, `pickup`, `ui`, `place`,
plus machine events (`entered`, `exited`, `behavior_done`,
`behavior_aborted`, `wake`). (`behavior_done` added in the 2026-08-01
hardening pass — leaf completion is explicit; see MACHINE.md. `place`
added 2026-08-03 under the rare-reviewed-change rule, docs/25:
`environment` is the world changing, `place` is YOUR relationship to
the world changing — cues `region_entered`, `fell`.)
Example: `{"event": "telegraph", "actor": "deku_baba#3", "cue": "rearing",
"t": 48212}`.

## The wake (blocking delivery — 0.10.0, dojo docs/31)

Wake delivery is a **plain blocking MCP tool call**: the mind, holding
a frozen world, thinks and acts via the verbs, then calls `resume()`.
The world unfreezes and runs; the call blocks. The next wake —
transition, escalation, heartbeat, any of them — freezes the game
(**freeze-confirmed first**, unchanged) and returns the wake pack **as
the result of the blocked call**. One call is one act of living. The
world only runs while someone is listening, so a wake cannot fire into
silence — the missed-wake failure is structurally impossible, not
mitigated. A blocked call costs nothing while blocked; portable to any
MCP client; no research-preview flag, no session required.

The wake pack: reason, state digest, event tail, current node,
directive, and (0.10.0) the **interval digest** — a compression of the
interval since the last wake in the narration layer's own voice: state
delta (hearts, rupees, region trail, items), repeat-collapsed event
tallies, novel firsts quoted verbatim, wall/game clocks. Fairness: the
digest summarizes narration that already passed curation; it computes
nothing the journal didn't present. Raw events stay in `oot://events`.

Rules (ratified with docs/31):
- **One awaiter at a time.** A second concurrent `resume()`/
  `await_wake()` is a loud error, never a queue.
- **Severed block** (cancellation, client crash, timeout): the machine
  plays on — it IS the autopilot — and the next wake parks frozen as
  `pending_wake` with the wake's declared default armed, exactly
  today's machinery, demoted from normal path to crash recovery.
  Re-attach with `await_wake()`, never `resume()` (docs/28:
  resume-after-wake re-runs the current node's body).
- **Honest cap.** Both verbs take optional `max_block_s`; on expiry
  they return `{"no_wake": true, "elapsed_s": …}` and the client
  re-arms with `await_wake()`. For clients with short MCP timeouts;
  Claude Code's stdio default (~28 h) never sees it.
- Wake **defaults** are unchanged: blocking guarantees a listening
  mind hears every wake; defaults remain the answer to a dead one.

The skeleton wake set (shipped by navi, game-agnostic): health drop,
novel actor, dialogue, stuck, heartbeat. Everything else the mind
wires as it learns what matters.

**Channels (demoted 2026-08-07 to optional transport):** a Claude Code
session started with `--dangerously-load-development-channels
server:ocarina` also receives each wake as a channel push
(live-verified 2026-08-07). A nicety for interactive sessions; scored
play specifies the blocking path.

## Versioning (decided 2026-08-01)

- **Semver with benchmark meaning baked into the bump rules.** A diff
  that touches SURFACE.md or MACHINE.md is a **major** bump, full stop —
  the contract files ARE the version boundary, so "scoring-relevant" is
  a review discipline, not a judgment call at comparison time. Minor =
  internals that cannot change what's observable; patch = bugfixes.
- **Runs pin, save files record.** The save-file repo carries a lockfile
  stamped at `create_file` time with ocarina's version + machine format
  version; `status()` reports both; a mismatch on connect is a loud
  diagnostic, never a silent adapt. Cross-run comparisons are only
  claimed at equal major versions.
- **Coverage-leads-the-frontier composes cleanly:** new-region senses
  are major bumps, and that's fine — the benchmark artifact reads
  "% of OoT at ocarina vN," exactly as SWE-bench results name their
  scaffold (harness and model are separate axes).

## Open questions for the hardening session

- ~~The machine's on-disk format~~ — RESOLVED 2026-08-01: see `MACHINE.md`
  (files, two-trigger grammar, guard language, behavior interface,
  reload validation).
- ~~Versioning for benchmark comparability~~ — RESOLVED 2026-08-01: see
  Versioning above.
- ~~Identified-registry custody~~ — MOOT 2026-08-01: identification
  gating retired (see the naming principle above); no registry exists.
- Channel burst behavior (undocumented upstream; measure).
- The exact state-digest schema (`oot://state`) — the single largest
  curation artifact; expect it to grow one region ahead of the player
  forever.
