# ocarina — session orientation

You are in the ocarina repo: the MCP server piece of OoT Bench.
**`SURFACE.md` and `MACHINE.md` are BLESSED (AJ, 2026-08-01)** — the
contract is in force, ratified-in-place clarifications included (see
MACHINE.md's status block), and the server has flown **twice**, both on
2026-08-01. First light (0.1.0) proved the server flies: boot via a
behavior, geometry-sense wandering, the channel wake path, a live
hot-swap. Second light (0.2.x–0.3.0) proved the **loop**: three wakes
answered by a watching client, three brain surgeries mid-run, a
dojo-graded killer ported import-lines-only (3 field kills, zero
damage), the first mind-authored behavior, and AJ's fairness ruling
live-editing the sensorium's obligations. Session records:
`../oot-dojo/docs/20-first-light-2026-08-01.md` and
`../oot-dojo/docs/21-second-light-2026-08-01.md`.

**Read first:** `SURFACE.md` and `MACHINE.md`, then
`../oot-dojo/docs/19-senses-and-the-machine-2026-07-31.md` (the substance)
and docs/20 + docs/21 (what is built and what it did). The workshop's
`../oot-dojo/CLAUDE.md` maps the validated internals these modules were
ported from; its `docs/08-false-signals.md` discipline applies here
fully — both flights caught its classics live (the dist_y sign; the
silently-never-fires transition shape, twice).

## Operating this repo

- Tests: `python3 -m unittest discover -s tests -t .` (92; includes a
  subprocess-over-real-pipes smoke test with the ported fakegame).
- Run: `python3 -m ocarina --repo <save-file-repo>` — the repo declares
  the machine under `machine/`; SoH connects in over Sail (43384; SoH's
  own config persists Sail enabled, so launching the game auto-connects).
  `examples/first-light/` and `examples/second-light/` are working
  save-file repos; second-light carries the seek→hunt clearing loop and
  the session-fossil commentary.
- `tools/drive.py` is the hand-drive rig: spawns the server, does the
  MCP handshake, relays JSON commands from a FIFO, logs all traffic
  (wake packs included) to `traffic.jsonl`. It is how a Claude session
  plays the mind's role until real idle-channel delivery is exercised.
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

## State of play after second light (versions 0.2.0 → 0.3.0, all committed)

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

**Top open items** (details in `../oot-dojo/harness-backlog.md`):
the `bgm_change` producer (enemy battle music on proximity — the
game's own fair unseen-enemy channel, and the compensation for losing
X-ray proximity info) is the next sense; the example machine's removed
`overhead-lurker` reflex is now rebuildable per its own in-file
condition; attacker
identity on `damage_taken` (needs a wire-side patch; nearest-enemy-at-
freeze is the documented workaround); Object_Kankyo filter; En_Item00
param-aware naming; the absence-semantics foot-gun lint (deferred);
dojo-trial `approach_baba_v1` (UNGRADED — its walking leg never ran);
dialogue text onto the wire.

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
5. **No practice tools on this surface, ever.** Not gated — absent, all
   the way down: `game.py` has no savestate methods and no `console()`.
   Game-native saves only.
6. **The machine is source in the save-file repo.** Ocarina runs it;
   `reload_machine()` validates + hot-swaps; connect rehydrates from the
   repo. The server's live state is never the only copy. The 20 Hz leaves
   are called **behaviors** — never "skills", which means Claude Code
   SKILL.md artifacts only.
7. **Wake transport is MCP channels** (freeze-confirmed first, then push;
   round-tripped live with a watching client as of second light — 3
   wakes, 0 freeze failures). A long-poll `await_wake` fallback exists
   in the spec for non-Claude clients but is not built. Platform facts:
   channels work over local stdio; delivery queues until idle; resources
   cannot be subscribed to. Real idle-session delivery remains
   unexercised (the rig listens; an idle Claude session hasn't).
8. **Not-yet-built surface stays honest.** Tools/resources awaiting
   instrument work (dialogue text, menu navigation, screenshot) are
   registered and return explicit not-yet errors naming what they wait
   on (`NOT_YET` in server.py). Never quietly stub one.
