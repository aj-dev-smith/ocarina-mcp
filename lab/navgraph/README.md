# navgraph lab — the place-sense feasibility experiment

**Question (AJ, 2026-08-03):** can a navigation region graph be *generated*
from OoT's collision data — no per-room authoring — and does it solve the
"o'clock problem" (mind at 12 o'clock on the Deku Tree's 2F ring, chest at
6 o'clock, straight-line thinking walks into the void)?

**Answer: yes, empirically.** The whole Deku Tree is 2,321 collision polys.
Flood fill over walkable polys produces 50 regions whose big members are
instantly recognizable geography (ground floor, 2F ring, 3F, B1, B2, the
compass rooms). Ladder/vine/crawl surfaces self-identify from wall flags in
the surface data and cluster into 12 climb columns — the dungeon's whole
vertical spine (B2→B1→GF→ring→3F) reconstructs automatically. Poly-level A*
routes 12→6 o'clock along 1,816 units of perimeter against an 842-unit
chord, never nearer than 300 units to the void's center — the void has no
polys, so no route can cross it: "go around" is the absence of edges, not
knowledge. Region-level BFS over climb edges plans multi-leg routes
(GF → vine → walk the ring arc).

## Pipeline

    o2r_collision.py   parse SoH's oot.o2r CollisionHeader resource
                       (layout transcribed from Shipwright source — see
                       the file header for the exact provenance)
    distill.py         classify polys, flood-fill regions, cluster climb
                       columns, link them to regions, emit navgraph JSON
    make_viewer.py     bake the JSON into a self-contained HTML viewer
                       (canvas map, elevation slices, hover, click-to-route
                       with in-region A* + cross-region leg planning)
    test_ring.py       the o'clock test, headless (run it after changes)

Reproduce:

    python3 distill.py /Users/aj/Code/Shipwright/oot.o2r \
        scenes/nonmq/ydan_scene/ydan_sceneCollisionHeader_00B610 ydan_navgraph.json
    python3 make_viewer.py ydan_navgraph.json ydan_viewer.html
    python3 test_ring.py
    open ydan_viewer.html

## Ground-truth anchors (fourth flight, dojo docs/23)

- The atrium ladder the mind found by scan (bearing 0xC000, 131 units)
  appears as the `ladder y 0..210 from [0] to [1]` column at (-241, 105, 211).
- Region 0 (y=0) is the room-0 floor the flight was stuck on; region 2
  (y 280..400 — it spirals) is the ring above it; the chest ledge and the
  bushes' floor separate exactly as the census `above` column implied.

## v0 limitations (deliberate)

- Drop/jump candidates are boundary-proximity guesses, unverified — the
  viewer draws them dashed; nothing consumes them yet.
- Crawl tunnels cluster as per-end thresholds, not a single edge; the
  tunnel's own sliver floor region carries the connectivity.
- Routes are poly-centroid polylines (no funnel smoothing) — they zigzag.
- One 3F vine column and the crawl ends remain honestly unlinked (`!!` in
  distill output, amber in the viewer) — the boundary is shown, not hidden.
  (The crawl ends are an END-CLUSTERING gap, not a linking one: the four
  crawl panels share no vertices, so the lo/hi split empties.)
- Region ids are unstable across distiller changes; a real place sense
  needs deterministic naming before mind-side knowledge can accrue on them.

## The fifth flight (2026-08-03): the graph flew, and the chest opened

Same evening as the distiller: the mission the fourth flight failed three
ways — open room 0's chest — completed end-to-end with the mind navigating
by this graph (see `ocarina-flights/04-mcp-direct/second-light/machine/
behaviors/navgraph.py` for the flight bodies and their post-mortems).
Vine leg 22-33s, spiral arc walk ~5-7s, chest opened on the v8 approach.
Field results for the design doc:

- **Localization worked every time.** locate_probe pos -> region matched
  the eyewitness view at every check, including "over the web hole is not
  region 0" (the localizer was right and the test point was wrong).
- **Trilateration from census distances fixed the chest 5 units off its
  actor-entry truth** — the bearings gap (backlog #3) is workable-around
  but cost three behavior versions; bearings in the digest would have
  cost zero.
- **Interaction is the next starvation, not navigation.** Getting to the
  chest took one try; opening it took six. Missing senses, in order
  earned: prop FACING (En_Box front = rot_y + 0x8000 — learned from AJ's
  eyewitness call, twice), fine motor (analog magnitude — the body had
  two gaits: sprint and nothing), and interaction affordance feedback
  (the A-icon's text is presented truth ocarina cannot yet read).
- **The void jump (v6): the mind hardcoded a staging point its own map
  calls off-mesh, and Link auto-jumped into the atrium.** Waypoint
  validation against the graph must be automatic (a `goto` service
  refuses off-mesh targets by construction), not a discipline.
- Screenshot-as-escalation earned its backlog rank: AJ's two screenshots
  resolved in seconds what probes argued about for minutes.

## Kokiri Forest: two motor-grade fixes (2026-08-05, dojo docs/28 §4)

The first OVERWORLD scene distilled (spot04, 1,692 polys) exposed two
assumptions that only held indoors. Both fixed here and mirrored verbatim
into the port (`ocarina/navgraph.py` — the lab/port diff is still just the
header, the import line, the CLI harness and `base_segments`); ydan
re-distills BYTE-IDENTICAL under both, `ydan_navgraph.json` included, so
no pinned name moved.

- **Tolerance welding (`WELD_TOL = 1.5`).** The shipped scenes stitch
  sub-meshes without welding: Kokiri's forest floor meets itself at
  corners 1.0 unit apart (`[-701,0,-301]` vs `[-701,1,-301]`), and an
  exact-coordinate weld flood-filled the main floor into two non-adjacent
  regions — an invisible wall across the mind's own front yard. The
  tolerance sits below the smallest genuine feature separation measured
  across ydan (2.0), link_home (2.24) and kokiri_shop (2.83), so seams
  heal and no two real surfaces fuse. spot04: 101 -> 98 regions (three
  seam merges, 124+22+3 polys into one 149-poly forest floor).
- **Point-in-poly climb linking.** Linking a column by nearby region
  VERTICES assumed indoor mesh density. Outdoors one terrain triangle
  spans hundreds of units: the treehouse ladder's nearest region vertex
  is 289 units away even though it stands ON a floor poly, so it linked
  its top to the balcony and its bottom to nothing — Link's front door,
  map-unreachable. Columns now also link to every region whose floor
  SURFACE lies under (or over) their XZ footprint within the span.
  spot04: 1/6 -> 2/6 columns linked; `traverse("ladder@-30,-80,1000")`
  now resolves from anywhere on the forest floor.

Regression: `tests/test_place.py` (`TestSeamWelding`,
`TestClimbLinkingOnCoarseTerrain` — synthetic, always run;
`TestRealSpot04Graph` — real-o2r pins, skipped without the o2r), beside
this file's `test_ring.py`, which must stay green unchanged.

## Status

Lab only. Nothing here touches the blessed surface; promoting any of it
into ocarina (digest `place.*` section, `oot://place`, nav service, `goto`)
is contract work needing a design doc and AJ's blessing.
