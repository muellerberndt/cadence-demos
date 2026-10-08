// Cadence walkers: three treadmills, the beat paid by the world. Two Cadence brains live in a
// worker (Pyodide, the released library) and learn here; this page draws what the world saw
// and what the brains report of themselves, runs the coin-flipping walker itself, and lets
// the visitor freeze the floor, flash a distractor, erase the first walker's copy of its last
// step, and start over with new walkers.

const $ = (id) => document.getElementById(id);
const PACK = new URL("pack/", import.meta.url).href;
const KIND = { drive: 0, pause: 1, distractor: 2 };
const LANES = ["copy", "bare", "random"];
const BRAINS = ["copy", "bare"];
const NAMES = { copy: "with a copy of its last step", bare: "without the copy", random: "a coin" };
const COLOURS = { copy: "#6aa8ff", bare: "#c9a06a", random: "#b48cff" };
const BLOCK = 25;
const CHIPS = 24;

let worker = null;
let seq = 0;
const waiting = new Map();
let describe = null;
let running = false;
let busy = false;
let rate = 12;
let timer = null;
let moment = 0;
let queue = []; // moment kinds the next moments will take
const marks = []; // {moment, kind} for the strip
let lanes = {};
let coin = null;
let audio = null;
let soundOn = false;
let lastMode = null;

const track = $("track");
const tctx = track.getContext("2d");
const strip = $("strip");
const sctx = strip.getContext("2d");

// -- the coin

function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function freshLane() {
  return { steps: [], changed: [], aroused: [], position: 0, found: null, status: null, last: null, stumble: 0, x: 0 };
}

function beatOf(steps) {
  let pairs = 0, changes = 0;
  for (let i = 1; i < steps.length; i++) {
    if (steps[i] === null || steps[i - 1] === null) { pairs++; continue; }
    pairs++;
    if (steps[i] !== steps[i - 1]) changes++;
  }
  return pairs ? changes / pairs : 0;
}

function born(seed) {
  lanes = { copy: freshLane(), bare: freshLane(), random: freshLane() };
  coin = mulberry32(seed + 1);
  moment = 0;
  queue = [];
  marks.length = 0;
  lastMode = null;
}

// -- the worker

function startWorker() {
  worker = new Worker(new URL("worker.js", import.meta.url), { type: "module" });
  worker.onmessage = (event) => {
    const m = event.data;
    if (m.status) { $("loading").textContent = m.status; return; }
    const p = waiting.get(m.rid);
    if (!p) return;
    waiting.delete(m.rid);
    if (m.error) p.reject(new Error(m.error)); else p.resolve(m.result);
  };
}
function ask(op, data = {}) {
  return new Promise((resolve, reject) => {
    const rid = ++seq;
    waiting.set(rid, { resolve, reject });
    worker.postMessage({ ...data, op, rid });
  });
}

// -- sound

function beep(freq, seconds, gain) {
  if (!soundOn || !audio) return;
  const o = audio.createOscillator();
  const g = audio.createGain();
  o.type = freq < 200 ? "triangle" : "sine";
  o.frequency.value = freq;
  g.gain.value = gain;
  g.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + seconds);
  o.connect(g).connect(audio.destination);
  o.start();
  o.stop(audio.currentTime + seconds);
}

// -- the log

function log(text, cls = "") {
  const box = $("log");
  const line = document.createElement("div");
  if (cls) line.className = cls;
  line.textContent = `${moment}: ${text}`;
  box.appendChild(line);
  while (box.children.length > 400) box.removeChild(box.firstChild);
  box.scrollTop = box.scrollHeight;
}

// -- taking a moment

