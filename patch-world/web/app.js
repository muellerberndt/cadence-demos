// Patch World: the page. One worker runs the world (Python, the same code as the training runs),
// two to four run the creatures' Cadence brains. Each moment the page carries every creature's
// observation to the worker that holds its brain, the actions back to the world, and draws.

// Where the runtime pack lives: <meta name="cadence-pack" content="..."> if the host page sets one,
// else pack/ beside the page. Workers are told this absolute URL; they never derive it.
import { BrainView } from './brainview.js';

const PACK = new URL(document.querySelector('meta[name="cadence-pack"]')?.content || 'pack/', document.baseURI).href;
const ACTIONS = ['north', 'east', 'south', 'west', 'eat', 'drink'];
const DIRS = ['N', 'E', 'S', 'W'];
const KINDS6 = ['berry', 'root', 'leaf', 'water', 'predator', 'creature'];
const KIND_NAME = { live: 'learner', frozen: 'frozen twin', random: 'random walker' };
const CELL = 20;

const $ = (id) => document.getElementById(id);
const canvas = $('world');
const brainView = new BrainView($('brainview'), document.querySelector('.bv-wrap'));
const ctx = canvas.getContext('2d');

const state = {
  ready: false, running: true, speed: 10, tool: null, selected: null,
  width: 48, height: 32, terrain: null, food: null, snapshot: null, requests: [],
  prev: new Map(), cur: new Map(), tickAt: 0, tickMs: 100, assign: new Map(),
  details: new Map(), levels: [], particles: [], feed: [], loads: [], busy: false,
  lastTickWall: 0, moments: 0, msPerMoment: 0, manifest: null, terrainCanvas: null,
  terrainSummer: null, describe: null, inspect: null, lastInspect: 0, controls: [], modes: new Map(), heading: new Map(),
  snow: Array.from({ length: 140 }, (_, i) => ({ x: Math.random(), y: Math.random(), v: 0.4 + Math.random() * 0.6, p: i })),
  sickened: new Map(), remembered: new Map(), winterSince: null, coach: 0, coachOff: false,
};

// -------------------------------------------------------------------- workers

class Worker2 {
  constructor(role, index) {
    this.role = role; this.index = index; this.rid = 0; this.waiting = new Map();
    this.w = new Worker(new URL('worker.js', import.meta.url), { type: 'module' });
    this.w.onmessage = ({ data }) => {
      if (data.status) { if (role === 'world' || index === 0) setRuntime(data.status); return; }
      const p = this.waiting.get(data.rid); if (!p) return;
      this.waiting.delete(data.rid);
      if (data.error) p.reject(new Error(data.error)); else p.resolve(data.result);
    };
    this.w.onerror = (e) => fail(`A worker failed: ${e.message || e}`);
  }
  call(command, payload) {
    const rid = ++this.rid;
    return new Promise((resolve, reject) => { this.waiting.set(rid, { resolve, reject }); this.w.postMessage({ rid, command, payload }); });
  }
}

let world = null;
let brains = [];

function setRuntime(text, more = '') { $('runtime-text').textContent = text; $('runtime-more').textContent = more; }
function fail(message) {
  $('runtime-dot').className = 'error'; setRuntime('Stopped', message);
  $('loading').hidden = false; $('loading').classList.add('error'); $('loading-text').textContent = message;
  state.running = false;
}

async function boot() {
  const cores = navigator.hardwareConcurrency || 4;
  const nBrains = Math.max(2, Math.min(4, cores - 2));
  const seed = Math.floor(Math.random() * 1e6);
  world = new Worker2('world', 0);
  brains = Array.from({ length: nBrains }, (_, i) => new Worker2('brain', i));
  state.loads = brains.map(() => 0);
  try {
    const inits = await Promise.all([world.call('init', { role: 'world', seed, pack: PACK }),
      ...brains.map((b, i) => b.call('init', { role: 'brain', seed: seed + 101 * (i + 1), pack: PACK }))]);
    state.manifest = await (await fetch(new URL('manifest.json', PACK), { cache: 'no-cache' })).json();
    const opening = await world.call('opening', {});
    state.width = opening.width; state.height = opening.height;
    state.terrain = hexBytes(opening.terrain);
    buildTerrain();
    await placeBirths(opening.births);
    state.requests = opening.requests;
    applySnapshot(opening.snapshot, true);
    // the brain of a learner is open from the start; a click on any creature opens its brain instead
    const firstLearner = opening.snapshot.creatures.find((c) => c.kind === 'live');
    if (firstLearner) select(firstLearner.id, false);
    state.ready = true;
    $('loading').hidden = true;
    $('runtime-dot').className = 'ready';
    const ms = Math.max(...inits.map((r) => r.startup_ms));
    setRuntime(`Cadence ${state.manifest.cadence} in ${brains.length} brain workers`, ` · ready in ${(ms / 1000).toFixed(1)} s`);
    for (const id of ['play', 'flip', 'calm']) $(id).disabled = false;
    updateCoach();
    loop();
  } catch (error) { fail(error.message || String(error)); }
}

// births go to the brain worker of the parent when it is not much busier, else to the least loaded
async function placeBirths(births) {
  for (const b of births) {
    const min = Math.min(...state.loads);
    let target = state.loads.indexOf(min);
    const parentAt = b.parent != null ? state.assign.get(b.parent) : undefined;
    if (parentAt !== undefined && state.loads[parentAt] <= min + 2) target = parentAt;
    let payload = { births: [b] };
    if (parentAt !== undefined && parentAt !== target) {
      const exported = await brains[parentAt].call('export', { id: b.parent });
      payload.brains = { [b.id]: exported.brain };
    }
    await brains[target].call('born', payload);
    state.assign.set(b.id, target);
    state.loads[target] += b.kind === 'random' ? 0.2 : 1;
  }
}

