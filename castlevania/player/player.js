// Two recordings. Brain + look-ahead: the highlights video (game, choice and brain view drawn into
// each frame), with the page's explanations over its parts. Brain alone: the video of one game,
// and beside it the brain view (brain.js, a copy of ../web/brain.js) driven by the decision the
// video is showing. The trace (pack/trace.json.gz) holds, per decision, the
// first video frame it covers, the eye's exact input and the brain's recorded state. Live mode runs
// the brain itself in a worker (Pyodide, the released wheel) on those inputs, in order, and checks
// its chosen buttons against the recording.
const $ = (id) => document.getElementById(id);
const PACK_ROOT = new URL(document.querySelector('meta[name="cadence-pack"]')?.content || "pack/", document.baseURI).href;
const SLICES = { scene: [0, 192], motion: [192, 384], ahead: [384, 576], body: [576, 588], behind: [588, 780],
  stage: [780, 798], block: [798, 802], state: [802, 812], floor: [812, 827] };
const SLOT_NAMES = [["horizontal", ["left", "-", "right"]], ["vertical", ["up", "-", "down"]], ["whip", ["no", "yes"]], ["jump", ["no", "yes"]]];
const ACTIONS = []; for (const h of [-1, 0, 1]) for (const v of [-1, 0, 1]) for (const w of [0, 1]) for (const j of [0, 1]) ACTIONS.push([h, v, w, j]);
const video = $("video"), view = new BrainView($("brainview"), { hoverCards: false });
const state = { rec: "lookahead", ready: false, frame: 0, decision: -1, shown: -1, source: "recorded", frameTimes: [],
  live: { on: false, ready: false, next: 0, done: 0, busy: false, results: new Map(), matches: 0, checked: 0, ms: [] } };
window.__player = state;
let trace = null, frames = null, manifest = null, worker = null;

async function sha256(bytes) {
  if (!crypto.subtle) return null;
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map((b) => b.toString(16).padStart(2, "0")).join("");
}
async function fetchChecked(url, expected) {
  const r = await fetch(url); if (!r.ok) throw new Error(`cannot load ${url}`);
  const bytes = new Uint8Array(await r.arrayBuffer());
  const got = await sha256(bytes);
  if (expected && got && got !== expected) throw new Error(`${url} does not match its manifest`);
  return bytes;
}
function f64(b64) { const s = atob(b64), u = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); return new Float64Array(u.buffer); }

// a recorded decision as the brain view's snapshot: the eye maps rebuilt from the exact input,
// the recall view's thumbnails from the decisions that saw those frames
function snapshotOf(k, live) {
  const rec = trace.decisions[k], base = live || rec.snap, x = f64(rec.x);
  const s = Object.assign({}, base);
  s.eye = {}; for (const [name, [a, b]] of Object.entries(SLICES)) s.eye[name] = Array.from(x.subarray(a, b));
  s.fovea = rec.snap.fovea; s.game = rec.snap.game;
  if (s.memory && s.memory.top) s.memory = Object.assign({}, s.memory, { top: s.memory.top.map((t) => Object.assign({}, t, { thumb: (trace.decisions[t.decision] || {}).thumb })) });
  return s;
}
function decisionAt(frame) {
  let lo = 0, hi = frames.length - 1;
  if (frame < frames[0]) return 0;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (frames[mid] <= frame) lo = mid; else hi = mid - 1; }
  return lo;
}
function drawSlots(probs, act) {
  const chosen = [act[0] + 1, act[1] + 1, act[2], act[3]];
  $("slots").innerHTML = probs.map((p, k) => {
    const [name, labels] = SLOT_NAMES[k];
    const bars = p.map((v, j) => `<div class="bar${j === chosen[k] ? " win" : ""}"><i style="width:${(100 * v).toFixed(0)}%"></i><em>${labels[j]} ${v.toFixed(2)}</em></div>`).join("");
    return `<div class="slot"><span>${name}</span><div class="bars">${bars}</div></div>`;
  }).join("");
}
function showDecision(k) {
  const live = state.live.on ? state.live.results.get(k) : null;
  const snap = snapshotOf(k, live ? live.snap : null);
  view.setSnap(snap);
  state.shown = k; state.source = live ? "live" : "recorded";
  const g = snap.game || {};
  $("stats").innerHTML = [["stage", g.stage], ["block", g.block], ["world x", g.world_x], ["health", g.health], ["lives", g.lives], ["decision", k]]
    .map(([a, b]) => `<span>${a} <b>${b ?? "-"}</b></span>`).join("");
  document.querySelectorAll("#pad [data-b]").forEach((el) => el.classList.toggle("lit", snap.buttons.includes(el.dataset.b)));
  drawSlots(snap.probs, snap.act);
  $("settle").textContent = `${snap.sweeps} sweeps`;
  $("source").textContent = live ? "live: settled in this tab" : "recorded";
}

