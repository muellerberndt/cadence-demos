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
  ask: ['Ask it', 'In <b>Curious</b>: pick a question and press <b>Ask</b>, or ask it yourself about the <b>thing</b> in focus. In <b>Listen to me</b>: say a word, and it says it back.'],
  asking: ['Listen', 'It hears the question as one utterance, each word it knows lighting as it is said, then answers in the gap after it.'],
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
  if (!state.dragging.moved) { flow.pointedAt = performance.now(); state.cue = cueFor(state.dragging.id); state.focus = { id: state.dragging.id, why: 'you pointed at it' }; state.pointed = { id: state.dragging.id, until: performance.now() + (state.trained ? POINT_MS : 6000), cued: performance.now() }; if (flow.mode === 'curious') { trained.focus = state.dragging.id; askNote(); } }
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
    const seenKind = state.focus ? room.things.get(state.focus.id)?.kind || null : null;
    const focusKind = state.trained ? WORLD[seenKind]?.kind || null : seenKind; // the hearing layer links a sound to the word for the thing in focus
    const scene = state.composed && room.version !== state.sentVersion ? room.describe() : null;
    if (scene) state.sentVersion = room.version;
    // while the trained brain hears a question and answers, the hearing layer's calls wait
    const calls = voiceOk && !(state.trained && (trained.busy || now < trained.quietUntil));
    // how it attends (flow.mode), and the page's knowledge of its own voice sounding (so its ear does not take its voice for yours)
    const attend = state.trained ? { mode: flow.mode, own_voice: audio.ownVoice(now), hold: flow.asking || now - (flow.pointedAt || -1e9) < POINTED_HOLD_MS } : {}; // (hold: a question is about to sound, or you just pointed at a thing and may ask about it, so it says nothing by itself)
    reply = await brain.call('step', { meta: { t: state.moment, reward, voice_ok: calls, cue, things: room.things.size, focus_kind: focusKind, scene, learn: true, viz: !!state.composed && state.moment % VIZ_EVERY === 0, memory_shown: state.tab === 'tab-memory', ...attend, ...(op ? { meaning: op.meta } : {}) }, arrays: { left, right, proprio: pro, mel: sound.mel, audio: sound.audio, pcm: sound.pcm } },
      [left.buffer, right.buffer, pro.buffer, sound.mel.buffer, sound.audio.buffer, sound.pcm.buffer]);
  } catch (error) { state.pending = false; op?.reject(error); setStatus(`The brain stopped: ${error.message}`, 'error'); state.brainReady = false; return; }
  state.pending = false;
  state.moment += 1;
  state.lastReply = reply;
  // each moment's cost (for the page's checks): the worker's time, the trained brain's share, whether a sound was being followed
  flow.perf.push({ ms: reply.worker_ms, round: Math.round(performance.now() - now), op: op ? op.meta.op : null, focus: op?.meta.focus ? room.things.get(op.meta.focus)?.kind : null, hear: op?.meta.hear ?? null, said: reply.meaning?.said ?? null, brain: reply.meaning?.ms ?? null, hearing: !!reply.hearing, at: Math.round(now) }); if (flow.perf.length > 900) flow.perf.shift();
  if (op) {
    op.resolve(reply.meaning || {});
    if (op.meta.op !== 'look' && op.meta.op !== 'clear') gaze.clear = true; // an exchange's moment: the next looks start from a cleared state
    if (reply.meaning?.mind && op.meta.op === 'look' && op.meta.read) { showMind(reply.meaning.mind, op.meta.focus); brain3d?.scan?.holds?.(reply.meaning.mind.facets, room.things.get(op.meta.focus)?.kind); }
    else if (op.meta.op !== 'look' || !op.meta.read) brain3d?.scan?.holds?.(null);
  }
  if (state.mode === 'brain' && reply.arrays.angles && state.composed) { // the composed brain's body: its angles, smoothed by the page
    reply.arrays.angles.forEach((v, i) => { if (i < parrot.joints.n && parrot.joints.spec[i].name !== 'beak_open') parrot.joints.target[i] = v; });
  } else if (state.mode === 'brain' && reply.arrays.targets) parrot.joints.setUnitTargets(reply.arrays.targets);
  if (state.trained && state.mode === 'brain') attendHead(performance.now());
  if (reply.arrays.left && desc?.eye) { drawHostEye(ui.eyeL, reply.arrays.left, desc.eye.w, desc.eye.h, false); drawHostEye(ui.eyeR, reply.arrays.right, desc.eye.w, desc.eye.h, true); }
  const subject = state.subject ? distanceOf(state.subject) : null;
  if (!DEMO) view.update(reply, reply.arrays, subject); // the detail panel's cards (hidden in the demo layout: nothing drawn for them)
  brain3d?.update(reply.arrays.activity, reply);
  if (reply.arrays.voice?.length) { // the voice motor's frames: the parrot says them
    const said = reply.said_sound || reply.said; // the hearing layer's sound (a call, a babble, a sound it keeps: said by itself or said back)
    const own = said?.source === 'you' ? ownTake(said.id) : null; // a starting word: its own rendering of it
    const spoken = own ? audio.speakOwn(own.pcm, own.rate) : reply.arrays.voice_pcm?.length ? audio.speakPcm(reply.arrays.voice_pcm, reply.voice_rate || 8000) : audio.speak(reply.arrays.voice); // a remembered sound: its own audio
    const what = said ? (said.source === 'you' ? 'a sound learned from you' : said.source === 'recording' ? `a ${said.tag}` : 'a babble') : 'a sound';
    if (spoken) { ui.voiceNote.textContent = `${what}, ${(spoken.env.length / 100).toFixed(1)} s`; state.saying = said?.id; markChip(said?.id); }
    if (spoken && state.trained && said?.source === 'you') saidSound(said, !!own);
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
  $('you-focus').hidden = !((state.trained && flow.mode === 'listen') || (state.focusYou && performance.now() - state.focusYou < 2600));
  if (reply.memory) memview?.update(reply.memory);
  // the badge says what it has learned so far
  const words = reply.words || 0, lessons = reply.lessons || 0;
  const badge = state.trained ? `trained tonight: names of things${words ? `; ${words} sound${words === 1 ? '' : 's'} from you` : ''}`
    : words || lessons ? `learning: ${words} word${words === 1 ? '' : 's'}${state.composed ? `, distance taught by ${lessons} head turn${lessons === 1 ? '' : 's'}` : ''}` : 'a newborn: it has learned nothing yet';
  const el = document.querySelector('.newborn');
  if (el && el.firstChild.textContent !== badge) el.firstChild.textContent = badge;
  if (reply.repertoire) syncChips(reply.repertoire, reply.sayable); // (the sounds that changed, and the ids of all it can say)
  // every sound the ear heard this moment (a long moment can end several), in order; every start begins from the
  // starting memory, so nothing heard is kept past the visit
  // each word known in the utterance as it is spoken (the hearing layer's follower), before the utterance's end
  if (state.trained) for (const s of reply.spotted || []) spottedWord(s);
  for (const h of reply.heard_sounds || (reply.heard_sound ? [reply.heard_sound] : [])) {
    if (h.word) console.log(`[ear] heard a sound: record ${h.slot}, linked to "${h.word}" (link ${h.link})`); else console.log(`[ear] heard a sound: record ${h.slot}, linked to no word`);
    window.parrotPage.lastHeardSound = { ...h, at: performance.now() };
    // what the hearing memory made of the sound: known (its record told again), and the word its record links to
    brain3d?.scan?.heardSound({ recognized: !!h.known || !!h.word, kind: h.word || null, strength: h.link || 0, slot: h.slot });
    if (h.word) lightThing(h.word);
    if (state.trained) heardUtterance(h);
  }
  if (state.trained) hearingNow(!!reply.hearing); // the ear is in an utterance
  if (reply.linked) showLinked(reply.linked); // a pistachio for a word it said by itself with a thing in focus: the sound and the thing's word are linked
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
  // joint attention: a thing you pointed at holds the parrot's attention for some seconds
  if (state.pointed && performance.now() < state.pointed.until && room.things.has(state.pointed.id)) {
    state.focus = { id: state.pointed.id, why: state.pointed.why || 'you pointed at it' };
    if (state.trained && performance.now() - (state.pointed.cued || 0) > 1500) { state.cue = cueFor(state.pointed.id); state.pointed.cued = performance.now(); } // its head stays with it
  } else state.pointed = null;
  if (state.trained) attendFocus();
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

// --- its sounds: the repertoire's chips, what it learned from you, the turns
// Sounds learned in a visit last for the visit: every start begins from the starting memory (an older page
// kept them in this browser; that copy is cleared).
const learnedStore = { clear() { try { localStorage.removeItem('parrot.memory'); } catch (e) { /* storage blocked */ } } };
function syncChips(list, sayable = null) {
  const ids = new Set(sayable || list.map((r) => r.id));
  for (const c of ui.sounds.querySelectorAll('.chip-s.you')) if (!ids.has(c.dataset.sound)) { soundPcm.delete(c.dataset.sound); c.remove(); }
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
// the parrot's own rendering of each starting sound (voice/parrot/<slot>.wav), used while the record holds the
// sound it was made from (its length and summed level match); a sound told again, or learned from you, is said
// through the page's parrot voice instead
const ownTakes = new Map();
const pcmPrint = (pcm) => { let a = 0; for (const v of pcm) a += Math.abs(v); return { n: pcm.length, abs: a }; };
function ownTake(id) {
  const own = ownTakes.get(id), kept = soundPcm.get(id);
  if (!own || !kept?.pcm?.length) return null;
  return pcmPrint(kept.pcm).n === own.n ? own : null; // (a word told again is mixed into the record at the record's own length: the rendering stands)
}
async function loadOwnTakes(renderings) {
  for (const [slot, r] of Object.entries(renderings || {})) {
    try {
      const b = new DataView(await (await fetch(`voice/${r.file}`)).arrayBuffer());
      let off = 12, rate = 16000, data = null;
      while (off + 8 <= b.byteLength) { // a 16-bit mono wav
        const id = String.fromCharCode(b.getUint8(off), b.getUint8(off + 1), b.getUint8(off + 2), b.getUint8(off + 3)), size = b.getUint32(off + 4, true);
        if (id === 'fmt ') rate = b.getUint32(off + 12, true);
        if (id === 'data') { data = new Float32Array(size / 2); for (let i = 0; i < data.length; i++) data[i] = b.getInt16(off + 8 + 2 * i, true) / 32768; break; }
        off += 8 + size + (size % 2);
      }
      if (data) ownTakes.set(`you-${slot}`, { pcm: data, rate, n: r.n, abs: r.abs, word: r.word });
    } catch (e) { /* that sound is said through the parrot voice */ }
  }
}
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
const OPEN_MS = 9000; // an answer waits this long for its pistachio
const POINTED_HOLD_MS = 3000; // after you point at a thing it says nothing by itself for this long: your question may follow
const gaze = { id: null, n: 0, clear: true }; // the looks at the thing in focus since its state was cleared
const trained = { listen: null, busy: false, queue: [], lastAt: 0, momentMs: 300, turn: 3, vocab: new Set(), colours: [], materials: [], focus: null, open: null, quietUntil: 0, serial: 0, log: [] };

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
  if (!trained.queue.length) { // between questions it keeps looking, its voice held, so its mind holds the thing in focus
    if (now - trained.lastAt < trained.momentMs - 8) return null; // (a look every 300 ms; an exchange's moments run with every moment of the body)
    if (trained.open && now - trained.open.at > OPEN_MS) { trained.open = null; ui.pistachio.classList.remove('ask'); trained.queue.push({ meta: { op: 'over' }, resolve() {}, reject() {} }); gaze.clear = true; } // an answer no pistachio followed
    else if (trained.open) return null; // an answer waits for its pistachio: its brain rests on the reply (measured: with looks between the reply and the pistachio the lesson unsettles other answers, 65 of 72 right; resting, 143 of 144)
    else if (flow.hearing) return null; // an utterance is being heard: no look, so the moment it ends in carries the hearing alone and the answer comes sooner
    else {
      const f = !trained.busy && flow.mode === 'curious' && lookFocus();
      if (!f) { gaze.id = null; return null; }
      // the probes read the thing in focus at any look from a cleared state (fitted over looks 1 to 4 after a
      // clearing: kind .99, colour .99, round 1.00 on rooms held out; a state that carries an exchange they
      // misread): a new thing in focus, or an exchange behind it, clears the state first. An answer that waits
      // for its pistachio is not cleared (the lesson needs its moments).
      if ((gaze.id !== f || gaze.clear) && !trained.open) { gaze.id = f; gaze.clear = false; gaze.n = 0; trained.queue.push({ meta: { op: 'clear' }, resolve() {}, reject() {} }); }
      else { if (gaze.id === f && !gaze.clear) gaze.n += 1; else gaze.n = 0; trained.queue.push({ meta: { op: 'look', focus: f, read: gaze.n >= 1 }, resolve() {}, reject() {} }); }
    }
  }
  trained.lastAt = now;
  const op = trained.queue.shift();
  if (op.meta.op === 'moment' || op.meta.op === 'correct' || op.meta.op === 'look' || op.meta.op === 'hears') {
    const seen = trainedThings(op.meta.focus, op.meta.glimpseId);
    op.meta = { ...op.meta, things: seen.things, glimpse: seen.glimpse };
  }
  return op;
}

const askEl = { card: $('ask'), form: $('ask-form'), q: $('ask-q'), log: $('ask-log'), note: $('ask-note'), words: $('ask-words'), bubble: $('say-bubble'), hint: $('ask-hint') };
/** What to do next, by the Pistachio button: after a sound it made nothing of, or an answer it guessed. */
const HINTS = {
  unknown: 'It did not understand that. <b>Say it again</b>, or pick a question from the list.',
  guess: 'It was not sure what you asked, and guessed. If the answer is right, give it a <b>Pistachio</b>: it learns what your words mean. If not, <b>say it again</b>.',
};
function hint(kind) {
  const el = askEl.hint; if (!el) return;
  clearTimeout(hint.timer);
  flow.hint = kind ? { kind, at: performance.now() } : null;
  el.hidden = !kind; el.innerHTML = kind ? `<span class="q">?</span>${HINTS[kind]}` : '';
  if (kind) hint.timer = setTimeout(() => hint(null), kind === 'guess' ? OPEN_MS : 7000);
}
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
  if (words[0] === 'what' && words[1] === 'colour' && focusKind) { const t = scene.find((x) => x.focus); return [t ? t.colour : WORLD_COLOUR(focusKind)]; }
  if (w === 'what objects are round') return [...new Set(kinds.filter((k) => ROUND.has(k)))].sort();
  if (w === 'what can you eat') return [...new Set(scene.filter((t) => t.material === 'fruit').map((t) => t.kind))].sort();
  if (words[0] === 'can' && words[1] === 'you' && words[2] === 'eat' && focusKind) return [Object.values(WORLD).find((x) => x && x.kind === focusKind)?.material === 'fruit' ? 'yes' : 'no'];
  if (words[0] === 'is' && words[1] === 'this' && words.length === 3 && focusKind) { // is this <colour>? is this round?
    if (words[2] === 'round') return [ROUND.has(focusKind) ? 'yes' : 'no'];
    if (trained.colours.includes(words[2])) { const t = scene.find((x) => x.focus); return t ? [t.colour === words[2] ? 'yes' : 'no'] : null; }
  }
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
  if (text) { flow.bubble = { text, who: who || '', at: performance.now() }; flow.bubbles = [...(flow.bubbles || []).slice(-19), flow.bubble]; } // (what the parrot showed, for the page's checks)
  clearTimeout(bubble.timer); if (text) bubble.timer = setTimeout(() => { b.hidden = true; }, (who || '').startsWith('it') ? 3200 : 1500);
}
/** The visitor's question as a subtitle at the foot of the room (the parrot's answer alone goes by the parrot). */
const sub = { el: $('subtitle'), words: [], at: 0, timer: 0, preset: false };
function subtitle(text, preset = false) {
  clearTimeout(sub.timer); sub.el.classList.remove('fading');
  sub.el.textContent = ''; sub.words = []; sub.at = 0; sub.el.hidden = !text; sub.preset = !!text && preset;
  for (const w of (text || '').split(/\s+/).filter(Boolean)) {
    const span = document.createElement('span'); span.textContent = w + ' '; sub.el.append(span);
    sub.words.push({ span, key: w.toLowerCase().replace(/[^a-z]/g, '').replace(/^color$/, 'colour') });
  }
}
function subtitleHeard(word) { // the word the brain hears this moment lights (a word said otherwise, as "it" for "this": the next word)
  let i = sub.words.findIndex((w, k) => k >= sub.at && w.key === word);
  if (i < 0 && sub.at < sub.words.length) i = sub.at;
  if (i < 0) return;
  for (let k = 0; k <= i; k++) sub.words[k].span.classList.add('on');
  sub.at = i + 1;
}
function subtitleAdd(word) { // your own words, each as its ear knows it
  clearTimeout(sub.timer); sub.el.classList.remove('fading'); sub.el.hidden = false; sub.preset = false;
  const span = document.createElement('span'); span.textContent = word + ' '; span.classList.add('on'); sub.el.append(span);
  sub.words.push({ span, key: word }); sub.at = sub.words.length;
}
function subtitleDone(ms = 1500) { clearTimeout(sub.timer); sub.timer = setTimeout(() => { sub.el.classList.add('fading'); sub.timer = setTimeout(() => { sub.el.hidden = true; sub.preset = false; sub.words = []; sub.at = 0; sub.el.textContent = ''; }, 300); }, ms); }
function placeBubble() {
  const b = askEl.bubble;
  if (!b || b.hidden || !parrot) return;
  const p = new THREE.Vector3(); parrot.bones.head.getWorldPosition(p); p.y += 0.07;
  p.project(camera);
  b.style.transform = `translate(${Math.round((p.x + 1) / 2 * canvas.clientWidth)}px, ${Math.round((1 - p.y) / 2 * canvas.clientHeight)}px) translate(-50%, -100%)`;
}
/** Say a word its voice chose: the sound its hearing memory links to the word (`sound`, the record the word
 *  recalls), in the parrot's voice, the beak moving with it; the concept lights and the path to the voice. */
