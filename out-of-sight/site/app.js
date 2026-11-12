// Out of sight: the page. The scene steps in JavaScript (world.js, a port of the tracking
// chamber's world); every moment goes to the brain's map in the worker (Python in Pyodide, the
// Cadence wheel). The map is the brain's own state: a thing enters it at the moment a sense first
// reports it, and every thing drawn on the scene as the brain holds it is read off the map at
// that moment. One moment is sent at a time: the scene's clock waits for the map's answer.
//
// The page is one screen: the scene and the brain. The visitor drags the hand, a thing or the
// pillar, drags the floor to turn the camera, taps a thing to ask the map where it is, taps the
// floor to ask what is there, and taps the body to switch the camera. A short tutorial walks
// through the promise; every part of the brain explains itself when pointed at (cards.js).

import { Stage, DT, forward, visible, readScene, around, wrap, cartesian, Random } from './world.js';
import { SceneView, ChartView } from './scene.js';
import { BrainView } from './brain.js';
import { LastSeen, Kalman } from './controls.js';
import { sheetArea } from './region.js';
import { partCard, tractCard, stageCard, stagesFor } from './cards.js';
import { whereSentence, whatSentence, the } from './where.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const distance = (p, q) => Math.hypot(p[0] - q[0], p[1] - q[1]);

// The page's sentence: the headline over the scene and the welcome's line. ONE constant;
// provisional until the owner confirms it.
const PROMISE = 'Hide the hand, and the brain knows where it is.';

const stage = new Stage({ seed: Number(params.get('seed') ?? 20261112) });
// the camera's noise on the arm's own hand where the page follows a person's: a stream of its own
const armNoise = new Random(5150);
const sceneView = new SceneView($('scene'));
const chartView = new ChartView($('chart'));
const brainView = new BrainView({ canvas: $('brain'), overlay: $('brain-overlay'), parts: $('parts'), renderer: params.get('renderer') || 'auto' });

const state = {
  ready: false, failed: null, kind: 'map', describe: null, regions: {},
  showHidden: true, more: false, selected: 'hand',
  record: null, previous: null, stepAt: 0, pending: false,
  inventory: [], drawn: [], things: {}, handPlace: null, emptied: null,
  history: [], controls: null, estimates: null, unseen: 0, moments: 0,
  waveEvery: Number(params.get('wave') ?? 3), settle: null,
  frameTimes: [], think: [], roundTrip: [], run: null, undo: [],
};

// The hand the page follows: a person's hand, or the arm's own (a kind of its own on the map).
const handName = () => (stage.own ? 'own' : 'hand');

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

function setRuntime(text, kind = 'busy') {
  $('runtime-text').textContent = text;
  $('runtime-dot').className = kind === 'ready' ? 'ready' : kind === 'error' ? 'error' : '';
}
function fail(message) {
  state.failed = message; state.ready = false;
  setRuntime(message, 'error');
  coach(message, 'quiet');
  document.body.dataset.error = message;
}

// -- the comparison beside the map, given the same camera reports (Details)

function restartControls(start = stage.world.things[0]) {
  state.controls = { last: new LastSeen(start), kalman: new Kalman(start, { q: 3.16e-7, r: 0.02 }) };
  state.unseen = 0;
}

// -- one moment

function tick(now) {
  if (!state.ready || state.pending) return;
  if (now - state.stepAt < 1000 * DT - 3) return;
  const record = stage.advance();
  state.previous = state.record || record; state.record = record; state.stepAt = now;
  const report = record.report[0];
  const estimates = { last: state.controls.last.step(report), kalman: state.controls.kalman.step(report), kalmanRadius: state.controls.kalman.radius };
  state.unseen = record.in_view[0] ? 0 : state.unseen + 1;
  const g = stage.geometry, names = stage.names.map((name, k) => (k === 0 ? handName() : name));
  // what the senses report at this moment: the camera, a sound, and the arm's own joint readings
  const seen = [], heard = [], felt = [];
  record.report.forEach((p, k) => { if (p) seen.push([names[k], p[0], p[1]]); });
  record.cue.forEach((cue, k) => { if (cue) { const p = cartesian(g, cue); heard.push([names[k], p[0], p[1]]); sceneView.ring(record.truth[k], cue, g); } });
  // the arm's own hand: the page works its place out from the joint readings (forward
  // kinematics, a program's step) and gives the map that place as what the body's sense names
  if (stage.own) { const tip = forward(g, record.joints).at(-1); felt.push([names[0], tip[0], tip[1]]); }
  else {
    // the arm's own hand stands in the room whichever hand the page follows: the camera reports
    // it where it sees it, as it reports every thing it sees
    const tip = record.chain.at(-1), seenArm = stage.cameraOn && visible(g, tip, record.joints, true, record.chain);
    const n = stage.world.cameraNoise, dx = armNoise.normal() * n, dy = armNoise.normal() * n;
    record.arm = { tip: tip.slice(), seen: seenArm };
    if (seenArm) seen.push(['own', tip[0] + dx, tip[1] + dy]);
  }
  const message = {
    seen, heard, felt,
    wave: state.waveEvery > 0 && record.moment % state.waveEvery === 0 && !brainView.wave,
    view: { on: stage.cameraOn, geometry: g, joints: stage.world.joints },
  };
  state.pending = true;
  const sent = performance.now();
  brain.call('step', message).then(({ reply, arrays }) => {
    state.pending = false;
    state.roundTrip.push(performance.now() - sent); if (state.roundTrip.length > 600) state.roundTrip.shift();
    answered(record, estimates, reply, arrays);
  }).catch((error) => { state.pending = false; fail(error.message); });
  if (stage.reach === null) finishRun();
}

