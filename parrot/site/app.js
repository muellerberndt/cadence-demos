// The page: the room, the parrot on its perch, the things the visitor places, the two eyes, and the
// loop that gives the brain (in the worker) each moment's two images and joint readings and moves
// the joints toward the targets it sends back.
import * as THREE from 'three';
import { OrbitControls } from './vendor/three/jsm/controls/OrbitControls.js';
import { makeRenderer, Room, BAR_Y, KINDS, TABLE } from './scene.js';
import { loadRig } from './parrot.js';
import { Eyes, EYE } from './eyes.js';
import { BrainView } from './brainview.js';
import { Brain3D } from './brain3d.js';
import { ParrotAudio } from './audio.js';
import { MemoryView } from './memview.js';
import { Pistachio } from './pistachio.js';
import { lookList, makeParrot } from './looks.js';

const $ = (id) => document.getElementById(id);
const query = new URLSearchParams(location.search);
const MOMENT_MS = 100; // the brain's moment: ten a second
const ui = {
  status: $('status'), statusText: $('status-text'), coach: $('coach'), coachStep: $('coach-step'), coachText: $('coach-text'), toast: $('toast'),
  sub: $('brain-sub'), moment: $('s-moment'), think: $('s-think'), fps: $('s-fps'), tags: $('tags'),
  eyeL: $('eye-l'), eyeR: $('eye-r'), fields: $('fields'), palette: $('palette'), looks: $('looks'), mode: $('mode'),
  test: $('test'), clear: $('clear'), pistachio: $('pistachio'), pistachios: $('pistachios'), silence: $('silence'), drawer: $('drawer'),
  mic: $('mic'), driveLevel: $('drive-level'), turns: $('turns'), turnNote: $('turn-note'), sounds: $('sounds'), forget: $('forget'), earLevel: $('ear-level'), earBands: $('ear-bands'), voiceLevel: $('voice-level'), voiceNote: $('voice-note'),
};
const state = { phase: 'loading', mode: 'brain', look: null, moment: 0, brainReady: false, pending: false, lastStep: 0, reward: 0, pistachios: 0,
  silenced: false, subject: null, dragging: null, script: null, thinkMs: [], frameTimes: [], fps: 0, coach: null };
let rig, parrot, eyes, view, brain, desc, brain3d, memview;
const audio = new ParrotAudio();

function setStatus(text, kind = 'busy') { ui.statusText.textContent = text; ui.status.className = `status ${kind}`; }
let toastTimer = null;
function toast(text, kind = '', ms = 2200) {
  ui.toast.textContent = text; ui.toast.className = `toast ${kind}`; ui.toast.hidden = false;
  clearTimeout(toastTimer);
  if (ms) toastTimer = setTimeout(() => { ui.toast.hidden = true; }, ms);
}

// --- the coach: one line that says what to do next ---------------------------------------------
const COACH = {
  loading: ['', 'The room, the parrot and its brain are loading in your browser.'],
  idle: ['Try it', 'Drag a <b>thing</b> on the table, or add one below. The parrot’s two eyes (right) see it.'],
  dragging: ['Watch', 'Move it nearer or further: the <b>distance</b> neurons (right) answer.'],
  behind: ['Watch', 'Behind the parrot is its blind spot: neither eye sees there.'],
  script: ['Test', 'A test runs: things are placed round the parrot, one after another.'],
  manual: ['Your turn', 'You move the parrot: use the sliders. Its brain keeps seeing, and its moves wait.'],
};
function coachKey() {
  if (!state.brainReady && state.phase === 'loading') return 'loading';
  if (state.script) return 'script';
  if (state.mode === 'you') return 'manual';
  if (state.dragging) return state.behind ? 'behind' : 'dragging';
  return 'idle';
}
function updateCoach() {
  const key = coachKey();
  if (key === state.coach) return;
  state.coach = key;
  const [step, html] = COACH[key];
  ui.coachStep.textContent = step; ui.coachText.innerHTML = html;
  document.body.dataset.coach = key;
}

// --- the brain worker --------------------------------------------------------------------------
const PACK = new URL(document.querySelector('meta[name="cadence-pack"]')?.content || 'pack/', document.baseURI).href;
class BrainWorker {
  constructor() {
    this.worker = new Worker(new URL('./worker.js', import.meta.url), { type: 'module' });
    this.rid = 0; this.pending = new Map();
    this.worker.onmessage = ({ data }) => {
      if (data.status) { if (!state.brainReady) setStatus(data.status, 'busy'); return; }
      const p = this.pending.get(data.rid);
      if (!p) return;
      this.pending.delete(data.rid);
      if (data.error) p.reject(new Error(data.error)); else p.resolve({ ...data.result, arrays: data.arrays || {} });
    };
  }
  call(command, payload, transfer = []) {
    const rid = ++this.rid;
    return new Promise((resolve, reject) => { this.pending.set(rid, { resolve, reject }); this.worker.postMessage({ rid, command, payload }, transfer); });
  }
}

