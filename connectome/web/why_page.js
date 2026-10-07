// Page 3: the same compiled wiring twice, on one clock. Left, the spiking port (spiking.js): leaky
// integrate-and-fire neurons with the synapse counts as weights, steps of 0.1 ms, the driven neurons
// fed Poisson spikes. Middle, the patch net (brain.js) settling: one step is dt of the unit's time
// constant, declared here as 200 ms, so a step is 40 ms of fish time and a simulated second is 25 steps.
// Right, the neurons that are not driven: each one's rate over the last 500 ms against its activity
// now, with the cosine and the Spearman correlation computed here. A simulated second is 1000 simulated
// ms of spiking (10,000 steps) and 25 settling steps; a settling step is taken after every 400
// spiking steps, so the two engines never drift apart. The strips and the bars are pixel buffers
// put onto their canvases once per frame, one row of device pixels per neuron.
import { mountShell, app, el, $, renderParagraphs, int, num, fetchJSON, RECEIPT_URL, CLASS_NAMES, sourcesList } from "./site.js";
import { spikingEvidence } from "./evidence.js";
import { SettlingBrain } from "./brain.js";
import { SpikingBrain } from "./spiking.js";

const PAYLOAD_URL = "./data/brain_oculomotor.json", COST_URL = "./data/cost.json";
const TAU_MS = 200;                 // the unit's time constant this page declares
const RASTER_MS = 2000, RATE_MS = 500, BURST_MS = 200, MAX_FRAME_MS = 50;
const LEVEL = 0.3;                  // the settling drive level, the receipt's comparison level
const W_DEFAULT = 0.35;             // mV, the receipt's static weight
const W_RANGE = [0.1, 4.0], GAIN_RANGE = [0.1, 0.6];
const GAIN_MARKS = { decays: 0.22, ignites: 0.45 };   // page 2's presets; "holds" is the payload's gain
const ORDER = ["_Int_", "_DOs_", "ABD_m", "ABD_i"];
const RGB = { _Int_: [103, 231, 142], _DOs_: [90, 220, 190], ABD_m: [210, 255, 120], ABD_i: [60, 170, 160], other: [96, 148, 116] };  // brain_view.js's soma colours
const BURST = "255,209,102";
const FONT = "IBM Plex Mono, ui-monospace, monospace";
const AXIS_PX = 14;                 // the time or value axis under a pane, CSS px

const shell = mountShell("why", { status: "loading the two engines" });
$("page-title").textContent = shell.page.title;
renderParagraphs($("prose"), shell.page);
renderAdvantages(shell.page.advantages);
$("kept").textContent = shell.page.advantages.kept;
function fail(reason) { app.errors.push(`why: ${reason}`); shell.status(`engines unavailable: ${reason}`); $("loading").textContent = `engines unavailable: ${reason}`; }

let payload, cost, receipt;
try { [payload, cost, receipt] = await Promise.all([fetchJSON(PAYLOAD_URL), fetchJSON(COST_URL), fetchJSON(RECEIPT_URL)]); }
catch (e) { fail(String(e.message || e)); throw e; }
renderCost(cost, shell.page.advantages);
$("evidence").appendChild(spikingEvidence(receipt));

// the two engines on the one payload
const n = payload.n, kind = payload.kind, P = payload.populations;
const spike = new SpikingBrain(payload, { wSynMv: W_DEFAULT, seed: 1, historyMs: RASTER_MS });
const settle = new SettlingBrain(payload);
const STEP_MS = TAU_MS * settle.dt, SPIKE_STEPS_PER_SETTLE = Math.round(STEP_MS / spike.dtMs), STEPS_PER_SECOND = Math.round(1000 / STEP_MS);
const w0 = Float64Array.from(settle.w), gain0 = settle.gain;
const se = receipt.spiking.static_equivalence, critical = receipt.spiking.critical_weight_mv, ignited = receipt.spiking.ignited;