async function removeDead(deaths) {
  const per = brains.map(() => []);
  for (const d of deaths) {
    const at = state.assign.get(d.id);
    if (at === undefined) continue;
    per[at].push(d.id); state.assign.delete(d.id);
    state.loads[at] -= d.kind === 'random' ? 0.2 : 1;
  }
  await Promise.all(per.map((ids, i) => (ids.length ? brains[i].call('died', { ids }) : null)));
}

// -------------------------------------------------------------------- the loop

async function tick() {
  const began = performance.now();
  const per = brains.map(() => []);
  for (const r of state.requests) {
    const at = state.assign.get(r.id);
    if (at !== undefined) per[at].push(r);
  }
  const detail = state.selected;
  const answers = await Promise.all(per.map((reqs, i) => brains[i].call('answer', { requests: reqs, detail })));
  const replies = {};
  for (const a of answers) Object.assign(replies, a.replies);
  const nowMs = performance.now();
  for (const [id, r] of Object.entries(replies)) {
    const prevMode = state.modes.get(Number(id));
    state.modes.set(Number(id), { mode: r.mode, level: r.level || 0, dopamine: r.dopamine, at: nowMs,
      dopaAt: r.dopamine !== undefined ? nowMs : (prevMode ? prevMode.dopaAt : -1e9),
      dopaV: r.dopamine !== undefined ? r.dopamine : (prevMode ? prevMode.dopaV : 0) });
    if (Number(id) === state.selected) {
      const c = state.cur.get(Number(id));
      brainView.push(r, { tickMs: state.tickMs, here: c ? { x: c.x, y: c.y } : null });
      state.details.set(Number(id), r);
      state.levels.push({ level: r.level || 0, mode: r.mode });
      if (state.levels.length > 160) state.levels.shift();
    }
    // the world only needs the action and the learning sweeps it charges for
    replies[id] = { action: r.action, learning_sweeps: r.learning_sweeps };
  }
  const res = await world.call('advance', { replies });
  await removeDead(res.deaths);
  await placeBirths(res.births);
  state.requests = res.requests;
  logChanges(res);
  applySnapshot(res.snapshot);
  state.moments += 1;
  const ms = performance.now() - began;
  state.msPerMoment = state.msPerMoment ? 0.9 * state.msPerMoment + 0.1 * ms : ms;
}

async function drainControls() {
  while (state.controls.length) {
    const { payload, resolve, reject } = state.controls.shift();
    try { const r = await world.call('control', payload); applySnapshot(r.snapshot); resolve(r); } catch (e) { reject(e); }
  }
}

async function loop() {
  while (true) {
    await drainControls();
    if (!state.running) { await sleep(60); continue; }
    const wait = 1000 / state.speed - (performance.now() - state.lastTickWall);
    if (wait > 0) await sleep(Math.min(wait, 200));
    if (!state.running) continue;
    state.busy = true;
    state.lastTickWall = performance.now();
    try { await tick(); } catch (error) { fail(error.message || String(error)); state.busy = false; return; }
    state.busy = false;
    const s = state.snapshot;
    if (s && s.t % 5 === 0) setRuntime(`Cadence ${state.manifest.cadence} in ${brains.length} brain workers`,
      ` · ${Math.round(state.msPerMoment)} ms a moment`);
    if (state.selected != null && performance.now() - state.lastInspect > 700) refreshInspector();
  }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function applySnapshot(s, first = false) {
  const wasSummer = state.snapshot ? state.snapshot.summer : s.summer;
  state.snapshot = s;
  state.food = hexBytes(s.food);
  state.prev = first ? new Map() : state.cur;
  state.cur = new Map(s.creatures.map((c) => [c.id, c]));
  for (const c of s.creatures) {
    const p = state.prev.get(c.id); if (!p) continue;
    let dx = c.x - p.x, dy = c.y - p.y;
    if (Math.abs(dx) > 2) dx = -Math.sign(dx); if (Math.abs(dy) > 2) dy = -Math.sign(dy);
    if (dx || dy) state.heading.set(c.id, Math.atan2(dy, dx));
  }
  state.tickMs = Math.max(30, Math.min(400, performance.now() - state.tickAt));
  state.tickAt = performance.now();
  if (wasSummer !== s.summer) { buildTerrain(); brainView.terrain = state.terrainCanvas; if (!s.summer) state.winterSince = s.t; }
  updateHud(); renderTally(); renderChart(); updateCoach();
  if (state.selected != null && !state.cur.has(state.selected)) {
    // the open brain's creature died. The brain the page opened by itself gives way, a moment
    // later, to another learner's; a creature the visitor chose stays, marked dead.
    const gone = state.selected;
    if (state.replacing !== gone) {
      state.replacing = gone;
      if (state.autoOpened) {
        $('insp-sub').textContent = 'This creature has died. Another learner’s brain opens.';
        setTimeout(() => {
          if (state.selected !== gone) return;
          const next = [...state.cur.values()].find((c) => c.kind === 'live');
          if (next) select(next.id, false);
        }, 1500);
      } else {
        $('insp-sub').textContent = 'This creature has died. Click another creature to watch its brain.';
      }
    }
  } else if (state.selected != null) updateInspectorLive();
}

// -------------------------------------------------------------------- events

function logChanges(res) {
  const t = state.snapshot ? state.snapshot.t : 0;
  for (const e of res.events) {
    const c = state.cur.get(e.id) || state.prev.get(e.id);
    if (c && (e.event !== 'passed' || e.kind === 'live')) state.particles.push({ x: c.x, y: c.y, kind: e.event, at: performance.now() });
    if (e.event === 'poisoned') { addFeed(t, 'poison', `${who(e.id, e.kind)} ate a winter berry and is sick`, e.id); state.sickened.set(e.id, (state.sickened.get(e.id) || 0) + 1); }
    if (e.event === 'passed' && e.kind === 'live' && state.snapshot && !state.snapshot.summer && state.sickened.get(e.id)
        && (state.remembered.get(e.id) || -1e9) < t - 150) {
      state.remembered.set(e.id, t);
      addFeed(t, 'birth', `${who(e.id, e.kind)}, poisoned ${state.sickened.get(e.id)}× before, walks past a berry`, e.id);
    }
  }
  for (const b of res.births) {
    if (b.kind === 'live' && b.parent != null) addFeed(t, 'birth', `${who(b.id, 'live')} born to ${who(b.parent, 'live')}${b.genes.recall ? ' (recall memory)' : ''}`, b.id);
    const c = state.cur.get(b.parent);
    if (c) state.particles.push({ x: c.x, y: c.y, kind: 'birth', at: performance.now() });
  }
  for (const d of res.deaths) addFeed(t, 'death', `${who(d.id, d.kind)} ${d.cause === 'starved' ? 'starved' : 'died of old age'} at age ${d.age.toLocaleString()}`, d.id);
}
const who = (id, kind) => `<span class="who" data-id="${id}">${KIND_NAME[kind] || kind} #${id}</span>`;
function addFeed(t, cls, html, id) {
  state.feed.unshift({ t, cls, html, id });
  if (state.feed.length > 60) state.feed.pop();
  const ol = $('feed');
  const li = document.createElement('li');
  li.innerHTML = `<time>${t}</time><span class="${cls}">${html}</span>`;
  ol.prepend(li);
  while (ol.children.length > 60) ol.lastChild.remove();
}
$('feed').addEventListener('click', (e) => { const el = e.target.closest('.who'); if (el) select(Number(el.dataset.id)); });

// -------------------------------------------------------------------- drawing the world

function hexBytes(hex) { const out = new Uint8Array(hex.length / 2); for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.substr(i * 2, 2), 16); return out; }
function rand(i) { const x = Math.sin(i * 12.9898) * 43758.5453; return x - Math.floor(x); }

