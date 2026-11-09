// Tron vs one Cadence brain. The page owns the clock: each tick it sends your move to the
// worker, waits for the brain's answer (never inventing one), then draws the arena, plays the
// settle on the brain view and the sounds. Your record against this brain (keyed by the
// brain file's SHA-256) is kept in this browser.

import { Link } from "./link.js";
import { ArenaView } from "./arena.js";
import { Steering, bindSwipe } from "./input.js";
import { DeepView } from "./deep.js";
import { AnatomyView } from "./anatomy.js";
import { Sound } from "./sound.js";

const TICK_MS = 120;
const KEYS = { ArrowUp: 0, KeyW: 0, ArrowRight: 1, KeyD: 1, ArrowDown: 2, KeyS: 2, ArrowLeft: 3, KeyA: 3 };
const STORE = "cadence-tron-play.record";
// Two brains share the page: ?brain=flat or ?brain=deep (the default) picks web/pack/<slot>/.
// Where the packs live: <meta name="cadence-pack"> if the host page sets one, else pack/ beside this page.
const PACK_ROOT = new URL(document.querySelector('meta[name="cadence-pack"]')?.content || "pack/", document.baseURI).href;
const SLOTS = ["flat", "deep"];
const SLOT = (() => {
  const asked = new URLSearchParams(location.search).get("brain");
  return SLOTS.includes(asked) ? asked : "deep";
})();
// ?search=N: the brain guides a tree search of N simulations per move (tron/mcts.py); 0, the
// default, plays the brain alone, one settle per move.
const SEARCH_SIMS = 32;
const SIMS = (() => {
  const n = parseInt(new URLSearchParams(location.search).get("search") || "0", 10);
  return Number.isFinite(n) && n > 0 ? Math.min(n, 200) : 0;
})();
const recordKey = (sha) => (SIMS ? `${sha}:search${SIMS}` : sha);
const RESULT = { win: "loss", loss: "win", draw: "draw" }; // the host reports the brain's result

const $ = (id) => document.getElementById(id);
const els = {
  overlay: $("overlay"), panel: $("panel"), status: $("status"), you: $("score-you"), them: $("score-them"),
  stats: $("stats"), mute: $("mute"), name: $("brain-name"),
};
const app = {
  phase: "loading", // loading | ready | countdown | playing | over | error
  manifest: null, desc: null, last: null, title: "Mako",
  record: { games: 0, you: 0, them: 0, draws: 0 },
  timings: [], frameGaps: [], replays: [],
};

const arena = new ArenaView($("arena"));
// The brain view: the anatomy (default) or the layers (?view=layers); the same neurons and sweeps.
const VIEW = new URLSearchParams(location.search).get("view") === "layers" ? "layers" : "anatomy";
const brain = VIEW === "layers" ? new DeepView($("brain"), $("zoom")) : new AnatomyView($("brain"), $("zoom"));
const sound = new Sound();
const steering = new Steering();
const link = new Link((s) => { if (app.phase === "loading") els.status.textContent = s; });

// ---- the record --------------------------------------------------------------------------
function loadRecord(sha) {
  try {
    const all = JSON.parse(localStorage.getItem(STORE) || "{}");
    if (all[recordKey(sha)]) app.record = { ...app.record, ...all[recordKey(sha)] };
  } catch (_) { /* storage blocked */ }
}
function saveRecord() {
  try {
    const all = JSON.parse(localStorage.getItem(STORE) || "{}");
    all[recordKey(app.manifest.brain.sha256)] = app.record;
    localStorage.setItem(STORE, JSON.stringify(all));
  } catch (_) { /* storage blocked */ }
}
function showRecord(bump) {
  const r = app.record;
  els.you.textContent = r.you;
  els.them.textContent = r.them;
  const rate = r.games ? Math.round((100 * (r.you + 0.5 * r.draws)) / r.games) : 0;
  const narrow = innerWidth < 520;
  els.stats.textContent = r.games ? (narrow ? `${r.games} · ${rate}%` : `${r.games} games · you ${rate}%`) : (narrow ? "" : "no games yet");
  if (bump) {
    const el = bump === "you" ? els.you : els.them;
    el.classList.add("bump");
    setTimeout(() => el.classList.remove("bump"), 260);
  }
}

