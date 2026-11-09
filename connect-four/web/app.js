// The page: the game, the controls and the readouts. Every move of the brain, every activation
// drawn and every lesson comes from the Cadence brain running in the worker.
import { Board } from './board.js';
import { BrainView } from './brain.js';

const $ = (id) => document.getElementById(id);
// Where the runtime pack lives: <meta name="cadence-pack" content="..."> if the host page sets one,
// else pack/ beside this page. Passed to the worker as an absolute URL.
const PACK = new URL(document.querySelector('meta[name="cadence-pack"]')?.content || 'pack/', document.baseURI).href;
const fmt = (n) => Number(n).toLocaleString('en-US');
const pct = (v) => `${(100 * v).toFixed(1)}%`;

const app = {
  ready: false, phase: 'loading', error: null,
  moves: [], game: null, empty: null, first: 'you', nextFirst: 'you',
  brain: null, manifest: null, startup: null,
  turn: 0, thinkRid: null, lastBrain: null, imagined: null, player: 'search',
  timings: [], lessons: 0, lastLesson: null, settle: null, lastFinal: null,
  settles: [], // every brain move of this game: its board, settle and readout, for undo
};
let worker, requestId = 0;
const pending = new Map();

// -- the worker

function request(command, payload = {}, onProgress = null) {
  const rid = ++requestId;
  if (command === 'think') app.thinkRid = rid;
  return new Promise((resolve, reject) => {
    pending.set(rid, { resolve, reject, onProgress });
    worker.postMessage({ rid, command, payload });
  });
}

function cancelThink() {
  if (app.thinkRid && pending.has(app.thinkRid)) worker.postMessage({ command: 'cancel', target: app.thinkRid });
  app.thinkRid = null;
}

// -- views

const board = new Board({
  board: $('board'), motor: $('motor'), ghosts: $('ghosts'),
  onColumn: (c) => (['teach', 'taught'].includes(app.phase) ? guard(teachColumn)(c) : guard(humanMove)(c)),
});
const view = new BrainView({
  canvas: $('brain-gl'), overlay: $('brain-overlay'), tooltip: $('tooltip'),
  onFrame: (f) => onSettleFrame(f),
  renderer: new URLSearchParams(location.search).get('render') || 'auto', // 'webgl' or '2d' to force one
});

const brainPlayer = () => (app.first === 'brain' ? 0 : 1);
const owners = (game) => game.cells.map((v) => (v === 0 ? 0 : (v - 1 === brainPlayer() ? 'brain' : 'you')));
const newCell = (before, after) => after.cells.findIndex((v, k) => v !== 0 && before.cells[k] === 0);

function setStatus(html, cls = '') {
  const s = $('status');
  s.innerHTML = html; s.className = `status ${cls}`;
}

function refresh() {
  const p = app.phase, g = app.game;
  const human = p === 'human';
  const teachable = p === 'teach' || p === 'taught';
  board.setPlayable(teachable ? app.teachLegal : g?.legal, human || teachable, teachable ? 'teach' : 'play');
  $('new-game').disabled = !app.ready;
  document.querySelectorAll('[data-first]').forEach((b) => { b.disabled = !app.ready; b.setAttribute('aria-pressed', String(b.dataset.first === app.nextFirst)); });
  document.querySelectorAll('[data-player]').forEach((b) => { b.disabled = !app.ready; b.setAttribute('aria-pressed', String(b.dataset.player === app.player)); });
  $('undo').disabled = !(app.ready && (human || p === 'over') && canUndo());
  const teaching = ['teach', 'teaching', 'taught'].includes(p);
  $('teach').disabled = !(app.ready && (((human || p === 'over') && app.lastBrain) || p === 'teach' || p === 'taught'));
  $('teach').classList.toggle('active', teaching);
  $('teach').textContent = p === 'teach' ? 'Cancel' : p === 'taught' || p === 'teaching' ? 'Done' : 'Teach it';
  $('reset-brain').hidden = !app.lessons;
  $('lessons-note').textContent = app.lessons ? `taught ${app.lessons}× in this tab` : '';
  if (p === 'human') {
    const last = app.lastBrain && app.moves.length && (app.moves.length - 1) % 2 === brainPlayer() ? app.moves.at(-1) : null;
    setStatus(last === null ? 'Your move. Tap a column.' : `It played <span class="c-brain">column ${last + 1}</span>. Your move.`);
  } else if (p === 'thinking') setStatus('The brain is settling…');
  else if (p === 'over') {
    if (g.winner === null) setStatus('The board is full. A draw.');
    else if (g.winner === brainPlayer()) setStatus('Four in a row. The brain wins.', 'loss');
    else setStatus('Four in a row. You win.', 'win');
  }
}

