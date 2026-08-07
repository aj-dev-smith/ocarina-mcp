import json
import shutil
import tempfile
import unittest
from pathlib import Path

from ocarina import OCARINA_VERSION
from ocarina.events import EventLog
from ocarina.game import Game
from ocarina.runtime import MachineRuntime
from ocarina.server import ServerCore

from .stubgame import StubLink

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "save-file"


class ServerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = Path(self.tmp) / "save-file"
        shutil.copytree(FIXTURE_REPO, self.repo)
        self.link = StubLink()
        self.game = Game(self.link)
        self.log = EventLog(persist_path=self.repo / "journal" / "mechanical.jsonl")
        self.runtime = MachineRuntime(self.game, self.repo, self.log)
        self.runtime.load()
        self.core = ServerCore(self.game, self.runtime, self.log)
        self.notifications = []
        self.core.notify = lambda method, params: self.notifications.append(
            (method, params))

    def tearDown(self):
        self.runtime.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def rpc(self, method, params=None, msg_id=1):
        return self.core.handle({"jsonrpc": "2.0", "id": msg_id,
                                 "method": method, "params": params or {}})

    def call_tool(self, name, arguments=None):
        return self.rpc("tools/call", {"name": name,
                                       "arguments": arguments or {}})["result"]

    def tool_body(self, result):
        return json.loads(result["content"][0]["text"])

    def read(self, uri):
        result = self.rpc("resources/read", {"uri": uri})["result"]
        return json.loads(result["contents"][0]["text"])


class TestHandshake(ServerCase):
    def test_initialize_declares_the_channel(self):
        result = self.rpc("initialize", {"protocolVersion": "2025-06-18"})["result"]
        self.assertEqual(result["serverInfo"],
                         {"name": "ocarina", "version": OCARINA_VERSION})
        self.assertIn("claude/channel", result["capabilities"]["experimental"])
        self.assertIn("resume()", result["instructions"])

    def test_unknown_method(self):
        response = self.rpc("no/such/method")
        self.assertEqual(response["error"]["code"], -32601)

    def test_notifications_get_no_response(self):
        self.assertIsNone(self.core.handle(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}))


class TestTools(ServerCase):
    def test_list_matches_the_blessed_surface(self):
        tools = {t["name"] for t in self.rpc("tools/list")["result"]["tools"]}
        for name in ("status", "reload_machine", "force_state", "set_directive",
                     "resume", "escalate", "scan", "screenshot", "create_file",
                     "continue_game", "save_and_quit", "save_game",
                     "dialogue_choose", "dialogue_advance", "equip", "use_item",
                     "buy", "play_song"):
            self.assertIn(name, tools)
        # And what must NEVER appear (benchmark purity): no pad, no savestates.
        for absent in ("pad", "save_state", "load_state", "drill", "dojo_test"):
            self.assertNotIn(absent, tools)

    def test_status(self):
        body = self.tool_body(self.call_tool("status"))
        self.assertEqual(body["ocarina_version"], OCARINA_VERSION)
        self.assertTrue(body["machine_loaded"])
        self.assertEqual(body["current_node"], "navigate_field")
        self.assertTrue(body["game_connected"])

    def test_not_yet_tools_error_honestly(self):
        # equip and buy left this list in 0.9.0 (docs/28); play_song still
        # waits on real note-entry UI.
        result = self.call_tool("play_song", {"name": "zeldas_lullaby"})
        self.assertTrue(result["isError"])
        self.assertIn("not yet implemented", result["content"][0]["text"])

    def test_dialogue_advance_wrong_screen_is_clean_error(self):
        result = self.call_tool("dialogue_advance")
        self.assertTrue(result["isError"])
        self.assertIn("no dialogue is open", result["content"][0]["text"])

    def test_dialogue_advance_presses_a(self):
        self.link.world["msg_mode"] = 4
        result = self.call_tool("dialogue_advance")
        self.assertFalse(result["isError"])
        pads = [r for r in self.link.requests if r.get("op") == "pad"]
        self.assertTrue(pads, "the server did the button mechanics")

    def test_force_state_and_resume(self):
        body = self.tool_body(self.call_tool("force_state", {"node": "kill_baba"}))
        self.assertEqual(body["current"], "kill_baba")
        result = self.call_tool("force_state", {"node": "nowhere"})
        self.assertTrue(result["isError"])
        # resume BLOCKS as of 0.10.0: with no wake coming, the honest cap
        # is what returns — and the world keeps running.
        body = self.tool_body(self.call_tool("resume", {"max_block_s": 0.1}))
        self.assertTrue(body["no_wake"])

    def test_scan(self):
        body = self.tool_body(self.call_tool("scan", {"rays": 8}))
        self.assertTrue(body["ok"])
        self.assertEqual(body["rays"], [])


