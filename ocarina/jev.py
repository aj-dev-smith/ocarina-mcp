"""Jev: System One judgments as a behavior primitive (2026-09-18).

TypeSafe's Jev is a model that never generates text: POST a `state`
(a string or JSON) and a map of typed questions, get back typed answers
with calibrated probabilities — `choice` (a distribution over named
options), `noul` (probability a condition holds), `score` (a weighted
position on an ordered rubric). AJ's framing, the session this was
built: a behavior stops being hand-written Python that pattern-matches
the input stream and becomes "shape the stream into a state, ask a
handful of typed questions, map the answers to a button". Code keeps
the 20 Hz loop and the pad; the model supplies the judgment.

What this module is:

- `JevClient` — ONE persistent HTTPS connection (measured 2026-09-18
  from AJ's machine: ~650 ms per request on a fresh connection, ~275 ms
  warm; the TLS handshake alone was ~370 ms, so keep-alive is not an
  optimisation, it is the difference between a 1.5 Hz and a 3.5 Hz
  policy). `ask()` is synchronous and NEVER raises for the service's
  sake: HTTP errors, timeouts and bad JSON come back as a Judgment with
  `ok=False` and a named `error`, because a 429 mid-fight must be a
  code default, not a stack trace in a body thread.
- `Judge` — the fire-and-hold runner a 20 Hz body actually wants. A
  round trip is 5+ ticks, so a body never blocks on it: `submit()` the
  freshest state (a newer submit supersedes an unsent one — the world
  moved, the old question is moot), keep acting on `latest()`, and let
  the answer land when it lands. One request in flight at a time on
  purpose: a second in-flight request would only answer a staler state.
- `find_key()` — `JEV_API` from the environment or a `.env` file
  (`KEY: value` or `KEY=value`); the key never enters the journal.
- `narrate()` lives in senses.py: the measured lesson of the first
  probe was that the SAME facts as one sentence of narration answered
  the low-health case right (retreat) where nested JSON answered it
  wrong (approach). The narration layer's own form is the better input.

Journaling: every completed call records a `diagnostic` carrying a
compact `judgment` block (question ids, the answers, latency, token
usage, the model that answered, a hash of the state — never the key,
never the state itself: the state is the body's business and can be
re-derived from the journal's own timeline). The journal is the fossil:
a scored run's every judgment is on the record, model version included.

Fairness: Jev sees exactly what the body sends it, and bodies already
hold the raw census. It is cognition on the player's side of the line,
not knowledge from the game's — the same standing as the mind's own
head. The contract touch (a `game.jev` handle and `game.digest_of` on
the behavior interface) is proposed in dojo docs/37, not yet blessed;
until then this is lab-grade: nothing on SURFACE.md or MACHINE.md moves.

Stdlib only (repo rule 4): http.client, json, threading.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import socket
import ssl
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable, Optional

DEFAULT_HOST = "api.typesafe.ai"
DEFAULT_PATH = "/v1/systemone"
DEFAULT_MODEL = "jev-latest"
#: Per-request wall-clock cap. A body's code default takes over past it;
#: 2 s is ~7x the warm median and well under any wake's patience.
DEFAULT_TIMEOUT_S = 2.0
KEY_ENV_VARS = ("JEV_API", "TYPESAFE_API_KEY")
_KEY_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(.+?)\s*$")


# -- key discovery -----------------------------------------------------------

def find_key(*env_files: Path | str) -> tuple[Optional[str], str]:
    """(key, source). The environment wins; then each `.env` in order.
    `source` names where it came from (for the boot diagnostic) and
    never the key. Missing files are not errors: (None, 'not found')."""
    for var in KEY_ENV_VARS:
        val = os.environ.get(var)
        if val:
            return val.strip(), f"${var}"
    for f in env_files:
        p = Path(f)
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            m = _KEY_LINE.match(line)
            if m and m.group(1) in KEY_ENV_VARS:
                val = m.group(2).strip().strip("'\"")
                if val:
                    return val, str(p)
    return None, "not found"


# -- answers -----------------------------------------------------------------

class Judgment:
    """One request's worth of answers, typed accessors over the raw map.

    `ok` False means NO answers: `error` names why (http 429, timeout,
    ...) and every accessor returns None. A body treats None as "use the
    code default", never as a verdict.
    """

    def __init__(self, answers: Optional[dict] = None, *, ok: bool = True,
                 error: Optional[str] = None, latency_ms: float = 0.0,
                 usage: Optional[dict] = None, model: Optional[str] = None,
                 state_hash: str = "", seq: int = 0):
        self.answers: dict = answers or {}
        self.ok = ok
        self.error = error
        self.latency_ms = latency_ms
        self.usage = usage or {}
        self.model = model
        self.state_hash = state_hash
        self.seq = seq
        self.at = time.monotonic()

    @property
    def age_s(self) -> float:
        return time.monotonic() - self.at

    def _answer(self, qid: str) -> Optional[dict]:
        a = self.answers.get(qid)
        return a if isinstance(a, dict) else None

    def choice(self, qid: str) -> Optional[str]:
        a = self._answer(qid)
        return a.get("choice") if a and a.get("type") == "choice" else None

    def probabilities(self, qid: str) -> dict:
        a = self._answer(qid)
        return dict(a.get("probabilities") or {}) if a else {}

    def prob(self, qid: str, option: str) -> Optional[float]:
        p = self.probabilities(qid)
        return float(p[option]) if option in p else None

    def noul(self, qid: str) -> Optional[float]:
        a = self._answer(qid)
        return float(a["noul"]) if a and a.get("type") == "noul" and "noul" in a else None

    def score(self, qid: str) -> Optional[float]:
        a = self._answer(qid)
        return float(a["score"]) if a and a.get("type") == "score" and "score" in a else None

    def confidence(self, qid: str) -> Optional[float]:
        a = self._answer(qid)
        return float(a["confidence"]) if a and "confidence" in a else None

    def compact(self) -> dict:
        """The journal form: one value per question, no legends."""
        out = {}
        for qid, a in self.answers.items():
            if not isinstance(a, dict):
                continue
            t = a.get("type")
            if t == "choice":
                out[qid] = {"choice": a.get("choice"),
                            "conf": _r(a.get("confidence")),
                            "p": {k: _r(v) for k, v in
                                  (a.get("probabilities") or {}).items()}}
            elif t == "noul":
                out[qid] = _r(a.get("noul"))
            elif t == "score":
                out[qid] = {"score": _r(a.get("score")),
                            "conf": _r(a.get("confidence"))}
            else:
                out[qid] = a
        return out


def _r(v):
    try:
        return round(float(v), 3)
    except (TypeError, ValueError):
        return v


def state_hash(state) -> str:
    raw = state if isinstance(state, str) else json.dumps(state, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


# -- the client --------------------------------------------------------------

class JevClient:
    """One keep-alive connection to Jev; synchronous `ask()`.

    `log` is an EventLog (or anything with `.record(dict)`); every call
    journals. `transport` is the seam tests use: a callable
    (body_bytes, timeout_s) -> (status, body_bytes) replacing HTTPS.
    """

    def __init__(self, api_key: str, *, model: str = DEFAULT_MODEL,
                 host: str = DEFAULT_HOST, path: str = DEFAULT_PATH,
                 timeout_s: float = DEFAULT_TIMEOUT_S, log=None,
                 transport: Optional[Callable] = None, journal: bool = True):
        self._key = api_key
        self.model = model
        self.host = host
        self.path = path
        self.timeout_s = timeout_s
        self.log = log
        self.journal = journal
        self._transport = transport
        self._conn: Optional[http.client.HTTPSConnection] = None
        self._lock = threading.Lock()      # one request on the wire at a time
        # Instruments (status() reads these; never the key, never a state).
        self.calls = 0
        self.ok_calls = 0
        self.errors = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.last_error: Optional[str] = None
        self.last_model: Optional[str] = None
        self.latencies: deque = deque(maxlen=64)
        self._seq = 0

    # -- wire ---------------------------------------------------------------

    def _connect(self, timeout_s: float) -> http.client.HTTPSConnection:
        if self._conn is None:
            self._conn = http.client.HTTPSConnection(
                self.host, timeout=timeout_s, context=ssl.create_default_context())
        else:
            # http.client only honours timeout at connect; re-arm the socket
            # in case this call's cap differs from the connection's.
            sock = getattr(self._conn, "sock", None)
            if sock is not None:
                sock.settimeout(timeout_s)
        return self._conn

    def _drop(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _post(self, body: bytes, timeout_s: float) -> tuple[int, bytes]:
        if self._transport is not None:
            return self._transport(body, timeout_s)
        headers = {"Authorization": f"Bearer {self._key}",
                   "Content-Type": "application/json",
                   "Connection": "keep-alive"}
        for attempt in (1, 2):
            conn = self._connect(timeout_s)
            try:
                conn.request("POST", self.path, body=body, headers=headers)
                resp = conn.getresponse()
                data = resp.read()
                return resp.status, data
            except (http.client.HTTPException, OSError) as e:
                # A server-closed keep-alive reads as a BadStatusLine /
                # RemoteDisconnected / broken pipe on the NEXT request:
                # reconnect once, then give up honestly. A timeout is
                # OSError too (socket.timeout), and is not retried.
                self._drop()
                if attempt == 2 or isinstance(e, socket.timeout):
                    raise
        raise RuntimeError("unreachable")

    # -- the verb -------------------------------------------------------------

    def ask(self, state, questions: dict, timeout_s: Optional[float] = None,
            tag: str = "") -> Judgment:
        """One request, all `questions` over one `state`. Never raises on
        the service's account; a failed call is `Judgment(ok=False)`."""
        cap = self.timeout_s if timeout_s is None else float(timeout_s)
        payload = {"state": state, "model": self.model, "questions": questions}
        body = json.dumps(payload, default=str).encode("utf-8")
        shash = state_hash(state)
        with self._lock:
            self._seq += 1
            seq = self._seq
            self.calls += 1
            t0 = time.perf_counter()
            try:
                status, data = self._post(body, cap)
                ms = (time.perf_counter() - t0) * 1000.0
                if status != 200:
                    j = self._fail(f"http {status}: {data[:200].decode('utf-8', 'replace')}",
                                   ms, shash, seq)
                else:
                    parsed = json.loads(data)
                    answers = parsed.get("answers")
                    if not isinstance(answers, dict):
                        j = self._fail("malformed reply: no answers map", ms, shash, seq)
                    else:
                        usage = parsed.get("usage") or {}
                        j = Judgment(answers, latency_ms=ms, usage=usage,
                                     model=parsed.get("model"), state_hash=shash,
                                     seq=seq)
                        self.ok_calls += 1
                        self.last_model = j.model
                        self.input_tokens += int(usage.get("input_tokens", 0) or 0)
                        self.output_tokens += int(usage.get("output_tokens", 0) or 0)
            except socket.timeout:
                j = self._fail(f"timeout after {cap:.2f}s", (time.perf_counter() - t0) * 1000.0,
                               shash, seq)
            except (OSError, http.client.HTTPException, ValueError) as e:
                j = self._fail(f"{type(e).__name__}: {e}", (time.perf_counter() - t0) * 1000.0,
                               shash, seq)
            self.latencies.append(j.latency_ms)
        self._journal(j, questions, tag)
        return j

    def _fail(self, error: str, ms: float, shash: str, seq: int) -> Judgment:
        self.errors += 1
        self.last_error = error
        return Judgment(ok=False, error=error, latency_ms=ms, state_hash=shash, seq=seq)

    def _journal(self, j: Judgment, questions: dict, tag: str) -> None:
        if not self.journal or self.log is None:
            return
        block = {"seq": j.seq, "ok": j.ok, "latency_ms": round(j.latency_ms, 1),
                 "state_hash": j.state_hash, "questions": sorted(questions),
                 "model": j.model}
        if tag:
            block["tag"] = tag
        if j.ok:
            block["answers"] = j.compact()
            block["usage"] = j.usage
            text = f"jev: {tag or 'judgment'} answered in {j.latency_ms:.0f} ms"
        else:
            block["error"] = j.error
            text = f"jev: {tag or 'judgment'} FAILED ({j.error})"
        try:
            self.log.record({"event": "diagnostic", "text": text, "judgment": block})
        except Exception:
            pass    # the journal is a passenger of the call, never its gate

    def stats(self) -> dict:
        lat = sorted(self.latencies)
        return {"model": self.model, "answered_by": self.last_model,
                "calls": self.calls, "ok": self.ok_calls, "errors": self.errors,
                "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "latency_ms_median": round(lat[len(lat) // 2], 1) if lat else None,
                "latency_ms_max": round(lat[-1], 1) if lat else None,
                "last_error": self.last_error}

    def close(self) -> None:
        with self._lock:
            self._drop()


