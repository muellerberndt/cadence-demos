// Out of sight: the page. The scene steps in JavaScript (world.js, a port of the tracking
// chamber's world); every moment goes to the brain in the worker (Python in Pyodide, the Cadence
// wheel), and everything drawn of the brain is its reply: the place it gives the hand, the area
// that holds it, every neuron's activation, the settle sweep by sweep, the synapses a lesson
// changed and the records of the things. One moment is sent at a time: the scene's clock waits
// for the brain's answer, so the brain lives every moment of the scene in order.

import { Stage, DT, forward } from './world.js';
import { SceneView, MapView, ChartView, THING_COLOR } from './scene.js';
import { BrainView } from './brain.js';
import { LastSeen, Kalman } from './controls.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

const stage = new Stage({ seed: Number(params.get('seed') ?? 20261112) });
const sceneView = new SceneView($('scene'));
const mapView = new MapView($('map'));
const chartView = new ChartView($('chart'));
const brainView = new BrainView({ canvas: $('brain'), overlay: $('brain-overlay'), tooltip: $('tooltip'), renderer: params.get('renderer') || 'auto' });

const state = {
  ready: false, failed: null, paused: false,
  showHidden: true, compare: true, teach: true, selected: 'hand',
  record: null, previous: null, stepAt: 0, pending: false,
  belief: null, sheet: null, pins: {}, history: [],
  controls: null, unseen: 0, moments: 0, refused: 0, lessons: 0, lastLesson: -1e9,
  waveEvery: Number(params.get('wave') ?? 3),
  frameTimes: [], think: [], roundTrip: [], run: null, reaches: [], describe: null,
};

// -- the brain's worker

class BrainWorker {
  constructor() {
    this.worker = new Worker(new URL('./worker.js', import.meta.url), { type: 'module' });
    this.rid = 0; this.pending = new Map();
    this.worker.onmessage = ({ data }) => {
      if (data.status) { if (!state.ready) setRuntime(data.status, 'busy'); return; }
      const p = this.pending.get(data.rid);
      if (!p) return;
      this.pending.delete(data.rid);
      if (data.error) p.reject(new Error(data.error)); else p.resolve({ reply: data.result, arrays: data.arrays || {} });
    };
    this.worker.onerror = (event) => fail(event.message || 'The brain’s worker stopped.');
  }
  call(command, payload) {
    const rid = ++this.rid;
    return new Promise((resolve, reject) => { this.pending.set(rid, { resolve, reject }); this.worker.postMessage({ rid, command, payload }); });
  }
}
const brain = new BrainWorker();

function setRuntime(text, kind = 'busy', more = '') {
  $('runtime-text').textContent = text;
  $('runtime-dot').className = kind === 'ready' ? 'ready' : kind === 'error' ? 'error' : '';
  $('runtime-more').textContent = more;
}

function fail(message) {
  state.failed = message; state.ready = false;
  setRuntime(message, 'error');
  document.body.dataset.error = message;
}

// -- the controls beside the brain, given the same reports

function restartControls() {
  const start = stage.world.things[0];
  state.controls = { last: new LastSeen(start), kalman: new Kalman(start, { noise: stage.world.cameraNoise }) };
  state.unseen = 0;
}

// -- one moment

function tick(now) {
  if (!state.ready || state.pending || state.paused) return;
  if (now - state.stepAt < 1000 * DT - 3) return;
  const record = stage.advance();
  state.previous = state.record || record; state.record = record; state.stepAt = now;
  const report = record.report[0];
  const estimates = { last: state.controls.last.step(report), kalman: state.controls.kalman.step(report), kalmanSd: state.controls.kalman.sd };
  state.unseen = record.in_view[0] ? 0 : state.unseen + 1;
  record.cue.forEach((cue, k) => { if (cue) { sceneView.ring(record.truth[k], cue, stage.geometry); knockSound(cue); } });
  const message = {
    hand: { report }, joints: record.joints, commands: record.commands,
    things: stage.names.slice(1).map((name, i) => ({ name, report: record.report[i + 1], cue: record.cue[i + 1] })),
    teach: state.teach, wave: state.waveEvery > 0 && record.moment % state.waveEvery === 0 && !brainView.wave,
  };
  state.pending = true;
  const sent = performance.now();
  brain.call('step', message).then(({ reply, arrays }) => {
    state.pending = false;
    state.roundTrip.push(performance.now() - sent); if (state.roundTrip.length > 600) state.roundTrip.shift();
    answered(record, estimates, reply, arrays);
  }).catch((error) => { state.pending = false; fail(error.message); });
  if (stage.reach === null && state.run && !state.run.ended) finishRun();
}