// rows: neurons grouped by class in ORDER, index order within a class; a class's members, colour and packed pixels
const rowOf = new Int32Array(n), classOf = new Int32Array(n), classRows = [];
{
  let r = 0;
  for (const cls of [...ORDER, ...kind.filter((k) => !ORDER.includes(k))]) {
    if (classRows.some((c) => c.cls === cls)) continue;
    const from = r, members = [];
    for (let i = 0; i < n; i++) if (kind[i] === cls) { rowOf[i] = r++; classOf[i] = classRows.length; members.push(i); }
    if (r > from) classRows.push({ cls, from, to: r, members, rgb: RGB[cls] || RGB.other });
  }
}
const pack = (rgb, a) => ((a << 24) | (rgb[2] << 16) | (rgb[1] << 8) | rgb[0]) >>> 0;   // RGBA bytes read as one little-endian word
for (const c of classRows) { c.color = `rgb(${c.rgb.join(",")})`; c.px = pack(c.rgb, 255); }
const pxOf = new Uint32Array(n);
for (let i = 0; i < n; i++) pxOf[i] = classRows[classOf[i]].px;

// the drives: index lists; the half is the first half of the integrator by index
const DRIVES = {
  int: { label: "integrator", idx: P._Int_ }, ves: { label: "vestibular", idx: P._DOs_ },
  half: { label: "half of the integrator", idx: P._Int_.slice(0, Math.ceil(P._Int_.length / 2)) }, none: { label: "none", idx: [] },
};
const driven = new Uint8Array(n);
let free = [];
const S = { paused: false, drive: "int", burstStep: -1, burstFromMs: -1, burstToMs: -1, carry: 0, rasterSteps: 0, w: W_DEFAULT, gain: gain0, cos: null, rho: null, fps: 0, frames: 0, meanRate: 0, meanAct: 0 };

function applyDrive(key) {
  S.drive = key;
  const idx = DRIVES[key].idx;
  spike.clearDrive();
  if (idx.length) spike.drive(idx, true);
  settle.clearStimuli();
  for (const i of idx) settle.setDrive(i, LEVEL);
  driven.fill(0);
  for (const i of idx) driven[i] = 1;
  free = [];
  for (let i = 0; i < n; i++) if (!driven[i]) free.push(i);
  for (const b of $("drive").querySelectorAll("button")) b.classList.toggle("on", b.dataset.drive === key);
  $("ag-tag").textContent = `${int(free.length)} of ${int(n)}`;
}
function burst() {
  const key = S.drive === "none" ? "int" : S.drive;
  applyDrive(key);
  S.burstStep = spike.steps + Math.round(BURST_MS / spike.dtMs);
  S.burstFromMs = spike.t; S.burstToMs = -1;
  if (S.paused) setPaused(false);
  refreshControls();
}
function release() { S.burstStep = -1; S.burstToMs = spike.t; applyDrive("none"); refreshControls(); }
function setWeight(w) { w = Math.min(W_RANGE[1], Math.max(W_RANGE[0], w)); S.w = w; spike.setWeight(w); $("w").value = String(w); $("w-v").textContent = `${num(w, 3)} mV`; }
function setGain(g) { g = Math.min(GAIN_RANGE[1], Math.max(GAIN_RANGE[0], g)); S.gain = g; const f = g / gain0; for (let e = 0; e < w0.length; e++) settle.w[e] = w0[e] * f; $("g").value = String(g); $("g-v").textContent = num(g, 4); }
function setPaused(flag) { S.paused = flag; refreshControls(); status(); }
function reset() {
  spike.reset(); settle.reset();
  Object.assign(S, { carry: 0, rasterSteps: 0, burstStep: -1, burstFromMs: -1, burstToMs: -1 });
  raster.clear(); trail.clear();
  refreshControls(); status();
}
function refreshControls() {
  const running = S.burstStep >= 0;
  $("burst").classList.toggle("on", running);
  $("burst").textContent = running ? "burst running" : "burst 200 ms then free";
  $("pause").textContent = S.paused ? "resume" : "pause";
  $("pause").classList.toggle("on", S.paused);
}

