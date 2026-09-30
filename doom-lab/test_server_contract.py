"""Pure read endpoints, coherent registry publication and actual browser control JS."""
import asyncio
import copy
import json
from pathlib import Path
import shutil
import subprocess
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from aiohttp.test_utils import TestClient, TestServer
import server
import brainlab

source = Path(__file__).resolve().parent/'server.py'


class Endpoints(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.payload = {'mode': 'student', 'model': {'id': 'unit'}, 'learning': {}}
        self.lab = SimpleNamespace(mode='student', hud=Mock(return_value=self.payload),
            student=SimpleNamespace(scan_models=lambda: [{'id': 'unit'}], model_id='unit'), close=Mock())
        self.client = TestClient(TestServer(server.create_app(self.lab)))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def test_state_is_pure_and_connect_disconnect_does_not_change_mode(self):
        for _ in range(3):
            response = await self.client.get('/state')
            self.assertEqual(await response.json(), self.payload)
        socket = await self.client.ws_connect('/ws')
        state = await socket.receive_json()
        self.assertEqual(state['mode'], 'student')
        await socket.close()
        self.assertEqual(self.lab.mode, 'student')
        self.assertEqual(self.payload, {'mode': 'student', 'model': {'id': 'unit'}, 'learning': {}})

    async def test_malformed_control_is_refused_without_closing_socket(self):
        socket = await self.client.ws_connect('/ws'); await socket.receive_json()
        await socket.send_str('{broken')
        reply = await socket.receive_json()
        self.assertFalse(reply['ok'])
        await socket.send_json({'type': 'keys', 'down': ['attack']})
        reply = await socket.receive_json()
        self.assertFalse(reply['ok'])
        self.assertEqual(self.lab.mode, 'student')
        await socket.close()


class RegistryConsistency(unittest.TestCase):
    def test_save_pins_model_identity_while_export_is_running(self):
        student = brainlab.Student.__new__(brainlab.Student)
        student.lock = threading.RLock(); student.model_id = 'old'; student.models_dir = Path('/unused')
        entered, allow, swapped = threading.Event(), threading.Event(), threading.Event()
        def exported():
            entered.set(); self.assertTrue(allow.wait(2))
            return {'hashes': {'checkpoint_sha256': 'old-hash'}}
        student.adapter = SimpleNamespace(export_bundle=exported)
        writes=[]
        with patch.object(brainlab, 'write_bundle', side_effect=lambda path,value:writes.append((path,value))):
            save=threading.Thread(target=student.save); save.start(); self.assertTrue(entered.wait(2))
            def swap():
                with student.lock:
                    student.model_id='new'; swapped.set()
            writer=threading.Thread(target=swap); writer.start()
            self.assertFalse(swapped.wait(.03)); allow.set(); save.join(2); writer.join(2)
        self.assertEqual(writes[0][0], Path('/unused/old/saved_export.json'))
        self.assertEqual(writes[0][1]['hashes']['checkpoint_sha256'], 'old-hash')
        self.assertEqual(student.model_id, 'new')


class BrowserModeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is needed to execute the browser control script')
    def test_connection_is_read_only_and_controls_follow_server_state(self):
        """Exercise the shipped script with two sockets, without a browser/server."""
        html = (source.parent/'static'/'index.html').read_text()
        script = html.split('<script>', 1)[1].split('</script>', 1)[0]
        harness = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const elements = new Map(), sockets = [], timers = [], sent = [];
let created = 0;
function element(id) {
  if (!elements.has(id)) {
    const classes = new Set();
    elements.set(id, {textContent: '', disabled: false, style: {}, dataset: {}, children: [],
      getBoundingClientRect: () => ({left:0,top:0,width:640,height:480}),
      classList: {add: x => classes.add(x), remove: x => classes.delete(x),
        contains: x => classes.has(x), toggle(x, force) {
          const on = force === undefined ? !classes.has(x) : force;
          if (on) classes.add(x); else classes.delete(x); return on;
        }}, addEventListener() {}, appendChild(value) {this.children.push(value);},
        replaceChildren(...values) {this.children = values;}});
  }
  return elements.get(id);
}
class Socket {
  constructor() { this.readyState = 0; sockets.push(this); }
  send(value) { sent.push(JSON.parse(value)); }
  open() { this.readyState = 1; this.onopen(); }
  close() { this.readyState = 3; this.onclose(); }
  state(mode, qualified = true) {
    this.onmessage({data: JSON.stringify({type: 'state', mode, episode: 1,
      shadow: {qualified}, learning: {available: false}})});
  }
}
const document = {getElementById: element, querySelector: element,
  createElement: () => element('created-'+(++created)), body: element('body')};
const context = {document, window: {addEventListener() {}},
  location: {host: 'unit.test', protocol: 'http:'}, WebSocket: Socket,
  fetch: async () => ({json: async () => ({models: []})}),
  setTimeout: fn => (timers.push(fn), timers.length), clearTimeout() {},
  setInterval() {}, clearInterval() {}, requestAnimationFrame() {},
  performance: {now: () => 0}, console};
vm.runInNewContext(SCRIPT, context);
const button = element('pause-btn');
function flushTimers() {
  let remaining = 20;
  while (timers.length && remaining-- > 0) timers.shift()();
  assert.ok(remaining > 0, 'Unexpected reconnect/timer loop');
}
const first = sockets[0];
first.open(); flushTimers();
assert.deepEqual(sent, [], 'Opening a tab must not alter the shared mode');
assert.equal(button.disabled, true, 'Wait for authoritative server mode');
first.state('idle');
assert.equal(button.disabled, false);
assert.equal(button.textContent, 'RESUME');
button.onclick();
assert.deepEqual(sent, [{type: 'mode', mode: 'student'}]);
first.state('student');
assert.equal(button.textContent, 'PAUSE');
first.state('idle'); // a different client paused it
assert.equal(button.textContent, 'RESUME');
first.close();
assert.equal(button.disabled, true);
button.onclick(); // disconnected clicks cannot queue a future mode mutation
assert.equal(sent.length, 1);
flushTimers();
const second = sockets[1];
second.open();
second.state('student'); // another client resumed while this tab was away
flushTimers();
assert.equal(sent.length, 1, 'Reconnection must not replay a stale pause/resume');
assert.equal(button.textContent, 'PAUSE');
first.state('idle'); // an old socket cannot overwrite the new connection's HUD
assert.equal(button.textContent, 'PAUSE');
button.onclick();
assert.deepEqual(sent[1], {type: 'mode', mode: 'idle'});
second.state('idle', false); // qualification refusal remains explicitly paused
assert.equal(button.textContent, 'RESUME');
assert.equal(button.classList.contains('active'), true);
context.renderFullGame({cloud_state: 'reachable', resources: {cpus: 64},
  browser_actor: {scenario: 'basic', model_id: 'current-basic', mode: 'student', champion: 4},
  runs: [{run: 'teacher_probe/e1m1', files: {'summary.json': {schema: 'doom-v3-teacher-result/1',
    outcome: {success: true, native_exit: true, tics: 200}}}}]});
assert.match(element('development-status').textContent, /Full-game development/);
assert.match(element('development-browser').textContent, /basic.*current-basic/);
assert.match(element('development-gates').textContent, /Full-game competence has not been demonstrated/);
const cells = element('development-runs').children[0].children[1].children.map(e => e.textContent);
assert.equal(cells[1], 'Teacher probe');
assert.equal(cells[3], 'native exit');
context.renderFullGame({cloud_state: 'reachable', resources: {}, runs: [{run: 'gpu_capacity_monitor',
  files: {'status.json': {schema: 'doom-v3-gpu-capacity-monitor/1', phase: 'experimental GPU capacity wave',
    candidates: [{name: '<deep>', status: 'running', updates: 12}],
    benchmark: {comparisons: [{size: 'small', repair_speedup: 4.5}]}}}}]});
const gpuCells = element('development-runs').children[0].children[1].children.map(e => e.textContent);
assert.equal(gpuCells[1], 'Experimental GPU capacity');
assert.match(gpuCells[2], /<deep>: running \(12 admissions\)/);
assert.match(gpuCells[2], /small repair benchmark 4.5× CPU\/GPU/);
assert.match(element('development-gates').textContent, /Full-game competence has not been demonstrated/);
context.renderFullGame({cloud_state: 'unknown', error: 'SSH unavailable', resources: {},
  task_gates: [{task_id: 'e1m1', scope: 'teacher', passed: true}]});
assert.match(element('development-status').textContent, /state unknown.*SSH unavailable/);
assert.match(element('development-gates').textContent, /teacher \/ e1m1: passed/);
assert.match(element('development-gates').textContent, /Teacher gates are not student competence/);
second.onmessage({data: JSON.stringify({type: 'state', mode: 'student', episode: 1,
  model: {id: 'v3-test', pending: true, scenario: 'basic', schema: 'cadence-doom-player-v3/1',
    deployment_validation: 'not_evaluated'},
  learning: {available: false, enabled: false, phase: 'frozen full-game actor'}})});
assert.match(element('learning-status').textContent, /^CADENCE v1.*not_evaluated/);
assert.equal(element('learn-btn').disabled, true);
second.onmessage({data: JSON.stringify({type: 'state', mode: 'student', episode: 2,
  model: {id: 'v3-sampled', pending: true, scenario: 'basic', schema: 'cadence-doom-player-v3/1'},
  learning: {available: true, enabled: true, phase: 'native_feedback', collection_stride: 32,
    selected_transitions: 3, intentionally_unsampled_transitions: 62}})});
assert.match(element('learning-status').textContent, /collect 1\/32/);
assert.equal(element('learn-btn').textContent, 'AUTOLEARN ON');
element('retina-btn').onclick();
context.placeRetinaBoxes();
assert.equal(element('periph-box').style.width, '640px');
assert.equal(element('periph-box').style.height, '480px');
assert.equal(element('fovea-box').style.left, '64px');
assert.equal(element('fovea-box').style.top, '96px');
assert.equal(element('fovea-box').style.width, '512px');
assert.equal(element('fovea-box').style.height, '288px');
context.window.BV.state = [99]; context.window.BV.errors = [99]; context.window.BV.buttons = [1];
context.onModelChange({id:'fresh',fingerprint:'fresh'});
assert.equal(context.window.BV.state, null);
assert.equal(context.window.BV.errors, null);
assert.equal(context.window.BV.buttons, null);
console.log('reconnect, retina and model-state controls passed');
'''.replace('SCRIPT', json.dumps(script))
        result = subprocess.run([shutil.which('node'), '-e', harness],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)



if __name__ == '__main__': unittest.main()
