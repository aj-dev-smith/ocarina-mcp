# seventh-flight — the free-play line, through the 0.8.0 acceptance

Lineage: a copy of the second-light repo that kept playing (flights
four and five as `examples/fifth-flight`, six as
`examples/sixth-flight`). This snapshot carries TWO sessions on the
same line (both 2026-08-04, MCP-direct):

**The free-play session** (AJ: "do whatever you want" — recorded in
dojo docs/27's evidence section, its only written record): the ring
chest re-taken by one named traverse, the bench's first deliberate jump
(the 2F walkway gap, lab-measured), its first door, a scene door map by
probe, a full video-take run for AJ's recording — and the bench's
SECOND death: the health-critical wake's `hold` default fired (~5 min)
while the mind deliberated, and the scrub volley finished Link at the
2F scrub room. A freeze is not indefinite shelter. AJ's eyewitness also
corrected the ring chest's prize on this session: the DUNGEON MAP, not
the slingshot (docs/26 erratum).

**The 0.8.0 acceptance** (dojo docs/27, same evening): the first
game-native save in bench history, `use_item("deku_nut")` working on
first exercise (5→4 on the wire), the chest `opened` bit commissioned
from AJ's eyewitness and landed mid-session (open_chest_v5 now refuses
in 0.1 s by name instead of pressing A at furniture), and the first
dialogue ocarina ever read — Navi, verbatim, name substitution and all:
"Look, look, Claude! You can see down below this web using [C-Up]!"
The journal carries every beat, both deaths' lineage included.

Run it (copy it out of examples/ first — never in place):

```bash
python3 -m ocarina --repo <flight-dir>/seventh-flight \
    --o2r /Users/aj/Code/Shipwright/oot.o2r
# then launch SoH; it connects out to 127.0.0.1:43384
# requires the 2026-08-04 DojoLink patch (message block, save/assign_c
# ops, chest opened bit) — an older instrument is diagnosed loudly
```

The session's artifacts, in `machine/behaviors/stroll.py` (free play)
and the guard added to `navgraph.py`:

- `goto_ring_v1` — the GF → ring leg by NAME (`vine@120,0,-300`);
  traverse routes on the mesh so the web hole is unpathable by
  construction and the start position stops mattering. Clears Navi
  boxes blind (bounded 12×A, journaled as blind) — a discipline 0.8.0
  makes obsolete: the box text now lands in the journal and
  `oot://dialogue` regardless.
- `leap_gap_v1` — the bench's first deliberate jump: lab-validated arc
  waypoints, a full-sprint run-up on a fixed world bearing over the
  measured ~100-unit gap, ledge-grab recovery, map-judged landing.
- `enter_door_v1` — the first door body; doors are the region graph's
  missing edge type, so this is a body-with-eyes job (census pos,
  contact-walk, map-judged arrival). v1's false success (the near side
  of the door, Navi box open) was caught by AJ's eyes and fixed by
  excluding the approach's start region.
- `door_census_v1` — every door/shutter/transition-plane actor with
  world pos + yaw in one journal line (the abort IS the report).
- `goto_entrance_v1` — walk home to GF's entrance stretch; the
  clearing loop starves mid-room because the babas live by the
  entrance, outside the sight predicate's reach from the vine wall.
- `open_chest_v5`'s already-open guard (`navgraph.py`) — reads the
  census `opened` bit (the game's own treasure flag, on the wire as of
  2026-08-04) and refuses before walking a single step.

Field lessons priced this snapshot: wake `hold` defaults FIRE (the
second death's mechanism); `fetch_item` chases phantom drops toward
the atrium web hole (Link fell through twice; the `fell` sense
narrated both — "dropped about 17 times your height"); and the census
anomaly of two id 0x0192 (== ACTOR_ID_MAX) category-5 actors at dist
0.0 in the scrub room remains uninvestigated.