// The cell of the map a point lies in, as the map numbers its cells (x first): -1 outside.
function cellOf(point) {
  const d = state.describe, [nx, ny] = d.cells, [x0, , y0] = d.plane, [sx, sy] = d.cell;
  const i = Math.floor((point[0] - x0) / sx), j = Math.floor((point[1] - y0) / sy);
  return i < 0 || j < 0 || i >= nx || j >= ny ? -1 : i * ny + j;
}

// An inventory entry with its area as region.js draws it: its cells' activity as shares of a
// sheet (row by row from the lowest y), every cell of the entry inside.
function withArea(e) {
  if (!e.cells.length) return { ...e, area: null };
  const d = state.describe, [nx, ny] = d.cells, share = new Float32Array(nx * ny);
  e.cells.forEach((c, k) => { const i = Math.floor(c / ny), j = c % ny; share[j * nx + i] = Math.max(1e-9, e.shares[k]); });
  return { ...e, area: sheetArea({ nx, ny, plane: d.plane, rate: 1 }, share) };
}

function answered(record, estimates, reply, arrays) {
  const truth = record.truth[0], seen = record.in_view[0];
  state.moments = reply.moment;
  state.think.push(reply.ms); if (state.think.length > 600) state.think.shift();
  state.estimates = estimates;
  state.inventory = reply.things;
  state.drawn = reply.things.map(withArea); // each with its area, as the scene draws it
  // a kind may be on the map twice (a thing left where it was, and one seen since): the page
  // names the one a sense wrote last
  const things = {};
  for (const e of state.inventory) if (!things[e.name] || (e.since ?? 1e9) < (things[e.name].since ?? 1e9)) things[e.name] = e;
  state.things = things;
  const hand = things[handName()] || null;
  if (hand?.place) state.handPlace = hand.place;
  const place = hand?.place || null;
  const row = { moment: record.moment, seen, unseen: seen ? 0 : state.unseen, brain: place ? distance(place, truth) : null,
    last: distance(estimates.last, truth), kalman: distance(estimates.kalman, truth), state: hand ? hand.state : null,
    inside: hand ? hand.cells.includes(cellOf(truth)) : false, cells: hand ? hand.cells.length : 0, pins: {} };
  stage.names.forEach((name, k) => {
    const e = things[k === 0 ? handName() : name];
    if (e) row.pins[k === 0 ? handName() : name] = { place: e.place, state: e.state, since: e.since, seen: record.in_view[k], off: e.place ? distance(e.place, record.truth[k]) : null };
  });
  brainView.update(arrays.activation);
  if (reply.wave && arrays.wave_frames) brainView.playWave(arrays.wave_frames, reply.wave.frames, reply.wave.sweeps, reply.wave.of, arrays.wave_move);
  state.settle = { ms: reply.settle_ms };
  state.history.push(row); if (state.history.length > 3000) state.history.shift();
  const run = state.run;
  if (run && !run.done && record.moment >= run.first && record.moment <= (run.last ?? Infinity)) {
    run.rows.push(row);
    if (run.ended && record.moment >= run.last) summarise(run);
  }
  tour.observe(record, row);
  readouts(record, row);
}

// A place as the body has it at this moment: its distance, and its bearing from the way it faces.
const aroundBody = (place) => around(stage.geometry, place);

// -- readouts

const cm = (v) => (v === null || v === undefined ? '–' : v < 0.1 ? `${(v * 100).toFixed(1)} cm` : `${Math.round(v * 100)} cm`);
const secs = (moments) => `${(moments * DT).toFixed(0)} s`;
function readouts(record, row) {
  const view = $('chip-view'), hand = state.things[handName()];
  view.hidden = record.in_view[0];
  if (!record.in_view[0]) view.textContent = stage.cameraOn ? `out of view ${(state.unseen * DT).toFixed(1)} s` : `camera off ${(state.unseen * DT).toFixed(1)} s`;
  $('readout').textContent = state.settle ? `this moment: the map settled in ${state.settle.ms.toFixed(1)} ms` : '';
  if (!state.more) return;
  $('e-brain').textContent = cm(row.brain); $('e-kalman').textContent = cm(row.kalman); $('e-last').textContent = cm(row.last);
  const median = (list) => { const t = list.slice(-120).sort((a, b) => a - b); return t.length ? t[t.length >> 1] : null; };
  const think = median(state.think), frame = median(state.frameTimes);
  $('s-ms').textContent = think === null ? '–' : `${think.toFixed(1)} ms`;
  $('s-frame').textContent = frame === null ? '–' : `${frame.toFixed(1)} ms`;
  $('s-cells').textContent = hand ? `${hand.cells.length}` : '–';
}

// -- a part's card, and the path of a position

const card = { el: $('card'), mode: null, id: null, stage: -1, pinned: false, html: '' };

function context() {
  const r = state.record;
  return {
    record: r, names: stage.names, unseen: state.unseen, dt: DT, own: stage.own, hand: state.things[handName()] || null, handName: handName(),
    things: state.things, inventory: state.inventory, describe: state.describe, regions: state.regions,
    act: (name) => brainView.activity(name), around: aroundBody, cameraOn: stage.cameraOn,
    why: r && !r.in_view[0] ? stage.why(0) : null, asked: state.asked,
  };
}