// --- three.js ----------------------------------------------------------------------------------
const canvas = $('scene');
const renderer = makeRenderer(canvas);
const room = new Room(renderer);
const camera = new THREE.PerspectiveCamera(32, 1, 0.01, 40);
const controls = new OrbitControls(camera, canvas);
const HOME = { pos: new THREE.Vector3(0.78, BAR_Y + 0.62, 1.18), at: new THREE.Vector3(0, BAR_Y - 0.03, 0.04) };
const VIEWS = { // named views for the page's checks and the help page's figures (?view=)
  front: [[0.03, BAR_Y + 0.15, 0.62], [0, BAR_Y + 0.09, 0]], side: [[0.62, BAR_Y + 0.15, 0.06], [0, BAR_Y + 0.09, 0]],
  head: [[0.13, BAR_Y + 0.25, 0.30], [0, BAR_Y + 0.205, 0.03]], feet: [[0.10, BAR_Y + 0.06, 0.26], [0, BAR_Y, 0]],
  back: [[-0.2, BAR_Y + 0.2, -0.6], [0, BAR_Y + 0.08, 0]],
};
if (VIEWS[query.get('view')]) { HOME.pos.set(...VIEWS[query.get('view')][0]); HOME.at.set(...VIEWS[query.get('view')][1]); }
camera.position.copy(HOME.pos); controls.target.copy(HOME.at);
controls.enableDamping = true; controls.minDistance = 0.25; controls.maxDistance = 3.2; controls.maxPolarAngle = Math.PI * 0.49;
controls.update();

function resize() {
  const stage = $('stage'), w = stage.clientWidth, h = stage.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.fov = w / h < 0.9 ? 44 : 32;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe($('stage'));

// --- things: names over them, dragging, adding ----------------------------------------------------
const tags = new Map();
function tagFor(id, kind) {
  if (tags.has(id)) return tags.get(id);
  const el = document.createElement('span');
  el.className = 'tag'; el.dataset.thing = id;
  el.setAttribute('data-explain-title', `The ${KINDS[kind].label}`);
  el.setAttribute('data-explain', `A ${KINDS[kind].label} at its real size. Drag it on the table: the parrot’s eyes see it move. Its distance from the parrot’s eyes is the page’s measure, for the curves on the right; the brain is never told it.`);
  const t = document.createElement('span'); t.className = 't'; t.textContent = KINDS[kind].label;
  el.append(t); ui.tags.append(el); tags.set(id, el);
  return el;
}
const tagPoint = new THREE.Vector3();
function syncTags() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  for (const [id, el] of tags) {
    const t = room.things.get(id);
    if (!t) { el.remove(); tags.delete(id); continue; }
    tagPoint.copy(t.obj.position); tagPoint.y += KINDS[t.kind].size + 0.02;
    tagPoint.project(camera);
    if (tagPoint.z > 1) { el.hidden = true; continue; }
    el.hidden = false;
    el.style.transform = `translate(${Math.round((tagPoint.x + 1) / 2 * w)}px, ${Math.round((1 - tagPoint.y) / 2 * h) - 4}px) translate(-50%, -100%)`;
    el.classList.toggle('subject', state.subject === id);
    const d = distanceOf(id);
    const text = `${KINDS[t.kind].label} · ${Math.round(d * 100)} cm`;
    if (el.firstChild.textContent !== text) el.firstChild.textContent = text;
  }
}

const eyesMid = new THREE.Vector3(), tmpA = new THREE.Vector3(), tmpQ = new THREE.Quaternion();
function eyesMidpoint() {
  parrot.eyePose('eye_l', eyesMid, tmpQ); parrot.eyePose('eye_r', tmpA, tmpQ);
  return eyesMid.add(tmpA).multiplyScalar(0.5);
}
/** The true distance (m) from the eyes' midpoint to a thing's middle: the page's measure, never the brain's input. */
function distanceOf(id) {
  const t = room.things.get(id);
  if (!t || !parrot) return null;
  const c = t.obj.position.clone(); c.y += KINDS[t.kind].size / 2;
  return c.distanceTo(eyesMidpoint());
}

async function place(kind, x, z, yaw = 0, id = null) {
  const made = await room.place(kind, x, z, yaw, id);
  tagFor(made, kind);
  return made;
}
async function addThing(kind) {
  // somewhere free in front of the parrot or beside it
  for (let i = 0; i < 60; i++) {
    const a = (Math.random() - 0.5) * Math.PI * 1.2, r = 0.2 + Math.random() * 0.35;
    const x = Math.sin(a) * r, z = Math.cos(a) * r;
    if ([...room.things.values()].every((t) => Math.hypot(t.obj.position.x - x, t.obj.position.z - z) > 0.12)) {
      const id = await place(kind, x, z, Math.random() * 360);
      state.subject = id; view?.clearTuning();
      return id;
    }
  }
  return null;
}

