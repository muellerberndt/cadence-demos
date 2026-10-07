// Page 2: the compiled brainstem settling in a worker, the gain free, a burst to the integrator,
// a strip chart of the left half's readouts over the last 800 steps, the brain view lit by the
// left half's activity. One brain step is dt of the unit's time constant; time is counted in steps.
import { mountShell, app, el, $, renderParagraphs, int, num, describePayload, sourcesList, SKELETONS_URL, SKELETONS_FALLBACK, BRAIN_URL } from "./site.js";
import { BrainView, loadPayload, HOT } from "./brain_view.js";

const WINDOW = 800, BURST_STEPS = 20, BURST_LEVEL = 0.03, MAX_RUN = 64;
const PRESETS = { low: 0.22, high: 0.45 }; // critical is the payload's gain
const SERIES = [["int", "integrator", "--int"], ["m", "abducens motor", "--abdm"], ["i", "abducens internuclear", "--abdi"]];
const shell = mountShell("paste", { status: "loading the brain" });
$("page-title").textContent = shell.page.title;
renderParagraphs($("prose"), shell.page);

const S = { ready: false, inflight: false, paused: false, speed: 25, due: 0, light: 20, gain: null, gain0: null, pendingGain: null, steps: 0, expected: 0, burstLeft: 0, burstOn: false, burstEnd: -1, p200: null, p600: null, active: 0, readouts: { _Int_: 0, ABD_m: 0, ABD_i: 0 } };
const hist = { step: [], int: [], m: [], i: [], burst: [] };
let meta = null, scaled = null;

// the view
const skeletons = await loadPayload(SKELETONS_URL).catch(() => loadPayload(SKELETONS_FALLBACK));
const view = new BrainView($("view-host"), skeletons, { spin: true });
addEventListener("resize", () => { view.resize(); drawChart(); });
$("fit").onclick = () => view.fit();
$("spin").onclick = () => { view.options.spin = !view.options.spin; $("spin").classList.toggle("on", view.options.spin); };
$("view-foot").textContent = `${int(skeletons.counts.skeletons)} skeletons drawn · activity times the view light`;

// the brain in its worker
const worker = new Worker("./paste_worker.js", { type: "module" });
worker.onmessage = (e) => {
  const m = e.data;
  if (m.type === "ready") onReady(m);
  else if (m.type === "state") onState(m);
  else if (m.type === "gain") { S.gain = m.gain; refreshGain(); }
  else if (m.type === "error") fail(m.reason);
};
worker.onerror = (e) => fail(e.message || "worker error");
worker.postMessage({ type: "init", url: BRAIN_URL });
function fail(reason) { app.errors.push(`worker: ${reason}`); shell.status(`brain unavailable: ${reason}`); $("loading").textContent = `brain unavailable: ${reason}`; }

function onReady(m) {
  meta = m.meta;
  S.gain = S.gain0 = S.sentGain = m.gain;
  scaled = new Float32Array(m.n);
  $("gain").value = String(S.gain0);
  refreshGain();
  $("l-int").textContent = `integrator mean (${int(m.populations._Int_ || 0)} cells)`;
  $("l-m").textContent = `abducens motor mean (${int(m.populations.ABD_m || 0)})`;
  $("l-i").textContent = `abducens internuclear mean (${int(m.populations.ABD_i || 0)})`;
  shell.card([
    ...describePayload(meta),
    `<b>This page.</b> Two copies of the compiled half-brainstem settle in a worker (twin.js); the burst goes to the left copy's integrator, at level ${BURST_LEVEL} of the stimulus amplitude for ${BURST_STEPS} steps, and the chart and the view read the left copy. The gain slider rescales every weight by the new gain over the old one and keeps the state; the preset "critical" is the gain the protocol selected, ${num(S.gain0, 6)}. The persistence line reads the integrator mean 200 and 600 steps after the burst, the protocol's training fact.`,
    sourcesList(),
  ]);
  $("loading").classList.add("gone");
  S.ready = true;
  burst();
}

