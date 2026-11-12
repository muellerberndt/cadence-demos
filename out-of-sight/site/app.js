// Out of sight: the page. The scene steps in JavaScript (world.js, a port of the tracking
// chamber's world); every moment goes to the brain in the worker (Python in Pyodide, the Cadence
// wheel), and everything drawn of the brain is its reply: the place it gives the hand, the area
// that holds it, every neuron's activation, the settle sweep by sweep, the synapses a lesson
// changed and the records of the things. One moment is sent at a time: the scene's clock waits
// for the brain's answer, so the brain lives every moment of the scene in order.
//
// The page is one screen: the scene and the brain. The visitor drags the hand, a thing or the
// pillar, drags the floor to turn the camera, taps a thing to knock on it and taps the body to
// switch the camera. A small map shows the brain's records as the body has them, and answers
// two questions: where is this thing, and what is that way. A short tutorial walks through the
// promise; every part of the brain explains itself when pointed at (cards.js).

import { Stage, DT, forward, visible, readScene, around, wrap, Random, MERGED_JOINTS } from './world.js';
import { SceneView, MapView, ChartView, AroundView } from './scene.js';
import { BrainView } from './brain.js';
import { LastSeen, Kalman, radiusAt, RATE } from './controls.js';
import { sheetArea } from './region.js';
import { partCard, tractCard, stageCard, stagesFor, uncertainty, configure } from './cards.js';
import { whereSentence, whatSentence, handSentence, the, placed } from './where.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const distance = (p, q) => Math.hypot(p[0] - q[0], p[1] - q[1]);

const stage = new Stage({ seed: Number(params.get('seed') ?? 20261112) });
const sceneView = new SceneView($('scene'));
const mapView = new MapView($('map'));
const chartView = new ChartView($('chart'));
const aroundView = new AroundView($('around'));
const brainView = new BrainView({ canvas: $('brain'), overlay: $('brain-overlay'), parts: $('parts'), renderer: params.get('renderer') || 'auto' });

const state = {
  ready: false, failed: null, kind: 'baseline',
  showHidden: true, more: false, teach: true, selected: 'hand',
  sight: params.get('sight') !== '0', takesSight: false, held: false, // the sight evidence: asked for, taken by the host, and whether the hand's place was held back
  gone: false, rulesGone: false, // the hand's place is marked gone (in sight, with no report), and whether the pack's library has that rule
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
    hand: { report }, joints: record.joints, commands: record.commands, body: record.body, own: stage.own,
    things: stage.names.slice(1).map((name, i) => ({ name, report: record.report[i + 1], cue: record.cue[i + 1] })),
    teach: state.teach, wave: state.waveEvery > 0 && record.moment % state.waveEvery === 0 && !brainView.wave,
    // the scene as it stands at this moment: the worker says from it which predicted places the camera would see
    view: state.sight && state.takesSight ? { on: stage.cameraOn, geometry: stage.geometry, joints: stage.world.joints } : null,
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
    area: null, uncertainty: null, inside: null, lesson: false, place: null, pins: {}, held: false, sight: false, gone: false };
  state.estimates = estimates;
  if (reply.refused) {
    state.refused = reply.refusals;
  } else {
    state.belief = { place: reply.place, sd: reply.sd, area: reply.area, radius: reply.radius ?? null };
    state.asked = reply.asked ?? true; // a module's brain is asked only for a place that may have moved
    state.held = !!reply.held_back; row.held = state.held; row.sight = !!reply.sight?.given;
    state.gone = !!reply.gone; row.gone = state.gone; if (Array.isArray(reply.sight?.gone)) state.rulesGone = true;
    if (seen) state.seenBelief = state.belief;
    state.sheet = { px: arrays.px, py: arrays.py };
    row.brain = distance(reply.place, truth); row.place = reply.place;
    // inside the stated area: the ellipse of the answer's spread at the stated rate
    const k2 = -2 * Math.log(1 - 0.9);
    row.inside = ((reply.place[0] - truth[0]) / Math.max(reply.sd[0], 1e-6)) ** 2 + ((reply.place[1] - truth[1]) / Math.max(reply.sd[1], 1e-6)) ** 2 <= k2;
    if (reply.cells && arrays.cells) {
      // the answer states its area as a set of cells (region.js): the true hand is inside it
      // where its cell is one of them, and its one number is the radius of a circle as large
      const cells = sheetArea(reply.cells, arrays.cells), even = Math.sqrt(cells.area / Math.PI) / radiusAt(RATE);
      state.belief = { ...state.belief, cells, area: cells.area, sd: [even, even], radius: null };
      if (seen) state.seenBelief = state.belief;
      row.inside = cells.holds(truth);
    }
    row.area = state.belief.area; row.uncertainty = uncertainty(state.belief);
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
    brainView.restLabel = reply.asked === false ? 'nothing says the place moved' : null;
  }
  (reply.things || []).forEach((t, i) => {
    state.pins[t.name] = t.place ? t : null;
    if (t.place) row.pins[t.name] = { off: distance(t.place, record.truth[i + 1]), from: t.from, place: t.place, seen: record.in_view[i + 1], gone: !!t.gone, ...aroundBody(record.body, t.place) };
  });
  brainView.setRecords(reply.things);
  state.history.push(row); if (state.history.length > 3000) state.history.shift();
  const run = state.run;
  if (run && !run.done && record.moment >= run.first && record.moment <= (run.last ?? Infinity)) {
    run.rows.push(row);
    if (run.ended && record.moment >= run.last) summarise(run);
  }
  const heard = record.cue.findIndex((cue, k) => k > 0 && cue);
  if (heard > 0 && state.pins[stage.names[heard]]?.place) {
    // a knock: the cue's own error (its stated noise at the distance heard) beside where the map put the thing
    const name = stage.names[heard], noise = stage.world.cueNoise, sd = record.cue[heard][1] * Math.hypot(noise[0], noise[1]);
    say(`A knock: the ear places ${the(name)} to within about ${Math.round(sd * 100)} cm. The map puts it ${placed(around(stage.geometry, state.pins[name].place))}.`, { place: state.pins[name].place });
  }
  tour.observe(record, row);
  readouts(record, row);
}

