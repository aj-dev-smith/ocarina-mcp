"""Field localizer: world position -> region, edges, and leg plans.

Flight-time usage (positions read live off the wire):

    python3 locate.py <x> <y> <z>              # where am I?
    python3 locate.py <x> <y> <z> <gx> <gy> <gz>   # ...and how do I get there?

Point-in-region: XZ point-in-triangle over floor polys, choosing the poly
whose plane sits closest below the query point (within a tolerance above,
for mid-step queries). Lab tool — not part of the ocarina surface.
"""

import json
import math
import sys
from pathlib import Path

GRAPH = Path(__file__).parent / "ydan_navgraph.json"
FOOT_TOL = 60.0   # accept floors up to this far above the query y (steps, noise)


def load():
    with open(GRAPH) as f:
        g = json.load(f)
    V = g["vertices"]
    for p in g["floor_polys"]:
        a, b, c = (V[k] for k in p["v"])
        p["tri"] = (a, b, c)
        p["cen"] = [(a[0]+b[0]+c[0])/3, (a[1]+b[1]+c[1])/3, (a[2]+b[2]+c[2])/3]
    return g


def _bary_xz(pt, a, b, c):
    (px, pz) = pt
    v0 = (c[0]-a[0], c[2]-a[2])
    v1 = (b[0]-a[0], b[2]-a[2])
    v2 = (px-a[0], pz-a[2])
    d00 = v0[0]*v0[0] + v0[1]*v0[1]
    d01 = v0[0]*v1[0] + v0[1]*v1[1]
    d11 = v1[0]*v1[0] + v1[1]*v1[1]
    d20 = v2[0]*v0[0] + v2[1]*v0[1]
    d21 = v2[0]*v1[0] + v2[1]*v1[1]
    den = d00*d11 - d01*d01
    if abs(den) < 1e-9:
        return None
    u = (d11*d20 - d01*d21) / den
    v = (d00*d21 - d01*d20) / den
    return u >= -0.02 and v >= -0.02 and (u + v) <= 1.02


def _plane_y(pt, a, b, c):
    # y on the triangle's plane at XZ point (fallback: centroid y)
    u = (b[0]-a[0], b[1]-a[1], b[2]-a[2])
    w = (c[0]-a[0], c[1]-a[1], c[2]-a[2])
    nx = u[1]*w[2] - u[2]*w[1]
    ny = u[2]*w[0] - u[0]*w[2]
    nz = u[0]*w[1] - u[1]*w[0]
    if abs(ny) < 1e-9:
        return (a[1] + b[1] + c[1]) / 3
    return a[1] - (nx*(pt[0]-a[0]) + nz*(pt[1]-a[2])) / ny


def locate(g, x, y, z):
    """Best floor poly under (x, y, z), or None -> (poly, floor_y)."""
    best = None
    for p in g["floor_polys"]:
        a, b, c = p["tri"]
        if not _bary_xz((x, z), a, b, c):
            continue
        fy = _plane_y((x, z), a, b, c)
        if fy > y + FOOT_TOL:
            continue
        if best is None or fy > best[1]:
            best = (p, fy)
    return best


def region_edges(g, rid):
    out = []
    for e in g["climb_edges"]:
        if not e["linked"]:
            continue
        if rid in e["from"]:
            for t in e["to"]:
                out.append((e["kind"] + " up", t, e["at"], e))
        if rid in e["to"]:
            for f in e["from"]:
                out.append((e["kind"] + " down", f, e["at"], e))
    for e in g["candidate_edges"]:
        if e["from"] == rid:
            out.append((e["kind"] + "?", e["to"], e["at"], e))
    return out


def plan(g, start_rid, goal_rid):
    if start_rid == goal_rid:
        return []
    q = [[(None, start_rid, None)]]
    seen = {start_rid}
    while q:
        path = q.pop(0)
        last = path[-1][1]
        for kind, to, at, _e in region_edges(g, last):
            if to in seen:
                continue
            np = path + [(kind, to, at)]
            if to == goal_rid:
                return np[1:]
            seen.add(to)
            q.append(np)
    return None


def describe(g, x, y, z):
    hit = locate(g, x, y, z)
    if hit is None:
        print(f"({x:.0f}, {y:.0f}, {z:.0f}): OFF THE MAP — no floor poly "
              f"below within tolerance (airborne? climbing? unmapped?)")
        return None
    p, fy = hit
    r = next(r for r in g["regions"] if r["id"] == p["r"])
    print(f"({x:.0f}, {y:.0f}, {z:.0f}): region {r['id']}  "
          f"(floor y {fy:.0f}, region spans y {r['y_min']}..{r['y_max']}, "
          f"area {r['area']:.0f}{', SLIVER' if r['sliver'] else ''})")
    for kind, to, at, _e in region_edges(g, r["id"]):
        d = math.hypot(at[0] - x, at[2] - z)
        print(f"    {kind:12s} -> region {to:3d}  at "
              f"[{at[0]:.0f}, {at[1]:.0f}, {at[2]:.0f}]  ({d:.0f} away XZ)")
    return r["id"]


def main():
    g = load()
    if len(sys.argv) not in (4, 7):
        print(__doc__)
        return
    x, y, z = map(float, sys.argv[1:4])
    rid = describe(g, x, y, z)
    if len(sys.argv) == 7 and rid is not None:
        gx, gy, gz = map(float, sys.argv[4:7])
        print("goal:")
        goal_rid = describe(g, gx, gy, gz)
        if goal_rid is None:
            return
        legs = plan(g, rid, goal_rid)
        if legs is None:
            print(f"NO PLAN region {rid} -> {goal_rid} "
                  f"(no linked climb/candidate chain)")
        elif not legs:
            print("same region — walk it")
        else:
            print(f"plan ({len(legs)} leg(s)):")
            cur = rid
            for kind, to, at in legs:
                print(f"    from region {cur}: {kind} at "
                      f"[{at[0]:.0f}, {at[1]:.0f}, {at[2]:.0f}] -> region {to}")
                cur = to


if __name__ == "__main__":
    main()