function canUndo() {
  const human = 1 - brainPlayer();
  return app.moves.some((_, ply) => ply % 2 === human);
}

// -- the game

async function newGame() {
  if (!app.ready) return;
  cancelThink();
  endTeachView();
  app.turn++;
  app.first = app.nextFirst;
  app.moves = []; app.game = app.empty; app.lastBrain = null; app.imagined = null; app.lastFinal = null; app.settles = [];
  board.set(owners(app.game)); board.setMarks(); board.setMotor(null); board.setGhosts(null); setVerdict(null); setSearch(null);
  view.rest(); view.setChosen(null); setReadout('at rest');
  drawSpark([]);
  if (app.first === 'brain') return brainTurn();
  app.phase = 'human'; refresh();
}

async function humanMove(column) {
  if (app.phase !== 'human' || !app.game.legal[column]) return;
  const token = app.turn;
  app.phase = 'dropping'; refresh();
  const before = app.game;
  const { reply } = await request('position', { moves: [...app.moves, column] });
  if (token !== app.turn) return;
  app.moves = reply.game.moves; app.game = reply.game;
  const cell = newCell(before, app.game);
  board.setGhosts(null);
  await board.set(owners(app.game), { animate: cell, last: cell, line: app.game.line });
  if (token !== app.turn) return;
  if (app.game.over) return finish();
  return brainTurn();
}

async function brainTurn() {
  const token = app.turn;
  app.phase = 'thinking'; refresh();
  const movesBefore = app.moves.slice(), before = app.game;
  try {
    if ($('imagine-toggle').checked) {
      const imagined = await request('imagine', { moves: movesBefore });
      if (token !== app.turn) return;
      app.imagined = imagined.reply;
      board.setGhosts(imagined.reply.candidates, owners(before));
    } else {
      app.imagined = null;
      board.setGhosts(null);
    }
    view.setChosen(null);
    view.beginSettle();
    app.settle = { sweeps: 0, movement: [] };
    const { reply: final } = await request('think', { moves: movesBefore, search: app.player === 'search' }, (progress, arrays) => {
      if (token !== app.turn) return;
      view.pushFrames(arrays.frames, progress.movement);
      app.settle.movement.push(...progress.movement);
    });
    if (final.cancelled || token !== app.turn) return;
    view.endSettle(final);
    await view.finished();
    if (token !== app.turn) return;
    app.lastFinal = final;
    app.timings.push({ ms: final.ms, wall_ms: final.wall_ms, sweeps: final.sweeps, column: final.column, legal: final.legal[final.column],
      brain_column: final.brain_column, search_ms: final.search ? final.search.ms : null, search_depth: final.search ? final.search.depth : null });
    view.setChosen(final.column);
    board.setMotor(final.motor, { chosen: final.column, legal: final.legal });
    setVerdict(final.verdict);
    setReadout(final.settled ? `settled in ${final.sweeps} sweeps · ${final.ms.toFixed(0)} ms` : `stopped at ${final.sweeps} sweeps · ${final.ms.toFixed(0)} ms`, final.settled ? 'settled' : 'settling');
    setSearch(final);
    drawSpark(app.settle.movement, final.sweeps);
    app.moves = final.after.moves; app.game = final.after;
    const cell = newCell(before, app.game);
    app.lastBrain = { moves: movesBefore, column: final.column, motor: final.motor, legal: final.legal, cell,
      activation: Float32Array.from(view.display), sweeps: final.sweeps, ms: final.ms, settled: final.settled, movement: app.settle.movement.slice() };
    app.settles.push(app.lastBrain);
    await board.set(owners(app.game), { animate: cell, last: cell, line: app.game.line });
    if (token !== app.turn) return;
    if (app.game.over) return finish();
    app.phase = 'human'; refresh();
  } catch (error) {
    if (token !== app.turn) return;
    view.show(view.display); // stop the playback where it is
    app.phase = 'human'; refresh();
    fail(error);
  }
}