function buildTerrain() {
  const W = state.width, H = state.height;
  const winter = state.snapshot ? !state.snapshot.summer : false;
  const c = document.createElement('canvas'); c.width = W * CELL; c.height = H * CELL;
  const g = c.getContext('2d');
  const pal = winter
    ? { 0: [62, 70, 82], 1: [40, 92, 140], 2: [48, 64, 62], 3: [74, 86, 96] }
    : { 0: [38, 46, 30], 1: [34, 96, 150], 2: [26, 52, 30], 3: [46, 78, 38] };
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const k = state.terrain[y * W + x];
    const [r, gg, b] = pal[k]; const n = (rand(y * W + x) - 0.5) * 14;
    g.fillStyle = `rgb(${r + n},${gg + n},${b + n})`;
    g.fillRect(x * CELL, y * CELL, CELL, CELL);
    if (k === 2) { // thicket texture
      g.fillStyle = winter ? 'rgba(200,215,230,0.10)' : 'rgba(10,30,12,0.45)';
      for (let j = 0; j < 3; j++) { g.beginPath(); g.arc(x * CELL + 4 + rand(x * 7 + y * 13 + j) * 12, y * CELL + 4 + rand(x * 11 + y * 3 + j) * 12, 4, 0, 7); g.fill(); }
    }
    if (k === 1) { g.fillStyle = 'rgba(180,220,255,0.10)'; g.fillRect(x * CELL + 3 + rand(x + y * 5) * 8, y * CELL + 6 + rand(x * 3 + y) * 8, 6, 1.5); }
  }
  if (winter) { g.fillStyle = 'rgba(255,255,255,0.75)'; for (let i = 0; i < W * H * 0.6; i++) g.fillRect(rand(i * 3.1) * W * CELL, rand(i * 7.7) * H * CELL, 1.4, 1.4); }
  state.terrainCanvas = c;
}

