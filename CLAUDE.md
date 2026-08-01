# ocarina — session orientation

You are in the ocarina repo: the MCP server piece of OoT Bench.
**`SURFACE.md` and `MACHINE.md` are BLESSED (AJ, 2026-08-01)** — the
contract is in force, and as of the same day **the server exists and has
flown**: ocarina 0.1.0 implements the contract, is green on its offline
suite, and ran first light against the real game (booted a save via a
behavior, wandered the Deku Tree on the geometry sense, woke over the
channel path, hot-swapped its machine live). Full session record:
`../oot-dojo/docs/20-first-light-2026-08-01.md`.

**Read first:** `SURFACE.md` and `MACHINE.md`, then
`../oot-dojo/docs/19-senses-and-the-machine-2026-07-31.md` (the substance)
and `../oot-dojo/docs/20-first-light-2026-08-01.md` (what is actually
built and what it did). The workshop's `../oot-dojo/CLAUDE.md` maps the
validated internals these modules were ported from; its
`docs/08-false-signals.md` discipline applies here fully — first light
already caught one of its classics (§17's dist_y sign, live).

## Operating this repo

- Tests: `python3 -m unittest discover -s tests -t .` (82; includes a
  subprocess-over-real-pipes smoke test with the ported fakegame).
- Run: `python3 -m ocarina --repo <save-file-repo>` — the repo declares
  the machine under `machine/`; SoH connects in over Sail (43384).
  `examples/first-light/` is a working save-file repo.
- Module map: `machine.py` (parse + the five validation steps),
  `guards.py` (AST whitelist + `state.*` chains), `senses.py` (the v0
  digest/schema/event grammar — THE growing curation artifact),
  `runtime.py` (20 Hz loop, dispatch, edges, freeze-confirmed wakes),
  `executor.py` (+ the blessed preemption extension), `server.py` (stdio
  MCP + channel push). `protocol/link/game/miniyaml/behavior*` are ports.

## Pending AJ review (candidate MACHINE.md clarifications, next major)

Where the blessed contract was silent, code chose and documented — each
in the module docstring: miniyaml scalar continuation (MACHINE.md's own
multiline `when` example needs it); absent state entities compare False
in EVERY comparison including `!=`; `do` lists allow one terminal verb
(goto/wake/hold), last; self-goto keeps `when` edge state (hysteresis
beats scope-entry reset); machine-event vocabulary grew by
journal/directive/escalation/diagnostic; wake deadline defaults 300s
(`--wake-deadline`).

## Rules for this repo

1. **The surface is the contract.** SURFACE.md + MACHINE.md are blessed;
   code implements them exactly. A change to either file is a major
   version bump (SURFACE.md, Versioning) and needs AJ's blessing —
   never edit them as a side effect of an implementation convenience.
2. **The north star is the narration layer.** Ocarina is an
   audio-description track for a player with an unusual sensory profile.
   Curation rules live in SURFACE.md ("presented, not computed"; the UI
   principle; official names; vocabulary-not-grammar). Every new sense
   field must pass them — `senses.py` documents its v0 honesty gaps
   in-file; keep doing that.
3. **Internals are ported, not rewritten.** Ported modules carry their
   provenance headers; keep diffs against the workshop originals
   reviewable. The behavior interface must never break dojo-graded
   bodies — that equivalence is the point.
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
   working live as of first light). A long-poll `await_wake` fallback
   exists in the spec for non-Claude clients but is not built. Platform
   facts: channels work over local stdio; delivery queues until idle;
   resources cannot be subscribed to.
8. **Not-yet-built surface stays honest.** Tools/resources awaiting
   instrument work (dialogue text, menu navigation, screenshot) are
   registered and return explicit not-yet errors naming what they wait
   on (`NOT_YET` in server.py). Never quietly stub one.
