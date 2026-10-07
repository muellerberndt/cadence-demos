// Wall time per simulated millisecond of web/spiking.js in node: the oculomotor wiring and the whole
// reconstruction, the integrator neurons driven at w_syn 0.35 mV, three timed seconds each after a warm-up.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { performance } from "node:perf_hooks";
import { SpikingBrain } from "../web/spiking.js";

const here = dirname(fileURLToPath(import.meta.url));
globalThis.atob ??= (b) => Buffer.from(b, "base64").toString("binary");
const wSynMv = Number(process.argv[2] ?? 0.35), population = process.argv[3] ?? "_Int_";
const sum = (a) => { let s = 0; for (const x of a) s += x; return s; };
for (const [name, file] of [["oculomotor", "brain_oculomotor.json"], ["all", "brain.json"]]) {
  const payload = JSON.parse(readFileSync(join(here, "..", "web", "data", file), "utf8"));
  const brain = new SpikingBrain(payload, { wSynMv, seed: 1 });
  brain.drive(population, true);
  brain.run(200);
  const timings = [];
  for (let r = 0; r < 3; r++) {
    const before = sum(brain.counts), t0 = performance.now();
    brain.run(1000);
    const wall = performance.now() - t0, spikes = sum(brain.counts) - before;
    timings.push({ wall, spikes });
  }
  const best = Math.min(...timings.map((x) => x.wall)), spikes = timings.map((x) => x.spikes);
  console.log(`${name}: ${brain.n} neurons, ${brain.edges} synapse classes, ${brain.drivenList.length} driven at w_syn ${wSynMv} mV: `
    + `${(best / 1000).toFixed(4)} ms wall per simulated ms (best of ${timings.map((x) => (x.wall / 1000).toFixed(4)).join(", ")}); `
    + `${spikes.join(", ")} spikes per simulated second, mean ${(spikes[spikes.length - 1] / brain.n).toFixed(1)} Hz over all neurons`);
}