// the gain: the slider posts a rebuild at most every 80 ms, a preset at once; a burst flushes a
// pending request first so it runs at the gain shown. The persistence readout belongs to one gain.
let gainTimer = 0;
function requestGain(g, immediate = false) {
  g = Math.min(0.6, Math.max(0.1, g));
  S.pendingGain = g;
  $("gain").value = String(g);
  $("gain-v").textContent = num(g, 4);
  S.burstEnd = -1; S.p200 = S.p600 = null;
  updateReadouts();
  if (immediate) flushGain();
  else if (!gainTimer) gainTimer = setTimeout(flushGain, 80);
}
function flushGain() {
  if (gainTimer) { clearTimeout(gainTimer); gainTimer = 0; }
  if (S.pendingGain == null || S.pendingGain === S.sentGain) return;
  S.sentGain = S.pendingGain;
  worker.postMessage({ type: "gain", gain: S.pendingGain });
}
function refreshGain() {
  $("gain-v").textContent = num(S.gain, 4);
  for (const b of $("presets").querySelectorAll("button")) {
    const target = b.dataset.preset === "critical" ? S.gain0 : PRESETS[b.dataset.preset];
    b.classList.toggle("on", Math.abs(S.gain - target) < 5e-4);
  }
  status();
}
$("gain").addEventListener("input", (e) => requestGain(Number(e.target.value)));
for (const b of $("presets").querySelectorAll("button")) b.onclick = () => requestGain(b.dataset.preset === "critical" ? S.gain0 : PRESETS[b.dataset.preset], true);
for (const b of $("speed").querySelectorAll("button")) b.onclick = () => setSpeed(Number(b.dataset.speed));
for (const b of $("light").querySelectorAll("button")) b.onclick = () => setLight(Number(b.dataset.light));
function setSpeed(v) { S.speed = v; for (const b of $("speed").querySelectorAll("button")) b.classList.toggle("on", Number(b.dataset.speed) === v); status(); }
function setLight(v) { S.light = v; for (const b of $("light").querySelectorAll("button")) b.classList.toggle("on", Number(b.dataset.light) === v); if (S.lastLeft) lightView(S.lastLeft); }

function burst() { flushGain(); S.burstLeft = BURST_STEPS; S.burstEnd = -1; S.p200 = S.p600 = null; if (S.paused) setPaused(false); updateReadouts(); }
function setPaused(flag) { S.paused = flag; $("pause").textContent = flag ? "resume" : "pause"; $("pause").classList.toggle("on", flag); status(); }
function reset() {
  worker.postMessage({ type: "reset" });
  for (const k of Object.keys(hist)) hist[k].length = 0;
  Object.assign(S, { due: 0, burstLeft: 0, burstOn: false, burstEnd: -1, p200: null, p600: null, steps: 0, expected: 0, active: 0, readouts: { _Int_: 0, ABD_m: 0, ABD_i: 0 } });
  drawChart(); updateReadouts();
}
$("burst").onclick = burst;
$("pause").onclick = () => setPaused(!S.paused);
$("reset").onclick = reset;

// the run loop: the steps due from the wall clock, one request in flight, the burst honoured
function requestSteps() {
  let steps = Math.floor(S.due), stimuli = null;
  if (S.burstLeft > 0) { steps = Math.min(steps, S.burstLeft); stimuli = { left: { _Int_: BURST_LEVEL } }; }
  if (steps < 1) return;
  S.inflight = true;
  S.due -= steps;
  S.expected = S.steps + steps;
  S.burstOn = !!stimuli;
  if (stimuli) { S.burstLeft -= steps; if (S.burstLeft === 0) S.burstEnd = S.expected; }
  worker.postMessage({ type: "run", steps, stimuli });
}
function onState(m) {
  S.inflight = false;
  if (m.steps === 0 && !m.trace.length) { S.lastLeft = m.left; lightView(m.left); return; } // after a reset
  const from = S.steps;
  S.steps = m.steps;
  const t = m.trace, k = t.length / 4;
  for (let j = 0; j < k; j++) {
    const s = from + j + 1;
    hist.step.push(s); hist.int.push(t[4 * j]); hist.m.push(t[4 * j + 1]); hist.i.push(t[4 * j + 2]); hist.burst.push(S.burstOn ? 1 : 0);
    if (S.burstEnd > 0) { if (s === S.burstEnd + 200) S.p200 = t[4 * j]; if (s === S.burstEnd + 600) S.p600 = t[4 * j]; }
  }
  const extra = hist.step.length - WINDOW;
  if (extra > 0) for (const key of Object.keys(hist)) hist[key].splice(0, extra);
  const left = m.sides && m.sides.left;
  if (left) { S.readouts = left.readouts; S.active = left.active; }
  S.lastLeft = m.left;
  lightView(m.left);
  drawChart(); updateReadouts(); status();
}
function lightView(left) {
  for (let i = 0; i < left.length; i++) { const a = left[i] * S.light; scaled[i] = a > 1 ? 1 : a; }
  view.setActivity(scaled);
}