/** Both engines forward by `ms` of fish time: spiking steps of 0.1 ms, a settling step after every 400 of them. */
function advance(ms) {
  S.carry += ms;
  const steps = Math.floor(S.carry / spike.dtMs);
  S.carry -= steps * spike.dtMs;
  for (let s = 0; s < steps; s++) {
    if (S.burstStep >= 0 && spike.steps >= S.burstStep) release();
    spike.step();
    if (spike.steps % SPIKE_STEPS_PER_SETTLE === 0) { settle.step(); trailStep(); }
  }
}

// the panes: a canvas whose plot is a pixel buffer with one row (or more) of device pixels per neuron
const dprOf = () => Math.min(2, devicePixelRatio || 1);
for (const row of document.querySelectorAll("#engines .row")) row.style.height = `${n + AXIS_PX}px`;
class Pane {
  constructor(canvas, marginLeft) { this.canvas = canvas; this.ml = marginLeft; this.resize(); }
  resize() {
    const c = this.canvas, dpr = dprOf();
    c.width = Math.round(Math.max(20, c.clientWidth) * dpr); c.height = Math.round(Math.max(20, c.clientHeight) * dpr);
    this.dpr = dpr; this.ML = Math.round(this.ml * dpr); this.MB = Math.round(AXIS_PX * dpr);
    this.W = Math.max(1, c.width - this.ML - Math.round(2 * dpr)); this.H = Math.max(1, c.height - this.MB);
    this.g = c.getContext("2d");
    const rowH = this.H / n;
    this.rowH = rowH; this.top = new Int32Array(n); this.end = new Int32Array(n);
    for (let r = 0; r < n; r++) { this.top[r] = Math.floor(r * rowH); this.end[r] = Math.max(this.top[r] + 1, Math.floor((r + 1) * rowH)); }
    const buf = new ArrayBuffer(this.W * this.H * 4);
    this.out = new Uint32Array(buf); this.img = new ImageData(new Uint8ClampedArray(buf), this.W, this.H);
  }
  /** The buffer onto the canvas, then the class lines, the driven marks and the axis words. */
  present(left, middle, right) {
    const g = this.g, c = this.canvas, W = this.W, H = this.H, ML = this.ML, dpr = this.dpr;
    g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, c.width, c.height);
    g.putImageData(this.img, ML, 0);
    g.strokeStyle = "rgba(200,255,216,.28)"; g.lineWidth = 1;
    for (const cr of classRows.slice(1)) { const y = this.top[cr.from] + 0.5; g.beginPath(); g.moveTo(ML, y); g.lineTo(ML + W, y); g.stroke(); }
    if (ML) {
      g.fillStyle = `rgb(${BURST})`;
      let r = 0;
      while (r < n) {
        if (!driven[rowNeuron[r]]) { r++; continue; }
        let to = r; while (to < n && driven[rowNeuron[to]]) to++;
        g.fillRect(0, this.top[r], Math.max(1, ML - Math.round(2 * dpr)), this.end[to - 1] - this.top[r]);
        r = to;
      }
    }
    g.fillStyle = "#679774"; g.font = `${10 * dpr}px ${FONT}`; g.textBaseline = "top";
    g.textAlign = "left"; g.fillText(left, ML, H + 3 * dpr);
    if (middle) { g.textAlign = "center"; g.fillText(middle, ML + W / 2, H + 3 * dpr); }
    g.textAlign = "right"; g.fillText(right, ML + W, H + 3 * dpr);
  }
}
const rowNeuron = new Int32Array(n);
for (let i = 0; i < n; i++) rowNeuron[rowOf[i]] = i;

