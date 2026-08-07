"""The stdio MCP server: SURFACE.md's tool/resource contract on the wire.

Stdlib JSON-RPC 2.0 over stdio (MCP framing: one JSON message per line).
The core is transport-free (`ServerCore.handle(msg)`) so the whole surface
is testable without pipes; `main()` wires stdin/stdout, the Sail link, and
the 20 Hz runtime thread.

Wakes ride MCP channels (verified 2026-07-31): the initialize response
declares `experimental: {"claude/channel": {}}` and wake packs go out as
`notifications/claude/channel` — `content` lands as the body of a
`<channel source="ocarina">` block, `meta` keys become tag attributes.
Delivery queues until the session is idle; harmless here, because
cognition happens in stopped time.

Tools not yet implemented return a clean isError result saying exactly
what instrument work they wait on — the surface shape is the blessed
contract, and an honest "not built" beats a missing verb (which would
read as "not part of the design", untrue) or a quiet failure (docs/08).
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import MACHINE_FORMAT_VERSION, OCARINA_VERSION, senses
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
reload_machine() validates and hot-swaps it. Wake packs arrive as
<channel source="ocarina"> blocks while the game is FROZEN: read the
pack, inspect resources, edit the machine if needed, then call resume()
to unfreeze. Every wake has a declared default that fires if you never
answer, so the world will not wait forever."""


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
    _tool("resume", "Unfreeze the game, back to autopilot. Optional heartbeat override.",
          {"max_sleep": {"type": "number", "description": "Seconds between heartbeat wakes (stored; heartbeat wake is machine content)."}}),
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
    _tool("screenshot", "Vision on demand; a debugging sense, never a stream."),
]

#: Tools that exist on the blessed surface but wait on instrument work.
#: Each maps to what it needs — an honest error beats a silent stub.
#: (0.8.0 graduated dialogue_choose/save_game/use_item; 0.9.0 graduated
#: equip and buy. What is left here waits on real UI substrate.)
NOT_YET = {
    "create_file": "file-select UI navigation not built yet",
    "continue_game": "death-screen UI navigation not built yet",
    "save_and_quit": "save-screen UI navigation not built yet",
    "play_song": "ocarina UI note entry not built yet",
    "screenshot": "no screenshot op on the wire yet (DojoLink patch needed)",
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
     "description": "The place sense (docs/25): this scene's region graph as "
                    "judgments over stable names — regions, climb columns, "
                    "unverified candidates, where you are. Route planning is "
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


class ServerCore:
    """The MCP surface, transport-free. `notify` is called with outbound
    notifications (the channel push); main() points it at stdout."""

    def __init__(self, game: Game, runtime: MachineRuntime, log: EventLog):
        self.game = game
        self.runtime = runtime
        self.log = log
        self.notify = lambda method, params: None
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
                result = {"tools": TOOLS}
            elif method == "tools/call":
                result = self._call_tool(msg.get("params") or {})
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

    def _call_tool(self, params: dict) -> dict:
        name = params.get("name")
        args = params.get("arguments") or {}
        if name in NOT_YET:
            return _tool_error(f"{name} is on the surface but not yet "
                               f"implemented in ocarina {OCARINA_VERSION}: "
                               f"{NOT_YET[name]}")
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return _tool_error(f"unknown tool {name!r}")
        try:
            result = handler(args)
        except LinkError as e:
            return _tool_error(f"game link: {e}")
        if isinstance(result, dict) and result.get("ok") is False:
            # Context-legal, not context-mounted: wrong-screen (and
            # wrong-state) calls are clean tool errors.
            return _tool_error(result.get("error", json.dumps(result)))
        return _tool_ok(result)

    def _tool_status(self, args) -> dict:
        st = self.runtime.status()
        st.update({"ocarina_version": OCARINA_VERSION,
                   "machine_format_version": MACHINE_FORMAT_VERSION,
                   "repo": str(self.runtime.repo)})
        return st

    def _tool_reload_machine(self, args) -> dict:
        return self.runtime.reload()

    def _tool_force_state(self, args) -> dict:
        return self.runtime.force_state(str(args.get("node", "")))

    def _tool_set_directive(self, args) -> dict:
        return self.runtime.set_directive(str(args.get("text", "")))

    def _tool_resume(self, args) -> dict:
        max_sleep = args.get("max_sleep")
        return self.runtime.resume(None if max_sleep is None else float(max_sleep))

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
        msg = st.get("message")
        if msg is None:
            return {"ok": False,
                    "error": "instrument predates the dialogue sense — "
                             "rebuild SoH with the 2026-08-04 AgentLink patch"}
        if msg.get("state") != "choice":
            return {"ok": False,
                    "error": f"no choice is being offered "
                             f"(box state: {msg.get('state')})"}
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
                             f"(sits at {cur})"}
        self.game.press("A", frames=3)
        label = choices[target] if target < len(choices) else None
        return {"ok": True, "chose": target, "label": label,
                "dialogue_open": self.game.state().get("msg_mode", 0) != 0}

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
                sample = (self.runtime.place.sample(st)
                          if self.runtime.place is not None else None)
                body = senses.digest(st, self.runtime.sightings, sample)
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
        return senses.equipment_view(equips)

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


def _tool_ok(body: dict) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(body, indent=1)}],
            "isError": False}


def _tool_error(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": True}


def _rpc_error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id,
            "error": {"code": code, "message": message}}


# -- transport ----------------------------------------------------------------

def serve(core: ServerCore, stdin=None, stdout=None) -> None:
    """Newline-delimited JSON-RPC over stdio. Blocks until stdin closes."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    write_lock = threading.Lock()

    def write(obj: dict) -> None:
        with write_lock:
            stdout.write(json.dumps(obj) + "\n")
            stdout.flush()

    core.notify = lambda method, params: write(
        {"jsonrpc": "2.0", "method": method, "params": params})

    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        response = core.handle(msg)
        if response is not None:
            write(response)


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
    args = parser.parse_args(argv)

    link = GameLink(host=args.host, port=args.port)
    game = Game(link)
    log = EventLog(persist_path=args.repo / "journal" / "mechanical.jsonl")
    runtime = MachineRuntime(game, args.repo, log,
                             wake_deadline_s=args.wake_deadline,
                             place=PlaceSense(args.o2r))
    core = ServerCore(game, runtime, log)

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
