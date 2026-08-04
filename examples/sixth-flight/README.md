# sixth-flight — the Deku Tree repo that flew the place-sense acceptance

Lineage: a copy of the second-light repo that kept playing (the same
line that flew flights four and five as `examples/fifth-flight`). It
flew the sixth flight (2026-08-04, MCP-direct, dojo docs/26): the
**acceptance flight for ocarina 0.7.0's place sense** — the first
mission ordered entirely in region-graph names, and the first flight
that patched the *server itself* mid-run (twice), landing 0.7.1's three
traverse fixes. It is also the flight on which Link died — the first
death in the bench's history, standing watch at 0.5 hearts inside a
sleeping guard's wake-up radius. The journal carries all of it.

Run it:

```bash
python3 -m ocarina --repo examples/sixth-flight \
    --o2r /Users/aj/Code/Shipwright/oot.o2r
# then launch SoH; it connects out to 127.0.0.1:43384
```

The sixth flight's artifacts, all in `machine/behaviors/place_flight.py`
with their post-mortems in-file:

- `refusal_probe_v1` — attempts three illegal traversals (candidate
  edge, non-adjacent region, descent) and requires clean refusals with
  measured zero movement. Passed on its first run: refusals are a
  designed feature and got flown like one.
- `ascend_to_3f_v5` — GF → ring → 3F by named traverse legs, skipping
  legs `place.region` says are already behind us. Versions 1–4 are the
  flight's story: v1 not retry-safe, v2 bitten off the vine, v3 waited
  for a patrol that never moves, v4 hand-rolled a spider-slalom that
  chased the map's too-coarse base point into a chest and a real gap in
  the vines. Every fix v5 relies on moved SERVER-side (0.7.1) — which
  is the shape the contract wants. The retired slalom stays in-file.
- `spider_probe_v1` — diagnostic (census_probe lineage): 15 s of
  skullwalltula patrol envelopes, reported through the abort detail into
  a wake. It measured three guards at ZERO movement — and the flight's
  hardest lesson is that it measured them *asleep*, from a floor below:
  stationary-in-census is not stationary-when-approached.

The machine.yaml nodes `probe_refusals`, `spider_probe`, and `ascend_3f`
are the flight's additions; everything else is the inherited fossil.

NOTE: this is a commissioning example, not a benchmark run. A real
playthrough repo starts empty (new repo = new kid) and grows its own
machine.
