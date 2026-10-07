// The larva page: the Platynereis larva in its tank with its complete compiled connectome in
// the loop. The body (larva_body.js) swims at the frame rate; the compiled whole-body net
// (brain.js on web/data/larva_brain.json, 25,609 cells) takes one step per STEP_MS of larva
// time, synchronously on the main thread: a step costs a fifth of a millisecond and there are
// 25 per larva second. The life (larva_life.js) lands the senses on the net's real sensory
// cells and reads the commands from its real effector cells through the declared dictionary
// (larva_dictionary.js); nothing in between is a pilot. The brain view lights every traced
// cell from the net's activity vector and flashes it gold by the repair it made in the last
// step, so a tap or the lamp shows as a wave of repairs sweeping through the net before it
// rests again. window.__app carries the parts for tools/scenario_larva.py.
import { mountShell, app, el, $, int, fetchJSON, tooltips, TITLE } from "./site.js";
import { BrainView, loadPayload, HOT } from "./brain_view.js";
import { SettlingBrain } from "./brain.js";
import { TANK, WATER, DEG, SPEED } from "./larva_body.js";
import { Aquarium } from "./aquarium.js";
import { LarvaMesh } from "./larva.js";
import { LarvaLife } from "./larva_life.js";
import { STEP_MS, LIGHT_LEVEL, SENSE_SATURATION, TAP_LEVEL, CPRC_LEVEL, BEAT_GAIN, ARREST_GAIN, SEROTONIN_GAIN, MUSCLE_GAIN, PARAPODIA_GAIN, BASELINE_BEAT } from "./larva_dictionary.js";

const params = new URLSearchParams(location.search);
const NOSCAN = params.get("noscan") === "1";  // no brain view: the headless checks
const SKELETONS_URL = typeof DecompressionStream === "undefined" ? "./data/larva_skeletons.json" : "./data/larva_skeletons.json.gz";
const SKELETONS_FALLBACK = "./data/larva_skeletons.json";
const BRAIN_URL = "./data/larva_brain.json";
const PAPER_URL = "https://doi.org/10.7554/eLife.97964";
const SUBSTEP = 0.01;                         // s, the life advances in pieces this long at most, as tests/larva_life.mjs does
const LIT_MS = 50;                            // the view reads the brain twenty times a second
const REPAIR_FLOOR = 0.004;                   // a repair (|Δv| in one step) below this is the net's resting drift and does not flash
const REPAIR_GAIN = 10;                       // a cell's flash is sqrt(min(1, (|Δv| - floor) × this)): a repair a tenth of a unit above the floor flashes it fully
const FLASH_DECAY = 0.9;                      // per reading: a flash halves in about a third of a second of wall time
const START = { position: [3, 3, WATER - 0.8], heading: 0.3 };  // near the surface, where a three-day larva swims, the tank's long diagonal ahead
const FOLLOW_DISTANCE = 6;                    // mm, the orbit's distance when the camera follows the larva
const LABEL = "compiled: measured cell-to-cell wiring · declared: dynamics, senses, body and time scale";

const shell = mountShell("index", { connectome: "Verasztó et al. 2025", connectomeUrl: "https://doi.org/10.7554/eLife.97964", status: LABEL });
document.title = `the larva · ${TITLE}`;
const S = { paused: false, seed: Number(params.get("seed") || 1), frames: 0, totalFrames: 0, fps: 0, fpsClock: 0, lastHud: -Infinity, lastLit: -Infinity, brainMs: 0, brainSteps: 0, reflections: 0, repairFloor: REPAIR_FLOOR, repairGain: REPAIR_GAIN };

/** The settling brain with the cost of its steps measured and, per cell, the largest repair
 *  (|Δv| of one step) since the view last read it: the view's second channel. */
class TimedBrain extends SettlingBrain {
  constructor(payload) { super(payload); this.vPrev = new Float64Array(this.n); this.burst = new Float32Array(this.n); }
  step() {
    this.vPrev.set(this.v);
    const t0 = performance.now(); super.step(); S.brainMs += performance.now() - t0; S.brainSteps++;
    const v = this.v, p = this.vPrev, b = this.burst;
    for (let i = 0; i < this.n; i++) { const d = Math.abs(v[i] - p[i]); if (d > b[i]) b[i] = d; }
  }
}