const raycaster = new THREE.Raycaster(), pointer = new THREE.Vector2(), tablePlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
function pick(e) {
  const r = canvas.getBoundingClientRect();
  pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  raycaster.setFromCamera(pointer, camera);
}
function onTable(e) { pick(e); const p = new THREE.Vector3(); return raycaster.ray.intersectPlane(tablePlane, p) ? p : null; }
canvas.addEventListener('pointerdown', (e) => {
  if (!parrot) return;
  pick(e);
  const hit = raycaster.intersectObjects(room.pickables, false)[0];
  if (!hit) return;
  const id = hit.object.userData.thing, t = room.things.get(id), p = onTable(e);
  if (!t || !p) return;
  if (state.subject !== id) view?.clearTuning();
  state.subject = id;
  state.dragging = { id, dx: t.obj.position.x - p.x, dz: t.obj.position.z - p.z, x0: e.clientX, y0: e.clientY, moved: false };
  controls.enabled = false;
  canvas.setPointerCapture(e.pointerId);
  canvas.classList.add('dragging');
});
canvas.addEventListener('pointermove', (e) => {
  if (!parrot) return;
  if (!state.dragging) { pick(e); canvas.classList.toggle('over', raycaster.intersectObjects(room.pickables, false).length > 0); return; }
  const p = onTable(e);
  if (!p) return;
  if (Math.hypot(e.clientX - state.dragging.x0, e.clientY - state.dragging.y0) > 4) state.dragging.moved = true;
  if (!state.dragging.moved) return;
  room.move(state.dragging.id, p.x + state.dragging.dx, p.z + state.dragging.dz);
  const pos = room.things.get(state.dragging.id).obj.position;
  state.behind = pos.z < -0.08 && Math.abs(Math.atan2(pos.x, -pos.z)) < 0.35;
});
// A click on a thing (no drag) points the parrot at it: the brain gets where it lies from the
// head (azimuth and elevation in the head's frame) as a cue, and its focus goes there.
function cueFor(id) {
  const t = room.things.get(id);
  if (!t || !parrot) return null;
  const head = parrot.bones.head, hp = new THREE.Vector3(), hq = new THREE.Quaternion();
  head.getWorldPosition(hp); head.getWorldQuaternion(hq);
  const c = t.obj.position.clone(); c.y += KINDS[t.kind].size / 2;
  const d = c.sub(hp).applyQuaternion(hq.invert());
  return { az: +(Math.atan2(d.x, d.z) * 180 / Math.PI).toFixed(1), el: +(Math.atan2(d.y, Math.hypot(d.x, d.z)) * 180 / Math.PI).toFixed(1), id };
}
function endDrag(e) {
  if (!state.dragging) return;
  if (!state.dragging.moved) { state.cue = cueFor(state.dragging.id); state.focus = { id: state.dragging.id, why: 'you pointed at it' }; }
  state.dragging = null; state.behind = false;
  controls.enabled = true; canvas.classList.remove('dragging');
  if (e?.pointerId !== undefined && canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId);
}
canvas.addEventListener('pointerup', endDrag);
canvas.addEventListener('pointercancel', endDrag);

// --- the scripted placements: the experiment's tests (INTERFACES P4) ---------------------------------
const TEST = [
  { at: 0, clear: true },
  { at: 0.2, place: { id: 'apple-t', kind: 'apple', x: 0.0, z: 0.22 } },
  { at: 3, move: { id: 'apple-t', x: 0.0, z: 0.4 } },
  { at: 6, move: { id: 'apple-t', x: 0.0, z: 0.6 } },
  { at: 9, place: { id: 'ball-t', kind: 'ball', x: 0.35, z: 0.1 } },
  { at: 12, place: { id: 'cup-t', kind: 'cup', x: -0.3, z: 0.05, yaw: 120 } },
  { at: 15, move: { id: 'apple-t', x: 0.05, z: -0.35 } },
  { at: 18, place: { id: 'block-t', kind: 'block', x: -0.2, z: 0.3, yaw: 20 } },
  { at: 21, move: { id: 'ball-t', x: 0.15, z: 0.18 } },
  { at: 24, end: true },
];
async function runScript(list) {
  const token = {};
  state.script = token; ui.test.textContent = 'Stop test'; ui.test.setAttribute('aria-pressed', 'true');
  const start = performance.now();
  for (const step of list) {
    const wait = start + step.at * 1000 - performance.now();
    if (wait > 0) await new Promise((r) => setTimeout(r, wait));
    if (state.script !== token) return;
    if (step.clear) { room.clear(); view?.clearTuning(); }
    if (step.place) { const s = step.place; await place(s.kind, s.x, s.z, s.yaw || 0, s.id); state.subject = s.id; }
    if (step.move) { room.move(step.move.id, step.move.x, step.move.z, step.move.yaw ?? null); state.subject = step.move.id; }
    if (step.remove) room.remove(step.remove.id);
  }
  if (state.script === token) { state.script = null; ui.test.textContent = 'Test run'; ui.test.setAttribute('aria-pressed', 'false'); }
}

