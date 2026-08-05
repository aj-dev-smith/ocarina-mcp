"""Sight-honest seeking: go to things the player has actually seen.

Authored live, fourth flight 2026-08-02, immediately after the census cap
was lifted (12 -> 256).

WHY THIS FILE EXISTS. Behaviors read the RAW census through
`game.actors()`, which sight-gating never touched — senses.py gates what
the MIND is told, not what the HANDS can reach for. While the wire
truncated at ~310 units that hole was accidentally small. Lifting the cap
made it the whole room: `approach_baba_v1` would now happily walk a
straight line at a baba 1500 units away through two walls, and
`survey_room_v1`'s success test ("a baba is in the census") became
trivially true, so it would never turn to look at all — the looking organ
would stop looking.

The fix is to filter on the wire's own `sighted` bit, which every census
actor now carries. That is the same predicate the sensorium uses, so a
behavior can no longer reach for something the narration would refuse to
mention.

OBJECT PERMANENCE, per run. `sighted` is a THIS-FRAME answer, and the
camera swings constantly while walking; gating each step on it would
abort the moment the target slid off screen. So each body keeps its own
set of keys it has seen sighted during this run and keeps targeting
those — you cannot unsee a baba by turning away from it. Deliberately
per-run rather than persistent: senses.Sightings owns the durable
version, and a behavior inventing a second long-lived memory of what the
player knows is how the two drift apart.
"""

import time

from ocarina.behavior import Behavior, BehaviorAbort
from ocarina.game import Game
from ocarina.protocol import ACTOR_EN_DEKUBABA, TICK

#: En_Item00 — the ground-collectible drops (hearts, rupees). Unnamed in
#: OFFICIAL_NAMES pending param-aware naming (senses.py's open item), so
#: it is spelled here rather than imported as a name that doesn't exist.
ACTOR_EN_ITEM00 = 0x0015

APPROACH_STOP = 550.0     # inside deku_baba_v4's KILL_CHECK_RANGE (700)
PICKUP_DIST = 25.0        # contact range; drops are collected by touch
PROGRESS_STEP = 25.0
STALL_S = 4.0


class _Seen:
    """Keys this run has watched become sighted (see module docstring)."""

    def __init__(self):
        self.keys = set()

    def update(self, game: Game, actor_id: int) -> list:
        """Refresh from the census; return this run's reachable targets,
        nearest first (the census is already sorted nearest-first)."""
        actors = game.actors(actor_id=actor_id)
        for a in actors:
            if a.get("sighted"):
                self.keys.add(a.get("key"))
        return [a for a in actors if a.get("key") in self.keys]


def _go_to(game: Game, actor_id: int, stop_dist: float, deadline_s: float,
           what: str) -> None:
    """Walk at the nearest ever-sighted `actor_id` until inside stop_dist.

    Straight-line, no pathfinding — geometry between Link and the target
    stalls it, which it detects and reports honestly rather than grinding
    into a wall (approach_baba_v1's inherited discipline, and the reason
    that body was worth keeping).
    """
    seen = _Seen()
    deadline = time.monotonic() + deadline_s
    best = None
    stall_until = time.monotonic() + STALL_S
    while time.monotonic() < deadline:
        targets = seen.update(game, actor_id)
        if not targets:
            raise BehaviorAbort(f"no {what} sighted from here")
        target = targets[0]
        dist = target["dist_xz"]
        if dist <= stop_dist:
            return
        if best is None or dist < best - PROGRESS_STEP:
            best, stall_until = dist, time.monotonic() + STALL_S
        elif time.monotonic() > stall_until:
            raise BehaviorAbort(f"no progress toward {what}, stalled near {dist:.0f}")
        game.walk_toward(target, seconds=0.25)
        game.wait(TICK)
    raise BehaviorAbort(f"deadline with {what} still {dist:.0f} away")


def _approach_baba(game, ctx):
    _go_to(game, ACTOR_EN_DEKUBABA, APPROACH_STOP, 20.0, "baba")