/** A strip of the last RASTER_MS: a ring of columns, one per device pixel, presented with the newest column at the right edge. */
class Strip extends Pane {
  resize() { super.resize(); this.ring = new Uint32Array(this.W * this.H); this.msPerCol = RASTER_MS / this.W; this.lastCol = -1; }
  clear() { this.ring.fill(0); this.lastCol = -1; }
  col(tMs) { return Math.floor(tMs / this.msPerCol); }
  /** Clear the columns the clock passed since the last call, up to the column of tMs. */
  clearTo(tMs) {
    const c1 = this.col(tMs), W = this.W, H = this.H, ring = this.ring;
    if (this.lastCol < 0 || c1 - this.lastCol >= W) ring.fill(0);
    else for (let c = this.lastCol + 1; c <= c1; c++) { const x = c % W; for (let y = 0; y < H; y++) ring[y * W + x] = 0; }
    if (c1 > this.lastCol) this.lastCol = c1;
  }
  /** One pixel column of a neuron's rows. */
  plot(x, row, px) { const W = this.W, ring = this.ring; for (let y = this.top[row], end = this.end[row]; y < end; y++) ring[y * W + x] = px; }
  /** A neuron's rows across the ring columns [x0, x1). */
  band(x0, x1, row, px) { const W = this.W, ring = this.ring; for (let y = this.top[row], end = this.end[row]; y < end; y++) ring.fill(px, y * W + x0, y * W + x1); }
  /** The visible x of a time within the window, in device pixels. */
  x(tMs, nowMs) { return this.ML + this.W - 1 - (this.col(nowMs) - this.col(tMs)); }
  show(nowMs) {
    const W = this.W, H = this.H, ring = this.ring, out = this.out, right = (this.col(nowMs) % W) + 1;
    for (let y = 0; y < H; y++) {
      const base = y * W;
      out.set(ring.subarray(base + right, base + W), base);
      out.set(ring.subarray(base, base + right), base + W - right);
    }
    this.present("2 s ago", "1 s ago", "now");
    if (S.burstFromMs >= 0) {
      const x0 = Math.max(this.ML, this.x(S.burstFromMs, nowMs)), x1 = Math.min(this.ML + W, this.x(S.burstToMs < 0 ? nowMs : S.burstToMs, nowMs) + 1);
      if (x1 > x0) { this.g.fillStyle = `rgba(${BURST},.18)`; this.g.fillRect(x0, 0, x1 - x0, H); }
    }
  }
}
/** Horizontal bars, one per neuron, in the row order of the strips. */
class Bars extends Pane {
  draw(values, vmax, label) {
    const W = this.W, out = this.out;
    out.fill(0);
    for (let i = 0; i < n; i++) {
      const v = values[i]; if (!(v > 0)) continue;
      const len = Math.max(1, Math.min(W, Math.round((v / vmax) * W))), r = rowOf[i], px = pxOf[i];
      for (let y = this.top[r], end = this.end[r]; y < end; y++) out.fill(px, y * W, y * W + len);
    }
    this.present("0", null, label);
  }
}
const raster = new Strip($("raster"), 5), trail = new Strip($("trail"), 5);
const rateBars = new Bars($("rates"), 0), actBars = new Bars($("acts"), 0);
const scatter = $("scatter");

/** The spikes since the last frame onto the raster ring. */
function rasterFresh() {
  const fresh = spike.spikesSince(S.rasterSteps * spike.dtMs);
  S.rasterSteps = spike.steps;
  raster.clearTo(spike.t);
  const W = raster.W;
  for (let k = 0; k < fresh.times.length; k++) { const i = fresh.neurons[k]; raster.plot(raster.col(fresh.times[k]) % W, rowOf[i], pxOf[i]); }
}
/** The settling step just taken onto the trail ring: a band of one step, brightness the square root of the activity. */
function trailStep() {
  const T = settle.steps * STEP_MS, a = trail.col(T - STEP_MS) + 1, b = trail.col(T), W = trail.W;
  trail.clearTo(T);
  if (b < a) return;  // the step did not reach a new column; the next one that does draws it
  const segs = [];
  if (b - a + 1 >= W) segs.push([0, W]);
  else { const xa = a % W, xb = b % W; if (xa <= xb) segs.push([xa, xb + 1]); else segs.push([xa, W], [0, xb + 1]); }
  const s = settle.s;
  for (let i = 0; i < n; i++) {
    const v = s[i]; if (!(v > 0.001)) continue;
    const px = pack(classRows[classOf[i]].rgb, Math.round(Math.min(1, Math.sqrt(v)) * 255));
    for (const [x0, x1] of segs) trail.band(x0, x1, rowOf[i], px);
  }
}

