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
import json
import queue
import random
import threading
import time

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


class Lab:
    def __init__(self):
        self.student = Student()
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
        self._thread = threading.Thread(target=self._game_loop, daemon=True)
        self._thread.start()
        self._shadow_thread = threading.Thread(
            target=self._shadow_loop, daemon=True)
        self._shadow_thread.start()
        self._latest_view = None
        self._decide_queue = queue.Queue(maxsize=1)
        self._decision = None
        self._decider = threading.Thread(target=self._decide_loop, daemon=True)
        self._decider.start()

    # ---- browser-facing state ----------------------------------------

    def set_mode(self, mode):
        assert mode in ("idle", "teach", "student")
        self.mode = mode
        self._mode_flag.set()

    def hud(self):
        pressed = sorted({KEYMAP[k] for k in self.keys_down if k in KEYMAP})
        recent = self.agreement[-60:]
        return {
            "mode": self.mode,
            "episode": self.episode,
            "game": self.game_stats,
            "trainer": dict(self.student.stats),
            "shadow": self.shadow_view,
            "pressed": pressed,
            "agreement": round(float(np.mean(recent)), 3) if recent else None,
            "buttons": list(BUTTONS),
            "brain_layout": self.student.layout_meta,
            "auto_resets": self.auto_resets,
            "model": {"id": self.student.model_id,
                      "pending": self.student._swap_request is not None,
                      **self.student.model_info},
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
            if lab is None:
                lab = DoomLab()
                lab.new_episode()
                self.episode += 1
            if self.reset_request:
                self.reset_request = False
                self._decision = None
                self._still_pos = self._still_since = None
                lab.new_episode()
                self.episode += 1
            if lab.finished:
                lab.new_episode()
                self.episode += 1
            state = lab.state()
            if state is None:
                lab.new_episode()
                self.episode += 1
                continue
            periphery, fovea = brain_view(state.screen_buffer)
            self._latest_view = (periphery, fovea)
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
                # Pipelined: hand this frame to the decider, act on the last
                # finished decision while these tics render at full rate.
                try:
                    self._decide_queue.put_nowait((periphery, fovea))
                except queue.Full:
                    pass
                decision = self._decision
                buttons = (decision["buttons"] if decision
                           else [0] * len(BUTTONS))
                self._run_tics(lab, buttons, live_keys=False)
            else:
                time.sleep(0.05)
        if lab is not None:
            lab.close()

    def _run_tics(self, lab, buttons, *, live_keys):
        """Advance FRAME_SKIP tics one by one at 35 Hz, publishing each frame."""
        for _ in range(FRAME_SKIP):
            tick = time.perf_counter()
            if lab.finished:
                return
            if live_keys:
                buttons = self._buttons_from_keys()
            lab.act(buttons, 1)
            state = lab.state()
            if state is not None:
                views = brain_view(state.screen_buffer)
                self._latest_view = views
                self._publish_frame(state.screen_buffer, *views)
            remaining = (1.0 / 35.0) - (time.perf_counter() - tick)
            if remaining > 0:
                time.sleep(remaining)

    def _decide_loop(self):
        """Student-mode brain: one settle behind the render, never blocking it."""
        last_ok = [0] * len(BUTTONS)
        while not self._stop.is_set():
            try:
                periphery, fovea = self._decide_queue.get(timeout=0.3)
            except queue.Empty:
                continue
            if self.mode != "student":
                continue
            try:
                view = self.student.predict_buttons(periphery, fovea)
            except ValueError as error:
                self.shadow_view = {"error": str(error)}
                continue
            if view["qualified"]:
                last_ok = view["buttons"]
            view["buttons"] = last_ok
            self.shadow_view = view
            self._decision = view

    def _shadow_loop(self):
        """Teacher-mode side panel: what would the student do right now?"""
        while not self._stop.is_set():
            if self.mode != "teach" or self._latest_view is None:
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


lab = Lab()
routes = web.RouteTableDef()


@routes.get("/")
async def index(_):
    return web.FileResponse("static/index.html")


@routes.get("/models")
async def models(_):
    return web.json_response({
        "models": lab.student.scan_models(),
        "current": lab.student.model_id,
    })


@routes.get("/export")
async def export(_):
    bundle = lab.student.export_bundle()
    name = f"cadence-doom-{bundle['model_id']}-{bundle['exported'][:10]}.json"
    return web.json_response(bundle, headers={
        "Content-Disposition": f'attachment; filename="{name}"'})


@routes.post("/import")
async def import_brain(request):
    try:
        payload = await request.json()
        name = request.query.get("name", "imported")
        model_id = lab.student.import_bundle(name, payload)
        return web.json_response({"ok": True, "id": model_id})
    except (ValueError, KeyError) as error:
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
    app = web.Application(client_max_size=64 * 1024 * 1024,
                          middlewares=[no_static_cache])
    app.add_routes(routes)
    app.router.add_static("/static", "static")
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host="127.0.0.1", port=8666)


if __name__ == "__main__":
    main()