// ---- overlay -----------------------------------------------------------------------------
const touch = () => matchMedia("(pointer: coarse)").matches;
function overlay(html, dim = true) {
  els.panel.innerHTML = html;
  els.overlay.classList.toggle("dim", dim);
}
function showStart() {
  overlay(`<div class="big"><span class="you">RIDE</span></div>
    <div class="sub">You are blue. ${app.title} is pink, a brain that sees the whole field.<br>Don't hit a wall or a trail.</div>
    <div class="go-hint">${touch() ? "TAP TO RIDE" : "SPACE TO RIDE"}</div>`);
}
function showResult(result, ticks) {
  const head = result === "win" ? '<span class="you">YOU WIN</span>' : result === "loss" ? `<span class="them">${app.title.toUpperCase()} WINS</span>` : "DRAW";
  overlay(`<div class="big">${head}</div><div class="sub">${ticks} ticks</div>
    <div class="go-hint">${touch() ? "TAP TO RIDE AGAIN" : "SPACE TO RIDE AGAIN"}</div>`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---- the game ----------------------------------------------------------------------------
async function startGame() {
  sound.unlock();
  if (!["ready", "over"].includes(app.phase)) return;
  if (app.phase === "over" && performance.now() - (app.overAt || 0) < 450) return;
  app.phase = "countdown";
  let state;
  try {
    state = await link.call("begin");
  } catch (error) { fail(error); return; }
  brain.clear();
  arena.start(state);
  steering.reset(state.headings[1]);
  steering.enabled = true;
  brain.push(state);
  app.last = state;
  app.replay = { brain: app.manifest.brain.id, brain_sha256: app.manifest.brain.sha256, cadence: app.manifest.cadence,
    seed: state.seed, moves: [], result: null, started: Date.now() };
  for (const n of ["3", "2", "1"]) {
    overlay(`<div class="big count">${n}</div>`, false);
    sound.count(false);
    await sleep(480);
  }
  overlay(`<div class="big count you">GO</div>`, false);
  sound.count(true);
  setTimeout(() => { if (app.phase === "playing") overlay("", false); }, 380);
  app.phase = "playing";
  sound.engine(0, true, 1, 0);
  sound.engine(1, true, 1, 0);
  play();
}

async function play() {
  let next = performance.now();
  let previous = performance.now();
  while (app.phase === "playing") {
    const wait = next - performance.now();
    if (wait > 1) await sleep(wait);
    const sent = performance.now();
    const move = steering.next();
    const before = app.last.headings.slice();
    let state;
    try {
      state = await link.call("tick", { move });
    } catch (error) { fail(error); return; }
    const now = performance.now();
    app.timings.push({ round: now - sent, worker: state.worker_ms, act: state.brain && state.brain.act_ms });
    if (state.moved) app.replay.moves.push(state.moved);
    const duration = Math.max(TICK_MS, now - sent);
    arena.update(state, Math.min(duration, 400));
    brain.push(state);
    steering.sync(state.headings[1]);
    for (let seat = 0; seat < 2; seat++) if (state.headings[seat] !== before[seat] && state.alive[seat]) sound.turn(seat);
    const speed = TICK_MS / Math.max(TICK_MS, now - previous);
    previous = now;
    sound.pulse();
    for (let seat = 0; seat < 2; seat++) if (state.alive[seat]) sound.engine(seat, true, speed, state.tick);
    if (state.brain && state.brain.sweeps) sound.thinking(state.repair, Math.min(0.5, (duration + 300) / 1000), state.brain.choice);
    app.last = state;
    if (state.over) { finish(state); return; }
    next = Math.max(sent + TICK_MS, now);
  }
}

function finish(state) {
  app.phase = "over";
  app.overAt = performance.now();
  steering.enabled = false;
  const result = RESULT[state.result];
  const r = app.record;
  r.games += 1;
  if (result === "win") r.you += 1; else if (result === "loss") r.them += 1; else r.draws += 1;
  saveRecord();
  showRecord(result === "win" ? "you" : result === "loss" ? "them" : null);
  app.replay.result = state.result; // the brain's side: win | loss | draw
  app.replay.ticks = state.tick;
  replays.record(app.replay);
  sound.quiet();
  sound.stinger(result);
  setTimeout(() => { if (app.phase === "over") showResult(result, state.tick); }, 700);
}

function fail(error) {
  console.warn(error);
  app.phase = "ready";
  steering.enabled = false;
  sound.quiet();
  overlay(`<div class="big them">STOPPED</div><div class="sub">${String(error.message || error).replace(/[<>&]/g, "")}</div>`);
}

// ---- replays: kept in memory; `replays.sink` is the seam for an upload later ------------
const replays = {
  list: app.replays,
  sink: null, // (replay) => Promise; e.g. an upload, set by a backend integration
  record(replay) {
    this.list.push(replay);
    if (this.sink) Promise.resolve(this.sink(replay)).catch((e) => console.warn("replay upload failed", e));
  },
};

// ---- input -------------------------------------------------------------------------------
const playing = () => app.phase === "playing" || app.phase === "countdown";
window.addEventListener("keydown", (event) => {
  if (event.altKey || event.ctrlKey || event.metaKey) return;
  const d = KEYS[event.code];
  if (d !== undefined) {
    event.preventDefault();
    sound.unlock();
    steering.request(d);
    return;
  }
  if (event.code === "Space" || event.code === "Enter" || event.code === "KeyR") { event.preventDefault(); startGame(); }
  if (event.code === "KeyM") toggleMute();
});
bindSwipe($("arena-wrap"), steering, { onTap: () => { sound.unlock(); if (!playing()) startGame(); } });
for (const [id, side] of [["left", -1], ["right", 1]]) {
  $(id).addEventListener("pointerdown", (e) => { e.preventDefault(); sound.unlock(); if (!playing()) { startGame(); return; } steering.turn(side); });
}
function toggleMute() {
  sound.unlock();
  sound.setMuted(!sound.muted);
  els.mute.classList.toggle("muted", sound.muted);
  els.mute.setAttribute("aria-label", sound.muted ? "Sound off" : "Sound on");
}
els.mute.addEventListener("click", toggleMute);
els.mute.classList.toggle("muted", sound.muted);
window.addEventListener("resize", () => showRecord());

// ---- the frame loop ----------------------------------------------------------------------
let lastFrame = performance.now();
function loop(now) {
  const gap = now - lastFrame;
  lastFrame = now;
  if (app.phase === "playing") {
    app.frameGaps.push(gap);
    if (app.frameGaps.length > 6000) app.frameGaps.splice(0, 3000);
  }
  arena.overlay = brain.boardOverlay();
  arena.frame(now);
  brain.frame(now);
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);

// ---- boot --------------------------------------------------------------------------------
async function boot() {
  try {
    const extra = (SIMS ? `&search=${SIMS}` : "") + (VIEW === "layers" ? "&view=layers" : "");
    document.querySelectorAll("#pick a[data-slot]").forEach((a) => {
      a.classList.toggle("on", a.dataset.slot === SLOT);
      a.href = `?brain=${a.dataset.slot}${extra}`;
    });
    document.querySelectorAll("#views a[data-view]").forEach((a) => {
      a.classList.toggle("on", a.dataset.view === VIEW);
      a.href = `?brain=${SLOT}${SIMS ? `&search=${SIMS}` : ""}${a.dataset.view === "layers" ? "&view=layers" : ""}`;
    });
    const sw = document.getElementById("search"); // the search switch, where the page shows one
    if (sw) {
      sw.classList.toggle("on", SIMS > 0);
      sw.href = `?brain=${SLOT}${SIMS ? "" : `&search=${SEARCH_SIMS}`}`;
      sw.title = SIMS ? `The brain guides a search of ${SIMS} simulations per move; tap for the brain alone`
        : `Let the brain guide a tree search of ${SEARCH_SIMS} simulations per move`;
    }
    const manifest = await (await fetch(`${PACK_ROOT}${SLOT}/manifest.json`, { cache: "no-cache" })).json();
    app.manifest = manifest;
    app.title = manifest.brain.title;
    els.name.textContent = app.title.toUpperCase();
    if (SIMS) app.title = `${app.title} + search`;
    document.title = `Tron vs ${app.title}`;
    loadRecord(manifest.brain.sha256);
    showRecord();
    const pack = new URL(`${SLOT}/`, PACK_ROOT).href;
    const intro = manifest.brain.introspect
      ? fetch(`${PACK_ROOT}${SLOT}/${manifest.brain.introspect}`, { cache: "no-cache" }).then((r) => (r.ok ? r.json() : null)).catch(() => null)
      : Promise.resolve(null);
    const [{ describe }, introspect] = await Promise.all([link.call("start", { pack, games: app.record.games }), intro]);
    if (SIMS) await link.call("mode", { sims: SIMS });
    app.desc = describe;
    app.intro = introspect;
    brain.setIntrospect(introspect);
    brain.setBrain(describe);
    arena.clear(24);
  } catch (error) {
    app.phase = "error";
    overlay(`<div class="big them">NO BRAIN</div><div class="sub">${String(error.message || error).replace(/[<>&]/g, "")}<br>This page needs WebAssembly, module workers and a network connection on the first visit.</div>`);
    return;
  }
  app.phase = "ready";
  showStart();
}

// A read-only view and a direct line to the worker, for automated checks (tests/play_check.py).
window.__tron = {
  view: () => ({
    phase: app.phase, size: arena.size, tick: app.last ? app.last.tick : 0,
    heads: app.last ? app.last.heads : null, headings: app.last ? app.last.headings : null,
    occupied: Array.from(arena.occupied), planned: steering.planned(), queued: steering.queue.length,
    record: app.record, replays: app.replays.length, slot: SLOT, sims: SIMS, view: VIEW, brain: app.manifest ? app.manifest.brain.id : null,
  }),
  call: (op, payload) => link.call(op, payload),
  timings: () => app.timings,
  frameGaps: () => app.frameGaps,
  last: () => app.last,
  replays: () => app.replays,
  replaySink: (fn) => { replays.sink = fn; },
  zoom: (layer, k) => { // select a neuron (layer key, index) or clear with null
    if (layer === null) { brain.select(null); return null; }
    const L = brain.layers && brain.layers.find((x) => x.key === layer);
    if (!L) return null;
    brain.select(L.start + k);
    return { x: brain.px[L.start + k] / brain.dpr, y: brain.py[L.start + k] / brain.dpr };
  },
  layers: () => (brain.layers || []).map((L) => ({ key: L.key, pop: L.pop, count: L.count,
    groups: L.groups.map((g) => [g.family, g.members.length]),
    supported: L.labels ? L.labels.map((x, k) => (x.supported ? k : -1)).filter((k) => k >= 0) : [] })),
};

boot();
