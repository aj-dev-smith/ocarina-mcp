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
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import MACHINE_FORMAT_VERSION, OCARINA_VERSION, senses
from .brainviz import Brainviz
from .events import EventLog
from .game import Game
from .link import GameLink, LinkError
from .place import PlaceSense
from .protocol import DEFAULT_PORT
from .runtime import MachineRuntime

PROTOCOL_VERSION = "2025-06-18"

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
    _tool("buy", "Shops: buy an item.", {"item": {"type": "string"}}, ["item"]),
    _tool("play_song", "The ocarina interface: choosing the song is the game; note entry is UI mechanics.",
          {"name": {"type": "string"}}, ["name"]),
    _tool("screenshot", "Vision on demand; a debugging sense, never a stream."),
]

#: Tools that exist on the blessed surface but wait on instrument work.
#: Each maps to what it needs — an honest error beats a silent stub.
NOT_YET = {
    "create_file": "file-select UI navigation not built yet",
    "continue_game": "death-screen UI navigation not built yet",
    "save_and_quit": "save-screen UI navigation not built yet",
    "equip": "B-button/gear assignment not built yet (use_item covers C buttons; docs/27 kept equip out of scope)",
    "buy": "shop UI navigation not built yet",
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
                             "rebuild SoH with the 2026-08-04 dojo patch"}
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
        cur = msg.get("choice_index", 0)
        for _ in range(8):
            if cur == target:
                break
            # Stick up moves the cursor up (index down), per the game's own
            # Message_HandleChoiceSelection; neutral between nudges so its
            # held-stick latch re-arms.
            self.game.pad(stick=(0, -127 if target > cur else 127))
            self.game.wait(0.15)
            self.game.pad_clear()
            self.game.wait(0.1)
            cur = (self.game.state().get("message") or {}).get("choice_index", cur)
        if cur != target:
            return {"ok": False,
                    "error": f"cursor would not reach option {target} "
                             f"(sits at {cur})"}
        self.game.press("A", frames=3)
        label = choices[target] if target < len(choices) else None
        return {"ok": True, "chose": target, "label": label,
                "dialogue_open": self.game.state().get("msg_mode", 0) != 0}

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
                             "rebuild SoH with the 2026-08-04 dojo patch"}
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
                             "rebuild SoH with the 2026-08-04 dojo patch")
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
                             "rebuild SoH with the 2026-08-04 dojo patch"}
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
                             "rebuild SoH with the 2026-08-04 dojo patch"}
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