function renderCard() {
  if (!card.mode || !state.describe) return;
  const ctx = context();
  let html;
  if (card.mode === 'stage') html = stageCard(card.stage, ctx);
  else if (card.id.startsWith('tract:')) html = tractCard(card.id.slice(6), brainView.flow(card.id.slice(6)), ctx);
  else html = partCard(card.id, ctx, brainView.unitLine(card.id));
  if (html === card.html) return;
  card.html = html;
  card.el.querySelector('.content').innerHTML = html;
  placeCard();
}

// A card stands beside its part with a thin line to it, never over it. On a narrow screen it is
// a sheet at the bottom of the brain's pane, and the brain moves up above it.
const narrow = matchMedia('(max-width: 860px), (max-aspect-ratio: 1 / 1)');
function placeCard(force = false) {
  if (!card.mode) return;
  if (narrow.matches) {
    card.el.style.left = ''; card.el.style.top = '';
    document.body.classList.add('sheet');
    brainView.leader = null;
    brainView.setInset(card.el.offsetHeight + 8);
    return;
  }
  const w = card.el.offsetWidth, h = card.el.offsetHeight;
  const ids = card.mode === 'stage' ? [...brainView.spot] : [card.id];
  if (force || !card.place || card.place.key !== ids.join() || Math.abs(card.place.h - h) > 48) {
    card.place = { ...brainView.cardBeside(ids, w, h), key: ids.join(), h };
    card.el.style.left = `${card.place.left}px`; card.el.style.top = `${card.place.top}px`;
  }
  brainView.leader = { rect: { left: card.place.left, top: card.place.top, w, h }, id: ids[0] };
}
window.addEventListener('resize', () => placeCard(true));
new ResizeObserver(() => { if (card.mode && narrow.matches) placeCard(true); }).observe(card.el);

function showCard(mode, pinned) {
  card.mode = mode; card.pinned = pinned; card.html = ''; card.place = null;
  card.el.hidden = false;
  card.el.classList.toggle('pinned', pinned);
  const stages = stagesFor();
  card.el.classList.toggle('wide', mode === 'stage' && !!stages[card.stage].wide);
  card.el.innerHTML = '<div class="content"></div>' + (mode === 'stage'
    ? `<div class="nav"><button type="button" data-go="-1" aria-label="The stage before">‹</button><span>${card.stage + 1} / ${stages.length}</span><button type="button" data-go="1" aria-label="The next stage">›</button><button type="button" data-go="0" aria-label="Close">Close</button></div>` : '');
  card.el.dataset.mode = mode;
  spots();
  renderCard();
}
function openPart(id, pinned = false) {
  if (!id || !state.describe) return;
  card.id = id; card.stage = -1;
  showCard('part', pinned);
}
function openStage(index) {
  const stages = stagesFor();
  card.stage = (index + stages.length) % stages.length; card.id = null;
  showCard('stage', true);
  $('follow').setAttribute('aria-pressed', 'true');
}
function closeCard() {
  card.mode = null; card.id = null; card.pinned = false; card.el.hidden = true; card.place = null;
  brainView.leader = null; brainView.setInset(0);
  document.body.classList.remove('sheet');
  $('follow').setAttribute('aria-pressed', 'false');
  spots();
}
// what the brain view rings: the card's part, the stage's parts, or the tutorial's
function spots() {
  const ids = new Set();
  if (card.mode === 'part') ids.add(card.id);
  if (card.mode === 'stage') stagesFor()[card.stage].parts.forEach((p) => ids.add(p));
  if (!card.mode && tour.active && tour.current()?.brain) ids.add(tour.current().brain);
  brainView.spot = ids;
}

brainView.onPart = (id, type) => {
  if (card.mode === 'stage') {
    if (type !== 'tap') return;
    const k = id ? stagesFor().findIndex((s) => s.parts.includes(id)) : -1;
    if (k >= 0) openStage(k); else if (!id) closeCard();
    return;
  }
  if (type === 'enter') { if (!card.pinned) openPart(id, false); }
  else if (type === 'leave') { if (!card.pinned && card.id === id) closeCard(); }
  else if (!id || (card.pinned && card.id === id)) closeCard();
  else openPart(id, true);
};
card.el.addEventListener('click', (event) => {
  const go = event.target.closest('[data-go]');
  if (!go) return;
  if (go.dataset.go === '0') closeCard(); else openStage(card.stage + Number(go.dataset.go));
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && card.mode) { closeCard(); return; }
  if (card.mode === 'stage' && (event.key === 'ArrowRight' || event.key === 'ArrowLeft') && document.activeElement !== $('scene')) {
    openStage(card.stage + (event.key === 'ArrowRight' ? 1 : -1)); event.preventDefault();
  }
});
document.addEventListener('pointerdown', (event) => {
  if (card.mode === 'part' && card.pinned && !event.target.closest('#brain-stage')) closeCard();
});

// -- the two questions, asked of the map by settling: where is this thing, and what is there

function say(text, asked = null) {
  const el = $('said');
  el.textContent = text; el.classList.remove('old');
  state.said = asked ? { ...asked, at: performance.now() } : null;
  document.body.dataset.said = text;
  clearTimeout(say.timer);
  if (text) say.timer = setTimeout(() => { el.classList.add('old'); }, 9000);
}

function showQuestion(reply, arrays) {
  state.asked = { kind: reply.asked, name: reply.name, at: performance.now() };
  if (arrays.activation) brainView.update(arrays.activation);
  if (reply.wave && arrays.wave_frames) { brainView.wave = null; brainView.playWave(arrays.wave_frames, reply.wave.frames, reply.wave.sweeps, reply.wave.of, arrays.wave_move); }
}