// the video's frame: requestVideoFrameCallback gives the exact media time where the browser has it
let mediaTime = 0, mediaAt = 0;
if ("requestVideoFrameCallback" in HTMLVideoElement.prototype) {
  const cb = (now, meta) => { mediaTime = meta.mediaTime; mediaAt = now; video.requestVideoFrameCallback(cb); };
  video.requestVideoFrameCallback(cb);
}
function currentFrame(now) {
  let t = video.currentTime;
  if (mediaAt && !video.paused && Math.abs(mediaTime - t) < 0.25) t = mediaTime + (now - mediaAt) / 1000 * video.playbackRate;
  else if (mediaAt && video.paused) t = video.currentTime;
  return Math.max(0, Math.floor(t * trace.fps + 1e-6));
}
let last = 0;
function loop(now) {
  if (last) { state.frameTimes.push(now - last); if (state.frameTimes.length > 600) state.frameTimes.shift(); }
  last = now;
  if (trace) {
    const frame = currentFrame(now), k = decisionAt(frame);
    state.frame = frame; state.decision = k;
    const wantLive = state.live.on && state.live.results.has(k);
    if (k !== state.shown || (wantLive && state.source !== "live")) showDecision(k);
    const phase = Math.min(1, (frame - frames[k] + 1) / trace.settle_frames);
    view.draw(phase, now);
    if (state.live.on) feedLive(k);
  }
  requestAnimationFrame(loop);
}
function fitBrain() {
  const c = $("brainview"), w = c.clientWidth, ratio = window.devicePixelRatio || 1, [bw, bh] = window.BRAIN_VIEW_SIZE;
  if (!w) return;
  c.width = Math.round(w * ratio); c.height = Math.round(w * bh / bw * ratio);
  brainSpots();
}
window.addEventListener("resize", () => { fitBrain(); videoSpots(); });

