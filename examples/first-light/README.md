# first-light — the example save-file repo

The machine that flew ocarina's first live session (2026-08-01, the same
day the server was built — full record:
`../../../oot-dojo/docs/20-first-light-2026-08-01.md`). Kept as a working
example of what a save-file repo looks like: `machine/machine.yaml` is
the topology, `machine/behaviors/` the 20 Hz bodies, and everything else
(journal/, .ocarina/) is grown by the server at run time.

Run it:

```bash
python3 -m ocarina --repo examples/first-light
# then launch SoH; it connects out to 127.0.0.1:43384
```

What this machine does: `boot` presses A/START (never the stick — see the
safety argument in behaviors/watch.py) until the save file loads, then
`stand_watch` observes without holding the pad, so a human keyboard stays
live. Root transitions journal first sightings and wake on damage.
`explore_room` (reachable via `force_state`) wanders on the geometry
sense.

The behaviors file is also the first postmortem trail: `wander_scan_v1`
is RETIRED in place — it pinballed in open space because the bearing
behind you is as open as the one ahead — and `wander_scan_v2` fixed it
with heading persistence, which promptly walked Link clean out of the
Deku Tree. Lessons stay in the file; that is what the trail is for.

NOTE: this is a commissioning example, not a benchmark run. A real
playthrough repo starts empty (new repo = new kid) and grows its own
machine.
