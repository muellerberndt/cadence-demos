"""Headless check of the demo: start the server, fetch the page and a frame, run three trials
through the API (two with the brain, one with the teacher) and print their stages.

    python -m arm2.demo.check --checkpoint runs/demo/D3b_s1_brain.npz
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

LANE = Path(__file__).resolve().parent.parent.parent


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.read()


def post(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--trials", type=int, default=3)
    a = p.parse_args()
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen([sys.executable, "-m", "arm2.demo.server", "--checkpoint", a.checkpoint, "--port", str(port)],
                            cwd=LANE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out: dict = {"port": port, "trials": []}
    try:
        for _ in range(60):
            try:
                get(base + "/api/state")
                break
            except Exception:
                time.sleep(1)
        page = get(base + "/").decode()
        out["page_ok"] = "Panda" in page and "/api/state" in page
        frame = b""
        for _ in range(100):
            try:
                frame = get(base + "/frame.png")
            except urllib.error.HTTPError:  # 503 until the first frame is painted
                frame = b""
            if frame[:8] == b"\x89PNG\r\n\x1a\n":
                break
            time.sleep(0.3)
        out["frame_ok"] = frame[:8] == b"\x89PNG\r\n\x1a\n"
        out["frame_bytes"] = len(frame)
        for k in range(a.trials):
            teacher = k == a.trials - 1
            post(base + "/api/new_trial", {"teacher": teacher, "auto": False, "mass": None, "friction": None, "x": None, "y": None, "order": None})
            t = time.time()
            state = None
            for _ in range(20):  # the simulation thread starts the trial within a decision
                state = json.loads(get(base + "/api/state"))
                if not state["done"] and state["decision"] < 3:
                    break
                time.sleep(0.2)
            while time.time() - t < 120:
                state = json.loads(get(base + "/api/state"))
                if state["done"]:
                    break
                time.sleep(0.5)
            if k == 0 and state is not None:
                post(base + "/api/nudge", {})
            out["trials"].append({"policy": state["policy"], "passed": state["passed"], "decisions": state["decision"], "done": state["done"],
                                  "gates": {g: state["gates"].get(g) for g in ("settling_s", "effort_nms", "oscillation_near_hz")},
                                  "ratios": state["ratios"], "sweeps": state["sweeps"], "physics": state["physics"],
                                  "seconds": round(time.time() - t, 1)})
        out["ok"] = out["page_ok"] and out["frame_ok"] and all(t["done"] for t in out["trials"])
    finally:
        proc.terminate()
        try:
            server_out = proc.communicate(timeout=5)[0]
        except subprocess.TimeoutExpired:
            proc.kill()
            server_out = proc.communicate()[0]
        out["server_tail"] = (server_out or "")[-1500:]
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