function finish() {
  app.phase = 'over';
  board.setGhosts(null);
  refresh();
}

async function undo() {
  if (!['human', 'over'].includes(app.phase) || !canUndo()) return;
  const human = 1 - brainPlayer();
  const moves = app.moves.slice();
  while (moves.length) { const ply = moves.length - 1; moves.pop(); if (ply % 2 === human) break; }
  app.turn++;
  const token = app.turn;
  const { reply } = await request('position', { moves });
  if (token !== app.turn) return;
  app.moves = reply.game.moves; app.game = reply.game;
  app.imagined = null;
  app.settles = app.settles.filter((e) => e.moves.length < app.moves.length);
  app.lastBrain = app.settles.at(-1) || null;
  const last = app.lastBrain;
  board.set(owners(app.game), { line: app.game.line, last: last?.cell ?? null }); board.setMarks(); board.setGhosts(null);
  if (last) {
    view.show(last.activation); view.setChosen(last.column);
    board.setMotor(last.motor, { chosen: last.column, legal: last.legal });
    setReadout(`settled in ${last.sweeps} sweeps · ${last.ms.toFixed(0)} ms`, last.settled ? 'settled' : 'settling');
    drawSpark(last.movement, last.sweeps);
  } else {
    board.setMotor(null); view.rest(); view.setChosen(null); setReadout('at rest'); drawSpark([]);
  }
  app.phase = 'human'; refresh();
}

// -- teaching: one lesson on the position of the brain's last move

async function startTeach() {
  if (!app.lastBrain || !['human', 'over'].includes(app.phase)) return;
  const { reply } = await request('position', { moves: app.lastBrain.moves });
  app.teachGame = reply.game;
  app.teachLegal = reply.game.legal.map((ok, c) => ok && c !== app.lastBrain.column);
  app.phase = 'teach';
  board.set(owners(reply.game), {}); board.setMarks({ ghostCell: app.lastBrain.cell });
  board.setMotor(app.lastBrain.motor, { chosen: app.lastBrain.column, legal: app.lastBrain.legal });
  board.setGhosts(null);
  refresh();
  setStatus(`It played <b>column ${app.lastBrain.column + 1}</b> here. Tap the column it should have played.`, 'teach');
}

async function teachColumn(column) {
  if (!['teach', 'taught'].includes(app.phase) || !app.teachLegal?.[column]) return;
  app.phase = 'teaching'; refresh();
  setStatus('One lesson, in your browser…', 'teach');
  const token = app.turn;
  const { reply, arrays } = await request('lesson', { moves: app.lastBrain.moves, column });
  if (token !== app.turn) return;
  app.lastLesson = reply;
  let message;
  if (reply.refused) {
    message = `The lesson was refused: ${reply.refused}`;
  } else if (!reply.accepted) {
    message = `No lesson needed: it already answers column ${column + 1} on this board.`;
  } else {
    app.lessons = reply.lessons;
    view.setWeights(arrays.weight, arrays.bias);
    view.flash(arrays.changed, arrays.delta);
    board.setMarks({ ghostCell: app.lastBrain.cell, taught: landing(app.teachGame, column) });
    // the same board, settled again under the changed synapses
    view.beginSettle();
    const { reply: final } = await request('think', { moves: app.lastBrain.moves }, (progress, a) => {
      if (token === app.turn) view.pushFrames(a.frames, progress.movement);
    });
    if (token !== app.turn || final.cancelled) return;
    view.endSettle(final);
    await view.finished();
    if (token !== app.turn) return;
    view.setChosen(final.column);
    board.setMotor(final.motor, { chosen: final.column, legal: final.legal, before: reply.before });
    setReadout(`settled again in ${final.sweeps} sweeps · ${final.ms.toFixed(0)} ms`, 'settled');
    const b = reply.before[column], a = final.motor[column];
    const now = final.column === column ? `It would now play <b>column ${column + 1}</b> here.` : `It would still play column ${final.column + 1} here.`;
    message = `One lesson changed <b>${fmt(reply.changed)}</b> synapses. Column ${column + 1}’s motor neuron: ${b.toFixed(3)} → <b>${a.toFixed(3)}</b>. ${now} Tap again to repeat the lesson.`;
  }
  app.phase = 'taught'; refresh();
  setStatus(message, 'teach');
}

