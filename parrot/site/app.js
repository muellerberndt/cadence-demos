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
// the page's layout: the room and the brain side by side, the brain as a scan, a small chat (?layout=classic: the panels)
const DEMO = query.get('layout') !== 'classic';
const START_KEY = 'parrot.start.v3'; // the version of a start (older saves are cleared at every start)
if (DEMO) document.body.classList.add('demo');
const MOMENT_MS = 100; // the brain's moment: ten a second
const VIZ_EVERY = 3; // the body's settles go to the brain view every third moment (their trace costs time in the browser); the trained brain's with each of its moments
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
  ask: ['Ask it', 'Click a <b>thing</b>, then type <b>what is this?</b> in <b>Ask it</b> under the brain.'],
  asking: ['Listen', 'It hears your question one word a moment, then answers in the gap after it.'],
};
function coachKey() {
  if (!state.brainReady && state.phase === 'loading') return 'loading';
  if (state.script) return 'script';
  if (state.mode === 'you') return 'manual';
  if (state.dragging) return state.behind ? 'behind' : 'dragging';
  if (state.trained) return trained.busy ? 'asking' : 'ask';
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
  askNote();
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
  if (!state.dragging.moved) { state.cue = cueFor(state.dragging.id); state.focus = { id: state.dragging.id, why: 'you pointed at it' }; state.pointed = { id: state.dragging.id, until: performance.now() + (state.trained ? 1e9 : 6000) }; trained.focus = state.dragging.id; askNote(); }
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
  if (!state.composed) { eyes.render(); eyes.draw('left', ui.eyeL); eyes.draw('right', ui.eyeR); }
  if (!state.brainReady || state.pending) return;
  state.pending = true; state.lastStep = now;
  parrot.joints.proprio(proprio);
  const left = eyes.left.rgb.slice(), right = eyes.right.rgb.slice(), pro = proprio.slice();
  const reward = state.reward; state.reward = 0;
  const sound = audio.moment();
  const cue = state.cue; state.cue = null;
  const voiceOk = !!audio.ctx && audio.ctx.state === 'running';
  const op = state.trained ? nextOp(now) : null;
  let reply;
  try {
    const focusKind = state.focus ? room.things.get(state.focus.id)?.kind || null : null;
    const scene = state.composed && room.version !== state.sentVersion ? room.describe() : null;
    if (scene) state.sentVersion = room.version;
    // while the trained brain hears a question and answers, the hearing layer's calls wait
    const calls = voiceOk && !(state.trained && (trained.busy || now < trained.quietUntil));
    reply = await brain.call('step', { meta: { t: state.moment, reward, voice_ok: calls, cue, things: room.things.size, focus_kind: focusKind, scene, learn: true, viz: !!state.composed && state.moment % VIZ_EVERY === 0, ...(op ? { meaning: op.meta } : {}) }, arrays: { left, right, proprio: pro, mel: sound.mel, audio: sound.audio, pcm: sound.pcm } },
      [left.buffer, right.buffer, pro.buffer, sound.mel.buffer, sound.audio.buffer, sound.pcm.buffer]);
  } catch (error) { state.pending = false; op?.reject(error); setStatus(`The brain stopped: ${error.message}`, 'error'); state.brainReady = false; return; }
  state.pending = false;
  state.moment += 1;
  state.lastReply = reply;
  if (op) { op.resolve(reply.meaning || {}); if (reply.meaning?.mind) showMind(reply.meaning.mind, op.meta.glimpseId || op.meta.focus); }
  if (state.mode === 'brain' && reply.arrays.angles && state.composed) { // the composed brain's body: its angles, smoothed by the page
    reply.arrays.angles.forEach((v, i) => { if (i < parrot.joints.n && parrot.joints.spec[i].name !== 'beak_open') parrot.joints.target[i] = v; });
  } else if (state.mode === 'brain' && reply.arrays.targets) parrot.joints.setUnitTargets(reply.arrays.targets);
  if (reply.arrays.left && desc?.eye) { drawHostEye(ui.eyeL, reply.arrays.left, desc.eye.w, desc.eye.h, false); drawHostEye(ui.eyeR, reply.arrays.right, desc.eye.w, desc.eye.h, true); }
  const subject = state.subject ? distanceOf(state.subject) : null;
  if (!DEMO) view.update(reply, reply.arrays, subject); // the detail panel's cards (hidden in the demo layout: nothing drawn for them)
  brain3d?.update(reply.arrays.activity, reply);
  if (reply.arrays.voice?.length) { // the voice motor's frames: the parrot says them
    const spoken = reply.arrays.voice_pcm?.length ? audio.speakPcm(reply.arrays.voice_pcm, reply.voice_rate || 8000) : audio.speak(reply.arrays.voice); // a remembered sound: its own audio
    const what = reply.said ? (reply.said.source === 'you' ? 'a sound learned from you' : reply.said.source === 'recording' ? `a ${reply.said.tag}` : 'a babble') : 'a sound';
    if (spoken) { ui.voiceNote.textContent = `${what}, ${(spoken.env.length / 100).toFixed(1)} s`; state.saying = reply.said?.id; markChip(reply.said?.id); }
  }
  if (reply.drive !== undefined) ui.driveLevel.style.width = `${Math.round(reply.drive * 100)}%`;
  teachUpdate(reply);
  // the focused thing recalls its word: that word's chip is ringed while the parrot looks at the thing
  for (const c of ui.sounds.querySelectorAll('.chip-s.you')) {
    const on = reply.recalled && c.dataset.sound === reply.recalled.id;
    c.style.outline = on ? '2px solid #f5c542' : ''; c.title = on ? `The ${reply.recalled.kind} brings this word back from memory (link ${reply.recalled.link})` : c.title;
  }
  if (reply.startle) { // a sudden sound: the head turns toward the visitor (the camera, from the head)
    const head = parrot.bones.head, hp = new THREE.Vector3(), hq = new THREE.Quaternion();
    head.getWorldPosition(hp); head.getWorldQuaternion(hq);
    const d = camera.position.clone().sub(hp).applyQuaternion(hq.invert());
    state.cue = { az: +(Math.atan2(d.x, d.z) * 180 / Math.PI).toFixed(1), el: +(Math.atan2(d.y, Math.hypot(d.x, d.z)) * 180 / Math.PI).toFixed(1), you: true };
    state.focus = null; state.focusYou = performance.now();
  }
  $('you-focus').hidden = !(state.focusYou && performance.now() - state.focusYou < 2600);
  if (reply.memory) memview?.update(reply.memory);
  // the badge says what it has learned so far
  const words = reply.words || 0, lessons = reply.lessons || 0;
  const badge = state.trained ? `trained tonight: names of things${words ? `; ${words} sound${words === 1 ? '' : 's'} from you` : ''}`
    : words || lessons ? `learning: ${words} word${words === 1 ? '' : 's'}${state.composed ? `, distance taught by ${lessons} head turn${lessons === 1 ? '' : 's'}` : ''}` : 'a newborn: it has learned nothing yet';
  const el = document.querySelector('.newborn');
  if (el && el.firstChild.textContent !== badge) el.firstChild.textContent = badge;
  if (reply.repertoire) syncChips(reply.repertoire);
  if (reply.heard_sound) {
    saveMemory();
    if (state.trained) heardForWord(reply.heard_sound);
    if (brain3d?.scan) { // what the hearing memory made of the sound: known (its record told again), and the thing its record links to
      const mem = reply.memory, rec = mem?.records?.find((r) => r.slot === reply.heard_sound.slot), things = mem?.things || [];
      let best = null;
      (rec?.slow || []).forEach((v, k) => { const s = v + (rec.fast?.[k] || 0); if (!best || s > best.s) best = { kind: things[k], s }; });
      const recognized = !!mem?.write?.revised;
      brain3d.scan.heardSound({ recognized, kind: recognized && best && best.s > 0.1 ? best.kind : null, strength: best?.s || 0, slot: reply.heard_sound.slot });
    }
  }
  if (reply.paid) for (const [id] of Object.entries(reply.paid)) ui.sounds.querySelector(`[data-sound="${id}"]`)?.classList.add('paid');
  // the focus the brain reports: the thing nearest the direction it turned to
  if (state.composed) { // the composed brain's focus is a place on the map: the thing nearest it
    const f = reply.focus;
    let best = null;
    if (f?.place) for (const t of room.things.values()) { const d = Math.hypot(t.obj.position.x - f.place[0], t.obj.position.z - f.place[1]); if (d < 0.15 && (!best || d < best.d)) best = { id: t.id, d, why: f.why || 'it won the focus' }; }
    state.focus = best;
  } else {
    const key = reply.focus ? `${reply.focus.az},${reply.focus.el}` : null;
    if (key !== state.focusKey) { state.focusKey = key; state.focus = reply.focus ? focusFrom(reply.focus) : null; }
  }
  // joint attention: a thing you pointed at holds the parrot's attention for six seconds
  if (state.pointed && performance.now() < state.pointed.until && room.things.has(state.pointed.id)) state.focus = { id: state.pointed.id, why: 'you pointed at it' };
  else state.pointed = null;
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
// An eye image from the brain host (D2: rows top-down, column 0 at the eye's rear edge), drawn as
// the page's own eye images are: the right eye mirrored, so the two read round from left to right.
function drawHostEye(canvas, data, w, h, mirror) {
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  const g = canvas.getContext('2d'), img = g.createImageData(w, h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const sx = mirror ? w - 1 - x : x, s = 3 * (y * w + sx), d = 4 * (y * w + x);
    img.data[d] = data[s]; img.data[d + 1] = data[s + 1]; img.data[d + 2] = data[s + 2]; img.data[d + 3] = 255;
  }
  g.putImageData(img, 0, 0);
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
    if (c && r.deep !== undefined) {
      c.querySelector('.deep i').style.width = `${Math.round(Math.min(1, r.deep / 20) * 100)}%`;
      const m = r.matches?.length ? r.matches[r.matches.length - 1] : null;
      c.querySelector('.heard').textContent = `heard ${r.heard}`;
      c.querySelector('.match').textContent = m === null ? 'not said yet' : `said ${Math.round(m * 100)}%`;
      sparkline(c.querySelector('.spark'), r.matches || []);
      c.title = `A word learned from you. Click: hear how the parrot says it. Shift-click: the word as it remembers hearing it.`;
      if (r.frames) soundFrames.set(r.id, Float32Array.from(r.frames));
      if (r.program) programFrames.set(r.id, Float32Array.from(r.program));
      if (r.pcm?.length) soundPcm.set(r.id, { pcm: Float32Array.from(r.pcm), rate: r.pcm_rate || 8000 });
    }
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
const soundFrames = new Map(), programFrames = new Map(), soundPcm = new Map();
function sparkline(c, values) {
  const g = c.getContext('2d'), W = c.width, H = c.height; g.clearRect(0, 0, W, H);
  if (values.length < 2) return;
  g.strokeStyle = '#5fd08e'; g.lineWidth = 1.2; g.beginPath();
  values.forEach((v, i) => { const x = (i / (values.length - 1)) * (W - 1), y = H - 1 - v * (H - 2); if (i) g.lineTo(x, y); else g.moveTo(x, y); });
  g.stroke();
}
function addChip(r) {
  if (ui.sounds.querySelector(`[data-sound="${r.id}"]`)) return;
  const b = document.createElement('button'); b.className = `chip-s ${r.source === 'you' ? 'you' : ''} ${r.paid ? 'paid' : ''}`; b.dataset.sound = r.id;
  b.title = r.source === 'recording' ? `${r.tag}: an African Grey call from a recording` : r.source === 'you' ? 'learned from you' : 'its own babble';
  if (r.frames) { const c = document.createElement('canvas'); spectro(r.frames, c); b.append(c); soundFrames.set(r.id, Float32Array.from(r.frames)); }
  if (r.pcm?.length) soundPcm.set(r.id, { pcm: Float32Array.from(r.pcm), rate: r.pcm_rate || 8000 });
  b.append(document.createTextNode(r.source === 'you' ? 'word' : r.tag));
  if (r.source === 'you') {
    const d = document.createElement('span'); d.className = 'deep'; d.append(document.createElement('i'));
    const heard = document.createElement('span'); heard.className = 'heard';
    const match = document.createElement('span'); match.className = 'match';
    const spark = document.createElement('canvas'); spark.className = 'spark'; spark.width = 36; spark.height = 12;
    b.append(heard, d, match, spark);
  }
  b.addEventListener('click', async (ev) => {
    await audio.unlock();
    const kept = soundPcm.get(r.id);
    if (kept?.pcm?.length && !ev.shiftKey) { audio.speakPcm(kept.pcm, kept.rate); markChip(r.id); ui.voiceNote.textContent = r.source === 'you' ? 'the word as the parrot remembers it' : `${b.title} (you played it)`; return; }
    const template = ev.shiftKey || r.source !== 'you';
    const f = template ? soundFrames.get(r.id) : programFrames.get(r.id) || soundFrames.get(r.id);
    if (f) { audio.speak(f); markChip(r.id); ui.voiceNote.textContent = r.source === 'you' ? (template ? 'the word as it remembers hearing it' : 'the word as the parrot says it') : `${b.title} (you played it)`; }
  });
  ui.sounds.append(b);
  if (r.source === 'you') ui.forget.hidden = false;
}
function markChip(id) {
  for (const c of ui.sounds.querySelectorAll('.chip-s')) c.classList.toggle('playing', c.dataset.sound === id);
  setTimeout(() => ui.sounds.querySelector(`[data-sound="${id}"]`)?.classList.remove('playing'), 1500);
}
// --- teaching: the lesson's steps light as you go, and the list shows what it knows ----------------------
function teachUpdate(reply) {
  const kind = state.focus ? room.things.get(state.focus.id)?.kind || null : null;
  const rec = reply.recalled && reply.recalled.kind === kind ? reply.recalled : null;
  const saidIt = rec && reply.said && reply.said.id === rec.id;
  if (saidIt) state.askPistachio = performance.now();
  const asking = state.askPistachio && performance.now() - state.askPistachio < 4000;
  const step = !kind ? 1 : asking ? 4 : rec && rec.link > 0.2 ? 3 : 2;
  for (const li of document.querySelectorAll('.teach-steps li')) { const n = +li.dataset.step; li.classList.toggle('now', n === step); li.classList.toggle('done', n < step); }
  ui.pistachio.classList.toggle('ask', !!asking);
  const box = $('knows'), knows = reply.knows || [];
  const sig = JSON.stringify(knows);
  if (sig === state.knowsSig) return;
  state.knowsSig = sig; box.textContent = '';
  if (!knows.length) { const e = document.createElement('span'); e.className = 'knows-empty'; e.textContent = 'It links no word to a thing yet.'; box.append(e); return; }
  for (const k of knows) {
    const el = document.createElement('span'); el.className = 'know'; el.title = `Looking at the ${k.kind} brings back this word (link ${k.link}). Click: hear it.`;
    const bar = document.createElement('span'); bar.className = 'bar'; const i = document.createElement('i'); i.style.width = `${Math.round(Math.min(1, k.link) * 100)}%`; bar.append(i);
    el.append(document.createTextNode(`${k.kind} \u2192 word`), bar);
    el.addEventListener('click', async () => { await audio.unlock(); const kept = soundPcm.get(k.id); if (kept?.pcm?.length) audio.speakPcm(kept.pcm, kept.rate); });
    box.append(el);
  }
}
$('sound-report').addEventListener('click', async () => {
  const r = await brain.call('debug', {});
  const blob = new Blob([JSON.stringify({ saved: new Date().toISOString(), ...(r.reply || r) })], { type: 'application/json' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `parrot-sound-report-${Date.now()}.json`; a.click();
  toast('Saved the sound report to your downloads', 'good', 2200);
});
$('brain-kind').addEventListener('change', (e) => {
  try { localStorage.setItem('parrot.brain', e.target.value); } catch (err) { /* storage blocked */ }
  const u = new URL(location.href); u.searchParams.set('brain', e.target.value); location.href = u.href;
});
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
  if (R <= 0) return; // the panel is hidden: nothing to draw (an arc of negative radius throws)
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

// --- the brain trained tonight: ask it ------------------------------------------------------------------
// The trained brain (cadence#334, the meaning lane's night) lives one of its own moments at a time
// (300 ms), each riding with a moment of the body: the question heard one word a moment with its
// voice held, then its turn in the gap after the last word (three moments; for a question about the
// whole room, one moment a thing, its glimpse on that thing). What it sees of a thing is what its
// training world reports: the kind's shape and size, the colour, the material, the direction from
// where the parrot faces on its perch (positive to its left) and the distance. The page's things in that world, each as its world names it:
const WORLD = {
  apple: { kind: 'apple', colour: 'red', material: 'fruit' },
  ball: { kind: 'ball', colour: 'white', material: 'cloth', note: 'the baseball is a white ball of cloth there (its world has no leather)' },
  cup: { kind: 'cup', colour: 'white', material: 'glass', note: 'the china cup is a white cup of glass there (its world has no china)' },
  banana: { kind: 'banana', colour: 'yellow', material: 'fruit' },
  block: { kind: 'block', colour: 'blue', material: 'wood' },
  key: { kind: 'key', colour: 'yellow', material: 'metal' },
  greenball: { kind: 'ball', colour: 'green', material: 'plastic' },
  lemon: { kind: 'lemon', colour: 'yellow', material: 'fruit', note: 'the lemon is the kind it never saw in training, and it has no word for it' },
  duck: null, pear: null,
};
const ROUND = new Set(['apple', 'ball', 'cup', 'lemon']); // the round kinds of its world (night.py ROUND)
const DIRECTIONS = ['front', 'right', 'behind', 'left']; // a quarter each, front within 45 degrees (night.py direction_of)
const trained = { wordSounds: (() => { try { return JSON.parse(localStorage.getItem('parrot.words') || '{}'); } catch (e) { return {}; } })(), awaitWord: null, busy: false, queue: [], lastAt: 0, momentMs: 300, turn: 3, vocab: new Set(), colours: [], materials: [], focus: null, open: null, quietUntil: 0, serial: 0, log: [] };

/** The things it sees: the room's things in its world, the nearest five, the thing in focus among them. */
function trainedThings(focusId, glimpseId) {
  const rows = [];
  for (const t of room.things.values()) {
    const w = WORLD[t.kind];
    if (!w) continue;
    const a = Math.atan2(t.obj.position.x, t.obj.position.z); // from where it faces on the perch (+z), positive to its left
    rows.push({ id: t.id, kind: w.kind, colour: w.colour, material: w.material, direction: +Math.atan2(Math.sin(a), Math.cos(a)).toFixed(4), distance: +distanceOf(t.id).toFixed(3), focus: t.id === focusId });
  }
  rows.sort((p, q) => (q.focus - p.focus) || (q.id === glimpseId) - (p.id === glimpseId) || p.distance - q.distance);
  const things = rows.slice(0, 5);
  const glimpse = glimpseId ? things.findIndex((t) => t.id === glimpseId) : -1;
  return { things, glimpse: glimpse >= 0 ? glimpse : null };
}
/** One of its moments, sent with the next step of the body once 300 ms have passed since the last. */
function trainedOp(meta) { return new Promise((resolve, reject) => trained.queue.push({ meta, resolve, reject })); }
function lookFocus() { // the thing its mind holds between questions: the one you clicked (none: it holds no thing)
  const t = trained.focus && room.things.get(trained.focus);
  if (t && WORLD[t.kind]) return trained.focus;
  if (brain3d?.scan?.concept) brain3d.scan.clearConcept();
  return null;
}
function nextOp(now) {
  if (now - trained.lastAt < trained.momentMs - 8) return null;
  if (!trained.queue.length) { // between questions it keeps looking, its voice held, so its mind holds the thing in focus
    const f = !trained.busy && lookFocus();
    if (!f) return null;
    trained.queue.push({ meta: { op: 'look', focus: f }, resolve() {}, reject() {} });
  }
  trained.lastAt = now;
  const op = trained.queue.shift();
  if (op.meta.op === 'moment' || op.meta.op === 'correct' || op.meta.op === 'look') {
    const seen = trainedThings(op.meta.focus, op.meta.glimpseId);
    op.meta = { ...op.meta, things: seen.things, glimpse: seen.glimpse };
  }
  return op;
}

const askEl = { card: $('ask'), form: $('ask-form'), q: $('ask-q'), log: $('ask-log'), fix: $('ask-fix'), word: $('ask-word'), note: $('ask-note'), words: $('ask-words'), bubble: $('say-bubble') };
function setupTrained(t) {
  trained.vocab = new Set(t.words); trained.colours = t.colours; trained.materials = t.materials;
  trained.momentMs = t.moment_ms || 300; trained.turn = t.turn_moments || 3;
  askEl.card.hidden = false;
  setupMind(t);
  askEl.words.textContent = [...t.words].sort().join(' · ');
  const v = t.version || {};
  $('ask-version').textContent = `Version: step ${v.stage || '?'} (${v.step || ''}) · founder ${v.founder ?? '?'} · exported ${v.exported || '?'}${v.good ? ` · does well: ${v.good}` : ''}${v.lost ? ` · lacks: ${v.lost}` : ''}`;
  if (v.learned) $('ask-learned').textContent = `Learned tonight: ${v.learned}. Not learned: ${v.not_learned || 'see the help'}.`;
  $('ask-version').title = `${t.neurons.toLocaleString('en')} neurons, ${t.synapses.toLocaleString('en')} synapses, ${t.records.toLocaleString('en')} word records; from ${v.source || 'the meaning lane'}`;
  askNote();
  const foot = document.querySelector('.mind-foot'); if (foot) foot.scrollTop = foot.scrollHeight;
}
/** The line under the box: what it sees of the room, and the thing a question is about. */
function askNote() {
  if (!state.trained) return;
  const kinds = [...room.things.values()].map((t) => t.kind);
  const missing = [...new Set(kinds.filter((k) => !WORLD[k]))];
  const notes = [...new Set(kinds.filter((k) => WORLD[k]?.note))].map((k) => WORLD[k].note);
  const inWorld = kinds.filter((k) => WORLD[k]).length;
  const f = trained.focus && room.things.get(trained.focus);
  const parts = [f ? (WORLD[f.kind] ? `In focus: the ${f.kind}.` : `The ${f.kind} is in focus, and the trained brain does not see it.`) : 'Click a thing to put it in focus.'];
  if (missing.length) parts.push(`It does not see the ${missing.join(' or the ')}: its training world had no such kind.`);
  if (inWorld > 5) parts.push('It sees the five things nearest it.');
  parts.push(...notes.map((n) => n.replace(/^./, (c) => c.toUpperCase()) + '.'));
  askEl.note.textContent = parts.join(' ');
}
/** The page's own check of a reply, for the forms its training taught (night.py FORMS); null where the page does not judge. */
function expected(words, focusKind, scene) {
  const w = words.join(' ');
  const kinds = scene.map((t) => t.kind);
  if (w === 'what is this' && focusKind) return [focusKind];
  if (words[0] === 'what' && words[1] === 'colour' && focusKind) return [WORLD_COLOUR(focusKind)];
  if (w === 'what objects are round') return [...new Set(kinds.filter((k) => ROUND.has(k)))].sort();
  if (w === 'what can you eat') return [...new Set(scene.filter((t) => t.material === 'fruit').map((t) => t.kind))].sort();
  if (words[0] === 'can' && words[1] === 'you' && words[2] === 'eat' && focusKind) return [Object.values(WORLD).find((x) => x && x.kind === focusKind)?.material === 'fruit' ? 'yes' : 'no'];
  if (words[0] === 'what' && words[1] === 'shape' && focusKind) return [ROUND.has(focusKind) ? 'round' : 'no']; // its voice has no word for another shape
  if (words[0] === 'where' && focusKind) { const t = scene.find((x) => x.focus); return t ? [DIRECTIONS[Math.floor((((-t.direction + Math.PI / 4) % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI) / (Math.PI / 2))]] : null; }
  return null;
}
const WORLD_COLOUR = (k) => Object.values(WORLD).find((w) => w && w.kind === k)?.colour;
function isScan(w) { // a question about the whole room: the focus visits each thing in turn (night.py FORMS)
  if (w[0] !== 'what') return false;
  if (w[1] === 'objects' || (w[1] === 'can' && w[2] === 'you' && w[3] === 'eat')) return true;
  return w[1] === 'is' && (['left', 'right', 'next', 'opposite', 'made'].includes(w[2]) || trained.colours.includes(w[2]));
}
function logLine(html, kind = '') {
  const li = document.createElement('li'); li.className = kind; li.innerHTML = html;
  askEl.log.append(li);
  while (askEl.log.children.length > 7) askEl.log.firstChild.remove();
  askEl.log.scrollTop = askEl.log.scrollHeight;
  const foot = askEl.card.parentElement; // the card's last line stays in view
  if (foot && foot.scrollHeight > foot.clientHeight) foot.scrollTop = foot.scrollHeight;
  return li;
}
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
/** The bubble over the parrot's head: what it hears (the visitor's word) or says. */
function bubble(text, who) {
  const b = askEl.bubble; b.hidden = !text; b.textContent = text || ''; b.className = `say-bubble ${who || ''}`;
  clearTimeout(bubble.timer); if (text) bubble.timer = setTimeout(() => { b.hidden = true; }, who === 'it' ? 3200 : 1200);
}
/** The visitor's question as a subtitle at the foot of the room (the parrot's answer alone goes by the parrot). */
const sub = { el: $('subtitle'), words: [], at: 0, timer: 0 };
function subtitle(text) {
  clearTimeout(sub.timer); sub.el.classList.remove('fading');
  sub.el.textContent = ''; sub.words = []; sub.at = 0; sub.el.hidden = !text;
  for (const w of (text || '').split(/\s+/).filter(Boolean)) {
    const span = document.createElement('span'); span.textContent = w + ' '; sub.el.append(span);
    sub.words.push({ span, key: w.toLowerCase().replace(/[^a-z]/g, '').replace(/^color$/, 'colour') });
  }
}
function subtitleHeard(word) { // the word the brain hears this moment lights
  for (let i = sub.at; i < sub.words.length; i++) if (sub.words[i].key === word) { for (let k = 0; k <= i; k++) sub.words[k].span.classList.add('on'); sub.at = i + 1; return; }
}
function subtitleDone(ms = 1500) { clearTimeout(sub.timer); sub.timer = setTimeout(() => { sub.el.classList.add('fading'); sub.timer = setTimeout(() => { sub.el.hidden = true; }, 300); }, ms); }
function placeBubble() {
  const b = askEl.bubble;
  if (!b || b.hidden || !parrot) return;
  const p = new THREE.Vector3(); parrot.bones.head.getWorldPosition(p); p.y += 0.07;
  p.project(camera);
  b.style.transform = `translate(${Math.round((p.x + 1) / 2 * canvas.clientWidth)}px, ${Math.round((1 - p.y) / 2 * canvas.clientHeight)}px) translate(-50%, -100%)`;
}
/** Say a word it chose: with the sound the visitor taught for that thing where its hearing links one. */
function sayWord(word) {
  brain3d?.scan?.say(word);
  const knows = state.lastReply?.knows || [];
  // the visitor's own sound for this thing (heard while it was in focus, a few times) comes first; then
  // the word's own sound (shipped, or the one you made after a silent answer); then any sound linked to it
  const yours = KINDS[word] ? knows.filter((k) => k.kind === word && !trained.bundleIds?.has(k.id) && k.link > 0.1).sort((a, b) => b.link - a.link)[0] : null;
  const own = !yours && trained.wordSounds[word];
  const link = yours || (own ? { id: own } : knows.find((k) => k.kind === word));
  trained.lastVoice = link ? { word, id: link.id, from: yours ? 'yours' : own ? 'word' : 'link' } : { word, id: null };
  const kept = link ? soundPcm.get(link.id) : null;
  if (kept?.pcm?.length && audio.ctx?.state === 'running') {
    const spoken = audio.speakPcm(kept.pcm, kept.rate);
    if (spoken) {
      markChip(link.id); ui.voiceNote.textContent = `${word}: in the sound you taught it for the ${word}`;
      const slot = Number(link.id.slice(4)), live = brain3d?.live;
      if (live?.slots?.has(slot)) live.packets.push({ path: [`slot:${slot}`, 'vocal', 'voice'], t0: brain3d.clock.vt, dur: 1.4, colour: live.cSay, slot });
      return 'in the sound you taught it';
    }
  }
  ui.voiceNote.textContent = `${word}: shown as text (no sound of yours links to it)`;
  audio.mouth(word); // the beak opens and closes with the word though it has no sound
  trained.awaitWord = { word, until: performance.now() + 20000 }; // the next sound you make becomes this word's sound
  return KINDS[word] ? `as text only: no sound of yours links to the ${word}` : 'as text only: it has no sound of yours for this word';
}

/** A sound the visitor made just after the parrot gave a word only as text: it becomes that word's
 *  sound (the parrot keeps it and says it back at once), and the word is said with it from then on. */
async function heardForWord(heard) {
  const w = trained.awaitWord;
  if (!heard?.id) return;
  if (!w || performance.now() > w.until) { // a sound it knows as a word: the trained brain hears that word and says it back
    const known = Object.entries(trained.wordSounds).find(([, id]) => id === heard.id);
    if (known && !trained.busy) imitate(known[0]);
    return;
  }
  trained.awaitWord = null;
  trained.wordSounds[w.word] = heard.id;
  try { localStorage.setItem('parrot.words', JSON.stringify(trained.wordSounds)); } catch (e) { /* storage blocked */ }
  if (!soundPcm.has(heard.id)) {
    const r = await brain.call('sound', { slot: heard.slot });
    if (r.pcm?.length) soundPcm.set(heard.id, { pcm: Float32Array.from(r.pcm), rate: r.rate || 8000 });
  }
  const kept = soundPcm.get(heard.id);
  if (kept?.pcm?.length) { audio.speakPcm(kept.pcm, kept.rate); bubble(w.word, 'it'); brain3d?.scan?.say(w.word); logLine(`<span class="who">parrot</span> <b>${esc(w.word)}</b> <span class="dim">(it says back the sound you made for the word)</span>`, 'a'); }
}

/** The visitor said a word whose sound the parrot keeps: the trained brain hears that word (its code, as
 *  in its training's imitation: one word, then its turn) and says what it says back. */
async function imitate(word) {
  if (!state.trained || trained.busy) return;
  trained.busy = true; trained.open = null;
  logLine(`<span class="who">you</span> ${esc(word)} <span class="dim">(heard: the sound it keeps for the word)</span>`, 'q');
  const said = [];
  try {
    await trainedOp({ op: 'begin' });
    await trainedOp({ op: 'moment', hear: word, more: true, focus: trained.focus });
    for (let k = 0; k < trained.turn; k++) {
      const r = await trainedOp({ op: 'moment', hear: null, more: false, focus: trained.focus });
      if (!r.said && said.length) break;
      if (r.said && said[said.length - 1] !== r.said) { said.push(r.said); bubble(said.join(', '), 'it'); sayWord(r.said); }
    }
    logLine(said.length ? `<span class="who">parrot</span> <b>${esc(said.join(', '))}</b>` : '<span class="who">parrot</span> <span class="dim">said nothing</span>', 'a');
    trained.last = { question: word, said: [...said], imitation: true, right: said.length === 1 && said[0] === word };
    trained.open = said.length ? { id: ++trained.serial, said, at: performance.now() } : null;
    if (!said.length) await trainedOp({ op: 'over' });
  } finally { trained.busy = false; trained.quietUntil = performance.now() + 2500; }
}

// --- In its mind: the facets of the thing in focus read from its state by the meaning lane's probes
const FACETS = [['kind', 'kind'], ['colour', 'colour'], ['round', 'shape'], ['material', 'material'], ['edible', 'edible'], ['direction', 'direction'], ['distance', 'distance']];
const FACET_VALUE = { round: { True: 'round', False: 'not round' }, edible: { True: 'yes', False: 'no' } };
const atChance = (f) => f && f.accuracy != null && f.base_rate != null && f.accuracy <= f.base_rate + 0.05;
const mindEl = { card: $('in-mind'), thing: $('im-thing'), facets: $('im-facets'), voice: $('im-voice'), outside: $('im-outside') };
function setupMind(t) {
  mindEl.card.hidden = false;
  const p = t.probes;
  trained.probes = p;
  mindEl.facets.textContent = '';
  if (!p) { const e = document.createElement('span'); e.className = 'none'; e.textContent = 'The meaning lane has not exported probes for this brain, so no facet is read from its state.'; mindEl.facets.append(e); }
  else for (const [f, label] of FACETS) {
    const pf = p.facets[f];
    const a = document.createElement('span'); a.className = 'f'; a.textContent = label;
    const v = document.createElement('span'); v.className = `v${atChance(pf) ? ' chance' : ''}`; v.dataset.facet = f; v.textContent = pf ? '…' : 'no probe';
    const c = document.createElement('span'); c.className = `c${atChance(pf) ? ' chance' : ''}`;
    if (pf?.accuracy != null) {
      c.textContent = atChance(pf) ? 'at chance' : `${Math.round(100 * pf.accuracy)}%`;
      c.title = `Its probe reads this facet right on ${Math.round(100 * pf.accuracy)} % of scenes it never saw; the commonest answer alone gets ${Math.round(100 * (pf.base_rate ?? 0))} %.`;
    }
    mindEl.facets.append(a, v, c);
  }
  mindEl.thing.textContent = 'click a thing';
  $('im-note').hidden = !p;
}
function showMind(mind, focusId) {
  if (!state.trained || !mindEl.card) return;
  const t = focusId && room.things.get(focusId);
  mindEl.thing.textContent = t ? `the ${t.kind} in focus` : 'nothing in focus';
  for (const [f, got] of Object.entries(mind.facets || {})) {
    const v = mindEl.facets.querySelector(`[data-facet="${f}"]`);
    if (!v) continue;
    const k = trained.probes?.facets?.[f]?.classes?.length || 2;
    v.textContent = `${FACET_VALUE[f]?.[got.value] ?? got.value} ${got.p.toFixed(2)}`;
    v.title = `Its probe's share for this answer at this moment, ${got.p.toFixed(2)}, among ${k} answers (one in ${k} by chance: the mark on the bar).`;
    const bar = document.createElement('i'); bar.style.width = `${Math.round(got.p * 100)}%`;
    const tick = document.createElement('b'); tick.className = 'tick'; tick.style.left = `${Math.round(100 / k)}%`;
    const track = document.createElement('span'); track.className = 'track'; track.append(bar, tick); v.append(track);
  }
  const w = mind.voice?.word;
  const link = w ? (state.lastReply?.knows || []).find((k) => k.kind === w) : null;
  mindEl.voice.textContent = '';
  if (w) {
    mindEl.voice.append('Its voice is ready to say ');
    const b = document.createElement('b'); b.textContent = w; mindEl.voice.append(b, ` (${mind.voice.level.toFixed(2)})`);
    if (link && soundPcm.get(link.id)) {
      const btn = document.createElement('button'); btn.type = 'button'; btn.textContent = 'hear it';
      btn.addEventListener('click', async () => { await audio.unlock(); const k = soundPcm.get(link.id); if (k) audio.speakPcm(k.pcm, k.rate); });
      mindEl.voice.append(btn);
    }
  }
  const kind = t ? t.kind : 'thing';
  mindEl.outside.textContent = `Outside its state: the written word (it never sees letters); the sound of the word, which the page keeps in its own sound memory${link ? `, linked to the ${kind}` : ''}.`;
}

async function askIt(text) {
  if (!state.trained || trained.busy) return;
  const words = text.toLowerCase().replace(/\bcolor\b/g, 'colour').replace(/[^a-z<>\s]/g, ' ').split(/\s+/).filter(Boolean);
  const heard = words.filter((w) => trained.vocab.has(w)), unheard = words.filter((w) => !trained.vocab.has(w));
  if (!heard.length) { logLine(`It knows none of these words. Its words are listed under <b>Its words</b>.`, 'warn'); return; }
  const scan = isScan(heard);
  // the thing a question is about: one it names (the trainers attend to it), else the thing clicked
  const named = heard.find((w) => Object.values(WORLD).some((x) => x && x.kind === w));
  let focusId = null;
  if (named) focusId = [...room.things.values()].filter((t) => WORLD[t.kind]?.kind === named).sort((a, b) => distanceOf(a.id) - distanceOf(b.id))[0]?.id || null;
  else if (!scan) focusId = trained.focus;
  if (named && !focusId) { logLine(`There is no ${esc(named)} on the table.`, 'warn'); return; }
  if (!scan && !focusId) { logLine('Click a thing first: a question like this is about the thing in focus.', 'warn'); return; }
  const fk = focusId ? room.things.get(focusId)?.kind : null;
  if (focusId && !WORLD[fk]) { logLine(`The ${esc(fk)} is in focus, and the trained brain does not see it: its training world had no ${esc(fk)}.`, 'warn'); return; }
  trained.busy = true; trained.open = null; askEl.fix.hidden = true; ui.pistachio.classList.remove('ask');
  const id = ++trained.serial;
  logLine(`<span class="who">you</span> ${esc(heard.join(' '))}?${fk ? ` <span class="dim">(the ${esc(fk)} in focus)</span>` : ''}${unheard.length ? ` <span class="dim">· words it never heard, left out: ${esc(unheard.join(', '))}</span>` : ''}`, 'q');
  if (focusId) { state.cue = cueFor(focusId); state.pointed = { id: focusId, until: performance.now() + 9000 }; if (named) { trained.focus = focusId; askNote(); } }
  const said = [];
  let li = null, recalled = null;
  try {
    await trainedOp({ op: 'begin' });
    if (sub.el.hidden || !sub.words.length) subtitle(text);
    for (const w of heard) { subtitleHeard(w); await trainedOp({ op: 'moment', hear: w, more: true, focus: focusId }); }
    for (const x of sub.words) x.span.classList.add('on');
    subtitleDone(1600);
    const say = (w) => { if (w && said[said.length - 1] !== w) { said.push(w); bubble(said.join(', '), 'it'); const how = sayWord(w); li ||= logLine('', 'a'); li.innerHTML = `<span class="who">parrot</span> <b>${esc(said.join(', '))}</b> <span class="dim">(${esc(how)})</span>`; } };
    if (scan) {
      const order = trainedThings(focusId, null).things.filter((t) => !t.focus).map((t) => t.id).sort(() => Math.random() - 0.5);
      for (const g of order) {
        state.cue = cueFor(g); state.pointed = { id: g, until: performance.now() + 900 };
        const r = await trainedOp({ op: 'moment', hear: null, more: false, focus: focusId, glimpseId: g });
        recalled ||= r.recalled; say(r.said);
      }
    } else {
      for (let k = 0; k < trained.turn; k++) {
        const r = await trainedOp({ op: 'moment', hear: null, more: false, focus: focusId });
        recalled ||= r.recalled;
        if (!r.said && said.length) break;
        say(r.said);
      }
    }
    if (!said.length) logLine('<span class="who">it</span> <span class="dim">said nothing in its turn</span>', 'a');
    if (recalled) logLine(`<span class="dim">its word records brought back “${esc(recalled)}” to its ear at its turn</span>`);
    const want = expected(heard, fk && WORLD[fk].kind, trainedThings(focusId, null).things);
    if (want) {
      const right = want.length === said.length && want.every((w) => said.includes(w));
      logLine(right ? `<span class="ok">right</span> <span class="dim">· a pistachio pays it</span>` : `<span class="no">wrong</span> <span class="dim">· the answer: ${esc(want.join(', ') || 'none')}${want.some((w) => !trained.vocab.has(w)) ? ' (a word it never heard)' : ''} · type the right word below</span>`, right ? 'judge ok' : 'judge no');
      if (!right) askEl.word.value = want.find((w) => trained.vocab.has(w)) || '';
    } else if (said.length) logLine('<span class="dim">The page does not judge this question: give a pistachio if it is right, or type the right word.</span>');
    trained.last = { id, question: heard.join(' '), unheard, focus: fk, said: [...said], expected: want, right: want ? want.length === said.length && want.every((w) => said.includes(w)) : null, recalled };
    trained.open = said.length ? { id, said, at: performance.now() } : null;
    askEl.fix.hidden = !said.length;
    ui.pistachio.classList.toggle('ask', !!said.length);
    if (!said.length) await trainedOp({ op: 'over' });
  } catch (error) { logLine(`The trained brain stopped: ${esc(error.message)}`, 'warn'); }
  finally {
    trained.busy = false; trained.quietUntil = performance.now() + 2500;
    // the thing in focus stays the one clicked (a scan's glimpses visited the others)
    if (trained.focus && room.things.has(trained.focus)) state.pointed = { id: trained.focus, until: performance.now() + 1e9 };
  }
}
async function payAnswer(open) {
  if (trained.open !== open) return;
  trained.open = null; askEl.fix.hidden = true; ui.pistachio.classList.remove('ask');
  const r = await trainedOp({ op: 'pistachio' });
  logLine(`<span class="nut">a pistachio</span> for “${esc(open.said.join(', '))}” <span class="dim">· ${r.lessons} small lesson${r.lessons === 1 ? '' : 's'}, one a word it said, its own words the labels</span>`, 'p');
}
async function correctIt(word) {
  const open = trained.open;
  if (!open || trained.busy) return;
  word = word.toLowerCase().trim();
  if (!trained.vocab.has(word)) { logLine(`It never heard “${esc(word)}”: its training gave it no such word, so it cannot keep it.`, 'warn'); return; }
  trained.open = null; askEl.fix.hidden = true; ui.pistachio.classList.remove('ask');
  trained.busy = true;
  try {
    subtitle(word); subtitleHeard(word); subtitleDone(1600);
    const r = await trainedOp({ op: 'correct', word, focus: trained.focus });
    trained.lastCorrection = { word, wrote: !!r.wrote, records: r.records };
    logLine(`<span class="who">you</span> ${esc(word)} <span class="dim">· ${r.wrote ? `kept as a word record under the pattern of the question's end (${r.records.toLocaleString('en')} records); it hears the word` : 'heard, and no record kept'}</span>`, 'c');
  } finally { trained.busy = false; trained.quietUntil = performance.now() + 1500; }
}
// How this brain works: the explainer in a drawer (or a tab); the "how?" links open it at their part
function explainer(anchor = '') {
  const frame = $('ed-frame'), url = `brain-explainer.html${anchor}`;
  if (frame.getAttribute('src') !== url) frame.setAttribute('src', url);
  $('ed-tab').href = url; $('explain-drawer').hidden = false;
}
$('how-brain').addEventListener('click', () => explainer());
$('ed-close').addEventListener('click', () => { $('explain-drawer').hidden = true; });
window.addEventListener('keydown', (e) => { if (e.key === 'Escape') $('explain-drawer').hidden = true; });
for (const a of document.querySelectorAll('a.how')) {
  a.hidden = false;
  a.addEventListener('click', (e) => { if (e.metaKey || e.ctrlKey || e.shiftKey) return; e.preventDefault(); explainer(new URL(a.href).hash); });
}
// the preset questions are spoken in the visitor's voice (voice/questions.json names its clips, played in turn:
// the first ask of a question has a lead-in); a pistachio for an answer brings a word of praise. The voice is a
// voiceover: the brain takes the typed words.
const voiceLines = fetch('voice/questions.json').then((r) => (r.ok ? r.json() : {})).catch(() => ({}));
const normQ = (t) => t.toLowerCase().replace(/[^a-z ]/g, ' ').replace(/\s+/g, ' ').trim();
const askedTimes = new Map(); let praised = 0;
async function speakQuestion(q) {
  const key = normQ(q), list = (await voiceLines).questions?.[key];
  if (!list?.length) return 0;
  const n = askedTimes.get(key) || 0; askedTimes.set(key, n + 1);
  try { return 1000 * (await audio.playClip(`voice/${list[Math.min(n, list.length - 1)]}`)); } catch (e) { return 0; }
}
async function speakPraise() {
  const list = Object.values((await voiceLines).reactions || {});
  if (!list.length) return 0;
  try { return 1000 * (await audio.playClip(`voice/${list[praised++ % list.length]}`)); } catch (e) { return 0; }
}
askEl.form?.addEventListener('submit', async (e) => {
  e.preventDefault(); const q = askEl.q.value.trim();
  if (!q || trained.busy) return;
  audio.unlock().catch(() => {});
  brain3d?.scan?.question(q); subtitle(q);
  const ms = await speakQuestion(q);
  if (ms > 0) await new Promise((r) => setTimeout(r, Math.max(0, ms - 600))); // the brain hears the typed words as the voice ends
  askIt(q);
});
$('ask-preset')?.addEventListener('change', (e) => { askEl.q.value = e.target.value; });
if (DEMO) askEl.q.value = $('ask-preset')?.value || ''; // the demo asks the preset picked (no typed questions)
$('ask-nut')?.addEventListener('click', () => ui.pistachio.click());
$('ask-forget')?.addEventListener('click', async () => { // every sound it learned, its links and its paid calls: gone, and a fresh start
  try { for (const k of Object.keys(localStorage)) if (/^parrot\.(memory|words)/.test(k)) localStorage.removeItem(k); } catch (e) { /* storage blocked */ }
  trained.wordSounds = {};
  try { if (state.brainReady) await brain.call('forget'); } catch (e) { /* the reload starts it clean anyway */ }
  location.reload();
});
$('ask-mic')?.addEventListener('click', (e) => { e.preventDefault(); toggleMic(); });
askEl.fix?.addEventListener('submit', (e) => { e.preventDefault(); const w = askEl.word.value.trim(); if (w) correctIt(w); });
for (const b of document.querySelectorAll('[data-ask]')) b.addEventListener('click', () => { askEl.q.value = b.dataset.ask; askEl.q.focus(); });

// --- the frame loop ----------------------------------------------------------------------------------------
let last = performance.now(), slowSince = 0;
function frame(now) {
  const dt = Math.min(0.05, (now - last) / 1000); last = now;
  if (parrot) {
    const loud = audio.loudness(now);
    const eating = nut ? nut.update(dt) : null;
    if (eating !== null) { parrot.joints.set('beak_open', eating); state.wasEating = true; }
    else {
      state.beakEnv = Math.max(loud, (state.beakEnv || 0) * Math.exp(-dt / 0.12)); // opens at once with the sound, closes over about a tenth of a second
      if (state.beakEnv > 0.01 || state.wasSpeaking || state.wasEating) { parrot.joints.set('beak_open', 33 * Math.sqrt(state.beakEnv)); state.wasSpeaking = state.beakEnv > 0.01; state.wasEating = false; }
    }
    ui.voiceLevel.style.width = `${Math.round(loud * 100)}%`;
    ui.earLevel.style.width = `${Math.round(audio.level * 100)}%`;
    $('mic-level').style.width = `${Math.round(audio.level * 100)}%`;
    if (!DEMO) { drawBands(); drawTurns(now); }
    parrot.update(dt);
    placeFocus();
    if (now - state.lastMomentAt >= MOMENT_MS || !state.lastMomentAt) { state.lastMomentAt = now; moment(now); }
    if (!DEMO) view?.setJoints(parrot.joints.pos, parrot.joints.target);
    syncTags(); if (!DEMO) drawFields(); placeBubble();
  }
  updateCoach();
  controls.update();
  renderer.shadowMap.needsUpdate = true;
  renderer.render(room.scene, camera);
  if (!DEMO) view?.frame(dt);
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
ui.clear.addEventListener('click', () => { state.script = null; room.clear(); state.subject = null; view?.clearTuning(); state.pointed = null; trained.focus = null; askNote(); });
// The pistachio: thrown from the visitor's side, caught in the beak, nibbled and eaten. The reward
// reaches the brain when the nut is in the beak, not on the click.
let nut = null;
ui.pistachio.addEventListener('click', () => {
  if (!parrot) return;
  nut ||= new Pistachio(room.scene);
  const from = camera.position.clone().lerp(new THREE.Vector3(0, BAR_Y + 0.2, 0), 0.35); from.y -= 0.1;
  const forAnswer = state.trained && trained.open && !trained.busy ? trained.open : null;
  const thrown = nut.throw(from, parrot, () => {
    if (forAnswer) payAnswer(forAnswer); else state.reward = 1;
    state.pistachios += 1; ui.pistachios.textContent = String(state.pistachios);
    brain3d?.reward();
    $('dopamine').hidden = false;
    $('dopamine-note').textContent = forAnswer ? ` It pays the trained brain\u2019s reply \u201c${forAnswer.said.join(', ')}\u201d: one small lesson for each word it said (a word once), its own words the labels; the tracts the lesson changed glow.`
      : typeof state.lastReply?.vta === 'number' ? 'Its dopamine runs out from the VTA (the gold wash), and the tracts it strengthens glow.' : 'This brain has no dopamine signal: the view marks the pistachio arriving, and no synapse changes.';
    clearTimeout(state.dopTimer); state.dopTimer = setTimeout(() => { $('dopamine').hidden = true; }, 4200);
  }, () => {});
  if (!thrown) toast('It is eating the last one', '', 1400);
  else if (forAnswer) speakPraise();
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
// The microphone: on from the start (the browser asks the first time); both mic buttons turn it on and
// off. A click sets what you want at once (the buttons light with it) and the page brings the microphone
// to that state, one start or stop at a time, so no click is lost while a start is under way.
function micError(error) {
  const name = error?.name || '';
  if (!window.isSecureContext) return 'The microphone needs a secure page. Open it at http://localhost:8842/ (on this computer) or over https.';
  if (name === 'NotAllowedError' || name === 'SecurityError') return 'The microphone is blocked for this page. Allow it in the address bar (the site settings by the address), then press Mic again.';
  if (name === 'NotFoundError' || name === 'OverconstrainedError') return 'No microphone was found. Plug one in or choose one in your computer’s sound settings, then try again.';
  if (name === 'NotReadableError') return 'The microphone is busy in another app. Close it there, then try again.';
  return `The microphone did not start: ${error?.message || name || 'unknown error'}.`;
}
const mic = { want: false, run: null, toggles: 0 };
function micUi() {
  for (const b of [ui.mic, $('ask-mic')]) {
    if (!b) continue;
    b.setAttribute('aria-pressed', String(mic.want)); b.classList.toggle('starting', mic.want && !audio.mic);
  }
  const mini = $('ask-mic'); if (mini) mini.textContent = mic.want ? 'Mic on' : 'Mic off';
  document.body.dataset.mic = mic.want ? 'on' : 'off';
}
function settleMic() { // bring the microphone to what was asked, one change at a time
  if (mic.run) return mic.run;
  mic.run = (async () => {
    while (mic.want !== audio.mic) {
      if (mic.want) { try { await audio.startMic(); } catch (error) { mic.want = false; toast(micError(error), 'bad', 6000); } }
      else audio.stopMic();
    }
  })().finally(() => { mic.run = null; micUi(); });
  micUi();
  return mic.run;
}
function setMic(on) { mic.want = !!on; micUi(); return settleMic(); }
function toggleMic() { mic.toggles += 1; return setMic(!mic.want); }
ui.mic.addEventListener('click', (e) => { e.preventDefault(); toggleMic(); });
$('talk-yes').addEventListener('click', () => { $('talk').hidden = true; setMic(true); });
$('talk-no').addEventListener('click', () => { $('talk').hidden = true; setMic(false); audio.unlock().catch(() => {}); });
function offerMic() { if (query.get('mic') !== 'off') setMic(true); } // on by default (?mic=off leaves it off)
$('home').addEventListener('click', () => { camera.position.copy(HOME.pos); controls.target.copy(HOME.at); controls.update(); });

// --- start --------------------------------------------------------------------------------------------------------
async function start() {
  offerMic(); // the microphone from the start: the browser asks the first time
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
    // the meaning lane's demo room (demo_stage.py): a red apple left and far, a blue block, a white cup
    // behind, a yellow key in front and a green ball to the parrot's right (its directions; 0.4 m a unit)
    const at = (deg, r) => [r * Math.sin(deg * Math.PI / 180), r * Math.cos(deg * Math.PI / 180)];
    for (const [kind, deg, r, yaw] of [['apple', 70, 0.6, 30], ['block', 120, 0.4, 25], ['cup', 180, 0.36, 200], ['key', -20, 0.4, 60], ['greenball', -80, 0.4, 0]]) await place(kind, ...at(deg, r), yaw);
    state.subject = [...room.things.keys()][0];
    resize();
    state.phase = 'idle';
    requestAnimationFrame(frame);
  } catch (error) {
    setStatus(`The room failed to load: ${error.message}`, 'error');
    throw error;
  }
  brain3d = new Brain3D($('brain3d'), $('b3-labels'), { scan: DEMO });
  if (DEMO) { // the demo layout: the eyes in the scan's boxes, the chat over the brain, the switch in its corner
    brain3d.scan.eyes(ui.eyeL, ui.eyeR);
    const corner = document.createElement('div'); corner.className = 'scan-corner';
    corner.append($('brain-kind'), $('how-brain'));
    $('view-brain').append(corner, $('ask'));
  }
  memview = new MemoryView($('memory'));
  for (const [tab, panel] of [['tab-brain', 'view-brain'], ['tab-memory', 'view-memory']]) {
    $(tab).addEventListener('click', () => {
      for (const [t, v] of [['tab-brain', 'view-brain'], ['tab-memory', 'view-memory']]) { $(t).setAttribute('aria-selected', String(t === tab)); $(v).hidden = t !== tab; }
      state.tab = tab; if (tab === 'tab-memory') memview.layout(); else brain3d.resize();
      void panel;
    });
  }
  view = new BrainView({ regions: $('brain'), units: $('dist-units'), tuning: $('dist-tuning'), readout: $('dist-readout'), silence: ui.silence, joints: $('joints') });
  window.parrotPage = { room, state, eyes, audio, trained, controls, get brainView() { return view; }, get brain3d() { return brain3d; }, get parrot() { return parrot; }, place, addThing, move: (id, x, z) => room.move(id, x, z), remove: (id) => room.remove(id),
    label: (k) => KINDS[k]?.label || k, describe: () => room.describe(), load: (d) => room.load(d), script: runScript, TEST, setLook, setMode, distanceOf, camera, THREE,
    view(name) { const v = VIEWS[name]; if (!v) return; camera.position.set(...v[0]); controls.target.set(...v[1]); controls.update(); },
    screenOf(x, y, z) { const v = new THREE.Vector3(x, y, z).project(camera); const r = canvas.getBoundingClientRect(); return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; } };
  if (query.get('brain') === 'off') { setStatus('Ready (no brain)', 'ready'); document.body.dataset.ready = '1'; return; }
  // the composed brain (the parrot-brain lane's), or the placeholder; the placeholder also when the
  // composed brain does not start
  // the switch's trained entries, each named by its version: what it does well, and what it lacks
  const options = fetch(new URL('manifest.json', PACK)).then((r) => r.json()).then((m) => {
    const sel = $('brain-kind'), first = sel.querySelector('option[value="trained"]');
    const versions = m.trained_versions || (m.trained_version ? { trained: m.trained_version } : {});
    if (!m.hosts?.trained) first?.remove();
    let after = first;
    for (const [key, v] of Object.entries(versions)) {
      let o = sel.querySelector(`option[value="${key}"]`);
      if (!o) { o = document.createElement('option'); o.value = key; after.after(o); }
      o.textContent = `trained: ${v.label}${v.good ? ` · ${v.good}` : ''}`;
      o.title = [v.good && `Does well: ${v.good}.`, v.lost && `Lacks: ${v.lost}.`].filter(Boolean).join(' ');
      after = o;
    }
  }).catch(() => {});
  let wanted = query.get('brain') || (() => { try { return localStorage.getItem('parrot.brain'); } catch (e) { return null; } })() || 'trained';
  const config = { eye: { w: EYE.w, h: EYE.h, field: EYE.field, vfield: EYE.vfield, fovea: EYE.fovea, axis: EYE.axis } };
  try {
    let out;
    try {
      brain = new BrainWorker();
      out = await brain.call('init', { pack: PACK, brain: wanted, config });
    } catch (error) { // the trained brain falls back to the composed one, and that to the placeholder
      if (wanted === 'placeholder') throw error;
      const next = wanted === 'trained' ? 'composed' : 'placeholder';
      console.warn(`The ${wanted} brain did not start (${error.message}); the ${next} brain runs.`);
      toast(`The ${wanted} brain did not start (${error.message}); the ${next} brain runs.`, 'bad', 6000);
      brain.worker.terminate(); wanted = next;
      brain = new BrainWorker();
      try { out = await brain.call('init', { pack: PACK, brain: wanted, config }); } catch (again) {
        if (wanted === 'placeholder') throw again;
        brain.worker.terminate(); wanted = 'placeholder';
        brain = new BrainWorker();
        out = await brain.call('init', { pack: PACK, brain: wanted, config });
      }
    }
    desc = out;
    state.composed = !desc.placeholder;
    state.trained = desc.name === 'trained';
    document.body.dataset.brain = state.trained ? 'trained' : state.composed ? 'composed' : 'placeholder';
    await options;
    $('brain-kind').value = state.trained ? out.brain_kind || 'trained' : document.body.dataset.brain;
    if (state.trained) setupTrained(desc.trained);
    view.setup(desc, rig.joints);
    for (const r of desc.repertoire || []) addChip(r);
    // every start begins from the shipped words: the sounds, links and paid calls of a visit are not kept
    // past it (Forget my sounds clears them within one)
    try { for (const k of Object.keys(localStorage)) if (/^parrot\.(memory|words)/.test(k)) localStorage.removeItem(k); localStorage.setItem(START_KEY, String(Date.now())); } catch (e) { /* storage blocked */ }
    trained.wordSounds = {};
    if (state.trained || desc.name === 'trained') { // a first visit: the words taught in a recorded voice (voice/words.json), its starting words
      try {
        const bundle = await (await fetch('voice/words.json')).json();
        if (bundle?.memory?.records?.length) {
          const out = await brain.call('remember', { saved: bundle.memory }); syncChips(out.repertoire || []); memview?.update(out.memory);
          trained.wordSounds = { ...bundle.words }; trained.bundleIds = new Set(Object.values(bundle.words));
        }
      } catch (e) { /* no bundle: it starts with no words of its own */ }
    }
    brain3d.setup(desc);
    ui.sub.textContent = desc.placeholder ? `${desc.title} · ${desc.neurons} units` : state.trained ? `${desc.title} · ${desc.neurons.toLocaleString('en')} neurons, the trained brain's ${desc.trained.neurons.toLocaleString('en')} among them`
      : `${desc.title || desc.name} · ${desc.neurons.toLocaleString('en')} neurons${desc.newborn ? ' · a newborn' : ''}`;
    const g = (desc.groups || []).find((x) => x.variable === 'distance');
    void g; // the brain panel names the distance card (the arcopallium's distance neurons)
    state.brainReady = true;
    setStatus('Ready', 'ready');
    ui.status.title = `Brain loaded in ${(desc.startup_ms / 1000).toFixed(1)} s`;
    document.body.dataset.ready = '1';
    if (query.get('test')) runScript(TEST);
  } catch (error) {
    setStatus(`The brain failed to load: ${error.message}`, 'error');
    document.body.dataset.ready = '1';
  }
}
start();
