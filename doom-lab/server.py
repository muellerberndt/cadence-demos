"""Cadence Doom Lab v1: a settled visual actor and separately owned native practice.

The game thread alone executes actions. Browser connections observe current
state; only explicit controls change it. Imported models never enable learning.
"""
from __future__ import annotations

import asyncio
import base64
import collections
import io
import json
import os
from pathlib import Path
import random
import threading
import time
import uuid

import numpy as np
from aiohttp import WSMsgType, web
from PIL import Image

from brainlab import Student
from v1.interface import ACTION_NAMES

LAB_ROOT = Path(__file__).resolve().parent


class Lab:
    def __init__(self, *, data_dir=None, start_thread=True):
        self.student = Student(data_dir=data_dir)
        self.session_id = uuid.uuid4().hex
        self.mode = 'idle'
        self.frame_jpeg = b''
        self.frame_seq = 0
        self.retinas = ('', '')
        self.game_stats = {}
        self.shadow_view = {}
        self.episode = 0
        self.reset_request = False
        self.events = collections.deque(maxlen=100)
        self.events_seq = 0
        self._learning_counts = {}
        self.lock = threading.Lock()
        self.rng = random.Random(0)
        self._mode_flag = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._game_loop, daemon=True)
        if start_thread:
            self._thread.start()

    def set_mode(self, mode):
        if mode not in ('idle', 'student'):
            raise ValueError('The v1 Lab accepts idle or student mode; actions must come from the qualified actor')
        self.mode = mode
        self._mode_flag.set()

    def note_event(self, payload):
        """Append one live-feed event; the game thread and HUD readers share it."""
        with self.lock:
            self.events_seq += 1
            self.events.append({'seq': self.events_seq, 't': round(time.time(), 3), **payload})

    def _learning_events(self, learning):
        """Diff learner counters once, whichever HUD reader arrives first."""
        pending = []
        with self.lock:
            counts = self._learning_counts
            def moved(key):
                value, previous = learning.get(key), counts.get(key)
                counts[key] = value
                return previous is not None and isinstance(value, (int, float)) and value > previous
            if moved('accepted_updates'):
                pending.append({'kind': 'repair', 'updates': learning['accepted_updates']})
            if moved('promotions'):
                pending.append({'kind': 'promotion', 'promotions': learning['promotions'],
                                'champion': learning.get('champion')})
            gate = learning.get('last_gate')
            marker = json.dumps(gate, sort_keys=True, default=str) if gate else None
            if marker is not None and marker != counts.get('last_gate_marker'):
                pending.append({'kind': 'gate',
                                **{k: gate[k] for k in ('promote', 'rollback', 'reason') if k in gate}})
            counts['last_gate_marker'] = marker
            enabled = bool(learning.get('enabled'))
            if counts.get('enabled') is not None and enabled != counts['enabled']:
                pending.append({'kind': 'learning', 'enabled': enabled})
            counts['enabled'] = enabled
            for payload in pending:
                self.events_seq += 1
                self.events.append({'seq': self.events_seq, 't': round(time.time(), 3), **payload})

    def hud(self):
        with self.student.lock, self.student.adapter.lock:
            adapter = self.student.adapter
            learning = adapter.status()
            self._learning_events(learning)
            return {'mode': self.mode, 'session_id': self.session_id, 'episode': self.episode,
                'events': list(self.events),
                'game': dict(self.game_stats), 'learning': learning, 'shadow': self.shadow_view,
                'trainer': {'admitted': learning.get('accepted_examples', 0),
                            'queued': learning.get('queue_depth', 0), 'training': learning.get('busy', False)},
                'buttons': list(ACTION_NAMES), 'brain_layout': self.student.layout_meta,
                'model': {'id': self.student.model_id,
                    'pending': self.student._swapping or self.student._swap_request is not None,
                    'error': self.student.swap_error, **adapter.model_info},
                'retinas': {'periphery': self.retinas[0], 'fovea': self.retinas[1]}}

    def _publish_frame(self, screen, periphery, fovea):
        image = Image.fromarray(screen)
        buf = io.BytesIO(); image.save(buf, 'JPEG', quality=82)
        thumbs = None
        if self.frame_seq % 6 == 0:
            thumbs = []
            for retina in (periphery, fovea):
                gray = ((retina+.6)/1.2*255).clip(0, 255).astype(np.uint8)
                tb = io.BytesIO(); Image.fromarray(gray, 'L').save(tb, 'PNG')
                thumbs.append(base64.b64encode(tb.getvalue()).decode())
        with self.lock:
            self.frame_jpeg = buf.getvalue(); self.frame_seq += 1
            if thumbs is not None:
                self.retinas = tuple(thumbs)

    def _game_loop(self):
        while not self._stop.is_set():
            if self.student._swap_request is not None:
                self.student.apply_swap()
                self.shadow_view = {}
                self.reset_request = False
            if self.mode == 'idle':
                self._mode_flag.wait(timeout=.2); self._mode_flag.clear()
                continue
            try:
                self.student.adapter.run_session(self)
            except Exception as error:
                self.shadow_view = {'qualified': False, 'error': str(error)}
                self.game_stats = {'error': str(error)}
                self.set_mode('idle')

    def close(self):
        self._stop.set(); self._mode_flag.set()
        if self._thread.is_alive():
            self._thread.join(timeout=15)
        return self.student.close()