function draw(now) {
  requestAnimationFrame(draw);
  if (!state.terrainCanvas || !state.snapshot) return;
  const W = state.width, H = state.height, s = state.snapshot;
  ctx.drawImage(state.terrainCanvas, 0, 0);
  // food
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const f = state.food[y * W + x]; if (!f) continue;
    const cx = x * CELL + CELL / 2, cy = y * CELL + CELL / 2;
    if (f === 1) { ctx.fillStyle = '#ff4d6d'; for (const [dx, dy] of [[-3, -2], [3, -1], [0, 3]]) { ctx.beginPath(); ctx.arc(cx + dx, cy + dy, 2.6, 0, 7); ctx.fill(); } }
    else if (f === 2) { ctx.fillStyle = '#d2a36a'; ctx.fillRect(cx - 4, cy - 2.5, 8, 5); ctx.fillStyle = '#8a6438'; ctx.fillRect(cx - 1, cy + 2, 2, 4); }
    else if (f === 3) { ctx.fillStyle = '#82d96b'; ctx.beginPath(); ctx.moveTo(cx, cy - 5); ctx.lineTo(cx + 4, cy); ctx.lineTo(cx, cy + 5); ctx.lineTo(cx - 4, cy); ctx.fill(); }
  }
  // hidden caches (the creatures do not see them until they stand on one)
  ctx.setLineDash([3, 3]); ctx.lineWidth = 1.5;
  for (const [x, y, n] of s.caches) {
    ctx.strokeStyle = 'rgba(255,206,102,0.75)';
    ctx.beginPath(); ctx.arc(x * CELL + CELL / 2, y * CELL + CELL / 2, 8, 0, 7); ctx.stroke();
    ctx.fillStyle = '#ffce66';
    for (let i = 0; i < n; i++) { ctx.beginPath(); ctx.arc(x * CELL + 6 + i * 4, y * CELL + CELL / 2, 1.6, 0, 7); ctx.fill(); }
  }
  ctx.setLineDash([]);
  // day and night: the senses switch at dusk and dawn (s.light); the sky fades around them
  const dp = s.day_progress, edge = 0.06;
  let dark = s.light ? 0 : 1;
  if (dp > 0.5 - edge && dp < 0.5) dark = (dp - (0.5 - edge)) / edge;       // dusk
  else if (dp > 1 - edge) dark = 1 - (dp - (1 - edge)) / edge;              // dawn
  if (dark > 0) drawNight(dark, now);
  if (!s.summer) drawSnow(now);
  // creatures, moving between their last and present cells
  const k = Math.min(1, (now - state.tickAt) / state.tickMs);
  for (const c of state.cur.values()) {
    const p = state.prev.get(c.id) || c;
    let dx = c.x - p.x, dy = c.y - p.y;
    if (Math.abs(dx) > 2) dx = 0; if (Math.abs(dy) > 2) dy = 0; // wrapped round the torus
    const px = (p.x + dx * k) * CELL + CELL / 2, py = (p.y + dy * k) * CELL + CELL / 2;
    drawCreature(c, px, py, now);
  }
  for (const [x, y, resting] of s.predators) drawPredator(x * CELL + CELL / 2, y * CELL + CELL / 2, resting, now);
  // particles
  state.particles = state.particles.filter((q) => now - q.at < 1400);
  for (const q of state.particles) {
    const age = (now - q.at) / 1400, x = q.x * CELL + CELL / 2, y = q.y * CELL + CELL / 2 - age * 18;
    ctx.globalAlpha = 1 - age;
    ctx.font = '600 12px Inter, sans-serif'; ctx.textAlign = 'center';
    if (q.kind === 'poisoned') { ctx.fillStyle = '#b9f27a'; ctx.fillText('sick', x, y - 10); }
    else if (q.kind === 'berry') { ctx.fillStyle = '#ff8fa3'; ctx.fillText('+', x, y - 10); }
    else if (q.kind === 'passed') { if (s.summer) continue; ctx.fillStyle = '#c9f0ea'; ctx.fillText('no', x, y - 10); }
    else if (q.kind === 'nut') { ctx.fillStyle = '#ffce66'; ctx.fillText('nut!', x, y - 10); }
    else if (q.kind === 'bitten') { ctx.strokeStyle = '#ff5a4f'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y + age * 18, 10 + age * 10, 0, 7); ctx.stroke(); }
    else if (q.kind === 'birth') { ctx.strokeStyle = '#3fe0cf'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y + age * 18, 6 + age * 16, 0, 7); ctx.stroke(); }
    ctx.globalAlpha = 1;
  }
  ctx.globalAlpha = 1;
  // tool hover
  if (state.hover && state.tool) {
    ctx.strokeStyle = '#ffce66'; ctx.lineWidth = 1.5;
    ctx.strokeRect((state.hover.x - (state.tool === 'predator' ? 0 : 1)) * CELL, (state.hover.y - (state.tool === 'predator' ? 0 : 1)) * CELL,
      CELL * (state.tool === 'predator' ? 1 : 3), CELL * (state.tool === 'predator' ? 1 : 3));
  }
}

function drawNight(dark, now) {
  const W = state.width * CELL, H = state.height * CELL;
  if (!state.nightCanvas) { state.nightCanvas = document.createElement('canvas'); state.nightCanvas.width = W; state.nightCanvas.height = H; }
  const g = state.nightCanvas.getContext('2d');
  g.globalCompositeOperation = 'source-over'; g.clearRect(0, 0, W, H);
  g.fillStyle = `rgba(3,6,24,${0.62 * dark})`; g.fillRect(0, 0, W, H);
  g.globalCompositeOperation = 'destination-out';
  for (const c of state.cur.values()) {  // what a creature sees at night: half its sense range
    const rad = Math.max(1, Math.floor(c.sense / 2)) * CELL + CELL / 2;
    const grad = g.createRadialGradient(c.x * CELL + CELL / 2, c.y * CELL + CELL / 2, 0, c.x * CELL + CELL / 2, c.y * CELL + CELL / 2, rad);
    grad.addColorStop(0, `rgba(0,0,0,${0.55 * dark})`); grad.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = grad; g.fillRect(c.x * CELL - rad, c.y * CELL - rad, rad * 2 + CELL, rad * 2 + CELL);
  }
  ctx.drawImage(state.nightCanvas, 0, 0);
}

function drawSnow(now) {
  const W = state.width * CELL, H = state.height * CELL;
  ctx.fillStyle = 'rgba(235,242,255,0.75)';
  for (const f of state.snow) {
    const y = ((f.y + now / 26000 * f.v) % 1) * H, x = ((f.x + Math.sin(now / 1500 + f.p) * 0.004) % 1) * W;
    ctx.fillRect(x, y, 1.6 * f.v + 0.4, 1.6 * f.v + 0.4);
  }
}