# -- the fire-and-hold runner ----------------------------------------------

class Judge:
    """Asynchronous judgments for a 20 Hz body.

        judge = game.jev.judge(QUESTIONS, tag="duel")
        while fighting:
            judge.submit(narration)         # newest state wins; never blocks
            j = judge.latest()              # last COMPLETED answer or None
            act(j.choice("action") if j and j.ok else DEFAULT)
            game.wait(TICK)
        judge.close()

    One worker thread, one request in flight. `submit()` while a request
    is in flight parks the state as "next"; a later submit replaces it
    (the world moved on — answering the older state would be answering a
    question nobody is asking any more). `latest()` returns the most
    recent completed Judgment, ok or not; `fresh(max_age_s)` gates on
    its age so a body can stop trusting an answer the world has outrun.
    """

    def __init__(self, client: JevClient, questions: Optional[dict] = None,
                 tag: str = "", timeout_s: Optional[float] = None):
        self.client = client
        self.questions = questions or {}
        self.tag = tag
        self.timeout_s = timeout_s
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._next: Optional[tuple] = None
        self._latest: Optional[Judgment] = None
        self._in_flight = False
        self._closed = False
        self.submitted = 0
        self.superseded = 0
        self.completed = 0
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name=f"jev:{tag or 'judge'}")
        self._thread.start()

    def submit(self, state, questions: Optional[dict] = None) -> bool:
        """Queue the freshest state. False if closed."""
        with self._lock:
            if self._closed:
                return False
            if self._next is not None:
                self.superseded += 1
            self._next = (state, questions if questions is not None else self.questions)
            self.submitted += 1
        self._wake.set()
        return True

    @property
    def pending(self) -> bool:
        with self._lock:
            return self._in_flight or self._next is not None

    def latest(self) -> Optional[Judgment]:
        with self._lock:
            return self._latest

    def fresh(self, max_age_s: float) -> Optional[Judgment]:
        """The latest judgment only if it is ok and younger than max_age_s."""
        j = self.latest()
        if j is None or not j.ok or j.age_s > max_age_s:
            return None
        return j

    def wait_for(self, seq_after: int = 0, timeout_s: float = 3.0) -> Optional[Judgment]:
        """Block (tests / non-loop callers) until a judgment newer than
        `seq_after` lands, or the timeout passes."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            j = self.latest()
            if j is not None and j.seq > seq_after:
                return j
            time.sleep(0.005)
        return None

    def _run(self) -> None:
        while True:
            self._wake.wait()
            with self._lock:
                if self._closed:
                    return
                job = self._next
                self._next = None
                if job is None:
                    self._wake.clear()
                    continue
                self._in_flight = True
            state, questions = job
            try:
                j = self.client.ask(state, questions, timeout_s=self.timeout_s, tag=self.tag)
            except Exception as e:      # ask() never raises; belt and braces
                j = Judgment(ok=False, error=f"{type(e).__name__}: {e}")
            with self._lock:
                self._latest = j
                self._in_flight = False
                self.completed += 1
                if self._next is None:
                    self._wake.clear()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._next = None
        self._wake.set()

    def stats(self) -> dict:
        return {"submitted": self.submitted, "completed": self.completed,
                "superseded": self.superseded, "pending": self.pending}


class JevSense:
    """The handle bodies get as `game.jev` (attached by the runtime, the
    `game.place` pattern). Wraps one client; hands out Judges."""

    def __init__(self, client: JevClient):
        self.client = client

    def ask(self, state, questions: dict, timeout_s: Optional[float] = None,
            tag: str = "") -> Judgment:
        return self.client.ask(state, questions, timeout_s=timeout_s, tag=tag)

    def judge(self, questions: Optional[dict] = None, tag: str = "",
              timeout_s: Optional[float] = None) -> Judge:
        return Judge(self.client, questions, tag=tag, timeout_s=timeout_s)

    def stats(self) -> dict:
        return self.client.stats()
