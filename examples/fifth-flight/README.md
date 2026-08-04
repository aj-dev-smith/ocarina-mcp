# fifth-flight — the Deku Tree repo that flew flights four and five

Lineage: a copy of `examples/second-light` that kept playing. It flew the
fourth flight (2026-08-02 evening, MCP-direct, dojo docs/23 — the census
cap, the looking organ, ocarina's first climb) and then the fifth
(2026-08-03, dojo docs/24): **the first navigation by a mind-side map** —
a region graph distilled offline from the scene's collision mesh
(`lab/navgraph/` in this repo's root), compiled into waypoints, and flown
to the exact chest the fourth flight failed three ways to reach. The
chest opened. The journal carries both flights end to end.

Run it:

```bash
python3 -m ocarina --repo examples/fifth-flight
# then launch SoH; it connects out to 127.0.0.1:43384
```

The fifth flight's artifacts, all in `machine/behaviors/navgraph.py` with
their post-mortems in-file:

- `goto_vine_v1` — cross the ground floor east of the web hole (a bg
  actor the graph cannot know), climb the graph's region-0→region-2 vine
  column. First body steered by an offline nav graph.
- `walk_ring_v1` — the spiral walkway by compiled waypoints, carrying its
  own expected-height table: the hand-rolled ancestor of the `fell`
  event. Never steers at the chest — on an annulus the straight line is
  the void.
- `open_chest_v2..v5` — six versions of humility, each buying a missing
  sense: trilateration beats the bearings gap (5-unit fix vs the room's
  actor-entry truth), En_Box's front = rot_y + 0x8000 (AJ, eyewitness,
  twice), analog magnitude 32 is the fine motor the body never had, and
  v6's staging point sat off-mesh so Link auto-jumped into the atrium —
  waypoint validation against the graph must be a service, not a
  discipline.
- `probe.py`'s `locate_probe_v1` — absolute position into the journal
  for mind-side localization; the measuring instrument of the place
  sense the design doc will propose.

The second-light fossils (demoted damage wake, removed overhead-lurker,
the rewired hunt-over) are all still here — see
`examples/second-light/README.md` for their stories.

NOTE: this is a commissioning example, not a benchmark run. A real
playthrough repo starts empty (new repo = new kid) and grows its own
machine.
