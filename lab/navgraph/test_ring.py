"""The o'clock test, headless: routes must respect the mesh, never the void.

1. Within the 2F ring (region 2): route between opposite sides of the
   annulus must exist, stay in-region, and be much longer than the chord
   (i.e. it walks the perimeter, it cannot cross the void).
2. Ground floor (region 0) -> ring (region 2): no walk path exists;
   the region-level planner must find the vine climb leg.
"""

import json
import math

with open("ydan_navgraph.json") as f:
    G = json.load(f)

V = G["vertices"]
polys = {p["i"]: p for p in G["floor_polys"]}
for p in polys.values():
    a, b, c = (V[k] for k in p["v"])
    p["cen"] = [(a[0]+b[0]+c[0])/3, (a[1]+b[1]+c[1])/3, (a[2]+b[2]+c[2])/3]


def dist3(a, b):
    return math.dist(a, b)


def astar(si, gi):
    import heapq
    goal = polys[gi]["cen"]
    g = {si: 0.0}
    came = {}
    pq = [(dist3(polys[si]["cen"], goal), si)]
    closed = set()
    while pq:
        _, cur = heapq.heappop(pq)
        if cur == gi:
            path = [cur]
            while cur in came:
                cur = came[cur]
                path.append(cur)
            return path[::-1]
        if cur in closed:
            continue
        closed.add(cur)
        for nb in polys[cur]["adj"]:
            t = g[cur] + dist3(polys[cur]["cen"], polys[nb]["cen"])
            if t < g.get(nb, math.inf):
                g[nb] = t
                came[nb] = cur
                heapq.heappush(pq, (t + dist3(polys[nb]["cen"], goal), nb))
    return None


# --- test 1: the ring -------------------------------------------------------
ring = [p for p in polys.values() if p["r"] == 2]
# the void center = the atrium's ground-floor centroid (region 0), NOT the
# mean of ring polys — the 2F walkway is a C-shaped arc, its mean is off-center
r0 = next(r for r in G["regions"] if r["id"] == 0)
cx, cz = r0["centroid"][0], r0["centroid"][2]
north = min(ring, key=lambda p: p["cen"][2])   # 12 o'clock (min z)
south = max(ring, key=lambda p: p["cen"][2])   # 6 o'clock (max z)
print(f"ring center ~({cx:.0f}, {cz:.0f}); "
      f"12h poly #{north['i']} at {[round(v) for v in north['cen']]}, "
      f"6h poly #{south['i']} at {[round(v) for v in south['cen']]}")

path = astar(north["i"], south["i"])
assert path, "no path around the ring?!"
assert all(polys[i]["r"] == 2 for i in path), "path left the ring region"
plen = sum(dist3(polys[a]["cen"], polys[b]["cen"]) for a, b in zip(path, path[1:]))
chord = dist3(north["cen"], south["cen"])
print(f"route: {len(path)} polys, length {plen:.0f} vs chord {chord:.0f} "
      f"(ratio {plen/chord:.2f})")
assert plen > 1.4 * chord, "route is suspiciously chord-like — did it cross the void?"

# does the route bend around the center rather than through it?
min_r = min(math.hypot(polys[i]["cen"][0] - cx, polys[i]["cen"][2] - cz)
            for i in path)
print(f"closest approach to ring center along route: {min_r:.0f} units")
assert min_r > 150, "route passed through the middle of the atrium!"
print("TEST 1 OK: the route walks the perimeter; the void is uncrossable\n")

# --- test 2: ground floor -> ring needs a climb leg -------------------------
gf = next(p for p in polys.values() if p["r"] == 0)
assert astar(gf["i"], north["i"]) is None, "walk path between region 0 and 2?!"
links = [e for e in G["climb_edges"]
         if e["linked"] and 0 in e["from"] and 2 in e["to"]]
assert links, "no climb edge links region 0 to region 2"
e = links[0]
print(f"TEST 2 OK: no walk path region 0 -> 2; planner leg = {e['kind']} at "
      f"{e['at']} (y {e['y_lo']}..{e['y_hi']})")
