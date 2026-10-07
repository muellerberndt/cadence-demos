// Page 5: the larva in its tank with the compiled brainstem in the loop. The body swims under
// the declared pilot (body.js) at the frame rate; the compiled twin brain (twin.js, two copies
// of the measured half) takes one step per STEP_MS of fish time, synchronously on the main
// thread: one step of both halves costs a tenth of a millisecond and there are 25 per fish
// second, so the worker (worker.js) is not needed here. The dictionary (dictionary.js) turns
// saccades and the yaw rate into stimuli and the abducens readouts into the gaze. The brain
// view is lit by the left half, the measured side, and flashed gold by the repair each neuron
// made in its last step, so a saccade shows as a wave through the integrator; the right half
// is its mirror copy. window.__app carries the parts for tools/scenario_fish.py.
import { mountShell, app, el, $, describePayload, sourcesList, fetchJSON, tooltips, SKELETONS_URL, SKELETONS_FALLBACK, BRAIN_URL } from "./site.js";
import { BrainView, loadPayload, HOT } from "./brain_view.js";
import { TANK, WATER, SNOUT, DEG, wrap } from "./body.js";
import { Aquarium } from "./aquarium.js";
import { FishMesh } from "./fish.js";
import { TwinBrain } from "./twin.js";
import { Life } from "./life.js";
import { Saccades, STEP_MS, SACCADE_STEPS, SACCADE_LEVEL, GAZE_DEGREES_PER_UNIT, GAZE_MAX, PULSE_DEGREES, VESTIBULAR_SATURATION, VESTIBULAR_LEVEL } from "./dictionary.js";

const params = new URLSearchParams(location.search);
const NOSCAN = params.get("noscan") === "1";  // no brain view: the headless checks
const CAPTURE_RADIUS = 0.4;                   // mm from the snout
const STRIPE_SPEEDS = [2, 5, 10];
const SUBSTEP = 0.01;                         // s, the life advances in pieces this long at most, as tests/life.mjs does
const LIT_MS = 50;                            // the view reads the brain twenty times a second
const REPAIR_FLOOR = 0.004;                   // a repair (|Δv| in one step) below this is the net's resting drift and does not flash
const REPAIR_GAIN = 10;                       // a neuron's flash is sqrt(min(1, (|Δv| - floor) × this))
const FLASH_DECAY = 0.9;                      // per reading: a flash halves in about a third of a second of wall time
const LABEL = "compiled: gaze holding and the vestibular push · declared pilot: bouts, hunt, escape, pulse";

const shell = mountShell("fish", { status: LABEL });
$("tank-title").textContent = shell.page.title;
const S = { paused: false, seed: Number(params.get("seed") || 1), frames: 0, totalFrames: 0, fps: 0, fpsClock: 0, lastHud: -Infinity, lastLit: -Infinity, captures: 0, brainMs: 0, brainSteps: 0, repairFloor: REPAIR_FLOOR, repairGain: REPAIR_GAIN };

/** The page's scheduler: a saccade requested through Life.requestSaccade (which sets `pending`)
 *  goes in its own direction and restarts the spontaneous schedule; Saccades.tick itself does
 *  not read `pending`. `spontaneous` false keeps the schedule quiet, for the checks. */
class PageSaccades extends Saccades {
  constructor(seed) { super(seed); this.spontaneous = true; }
  tick(time, wish = 0) {
    if (!this.spontaneous) this.next = Infinity;
    if (this.pending && this.stepsLeft <= 0) {
      const want = this.pending;
      this.pending = 0;
      if (this.spontaneous) { this.rng = (this.rng * 9301 + 49297) % 233280; const u = this.rng / 233280; this.next = time + 3 + 5 * (u * 7.3 - Math.floor(u * 7.3)); }
      return super.tick(time, want);
    }
    return super.tick(time, wish);
  }
}

/** The twin with the cost of its steps measured and, per neuron of the left half, the largest
 *  repair (|Δv| of one step) since the view last read it: the view's second channel. */
class TimedTwin extends TwinBrain {
  constructor(payload) { super(payload); this.vPrev = new Float64Array(this.n); this.burst = new Float32Array(this.n); }
  run(stimuli, steps) {
    const left = this.halves.left; this.vPrev.set(left.v);
    const t0 = performance.now(); const out = super.run(stimuli, steps); S.brainMs += performance.now() - t0; S.brainSteps += steps;
    const v = left.v, p = this.vPrev, b = this.burst;
    for (let i = 0; i < this.n; i++) { const d = Math.abs(v[i] - p[i]); if (d > b[i]) b[i] = d; }
    return out;
  }
}

