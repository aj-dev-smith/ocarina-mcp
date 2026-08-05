"""First-light behaviors: boot from the title screen, then stand watch.

boot_from_title is the workshop's setup_encounter.boot_to_save as a
behavior body. SAFETY (ported argument): presses only A/START and NEVER
touches the stick or d-pad. In FileChoose_UpdateMainMenu A/START act on
buttonIndex, which only moves on stick/d-pad input, so the cursor cannot
reach Copy/Erase and an existing file goes straight to Open File. This
cannot start a new game over an existing save.

stand_watch holds no pad at all — the keyboard stays live for a human
while the sensorium narrates.
"""

from ocarina.behavior import Behavior


def _boot_body(game, ctx):
    presses = 0
    while not game.state().get("save_loaded") and presses < 80:
        game.press("START" if presses % 2 == 0 else "A", frames=4)
        presses += 1
        game.wait(0.6)


def _boot_success(game, initial, events):
    return bool(game.state().get("save_loaded"))


def _watch_body(game, ctx):
    for _ in range(12):
        game.state()
        game.wait(0.25)


BEHAVIORS = {
    "boot_from_title_v1": Behavior(
        name="boot_from_title", version=1,
        description="press A/START (never the stick) until the save file loads",
        body=_boot_body, success=_boot_success, timeout_s=90.0,
        grade="commissioning behavior; safe by construction, see docstring"),
    "stand_watch_v1": Behavior(
        name="stand_watch", version=1,
        description="hold no pad; observe for ~3s and return (loops via machine)",
        body=_watch_body,
        success=lambda game, initial, events: True, timeout_s=10.0,
        grade="commissioning behavior; leaves the keyboard live for a human"),
}
