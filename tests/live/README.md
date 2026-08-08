# tests/live — e2e against the REAL game

The missing rung of the pyramid (dojo docs/33). Everything else in
`tests/` runs against a simulated game; acceptance flights run against
the real one at the cost of a whole session with AJ on the camera.
These tests run against the real game in **minutes**, because the dev
harness can put Link anywhere: `dev_warp` to the scene, `dev_teleport`
to the exact pose, assert, repeat.

They require `--dev-tools` **by construction** — the harness spawns the
server with it, and without the flag the `dev_*` verbs are absent, so
there is no way to reach a chosen world state and nothing here can run.
That is also why nothing here is scored play: the server runs under the
flag against a throwaway repo, and that repo's journal says so in
permanent ink (`dev_mode` banner, one `dev_cheat` line per call).

## Running them

```
OCARINA_LIVE=1 python3 -m unittest discover -s tests/live -t .
```

with Shipwright running (Sail enabled, a save file loaded). Knobs:

| env | default | what |
|---|---|---|
| `OCARINA_LIVE` | unset | the opt-in; nothing runs without it |
| `OCARINA_O2R` | `/Users/aj/Code/Shipwright/oot.o2r` | the place sense's collision source — the position assertions ride `place.*`, and skip without it |
| `OCARINA_LIVE_PORT` | 43384 | the Sail port (only for exercising the gates, or a second bench) |
| `OCARINA_LIVE_CONNECT_S` | 20 | how long to wait for SoH to dial in before skipping |

The default suite (`python3 -m unittest discover -s tests -t .`) picks
these up and skips them instantly; they never fail there.

## The skip gates (never failures)

1. **`OCARINA_LIVE` unset** — the opt-in. Instant skip; this is what
   keeps the default run fast and green.
2. **Sail port 43384 already bound** — another ocarina server owns the
   game (a flight in progress!). Skip, loudly, and touch nothing.
3. **No game dials in within ~20 s** — SoH is not running. Skip.

A *failure* here means the game WAS there and a harness verb did the
wrong thing. That distinction is the whole design: none of the three
gates says anything about the code under test.

## What lives here

- `harness.py` — the plumbing: builds a throwaway save-file repo (an
  idle machine that touches nothing, no `identity.json`, so the boot
  check is off and it can never be mistaken for a scored line), spawns
  `python -m ocarina --dev-tools`, speaks MCP over its pipes, and
  offers `state()` / `journal()` for assertions.
- `test_dev_live.py` — the first family: warp arrives (asserted off
  `oot://state`, never off the op's claim), teleport lands Link near
  where it was asked to, and the journal carries the banner and every
  cheat. Plus the two pins the first live pass earned (0.12.1): a warp
  back into the CURRENT scene is an arrival (the `loads` counter,
  because the scene id never moves), and a teleport with a `room`
  argument leaves the world in that room. Both add a fourth gate —
  `counters()` skips loudly when the connected instrument predates the
  room/loads AgentLink patch, since neither field is on the wire to
  read.

  The teleport pins' truth model changed with 0.12.2, when the op was
  rebuilt on the game's own Farore's Wind respawn machinery (a raw
  position write left the camera wedged in the geometry): its reply is
  the RESPAWN RECORD's word at staging time — requested position plus
  the resolved room and yaw — arrival is a real scene reload watched
  through `loads`, and what the world holds afterwards is asserted as
  NEAR the request (floor snap and spawn-safety nudges are the game
  doing its job, not the verb missing). `counters()` costs a reload
  per call now; keep it at the edges of a test.
- `test_walk_live.py` — the routed-walk family (0.13.0, docs/30:
  "development happens against the dev harness"). `walk_to` and
  `reachable` are BEHAVIOR-layer verbs, so the repo carries a probe
  behavior: the test writes `walk_target.json`, `force_state`s the
  probe node, and reads `walk_result.json` — position-before/after and
  elapsed time measured INSIDE the body, which is how criterion 1's
  "zero movement, under 0.5 s" is witnessed rather than asserted. The
  pins: the cliff (a cross-region target) refused cold; `reachable`
  agreeing with the walk in both directions; a routed walk arriving
  map-verified. Warps land at ENTRANCES (the third router lesson:
  entrance spawns are in-bounds by construction). UNRUN as written —
  built 2026-08-07 with SoH down; run it before the maze flight.

## The pattern to keep: warp-there-and-pin

Every bug a flight finds becomes a live test at the place it happened,
the way `lab/navgraph/test_ring.py` pinned the o'clock problem. Nothing
found live should ever need to be re-found live. The sixth flight's
three traverse bugs and the docs/30 routed-walk acceptance checks are
the standing backlog for this directory.
