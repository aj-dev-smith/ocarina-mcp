"""The stdio MCP server: SURFACE.md's tool/resource contract on the wire.

Stdlib JSON-RPC 2.0 over stdio (MCP framing: one JSON message per line).
The core is transport-free (`ServerCore.handle(msg)`) so the whole surface
is testable without pipes; `main()` wires stdin/stdout, the Sail link, and
the 20 Hz runtime thread.

Wake delivery is a plain blocking tool call as of 0.10.0 (SURFACE.md
"The wake"; dojo docs/31): `resume` unfreezes and blocks, `await_wake`
listens without resuming, and the wake pack comes back as that call's
result. Those two verbs run on their own thread (`serve` dispatches
them there) so a blocked wake-wait cannot starve status/ping/cancel —
JSON-RPC answers by id, so out-of-order responses are legal. MCP
cancellation (`notifications/cancelled`) severs the block and writes no
response; the machine plays on and the next wake parks frozen.

Wakes ALSO ride MCP channels (verified 2026-07-31, demoted to optional
2026-08-07): the initialize response declares
`experimental: {"claude/channel": {}}` and wake packs go out as
`notifications/claude/channel` — `content` lands as the body of a
`<channel source="ocarina">` block, `meta` keys become tag attributes.
A nicety for flag-loaded Claude Code sessions; scored play blocks.

Tools not yet implemented return a clean isError result saying exactly
what instrument work they wait on — the surface shape is the blessed
contract, and an honest "not built" beats a missing verb (which would
read as "not part of the design", untrue) or a quiet failure (docs/08).
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import threading
import time
from collections import deque
from functools import partial
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import MACHINE_FORMAT_VERSION, OCARINA_VERSION, dev, jev, screenshot, senses
from .brainviz import Brainviz
from .events import EventLog
from .game import Game
from .link import GameLink, LinkError
from .place import PlaceSense
from .protocol import ACTOR_EN_GIRLA, DEFAULT_PORT
from .runtime import MachineRuntime

PROTOCOL_VERSION = "2025-06-18"

#: One stick nudge, the shape dialogue_choose established live: hold, then
#: neutral, so the game's held-stick latch (and En_Ossan's stickAccumX)
#: re-arms before the next one. LIVE-TUNED CONSTANTS — the shop's browse
#: states want |stickAccumX| > 500, which no test can price.
_NUDGE_HOLD_S = 0.15
_NUDGE_GAP_S = 0.1

#: The shop, in text ids (z_en_ossan.c). Mechanics knowledge, like the
#: catalog: these are how the server READS the shop's state machine off
#: the wire instead of assuming it — every phase of buy() verifies which
#: box is actually on screen before pressing anything.
SHOP_FACING_BOX = 0x83          # facing the shopkeeper, shelves either side
SHOP_QUICK_BUY_BOXES = (0x84, 0x9A)   # bought over the counter, no fanfare
SHOP_NEED_RUPEES_BOX = 0x85     # CANBUY_RESULT_NEED_RUPEES
SHOP_CANT_GET_BOX = 0x86        # CANBUY_RESULT_CANT_GET_NOW
SHOP_CONTINUE_BOX = 0x6B        # "Do you want to buy anything else?"

_BUY_MAX_NUDGES = 20            # eight slots, two shelves, slack for a turn
_BUY_BOX_TIMEOUT_S = 2.0
_BUY_POLL_S = 0.1
_BUY_OUTCOME_TIMEOUT_S = 15.0   # the fanfare is long; a stuck modal is worse
_BUY_SELECT_TRIES = 3

#: dialogue_choose's own clocks, on the same typewriter as the shop's:
#: how long a box gets to finish typing, and how long the choice box gets
#: to let go of the screen after the confirming A (ninth flight: the
#: choice "took" but needed a follow-up advance; tenth flight saw the
#: swallowed press twice more).
_CHOOSE_BOX_TIMEOUT_S = 2.0
_CHOOSE_COMMIT_TIMEOUT_S = 1.5

#: A box still "opening" or "displaying" is typing itself out, and the shop
#: reads nothing until it stops: En_Ossan takes the stick and the A in
#: TEXT_STATE_EVENT only (z_en_ossan.c:1240,1313), and an A inside that
#: window just fast-forwards the typewriter. That is what ate the ninth
#: flight's first select-A (docs/28).
_SETTLED_BOX_STATES = ("done", "awaiting_advance", "choice")


def _quote_box(msg) -> str:
    """The open box, verbatim, for a refusal to name what it is looking
    at (traverse's discipline: quote the blocker, don't categorize it)."""
    msg = msg or {}
    if not msg:
        return "no text box is open"
    text = msg.get("text")
    where = f"box 0x{msg.get('text_id', 0):02X}"
    return f'{where} says: "{text}"' if text else f"{where} carries no text"

INSTRUCTIONS = """\
ocarina is the instrument you play Ocarina of Time through. You act by
putting a hierarchical state machine in a state, never by pressing
buttons — the machine is source in this save-file repo (machine/), and
reload_machine() validates and hot-swaps it. One call is one act of
living: while you hold a FROZEN world you read the pack, inspect
resources, edit the machine if needed, then call resume() — which
unfreezes and BLOCKS, returning the next wake pack as its result. The
world only runs while someone is listening. If a resume() was cut
short, re-attach with await_wake() (never resume() again — it re-runs
the current node's body). Every wake has a declared default that fires
if you never answer, so the world will not wait forever."""


def _tool(name, description, properties=None, required=None):
    return {"name": name, "description": description,
            "inputSchema": {"type": "object",
                            "properties": properties or {},
                            "required": required or []}}


TOOLS = [
    _tool("status", "Server version, game connection, machine loaded/hash, current node."),
    _tool("reload_machine", "Validate + hot-swap the machine from repo source; returns diagnostics."),
    _tool("force_state", "Jump the machine to a node now.",
          {"node": {"type": "string", "description": "Target node name (bare, machine-wide unique)."}},
          ["node"]),
    _tool("set_directive", "Set the standing intent (feeds wake packs, HUD, telemetry).",
          {"text": {"type": "string"}}, ["text"]),
    _tool("resume", "Unfreeze the game and BLOCK until the next wake, which "
                    "is this call's result. One call is one act of living: "
                    "the world only runs while someone is listening.",
          {"max_sleep": {"type": "number", "description": "Seconds between heartbeat wakes (stored; heartbeat wake is machine content)."},
           "max_block_s": {"type": "number", "description": "Cap the block; on expiry returns {no_wake: true, elapsed_s} with the world STILL RUNNING — re-arm with await_wake(), never resume()."}}),
    _tool("await_wake", "Listen for the next wake WITHOUT resuming (no side "
                        "effect on machine or game): returns a parked wake "
                        "at once, blocks while the world runs, errors if a "
                        "delivered wake is unanswered. The re-attach verb "
                        "after a severed resume().",
          {"max_block_s": {"type": "number", "description": "Cap the block; on expiry returns {no_wake: true, elapsed_s}."}}),
    _tool("escalate", "Escalate up the ladder (ultimately to the human; journaled).",
          {"reason": {"type": "string"}}, ["reason"]),
    _tool("scan", "Collision fan around Link — the geometry sense.",
          {"rays": {"type": "integer"}, "length": {"type": "number"},
           "height": {"type": "number"}, "from_yaw": {"type": "integer"},
           "span": {"type": "integer"}}),
    _tool("dialogue_advance", "Advance the open text box (the server does the button mechanics)."),
    _tool("dialogue_choose", "Pick a dialogue option by index.",
          {"option": {"type": "integer"}}, ["option"]),
    _tool("create_file", "File select: the naming ceremony. Names the save file (= this repo).",
          {"name": {"type": "string"}}, ["name"]),
    _tool("continue_game", "Death screen: continue."),
    _tool("save_and_quit", "Save screen: save and quit."),
    _tool("save_game", "Game-native save (benchmark-legal: it's a menu function)."),
    _tool("equip", "Pause subscreens: equip an item.", {"item": {"type": "string"}}, ["item"]),
    _tool("use_item", "Use an item.", {"item": {"type": "string"}}, ["item"]),
    _tool("buy", "Shops: buy an item. Owns the whole purchase — shelf, "
                 "confirm, the get-item box, and the shopkeeper's "
                 "continue-shopping question.",
          {"item": {"type": "string"},
           "keep_shopping": {"type": "boolean",
                             "description": "Answer the continue-shopping "
                                            "prompt with 'yes' and stay at "
                                            "the counter (default: leave)."}},
          ["item"]),
    _tool("play_song", "The ocarina interface: choosing the song is the game; note entry is UI mechanics.",
          {"name": {"type": "string"}}, ["name"]),
    _tool("screenshot", "Vision on demand; a debugging sense, never a stream. "
                        "Returns the game window's final composited frame as "
                        "a PNG image block — the debug overlay's labels "
                        "included, so it shows ocarina's beliefs ON the "
                        "world's truth.",
          {"max_width": {"type": "integer",
                         "description": "Cap the returned width in pixels "
                                        "(the instrument box-averages down; "
                                        "0 = native). Default 640."}}),
]

#: Tools that exist on the blessed surface but wait on instrument work.
#: Each maps to what it needs — an honest error beats a silent stub.
#: (0.8.0 graduated dialogue_choose/save_game/use_item; 0.9.0 graduated
#: equip and buy; screenshot graduated on the 2026-08-07 AgentLink patch.
#: What is left here waits on real UI substrate.)
NOT_YET = {
    "create_file": "file-select UI navigation not built yet",
    "continue_game": "death-screen UI navigation not built yet",
    "save_and_quit": "save-screen UI navigation not built yet",
    "play_song": "ocarina UI note entry not built yet",
}

RESOURCES = [
    {"uri": "oot://state", "name": "state",
     "description": "The curated game-state digest: what a player sees and "
                    "(gameplay-relevant) hears at this instant.",
     "mimeType": "application/json"},
    {"uri": "oot://events", "name": "events",
     "description": "The event log, queryable: oot://events?last=N&category=C&kind=K&since_t=T.",
     "mimeType": "application/json"},
    {"uri": "oot://dialogue", "name": "dialogue",
     "description": "Current/recent text verbatim, choices as data.",
     "mimeType": "application/json"},
    {"uri": "oot://menu/items", "name": "menu/items",
     "description": "The items pause subscreen as a document.",
     "mimeType": "application/json"},
    {"uri": "oot://menu/equipment", "name": "menu/equipment",
     "description": "The equipment pause subscreen.", "mimeType": "application/json"},
    {"uri": "oot://menu/map", "name": "menu/map",
     "description": "The map pause subscreen.", "mimeType": "application/json"},
    {"uri": "oot://menu/quest", "name": "menu/quest",
     "description": "The quest pause subscreen (songs learned live here).",
     "mimeType": "application/json"},
    {"uri": "oot://place", "name": "place",
     "description": "The place sense (docs/25; discovery grain docs/34): "
                    "this scene's region graph as judgments over stable "
                    "names — regions, climb columns, unverified candidates, "
                    "where you are. Overworld scenes reveal whole at entry; "
                    "dungeons present only what presence has earned, with "
                    "frontier legs 'destination unknown'. Route planning is "
                    "yours; bodies traverse one named edge at a time.",
     "mimeType": "application/json"},
    {"uri": "oot://machine", "name": "machine",
     "description": "Declared vs LIVE machine, two columns (the conjunction discipline).",
     "mimeType": "application/json"},
    {"uri": "oot://journal/mechanical", "name": "journal/mechanical",
     "description": "The persisted event timeline.", "mimeType": "application/json"},
]

_NOT_YET_RESOURCES = {
    "oot://menu/map": "map-subscreen substrate not on the wire yet",
    "oot://menu/quest": "quest-subscreen substrate not on the wire yet",
}


class RequestCancelled(Exception):
    """The client cancelled a blocked request. MCP says a cancelled
    request gets no response, so `handle` returns None for it."""


#: The verbs that BLOCK on the next wake (0.10.0). `serve` runs them on
#: their own thread; everything else stays on the read loop.
BLOCKING_TOOLS = ("resume", "await_wake")


class ServerCore:
    """The MCP surface, transport-free. `notify` is called with outbound
    notifications (the channel push); main() points it at stdout."""

    def __init__(self, game: Game, runtime: MachineRuntime, log: EventLog,
                 dev_tools: "dev.DevTools | None" = None):
        self.game = game
        self.runtime = runtime
        self.log = log
        #: The dev harness (0.12.0, docs/33), or None. None is the
        #: default surface and it must stay byte-identical to a server
        #: that has never heard of dev mode: the verbs are not listed,
        #: not stubbed, and not dispatchable.
        self.dev = dev_tools
        self.notify = lambda method, params: None
        # Blocked calls by request id, so notifications/cancelled can reach
        # the awaiter. `_cancelled` is the race the other way: a
        # cancellation that arrives before its request armed.
        self._inflight: dict = {}
        self._cancelled: deque = deque(maxlen=64)
        self._inflight_lock = threading.Lock()
        runtime.wake_push = self._push_pack

    # -- the channel ---------------------------------------------------------

    def _push_pack(self, pack: dict) -> None:
        if "escalation" in pack:
            content = (f"ESCALATION: {pack['escalation']}\n"
                       f"node: {pack.get('node')}\n"
                       f"state: {json.dumps(pack.get('state', {}))}")
            meta = {"kind": "escalation"}
        else:
            lines = [f"WAKE: {pack['reason']}",
                     f"transition: {pack['transition']} · node: {pack['node']} · "
                     f"game {'FROZEN' if pack.get('frozen') else 'RUNNING (freeze failed)'}"]
            if pack.get("directive"):
                lines.append(f"directive: {pack['directive']}")
            lines.append(f"trigger: {json.dumps(pack.get('trigger', {}))}")
            lines.append(f"state: {json.dumps(pack.get('state', {}))}")
            lines.extend(senses.interval_lines(pack.get("interval") or {}))
            lines.append("recent events:")
            for ev in pack.get("events", []):
                lines.append("  " + json.dumps(ev))
            lines.append("Think in stopped time; act via the tools; resume() when done.")
            content = "\n".join(lines)
            meta = {"kind": "wake", "transition": pack["transition"],
                    "node": str(pack.get("node"))}
        self.notify("notifications/claude/channel",
                    {"content": content, "meta": meta})

    # -- JSON-RPC ------------------------------------------------------------

    def handle(self, msg: dict):
        """One inbound message -> response dict, or None for notifications."""
        method = msg.get("method")
        msg_id = msg.get("id")
        if method is None:
            return None
        try:
            if method == "initialize":
                result = self._initialize(msg.get("params") or {})
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.tools()}
            elif method == "notifications/cancelled":
                self._cancel((msg.get("params") or {}).get("requestId"))
                return None
            elif method == "tools/call":
                result = self._call_tool(msg.get("params") or {}, msg_id)
            elif method == "resources/list":
                result = {"resources": RESOURCES}
            elif method == "resources/templates/list":
                result = {"resourceTemplates": []}
            elif method == "resources/read":
                result = self._read_resource(msg.get("params") or {})
            elif msg_id is None:
                return None    # unknown notification: ignore
            else:
                return _rpc_error(msg_id, -32601, f"method not found: {method}")
        except RequestCancelled:
            return None      # cancelled requests get no response (MCP)
        except Exception as e:
            if msg_id is None:
                return None
            return _rpc_error(msg_id, -32603, f"{type(e).__name__}: {e}")
        if msg_id is None:
            return None
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def _initialize(self, params: dict) -> dict:
        return {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
            "capabilities": {
                "tools": {},
                "resources": {},
                "experimental": {"claude/channel": {}},
            },
            "serverInfo": {"name": "ocarina", "version": OCARINA_VERSION},
            "instructions": INSTRUCTIONS,
        }

    # -- tools ---------------------------------------------------------------

    def tools(self) -> list:
        """The advertised surface. Without `--dev-tools` this is exactly
        the blessed list — the dev verbs are ABSENT, not stubbed (rule
        8's NOT_YET pattern is for blessed-but-unbuilt surface, which
        dev tools are not: docs/33 ratified call 2)."""
        return TOOLS if self.dev is None else TOOLS + dev.TOOLS

    def _call_tool(self, params: dict, msg_id=None) -> dict:
        name = params.get("name")
        args = params.get("arguments") or {}
        if name in NOT_YET:
            return _tool_error(f"{name} is on the surface but not yet "
                               f"implemented in ocarina {OCARINA_VERSION}: "
                               f"{NOT_YET[name]}")
        if name in dev.TOOL_NAMES:
            if self.dev is None:
                # Absent means absent: a server without the flag does not
                # know this verb, and says so in the same words it uses
                # for a typo.
                return _tool_error(f"unknown tool {name!r}")
            # The mark lands BEFORE the op runs, so a call that fails —
            # or crashes the process — still leaves its trace in the
            # permanent record (docs/33 commitment 2).
            self.log.record(dev.cheat_event(name, args))
            handler = partial(self.dev.call, name)
        else:
            handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return _tool_error(f"unknown tool {name!r}")
        try:
            result = (handler(args, msg_id) if name in BLOCKING_TOOLS
                      else handler(args))
        except LinkError as e:
            return _tool_error(f"game link: {e}")
        if isinstance(result, dict) and result.get("ok") is False:
            # Context-legal, not context-mounted: wrong-screen (and
            # wrong-state) calls are clean tool errors.
            return _tool_error(result.get("error", json.dumps(result)))
        if isinstance(result, dict) and "_content" in result:
            # The one shape a JSON text block cannot carry: screenshot hands
            # back real pixels as an MCP image block. Every other tool goes
            # through _tool_ok, whose single JSON text block is the norm.
            return {"content": result["_content"], "isError": False}
        return _tool_ok(result)

    def _tool_status(self, args) -> dict:
        st = self.runtime.status()
        st.update({"ocarina_version": OCARINA_VERSION,
                   "machine_format_version": MACHINE_FORMAT_VERSION,
                   "repo": str(self.runtime.repo)})
        if self.dev is not None:
            # Only under the flag: the default surface is unchanged, and
            # the presence of this key IS the report (docs/33 commitment
            # 2 — scored play requires the flag off, and the journal and
            # this line both prove it).
            st["dev_mode"] = True
        return st

    def _tool_reload_machine(self, args) -> dict:
        return self.runtime.reload()

    def _tool_force_state(self, args) -> dict:
        return self.runtime.force_state(str(args.get("node", "")))

    def _tool_set_directive(self, args) -> dict:
        return self.runtime.set_directive(str(args.get("text", "")))

    def _tool_resume(self, args, msg_id=None) -> dict:
        max_sleep = args.get("max_sleep")
        return self._blocking(msg_id, lambda on_arm: self.runtime.resume_and_block(
            None if max_sleep is None else float(max_sleep),
            _opt_float(args.get("max_block_s")), on_arm=on_arm))

    def _tool_await_wake(self, args, msg_id=None) -> dict:
        return self._blocking(msg_id, lambda on_arm: self.runtime.await_wake(
            _opt_float(args.get("max_block_s")), on_arm=on_arm))

    def _blocking(self, msg_id, call) -> dict:
        """Run one of the blocking verbs with its awaiter registered under
        this request's id, so notifications/cancelled can sever it. A
        severed block returns None from the runtime: no answer to write."""
        try:
            result = call(self._register(msg_id))
        finally:
            self._forget(msg_id)
        if result is None:
            raise RequestCancelled()
        return result

    def _register(self, msg_id):
        # Lock order, one way only: nothing here calls the runtime while
        # holding `_inflight_lock` (the runtime calls US, under its own
        # lock, when it arms an awaiter).
        def arm(awaiter) -> None:
            with self._inflight_lock:
                beaten = msg_id in self._cancelled
                if beaten:
                    self._cancelled.remove(msg_id)
                elif msg_id is not None:
                    self._inflight[msg_id] = awaiter
            if beaten:
                # The cancellation beat the arming: sever on arrival
                # rather than block for a request nobody is waiting for.
                self.runtime.cancel_awaiter(awaiter)
        return arm

    def _forget(self, msg_id) -> None:
        with self._inflight_lock:
            self._inflight.pop(msg_id, None)

    def _cancel(self, request_id) -> None:
        """MCP cancellation: unblock cleanly and let the machine play on —
        it IS the autopilot (docs/31 ruling 2). The next wake parks frozen
        with its default armed, and await_wake() re-attaches to it."""
        with self._inflight_lock:
            awaiter = self._inflight.pop(request_id, None)
            if awaiter is None:
                self._cancelled.append(request_id)
                return
        self.runtime.cancel_awaiter(awaiter)

    def sever_all(self) -> None:
        """The client is gone (stdin closed): unblock every waiting call."""
        with self._inflight_lock:
            awaiters = list(self._inflight.values())
            self._inflight.clear()
        for awaiter in awaiters:
            self.runtime.cancel_awaiter(awaiter)

    def _tool_escalate(self, args) -> dict:
        return self.runtime.escalate(str(args.get("reason", "")))

    def _tool_scan(self, args) -> dict:
        if not self.game.link.connected:
            return {"ok": False, "error": "game not connected"}
        kw = {}
        for key in ("rays", "length", "height", "from_yaw", "span"):
            if args.get(key) is not None:
                kw[key] = args[key]
        return {"ok": True, "rays": self.game.scan(**kw)}

    def _tool_dialogue_advance(self, args) -> dict:
        # Context-legal, not context-mounted: wrong-screen calls return
        # clean errors (SURFACE.md, the UI principle).
        if not self.game.link.connected:
            return {"ok": False, "error": "game not connected"}
        if self.game.state().get("msg_mode", 0) == 0:
            return {"ok": False, "error": "no dialogue is open"}
        self.game.press("A", frames=3)
        return {"ok": True, "dialogue_open": self.game.state().get("msg_mode", 0) != 0}

    def _tool_dialogue_choose(self, args) -> dict:
        # The choice is made with a player's own inputs: nudge the stick
        # until the wire's LIVE cursor (message.choice_index) matches, then
        # A — verified off the wire, never a memory write (docs/27 call 6).
        if not self.game.link.connected:
            return {"ok": False, "error": "game not connected"}
        st = self.game.state()
        if st.get("msg_mode", 0) == 0:
            return {"ok": False, "error": "no dialogue is open"}
        if st.get("message") is None:
            return {"ok": False,
                    "error": "instrument predates the dialogue sense — "
                             "rebuild SoH with the 2026-08-04 AgentLink patch"}
        # Read the box only once it has settled: a nudge inside the
        # typewriter is eaten, and so is the A behind it (buy's phase 3-4
        # lesson, docs/28 — the same mechanic, the same clock).
        msg = self._settled_box(_CHOOSE_BOX_TIMEOUT_S)
        if msg is None:
            return {"ok": False,
                    "error": "the box never finished typing, so the cursor "
                             "nudge (and the A behind it) would only "
                             "fast-forward it — " + _quote_box(self._message())}
        if msg.get("state") != "choice":
            return {"ok": False,
                    "error": f"no choice is being offered "
                             f"(box state: {msg.get('state')}) — "
                             + _quote_box(msg)}
        choices = msg.get("choices") or []
        try:
            target = int(args.get("option"))
        except (TypeError, ValueError):
            return {"ok": False, "error": "option must be an integer index"}
        if not (0 <= target < max(len(choices), 1)):
            return {"ok": False,
                    "error": f"option {target} out of range "
                             f"(choices: {choices})"}
        cur = self._cursor_to(target, start=msg.get("choice_index", 0))
        if cur != target:
            return {"ok": False,
                    "error": f"cursor would not reach option {target} "
                             f"(sits at {cur}) — " + _quote_box(self._message())}
        text_id = msg.get("text_id")
        settled = self._settled_box(_CHOOSE_BOX_TIMEOUT_S)
        if settled is None or settled.get("state") != "choice":
            return {"ok": False,
                    "error": f"the choice box did not hold still for the A "
                             f"on option {target} — "
                             + _quote_box(self._message())}
        self.game.press("A", frames=3)
        # Verify the choice COMMITTED: the box has to close or be replaced.
        # A press that lands as the box re-issues itself is simply lost, and
        # the ninth flight's "ok" then needed a follow-up advance by hand.
        if not self._choice_committed(text_id, _CHOOSE_COMMIT_TIMEOUT_S):
            # Eaten. The box re-issues itself under a lost press, and that
            # sends its cursor home with it — so the retry re-verifies the
            # cursor before pressing, never just presses again.
            live = self._settled_box(_CHOOSE_BOX_TIMEOUT_S) or {}
            if (live.get("text_id") == text_id
                    and live.get("state") == "choice"):
                if self._cursor_to(target,
                                   start=live.get("choice_index", 0)) != target:
                    return {"ok": False,
                            "error": f"the cursor would not go back to option "
                                     f"{target} for the retry — "
                                     + _quote_box(self._message())}
                self.game.press("A", frames=3)
            if not self._choice_committed(text_id, _CHOOSE_COMMIT_TIMEOUT_S):
                return {"ok": False,
                        "error": f"option {target} was pressed twice and the "
                                 f"same choice box is still on screen — "
                                 + _quote_box(self._message())}
        label = choices[target] if target < len(choices) else None
        return {"ok": True, "chose": target, "label": label,
                "dialogue_open": self.game.state().get("msg_mode", 0) != 0}

    def _choice_committed(self, text_id, timeout: float) -> bool:
        """Did the choice box we just pressed A on let go? True once it is
        closed, replaced, or settled into some other state; False if that
        same choice box is still offering the same choice after `timeout`
        (the press was eaten — retry it)."""
        deadline = time.monotonic() + timeout
        while True:
            msg = self._message()
            if msg is None or msg.get("text_id") != text_id:
                return True
            state = msg.get("state")
            if state != "choice" and state in _SETTLED_BOX_STATES:
                return True
            if time.monotonic() >= deadline:
                return False
            self.game.wait(_BUY_POLL_S)

    def _cursor_to(self, target: int, start: int | None = None,
                   tries: int = 8) -> int:
        """Nudge the open box's choice cursor onto `target`; returns where
        the WIRE says it ended up (== target on success). Shared by
        dialogue_choose and buy's two choice boxes — one mechanic, so a
        fix to the nudge timing can never fix only half the surface."""
        cur = (self._message() or {}).get("choice_index", 0) \
            if start is None else start
        for _ in range(tries):
            if cur == target:
                break
            # Stick up moves the cursor up (index down), per the game's own
            # Message_HandleChoiceSelection; neutral between nudges so its
            # held-stick latch re-arms.
            self.game.pad(stick=(0, -127 if target > cur else 127))
            self.game.wait(_NUDGE_HOLD_S)
            self.game.pad_clear()
            self.game.wait(_NUDGE_GAP_S)
            cur = (self._message() or {}).get("choice_index", cur)
        return cur

    def _message(self) -> dict | None:
        """The wire's current `message` block, or None (no box open, or an
        instrument that predates the dialogue sense)."""
        return self.game.state().get("message")

    def _tool_equip(self, args) -> dict:
        # The equipment subscreen's own commit, its own gates (docs/28):
        # the mind names a piece, the server finds its row. Refusals land
        # BEFORE the op wherever the wire can already answer (traverse's
        # discipline); the game side still backstops every one of them.
        # The worn mask this writes is the exact predicate Mido reads.
        if not self.game.link.connected:
            return {"ok": False, "error": "game not connected"}
        name = str(args.get("item", ""))
        found = next(((t, row, pieces.index(name) + 1)
                      for t, row in enumerate(senses.EQUIP_TYPES)
                      for pieces in [senses.EQUIP_PIECES[row]]
                      if name in pieces), None)
        if found is None:
            rows = "; ".join(f"{row}: {', '.join(senses.EQUIP_PIECES[row])}"
                             for row in senses.EQUIP_TYPES)
            return {"ok": False,
                    "error": f"unknown gear {name!r} — the equipment "
                             f"subscreen's four rows are {rows}"}
        equip_type, row, value = found
        st = self.game.state()
        equips = st.get("equips")
        if equips is None or "worn" not in equips:
            return {"ok": False,
                    "error": "instrument predates the equipment sense — "
                             "rebuild SoH with the 2026-08-04 AgentLink patch"}
        owned = senses.equipment_view(equips)["owned"][row]
        if name not in owned:
            return {"ok": False,
                    "error": f"{name} is not owned — the {row} row holds "
                             f"{', '.join(owned) if owned else 'nothing'}"}
        result = self.game.equip_gear(equip_type, value)
        if not result.get("ok"):
            return result       # the game's own refusal, by name
        # Verify off the wire: the mask, not the op's word for it.
        after = self.game.state().get("equips") or {}
        worn = senses.equipment_view(after)["worn"]
        if worn.get(row) != name:
            return {"ok": False,
                    "error": f"equip did not take: worn shows "
                             f"{worn.get(row)!r} in the {row} row, "
                             f"not {name!r}"}
        if row == "sword" and after.get("b") == senses.ITEM_NONE:
            return {"ok": False,
                    "error": f"equip did not take: worn shows {name} but the "
                             f"B button is still empty (the sword row writes "
                             f"B — a sword worn with nothing on B is the "
                             f"half-commit, not a success)"}
        return {"ok": True, "equipped": name, "slot": row, "worn": worn}

    def _tool_buy(self, args) -> dict:
        """Buy one named item from the shop Link is standing at.

        The shop is a message-box state machine (En_Ossan), so this is
        dialogue_choose's mechanic generalized: nudge, then read the LIVE
        box off the wire and verify — every shelf-cursor move re-issues
        that slot's description box (z_en_ossan.c:1287,1360), which is
        what makes cursor position observable at all.

        The tool owns the WHOLE purchase. The rupees only leave the wallet
        on the A through the "you got it" box (buyEventFunc via
        TEXT_STATE_DONE, z_en_ossan.c:1739-1760), so returning at the
        fanfare would leave a half-commit behind a stuck modal. It ends
        with the shopkeeper's continue-shopping question answered.

        The catalog (senses.SHOP_CATALOG) is mechanics knowledge of the
        ITEM_IDS class — id tables for steering the game's own UI, ratified
        as such (docs/28 call 6). Its prices are the game's declared base
        prices; the ACTUAL cost is verified off the wire before this ever
        claims success, and a mismatch is returned by name rather than
        papered over.
        """
        if not self.game.link.connected:
            return {"ok": False, "error": "game not connected"}
        name = str(args.get("item", ""))
        row = senses.SHOP_CATALOG.get(name)
        if row is None:
            known = ", ".join(sorted(senses.SHOP_CATALOG))
            return {"ok": False,
                    "error": f"unknown shop item {name!r} (known: {known} — "
                             f"the catalog covers the Kokiri shop's shelves)"}
        si_param, price, desc_id, prompt_id = row
        keep_shopping = bool(args.get("keep_shopping", False))

        # -- 1. everything refusable before a single button is pressed ----
        st = self.game.state()
        on_shelf = any(a.get("id") == ACTOR_EN_GIRLA
                       and (a.get("params") or 0) & 0xFF == si_param
                       for a in st.get("actors") or [])
        if not on_shelf:
            return {"ok": False,
                    "error": f"{name} is not sold in this shop (no shelf item "
                             f"with that row is in the census — not stocked "
                             f"here, or sold out: a sold-out slot's actor "
                             f"carries SI_SOLD_OUT, not its own row)"}
        rupees_before = int(st.get("rupees", 0))
        if rupees_before < price:
            return {"ok": False,
                    "error": f"insufficient rupees (have {rupees_before}, "
                             f"need {price})"}
        if st.get("msg_mode", 0) != 0 and st.get("message") is None:
            return {"ok": False,
                    "error": "instrument predates the dialogue sense — "
                             "rebuild SoH with the 2026-08-04 AgentLink patch"}

        # -- 2. must already be talking to the shopkeeper -----------------
        # buy is a UI verb: walking up to the counter and pressing A is the
        # mind's (a behavior's) job, the same line use_item draws.
        if st.get("msg_mode", 0) == 0:
            return {"ok": False,
                    "error": "not talking to a shopkeeper — face the counter "
                             "and talk first"}
        msg = st.get("message") or {}
        shelf_ids = {entry[2] for entry in senses.SHOP_CATALOG.values()}
        if msg.get("text_id") not in shelf_ids | {SHOP_FACING_BOX}:
            # The hello box (or the shopkeeper's own greeting): advance it
            # once and wait for the shop's facing box.
            if self._settled_box(_BUY_BOX_TIMEOUT_S) is None:
                return {"ok": False,
                        "error": "the shopkeeper's box never finished "
                                 "typing, so an A would only fast-forward "
                                 "it — " + _quote_box(self._message())}
            self.game.press("A", frames=3)
            msg = self._await_box({SHOP_FACING_BOX}, _BUY_BOX_TIMEOUT_S)
            if msg is None:
                return {"ok": False,
                        "error": "the shop's item board never came up — "
                                 + _quote_box(self._message())}

        # -- 3. walk the shelves until the item's own box is on screen ----
        direction, on_shelves, turned = 1, False, False
        for _ in range(_BUY_MAX_NUDGES):
            # Read the box only once it has settled: a nudge during the
            # typewriter is eaten, and so is the A below.
            msg = self._settled_box(_BUY_BOX_TIMEOUT_S) or self._message() or {}
            text_id = msg.get("text_id")
            if text_id == desc_id:
                if msg.get("state") not in _SETTLED_BOX_STATES:
                    return {"ok": False,
                            "error": f"{name}'s description box never "
                                     f"finished typing, so the A that "
                                     f"selects the slot would only "
                                     f"fast-forward it — " + _quote_box(msg)}
                break
            if text_id != SHOP_FACING_BOX:
                on_shelves = True
            elif on_shelves and not turned:
                # Walked off the end of a shelf and back to the shopkeeper:
                # the other shelf is the only place left to look.
                direction, turned = -direction, True
            self.game.pad(stick=(127 * direction, 0))
            self.game.wait(_NUDGE_HOLD_S)
            self.game.pad_clear()
            self.game.wait(_NUDGE_GAP_S)
        else:
            return {"ok": False,
                    "error": f"never reached {name} on the shelves after "
                             f"{_BUY_MAX_NUDGES} cursor moves (sold out, or "
                             f"this slot is not stocked) — "
                             + _quote_box(self._message())}

        # -- 4. select the slot: the buy prompt must actually come up -----
        # Retried because landing the cursor re-issues the slot's own
        # description (z_en_ossan.c:1287): an A that arrives while that box
        # is typing is spent fast-forwarding it, and the shop never sees a
        # selection. The retry is what the field did by hand (docs/28).
        msg = None
        for _ in range(_BUY_SELECT_TRIES):
            self.game.press("A", frames=3)
            msg = self._await_box({prompt_id}, _BUY_BOX_TIMEOUT_S,
                                  state="choice")
            if msg is not None:
                break
            live = self._settled_box(_BUY_BOX_TIMEOUT_S) or {}
            if live.get("text_id") != desc_id:
                break       # another box answered: not a swallowed press
        if msg is None:
            return {"ok": False,
                    "error": "slot refused selection (sold out?) — "
                             + _quote_box(self._message())}

        # -- 5. confirm: "Buy" is option 0, and the cursor is verified ----
        if self._cursor_to(0, start=msg.get("choice_index", 0)) != 0:
            return {"ok": False,
                    "error": "the buy prompt's cursor would not move to "
                             "'Buy' — " + _quote_box(self._message())}
        self.game.press("A", frames=3)

        # -- 6. ride the outcome out, whichever of the five it is ---------
        outcome = self._buy_outcome(name, keep_shopping)
        if not outcome.get("ok"):
            return outcome

        # -- 7. the wallet is the proof --------------------------------
        rupees_after = int(self.game.state().get("rupees", 0))
        spent = rupees_before - rupees_after
        out = {"item": name, "price": price, "rupees_before": rupees_before,
               "rupees_after": rupees_after, "spent": spent,
               "path": outcome["path"], "kept_shopping": keep_shopping}
        if spent != price:
            out["ok"] = False
            out["error"] = (f"bought {name} but the wallet does not agree: "
                            f"{spent} rupees left it, the catalog says "
                            f"{price} (a discount, a price this table has "
                            f"wrong, or a purchase that never committed)")
            return out
        out["ok"] = True
        return out

    def _await_box(self, text_ids: set, timeout: float,
                   state: str | None = None) -> dict | None:
        """Poll for a box with one of `text_ids` (and optionally that box
        state). Returns the message block, or None on timeout."""
        deadline = time.monotonic() + timeout
        while True:
            msg = self._message() or {}
            if msg.get("text_id") in text_ids and (state is None
                                                   or msg.get("state") == state):
                return msg
            if time.monotonic() >= deadline:
                return None
            self.game.wait(_BUY_POLL_S)

    def _settled_box(self, timeout: float) -> dict | None:
        """Poll until the live box has stopped typing (see
        `_SETTLED_BOX_STATES`). Returns that box, or None on timeout —
        including when no box is open at all."""
        deadline = time.monotonic() + timeout
        while True:
            msg = self._message() or {}
            if msg.get("state") in _SETTLED_BOX_STATES:
                return msg
            if time.monotonic() >= deadline:
                return None
            self.game.wait(_BUY_POLL_S)

    def _buy_outcome(self, name: str, keep_shopping: bool) -> dict:
        """Watch the shop's answer to the confirmed purchase through to a
        settled state. Five endings (z_en_ossan.c:1419-1456): the two
        refusal boxes, the quick-buy box, and the fanfare, which is the
        only one that also has to be walked through the get-item box and
        the continue-shopping question."""
        deadline = time.monotonic() + _BUY_OUTCOME_TIMEOUT_S
        path = "fanfare"
        while time.monotonic() < deadline:
            msg = self._message() or {}
            text_id, box_state = msg.get("text_id"), msg.get("state")
            if text_id == SHOP_NEED_RUPEES_BOX:
                return {"ok": False,
                        "error": "the shopkeeper says you cannot afford it — "
                                 + _quote_box(msg)}
            if text_id == SHOP_CANT_GET_BOX:
                return {"ok": False,
                        "error": "cannot take this now (already owned? no "
                                 "room?) — " + _quote_box(msg)}
            if text_id in SHOP_QUICK_BUY_BOXES:
                # The over-the-counter purchase: the item is already given
                # and paid for; one A closes the box back to the shelf.
                self.game.press("A", frames=3)
                self.game.wait(_BUY_POLL_S)
                return {"ok": True, "path": "quick_buy"}
            if text_id == SHOP_CONTINUE_BOX and box_state == "choice":
                target = 0 if keep_shopping else 1
                if self._cursor_to(target,
                                   start=msg.get("choice_index", 0)) != target:
                    return {"ok": False,
                            "error": f"bought {name}, but the "
                                     f"continue-shopping cursor would not "
                                     f"reach option {target} — the box is "
                                     f"still open: " + _quote_box(msg)}
                self.game.press("A", frames=3)
                return {"ok": True, "path": path}
            if box_state == "done":
                # The "You got a ...!" box. THIS A is what commits the
                # rupee deduction (buyEventFunc), so it is not optional and
                # it is not the mind's to make — the tool owns the whole
                # sequence or leaves a half-commit behind a modal.
                self.game.press("A", frames=3)
            self.game.wait(_BUY_POLL_S)
        return {"ok": False,
                "error": f"the shop never settled after confirming {name} "
                         f"({_BUY_OUTCOME_TIMEOUT_S:.0f}s) — "
                         + _quote_box(self._message())}

    def _tool_screenshot(self, args) -> dict:
        # The one tool whose result is not JSON text. The instrument sends
        # raw RGBA8 (libultraship vendors no image encoder and this lane
        # adds no dependencies); the PNG is made here, stdlib.
        if not self.game.link.connected:
            return {"ok": False, "error": "game not connected"}
        max_width = args.get("max_width")
        shot = self.game.screenshot(
            None if max_width is None else int(max_width))
        if not shot.get("ok"):
            return shot
        captured_at = time.time()
        try:
            png = screenshot.encode_png(shot["rgba"], shot["width"], shot["height"])
        except ValueError as e:
            return {"ok": False, "error": f"could not encode the frame: {e}"}
        note = {"width": shot["width"], "height": shot["height"],
                "captured_at": captured_at,
                "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                 time.gmtime(captured_at)),
                "png_bytes": len(png)}
        # The boundary, always (0.6.0's flight lesson: a debug layer shows
        # what it did NOT give you). A downscaled frame says so by carrying
        # the native size it was reduced from.
        if (shot["full_width"], shot["full_height"]) != (shot["width"], shot["height"]):
            note["downscaled_from"] = f"{shot['full_width']}x{shot['full_height']}"
        note["includes_debug_overlay"] = True
        return {"ok": True, "_content": [
            {"type": "image",
             "data": base64.b64encode(png).decode("ascii"),
             "mimeType": "image/png"},
            {"type": "text", "text": json.dumps(note, indent=1)},
        ]}

    def _tool_save_game(self, args) -> dict:
        # Play_PerformSave behind the pause-legality gate, game-side; the
        # refusal (if any) comes back named. No silent success path exists:
        # "ok" here is the game's own verdict, not an assumption.
        if not self.game.link.connected:
            return {"ok": False, "error": "game not connected"}
        return self.game.save_game()

    _C_BUTTONS = (("C_LEFT", "c_left", 0), ("C_DOWN", "c_down", 1),
                  ("C_RIGHT", "c_right", 2))

    def _tool_use_item(self, args) -> dict:
        # Assignment is the item subscreen's own commit (game-side, its own
        # legality gates); use is a real C-button press; both verified off
        # the wire's equips/inventory blocks (docs/27 call 3: the mind names
        # the item, buttons are the server's mechanics).
        if not self.game.link.connected:
            return {"ok": False, "error": "game not connected"}
        name = str(args.get("item", ""))
        item_id = senses.ITEM_IDS.get(name)
        if item_id is None:
            known = ", ".join(sorted(senses.ITEM_IDS))
            return {"ok": False,
                    "error": f"unknown item {name!r} (known: {known} — the "
                             f"vocabulary grows as items are acquired)"}
        st = self.game.state()
        equips = st.get("equips")
        if equips is None:
            return {"ok": False,
                    "error": "instrument predates the equips sense — "
                             "rebuild SoH with the 2026-08-04 AgentLink patch"}
        button = next((b for b in self._C_BUTTONS
                       if equips.get(b[1]) == item_id), None)
        if button is None:
            # Not on a C button yet: assign it. Server picks the button —
            # first empty, else C-left (mechanics, not a choice).
            button = next((b for b in self._C_BUTTONS
                           if equips.get(b[1]) in (None, senses.ITEM_NONE)),
                          self._C_BUTTONS[0])
            assigned = self.game.assign_c(item_id, button[2])
            if not assigned.get("ok"):
                return assigned
            verify = (self.game.state().get("equips") or {}).get(button[1])
            if verify != item_id:
                return {"ok": False,
                        "error": f"assignment did not take: {button[1]} "
                                 f"holds {verify!r} after assign_c"}
        if not self.game.controllable():
            return {"ok": False,
                    "error": f"{name} is on {button[0]} but Link is not "
                             f"controllable (dialogue open or cutscene) — "
                             f"the press would be eaten"}
        before = self._ammo_for(st, item_id)
        self.game.press(button[0], frames=3)
        self.game.wait(0.6)
        after = self._ammo_for(self.game.state(), item_id)
        out = {"ok": True, "item": name, "button": button[0]}
        if before is not None:
            out["ammo_before"] = before
            out["ammo_after"] = after
        return out

    @staticmethod
    def _ammo_for(st: dict, item_id: int):
        """The ammo count backing `item_id`'s inventory slot, or None when
        the slot carries no meaningful ammo (senses.AMMO_SLOTS)."""
        inv = st.get("inventory") or {}
        items, ammo = inv.get("items") or [], inv.get("ammo") or []
        for slot, item in enumerate(items):
            if item == item_id:
                if slot in senses.AMMO_SLOTS and slot < len(ammo):
                    return ammo[slot]
                return None
        return None

    # -- resources -----------------------------------------------------------

    def _read_resource(self, params: dict) -> dict:
        uri = params.get("uri", "")
        parsed = urlparse(uri)
        base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
        if base in _NOT_YET_RESOURCES:
            body = {"not_yet": _NOT_YET_RESOURCES[base],
                    "ocarina_version": OCARINA_VERSION}
        elif base == "oot://state":
            if not self.game.link.connected:
                body = {"error": "game not connected"}
            else:
                st = self.game.state()
                body = self.runtime.digest_of(st)
        elif base == "oot://events":
            q = parse_qs(parsed.query)

            def one(key, cast, default=None):
                return cast(q[key][0]) if key in q else default
            body = self.log.tail(n=one("last", int, 50),
                                 category=one("category", str),
                                 kind=one("kind", str),
                                 since_t=one("since_t", int))
        elif base == "oot://dialogue":
            body = self._dialogue_view()
        elif base == "oot://menu/items":
            body = self._menu_items_view()
        elif base == "oot://menu/equipment":
            body = self._menu_equipment_view()
        elif base == "oot://place":
            body = self.runtime.place_view()
        elif base == "oot://machine":
            body = self.runtime.machine_view()
        elif base == "oot://journal/mechanical":
            body = self._journal_tail()
        else:
            raise ValueError(f"unknown resource {uri!r}")
        return {"contents": [{"uri": uri, "mimeType": "application/json",
                              "text": json.dumps(body, indent=1)}]}

    def _dialogue_view(self) -> dict:
        """oot://dialogue (docs/27): the current box verbatim, choices as
        data, plus the session's recent-texts ring — get-item boxes land
        in the ring even when a body advanced them blind."""
        if not self.game.link.connected:
            return {"error": "game not connected"}
        st = self.game.state()
        box_open = st.get("msg_mode", 0) != 0
        msg = st.get("message")
        body: dict = {"open": box_open}
        if box_open and msg is None:
            body["blind"] = ("instrument predates the dialogue sense — "
                             "rebuild SoH with the 2026-08-04 AgentLink patch")
        elif msg is not None:
            body["current"] = {k: msg[k] for k in
                               ("text", "state", "text_id", "choices",
                                "choice_index", "wide") if k in msg}
        body["recent"] = self.runtime.dialogue_recent()
        return body

    def _menu_items_view(self) -> dict:
        """oot://menu/items: the items subscreen as a document — held
        items by slot with meaningful ammo, and what sits on B/C."""
        if not self.game.link.connected:
            return {"error": "game not connected"}
        st = self.game.state()
        inv = st.get("inventory")
        if inv is None:
            return {"blind": "instrument predates the menu senses — "
                             "rebuild SoH with the 2026-08-04 AgentLink patch"}
        items, ammo = inv.get("items") or [], inv.get("ammo") or []
        held = []
        for slot, item in enumerate(items):
            if item == senses.ITEM_NONE:
                continue
            entry = {"slot": slot, "item": senses.item_name(item)}
            if slot in senses.AMMO_SLOTS and slot < len(ammo):
                entry["ammo"] = ammo[slot]
            held.append(entry)
        equips = st.get("equips") or {}
        buttons = {key: senses.item_name(equips[key])
                   for key in ("b", "c_left", "c_down", "c_right")
                   if equips.get(key) not in (None, senses.ITEM_NONE)}
        return {"items": held, "buttons": buttons}

    def _menu_equipment_view(self) -> dict:
        """oot://menu/equipment: worn + owned gear by name (the masks ride
        the wire's equips block; senses.equipment_view is the decode)."""
        if not self.game.link.connected:
            return {"error": "game not connected"}
        equips = self.game.state().get("equips")
        if equips is None or "worn" not in equips:
            return {"blind": "instrument predates the equipment sense — "
                             "rebuild SoH with the 2026-08-04 AgentLink patch"}
        view = senses.equipment_view(equips)
        # The raw masks beside the decode: a debug affordance on a menu
        # document (the pause screen presents this same information as icons).
        view["masks"] = {"worn": f"0x{int(equips.get('worn') or 0):04X}",
                         "owned": f"0x{int(equips.get('owned') or 0):04X}"}
        return view

    def _journal_tail(self, n: int = 200):
        path = self.log.persist_path
        if path is None or not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()[-n:]
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out