// --- the brain's moment ------------------------------------------------------------------------------
const proprio = new Float32Array(22);
async function moment(now) {
  eyes.render();
  eyes.draw('left', ui.eyeL); eyes.draw('right', ui.eyeR);
  if (!state.brainReady || state.pending) return;
  state.pending = true; state.lastStep = now;
  parrot.joints.proprio(proprio);
  const left = eyes.left.rgb.slice(), right = eyes.right.rgb.slice(), pro = proprio.slice();
  const reward = state.reward; state.reward = 0;
  const sound = audio.moment();
  const cue = state.cue; state.cue = null;
  const voiceOk = !!audio.ctx && audio.ctx.state === 'running';
  let reply;
  try {
    const focusKind = state.focus ? room.things.get(state.focus.id)?.kind || null : null;
    reply = await brain.call('step', { meta: { t: state.moment, reward, voice_ok: voiceOk, cue, things: room.things.size, focus_kind: focusKind }, arrays: { left, right, proprio: pro, mel: sound.mel, audio: sound.audio } },
      [left.buffer, right.buffer, pro.buffer, sound.mel.buffer, sound.audio.buffer]);
  } catch (error) { state.pending = false; setStatus(`The brain stopped: ${error.message}`, 'error'); state.brainReady = false; return; }
  state.pending = false;
  state.moment += 1;
  state.lastReply = reply;
  if (state.mode === 'brain' && reply.arrays.targets) parrot.joints.setUnitTargets(reply.arrays.targets);
  const subject = state.subject ? distanceOf(state.subject) : null;
  view.update(reply, reply.arrays, subject);
  brain3d?.update(reply.arrays.activity);
  if (reply.arrays.voice?.length) { // the voice motor's frames: the parrot says them
    const spoken = audio.speak(reply.arrays.voice);
    const what = reply.said ? (reply.said.source === 'you' ? 'a sound learned from you' : reply.said.source === 'recording' ? `a ${reply.said.tag}` : 'a babble') : 'a sound';
    if (spoken) { ui.voiceNote.textContent = `${what}, ${(spoken.env.length / 100).toFixed(1)} s`; state.saying = reply.said?.id; markChip(reply.said?.id); }
  }
  if (reply.drive !== undefined) ui.driveLevel.style.width = `${Math.round(reply.drive * 100)}%`;
  if (reply.memory) memview?.update(reply.memory);
  if (reply.repertoire) syncChips(reply.repertoire);
  if (reply.heard_sound) saveMemory();
  if (reply.paid) for (const [id] of Object.entries(reply.paid)) ui.sounds.querySelector(`[data-sound="${id}"]`)?.classList.add('paid');
  // the focus the brain reports: the thing nearest the direction it turned to
  const key = reply.focus ? `${reply.focus.az},${reply.focus.el}` : null;
  if (key !== state.focusKey) { state.focusKey = key; state.focus = reply.focus ? focusFrom(reply.focus) : null; }
  state.thinkMs.push(reply.worker_ms); if (state.thinkMs.length > 50) state.thinkMs.shift();
  ui.moment.textContent = String(state.moment);
  ui.think.textContent = `${Math.round(median(state.thinkMs))} ms`;
  document.body.dataset.moment = String(state.moment);
}
// The brain's focus is a direction from the head (at the moment it chose it); the page names the
// thing that lies nearest that direction, within 25 degrees.
function focusFrom(f) {
  const head = parrot.bones.head, hp = new THREE.Vector3(), hq = new THREE.Quaternion();
  head.getWorldPosition(hp); head.getWorldQuaternion(hq);
  const a = f.az * Math.PI / 180, e = f.el * Math.PI / 180;
  const ray = new THREE.Vector3(Math.sin(a) * Math.cos(e), Math.sin(e), Math.cos(a) * Math.cos(e)).applyQuaternion(hq);
  let best = null;
  for (const t of room.things.values()) {
    const c = t.obj.position.clone(); c.y += KINDS[t.kind].size / 2;
    const miss = c.sub(hp).normalize().angleTo(ray) * 180 / Math.PI;
    if (!best || miss < best.miss) best = { id: t.id, miss, why: f.why || 'it stood out most' };
  }
  return best && best.miss < 25 ? best : null;
}
const median = (a) => { const s = [...a].sort((x, y) => x - y); return s.length ? s[s.length >> 1] : 0; };

// --- the ear's bands, and the focus ring --------------------------------------------------------------
function drawBands() {
  const c = ui.earBands, g = c.getContext('2d'), f = audio.frames[audio.frames.length - 1];
  const img = g.createImageData(40, 1);
  for (let m = 0; m < 40; m++) {
    const v = f && audio.mic ? Math.max(0, Math.min(1, (f[m] + 9) / 12)) : 0;
    img.data[4 * m] = 30 + 49 * v * 2.5; img.data[4 * m + 1] = 34 + 161 * v; img.data[4 * m + 2] = 44 + 203 * v; img.data[4 * m + 3] = 255;
  }
  g.putImageData(img, 0, 0);
}
const ring = new THREE.Mesh(new THREE.RingGeometry(0.5, 0.62, 48), new THREE.MeshBasicMaterial({ color: '#f2b33d', transparent: true, opacity: 0.0, depthWrite: false, side: THREE.DoubleSide }));
ring.rotation.x = -Math.PI / 2; ring.renderOrder = 2;
let focusTag = null;
function placeFocus() {
  if (!ring.parent) room.scene.add(ring);
  const f = state.focus, t = f ? room.things.get(f.id) : null;
  const want = t ? 0.75 : 0;
  ring.material.opacity += (want - ring.material.opacity) * 0.15;
  if (!focusTag) {
    focusTag = document.createElement('span'); focusTag.className = 'focus-tag'; focusTag.textContent = 'focus';
    focusTag.setAttribute('data-explain-title', 'Its focus');
    ui.tags.append(focusTag);
  }
  if (!t) { focusTag.hidden = true; return; }
  const size = KINDS[t.kind].size;
  ring.position.set(t.obj.position.x, 0.002, t.obj.position.z); ring.scale.setScalar(size * 0.85 + 0.03);
  focusTag.setAttribute('data-explain', `The one thing the parrot attends to now. Its head turns to it, and it is what a heard word is linked to. It won because ${f.why}.`);
  const v = new THREE.Vector3(t.obj.position.x, 0.0, t.obj.position.z + size * 0.6 + 0.02).project(camera);
  focusTag.hidden = v.z > 1;
  focusTag.style.transform = `translate(${Math.round((v.x + 1) / 2 * canvas.clientWidth)}px, ${Math.round((1 - v.y) / 2 * canvas.clientHeight)}px) translate(-50%, 0)`;
}