function landing(game, column) {
  for (let r = 0; r < 6; r++) if (!game.cells[r * 7 + column]) return r * 7 + column;
  return null;
}

function endTeachView() {
  board.setMarks();
}

function finishTeach() {
  if (!['teach', 'taught'].includes(app.phase)) return;
  const taught = app.phase === 'taught';
  endTeachView();
  board.set(owners(app.game), { line: app.game.line, last: app.lastBrain?.cell ?? null });
  if (app.lastBrain && !taught) board.setMotor(app.lastBrain.motor, { chosen: app.lastBrain.column, legal: app.lastBrain.legal });
  app.phase = app.game.over ? 'over' : 'human';
  refresh();
}

async function resetBrain() {
  if (!app.ready || ['thinking', 'teaching'].includes(app.phase)) return;
  const { reply, arrays } = await request('reset_brain');
  app.brain = reply.brain; app.lessons = 0; app.lastLesson = null;
  view.setWeights(arrays.weight, arrays.bias);
  if (app.lastBrain) view.show(app.lastBrain.activation);
  renderCard();
  refresh();
}

// -- readouts

// What the search did with the brain's proposal.
function setSearch(final) {
  const el = $('search-note'), s = final?.search;
  if (!s) { el.hidden = true; return; }
  const brain = final.brain_column + 1, played = final.column + 1;
  if (s.immediate) {
    el.innerHTML = `<b>Search</b> column ${played} wins now${final.column === final.brain_column ? '' : ` (the brain preferred column ${brain})`}`;
    el.hidden = false;
    return;
  }
  const why = s.reason === 'win' ? `found a forced win: column ${played}`
    : final.column === final.brain_column ? `kept the brain's column ${brain}`
    : `overruled the brain's column ${brain}: column ${played}`;
  el.innerHTML = `<b>Search</b> ${why} · ${s.depth} moves ahead · ${(s.nodes || 0).toLocaleString()} positions · ${Math.round(s.ms)} ms`;
  el.hidden = false;
}

// The verdict slot: the brain's judgement of the position it moved from, for itself.
function setVerdict(v) {
  const el = $('verdict');
  if (!v) { el.hidden = true; return; }
  const [loss, draw, win] = v;
  const word = win >= draw && win >= loss ? 'it is winning' : loss >= draw ? 'it is losing' : 'a draw';
  el.innerHTML = `<span>Its verdict before this move: <b>${word}</b></span><span class="bar" title="loss ${pct(loss)} · draw ${pct(draw)} · win ${pct(win)}"><i class="loss" style="width:${100 * loss}%"></i><i class="draw" style="width:${100 * draw}%"></i><i class="win" style="width:${100 * win}%"></i></span><span>win ${pct(win)}</span>`;
  el.hidden = false;
}

function setReadout(text, cls = '') {
  $('settle-text').textContent = text;
  $('settle-text').parentElement.className = `readout ${cls}`;
}

function onSettleFrame(f) {
  board.setMotor(f.motor, { legal: app.phase === 'thinking' ? app.game?.legal : null });
  const sweep = Math.floor(f.sweep);
  const m = f.movement.at(-1);
  if (f.playing) setReadout(sweep < 1 ? 'from rest' : `sweep ${sweep} · Δ ${m !== undefined ? m.toFixed(4) : '…'}`, 'settling');
  drawSpark(f.movement, f.sweeps);
}

