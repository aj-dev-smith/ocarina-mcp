"""Hand-drive rig for a live ocarina flight (the docs/20 'drove the pipe
by hand' pattern, scripted). Spawns the real server, does the MCP
handshake, then relays JSON commands from a FIFO to the server's stdin.
Every message in either direction lands in traffic.jsonl with a wall
timestamp — wake packs (notifications/claude/channel) included.

Command lines written to the FIFO:
  {"method": "tools/call", "params": {"name": "status", "arguments": {}}}
  {"method": "resources/read", "params": {"uri": "oot://state"}}
"""

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime

FLIGHT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(FLIGHT, "second-light")
OCARINA_ROOT = "/Users/aj/Code/ocarina"
FIFO = os.path.join(FLIGHT, "cmd.fifo")
LOG = os.path.join(FLIGHT, "traffic.jsonl")
PORT = 43384


def log(direction, payload):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"wall": datetime.now().isoformat(timespec="seconds"),
                            "dir": direction, "msg": payload}) + "\n")


def main():
    if os.path.exists(FIFO):
        os.remove(FIFO)
    os.mkfifo(FIFO)
    proc = subprocess.Popen(
        [sys.executable, "-m", "ocarina", "--repo", REPO, "--port", str(PORT)],
        cwd=OCARINA_ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1)
    log("meta", {"note": "server spawned", "pid": proc.pid, "port": PORT})

    def read_stdout():
        for line in proc.stdout:
            line = line.strip()
            if line:
                try:
                    log("recv", json.loads(line))
                except ValueError:
                    log("recv-raw", line)
        log("meta", {"note": "server stdout closed"})

    def read_stderr():
        for line in proc.stderr:
            log("stderr", line.rstrip())

    threading.Thread(target=read_stdout, daemon=True).start()
    threading.Thread(target=read_stderr, daemon=True).start()

    next_id = [0]

    def send(method, params):
        next_id[0] += 1
        msg = {"jsonrpc": "2.0", "id": next_id[0], "method": method,
               "params": params}
        log("send", msg)
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    send("initialize", {"protocolVersion": "2025-06-18"})
    time.sleep(0.3)

    while proc.poll() is None:
        with open(FIFO, "r", encoding="utf-8") as fifo:
            for line in fifo:
                line = line.strip()
                if not line:
                    continue
                if line == "QUIT":
                    log("meta", {"note": "quit requested"})
                    proc.terminate()
                    return
                try:
                    cmd = json.loads(line)
                    send(cmd["method"], cmd.get("params") or {})
                except (ValueError, KeyError) as e:
                    log("meta", {"note": f"bad command: {e}", "line": line})
    log("meta", {"note": "server exited", "code": proc.returncode})


if __name__ == "__main__":
    main()