// --- its sounds: the repertoire's chips, what it learned from you (kept in this browser), the turns
// The library's stores, kept in this browser between visits (the records' values and depths, and
// the consolidated synapses), so the parrot remembers the visitor.
const learnedStore = {
  get() { try { return JSON.parse(localStorage.getItem('parrot.memory') || 'null'); } catch (e) { return null; } },
  set(saved) { try { localStorage.setItem('parrot.memory', JSON.stringify(saved)); } catch (e) { /* storage blocked: it forgets on leaving */ } },
  clear() { try { localStorage.removeItem('parrot.memory'); } catch (e) { /* storage blocked */ } },
};
let saving = false;
async function saveMemory() {
  if (saving || !state.brainReady) return;
  saving = true;
  try { const out = await brain.call('memory'); learnedStore.set(out.saved); } finally { saving = false; }
}
function syncChips(list) {
  const ids = new Set(list.map((r) => r.id));
  for (const c of ui.sounds.querySelectorAll('.chip-s.you')) if (!ids.has(c.dataset.sound)) c.remove();
  for (const r of list) {
    addChip(r);
    const c = ui.sounds.querySelector(`[data-sound="${r.id}"]`);
    if (c && r.deep !== undefined) { c.querySelector('.deep i').style.width = `${Math.round(Math.min(1, r.deep / 10) * 100)}%`; c.title = `learned from you: depth ${r.deep.toFixed(1)}`; if (r.frames) soundFrames.set(r.id, Float32Array.from(r.frames)); }
  }
  ui.forget.hidden = !ui.sounds.querySelector('.chip-s.you');
}
function spectro(frames, canvas) {
  const n = frames.length / 40, g = canvas.getContext('2d'); canvas.width = Math.max(1, Math.min(48, n)); canvas.height = 20;
  const img = g.createImageData(canvas.width, 20);
  for (let x = 0; x < canvas.width; x++) for (let y = 0; y < 20; y++) {
    const f = Math.floor((x / canvas.width) * n), m = 39 - y * 2, v = Math.max(0, Math.min(1, (frames[f * 40 + m] + 9) / 13));
    const k = 4 * (y * canvas.width + x); img.data[k] = 30 + 200 * v; img.data[k + 1] = 34 + 170 * v; img.data[k + 2] = 44 + 120 * v; img.data[k + 3] = 255;
  }
  g.putImageData(img, 0, 0);
}
const soundFrames = new Map();
function addChip(r) {
  if (ui.sounds.querySelector(`[data-sound="${r.id}"]`)) return;
  const b = document.createElement('button'); b.className = `chip-s ${r.source === 'you' ? 'you' : ''} ${r.paid ? 'paid' : ''}`; b.dataset.sound = r.id;
  b.title = r.source === 'recording' ? `${r.tag}: an African Grey call from a recording` : r.source === 'you' ? 'learned from you' : 'its own babble';
  if (r.frames) { const c = document.createElement('canvas'); spectro(r.frames, c); b.append(c); soundFrames.set(r.id, Float32Array.from(r.frames)); }
  b.append(document.createTextNode(r.source === 'you' ? 'from you' : r.tag));
  if (r.source === 'you') { const d = document.createElement('span'); d.className = 'deep'; d.append(document.createElement('i')); b.append(d); }
  b.addEventListener('click', async () => { await audio.unlock(); const f = soundFrames.get(r.id); if (f) { audio.speak(f); markChip(r.id); ui.voiceNote.textContent = `${b.title} (you played it)`; } });
  ui.sounds.append(b);
  if (r.source === 'you') ui.forget.hidden = false;
}
function markChip(id) {
  for (const c of ui.sounds.querySelectorAll('.chip-s')) c.classList.toggle('playing', c.dataset.sound === id);
  setTimeout(() => ui.sounds.querySelector(`[data-sound="${id}"]`)?.classList.remove('playing'), 1500);
}
ui.forget.addEventListener('click', async () => {
  learnedStore.clear();
  for (const c of ui.sounds.querySelectorAll('.chip-s.you')) c.remove();
  ui.forget.hidden = true;
  if (state.brainReady) { const out = await brain.call('forget'); memview?.update(out.memory); }
  toast('It forgot the sounds it learned from you', '', 2000);
});
// whose turn: the last eight seconds of your sound and its sound, and how the last turn went
const turnLog = [];
function drawTurns(now) {
  const you = audio.mic && audio.level > 0.12, it = audio.loudness(now) > 0.06;
  turnLog.push({ t: now, you, it }); while (turnLog.length && turnLog[0].t < now - 8000) turnLog.shift();
  const c = ui.turns, W = c.clientWidth, H = c.clientHeight, dpr = Math.min(window.devicePixelRatio || 1, 1.5);
  if (c.width !== Math.round(W * dpr)) { c.width = Math.round(W * dpr); c.height = Math.round(H * dpr); }
  const g = c.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
  g.fillStyle = '#1f242b'; g.fillRect(34, 3, W - 34, 8); g.fillRect(34, 15, W - 34, 8);
  g.fillStyle = '#6c7583'; g.font = '500 9px "IBM Plex Mono", monospace'; g.fillText('you', 0, 10); g.fillText('parrot', 0, 22);
  for (const e of turnLog) {
    const x = 34 + ((e.t - (now - 8000)) / 8000) * (W - 34);
    if (e.you) { g.fillStyle = '#4fc3f7'; g.fillRect(x, 3, 2, 8); }
    if (e.it) { g.fillStyle = '#d23a3a'; g.fillRect(x, 15, 2, 8); }
  }
  // the last turn: your sound's end, and the parrot's sound in the 1.5 s after it, during it, or none
  let end = null, start = null;
  for (let i = turnLog.length - 1; i > 0; i--) { if (!turnLog[i].you && turnLog[i - 1].you) { end = turnLog[i].t; break; } }
  if (end !== null) {
    for (let i = turnLog.length - 1; i >= 0 && turnLog[i].t >= end - 3000; i--) if (turnLog[i].you) { start = turnLog[i].t; }
    const during = turnLog.some((e) => e.it && e.you);
    const after = turnLog.some((e) => e.it && e.t > end && e.t <= end + 1500);
    const note = during ? 'it spoke over you' : after ? 'it answered in the gap after you' : now - end > 1500 ? 'it stayed quiet after you' : '';
    if (note && ui.turnNote.textContent !== note) ui.turnNote.textContent = note;
  }
}

