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
import { probeLearning } from "./learning_probe.js";
import { learningView } from "./learning_view.js";
import { Saccades, STEP_MS, SACCADE_STEPS, SACCADE_LEVEL, SACCADE_INHIBITION, SACCADE_SIZES, GAZE_DEGREES_PER_UNIT, GAZE_MAX, PULSE_DEGREES, VESTIBULAR_SATURATION, VESTIBULAR_LEVEL, LEARN, WORLDS } from "./dictionary.js";

const params = new URLSearchParams(location.search);
const NOSCAN = params.get("noscan") === "1";  // no brain view: the headless checks
const CAPTURE_RADIUS = 0.4;                   // mm from the snout
const STRIPE_SPEEDS = [2, 5, 10];
const SUBSTEP = 0.01;                         // s, the life advances in pieces this long at most, as tests/life.mjs does
const LIT_MS = 50;                            // the view reads the brain twenty times a second
const REPAIR_FLOOR = 0.004;                   // a repair (|Δv| in one step) below this is the net's resting drift and does not flash
const REPAIR_GAIN = 10;                       // a neuron's flash is sqrt(min(1, (|Δv| - floor) × this))
const FLASH_DECAY = 0.9;                      // per reading: a flash halves in about a third of a second of wall time
const LABEL = "compiled graph: gaze and vestibular response · learned synapses · fixed pilot: swimming, hunting, escape";
const WORLD_SHORT = { still: "hold gaze", back: "let gaze return", against: "amplified correction experiment" };
const WORLD_LABEL = { still: "lessons favor retaining the gaze activity", back: "lessons favor a return toward rest", against: "experimental amplified feedback: may destabilize the response; recovery is not guaranteed" };

const shell = mountShell("fish", { status: LABEL });
$("tank-title").textContent = shell.page.title;
const S = { paused: false, speed: 1, practiceEnd: null, practiceStart: 0, viewSide: "left", seed: Number(params.get("seed") || 1), frames: 0, totalFrames: 0, fps: 0, fpsClock: 0, lastHud: -Infinity, lastLit: -Infinity, captures: 0, brainMs: 0, brainSteps: 0, repairFloor: REPAIR_FLOOR, repairGain: REPAIR_GAIN };

/** Observe applied synaptic changes for the display; the lesson itself stays in TwinBrain. */
class TimedTwin extends TwinBrain {
  constructor(payload, options) {
    super(payload, options);
    this.learningFlash = { left: new Float32Array(this.n), right: new Float32Array(this.n) };
    this.visualLessons = 0; this.lastVisualLesson = null;
  }
  run(stimuli, steps) {
    const t0 = performance.now(), out = super.run(stimuli, steps);
    S.brainMs += performance.now() - t0; S.brainSteps += steps;
    return out;
  }
  lesson(side, target) {
    const b = this.halves[side], before = b.w.slice();
    const report = super.lesson(side, target);
    const view = learningView(b.rowPtr, before, b.w), flash = this.learningFlash[side];
    for (let i = 0; i < this.n; i++) flash[i] = Math.max(flash[i], view.levels[i]);
    this.visualLessons++;
    this.lastVisualLesson = { side, changedEdges: view.changedEdges, changedCells: view.changedCells };
    S.viewSide = side;
    return report;
  }
}