/** Where is this thing? The map settles with the thing's kind as its cue. */
async function askWhere(name) {
  if (!state.ready) return null;
  const { reply, arrays } = await brain.call('ask', { thing: name });
  showQuestion(reply, arrays);
  const k = stage.names.indexOf(name === 'own' ? 'hand' : name), e = state.things[name];
  const places = reply.places || [];
  // of several places of the kind, the one the map's inventory names last written
  const place = places.length ? (e?.place ? places.slice().sort((a, b) => distance(a, e.place) - distance(b, e.place))[0] : places[0]) : null;
  const text = whereSentence(name, place ? aroundBody(place) : null, e, k >= 0 && !!state.record?.in_view?.[k], DT, places.length);
  say(text, place ? { place } : null);
  return text;
}

/** What is there? The map settles with the place as its cue. */
async function askWhat(point) {
  if (!state.ready) return null;
  const { reply, arrays } = await brain.call('what', { point });
  showQuestion(reply, arrays);
  const text = whatSentence(reply.name, aroundBody(point));
  say(text, { place: point });
  return text;
}

// -- the tutorial: four steps the visitor performs

const HOME_HINT = 'Drag the hand, a thing or the pillar. Drag the floor to turn the camera. Tap a thing to ask where the map holds it, or the floor to ask what is there. Point at a part of the brain and it explains itself.';
function coach(text, kind = '', step = -1, steps = 0) {
  $('coach-text').innerHTML = text;
  $('coach').className = `coach ${kind}`;
  $('coach-dots').innerHTML = steps ? Array.from({ length: steps }, (_, k) => `<i class="${k < step ? 'did' : k === step ? 'on' : ''}"></i>`).join('') : '';
  $('coach-skip').hidden = !steps;
}

// A point in the pillar's shadow, `depth` metres behind it as the camera looks.
function shadowPoint(depth) {
  const g = stage.geometry, o = g.occluders[0], eye = g.camera.position;
  if (!o) return stage.world.things[0];
  const d = distance(o.center, eye) || 1, ux = (o.center[0] - eye[0]) / d, uy = (o.center[1] - eye[1]) / d;
  const [lx, hx, ly, hy] = g.plane;
  for (const extra of [0, -0.08, 0.08, -0.16, 0.16, -0.24]) {
    const p = [o.center[0] + ux * (depth + extra), o.center[1] + uy * (depth + extra)];
    if (p[0] > lx + 0.06 && p[0] < hx - 0.06 && p[1] > ly + 0.06 && p[1] < hy - 0.06 && !visible(g, p, stage.world.joints)) return p;
  }
  return [o.center[0] + ux * depth, o.center[1] + uy * depth];
}

// The heading that puts a thing behind the body: 150 degrees off the way it faces, on the side
// that is the shorter turn.
function awayHeading(name) {
  const g = stage.geometry, p = stage.where(name), to = Math.atan2(p[1] - g.camera.position[1], p[0] - g.camera.position[0]);
  const options = [to - (150 * Math.PI) / 180, to + (150 * Math.PI) / 180];
  return options.sort((a, b) => Math.abs(wrap(a - g.camera.heading)) - Math.abs(wrap(b - g.camera.heading)))[0];
}

// A point the arm can reach that the camera does not see, well away from where its hand is.
function unseenReach() {
  const g = stage.geometry, tip = forward(g, stage.world.joints).at(-1), [lx, hx, ly, hy] = g.plane;
  let best = null, score = -Infinity;
  for (let a = 0.4; a <= 2.7; a += 0.1) {
    for (const r of [0.45, 0.55, 0.65]) {
      const p = [g.arm.base[0] + r * Math.cos(a), g.arm.base[1] + r * Math.sin(a)];
      if (p[0] < lx + 0.08 || p[0] > hx - 0.08 || p[1] < ly + 0.08 || p[1] > hy - 0.08 || visible(g, p, stage.world.joints)) continue;
      const s = Math.min(distance(p, tip), 0.4) - 0.1 * Math.abs(r - 0.55);
      if (s > score) { score = s; best = p; }
    }
  }
  return best;
}

// A lit point near a place: where the camera sees a thing put there.
function litNear(p) {
  const g = stage.geometry, [lx, hx, ly, hy] = g.plane;
  for (let r = 0; r <= 0.6; r += 0.05) {
    for (let a = 0; a < 2 * Math.PI; a += Math.PI / 8) {
      const q = [clamp(p[0] + r * Math.cos(a), lx + 0.08, hx - 0.08), clamp(p[1] + r * Math.sin(a), ly + 0.08, hy - 0.08)];
      if (visible(g, q, stage.world.joints) && distance(q, g.camera.position) > 0.2) return q;
    }
  }
  return p;
}

// A point of the floor where the map holds nothing and no thing stands.
function emptyFloor() {
  const g = stage.geometry, held = state.inventory.flatMap((e) => (e.place ? [e.place] : []));
  for (const p of [[0.6, 1.2], [-0.8, 0.0], [0.7, 0.0], [-0.8, 1.25], [0.2, 1.25]]) {
    if (held.every((q) => distance(p, q) > 0.25) && stage.world.things.every((q) => distance(p, q) > 0.2) && distance(p, g.camera.position) > 0.2) return p;
  }
  return [0.6, 1.2];
}