// -- the explanations: what each part of the brain does, in the role it plays
const PARTS = {
  settle: ["The settle", "Each decision the whole brain settles: every neuron updates from the neurons it reads, sweep by sweep, until nothing changes. The line is the largest change in a sweep, falling to the dashed tolerance."],
  eye: ["Visual cortex: the eye", "What the eye sees at this decision, as four small maps: the whole screen, what moved since the last decision, and a sharp window ahead of Simon and one behind him (in the highlights, the red and blue boxes on the game)."],
  body: ["Body sense", "Simon's position, health, lives and facing, and which stage, block and floor he is on, read from the console's memory."],
  module_0: ["Module 0", "256 neurons that read the eye's maps and the body sense and pass on what they find."],
  association: ["Association", "128 neurons, the hub: every other region reads it and writes to it, so the eye, the memory and the motor strip come to agree here."],
  prefrontal: ["Prefrontal: working memory", "128 neurons that carry a trace of the last moments from one decision to the next. The brain never starts a decision from nothing: each settle begins from the state the last one left."],
  motor: ["Motor strip", "Ten motor neurons in four slots: left, none or right; up, none or down; whip or not; jump or not."],
  striatum: ["The choice", "Each slot's choice, from its motor neurons (the role of the striatum). The chosen buttons are held for 12 frames, a fifth of a second."],
  thalamus: ["Where the eye enters", "The eye's 827 readings enter the brain here; the glow is their mean."],
  hippocampus: ["Hippocampus: recall memory", "128 slots, each holding a moment of this game. Every decision the brain writes the moment it is in, and its two read heads read back the moments that match it (gold). The line counts the moments held. A new game empties it."],
  recalled: ["What it recalls", "What the memory's two read heads hand back to the brain at this decision, and what they expect to come next (the scene part of each)."],
  read: ["The moment recalled", "The game frame of the moment the brightest memory slot holds, and how many decisions ago it was."],
  lookahead: ["Brain or look-ahead", "Which move was played: the brain's own, the look-ahead's (amber) or route recovery's (teal), and the running shares of the three."],
  dopamine: ["Frozen", "Dopamine, arousal and plasticity at their true state: the brain plays frozen, so nothing in it learns while it plays."],
};
const VIDEO_PARTS = {  // the highlights' own layout (1280 x 720 units): the game, the choice, what was played
  game: [[12, 12, 612, 64], "The game", "NES Castlevania, as the brain plays it. The red box is the eye's sharp window ahead of Simon, the blue box the one behind him. A card marks each cut between the recorded stretches."],
  slots: [[12, 590, 612, 652], "The brain's choice", "One row per slot of the pad: left or right, up or down, whip, jump. The bars are the brain's probabilities, the red one its choice. An amber outline marks the move the look-ahead played instead."],
  played: [[634, 598, 1272, 652], "What was played", "The brain's own move, or the look-ahead's when it overruled the brain (amber), or route recovery's (teal), with the running shares of the three."],
};
function brainSpots() {
  const stage = $("brain-stage"), c = $("brainview"), k = c.clientWidth / window.BRAIN_VIEW_SIZE[0];
  if (!window.CadenceExplain || !k) return;
  CadenceExplain.clearSpots(stage);
  for (const [id, [x0, y0, x1, y1]] of Object.entries(window.BRAIN_VIEW_PARTS)) {
    if (id === "lookahead") continue;  // the brain alone: no look-ahead
    const [title, text] = PARTS[id];
    CadenceExplain.spot(stage, { x: x0 * k, y: y0 * k, w: (x1 - x0) * k, h: (y1 - y0) * k }, text, { title, id });
  }
}
function videoSpots() {
  const wrap = $("hl-wrap"), w = wrap.clientWidth, h = wrap.clientHeight;
  if (!window.CadenceExplain || !w || !h) return;
  CadenceExplain.clearSpots(wrap);
  const kx = w / 1280, ky = h / 720, put = ([x0, y0, x1, y1], title, text, id) =>
    CadenceExplain.spot(wrap, { x: x0 * kx, y: y0 * ky, w: (x1 - x0) * kx, h: (y1 - y0) * ky }, text, { title, id });
  for (const [id, [box, title, text]] of Object.entries(VIDEO_PARTS)) put(box, title, text, id);
  // the brain view sits at (622, 4) at 652 x 588 units in each frame
  const [W, H] = window.BRAIN_VIEW_SIZE, sx = 652 / W, sy = 588 / H;
  for (const [id, [x0, y0, x1, y1]] of Object.entries(window.BRAIN_VIEW_PARTS)) {
    if (id === "lookahead") continue;  // the line under the frame says it larger
    const [title, text] = PARTS[id];
    put([622 + x0 * sx, 4 + y0 * sy, 622 + x1 * sx, 4 + y1 * sy], title, text, "v-" + id);
  }
}