// the agreement over the neurons not driven: cosine of the two vectors, Spearman with average ranks for ties
function ranks(a) {
  const m = a.length, idx = Array.from({ length: m }, (_, i) => i).sort((p, q) => a[p] - a[q]), r = new Float64Array(m);
  let k = 0;
  while (k < m) { let j = k; while (j + 1 < m && a[idx[j + 1]] === a[idx[k]]) j++; const avg = (k + j) / 2 + 1; for (let t = k; t <= j; t++) r[idx[t]] = avg; k = j + 1; }
  return r;
}
function pearson(a, b) {
  const m = a.length; let ma = 0, mb = 0;
  for (let i = 0; i < m; i++) { ma += a[i]; mb += b[i]; }
  ma /= m; mb /= m;
  let sab = 0, saa = 0, sbb = 0;
  for (let i = 0; i < m; i++) { const x = a[i] - ma, y = b[i] - mb; sab += x * y; saa += x * x; sbb += y * y; }
  return saa > 0 && sbb > 0 ? sab / Math.sqrt(saa * sbb) : null;
}
function agreement(rate, act) {
  const m = free.length;
  if (m < 3) return { cos: null, rho: null };
  const a = new Float64Array(m), b = new Float64Array(m);
  let ab = 0, aa = 0, bb = 0;
  for (let k = 0; k < m; k++) { const i = free[k]; a[k] = rate[i]; b[k] = act[i]; ab += a[k] * b[k]; aa += a[k] * a[k]; bb += b[k] * b[k]; }
  return { cos: aa > 0 && bb > 0 ? ab / Math.sqrt(aa * bb) : null, rho: pearson(ranks(a), ranks(b)) };
}
function niceCeil(y) { const p = Math.pow(10, Math.floor(Math.log10(y))), f = y / p; return ([1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].find((m) => f <= m) || 10) * p; }

function drawScatter(rate, act, xmax, ymax) {
  const c = scatter, dpr = dprOf();
  const cw = Math.round(Math.max(20, c.clientWidth) * dpr), ch = Math.round(Math.max(20, c.clientHeight) * dpr);
  if (c.width !== cw || c.height !== ch) { c.width = cw; c.height = ch; }
  const g = c.getContext("2d");
  g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, cw, ch);
  const ML = Math.round(34 * dpr), MR = Math.round(10 * dpr), MT = Math.round(16 * dpr), MB = Math.round(18 * dpr), W = cw - ML - MR, H = ch - MT - MB;
  g.strokeStyle = "rgba(97,186,121,.35)"; g.lineWidth = 1;
  g.beginPath(); g.moveTo(ML + 0.5, MT); g.lineTo(ML + 0.5, MT + H + 0.5); g.lineTo(ML + W, MT + H + 0.5); g.stroke();
  g.fillStyle = "#679774"; g.font = `${10 * dpr}px ${FONT}`;
  g.textAlign = "right"; g.textBaseline = "middle"; g.fillText(num(ymax, 2), ML - 4 * dpr, MT); g.fillText("0", ML - 4 * dpr, MT + H);
  g.textAlign = "left"; g.textBaseline = "top"; g.fillText("0", ML, MT + H + 4 * dpr);
  g.textAlign = "right"; g.fillText(`${num(xmax, 3)} Hz over the last 500 ms`, ML + W, MT + H + 4 * dpr);
  g.textAlign = "left"; g.textBaseline = "bottom"; g.fillText("activity now", ML + 4 * dpr, MT - 2 * dpr);
  g.globalAlpha = 0.85;
  const r = 2 * dpr;
  classRows.forEach((cr, k) => {
    g.fillStyle = cr.color;
    for (const i of free) {
      if (classOf[i] !== k) continue;
      const x = ML + (Math.min(rate[i], xmax) / xmax) * W, y = MT + H - (Math.min(act[i], ymax) / ymax) * H;
      g.fillRect(x - r, y - r, 2 * r, 2 * r);
    }
  });
  g.globalAlpha = 1;
}