def _baba_in_engage_range(game, initial, events):
    """Present-tense positive evidence, and sight-honest: an ever-sighted
    baba is inside v4's engage range NOW."""
    return any(a.get("dist_xz", 1e9) <= 600.0
               for a in game.actors(actor_id=ACTOR_EN_DEKUBABA)
               if a.get("sighted"))


#: One full circle in 45-degree pulses, same mechanics as survey_room_v1
#: (short low-magnitude pulses turn Link far more than they move him; the
#: untargeted Z snaps the lagging follow-cam behind his new facing).
#: LEDGE-SAFE. These were 0.30s at magnitude 45, which turns Link by
#: walking him round a small circle — fine on open floor, a step off the
#: edge when he is standing on top of a climb. He fell exactly that way
#: this flight, immediately after his first successful ladder, and gave
#: back every unit of height he had just earned. Short weak pulses still
#: turn him (facing snaps to the stick almost at once) while moving him
#: barely at all. There is no ledge sense to warn us, so the mitigation
#: has to be "never take a big step while looking".
_LOOK_STEPS = 8
_LOOK_YAW = 0x2000
_LOOK_PULSE_S = 0.14
_LOOK_MAGNITUDE = 28
_LOOK_SETTLE_S = 0.5


def _any_sighted(game: Game, actor_id: int) -> bool:
    return any(a.get("sighted") for a in game.actors(actor_id=actor_id))


def _look_around_for(game: Game, actor_id: int) -> bool:
    """Turn in place until `actor_id` is sighted. True if one is."""
    base = game.camera_yaw()
    for step in range(1, _LOOK_STEPS + 1):
        if _any_sighted(game, actor_id):
            game.pad_clear()
            return True
        game.walk_bearing((base + step * _LOOK_YAW) & 0xFFFF,
                          seconds=_LOOK_PULSE_S, magnitude=_LOOK_MAGNITUDE)
        game.press("Z")
        game.wait(_LOOK_SETTLE_S)
    game.pad_clear()
    return _any_sighted(game, actor_id)


def _collect_item(game, ctx):
    # Drops are collected by walking into them — no button, and pressing A
    # near vines would yank Link up a wall (wander_scan's lesson).
    _go_to(game, ACTOR_EN_ITEM00, PICKUP_DIST, 25.0, "item")
    game.wait(0.4)          # let the contact register before judging


def _collect_item_v2(game, ctx):
    """v1 + eyes. v1 aborted outright when no drop was sighted, which in
    the field meant standing 136 units from a collectible and refusing to
    fetch it because the last sweep happened to end facing elsewhere
    (fourth flight, live). Sight honesty says "don't walk at what you
    haven't seen" — it does not say "give up"; a player looks around.
    Looking is cheap, fair, and the thing the room-clearing loop already
    does between kills."""
    if not _any_sighted(game, ACTOR_EN_ITEM00):
        if not _look_around_for(game, ACTOR_EN_ITEM00):
            raise BehaviorAbort("swept a full circle, no drop in sight")
    _go_to(game, ACTOR_EN_ITEM00, PICKUP_DIST, 25.0, "item")
    game.wait(0.4)


ACTOR_EN_BOX = 0x000A     # treasure_chest, already in OFFICIAL_NAMES

CHEST_OPEN_DIST = 60.0    # "Open" prompt range; the chest has collision, so
                          # walking at it ends in contact, not overlap
CHEST_TRIES = 10
CHEST_SETTLE_S = 0.6      # a press has to survive the open animation before
                          # the get-item message appears


def _yaw_diff(a: int, b: int) -> int:
    return abs((((a - b) & 0xFFFF) + 0x8000) % 0x10000 - 0x8000)