// --- the fields of view, seen from above ----------------------------------------------------------------
function drawFields() {
  const c = ui.fields, g = c.getContext('2d');
  const W = c.clientWidth, H = c.clientHeight, dpr = Math.min(window.devicePixelRatio || 1, 1.5);
  if (c.width !== Math.round(W * dpr)) { c.width = Math.round(W * dpr); c.height = Math.round(H * dpr); }
  g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
  const cx = W / 2, cy = H / 2 + 6, R = Math.min(W, H) / 2 - 8, scale = R / 0.75;
  const yaw = (parrot.joints.get('head_yaw')) * Math.PI / 180;
  // screen: the parrot faces down the canvas (toward the visitor); its left (+x) is to the screen's right
  const toScreen = (x, z) => [cx + x * scale, cy + z * scale];
  const dirAngle = (a) => Math.PI / 2 - a; // a heading (0 = facing +z, + = to its left) as a canvas angle
  const f = EYE.field * Math.PI / 180, ax = EYE.axis * Math.PI / 180;
  for (const [side, col] of [[1, 'rgba(79,195,247,0.20)'], [-1, 'rgba(242,179,61,0.20)']]) {
    const mid = yaw + side * ax;
    g.beginPath(); g.moveTo(cx, cy);
    g.arc(cx, cy, R, dirAngle(mid + f), dirAngle(mid - f), false);
    g.closePath(); g.fillStyle = col; g.fill();
  }
  g.strokeStyle = '#3a4250'; g.beginPath(); g.arc(cx, cy, R, 0, Math.PI * 2); g.stroke();
  // the head and its beak
  g.fillStyle = '#a8b0bc'; g.beginPath(); g.arc(cx, cy, 5, 0, Math.PI * 2); g.fill();
  g.strokeStyle = '#e8ebf0'; g.lineWidth = 2; g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + Math.cos(dirAngle(yaw)) * 11, cy + Math.sin(dirAngle(yaw)) * 11); g.stroke(); g.lineWidth = 1;
  for (const t of room.things.values()) {
    const [x, y] = toScreen(t.obj.position.x, t.obj.position.z);
    const a = Math.atan2(t.obj.position.x, t.obj.position.z) - yaw; // heading of the thing from the beak
    const off = Math.abs(Math.atan2(Math.sin(a), Math.cos(a)));
    const seen = off <= ax + f || off <= f - ax; // within either field
    g.fillStyle = seen ? '#e8ebf0' : '#6c7583';
    g.beginPath(); g.arc(Math.min(W - 3, Math.max(3, x)), Math.min(H - 3, Math.max(3, y)), state.subject === t.id ? 4 : 3, 0, Math.PI * 2); g.fill();
  }
}

// --- the frame loop ----------------------------------------------------------------------------------------
let last = performance.now(), slowSince = 0;
function frame(now) {
  const dt = Math.min(0.05, (now - last) / 1000); last = now;
  if (parrot) {
    const loud = audio.loudness(now);
    const eating = nut ? nut.update(dt) : null;
    if (eating !== null) { parrot.joints.set('beak_open', eating); state.wasEating = true; }
    else if (loud > 0 || state.wasSpeaking || state.wasEating) { parrot.joints.set('beak_open', 30 * loud); state.wasSpeaking = loud > 0; state.wasEating = false; }
    ui.voiceLevel.style.width = `${Math.round(loud * 100)}%`;
    ui.earLevel.style.width = `${Math.round(audio.level * 100)}%`;
    $('mic-level').style.width = `${Math.round(audio.level * 100)}%`;
    drawBands();
    drawTurns(now);
    parrot.update(dt);
    placeFocus();
    if (now - state.lastMomentAt >= MOMENT_MS || !state.lastMomentAt) { state.lastMomentAt = now; moment(now); }
    view?.setJoints(parrot.joints.pos, parrot.joints.target);
    syncTags(); drawFields();
  }
  updateCoach();
  controls.update();
  renderer.shadowMap.needsUpdate = true;
  renderer.render(room.scene, camera);
  view?.frame(dt);
  if (state.tab === 'tab-memory') memview?.frame(); else brain3d?.frame(dt);
  // the frame rate, and a lighter picture when the laptop cannot keep up
  state.frameTimes.push(now); while (state.frameTimes.length && state.frameTimes[0] < now - 1000) state.frameTimes.shift();
  state.fps = state.frameTimes.length;
  if (now - (state.fpsShown || 0) > 500) { ui.fps.textContent = `${state.fps}`; state.fpsShown = now; }
  if (state.fps < 40 && state.frameTimes.length > 5) { slowSince ||= now; if (now - slowSince > 2500 && renderer.getPixelRatio() > 0.8) { renderer.setPixelRatio(renderer.getPixelRatio() * 0.85); resize(); slowSince = now; } } else slowSince = 0;
  requestAnimationFrame(frame);
}

