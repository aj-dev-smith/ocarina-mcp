"""jev.py offline: the client over a fake transport, the fire-and-hold
Judge, key discovery, journaling, and senses.narrate()."""

import json
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from ocarina import jev, senses
from ocarina.events import EventLog


def canned(answers: dict, model="jev-latest", usage=None):
    body = json.dumps({"model": model, "answers": answers,
                       "usage": usage or {"input_tokens": 100, "output_tokens": 10}})
    return body.encode()


CHOICE = {"type": "choice", "choice": "attack", "confidence": 0.71,
          "probabilities": {"attack": 0.75, "approach": 0.19, "ignore": 0.06}}
NOUL = {"type": "noul", "noul": 0.82}
SCORE = {"type": "score", "score": 1.66, "confidence": 0.22,
         "probabilities": {"0": 0.1, "1": 0.3, "2": 0.44, "3": 0.16},
         "legend": {"0": "safe", "1": "watchful", "2": "pressing", "3": "critical"}}
ANSWERS = {"action": CHOICE, "reach": NOUL, "danger": SCORE}
QUESTIONS = {"action": {"type": "choice", "instructions": "?", "criteria": {"attack": "a"}},
             "reach": {"type": "noul", "instructions": "?"},
             "danger": {"type": "score", "instructions": "?", "criteria": ["a", "b"]}}


class FakeTransport:
    """(body, timeout) -> (status, bytes); records requests; scriptable."""

    def __init__(self, status=200, body=None, delay_s=0.0):
        self.status = status
        self.body = body if body is not None else canned(ANSWERS)
        self.delay_s = delay_s
        self.requests = []
        self.lock = threading.Lock()
        self.script = []      # optional per-call overrides: (status, body) or exception

    def __call__(self, body, timeout_s):
        with self.lock:
            self.requests.append(json.loads(body))
            step = self.script.pop(0) if self.script else None
        if self.delay_s:
            time.sleep(self.delay_s)
        if isinstance(step, Exception):
            raise step
        if step is not None:
            return step
        return self.status, self.body