function drawCreature(c, x, y, now) {
  const r = 6.5 * Math.sqrt(c.size);
  const m = state.modes.get(c.id);
  if (m && m.mode === 'aroused') {  // learning: its brain is aroused this moment
    const pulse = 0.55 + 0.25 * Math.sin(now / 140 + c.id);
    const halo = ctx.createRadialGradient(x, y, r * 0.6, x, y, r + 11);
    halo.addColorStop(0, `rgba(255,206,102,${0.55 * pulse})`); halo.addColorStop(1, 'rgba(255,206,102,0)');
    ctx.fillStyle = halo; ctx.beginPath(); ctx.arc(x, y, r + 11, 0, 7); ctx.fill();
  }
  if (m && now - m.dopaAt < 900) {  // the dopamine of its last lesson
    const k = (now - m.dopaAt) / 900;
    ctx.strokeStyle = m.dopaV >= 0 ? `rgba(255,206,102,${1 - k})` : `rgba(110,170,255,${1 - k})`;
    ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y, r + 4 + k * 12 * Math.min(1, 0.3 + Math.abs(m.dopaV)), 0, 7); ctx.stroke();
  }
  const color = c.kind === 'live' ? `hsl(${172 + ((c.lineage * 37) % 50) - 25},72%,58%)` : c.kind === 'frozen' ? '#9fb4ff' : '#ff9f4a';
  if (c.id === state.selected) { ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(x, y, r + 6 + Math.sin(now / 200) * 1.5, 0, 7); ctx.stroke(); }
  // energy ring
  const share = Math.max(0, Math.min(1, c.energy / c.capacity));
  ctx.strokeStyle = 'rgba(0,0,0,0.5)'; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.arc(x, y, r + 2.5, 0, 7); ctx.stroke();
  ctx.strokeStyle = share > 0.3 ? 'rgba(255,255,255,0.75)' : '#ff6b7f'; ctx.beginPath(); ctx.arc(x, y, r + 2.5, -Math.PI / 2, -Math.PI / 2 + share * 2 * Math.PI); ctx.stroke();
  ctx.fillStyle = c.sick > 0 ? '#9be25a' : color;
  ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill();
  // it faces the way it last walked
  const h = state.heading.get(c.id) || 0;
  const ex = Math.cos(h), ey = Math.sin(h), px = -ey, py = ex;
  for (const side of [-1, 1]) {
    const cx = x + ex * r * 0.45 + px * side * r * 0.38, cy = y + ey * r * 0.45 + py * side * r * 0.38;
    ctx.fillStyle = '#f4f7ff'; ctx.beginPath(); ctx.arc(cx, cy, r * 0.24, 0, 7); ctx.fill();
    ctx.fillStyle = '#0a0d18'; ctx.beginPath(); ctx.arc(cx + ex * r * 0.08, cy + ey * r * 0.08, r * 0.12, 0, 7); ctx.fill();
  }
  if (c.kind === 'frozen') {  // frozen twins: an ice-blue rim
    ctx.strokeStyle = 'rgba(230,240,255,0.95)'; ctx.lineWidth = 1.4; ctx.setLineDash([2, 2]);
    ctx.beginPath(); ctx.arc(x, y, r - 0.8, 0, 7); ctx.stroke(); ctx.setLineDash([]);
  } else if (c.kind === 'random') {
    ctx.fillStyle = '#ffd9b0'; ctx.font = '700 9px Inter, sans-serif'; ctx.textAlign = 'center'; ctx.fillText('?', x, y - r - 5);
  } else if (c.recall) {  // a recall memory: a gold spot at the back of the head
    const hb = state.heading.get(c.id) || 0;
    ctx.fillStyle = '#ffce66'; ctx.beginPath(); ctx.arc(x - Math.cos(hb) * r * 0.55, y - Math.sin(hb) * r * 0.55, r * 0.2, 0, 7); ctx.fill();
  }
}

function drawPredator(x, y, resting, now) {
  ctx.save(); ctx.translate(x, y);
  ctx.globalAlpha = resting ? 0.55 : 1;
  ctx.fillStyle = '#ff5a4f'; ctx.beginPath(); ctx.moveTo(0, -9); ctx.lineTo(8, 7); ctx.lineTo(-8, 7); ctx.closePath(); ctx.fill();
  ctx.fillStyle = '#1a0505'; ctx.beginPath(); ctx.arc(-2.5, 1, 1.4, 0, 7); ctx.arc(2.5, 1, 1.4, 0, 7); ctx.fill();
  if (!resting) { ctx.strokeStyle = 'rgba(255,90,79,0.25)'; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(0, 0, 14 + Math.sin(now / 160) * 2, 0, 7); ctx.stroke(); }
  ctx.restore();
}
requestAnimationFrame(draw);

// -------------------------------------------------------------------- panels

function updateHud() {
  const s = state.snapshot;
  $('season').classList.toggle('winter', !s.summer);
  $('season-text').textContent = s.summer ? 'summer: berries nourish' : 'winter: berries sicken';
  $('season-bar').style.width = `${Math.round(s.season_progress * 100)}%`;
  $('clock').textContent = `moment ${s.t.toLocaleString()}`;
  const air = s.temperature > 0.66 ? 'warm' : s.temperature > 0.33 ? 'cooling' : 'cold';
  const turning = (s.summer && s.temperature < 0.9) ? ' (warming)' : (!s.summer && air === 'warm') ? ' (summer air)' : '';
  $('daynight').textContent = `${s.light ? 'day' : 'night: senses reach half as far'} · air ${air}${turning}`;
}