def _opt_float(value):
    return None if value is None else float(value)


def _tool_ok(body: dict) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(body, indent=1)}],
            "isError": False}


def _tool_error(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": True}


def _rpc_error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id,
            "error": {"code": code, "message": message}}


# -- transport ----------------------------------------------------------------

def _is_blocking_call(msg: dict) -> bool:
    return (msg.get("method") == "tools/call"
            and (msg.get("params") or {}).get("name") in BLOCKING_TOOLS
            and msg.get("id") is not None)


def serve(core: ServerCore, stdin=None, stdout=None) -> None:
    """Newline-delimited JSON-RPC over stdio. Blocks until stdin closes.

    The wake verbs block for as long as the world runs, so they get their
    own thread and the read loop keeps serving everything else — status,
    resources, and above all the cancellation that severs the block.
    Responses are matched by id, so answering out of order is legal."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    write_lock = threading.Lock()

    def write(obj: dict) -> None:
        with write_lock:
            stdout.write(json.dumps(obj) + "\n")
            stdout.flush()

    core.notify = lambda method, params: write(
        {"jsonrpc": "2.0", "method": method, "params": params})

    def dispatch(msg: dict) -> None:
        response = core.handle(msg)
        if response is None:
            return
        try:
            write(response)
        except (ValueError, OSError):
            pass    # stdout closed under a blocked call: the client is gone

    try:
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if _is_blocking_call(msg):
                threading.Thread(target=dispatch, args=(msg,), daemon=True,
                                 name="wake-wait").start()
            else:
                dispatch(msg)
    finally:
        core.sever_all()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="ocarina",
        description="MCP server for playing Ocarina of Time. The save-file "
                    "repo declares the machine; ocarina runs it.")
    parser.add_argument("--repo", required=True, type=Path,
                        help="the save-file repo (contains machine/)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Sail listen host (the game connects to us)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help="Sail listen port")
    parser.add_argument("--wake-deadline", type=float, default=300.0,
                        help="seconds before an unanswered wake takes its default")
    parser.add_argument("--o2r", type=Path, default=None,
                        help="SoH's oot.o2r (the collision source the place "
                             "sense distills region graphs from); without it "
                             "the place sense is OFF, loudly")
    parser.add_argument("--brainviz", type=int, default=None, metavar="PORT",
                        help="serve the brain viewer (lab/brainviz) on this "
                             "local port — a one-way debug view of the live "
                             "machine, off by default")
    parser.add_argument("--dev-tools", action="store_true",
                        help="register the dev_* harness verbs (warp, "
                             "teleport) for harness development and live "
                             "e2e tests. Server layer only — never "
                             "behavior-reachable; every call is journaled; "
                             "refused outright on a repo declaring "
                             "\"scored\": true. Off (the default) = the "
                             "verbs are ABSENT")
    parser.add_argument("--no-overlay", action="store_true",
                        help="do not push the human debug overlay (world-space "
                             "labels + the census-boundary HUD panel) to the "
                             "game. For recordings. Lab-grade: the overlay is "
                             "one-way and never feeds the sensorium, so this "
                             "changes nothing the mind or the machine sees")
    parser.add_argument("--no-jev", action="store_true",
                        help="do not construct the Jev judge even if a key is "
                             "found (JEV_API in the environment, then .env in "
                             "the ocarina checkout, then <repo>/.env). Without "
                             "a key Jev is OFF, loudly; bodies that ask for a "
                             "judgment abort by name")
    parser.add_argument("--jev-timeout", type=float, default=jev.DEFAULT_TIMEOUT_S,
                        help="per-request wall-clock cap for Jev calls (seconds)")
    args = parser.parse_args(argv)

    if args.dev_tools:
        # Commitment 3, before anything is constructed and long before
        # any connection: a scored repo refuses the flag, loudly.
        refusal = dev.scored_refusal(args.repo)
        if refusal is not None:
            print(f"ocarina: REFUSING to start with --dev-tools — {refusal}",
                  file=sys.stderr)
            return 2

    link = GameLink(host=args.host, port=args.port)
    game = Game(link)
    log = EventLog(persist_path=args.repo / "journal" / "mechanical.jsonl")
    judge = None
    if args.no_jev:
        log.record({"event": "diagnostic",
                    "text": "Jev is OFF (--no-jev): game.jev is None"})
    else:
        key, source = jev.find_key(Path(__file__).resolve().parent.parent / ".env",
                                   args.repo / ".env")
        if key is None:
            log.record({"event": "diagnostic",
                        "text": "Jev is OFF: no JEV_API in the environment, "
                                "the ocarina checkout's .env, or the repo's "
                                ".env — game.jev is None"})
        else:
            client = jev.JevClient(key, log=log, timeout_s=args.jev_timeout)
            judge = jev.JevSense(client)
            log.record({"event": "diagnostic",
                        "text": f"Jev is ON (key from {source}; model "
                                f"{client.model}; per-call cap "
                                f"{args.jev_timeout:g}s) — every judgment "
                                "journals"})
    runtime = MachineRuntime(game, args.repo, log,
                             wake_deadline_s=args.wake_deadline,
                             place=PlaceSense(args.o2r), jev=judge)
    if args.no_overlay:
        runtime.overlay_enabled = False
        log.record({"event": "diagnostic",
                    "text": "debug overlay OFF (--no-overlay): no labels, no "
                            "boundary HUD; the sensorium is unaffected"})
    dev_tools = dev.DevTools(game) if args.dev_tools else None
    core = ServerCore(game, runtime, log, dev_tools=dev_tools)
    if dev_tools is not None:
        # The banner is the first line of this boot's journal, and the
        # runtime re-journals it on every attach (a repo's fossil must
        # carry the mark for every world it touched under the flag).
        log.record(dev.banner_event("boot"))
        runtime.dev_banner = dev.banner_event("connect")
        print(f"ocarina: {dev.STARTUP_TEXT}", file=sys.stderr)

    viz = None
    if args.brainviz is not None:
        viz = Brainviz(runtime, log, port=args.brainviz)
        url = viz.start()      # a taken port fails the boot, loudly
        log.record({"event": "diagnostic", "text": f"brainviz serving at {url}"})

    link.start()
    runtime.load()    # rehydrate from the repo: live state is never the only copy
    threading.Thread(target=runtime.run, daemon=True, name="runtime").start()
    try:
        serve(core)
    finally:
        runtime.stop()
        if viz is not None:
            viz.stop()
        link.stop()
    return 0
