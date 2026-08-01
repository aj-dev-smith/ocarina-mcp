# SURFACE.md — ocarina's tool/resource contract

**STATUS: DRAFT** — captured from the 2026-07-31 design sessions (AJ
participating and ratifying; full record: `../oot-dojo/docs/19`, with
docs/17–18 for context). Needs a hardening pass in a fresh session — plus
the machine's on-disk format — and AJ's explicit blessing before any tool
code is written.

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
- **Identification gating ("????").** No name until the game presents it
  to THIS save file (Navi/Z-target). Unknown actors are descriptors
  ("small skeletal biped"); after in-game identification the narration
  uses the name forever. Registry is save-file state, write-through. A new
  repo is a new kid.
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
save-file repo**. Interior nodes = modes; transitions = guarded events
(validated: whitelisted guard expressions, cooldowns, mandatory defaults,
reachability); leaves = **behaviors**, deterministic 20 Hz scripts. Wake
transitions (`wake_mind`) freeze the game and push a channel message. The
repo declares; the server runs; `reload_machine` is the only bridge.
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
machine events (`entered`, `exited`, `behavior_aborted`, `wake`).
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

## Open questions for the hardening session

- The machine's on-disk format (files, guard syntax, behavior interface).
- Versioning for benchmark comparability: what sensorium changes are
  scoring-relevant, and how runs pin server versions.
- Identified-registry custody (leaning: ocarina-managed save-file state,
  write-through, so the gate can't be forgotten).
- Channel burst behavior (undocumented upstream; measure).
- The exact state-digest schema (`oot://state`) — the single largest
  curation artifact; expect it to grow one region ahead of the player
  forever.
