"""Distill a parsed collision mesh into a navigation region graph.

v0 algorithm, deliberately simple:
  - walkable polys (normal.y >= FLOOR_NY) flood-filled over shared edges
    (vertices deduped by coordinate so sub-mesh seams don't split regions)
  - climb edges from ladder/vine wall polys, linked to the floor regions
    their bottom/top vertices touch
  - drop/jump candidate edges from region-boundary proximity (marked
    "candidate" — v0 makes no traversability promise)

Output: JSON for the HTML viewer, including poly-level adjacency so the
viewer can run A* interactively.

Stdlib only. Lab tool — not part of the ocarina surface.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict

from o2r_collision import CollisionMesh, load_from_o2r

FLOOR_NY = 0.6      # walkable
STEEP_NY = 0.45     # 0.45..0.6 rendered as "steep" (slide-y), not walkable
WALL_NY = 0.3       # |ny| below this = wall
MIN_REGION_AREA = 400.0   # ~20x20 units; smaller regions flagged as slivers

DROP_XZ_RADIUS = 120.0    # boundary midpoints closer than this (XZ) pair up
DROP_MIN_DY = 40.0        # height loss to call it a drop
JUMP_MAX_DY = 24.0        # near-level
JUMP_GAP = (20.0, 130.0)  # XZ gap range for a jump candidate


def _dedupe_vertices(mesh: CollisionMesh):
    """Map original vertex indices to canonical per-coordinate ids."""
    canon = {}
    coords = []
    remap = []
    for v in mesh.vertices:
        if v not in canon:
            canon[v] = len(coords)
            coords.append(v)
        remap.append(canon[v])
    return coords, remap


def _tri_area_and_centroid(a, b, c):
    ux, uy, uz = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    vx, vy, vz = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    cx, cy, cz = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    area = 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)
    cen = ((a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3, (a[2] + b[2] + c[2]) / 3)
    return area, cen


def distill(mesh: CollisionMesh) -> dict:
    coords, remap = _dedupe_vertices(mesh)

    floors, steeps, walls = [], [], []
    for p in mesh.polys:
        if p.ny >= FLOOR_NY:
            floors.append(p)
        elif p.ny >= STEEP_NY:
            steeps.append(p)
        elif abs(p.ny) <= WALL_NY:
            walls.append(p)

    def tri(p):
        return (remap[p.va], remap[p.vb], remap[p.vc])

    # -- flood fill floors over shared (deduped) edges -----------------------
    edge_owners = defaultdict(list)
    for p in floors:
        a, b, c = tri(p)
        for e in (frozenset((a, b)), frozenset((b, c)), frozenset((c, a))):
            edge_owners[e].append(p.index)

    adjacency = defaultdict(set)
    for owners in edge_owners.values():
        for i in owners:
            for j in owners:
                if i != j:
                    adjacency[i].add(j)

    poly_region = {}
    regions = []
    for p in floors:
        if p.index in poly_region:
            continue
        rid = len(regions)
        stack, members = [p.index], []
        poly_region[p.index] = rid
        while stack:
            cur = stack.pop()
            members.append(cur)
            for nb in adjacency[cur]:
                if nb not in poly_region:
                    poly_region[nb] = rid
                    stack.append(nb)
        regions.append(members)

    poly_by_index = {p.index: p for p in mesh.polys}

    region_info = []
    for rid, members in enumerate(regions):
        area = 0.0
        cen_acc = [0.0, 0.0, 0.0]
        ys = []
        for pi in members:
            a, b, c = (coords[k] for k in tri(poly_by_index[pi]))
            t_area, t_cen = _tri_area_and_centroid(a, b, c)
            area += t_area
            for k in range(3):
                cen_acc[k] += t_cen[k] * t_area
            ys += [a[1], b[1], c[1]]
        cen = [round(v / area, 1) if area else 0.0 for v in cen_acc]
        # boundary edges: owned by exactly one floor poly of this region
        boundary = []
        for e, owners in edge_owners.items():
            mine = [o for o in owners if poly_region.get(o) == rid]
            if len(mine) == 1 and len(owners) == 1:
                va, vb = tuple(e)
                boundary.append((coords[va], coords[vb]))
        region_info.append({
            "id": rid,
            "polys": len(members),
            "area": round(area, 1),
            "y_min": min(ys), "y_max": max(ys),
            "centroid": cen,
            "sliver": area < MIN_REGION_AREA,
            "boundary": boundary,
        })

    # -- climb edges ---------------------------------------------------------
    # Tall climbs are stored as stacked wall-poly segments; cluster climbable
    # polys into columns over shared vertices, then link each column's bottom
    # and top to nearby floor regions by proximity (vertex sharing is too
    # strict: floor and wall sub-meshes don't always share vertices).
    climb_polys = []
    for p in walls:
        st = mesh.surface(p)
        if st.is_ladder or st.is_vine or st.is_crawlspace:
            kind = "ladder" if st.is_ladder else ("vine" if st.is_vine else "crawl")
            climb_polys.append((p, kind))

    parent = {}

    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a, b):
        parent.setdefault(a, a)
        parent.setdefault(b, b)
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    vert_climb = defaultdict(list)
    for p, kind in climb_polys:
        parent.setdefault(p.index, p.index)
        for k in tri(p):
            vert_climb[(kind, k)].append(p.index)
    for members in vert_climb.values():
        for other in members[1:]:
            union(members[0], other)

    clusters = defaultdict(list)
    kind_of = {p.index: kind for p, kind in climb_polys}
    for p, _ in climb_polys:
        clusters[find(p.index)].append(p)

    region_verts = defaultdict(set)   # region id -> canonical vertex ids
    for pi, rid in poly_region.items():
        for k in tri(poly_by_index[pi]):
            region_verts[rid].add(k)

    LINK_XZ, LINK_Y = 90.0, 90.0

    def regions_near(points):
        """Regions with a vertex within LINK_XZ/LINK_Y of any given point."""
        hits = set()
        for rid, vids in region_verts.items():
            for k in vids:
                v = coords[k]
                for pt in points:
                    if (abs(v[1] - pt[1]) <= LINK_Y and
                            math.hypot(v[0] - pt[0], v[2] - pt[2]) <= LINK_XZ):
                        hits.add(rid)
                        break
                else:
                    continue
                break
        return hits

    climb_edges = []
    for root, members in clusters.items():
        kind = kind_of[root]
        pts = [coords[k] for p in members for k in tri(p)]
        y_lo = min(pt[1] for pt in pts)
        y_hi = max(pt[1] for pt in pts)
        if kind == "crawl":
            # crawl tunnels connect horizontally: link the XZ extremes
            xs = sorted(pts, key=lambda pt: (pt[0], pt[2]))
            lo_regions = regions_near(xs[: len(xs) // 2])
            hi_regions = regions_near(xs[len(xs) // 2:]) - lo_regions
        else:
            # a climb column can be exited at ANY floor along its span, so
            # link every region XZ-near the column with y inside the span
            near = {}
            for rid, vids in region_verts.items():
                best_y = None
                for k in vids:
                    v = coords[k]
                    if not (y_lo - LINK_Y <= v[1] <= y_hi + LINK_Y):
                        continue
                    if any(math.hypot(v[0] - pt[0], v[2] - pt[2]) <= LINK_XZ
                           for pt in pts):
                        best_y = v[1] if best_y is None else min(best_y, v[1])
                if best_y is not None:
                    near[rid] = best_y
            mid = (y_lo + y_hi) / 2
            lo_regions = {r for r, y in near.items() if y < mid}
            hi_regions = {r for r, y in near.items() if y >= mid}
        cen = [round(sum(pt[i] for pt in pts) / len(pts), 1) for i in range(3)]
        climb_edges.append({
            "kind": kind, "at": cen, "y_lo": y_lo, "y_hi": y_hi,
            "segments": len(members),
            "from": sorted(lo_regions), "to": sorted(hi_regions),
            "linked": bool(lo_regions and hi_regions),
        })
    climb_edges.sort(key=lambda e: e["y_lo"])

    # -- drop / jump candidates from boundary proximity ----------------------
    def boundary_midpoints(info):
        for (a, b) in info["boundary"]:
            yield ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)

    candidates = {}
    big = [ri for ri in region_info if not ri["sliver"]]
    for ra in big:
        for rb in big:
            if ra["id"] == rb["id"]:
                continue
            best = None
            for ma in boundary_midpoints(ra):
                for mb in boundary_midpoints(rb):
                    dxz = math.hypot(ma[0] - mb[0], ma[2] - mb[2])
                    if dxz > DROP_XZ_RADIUS:
                        continue
                    dy = mb[1] - ma[1]
                    if best is None or dxz < best[0]:
                        best = (dxz, dy, ma, mb)
            if best is None:
                continue
            dxz, dy, ma, mb = best
            if dy <= -DROP_MIN_DY:
                kind = "drop"
            elif abs(dy) <= JUMP_MAX_DY and JUMP_GAP[0] <= dxz <= JUMP_GAP[1]:
                kind = "jump"
            else:
                continue
            candidates[(ra["id"], rb["id"])] = {
                "kind": kind, "from": ra["id"], "to": rb["id"],
                "gap_xz": round(dxz, 1), "dy": round(dy, 1),
                "at": [round(v, 1) for v in ma], "candidate": True,
            }

    # -- viewer payload ------------------------------------------------------
    floor_polys = []
    for p in floors:
        floor_polys.append({
            "i": p.index, "v": list(tri(p)), "r": poly_region[p.index],
            "adj": sorted(adjacency[p.index]),
        })
    wall_polys = []
    for p in walls:
        st = mesh.surface(p)
        kind = ("ladder" if st.is_ladder else "vine" if st.is_vine
                else "crawl" if st.is_crawlspace else None)
        wall_polys.append({"v": list(tri(p)), "climb": kind})
    steep_polys = [{"v": list(tri(p))} for p in steeps]

    return {
        "bounds": [mesh.min_bounds, mesh.max_bounds],
        "vertices": coords,
        "floor_polys": floor_polys,
        "wall_polys": wall_polys,
        "steep_polys": steep_polys,
        "regions": [{k: v for k, v in ri.items() if k != "boundary"}
                    for ri in region_info],
        "region_boundaries": {ri["id"]: ri["boundary"] for ri in region_info},
        "climb_edges": climb_edges,
        "candidate_edges": sorted(candidates.values(),
                                  key=lambda e: (e["from"], e["to"])),
        "water_boxes": [vars(w) for w in mesh.water_boxes],
    }


if __name__ == "__main__":
    import sys

    o2r = sys.argv[1] if len(sys.argv) > 1 else "/Users/aj/Code/Shipwright/oot.o2r"
    entry = sys.argv[2] if len(sys.argv) > 2 else \
        "scenes/nonmq/ydan_scene/ydan_sceneCollisionHeader_00B610"
    out = sys.argv[3] if len(sys.argv) > 3 else "lab/navgraph/ydan_navgraph.json"

    mesh = load_from_o2r(o2r, entry)
    graph = distill(mesh)

    n_regions = len(graph["regions"])
    n_big = sum(1 for r in graph["regions"] if not r["sliver"])
    print(f"{len(graph['floor_polys'])} floor polys -> {n_regions} regions "
          f"({n_big} above sliver threshold)")
    for r in sorted(graph["regions"], key=lambda r: -r["area"])[:15]:
        print(f"  region {r['id']:3d}: {r['polys']:3d} polys, area {r['area']:9.0f}, "
              f"y {r['y_min']:5d}..{r['y_max']:5d}, centroid {r['centroid']}")
    linked = sum(1 for e in graph["climb_edges"] if e["linked"])
    print(f"{len(graph['climb_edges'])} climb walls ({linked} linked to regions "
          f"both ends)")
    for e in graph["climb_edges"]:
        tag = "OK " if e["linked"] else "!! "
        print(f"  {tag}{e['kind']:6s} y {e['y_lo']:5d}..{e['y_hi']:5d} "
              f"from {e['from']} to {e['to']} at {e['at']}")
    print(f"{len(graph['candidate_edges'])} drop/jump candidates")

    with open(out, "w") as f:
        json.dump(graph, f)
    print(f"wrote {out}")
