# ninth-flight — the fresh-file Kokiri repo (0.9.0 acceptance)

Lineage: NEW — not the second-light line. A fresh save file ("C") and
an empty seen-kinds table, started 2026-08-05 for the ninth flight
(dojo docs/28): the **acceptance flight for ocarina 0.9.0's equip /
buy / dialogue_choose**, flown MCP-direct the same day the slate was
built. The mission ran from the treehouse to the Deku Tree's mouth —
sword via the crawlspace, 40 rupees farmed, the bench's FIRST LIVE
BUY (deku_shield, wallet-verified 47→7), the first live
dialogue_choose (the continue-shopping box), both equips worn — then,
extended by AJ at the mouth, INTO the tree: room 0 cleared, two deku
babas, zero damage, three game-native saves, no deaths. The session
record and the honesty audit (scene-table lookups and mind-side mesh
A* — legal in an acceptance flight, contraband in scored play; the
baba killer is a prior-run port) are the last two sections of
docs/28. Read them before citing this flight.

Run it:

```bash
python3 -m ocarina --repo examples/ninth-flight \
    --o2r /Users/aj/Code/Shipwright/oot.o2r
# then launch SoH; it connects out to 127.0.0.1:43384
```

The flight's artifacts:

- `machine/behaviors/kokiri.py` — all 19 field-authored bodies with
  their version stories in the grade strings: the exit-plane house
  legs, the crawl pair, open_chest v1→v4 (boulder-pass, L-approach,
  front = PLAIN yaw), the collectors with their twice-reinvented
  unreachable-target blacklist (the argument for a surface
  primitive), the autonomous money loop (farm → dry → house-cycle →
  farm), the shop legs (door-candidate probing; box hygiene at every
  attempt after a kokiri greeting froze a pad for 100 s), the
  mesh-routed trail leg that stopped 150 short of the mouth as
  ordered, and the room-0 clear chain (seek → approach → kill).
- `machine/behaviors/combat.py` — deku_baba_v4 + approach_baba_v1,
  ported byte-identical from `examples/second-light` (the dojo-graded
  champion killer: 19/20 arena kills). Provenance in-file.
- `journal/mechanical.jsonl` — the whole morning: every wake, both
  spurious force_state wakes, the web localization flicker (six false
  `fell` narrations during the fight over the atrium web), the first
  dialogue of a fresh file ("Hey! C'mon!"), and the room-clear report.