function renderTally() {
  const s = state.snapshot, t = s.tally || {};
  const alive = { live: 0, frozen: 0, random: 0 };
  for (const c of s.creatures) alive[c.kind] = (alive[c.kind] || 0) + 1;
  const fmt = (v, d = 0) => (v === null || v === undefined ? '–' : Number(v).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }));
  $('tally').querySelector('tbody').innerHTML = ['live', 'frozen', 'random'].map((k) => {
    const r = t[k] || {};
    return `<tr class="${k}"><td>${KIND_NAME[k]}s</td><td>${alive[k]}</td><td><b>${fmt(r.income_per_moment, 3)}</b></td><td>${fmt(r.poisonings_per_1000, 1)}</td><td>${fmt(r.ended)}</td><td>${fmt(r.mean_age_at_death)}</td></tr>`;
  }).join('');
  const gens = s.creatures.filter((c) => c.kind === 'live').map((c) => c.generation);
  $('tally-foot').textContent = `Learners up to generation ${gens.length ? Math.max(...gens) : 0}${s.reseeded ? `; founders re-entered ${s.reseeded} times after the learners died out` : ''}. A dead frozen twin or random walker is replaced.`;
}

function renderChart() {
  const c = $('chart'), g = c.getContext('2d');
  const W = c.width, H = c.height, pad = { l: 34, r: 8, t: 10, b: 20 };
  g.clearRect(0, 0, W, H);
  const hist = state.snapshot.history || [];
  if (hist.length < 2) { g.fillStyle = '#5c6684'; g.font = '12px Inter, sans-serif'; g.fillText('The curve starts after 100 moments.', pad.l, H / 2); return; }
  const share = (h, kind) => {
    const e = (h.events || {})[kind] || {};
    const ate = (e.berry || 0) + (e.poisoned || 0), passed = e.passed || 0;
    return ate + passed >= 1 ? ate / (ate + passed) : null;
  };
  const rows = hist.map((h) => ({ t: h.t, summer: h.summer, live: share(h, 'live'), frozen: share(h, 'frozen') }));
  const x = (i) => pad.l + (i / (rows.length - 1)) * (W - pad.l - pad.r);
  const y = (v) => H - pad.b - v * (H - pad.t - pad.b);
  rows.forEach((r, i) => { if (!r.summer && i > 0) { g.fillStyle = 'rgba(191,227,255,0.09)'; g.fillRect(x(i - 1), pad.t, x(i) - x(i - 1) + 0.5, H - pad.t - pad.b); } });
  g.strokeStyle = '#1a2135'; g.lineWidth = 1;
  for (const v of [0, 0.5, 1]) { g.beginPath(); g.moveTo(pad.l, y(v)); g.lineTo(W - pad.r, y(v)); g.stroke(); g.fillStyle = '#5c6684'; g.font = '11px JetBrains Mono, monospace'; g.textAlign = 'right'; g.fillText(`${Math.round(v * 100)}%`, pad.l - 4, y(v) + 4); }
  for (const [key, color] of [['frozen', '#9fb4ff'], ['live', '#3fe0cf']]) {
    // a running mean over three windows keeps the line readable; gaps where nobody stood on a berry
    g.strokeStyle = color; g.lineWidth = 2; g.beginPath(); let on = false;
    rows.forEach((r, i) => {
      const vals = rows.slice(Math.max(0, i - 2), i + 1).map((q) => q[key]).filter((v) => v !== null);
      if (!vals.length) { on = false; return; }
      const v = vals.reduce((a, b) => a + b, 0) / vals.length;
      if (on) g.lineTo(x(i), y(v)); else g.moveTo(x(i), y(v)); on = true;
    });
    g.stroke();
  }
  for (const f of state.snapshot.flips || []) {
    const i = rows.findIndex((r) => r.t >= f); if (i < 0) continue;
    g.strokeStyle = '#ffce66'; g.setLineDash([3, 3]); g.beginPath(); g.moveTo(x(i), pad.t); g.lineTo(x(i), H - pad.b); g.stroke(); g.setLineDash([]);
  }
  g.font = '11px Inter, sans-serif'; g.textAlign = 'left';
  g.fillStyle = '#3fe0cf'; g.fillText('learners', pad.l + 4, H - 5); g.fillStyle = '#9fb4ff'; g.fillText('frozen twins', pad.l + 64, H - 5);
  g.fillStyle = '#ffce66'; g.fillText('┆ you flipped', pad.l + 146, H - 5);
  g.fillStyle = '#5c6684'; g.textAlign = 'right'; g.fillText(`last ${(rows.length * 50).toLocaleString()} moments`, W - pad.r, H - 5);
  renderEvo(hist);
}

const EVO = [['generation', 'generation', 1], ['lineages', 'lineages', 0], ['eta', 'actor step', 3], ['sense', 'sense range', 2], ['size', 'body size', 2], ['recall', 'recall share', 2]];
function renderEvo(hist) {
  const box = $('evo');
  if (!box.children.length) box.innerHTML = EVO.map(([k, label]) => `<div><span>${label}<b id="evo-${k}"></b></span><canvas id="evoc-${k}" width="160" height="30"></canvas></div>`).join('');
  const rows = hist.filter((h) => h.genes && Object.keys(h.genes).length);
  for (const [k, , d] of EVO) {
    const vals = rows.map((h) => h.genes[k]);
    $(`evo-${k}`).textContent = vals.length ? Number(vals[vals.length - 1]).toFixed(d) : '–';
    const cv = $(`evoc-${k}`), g = cv.getContext('2d'); g.clearRect(0, 0, cv.width, cv.height);
    if (vals.length < 2) continue;
    const lo = Math.min(...vals), hi = Math.max(...vals), span = hi - lo || 1;
    g.strokeStyle = '#3fe0cf'; g.lineWidth = 1.5; g.beginPath();
    vals.forEach((v, i) => { const x = (i / (vals.length - 1)) * cv.width, y = cv.height - 3 - ((v - lo) / span) * (cv.height - 6); i ? g.lineTo(x, y) : g.moveTo(x, y); });
    g.stroke();
  }
}