function sayWord(word, sound) {
  brain3d?.scan?.say(word);
  const kept = sound ? soundPcm.get(sound.id) : null;
  trained.lastVoice = { word, id: sound?.id || null };
  if (kept?.pcm?.length && audio.ctx?.state === 'running') {
    const own = ownTake(sound.id);
    const spoken = own ? audio.speakOwn(own.pcm, own.rate) : audio.speakPcm(kept.pcm, kept.rate);
    if (spoken) {
      markChip(sound.id); ui.voiceNote.textContent = `${word}: the sound its memory links to the word${own ? ', in its own voice' : ''}`;
      trained.answerAt = performance.now();
      const live = brain3d?.live;
      if (live?.slots?.has(sound.slot)) live.packets.push({ path: [`slot:${sound.slot}`, 'vocal', 'voice'], t0: brain3d.clock.vt, dur: 1.4, colour: live.cSay, slot: sound.slot });
      trained.spoken = (trained.spoken || []).concat([{ word, id: sound.id, at: performance.now(), answer: true }]).slice(-40);
      return own ? 'its own voice: the sound it heard, as its voice makes it' : 'its sound for the word';
    }
  }
  console.log(`[voice] "${word}": no sound linked to the word, shown as text`);
  audio.mouth(word); // the beak opens and closes with the word though it has no sound
  return 'as text: it keeps no sound for this word';
}

