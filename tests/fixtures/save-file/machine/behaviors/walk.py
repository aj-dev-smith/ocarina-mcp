"""Test-fixture behaviors: bodies short enough for unit tests, shaped like
real workshop bodies (blocking, touch the game every tick)."""

from ocarina.behavior import Behavior


def _walk_body(game, ctx):
    for _ in range(2):
        game.state()
        game.wait(0.02)


def _walk_success(game, initial, events):
    return True


def _kill_body(game, ctx):
    game.state()
    game.wait(0.02)


def _kill_success(game, initial, events):
    return any(e.get("event") == "enemy_defeat" for e in events)


BEHAVIORS = {
    "walk_about_v1": Behavior(
        name="walk_about", version=1,
        description="fixture: wander briefly",
        body=_walk_body, success=_walk_success, timeout_s=5.0,
        grade="fixture behavior; always succeeds"),
    "kill_baba_v1": Behavior(
        name="kill_baba", version=1,
        description="fixture: pretend to fight",
        body=_kill_body, success=_kill_success, timeout_s=5.0,
        grade="fixture behavior; succeeds iff an enemy_defeat event arrived"),
}
