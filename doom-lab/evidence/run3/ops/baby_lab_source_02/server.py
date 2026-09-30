"""Browser Doom lab: teacher window (you play, Cadence learns live) and
student window (the brain plays). Serves http://localhost:8666 .

One game thread owns ViZDoom; the trainer thread owns the learning brain;
shadow predictions are serialized inside the Student. The browser supplies
keys over a WebSocket and watches an MJPEG stream plus a live HUD.
"""

from __future__ import annotations

import asyncio
import base64
import io
import os
import hashlib
import copy
import json
import random
import threading
import time
import uuid

import numpy as np
from aiohttp import WSMsgType, web
from PIL import Image

from brainlab import Student
from doomlab import BUTTONS, FRAME_SKIP, DoomLab, brain_view

DECISION_SECONDS = FRAME_SKIP / 35.0  # real-time pacing for the teacher

KEYMAP = {
    "KeyW": "forward", "ArrowUp": "forward",
    "ArrowLeft": "turn_left", "ArrowRight": "turn_right",
    "KeyA": "move_left", "KeyD": "move_right",
    "KeyS": "move_backward", "ArrowDown": "move_backward",
    "Space": "use", "KeyE": "use",
    "ControlLeft": "attack", "KeyJ": "attack", "Mouse": "attack",
}


def _basic_killed(outcomes):
    """Basic's +100 native kill reward, after per-tic living/firing costs."""
    return any(reward > 50 for outcome in outcomes for reward in outcome['rewards'])