function answered(record, estimates, reply, arrays) {
  const truth = record.truth[0], seen = record.in_view[0];
  const distance = (p) => Math.hypot(p[0] - truth[0], p[1] - truth[1]);
  state.moments = reply.moment;
  state.think.push(reply.ms); if (state.think.length > 600) state.think.shift();
  const row = { moment: record.moment, seen, brain: null, last: distance(estimates.last), kalman: distance(estimates.kalman), area: null, inside: null, lesson: false };
  state.estimates = estimates;
  if (reply.refused) {
    state.refused = reply.refusals;
  } else {
    state.belief = { place: reply.place, sd: reply.sd, area: reply.area };
    state.sheet = { px: arrays.px, py: arrays.py };
    row.brain = distance(reply.place);
    row.area = reply.area;
    // inside the stated area: the ellipse of the answer's spread at the stated rate
    const k2 = -2 * Math.log(1 - 0.9);
    row.inside = ((reply.place[0] - truth[0]) / Math.max(reply.sd[0], 1e-6)) ** 2 + ((reply.place[1] - truth[1]) / Math.max(reply.sd[1], 1e-6)) ** 2 <= k2;
    brainView.update(arrays.activation);
    if (reply.wave && arrays.wave_frames) brainView.playWave(arrays.wave_frames, reply.wave.frames, reply.wave.sweeps, reply.wave.of);
    if (arrays.weight) brainView.setWeights(arrays.weight);
    if (reply.lesson?.taught) {
      brainView.flash(arrays.flash_index, arrays.flash_delta, reply.lesson.changed);
      state.lastLesson = performance.now(); state.lastChanged = reply.lesson.changed; row.lesson = true;
    }
    state.lessons = reply.lessons; state.changedTotal = reply.changed_total;
    state.settle = { sweeps: reply.sweeps, residual: reply.residual, tolerance: reply.tolerance };
  }
  for (const t of reply.things || []) state.pins[t.name] = t.place ? t : null;
  brainView.setRecords(reply.things);
  state.history.push(row); if (state.history.length > 900) state.history.shift();
  if (state.run && !state.run.done) state.run.rows.push(row);
  readouts(record);
}

// -- readouts in the page

const cm = (v) => (v === null || v === undefined ? '–' : v < 0.1 ? `${(v * 100).toFixed(1)} cm` : `${Math.round(v * 100)} cm`);
function readouts(record) {
  const seen = record.in_view[0];
  const view = $('chip-view');
  view.textContent = seen ? 'hand: in view' : `hand: out of view ${(state.unseen * DT).toFixed(1)} s`;
  view.classList.toggle('out', !seen);
  const row = state.history.at(-1);
  $('chip-error').textContent = `error ${cm(row?.brain)}`;
  const area = state.belief?.area;
  $('chip-area').textContent = area === undefined || area === null ? 'area –' : area >= 1 ? `area ${area.toFixed(2)} m²` : `area ${Math.round(area * 1e4).toLocaleString()} cm²`;
  $('e-brain').textContent = cm(row?.brain); $('e-kalman').textContent = cm(row?.kalman); $('e-last').textContent = cm(row?.last);
  if (state.settle) {
    $('s-sweeps').textContent = `${state.settle.sweeps} sweeps`;
    $('s-residual').textContent = state.settle.residual.toExponential(1);
  }
  const think = state.think.slice(-60).sort((a, b) => a - b);
  $('s-ms').textContent = think.length ? `${think[think.length >> 1].toFixed(0)} ms` : '–';
  $('s-lessons').textContent = `${(state.lessons || 0).toLocaleString()}`;
  $('s-lessons').title = `${(state.changedTotal || 0).toLocaleString()} synapse changes in all`;
  $('s-refused').textContent = String(state.refused);
  // the things
  stage.names.slice(1).forEach((name, i) => {
    const k = i + 1, el = thingEls[name], pin = state.pins[name];
    const off = pin?.place ? Math.hypot(pin.place[0] - record.truth[k][0], pin.place[1] - record.truth[k][1]) : null;
    let text = 'never seen', stale = false;
    if (record.in_view[k]) text = 'in view';
    else if (pin?.place) {
      stale = off > 0.05;
      const held = `${((pin.unseen || 0) * DT).toFixed(0)} s`;
      text = pin.from === 'heard' ? `heard ${held} ago · pin ${cm(off)} off` : stale ? `out of view · pin ${cm(off)} off` : `out of view · held ${held}`;
    }
    el.state.textContent = text; el.state.classList.toggle('stale', stale);
  });
}

