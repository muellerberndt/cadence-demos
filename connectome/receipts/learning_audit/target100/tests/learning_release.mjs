// Independent continuation assay. Teaching uses the page's Life; assessment uses fresh clones
// of its weights, never its lesson targets or a filtered subset of reported hold constants.
// node tests/learning_release.mjs --out receipts/learning_release.json
// --report-only records an unsuccessful candidate without treating it as a release pass.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";

const root = new URL("../", import.meta.url);
const arg = (name, fallback) => { const i = process.argv.indexOf(`--${name}`); return i < 0 ? fallback : process.argv[i + 1]; };
const sourceFiles = ["tests/learning_release.mjs", "web/brain.js", "web/twin.js", "web/life.js", "web/dictionary.js", "web/body.js", "web/senses.js", "web/settlement-trace.js", "web/neural-replay.js", "web/data/brain.json"];
const hash = value => createHash("sha256").update(value).digest("hex");
const sourceHashes = () => Object.fromEntries(sourceFiles.map(path => [path, hash(readFileSync(new URL(path, root)))]));
const sources = sourceHashes();
const { SettlingBrain } = await import("../web/brain.js");
const { TwinBrain, SIDES } = await import("../web/twin.js");
const { Life } = await import("../web/life.js");
const { LEARN, WORLDS, STEP_MS, SACCADE_STEPS, GAZE_DEGREES_PER_UNIT } = await import("../web/dictionary.js");
const payload = JSON.parse(readFileSync(new URL("web/data/brain.json", root), "utf8"));
const seeds = arg("seeds", "7,8,9").split(",").map(Number);
assert(seeds.length && seeds.every(seed => Number.isSafeInteger(seed) && seed > 0), "invalid seeds");
const protocol = {
  seeds, dt_seconds: 0.01, start_gain_fraction: LEARN.start,
  phases: [{ name: "hold", world: "still", seconds: 600 }, { name: "return", world: "back", seconds: 150 }, { name: "stress", world: "against", seconds: 120 }, { name: "recovery", world: "still", seconds: 240 }],
  probe_levels: [0.03, 0.1], probe_burst_steps: SACCADE_STEPS, probe_delay_steps: LEARN.targetDelay,
  probe_seconds: [1, 5, 12, 24], probe_step_seconds: STEP_MS / 1000,
  learning: LEARN, worlds: WORLDS,
  controls: "Same payload, initial weights and gain, seed, body/pilot, durations and world schedule; plasticity frozen. Subsequent actions may differ because gaze feeds the pilot.",
  assessment: "Fresh copies of each half's current weights and bias; no learning, body, clipping or feedback. Gaze is 65 times the SUM of the ABD_m and ABD_i population means, as in the live dictionary. Zero opposite-half activity and no direct saccade pulse during assessment.",
  release_claim: "The still lesson improves both halves' unclamped readout retention over the matched frozen control; the return lesson reduces it. The against/recovery phases are characterized separately and are not required to pass this narrower release claim.",
};

