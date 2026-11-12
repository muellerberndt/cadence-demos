// Out of sight: the page. The scene steps in JavaScript (world.js, a port of the tracking
// chamber's world); every moment goes to the brain in the worker (Python in Pyodide, the Cadence
// wheel), and everything drawn of the brain is its reply: the place it gives the hand, the area
// that holds it, every neuron's activation, the settle sweep by sweep, the synapses a lesson
// changed and the records of the things. One moment is sent at a time: the scene's clock waits
// for the brain's answer, so the brain lives every moment of the scene in order.
//
// The page is one screen: the scene and the brain. The visitor drags the hand, a thing or the
// pillar, taps a thing to knock on it and taps the camera to switch it. A short tutorial walks
// through the promise; every part of the brain explains itself when pointed at (cards.js).

import { Stage, DT, forward, visible, readScene } from './world.js';
import { SceneView, MapView, ChartView } from './scene.js';
import { BrainView } from './brain.js';
import { LastSeen, Kalman } from './controls.js';
import { partCard, tractCard, stageCard, stagesFor, uncertainty } from './cards.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const distance = (p, q) => Math.hypot(p[0] - q[0], p[1] - q[1]);

const stage = new Stage({ seed: Number(params.get('seed') ?? 20261112) });
const sceneView = new SceneView($('scene'));
const mapView = new MapView($('map'));
const chartView = new ChartView($('chart'));
const brainView = new BrainView({ canvas: $('brain'), overlay: $('brain-overlay'), parts: $('parts'), renderer: params.get('renderer') || 'auto' });