function learningBadge(now) {
  const el = $('learning'), seen = state.record?.in_view?.[0];
  const on = now - state.lastLesson < 350;
  el.classList.toggle('on', on);
  el.classList.toggle('blind', !on && state.record && !seen);
  el.textContent = !state.teach ? 'lessons off' : on ? `learning · ${(state.lastChanged || 0).toLocaleString()} synapses` : state.record && !seen ? 'no lesson: out of view' : 'no surprise';
  $('s-learn-box').classList.toggle('on', on);
}

// -- drawing

let lastFrame = performance.now();
function frame(now) {
  const interval = now - lastFrame; lastFrame = now;
  state.frameTimes.push(interval); if (state.frameTimes.length > 1200) state.frameTimes.shift();
  tick(now);
  const s = {
    geometry: stage.geometry, record: state.record, previous: state.previous,
    blend: clamp((now - state.stepAt) / (1000 * DT), 0, 1), joints: stage.world.joints, things: stage.world.things,
    names: stage.names, own: stage.own, cameraOn: stage.cameraOn, showHidden: state.showHidden, compare: state.compare,
    belief: state.belief, sheet: state.sheet, pins: state.pins, selected: document.activeElement === $('scene') || dragging ? state.selected : null,
    controls: state.estimates, rate: 0.9,
  };
  sceneView.draw(s, now);
  mapView.draw(s);
  chartView.draw(state.history, { compare: state.compare, dt: DT });
  brainView.frame(now, interval);
  learningBadge(now);
  requestAnimationFrame(frame);
}

// -- a recorded reach, and its summary (the page check reads it)

function playReach(index) {
  const scene = state.reaches[index];
  if (!scene) return Promise.resolve(null);
  stage.play(scene);
  setCase(scene.case, false);
  restartControls();
  $('play').textContent = 'Stop';
  return new Promise((resolve) => { state.run = { name: scene.name, kind: scene.kind, index, rows: [], ended: false, done: false, resolve, steps: scene.truth.length }; });
}

function mean(rows, key, pick) {
  const values = rows.filter(pick).map((r) => r[key]).filter((v) => v !== null && v !== undefined);
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
}

function finishRun() {
  const run = state.run;
  run.ended = true;
  $('play').textContent = 'Play';
  // the last moment's answer may be on its way: summarise once it is in
  const settle = () => {
    if (state.pending) { setTimeout(settle, 10); return; }
    run.done = true;
    const rows = run.rows, out = (r) => !r.seen, inn = (r) => r.seen, answered = rows.filter((r) => r.brain !== null);
    const summary = {
      name: run.name, kind: run.kind, moments: rows.length, out_of_view: rows.filter(out).length,
      no_answer: rows.length - answered.length,
      in_view: { brain: mean(rows, 'brain', inn), kalman: mean(rows, 'kalman', inn), last: mean(rows, 'last', inn) },
      unseen: { brain: mean(rows, 'brain', out), kalman: mean(rows, 'kalman', out), last: mean(rows, 'last', out) },
      inside_area: answered.length ? answered.filter((r) => r.inside).length / answered.length : null,
      inside_area_unseen: answered.filter(out).length ? answered.filter((r) => out(r) && r.inside).length / answered.filter(out).length : null,
      lessons_in_view: rows.filter((r) => r.seen && r.lesson).length, lessons_out_of_view: rows.filter((r) => !r.seen && r.lesson).length,
    };
    state.lastRun = summary;
    document.body.dataset.run = JSON.stringify(summary);
    run.resolve(summary);
  };
  settle();
}