function drawSpark(movement, total = null) {
  const canvas = $('spark'), dpr = Math.min(2, window.devicePixelRatio || 1);
  const w = 112, h = 26;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const c = canvas.getContext('2d');
  c.setTransform(dpr, 0, 0, dpr, 0, 0);
  c.clearRect(0, 0, w, h);
  const tol = app.brain?.tolerance ?? 0.003;
  const y = (v) => { const l = Math.log10(Math.max(1e-5, v)); return 2 + (h - 4) * (0 - l) / 4; };
  c.strokeStyle = 'rgba(255,206,102,0.45)'; c.setLineDash([2, 2]); c.lineWidth = 1;
  c.beginPath(); c.moveTo(0, y(tol)); c.lineTo(w, y(tol)); c.stroke(); c.setLineDash([]);
  if (!movement.length) return;
  const span = Math.max(total || 0, movement.length, 24);
  c.strokeStyle = 'rgba(63,224,207,0.95)'; c.lineWidth = 1.4;
  c.beginPath();
  movement.forEach((v, i) => { const x = (i + 0.5) * w / span; if (i) c.lineTo(x, y(v)); else c.moveTo(x, y(v)); });
  c.stroke();
}

// The readings of the packed brain itself (the receipt's "readings"), else the last training reading.
function measured(t, pending) {
  const r = t.readings, last = (t.curve || []).at(-1);
  const held = r?.heldout || last;
  if (!held) return `<p>Held-out readings: ${pending}.</p>`;
  const lines = [`<p>On ${fmt(held.positions || 3000)} held-out positions from solver games, never taught: the solver’s optimal move <b>${pct(held.optimal)}</b> of the time; a move that keeps the theoretical result where it is not already lost <b>${pct(held.keep_not_lost)}</b>; an immediate win taken <b>${pct(held.wins_now)}</b>; a forced block made <b>${pct(held.blocks)}</b>${held.verdict !== undefined ? `; the verdict agrees with the solver’s result <b>${pct(held.verdict)}</b>` : ''}.</p>`];
  for (const g of r?.games || []) {
    lines.push(`<p>${g.games} games from the empty board, ${g.policy_first ? 'the brain first, against the perfect solver' : `the solver first${g.strength < 1 ? `, playing its best move ${Math.round(100 * g.strength)}% of the time` : ''}`}: <b>${g.win} won, ${g.draw} drawn, ${g.loss} lost</b>.</p>`);
  }
  return lines.join('');
}