// ---- the tank, the larva, the brain and the life -------------------------------------------
// ?nobloom=1 draws without the bloom pass; ?bloom=0.35&threshold=0.6 tune it; ?seed=n replays a life
const aquarium = new Aquarium($("tank-host"), { bloom: !params.get("nobloom"), bloomStrength: params.get("bloom") ? Number(params.get("bloom")) : undefined, bloomThreshold: params.get("threshold") ? Number(params.get("threshold")) : undefined });
const fish = new FishMesh().addTo(aquarium.world);
const skeletonLoad = NOSCAN ? Promise.resolve(null) : loadPayload(SKELETONS_URL).catch(() => loadPayload(SKELETONS_FALLBACK));
function fail(reason) { app.errors.push(String(reason)); shell.status(`brain unavailable: ${reason}`); $("loading").textContent = `brain unavailable: ${reason}`; }
const brain = await fetchJSON(BRAIN_URL).catch((e) => { fail(e.message || e); throw e; });
const twin = new TimedTwin(brain);
const life = new Life(twin, S.seed);
life.saccades = new PageSaccades(S.seed);
const world = life.world;
let brainView = null, stripeSpeed = 1;

// ---- the controls ---------------------------------------------------------------------------
function toast(text) { const t = $("toast"); t.textContent = text; t.classList.add("show"); clearTimeout(toast.timer); toast.timer = setTimeout(() => t.classList.remove("show"), 1600); }
function tap(side) {
  const hit = aquarium.tap(side);
  world.tapSide = hit.side; world.tapAge = 0;
  toast(`tap on the ${hit.side < 0 ? "left" : "right"} pane`);
  return hit;
}
function setStripes(opts) {
  world.stripes = aquarium.setStripes(opts);
  $("stripes").textContent = world.stripes.on ? "stripes on" : "stripes off";
  $("stripes").classList.toggle("on", world.stripes.on);
  $("direction").textContent = world.stripes.direction > 0 ? "direction +x" : "direction -x";
  $("speed").textContent = `${world.stripes.speed} mm/s`;
  return world.stripes;
}
function dropPrey() {
  const id = aquarium.addPrey([1 + (TANK[0] - 2) * Math.random(), 1 + (TANK[1] - 2) * Math.random(), 1 + (WATER - 2) * Math.random()]);
  world.prey = aquarium.preyList();
  return id;
}
function clearPrey() {
  for (const q of aquarium.preyList()) aquarium.removePrey(q.id);
  world.prey = [];
  return world.prey.length;
}
function moveLight(opts = null) {
  world.light = aquarium.setLight(opts || { x: 2 + (TANK[0] - 4) * Math.random(), y: 1 + (TANK[1] - 2) * Math.random(), z: TANK[2] + 2 + 2 * Math.random() });
  $("light-on").textContent = world.light.on ? "light on" : "light off";
  $("light-on").classList.toggle("on", world.light.on);
  return world.light;
}
function setFollow(on) {
  const f = aquarium.setFollow(on);
  $("follow").classList.toggle("on", f);
  return f;
}
function togglePause() { S.paused = !S.paused; $("pause").textContent = S.paused ? "resume" : "pause"; $("pause").classList.toggle("on", S.paused); }
/** The brain in or out of the loop, for the checks (tools/scenario_fish.py): off rests both halves and the eyes follow the pilot alone, the control. No button; the page always runs compiled. */
function setBrain(on) {
  life.brainOn = !!on;
  if (!life.brainOn) { life.brain.reset(); life.sides = { left: null, right: null }; life.gaze = 0; }
  toast(life.brainOn ? "the compiled brainstem holds the eyes" : "brain off: the pilot alone moves the eyes");
  return life.brainOn;
}
/** The spontaneous saccades every 3 to 8 s, on or off (off for the checks). */
function setSpontaneous(flag) {
  life.saccades.spontaneous = !!flag;
  if (life.saccades.spontaneous) life.saccades.next = life.time + 3;
  return life.saccades.spontaneous;
}
function requestSaccade(direction) {
  life.requestSaccade(direction);
  toast(direction > 0 ? "a leftward saccade: a burst to the left half's integrator" : "a rightward saccade: a burst to the right half's integrator");
}
$("tap-left").onclick = () => tap(-1);
$("tap-right").onclick = () => tap(1);
$("stripes").onclick = () => setStripes({ on: !world.stripes.on });
$("direction").onclick = () => setStripes({ direction: -world.stripes.direction });
$("speed").onclick = () => { stripeSpeed = (stripeSpeed + 1) % STRIPE_SPEEDS.length; setStripes({ speed: STRIPE_SPEEDS[stripeSpeed] }); };
$("prey").onclick = () => dropPrey();
$("light-move").onclick = () => moveLight();
$("light-on").onclick = () => moveLight({ on: !world.light.on });
$("follow").onclick = () => setFollow(!aquarium.following);
$("pause").onclick = togglePause;
$("saccade-left").onclick = () => requestSaccade(1);
$("saccade-right").onclick = () => requestSaccade(-1);
$("fit").onclick = () => { if (brainView) brainView.fit(); };
$("spin").onclick = () => { if (!brainView) return; brainView.options.spin = !brainView.options.spin; $("spin").classList.toggle("on", brainView.options.spin); };
addEventListener("keydown", (e) => { if (e.key === " " && e.target === document.body) { e.preventDefault(); togglePause(); } });
addEventListener("resize", () => { if (brainView) brainView.resize(); });
tooltips($("tank")); tooltips($("brain"));  // the hover explanations of the buttons, drawn inside their pane
setStripes({}); moveLight({});
setFollow(true);  // the camera follows the fish by default
for (let k = 0; k < 3; k++) dropPrey();