function stepLane(name, action, changed, aroused) {
  const lane = lanes[name];
  lane.steps.push(action);
  lane.changed.push(changed);
  lane.aroused.push(aroused);
  if (changed) lane.position += 1;
  else if (lane.steps.length > 1 && action !== null) lane.stumble = performance.now();
  if (lane.found === null && lane.steps.length >= 21 && beatOf(lane.steps.slice(-20)) === 1) {
    lane.found = moment;
    log(`${NAMES[name]}: found the beat, twenty steps without a stumble`, name === "copy" ? "good" : "");
  }
}

function takeBrain(name, record) {
  const lane = lanes[name];
  if (record.refused) {
    stepLane(name, null, false, null);
    lane.last = { ...(lane.last || {}), refused: true };
    log(`${NAMES[name]}: the brain refused to answer (${record.error}); the step is missed`, "cost");
    return;
  }
  stepLane(name, record.action, record.changed, record.aroused);
  lane.position = record.position;
  lane.last = record;
  if (name === "copy") {
    if (record.changed) beep(record.action === 0 ? 660 : 880, 0.06, 0.08);
    else if (lane.steps.length > 1) beep(140, 0.12, 0.12);
    if (lastMode !== null && record.mode !== lastMode) {
      log(record.mode === "aroused" ? `roused (want ${record.want.toFixed(2)}, surprise ${record.surprise.toFixed(2)})` : "calm again: routine", record.mode === "aroused" ? "roused" : "");
    }
    lastMode = record.mode;
  }
}

function takeCoin() {
  const action = coin() < 0.5 ? 0 : 1;
  const lane = lanes.random;
  const previous = lane.steps.length ? lane.steps[lane.steps.length - 1] : null;
  stepLane("random", action, previous !== null && action !== previous, null);
}

async function tick() {
  if (busy || !running || !describe) return;
  busy = true;
  try {
    const kind = queue.length ? queue.shift() : KIND.drive;
    moment += 1;
    const result = await ask("moment", { kind, lanes: BRAINS });
    for (const name of BRAINS) takeBrain(name, result[name]);
    takeCoin();
    if (moment % 10 === 0) {
      const status = await ask("status", { lanes: BRAINS });
      for (const name of BRAINS) lanes[name].status = status[name];
    }
    render();
  } catch (error) {
    $("loading").textContent = `error: ${error.message}`;
    $("loading").className = "loading failed";
    running = false;
    $("start").textContent = "Start";
  } finally {
    busy = false;
  }
}

async function fastForward(moments, kind = KIND.drive) {
  if (busy || !describe) return null;
  busy = true;
  const wasRunning = running;
  running = false;
  try {
    const result = await ask("run", { moments, kind, lanes: BRAINS });
    for (const name of BRAINS) {
      const feet = result[name].feet;
      const aroused = result[name].aroused;
      for (let i = 0; i < feet.length; i++) {
        moment += name === "copy" ? 1 : 0;
        const lane = lanes[name];
        const previous = lane.steps.length ? lane.steps[lane.steps.length - 1] : null;
        const changed = feet[i] !== null && previous !== null && feet[i] !== previous;
        stepLane(name, feet[i], changed, aroused[i]);
      }
      lanes[name].status = result[name];
      lanes[name].position = result[name].position;
      if (result[name].last && !result[name].last.refused) lanes[name].last = result[name].last;
    }
    for (let i = 0; i < moments; i++) takeCoin();
    log(`lived ${moments} moments in ${result.worker_ms} ms`);
    render();
    return result;
  } finally {
    running = wasRunning;
    busy = false;
  }
}

// -- drawing

function fit(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return [w, h];
}