// --- how it attends: to the visitor, or to the things round it ------------------------------------------------
// Listen to me: it looks at you, keeps every utterance it hears (a word or a whole phrase) and says it back.
// Curious: its attention moves over the things by its body's own focus (a new thing, a moved thing, a thing it
// has not looked at for a while; a click points it at one); it listens for a question about the thing in focus
// and answers it; at times it says a word it knows, most often the word linked to what it looks at.
// The ear's unit is the utterance. Its record's link is its meaning: a word, or a question its brain was taught
// (a sequence of its words, which the trained brain then hears one a moment). A sound with no meaning it knows is
// guessed (in Curious, with a thing in focus) and answered by the guess; a pistachio then links the sound to the
// meaning it was taken for, and the words it said to the sounds it said them with (parrotbrain.host).
const POINT_MS = 9000; // a thing you click holds its attention this long; then its own curiosity takes over
const flow = { mode: 'curious', live: null, hearing: false, asking: false, tiltUntil: 0, said: [], spotted: [], heard: [], linked: [], perf: [], answers: 0, busyFor: 0, liveTimer: 0 };
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const thingOfWord = (word) => [...room.things.values()].filter((t) => WORLD[t.kind]?.kind === word).sort((a, b) => distanceOf(a.id) - distanceOf(b.id))[0] || null;