// --- looks, mode, buttons ------------------------------------------------------------------------------------
let looks = [];
async function setLook(id) {
  let look = looks.find((l) => l.id === id) || looks[0] || null;
  let made;
  try { made = await makeParrot(look, rig); } catch (error) { // the drawn body, when a look cannot load
    console.warn(`The ${look?.title} look did not load: ${error.message}`);
    look = looks.find((l) => l.fallback) || null;
    made = await makeParrot(look, rig);
  }
  if (parrot) room.scene.remove(parrot.group);
  if (made.parrot && parrot) made.parrot.joints.pos.set(parrot.joints.pos), made.parrot.joints.target.set(parrot.joints.target);
  parrot = made.parrot;
  parrot.group.position.set(0, BAR_Y, 0);
  room.scene.add(parrot.group);
  room.setBarRadius?.(parrot.rig.bar_radius);
  parrot.update(0);
  if (eyes) eyes.parrot = parrot; else eyes = new Eyes(renderer, room.scene, parrot);
  state.look = look ? look.id : 'drawn';
  for (const b of ui.looks.querySelectorAll('.seg')) b.setAttribute('aria-pressed', String(b.dataset.look === state.look));
  document.body.dataset.look = state.look;
  $('credit').innerHTML = look?.credit || 'The parrot’s body is drawn by the page.';
}

function setMode(mode) {
  state.mode = mode;
  for (const b of ui.mode.querySelectorAll('.seg')) b.setAttribute('aria-pressed', String(b.dataset.mode === mode));
  ui.drawer.hidden = mode !== 'you';
  if (mode === 'you') syncSliders();
}
function buildSliders() {
  ui.drawer.textContent = '';
  for (const j of rig.joints) {
    const row = document.createElement('label'); row.className = 'slider';
    const name = document.createElement('span'); name.textContent = j.name.replace('_', ' ');
    const input = document.createElement('input'); input.type = 'range'; input.min = j.min; input.max = j.max; input.step = (j.max - j.min) / 200; input.dataset.joint = j.name;
    input.addEventListener('input', () => parrot.joints.set(j.name, Number(input.value)));
    row.append(name, input); ui.drawer.append(row);
  }
}
function syncSliders() { for (const input of ui.drawer.querySelectorAll('input')) input.value = parrot.joints.target[parrot.joints.index[input.dataset.joint]]; }

function buildPalette() {
  for (const [kind, spec] of Object.entries(KINDS)) {
    const b = document.createElement('button'); b.className = 'chip'; b.textContent = spec.label; b.dataset.kind = kind;
    b.addEventListener('click', () => addThing(kind));
    ui.palette.append(b);
  }
}

ui.test.addEventListener('click', () => { if (state.script) { state.script = null; ui.test.textContent = 'Test run'; ui.test.setAttribute('aria-pressed', 'false'); } else runScript(TEST); });
ui.clear.addEventListener('click', () => { state.script = null; room.clear(); state.subject = null; view?.clearTuning(); });
// The pistachio: thrown from the visitor's side, caught in the beak, nibbled and eaten. The reward
// reaches the brain when the nut is in the beak, not on the click.
let nut = null;
ui.pistachio.addEventListener('click', () => {
  if (!parrot) return;
  nut ||= new Pistachio(room.scene);
  const from = camera.position.clone().lerp(new THREE.Vector3(0, BAR_Y + 0.2, 0), 0.35); from.y -= 0.1;
  const thrown = nut.throw(from, parrot, () => {
    state.reward = 1; state.pistachios += 1; ui.pistachios.textContent = String(state.pistachios);
    brain3d?.reward();
    $('dopamine').hidden = false;
    $('dopamine-note').textContent = desc?.placeholder ? 'This placeholder brain learns nothing from it: the composed brain does the strengthening.' : '';
    clearTimeout(state.dopTimer); state.dopTimer = setTimeout(() => { $('dopamine').hidden = true; }, 4200);
  }, () => {});
  if (!thrown) toast('It is eating the last one', '', 1400);
});
ui.silence.addEventListener('click', async () => {
  if (!state.brainReady) return;
  state.silenced = !state.silenced;
  ui.silence.setAttribute('aria-pressed', String(state.silenced));
  ui.silence.textContent = state.silenced ? 'Silenced: wake them' : 'Silence them';
  await brain.call('silence', { group: 'distance', on: state.silenced });
  document.body.dataset.silenced = state.silenced ? '1' : '0';
});
for (const b of ui.mode.querySelectorAll('.seg')) b.addEventListener('click', () => setMode(b.dataset.mode));
// sound may start only after the visitor's first click (browsers hold it back until then)
window.addEventListener('pointerdown', () => { audio.unlock().catch(() => {}); }, { once: true, capture: true });
// The microphone: the first-visit card asks; the toolbar's button turns it on and off. The choice
// is remembered in this browser.
const remember = { get() { try { return localStorage.getItem('parrot.mic'); } catch (e) { return null; } },
  set(v) { try { localStorage.setItem('parrot.mic', v); } catch (e) { /* storage blocked: the card asks again */ } } };
