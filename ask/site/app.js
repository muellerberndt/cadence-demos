// Ask the parrot: the page. The room, the parrot, the questions, the namings, the pistachios and
// the tutorial run here; the brain runs in worker.js (Python in Pyodide, the Cadence wheel of the
// pack) and answers every request with its own calls. The page holds the world (where each thing
// stands, which way the parrot faces) and no part of the brain.
import { KIND_WORDS, COLOUR_WORDS, PLACE_WORDS, NAMED, RADIUS, PERCH, firstRoom, newRoom, clampPlace, frame, drawRoom, drawRetina, drawThing, truth, wrap, inView } from './room.js';
import { BrainView } from './brain.js';
import { canListen, listen, RATE } from './ears.js';

const params = new URLSearchParams(location.search);
const $ = (id) => document.getElementById(id);
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// -- the brain, in a worker

const packMeta = document.querySelector('meta[name="cadence-pack"]');
const PACK = new URL(packMeta?.content || 'pack/', location.href).href;
const worker = new Worker(new URL('worker.js', import.meta.url), { type: 'module' });
let rid = 0;
const pending = new Map();
worker.onmessage = ({ data }) => {
  if (data.status) { status(data.status + '…'); return; }
  const p = pending.get(data.rid);
  if (!p) return;
  pending.delete(data.rid);
  if (data.error) p.reject(new Error(data.error)); else p.resolve({ reply: data.result, arrays: data.arrays || {} });
};
worker.onerror = (e) => status('The brain could not start: ' + (e.message || 'a worker error'), 'error');
function send(command, payload) {
  return new Promise((resolve, reject) => { const id = ++rid; pending.set(id, { resolve, reject }); worker.postMessage({ rid: id, command, payload }); });
}

// -- the state of the page

const S = {
  things: firstRoom(), heading: 0, pose: { heading: 0, body: 0, tilt: 0, blink: 0, bob: 0, beakOpen: 0, fluff: 0 },
  held: [], words: [], info: null, ready: false, busy: false,
  last: null, // the latest answer: {question, said, story}
  rewarded: false, teach: null, hover: null, focus: null, askPlace: null, nut: null,
  taught: new Map(), // word -> namings on the page
  turned: 0, // radians turned since the tutorial step began
};

const room = $('room'), rctx = room.getContext('2d');
const retina = $('retina'), ectx = retina.getContext('2d');
const brain = new BrainView($('brain-stage'), $('brain'), onStage);

function status(text, kind = '') {
  $('runtime-text').innerHTML = text;
  $('runtime-dot').className = kind;
}

// -- drawing the room and the eyes, every frame

let roomSize = 400, roomFrame = frame(400);
function sizeRoom() {
  const wrapBox = $('room-wrap').getBoundingClientRect();
  const size = Math.max(160, Math.floor(Math.min(wrapBox.width, wrapBox.height - 4)));
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  room.width = Math.round(size * dpr); room.height = Math.round(size * dpr);
  room.style.width = size + 'px'; room.style.height = size + 'px';
  rctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  roomSize = size; roomFrame = frame(size);
  const rb = retina.getBoundingClientRect();
  retina.width = Math.round(rb.width * dpr); retina.height = Math.round(rb.height * dpr);
  ectx.setTransform(dpr, 0, 0, dpr, 0, 0);
}
new ResizeObserver(() => { sizeRoom(); placeBubble(); }).observe($('room-wrap'));

