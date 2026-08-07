# ocarina

The instrument you play Hyrule through.

Ocarina is an MCP server that exposes Ocarina of Time (via Ship of
Harkinian) to an AI agent as a fair, bounded tool surface. It is one third
of **OoT Bench**:

| piece | role |
|---|---|
| **ocarina** (this repo) | the instrument — the only way the agent touches the game |
| **soh-agentlink** | a small instrument patched into Ship of Harkinian that puts the game's senses on the wire |
| **save files** | playthrough repos — one per attempt, where behaviors and knowledge accumulate across plays |

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

**Contract blessed (2026-08-01); nine live flights flown.** `SURFACE.md`
and `MACHINE.md` are the blessed contract; ocarina 0.9 implements it —
the machine loader/validator, guard language, 20 Hz executor with
preemption, freeze-confirmed wake cycle, the sight-gated sensorium, the
place sense (a region graph distilled from the game's own collision
data), dialogue text, game-native saving, shopping, `screenshot()`, and
the stdio MCP surface, all tested
(`python3 -m unittest discover -s tests -t .`).
The latest flight started a fresh save file and played treehouse →
sword → shield → into the Deku Tree in ~2.5 hours. Tools that still
wait on instrument work (full menu navigation) return honest
not-yet-implemented errors.

Run it:

    python3 -m ocarina --repo <save-file-repo> --o2r <path to oot.o2r>

The save-file repo declares the machine under `machine/`; the game
connects in over Sail (build Ship of Harkinian with the
**soh-agentlink** patches — see that repo for setup). `--o2r` points at
your own legally-dumped game archive, the same file SoH itself
requires; without it the place sense is off, loudly. No game assets or
data derived from them ship in this repo — the lab pipeline
(`lab/navgraph/`) regenerates its artifacts from your o2r. `examples/`
contains real flight repos, journals included — `examples/ninth-flight/`
is the fresh-file run.

License: MIT.