function renderCard() {
  const m = app.manifest, b = app.brain;
  if (!m || !b) return;
  const t = m.training || {}, curve = t.curve || [], last = curve.at(-1);
  const pops = b.populations.map((p) => `${p.name} ${fmt(p.size)}`).join(' · ');
  const blocks = b.blocks.map((x) => `${x.pre}→${x.post} ${fmt(x.synapses)}`).join(' · ');
  const args = t.args || {};
  const games = t.games || [];
  const latestGames = last ? games.filter((g) => g.lesson === Math.max(...games.map((x) => x.lesson))) : games;
  const gameLine = (g) => `${g.games} games against the solver${g.strength < 1 ? ` playing ${Math.round(100 * (1 - g.strength))}% random moves` : ''} (lesson ${fmt(g.lesson)}): ${g.win} won, ${g.draw} drawn, ${g.loss} lost; ${pct(g.blunder_free_games)} of games without a blunder.`;
  const heldN = last ? Object.values(last.phases || {}).reduce((s, p) => s + p.n, 0) : 0;
  const phaseLine = last ? Object.entries(last.phases || {}).map(([name, p]) => `${name.split(' (')[0]} ${pct(p.optimal)}`).join(' · ') : '';
  const times = app.timings.map((x) => x.ms).sort((a, b) => a - b);
  const median = times.length ? times[Math.floor(times.length / 2)] : null;
  const pending = '<span class="pending">pending: the receipt has no reading yet</span>';
  $('card-summary').textContent = `${fmt(b.neurons)} neurons · ${fmt(b.synapses)} synapses · ${last ? `${fmt(last.lesson)} lessons · held-out optimal ${pct(last.optimal)}` : 'training receipt pending'} · cadence-net ${m.cadence} · GPL-3.0`;
  $('card-body').innerHTML = `
    <section>
      <h3>The brain</h3>
      <dl>
        <dt>Built by</dt><dd>${b.compose}</dd>
        <dt>Neurons</dt><dd>${fmt(b.neurons)} (${pops})</dd>
        <dt>Synapses</dt><dd>${fmt(b.synapses)}</dd>
      </dl>
      <p>${blocks}. The page draws ${fmt(b.drawn)} of them: every synapse of the active pathways${b.blocks.some((x) => x.sampled) ? ', and the strongest eight into each neuron where a block is larger than 150,000' : ''}.</p>
      <p>Senses: ${fmt(b.sensory.length)} neurons, the 42 cells of its own stones, the 42 of yours${b.planes === 3 ? ', and the 42 cells where a stone would land' : ''}. Acts: 7 column neurons, one per column; the strongest one whose column has room is the move.${b.verdict ? ' Three more motor neurons hold its verdict on the position for the side to move (loss, draw, win), taught beside the move; the move does not read them.' : ''} Each move settles from rest without memory (a position is fully observed), until no activation moves by ${b.tolerance} in a sweep (at most ${fmt(b.free_steps)} sweeps). The prefrontal region, the target of Cadence’s working trace, is silent here.</p>
    </section>
    <section>
      <h3>How it learned</h3>
      <p>Taught offline by a perfect Connect Four solver (Pascal Pons’ solver). ${(t.lineage || []).length ? `In ${t.lineage.length} stages, ${fmt(t.lineage.reduce((n, st) => n + st.lessons, 0))} lessons in all: ${t.lineage.map((st) => `${st.lessons.toLocaleString()} lessons ${st.what}`).join('; then ')}.` : ''}</p>
      <p>${args.batch ? `Each lesson showed ${args.batch} positions` : 'Each lesson showed a batch of positions'}: positions from games of the solver against itself, with deliberate mistakes and short random openings, each also mirrored, a quarter of each batch with a win to take or a win to block, an eighth finished boards seen by the loser (verdict: loss), and the brain’s own games against the solver, where each move that slipped is shown four more times.</p>
      <dl><dt>Lessons in the last stage</dt><dd>${last ? fmt(last.lesson) : pending}</dd><dt>Refused</dt><dd>${t.refused ?? '—'}</dd></dl>
    </section>
    <section>
      <h3>Measured play</h3>
      ${measured(t, pending)}
    </section>
    <section>
      <h3>In this tab</h3>
      <dl>
        <dt>Startup</dt><dd>${app.startup ? `${fmt(app.startup)} ms (Python, NumPy, Cadence, brain)` : '—'}</dd>
        <dt>Settle per move</dt><dd>${median !== null ? `median ${median.toFixed(1)} ms, max ${times.at(-1).toFixed(1)} ms over ${times.length} moves` : 'no move yet'}</dd>
        <dt>Drawing</dt><dd>${view.mode === 'webgl2' ? 'WebGL2' : 'Canvas2D fallback'}</dd>
        <dt>Lessons here</dt><dd>${app.lessons} (kept until reload or Reset brain)</dd>
      </dl>
    </section>
    <section>
      <h3>Provenance</h3>
      <dl>
        <dt>Library</dt><dd>cadence-net ${m.cadence}, ${m.wheel_source}</dd>
        <dt>Runtime</dt><dd>Pyodide ${m.pyodide}, in a Web Worker</dd>
        <dt>Packed</dt><dd>${m.packed}</dd>
      </dl>
      <p class="hash">wheel sha256 ${m.wheel_sha256}<br>brain sha256 ${m.brain_sha256} (${(m.brain_bytes / 1e6).toFixed(1)} MB)</p>
      <p>The worker checks these hashes before it runs anything. Training receipt: <a href="${PACK}receipt.json" target="_blank" rel="noreferrer">pack/receipt.json</a>.</p>
    </section>
    <section>
      <h3>Licence and limits</h3>
      <p>Cadence and this example are GPL-3.0; source at <a href="${m.source}" target="_blank" rel="noreferrer">github.com/muellerberndt/cadence</a>.</p>
      <p><b>Brain alone</b> plays from one settle per move: no search, no opening book, no memory of earlier moves. <b>Brain + search</b> settles the brain the same way and then looks ahead over the game’s rules (connect4/search.py): a proven win is played; columns proven lost are dropped; among the rest the brain’s strongest column is played unless the search scores another clearly higher. The search reads threats at its horizon, not the brain, and it does not know the solver’s scores. The imagined replies are not used for the move. Neither is a perfect player; the measured rates are above. A settled state certifies the settle’s equations, not the move’s quality.</p>
    </section>`;
}