const state = {
  ready: false, failed: null, kind: 'baseline',
  showHidden: true, more: false, teach: true, selected: 'hand',
  record: null, previous: null, stepAt: 0, pending: false,
  belief: null, seenBelief: null, sheet: null, pins: {}, history: [],
  controls: null, estimates: null, unseen: 0, moments: 0, refused: 0, lessons: 0, lesson: null, settle: null,
  waveEvery: Number(params.get('wave') ?? 3),
  frameTimes: [], think: [], roundTrip: [], run: null, reaches: [], describe: null, regions: {}, undo: [],
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

// -- the controls beside the brain, given the same reports

function restartControls(start = stage.world.things[0]) {
  state.controls = { last: new LastSeen(start), kalman: new Kalman(start, state.describe?.controls?.kalman || {}) };
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
  if (stage.reach === null) finishRun();
}

function answered(record, estimates, reply, arrays) {
  const truth = record.truth[0], seen = record.in_view[0];
  state.moments = reply.moment;
  state.think.push(reply.ms); if (state.think.length > 600) state.think.shift();
  const row = { moment: record.moment, seen, unseen: seen ? 0 : state.unseen, brain: null, last: distance(estimates.last, truth), kalman: distance(estimates.kalman, truth),
    area: null, uncertainty: null, inside: null, lesson: false, place: null, pins: {} };
  state.estimates = estimates;
  if (reply.refused) {
    state.refused = reply.refusals;
  } else {
    state.belief = { place: reply.place, sd: reply.sd, area: reply.area };
    if (seen) state.seenBelief = state.belief;
    state.sheet = { px: arrays.px, py: arrays.py };
    row.brain = distance(reply.place, truth); row.place = reply.place;
    row.area = reply.area; row.uncertainty = uncertainty(state.belief);
    // inside the stated area: the ellipse of the answer's spread at the stated rate
    const k2 = -2 * Math.log(1 - 0.9);
    row.inside = ((reply.place[0] - truth[0]) / Math.max(reply.sd[0], 1e-6)) ** 2 + ((reply.place[1] - truth[1]) / Math.max(reply.sd[1], 1e-6)) ** 2 <= k2;
    brainView.update(arrays.activation);
    if (reply.wave && arrays.wave_frames) brainView.playWave(arrays.wave_frames, reply.wave.frames, reply.wave.sweeps, reply.wave.of, arrays.wave_move);
    if (arrays.weight) brainView.setWeights(arrays.weight);
    if (reply.lesson?.taught) {
      brainView.flash(arrays.flash_index, arrays.flash_delta, reply.lesson.changed);
      state.lesson = { at: performance.now(), changed: reply.lesson.changed, mismatch: reply.lesson.mismatch };
      row.lesson = true;
    }
    state.lessons = reply.lessons; state.changedTotal = reply.changed_total;
    state.settle = { sweeps: reply.sweeps, residual: reply.residual, tolerance: reply.tolerance };
    brainView.resting = reply.sweeps === 0;
  }
  (reply.things || []).forEach((t, i) => {
    state.pins[t.name] = t.place ? t : null;
    if (t.place) row.pins[t.name] = { off: distance(t.place, record.truth[i + 1]), from: t.from, place: t.place, seen: record.in_view[i + 1] };
  });
  brainView.setRecords(reply.things);
  state.history.push(row); if (state.history.length > 3000) state.history.shift();
  const run = state.run;
  if (run && !run.done && record.moment >= run.first && record.moment <= (run.last ?? Infinity)) {
    run.rows.push(row);
    if (run.ended && record.moment >= run.last) summarise(run);
  }
  tour.observe(record, row);
  readouts(record, row);
}

// -- readouts

const cm = (v) => (v === null || v === undefined ? '–' : v < 0.1 ? `${(v * 100).toFixed(1)} cm` : `${Math.round(v * 100)} cm`);
function readouts(record, row) {
  const view = $('chip-view');
  view.hidden = record.in_view[0];
  if (!record.in_view[0]) view.textContent = stage.cameraOn ? `out of view ${(state.unseen * DT).toFixed(1)} s` : `camera off ${(state.unseen * DT).toFixed(1)} s`;
  if (state.settle) $('readout').textContent = `this moment: ${state.settle.sweeps} sweeps · residual ${state.settle.residual.toExponential(1)}`;
  if (!state.more) return;
  $('chip-error').textContent = `error ${cm(row.brain)}`;
  const area = state.belief?.area;
  $('chip-area').textContent = area === undefined || area === null ? 'area –' : area >= 1 ? `area ${area.toFixed(2)} m²` : `area ${Math.round(area * 1e4).toLocaleString('en')} cm²`;
  $('e-brain').textContent = cm(row.brain); $('e-kalman').textContent = cm(row.kalman); $('e-last').textContent = cm(row.last);
  if (state.settle) { $('s-sweeps').textContent = `${state.settle.sweeps} sweeps`; $('s-residual').textContent = state.settle.residual.toExponential(1); }
  const median = (list) => { const t = list.slice(-120).sort((a, b) => a - b); return t.length ? t[t.length >> 1] : null; };
  const think = median(state.think), frame = median(state.frameTimes);
  $('s-ms').textContent = think === null ? '–' : `${think.toFixed(0)} ms`;
  $('s-frame').textContent = frame === null ? '–' : `${frame.toFixed(1)} ms`;
  $('s-lessons').textContent = (state.lessons || 0).toLocaleString('en');
  $('s-lessons').title = `${(state.changedTotal || 0).toLocaleString('en')} synapse changes in all`;
  $('s-refused').textContent = String(state.refused);
}

function learningBadge(now) {
  const el = $('learning'), seen = state.record?.in_view?.[0];
  const on = state.lesson && now - state.lesson.at < 350;
  el.classList.toggle('on', !!on);
  el.classList.toggle('blind', !on && !!state.record && !seen);
  el.textContent = on ? `learning · ${state.lesson.changed.toLocaleString('en')} synapses` : state.record && !seen ? 'no lesson: out of view' : 'learning';
}

// -- a part's card, and the path of a position

const card = { el: $('card'), mode: null, id: null, stage: -1, pinned: false, html: '' };

function context() {
  const d = state.describe, r = state.record;
  const rows = state.history.slice(-300).filter((x) => x.inside !== null);
  return {
    record: r, why: r && !r.in_view[0] ? stage.why(0) : null, own: stage.own,
    belief: state.belief, seenBelief: state.seenBelief, sheet: state.sheet, centres: d.place.centres,
    unseen: state.unseen, pins: state.pins, names: stage.names, settle: state.settle,
    lesson: state.lesson ? { ...state.lesson, ageMs: performance.now() - state.lesson.at } : null,
    lessons: state.lessons || 0, teach: state.teach,
    coverage: rows.length >= 30 ? { moments: rows.length, share: rows.filter((x) => x.inside).length / rows.length } : null,
    act: (name) => brainView.activity(name), regions: state.regions, dt: DT,
  };
}

function renderCard() {
  if (!card.mode || !state.describe) return;
  const ctx = context();
  let html;
  if (card.mode === 'stage') html = stageCard(state.kind, card.stage, ctx);
  else if (card.id.startsWith('tract:')) html = tractCard(state.kind, card.id.slice(6), brainView.flow(card.id.slice(6)));
  else html = partCard(state.kind, card.id, ctx, brainView.unitLine(card.id));
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
  // the card keeps its place while it is open, unless it grows or shrinks a good deal
  if (force || !card.place || card.place.key !== ids.join() || Math.abs(card.place.h - h) > 48) {
    card.place = { ...brainView.cardBeside(ids, w, h), key: ids.join(), h };
    card.el.style.left = `${card.place.left}px`; card.el.style.top = `${card.place.top}px`;
  }
  brainView.leader = { rect: { left: card.place.left, top: card.place.top, w, h }, id: ids[0] };
}
window.addEventListener('resize', () => placeCard(true));

function showCard(mode, pinned) {
  card.mode = mode; card.pinned = pinned; card.html = ''; card.place = null;
  card.el.hidden = false;
  card.el.classList.toggle('pinned', pinned);
  const stages = stagesFor(state.kind);
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
  const stages = stagesFor(state.kind);
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
  if (card.mode === 'stage') { const s = stagesFor(state.kind)[card.stage]; s.parts.forEach((p) => ids.add(p)); if (s.tract) ids.add(`tract:${s.tract}`); }
  if (!card.mode && tour.active && tour.current()?.brain) ids.add(tour.current().brain);
  brainView.spot = ids;
}

brainView.onPart = (id, type) => {
  if (card.mode === 'stage') {
    if (type !== 'tap') return;
    const k = id ? stagesFor(state.kind).findIndex((s) => s.parts.includes(id) || `tract:${s.tract}` === id) : -1;
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
  // a tap elsewhere closes a card that was tapped open
  if (card.mode === 'part' && card.pinned && !event.target.closest('#brain-stage')) closeCard();
});

// -- the tutorial: five steps the visitor performs

const HOME_HINT = 'Drag the hand, a thing or the pillar. Tap a thing to knock on it. Tap the camera to switch it off. Point at a part of the brain and it explains itself.';
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

const tour = {
  active: false, step: 0, since: null, log: [], doneAt: 0,
  steps: [
    { id: 'follow', brain: 'camera',
      text: '<b>Drag the hand</b> across the table. The glow is where the brain says the hand is.',
      aside: 'In the brain, the ringed part plays the role of the visual cortex: the camera’s report enters there.',
      guide: () => ({ ring: stage.world.things[0] }),
      done: (t) => t.moved >= 0.5 },
    { id: 'hide', brain: 'place',
      text: '<b>Drag it behind the pillar</b>, into the shadow. The camera loses it. The brain keeps its place, and the ring of doubt grows.',
      aside: 'The ringed part plays the role of the map: it holds the place while nothing is seen.',
      guide: () => ({ ring: stage.world.things[0], target: state.unseen ? null : shadowPoint(0.32) }),
      done: () => state.unseen >= 40 },
    { id: 'return', brain: 'association',
      text: '<b>Bring it back</b> into the light. The ring closes on the hand.',
      aside: 'Gold flashes are synapses changing: the brain learns only while it sees the hand.',
      guide: () => ({ ring: stage.world.things[0], target: state.unseen ? stage.home.things[0] : null }),
      done: (t) => t.seenRun >= 15 },
    { id: 'move', brain: 'records',
      text: '<b>Drag the cup</b> deep into the shadow. Its pin stays where the camera last saw it.',
      aside: 'The ringed cells play the role of the hippocampus: one record for each thing.',
      guide: () => ({ ring: stage.world.things[1], radius: 0.1, target: shadowPoint(0.5) }),
      done: (t, row) => !!row.pins.cup && !row.pins.cup.seen && row.pins.cup.off >= 0.1 },
    { id: 'knock', brain: 'records',
      text: '<b>Tap the cup</b> to knock on it. The ear hears where the sound came from, and the pin moves without sight.',
      aside: 'A record rewritten from a sound alone.',
      guide: () => ({ ring: stage.world.things[1], radius: 0.1 }),
      done: (t, row) => !!row.pins.cup && !row.pins.cup.seen && row.pins.cup.from === 'heard' },
  ],
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
    this.since = { moved: 0, seenRun: 0, from: state.record?.moment ?? 0 };
    this.doneAt = 0;
    coach(`${s.text} <span class="aside">${s.aside}</span>`, '', this.step, this.steps.length);
    document.body.dataset.tour = s.id;
    spots();
  },
  observe(record, row) {
    if (!this.active || this.doneAt) return;
    const t = this.since, prev = state.previous;
    if (record.in_view[0]) { t.seenRun += 1; if (prev) t.moved += distance(record.truth[0], prev.truth[0]); } else t.seenRun = 0;
    const s = this.current();
    if (!s.done(t, row)) return;
    this.log.push({ id: s.id, from: t.from, to: record.moment });
    this.doneAt = performance.now();
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
  const s = {
    geometry: stage.geometry, record: state.record, previous: state.previous,
    blend: clamp((now - state.stepAt) / (1000 * DT), 0, 1), joints: stage.world.joints, things: stage.world.things,
    names: stage.names, own: stage.own, cameraOn: stage.cameraOn, showHidden: state.showHidden, compare: state.more,
    belief: state.belief, sheet: state.sheet, pins: state.pins, selected: focused && focusByKey ? state.selected : null,
    controls: state.estimates, rate: 0.9, guide: tour.active && !tour.doneAt && state.ready ? tour.current().guide() : null,
  };
  sceneView.draw(s, now);
  if (state.more) { mapView.draw(s); chartView.draw(state.history, { compare: true, dt: DT }); }
  brainView.frame(now, interval);
  learningBadge(now);
  if (card.mode) renderCard();
  requestAnimationFrame(frame);
}

// -- a recorded scene, and its summary (the page check reads it)

async function ensureBrain(geometry) {
  // a scene on another plane or arm than the brain's inputs cover: a new baseline brain for it
  const have = state.config, same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  if (same(have.plane, geometry.plane) && same(have.limits, geometry.arm.limits)) return;
  if (state.kind !== 'baseline') { coach('This scene stands on another plane or arm than the brain was raised on.', 'quiet'); return; }
  await reborn({ plane: geometry.plane, limits: geometry.arm.limits, ear: geometry.ear });
}

async function playScene(scene) {
  if (!scene) return null;
  stage.stop(); finishRun();
  await ensureBrain(scene.geometry);
  while (state.pending) await new Promise((r) => setTimeout(r, 5));
  await brain.call('reset', {});
  stage.play(scene);
  setCase(scene.case === 'own' ? 'own' : 'other', false);
  restartControls(scene.start[0]);
  state.undo = []; $('undo').disabled = true;
  $('play').textContent = 'Stop';
  return new Promise((resolve) => { state.run = { name: scene.name, kind: scene.kind, rows: [], first: stage.moment + 1, ended: false, done: false, resolve, steps: scene.steps }; });
}
const playReach = (index) => playScene(state.reaches[index]);

function mean(rows, key, pick) {
  const values = rows.filter(pick).map((r) => r[key]).filter((v) => v !== null && v !== undefined);
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
}

// A run ends at the scene's last moment, or where the visitor stops it; it is summarised once
// that moment's answer is in.
function finishRun() {
  const run = state.run;
  if (!run || run.ended) return;
  run.ended = true;
  run.last = state.record ? state.record.moment : 0;
  $('play').textContent = 'Play';
  if (!state.pending) summarise(run);
}

function summarise(run) {
  run.done = true;
  const rows = run.rows, out = (r) => !r.seen, inn = (r) => r.seen, answers = rows.filter((r) => r.brain !== null);
  const summary = {
    name: run.name, kind: run.kind, moments: rows.length, out_of_view: rows.filter(out).length,
    no_answer: rows.length - answers.length,
    in_view: { brain: mean(rows, 'brain', inn), kalman: mean(rows, 'kalman', inn), last: mean(rows, 'last', inn) },
    unseen: { brain: mean(rows, 'brain', out), kalman: mean(rows, 'kalman', out), last: mean(rows, 'last', out) },
    inside_area: answers.length ? answers.filter((r) => r.inside).length / answers.length : null,
    inside_area_unseen: answers.filter(out).length ? answers.filter((r) => out(r) && r.inside).length / answers.filter(out).length : null,
    lessons_in_view: rows.filter((r) => r.seen && r.lesson).length, lessons_out_of_view: rows.filter((r) => !r.seen && r.lesson).length,
  };
  state.lastRun = summary;
  document.body.dataset.run = JSON.stringify(summary);
  run.resolve(summary);
}

async function loadFile(file) {
  try {
    const scene = readScene(JSON.parse(await file.text()));
    if (!scene.name) scene.name = file.name;
    coach(`Playing ${scene.name}: ${scene.steps} moments, ${scene.things === 1 ? 'one thing' : `${scene.things} things`}.`, 'quiet');
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
  if (state.ready) brain.call('reset', {}).catch((error) => fail(error.message));
}
function setCase(kind, restart = true) {
  if (restart) { stage.setCase(kind); restartControls(); }
  document.querySelectorAll('[data-case]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.case === kind)));
  if (kind === 'own' && state.selected === 'hand') state.selected = 'cup';
  if (kind === 'own' && restart) coach('The arm moves its own hand: tap the table and it reaches there.', 'quiet');
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

function knock(name) { audio(); stage.knock(name); }

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
  const [direction, far] = cue;
  // to the left of the camera's axis is to the listener's left
  const pan = clamp(-Math.sin(direction - stage.geometry.camera.heading) * 1.6, -1, 1);
  const gain = clamp(0.5 / (0.5 + far), 0.15, 0.9);
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

// -- direct manipulation: drag to move, tap to knock or to switch the camera

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
  stage.moveArm(to, Math.round(clamp(distance(point, from) / 0.02, 12, 60)));
}
function moveSelected(name, p) {
  if (name === 'pillar') { const o = stage.geometry.occluders[0]; if (o) o.center = inPlane(p, o.radius); return; }
  const k = stage.names.indexOf(name);
  if (k < 0) return;
  if (k === 0 && stage.own) { reachTo(p); return; }
  if (stage.reach) { stage.stop(); finishRun(); }
  stage.targets[k] = inPlane(p);
}
function tap(name) {
  if (name === 'camera') setCamera(!stage.cameraOn);
  else if (name !== 'hand' && name !== 'pillar') knock(name);
}

function bindScene() {
  const canvas = $('scene');
  canvas.addEventListener('pointerdown', (event) => {
    const { x, y, p } = planePoint(event);
    const hit = sceneView.hit(x, y, sceneState());
    focusByKey = false; canvas.classList.remove('keys');
    canvas.focus({ preventScroll: true });
    if (!hit) { if (stage.own) reachTo(p); return; }
    press = { name: hit, x, y, at: performance.now(), moved: false };
    if (hit !== 'camera') state.selected = hit;
    try { canvas.setPointerCapture(event.pointerId); } catch { /* a synthetic pointer has no capture */ }
    event.preventDefault();
  });
  canvas.addEventListener('pointermove', (event) => {
    const { x, y, p } = planePoint(event);
    if (!press) {
      const hit = sceneView.hit(x, y, sceneState());
      canvas.classList.toggle('grab', !!hit && hit !== 'camera');
      canvas.classList.toggle('tap', hit === 'camera');
      return;
    }
    if (!press.moved && Math.hypot(x - press.x, y - press.y) > 6) {
      press.moved = true;
      if (press.name !== 'camera') { pushUndo({ name: press.name, from: stage.where(press.name) }); canvas.classList.add('dragging'); }
    }
    if (press.moved && press.name !== 'camera') moveSelected(press.name, p);
  });
  const end = (event) => {
    if (!press) return;
    const k = stage.names.indexOf(press.name);
    if (k >= 0) stage.targets[k] = null;
    if (event.type === 'pointerup' && !press.moved && performance.now() - press.at < 450) tap(press.name);
    press = null; canvas.classList.remove('dragging');
  };
  canvas.addEventListener('pointerup', end);
  canvas.addEventListener('pointercancel', end);
  canvas.addEventListener('keyup', (event) => { if (event.key === 'Tab') { focusByKey = true; canvas.classList.add('keys'); } });
  canvas.addEventListener('keydown', (event) => {
    const order = ['hand', 'cup', 'wrench', 'box', 'pillar'];
    const arrows = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1] };
    const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
    focusByKey = true; canvas.classList.add('keys');
    if (key >= '1' && key <= '5') state.selected = order[Number(key) - 1];
    else if (arrows[key]) {
      const name = state.selected, k = stage.names.indexOf(name), stride = event.shiftKey ? 0.12 : 0.04;
      const from = name === 'pillar' ? stage.geometry.occluders[0]?.center : stage.targets[k] || stage.world.things[k];
      if (!from) return;
      pushUndo({ name, from: stage.where(name) });
      moveSelected(name, [from[0] + arrows[key][0] * stride, from[1] + arrows[key][1] * stride]);
    } else if (key === 'k' || key === 'Enter') tap(state.selected);
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
  document.querySelectorAll('[data-case]').forEach((b) => b.addEventListener('click', () => {
    stage.stop(); finishRun();
    setCase(b.dataset.case);
  }));
  $('teach').addEventListener('change', (e) => { state.teach = e.target.checked; });
  $('play').addEventListener('click', () => {
    if (state.run && !state.run.ended) { stage.stop(); finishRun(); return; }
    playReach(Number($('reach').value));
  });
  $('load').addEventListener('click', () => $('file').click());
  $('file').addEventListener('change', (e) => { if (e.target.files[0]) loadFile(e.target.files[0]); e.target.value = ''; });
  window.addEventListener('dragover', (e) => e.preventDefault());
  window.addEventListener('drop', (e) => { e.preventDefault(); const file = e.dataTransfer?.files?.[0]; if (file) loadFile(file); });
  $('reborn').addEventListener('click', () => reborn({}));
}

async function reborn(config) {
  if (!state.describe) return;
  state.ready = false; setRuntime('A new brain', 'busy');
  while (state.pending) await new Promise((r) => setTimeout(r, 10));
  try {
    const { reply, arrays } = await brain.call('reborn', { config });
    Object.assign(state.config, config);
    adopt(reply, arrays);
    state.history = []; state.pins = {}; state.belief = null; state.seenBelief = null; state.sheet = null; state.lessons = 0; state.refused = 0; state.lesson = null;
    state.ready = true; setRuntime('Ready', 'ready');
  } catch (error) { fail(error.message); }
}

// -- start

function adopt(describe, arrays) {
  state.describe = describe;
  state.kind = describe.brain.kind;
  state.regions = Object.fromEntries(describe.regions.map((r) => [r.name, r]));
  closeCard();
  brainView.setBrain(describe, arrays);
  const b = describe.brain;
  $('brain-badge').hidden = !!b.trained; $('brain-badge').textContent = b.label;
  $('brain-note').textContent = b.trained ? '' : `${b.label}. ${b.note}`;
  $('card-wheel').textContent = `cadence-net==${describe.cadence}`;
  const facts = [['Brain', b.compose || b.label], ['Neurons', describe.neurons.toLocaleString('en')], ['Synapses', `${describe.synapses.toLocaleString('en')}, every one drawn`],
    ['Place answer', `${describe.place.bins} units an axis`], ['Records', `${describe.records.capacity} slots`], ['A moment', `${(DT * 1000).toFixed(0)} ms of the scene`],
    ['Runs in', `Pyodide ${describe.manifest?.pyodide || state.pyodide || ''}, ${brainView.mode === 'webgl2' ? 'WebGL2' : 'Canvas2D'}`]];
  if (describe.manifest) state.pyodide = describe.manifest.pyodide;
  $('card-facts').innerHTML = facts.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('');
}

async function start() {
  bindScene(); bindControls(); restartControls();
  if (params.get('details') === '1') setMore(true);
  requestAnimationFrame(frame);
  try {
    const pack = new URL('pack/', location.href);
    const reaches = fetch(new URL('reaches.json', pack)).then((r) => (r.ok ? r.json() : { reaches: [] }));
    const g = stage.geometry;
    state.config = { plane: g.plane.slice(), limits: g.arm.limits.map((l) => l.slice()), ear: g.ear.slice() };
    const { reply, arrays } = await brain.call('init', { pack: pack.href, config: state.config });
    adopt(reply, arrays);
    restartControls();
    state.reaches = (await reaches).reaches.map((r) => readScene(r));
    $('reach').innerHTML = state.reaches.map((r, i) => `<option value="${i}">${r.name}</option>`).join('');
    state.ready = true;
    setRuntime('Ready', 'ready');
    $('play').disabled = false;
    document.body.dataset.ready = '1';
    const auto = params.get('autoplay'), wanted = params.get('tour');
    let seen = false;
    try { seen = localStorage.getItem('out-of-sight-tour') === '1'; } catch { /* a browser without storage */ }
    if (auto !== null) { tour.finish(); playReach(Number(auto)); }
    else if (wanted === '0' || (seen && wanted === null)) tour.finish();
    else if (wanted === '1' || wanted === 'fast') tour.start();
    else { coach('', 'quiet'); $('welcome').hidden = false; $('welcome-go').focus({ preventScroll: true }); }
  } catch (error) { fail(error.message); }
}

// what the page check drives
window.outOfSight = { stage, state, brainView, sceneView, tour, card, playScene, playReach, loadScene: (data) => playScene(readScene(data)), knock, setCamera, reset, undo,
  setMore, openPart, openStage, closeCard, shadowPoint,
  /** Where a thing, the pillar or the camera is on the screen, in client pixels. */
  screenOf(name) {
    const box = $('scene').getBoundingClientRect();
    const p = name === 'camera' ? stage.geometry.camera.position : stage.where(name);
    const q = sceneView.toScreen(p);
    return [box.left + q[0], box.top + q[1]];
  },
  screenAt(p) { const box = $('scene').getBoundingClientRect(), q = sceneView.toScreen(p); return [box.left + q[0], box.top + q[1]]; },
  frameStats(last = 600) {
    const t = state.frameTimes.slice(-last).sort((a, b) => a - b), q = (f) => (t.length ? t[Math.min(t.length - 1, Math.floor(f * t.length))] : null);
    return { frames: t.length, median_ms: q(0.5), p95_ms: q(0.95), worst_ms: t.at(-1) ?? null };
  } };

start();
