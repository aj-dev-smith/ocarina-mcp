"""Wake-delivery test driver (2026-08-07, the channel-registration find).

Connects the ported fakegame to a LIVE ocarina server on 43384. The
runtime's identity check (0.11.0, docs/32 — it replaced the machine-side
gate this driver was first written against) refuses the fake save
against the repo's identity.json and fires a real identity wake —
freeze-confirmed, hold default, journaled. Harmless: the world parks
frozen in the refusal; the machine never gets to play the fake line.

Use it to verify channel delivery after starting the session with
    claude --dangerously-load-development-channels server:ocarina
Run `python3 tools/fakewake.py --delay 60`, let the session go idle,
and the wake should inject and start a turn on its own. If it doesn't,
the Monitor doorbell in CLAUDE.md ("Playing it directly") is the
fallback. Afterward: kill this process (or wait out the 10-minute
watchdog), then force_state("boot") + resume() to reset the machine.

Detach it (nohup) if the session must not see the process finish.
"""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.fakegame import FakeGame


def main() -> None:
    delay = 0.0
    if "--delay" in sys.argv:
        delay = float(sys.argv[sys.argv.index("--delay") + 1])
    if delay:
        time.sleep(delay)
    threading.Timer(600, lambda: os._exit(0)).start()
    try:
        FakeGame().run()
    except Exception as e:
        print(f"fakewake: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