// ---- the tank, the larva, the brain and the life -------------------------------------------
// ?nobloom=1 draws without the bloom pass; ?bloom=0.35&threshold=0.6 tune it; ?seed=n replays a life
const aquarium = new Aquarium($("tank-host"), { bloom: !params.get("nobloom"), bloomStrength: params.get("bloom") ? Number(params.get("bloom")) : undefined, bloomThreshold: params.get("threshold") ? Number(params.get("threshold")) : undefined });
const mesh = new LarvaMesh().addTo(aquarium.world);
const skeletonLoad = NOSCAN ? Promise.resolve(null) : loadPayload(SKELETONS_URL).catch(() => loadPayload(SKELETONS_FALLBACK));
function fail(reason) { app.errors.push(String(reason)); shell.status(`brain unavailable: ${reason}`); $("loading").textContent = `brain unavailable: ${reason}`; }
const payload = await fetchJSON(BRAIN_URL).catch((e) => { fail(e.message || e); throw e; });
const brain = new TimedBrain(payload);
const life = new LarvaLife(brain, S.seed, START.position, START.heading);
const world = life.world;
let brainView = null;

// ---- the controls ---------------------------------------------------------------------------
function toast(text) { const t = $("toast"); t.textContent = text; t.classList.add("show"); clearTimeout(toast.timer); toast.timer = setTimeout(() => t.classList.remove("show"), 1600); }
/** A tap on the glass: the rings on the pane, the pulse on the collar receptors. */
function tap(side) {
  const hit = aquarium.tap(side);
  life.tap(hit.side);
  toast(`tap on the ${hit.side < 0 ? "left" : "right"} pane`);
  return hit;
}
/** The lamp: {on, x, y, z}, fields given replace the old; the senses read it from the body's world. */
function setLight(opts = {}) {
  const L = aquarium.setLight(opts);
  life.setLight({ on: L.on, x: L.x, y: L.y, z: L.z });
  $("light-on").textContent = L.on ? "light on" : "light off";
  $("light-on").classList.toggle("on", L.on);
  return L;
}
function moveLight() { return setLight({ x: 2 + (TANK[0] - 4) * Math.random(), y: 1 + (TANK[1] - 2) * Math.random(), z: TANK[2] + 2 + 2 * Math.random() }); }
/** The ultraviolet from above, 0 or 1: the ciliary photoreceptors answer it, strongest at the surface. */
function setUv(uv) {
  const v = Math.max(0, Math.min(1, Number(uv) || 0));
  life.setUv(v);
  $("uv").textContent = v > 0 ? "UV on" : "UV off";
  $("uv").classList.toggle("on", v > 0);
  return v;
}
function setFollow(on) {
  const f = aquarium.setFollow(on);
  if (f) aquarium.rig.dWant = FOLLOW_DISTANCE;  // closer than the fish's orbit: the larva is half its size
  $("follow").classList.toggle("on", f);
  return f;
}
function togglePause() { S.paused = !S.paused; $("pause").textContent = S.paused ? "resume" : "pause"; $("pause").classList.toggle("on", S.paused); }
/** The brain in or out of the loop, for the checks (tools/scenario_larva.py): off rests the net, the cilia beat at their baseline and nothing steers, the control. No button; the page always runs compiled. */
function setBrain(on) {
  life.brainOn = !!on;
  if (!life.brainOn) { brain.reset(); brain.clearStimuli(); life.readouts = {}; }
  toast(life.brainOn ? "the compiled connectome steers the larva" : "brain off: the cilia beat at their baseline, nothing steers");
  return life.brainOn;
}
$("tap-left").onclick = () => tap(-1);
$("tap-right").onclick = () => tap(1);
$("light-move").onclick = () => moveLight();
$("light-on").onclick = () => setLight({ on: !world.light.on });
$("uv").onclick = () => { setUv(world.uv > 0 ? 0 : 1); toast(world.uv > 0 ? "ultraviolet from above: the ciliary photoreceptors answer near the surface" : "ultraviolet off"); };
$("follow").onclick = () => setFollow(!aquarium.following);
$("pause").onclick = togglePause;
$("fit").onclick = () => { if (brainView) brainView.fit(); };
$("spin").onclick = () => { if (!brainView) return; brainView.options.spin = !brainView.options.spin; $("spin").classList.toggle("on", brainView.options.spin); };
addEventListener("keydown", (e) => { if (e.key === " " && e.target === document.body) { e.preventDefault(); togglePause(); } });
addEventListener("resize", () => { if (brainView) brainView.resize(); });
tooltips($("tank")); tooltips($("brain"));  // the hover explanations of the buttons, drawn inside their pane
setLight({});    // the tank's lamp as the senses' lamp
setUv(0);        // the ultraviolet off until asked for: on, the ciliary photoreceptors arrest the cilia near the surface
setFollow(true); // the camera follows the larva by default