// -- the page's controls

function setCase(kind, restart = true) {
  if (restart) { stage.setCase(kind); restartControls(); }
  document.querySelectorAll('[data-case]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.case === kind)));
  if (kind === 'own' && state.selected === 'hand') state.selected = 'cup';
  banner(kind === 'own' ? 'The arm moves its own hand: tap the table and it reaches there.' : '');
}

function banner(text, ms = 3200) {
  const el = $('banner');
  el.textContent = text; el.hidden = !text;
  clearTimeout(banner.timer);
  if (text) banner.timer = setTimeout(() => { el.hidden = true; }, ms);
}

function setToggle(id, on) { $(id).setAttribute('aria-pressed', String(on)); }
function setCamera(on) {
  stage.cameraOn = on; setToggle('camera', on);
  $('camera').textContent = on ? 'Camera on' : 'Camera off';
}

const thingEls = {};
function buildThings() {
  const root = $('things');
  stage.names.slice(1).forEach((name) => {
    const color = THING_COLOR[name] || [200, 200, 220];
    const el = document.createElement('div');
    el.className = 'thing'; el.style.setProperty('--c', `rgb(${color.join(',')})`);
    el.innerHTML = `<span class="who"><span class="name"><i></i>${name}</span><span class="state">–</span></span><button type="button" title="A sound from where the ${name} is: the ear hears its direction and distance">Knock</button>`;
    el.querySelector('button').addEventListener('click', () => knock(name));
    root.append(el);
    thingEls[name] = { el, state: el.querySelector('.state') };
  });
}

function knock(name) {
  audio();
  stage.knock(name);
}

// A knock, heard from the sound's direction: two short thumps, panned by the direction the ear
// hears and quieter with the distance.
let audioContext = null;
function audio() {
  if (audioContext || params.get('sound') === '0') return audioContext;
  try { audioContext = new (window.AudioContext || window.webkitAudioContext)(); } catch { audioContext = null; }
  return audioContext;
}
function knockSound(cue) {
  const ac = audioContext;
  if (!ac) return;
  const [direction, distance] = cue;
  // to the left of the camera's axis is to the listener's left
  const pan = clamp(-Math.sin(direction - stage.geometry.camera.heading) * 1.6, -1, 1);
  const gain = clamp(0.5 / (0.5 + distance), 0.15, 0.9);
  for (const delay of [0, 0.13]) {
    const t = ac.currentTime + delay;
    const osc = ac.createOscillator(), amp = ac.createGain(), panner = ac.createStereoPanner();
    osc.type = 'triangle'; osc.frequency.setValueAtTime(190, t); osc.frequency.exponentialRampToValueAtTime(70, t + 0.09);
    amp.gain.setValueAtTime(0.0001, t); amp.gain.exponentialRampToValueAtTime(gain, t + 0.004); amp.gain.exponentialRampToValueAtTime(0.0001, t + 0.12);
    panner.pan.value = pan;
    osc.connect(amp).connect(panner).connect(ac.destination);
    osc.start(t); osc.stop(t + 0.14);
  }
}

// -- dragging and keys

let dragging = null;
function planePoint(event) {
  const box = $('scene').getBoundingClientRect();
  return { x: event.clientX - box.left, y: event.clientY - box.top, p: sceneView.toPlane(event.clientX - box.left, event.clientY - box.top) };
}
function sceneState() {
  return { geometry: stage.geometry, record: state.record, things: stage.world.things, names: stage.names, own: stage.own };
}
function inPlane(p, margin = 0.02) {
  const [lx, hx, ly, hy] = stage.geometry.plane;
  return [clamp(p[0], lx + margin, hx - margin), clamp(p[1], ly + margin, hy - margin)];
}
// Joint angles that put the arm's end at a point (two links; the elbow on the side its limits allow).
function armTo(point) {
  const g = stage.geometry, [l1, l2] = g.arm.lengths, lim = g.arm.limits;
  if (g.arm.lengths.length !== 2) return null;
  const dx = point[0] - g.arm.base[0], dy = point[1] - g.arm.base[1];
  const d = clamp(Math.hypot(dx, dy), Math.abs(l1 - l2) + 0.02, l1 + l2 - 0.005);
  const q2 = -Math.acos(clamp((d * d - l1 * l1 - l2 * l2) / (2 * l1 * l2), -1, 1));
  const q1 = Math.atan2(dy, dx) - Math.atan2(l2 * Math.sin(q2), l1 + l2 * Math.cos(q2));
  return [clamp(q1, lim[0][0], lim[0][1]), clamp(q2, lim[1][0], lim[1][1])];
}
function reachTo(point) {
  const to = armTo(point);
  if (!to) return;
  const from = forward(stage.geometry, stage.world.joints).at(-1);
  const span = Math.hypot(point[0] - from[0], point[1] - from[1]);
  stage.stop();
  stage.moveArm(to, Math.round(clamp(span / 0.02, 12, 60)));
}
function moveSelected(name, p) {
  const k = stage.names.indexOf(name);
  if (name === 'screen') { stage.geometry.occluders[0].center = inPlane(p, stage.geometry.occluders[0].radius); return; }
  if (k < 0) return;
  if (k === 0 && stage.own) { reachTo(p); return; }
  if (stage.reach) { stage.stop(); if (state.run && !state.run.ended) finishRun(); }
  stage.targets[k] = inPlane(p);
}

function bindScene() {
  const canvas = $('scene');
  canvas.addEventListener('pointerdown', (event) => {
    const { x, y, p } = planePoint(event);
    const hit = sceneView.hit(x, y, sceneState());
    canvas.focus({ preventScroll: true });
    if (hit === 'camera') { setCamera(!stage.cameraOn); return; }
    if (!hit) { if (stage.own) reachTo(p); return; }
    state.selected = hit; dragging = hit;
    try { canvas.setPointerCapture(event.pointerId); } catch { /* a synthetic pointer has no capture */ }
    canvas.classList.add('dragging');
    moveSelected(hit, p);
    event.preventDefault();
  });
  canvas.addEventListener('pointermove', (event) => {
    if (!dragging) return;
    moveSelected(dragging, planePoint(event).p);
  });
  const end = () => {
    if (!dragging) return;
    const k = stage.names.indexOf(dragging);
    if (k >= 0) stage.targets[k] = null;
    dragging = null; canvas.classList.remove('dragging');
  };
  canvas.addEventListener('pointerup', end);
  canvas.addEventListener('pointercancel', end);
  canvas.addEventListener('keydown', (event) => {
    const order = ['hand', 'cup', 'wrench', 'box', 'screen'];
    const arrows = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1] };
    if (event.key >= '1' && event.key <= '5') { state.selected = order[Number(event.key) - 1]; }
    else if (arrows[event.key]) {
      const name = state.selected, k = stage.names.indexOf(name), stepSize = event.shiftKey ? 0.12 : 0.04;
      const from = name === 'screen' ? stage.geometry.occluders[0].center : stage.targets[k] || stage.world.things[k] || [0, 0];
      moveSelected(name, [from[0] + arrows[event.key][0] * stepSize, from[1] + arrows[event.key][1] * stepSize]);
    } else if (event.key === 'k' || event.key === 'K') { if (thingEls[state.selected]) knock(state.selected); }
    else if (event.key === 'c' || event.key === 'C') setCamera(!stage.cameraOn);
    else if (event.key === 'h' || event.key === 'H') { state.showHidden = !state.showHidden; setToggle('hidden', state.showHidden); }
    else if (event.key === ' ') $('play').click();
    else return;
    event.preventDefault();
  });
}