function fail(error) {
  app.error = error?.message || String(error);
  console.error(error);
  setStatus(`Something went wrong: ${app.error}`);
}

// A visitor's action that fails leaves the game playable and says what went wrong.
const guard = (action) => (...args) => action(...args).catch((error) => {
  if (['dropping', 'teaching', 'teach', 'taught'].includes(app.phase)) {
    endTeachView();
    if (app.game) board.set(owners(app.game), { line: app.game.line });
    app.phase = app.game?.over ? 'over' : 'human';
    refresh();
  }
  fail(error);
});

// -- start

async function boot() {
  worker = new Worker(new URL('./worker.js', import.meta.url), { type: 'module' });
  worker.onmessage = ({ data }) => {
    if (data.status) { $('runtime-text').textContent = data.status; setStatus(data.status); return; }
    const task = pending.get(data.rid);
    if (!task) return;
    if (data.progress) { task.onProgress?.(data.progress, data.arrays || {}); return; }
    pending.delete(data.rid);
    if (data.error) task.reject(new Error(data.error));
    else task.resolve({ reply: data.result, arrays: data.arrays || {} });
  };
  worker.onerror = (event) => { for (const task of pending.values()) task.reject(new Error(event.message || 'The Python worker could not start.')); pending.clear(); };
  try {
    const { reply, arrays } = await request('init', { pack: PACK });
    app.brain = reply.brain; app.manifest = reply.manifest; app.startup = reply.startup_ms;
    app.empty = reply.game; app.game = reply.game;
    view.setBrain(reply.brain, arrays);
    $('brain-size').textContent = `${fmt(reply.brain.neurons)} neurons · ${fmt(reply.brain.synapses)} synapses`;
    $('runtime-text').textContent = `Cadence ${reply.brain.cadence}`;
    $('runtime-more').textContent = ' · Python in your tab';
    $('runtime-dot').className = 'ready';
    app.ready = true;
    renderCard();
    await newGame();
  } catch (error) {
    $('runtime-dot').className = 'error';
    $('runtime-text').textContent = 'The brain could not load';
    fail(error);
  }
}

$('new-game').addEventListener('click', guard(newGame));
document.querySelectorAll('[data-first]').forEach((b) => b.addEventListener('click', () => { app.nextFirst = b.dataset.first; guard(newGame)(); }));
document.querySelectorAll('[data-player]').forEach((b) => b.addEventListener('click', () => { app.player = b.dataset.player; refresh(); }));
$('undo').addEventListener('click', guard(undo));
$('teach').addEventListener('click', () => (app.phase === 'teach' || app.phase === 'taught' ? finishTeach() : guard(startTeach)()));
$('reset-brain').addEventListener('click', guard(resetBrain));
$('ghost-info').addEventListener('click', () => {
  const open = $('ghost-note').hidden;
  $('ghost-note').hidden = !open; $('ghost-info').setAttribute('aria-expanded', String(open));
});
$('model-card').addEventListener('toggle', () => { if ($('model-card').open) renderCard(); });
document.addEventListener('keydown', (e) => {
  if (e.target.closest?.('input, textarea, select')) return;
  const n = Number(e.key);
  if (n >= 1 && n <= 7) { e.preventDefault(); guard(['teach', 'taught'].includes(app.phase) ? teachColumn : humanMove)(n - 1); }
});

window.c4 = {
  state: () => ({
    ready: app.ready, phase: app.phase, error: app.error, moves: app.moves.slice(), game: app.game,
    first: app.first, brainPlayer: brainPlayer(), timings: app.timings.slice(), lessons: app.lessons,
    lastLesson: app.lastLesson, imagined: app.imagined, lastFinal: app.lastFinal, startup: app.startup, player: app.player,
    view: view.stats(), brain: app.brain && { neurons: app.brain.neurons, synapses: app.brain.synapses, cadence: app.brain.cadence },
  }),
  request: (command, payload) => request(command, payload).then((r) => r.reply),
  view,
};
boot();