class Lab:
    def __init__(self):
        self.student = Student()
        self.session_id = uuid.uuid4().hex
        self.mode = "idle"
        self.keys_down: set[str] = set()
        self.frame_jpeg = b""
        self.frame_seq = 0
        self.retinas = ("", "")
        self.game_stats = {}
        self.agreement = []
        self.shadow_view = {}
        self.episode = 0
        self.auto_resets = 0
        self.reset_request = False
        self._still_pos = None
        self._still_since = None
        self.lock = threading.Lock()
        self.rng = random.Random(0)
        self._mode_flag = threading.Event()
        self._stop = threading.Event()
        self._latest_view = None
        self._decision = None
        self._thread = threading.Thread(target=self._game_loop, daemon=True)
        self._thread.start()
        self._shadow_thread = threading.Thread(
            target=self._shadow_loop, daemon=True)
        self._shadow_thread.start()

    # ---- browser-facing state ----------------------------------------

    def set_mode(self, mode):
        assert mode in ("idle", "teach", "student")
        if (self.student.v2 is not None and self.mode in ("teach", "student")
                and mode in ("teach", "student") and mode != self.mode):
            self.reset_request = True
        self.mode = mode
        self._decision = None
        self._mode_flag.set()

    def hud(self):
        pressed = sorted({KEYMAP[k] for k in self.keys_down if k in KEYMAP})
        recent = self.agreement[-60:]
        adapter = self.student.v2
        info = adapter.model_info if adapter else self.student.model_info
        learning = adapter.status() if adapter else {"available": False, "enabled": False}
        trainer = dict(self.student.stats)
        if adapter:
            trainer.update(admitted=learning.get("accepted_examples", 0),
                           queued=learning.get("queue_depth", 0), training=learning.get("busy", False))
        return {
            "mode": self.mode,
            "session_id": self.session_id,
            "episode": self.episode,
            "game": self.game_stats,
            "trainer": trainer,
            "learning": learning,
            "shadow": self.shadow_view,
            "pressed": pressed,
            "agreement": round(float(np.mean(recent)), 3) if recent else None,
            "buttons": list(BUTTONS),
            "brain_layout": self.student.layout_meta,
            "auto_resets": self.auto_resets,
            "model": {"id": self.student.model_id,
                      "pending": self.student._swapping or self.student._swap_request is not None,
                      "error": self.student.swap_error, **info},
            "retinas": {"periphery": self.retinas[0], "fovea": self.retinas[1]},
        }

    # ---- game thread --------------------------------------------------

    def _buttons_from_keys(self):
        names = {KEYMAP[k] for k in self.keys_down if k in KEYMAP}
        return [1 if name in names else 0 for name in BUTTONS]

    def _publish_frame(self, screen, periphery, fovea):
        image = Image.fromarray(screen)
        buf = io.BytesIO()
        image.save(buf, "JPEG", quality=82)
        thumbs = None
        if self.frame_seq % 6 == 0:  # retina thumbs are a 5 Hz side channel
            thumbs = []
            for retina in (periphery, fovea):
                gray = ((retina + 0.6) / 1.2 * 255).clip(0, 255).astype(np.uint8)
                tb = io.BytesIO()
                Image.fromarray(gray, "L").save(tb, "PNG")
                thumbs.append(base64.b64encode(tb.getvalue()).decode())
        with self.lock:
            self.frame_jpeg = buf.getvalue()
            self.frame_seq += 1
            if thumbs is not None:
                self.retinas = (thumbs[0], thumbs[1])

    def _game_loop(self):
        lab = None
        import vizdoom as vzd

        while not self._stop.is_set():
            if self.mode == "idle":
                if lab is not None:
                    lab.close()
                    lab = None
                self._mode_flag.wait(timeout=0.5)
                self._mode_flag.clear()
                continue
            if self.student._swapping or self.student._swap_request:
                time.sleep(.05)
                continue
            if self.student.v2 is not None:
                if lab is not None:
                    lab.close()
                    lab = None
                try:
                    adapter = self.student.v2
                    if adapter.model_info.get("schema") == "cadence-doom-player-v3/1":
                        adapter.run_session(self)
                    else:
                        self._basic_session(adapter)
                except Exception as error:
                    self.shadow_view = {"qualified": False, "error": str(error)}
                    self.game_stats = {"error": str(error)}
                    self.set_mode("idle")
                continue
            if lab is None:
                lab = DoomLab()
                lab.new_episode()
                self.episode += 1
            if self.reset_request:
                self.reset_request = False
                self._decision = None
                self._still_pos = self._still_since = None
                self.student.reset_context()
                lab.new_episode()
                self.episode += 1
            if lab.finished:
                self.student.reset_context()
                lab.new_episode()
                self.episode += 1
            state = lab.state()
            if state is None:
                lab.new_episode()
                self.episode += 1
                continue
            periphery, fovea = brain_view(state.screen_buffer)
            self._latest_view = (periphery, fovea)
            self.student.advance_context(periphery.ravel(), fovea.ravel())
            gv = state.game_variables
            if self.mode == "student":
                # Stuck watchdog: the environment (not the brain) restarts a
                # frozen episode, and says so on the HUD.
                pos = (gv[3], gv[4])
                clock = time.monotonic()
                if (self._still_pos is None or
                        abs(pos[0] - self._still_pos[0]) +
                        abs(pos[1] - self._still_pos[1]) > 8.0):
                    self._still_pos, self._still_since = pos, clock
                elif clock - (self._still_since or clock) > 6.0:
                    self.auto_resets += 1
                    self.reset_request = True
                    continue
            self.game_stats = {
                "health": gv[0], "kills": gv[1], "ammo": gv[2],
                "qualified": self.shadow_view.get("qualified"),
            }
            if self.mode == "teach":
                # One decision window = FRAME_SKIP tics, but every tic is
                # rendered, published and paced, and keys are sampled live.
                # The witness pairs the window's first frame with the keys
                # held at that moment; learning cadence is unchanged.
                buttons = self._buttons_from_keys()
                self.student.submit_witness(
                    periphery.ravel(), fovea.ravel(), buttons, self.rng)
                shadow = self.shadow_view.get("buttons")
                if shadow is not None:
                    match = np.mean([int(a == b) for a, b in
                                     zip(shadow, buttons, strict=True)])
                    self.agreement.append(float(match))
                    self.agreement = self.agreement[-600:]
                self._run_tics(lab, None, live_keys=True)
            elif self.mode == "student":
                generation, episode = self.student.generation, self.episode
                try:
                    decision = self.student.predict_buttons(periphery, fovea)
                except ValueError as error:
                    decision = {"qualified": False, "error": str(error)}
                self.shadow_view = decision
                if (generation != self.student.generation or episode != self.episode
                        or self.mode != "student" or self.student._swapping or self.student._swap_request):
                    continue
                if not decision.get("qualified"):
                    self.set_mode("idle")
                    continue
                self._run_tics(lab, decision["buttons"], live_keys=False)
            else:
                time.sleep(0.05)
        if lab is not None:
            lab.close()

    def _basic_session(self, adapter):
        """Only the game thread executes actions; query freezes simulator time."""
        from v2.basic_env import Episode, compact, pool, history
        generation = self.student.generation
        env = None
        try:
            while (not self._stop.is_set() and self.mode != "idle"
                   and self.student.v2 is adapter and generation == self.student.generation):
                if self.student._swapping or self.student._swap_request:
                    time.sleep(.05)
                    continue
                if not adapter.flush_pending():
                    time.sleep(.05)
                    continue
                if env is None or env.game.is_episode_finished() or self.reset_request:
                    if env:
                        adapter.last_episode = {"session_id": self.session_id, "seed": seed, "return": episode_return,
                                                "transitions": len(prefix),
                                                "terminal": env.game.is_episode_finished(),
                                                "killed": _basic_killed(outcomes),
                                                "queries": queries, "qualified_queries": qualified_queries,
                                                "policy_checkpoint_sha256": episode_checkpoint,
                                                "behavior_source": episode_mode,
                                                "tics": sum(o['tics'] for o in outcomes),
                                                "cutoff_reason": None if env.game.is_episode_finished() else "reset"}
                        env.close()
                    self.reset_request = False
                    adapter.episode_boundary()
                    seed = self.rng.randrange(800000000, 900000000)
                    env = Episode(seed)
                    self.episode += 1
                    prefix, outcomes, episode_return = [], [], 0.
                    queries = qualified_queries = 0
                    episode_checkpoint = adapter.bundle['metadata']['hashes']['checkpoint_sha256']
                    episode_mode = "autonomous" if self.mode == "student" else "human"
                    self._latest_view = None
                raw = env.raw()
                if raw is None:
                    env.close(); env = None
                    continue
                def publish(frame):
                    pixels = compact(pool(frame)).reshape(15, 15)*1.2-.6
                    h = history(prefix)*1.2-.6
                    self._publish_frame(frame, pixels, h)
                publish(raw)
                mode = self.mode
                view = adapter.predict(raw, prefix)
                queries += 1
                qualified_queries += int(view['qualified'])
                self.shadow_view = {k:v for k,v in view.items() if k != "inputs"}
                if (self.mode != mode or self.student.v2 is not adapter
                        or self.student._swapping or self.student._swap_request or self.reset_request):
                    continue
                if mode == "student":
                    if not view['qualified']:
                        adapter.error = "Query refused; play paused without executing a proposal"
                        self.set_mode("idle")
                        continue
                    action = view['action']
                else:
                    keys = self.keys_down
                    left = bool(keys & {"KeyA", "ArrowLeft"})
                    right = bool(keys & {"KeyD", "ArrowRight"})
                    fire = bool(keys & {"ControlLeft", "KeyJ", "Mouse"})
                    action = (1 if left and not right else 2 if right and not left else 0) + (3 if fire else 0)
                record = {"episode_id": f"browser-{self.session_id}-{generation}-{self.episode}-{seed}",
                          "session_id": self.session_id, "seed": seed, "step_index": len(prefix),
                          "inputs": view['inputs'], "raw_sha256": hashlib.sha256(raw.tobytes()).hexdigest(),
                          "prefix_actions": list(prefix), "prefix_outcomes": copy.deepcopy(outcomes),
                          "executed_action": int(action), "champion": adapter.version,
                          "learning_enabled": adapter.enabled and mode == "student",
                          "qualified": bool(view['qualified']), "fallback": False,
                          "behavior_source": "autonomous" if mode == "student" else "human",
                          "policy_checkpoint_sha256": adapter.bundle['metadata']['hashes']['checkpoint_sha256']}
                # Complete this acknowledged decision window even if the browser
                # requests pause/reset midway. No next decision begins afterwards.
                rewards = []
                for _ in range(12):
                    started = time.monotonic()
                    transition = env.step(int(action), 1, kind='browser')
                    rewards.extend(transition['rewards'])
                    frame = env.raw()
                    if frame is not None:
                        publish(frame)
                    if transition['terminal']:
                        break
                    self._stop.wait(max(0., 1/35 - (time.monotonic()-started)))
                transition = dict(reward=sum(rewards), rewards=rewards, tics=len(rewards),
                                  terminal=transition['terminal'], timeout=transition['timeout'])
                record['transition'] = transition
                prefix.append(int(action)); outcomes.append(transition)
                episode_return += transition['reward']
                adapter.acknowledge(record)
                self.game_stats = dict(health='–', ammo='–', kills=int(_basic_killed(outcomes)),
                                       reward=episode_return, seed=seed, qualified=view['qualified'], scenario='basic')
        finally:
            if env:
                adapter.last_episode = {"session_id": self.session_id, "seed": seed, "return": episode_return,
                                        "transitions": len(prefix), "terminal": env.game.is_episode_finished(),
                                        "killed": _basic_killed(outcomes),
                                        "queries": queries, "qualified_queries": qualified_queries,
                                        "policy_checkpoint_sha256": episode_checkpoint,
                                        "behavior_source": episode_mode,
                                        "tics": sum(o['tics'] for o in outcomes),
                                        "cutoff_reason": None if env.game.is_episode_finished() else
                                        "paused" if self.mode == "idle" else
                                        "model_change" if self.student.v2 is not adapter else "interrupted"}
                env.close()

    def _run_tics(self, lab, buttons, *, live_keys):
        """Advance FRAME_SKIP tics one by one at 35 Hz, publishing each frame."""
        for _ in range(FRAME_SKIP):
            tick = time.perf_counter()
            if lab.finished:
                return
            if live_keys:
                buttons = self._buttons_from_keys()
            lab.act(buttons, 1)
            self.student.acknowledge_buttons(buttons)
            state = lab.state()
            if state is not None:
                views = brain_view(state.screen_buffer)
                self._latest_view = views
                self._publish_frame(state.screen_buffer, *views)
            remaining = (1.0 / 35.0) - (time.perf_counter() - tick)
            if remaining > 0:
                time.sleep(remaining)

    def _shadow_loop(self):
        """Teacher-mode side panel: what would the student do right now?"""
        while not self._stop.is_set():
            if self.student.v2 is not None or self.mode != "teach" or self._latest_view is None:
                time.sleep(0.2)
                continue
            periphery, fovea = self._latest_view
            try:
                self.shadow_view = self.student.predict_buttons(periphery, fovea)
            except ValueError as error:
                self.shadow_view = {"error": str(error)}
            time.sleep(0.1)

    def close(self):
        self._stop.set()
        self.set_mode("idle")
        self._thread.join(timeout=5)
        return self.student.close()