// ---- the card ---------------------------------------------------------------------------------
shell.card([
  ...shell.page.paragraphs.map((text) => el("p", {}, text)),
  ...describePayload(brain),
  `<b>This page.</b> The dictionary (dictionary.js) between the fish and the compiled brainstem: one brain step is a fifth of the unit's time constant, declared as 0.2 s, so a step is ${STEP_MS} ms of fish time and the brain takes ${1000 / STEP_MS} steps per fish second, on the main thread (twin.js, two copies of the compiled half; the left copy lights the view). A saccade is a burst of ${SACCADE_STEPS} steps at level ${SACCADE_LEVEL} to one half's integrator, leftward to the left half. The yaw rate drives the Ve2 vestibular cells of the half the head turns toward, level ${VESTIBULAR_LEVEL} at ${VESTIBULAR_SATURATION} rad/s, so the eyes move against the turn. The conjugate gaze is ${GAZE_DEGREES_PER_UNIT} degrees per unit of the two halves' abducens readout difference, within ${GAZE_MAX} degrees, plus a declared pulse of ${PULSE_DEGREES} degrees while a burst is on. Compiled: the gaze holding and the vestibular push. Declared: the swim bouts, the hunt, the escape from a tap, the pulse, the mirror half, the eye geometry, the senses on the panel, the saccade schedule. The checks rest the brain as the control: the eyes then follow the pilot alone.`,
  `<b>The brain view.</b> Every neuron of the measured half is lit by its own activity, scaled to the brightest cell of the moment, and flashed gold by the repair it made in its last step: how far it moved its potential toward what its synapses told it. Ask for a saccade and watch the wave: the integrator neurons flash as the burst arrives, the abducens cells follow, and the flashes die out while the integrator keeps holding its new level. That wave is the settlement; the held level is the answer, and the eye reads it.`,
  sourcesList(),
]);

// a paramecium within reach of the snout and ahead is eaten; another appears elsewhere
function captures(state) {
  const [x, y, z] = state.position, h = state.heading;
  const sx = x + SNOUT * Math.cos(h), sy = y + SNOUT * Math.sin(h);
  for (const q of aquarium.preyList()) {
    const d = Math.hypot(q.x - sx, q.y - sy, q.z - z);
    if (d > CAPTURE_RADIUS) continue;
    if (Math.abs(wrap(Math.atan2(q.y - y, q.x - x) - h)) > 60 * DEG) continue;
    aquarium.removePrey(q.id); S.captures++; toast("a paramecium is eaten"); dropPrey();
  }
  world.prey = aquarium.preyList();
}

// ---- the view's two channels: the activity of the left half, and its repair since the last reading, fading ----
const flash = new Float32Array(twin.n);
function lit() {
  const b = twin.burst;
  const floor = S.repairFloor, gain = S.repairGain;
  for (let i = 0; i < twin.n; i++) { const x = (b[i] - floor) * gain, f = x <= 0 ? 0 : Math.sqrt(Math.min(1, x)), old = flash[i] * FLASH_DECAY; flash[i] = f > old ? f : old; b[i] = 0; }
  brainView.setActivity(life.brain.activity("left"), flash);
}
// ---- the brain view, when the skeletons arrive ------------------------------------------------
skeletonLoad.then((payload) => {
  if (!payload) { $("view-host").append(el("div", { id: "noscan" }, "brain view skipped (noscan)")); return; }
  brainView = new BrainView($("view-host"), payload, { spin: true, controls: "legend", scale: "auto", gamma: 0.5, floor: 0.05 });
  app.brainView = brainView;
}).catch((e) => { app.errors.push(String(e.message || e)); shell.status(`brain view unavailable: ${e.message || e}`); });

// ---- the loop ---------------------------------------------------------------------------------
let last = performance.now();
function frame(now) {
  requestAnimationFrame(frame);
  const dtWall = Math.min(0.05, Math.max(0, (now - last) / 1000)); last = now;
  const dt = S.paused ? 0 : dtWall;
  if (dt > 0) {
    world.prey = aquarium.preyList();
    if (world.tapSide !== 0 && world.tapAge > 0.3) world.tapSide = 0;
    const n = Math.max(1, Math.ceil(dt / SUBSTEP)), h = dt / n;
    for (let i = 0; i < n; i++) life.step(h);
  }
  const state = life.body.state();
  if (dt > 0) captures(state);
  fish.update(state);
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
  S, life, aquarium, fish, brainView, world, brain: twin,
  state: () => life.body.state(), senses: () => ({ ...(life.senses || {}) }), decision: () => life.lastDecision,
  tap, setStripes, dropPrey, clearPrey, moveLight, setFollow, togglePause, setBrain, setSpontaneous, requestSaccade,
});