function setFlow(mode) {
  if (mode !== 'listen' && mode !== 'curious') return;
  flow.mode = mode;
  for (const b of document.querySelectorAll('#flow-mode .seg')) b.setAttribute('aria-pressed', String(b.dataset.flow === mode));
  document.body.dataset.flow = mode;
  if (flow.live) dropLive(); // a question half heard is let go
  subtitle(null); bubble(null); hint(null);
  if (mode === 'listen') { state.pointed = null; trained.focus = null; brain3d?.scan?.clearConcept(); }
  askNote();
}
/** The exchange begun while a sound was being followed ends with nothing said (the sound was no question). */
function dropLive() {
  if (!flow.live) return;
  flow.live = null;
  trainedOp({ op: 'over' }).catch(() => {}).finally(() => { trained.busy = false; });
}
/** Its head: toward you in Listen to me (where the camera stands from its perch); and the tilt of not knowing. */
function attendHead(now) {
  const J = parrot.joints, lim = (name, v) => { const sp = J.spec[J.index[name]]; return clamp(v, sp.min, sp.max); };
  if (flow.mode === 'listen') {
    const d = camera.position.clone().sub(new THREE.Vector3(0, BAR_Y + 0.2, 0));
    J.target[J.index.head_yaw] = lim('head_yaw', Math.atan2(d.x, d.z) * 180 / Math.PI);
    J.target[J.index.head_pitch] = lim('head_pitch', 0.7 * Math.atan2(d.y, Math.hypot(d.x, d.z)) * 180 / Math.PI);
    if (now >= flow.tiltUntil) J.target[J.index.head_roll] = 0;
    if (now - (flow.lookAt || 0) > 1500) { // its body's own focus is drawn your way too (the direction of the camera from its head)
      const head = parrot.bones.head, hp = new THREE.Vector3(), hq = new THREE.Quaternion();
      head.getWorldPosition(hp); head.getWorldQuaternion(hq);
      const v = camera.position.clone().sub(hp).applyQuaternion(hq.invert());
      state.cue = { az: +(Math.atan2(v.x, v.z) * 180 / Math.PI).toFixed(1), el: +(Math.atan2(v.y, Math.hypot(v.x, v.z)) * 180 / Math.PI).toFixed(1), you: true };
      flow.lookAt = now;
    }
  }
  if (now < flow.tiltUntil) J.target[J.index.head_roll] = lim('head_roll', 17 * Math.sin(Math.PI * Math.min(1, (flow.tiltUntil - now) / 1500)));
}
/** The thing its trained brain holds: in Curious, the thing its body's own focus is on (while no question runs). */
function attendFocus() {
  if (flow.mode === 'listen') { state.focus = null; return; }
  if (trained.busy || flow.hearing || flow.asking) return; // a question keeps the thing it is about
  const id = state.focus?.id;
  if (id && id !== trained.focus && WORLD[room.things.get(id)?.kind]) { trained.focus = id; askNote(); }
}
/** The ear is in an utterance (or has left it). */
function hearingNow(on) {
  if (on === flow.hearing) return;
  flow.hearing = on; document.body.dataset.hearing = on ? '1' : '0';
  clearTimeout(flow.liveTimer);
  if (on) {
    if (!sub.preset && !trained.busy) subtitle(null);
    // the thing in focus stays in focus while you speak about it
    if (flow.mode === 'curious' && trained.focus && !trained.busy && room.things.has(trained.focus)) state.pointed = { id: trained.focus, until: performance.now() + 6000, why: state.pointed?.why || 'you are speaking', cued: performance.now() };
  } else if (flow.live) flow.liveTimer = setTimeout(() => { if (flow.live && !flow.hearing) dropLive(); }, 900); // a sound it followed that became no utterance (too long, or no voice)
}
function lightThing(word) { // the thing on the table a heard word stands for (its record's link)
  for (const [id, el] of tags) {
    const t = room.things.get(id);
    if (t && WORLD[t.kind]?.kind === word) { el.classList.add('heard'); clearTimeout(el.heardTimer); el.heardTimer = setTimeout(() => el.classList.remove('heard'), 2600); }
  }
}
/** A word known in the utterance as it is spoken (the hearing layer follows the sound along the records that keep
 *  their words' places): it lights as it is said, and in Curious the trained brain hears it that moment. */