# Multiprocessing spawn imports this module in child interpreters. Only the
# actual server process creates the Lab and its simulator/learner threads.
lab = None
routes = web.RouteTableDef()


@routes.get("/")
async def index(_):
    return web.FileResponse("static/index.html")


@routes.get("/state")
async def state(_):
    """Observe the HUD without joining the keyboard-owning WebSocket channel."""
    return web.json_response(lab.hud())


@routes.get("/decode")
async def decode_mode(request):
    mode = request.query.get("mode")
    if mode in ("raw", "cal", "top1"):
        lab.student.decode_mode = mode
    return web.json_response({
        "mode": lab.student.decode_mode,
        "calibrated": lab.student.calibration is not None,
    })


@routes.get("/training")
async def training(_):
    import glob as _glob
    import re as _re
    exports = []
    for meta_path in sorted(_glob.glob("data/models/doom-hero_b*.meta.json")):
        m = _re.search(r"_b(\d+)\.meta\.json$", meta_path)
        if not m:
            continue
        try:
            meta = json.load(open(meta_path))
        except ValueError:
            continue
        probe = meta.get("probe") or {}
        if probe.get("button_acc"):
            acc = probe["button_acc"]
            row = {
                "batches": int(m.group(1)),
                "rows": meta.get("rows"),
                "mean_acc": round(sum(acc) / len(acc), 3),
                "forward_acc": acc[0],
                "fire_acc": acc[3],
                "kill_mae": (probe.get("outcome_mae") or [None] * 3)[2],
                "refused": probe.get("refused", 0),
            }
            deep = meta.get("deep") or {}
            dp = deep.get("probe") or {}
            recalls = dp.get("pressed_recall") or []
            if recalls:
                known = [r for r in recalls if r is not None]
                row["forward_recall"] = recalls[0]
                row["mean_recall"] = round(sum(known) / len(known), 3) \
                    if known else None
                row["pressed_recall"] = recalls
                row["pred_press"] = dp.get("pred_press_rate")
                row["deep_refused"] = dp.get("refused")
                aucs = dp.get("auc") or []
                if aucs:
                    known = [a for a in aucs if a is not None]
                    row["forward_auc"] = aucs[0]
                    row["mean_auc"] = round(sum(known) / len(known), 3) \
                        if known else None
                cal = dp.get("cal_recall") or []
                if cal:
                    row["forward_cal_recall"] = cal[0]
                row["score_mean"] = dp.get("score_mean")
                row["thresholds"] = dp.get("thresholds")
            live = deep.get("live") or []
            if live:
                row["live_path"] = round(
                    sum(e["path"] for e in live) / len(live), 1)
                row["live_kills"] = round(
                    sum(e["kills"] for e in live) / len(live), 2)
                row["forward_rate"] = round(
                    sum(e["press_rate"]["forward"] for e in live)
                    / len(live), 3)
            exports.append(row)
    progress = {}
    try:
        text = open("data/hero_progress.log").read()
        lines = [l for l in text.splitlines() if l.startswith("batch ")]
        if lines:
            last = lines[-1].split()
            progress = {"line": lines[-1],
                        "batch": int(last[1]),
                        "rows": last[2].split("=")[1],
                        "eta_min": float(last[-1].replace("eta=", "")
                                         .replace("min", ""))}
            series = []
            for line in lines:
                try:
                    tail = line.split("sweeps=")[1].split()
                    series.append({
                        "batch": int(line.split()[1]),
                        "sweeps": int(tail[0]),
                        "seconds": float(tail[1].rstrip("s")),
                    })
                except (ValueError, IndexError):
                    continue
            progress["series"] = series
        if "FINAL" in text:
            progress["complete"] = True
    except (OSError, ValueError, IndexError):
        pass
    v2_status = None
    try:
        with open("data/v2_training_status.json") as stream:
            candidate = json.load(stream)
        if isinstance(candidate, dict) and candidate.get("schema") == "doom-v2-monitor/1":
            v2_status = candidate
    except (OSError, ValueError):
        pass
    adapter = lab.student.v2
    return web.json_response({"exports": exports, "progress": progress,
                              "v2": v2_status,
                              "online": adapter.status() if adapter else None})