function digestBrain(brain, weightsOnly = false) {
  const h = createHash("sha256");
  for (const key of weightsOnly ? ["w", "bias"] : ["v", "s", "drive", "w", "bias", "efficacy"]) {
    if (brain[key]) h.update(Buffer.from(brain[key].buffer, brain[key].byteOffset, brain[key].byteLength));
  }
  if (!weightsOnly) h.update(String(brain.steps));
  return h.digest("hex");
}
const levels = brain => ({ integrator: brain.mean("_Int_"), gaze_degrees: GAZE_DEGREES_PER_UNIT * (brain.mean("ABD_m") + brain.mean("ABD_i")) });
function probeHalf(live, level) {
  const before = digestBrain(live), brain = new SettlingBrain(payload);
  brain.w.set(live.w); brain.bias.set(live.bias);
  brain.stimulate("_Int_", level);
  for (let k = 0; k < protocol.probe_burst_steps; k++) brain.step();
  brain.clearStimuli();
  for (let k = 0; k < protocol.probe_delay_steps; k++) brain.step();
  const initial = levels(brain), samples = [];
  let previous = 0;
  for (const seconds of protocol.probe_seconds) {
    const steps = Math.round(seconds / protocol.probe_step_seconds);
    for (let k = previous; k < steps; k++) brain.step();
    previous = steps;
    const values = levels(brain);
    const ratios = Object.fromEntries(Object.entries(values).map(([key, value]) => [key, initial[key] > 0 ? value / initial[key] : null]));
    assert(Object.values(values).every(Number.isFinite), "nonfinite independent assessment");
    samples.push({ seconds, ...values, retention: ratios,
      growing: ratios.gaze_degrees !== null && ratios.gaze_degrees > 1.05 });
  }
  assert.equal(digestBrain(live), before, "an assessment changed the continuing brain");
  return { level, initial, samples };
}
function assess(twin) {
  return Object.fromEntries(SIDES.map(side => [side, {
    weights_sha256: digestBrain(twin.halves[side], true),
    probes: protocol.probe_levels.map(level => probeHalf(twin.halves[side], level)),
  }]));
}
function phase(life, spec) {
  life.setWorld(spec.world);
  const lessons0 = life.learning.lessons, saccades0 = life.saccades.count;
  const events = { taken: 0, growing: 0, decaying: 0, zero: 0, per_side: { left: 0, right: 0 } };
  let maxGaze = 0, pinnedTicks = 0, previousFixations = life.learning.fixations;
  for (let k = 0; k < Math.round(spec.seconds / protocol.dt_seconds); k++) {
    life.step(protocol.dt_seconds);
    maxGaze = Math.max(maxGaze, Math.abs(life.gaze));
    if (Math.abs(life.gaze) >= 24.9) pinnedTicks++;
    const count = life.learning.fixations - previousFixations;
    assert(count >= 0 && count <= life.learning.log.length, "lost fixation events");
    if (count) for (const event of life.learning.log.slice(-count)) if (event.taken) {
      events.taken++; events.per_side[event.side]++;
      if (event.level1 >= event.level0 && event.level0 > 0) events.growing++;
      else if (event.level1 > 0) events.decaying++;
      else events.zero++;
    }
    previousFixations = life.learning.fixations;
  }
  assert.equal(events.taken, life.learning.lessons - lessons0, "missed a lesson in the audit log");
  for (const side of SIDES) for (const value of life.brain.halves[side].w) assert(Number.isFinite(value), "nonfinite learned weight");
  return { ...spec, time: life.time, lessons: events, saccades: life.saccades.count - saccades0,
    gaze_max_degrees: maxGaze, gaze_at_limit_seconds: pinnedTicks * protocol.dt_seconds,
    assessment: assess(life.brain) };
}
function run(seed, learning) {
  const twin = new TwinBrain(payload, { learning: true }), life = new Life(twin, seed);
  // Directly freeze only the lesson gate, avoiding the older setLearning(false) gain reset.
  // Both arms therefore begin with byte-identical .8-gain synapses on old and new implementations.
  if (!learning) { twin.learning = false; life.learning.on = false; }
  const initial = assess(twin);
  const phases = protocol.phases.map(spec => phase(life, spec));
  if (!learning) for (const p of phases) for (const side of SIDES) {
    assert.equal(p.assessment[side].weights_sha256, initial[side].weights_sha256, "frozen control changed weights");
    assert.equal(p.lessons.taken, 0, "frozen control took a lesson");
  }
  const result = { seed, learning, initial, phases };
  const brief = p => Object.fromEntries(SIDES.map(side => [side, p.assessment[side].probes.map(probe => +probe.samples.find(s => s.seconds === 12).retention.gaze_degrees.toFixed(4))]));
  console.log(JSON.stringify({ seed, learning, retention_12s: Object.fromEntries(phases.map(p => [p.name, brief(p)])), lessons: phases.map(p => p.lessons.taken) }));
  return result;
}
const runs = [];
for (const seed of seeds) { runs.push(run(seed, false)); runs.push(run(seed, true)); }
const failures = [], observations = [];
for (const seed of seeds) {
  const learned = runs.find(r => r.seed === seed && r.learning), frozen = runs.find(r => r.seed === seed && !r.learning);
  for (const side of SIDES) {
    assert.equal(learned.initial[side].weights_sha256, frozen.initial[side].weights_sha256, "unmatched initial gain or weights");
    for (let index = 0; index < protocol.probe_levels.length; index++) {
      const ratio = (run, phase, seconds) => run.phases.find(p => p.name === phase).assessment[side].probes[index].samples.find(s => s.seconds === seconds).retention.gaze_degrees;
      const control = ratio(frozen, "hold", 12), hold = ratio(learned, "hold", 12), hold24 = ratio(learned, "hold", 24), back = ratio(learned, "return", 12), recovery = ratio(learned, "recovery", 12);
      const row = { seed, side, level: protocol.probe_levels[index], frozen_12s: control, hold_12s: hold, hold_24s: hold24, return_12s: back, recovery_12s: recovery,
        holds: hold >= Math.exp(-12 / 10) && hold <= 1.05 && hold24 <= 1.05 && hold > control * 10,
        returns: back < hold / 2 && back < Math.exp(-12 / 6),
        recovers: recovery >= Math.exp(-12 / 10) && recovery <= 1.05 };
      observations.push(row);
      if (!row.holds) failures.push(`seed ${seed} ${side} level ${row.level}: still lesson fails independent retention/growth criterion`);
      if (!row.returns) failures.push(`seed ${seed} ${side} level ${row.level}: return lesson fails independent decay criterion`);
    }
  }
}
assert.deepEqual(sourceHashes(), sources, "sources changed during this run; rerun before recording evidence");
const receipt = { schema: "cadence-learning-release/1", generated_at: new Date().toISOString(), node: process.version,
  command: `node tests/learning_release.mjs${seeds.join(",") === "7,8,9" ? "" : ` --seeds ${seeds.join(",")}`} --out receipts/learning_release.json`,
  sources_sha256: sources, protocol, runs, observations,
  verdict: { simple_hold_and_return_supported: failures.length === 0, failures,
    recovery_all_probes: observations.every(row => row.recovers),
    scope: "Declared population-rate model and teacher. No biological learning claim, general intelligence claim, uniform-random policy comparison, or proof of long-run stability." } };
const output = arg("out", "");
if (output) writeFileSync(output, JSON.stringify(receipt, null, 2) + "\n");
console.log(JSON.stringify(receipt.verdict, null, 2));
if (failures.length && !process.argv.includes("--report-only")) process.exitCode = 1;
