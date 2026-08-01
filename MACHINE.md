# MACHINE.md — the machine's on-disk format

**STATUS: BLESSED (AJ, 2026-08-01)** — designed in the 2026-08-01
hardening session (AJ participating and ratifying: layout, preemption,
state guards, explicit leaf completion, version pinning all decided in
conversation). Part of the contract with SURFACE.md; a change here is a
major version bump and needs AJ's blessing.

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