class TestClient(unittest.TestCase):
    def test_typed_accessors(self):
        t = FakeTransport()
        c = jev.JevClient("k", transport=t)
        j = c.ask({"hearts": 3}, QUESTIONS)
        self.assertTrue(j.ok)
        self.assertEqual(j.choice("action"), "attack")
        self.assertAlmostEqual(j.prob("action", "approach"), 0.19)
        self.assertAlmostEqual(j.noul("reach"), 0.82)
        self.assertAlmostEqual(j.score("danger"), 1.66)
        self.assertAlmostEqual(j.confidence("danger"), 0.22)
        self.assertIsNone(j.choice("reach"))          # wrong primitive -> None
        self.assertIsNone(j.noul("nope"))             # unknown question -> None
        self.assertEqual(j.model, "jev-latest")
        self.assertEqual(c.input_tokens, 100)
        self.assertEqual(c.ok_calls, 1)

    def test_request_shape(self):
        t = FakeTransport()
        c = jev.JevClient("k", transport=t, model="jev-test")
        c.ask("Link has 3 hearts.", QUESTIONS)
        req = t.requests[0]
        self.assertEqual(req["state"], "Link has 3 hearts.")
        self.assertEqual(req["model"], "jev-test")
        self.assertEqual(set(req["questions"]), {"action", "reach", "danger"})

    def test_http_error_is_a_failed_judgment_not_an_exception(self):
        t = FakeTransport(status=429, body=b'{"detail":"rate limited"}')
        c = jev.JevClient("k", transport=t)
        j = c.ask({}, QUESTIONS)
        self.assertFalse(j.ok)
        self.assertIn("http 429", j.error)
        self.assertIsNone(j.choice("action"))
        self.assertEqual(c.errors, 1)
        self.assertEqual(c.last_error, j.error)

    def test_timeout_and_transport_exceptions_are_failed_judgments(self):
        t = FakeTransport()
        t.script = [socket.timeout("timed out"), OSError("connection reset")]
        c = jev.JevClient("k", transport=t, timeout_s=0.5)
        j1 = c.ask({}, QUESTIONS)
        j2 = c.ask({}, QUESTIONS)
        self.assertFalse(j1.ok); self.assertIn("timeout", j1.error)
        self.assertFalse(j2.ok); self.assertIn("OSError", j2.error)

    def test_malformed_reply(self):
        t = FakeTransport(body=b'{"model":"x"}')
        j = jev.JevClient("k", transport=t).ask({}, QUESTIONS)
        self.assertFalse(j.ok)
        self.assertIn("malformed", j.error)
        j = jev.JevClient("k", transport=FakeTransport(body=b'not json')).ask({}, QUESTIONS)
        self.assertFalse(j.ok)

    def test_journal_carries_answers_never_the_key_or_state(self):
        log = EventLog()
        t = FakeTransport()
        c = jev.JevClient("SECRET-KEY", transport=t, log=log)
        c.ask({"secret_state": "the whole room"}, QUESTIONS, tag="duel")
        ev = log.tail(5)[-1]
        self.assertEqual(ev["event"], "diagnostic")
        blob = json.dumps(ev)
        self.assertNotIn("SECRET-KEY", blob)
        self.assertNotIn("the whole room", blob)
        jb = ev["judgment"]
        self.assertTrue(jb["ok"])
        self.assertEqual(jb["tag"], "duel")
        self.assertEqual(jb["answers"]["action"]["choice"], "attack")
        self.assertEqual(jb["answers"]["reach"], 0.82)
        self.assertEqual(jb["answers"]["danger"]["score"], 1.66)
        self.assertEqual(jb["questions"], ["action", "danger", "reach"])
        self.assertEqual(len(jb["state_hash"]), 12)
        self.assertIn("answered in", ev["text"])
        # a failure journals too, naming the error
        t.status = 529
        c.ask({}, QUESTIONS, tag="duel")
        ev = log.tail(5)[-1]
        self.assertIn("FAILED", ev["text"])
        self.assertIn("http 529", ev["judgment"]["error"])

    def test_stats(self):
        c = jev.JevClient("k", transport=FakeTransport())
        for _ in range(3):
            c.ask({}, QUESTIONS)
        s = c.stats()
        self.assertEqual(s["calls"], 3)
        self.assertEqual(s["ok"], 3)
        self.assertEqual(s["answered_by"], "jev-latest")
        self.assertIsNotNone(s["latency_ms_median"])


class TestJudge(unittest.TestCase):
    def test_fire_and_hold_returns_latest_completed(self):
        t = FakeTransport(delay_s=0.05)
        c = jev.JevClient("k", transport=t)
        judge = jev.Judge(c, QUESTIONS, tag="t")
        self.assertIsNone(judge.latest())
        judge.submit("s1")
        j = judge.wait_for(0, timeout_s=2.0)
        self.assertIsNotNone(j)
        self.assertEqual(j.choice("action"), "attack")
        self.assertFalse(judge.pending)
        judge.close()

    def test_newest_submit_supersedes_unsent(self):
        t = FakeTransport(delay_s=0.08)
        c = jev.JevClient("k", transport=t)
        judge = jev.Judge(c, QUESTIONS)
        judge.submit("s1")            # goes on the wire
        time.sleep(0.01)
        judge.submit("s2")            # parked
        judge.submit("s3")            # replaces s2
        judge.submit("s4")            # replaces s3
        judge.wait_for(1, timeout_s=2.0)
        time.sleep(0.05)
        states = [r["state"] for r in t.requests]
        self.assertEqual(states, ["s1", "s4"])
        self.assertEqual(judge.superseded, 2)
        self.assertEqual(judge.completed, 2)
        judge.close()

    def test_fresh_gates_on_age_and_ok(self):
        t = FakeTransport()
        c = jev.JevClient("k", transport=t)
        judge = jev.Judge(c, QUESTIONS)
        judge.submit("s")
        j = judge.wait_for(0)
        self.assertIsNotNone(judge.fresh(1.0))
        j.at -= 5.0
        self.assertIsNone(judge.fresh(1.0))
        t.status = 500
        judge.submit("s")
        judge.wait_for(j.seq)
        self.assertIsNone(judge.fresh(1.0))    # not ok -> None
        self.assertFalse(judge.latest().ok)
        judge.close()

    def test_closed_judge_refuses(self):
        judge = jev.Judge(jev.JevClient("k", transport=FakeTransport()), QUESTIONS)
        judge.close()
        self.assertFalse(judge.submit("s"))

    def test_sense_handle(self):
        sense = jev.JevSense(jev.JevClient("k", transport=FakeTransport()))
        self.assertTrue(sense.ask("s", QUESTIONS).ok)
        jd = sense.judge(QUESTIONS, tag="x")
        jd.submit("s")
        self.assertIsNotNone(jd.wait_for(0))
        jd.close()
        self.assertEqual(sense.stats()["calls"], 2)