function spottedWord(s) {
  const word = s.word, now = performance.now();
  flow.spotted.push({ word, index: s.index, frame: s.frame, at: now }); if (flow.spotted.length > 80) flow.spotted.shift();
  if (sub.preset) subtitleHeard(word); else subtitleAdd(word);
  brain3d?.scan?.heardWord?.(word);
  lightThing(word);
  if (flow.mode !== 'curious') return;
  if (!flow.live) {
    if (trained.busy) return; // it is answering: this sound is not followed
    trained.busy = true; trained.open = null; ui.pistachio.classList.remove('ask'); bubble(null);
    flow.live = { words: [], focus: trained.focus, at: now };
    trainedOp({ op: 'begin' }).catch(() => {});
  }
  flow.live.words.push(word);
  const named = thingOfWord(word);
  if (named && named.id !== flow.live.focus) { // the question names a thing: its focus goes there as the name is said, and its brain hears the words so far with that thing in focus
    flow.live.focus = named.id; trained.focus = named.id; askNote();
    state.cue = cueFor(named.id); state.pointed = { id: named.id, until: now + POINT_MS, why: 'it heard its name', cued: now };
    trainedOp({ op: 'hears', begin: true, words: [...flow.live.words], focus: named.id }).catch(() => {});
  } else trainedOp({ op: 'moment', hear: word, more: true, focus: flow.live.focus }).catch(() => {});
}
/** An utterance heard whole: in Listen to me the hearing layer says it back; in Curious it is answered. */
function heardUtterance(h) {
  flow.heard.push({ ...h, at: performance.now(), mode: flow.mode }); if (flow.heard.length > 60) flow.heard.shift();
  if (flow.mode === 'listen') { subtitleDone(1200); return; }
  answerHeard(h).catch((error) => { console.warn(`[ear] the answer stopped: ${error.message}`); trained.busy = false; flow.live = null; });
}
/** It can make nothing of the sound (or is not sure): its head tilts, and a question mark shows by it. */
function notKnown(h, why = 'unknown') {
  flow.tiltUntil = performance.now() + 1500; bubble('?', 'unsure');
  flow.unknown = { slot: h?.slot ?? null, why, at: performance.now() };
  if (flow.mode === 'curious') hint('unknown');
  console.log(`[ear] a sound it makes nothing of (${why})`);
}
/** A word it knows, said alone in Curious: a thing's word draws its attention to the thing (the sound stands for it). */
function heardWordAlone(word, h) {
  const t = thingOfWord(word), now = performance.now(); hint(null);
  if (t) { trained.focus = t.id; state.cue = cueFor(t.id); state.pointed = { id: t.id, until: now + POINT_MS, why: 'it heard its name', cued: now }; askNote(); }
  flow.lastWord = { word, slot: h.slot, thing: t ? t.id : null, at: now };
  console.log(`[ear] "${word}" heard alone${t ? ': its attention goes to the ' + t.kind : ''}`);
}
/** The exchange for a heard utterance: its meaning's words reach the trained brain (those it followed as they were
 *  spoken stand, the rest follow), it takes its turn, and says its answer with the sounds its words recall. */
