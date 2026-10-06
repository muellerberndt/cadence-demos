// Cadence key door: one continuing creature in a corridor. The brain lives in a worker (Pyodide,
// the released library); this page draws what the world saw and what the brain reports of
// itself, and lets the visitor move the key, cut a trip, save and restore the brain.

const $ = (id) => document.getElementById(id);
const PACK = new URL("pack/", import.meta.url).href;
const KINDS = ["floor", "chest", "lamp", "lever", "door"];
const FLOOR = 0, CHEST = 1, LAMP = 2, LEVER = 3, DOOR = 4;
const WINDOW = 300; // moments over which the policy chart averages

let worker = null;
let seq = 0;
const waiting = new Map();
let describe = null;
let manifest = null;
let paused = false;
let busy = false;
let rate = 8;
let timer = null;
let trip = { cells: null, index: 0, holding: false, keyed: CHEST, number: 0 };
let last = null; // the last moment's record
let status = null;
const rows = []; // per trip
const moments = []; // the last WINDOW moments: {holding, kind, p, q}
let flash = null; // {kind, text, colour, until}
let lastMode = null;
let saved = null;

const corridor = $("corridor");
const cctx = corridor.getContext("2d");
const strip = $("strip");
const sctx = strip.getContext("2d");
const policy = $("policy");
const pctx = policy.getContext("2d");

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

// -- the log

function log(text, cls = "") {
  const box = $("log");
  const line = document.createElement("div");
  if (cls) line.className = cls;
  line.textContent = `${status ? status.trips : 0}: ${text}`;
  box.appendChild(line);
  while (box.children.length > 400) box.removeChild(box.firstChild);
  box.scrollTop = box.scrollHeight;
}

// -- taking a moment

function take(record) {
  if (record.refused) {
    $("mode").textContent = "refused";
    $("mode").className = "pill refused";
    log(`the brain refused to answer (${record.error}); the outcome waits for its retry`, "cost");
    return;
  }
  if (record.cells) {
    trip = { cells: record.cells, index: 0, holding: false, keyed: record.keyed, number: record.trip };
  }
  trip.index = record.index;
  trip.holding = record.holding_after;
  trip.keyed = record.keyed;
  last = record;
  moments.push({ holding: record.holding, kind: record.kind, p: record.p_interact, q: record.p_interact_policy });
  while (moments.length > WINDOW) moments.shift();
  const now = performance.now();
  if (record.event === "food") flash = { kind: record.kind, text: "+1", colour: "#46d07a", until: now + 700 };
  else if (record.event === "wrong") flash = { kind: record.kind, text: "-0.25", colour: "#ff7b72", until: now + 700 };
  else if (record.event === "key") flash = { kind: record.kind, text: "key", colour: "#6aa8ff", until: now + 700 };
  if (record.event === "food") log("opened the door with the key: fed", "food");
  if (record.event === "wrong") log(`touched the ${KINDS[record.kind]} without a key: cost 0.25`, "cost");
  if (record.event === "key") log(`took the key from the ${KINDS[record.kind]}`, "key");
  if (record.cut) log("the trip was cut before the door; the key is lost, the forecast carries over", "roused");
  if (lastMode !== null && record.mode !== lastMode) {
    log(record.mode === "aroused" ? `roused (want ${record.want.toFixed(2)}, heat ${record.heat.toFixed(2)})` : "calm again: routine", record.mode === "aroused" ? "roused" : "");
  }
  lastMode = record.mode;
  if (record.trip_row) rows.push(record.trip_row);
}

async function moment() {
  if (busy || paused || !describe) return;
  busy = true;
  try {
    const record = await ask("moment");
    take(record);
    status = await ask("status");
    render();
  } catch (error) {
    $("loading").textContent = `error: ${error.message}`;
    $("loading").className = "loading failed";
    paused = true;
  } finally {
    busy = false;
  }
}