def _walk_open_leg(game: Game, avoid_yaw, seconds: float = 1.6):
    """One exploring leg down the most open bearing. Returns the heading.

    `avoid_yaw` vetoes a cone around where we just came from — without it
    the most open bearing after any leg is usually the way back, and the
    body paces a line forever (wander_scan_v1's oscillation postmortem,
    first light).
    """
    best_yaw, best_score = None, -1.0
    for ray in game.scan(rays=16, length=600):
        yaw = int(ray.get("yaw", 0)) & 0xFFFF
        if avoid_yaw is not None and _yaw_diff(yaw, avoid_yaw) < 0x2000:
            continue
        score = 600.0 if not ray.get("hit") else float(ray.get("dist", 0.0))
        if score > best_score:
            best_yaw, best_score = yaw, score
    if best_yaw is None:
        game.wait(0.5)
        return None
    game.walk_bearing(best_yaw, seconds=seconds)
    return best_yaw


def _find_and_open_chest(game, ctx):
    """Explore until a chest is SIGHTED, then open it.

    v1 turned in place and gave up. In room 0 that fails honestly and
    uselessly: the chest sits ~625 units off with geometry in the way, so
    no amount of pivoting will ever sight it. A player who has been told
    there is a chest walks around until they can see it — the knowledge
    that one exists is fair (AJ can see it), the LOCATION has to be
    earned by looking.

    Deliberately not "walk to the chest's census coordinates": those are
    available through game.actors() and using them would be exactly the
    X-ray this whole flight has been closing.
    """
    came_from = None
    for _ in range(5):
        if _any_sighted(game, ACTOR_EN_BOX) or _look_around_for(game, ACTOR_EN_BOX):
            return _approach_and_open(game)
        heading = _walk_open_leg(game, came_from)
        if heading is not None:
            came_from = (heading + 0x8000) & 0xFFFF
    raise BehaviorAbort("explored five legs, never sighted a chest")


def _open_chest(game, ctx):
    """Walk to a sighted chest and press A until a message box appears.

    Approach cannot reuse _go_to: that body treats "stopped closing" as a
    stall and aborts, but bumping into a chest is exactly how a correct
    approach ENDS. So this one walks on its own terms and lets contact be
    success.

    It stops at the message box rather than reading it. Dialogue is the
    mind's business (SURFACE.md gives it dialogue_advance and the
    oot://dialogue resource); a 20 Hz body that mashed A through a
    get-item text would be the hands making a decision the head should
    make — and would discard the one thing the chest is for, which is
    finding out what was inside.
    """
    if not _any_sighted(game, ACTOR_EN_BOX):
        if not _look_around_for(game, ACTOR_EN_BOX):
            raise BehaviorAbort("swept a full circle, no chest in sight")
    _approach_and_open(game)


#: Above this much vertical separation the target is on ANOTHER LEVEL and
#: walking at it is meaningless. Link's own step-up limit is well under
#: this; a chest +360 up is three of him.
#: 140, not 80: from the top of the vine wall the chest reads +80, which
#: is a STEP (OoT's own ledge-grab threshold is 79) rather than a storey.
#: The guard exists to catch "+360, three floors up", not to refuse a
#: kerb.
SAME_LEVEL_ABOVE = 140.0


def _approach_and_open(game: Game) -> None:
    """Close on an already-sighted chest and open it.

    Refuses outright when the chest is on another level. Field evidence
    (fourth flight): Link climbed the ladder, sighted the chest, walked
    at it, FELL BACK OFF THE LEDGE, and then stood 104 units from a chest
    +360 overhead pressing A ten times. Every step of that was reported
    as progress, because dist_xz is a projection onto the floor plane and
    says nothing about whether the target is reachable — the harness
    backlog's oldest open item (probe_room.py's "dist" column, raised
    2026-07-30) in behavior form.

    Nothing here can fix the underlying gap: there is no sense for
    ledges, drops, or having just fallen, so a body cannot know it lost
    the height it gained. Refusing loudly is the honest floor.
    """
    seen = _Seen()
    deadline = time.monotonic() + 20.0
    dist = None
    while time.monotonic() < deadline:
        targets = seen.update(game, ACTOR_EN_BOX)
        if not targets:
            raise BehaviorAbort("lost sight of the chest")
        dist = targets[0]["dist_xz"]
        above = -float(targets[0].get("dist_y", 0.0))
        if abs(above) > SAME_LEVEL_ABOVE:
            raise BehaviorAbort(
                f"chest is {above:+.0f} above at {dist:.0f} out — another "
                f"level, not a walk. Needs a climb that ENDS beside it; "
                f"no ledge sense exists to keep one.")
        if dist <= CHEST_OPEN_DIST:
            break
        game.walk_toward(targets[0], seconds=0.25)
        game.wait(TICK)

    for _ in range(CHEST_TRIES):
        if game.state().get("msg_mode", 0) != 0:
            return                      # open; the mind takes it from here
        targets = seen.update(game, ACTOR_EN_BOX)
        if targets:
            # Re-aim every attempt: the prompt needs Link FACING the chest,
            # and a nudge both turns him and closes any last few units.
            game.walk_toward(targets[0], seconds=0.12)
        game.press("A", frames=3)
        game.wait(CHEST_SETTLE_S)
    if game.state().get("msg_mode", 0) != 0:
        return
    raise BehaviorAbort(
        f"pressed A {CHEST_TRIES}x at {dist:.0f} units, no message box "
        f"(wrong side of the chest, or not close enough)")


