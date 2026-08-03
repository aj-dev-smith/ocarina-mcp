# fourth-flight — the Deku Tree, played from a real Claude session

The machine that flew ocarina's fourth live session (2026-08-02 evening
— full record: `../../../oot-dojo/docs/23-fourth-flight-2026-08-02.md`).
It is the first flight with **no rig in the middle**: ocarina ran as an
MCP server registered in Claude Code, and the mind played it through
`mcp__ocarina__*` tool calls end to end — status, reload_machine,
force_state, set_directive, resume, and `scan`.

The session's headline is a bug the first three flights could not have
found, because none of them was *trying to accomplish anything*: the
wire's actor census was capped at the nearest **12** actors, and 0.5.0
had just moved the sensorium's spine onto that census. In Deku Tree room
0 that sent 12 of 29 actors with the wire stopping at ~310 units, so
live Deku Babas AJ was looking straight at never reached the sight
predicate. Worse, a RANK cap shrinks its own radius as clutter rises:
walking deeper into the room let bushes evict the enemies. AJ's ruling —
"raise it VERY high... it's up to YOU to design the machine in a way
that works off the information that you need" — put the cap at 256 and
the curation upstairs where it can be reviewed.

Run it:

```bash
python3 -m ocarina --repo examples/fourth-flight
# or register it as an MCP server and play it directly:
#   claude mcp add ocarina --env PYTHONPATH=$PWD -- \
#       python3 -m ocarina --repo $PWD/examples/fourth-flight
# then launch SoH; it connects out to 127.0.0.1:43384
```

Requires an instrument built after 2026-08-02 (`kMaxActors = 256` in
DojoLink.cpp). An older one still runs, and says so loudly — the runtime
diagnoses a truncated census rather than quietly judging a partial world.

## What is here that second-light did not have

**behaviors/climb.py** — `climb_ladder_v1`, ocarina's first vertical
movement of any kind. Written from `z_player.c`'s three facts (the climb
is not camera-relative, A lets go, the grab needs forward motion) after
the mind called the `scan` tool itself and found `is_ladder: true` at
bearing 0xC000. Climbed first try in 5.6s. v2 of the body adds a
widening scan and travel, because the climbable is rarely where you are
standing.

**behaviors/seek.py** — sight-honest seeking. Raising the census cap
widened a pre-existing hole: behaviors read the RAW census through
`game.actors()`, which sight-gating never touched, so `approach_baba_v1`
would now walk at a baba 1500 units away through two walls. v2 filters
on the wire's own `sighted` bit with per-run object permanence. Also
`charge_chest_v1`, `collect_item_v2`, `find_and_open_chest_v1`.

**behaviors/survey.py** — `survey_room_v1`, the looking organ. Nothing
in second-light's machine ever turned the view, so the clearing loop
starved after the first kill with live babas at Link's back.

**behaviors/probe.py** — `census_probe_v1`, the diagnostic that found the
census cap, reporting by aborting with its findings (`detail` is the one
string a behavior can put in the journal). Its v1 shipped the harness
backlog's oldest open bug verbatim — printing `dist_xz` and calling it
"dist" — and adding `above` cracked the chest hunt open in one line.

## What this machine does NOT do, and why it matters

It never opened the chest. The chest sits +360 above the floor and every
door in room 0 is above or below Link; the room is a vertical shaft and
the sensorium is flat. Three attempts failed three ways, all downstream
of one absence: **`scan` is a horizontal fan at a fixed height and never
looks down**, so nothing can report a ledge, a drop, or having just
fallen. Link climbed, gained 280 units, and gave them back to a
look-around that could not see the edge it was walking off.

The honest failures are kept in the file rather than tuned away —
`collect_item_v1` and `open_chest_v1` are RETIRED with their field
postmortems, and `_approach_and_open` refuses outright when the target is
more than 140 units above instead of walking underneath it and mashing A.
The design conclusion is filed in `harness-backlog.md` as the place-sense
item; a `fell` event is nearly free and should land first.

NOTE: this is a commissioning example, not a benchmark run. A real
playthrough repo starts empty (new repo = new kid) and grows its own
machine.