const TOUR = {
  promise: PROMISE,
  steps: [
    { id: 'hide', brain: 'map',
      text: '<b>Drag the hand behind the pillar</b>, into its shadow. The camera loses it. The map holds it where it can be: out of sight, near where it vanished.',
      aside: 'The ringed part is the map in the brain. The hand is a patch of its activity.',
      guide: () => ({ ring: stage.world.things[0], target: state.unseen ? null : shadowPoint(0.32) }),
      done: () => state.unseen >= 40 },
    { id: 'return', brain: 'map',
      text: '<b>Bring it back</b> into the light. The camera reports it, and the map writes it where it is seen.',
      aside: 'A cell the camera sees holds no thing it does not report.',
      guide: () => ({ ring: stage.world.things[0], target: state.unseen ? stage.home.things[0] : null }),
      done: (t) => t.seenRun >= 15 },
    { id: 'turn', brain: 'clock',
      text: '<b>Turn away from the apple</b>: drag the floor around the body. The apple stays on the map, behind you. The bread enters the map when the camera first sees it.',
      aside: 'Nothing is handed to the brain beforehand: a thing enters the map when a sense first reports it.',
      guide: () => ({ ring: stage.geometry.camera.position, radius: 0.09, turn: { from: stage.geometry.camera.heading, to: awayHeading('apple') } }),
      done: (t, row) => { t.behind = row.pins.apple && !row.pins.apple.seen && Math.abs(aroundBody(stage.where('apple')).bearing) >= 1.95 ? (t.behind || 0) + 1 : 0; return t.behind >= 12; },
      after: () => askWhere('apple') },
    { id: 'own', brain: 'map',
      enter: () => { setCase('own'); tour.target = unseenReach(); },
      text: '<b>The arm’s own hand.</b> Tap the ring on the floor: the arm reaches there, where the camera cannot see it. Its joint readings place the hand on the map at every moment.',
      aside: 'The place the arm’s joint readings name is the arm’s forward kinematics, which the program computes as a robot knows its own arm; the map takes it as a report of the body’s own sense.',
      guide: () => ({ ring: tour.target || stage.world.things[0], radius: 0.07, target: tour.target }),
      done: (t) => stage.own && state.unseen >= 30 && t.reached },
  ],
};

const tour = {
  active: false, step: 0, since: null, log: [], doneAt: 0, target: null,
  get steps() { return TOUR.steps; },
  current() { return this.active ? this.steps[this.step] : null; },
  start() {
    reset();
    closeCard();
    $('welcome').hidden = true;
    this.active = true; this.step = 0; this.log = [];
    this.enter();
  },
  enter() {
    const s = this.current();
    s.enter?.();
    this.since = { moved: 0, seenRun: 0, from: state.record?.moment ?? 0, tip: forward(stage.geometry, stage.world.joints).at(-1) };
    this.doneAt = 0;
    coach(`${s.text} <span class="aside">${s.aside}</span>`, '', this.step, this.steps.length);
    document.body.dataset.tour = s.id;
    spots();
  },
  observe(record, row) {
    if (!this.active || this.doneAt) return;
    const t = this.since, prev = state.previous;
    if (record.in_view[0]) { t.seenRun += 1; if (prev) t.moved += distance(record.truth[0], prev.truth[0]); } else t.seenRun = 0;
    if (stage.own && distance(record.truth[0], t.tip) > 0.15) t.reached = true;
    const s = this.current();
    if (!s.done(t, row)) return;
    this.log.push({ id: s.id, from: t.from, to: record.moment });
    this.doneAt = performance.now();
    s.after?.();
    coach(`${s.text} <span class="aside">${s.aside}</span>`, 'done', this.step + 1, this.steps.length);
    setTimeout(() => this.next(), params.get('tour') === 'fast' ? 150 : 1300);
  },
  next() {
    if (!this.active) return;
    if (this.step + 1 < this.steps.length) { this.step += 1; this.enter(); return; }
    this.finish('That is all of it. ' + HOME_HINT);
  },
  finish(text = HOME_HINT) {
    this.active = false;
    try { localStorage.setItem('out-of-sight-tour', '1'); } catch { /* a browser without storage */ }
    coach(text, 'quiet');
    document.body.dataset.tour = 'free';
    spots();
  },
};

// -- drawing

let lastFrame = performance.now();
function frame(now) {
  const interval = now - lastFrame; lastFrame = now;
  state.frameTimes.push(interval); if (state.frameTimes.length > 1800) state.frameTimes.shift();
  tick(now);
  const focused = document.activeElement === $('scene');
  sceneView.draw({
    geometry: stage.geometry, record: state.record, previous: state.previous,
    blend: clamp((now - state.stepAt) / (1000 * DT), 0, 1), joints: stage.world.joints, things: stage.world.things,
    names: stage.names, own: stage.own, handName: handName(), cameraOn: stage.cameraOn, showHidden: state.showHidden, compare: state.more,
    inventory: state.drawn || [], hand: state.drawn[state.inventory.indexOf(state.things[handName()])] || null, dt: DT,
    selected: focused && focusByKey ? state.selected : null, controls: state.estimates,
    guide: tour.active && !tour.doneAt && state.ready ? tour.current().guide() : null,
    asked: state.said && now - state.said.at < 2200 ? state.said : null,
  }, now);
  if (state.more) chartView.draw(state.history, { compare: true, dt: DT });
  brainView.frame(now, interval);
  if (card.mode) renderCard();
  requestAnimationFrame(frame);
}

// -- a scene file, and its summary (the page check reads it)

