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
"press button" verb — the agent acts by putting a **hierarchical state
machine** in a state; its leaves are **behaviors**, deterministic scripts
executed at the game's 20 Hz. Practice tools (savestates, drill trials)
are not mode-gated on this surface — they are **absent**: a playthrough
cannot cheat, because the verbs don't exist on the wire. Saving is
game-native only (it's a menu function).

What the server owns: the Sail link to the game, the 20 Hz behavior
executor, the machine runtime (the machine itself is source in the
save-file repo; `reload_machine()` validates and hot-swaps), freeze-time
thinking (a wake freezes the game, then pushes a wake pack over an MCP
channel — the world stops while the mind decides), and mechanical
telemetry.

The contract is `SURFACE.md` (tools/resources) and `MACHINE.md` (the
machine's on-disk format).

## Status

**Surface hardening in progress.** The tool/resource surface is the
contract and gets designed — and blessed — before any tool code is
written. `SURFACE.md` and `MACHINE.md` are drafts under active hardening.
The design record and the validated internals this server will wrap live
in the OoT Bench workshop repo (`oot-dojo`) — everything mechanical here
(executor, freeze discipline, rules-engine validation, collision
scanning) has already been proven against the real game there.

License: TBD — open-sourcing the layers is the plan once the foundation is
in place.