function micError(error) {
  const name = error?.name || '';
  if (!window.isSecureContext) return 'The microphone needs a secure page. Open it at http://localhost:8842/ (on this computer) or over https.';
  if (name === 'NotAllowedError' || name === 'SecurityError') return 'The microphone is blocked for this page. Allow it in the address bar (the site settings by the address), then press Let it hear me again.';
  if (name === 'NotFoundError' || name === 'OverconstrainedError') return 'No microphone was found. Plug one in or choose one in your computer\u2019s sound settings, then try again.';
  if (name === 'NotReadableError') return 'The microphone is busy in another app. Close it there, then try again.';
  return `The microphone did not start: ${error?.message || name || 'unknown error'}.`;
}
async function startMic() {
  await audio.startMic();
  ui.mic.setAttribute('aria-pressed', 'true');
  document.body.dataset.mic = 'on';
}
ui.mic.addEventListener('click', async () => {
  if (audio.mic) { audio.stopMic(); ui.mic.setAttribute('aria-pressed', 'false'); document.body.dataset.mic = 'off'; return; }
  try { await startMic(); remember.set('yes'); toast('The parrot hears you: speak, and watch its ear light up', 'good', 2400); }
  catch (error) { toast(micError(error), 'bad', 6000); }
});
$('talk-yes').addEventListener('click', async () => {
  $('talk-error').hidden = true;
  try { await audio.unlock(); await startMic(); remember.set('yes'); $('talk').hidden = true; toast('It hears you: speak, and watch its ear light up', 'good', 2600); }
  catch (error) { $('talk-error').textContent = micError(error); $('talk-error').hidden = false; }
});
$('talk-no').addEventListener('click', () => { remember.set('no'); $('talk').hidden = true; audio.unlock().catch(() => {}); });
function offerMic() {
  const choice = remember.get();
  if (choice === 'no') return;
  if (choice === 'yes') { // asked before: the first click anywhere turns it on (a browser lets sound start only from a click)
    window.addEventListener('pointerdown', () => { startMic().catch(() => { $('talk').hidden = false; }); }, { once: true });
    return;
  }
  $('talk').hidden = false;
}
$('home').addEventListener('click', () => { camera.position.copy(HOME.pos); controls.target.copy(HOME.at); controls.update(); });

// --- start --------------------------------------------------------------------------------------------------------
async function start() {
  try {
    setStatus('Building the room');
    await room.build();
    rig = await loadRig();
    looks = await lookList();
    for (const l of looks.filter((x) => !x.fallback)) {
      const b = document.createElement('button'); b.className = 'seg'; b.dataset.look = l.id; b.textContent = l.title; b.setAttribute('aria-pressed', 'false');
      b.addEventListener('click', () => setLook(l.id));
      ui.looks.append(b);
    }
    ui.looks.hidden = looks.filter((x) => !x.fallback).length < 2;
    setStatus('Bringing the parrot');
    await setLook(query.get('look') || looks[0]?.id);
    buildPalette(); buildSliders();
    for (const [kind, x, z, yaw] of [['apple', 0.16, 0.26, 30], ['ball', -0.3, 0.16, 0], ['cup', 0.34, -0.12, 200], ['block', -0.1, 0.42, 25]]) await place(kind, x, z, yaw);
    state.subject = [...room.things.keys()][0];
    resize();
    state.phase = 'idle';
    requestAnimationFrame(frame);
  } catch (error) {
    setStatus(`The room failed to load: ${error.message}`, 'error');
    throw error;
  }
  brain3d = new Brain3D($('brain3d'), $('b3-labels'));
  memview = new MemoryView($('memory'));
  for (const [tab, panel] of [['tab-brain', 'view-brain'], ['tab-memory', 'view-memory']]) {
    $(tab).addEventListener('click', () => {
      for (const [t, v] of [['tab-brain', 'view-brain'], ['tab-memory', 'view-memory']]) { $(t).setAttribute('aria-selected', String(t === tab)); $(v).hidden = t !== tab; }
      state.tab = tab; if (tab === 'tab-memory') memview.layout(); else brain3d.resize();
      void panel;
    });
  }
  view = new BrainView({ canvas: $('brain'), units: $('dist-units'), tuning: $('dist-tuning'), readout: $('dist-readout'), silence: ui.silence, joints: $('joints') });
  window.parrotPage = { room, state, eyes, audio, get parrot() { return parrot; }, place, addThing, move: (id, x, z) => room.move(id, x, z), remove: (id) => room.remove(id),
    describe: () => room.describe(), load: (d) => room.load(d), script: runScript, TEST, setLook, setMode, distanceOf, camera, THREE,
    view(name) { const v = VIEWS[name]; if (!v) return; camera.position.set(...v[0]); controls.target.set(...v[1]); controls.update(); },
    screenOf(x, y, z) { const v = new THREE.Vector3(x, y, z).project(camera); const r = canvas.getBoundingClientRect(); return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; } };
  if (query.get('brain') === 'off') { setStatus('Ready (no brain)', 'ready'); document.body.dataset.ready = '1'; return; }
  brain = new BrainWorker();
  try {
    const out = await brain.call('init', { pack: PACK, config: { eye: { w: EYE.w, h: EYE.h, field: EYE.field, vfield: EYE.vfield, fovea: EYE.fovea, axis: EYE.axis } } });
    desc = out;
    view.setup(desc, rig.joints);
    for (const r of desc.repertoire || []) addChip(r);
    const kept = learnedStore.get();
    if (kept?.records?.length) { const out = await brain.call('remember', { saved: kept }); syncChips(out.repertoire || []); memview?.update(out.memory); }
    brain3d.setup(desc);
    ui.sub.textContent = desc.placeholder ? `${desc.title} · ${desc.neurons} units` : `${desc.title || desc.name} · ${desc.neurons.toLocaleString('en')} neurons`;
    const g = (desc.groups || []).find((x) => x.variable === 'distance');
    if (g) { $('dist-title').textContent = g.title; $('dist-card').setAttribute('data-explain', g.explain); $('dist-card').setAttribute('data-explain-title', g.title); }
    state.brainReady = true;
    setStatus('Ready', 'ready');
    ui.status.title = `Brain loaded in ${(desc.startup_ms / 1000).toFixed(1)} s`;
    document.body.dataset.ready = '1';
    offerMic();
    if (query.get('test')) runScript(TEST);
  } catch (error) {
    setStatus(`The brain failed to load: ${error.message}`, 'error');
    document.body.dataset.ready = '1';
  }
}
start();