// A place as the body had it at a moment: its distance and its bearing from the way it faced.
function aroundBody(body, place) {
  return around({ camera: body }, place);
}

// -- readouts

const cm = (v) => (v === null || v === undefined ? '–' : v < 0.1 ? `${(v * 100).toFixed(1)} cm` : `${Math.round(v * 100)} cm`);
function readouts(record, row) {
  const view = $('chip-view');
  view.hidden = record.in_view[0];
  // with the camera off and the hand moving, a module is outside what it was raised on after about 100 moments
  const far = state.describe?.limits?.unseen_moving, moving = state.previous && distance(record.truth[0], state.previous.truth[0]) > 1e-4;
  if (moving) state.movedDark = stage.cameraOn ? 0 : (state.movedDark || 0) + 1; else if (stage.cameraOn) state.movedDark = 0;
  if (!record.in_view[0]) view.textContent = stage.cameraOn ? `out of view ${(state.unseen * DT).toFixed(1)} s` : `camera off ${(state.unseen * DT).toFixed(1)} s`;
  const range = $('chip-range'), held = $('chip-held');
  range.hidden = !(!stage.cameraOn && far && state.movedDark > 5);
  if (!range.hidden) range.innerHTML = `<span class="wide">this module was </span>raised on up to about ${Math.round(far * DT)} s of a moving hand it does not see`;
  // the sight evidence held the place back: the camera would see the hand where its movement leads, and does not
  held.hidden = !(state.held && !record.in_view[0] && !state.gone);
  // marked gone: the camera sees the place held for the hand, and no hand is there
  $('chip-gone').hidden = !(state.gone && !record.in_view[0]);
  // a narrow screen shows the first words alone
  if (!held.hidden && held.dataset.kind !== String(state.takesSight)) {
    held.dataset.kind = String(state.takesSight);
    held.innerHTML = state.takesSight === 'function' ? 'it has not come out<span class="wide">: held at the middle of its hidden stretch</span>' : 'it did not come out where its movement leads<span class="wide">: held on its hidden path</span>';
  }
  if (state.settle) $('readout').textContent = state.asked === false ? 'this moment: the brain was not asked' : `this moment: ${state.settle.sweeps} sweeps run · residual ${state.settle.residual.toExponential(1)}`;
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
    unseen: state.unseen, pins: state.pins, names: stage.names, settle: state.settle, asked: state.asked,
    lesson: state.lesson ? { ...state.lesson, ageMs: performance.now() - state.lesson.at } : null,
    lessons: state.lessons || 0, teach: state.teach, held: state.held, sight: state.sight && state.takesSight, course: !!d.space?.course,
    gone: state.gone, rulesGone: state.rulesGone,
    coverage: rows.length >= 30 ? { moments: rows.length, share: rows.filter((x) => x.inside).length / rows.length } : null,
    act: (name) => brainView.activity(name), regions: state.regions, dt: DT,
    around: (place) => around(stage.geometry, place),
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
// a sheet is a share of its pane, which grows while it opens: the brain keeps clear of it as it stands
new ResizeObserver(() => { if (card.mode && narrow.matches) placeCard(true); }).observe(card.el);

function showCard(mode, pinned) {
  card.mode = mode; card.pinned = pinned; card.html = ''; card.place = null;
  card.el.hidden = false;
  card.el.classList.toggle('pinned', pinned);
  const stages = stagesFor(state.kind);
  card.el.classList.toggle('wide', mode === 'stage' && !!stages[card.stage].wide); // a long stage gets a wider card
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
  if (!card.mode && tour.active && tour.current()?.brain) ids.add(tourPart(tour.current()));
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

// -- the two questions: where is this thing, and what is that way

function say(text, asked = null) {
  const el = $('said');
  el.textContent = text; el.classList.remove('old');
  state.said = asked ? { ...asked, at: performance.now() } : null;
  document.body.dataset.said = text;
  clearTimeout(say.timer);
  if (text) say.timer = setTimeout(() => { el.classList.add('old'); }, 9000);
}

/** Where is this thing? The hand: the brain's own place answer. A kind of thing: its record. */
async function askWhere(name) {
  if (!state.ready) return null;
  const g = stage.geometry, k = stage.names.indexOf(name);
  let place, text;
  if (name === 'hand') {
    place = state.belief?.place || null;
    text = handSentence(place ? around(g, place) : null, state.unseen, DT, state.gone);
  } else {
    const { reply } = await brain.call('ask', { thing: name });
    place = reply.place;
    text = whereSentence(name, place ? around(g, place) : null, reply, !!state.record?.in_view?.[k], DT);
  }
  if (place) aroundView.ask(around(g, place).bearing);
  say(text, place ? { place } : null);
  return text;
}

/** What is that way? `bearing`: from the way the body faces (0 ahead, positive to the left). */
async function askWhat(bearing, tolerance = 0.45, point = null) {
  if (!state.ready) return null;
  const g = stage.geometry;
  const { reply } = await brain.call('what', { origin: g.camera.position, direction: g.camera.heading + bearing, tolerance, point });
  let name = reply.name, place = reply.place, gap = reply.gap ?? Infinity;
  if (state.belief?.place) {
    // the hand is the brain's own answer, not a record: it is named where it lies nearer that way
    const off = Math.abs(wrap(around(g, state.belief.place).bearing - bearing));
    if (off <= tolerance && off < gap) { name = 'hand'; place = state.belief.place; }
  }
  aroundView.ask(bearing);
  const text = whatSentence(bearing, name, place ? around(g, place) : null);
  say(text, place ? { place } : null);
  return text;
}

function bindAround() {
  const canvas = $('around');
  const at = (event) => { const box = canvas.getBoundingClientRect(); return [event.clientX - box.left, event.clientY - box.top]; };
  canvas.addEventListener('click', (event) => {
    const [x, y] = at(event), name = aroundView.hit(x, y);
    if (name) askWhere(name); else askWhat(aroundView.bearingAt(x, y, stage.geometry), 0.45, aroundView.pointAt(x, y, stage.geometry));
  });
  canvas.addEventListener('keydown', (event) => {
    const ways = { ArrowUp: 0, ArrowLeft: Math.PI / 2, ArrowRight: -Math.PI / 2, ArrowDown: Math.PI };
    if (event.key in ways) askWhat(ways[event.key]);
    else if (event.key >= '1' && event.key <= '4') askWhere(stage.names[Number(event.key) - 1]);
    else return;
    event.preventDefault();
  });
  $('around-mode').addEventListener('click', () => {
    aroundView.mode = aroundView.mode === 'me' ? 'room' : 'me';
    $('around-mode').textContent = aroundView.mode === 'me' ? 'around me' : 'the room';
    $('inset').classList.toggle('room', aroundView.mode === 'room');
  });
}

// -- the tutorial: six steps the visitor performs

const HOME_HINT = 'Drag the hand, a thing or the pillar. Drag the floor to turn the camera. Tap a thing to knock on it. Tap the small map to ask what is where. Point at a part of the brain and it explains itself.';
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
// A point `far` metres further from the body than a thing stands, out of the camera's view.
function awayPoint(name, far) {
  const g = stage.geometry, p = stage.where(name), eye = g.camera.position;
  const d = distance(p, eye) || 1, [lx, hx, ly, hy] = g.plane;
  const q = [clamp(p[0] + ((p[0] - eye[0]) / d) * far, lx + 0.08, hx - 0.08), clamp(p[1] + ((p[1] - eye[1]) / d) * far, ly + 0.08, hy - 0.08)];
  return visible(g, q, stage.world.joints) ? shadowPoint(0.5) : q;
}

// The part of the brain each step of the tutorial points at, and its sentence, for a brain of
// another kind than the baseline.
const TOUR_PARTS = {
  place: {
    follow: ['place', 'The ringed part shows the brain the place a program beside it holds for the hand.'],
    hide: ['shift', 'The ringed part is the brain’s answer: how far the place moves in each step while nothing is seen.'],
    return: ['spread', 'The ringed part answers how far off the place may be: the ring of doubt. Gold flashes are lessons, made of the camera’s reports alone.'],
    knock: ['found', 'The ringed part answers the place a sound names.'],
  },
};
// on its course a thing is moved by its seen movement times the share the brain's keep answers
const ON_COURSE = { hide: ['keep', 'The ringed part is the brain’s answer: how much of its last seen movement the hand keeps in each step while nothing is seen.'] };
const tourEntry = (s) => (state.kind === 'place' && state.describe?.space?.course && state.regions.keep && ON_COURSE[s.id]) || TOUR_PARTS[state.kind]?.[s.id];
const tourPart = (s) => tourEntry(s)?.[0] || s.brain;
const tourAside = (s) => tourEntry(s)?.[1] || s.aside;

// The tutorials, one for each kind of model. Each holds its sentence (the page's headline and
// the welcome's line: ONE constant a tutorial) and the steps the visitor performs.
//
// `held` is the tutorial of the model on this page: a place held while the hand is hidden.
//
// `map` is prepared for the model of cadence#320's "The model": the map is the brain's own
// state, a thing enters it when it is first sensed, and with no sensory information the last
// known position stays. It is chosen when a host describes its brain as of kind 'map'; no host
// of this pack does. Its sentence waits for a decision and is null until then (the page keeps
// the `held` sentence). Its steps read the page's state as it is named in this file (pins, the
// gone mark, the moments unseen), and its `ring` parts are null until the module names its
// regions. `start`: where the camera looks when the page opens, so that the map fills as the
// visitor turns it; null keeps the scene's own.
const PROMISE = 'Hide the hand, and the brain keeps knowing where it is.';
const TOURS = {
  held: {
    promise: PROMISE,
    start: null,
    steps: [
    { id: 'follow', brain: 'camera',
      text: '<b>Drag the hand</b> across the table. The glow is where the brain says the hand is.',
      aside: 'In the brain, the ringed part plays the role of the visual cortex: the camera’s report enters there.',
      guide: () => ({ ring: stage.world.things[0] }),
      done: (t) => t.moved >= 0.5 },
    { id: 'hide', brain: 'place',
      text: '<b>Drag it behind the pillar</b>, into the shadow. The camera loses it. Watch where the glow goes, and how wide its ring of doubt is.',
      aside: 'The ringed part plays the role of the map: the peak over its units is where the brain says the hand is.',
      guide: () => ({ ring: stage.world.things[0], target: state.unseen ? null : shadowPoint(0.32) }),
      done: () => state.unseen >= 40 },
    { id: 'return', brain: 'association',
      text: '<b>Bring it back</b> into the light. The ring closes on the hand.',
      aside: 'Gold flashes are synapses changing: the brain learns only while it sees the hand.',
      guide: () => ({ ring: stage.world.things[0], target: state.unseen ? stage.home.things[0] : null }),
      done: (t) => t.seenRun >= 15 },
    { id: 'turn', brain: 'records',
      text: '<b>Turn the camera away from the apple</b>: drag the floor around the body, or twist with two fingers. The apple ends up behind you, and the map keeps it.',
      aside: 'The small map shows the room as the body has it: you at the centre, facing up. Tap a thing in it to ask where it is.',
      guide: () => ({ ring: stage.geometry.camera.position, radius: 0.09, turn: { from: stage.geometry.camera.heading, to: awayHeading('apple') } }),
      done: (t, row) => { t.behind = row.pins.apple && !row.pins.apple.seen && Math.abs(row.pins.apple.bearing) >= 1.95 ? (t.behind || 0) + 1 : 0; return t.behind >= 12; },
      after: () => askWhere('apple') },
    { id: 'move', brain: 'records',
      text: '<b>Drag the cup</b> while the camera looks away. Its pin stays where the camera last saw it.',
      aside: 'The ringed cells play the role of the hippocampus: one record for each kind of thing, with its place.',
      guide: () => ({ ring: stage.world.things[1], radius: 0.1, target: state.pins.cup && distance(state.pins.cup.place, stage.world.things[1]) < 0.1 ? awayPoint('cup', 0.3) : null }),
      done: (t, row) => !!row.pins.cup && !row.pins.cup.seen && row.pins.cup.off >= 0.1 },
    { id: 'knock', brain: 'records',
      text: '<b>Tap the cup</b> to knock on it. The ear hears where the sound came from, and the pin moves without sight.',
      aside: 'A record rewritten from a sound alone.',
      guide: () => ({ ring: stage.world.things[1], radius: 0.1 }),
      done: (t, row) => !!row.pins.cup && !row.pins.cup.seen && row.pins.cup.from === 'heard' },
    ],
  },
  map: {
    promise: null,
    start: null,
    steps: [
      { id: 'look', brain: null,
        text: '<b>Look around</b>: drag the floor around the body to turn the camera. Each thing arrives on the map at the moment the camera first sees it.',
        aside: 'Nothing is handed to the brain beforehand. The small map shows what it holds.',
        guide: () => ({ ring: stage.geometry.camera.position, radius: 0.09 }),
        done: () => stage.names.slice(1).every((name) => state.pins[name]?.place) },
      { id: 'turn', brain: null,
        text: '<b>Turn the camera away from the apple.</b> It stays on the map, behind you.',
        aside: 'With no sight of it, its last known place is the one the map holds.',
        guide: () => ({ ring: stage.geometry.camera.position, radius: 0.09, turn: { from: stage.geometry.camera.heading, to: awayHeading('apple') } }),
        done: (t, row) => { t.behind = row.pins.apple && !row.pins.apple.seen && Math.abs(row.pins.apple.bearing) >= 1.95 ? (t.behind || 0) + 1 : 0; return t.behind >= 12; },
        after: () => askWhere('apple') },
      { id: 'move', brain: null,
        text: '<b>Drag the cup</b> while the camera looks elsewhere. The map keeps the place where the camera last saw it.',
        aside: 'Nothing told the brain that the cup moved.',
        guide: () => ({ ring: stage.world.things[1], radius: 0.1, target: state.pins.cup && distance(state.pins.cup.place, stage.world.things[1]) < 0.1 ? awayPoint('cup', 0.3) : null }),
        done: (t, row) => !!row.pins.cup && !row.pins.cup.seen && row.pins.cup.off >= 0.1 },
      { id: 'find', brain: null,
        text: '<b>Look back</b> at where the cup stood. The camera finds the place empty, and the map clears it. Then <b>look at the cup</b>: the map has it again.',
        aside: 'The sight of an empty place is information as well.',
        guide: () => ({ ring: stage.geometry.camera.position, radius: 0.09 }),
        done: (t, row) => { if (row.pins.cup?.gone) t.cleared = true; return !!t.cleared && !!row.pins.cup?.seen && row.pins.cup.off < 0.05; } },
      { id: 'knock', brain: null,
        text: '<b>Turn away from the cup and tap it</b> to knock on it. The ear hears where the sound came from, and the map updates from sound alone.',
        aside: 'A sound carries a direction and a distance, which name a place.',
        guide: () => ({ ring: stage.world.things[1], radius: 0.1 }),
        done: (t, row) => !!row.pins.cup && !row.pins.cup.seen && row.pins.cup.from === 'heard' },
      { id: 'hide', brain: null,
        text: '<b>Drag the hand behind the pillar</b>, into the shadow. The camera loses it, and the map holds where it was last seen.',
        aside: 'The map says how long ago that was.',
        guide: () => ({ ring: stage.world.things[0], target: state.unseen ? null : shadowPoint(0.32) }),
        done: () => state.unseen >= 40 },
    ],
  },
};
const tourOf = () => TOURS[state.kind] || TOURS.held;
/** The page's sentence: the headline over the scene and the welcome's line. */
function promise() {
  const text = tourOf().promise || PROMISE;
  document.querySelectorAll('[data-promise]').forEach((el) => { el.textContent = text; });
}

const tour = {
  active: false, step: 0, since: null, log: [], doneAt: 0,
  get steps() { return tourOf().steps; },
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
    coach(`${s.text} <span class="aside">${tourAside(s)}</span>`, '', this.step, this.steps.length);
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
    s.after?.();
    coach(`${s.text} <span class="aside">${tourAside(s)}</span>`, 'done', this.step + 1, this.steps.length);
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
    gone: state.gone, controls: state.estimates, rate: 0.9, guide: tour.active && !tour.doneAt && state.ready ? tour.current().guide() : null,
    asked: state.said && now - state.said.at < 2200 ? state.said : null,
  };
  sceneView.draw(s, now);
  aroundView.draw(s, now);
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
  say('');
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
  // no joint is asked for more in a step than the brain's range of commands holds
  const most = Math.max(...to.map((q, k) => Math.abs(q - stage.world.joints[k]))), cap = state.describe?.limits?.command;
  stage.moveArm(to, Math.max(Math.round(clamp(distance(point, from) / 0.02, 12, 60)), cap ? Math.ceil((most / cap) * 1.9) : 0));
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
      // a second finger: the two of them turn the camera, as a hand turns a dial
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
        // the floor is a turntable for the camera: it turns by the angle the pointer sweeps around the body
        if (stage.reach) { stage.stop(); finishRun(); }
        pushUndo({ name: 'heading', from: stage.where('heading') });
        press.angle = angleFromBody(press.x, press.y).angle; press.target = stage.geometry.camera.heading;
      } else pushUndo({ name: press.name, from: stage.where(press.name) });
    }
    if (!press.moved) return;
    if (press.name === 'camera') {
      // dragged from the body itself: the camera faces the pointer
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
    if (!tapped) return;
    if (name === 'floor') { if (stage.own) reachTo(p); } else tap(name);
  };
  canvas.addEventListener('pointerup', end);
  canvas.addEventListener('pointercancel', end);
  canvas.addEventListener('keyup', (event) => { if (event.key === 'Tab') { focusByKey = true; canvas.classList.add('keys'); } });
  canvas.addEventListener('keydown', (event) => {
    const order = [...stage.names, 'pillar'];
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
  const b = describe.brain, badge = b.badge || (b.trained ? '' : b.label);
  $('brain-badge').hidden = !badge; $('brain-badge').textContent = badge;
  $('brain-note').textContent = badge ? `${b.label}. ${b.note}` : '';
  brainView.verb = state.kind === 'baseline' ? 'settled in' : 'answered in';
  state.takesSight = describe.sight || false; state.held = false; state.gone = false; state.rulesGone = false; // 'function', 'flags' or false
  configure(state.kind, { course: !!describe.space?.course });
  promise();
  // a module arrives trained: on the page it takes no lessons unless the visitor switches them on (Details)
  if (params.get('teach') !== null) state.teach = params.get('teach') === '1';
  else state.teach = !(describe.brain.trained && state.kind !== 'baseline');
  $('teach').checked = state.teach;
  // a visitor's drag stays within the speed the brain was raised on
  stage.maxSpeed = describe.limits?.speed ?? 1.6;
  if (describe.manifest) state.manifest = describe.manifest;
  $('card-wheel').textContent = `cadence-net ${describe.cadence} (${state.manifest?.wheel_source || 'the pack’s wheel'})`;
  const facts = [['Brain', b.compose || b.label], ['Neurons', describe.neurons.toLocaleString('en')], ['Synapses', `${describe.synapses.toLocaleString('en')}, every one drawn`],
    ['Place answer', `${describe.place.bins} units an axis`], ['Records', `${describe.records.capacity} slots`], ['A moment', `${(DT * 1000).toFixed(0)} ms of the scene`],
    ['Runs in', `Pyodide ${describe.manifest?.pyodide || state.pyodide || ''}, ${brainView.mode === 'webgl2' ? 'WebGL2' : 'Canvas2D'}`]];
  if (describe.manifest) state.pyodide = describe.manifest.pyodide;
  $('card-facts').innerHTML = facts.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('');
}

async function start() {
  bindScene(); bindAround(); bindControls(); restartControls();
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

// A scripted scenario, for the page check: the brain as it arrives, the scene at its start, the
// camera's noise from a seed, and a route taken by scene steps. Every run gives the brain the
// same rows. Resolves with the page's record of its answers over the route.
async function scenario(route, { seed = 320, teach = null, sight = null, scene = 'default' } = {}) {
  await reborn({});
  if (teach !== null) { state.teach = teach; $('teach').checked = teach; }
  if (sight !== null) state.sight = !!sight;
  // the scene the route is taken in: the page's default, or its first scene, where the arm rests
  // with its end under the pillar's shadow and the two shadows join ('merged')
  const rest = stage.home.joints;
  if (scene === 'merged') stage.home.joints = MERGED_JOINTS.slice();
  while (state.pending) await new Promise((r) => setTimeout(r, 5));
  await brain.call('reset', {});
  while (state.pending) await new Promise((r) => setTimeout(r, 5));
  // from here to the route's first step nothing waits: the scene's rows are the seed's and the route's alone
  stage.reset(); stage.random = new Random(seed);
  setCase('other', false); restartControls();
  const from = stage.moment;
  stage.routeEnd = null;
  stage.route = route.map((leg) => ({ ...leg }));
  while (stage.route && stage.route.length) await new Promise((r) => setTimeout(r, 30));
  // the route's own moments, up to the one it ended at: a moment the clock adds after it is left out
  const last = stage.routeEnd ?? stage.moment;
  while (state.pending || !state.history.length || state.history.at(-1).moment < last) await new Promise((r) => setTimeout(r, 10));
  if (scene === 'merged') { stage.home.joints = rest; reset(); }
  return state.history.filter((r) => r.moment > from && r.moment <= last).map((r) => ({ m: r.moment - from, seen: r.seen, brain: r.brain, kalman: r.kalman, last: r.last, u: r.uncertainty, inside: r.inside, lesson: r.lesson, held: r.held, sight: r.sight, gone: r.gone }));
}

// what the page check drives
window.outOfSight = { sheetArea, scenario, stage, state, brainView, sceneView, aroundView, tour, card, askWhere, askWhat, awayPoint, awayHeading, playScene, playReach, loadScene: (data) => playScene(readScene(data)), knock, setCamera, reset, undo,
  setMore, openPart, openStage, closeCard, shadowPoint,
  /** Where a thing, the pillar or the camera is on the screen, in client pixels. */
  screenOf(name) {
    const box = $('scene').getBoundingClientRect();
    const p = name === 'camera' ? stage.geometry.camera.position : stage.where(name);
    const q = sceneView.toScreen(p);
    return [box.left + q[0], box.top + q[1]];
  },
  screenAt(p) { const box = $('scene').getBoundingClientRect(), q = sceneView.toScreen(p); return [box.left + q[0], box.top + q[1]]; },
  /** Whether the camera sees a point of the plane as the scene stands. */
  visibleAt: (p) => visible(stage.geometry, p, stage.world.joints),
  /** Where the small map draws a thing, or stands for a bearing at a share of its radius, in client pixels. */
  mapOf(name) { const box = $('around').getBoundingClientRect(), m = aroundView.marks.find((k) => k.name === name); return m ? [box.left + m.x, box.top + m.y] : null; },
  mapAt(bearing, share = 0.5) { const box = $('around').getBoundingClientRect(), d = aroundView.dial; return d ? [box.left + d.cx - Math.sin(bearing) * d.R * share, box.top + d.cy - Math.cos(bearing) * d.R * share] : null; },
  frameStats(last = 600) {
    const t = state.frameTimes.slice(-last).sort((a, b) => a - b), q = (f) => (t.length ? t[Math.min(t.length - 1, Math.floor(f * t.length))] : null);
    return { frames: t.length, median_ms: q(0.5), p95_ms: q(0.95), worst_ms: t.at(-1) ?? null };
  } };

start();