// ---- the tank, the larva, the brain and the life -------------------------------------------
// ?nobloom=1 draws without the bloom pass; ?bloom=0.35&threshold=0.6 tune it; ?seed=n replays a life
const aquarium = new Aquarium($("tank-host"), { bloom: !params.get("nobloom"), bloomStrength: params.get("bloom") ? Number(params.get("bloom")) : undefined, bloomThreshold: params.get("threshold") ? Number(params.get("threshold")) : undefined });
const fish = new FishMesh().addTo(aquarium.world);
const skeletonLoad = NOSCAN ? Promise.resolve(null) : loadPayload(SKELETONS_URL).catch(() => loadPayload(SKELETONS_FALLBACK));
function fail(reason) { app.errors.push(String(reason)); shell.status(`brain unavailable: ${reason}`); $("loading").textContent = `brain unavailable: ${reason}`; }
const brain = await fetchJSON(BRAIN_URL).catch((e) => { fail(e.message || e); throw e; });
const twin = new TimedTwin(brain, { learning: true });
const life = new Life(twin, S.seed);
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
/** Pause or resume plasticity without changing the acquired weights. */
function setLearning(on) { if (!on) S.practiceEnd = null; life.setLearning(on); $("learning-toggle").textContent = on ? "Pause learning" : "Resume learning"; status(); return life.learning.on; }
/** Select the declared activity-feedback lesson. */
function setWorld(name) {
  S.practiceEnd = null;
  life.setWorld(name);
  $("lesson-guide").textContent = name === "still" ? "Teach it to keep looking to the side after a glance. Gold flashes mark connections changing as it learns." : "Teach its gaze to drift back after a glance. This same brain keeps what it learned and adapts again.";
  for (const b of $("world").querySelectorAll("button")) { b.classList.toggle("on", b.dataset.world === name); b.setAttribute("aria-pressed", String(b.dataset.world === name)); }
  toast(WORLD_LABEL[name]);
  status();
  return name;
}
function resetSynapses() { S.practiceEnd = null; life.resetLearning(); $("learning-toggle").textContent = "Pause learning"; $("response-bars").hidden = true; $("probe-result").textContent = "Learning reset. Test its gaze to see the starting response."; twin.learningFlash.left.fill(0); twin.learningFlash.right.fill(0); twin.lastVisualLesson = null; toast("learning reset: starting weights and activity restored"); status(); return true; }
/** The status strip: the label, and the learning's count and last lesson. */
let shownLessons = 0;
function status() {
  const L = life.learning, last = L.last;
  let changed = 0, total = 0;
  for (const side of ["left", "right"]) { const b = twin.halves[side], original = b.efficacy0 || b.sign; if (b.efficacy) for (let e = 0; e < b.edges; e++) { total++; if (Math.abs(b.efficacy[e] - original[e]) > 1e-10) changed++; } }
  const clock = `${Math.floor(life.time / 60)}:${String(Math.floor(life.time % 60)).padStart(2, "0")}`;
  const remaining = Math.max(0, Math.ceil((S.practiceEnd ?? life.time) - life.time));
  const progress = S.practiceEnd !== null
    ? `Teaching · ${remaining} fish seconds left · ${L.lessons} lessons`
    : `${L.lessons} lessons · ${changed.toLocaleString()} connections changed · ${L.on ? "learning" : "learning paused"}`;
  if ($("learning-progress").textContent !== progress) $("learning-progress").textContent = progress;
  $("practice-progress").hidden = S.practiceEnd === null;
  $("practice-progress").value = S.practiceEnd === null ? 0 : (life.time - S.practiceStart) / (S.practiceEnd - S.practiceStart);
  $("practice-lesson").disabled = S.practiceEnd !== null;
  $("practice-lesson").textContent = S.practiceEnd !== null ? "Teaching…" : "Teach this lesson";
  const lastChange = twin.lastVisualLesson;
  $("brain-learning").textContent = lastChange ? `${lastChange.side} half · ${lastChange.changedEdges.toLocaleString()} connections changed in the last lesson` : "Gold marks cells receiving changed connections";
  const observation = last ? (last.drift < 0 ? `last fixation: activity fell ${Math.abs(100 * last.drift).toFixed(0)}% in ${last.fixation.toFixed(1)} s` : `last fixation: activity grew ${Math.abs(100 * last.drift).toFixed(0)}% in ${last.fixation.toFixed(1)} s`) : "waiting for an undisturbed fixation";
  shell.status(`${WORLD_SHORT[L.world]} · ${observation} · ${L.on ? "learning on" : "learning paused"}`);
  if (L.lessons !== shownLessons && last) { shownLessons = L.lessons; toast(`lesson ${L.lessons}: ${last.side} half · measured drift ${Math.abs(100 * last.drift).toFixed(0)}%`); }
}
function measureLearning() {
  const result = { ...probeLearning(twin), lessons: life.learning.lessons, fishTime: life.time }; app.lastProbe = result;
  $("response-bars").hidden = false;
  for (const [name, sample] of [["before", result.baseline], ["left", result.left], ["right", result.right]]) {
    const value = sample.ratio === null ? 0 : 100 * sample.ratio;
    $("response-" + name).value = Math.max(0, Math.min(100, value));
    $("value-" + name).textContent = sample.ratio === null ? "—" : `${value.toFixed(1)}%`;
  }
  const growing = result.left.ratio > 1 || result.right.ratio > 1;
  $("probe-result").textContent = `Gaze held after 5 seconds${growing ? " · above 100% means growing" : ""}`;
  return result;
}
function practiceLesson() {
  if (S.paused) togglePause();
  setLearning(true); setSpontaneous(true);
  $("auto-saccades").textContent = "Automatic glances on"; $("auto-saccades").setAttribute("aria-pressed", "true");
  S.speed = 8; $("life-speed").textContent = "Time: 8×";
  S.practiceStart = life.time;
  S.practiceEnd = life.time + (life.learning.world === "still" ? 600 : life.learning.world === "back" ? 150 : 120);
  status();
}
function finishPractice() {
  setLearning(false); S.speed = 1; $("life-speed").textContent = "Time: 1×";
  measureLearning(); status(); toast("practice complete · learning paused · acquired weights retained");
}
function restoreCompiled() { life.brain.restoreCompiled(); life.learning.on = false; life._clearFixations(); $("learning-toggle").textContent = "resume learning"; status(); }

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
for (const b of $("world").querySelectorAll("button")) b.onclick = () => setWorld(b.dataset.world);
$("reset-synapses").onclick = () => resetSynapses();
$("learning-toggle").onclick = () => setLearning(!life.learning.on);
$("practice-lesson").onclick = () => practiceLesson();
$("measure-learning").onclick = () => measureLearning();
$("auto-saccades").onclick = () => { const on = setSpontaneous(!life.saccades.spontaneous); $("auto-saccades").textContent = `Automatic glances ${on ? "on" : "off"}`; $("auto-saccades").setAttribute("aria-pressed", String(on)); };
$("life-speed").onclick = () => { const speeds = [1, 4, 8]; S.speed = speeds[(speeds.indexOf(S.speed) + 1) % speeds.length]; $("life-speed").textContent = `Time: ${S.speed}×`; };
$("saccade-left").onclick = () => requestSaccade(1);
$("saccade-right").onclick = () => requestSaccade(-1);
$("fit").onclick = () => { if (brainView) brainView.fit(); };
$("spin").onclick = () => { if (!brainView) return; brainView.options.spin = !brainView.options.spin; $("spin").classList.toggle("on", brainView.options.spin); };
addEventListener("keydown", (e) => { if (e.key === " " && e.target === document.body) { e.preventDefault(); togglePause(); } });
addEventListener("resize", () => { if (brainView) brainView.resize(); });
tooltips($("tank")); tooltips($("brain")); tooltips($("lesson-panel"));  // the hover explanations of the buttons, drawn inside their pane
setStripes({}); moveLight({ on: false, x: TANK[0] / 2, y: TANK[1] / 2, z: TANK[2] + 4 });
setFollow(true);  // the camera follows the fish by default
// Start without random prey so the default lesson follows the seeded life checked in Node.
// Feeding and lighting are optional disturbances, with their fixed pilot declared.

