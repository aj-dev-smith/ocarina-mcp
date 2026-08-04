"""The o'clock test, headless: routes must respect the mesh, never the void.

1. Within the 2F ring: route between opposite sides of the annulus must
   exist, stay in-region, and be much longer than the chord (i.e. it
   walks the perimeter, it cannot cross the void).
2. Ground floor -> ring: no walk path exists; the region-level planner
   must find the vine climb leg.
3. Identity is deterministic (dojo docs/25, a contract requirement):
   names derive from geometry alone, are unique, and the pinned names
   below survive any distiller change that doesn't move the geometry —
   mind-side knowledge accrues on names, and a rename is amnesia.
"""

import json
import math

# The pinned stable names (regenerating from an unchanged mesh MUST
# reproduce these — the fifth flight's geography, by name):
R_GROUND_FLOOR = "r@30,0,70"        # GF atrium, y 0
R_RING = "r@250,340,30"             # the 2F spiral walkway, y 280..400
E_GF_RING_VINE = "vine@120,0,-300"  # the vine column the fifth flight climbed
E_ATRIUM_LADDER = "ladder@-240,0,210"  # the ladder the fourth flight scanned out

with open("ydan_navgraph.json") as f:
    G = json.load(f)

V = G["vertices"]
polys = {p["i"]: p for p in G["floor_polys"]}
for p in polys.values():
    a, b, c = (V[k] for k in p["v"])
    p["cen"] = [(a[0]+b[0]+c[0])/3, (a[1]+b[1]+c[1])/3, (a[2]+b[2]+c[2])/3]

by_name = {r["name"]: r for r in G["regions"]}


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


# --- test 3 first: identity, because tests 1-2 resolve regions by name ------
names = [r["name"] for r in G["regions"]]
assert len(set(names)) == len(names), "region names are not unique"
for r in G["regions"]:
    if "~" in r["name"]:
        continue    # deterministic collision-breaker suffix
    cx, cy, cz = (int(round(v / 10.0) * 10) for v in r["centroid"])
    assert r["name"] == f"r@{cx},{cy},{cz}", \
        f"region {r['id']} name {r['name']!r} does not match its geometry"
areas = [r["area"] for r in G["regions"]]
assert areas == sorted(areas, reverse=True), "ids are not area-sorted"
for pinned in (R_GROUND_FLOOR, R_RING):
    assert pinned in by_name, f"pinned region name {pinned!r} vanished — " \
        f"a distiller change renamed the geography (mind-side amnesia)"
edge_names = [e["name"] for e in G["climb_edges"]]
assert len(set(edge_names)) == len(edge_names), "climb edge names not unique"
for pinned in (E_GF_RING_VINE, E_ATRIUM_LADDER):
    assert pinned in edge_names, f"pinned climb edge {pinned!r} vanished"
print("TEST 3 OK: identity is deterministic; pinned names present\n")

GF_ID = by_name[R_GROUND_FLOOR]["id"]
RING_ID = by_name[R_RING]["id"]

# --- test 1: the ring -------------------------------------------------------
ring = [p for p in polys.values() if p["r"] == RING_ID]
# the void center = the atrium's ground-floor centroid, NOT the mean of
# ring polys — the 2F walkway is a C-shaped arc, its mean is off-center
r_gf = by_name[R_GROUND_FLOOR]
cx, cz = r_gf["centroid"][0], r_gf["centroid"][2]
north = min(ring, key=lambda p: p["cen"][2])   # 12 o'clock (min z)
south = max(ring, key=lambda p: p["cen"][2])   # 6 o'clock (max z)
print(f"ring center ~({cx:.0f}, {cz:.0f}); "
      f"12h poly #{north['i']} at {[round(v) for v in north['cen']]}, "
      f"6h poly #{south['i']} at {[round(v) for v in south['cen']]}")

path = astar(north["i"], south["i"])
assert path, "no path around the ring?!"
assert all(polys[i]["r"] == RING_ID for i in path), "path left the ring region"
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
gf = next(p for p in polys.values() if p["r"] == GF_ID)
assert astar(gf["i"], north["i"]) is None, \
    f"walk path between {R_GROUND_FLOOR} and {R_RING}?!"
links = [e for e in G["climb_edges"]
         if e["linked"] and GF_ID in e["from"] and RING_ID in e["to"]]
assert links, f"no climb edge links {R_GROUND_FLOOR} to {R_RING}"
e = links[0]
assert e["name"] == E_GF_RING_VINE
print(f"TEST 2 OK: no walk path GF -> ring; planner leg = {e['name']} "
      f"(y {e['y_lo']}..{e['y_hi']})")
