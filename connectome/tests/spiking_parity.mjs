// The spiking port against the Python port: the Poisson events verify_lif.simulate consumed, replayed
// through web/spiking.js on the oculomotor wiring; every spike's step and neuron, and
// every neuron's spike count per bin, must match exactly.
// Then the seeded generator on its own: the integrator's mean rate under drive within 20 percent of Python's.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { SpikingBrain } from "../web/spiking.js";

const here = dirname(fileURLToPath(import.meta.url));
globalThis.atob ??= (b) => Buffer.from(b, "base64").toString("binary");
const payload = JSON.parse(readFileSync(join(here, "..", "web", "data", "brain_oculomotor.json"), "utf8"));
const cases = JSON.parse(readFileSync(join(here, "spiking_parity_cases.json"), "utf8"));
const fail = (message) => { console.error(message); process.exit(1); };
if (cases.format !== "cadence.spiking-parity-cases/2" || !Array.isArray(cases.spikes) || !cases.spikes.length) fail("exact spike timing requires the v2 Python parity fixture");
if (payload.connectome_digest !== cases.connectome_digest) fail("the payload and the cases come from different connectomes");
const lif = cases.lif;
const options = { wSynMv: cases.w_syn_mv, dtMs: lif.dt_ms, vThMv: lif.v_th_mv, tMbrMs: lif.t_mbr_ms, tauMs: lif.tau_ms, tRfcMs: lif.t_rfc_ms,
                  tDlyMs: lif.t_dly_ms, rPoiHz: lif.r_poi_hz, fPoi: lif.f_poi, seed: cases.seed[0], historyMs: cases.t_run_ms };
const sum = (a) => { let s = 0; for (const x of a) s += x; return s; };
const meanOver = (a, idx) => sum(idx.map((i) => a[i])) / idx.length;

// 1. the per-step constants, bit for bit against Python's
let brain = new SpikingBrain(payload, { ...options, eventSchedule: cases.events });
const pairs = [["eM", "e_m"], ["eS", "e_s"], ["c", "c"], ["pEvent", "p_event"], ["kickMv", "kick_mv"], ["delay", "delay_steps"], ["refractory", "refractory_steps"]];
const checks = pairs.map(([js, py]) => ({ js, py, a: brain.constants[js], b: cases.constants[py], same: Object.is(brain.constants[js], cases.constants[py]) }));
for (const k of checks) console.log(`${k.js}: js ${k.a} python ${k.b} ${k.same ? "identical" : "DIFFER"}`);
const stepConstantsDiffer = checks.filter((k) => !k.same && ["eM", "eS", "c"].includes(k.js));
if (checks.some((k) => !k.same && !["eM", "eS", "c"].includes(k.js))) fail("the derived constants differ from Python's");
if (stepConstantsDiffer.length) {
  console.warn(`this platform's Math.exp differs from numpy's in the last bit for ${stepConstantsDiffer.map((k) => k.js).join(", ")}; replaying with Python's constants`);
  brain = new SpikingBrain(payload, { ...options, eventSchedule: cases.events, constants: { eM: cases.constants.e_m, eS: cases.constants.e_s, c: cases.constants.c } });
}

// 2. the schedule replay. simulate keeps its stimulated neurons without a refractory period for the whole trial and
// stops their events at drive_until; here the drive stays on and the schedule itself ends at drive_until.
if (cases.events.some((e) => e[0] >= cases.drive_until)) fail("the schedule holds events past drive_until");
brain.drive(cases.population, true);
const n = brain.n, stim = cases.stimulated;
let previous = new Int32Array(n), mismatches = 0;
const examples = [];
for (let b = 0; b + 1 < cases.bins.length; b++) {
  const edge = cases.bins[b + 1];
  while (brain.steps < edge) brain.step();
  const expected = cases.counts[b];
  let got = 0, want = 0;
  for (let i = 0; i < n; i++) {
    const d = brain.counts[i] - previous[i];
    got += d; want += expected[i];
    if (d !== expected[i]) { mismatches++; if (examples.length < 10) examples.push(`bin ${b} neuron ${i}: js ${d} python ${expected[i]}`); }
  }
  const jsInt = meanOver(Array.from(brain.counts, (x, i) => x - previous[i]), stim) / (cases.bin_ms / 1000);
  console.log(`bin ${b} steps [${cases.bins[b]}, ${edge}): js ${got} spikes, python ${want}; ${cases.population} mean ${jsInt.toFixed(2)} Hz, python ${cases.mean_hz.stimulated[b].toFixed(2)} Hz`);
  previous = Int32Array.from(brain.counts);
}
if (mismatches) { for (const e of examples) console.error(e); fail(`parity failed: ${mismatches} of ${n * (cases.bins.length - 1)} per-neuron per-bin counts differ`); }
const total = sum(brain.counts), raster = brain.spikesSince(0);
if (raster.neurons.length !== total) fail(`spikesSince(0) returned ${raster.neurons.length} spikes, counts hold ${total}`);
// Ordering of simultaneous spikes is immaterial; neuron identity and the exact
// time step are not. Sorting also matches numpy.nonzero's row-major fixture order.
const spikes = Array.from(raster.neurons, (neuron, k) => [Math.round(raster.times[k] / brain.dtMs), neuron]);
spikes.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
if (spikes.length !== cases.spikes.length) fail(`exact raster length differs: js ${spikes.length}, python ${cases.spikes.length}`);
for (let k = 0; k < spikes.length; k++) {
  const [step, neuron] = spikes[k], [expectedStep, expectedNeuron] = cases.spikes[k];
  if (step !== expectedStep || neuron !== expectedNeuron) fail(`exact spike ${k} differs: js [${step}, ${neuron}], python [${expectedStep}, ${expectedNeuron}]`);
}
const lastBin = brain.rates(cases.bin_ms), lastCounts = cases.counts[cases.bins.length - 2];
for (let i = 0; i < n; i++) if (Math.round(lastBin[i] * cases.bin_ms / 1000) !== lastCounts[i]) fail(`rates(${cases.bin_ms}) disagrees with the last bin at neuron ${i}`);
console.log(`schedule replay ok: ${cases.events.length} events, ${total} spikes over ${cases.t_run_ms} ms, every spike step/neuron and per-neuron per-bin count identical${stepConstantsDiffer.length ? " (with Python's step constants)" : ""}`);

// 3. the seeded generator: a reproducible run whose integrator rate under drive is near Python's
const free = new SpikingBrain(payload, { ...options, seed: 7 });
free.drive(cases.population, true);
free.run(cases.drive_ms);
const window = cases.bin_ms, jsRates = free.rates(window);
const jsMean = meanOver(Array.from(jsRates), stim), pyMean = cases.mean_hz.stimulated[Math.round(cases.drive_ms / cases.bin_ms) - 1];
const firstTotal = sum(free.counts);
free.reset(); free.run(cases.drive_ms);
if (sum(free.counts) !== firstTotal) fail("the seeded generator is not reproducible across reset()");
const relative = Math.abs(jsMean - pyMean) / pyMean;
console.log(`seeded generator: ${cases.population} mean ${jsMean.toFixed(2)} Hz over the last ${window} ms of drive, python ${pyMean.toFixed(2)} Hz, ${(100 * relative).toFixed(1)} percent apart; reproducible (${firstTotal} spikes twice)`);
if (!(relative <= 0.2)) fail("the seeded generator's integrator rate is more than 20 percent from Python's");
console.log(`spiking parity ok: ${n} neurons, ${brain.edges} synapse classes`);