// ---- the card ---------------------------------------------------------------------------------
shell.card([
  "<b>A brain that keeps learning.</b> The fish's gaze circuit uses wiring compiled from a measured zebrafish connectome. Lessons change connection strengths on that same graph.",
  "<b>What you teach.</b> Hold your gaze targets a nearly retained activity pattern; let it return asks for a smaller one. These are declared teaching signals, not learning from camera pixels. Swimming and hunting use a fixed pilot.",
  "<b>What the colours mean.</b> Green shows neural activity. Gold marks cells whose incoming connections actually changed in a lesson. The view follows the half that just learned; brightness reflects the size of its changes.",
  "<b>What stays.</b> Pausing learning or choosing another lesson keeps the learned connections. Reset learning forgets them. Test its gaze compares starting and current weights without changing the live fish.",
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

// Green follows activity; gold follows only measured changes to effective weights.
function lit() {
  const side = S.viewSide;
  brainView.setActivity(life.brain.activity(side), twin.learningFlash[side]);
  for (const f of Object.values(twin.learningFlash)) for (let i = 0; i < f.length; i++) f[i] *= 0.96;
}
// ---- the brain view, when the skeletons arrive ------------------------------------------------
skeletonLoad.then((payload) => {
  if (!payload) { $("view-host").append(el("div", { id: "noscan" }, "brain view skipped (noscan)")); return; }
  brainView = new BrainView($("view-host"), payload, { spin: true, controls: false, scale: "auto", gamma: 0.5, floor: 0.05, rest: [0.005, 0.045, 0.012], lit: [0.08, 0.55, 0.16], flash: [3, 1.1, 0.05] });
  app.brainView = brainView;
}).catch((e) => { app.errors.push(String(e.message || e)); shell.status(`brain view unavailable: ${e.message || e}`); });

// ---- the loop ---------------------------------------------------------------------------------
let last = performance.now(), accumulated = 0;
function frame(now) {
  requestAnimationFrame(frame);
  const dtWall = Math.min(0.05, Math.max(0, (now - last) / 1000)); last = now;
  const dt = S.paused ? 0 : dtWall * S.speed;  // S.speed: fish seconds per wall second, 1 on the page; the checks raise it
  if (dt > 0) {
    world.prey = aquarium.preyList();
    if (world.tapSide !== 0 && world.tapAge > 0.3) world.tapSide = 0;
    accumulated += dt;
    while (accumulated + 1e-12 >= SUBSTEP) { life.step(SUBSTEP); accumulated -= SUBSTEP; if (S.practiceEnd !== null && life.time + 1e-9 >= S.practiceEnd) { finishPractice(); accumulated = 0; break; } }
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
  if (now - S.lastHud >= 500) { status(); S.lastHud = now; }
  if (!app.ready && S.totalFrames >= 3) app.ready = true;
}
$("loading").classList.add("gone");
requestAnimationFrame(frame);

Object.assign(app, {
  S, life, aquarium, fish, brainView, world, brain: twin,
  learningVisual: () => ({ lessons: twin.visualLessons, last: twin.lastVisualLesson, side: S.viewSide, peak: Math.max(...twin.learningFlash[S.viewSide]) }),
  state: () => life.body.state(), senses: () => ({ ...(life.senses || {}) }), decision: () => life.lastDecision,
  tap, setStripes, dropPrey, clearPrey, moveLight, setFollow, togglePause, setBrain, setSpontaneous, requestSaccade, setLearning, setWorld, resetSynapses, restoreCompiled, measureLearning, practiceLesson, learning: () => ({ ...life.learning, sides: undefined, log: life.learning.log.slice(-10) }),
});
