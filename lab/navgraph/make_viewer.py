"""Bake a navgraph JSON into a self-contained HTML debug viewer.

Usage: python3 make_viewer.py [navgraph.json] [out.html] [title]

The viewer is a plain-canvas top-down map: regions colored, climb edges
marked, y-slice filter, hover inspection, and click-to-route — poly-level
A* within a region, region-level planning (climb/drop/jump legs) across
regions. Stdlib only; the HTML has no external dependencies.
"""

import json
import sys

TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; background: #14161a; color: #cfd3da;
         font: 13px/1.4 -apple-system, "Segoe UI", sans-serif;
         display: flex; height: 100vh; overflow: hidden; }
  #side { width: 280px; padding: 12px; overflow-y: auto; flex-shrink: 0;
          border-right: 1px solid #2a2e35; }
  #main { flex: 1; position: relative; }
  canvas { display: block; cursor: crosshair; width: 100%; height: 100%; }
  h1 { font-size: 15px; margin: 0 0 8px; color: #fff; }
  h2 { font-size: 12px; margin: 14px 0 4px; text-transform: uppercase;
       letter-spacing: .06em; color: #8a919c; }
  .row { margin: 3px 0; }
  button { background: #23272e; color: #cfd3da; border: 1px solid #3a3f47;
           border-radius: 4px; padding: 2px 8px; margin: 1px; cursor: pointer; }
  button.on { background: #3b82f6; color: #fff; border-color: #3b82f6; }
  #hover, #route { background: #1b1e23; border: 1px solid #2a2e35;
                   border-radius: 6px; padding: 8px; margin-top: 8px;
                   white-space: pre-wrap; font-family: ui-monospace, monospace;
                   font-size: 12px; min-height: 30px; }
  .legend span { display: inline-block; margin-right: 10px; }
  .dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%;
         margin-right: 4px; vertical-align: -1px; }
  label { user-select: none; }
</style>
</head>
<body>
<div id="side">
  <h1>__TITLE__</h1>
  <div style="color:#8a919c">generated navigation graph &mdash; ocarina lab</div>
  <h2>Elevation slice</h2>
  <div id="bands" class="row"></div>
  <div class="row">
    y <input id="ylo" type="number" style="width:70px"> ..
    <input id="yhi" type="number" style="width:70px">
  </div>
  <h2>Layers</h2>
  <div class="row">
    <button id="t_steep">steep</button>
    <button id="t_walls">walls</button>
    <button id="t_climb" class="on">climbs</button>
    <button id="t_cand">drop/jump candidates</button>
    <button id="t_water" class="on">water</button>
    <button id="t_ids">region ids</button>
  </div>
  <h2>Legend</h2>
  <div class="legend">
    <span><span class="dot" style="background:#38d996"></span>climb (linked)</span>
    <span><span class="dot" style="background:#f59e0b"></span>climb (unlinked)</span><br>
    <span><span class="dot" style="background:#60a5fa"></span>water</span>
    <span><span class="dot" style="background:#f43f5e"></span>route</span>
  </div>
  <h2>Hover</h2>
  <div id="hover">&mdash;</div>
  <h2>Route (click start, click goal)</h2>
  <div id="route">click two points&hellip;</div>
  <h2>Regions by area</h2>
  <div id="rlist" style="font-family:ui-monospace,monospace; font-size:11px"></div>
</div>
<div id="main"><canvas id="cv"></canvas></div>
<script>
const DATA = __DATA__;

// ---- derived structures ----------------------------------------------------
const V = DATA.vertices;
const polys = DATA.floor_polys;
const byIndex = new Map(polys.map(p => [p.i, p]));
for (const p of polys) {
  const [a, b, c] = p.v.map(k => V[k]);
  p.cen = [(a[0]+b[0]+c[0])/3, (a[1]+b[1]+c[1])/3, (a[2]+b[2]+c[2])/3];
}
const regions = new Map(DATA.regions.map(r => [r.id, r]));
const regionPolys = new Map();
for (const p of polys) {
  if (!regionPolys.has(p.r)) regionPolys.set(p.r, []);
  regionPolys.get(p.r).push(p);
}
// region-level edges: climb (bidirectional), candidates (drop one-way, jump bi)
const regionEdges = [];
for (const e of DATA.climb_edges) {
  if (!e.linked) continue;
  for (const f of e.from) for (const t of e.to) {
    regionEdges.push({from:f, to:t, kind:e.kind, at:e.at, up:true});
    regionEdges.push({from:t, to:f, kind:e.kind + " (down)", at:e.at, up:false});
  }
}
for (const e of DATA.candidate_edges) {
  regionEdges.push({from:e.from, to:e.to, kind:e.kind + "?", at:e.at, cand:true});
  if (e.kind === "jump")
    regionEdges.push({from:e.to, to:e.from, kind:"jump?", at:e.at, cand:true});
}

function hue(r) { return (r * 137.508) % 360; }
function regionColor(r, a) { return `hsla(${hue(r)}, 60%, 55%, ${a})`; }

// ---- canvas / view ---------------------------------------------------------
const cv = document.getElementById("cv"), ctx = cv.getContext("2d");
let scale = 0.3, ox = 0, oy = 0;   // world -> screen: s*(x)+ox, s*(z)+oy
function fit() {
  const [mn, mx] = DATA.bounds;
  const w = cv.clientWidth, h = cv.clientHeight;
  scale = 0.9 * Math.min(w / (mx[0]-mn[0]), h / (mx[2]-mn[2]));
  ox = w/2 - scale * (mn[0]+mx[0])/2;
  oy = h/2 - scale * (mn[2]+mx[2])/2;
}
function sx(x) { return x*scale + ox; }
function sy(z) { return z*scale + oy; }
function resize() {
  const dpr = window.devicePixelRatio || 1;
  cv.width = cv.clientWidth * dpr; cv.height = cv.clientHeight * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  draw();
}

// ---- elevation bands -------------------------------------------------------
const yMins = [...new Set(DATA.regions.map(r => r.y_min))].sort((a,b)=>a-b);
const bands = [];
let cur = [yMins[0], yMins[0]];
for (const y of yMins.slice(1)) {
  if (y - cur[1] > 150) { bands.push(cur); cur = [y, y]; } else cur[1] = y;
}
bands.push(cur);
let ylo = -1e9, yhi = 1e9;
const bandsDiv = document.getElementById("bands");
const allBtn = document.createElement("button");
allBtn.textContent = "all"; allBtn.className = "on";
allBtn.onclick = () => setSlice(-1e9, 1e9, allBtn);
bandsDiv.appendChild(allBtn);
for (const [lo, hi] of bands) {
  const b = document.createElement("button");
  b.textContent = `${lo}`;
  b.onclick = () => setSlice(lo - 60, hi + 220, b);
  bandsDiv.appendChild(b);
}
function setSlice(lo, hi, btn) {
  ylo = lo; yhi = hi;
  document.getElementById("ylo").value = lo <= -1e9 ? "" : lo;
  document.getElementById("yhi").value = hi >= 1e9 ? "" : hi;
  for (const b of bandsDiv.children) b.classList.remove("on");
  if (btn) btn.classList.add("on");
  draw();
}
document.getElementById("ylo").onchange = e => { ylo = +e.target.value || -1e9; draw(); };
document.getElementById("yhi").onchange = e => { yhi = +e.target.value || 1e9; draw(); };
function visible(p) { return p.cen[1] >= ylo && p.cen[1] <= yhi; }

// ---- layer toggles ---------------------------------------------------------
const toggles = {};
for (const id of ["t_steep","t_walls","t_climb","t_cand","t_water","t_ids"]) {
  const b = document.getElementById(id);
  toggles[id] = b.classList.contains("on");
  b.onclick = () => { toggles[id] = !toggles[id]; b.classList.toggle("on"); draw(); };
}

// ---- drawing ---------------------------------------------------------------
function tripath(p) {
  const [a, b, c] = p.v.map(k => V[k]);
  ctx.beginPath();
  ctx.moveTo(sx(a[0]), sy(a[2]));
  ctx.lineTo(sx(b[0]), sy(b[2]));
  ctx.lineTo(sx(c[0]), sy(c[2]));
  ctx.closePath();
}
function draw() {
  ctx.fillStyle = "#14161a";
  ctx.fillRect(0, 0, cv.clientWidth, cv.clientHeight);

  if (toggles.t_walls) {
    ctx.strokeStyle = "rgba(150,155,165,0.13)"; ctx.lineWidth = 1;
    for (const p of DATA.wall_polys) {
      const ys = p.v.map(k => V[k][1]);
      if (Math.min(...ys) > yhi || Math.max(...ys) < ylo) continue;
      tripath(p); ctx.stroke();
    }
  }
  if (toggles.t_steep) {
    ctx.fillStyle = "rgba(140,140,150,0.25)";
    for (const p of DATA.steep_polys) {
      const ys = p.v.map(k => V[k][1]);
      if (Math.min(...ys) > yhi || Math.max(...ys) < ylo) continue;
      tripath(p); ctx.fill();
    }
  }
  const vis = polys.filter(visible).sort((a,b) => a.cen[1] - b.cen[1]);
  for (const p of vis) {
    const sliver = regions.get(p.r).sliver;
    ctx.fillStyle = regionColor(p.r, sliver ? 0.35 : 0.8);
    tripath(p); ctx.fill();
    ctx.strokeStyle = "rgba(0,0,0,0.25)"; ctx.lineWidth = 0.5; ctx.stroke();
  }
  if (toggles.t_water) {
    ctx.fillStyle = "rgba(96,165,250,0.28)";
    ctx.strokeStyle = "rgba(96,165,250,0.7)";
    for (const w of DATA.water_boxes) {
      if (w.y_surface < ylo || w.y_surface > yhi) continue;
      ctx.beginPath();
      ctx.rect(sx(w.x_min), sy(w.z_min), w.x_length*scale, w.z_length*scale);
      ctx.fill(); ctx.stroke();
    }
  }
  if (toggles.t_cand) {
    ctx.strokeStyle = "rgba(200,120,255,0.5)"; ctx.setLineDash([4,3]);
    for (const e of DATA.candidate_edges) {
      const a = e.at, t = regions.get(e.to).centroid;
      if (a[1] < ylo || a[1] > yhi) continue;
      ctx.beginPath(); ctx.moveTo(sx(a[0]), sy(a[2]));
      ctx.lineTo(sx((a[0]+t[0])/2), sy((a[2]+t[2])/2)); ctx.stroke();
    }
    ctx.setLineDash([]);
  }
  if (toggles.t_climb) {
    for (const e of DATA.climb_edges) {
      if (e.y_hi < ylo || e.y_lo > yhi) continue;
      const x = sx(e.at[0]), y = sy(e.at[2]);
      ctx.fillStyle = e.linked ? "#38d996" : "#f59e0b";
      ctx.beginPath(); ctx.arc(x, y, 7, 0, 7); ctx.fill();
      ctx.fillStyle = "#0b0d10"; ctx.font = "bold 9px monospace";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(e.kind[0].toUpperCase(), x, y + 0.5);
    }
  }
  if (toggles.t_ids) {
    ctx.font = "bold 11px monospace"; ctx.textAlign = "center";
    for (const [rid, ps] of regionPolys) {
      const r = regions.get(rid);
      if (r.sliver || r.centroid[1] < ylo || r.centroid[1] > yhi) continue;
      ctx.fillStyle = "#fff";
      ctx.fillText(rid, sx(r.centroid[0]), sy(r.centroid[2]));
    }
  }
  drawRoute();
  drawPicks();
}

// ---- picking / hover -------------------------------------------------------
function nearestPoly(mx, my, filter) {
  let best = null, bd = 25 * 25;
  for (const p of polys) {
    if (filter && !filter(p)) continue;
    const dx = sx(p.cen[0]) - mx, dy = sy(p.cen[2]) - my;
    const d = dx*dx + dy*dy;
    if (d < bd) { bd = d; best = p; }
  }
  return best;
}
cv.addEventListener("mousemove", ev => {
  const r = cv.getBoundingClientRect();
  const p = nearestPoly(ev.clientX - r.left, ev.clientY - r.top, visible);
  const h = document.getElementById("hover");
  if (!p) { h.textContent = "\\u2014"; return; }
  const reg = regions.get(p.r);
  h.textContent = `region ${reg.id}  y ${reg.y_min}..${reg.y_max}` +
    `\\npolys ${reg.polys}  area ${Math.round(reg.area)}` +
    `\\npoly #${p.i} at [${p.cen.map(v=>Math.round(v)).join(", ")}]` +
    (reg.sliver ? "\\n(sliver)" : "");
});

// ---- A* within a region ----------------------------------------------------
function dist3(a, b) {
  return Math.hypot(a[0]-b[0], a[1]-b[1], a[2]-b[2]);
}
function astar(startI, goalI) {
  const start = byIndex.get(startI), goal = byIndex.get(goalI);
  const open = new Map([[startI, 0]]);
  const g = new Map([[startI, 0]]), came = new Map();
  const f = new Map([[startI, dist3(start.cen, goal.cen)]]);
  const closed = new Set();
  while (open.size) {
    let cur = null, bf = Infinity;
    for (const [k] of open) if (f.get(k) < bf) { bf = f.get(k); cur = k; }
    if (cur === goalI) {
      const path = [cur];
      while (came.has(cur)) { cur = came.get(cur); path.push(cur); }
      return path.reverse().map(i => byIndex.get(i));
    }
    open.delete(cur); closed.add(cur);
    const cp = byIndex.get(cur);
    for (const nb of cp.adj) {
      if (closed.has(nb)) continue;
      const np = byIndex.get(nb);
      const t = g.get(cur) + dist3(cp.cen, np.cen);
      if (t < (g.get(nb) ?? Infinity)) {
        came.set(nb, cur); g.set(nb, t);
        f.set(nb, t + dist3(np.cen, goal.cen));
        open.set(nb, t);
      }
    }
  }
  return null;
}

// ---- region-level planning (BFS over climb/candidate edges) ----------------
function planRegions(fromR, toR) {
  if (fromR === toR) return [];
  const q = [[fromR]], seen = new Set([fromR]);
  const how = new Map();
  while (q.length) {
    const path = q.shift();
    const last = path[path.length - 1];
    for (const e of regionEdges) {
      if (e.from !== last || seen.has(e.to)) continue;
      const np = [...path, e.to];
      how.set(e.to, e);
      if (e.to === toR) {
        const legs = [];
        for (let i = 1; i < np.length; i++) legs.push(how.get(np[i]));
        return legs;
      }
      seen.add(e.to); q.push(np);
    }
  }
  return null;
}

// ---- route -----------------------------------------------------------------
let pickA = null, pickB = null, route = null, routeText = "";
function nearestPolyInRegion(rid, pt) {
  let best = null, bd = Infinity;
  for (const p of regionPolys.get(rid) || []) {
    const d = dist3(p.cen, pt);
    if (d < bd) { bd = d; best = p; }
  }
  return best;
}
function computeRoute() {
  route = []; routeText = "";
  const ra = pickA.r, rb = pickB.r;
  const legs = planRegions(ra, rb);
  if (legs === null) {
    routeText = `NO ROUTE: region ${ra} \\u2192 ${rb}\\n` +
      "no walk surface or climb/candidate edge connects them";
    route = null; return;
  }
  const lines = [`region ${ra} \\u2192 ${rb}: ` +
                 (legs.length ? `${legs.length + 1} leg(s)` : "walk")];
  let curPoly = pickA, curR = ra;
  for (const leg of legs) {
    const exitPoly = nearestPolyInRegion(curR, leg.at);
    const walk = astar(curPoly.i, exitPoly.i);
    if (walk) route.push({kind: "walk", pts: walk.map(p => p.cen)});
    const entryPoly = nearestPolyInRegion(leg.to, leg.at);
    route.push({kind: leg.kind, pts: [exitPoly.cen, leg.at, entryPoly.cen]});
    lines.push(`  walk region ${curR}, then ${leg.kind} \\u2192 region ${leg.to}`);
    curPoly = entryPoly; curR = leg.to;
  }
  const walk = astar(curPoly.i, pickB.i);
  if (walk) {
    route.push({kind: "walk", pts: walk.map(p => p.cen)});
    let len = 0;
    for (let i = 1; i < walk.length; i++) len += dist3(walk[i-1].cen, walk[i].cen);
    lines.push(`  final walk ${Math.round(len)} units, ${walk.length} polys`);
  } else if (!legs.length) {
    lines.push("  (no poly path?! regions should be walk-connected)");
  }
  routeText = lines.join("\\n");
}
function drawRoute() {
  if (!route) return;
  for (const seg of route) {
    ctx.strokeStyle = seg.kind === "walk" ? "#f43f5e" : "#38d996";
    ctx.lineWidth = seg.kind === "walk" ? 2.5 : 2;
    ctx.setLineDash(seg.kind === "walk" ? [] : [6, 4]);
    ctx.beginPath();
    seg.pts.forEach((pt, i) => {
      if (i === 0) ctx.moveTo(sx(pt[0]), sy(pt[2]));
      else ctx.lineTo(sx(pt[0]), sy(pt[2]));
    });
    ctx.stroke();
  }
  ctx.setLineDash([]);
}
function drawPicks() {
  for (const [p, color] of [[pickA, "#38d996"], [pickB, "#f43f5e"]]) {
    if (!p) continue;
    ctx.fillStyle = color;
    ctx.beginPath(); ctx.arc(sx(p.cen[0]), sy(p.cen[2]), 6, 0, 7); ctx.fill();
    ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.5; ctx.stroke();
  }
}
cv.addEventListener("click", ev => {
  if (dragMoved) return;
  const r = cv.getBoundingClientRect();
  const p = nearestPoly(ev.clientX - r.left, ev.clientY - r.top, visible);
  if (!p) return;
  if (!pickA || pickB) { pickA = p; pickB = null; route = null;
    document.getElementById("route").textContent =
      `start: region ${p.r} \\u2014 now click the goal`; }
  else { pickB = p; computeRoute();
    document.getElementById("route").textContent = routeText; }
  draw();
});

// ---- pan / zoom ------------------------------------------------------------
let dragging = false, dragMoved = false, lx = 0, ly = 0;
cv.addEventListener("mousedown", e => { dragging = true; dragMoved = false;
  lx = e.clientX; ly = e.clientY; });
window.addEventListener("mouseup", () => dragging = false);
window.addEventListener("mousemove", e => {
  if (!dragging) return;
  const dx = e.clientX - lx, dy = e.clientY - ly;
  if (Math.abs(dx) + Math.abs(dy) > 3) dragMoved = true;
  ox += dx; oy += dy; lx = e.clientX; ly = e.clientY; draw();
});
cv.addEventListener("wheel", e => {
  e.preventDefault();
  const r = cv.getBoundingClientRect();
  const mx = e.clientX - r.left, my = e.clientY - r.top;
  const k = Math.exp(-e.deltaY * 0.0015);
  ox = mx - (mx - ox) * k; oy = my - (my - oy) * k; scale *= k;
  draw();
}, {passive: false});

// ---- region list -----------------------------------------------------------
{
  const rl = document.getElementById("rlist");
  const rs = [...DATA.regions].filter(r => !r.sliver).sort((a,b) => b.area - a.area);
  for (const r of rs) {
    const d = document.createElement("div");
    d.innerHTML = `<span class="dot" style="background:${regionColor(r.id, 1)}"></span>` +
      `r${String(r.id).padEnd(3)} y ${r.y_min}..${r.y_max}  a ${Math.round(r.area/1000)}k`;
    d.style.cursor = "pointer";
    d.onclick = () => setSlice(r.y_min - 60, r.y_max + 220, null);
    rl.appendChild(d);
  }
}

window.addEventListener("resize", resize);
fit(); resize();
</script>
</body>
</html>
"""

def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "ydan_navgraph.json"
    out = sys.argv[2] if len(sys.argv) > 2 else "ydan_viewer.html"
    title = sys.argv[3] if len(sys.argv) > 3 else "ydan (Deku Tree) navgraph"
    with open(src) as f:
        data = json.load(f)
    data.pop("region_boundaries", None)  # not rendered; keeps the file lean
    html = TEMPLATE.replace("__TITLE__", title).replace("__DATA__", json.dumps(data))
    with open(out, "w") as f:
        f.write(html)
    print(f"wrote {out} ({len(html)//1024} KB)")


if __name__ == "__main__":
    main()