function bindControls() {
  document.querySelectorAll('[data-case]').forEach((b) => b.addEventListener('click', () => {
    if (state.run && !state.run.ended) { stage.stop(); finishRun(); }
    setCase(b.dataset.case);
  }));
  $('camera').addEventListener('click', () => setCamera(!stage.cameraOn));
  $('hidden').addEventListener('click', () => { state.showHidden = !state.showHidden; setToggle('hidden', state.showHidden); });
  $('compare').addEventListener('click', () => { state.compare = !state.compare; setToggle('compare', state.compare); document.body.classList.toggle('no-compare', !state.compare); });
  $('teach').addEventListener('change', (e) => { state.teach = e.target.checked; });
  $('play').addEventListener('click', () => {
    if (state.run && !state.run.ended) { stage.stop(); finishRun(); return; }
    playReach(Number($('reach').value));
  });
  $('reborn').addEventListener('click', async () => {
    if (!state.ready) return;
    state.ready = false; setRuntime('A new brain', 'busy');
    while (state.pending) await new Promise((r) => setTimeout(r, 10));
    try {
      const { reply, arrays } = await brain.call('reborn', {});
      adopt(reply, arrays);
      state.history = []; state.pins = {}; state.belief = null; state.sheet = null; state.lessons = 0; state.refused = 0;
      state.ready = true; ready();
    } catch (error) { fail(error.message); }
  });
}

