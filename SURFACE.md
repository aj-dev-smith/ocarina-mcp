# SURFACE.md — ocarina's tool/resource contract

**STATUS: BLESSED (AJ, 2026-08-01)** — captured from the 2026-07-31
design sessions, hardened 2026-08-01 (AJ participating and ratifying
throughout; full record: `../oot-dojo/docs/19`, with docs/17–18 for
context). This file and `MACHINE.md` are the contract; tool code
implements them exactly. A change to either file is a major version bump
and needs AJ's blessing (see Versioning).

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
(`wake_mind`) freeze the game and push a channel message. The repo
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
| `resume(max_sleep?)` | unfreeze, back to autopilot; optional heartbeat override |
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
`damage_taken`, `damage_dealt`, `actor_state`, `pickup`, `ui`, plus
machine events (`entered`, `exited`, `behavior_done`, `behavior_aborted`,
`wake`). (`behavior_done` added in the 2026-08-01 hardening pass — leaf
completion is explicit; see MACHINE.md.)
Example: `{"event": "telegraph", "actor": "deku_baba#3", "cue": "rearing",
"t": 48212}`.

## The wake (MCP channels)

Verified 2026-07-31 (research preview; needs org enablement + the
`--dangerously-load-development-channels` flag for now): local stdio
servers can push `notifications/claude/channel`; payloads land in the
session context as `<channel source="ocarina">` blocks; delivery is
queue-until-idle, grouped, no mid-turn interrupts (harmless here —
cognition happens in stopped time, so no game events fire mid-think).

Flow: `wake_mind` transition → **freeze-confirmed first** → channel push
with the wake pack (reason, state digest, event tail, current node,
directive) → idle session wakes → thinks → acts via the verbs → `resume`
unfreezes. The skeleton wake set (shipped by navi, game-agnostic):
health drop, novel actor, dialogue, stuck, heartbeat. Everything else the
mind wires as it learns what matters.

**Portability fallback (spec only, not built now):** a degenerate
long-poll `await_wake()` tool so non-Claude MCP clients can play. Channels
are the Claude-native path.

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