async function answerHeard(h) {
  const live = flow.live; flow.live = null; clearTimeout(flow.liveTimer);
  if (!live && trained.busy) return; // it is answering another
  const meaning = h.word || h.guess || null, words = h.words || null, heardAt = performance.now();
  if (!words || words.length < 2) { // no question: a word it knows, or a sound it makes nothing of
    if (live) await trainedOp({ op: 'over' });
    trained.busy = false; trained.quietUntil = performance.now() + 500; subtitleDone(900);
    if (words && h.word) heardWordAlone(words[0], h); else notKnown(h, meaning ? (h.word ? 'no thing in focus' : 'a word it guessed') : 'unknown'); // (a word it only guessed moves nothing: it is not sure)
    return;
  }
  trained.busy = true; trained.open = null; ui.pistachio.classList.remove('ask');
  const id = ++trained.serial;
  try {
    // the thing the question is about: one it names, else the thing in focus as the question began
    const named = words.find((w) => Object.values(WORLD).some((x) => x && x.kind === w));
    const focusId = named ? thingOfWord(named)?.id || null : (live ? live.focus : trained.focus);
    const fk = focusId ? room.things.get(focusId)?.kind : null;
    const q = words.join(' ');
    if (!focusId || !WORLD[fk]) {
      if (live) await trainedOp({ op: 'over' });
      notKnown(h, named ? `no ${named} on the table` : 'no thing in focus');
      trained.last = { id, question: q, meaning, guessed: !h.word, focus: null, said: [], expected: null, right: null, slot: h.slot };
      subtitleDone(900);
      return;
    }
    if (focusId !== trained.focus) { trained.focus = focusId; askNote(); }
    state.cue = cueFor(focusId); state.pointed = { id: focusId, until: performance.now() + POINT_MS, why: named ? 'it heard its name' : 'you asked about it', cued: performance.now() };
    if (!h.word) { flow.tiltUntil = performance.now() + 1500; bubble('?', 'unsure'); } // a guess: not sure, it tries
    logLine(`<span class="who">you</span> ${esc(q)}?${h.word ? '' : ' <span class="guess">a guess</span>'} <span class="dim">(the ${esc(fk)} in focus)</span>`, 'q');
    brain3d?.scan?.question(q);
    // its brain hears the question's words: those it followed as they were spoken stand; the rest follow
    let fed = live ? live.words : [];
    const stands = !!live && live.focus === focusId && fed.length <= words.length && fed.every((w, i) => w === words[i]);
    if (!stands) fed = [];
    const rest = words.slice(fed.length);
    for (const w of rest) { if (sub.preset) subtitleHeard(w); else subtitleAdd(w); }
    for (const x of sub.words) x.span.classList.add('on');
    subtitleDone(1600);
    // the words it has not heard as they were said, and the first moment of its turn, in one step of its brain
    const first = trainedOp({ op: 'hears', begin: !stands, words: rest, turn: true, focus: focusId, heard: { slot: h.slot, meaning, guessed: !h.word } });
    const said = [];
    let li = null, firstAt = null;
    const say = (w, sound) => {
      if (!w || said[said.length - 1] === w) return;
      said.push(w); bubble(said.join(', ') + (h.word ? '' : ' ?'), h.word ? 'it' : 'it unsure'); firstAt ??= performance.now(); // (a guess: its answer with the ? beside it)
      const how = sayWord(w, sound); li ||= logLine('', 'a');
      li.innerHTML = `<span class="who">parrot</span> <b>${esc(said.join(', '))}</b> <span class="dim">(${esc(how)})</span>`;
    };
    for (let k = 0; k < trained.turn; k++) {
      const r = k === 0 ? await first : await trainedOp({ op: 'moment', hear: null, more: false, focus: focusId });
      if (!r.said && said.length) break;
      say(r.said, r.sound);
    }
    if (!said.length) logLine('<span class="who">parrot</span> <span class="dim">said nothing in its turn</span>', 'a');
    const want = expected(words, WORLD[fk].kind, trainedThings(focusId, null).things);
    const right = want ? want.length === said.length && want.every((w) => said.includes(w)) : null;
    if (want) logLine(right ? `<span class="ok">right</span> <span class="dim">· a pistachio pays it</span>` : `<span class="no">wrong</span> <span class="dim">· the answer: ${esc(want.join(', ') || 'none')}</span>`, right ? 'judge ok' : 'judge no');
    trained.last = { id, question: q, meaning, guessed: !h.word, chance: h.chance ?? null, focus: fk, said: [...said], expected: want, right, slot: h.slot, told_again: !!h.known,
      followed: live ? [...live.words] : [], stood: stands, ms: { heard_to_answer: firstAt === null ? null : Math.round(firstAt - heardAt) }, at: performance.now() };
    trained.open = said.length ? { id, said, at: performance.now() } : null;
    ui.pistachio.classList.toggle('ask', !!said.length);
    hint(h.word ? null : said.length ? 'guess' : 'unknown'); // understood: no hint; a guess: a pistachio if right, else say it again
    if (!said.length) await trainedOp({ op: 'over' });
  } finally {
    trained.busy = false; trained.quietUntil = performance.now() + 2000; flow.answers += 1;
  }
}
/** A sound the hearing layer said: a word by itself (Curious) or what it just heard, said back (Listen to me). */
function saidSound(said, own) {
  const word = said.word && !said.word.includes(' ') ? said.word : null, now = performance.now();
  flow.said.push({ id: said.id, slot: +said.id.slice(4), word: said.word || null, echo: !!said.echo, own, at: now }); if (flow.said.length > 80) flow.said.shift();
  trained.spoken = (trained.spoken || []).concat([{ word, id: said.id, at: now, echo: !!said.echo }]).slice(-40);
  if (word) { bubble(word, 'it'); brain3d?.scan?.say(word); }
}
/** A pistachio's links: the sound heard to the meaning it was taken for, a word said to the sound it was said with. */
function showLinked(l) {
  const row = { ...l, word: l.meaning, at: performance.now() };
  window.parrotPage.lastLinked = row; flow.linked.push(row); if (flow.linked.length > 40) flow.linked.shift();
  console.log(`[ear] record ${l.slot} linked to "${l.meaning}" (link ${l.link})${l.guessed ? ': a guess the pistachio paid' : ''}`);
  for (const a of l.answers || []) if (a.guessed) console.log(`[ear] record ${a.slot} linked to "${a.word}" (link ${a.link}): the sound it said for the word`);
  if (l.guessed) brain3d?.scan?.caption?.(`A pistachio: this sound stands for “${l.meaning.replace('<this>', 'the thing in focus')}”`);
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

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function payAnswer(open) {
  if (trained.open !== open) return;
  trained.open = null; ui.pistachio.classList.remove('ask');
  const r = await trainedOp({ op: 'pistachio' });
  logLine(`<span class="nut">a pistachio</span> for “${esc(open.said.join(', '))}” <span class="dim">· ${r.lessons} small lesson${r.lessons === 1 ? '' : 's'}, one a word it said, its own words the labels</span>`, 'p');
  if (r.linked) showLinked(r.linked); // the sound it heard is linked to the meaning it took it for, each word it said to the sound it said it with
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
// The questions as sound: voice/questions.json names each question's clip (a woman's voice, the question a natural
// sentence). The clip plays and reaches the parrot's ear as the microphone's sound does; what its ear makes of the
// sound is all its brain gets (nothing is typed).
const voiceLines = fetch('voice/questions.json').then((r) => (r.ok ? r.json() : {})).catch(() => ({}));
async function buildPresets() {
  const v = await voiceLines, sel = $('ask-preset');
  if (!sel || !v.presets?.length) return;
  sel.textContent = '';
  for (const p of v.presets) {
    const o = document.createElement('option'); o.textContent = p.text; o.dataset.key = p.key; o.dataset.clip = p.clip; o.dataset.meaning = v.questions?.[p.key]?.meaning || '';
    if (p.focus) o.dataset.focus = p.focus;
    sel.append(o);
  }
}
async function askPreset(opt) {
  if (!opt?.dataset.clip || !state.trained || trained.busy || flow.asking || flow.hearing) return false;
  flow.asking = true;
  try {
    await audio.unlock().catch(() => {});
    if (flow.mode !== 'curious') setFlow('curious');
    const about = opt.dataset.focus || [...room.things.values()].find((x) => (opt.dataset.meaning || '').split(' ').includes(WORLD[x.kind]?.kind))?.kind;
    if (about) { // a question about one thing (the thing set for it, or the thing it names): that thing in focus from its first word
      const t = [...room.things.values()].find((x) => x.kind === about);
      if (t) { trained.focus = t.id; state.cue = cueFor(t.id); state.pointed = { id: t.id, until: performance.now() + POINT_MS, cued: performance.now() }; askNote(); }
    }
    bubble(null); // a new question: the last answer's bubble goes at once
    subtitle(opt.textContent, true);
    // its own sound first ends (its ear does not take in what it hears over its own voice); two moments pass first,
    // so a word it began by itself just before the question was asked is known here
    const t0 = performance.now(), m0 = state.moment;
    while (state.moment < m0 + 2 && performance.now() - t0 < 1500) await sleep(30);
    while ((audio.ownVoice() || state.lastReply?.saying) && performance.now() - t0 < 5000) await sleep(50);
    const { ended, duration } = await audio.playClip(`voice/${opt.dataset.clip}`, { ear: true });
    flow.clip = { key: opt.dataset.key, text: opt.textContent, startedAt: performance.now(), duration, endedAt: null };
    await ended;
    flow.clip.endedAt = performance.now();
  } finally { flow.asking = false; }
  return true;
}
askEl.form?.addEventListener('submit', (e) => { e.preventDefault(); askPreset($('ask-preset')?.selectedOptions?.[0]); });
for (const b of document.querySelectorAll('#flow-mode .seg')) b.addEventListener('click', () => { audio.unlock().catch(() => {}); setFlow(b.dataset.flow); });
$('ask-nut')?.addEventListener('click', () => ui.pistachio.click());
$('ask-forget')?.addEventListener('click', async () => { // every sound it learned, its links and its paid calls: gone, and a fresh start
  try { for (const k of Object.keys(localStorage)) if (/^parrot\.(memory|words)/.test(k)) localStorage.removeItem(k); } catch (e) { /* storage blocked */ }
  try { if (state.brainReady) await brain.call('forget'); } catch (e) { /* the reload starts it clean anyway */ }
  location.reload();
});
$('ask-mic')?.addEventListener('click', (e) => { e.preventDefault(); toggleMic(); });

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
    // (while an utterance is being followed the moments come as fast as the brain takes them, at most twenty a second: each word lights nearer the moment it is said)
    if (now - state.lastMomentAt >= (state.trained && (flow.hearing || trained.queue.length) ? MOMENT_MS / 2 : MOMENT_MS) || !state.lastMomentAt) { state.lastMomentAt = now; moment(now); } // (and while an exchange's moments wait, so the answer comes sooner)
    if (!DEMO) view?.setJoints(parrot.joints.pos, parrot.joints.target);
    syncTags(); if (!DEMO) drawFields(); placeBubble();
  }
  if (state.trained) { // an exchange that hangs is let go, so the page never stays busy
    flow.busyFor = trained.busy ? flow.busyFor + dt : 0;
    if (flow.busyFor > 25) { console.warn('[ear] an exchange hung: let go'); trained.queue.length = 0; flow.live = null; trained.busy = false; flow.busyFor = 0; trained.queue.push({ meta: { op: 'over' }, resolve() {}, reject() {} }); }
    document.body.dataset.turn = trained.busy || audio.ownVoice(now) ? 'parrot' : 'you';
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
    hint(null);
    state.pistachios += 1; ui.pistachios.textContent = String(state.pistachios);
    brain3d?.reward();
    $('dopamine').hidden = false;
    $('dopamine-note').textContent = forAnswer ? ` It pays the trained brain\u2019s reply \u201c${forAnswer.said.join(', ')}\u201d: a lesson for each word it said (a word once), its own words the labels, taken where the brain would not have said the word by itself; the tracts a lesson changed glow.`
      : typeof state.lastReply?.vta === 'number' ? 'Its dopamine runs out from the VTA (the gold wash), and the tracts it strengthens glow.' : 'This brain has no dopamine signal: the view marks the pistachio arriving, and no synapse changes.';
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
  window.parrotPage = { room, state, eyes, audio, trained, flow, setFlow, askPreset, controls, soundPcm, ownTake,
    sound: (slot) => brain.call('sound', { slot }), world: (kind) => WORLD[kind] || null, expected: (words, kind, focusId) => expected(words, kind, trainedThings(focusId, null).things), ear: () => brain.call('debug', {}), get brainView() { return view; }, get brain3d() { return brain3d; }, get parrot() { return parrot; }, place, addThing, move: (id, x, z) => room.move(id, x, z), remove: (id) => room.remove(id),
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
      o.textContent = DEMO ? `trained: ${v.label}` : `trained: ${v.label}${v.good ? ` · ${v.good}` : ''}`; // the demo layout: the name alone (what it does well and lacks is the option's title)
      o.title = [v.good && `Does well: ${v.good}.`, v.lost && `Lacks: ${v.lost}.`].filter(Boolean).join(' ');
      after = o;
    }
  }).catch(() => {});
  let wanted = query.get('brain') || (() => { try { return localStorage.getItem('parrot.brain'); } catch (e) { return null; } })() || 'trained';
  // "no words yet": the same trained brain (it sees, and has its concepts) with an empty memory of sounds; you teach it
  // sounds in Listen to me and their meanings in Curious, by pistachio
  state.noWords = wanted === 'trained-nowords';
  if (state.noWords) wanted = 'trained';
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
    $('brain-kind').value = state.trained ? (state.noWords ? 'trained-nowords' : out.brain_kind || 'trained') : document.body.dataset.brain;
    if (state.trained) setupTrained(desc.trained);
    if (state.trained) { document.body.dataset.words = state.noWords ? 'none' : 'starting'; await buildPresets(); setFlow(query.get('flow') || (state.noWords ? 'listen' : 'curious')); }
    view.setup(desc, rig.joints);
    for (const r of desc.repertoire || []) addChip(r);
    // every start begins from the shipped words: the sounds, links and paid calls of a visit are not kept
    // past it (Forget my sounds clears them within one)
    try { for (const k of Object.keys(localStorage)) if (/^parrot\.(memory|words)/.test(k)) localStorage.removeItem(k); localStorage.setItem(START_KEY, String(Date.now())); } catch (e) { /* storage blocked */ }
    if (state.trained && !state.noWords) { // every start: its starting memory of sounds (voice/words.json), each sound linked to its meaning, taught by hearing
      try {
        const bundle = await (await fetch('voice/words.json')).json();
        if (bundle?.memory?.records?.length) {
          const out = await brain.call('remember', { saved: bundle.memory, view: state.tab === 'tab-memory' }); syncChips(out.repertoire || []); memview?.update(out.memory);
          if (bundle.parrot?.renderings) await loadOwnTakes(bundle.parrot.renderings);
          console.log(`[ear] starting memory: ${bundle.memory.records.length} sounds, linked to ${new Set(Object.values(bundle.links || {}).filter(Boolean)).size} meanings`);
        }
      } catch (e) { console.warn(`[ear] no starting memory of sounds: ${e.message}`); }
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
