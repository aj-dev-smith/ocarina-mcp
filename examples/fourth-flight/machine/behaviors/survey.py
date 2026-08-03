"""survey_room: turn in place and LOOK — the organ 0.5.0 made necessary.

Authored live, fourth flight 2026-08-02 (the first MCP-direct session,
Claude Code holding the instrument end-to-end).

The gap it fills: under the view-locked census an enemy the player has
not sighted does not exist to ANY layer — digest, machine guards, or a
body's raw game.nearest(). Second light's clearing loop (hunt -> seek ->
hunt) therefore starves after the first kill if Link ends it facing a
wall: approach_baba_v1 returns "no baba" in 0.1s and nothing in the
machine ever turns the view. Witnessed live this flight — one kill,
then stand_watch forever with two babas at Link's back. A sighted
player pays nothing to fix this; they look around between swings. This
body is that looking, and nothing else.

Mechanics: 8 pivot-pulses at 45-degree increments walking a tight
circle (short, low magnitude — Link turns more than he travels), each
followed by an untargeted Z press (the attention predicate tests the
CAMERA frustum, and the follow-cam lags a pivot by seconds; untargeted
Z snaps it behind Link now) and a beat for the attention pass to run.
Early-out the moment a deku baba enters the census: the census is
view-locked, so mere presence IS the sighting.

KNOWN SHARP EDGE (accepted for the field trial, mind watching): if a
sighted baba is unreachable (geometry stalls approach_baba_v1), the
machine orbits survey -> seek -> survey hot, because survey early-outs
on a baba that never leaves the census. The mind sees the journal churn
and intervenes; a standing machine fix (stall counter / cooldown) is
the follow-up if the trial hits it.
"""

from ocarina.behavior import Behavior
from ocarina.protocol import ACTOR_EN_DEKUBABA

_STEPS = 8            # 45 degrees each: one full circle
_STEP_YAW = 0x2000
_PULSE_S = 0.30       # long enough to commit the pivot, short enough to barely travel
_MAGNITUDE = 45       # slow walk; the point is facing, not displacement
_SETTLE_S = 0.5       # camera snap + attention pass before reading the census


def _baba_sighted(game) -> bool:
    """A deku baba the player can see RIGHT NOW.

    v1 asked "is a baba in the census", which was equivalent while the
    wire truncated at ~310 units — presence implied nearness implied
    sight, near enough. The fourth flight lifted the cap to the whole
    room (30/30 actors out to 1528 units), and that made the old test
    trivially true from anywhere in room 0: the looking organ would
    early-out on step 1 and never look. Ask the sight bit itself.
    """
    return any(a.get("sighted") for a in game.actors(actor_id=ACTOR_EN_DEKUBABA))


def _survey_body(game, ctx):
    base = game.camera_yaw()
    for step in range(1, _STEPS + 1):
        if _baba_sighted(game):
            game.pad_clear()
            return                    # sighted: stop looking, let the judge confirm
        yaw = (base + step * _STEP_YAW) & 0xFFFF
        game.walk_bearing(yaw, seconds=_PULSE_S, magnitude=_MAGNITUDE)
        game.press("Z")               # untargeted: camera snaps behind Link's new facing
        game.wait(_SETTLE_S)
    game.pad_clear()


def _baba_in_census(game, initial, events):
    """Success = a deku baba is SIGHTED now. Present-tense positive
    evidence, and the same predicate the sensorium narrates on."""
    return _baba_sighted(game)


BEHAVIORS = {
    "survey_room_v1": Behavior(
        name="survey_room", version=1,
        description="pivot a full circle in small pulses, Z-snapping the "
                    "camera each step; succeed when a deku baba enters the "
                    "view-locked census",
        body=_survey_body, success=_baba_in_census, timeout_s=20.0,
        grade="UNGRADED (field-authored, fourth flight). The looking organ "
              "the view-locked census requires; drift per full sweep "
              "unmeasured — observe the first runs.",
        notes=["Authored live 2026-08-02: first kill left Link facing a "
               "wall, remaining babas unsighted, clearing loop starved."]),
}