// the readouts and the status strip
function updateReadouts() {
  const r = S.readouts;
  $("r-step").textContent = int(S.steps);
  $("r-int").textContent = num(r._Int_ || 0, 3);
  $("r-m").textContent = num(r.ABD_m || 0, 3);
  $("r-i").textContent = num(r.ABD_i || 0, 3);
  $("r-active").textContent = meta ? `${int(S.active)} of ${int(meta.n)}` : "0";
  const p = $("r-persist");
  p.className = "muted";
  if (S.burstLeft > 0) p.textContent = "burst running";
  else if (S.burstEnd < 0) p.textContent = S.steps ? "no burst at this gain yet" : "no burst yet";
  else if (S.p200 == null) p.textContent = `waiting for +200 steps (${int(Math.min(200, S.steps - S.burstEnd))} of 200)`;
  else if (S.p600 == null) p.textContent = `integrator at +200 steps ${num(S.p200, 3)} · waiting for +600 (${int(Math.min(600, S.steps - S.burstEnd))} of 600)`;
  else {
    const ratio = S.p200 > 0 ? S.p600 / S.p200 : 0, pass = ratio >= 0.25 && S.p200 > 0;
    p.className = pass ? "pass" : "fail";
    p.textContent = `integrator at +200 steps ${num(S.p200, 3)} · at +600 ${num(S.p600, 3)} · ratio ${num(ratio, 3)} · T1 asks for at least 0.25: ${pass ? "holds" : "fails"}`;
  }
}
function status() {
  if (!meta) return;
  const r = S.readouts;
  shell.status(`step ${int(S.steps)} · gain ${num(S.gain, 4)} · ${S.speed} steps/s · integrator ${num(r._Int_ || 0, 3)} · active (≥ ${HOT}) ${int(S.active)} of ${int(meta.n)} · view light ×${S.light}${S.paused ? " · paused" : ""}`);
}

// the strip chart: the three means over the last 800 steps, the burst steps shaded
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
function niceCeil(y) { const p = Math.pow(10, Math.floor(Math.log10(y))), f = y / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p; }
function drawChart() {
  const c = $("chart"), dpr = Math.min(2, devicePixelRatio || 1), W = Math.max(10, c.clientWidth), H = Math.max(10, c.clientHeight);
  if (c.width !== Math.round(W * dpr) || c.height !== Math.round(H * dpr)) { c.width = Math.round(W * dpr); c.height = Math.round(H * dpr); }
  const g = c.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, W, H);
  const L = 48, R = 10, T = 10, B = 20, w = W - L - R, h = H - T - B, m = hist.step.length;
  let ymax = 0;
  for (const [key] of SERIES) for (const y of hist[key]) if (y > ymax) ymax = y;
  ymax = niceCeil(Math.max(ymax, 0.005));
  const x = (k) => L + (w * k) / (WINDOW - 1), y = (v) => T + h - (h * Math.min(v, ymax)) / ymax;
  g.fillStyle = "rgba(255,209,102,.14)";
  for (let k = 0; k < m; k++) if (hist.burst[k]) g.fillRect(x(k), T, Math.max(1, w / (WINDOW - 1)), h);
  g.strokeStyle = "rgba(97,186,121,.25)"; g.lineWidth = 1;
  g.fillStyle = "#679774"; g.font = "10px IBM Plex Mono, ui-monospace, monospace"; g.textAlign = "right"; g.textBaseline = "middle";
  for (const f of [0, 0.5, 1]) { const yy = y(f * ymax); g.beginPath(); g.moveTo(L, yy); g.lineTo(L + w, yy); g.stroke(); g.fillText(num(f * ymax, 2), L - 6, yy); }
  g.textAlign = "left"; g.textBaseline = "top";
  if (m) { g.fillText(`step ${int(hist.step[0])}`, L, T + h + 5); g.textAlign = "right"; g.fillText(`step ${int(hist.step[m - 1])}`, L + w, T + h + 5); }
  else { g.fillText("steps", L, T + h + 5); }
  for (const [key, , color] of SERIES) {
    g.strokeStyle = css(color) || "#67e78e"; g.lineWidth = 1.5; g.beginPath();
    for (let k = 0; k < m; k++) { const xx = x(k), yy = y(hist[key][k]); if (k === 0) g.moveTo(xx, yy); else g.lineTo(xx, yy); }
    g.stroke();
  }
  $("legend").replaceChildren(...SERIES.map(([key, label, color]) => el("span", {}, el("i", { style: `background:var(${color})` }), `${label} ${num(m ? hist[key][m - 1] : 0, 3)}`)), el("span", { class: "warm" }, el("i", { style: "background:rgba(255,209,102,.5)" }), "burst steps"));
}
drawChart();

// the loop: steps due from the wall clock, the view every frame
let last = performance.now(), windowStart = last, windowFrames = 0, frames = 0;
function frame(now) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.25, (now - last) / 1000);
  last = now;
  if (S.ready && !S.paused) {
    S.due = Math.min(S.due + S.speed * dt, MAX_RUN);
    if (!S.inflight && S.due >= 1) requestSteps();
  }
  view.render(dt);
  frames++; windowFrames++;
  if (now - windowStart >= 1000) { $("fps").textContent = `${Math.round((windowFrames * 1000) / (now - windowStart))} fps · lit ${view.activeCount}`; windowStart = now; windowFrames = 0; }
  if (!app.ready && S.ready && frames >= 3) app.ready = true;
}
requestAnimationFrame(frame);
Object.assign(app, { view, burst, reset, setSpeed, setLight, setGain: requestGain, setPaused, state: () => ({ steps: S.steps, gain: S.gain, speed: S.speed, readouts: S.readouts, active: S.active, p200: S.p200, p600: S.p600, burstEnd: S.burstEnd, samples: hist.step.length }) });