// -------------------------------------------------------------------- inspector

function select(id, byVisitor = true) {
  if (!state.cur.has(id)) return;
  state.selected = id; state.autoOpened = !byVisitor; state.levels = []; state.details.delete(id);
  $('inspector').hidden = false;
  const kind = state.cur.get(id).kind;
  brainView.setAnatomy(null, kind);
  brainView.terrain = state.terrainCanvas; brainView.world = { w: state.width, h: state.height };
  const at = state.assign.get(id);
  if (at !== undefined && kind !== 'random') brains[at].call('anatomy', { id }).then((r) => { if (state.selected === id) brainView.setAnatomy(r.anatomy, kind); });
  refreshInspector();
  updateInspectorLive();
  if (!byVisitor) return;
  $('inspector').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  if (state.coach === 3) setCoach(4);
}
$('insp-close').onclick = () => { state.selected = null; $('inspector').hidden = true; };

async function refreshInspector() {
  state.lastInspect = performance.now();
  const id = state.selected; if (id == null) return;
  const at = state.assign.get(id);
  const [info, desc] = await Promise.all([world.call('inspect', { id }), at !== undefined ? brains[at].call('describe', { id }) : null]);
  if (state.selected !== id) return;
  state.inspect = info; state.describe = desc;
  renderInspectorStatic();
}

function renderInspectorStatic() {
  const info = state.inspect; if (!info || info.gone) return;
  const g = info.genes, d = state.describe;
  $('insp-title').textContent = `${KIND_NAME[info.kind]} #${info.id}`;
  const lineage = info.kind === 'live' ? `lineage ${info.lineage}, generation ${info.generation}${info.parent ? `, child of #${info.parent}` : ''}` : info.kind === 'frozen' ? 'a founder’s brain that never learns' : 'no brain: a uniform draw over six actions';
  $('insp-sub').textContent = `${lineage} · age ${info.age?.toLocaleString() ?? '–'} · ${info.children} children`;
  const rows = info.kind === 'random' ? [['body', `sense ${g.sense}, speed ${g.speed}, size ${(+g.size).toFixed(2)}`]] : [
    ['anatomy', `${g.depth === 1 ? `one region of ${g.width}` : `${g.width} → ${Math.max(8, Math.floor(g.width / 2))}`}${g.recall ? ', recall memory' : ''}`],
    ['actor step', (+g.eta).toPrecision(2)], ['critic step', (+g.eta_critic).toPrecision(2)],
    ['temperature', (+g.temperature).toFixed(2)], ['arousal threshold', (+g.threshold).toFixed(2)],
    ['need', (+g.need).toFixed(3)], ['store rate', (+g.memory_rate).toFixed(2)],
    ['body', `sense ${g.sense}, speed ${g.speed}, size ${(+g.size).toFixed(2)}`],
    ['bears young at', `${Math.round(g.birth * 100)}% full`],
  ];
  $('genes').innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('');
  $('brain-size').textContent = d && d.neurons ? `${d.neurons} neurons, ${d.synapses.toLocaleString()} synapses${d.arousal ? ` · ${(d.arousal.modes.aroused || 0).toLocaleString()} aroused, ${(d.arousal.modes.routine || 0).toLocaleString()} calm moments` : ''}` : '';
  const st = info.stats || {};
  const poison = info.poison_times || [];
  $('story').innerHTML = info.kind === 'random' ? '' :
    `Ate <b>${st.berry_summer || 0}</b> good berries, <b>${st.root || 0}</b> roots, <b>${st.leaf || 0}</b> leaves, <b>${st.nut || 0}</b> nuts from hidden caches; drank <b>${st.drink || 0}</b> times; bitten <b>${st.bitten || 0}</b> times. ` +
    `Poisoned <b>${st.poisoned || 0}</b> times${poison.length ? ` (at ages ${poison.slice(-6).join(', ')})` : ''}; stood on a berry and walked on <b>${st.refused_berry || 0}</b> times.`;
}

function updateInspectorLive() {
  const id = state.selected, c = state.cur.get(id); if (!c) return;
  $('bar-energy').style.width = `${Math.max(0, Math.min(100, (100 * c.energy) / c.capacity))}%`;
  $('val-energy').textContent = c.energy.toFixed(1);
  $('bar-thirst').style.width = `${Math.round(c.thirst * 100)}%`;
  $('val-thirst').textContent = c.thirst.toFixed(2);
  const r = state.details.get(id);
  const level = r ? r.level || 0 : 0;
  $('bar-level').style.width = `${Math.min(100, level * 100)}%`;
  $('val-level').textContent = level.toFixed(2);
  const mode = r ? r.mode : '–';
  const chip = $('mode-chip'); chip.className = `chip ${mode}`;
  chip.textContent = mode === 'aroused' ? 'aroused: learning' : mode === 'routine' ? 'calm: answering, not learning' : mode === 'frozen' ? 'frozen: never learns' : mode;
  $('settle-line').textContent = r && r.settle ? `settled in ${r.settle.steps} sweeps, residual ${r.settle.residual.toExponential(1)}; did: ${ACTIONS[r.action]}` : r ? `did: ${ACTIONS[r.action]}` : '';
  drawSpark();
}