async function playScene(scene) {
  if (!scene) return null;
  stage.stop(); finishRun();
  while (state.pending) await new Promise((r) => setTimeout(r, 5));
  const { reply } = await brain.call('reset', {}); // a new scene: the map holds no thing
  state.emptied = reply.things;
  state.history = []; state.handPlace = null;
  stage.play(scene);
  setCase(scene.case === 'own' ? 'own' : 'other', false);
  restartControls(scene.start[0]);
  state.undo = []; $('undo').disabled = true;
  return new Promise((resolve) => { state.run = { name: scene.name, kind: scene.kind, rows: [], first: stage.moment + 1, ended: false, done: false, resolve, steps: scene.steps }; });
}

function mean(values) {
  const v = values.filter((x) => x !== null && x !== undefined);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}

// A run ends at the scene's last moment, or where the visitor stops it; it is summarised once
// that moment's answer is in.
function finishRun() {
  const run = state.run;
  if (!run || run.ended) return;
  run.ended = true;
  run.last = state.record ? state.record.moment : 0;
  if (!state.pending) summarise(run);
}

function summarise(run) {
  run.done = true;
  const rows = run.rows, hidden = rows.filter((r) => !r.seen);
  const summary = {
    name: run.name, kind: run.kind, moments: rows.length, out_of_view: hidden.length,
    in_view_m: mean(rows.filter((r) => r.seen).map((r) => r.brain)), hidden_m: mean(hidden.map((r) => r.brain)),
    last_seen_hidden_m: mean(hidden.map((r) => r.last)), cells_hold: hidden.length ? hidden.filter((r) => r.inside).length / hidden.length : null,
    think_ms: (() => { const t = state.think.slice(-rows.length).sort((a, b) => a - b); return t.length ? t[t.length >> 1] : null; })(),
    rows: rows.map((r) => ({ m: r.moment, seen: r.seen, brain: r.brain, last: r.last, kalman: r.kalman, inside: r.inside, cells: r.cells, state: r.state })),
  };
  const { rows: _, ...brief } = summary;
  state.lastRun = brief;
  document.body.dataset.run = JSON.stringify(brief);
  run.resolve(summary);
  coach(`${run.name || 'The scene'}: ${rows.length} moments, ${hidden.length} with the hand out of view. Out of view the map held it ${cm(summary.hidden_m)} from the hand on average; last seen, ${cm(summary.last_seen_hidden_m)}.`, 'quiet');
}

async function loadFile(file) {
  try {
    const scene = readScene(JSON.parse(await file.text()));
    if (!scene.name) scene.name = file.name;
    coach(`Playing ${scene.name}: ${scene.steps} moments.`, 'quiet');
    return await playScene(scene);
  } catch (error) {
    coach(`That file did not load. ${error.message}`, 'quiet');
    return null;
  }
}

// -- undo, reset and the page's switches

function pushUndo(entry) {
  state.undo.push(entry); if (state.undo.length > 40) state.undo.shift();
  $('undo').disabled = false;
}
function undo() {
  const entry = state.undo.pop();
  $('undo').disabled = !state.undo.length;
  if (!entry) return;
  if (entry.name === 'camera') setCamera(entry.from, false); else stage.place(entry.name, entry.from);
}
function reset() {
  stage.stop(); finishRun();
  stage.reset();
  setCase('other', false); setCamera(true, false);
  restartControls();
  state.undo = []; $('undo').disabled = true;
  state.handPlace = null;
  say('');
  // a new scene: the map is emptied and holds no thing until a sense reports one
  if (state.ready) brain.call('reset', {}).then(({ reply }) => { state.emptied = reply.things; }).catch((error) => fail(error.message));
}
function setCase(kind, restart = true) {
  const own = kind === 'own';
  if (restart && own !== stage.own) {
    stage.stop(); finishRun();
    if (!own) stage.world.things[0] = stage.home.things[0].slice(); // a person's hand, back where it rests
    stage.setCase(kind); restartControls();
  }
  document.querySelectorAll('[data-case]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.case === kind)));
  if (own && state.selected === 'hand') state.selected = 'apple';
}
function setCamera(on, undoable = true) {
  if (undoable && on !== stage.cameraOn) pushUndo({ name: 'camera', from: stage.cameraOn });
  stage.cameraOn = on;
}
function setMore(on) {
  state.more = on;
  document.body.classList.toggle('more', on);
  $('details').setAttribute('aria-pressed', String(on));
  $('details-panel').hidden = !on;
  if (on) requestAnimationFrame(() => $('details-panel').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'nearest' }));
}

// -- direct manipulation: drag to move, tap to ask or to switch the camera

let press = null, focusByKey = false;
function planePoint(event) {
  const box = $('scene').getBoundingClientRect();
  return { x: event.clientX - box.left, y: event.clientY - box.top, p: sceneView.toPlane(event.clientX - box.left, event.clientY - box.top) };
}
const sceneState = () => ({ geometry: stage.geometry, record: state.record, things: stage.world.things, names: stage.names, own: stage.own });
function inPlane(p, margin = 0.02) {
  const [lx, hx, ly, hy] = stage.geometry.plane;
  return [clamp(p[0], lx + margin, hx - margin), clamp(p[1], ly + margin, hy - margin)];
}
// Joint angles that put the arm's end at a point (two links; the elbow on the side its limits allow).
function armTo(point) {
  const g = stage.geometry, lim = g.arm.limits;
  if (g.arm.lengths.length !== 2) return null;
  const [l1, l2] = g.arm.lengths;
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
  stage.stop();
  stage.moveArm(to, Math.round(clamp(distance(point, from) / 0.012, 20, 80)));
}
function moveSelected(name, p) {
  if (name === 'pillar') { const o = stage.geometry.occluders[0]; if (o) o.center = inPlane(p, o.radius); return; }
  const k = stage.names.indexOf(name);
  if (k < 0) return;
  if (k === 0 && stage.own) { reachTo(p); return; }
  if (stage.reach) { stage.stop(); finishRun(); }
  stage.targets[k] = inPlane(p);
}
function tap(name, p) {
  if (name === 'camera') setCamera(!stage.cameraOn);
  else if (name === 'floor') { if (stage.own) reachTo(p); else askWhat(p); }
  else if (name !== 'pillar') askWhere(name === 'hand' ? handName() : name);
}

