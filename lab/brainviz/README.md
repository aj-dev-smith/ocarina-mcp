# lab/brainviz — the brain viewer

A live, one-way debug view of the running machine: the force-directed
brain AJ watches next to the game window. The runtime side is
`ocarina/brainviz.py` (the spigot); this directory is the app (the
whole app — one self-contained HTML file, no dependencies, no build
step, the ydan_viewer.html house style).

Brainviz is to the MACHINE what `overlay.py` is to the SENSORIUM: a
human debug organ that renders beliefs and by construction feeds
nothing back. Every endpoint is a GET; SSE cannot carry anything
upstream; nothing here is readable by the sensorium, the machine, or
the mind's tool surface. Lab-grade, like the navgraph: no SURFACE.md or
MACHINE.md change rides with it.

## Running it

```
python3 -m ocarina --repo <save-file-repo> --o2r ... --brainviz 43385
```

then open `http://127.0.0.1:43385/` in a browser beside the game. Off
by default; the port is a suggestion (43385 sits next to Sail's 43384).
A taken port fails the boot loudly.

The server reads `viewer.html` from this directory **per request** —
edit the file, refresh the browser, no restart, no rebuild. The browser
also survives *server* restarts (the sixth flight had two mid-flight):
EventSource auto-reconnects, the page veils itself "brain offline" for
the gap, and re-reads `/topology` on reconnect.

## What you're looking at

- **Nodes** are machine nodes. Size tracks the behavior body's line
  count (the brain visibly grows as behaviors buy senses); the chip
  under the name is the pinned behavior version. Dashed outline =
  an instrument: a leaf no transition ever targets, reachable only by
  `force_state` (census_probe, locate_probe, the probe family).
  Interior nodes render as soft hulls around their children. The inner
  fill deepens with dwell time.
- **Edges** are `goto`s. Solid = event-triggered (`on`), dashed =
  state-triggered (`when`), faint dotted = a wake transition's
  `default` route. A dashed edge burning amber is an armed `when`
  guard: its expression is TRUE right now and it is holding hysteresis
  (`runtime.guard_edges()`, refreshed with each ~1 Hz status beat).
  Edges pulse when taken, colored by outcome.
- **The brainstem ring** is the root transition set — the reflexes in
  scope everywhere (health-critical, took-damage, novel-actor…), drawn
  as arc segments instead of an edge from every node. Gold-tinted
  segments wake.
- **The Mind orb** floats above the graph. When a `wake` fires, the
  world desaturates (frozen), a beam runs from the waking node up to
  the orb, and the orb counts the freeze (`thinking · 12s`). This is
  the two-layer thesis in one animation: 20 Hz reflexes below, judgment
  above, and the wire between them is the show.
- **The ticker** is `tail -f mechanical.jsonl` with eyes: journal
  lines, outcomes colored (success green / failure amber / damage red /
  wake gold / world cyan), and the stand_watch idle loop collapsed into
  `×N` repeat counters instead of scrolling everything away.
- Click a node or edge for the inspector: transitions with their full
  guards, actions, defaults, cooldowns; behavior description and grade.

## Replay mode

The stream opens with a backlog of the last 150 journal events, so the
viewer works on a flight's fossil with no game attached: point a
runtime at a **scratch copy** of an example repo (never run an
`examples/` repo in place — the live journal and seen-kinds mutate the
committed fossil), start `Brainviz`, and feed the committed
`journal/mechanical.jsonl` through `EventLog.record()` at replay speed.

## Data contract (what viewer.html consumes)

- `GET /topology` — nodes (parent, transitions, behavior name/version/
  loc/description/grade), root_transitions, initial, source hash. The
  viewer re-fetches when the status beat's hash changes, and morphs in
  place — layout is seeded by node-name hash, so surviving nodes hold
  their positions and a reload reads as surgery, not a re-shuffle.
- `GET /stream` — SSE: `backlog` (event array, once), `ev` (each
  journal event as recorded), `status` (~1 Hz: `runtime.status()` plus
  `guard_edges`).

## Not yet

- **Guard proximity** (an edge brightening as `dist` closes on its
  threshold): needs per-comparison distance-to-flip export from the
  guard evaluator, not just the boolean edge state. The display slot is
  reserved (the armed state already renders).
- **The git scrubber**: machine.yaml's history replayed as graph
  morphs — brain surgery across five flights. Seeded layout already
  makes the morphs readable; needs a small distiller over `git log`.
- Per-transition wake deadline display (the server knows
  `--wake-deadline`; the status beat doesn't carry it yet — the orb
  counts up, not down).