CHARGE_S = 50.0
CHARGE_STALL_S = 2.5
CHARGE_REACH = 115.0      # observed contact distance against the chest
CHARGE_ABOVE_OK = 130.0


def _charge_chest(game, ctx):
    """Go to the chest already seen, mounting ledges that block the way.

    NO look-around phase. Every survey in this repo turns by walking, and
    up here that costs height: the ledge-safe look still dropped Link 68
    units between two readings (+80 -> +148). When the target is a
    landmark you have already seen, looking again is pure downside.

    Sight honesty: the sensorium narrated *first sighting of a
    treasure_chest* earlier this session, so this chest is in the
    server's scene-level Sightings and a player would remember roughly
    where it is. `_Seen` is per-run and had simply forgotten — stricter
    than the sensorium itself, which is not honesty, just amnesia.
    Walking toward a remembered landmark is what a player does.

    Ledges: walking into one stalls. On a stall with the chest still
    above, press A — on the GROUND facing a ledge that is the grab/mount
    (yDistToLedge >= 79), not the wall-release that A means while
    already climbing (climb.py, fact 2). Then hold stick-up if the grab
    turned into a climb.
    """
    deadline = time.monotonic() + CHARGE_S
    best = None
    stall_until = time.monotonic() + CHARGE_STALL_S
    while time.monotonic() < deadline:
        targets = game.actors(actor_id=ACTOR_EN_BOX)
        if not targets:
            raise BehaviorAbort("the chest is not in the census any more")
        t = targets[0]
        dist = float(t.get("dist_xz", 1e9))
        above = -float(t.get("dist_y", 0.0))
        if dist <= CHARGE_REACH and abs(above) <= CHARGE_ABOVE_OK:
            break
        if best is None or dist < best - 20.0:
            best, stall_until = dist, time.monotonic() + CHARGE_STALL_S
        elif time.monotonic() > stall_until:
            # Blocked. If the prize is above us, this is a ledge: mount it.
            game.press("A", frames=3)
            game.wait(0.5)
            climb_deadline = time.monotonic() + 6.0
            while (game.climbing() or game.mounting_ledge()) \
                    and time.monotonic() < climb_deadline:
                game.pad(stick=(0, 80))     # raw stick: the climb is not
                game.wait(0.2)              # camera-relative
            game.pad_clear()
            best, stall_until = None, time.monotonic() + CHARGE_STALL_S
            continue
        game.walk_toward(t, seconds=0.25)
        game.wait(TICK)

    for _ in range(CHEST_TRIES):
        if game.state().get("msg_mode", 0) != 0:
            return
        targets = game.actors(actor_id=ACTOR_EN_BOX)
        if targets:
            game.walk_toward(targets[0], seconds=0.12)
        game.press("A", frames=3)
        game.wait(CHEST_SETTLE_S)
    if game.state().get("msg_mode", 0) != 0:
        return
    t = (game.actors(actor_id=ACTOR_EN_BOX) or [{}])[0]
    raise BehaviorAbort(
        f"reached {t.get('dist_xz', -1):.0f} out, "
        f"{-float(t.get('dist_y', 0.0)):+.0f} above; A did not open it")


