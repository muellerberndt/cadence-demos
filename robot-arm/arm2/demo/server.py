"""A live browser demo of a frozen stage-2 brain on the Panda cell.

    python -m arm2.demo.server --checkpoint runs/demo/D3b_s1_brain.npz --port 8820
    open http://127.0.0.1:8820/

One Python file and one page, the standard library only. A simulation thread runs the world at
the 5 Hz decision rate with the brain alone (or the scripted teacher, toggled live), renders the
scene offscreen (``mujoco.Renderer``, 640 x 480) twice per decision, and keeps the latest PNG and
the trial's state; the page polls ``/frame.png`` at 10 fps and ``/api/state`` at 5 Hz. Controls:
a new trial (random or placed block, mass and friction sliders spanning the nominal and held-out
ranges, the lamp), a nudge that shifts the block 3 cm mid-carry, the teacher toggle. Readouts:
the stage, the gates of the current trial against the teacher's nominal values, the sweeps per
settle. The brain learns nothing here.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import mujoco
import numpy as np

from arm2.actions import HOLD, execute, hold_answer, motion
from arm2.inspect import load_policy
from arm2.job import STAGES, GateRecorder, TeacherPolicy, prepare
from arm2.render import save_rgb_png
from arm2.scene import LIFT, ORDERS, PandaWorld

HERE = Path(__file__).resolve().parent
# The teacher's own values on 100 nominal trials (arm2.teacher --trials 100, Mac, 29 Oct 2026).
TEACHER_NOMINAL = {"right": 0.98, "decisions_median": 38, "oscillation_hz": 3.08, "oscillation_near_hz": 6.08, "overshoot_cm": 0.0,
                   "settling_s": 0.61, "effort_nms": 508.3, "effort_cmd": 0.57, "jerk": 131.1, "path_cm": 77.0}
MASS_RANGE = (0.03, 0.28)
FRICTION_RANGE = (0.30, 1.20)
DECISION_S = 0.2


def encode_png(image: np.ndarray) -> bytes:
    import io

    buf = io.BytesIO()
    tmp = HERE / ".frame.png"
    save_rgb_png(image, tmp)  # the lane's own encoder (no PIL)
    buf.write(tmp.read_bytes())
    return buf.getvalue()


class Demo(threading.Thread):
    def __init__(self, checkpoint: str, pools: str, velocity: bool, seed: int) -> None:
        super().__init__(daemon=True)
        self.lock = threading.Lock()
        self.world = PandaWorld(seed, "nominal")
        self.brain = load_policy(checkpoint, pools, velocity=velocity)
        self.teacher = TeacherPolicy(pools)
        self.pools = pools
        self.checkpoint = checkpoint
        self.renderer = None  # made inside the simulation thread: a GL context belongs to one thread
        self.camera = mujoco.MjvCamera()
        self.camera.type = mujoco.mjtCamera.mjCAMERA_FREE
        self.camera.lookat[:] = (0.52, 0.0, 0.08)
        self.camera.distance, self.camera.azimuth, self.camera.elevation = 1.25, 150.0, -32.0
        self.settings = {"teacher": False, "auto": True, "mass": None, "friction": None, "order": None, "x": None, "y": None}
        self.frame = b""
        self.events: list[str] = []
        self.tally = {"trials": 0, "right": 0, "wrong": 0, "dropped": 0}
        self.recorder: GateRecorder | None = None
        self.passed: set[str] = set()
        self.decision = 0
        self.done = False
        self.done_at = 0.0
        self.last_answer = None
        self.sweeps: list[int] = []
        self.pending_new = True
        self.pending_nudge = False
        self.physics = {}

    # --- requests from the page -----------------------------------------------------------------
    def request_new_trial(self, **settings) -> None:
        with self.lock:
            for k, v in settings.items():
                if k in self.settings:
                    self.settings[k] = v
            self.pending_new = True

    def set(self, **settings) -> None:
        with self.lock:
            for k, v in settings.items():
                if k in self.settings:
                    self.settings[k] = v

    def request_nudge(self) -> None:
        with self.lock:
            self.pending_nudge = True

    # --- the trial --------------------------------------------------------------------------------
    def _new_trial(self) -> None:
        w = self.world
        prepare(w)
        s = self.settings
        m = w.model
        if s["mass"] is not None:
            m.body_mass[w.block_body] = float(s["mass"])
            m.body_inertia[w.block_body] = float(s["mass"]) * (2 * w.half) ** 2 / 6.0
        if s["friction"] is not None:
            m.geom_friction[w.block_geom, 0] = float(s["friction"])
        if s["x"] is not None or s["y"] is not None:
            q = w.block_qpos
            x = float(s["x"]) if s["x"] is not None else float(w.data.qpos[q])
            y = float(s["y"]) if s["y"] is not None else float(w.data.qpos[q + 1])
            w.data.qpos[q:q + 7] = (x, y, w.half, 1.0, 0.0, 0.0, 0.0)
            w.data.qvel[w.block_qvel:w.block_qvel + 6] = 0.0
            mujoco.mj_forward(m, w.data)
        if s["order"] in (1, 2):
            w.order = int(s["order"])
            w.new_order()
            w.order = int(s["order"])
            for k, gid in w.lamps.items():
                m.geom_rgba[gid] = (1.0, 0.95, 0.4, 1.0) if ORDERS[w.order] == k else (0.3, 0.3, 0.3, 1.0)
        w.last_command = None
        self.brain.reset()
        self.recorder = GateRecorder(w)
        self.passed, self.events, self.sweeps = set(), [], []
        self.decision, self.done = 0, False
        self.physics = {"mass_kg": round(float(m.body_mass[w.block_body]), 3), "friction": round(float(m.geom_friction[w.block_geom, 0]), 2),
                        "half_cm": round(w.half * 100, 1), "solref_s": round(float(m.geom_solref[w.block_geom, 0]), 3)}
        self.tally["trials"] += 1
        self.pending_new = False

    def _nudge(self) -> None:
        w = self.world
        q = w.block_qpos
        w.data.qpos[q] += 0.03  # 3 cm along x: the block slides along the fingertip pads
        mujoco.mj_forward(w.model, w.data)
        self.events.append(f"d{self.decision}: nudge +3 cm x")
        self.pending_nudge = False

    def _render(self) -> None:
        self.renderer.update_scene(self.world.data, self.camera)
        png = encode_png(self.renderer.render())
        with self.lock:
            self.frame = png

    def _stage(self) -> str:
        w = self.world
        if self.done:
            return "done"
        if w.releasing:
            return "release"
        if w.holding:
            if "carried" in self.passed:
                return "carry"
            return "lift" if "lifted" in self.passed else "grasp"
        if w.closed:
            return "closing"
        tip, block = w.tip(), w.block_pos()
        return "lower" if np.hypot(tip[0] - block[0], tip[1] - block[1]) < 0.04 else "reach"

    def run(self) -> None:
        self.renderer = mujoco.Renderer(self.world.model, 480, 640)
        while True:
            t = time.perf_counter()
            with self.lock:
                new, nudge, teacher, auto = self.pending_new, self.pending_nudge, self.settings["teacher"], self.settings["auto"]
            if new or (self.done and auto and time.time() - self.done_at > 2.0):
                self._new_trial()
                self._render()
            elif not self.done:
                if nudge:
                    self._nudge()
                w = self.world
                tip = w.tip()
                if not w.holding and np.linalg.norm(tip - w.hover_point()) <= 0.025:
                    self.passed.update(("reached", "reached_hover"))
                if w.holding:
                    if w.block_pos()[2] - w.half >= 0.05:
                        self.passed.add("lifted")
                    ordered = w.ordered_bin()
                    if "lifted" in self.passed and ordered is not None and np.hypot(tip[0] - ordered[0], tip[1] - ordered[1]) <= 0.03:
                        self.passed.add("carried")
                policy = self.teacher if teacher else self.brain
                answer = policy.act(w)
                if answer is None:
                    answer = hold_answer(self.pools, w.closed)
                if not teacher and self.brain.sweeps:
                    self.sweeps.append(self.brain.sweeps[-1])
                self.last_answer = [int(v) for v in answer]
                before = w.rest()
                rec = self.recorder

                def hook(i: int, rec=rec) -> None:
                    rec.sample(i)
                    if i in (10, 20):
                        self._render()

                event = execute(w, answer, self.pools, hook)["event"] or ""
                rec.decision(before, w.rest())
                self.decision += 1
                if event:
                    self.events.append(f"d{self.decision}: {event}")
                if event == "grasped":
                    self.passed.update(("reached", "grasped"))
                elif event in ("dropped", "slipped"):
                    self.passed.add("dropped")
                    self.tally["dropped"] += 1
                elif event.startswith("placed"):
                    right = event.endswith("right")
                    self.passed.add("right" if right else "wrong")
                    self.tally["right" if right else "wrong"] += 1
                    self.done, self.done_at = True, time.time()
                if self.decision >= 80 and not self.done:
                    self.events.append("cap: 80 decisions")
                    self.done, self.done_at = True, time.time()
            else:
                self._render()
            time.sleep(max(0.0, DECISION_S - (time.perf_counter() - t)))

    def state(self) -> dict:
        rec = self.recorder
        try:
            gates = rec.summary() if rec is not None and len(rec.tips) > 3 else {}
        except (ValueError, IndexError):  # read while the simulation thread samples
            gates = {}
        with self.lock:
            s = dict(self.settings)
        ratios = {k: (None if gates.get(k) is None or not TEACHER_NOMINAL.get(k) else round(gates[k] / TEACHER_NOMINAL[k], 2))
                  for k in ("oscillation_hz", "oscillation_near_hz", "settling_s", "effort_nms", "jerk", "path_cm")}
        return {"policy": "teacher" if s["teacher"] else "brain", "checkpoint": self.checkpoint, "stage": self._stage(),
                "passed": [k for k in STAGES if k in self.passed], "decision": self.decision, "done": self.done,
                "holding": self.world.holding, "closed": self.world.closed, "lamp": ORDERS[self.world.order],
                "tip_cm": [round(float(v) * 100, 1) for v in self.world.tip()], "block_cm": [round(float(v) * 100, 1) for v in self.world.block_pos()],
                "lift_cm": LIFT * 100, "command": self.last_answer, "hold": self.last_answer is not None and all(v == HOLD for v in self.last_answer[:3]),
                "events": self.events[-6:], "gates": {k: (None if v is None else round(v, 3)) for k, v in gates.items()},
                "teacher_nominal": TEACHER_NOMINAL, "ratios": ratios,
                "sweeps": round(float(np.mean(self.sweeps)), 1) if self.sweeps else None, "physics": self.physics, "settings": s,
                "tally": self.tally, "motion_slots": motion(self.pools).stop}


class Handler(BaseHTTPRequestHandler):
    demo: Demo

    def log_message(self, *_args) -> None:
        pass

    def _send(self, code: int, body: bytes, kind: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/frame.png":
            with self.demo.lock:
                frame = self.demo.frame
            self._send(200 if frame else 503, frame or b"", "image/png")
        elif path == "/api/state":
            self._send(200, json.dumps(self.demo.state()).encode(), "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        if path == "/api/new_trial":
            self.demo.request_new_trial(**body)
        elif path == "/api/set":
            self.demo.set(**body)
        elif path == "/api/nudge":
            self.demo.request_nudge()
        else:
            self._send(404, b"not found", "text/plain")
            return
        self._send(200, json.dumps({"ok": True}).encode(), "application/json")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--port", type=int, default=8820)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--pools", choices=("cartesian", "joint"), default="cartesian")
    p.add_argument("--no-velocity", dest="no_velocity", action="store_true")
    a = p.parse_args()
    demo = Demo(a.checkpoint, a.pools, not a.no_velocity, a.seed)
    demo.start()
    Handler.demo = demo
    server = ThreadingHTTPServer((a.host, a.port), Handler)
    print(json.dumps({"serving": f"http://{a.host}:{a.port}/", "checkpoint": a.checkpoint}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
