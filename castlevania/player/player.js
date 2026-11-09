// The recorded run: the video of one game, and beside it the brain view (../web/brain.js) driven
// by the decision the video is showing. The trace (pack/trace.json.gz) holds, per decision, the
// first video frame it covers, the eye's exact input and the brain's recorded state. Live mode runs
// the brain itself in a worker (Pyodide, the released wheel) on those inputs, in order, and checks
// its chosen buttons against the recording.
const $ = (id) => document.getElementById(id);
const PACK_ROOT = new URL(document.querySelector('meta[name="cadence-pack"]')?.content || "pack/", document.baseURI).href;
const SLICES = { scene: [0, 192], motion: [192, 384], ahead: [384, 576], body: [576, 588], behind: [588, 780],
  stage: [780, 798], block: [798, 802], state: [802, 812], floor: [812, 827] };
const SLOT_NAMES = [["horizontal", ["left", "-", "right"]], ["vertical", ["up", "-", "down"]], ["whip", ["no", "yes"]], ["jump", ["no", "yes"]]];
const ACTIONS = []; for (const h of [-1, 0, 1]) for (const v of [-1, 0, 1]) for (const w of [0, 1]) for (const j of [0, 1]) ACTIONS.push([h, v, w, j]);
const video = $("video"), view = new BrainView($("brainview"));
const state = { ready: false, frame: 0, decision: -1, shown: -1, source: "recorded", frameTimes: [],
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
  c.width = Math.round(w * ratio); c.height = Math.round(w * bh / bw * ratio);
}
window.addEventListener("resize", fitBrain);

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

async function boot() {
  try {
    manifest = await (await fetch(new URL("manifest.json", PACK_ROOT), { cache: "no-cache" })).json();
    if (manifest.schema !== "cadence-castlevania-player/1") throw new Error("not a Castlevania player pack");
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
boot();