@routes.get("/models")
async def models(_):
    return web.json_response({
        "models": lab.student.scan_models(),
        "current": lab.student.model_id,
    })


@routes.get("/export")
async def export(_):
    bundle = lab.student.export_bundle()
    date = bundle.get('exported', time.strftime('%Y-%m-%d', time.gmtime()))[:10]
    name = f"cadence-doom-{bundle['model_id']}-{date}.json"
    return web.json_response(bundle, headers={
        "Content-Disposition": f'attachment; filename="{name}"'})


@routes.post("/import")
async def import_brain(request):
    try:
        payload = await request.json()
        name = request.query.get("name", "imported")
        model_id = lab.student.import_bundle(name, payload)
        return web.json_response({"ok": True, "id": model_id})
    except (ValueError, KeyError, TypeError, RuntimeError) as error:
        return web.json_response({"ok": False, "error": str(error)},
                                 status=400)


@routes.get("/graph")
async def graph(_):
    return web.json_response(lab.student.graph_payload())


@routes.get("/video")
async def video(request):
    response = web.StreamResponse(headers={
        "Content-Type": "multipart/x-mixed-replace; boundary=frame",
        "Cache-Control": "no-store",
    })
    await response.prepare(request)
    seen = -1
    try:
        while True:
            with lab.lock:
                seq, frame = lab.frame_seq, lab.frame_jpeg
            if seq != seen and frame:
                seen = seq
                await response.write(
                    b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                    + frame + b"\r\n")
            await asyncio.sleep(0.015)
    except (ConnectionResetError, asyncio.CancelledError):
        return response