function draw() {
  const now = spike.t;
  rasterFresh();
  trail.clearTo(now);
  raster.show(now); trail.show(now);
  const rate = spike.rates(RATE_MS), act = settle.s;
  let rmax = 0, amax = 0, rsum = 0, asum = 0;
  for (let i = 0; i < n; i++) { if (rate[i] > rmax) rmax = rate[i]; if (act[i] > amax) amax = act[i]; rsum += rate[i]; asum += act[i]; }
  S.meanRate = rsum / n; S.meanAct = asum / n;
  const rscale = niceCeil(Math.max(rmax, 10)), ascale = niceCeil(Math.max(amax, 0.01));
  rateBars.draw(rate, rscale, `${num(rscale, 3)} Hz`);
  actBars.draw(act, ascale, num(ascale, 2));
  const { cos, rho } = agreement(rate, act);
  S.cos = cos; S.rho = rho;
  $("cos").textContent = cos == null ? "n/a" : num(cos, 3);
  $("rho").textContent = rho == null ? "n/a" : num(rho, 3);
  let xmax = 10, ymax = 0.1;
  for (const i of free) { if (rate[i] > xmax) xmax = rate[i]; if (act[i] > ymax) ymax = act[i]; }
  drawScatter(rate, act, niceCeil(xmax), niceCeil(ymax));
  if (S.frames % 6 === 0) {
    $("sp-tag").textContent = `${(now / 1000).toFixed(2)} s · ${int(spike.steps)} steps`;
    $("se-tag").textContent = `${(settle.steps * STEP_MS / 1000).toFixed(2)} s · ${int(settle.steps)} steps`;
    $("sp-foot").textContent = `rate over the last 500 ms · mean ${num(S.meanRate, 3)} Hz · ${S.w} mV`;
    $("se-foot").textContent = `activation now · mean ${num(S.meanAct, 3)} · gain ${num(S.gain, 4)}`;
  }
}
function status() {
  const d = DRIVES[S.drive].label;
  shell.status(`fish time ${(spike.t / 1000).toFixed(1)} s · drive ${d}${S.burstStep >= 0 ? " (burst)" : ""} · weight ${num(S.w, 3)} mV · gain ${num(S.gain, 4)} · cosine ${S.cos == null ? "n/a" : num(S.cos, 3)} · Spearman ${S.rho == null ? "n/a" : num(S.rho, 3)} · ${Math.round(S.fps)} fps${S.paused ? " · paused" : ""}`);
}

