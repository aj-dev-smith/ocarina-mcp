# ocarina — session orientation

You are in the ocarina repo: the MCP server piece of OoT Bench. It is
freshly seeded; **the surface has NOT been designed yet.**

**Read first:** `../oot-dojo/docs/18-three-piece-architecture.md` (the
architecture and the decisions behind it), then
`../oot-dojo/docs/17-expedition-directives.md`, and `../oot-dojo/CLAUDE.md`
for the workshop's map — including `docs/08-false-signals.md`, whose
discipline applies in this repo too.

Rules for this repo, in force from the seed commit:

1. **Surface before code.** The first artifact is `SURFACE.md` — the full
   tool/resource contract, designed deliberately, because the surface IS
   the fairness ruleset. No MCP tool code lands before it exists and AJ
   has blessed it.
2. **Internals are ported, not rewritten.** The 20 Hz executor, freeze
   machinery, rules engine, scan op, merge gate — all validated in the
   workshop (`../oot-dojo/ootdojo/`, `../oot-dojo/ootbench/`) with tests.
   Ocarina is a thin stdio skin over them.
3. **Stdlib-only** (workshop convention carries over): the server must run
   anywhere Python does.
4. **Fairness lives in the surface, never in prose.** If a rule can be
   enforced by not mounting a verb, that is the enforcement — mode-gate
   the practice tools (savestates, dojo trials, probes); expedition mode
   mounts none of them.
5. **Registrations write through.** Triggers, modes, and skills the agent
   registers are declared in the playthrough repo and rehydrated on
   connect; the server's live state is never the only copy (docs/18,
   "write-through").
6. Platform constraint (verified 2026-07-31): Claude Code cannot subscribe
   to MCP resources — resources are the VIEW, `await_wake` is the only
   push channel.