let blinkAt = performance.now() + 2500;
function frameLoop(now) {
  // the head turns first, the body follows; a blink from time to time; a small tilt while it waits
  const p = S.pose;
  p.heading += wrap(S.heading - p.heading) * 0.22;
  p.body += wrap(p.heading - p.body) * 0.08;
  p.tilt = Math.sin(now / 900) * 0.06 + (S.busy ? Math.sin(now / 140) * 0.05 : 0);
  if (now > blinkAt) { p.blink = 1; if (now > blinkAt + 130) { p.blink = 0; blinkAt = now + 2200 + Math.random() * 3500; } }
  p.bob = brain.speaking ? Math.abs(Math.sin(now / 90)) : p.bob * 0.85;
  p.beakOpen = brain.speaking ? Math.abs(Math.sin(now / 70)) : 0;
  if (S.nut) { S.nut.t = Math.min(1, (now - S.nut.began) / 1500); if (S.nut.t >= 1) S.nut = null; }
  p.fluff = S.nut && S.nut.t > 0.45 ? Math.sin(((S.nut.t - 0.45) / 0.55) * Math.PI) * (0.6 + 0.4 * Math.abs(Math.sin(now / 60))) : p.fluff * 0.9;
  drawRoom(rctx, roomSize, { things: S.things, heading: S.heading, pose: p, held: S.held, focus: S.focus, ask: { place: S.askPlace }, teach: S.teach, hover: S.hover, nut: S.nut });
  const rb = retina.getBoundingClientRect();
  drawRetina(ectx, rb.width, rb.height, S.things, p.heading);
  requestAnimationFrame(frameLoop);
}

// the speech bubble sits by the parrot's head
function placeBubble() {
  const b = $('bubble');
  const wrapBox = $('room-wrap').getBoundingClientRect(), box = room.getBoundingClientRect();
  const [px, py] = roomFrame.toPx(0, 0);
  b.style.left = Math.round(box.left - wrapBox.left + px + roomFrame.scale * 0.32) + 'px';
  b.style.bottom = Math.round(wrapBox.bottom - (box.top + py) + roomFrame.scale * 0.22) + 'px';
}
function bubble(html) {
  const b = $('bubble');
  if (html == null) { b.hidden = true; return; }
  b.innerHTML = html; b.hidden = false; placeBubble();
}

// -- the brain's replies

function apply({ reply, arrays }) {
  if (reply.things) S.held = reply.things;
  if (reply.words) S.words = reply.words;
  brain.update(reply, arrays);
}

let momentBusy = false, momentDirty = false;
async function moment() {
  if (!S.ready) return;
  if (momentBusy) { momentDirty = true; return; }
  momentBusy = true;
  try {
    do {
      momentDirty = false;
      apply(await send('moment', scene()));
    } while (momentDirty);
  } catch (e) { console.warn(e); } finally { momentBusy = false; }
}
const scene = () => ({ things: S.things.map((t) => [t.kind, t.colour, t.x, t.y]), heading: S.heading });

// -- asking

async function ask(text) {
  text = String(text || '').trim();
  if (!S.ready || S.busy || !text) return;
  S.busy = true; setBusy();
  closeTeach();
  $('question').value = '';
  show('chips');
  logLine(`<b>You:</b> ${esc(text)}`);
  bubble('<span class="none">…</span>');
  try {
    while (momentBusy) await new Promise((r) => setTimeout(r, 30));
    const out = await send('ask', { question: text });
    apply(out);
    const story = out.reply;
    S.last = { question: text, said: story.said, story };
    S.rewarded = false;
    S.askPlace = story.about && story.about[0] === 'place' ? story.about[1] : null;
    S.focus = story.places.map((p) => nearestThing(p)).filter((id) => id != null);
    brain.playStory(story);
    await brain.finished();
    const said = story.said.filter((w) => w);
    bubble(said.length ? said.map(esc).join(', ') : '<span class="none">(it has no word to say)</span>');
    logLine(`<b>Parrot:</b> <span class="said">${esc(said.join(', ') || '…')}</span>`);
    show('reward'); $('nut').disabled = false; $('tell').value = '';
    tour.event({ type: 'ask', story, question: text });
  } catch (e) {
    bubble(null); logLine(`<span class="none">${esc(e.message)}</span>`);
  } finally { S.busy = false; setBusy(); }
}

function nearestThing(p) {
  let best = null, d = 0.35;
  for (const t of S.things) { const e = Math.hypot(t.x - p[0], t.y - p[1]); if (e < d) { d = e; best = t.id; } }
  return best;
}