def owner(request):
    return request.app['lab']


routes = web.RouteTableDef()


@routes.get('/')
async def index(_):
    return web.FileResponse(LAB_ROOT/'static/index.html')


@routes.get('/state')
async def state(request):
    return web.json_response(owner(request).hud())


@routes.get('/training')
async def training(request):
    lab = owner(request)
    return web.json_response({'online': lab.student.adapter.status(), 'model': lab.hud()['model']})


@routes.get('/models')
async def models(request):
    student = owner(request).student
    return web.json_response({'models': student.scan_models(), 'current': student.model_id})


@routes.get('/export')
async def export(request):
    student = owner(request).student
    return web.json_response(student.export_bundle(), headers={
        'Content-Disposition': f'attachment; filename="cadence-doom-{student.model_id}.json"'})


@routes.post('/import')
async def import_brain(request):
    try:
        payload = await request.json()
        model_id = await asyncio.to_thread(owner(request).student.import_bundle,
                                            request.query.get('name', 'imported'), payload)
        return web.json_response({'ok': True, 'id': model_id})
    except (ValueError, KeyError, TypeError, RuntimeError, OSError) as error:
        return web.json_response({'ok': False, 'error': str(error)}, status=400)


@routes.get('/graph')
async def graph(request):
    return web.json_response(owner(request).student.graph_payload())


@routes.get('/video')
async def video(request):
    lab = owner(request)
    response = web.StreamResponse(headers={'Content-Type': 'multipart/x-mixed-replace; boundary=frame',
                                           'Cache-Control': 'no-store'})
    await response.prepare(request)
    seen = -1
    try:
        while not lab._stop.is_set():
            with lab.lock:
                seq, frame = lab.frame_seq, lab.frame_jpeg
            if seq != seen and frame:
                seen = seq
                await response.write(b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'+frame+b'\r\n')
            await asyncio.sleep(.015)
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    return response


@routes.get('/ws')
async def websocket(request):
    lab = owner(request)
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    async def push():
        while not ws.closed:
            await ws.send_json({'type': 'state', **lab.hud()})
            await asyncio.sleep(.2)
    pusher = asyncio.create_task(push())
    try:
        async for message in ws:
            if message.type != WSMsgType.TEXT:
                continue
            kind = 'error'
            try:
                data = json.loads(message.data)
                kind = data.get('type', 'error')
                if kind == 'mode':
                    lab.set_mode(data['mode'])
                elif kind == 'reset':
                    lab.reset_request = True
                elif kind == 'model':
                    ok = lab.student.request_swap(str(data.get('id', '')))
                    lab._mode_flag.set()
                    await ws.send_json({'type': 'model_ack', 'ok': ok})
                elif kind == 'learning':
                    adapter = lab.student.adapter
                    await asyncio.to_thread(adapter.set_enabled, bool(data.get('enabled')))
                    await ws.send_json({'type': 'learning_ack', 'ok': True})
                elif kind == 'rollback':
                    ok = await asyncio.to_thread(lab.student.adapter.rollback)
                    if ok:
                        lab.reset_request = True
                    await ws.send_json({'type': 'rollback_ack', 'ok': bool(ok)})
                elif kind == 'save':
                    await ws.send_json({'type': 'saved', **await asyncio.to_thread(lab.student.save)})
                else:
                    raise ValueError('Unknown control: '+str(kind))
            except (ValueError, KeyError, TypeError, RuntimeError, OSError, ImportError) as error:
                await ws.send_json({'type': kind+'_ack', 'ok': False, 'error': str(error)})
    finally:
        pusher.cancel()
        await asyncio.gather(pusher, return_exceptions=True)
    return ws


@web.middleware
async def no_static_cache(request, handler):
    response = await handler(request)
    if request.path.startswith('/static') or request.path in ('/', '/state', '/training', '/models'):
        response.headers['Cache-Control'] = 'no-cache'
    return response


def create_app(lab):
    app = web.Application(client_max_size=64*1024*1024, middlewares=[no_static_cache])
    app['lab'] = lab
    app.add_routes(routes)
    app.router.add_static('/static', LAB_ROOT/'static')
    async def shutdown(_):
        print('shutdown:', await asyncio.to_thread(lab.close))
    app.on_shutdown.append(shutdown)
    return app


def main():
    lab = Lab()
    web.run_app(create_app(lab), host='127.0.0.1', port=int(os.environ.get('DOOM_LAB_PORT', '8666')))


if __name__ == '__main__':
    main()