def _chest_opened(game, initial, events):
    """Success = a message box is on screen.

    The engine's own positive evidence that the chest gave something up.
    Deliberately not an inventory check: the Deku Tree's chest carries a
    map, and quest items move no counter this sensorium can see.
    """
    return game.state().get("msg_mode", 0) != 0


def _item_gone(game, initial, events):
    """Success = the thing we walked to is no longer on the ground.

    A collectible vanishes when taken, so its ABSENCE is the kill-event
    equivalent here — the dojo's postmortem rule (require the engine's own
    positive evidence, never 'the body returned') applied to pickups.
    Counting hearts would be wrong: at full health a recovery heart is
    consumed with no counter to move.
    """
    before = len(initial.get("actors") or [])
    now = len([a for a in game.actors(actor_id=ACTOR_EN_ITEM00)])
    was = len([a for a in (initial.get("actors") or [])
               if a.get("id") == ACTOR_EN_ITEM00])
    del before
    return now < was


BEHAVIORS = {
    "approach_baba_v2": Behavior(
        name="approach_baba", version=2,
        description="v1 + sight honesty: walk only at babas this run has "
                    "actually seen, with per-run object permanence",
        body=_approach_baba, success=_baba_in_engage_range, timeout_s=25.0,
        grade="UNGRADED (field-authored, fourth flight). v1's straight-line "
              "approach and honest stall-abort, restricted to sighted "
              "targets after the census cap lifted.",
        notes=["v1 became unfair the moment the wire carried the whole room: "
               "it would walk at babas through walls."]),
    "collect_item_v1": Behavior(
        name="collect_item", version=1,
        description="walk into the nearest sighted ground drop (En_Item00)",
        body=_collect_item, success=_item_gone, timeout_s=30.0,
        grade="RETIRED after one field trial (fourth flight): aborted "
              "standing 136 units from a drop because the previous sweep "
              "left Link facing away. Sight honesty means don't walk at "
              "the unseen, not don't look.",
        notes=["Superseded by v2, which looks around first."]),
    "collect_item_v2": Behavior(
        name="collect_item", version=2,
        description="look around if no drop is in sight, then walk into "
                    "the nearest one seen",
        body=_collect_item_v2, success=_item_gone, timeout_s=45.0,
        grade="UNGRADED (field-authored, fourth flight). Success is the "
              "drop's disappearance, not a counter — a recovery heart at "
              "full health moves no counter."),
    "open_chest_v1": Behavior(
        name="open_chest", version=1,
        description="look for a chest, walk to it, press A until the "
                    "get-item message appears; leaves the text to the mind",
        body=_open_chest, success=_chest_opened, timeout_s=45.0,
        grade="RETIRED after one field trial (fourth flight): the chest in "
              "room 0 is ~625 units away behind geometry, so turning in "
              "place can never sight it. Honest, and useless.",
        notes=["Superseded by find_and_open_chest_v1, which walks."]),
    "charge_chest_v1": Behavior(
        name="charge_chest", version=1,
        description="walk straight to the already-seen chest, mounting "
                    "ledges that block the way, then press A to open",
        body=_charge_chest, success=_chest_opened, timeout_s=75.0,
        grade="UNGRADED (field-authored, fourth flight). No looking: on "
              "uneven high ground every survey in this repo costs height, "
              "and the target is a remembered landmark."),
    "find_and_open_chest_v1": Behavior(
        name="find_and_open_chest", version=1,
        description="explore open bearings, looking around at each stop, "
                    "until a chest is sighted — then approach and open it",
        body=_find_and_open_chest, success=_chest_opened, timeout_s=140.0,
        grade="UNGRADED (field-authored, fourth flight). Five legs of "
              "look-then-walk; no map, no memory of where it has been "
              "beyond not doubling straight back."),
}