// ---- the card ---------------------------------------------------------------------------------
shell.card([
  "<b>A whole-body connectome.</b> This model uses the published wiring of a three-day Platynereis larva, including sensory neurons, muscles and ciliated cells.",
  "<b>Try light and touch.</b> The lamp drives identified photoreceptors; a tap drives touch receptors. Activity travels through the compiled circuit to the modeled muscles and cilia.",
  "<b>Fixed connections.</b> These flashes show activity settling, not learning. Switch to the fish to teach a circuit whose connection strengths change.",
  el("p", {}, el("a", { href: PAPER_URL }, "Verasztó et al. 2025 · whole-body connectome")),
]);

// ---- the view's two channels: the activity, and the repair since the last reading, fading ----
const flash = new Float32Array(brain.n);
function lit() {
  const b = brain.burst;
  const floor = S.repairFloor, gain = S.repairGain;
  for (let i = 0; i < brain.n; i++) { const x = (b[i] - floor) * gain, f = x <= 0 ? 0 : Math.sqrt(Math.min(1, x)), old = flash[i] * FLASH_DECAY; flash[i] = f > old ? f : old; b[i] = 0; }
  brainView.setActivity(brain.s, flash);
}
// ---- the brain view, when the skeletons arrive ------------------------------------------------
skeletonLoad.then((skeletons) => {
  if (!skeletons) { $("view-host").append(el("div", { id: "noscan" }, "brain view skipped (noscan)")); return; }
  brainView = new BrainView($("view-host"), skeletons, { spin: true, controls: "legend", scale: "auto", gamma: 0.5, floor: 0.05, exposure: 0.5, fitScale: 0.62, pointRadius: 0.3, pointDim: 0.35 });
  app.brainView = brainView;
}).catch((e) => { app.errors.push(String(e.message || e)); shell.status(`brain view unavailable: ${e.message || e}`); });

// ---- the loop ---------------------------------------------------------------------------------
let last = performance.now(), lastHit = -1;
function frame(now) {
  requestAnimationFrame(frame);
  const dtWall = Math.min(0.05, Math.max(0, (now - last) / 1000)); last = now;
  const dt = S.paused ? 0 : dtWall;
  if (dt > 0) {
    const n = Math.max(1, Math.ceil(dt / SUBSTEP)), h = dt / n;
    for (let i = 0; i < n; i++) life.step(h);
  }
  const state = life.body.state();
  if (state.wallHit && state.wallHit.time !== lastHit) { S.reflections++; lastHit = state.wallHit.time; }
  mesh.update(state);
  aquarium.render(dtWall, state.position);
  if (brainView) {
    if (now - S.lastLit >= LIT_MS) { lit(); S.lastLit = now; }
    brainView.render(dtWall);
  }
  S.frames++; S.totalFrames++; S.fpsClock += dtWall;
  if (S.fpsClock >= 1) { S.fps = S.frames / S.fpsClock; S.frames = 0; S.fpsClock = 0; }
  if (!app.ready && S.totalFrames >= 3) app.ready = true;
}
$("loading").classList.add("gone");
requestAnimationFrame(frame);

Object.assign(app, {
  S, life, brain, aquarium, mesh, brainView, world,
  state: () => life.body.state(), senses: () => ({ ...(life.senses || {}) }), command: () => ({ ...life.command }), readouts: () => ({ ...life.readouts }),
  tap, setLight, moveLight, setUv, setBrain, setFollow, togglePause,
});