// -- start

function adopt(describe, arrays) {
  state.describe = describe;
  brainView.setBrain(describe, arrays);
  const b = describe.brain;
  $('brain-size').textContent = `${describe.neurons.toLocaleString()} neurons · ${describe.synapses.toLocaleString()} synapses · every one drawn`;
  $('brain-badge').hidden = b.trained; $('brain-badge').textContent = b.label;
  $('brain-note').textContent = b.trained ? '' : `${b.label}. ${b.note}`;
  $('card-line').textContent = `Cadence ${describe.cadence} · ${b.label.toLowerCase()}`;
  $('card-wheel').textContent = `cadence-net==${describe.cadence}`;
  const facts = [['Brain', b.compose || b.label], ['Neurons', describe.neurons.toLocaleString()], ['Synapses', describe.synapses.toLocaleString()],
    ['Place answer', `${describe.place.bins} units an axis`], ['Records', `${describe.records.capacity} slots`], ['A moment', `${(DT * 1000).toFixed(0)} ms of the scene`]];
  $('card-facts').innerHTML = facts.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('');
}

function ready() {
  const d = state.describe;
  setRuntime('Ready', 'ready', `Cadence ${d.cadence} in Pyodide ${d.manifest?.pyodide || ''} · ${brainView.mode === 'webgl2' ? 'WebGL2' : 'Canvas2D'}`);
  $('play').disabled = false;
  document.body.dataset.ready = '1';
}

async function start() {
  buildThings(); bindScene(); bindControls(); restartControls();
  requestAnimationFrame(frame);
  try {
    const pack = new URL('pack/', location.href);
    const reaches = fetch(new URL('reaches.json', pack)).then((r) => (r.ok ? r.json() : { reaches: [] }));
    const g = stage.geometry;
    const { reply, arrays } = await brain.call('init', { pack: pack.href,
      config: { plane: g.plane, limits: g.arm.limits, ear: g.ear } });
    adopt(reply, arrays);
    state.reaches = (await reaches).reaches;
    $('reach').innerHTML = state.reaches.map((r, i) => `<option value="${i}">${r.name}</option>`).join('');
    state.ready = true; ready();
    const auto = params.get('autoplay');
    if (auto !== null) playReach(Number(auto));
  } catch (error) { fail(error.message); }
}

// what the page check drives
window.outOfSight = { stage, state, brainView, sceneView, playReach, knock, setCamera, setCase, moveSelected,
  frameStats() {
    const t = state.frameTimes.slice().sort((a, b) => a - b), q = (f) => (t.length ? t[Math.min(t.length - 1, Math.floor(f * t.length))] : null);
    return { frames: t.length, median_ms: q(0.5), p95_ms: q(0.95), worst_ms: t.at(-1) ?? null };
  } };

start();