// -- the two recordings
function show(rec) {
  state.rec = rec;
  document.querySelectorAll("[data-rec]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.rec === rec)));
  $("rec-lookahead").hidden = rec !== "lookahead";
  $("rec-alone").hidden = rec !== "alone";
  if (rec === "alone") { $("hl").pause(); if (!state.booting) { state.booting = true; boot(); } else fitBrain(); }
  else { video.pause(); requestAnimationFrame(videoSpots); }
}
document.querySelectorAll("[data-rec]").forEach((b) => b.addEventListener("click", () => show(b.dataset.rec)));
new ResizeObserver(() => videoSpots()).observe($("hl-wrap"));
new ResizeObserver(() => { if (state.ready) fitBrain(); }).observe($("brain-stage"));


// live mode: the worker settles the brain decision by decision from the game's start
function feedLive(target) {
  const L = state.live;
  if (!L.ready || L.busy) return;
  if (target < L.next - 1 && !L.results.has(target)) {  // seeked back past what was settled: start over
    worker.postMessage({ op: "reset" }); L.next = 0; L.busy = true; return;
  }
  if (L.next <= target && L.next < trace.decisions.length) {
    L.busy = true; worker.postMessage({ op: "feed", k: L.next, x: trace.decisions[L.next].x });
  }
  const behind = Math.max(0, target - (L.next - 1));
  $("live-status").textContent = `${L.matches} of ${L.checked} live choices match the recording` +
    (behind > 0 ? ` · ${behind} decision${behind === 1 ? "" : "s"} behind` : " · in step") +
    (L.ms.length ? ` · ${Math.round(L.ms.reduce((a, b) => a + b, 0) / L.ms.length)} ms a decision` : "");
  $("live-status").className = "note " + (L.matches === L.checked ? "good" : "bad");
}
$("live").onclick = async () => {
  const L = state.live;
  L.on = !L.on;
  $("live").textContent = L.on ? "Live: on" : "Live: off";
  $("live").classList.toggle("on", L.on);
  if (!L.on) { $("live-status").textContent = "recorded state"; $("live-status").className = "note"; state.shown = -1; return; }
  if (!worker) {
    worker = new Worker("worker.js", { type: "module" });
    worker.onmessage = (e) => {
      const m = e.data;
      if (m.status) { $("live-status").textContent = m.status; return; }
      if (m.error) { $("live-status").textContent = "live mode stopped: " + m.error; $("live-status").className = "note bad"; L.busy = false; return; }
      if (m.op === "ready") { L.ready = true; L.busy = false; L.next = 0; return; }
      if (m.op === "reset") { L.busy = false; return; }
      if (m.op === "fed") {
        const rec = trace.decisions[m.k].snap;
        const same = m.action === rec.action;
        if (!L.results.has(m.k)) { L.checked++; if (same) L.matches++; }
        L.results.set(m.k, { action: m.action, same, snap: m.snap });
        L.ms.push(m.ms); if (L.ms.length > 50) L.ms.shift();
        L.next = m.k + 1; L.busy = false;
      }
    };
    L.busy = true;
    worker.postMessage({ op: "start", pack: PACK_ROOT });
  }
};

async function readManifest() {
  if (!manifest) {
    manifest = await (await fetch(new URL("manifest.json", PACK_ROOT), { cache: "no-cache" })).json();
    if (manifest.schema !== "cadence-castlevania-player/1") throw new Error("not a Castlevania player pack");
  }
  return manifest;
}
async function bootHighlights() {
  try {
    const m = await readManifest();
    const hl = $("hl");
    if (m.highlights.poster) hl.poster = new URL(m.highlights.poster, PACK_ROOT).href;
    hl.src = new URL(m.highlights.file, PACK_ROOT).href;
    videoSpots();
  } catch (error) {
    $("hl-hint").textContent = "The recording could not load: " + (error.message || error);
  }
}
async function boot() {
  try {
    await readManifest();
    const gz = await fetchChecked(new URL(manifest.trace.file, PACK_ROOT), manifest.trace.sha256);
    const text = await new Response(new Blob([gz]).stream().pipeThrough(new DecompressionStream("gzip"))).text();
    trace = JSON.parse(text);
    frames = trace.decisions.map((d) => d.frame);
    video.src = new URL(manifest.video.file, PACK_ROOT).href;
    fitBrain();
    state.ready = true;
    requestAnimationFrame(loop);
  } catch (error) {
    $("stats").textContent = "The player could not start: " + (error.message || error);
  }
}
bootHighlights();
if (new URLSearchParams(location.search).get("rec") === "alone") show("alone");