// the static content: the advantages, the cost table, the marks, the legend, the card
function renderAdvantages(adv) {
  $("adv-title").textContent = adv.title;
  $("advantages").replaceChildren(...adv.items.map((text) => {
    const cut = text.indexOf(". ");
    return cut > 0 ? el("li", {}, el("b", {}, text.slice(0, cut + 1)), text.slice(cut + 1)) : el("li", {}, text);
  }));
}
function renderCost(c, adv) {
  const names = { "brain_oculomotor.json": "oculomotor circuit", "brain.json": "whole hindbrain", "larva_brain.json": "Platynereis whole body" };
  const keys = Object.keys(c.payloads).sort((a, b) => c.payloads[a].neurons - c.payloads[b].neurons);
  const ps = keys.map((k) => c.payloads[k]);
  const weights = [...new Set(ps.flatMap((p) => Object.keys(p.spiking)))].sort((a, b) => parseFloat(a.slice(2)) - parseFloat(b.slice(2)));
  const first = ps[0];
  const rows = [
    ["represented cells · synapse classes", (p) => `${int(p.neurons)} · ${int(p.classes)}`],
    ["settling: ms per step", (p) => num(p.settling.ms_per_step, 3)],
    [`settling: ms per simulated second at the declared constant (${int(first.settling.steps_per_fish_second_declared)} steps)`, (p) => num(p.settling.ms_per_fish_second_declared, 3)],
    [`settling: ms per simulated second at a 20 ms constant (${int(first.settling.steps_per_fish_second_tau20ms)} steps)`, (p) => num(p.settling.ms_per_fish_second_tau20ms, 3)],
    ...weights.map((w) => [`spiking at ${w.slice(2).replace("_mV", " mV")}: ms per simulated second (${int(first.spiking[w].steps_per_fish_second)} steps)`, (p) => (p.spiking[w] ? `${num(p.spiking[w].ms_per_fish_second, 3)} at a mean rate of ${num(p.spiking[w].mean_rate_hz, 3)} Hz` : "n/a")]),
    ["spiking (0.35 mV) / settling at 200 ms", (p) => `${num(p.ratio_declared, 3)}×`],
    ["spiking (0.35 mV) / settling at 20 ms", (p) => `${num(p.ratio_tau20ms, 3)}×`],
  ];
  $("cost").querySelector("thead").replaceChildren(el("tr", {}, el("th", {}, "measure"), ...keys.map((k) => el("th", { class: "num" }, names[k] || k, el("small", {}, k)))));
  $("cost").querySelector("tbody").replaceChildren(...rows.map(([label, f]) => el("tr", {}, el("td", {}, label), ...ps.map((p) => el("td", { class: "num" }, f(p))))));
  $("cost-note").textContent = adv.costNote;
  $("cost-receipt").textContent = `${c.note}; measured with node ${c.node} on ${c.date}.`;
}
function marks(host, range, items) {
  host.replaceChildren(...items.map(([value, label, warm]) => el("i", { class: warm ? "warm" : null, style: `left:${(100 * (value - range[0])) / (range[1] - range[0])}%` }, label)));
}
marks($("w-marks"), W_RANGE, [[W_DEFAULT, `${W_DEFAULT} static`], [critical, `${critical} ignites`, true]]);
marks($("g-marks"), GAIN_RANGE, [[GAIN_MARKS.decays, "decays"], [gain0, "holds"], [GAIN_MARKS.ignites, "ignites", true]]);
$("legend").replaceChildren(
  ...classRows.map((c) => el("span", {}, el("i", { style: `background:${c.color}` }), `${CLASS_NAMES[c.cls] || c.cls} ${int(c.to - c.from)}`)),
  el("span", { class: "warm" }, el("i", { style: `background:rgb(${BURST})` }), "driven rows, the burst window"));
