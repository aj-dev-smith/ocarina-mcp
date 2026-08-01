# ocarina

The instrument you play Hyrule through.

Ocarina is an MCP server that exposes Ocarina of Time (via Ship of
Harkinian) to an AI agent as a fair, bounded tool surface. It is one third
of **OoT Bench**:

| piece | role |
|---|---|
| **ocarina** (this repo) | the instrument — the only way the agent touches the game |
| **navi** | a Claude Code plugin that teaches an agent to play through ocarina |
| **save files** | playthrough repos — one per attempt, where skills and knowledge accumulate across plays |

## The one design principle

**Fairness by construction: the tool surface IS the ruleset.** There is no
"press button" verb — an agent acts by running skills it has authored,
executed deterministically at the game's 20 Hz. In expedition mode the
practice tools (savestates, drill trials) are not mounted at all: a live
playthrough cannot cheat, because the verbs don't exist on the wire.

What the server owns: the Sail link to the game, the 20 Hz skill executor,
a trigger engine (reflexes the agent registers, validated and enforced
without tokens), a behavior state machine, freeze-time thinking
(`await_wake` — the world stops while the mind decides), and mechanical
telemetry.

## Status

**Pre-surface-design.** The tool/resource surface is the contract and gets
designed before any tool code is written. The design record and the
validated internals this server will wrap live in the OoT Bench workshop
repo (`oot-dojo`) — everything mechanical here (executor, freeze
discipline, savestate confirmation, collision scanning) has already been
proven against the real game there.

License: TBD — open-sourcing the layers is the plan once the foundation is
in place.