async function pistachio() {
  if (!S.ready || S.busy || !S.last || S.rewarded) return;
  S.busy = true; setBusy();
  S.rewarded = true; $('nut').disabled = true;
  const box = room.getBoundingClientRect(), nb = $('nut').getBoundingClientRect();
  S.nut = { began: performance.now(), t: 0, from: [Math.max(10, nb.left + nb.width / 2 - box.left), Math.min(roomSize - 10, nb.top - box.top)] };
  try {
    const out = await send('pistachio', {});
    apply(out);
    brain.lesson(out.reply.changed, out.reply.how === 'reward' ? 'dopamine' : 'lesson', out.reply.dopamine);
    const n = out.reply.changed.length;
    logLine(out.reply.how === 'reward'
      ? `<span class="nutted">A pistachio for “${esc(S.last.said.join(', '))}”: it cracks it. Surprise ${out.reply.dopamine.toFixed(2)}: ${n} synapse${n === 1 ? '' : 's'} change.</span>`
      : `<span class="nutted">A pistachio for “${esc(S.last.said.join(', '))}”: it cracks it, and takes its answer as right.</span>`);
    bubble('<span class="none">crack!</span>');
    setTimeout(() => { if (!S.busy) bubble(null); }, 1600);
    show('chips');
    tour.event({ type: 'pistachio' });
  } catch (e) { logLine(esc(e.message)); } finally { S.busy = false; setBusy(); }
}

async function tell(text) {
  text = String(text || '').trim().toLowerCase();
  if (!S.ready || S.busy || !S.last || !text) return;
  S.busy = true; setBusy();
  try {
    const out = await send('tell', { answer: text });
    apply(out);
    if (out.reply.refused) { logLine(esc(out.reply.refused)); return; }
    brain.lesson(out.reply.changed, 'lesson');
    logLine(`<b>You told it:</b> <span class="taught">${esc(text)}</span>`);
    $('tell').value = '';
    show('chips');
    tour.event({ type: 'tell' });
  } catch (e) { logLine(esc(e.message)); } finally { S.busy = false; setBusy(); }
}

// -- naming

function openTeach(id) {
  if (!S.ready) return;
  const t = S.things.find((x) => x.id === id);
  if (!t) return;
  S.teach = id;
  show('teach'); $('teach').hidden = false;
  const c = $('teach-thing'), g = c.getContext('2d');
  g.clearRect(0, 0, c.width, c.height);
  drawThing(g, t.kind, t.colour, c.width / 2, c.height / 2, c.width * 0.36);
  $('teach-count').textContent = '';
  $('teach-word').value = '';
  setTimeout(() => $('teach-word').focus(), 0);
  // the parrot turns to look at what is shown to it
  S.heading = Math.atan2(t.y, t.x);
  moment();
  tour.event({ type: 'teach-open', kind: t.kind });
}
function closeTeach() { S.teach = null; $('teach').hidden = true; show('chips'); }

// one slot under the question box: the questions to try, the pistachio row, or the naming panel
function show(which) {
  $('chips').hidden = which !== 'chips';
  $('reward').hidden = which !== 'reward';
  if (which !== 'teach') $('teach').hidden = true;
  if (which === 'chips') fitChips();
}