$("agree-receipt").textContent = `· stored six-trial comparison: ${num(se.cosine, 3)} and ${num(se.spearman, 3)} over ${int(se.neurons_compared)} neurons`;
shell.card([
  `<b>The data.</b> ${payload.source}: the oculomotor circuit, ${int(n)} neurons and ${int(payload.edges)} synapse classes carrying ${int(payload.synapses)} synapses. Classes: ${classRows.map((c) => `${CLASS_NAMES[c.cls] || c.cls} ${int(c.to - c.from)}`).join(", ")}. The vestibular senders are inhibitory, every other sender excitatory.`,
  `<b>The spiking engine.</b> spiking.js, the leaky integrate-and-fire port the compiler verifies against: membrane ${spike.tMbrMs} ms, synapse ${spike.tauMs} ms, threshold ${spike.vThMv} mV, refractory ${spike.tRfcMs} ms, delay ${spike.tDlyMs} ms, steps of ${spike.dtMs} ms. A spike adds the weight times the signed synapse count to every target; a driven neuron receives Poisson events at ${spike.rPoiHz} Hz, each a kick of the weight times ${spike.fPoi}, and has no refractory period. The slider sets the weight; the receipt found the net ignites at ${critical} mV.`,
  `<b>The settling engine.</b> brain.js, the Cadence ${payload.library?.version ?? ""} rate model: every neuron one activity in [0, 1], a rectified sigmoid of slope ${settle.slope} at threshold ${settle.threshold}, a step of dt ${settle.dt} of the unit's time constant. This page declares the constant as ${TAU_MS} ms, so a step is ${STEP_MS} ms of fish time and a simulated second is ${STEPS_PER_SECOND} steps; a settling step is taken after every ${int(SPIKE_STEPS_PER_SETTLE)} spiking steps. A synapse weighs the gain times its count, negative from an inhibitory sender; the slider rescales every weight by the new gain over the payload's ${num(gain0, 4)}. A driven neuron's stimulus is level ${LEVEL} of the amplitude ${settle.amplitude}, the level the receipt's comparison used.`,
  `<b>The comparison.</b> The scatter takes the neurons that are not driven: their rate over the last ${RATE_MS} ms against their activation now; the cosine and the Spearman correlation are computed on this page every frame. The receipt (data/receipt_oculomotor.json) holds a cosine of ${num(se.cosine, 3)} and a Spearman of ${num(se.spearman, 3)} over ${int(se.neurons_compared)} undriven neurons, the integrator driven across six trials at ${receipt.spiking.static_weight_mv} mV for a second against a 3000-step rate run at level ${LEVEL} and exact receipt gain ${receipt.wirings.measured.selected_gain}; at ${critical} mV the ignited spiking pattern matches the patch net's held state at a cosine of ${num(ignited.cos_rate_held, 3)}. The cost table reads data/cost.json.`,
  sourcesList(),
]);

// the controls
for (const b of $("drive").querySelectorAll("button")) b.onclick = () => { S.burstStep = -1; applyDrive(b.dataset.drive); refreshControls(); status(); };
$("burst").onclick = burst;
$("pause").onclick = () => setPaused(!S.paused);
$("reset").onclick = reset;
$("w").addEventListener("input", (e) => { setWeight(Number(e.target.value)); status(); });
$("g").addEventListener("input", (e) => { setGain(Number(e.target.value)); status(); });
addEventListener("resize", () => { raster.resize(); trail.resize(); rateBars.resize(); actBars.resize(); });
applyDrive("int");
setWeight(W_DEFAULT); setGain(gain0);
refreshControls();
$("loading").classList.add("gone");

// the loop: fish time from the wall clock, capped per frame; every frame draws
let last = performance.now(), winStart = last, winFrames = 0;
function frame(now) {
  requestAnimationFrame(frame);
  const dt = now - last;
  last = now;
  if (!S.paused) advance(Math.min(dt, MAX_FRAME_MS));
  draw();
  S.frames++; winFrames++;
  if (now - winStart >= 1000) { S.fps = (winFrames * 1000) / (now - winStart); winStart = now; winFrames = 0; $("fps").textContent = `${Math.round(S.fps)} fps`; status(); }
  if (!app.ready && S.frames >= 3) app.ready = true;
}
requestAnimationFrame(frame);
Object.assign(app, { burst, reset, setPaused, setWeight, setGain, setDrive: (key) => { S.burstStep = -1; applyDrive(key); refreshControls(); status(); }, spike, settle,
  state: () => ({ fishMs: spike.t, spikeSteps: spike.steps, settleSteps: settle.steps, drive: S.drive, burst: S.burstStep >= 0, w: S.w, gain: S.gain, cos: S.cos, rho: S.rho, compared: free.length, meanRate: S.meanRate, meanAct: S.meanAct, fps: S.fps, paused: S.paused }) });