@routes.get("/ws")
async def websocket(request):
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)

    async def push():
        while not ws.closed:
            await ws.send_json({"type": "state", **lab.hud()})
            await asyncio.sleep(0.2)

    pusher = asyncio.create_task(push())
    try:
        async for message in ws:
            if message.type != WSMsgType.TEXT:
                continue
            data = json.loads(message.data)
            if data.get("type") == "keys":
                lab.keys_down = set(data.get("down", []))
            elif data.get("type") == "mode":
                lab.set_mode(data["mode"])
            elif data.get("type") == "reset":
                lab.reset_request = True
            elif data.get("type") == "model":
                ok = lab.student.request_swap(str(data.get("id", "")))
                await ws.send_json({"type": "model_ack", "ok": ok})
            elif data.get("type") == "learning":
                adapter = lab.student.v2
                try:
                    if adapter is None:
                        raise ValueError("Autonomous learning requires a Basic v2 model")
                    await asyncio.to_thread(adapter.set_enabled, bool(data.get("enabled")))
                    await ws.send_json({"type": "learning_ack", "ok": True})
                except (ValueError, RuntimeError, OSError, ImportError) as error:
                    await ws.send_json({"type": "learning_ack", "ok": False, "error": str(error)})
            elif data.get("type") == "rollback":
                adapter = lab.student.v2
                ok = bool(adapter and adapter.rollback())
                if ok:
                    lab.reset_request = True
                await ws.send_json({"type": "rollback_ack", "ok": ok})
            elif data.get("type") == "save":
                await ws.send_json(
                    {"type": "saved", **lab.student.save()})
    finally:
        pusher.cancel()
        lab.keys_down = set()
    return ws


async def on_shutdown(_):
    report = lab.close()
    print("shutdown:", report)


@web.middleware
async def no_static_cache(request, handler):
    response = await handler(request)
    if request.path.startswith("/static") or request.path == "/":
        response.headers["Cache-Control"] = "no-cache"
    return response


def main():
    global lab
    if lab is None:
        lab = Lab()
    app = web.Application(client_max_size=64 * 1024 * 1024,
                          middlewares=[no_static_cache])
    app.add_routes(routes)
    app.router.add_static("/static", "static")
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host="127.0.0.1", port=int(os.environ.get("DOOM_LAB_PORT", "8666")))


if __name__ == "__main__":
    main()