async function name(word) {
  word = String(word || '').trim().toLowerCase().replace(/\s+/g, ' ');
  const t = S.things.find((x) => x.id === S.teach);
  if (!t || !S.ready || S.busy) return;
  if (!/^[a-z']{1,16}$/.test(word)) { $('teach-count').textContent = 'one word, letters only'; return; }
  S.busy = true; setBusy();
  try {
    while (momentBusy) await new Promise((r) => setTimeout(r, 30));
    S.heading = Math.atan2(t.y, t.x);
    apply(await send('moment', scene()));
    const out = await send('name', { word, at: [t.x, t.y] });
    apply(out);
    if (out.reply.error == null) { $('teach-count').textContent = 'it cannot see it there'; return; }
    S.taught.set(word, (S.taught.get(word) || 0) + 1);
    const n = out.reply.lessons;
    $('teach-count').textContent = `heard ${S.taught.get(word)}×`;
    brain.named(out.reply.unit, out.reply.changed);
    logLine(`<b>You:</b> <span class="taught">${esc(word)}</span> <span>(naming ${S.taught.get(word)})</span>`);
    bubble(`<span class="none">${S.taught.get(word) >= 3 ? 'hmm… ' + esc(word) + '!' : '…' + esc(word) + '?'}</span>`);
    if (S.taught.get(word) >= 3) makeChips();
    tour.event({ type: 'name', word, kind: t.kind, count: S.taught.get(word), lessons: n });
  } catch (e) { logLine(esc(e.message)); } finally { S.busy = false; setBusy(); }
}

// -- questions to try, made from the room

function makeChips() {
  const known = (w) => S.words.includes(w);
  const named = S.things.filter((t) => known(KIND_WORDS[t.kind]));
  const out = [];
  const ball = named.find((t) => t.kind === 0) || named[0];
  if (ball) out.push(`where is the ${KIND_WORDS[ball.kind]}?`);
  const other = named.find((t) => t !== ball) || ball;
  if (other) out.push(`what colour is the ${KIND_WORDS[other.kind]}?`);
  const red = S.things.find((t) => t.colour === 0) || S.things[0];
  if (red) out.push(`what is ${COLOUR_WORDS[red.colour]}?`);
  out.push('what is behind you?');
  for (const [w, n] of S.taught) if (n >= 3 && !KIND_WORDS.slice(0, NAMED).includes(w)) out.push(`where is the ${w}?`);
  $('chips').innerHTML = out.slice(0, 6).map((q) => `<button type="button" data-q="${esc(q)}">${esc(q)}</button>`).join('');
  setBusy();
  tour.light();
}
// the questions to try keep to one line: those that would wrap are left out
function fitChips() {
  const list = [...$('chips').querySelectorAll('button')];
  list.forEach((b) => { b.hidden = false; });
  const top = list.length ? list[0].offsetTop : 0;
  list.forEach((b) => { if (b.offsetTop > top + 2) b.hidden = true; });
}
window.addEventListener('resize', () => fitChips());
$('chips').addEventListener('click', (e) => { const b = e.target.closest('button[data-q]'); if (b) ask(b.dataset.q); });

function setBusy() {
  const off = !S.ready || S.busy;
  $('question').disabled = !S.ready; $('send').disabled = off;
  for (const b of $('chips').querySelectorAll('button')) b.disabled = off;
  $('teach-say').disabled = off; $('new-room').disabled = off; $('reset').disabled = off;
  $('nut').disabled = off || S.rewarded || !S.last;
}

function logLine(html) {
  const li = document.createElement('li'); li.innerHTML = html;
  const log = $('log'); log.appendChild(li);
  while (log.children.length > 3) log.removeChild(log.firstChild);
}

// -- the brain view's steps, in words

const READ_WORDS = { kind: 'what it is', colour: 'its colour', place: 'where it is' };
function onStage(step, story, progress) {
  const el = $('stage');
  if (!step) { el.textContent = ''; return; }
  const said = story.spoken[step.index];
  const about = story.about;
  const reads = Object.entries(story.hear.reads || {}).sort((a, b) => b[1] - a[1]);
  const text = {
    hear: '<span>1 · Hearing:</span> the words drive their neurons; the concepts settle',
    choose: about ? `<span>2 · Understood:</span> about one concept (teal), asking for ${READ_WORDS[reads[0]?.[0]] || 'something'} (gold)` : '<span>2 · Understood:</span> no concept it knows',
    map: '<span>3 · The map:</span> it settles on the things the question names',
    say: '<span>4 · Saying:</span> what it found drives the word neurons',
    motor: said && said.word ? `<span>5 · The motor says</span> “${esc(said.word)}”` : '<span>5 · The motor:</span> no word for it',
  }[step.kind];
  el.innerHTML = text;
  if (step.kind === 'motor' && said && said.word) {
    const before = story.spoken.slice(0, step.index).map((s) => s.word).filter((w) => w);
    const letters = said.word.slice(0, Math.max(1, Math.round(progress * said.word.length)));
    bubble([...before.map(esc), esc(letters)].join(', '));
  }
}

// -- the room by the pointer

let drag = null;
function roomPoint(ev) {
  const r = room.getBoundingClientRect();
  return roomFrame.toRoom(ev.clientX - r.left, ev.clientY - r.top);
}
function thingAt(x, y) {
  let best = null, d = RADIUS * 1.45;
  for (const t of S.things) { const e = Math.hypot(t.x - x, t.y - y); if (e < d) { d = e; best = t; } }
  return best;
}
room.addEventListener('pointerdown', (ev) => {
  if (!S.ready) return;
  const [x, y] = roomPoint(ev);
  const t = thingAt(x, y);
  room.setPointerCapture(ev.pointerId);
  if (t) drag = { kind: 'thing', id: t.id, x0: ev.clientX, y0: ev.clientY, moved: false };
  else if (Math.hypot(x, y) > PERCH * 0.6) { drag = { kind: 'turn', last: Math.atan2(y, x) }; turnTo(Math.atan2(y, x)); }
  room.classList.add('dragging');
});
room.addEventListener('pointermove', (ev) => {
  const [x, y] = roomPoint(ev);
  if (!drag) { const t = thingAt(x, y); S.hover = t ? t.id : null; room.classList.toggle('on-thing', !!t); return; }
  if (drag.kind === 'thing') {
    if (!drag.moved && Math.hypot(ev.clientX - drag.x0, ev.clientY - drag.y0) < 5) return;
    drag.moved = true;
    if (!$('reward').hidden) show('chips');
    const t = S.things.find((q) => q.id === drag.id);
    [t.x, t.y] = clampPlace(x, y);
    moment();
  } else if (drag.kind === 'turn' && Math.hypot(x, y) > 0.15) turnTo(Math.atan2(y, x));
});
function endDrag(ev) {
  if (!drag) return;
  if (drag.kind === 'thing' && !drag.moved) openTeach(drag.id);
  else if (drag.kind === 'thing') { moment(); tour.event({ type: 'moved' }); }
  drag = null; room.classList.remove('dragging');
}
room.addEventListener('pointerup', endDrag);
room.addEventListener('pointercancel', endDrag);
room.addEventListener('pointerleave', () => { if (!drag) S.hover = null; });
room.addEventListener('keydown', (ev) => {
  if (ev.key === 'ArrowLeft') { turnTo(S.heading + Math.PI / 12); ev.preventDefault(); }
  if (ev.key === 'ArrowRight') { turnTo(S.heading - Math.PI / 12); ev.preventDefault(); }
});
function turnTo(h) {
  if (!$('reward').hidden) show('chips'); // the room changed: the offer of a pistachio passes
  S.turned += Math.abs(wrap(h - S.heading));
  S.heading = wrap(h);
  moment();
  tour.event({ type: 'turn' });
}

$('ask').addEventListener('submit', (e) => { e.preventDefault(); ask($('question').value); });
$('teach-form').addEventListener('submit', (e) => { e.preventDefault(); name($('teach-word').value); });
$('teach-done').addEventListener('click', () => closeTeach());
$('nut').addEventListener('click', () => pistachio());
$('more').addEventListener('click', () => show('chips'));
$('tell-form').addEventListener('submit', (e) => { e.preventDefault(); tell($('tell').value); });
$('new-room').addEventListener('click', () => startRoom(newRoom()));
$('reset').addEventListener('click', async () => {
  if (S.busy) return;
  S.busy = true; setBusy();
  try { apply(await send('reset', {})); S.taught.clear(); } finally { S.busy = false; }
  await startRoom(firstRoom(), 0);
  $('log').innerHTML = '';
});
$('tour').addEventListener('click', () => tour.start());

// the ears: open only where the pack's brain has them (manifest.ears); the raw sound goes to the
// brain's host, with no recogniser in between (cadence#329)
let hearing = null;
$('mic').addEventListener('click', async () => {
  if (!S.ready || S.busy) return;
  if (hearing) { hearing.stop(); return; }
  try {
    hearing = await listen({ most: 6000 });
    $('mic').classList.add('on');
    const samples = await hearing.samples;
    hearing = null; $('mic').classList.remove('on');
    S.busy = true; setBusy();
    const out = await send('hear', { samples: Array.from(samples), rate: RATE });
    if (out.reply.refused) logLine(esc(out.reply.refused));
  } catch (e) { hearing = null; $('mic').classList.remove('on'); logLine(esc(e.message)); } finally { S.busy = false; setBusy(); }
});

async function startRoom(things, heading = S.heading) {
  S.busy = true; setBusy(); closeTeach(); bubble(null); brain.clearStory();
  S.things = things; S.heading = heading; S.focus = null; S.askPlace = null; S.last = null; show('chips');
  try { apply(await send('room', scene())); } finally { S.busy = false; }
  makeChips();
}

// -- the tutorial: six steps the visitor performs

const tour = {
  step: -1,
  steps: [
    { text: 'Ask the parrot <b>where is the ball?</b> Click the question below, or type it.', chip: 'where is the ball?', done: (e) => e.type === 'ask' && e.story.about && e.story.about[0] === 'kind' && e.story.said.some((w) => PLACE_WORDS.includes(w)) },
    { text: 'It answered from what its brain holds, in a word it learned by being shown things. Right? <b>Give it a pistachio.</b>', nut: true, done: (e) => e.type === 'pistachio' },
    { text: 'The green wash was its surprise, its dopamine: the words that asked learned a little. Ask it the other way round: <b>what is red?</b>', chip: 'what is red?', done: (e) => e.type === 'ask' && e.story.about && e.story.about[0] === 'colour' },
    { text: 'Turn the parrot: <b>drag across the floor</b> (or press ← →). Then ask <b>what is behind you?</b> It cannot see behind itself: it answers from its map.', chip: 'what is behind you?', done: (e) => e.type === 'ask' && e.story.about && e.story.about[0] === 'place' && S.turned > 0.4 },
    { text: 'The parrot has no word for some things in the room. <b>Click the yellow kettle</b>, type a name for it and press <b>Say it</b>, three times.', done: (e) => e.type === 'name' && e.kind >= NAMED && e.count >= 3 },
    { text: () => `Ask about it: <b>where is the ${esc(tour.word || 'kettle')}?</b>`, chip: () => `where is the ${tour.word || 'kettle'}?`, done: (e) => e.type === 'ask' && tour.word && e.question.toLowerCase().includes(tour.word) && e.story.said.some((w) => PLACE_WORDS.includes(w)) },
  ],
  word: null,
  start() {
    this.step = 0; S.turned = 0; this.show();
    try { localStorage.setItem('ask-parrot-tour', 'seen'); } catch (e) { /* storage blocked */ }
  },
  stop(text) {
    this.step = -1;
    $('coach-text').innerHTML = text || 'Ask it anything in its words, drag things, turn it, teach it words and reward right answers. <a href="help.html" target="_blank" rel="noopener">Help</a> explains every part.';
    $('coach-skip').hidden = true; this.dots(); this.light();
  },
  show() {
    const s = this.steps[this.step];
    $('coach-text').innerHTML = typeof s.text === 'function' ? s.text() : s.text;
    $('coach-skip').hidden = false; this.dots(); this.light();
  },
  dots() {
    $('coach-dots').innerHTML = this.steps.map((_, k) => `<i class="${k < this.step ? 'done' : k === this.step ? 'on' : ''}"></i>`).join('');
    if (this.step < 0) $('coach-dots').innerHTML = '';
  },
  light() {
    const s = this.step >= 0 ? this.steps[this.step] : null;
    const chip = s && (typeof s.chip === 'function' ? s.chip() : s.chip);
    for (const b of $('chips').querySelectorAll('button')) b.classList.toggle('lit', !!chip && b.dataset.q === chip);
    if (chip) {
      let b = [...$('chips').querySelectorAll('button')].find((x) => x.dataset.q === chip);
      if (!b) { b = document.createElement('button'); b.type = 'button'; b.dataset.q = chip; b.textContent = chip; b.className = 'lit'; }
      $('chips').prepend(b);
    }
    fitChips();
    $('nut').classList.toggle('lit', !!(s && s.nut));
  },
  event(e) {
    if (e.type === 'name' && e.count >= 3 && e.kind >= NAMED) this.word = e.word;
    if (this.step < 0) return;
    if (e.type === 'turn' && this.step === 3) return;
    if (this.steps[this.step].done(e)) {
      this.step += 1;
      if (e.type === 'ask' || e.type === 'pistachio') S.turned = this.step === 3 ? 0 : S.turned;
      if (this.step >= this.steps.length) this.stop('Done. Every word the parrot said, it learned from naming. Ask it anything in its words, move things, turn it, teach it words, and reward right answers with pistachios.');
      else this.show();
    }
  },
};
$('coach-skip').addEventListener('click', () => tour.stop());

// -- start

async function start() {
  sizeRoom();
  requestAnimationFrame(frameLoop);
  try {
    const out = await send('init', { pack: PACK });
    const info = out.reply;
    S.info = info;
    brain.describe(info);
    apply(out);
    const m = info.manifest;
    const dev = m.build === 'development' ? ' · <b>a development build</b>' : '';
    status(`The brain runs in your browser · cadence-net ${esc(m.cadence)}${dev}`, 'ready');
    $('runtime').title = `wheel ${m.wheel} (${m.branch || 'released'}, ${m.commit || ''}), brain ${m.brain.file}; started in ${(info.startup_ms / 1000).toFixed(1)} s`;
    $('nut').dataset.explain = info.reward_path
      ? 'A pistachio for a right answer. The parrot cracks it, and the reward goes into its brain: the words that asked (such as "where" or "colour") learn to ask for what its answer gave, as much as the pistachio surprised it. Sure of its answer, it learns little; unsure, more. This is how it learned what those words ask for.'
      : 'A pistachio for a right answer. The parrot cracks it, and its brain takes its own answer as the right one: the words that asked learn to ask for what the answer gave.';
    S.ready = true;
    $('mic').disabled = !(m.ears && canListen());
    await startRoom(firstRoom(), 0);
    let seen = null;
    try { seen = localStorage.getItem('ask-parrot-tour'); } catch (e) { /* storage blocked */ }
    if (params.get('tour') === '1' || (params.get('tour') !== '0' && !seen)) tour.start();
    else tour.stop();
    window.__ask.ready = true;
  } catch (e) {
    status('The brain could not start: ' + esc(e.message), 'error');
    $('coach-text').textContent = 'The brain could not start in this browser. ' + e.message;
  }
}

// for the page's checks: the world as it stands and what a teacher would answer
window.__ask = {
  ready: false,
  state: S,
  truth: () => truth(S.things, S.heading),
  busy: () => S.busy || brain.playing() || momentBusy,
  thingPx: (id) => { const t = S.things.find((q) => q.id === id); const r = room.getBoundingClientRect(); const [px, py] = roomFrame.toPx(t.x, t.y); return [r.left + px, r.top + py]; },
  floorPx: (x, y) => { const r = room.getBoundingClientRect(); const [px, py] = roomFrame.toPx(x, y); return [r.left + px, r.top + py]; },
  inView: (t) => inView(S.heading, t.x, t.y),
  tourStep: () => tour.step,
};
start();