function drawWalker(ctx, name, x, y, now) {
  const lane = lanes[name];
  const last = lane.steps.length ? lane.steps[lane.steps.length - 1] : null;
  const colour = COLOURS[name];
  const record = lane.last;
  const aroused = record && !record.refused ? record.aroused : null;
  const stumbling = now - lane.stumble < 260;
  const wobble = stumbling ? Math.sin(now / 18) * 2.5 : 0;
  ctx.save();
  ctx.translate(x + wobble, y);
  // glow: the mood of a brain, the coin's own colour
  ctx.shadowColor = aroused === null ? colour : aroused ? "#ffb347" : "#46d07a";
  ctx.shadowBlur = aroused === null ? 8 : aroused ? 22 : 14;
  // legs: the foot that moved last is forward
  const forward = last === null ? 0 : last === 0 ? -1 : 1;
  ctx.strokeStyle = colour;
  ctx.lineWidth = 3;
  ctx.lineCap = "round";
  for (const leg of [-1, 1]) {
    const ahead = leg === (forward || 1) ? 9 : -7;
    ctx.beginPath();
    ctx.moveTo(leg * 6, -14);
    ctx.lineTo(leg * 6 + ahead * 0.5, -4);
    ctx.lineTo(ahead, 0);
    ctx.stroke();
    ctx.fillStyle = colour;
    ctx.beginPath();
    ctx.ellipse(ahead + 2, 0, 5, 2.5, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  // body and head
  ctx.fillStyle = colour;
  ctx.beginPath();
  ctx.roundRect(-13, -36, 26, 24, 7);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(0, -45, 9, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.fillStyle = "#0b0e13";
  ctx.beginPath();
  ctx.arc(3 * (forward || 1), -46, 2.2, 0, Math.PI * 2);
  ctx.fill();
  if (stumbling) {
    ctx.fillStyle = "rgba(255,255,255,0.35)";
    for (let i = 0; i < 3; i++) {
      ctx.beginPath();
      ctx.arc(-12 - i * 7, -2 - (i % 2) * 4, 3 + i, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.restore();
}

function drawTrack() {
  const [w, h] = fit(track);
  const now = performance.now();
  tctx.clearRect(0, 0, w, h);
  const CELL = 26;
  const visible = Math.floor((w - 60) / CELL);
  const leader = Math.max(...LANES.map((n) => lanes[n].position));
  const camera = Math.max(0, leader - Math.floor(visible * 0.72));
  LANES.forEach((name, i) => {
    const y = 78 + i * 100;
    const lane = lanes[name];
    // the treadmill
    tctx.strokeStyle = "#1a2230";
    tctx.lineWidth = 6;
    tctx.beginPath();
    tctx.moveTo(10, y + 3);
    tctx.lineTo(w - 10, y + 3);
    tctx.stroke();
    tctx.fillStyle = "#2a3446";
    for (let c = 0; c <= visible; c++) {
      const cell = camera + c;
      const x = 30 + c * CELL;
      tctx.fillRect(x, y + 1, cell % 10 === 0 ? 3 : 1, 5);
      if (cell % 10 === 0) {
        tctx.fillStyle = "#4a5668";
        tctx.font = "10px ui-monospace, monospace";
        tctx.fillText(String(cell), x - 4, y + 18);
        tctx.fillStyle = "#2a3446";
      }
    }
    // the walker: smoothed toward its cell
    const target = 30 + Math.max(-1, lane.position - camera) * CELL;
    lane.x += (target - lane.x) * 0.35;
    if (Math.abs(target - lane.x) < 0.4) lane.x = target;
    drawWalker(tctx, name, lane.x, y, now);
    // the name, the mood, the distance
    tctx.fillStyle = COLOURS[name];
    tctx.font = "600 13px system-ui, sans-serif";
    tctx.fillText(NAMES[name], 14, y - 62);
    tctx.fillStyle = "#98a1b3";
    tctx.font = "12px system-ui, sans-serif";
    const behind = lane.position < camera ? ` (${camera - lane.position} cells behind the edge)` : "";
    tctx.fillText(`${lane.position} steps forward${behind}`, 14 + NAMES[name].length * 7.2 + 14, y - 62);
    // the last steps as chips
    const chips = lane.steps.slice(-CHIPS);
    const changed = lane.changed.slice(-CHIPS);
    chips.forEach((s, k) => {
      const x = w - 12 - (chips.length - k) * 13;
      tctx.fillStyle = s === null ? "#3a1f1f" : k === 0 && lane.steps.length <= CHIPS ? "#2a3446" : changed[k] ? "#2b6a45" : "#6a2b2b";
      tctx.fillRect(x, y - 52, 11, 14);
      tctx.fillStyle = "#e6e9f0";
      tctx.font = "10px ui-monospace, monospace";
      tctx.fillText(s === null ? "·" : s === 0 ? "L" : "R", x + 2, y - 41);
    });
  });
}

function drawStrip() {
  const [w, h] = fit(strip);
  sctx.clearRect(0, 0, w, h);
  const n = lanes.copy ? lanes.copy.steps.length : 0;
  const blocks = Math.max(1, Math.ceil(Math.max(n, 100) / BLOCK));
  const px = (b) => 36 + (b / blocks) * (w - 46);
  const py = (v) => 8 + (1 - v) * (h - 26);
  sctx.strokeStyle = "#222a37";
  sctx.lineWidth = 1;
  for (const v of [0, 0.5, 1]) {
    sctx.beginPath();
    sctx.moveTo(36, py(v));
    sctx.lineTo(w - 10, py(v));
    sctx.stroke();
    sctx.fillStyle = "#98a1b3";
    sctx.font = "10px ui-monospace, monospace";
    sctx.fillText(v.toFixed(1), 8, py(v) + 3);
  }
  // the first walker's arousal as an area
  if (lanes.copy) {
    sctx.fillStyle = "rgba(255,179,71,0.22)";
    sctx.beginPath();
    sctx.moveTo(px(0), py(0));
    for (let b = 0; b * BLOCK < n; b++) {
      const part = lanes.copy.aroused.slice(b * BLOCK, (b + 1) * BLOCK).filter((a) => a !== null);
      const share = part.length ? part.filter(Boolean).length / part.length : 0;
      sctx.lineTo(px(b + 0.5), py(share));
    }
    sctx.lineTo(px(Math.ceil(n / BLOCK) - 0.5), py(0));
    sctx.closePath();
    sctx.fill();
  }
  for (const m of marks) {
    sctx.strokeStyle = m.kind === "forget" ? "#ff7b72" : m.kind === "flash" ? "#ffd84a" : "#98a1b3";
    sctx.beginPath();
    sctx.moveTo(px(m.moment / BLOCK), py(1));
    sctx.lineTo(px(m.moment / BLOCK), py(0));
    sctx.stroke();
  }
  for (const name of LANES) {
    const lane = lanes[name];
    if (!lane) continue;
    sctx.strokeStyle = COLOURS[name];
    sctx.lineWidth = 2;
    sctx.beginPath();
    for (let b = 0; b * BLOCK < lane.steps.length; b++) {
      const part = lane.steps.slice(Math.max(0, b * BLOCK - 1), (b + 1) * BLOCK);
      const v = beatOf(part);
      if (b === 0) sctx.moveTo(px(b + 0.5), py(v)); else sctx.lineTo(px(b + 0.5), py(v));
    }
    sctx.stroke();
  }
  sctx.fillStyle = "#98a1b3";
  sctx.font = "10px ui-monospace, monospace";
  sctx.fillText(`moment ${n}`, w - 80, h - 6);
}

function mix(colour, t) {
  // the box's colour between the panel and the lane colour
  const c = parseInt(colour.slice(1), 16);
  const r = (c >> 16) & 255, g = (c >> 8) & 255, b = c & 255;
  const k = Math.max(0, Math.min(1, t));
  return `rgb(${Math.round(29 + (r - 29) * k)}, ${Math.round(36 + (g - 36) * k)}, ${Math.round(48 + (b - 48) * k)})`;
}

function renderLanes() {
  const box = $("lanes");
  box.innerHTML = "";
  for (const name of LANES) {
    const lane = lanes[name];
    const div = document.createElement("div");
    div.className = `lane ${name}`;
    const status = lane.status;
    const beat50 = beatOf(lane.steps.slice(-50));
    const last = lane.last;
    const mode = name === "random" ? "coin" : last ? (last.refused ? "refused" : last.mode) : "-";
    const income = lane.changed.slice(-100);
    const earned = income.length ? income.filter(Boolean).length / income.length : 0;
    div.innerHTML = `<div class="row"><span class="name">${NAMES[name]}</span><span class="pill ${mode}">${mode}</span></div>
      <div class="row"><span class="k">beat, last 50 steps</span><b>${beat50.toFixed(2)}</b></div>
      <div class="row"><span class="k">earned, last 100</span><b>${earned.toFixed(2)}</b></div>
      <div class="row"><span class="k">found the beat at</span><b>${lane.found === null ? "-" : lane.found}</b></div>
      <div class="row"><span class="k">aroused, last 50</span><b>${status && status.work ? (status.work.aroused_recent * 100).toFixed(0) + "%" : name === "random" ? "-" : "-"}</b></div>
      <div class="row"><span class="k">brain time per moment</span><b>${status && status.work ? status.work.ms_per_moment.toFixed(1) + " ms" : "-"}</b></div>`;
    box.appendChild(div);
  }
}

function renderBrain() {
  const lane = lanes.copy;
  const r = lane && lane.last && !lane.last.refused ? lane.last : null;
  if (!r) return;
  const copyL = r.copy ? r.copy[0] : 0, copyR = r.copy ? r.copy[1] : 0;
  $("copyL").style.background = mix(COLOURS.copy, copyL);
  $("copyR").style.background = mix(COLOURS.copy, copyR);
  $("copyL").style.color = copyL > 0.5 ? "#0b0e13" : "#98a1b3";
  $("copyR").style.color = copyR > 0.5 ? "#0b0e13" : "#98a1b3";
  const m = r.motor;
  const hi = Math.max(m[0], m[1]), lo = Math.min(m[0], m[1]);
  const span = Math.max(1e-6, hi - lo);
  const tL = 0.25 + 0.75 * (m[0] - lo) / span, tR = 0.25 + 0.75 * (m[1] - lo) / span;
  $("motorL").style.background = mix("#46d07a", m[0] === hi ? tL : 0.15);
  $("motorR").style.background = mix("#46d07a", m[1] === hi ? tR : 0.15);
  $("motorL").textContent = `L ${m[0].toFixed(2)}`;
  $("motorR").textContent = `R ${m[1].toFixed(2)}`;
  const belief = r.belief === null ? 0 : r.belief;
  $("belief").textContent = r.belief === null ? "-" : belief.toFixed(2);
  $("beliefbar").style.width = `${belief * 100}%`;
  $("level").textContent = r.level.toFixed(2);
  $("levelbar").style.width = `${Math.min(1, r.level) * 100}%`;
  $("want").textContent = r.want.toFixed(2);
  $("wantbar").style.width = `${Math.min(1, r.want) * 100}%`;
  const s = lane.status;
  const rows = [
    ["moment", r.moment],
    ["steps forward", r.position],
    ["beat, last 20 / 50", `${r.beat20.toFixed(2)} / ${r.beat50.toFixed(2)}`],
    ["earned, last 100", r.income100.toFixed(2)],
    ["mode", r.mode],
    ["found the beat at", lane.found === null ? "-" : lane.found],
    ["sweeps this moment", `${r.sweeps} + ${r.learning_sweeps} learning`],
    ["routine / aroused moments", s && s.work ? `${s.work.routine} / ${s.work.aroused}` : "-"],
    ["learning sweeps so far", s && s.work ? s.work.learning_sweeps : "-"],
    ["refusals", s && s.work ? s.work.refusals : "-"],
    ["age", r.age],
  ];
  $("ledger").innerHTML = rows.map(([k, v]) => `<tr><td class="k">${k}</td><td>${v}</td></tr>`).join("");
}

function render() {
  drawTrack();
  drawStrip();
  renderLanes();
  renderBrain();
}

// -- the loop and the controls

function schedule() {
  if (timer) clearInterval(timer);
  timer = setInterval(tick, 1000 / rate);
}

async function newborns() {
  if (busy) return;
  busy = true;
  try {
    const seed = Math.max(0, parseInt($("seed").value, 10) || 0);
    describe = await ask("born", { seed });
    born(seed);
    log(`three newborns from seed ${seed}`, "copy");
    render();
  } finally {
    busy = false;
  }
}

function wire() {
  $("start").onclick = () => {
    if (!audio && window.AudioContext) audio = new AudioContext();
    running = !running;
    $("start").textContent = running ? "Pause" : "Start";
  };
  $("rate").oninput = () => { rate = parseInt($("rate").value, 10); $("ratev").textContent = String(rate); schedule(); };
  $("ff").onclick = () => fastForward(100);
  $("freeze").onclick = () => { queue.push(KIND.pause, KIND.pause, KIND.pause); marks.push({ moment, kind: "freeze" }); log("the floor froze for three moments", "roused"); };
  $("flash").onclick = () => { queue.push(KIND.distractor); marks.push({ moment, kind: "flash" }); log("a flash instead of the drive", "roused"); };
  $("forget").onclick = async () => {
    if (busy || !describe) return;
    busy = true;
    try {
      await ask("forget", { lanes: ["copy"] });
      marks.push({ moment, kind: "forget" });
      log("the first walker's copy of its last step was erased; its learned relations stay", "cost");
      render();
    } finally { busy = false; }
  };
  $("newborn").onclick = newborns;
  $("sound").onclick = () => {
    if (!audio && window.AudioContext) audio = new AudioContext();
    soundOn = !soundOn;
    $("sound").textContent = soundOn ? "Sound on" : "Sound off";
    $("sound").classList.toggle("on", soundOn);
  };
  window.addEventListener("resize", render);
}

async function main() {
  wire();
  startWorker();
  born(parseInt($("seed").value, 10) || 0);
  render();
  try {
    describe = await ask("start", { pack: PACK, seed: parseInt($("seed").value, 10) || 0 });
    const m = describe.manifest;
    $("brainname").textContent = `Cadence ${m.cadence} in Pyodide ${m.pyodide}: Brain.compose(4, 2, modules=(32,)) at the reward-rhythm chamber's point; ${describe.copy.neurons} neurons and ${describe.copy.synapses} synapses with the copy, ${describe.bare.neurons} and ${describe.bare.synapses} without.`;
    $("loading").textContent = "ready";
    $("loading").className = "loading ready";
    log("the walkers are born; press Start", "copy");
    schedule();
  } catch (error) {
    $("loading").textContent = `failed: ${error.message}`;
    $("loading").className = "loading failed";
  }
}

// the page check drives the walkers through here
export async function drive(message) {
  if (message.op === "run") {
    const result = await fastForward(message.moments, message.kind === undefined ? KIND.drive : message.kind);
    return result && summary();
  }
  if (message.op === "forget") {
    await ask("forget", { lanes: ["copy"] });
    marks.push({ moment, kind: "forget" });
    return summary();
  }
  if (message.op === "queue") { queue.push(...message.kinds); return { queued: queue.length }; }
  if (message.op === "pause") { running = false; $("start").textContent = "Start"; return { running }; }
  if (message.op === "status") return summary();
  throw new Error(`unknown op ${message.op}`);
}

function summary() {
  const out = { moment };
  for (const name of LANES) {
    const lane = lanes[name];
    out[name] = {
      beat50: beatOf(lane.steps.slice(-50)),
      beat20: beatOf(lane.steps.slice(-20)),
      position: lane.position,
      found: lane.found,
      steps: lane.steps.length,
      status: lane.status,
      last: lane.last,
    };
  }
  return out;
}

main();