async function fastForward(trips) {
  if (busy || !describe) return;
  busy = true;
  const wasPaused = paused;
  paused = true;
  try {
    const result = await ask("run", { trips });
    for (const row of result.rows) rows.push(row);
    if (result.last && !result.last.refused) {
      // the corridor is redrawn from the next first cell; show the last state meanwhile
      last = result.last;
      trip = { cells: null, index: result.last.index, holding: result.last.holding_after, keyed: result.last.keyed, number: result.last.trip };
    }
    status = result;
    log(`lived ${trips} trips in ${result.worker_ms} ms: fed ${(result.recent.fed * 100).toFixed(0)}% of the last 20`);
    render();
  } finally {
    paused = wasPaused;
    busy = false;
  }
}

function schedule() {
  if (timer) clearInterval(timer);
  timer = setInterval(moment, 1000 / rate);
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

function drawCorridor() {
  const [w, h] = fit(corridor);
  cctx.clearRect(0, 0, w, h);
  const cells = trip.cells || Array(14).fill(FLOOR);
  const n = Math.max(cells.length, 14);
  const pad = 16, cw = (w - 2 * pad) / n, y0 = h * 0.42, ch = h * 0.3;
  for (let i = 0; i < n; i++) {
    const x = pad + i * cw;
    const kind = i < cells.length ? cells[i] : null;
    cctx.fillStyle = kind === null ? "#0a0d12" : i < trip.index ? "#151b26" : "#1b2230";
    cctx.fillRect(x + 1, y0, cw - 2, ch);
    if (kind === null) continue;
    const cx = x + cw / 2, cy = y0 + ch / 2;
    cctx.textAlign = "center";
    cctx.textBaseline = "middle";
    cctx.font = `${Math.min(cw * 0.5, 22)}px system-ui`;
    if (kind === CHEST) {
      cctx.fillStyle = "#b08968";
      cctx.fillRect(cx - cw * 0.3, cy - ch * 0.18, cw * 0.6, ch * 0.4);
      cctx.fillStyle = "#e6c79c";
      cctx.fillRect(cx - cw * 0.3, cy - ch * 0.18, cw * 0.6, ch * 0.1);
      if (trip.keyed === CHEST && !trip.holding) drawKey(cx, cy - ch * 0.35, cw);
    } else if (kind === LAMP) {
      cctx.fillStyle = "#f2e15b";
      cctx.beginPath(); cctx.arc(cx, cy - ch * 0.15, Math.min(cw, ch) * 0.16, 0, Math.PI * 2); cctx.fill();
      cctx.fillStyle = "#8a8f99";
      cctx.fillRect(cx - 2, cy - ch * 0.05, 4, ch * 0.3);
      if (trip.keyed === LAMP && !trip.holding) drawKey(cx, cy - ch * 0.45, cw);
    } else if (kind === LEVER) {
      cctx.strokeStyle = "#98a1b3";
      cctx.lineWidth = 3;
      cctx.beginPath(); cctx.moveTo(cx, cy + ch * 0.25); cctx.lineTo(cx + cw * 0.15, cy - ch * 0.2); cctx.stroke();
      cctx.fillStyle = "#ff7b72";
      cctx.beginPath(); cctx.arc(cx + cw * 0.15, cy - ch * 0.2, 4, 0, Math.PI * 2); cctx.fill();
    } else if (kind === DOOR) {
      cctx.fillStyle = "#5c4a3a";
      cctx.fillRect(cx - cw * 0.3, cy - ch * 0.4, cw * 0.6, ch * 0.8);
      cctx.fillStyle = "#f2e15b";
      cctx.beginPath(); cctx.arc(cx + cw * 0.15, cy, 3, 0, Math.PI * 2); cctx.fill();
    }
    cctx.fillStyle = "#4a5466";
    cctx.font = "11px system-ui";
    cctx.fillText(KINDS[kind], cx, y0 + ch + 14);
  }
  // the creature
  const i = Math.min(trip.index, n - 1);
  const cx = pad + i * cw + cw / 2, cy = y0 - h * 0.12;
  const level = last ? last.level : 0;
  const aroused = last && last.mode === "aroused";
  if (aroused || level > 0.05) {
    const r = 14 + 26 * Math.min(1, level);
    const halo = cctx.createRadialGradient(cx, cy, 4, cx, cy, r);
    halo.addColorStop(0, aroused ? "rgba(255,179,71,0.55)" : "rgba(106,168,255,0.25)");
    halo.addColorStop(1, "rgba(255,179,71,0)");
    cctx.fillStyle = halo;
    cctx.beginPath(); cctx.arc(cx, cy, r, 0, Math.PI * 2); cctx.fill();
  }
  cctx.fillStyle = aroused ? "#ffd296" : "#b6f1c6";
  cctx.beginPath(); cctx.arc(cx, cy, 11, 0, Math.PI * 2); cctx.fill();
  cctx.fillStyle = "#0b0e13";
  cctx.beginPath(); cctx.arc(cx - 4, cy - 2, 2, 0, Math.PI * 2); cctx.arc(cx + 4, cy - 2, 2, 0, Math.PI * 2); cctx.fill();
  if (trip.holding) drawKey(cx + 14, cy - 10, 30);
  if (last && last.action === 1 && last.index === trip.index) {
    cctx.strokeStyle = "#e6e9f0";
    cctx.lineWidth = 2;
    cctx.beginPath(); cctx.moveTo(cx, cy + 11); cctx.lineTo(cx, y0 - 4); cctx.stroke();
  }
  if (flash && performance.now() < flash.until) {
    cctx.fillStyle = flash.colour;
    cctx.font = "bold 16px system-ui";
    cctx.fillText(flash.text, cx, cy - 34);
  }
  cctx.fillStyle = "#98a1b3";
  cctx.font = "12px system-ui";
  cctx.textAlign = "left";
  cctx.fillText(`trip ${trip.number}${trip.cells && trip.cells.length < 14 ? " (cut short)" : ""}`, pad, 16);
  cctx.textAlign = "right";
  cctx.fillText(`key in the ${KINDS[trip.keyed]}`, w - pad, 16);
}

function drawKey(x, y, size) {
  cctx.save();
  cctx.strokeStyle = "#f2e15b";
  cctx.fillStyle = "#f2e15b";
  cctx.lineWidth = 2;
  const s = Math.min(size, 24) / 24;
  cctx.beginPath(); cctx.arc(x - 6 * s, y, 4 * s, 0, Math.PI * 2); cctx.stroke();
  cctx.beginPath(); cctx.moveTo(x - 2 * s, y); cctx.lineTo(x + 8 * s, y); cctx.lineTo(x + 8 * s, y + 4 * s); cctx.stroke();
  cctx.restore();
}

function drawStrip() {
  const [w, h] = fit(strip);
  sctx.clearRect(0, 0, w, h);
  const shown = rows.slice(-200);
  if (!shown.length) return;
  const pad = 6, bw = (w - 2 * pad) / 200, top = 14, bottom = h - 6, span = bottom - top;
  // the key's band
  for (let i = 0; i < shown.length; i++) {
    sctx.fillStyle = shown[i].keyed === LAMP ? "rgba(242,225,91,0.35)" : "rgba(176,137,104,0.35)";
    sctx.fillRect(pad + i * bw, 0, bw, 8);
  }
  // wrong interactions (bars, up to 5)
  for (let i = 0; i < shown.length; i++) {
    const r = shown[i];
    const hh = Math.min(1, r.wrongs / 5) * span * 0.6;
    sctx.fillStyle = "rgba(255,123,114,0.7)";
    sctx.fillRect(pad + i * bw, bottom - hh, Math.max(1, bw - 1), hh);
    if (r.cut) { sctx.fillStyle = "rgba(152,161,179,0.6)"; sctx.fillRect(pad + i * bw, bottom - 3, Math.max(1, bw - 1), 3); }
  }
  // aroused share (line)
  sctx.strokeStyle = "#ffb347";
  sctx.lineWidth = 1.5;
  sctx.beginPath();
  shown.forEach((r, i) => {
    const x = pad + i * bw + bw / 2, y = bottom - r.aroused * span;
    if (i === 0) sctx.moveTo(x, y); else sctx.lineTo(x, y);
  });
  sctx.stroke();
  // fed (dots at the top)
  for (let i = 0; i < shown.length; i++) {
    const r = shown[i];
    if (r.cut) continue;
    sctx.fillStyle = r.fed ? "#46d07a" : "#3a2b2b";
    sctx.beginPath(); sctx.arc(pad + i * bw + bw / 2, top + 6, Math.min(3, bw), 0, Math.PI * 2); sctx.fill();
  }
  sctx.fillStyle = "#98a1b3";
  sctx.font = "11px system-ui";
  sctx.textAlign = "left";
  sctx.fillText("fed", pad, top + 20);
  sctx.textAlign = "right";
  sctx.fillText(`last ${shown.length} trips`, w - pad, top + 20);
}

function drawPolicy() {
  const [w, h] = fit(policy);
  pctx.clearRect(0, 0, w, h);
  const pad = 10, top = 16, bottom = h - 18, span = bottom - top;
  const groups = 5, gw = (w - 2 * pad) / groups, bw = gw / 3;
  for (let kind = 0; kind < groups; kind++) {
    for (const holding of [false, true]) {
      const sel = moments.filter((m) => m.kind === kind && m.holding === holding);
      const x = pad + kind * gw + (holding ? bw * 1.6 : bw * 0.4);
      if (!sel.length) continue;
      const p = sel.reduce((a, m) => a + m.p, 0) / sel.length;
      const q = sel.reduce((a, m) => a + m.q, 0) / sel.length;
      pctx.fillStyle = holding ? "#6aa8ff" : "rgba(106,168,255,0.0)";
      pctx.strokeStyle = "#6aa8ff";
      pctx.lineWidth = 1.5;
      pctx.beginPath(); pctx.rect(x, bottom - p * span, bw * 0.9, p * span); pctx.fill(); pctx.stroke();
      pctx.strokeStyle = "#e6e9f0";
      pctx.beginPath(); pctx.moveTo(x - 2, bottom - q * span); pctx.lineTo(x + bw * 0.9 + 2, bottom - q * span); pctx.stroke();
      pctx.fillStyle = "#98a1b3";
      pctx.font = "10px system-ui";
      pctx.textAlign = "center";
      pctx.fillText(`${sel.length}`, x + bw * 0.45, top - 4);
    }
    pctx.fillStyle = "#98a1b3";
    pctx.font = "11px system-ui";
    pctx.textAlign = "center";
    pctx.fillText(KINDS[kind], pad + kind * gw + gw / 2, h - 5);
  }
  pctx.strokeStyle = "#222a37";
  pctx.beginPath(); pctx.moveTo(pad, bottom); pctx.lineTo(w - pad, bottom); pctx.stroke();
  pctx.fillStyle = "#98a1b3";
  pctx.textAlign = "left";
  pctx.fillText("P(interact)", pad, top - 4);
}

function render() {
  drawCorridor();
  drawStrip();
  drawPolicy();
  if (!status) return;
  const s = status;
  $("mode").textContent = s.mode;
  $("mode").className = `pill ${s.mode}`;
  $("trip").textContent = s.trips;
  $("fed").textContent = s.recent.trips ? `${(s.recent.fed * 100).toFixed(0)}%` : "-";
  $("wrong").textContent = s.recent.trips ? s.recent.wrong.toFixed(2) : "-";
  $("sweeps").textContent = last && !last.refused ? last.sweeps : "-";
  $("ms").textContent = last && !last.refused ? last.ms.toFixed(1) : "-";
  $("keyed").textContent = s.keyed_name;
  $("want").textContent = s.want.toFixed(2);
  $("wantbar").style.width = `${Math.min(1, s.want) * 100}%`;
  $("level").textContent = s.level.toFixed(2);
  $("levelbar").style.width = `${Math.min(1, s.level / 0.4) * 100}%`;
  $("heat").textContent = s.heat.toFixed(2);
  $("heatbar").style.width = `${Math.min(1, (s.heat - 1) / 2) * 100}%`;
  const wk = s.work;
  const perRoutine = wk.routine ? (wk.sweeps_routine / wk.routine).toFixed(1) : "-";
  const perAroused = wk.aroused ? (wk.sweeps_aroused / wk.aroused).toFixed(1) : "-";
  const ledger = [
    ["trips lived here", s.trips],
    ["moments", s.moments],
    ["routine moments", `${wk.routine} (${((1 - wk.aroused_share) * 100).toFixed(0)}%)`],
    ["aroused moments", `${wk.aroused} (${(wk.aroused_share * 100).toFixed(0)}%)`],
    ["sweeps per routine moment", perRoutine],
    ["sweeps per aroused moment", perAroused],
    ["learning sweeps", wk.learning_sweeps],
    ["memory writes", wk.memory_writes],
    ["refused answers", wk.refusals],
    ["brain time per moment", `${wk.ms_per_moment.toFixed(1)} ms`],
    ["trips cut short", s.recent.cuts],
    ["age of the brain (moments)", s.age],
  ];
  $("ledger").innerHTML = ledger.map(([k, v]) => `<tr><td class="k">${k}</td><td>${v}</td></tr>`).join("");
}

// -- controls

$("movekey").addEventListener("click", async () => {
  const out = await ask("move_key");
  log(`the key moved to the ${KINDS[out.keyed]}; the creature was not told`, "roused");
  trip.keyed = out.keyed;
  render();
});
$("cut").addEventListener("click", async () => { await ask("cut"); log("this trip will be cut at the next cell"); });
$("pause").addEventListener("click", () => {
  paused = !paused;
  $("pause").textContent = paused ? "Play" : "Pause";
  $("pause").classList.toggle("on", paused);
});
$("ff").addEventListener("click", () => fastForward(25));
$("rate").addEventListener("input", (e) => { rate = Number(e.target.value); $("ratev").textContent = rate; schedule(); });
$("save").addEventListener("click", async () => {
  const out = await ask("snapshot");
  saved = { brain: out.brain, trips: status ? status.trips : 0 };
  $("restore").disabled = false;
  log(`saved the brain at trip ${saved.trips}, with the outcome it awaits`);
});
$("restore").addEventListener("click", async () => {
  if (!saved) return;
  const out = await ask("restore", { brain: saved.brain });
  status = out;
  log(`restored the brain saved at trip ${saved.trips}; the world went on, the brain continues from there`);
  render();
});
async function reborn(kind) {
  if (busy) return;
  busy = true;
  try {
    const delay = Number($("delay").value);
    describe = kind === "newborn" ? await ask("newborn", { delay, seed: Math.floor(Math.random() * 1000) }) : await ask("raised");
    rows.length = 0; moments.length = 0; last = null; lastMode = null; saved = null; $("restore").disabled = true;
    trip = { cells: null, index: 0, holding: false, keyed: CHEST, number: 0 };
    status = await ask("status");
    $("brainname").textContent = `${describe.neurons} neurons · ${describe.synapses} synapses · ${describe.raised_trips ? `raised through ${describe.raised_trips} trips at delay ${describe.delay}` : `newborn at delay ${describe.delay}`} · Cadence ${describe.cadence} in Pyodide ${manifest.pyodide}`;
    log(kind === "newborn" ? `a newborn brain at delay ${describe.delay}: nothing is known yet` : `the raised creature again, as it was saved`, "roused");
    render();
  } finally {
    busy = false;
  }
}
$("newborn").addEventListener("click", () => reborn("newborn"));
$("raised").addEventListener("click", () => reborn("raised"));
window.addEventListener("resize", render);

// -- for the page check: the worker's messages, from outside the module
export function drive(message) {
  return ask(message.op, message);
}

// -- start

(async () => {
  try {
    startWorker();
    const started = await ask("start", { pack: PACK });
    manifest = started.manifest;
    describe = started.describe;
    status = await ask("status");
    $("loading").textContent = "ready";
    $("loading").className = "loading ready";
    $("brainname").textContent = `${describe.neurons} neurons · ${describe.synapses} synapses · raised through ${describe.raised_trips} trips at delay ${describe.delay} · Cadence ${describe.cadence} in Pyodide ${manifest.pyodide}`;
    log(`the raised creature arrives mid-life: fed ${(manifest.raised.fed_last_50 * 100).toFixed(0)}% of its last 50 trips, ${manifest.raised.wrong_last_50.toFixed(2)} wrong interactions per trip`);
    render();
    schedule();
  } catch (error) {
    $("loading").textContent = `failed: ${error.message}`;
    $("loading").className = "loading failed";
  }
})();