class TestResources(ServerCase):
    def test_list(self):
        uris = {r["uri"] for r in self.rpc("resources/list")["result"]["resources"]}
        for uri in ("oot://state", "oot://events", "oot://dialogue",
                    "oot://menu/quest", "oot://machine",
                    "oot://journal/mechanical"):
            self.assertIn(uri, uris)

    def test_state_digest(self):
        body = self.read("oot://state")
        self.assertEqual(body["hearts"], 3.0)
        self.assertEqual(body["enemies"], 0)
        self.assertNotIn("nearest_enemy", body)

    def test_events_query(self):
        body = self.read("oot://events?last=5&category=entered")
        self.assertTrue(all(e["event"] == "entered" for e in body))
        self.assertTrue(body)

    def test_machine_two_columns(self):
        body = self.read("oot://machine")
        self.assertTrue(body["declared"]["valid"])
        self.assertTrue(body["declared"]["in_sync"])
        self.assertEqual(body["live"]["current"], "navigate_field")
        self.assertIn("explore", body["live"]["nodes"]["nodes"])

    def test_machine_shows_drift(self):
        # Edit the repo without reloading: declared and live must disagree.
        yaml_path = self.repo / "machine" / "machine.yaml"
        yaml_path.write_text(yaml_path.read_text().replace(
            "cooldown_s: 30", "cooldown_s: 45"))
        body = self.read("oot://machine")
        self.assertTrue(body["declared"]["valid"])
        self.assertFalse(body["declared"]["in_sync"],
                         "the conjunction discipline: repo != server must show")

    def test_journal_mechanical(self):
        body = self.read("oot://journal/mechanical")
        self.assertTrue(any(e["event"] == "entered" for e in body))

    def test_equipment_document_carries_the_raw_masks(self):
        # Tenth flight: the sword/shield rows read null/empty on the wire
        # while tunic/boots parsed, and nothing in the document could say
        # whether the masks or the decode were at fault. They ride along now.
        self.link.world["equips"] = {"b": 0x3B, "c_left": 0xFF, "c_down": 0xFF,
                                     "c_right": 0xFF,
                                     "worn": 0x1122, "owned": 0x3333}
        body = self.read("oot://menu/equipment")
        self.assertEqual(body["worn"], {"sword": "master_sword",
                                        "shield": "hylian_shield",
                                        "tunic": "kokiri_tunic",
                                        "boots": "kokiri_boots"})
        self.assertEqual(body["owned"]["sword"],
                         ["kokiri_sword", "master_sword"])
        self.assertEqual(body["masks"], {"worn": "0x1122", "owned": "0x3333"})

    def test_equipment_masks_are_hex_even_when_empty(self):
        self.link.world["equips"] = {"worn": 0, "owned": 0}
        body = self.read("oot://menu/equipment")
        self.assertIsNone(body["worn"]["sword"])
        self.assertEqual(body["masks"], {"worn": "0x0000", "owned": "0x0000"})

    def test_not_yet_resources(self):
        # map/quest stay honest not-yets; dialogue/items/equipment
        # graduated in 0.8.0 (docs/27).
        body = self.read("oot://menu/map")
        self.assertIn("not_yet", body)
        self.assertNotIn("not_yet", self.read("oot://dialogue"))


class TestWakeChannel(ServerCase):
    def test_wake_pushes_a_channel_notification(self):
        self.link.world["health"] = 40
        self.link.push_wire({"type": "agent_event", "event": "health_change",
                             "amount": -8, "health": 40})
        for _ in range(10):
            self.runtime.tick()
            if self.notifications:
                break
        self.assertTrue(self.notifications)
        method, params = self.notifications[0]
        self.assertEqual(method, "notifications/claude/channel")
        self.assertTrue(params["content"].startswith("WAKE: health critical"))
        self.assertEqual(params["meta"]["kind"], "wake")
        self.assertEqual(params["meta"]["transition"], "health-drop")
        # meta keys must be identifier-safe (hyphens are dropped by the
        # client): transition names may contain '-', so check we still got it.
        self.assertTrue(all(k.replace("_", "a").isalnum() for k in params["meta"]))

    def test_escalation_pushes(self):
        self.tool_body_ok = self.call_tool("escalate", {"reason": "stuck at gate"})
        methods = [m for m, _ in self.notifications]
        self.assertIn("notifications/claude/channel", methods)


if __name__ == "__main__":
    unittest.main()