class TestFindKey(unittest.TestCase):
    def setUp(self):
        self._saved = {v: os.environ.pop(v, None) for v in jev.KEY_ENV_VARS}

    def tearDown(self):
        for v, val in self._saved.items():
            if val is not None:
                os.environ[v] = val
            else:
                os.environ.pop(v, None)

    def test_env_wins(self):
        os.environ["JEV_API"] = "from-env"
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".env").write_text("JEV_API: from-file\n")
            self.assertEqual(jev.find_key(Path(d) / ".env"), ("from-env", "$JEV_API"))

    def test_env_file_colon_and_equals_forms(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.env", Path(d) / "b.env"
            a.write_text("# comment\nOTHER=1\nJEV_API: apikey_colon\n")
            b.write_text('export JEV_API="apikey_eq"\n')
            self.assertEqual(jev.find_key(a, b), ("apikey_colon", str(a)))
            self.assertEqual(jev.find_key(b), ("apikey_eq", str(b)))
            self.assertEqual(jev.find_key(Path(d) / "missing.env"), (None, "not found"))


class TestNarrate(unittest.TestCase):
    def test_full_digest(self):
        d = {"hearts": 0.5, "hearts_max": 3.0, "enemies": 2,
             "player": {"climbing": False, "on_wall": False, "dead": False},
             "place": {"region": "ydan:r@30,0,70", "on_mesh": True, "heading": "n"},
             "nearest_enemy": {"kind": "deku_baba", "dist": 65.2, "above": 0.0,
                               "bearing": 1, "moving": True, "reach": "walkable"},
             "dialogue_open": False}
        s = senses.narrate(d, extra=["Its head is low"])
        self.assertIn("Link has 0.5 of 3 hearts.", s)
        self.assertIn("region ydan:r@30,0,70, heading n.", s)
        self.assertIn("The nearest enemy is a deku baba, 65 units away, just off ahead at 1 o'clock, "
                      "at Link's height, moving; the ground to it is walkable.", s)
        self.assertIn("2 enemies are in view.", s)
        self.assertTrue(s.endswith("Its head is low."))

    def test_absent_entities_are_absent_sentences(self):
        s = senses.narrate({"hearts": 3.0, "hearts_max": 3.0, "enemies": 0, "player": {}})
        self.assertEqual(s, "Link has 3 of 3 hearts. No enemy is in view.")
        self.assertEqual(senses.narrate({}), "")

    def test_dialogue_and_height(self):
        d = {"hearts": 3.0, "hearts_max": 3.0, "enemies": 1, "player": {},
             "nearest_enemy": {"kind": "skulltula", "dist": 40.0, "above": 1072.0, "bearing": 6},
             "dialogue": {"state": "choice", "text_id": 0x6B, "text": "Buy more?",
                          "choices": ["Yes", "No"], "choice_index": 1}}
        s = senses.narrate(d)
        self.assertIn("directly behind, 1072 units above Link.", s)
        self.assertIn('A message box is open (choice): "Buy more?"; it offers the choices '
                      "['Yes', 'No'], cursor on option 1.", s)
        d["player"] = {"dead": True}
        self.assertIn("Link is dead.", senses.narrate(d))


if __name__ == "__main__":
    unittest.main()