// The angle, in the room, of a point of the canvas as seen from the body.
function angleFromBody(x, y) {
  const eye = sceneView.toScreen(stage.geometry.camera.position);
  return { angle: Math.atan2(-(y - eye[1]), x - eye[0]), far: Math.hypot(x - eye[0], y - eye[1]) };
}
function turnBy(delta) {
  pushUndo({ name: 'heading', from: stage.where('heading') });
  stage.turnTo((stage.facing ?? stage.geometry.camera.heading) + delta);
}

function bindScene() {
  const canvas = $('scene');
  const fingers = new Map(); // the pointers on the scene: id -> [x, y]
  let twist = null;          // two fingers turning the camera: { angle, target }
  const release = () => {
    if (!press) return;
    const k = stage.names.indexOf(press.name);
    if (k >= 0) stage.targets[k] = null;
    press = null; canvas.classList.remove('dragging');
  };
  canvas.addEventListener('pointerdown', (event) => {
    const { x, y, p } = planePoint(event);
    fingers.set(event.pointerId, [x, y]);
    focusByKey = false; canvas.classList.remove('keys');
    canvas.focus({ preventScroll: true });
    try { canvas.setPointerCapture(event.pointerId); } catch { /* a synthetic pointer has no capture */ }
    event.preventDefault();
    if (fingers.size === 2) {
      release();
      const [a, b] = [...fingers.values()];
      twist = { angle: Math.atan2(-(b[1] - a[1]), b[0] - a[0]), target: stage.geometry.camera.heading };
      pushUndo({ name: 'heading', from: stage.where('heading') });
      return;
    }
    const hit = sceneView.hit(x, y, sceneState()) || 'floor';
    press = { name: hit, x, y, p, at: performance.now(), moved: false };
    if (hit !== 'camera' && hit !== 'floor') state.selected = hit;
  });
  canvas.addEventListener('pointermove', (event) => {
    const { x, y, p } = planePoint(event);
    if (fingers.has(event.pointerId)) fingers.set(event.pointerId, [x, y]);
    if (twist && fingers.size === 2) {
      const [a, b] = [...fingers.values()], angle = Math.atan2(-(b[1] - a[1]), b[0] - a[0]);
      twist.target += wrap(angle - twist.angle); twist.angle = angle;
      stage.turnTo(twist.target);
      return;
    }
    if (!press) {
      const hit = sceneView.hit(x, y, sceneState());
      canvas.classList.toggle('grab', !!hit && hit !== 'camera');
      canvas.classList.toggle('tap', hit === 'camera');
      return;
    }
    const turning = press.name === 'floor' || press.name === 'camera';
    if (!press.moved && Math.hypot(x - press.x, y - press.y) > 6) {
      press.moved = true;
      canvas.classList.add('dragging');
      if (turning) {
        if (stage.reach) { stage.stop(); finishRun(); }
        pushUndo({ name: 'heading', from: stage.where('heading') });
        press.angle = angleFromBody(press.x, press.y).angle; press.target = stage.geometry.camera.heading;
      } else pushUndo({ name: press.name, from: stage.where(press.name) });
    }
    if (!press.moved) return;
    if (press.name === 'camera') {
      const { angle, far } = angleFromBody(x, y);
      if (far > 24) stage.turnTo(angle);
    } else if (press.name === 'floor') {
      const { angle, far } = angleFromBody(x, y);
      if (far > 14) { press.target += wrap(angle - press.angle); stage.turnTo(press.target); }
      press.angle = angle;
    } else moveSelected(press.name, p);
  });
  const end = (event) => {
    fingers.delete(event.pointerId);
    if (fingers.size < 2) twist = null;
    if (!press) return;
    const tapped = event.type === 'pointerup' && !press.moved && performance.now() - press.at < 450;
    const { name, p } = press;
    release();
    if (tapped) tap(name, p);
  };
  canvas.addEventListener('pointerup', end);
  canvas.addEventListener('pointercancel', end);
  canvas.addEventListener('keyup', (event) => { if (event.key === 'Tab') { focusByKey = true; canvas.classList.add('keys'); } });
  canvas.addEventListener('keydown', (event) => {
    const order = [...stage.names, 'pillar'];
    const arrows = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1] };
    const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
    focusByKey = true; canvas.classList.add('keys');
    if (key >= '1' && key <= String(order.length)) state.selected = order[Number(key) - 1];
    else if (arrows[key]) {
      const name = state.selected, k = stage.names.indexOf(name), stride = event.shiftKey ? 0.12 : 0.04;
      const from = name === 'pillar' ? stage.geometry.occluders[0]?.center : stage.targets[k] || stage.world.things[k];
      if (!from) return;
      pushUndo({ name, from: stage.where(name) });
      moveSelected(name, [from[0] + arrows[key][0] * stride, from[1] + arrows[key][1] * stride]);
    } else if (key === 'w' || key === 'Enter') { if (state.selected !== 'pillar') askWhere(state.selected === 'hand' ? handName() : state.selected); }
    else if (key === 'q' || key === 'e') turnBy(((key === 'q' ? 1 : -1) * Math.PI) / 12);
    else if (key === 'c') setCamera(!stage.cameraOn);
    else if (key === 'h') state.showHidden = !state.showHidden;
    else if (key === 'z') undo();
    else if (key === 'r') reset();
    else return;
    event.preventDefault();
  });
}

