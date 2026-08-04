"""census_probe: report what the wire actually sent, into the journal.

Authored live, fourth flight 2026-08-02, to prove (not infer) the census
truncation finding: DojoLink.cpp sorts every actor of 8 categories by
xzDistToPlayer and sends only the nearest kMaxActors = 12. Far actors
never reach the sight predicate at all — they are ranked off the wire.

Diagnostic only: holds no pad, changes nothing. It reports by ABORTING
with its findings, because `detail` on behavior_done is the one string a
behavior can put in the journal.
"""

from ocarina.behavior import Behavior, BehaviorAbort


def _probe_body(game, ctx):
    st = game.state()
    actors = st.get("actors") or []
    total = st.get("actor_count_total")
    sighted = sum(1 for a in actors if a.get("sighted"))
    drawn = sum(1 for a in actors if a.get("drawn"))
    far = max((a.get("dist_xz", 0.0) for a in actors), default=0.0)
    # `above`, not just dist_xz. The harness backlog's oldest open item
    # (2026-07-30) is exactly this: probe_room.py labelled its dist_xz
    # column "dist", and a ceiling actor 1072 units overhead read as
    # adjacent — it cost a day of planning. v1 of THIS probe repeated the
    # bug verbatim. Sign convention matches the digest: above > 0 means
    # over Link's head (dist_y is player.y - actor.y, the negation of
    # what actor code computes — the trap docs/08 catches every flight).
    slots = ", ".join(
        f"{a.get('id'):#06x}/c{a.get('cat')}"
        f"@{a.get('dist_xz', 0):.0f}^{-float(a.get('dist_y', 0.0)):+.0f}"
        f"{'S' if a.get('sighted') else ''}{'D' if a.get('drawn') else ''}"
        for a in actors)
    raise BehaviorAbort(
        f"census {len(actors)}/{total} actors (truncated={total is not None and total > len(actors)}), "
        f"sighted={sighted} drawn={drawn} farthest_on_wire={far:.0f} :: {slots}")


def _locate_body(game, ctx):
    """Fifth flight (2026-08-03): the navgraph field test. The mind holds a
    lab-generated region graph of this scene (ocarina/lab/navgraph) and
    localizes Link against it by reading this probe's report. Absolute
    position is diagnostic-journal only — the fairness form of this sense
    (regions, not coordinates) is exactly what the place-sense design doc
    will propose; this probe is its measuring instrument."""
    pos = game.pos()
    if pos is None:
        raise BehaviorAbort("no player on the wire")
    st = game.state()
    actors = st.get("actors") or []
    slots = ", ".join(
        f"{a.get('id'):#06x}@{a.get('dist_xz', 0):.0f}^{-float(a.get('dist_y', 0.0)):+.0f}"
        f"{'S' if a.get('sighted') else ''}"
        for a in actors)
    raise BehaviorAbort(
        f"pos=({pos[0]:.0f}, {pos[1]:.0f}, {pos[2]:.0f}) "
        f"climbing={game.climbing()} on_wall={game.on_a_wall()} "
        f"cam_yaw={game.camera_yaw():#06x} :: census {slots}")


BEHAVIORS = {
    "census_probe_v1": Behavior(
        name="census_probe", version=1,
        description="journal the raw census: slots used, total on the wire, "
                    "sighted/drawn counts, farthest actor sent",
        body=_probe_body,
        success=lambda game, initial, events: False,
        timeout_s=10.0,
        grade="diagnostic; holds no pad, always aborts (the abort IS the report)"),
    "locate_probe_v1": Behavior(
        name="locate_probe", version=1,
        description="journal Link's absolute position + wall state + census "
                    "distances, for mind-side localization against the lab "
                    "navgraph (fifth flight)",
        body=_locate_body,
        success=lambda game, initial, events: False,
        timeout_s=10.0,
        grade="diagnostic; holds no pad, always aborts (the abort IS the report)"),
}
