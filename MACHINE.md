# MACHINE.md — the machine's on-disk format

**STATUS: BLESSED (AJ, 2026-08-01)** — designed in the 2026-08-01
hardening session (AJ participating and ratifying: layout, preemption,
state guards, explicit leaf completion, version pinning all decided in
conversation). Part of the contract with SURFACE.md; a change here is a
major version bump and needs AJ's blessing.

**Amended 2026-08-03 (ocarina 0.7.0, dojo docs/25 — the place sense):**
the digest schema grows `place.*` and `nearest_enemy.bearing` (guards
read them like any field; the load-time path check covers them); the
event grammar grows the dispatchable `place` category; and the behavior
interface gains the `traverse` leg primitive (see Leaves and behaviors).

**Amended 2026-08-07 (ocarina 0.11.0, dojo docs/32 — boot identity;
all four open calls ratified by AJ the same evening):** the save-file
repo may declare its line in `identity.json` at the repo root; the
RUNTIME judges every load and every attach against it, and a mismatch
raises the one runtime-initiated wake (`identity`, hold default). See
"The declared identity" below.

**Amended 2026-08-07 (ocarina 0.13.0, dojo docs/30 — route-aware
walking; ratified by AJ with all open calls as recommended, late the
same night: "ok both fully ratified with your recommended approaches"):**
the behavior interface gains `walk_to(x, z)` and `reachable(x, z)` (see
"The routed walk" below); the refusal exception family is renamed
`RouteRefused`/`RouteFailed` with the Traverse names ALIASED (same
classes — no graded body's `except` breaks); the digest's
`nearest_enemy` grows the judged `reach` field and the `moving` bit;
`game.actors()` grows a `sighted=` filter. `walk_to_point` is
unchanged and demoted in documentation to the deliberate unrouted
override.

**Clarification pass, 2026-08-01 (post-first-light):** six points where
this file was silent and the built server had to choose were reviewed
and ratified — AJ delegating the ruling to the mind as this surface's
primary user. Each is now specified in place below (scalar continuation,
absence semantics, terminal verbs, self-goto edge state, the machine-
event vocabulary, the wake deadline); ocarina bumped 0.1.0 → 0.2.0 per
SURFACE.md Versioning. No machine.yaml that loaded *and worked* before
this pass is invalidated; `on:` names that could never fire now fail
loudly at load instead of silently (format version stays 1).

The machine is **source in the save-file repo**; ocarina is its runtime.
This file specifies that source: the files, the grammar, the guard
language, the behavior interface, and what `reload_machine()` validates.
Provenance: everything here is a port of validated workshop internals
(`rules.py`'s transition grammar and AST whitelist, `executor.py`'s body
contract, `skill.py`/`skillsource.py`'s loading, `miniyaml.py`'s strict
subset) — arranged into a hierarchy, not rewritten. One workshop module is
deliberately *dissolved* rather than ported: `sensors.py`'s synthesized
events (`enemy_nearby` from idle polls) are subsumed by state-triggered
transitions (`when`, below) — the docs/19 unification finishing its job.

## Layout

```
identity.json           # OPTIONAL: the declared save-line identity (0.11.0)
machine/                # in the save-file repo, NOT .claude/skills/
  machine.yaml          # the topology: nodes, transitions, initial
  behaviors/
    navigate.py         # behavior bodies, one capability family per file
    combat.py
```

One `machine.yaml`, not per-node files: the mind edits one document, git
diffs show brain surgery in one hunk, `reload_machine()` has a single
entry point. If it outgrows one file, an include mechanism is a cheap
later addition — the server is the only consumer.

## The declared identity (identity.json — 0.11.0, dojo docs/32)

The tenth flight opened with an hour on the WRONG save file: the blind
boot accepted whatever line the file-select cursor sat on, and no sense
surfaced file identity. `identity.json`, hand-authored at the repo
root, is what the repo says it is playing — bumped in the same commit
as the flight that earned each claim.

```json
{
  "save_slot": 1,                  // 0-based fileNum; the load event's own field
  "save_name": "C",                // how the pack names the line
  "fingerprint": {                 // MONOTONE facts only: what this line cannot lose
    "health_capacity_at_least": 48,
    "b_item": "kokiri_sword",
    "c_buttons": {"c_left": "fairy_slingshot"},
    "inventory_items": ["fairy_slingshot"],
    "equipment_owned": {"sword": ["kokiri_sword"], "shield": ["deku_shield"]}
  },
  "journal_only": ["rupees", "nuts"],   // volatiles: READ every boot, asserted never
  "_provenance": {"...": "date every claim to the flight that earned it"}
}
```

Rules (all ratified with docs/32):

- **Validated at `--repo` load**, alongside the machine: malformed
  JSON, a missing `fingerprint` block, or a fingerprint key outside
  the checkable vocabulary is named in a load diagnostic — and the
  repo is then treated as opted-in-and-broken, which **fails closed**
  (every attach refuses with CANNOT VERIFY until the file is fixed).
  A declaration nobody checks is worse than none. `reload_machine()`
  re-reads it (hand-editable, like the machine).
- **The RUNTIME judges, not the machine**: on every `load_game` (the
  slot rides the event's `file` field) and on every attach to an
  already-loaded world — the rehydrate path no machine node covers,
  where the slot is honestly unverifiable and the verdict says so. A
  guard-language check would fail OPEN on a missing field (ABSENT
  semantics); code can refuse on missing evidence, so it does:
  missing wire blocks are CANNOT VERIFY, never a pass.
- **Mismatch = the one runtime-initiated wake**: transition name
  `identity`, freeze-confirmed like every wake, default
  `hold refusing to play a line this repo does not declare`, detail
  diffing expected against observed by name. Every other wake remains
  machine-initiated; this one exists because attach-time verification
  cannot be expressed machine-side.
- **No declaration = the check is OFF, loudly**: one diagnostic at
  load ("boot verification is OFF"), the `--o2r` pattern. The boot
  line — B/C assignments, owned gear, inventory with ammo, hearts,
  counters — is journaled on EVERY load regardless: the tenth
  flight's tell sat unread for an hour because nothing put it in
  front of anyone.
- **The server never repairs**: no stick on the file select (a blind
  cursor can reach Copy/Erase). It observes and refuses; choosing the
  file stays a human act.
- **The fingerprint is monotone or it is a bug**: consumables and worn
  gear are volatile and belong in `journal_only` at most. `equips.worn`
  is excluded on principle (docs/32 §4).

## machine.yaml grammar

Strict miniyaml (stdlib YAML subset); unknown keys are load errors at
every level, per the rules.py discipline. One addition to the ported
subset (ratified 2026-08-01): **scalar continuation** — a line indented
deeper than its key that is neither `key: value` nor a list item folds
into the previous string scalar with a single space; the multiline
`when:` in the example below relies on it. Everything else the subset
rejects (tabs, flow syntax, anchors, block scalars, duplicate keys)
stays rejected with a line number.

```yaml
version: 1
initial: explore                      # entry node; descends via initial chains

nodes:
  explore:
    initial: navigate_field           # interior node: children + initial
    transitions:                      # scoped: checked while any descendant is current
      - name: novel-actor
        on: spawn
        where: novel == 1          # first sighting of this actor kind, this save file
        do: wake novel actor sighted
        default: hold keep exploring
        cooldown_s: 30
    children:
      navigate_field:
        behavior: navigate_field_v3   # leaf node: exactly one behavior, version-pinned
        transitions:
          - name: nightfall-reflex
            on: environment
            where: cue == 'nightfall'
            do: goto navigate_field_night
          - name: baba-in-reach
            when: state.nearest_enemy.kind == 'deku_baba'
                  and state.nearest_enemy.dist <= 800
                  and state.sticks < 8
            do: goto kill_baba_collect_sticks
          - name: keep-going
            on: behavior_done
            do: goto navigate_field   # explicit loop — see leaf completion
      navigate_field_night:
        behavior: navigate_field_night_v1
        # ...
      kill_baba_collect_sticks:
        behavior: kill_baba_collect_v1
        # ...

transitions:                          # root scope: the skeleton wake set lives here
  - name: health-drop
    on: damage_taken
    where: hearts_after <= 3
    do: wake health critical
    default: hold no reflex yet
```

- **Interior nodes** have `children` + `initial` (+ optional
  `transitions`). **Leaf nodes** have `behavior` (+ optional
  `transitions`). A node with both `children` and `behavior` is a load
  error.
- **Node names are unique machine-wide.** Nesting expresses scope;
  `goto` and `force_state` take the bare name.
- `do` is one action or a list. At most one of a list's actions may be a
  **terminal verb** (`goto`, `wake`, `hold` — they move the machine,
  freeze it, or explicitly do nothing) and it must come last; `journal`
  entries execute first. Two gotos in one transition would be ambiguous
  brain surgery. `default` is a single non-wake action.

### Triggers: two kinds, one transition shape

A transition has **`on` + optional `where`** (event-triggered) **or**
**`when`** (state-triggered) — never both. `name`, `do`, `default`,
`cooldown_s` and their validation are shared.

- **`on <event>`** fires off the game's event stream (GameInteractor
  hooks: howls, damage, spawns, dialogue…) plus machine events. `where`
  is evaluated over the event's fields and `state.*`.
- **`when <expr>`** is evaluated every tick at 20 Hz, server-side,
  against the curated state. It fires on the **false→true edge** and
  will not refire until the expression has been false again (natural
  hysteresis; `cooldown_s` stacks on top). On entering the transition's
  scope, the prior value is taken as false — a condition already true on
  entry fires immediately (walk into the room with two babas already in
  range: the reflex trips on arrival). **Scope entry means the active
  chain changed**: a self-goto (the explicit `behavior_done` loop)
  restarts the behavior but does not reset edge state — a condition
  still true across the loop boundary does not refire every iteration.
  Hysteresis beats scope-entry reset (ratified 2026-08-01).

Some things exist only as events (a howl leaves no trace in state) and
some only as state (distance to the nearest enemy); the grammar honestly
has both. Rationale for events not being reducible to state and vice
versa: docs/19 §5.

### Action verbs

`goto <node>` · `wake <reason>` · `journal <template>` · `hold <reason>`

- `goto` enters a node (interior: descends via `initial` chains to a
  leaf). This replaces the workshop's `run_skill` — the mind and the
  machine both act by putting the machine in a state, never by running a
  body imperatively.
- `wake <reason>` is the `wake_mind` action: freeze-confirmed first,
  then channel push with the wake pack. **Every transition that wakes
  must declare a non-wake `default`** — what to do when no usable answer
  arrives (ported rule; a frozen game waiting on a mind that never
  answers is the failure this kills). "No usable answer" is bounded by
  the server's wake deadline (`--wake-deadline`, default 300 s): when it
  expires, the `default` runs and the game resumes. An operational knob
  on the server, deliberately not machine.yaml grammar — the machine
  says *what* to do, how-long-to-wait is deployment (ratified
  2026-08-01; per-transition deadlines can be added later without
  breaking anything).
- `journal` templates `{field}` from the event (event-triggered only).
- There is **no pad verb**. Ever.

### Dispatch semantics

Events (and each tick's `when` sweep) dispatch **innermost-out**: the
current leaf's transitions first, then each ancestor's, root last. First
match wins; within a node, file order. **Cooldowns are consumed at match
time** even if the action is then skipped — the wake-storm rule, ported.

The event grammar is closed (senses.py owns it; ratified 2026-08-01):
the world categories plus the machine events `entered · exited ·
behavior_done · behavior_aborted · wake · journal · directive ·
escalation · diagnostic`. All of them land in the one timeline, but only
`behavior_done` and `behavior_aborted` are **dispatchable** — the rest
are record-only (a transition on `entered` firing a goto that emits
`entered` is an infinite loop inside one tick). An `on:` naming a
record-only or unknown event is a load error: a transition that can
never fire must not load silently (the state-path discipline, applied to
event names).

### The guard language

Guards (`where` and `when`) are Python expressions compiled through the
ported AST whitelist: comparisons, boolean ops, arithmetic, literals,
tuples/lists, names — no calls, no subscripts. One extension: **attribute
chains rooted at `state`** (`state.nearest_enemy.dist`). Attribute access
anywhere else remains rejected.

- Bare names resolve to the triggering event's fields (`where` only);
  `state.*` paths resolve into the curated state digest.
- **Absent entities never match** (ratified 2026-08-01): a `state.*`
  path whose entity is legitimately absent at runtime —
  `state.nearest_enemy.dist` with no enemy in view — resolves to a falsy
  ABSENT value that compares False in EVERY comparison, **including
  `!=`**. A guard over an absent entity never fires, rather than
  erroring or accidentally matching (a reflex that trips because nothing
  is nearby is the failure this kills). The idiom for "there is an enemy
  and it isn't a baba":
  `state.nearest_enemy and state.nearest_enemy.kind != 'deku_baba'`.
- **The guard vocabulary IS the sense vocabulary**: guards read the same
  curated fields the mind reads in `oot://state`, not the raw values
  behaviors see. "Presented, not computed" is thereby enforced at the
  machine layer — there is no internal frame counter to guard on because
  the sensorium doesn't contain one. Actor names are official from first
  sighting (SURFACE's naming principle, 2026-08-01), so
  `state.nearest_enemy.kind == 'deku_baba'` is writable immediately.
- **Every `state.*` path is checked against the state schema at load
  time** — a typo'd path is a `reload_machine` diagnostic, not a
  transition that silently never fires. (Event fields can't be
  load-checked the same way; a `where` naming a field its event doesn't
  carry doesn't fire and is journaled once per (transition, field),
  ported behavior.)

## Leaves and behaviors

Entering a leaf starts its behavior on the executor. The behavior is the
20 Hz autopilot: a deterministic, blocking body issuing game ops.

**Completion is explicit.** When a body returns, the machine emits
`behavior_done` into the event stream, carrying the executor's judged
`outcome` (`success | failure | damage | death | timeout | abort |
error`), the behavior's full name, and duration. **The validator
requires every leaf's scope chain to contain an unguarded
`on: behavior_done` transition** (guarded ones may precede it — e.g.
`where: outcome == 'success' and state.sticks < 8` to loop until the
sticks are collected). A machine with nothing to do after a body returns
is a load error, never a silent stall. Extends the mandatory-default
discipline.

**Preemption happens at game-op boundaries.** Bodies are blocking and
are never killed. When a transition leaves a running leaf (or
`force_state` jumps, or `reload_machine` swaps), the executor sets a
flag and the body's next `game.*` call raises `BehaviorPreempted`;
the machine journals `behavior_aborted` with the preempting transition
as the reason. Deterministic 20 Hz bodies touch the game every tick, so
preemption latency is ≤ 1 tick and bodies need no changes. This is the
one deliberate extension to the validated executor (its docstring's
"future skill-API concern" — it bit).

### The behavior interface

`Behavior` is the workshop's `Skill` dataclass, renamed (docs/19: "skills"
means Claude Code SKILL.md artifacts only, always):

- `name`, `version` (int), `description`
- `body(game, ctx)` — blocking; `ctx` is the state snapshot at entry;
  raise `BehaviorAbort(reason)` to bail
- `success(game, initial, events) -> bool` — judged after return; prefer
  positive evidence (ported predicate discipline)
- `timeout_s` — hard wall-clock cap
- `notes` (postmortem trail), `grade` (one line for a reader choosing
  between behaviors)

Behavior modules live in `machine/behaviors/`, are loaded **by path**
(never imported as save-file packages), and expose a module-level
`BEHAVIORS` mapping — `skillsource.py`'s contract, renamed. A behavior
graded in the workshop runs here unmodified; that equivalence is the
point of the dojo and this format must never break it.

**machine.yaml pins exact versions** (`behavior: navigate_field_v3`).
Upgrading a behavior is a visible one-line diff — git history as the
literal evolution of Link's brain.

### The traverse primitive (added 0.7.0, docs/25)

`game.traverse(target)` moves Link across exactly ONE named place-graph
edge (a climb column) or into ONE named ADJACENT region — never a
route. Cross-region routing is cognition and belongs to the mind over
`oot://place` (ruled 2026-08-03: the harness must not pathfind for the
mind); within-region steering to the edge is motor, poly-level, and
cannot leave the region — so it cannot cross a void by construction.
Anything the map does not vouch for — an off-mesh start, an unknown
name, a non-adjacent region, an unverified drop/jump candidate, an
unlinked column — raises `TraverseRefused` BEFORE any movement (clean,
catchable, journal-honest; never a best-effort approximation). A legal
leg that doesn't complete raises `TraverseFailed`. Success is claimed
only after the map confirms arrival in the linked region. Descending
climbs and crawlspaces are honest not-yets, refused by name.

One preemption refinement rides along: long composite primitives
(traverse's walk/grab/ascend loops) poll the preemption flag every
iteration, so a transition leaving the leaf lands mid-climb rather
than after the whole leg — the same latency promise `game.wait()`'s
chunking already made for sleeps. Op-boundary preemption is unchanged
for everything else.

### The routed walk (added 0.13.0, docs/30)

`game.walk_to(x, z)` walks Link to a point INSIDE the current region by
route — traverse's grain brought down a level. The region is the
answer: a target in another walkable component is not walk-reachable by
construction, so the verb refuses it in milliseconds with the target's
region and the legs out of Link's named, instead of the 12 seconds of
wall-grinding the ninth flight paid per unreachable bush. All refusals
precede ALL movement (`RouteRefused`, one family with traverse's):
no map / off-mesh start / Link standing ABOVE the mapped floor (an
actor surface — the height is named, docs/28 learning 4) / target off
the map / target in another region / no in-region path / blocked by a
census prop with no way around ("blocked by a treasure_chest at your
2 o'clock" — prop radii are labelled guesses until the collider wire
rider lands). A legal route that doesn't complete raises `RouteFailed`.
Arrival is what the MAP says, never the motion. The walk itself carries
traverse's discipline: wedge sidestep (mesh-checked), 20 s stall,
message-box fail-fast, preemption polled mid-walk.

Routes are CLEARANCE-AWARE — a combat-safety requirement, not a
quality knob (AJ's flight testimony: wall-scrape slowdown turned
"boulder nearby" into "boulder hit"). The A* penalizes wall-adjacent
polys and waypoints hold an adaptive offset from region boundaries:
`min(desired, (width − link_diameter) / 2)` — the desired offset in
open space, the midline in pinches, and a corridor Link physically
fits is never refused. A corridor near Link's own width is reported as
a squeeze in the result (presentable narrowness).

`game.reachable(x, z)` is the same check with the walk removed: the
refusal text, or None — zero movement, so an electing body filters
BEFORE committing (the primitive both field-authored blacklists were
groping toward; skips carry named reasons instead of anonymous
timeouts).

Cross-region routing stays the MIND's (docs/25, unmoved): `walk_to`
refuses at the region boundary and names the legs; the mind sequences
them with `traverse`. `walk_to_point` stays exactly as it was —
unrouted, never refuses — as the last-20-units tool, combat footwork,
and the deliberate override when a refusal is believed false (a false
refusal is an INSTRUMENT DIAGNOSTIC: journal it).

## What reload_machine() validates

In order, all diagnostics collected and returned (errors fail the swap;
warnings don't):

1. Strict parse: miniyaml, unknown keys rejected at every level.
2. Structure: unique node names; `initial` chains resolve to leaves;
   every `goto` and `default` target exists; leaf/interior shape rules.
3. Guards and triggers: AST whitelist (+ `state.*` attribute chains
   only); every `state.*` path exists in the state schema; every `on`
   names a dispatchable event; cooldowns non-negative; every waking
   transition has a non-wake `default`.
4. Leaves: every referenced behavior exists in the loaded corpus (a
   missing behavior is a load error, not a runtime surprise); behavior
   modules import cleanly; every leaf's scope chain has its unguarded
   `behavior_done` transition.
5. Reachability from `initial` via transitions: unreachable nodes are
   **warnings** (dead code, not necessarily wrong — and `force_state`
   can still reach them).

**Hot-swap semantics:** on success, the running behavior (if any) is
preempted (`behavior_aborted: machine reloaded`); the current node
carries over **by name** if it still exists in the new machine,
otherwise the machine drops to `initial` — either way, journaled. On
failure, the old machine keeps running untouched and the diagnostics
come back to the caller.

On connect, the server rehydrates by running this same load from the
repo — live state is never the only copy, and `oot://machine` exposes
declared vs live as two columns (the conjunction discipline).

## Open questions (this artifact)

- The state digest schema itself (`oot://state`) — guards borrow its
  vocabulary, so SURFACE's open question 5 is also this file's. The
  load-time path check is only as good as the schema is explicit.
- Whether `behavior_done` needs sub-outcome vocabulary beyond the
  executor's seven (leaning no — vocabulary-not-grammar says outcomes
  are the closed set and details ride in `detail`).
- Include mechanism for `machine.yaml` when it outgrows one file
  (deferred until it does).