function drawSpark() {
  const cv = $('arousal-spark'), g = cv.getContext('2d'), W = cv.width, H = cv.height;
  g.clearRect(0, 0, W, H);
  const L = state.levels; if (L.length < 2) return;
  const max = Math.max(0.4, ...L.map((l) => l.level));
  L.forEach((l, i) => { if (l.mode === 'aroused') { g.fillStyle = 'rgba(255,206,102,0.12)'; g.fillRect((i / 160) * W, 0, W / 160 + 0.5, H); } });
  g.strokeStyle = '#ffce66'; g.lineWidth = 1.6; g.beginPath();
  L.forEach((l, i) => { const x = (i / 160) * W, y = H - 4 - (l.level / max) * (H - 8); i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.stroke();
  g.fillStyle = '#5c6684'; g.font = '10px Inter, sans-serif'; g.fillText('arousal level, last 160 moments (shaded: aroused)', 4, 11);
}

// -------------------------------------------------------------------- controls

$('play').onclick = () => { state.running = !state.running; $('play').textContent = state.running ? 'Pause' : 'Play'; };
document.querySelectorAll('[data-speed]').forEach((b) => b.onclick = () => {
  state.speed = Number(b.dataset.speed);
  document.querySelectorAll('[data-speed]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
});
document.querySelectorAll('[data-tool]').forEach((b) => b.onclick = () => {
  state.tool = state.tool === b.dataset.tool ? null : b.dataset.tool;
  document.querySelectorAll('[data-tool]').forEach((x) => x.setAttribute('aria-pressed', String(x.dataset.tool === state.tool)));
  canvas.classList.toggle('tool', !!state.tool);
  $('tool-hint').hidden = !state.tool;
  $('tool-hint').textContent = state.tool === 'predator' ? 'Click the map to add a predator (up to four)' : `Click the map to drop ${state.tool === 'berry' ? 'berries' : 'roots'} on a 3 x 3 patch`;
});
// the visitor's changes to the world wait for the moment in progress, then apply at once
function control(payload) {
  if (!state.ready) return Promise.resolve();
  return new Promise((resolve, reject) => state.controls.push({ payload, resolve, reject }));
}
$('flip').onclick = async () => {
  await control({ action: 'flip' });
  const s = state.snapshot;
  addFeed(s.t, 'flip', `The season turned: ${s.summer ? 'summer, berries nourish again' : 'winter, berries sicken'}`);
};
$('calm').onclick = () => control({ action: 'calm' });
function cellAt(e) {
  const rect = canvas.getBoundingClientRect();
  return { x: Math.floor(((e.clientX - rect.left) / rect.width) * state.width), y: Math.floor(((e.clientY - rect.top) / rect.height) * state.height) };
}
canvas.addEventListener('mousemove', (e) => { state.hover = cellAt(e); });
canvas.addEventListener('mouseleave', () => { state.hover = null; });
canvas.addEventListener('click', (e) => {
  const { x, y } = cellAt(e);
  if (state.tool === 'predator') { control({ action: 'predator', x, y }); return; }
  if (state.tool) { control({ action: 'food', kind: state.tool, x, y, radius: 1 }); return; }
  let best = null, bd = 2.5;
  for (const c of state.cur.values()) { const d = Math.hypot(c.x - x - 0.0, c.y - y); if (d < bd) { bd = d; best = c; } }
  if (best) select(best.id);
});

// -------------------------------------------------------------------- the hints
// Three steps walk a first visit through the page's promise: flip the season, watch the chart,
// open a learner's brain. The x hides them.

const COACH = {
  1: ['1 / 3', 'Press <em>Flip the season</em>. Winter makes every berry poisonous, and nothing the creatures sense says so.'],
  2: ['2 / 3', 'Watch <em>Berries eaten when standing on one</em>: within a few hundred moments the learners’ teal line falls, the frozen twins’ blue line stays up. <em>Fast</em> gets there sooner.'],
  3: ['3 / 3', 'Click a teal learner to watch its brain at the right. It glows gold while a surprise has it learning.'],
  4: ['done', 'Flip again for summer: the learners come back to the berries slowly. Point at a <em>?</em> or open <em>Help</em> for more.'],
};
function setCoach(step) {
  if (state.coachOff || state.coach === step) return;
  state.coach = step;
  const box = $('coach');
  box.hidden = false;
  box.classList.toggle('done', step === 4);
  $('coach-step').textContent = COACH[step][0];
  $('coach-text').innerHTML = COACH[step][1];
  $('flip').classList.toggle('pulse', step === 1);
  $('chart-panel').classList.toggle('pulse', step === 2);
}
function updateCoach() {
  if (!state.ready || state.coachOff) return;
  const s = state.snapshot;
  if (state.coach < 1) setCoach(1);
  if (state.coach === 1 && state.winterSince !== null) setCoach(2);
  if (state.coach === 2 && s && s.t >= state.winterSince + 350) setCoach(3);
}
$('coach-skip').onclick = () => {
  state.coachOff = true; $('coach').hidden = true;
  $('flip').classList.remove('pulse');
  $('chart-panel').classList.remove('pulse');
};

window.patchWorld = state; // read by check_page.py
state.brainView = brainView;
boot();
