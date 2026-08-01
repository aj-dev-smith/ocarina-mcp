# ocarina — session orientation

You are in the ocarina repo: the MCP server piece of OoT Bench.
**`SURFACE.md` and `MACHINE.md` are BLESSED (AJ, 2026-08-01)** — the
hardening pass is done and the contract is in force. The next work here
is **building the server**: porting the validated workshop internals
behind the blessed surface (stdio MCP, stdlib-only).

**Read first:** `SURFACE.md` and `MACHINE.md`, then
`../oot-dojo/docs/19-senses-and-the-machine-2026-07-31.md` (the substance)
and `../oot-dojo/docs/18-three-piece-architecture.md` (the shape; mind its
correction header). The workshop's `../oot-dojo/CLAUDE.md` maps the
validated internals; `docs/08-false-signals.md` discipline applies here
fully.

Rules for this repo:

1. **The surface is the contract.** SURFACE.md + MACHINE.md are blessed;
   code implements them exactly. A change to either file is a major
   version bump (SURFACE.md, Versioning) and needs AJ's blessing —
   never edit them as a side effect of an implementation convenience.
2. **The north star is the narration layer.** Ocarina is an
   audio-description track for a player with an unusual sensory profile.
   Curation rules live in SURFACE.md ("presented, not computed"; the UI
   principle; identification gating; vocabulary-not-grammar). Every new
   sense field must pass them.
3. **Internals are ported, not rewritten.** The 20 Hz executor, freeze
   machinery, rules-engine validation, scan — all validated with tests in
   `../oot-dojo/ootdojo/` and `../oot-dojo/ootbench/`. Ocarina is a thin
   stdio skin over them.
4. **Stdlib-only.**
5. **No practice tools on this surface, ever.** Savestates, drills, and
   gate tools are workshop dev-tooling for instrument validation — they
   are not mode-gated here, they are absent (AJ, 2026-07-31: shortcuts
   would be cheating for a real benchmark). Game-native saves only.
6. **The machine is source in the save-file repo.** Ocarina runs it;
   `reload_machine()` validates + hot-swaps; connect rehydrates from the
   repo. The server's live state is never the only copy. The 20 Hz leaves
   are called **behaviors** — never "skills", which means Claude Code
   SKILL.md artifacts only.
7. **Wake transport is MCP channels** (freeze-confirmed first, then push).
   A long-poll `await_wake` fallback exists in the spec for non-Claude
   clients but is not built now. Platform facts: channels work over local
   stdio; delivery queues until idle; resources cannot be subscribed to.