function bindControls() {
  $('tour').addEventListener('click', () => tour.start());
  $('undo').addEventListener('click', undo);
  $('reset').addEventListener('click', reset);
  $('details').addEventListener('click', () => setMore(!state.more));
  $('welcome-go').addEventListener('click', () => tour.start());
  $('welcome-skip').addEventListener('click', () => { $('welcome').hidden = true; tour.finish(); });
  $('coach-skip').addEventListener('click', () => tour.finish());
  $('follow').addEventListener('click', () => (card.mode === 'stage' ? closeCard() : openStage(0)));
  document.querySelectorAll('[data-case]').forEach((b) => b.addEventListener('click', () => setCase(b.dataset.case)));
  $('load').addEventListener('click', () => $('file').click());
  $('file').addEventListener('change', (e) => { if (e.target.files[0]) loadFile(e.target.files[0]); e.target.value = ''; });
  window.addEventListener('dragover', (e) => e.preventDefault());
  window.addEventListener('drop', (e) => { e.preventDefault(); const file = e.dataTransfer?.files?.[0]; if (file) loadFile(file); });
}

// -- start

function adopt(describe, arrays) {
  state.describe = describe;
  state.kind = describe.brain.kind;
  state.regions = Object.fromEntries(describe.regions.map((r) => [r.name, r]));
  closeCard();
  brainView.setBrain(describe, arrays);
  document.querySelectorAll('[data-promise]').forEach((el) => { el.textContent = TOUR.promise; });
  if (describe.manifest) state.manifest = describe.manifest;
  const m = state.manifest?.map || {};
  $('brain-badge').hidden = !params.has('badge');
  $('brain-note').textContent = m.note || '';
  $('card-wheel').textContent = `cadence-net ${describe.cadence} (${state.manifest?.wheel_source || 'the pack’s wheel'})`;
  const [nx, ny] = describe.cells, s = describe.settings || {};
  const facts = [['The map', `${nx} by ${ny} cells of ${Math.round(describe.cell[0] * 100)} cm, ${describe.units} code units a cell`],
    ['Neurons', describe.neurons.toLocaleString('en')], ['Synapses', `${describe.synapses.toLocaleString('en')}, every one drawn, none taught`],
    ['A place seen empty', s.empty === 'near' ? `out of sight, within ${Math.round(2 * s.reach * 100)} cm of where it was` : String(s.empty)],
    ['A moment', `${(DT * 1000).toFixed(0)} ms of the scene`],
    ['Runs in', `Pyodide ${state.manifest?.pyodide || ''}, ${brainView.mode === 'webgl2' ? 'WebGL2' : 'Canvas2D'}`]];
  $('card-facts').innerHTML = facts.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('');
}

async function start() {
  bindScene(); bindControls(); restartControls();
  if (params.get('details') === '1') setMore(true);
  requestAnimationFrame(frame);
  try {
    const pack = new URL('pack/', location.href);
    const { reply, arrays } = await brain.call('init', { pack: pack.href });
    adopt(reply, arrays);
    restartControls();
    state.ready = true;
    setRuntime('Ready', 'ready');
    document.body.dataset.ready = '1';
    const wanted = params.get('tour');
    let seen = false;
    try { seen = localStorage.getItem('out-of-sight-tour') === '1'; } catch { /* a browser without storage */ }
    if (wanted === '0' || (seen && wanted === null)) tour.finish();
    else if (wanted === '1' || wanted === 'fast') tour.start();
    else { coach('', 'quiet'); $('welcome').hidden = false; $('welcome-go').focus({ preventScroll: true }); }
  } catch (error) { fail(error.message); }
}

// what the page check drives
window.outOfSight = { stage, state, brainView, sceneView, tour, card, askWhere, askWhat, awayHeading, shadowPoint, litNear, emptyFloor, setCase, reset, undo,
  setMore, openPart, openStage, closeCard, aroundBody, stageCount: () => stagesFor().length,
  loadScene: (data) => playScene(readScene(data)),
  inventory: async () => (await brain.call('things', {})).reply.things,
  /** Where a thing, the pillar or the camera is on the screen, in client pixels. */
  screenOf(name) {
    const box = $('scene').getBoundingClientRect();
    const p = name === 'camera' ? stage.geometry.camera.position : stage.where(name);
    const q = sceneView.toScreen(p);
    return [box.left + q[0], box.top + q[1]];
  },
  screenAt(p) { const box = $('scene').getBoundingClientRect(), q = sceneView.toScreen(p); return [box.left + q[0], box.top + q[1]]; },
  /** Whether the camera sees a point of the plane as the scene stands. */
  visibleAt: (p) => stage.cameraOn && visible(stage.geometry, p, stage.world.joints),
  frameStats(last = 600) {
    const t = state.frameTimes.slice(-last).sort((a, b) => a - b), q = (f) => (t.length ? t[Math.min(t.length - 1, Math.floor(f * t.length))] : null);
    return { frames: t.length, median_ms: q(0.5), p95_ms: q(0.95), worst_ms: t.at(-1) ?? null };
  } };

start();
