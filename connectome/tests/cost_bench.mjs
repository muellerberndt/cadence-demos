// The cost of a second of fish time: the settling engine against the spiking port on the
// same payload, same machine. Writes receipts/cost.json for the "why" page.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { SettlingBrain } from "../web/brain.js";
import { SpikingBrain } from "../web/spiking.js";
import { STEP_MS } from "../web/dictionary.js";
const here = dirname(fileURLToPath(import.meta.url));
globalThis.atob ??= (b) => Buffer.from(b, "base64").toString("binary");
const now = () => Number(process.hrtime.bigint()) / 1e6;
function best(fn, reps = 3) { let b = Infinity; for (let r = 0; r < reps; r++) { const t = fn(); if (t < b) b = t; } return b; }
const out = { payloads: {}, note: "ms of wall time on one core of this machine; a second of fish time at the declared step of " + STEP_MS + " ms (one fifth of the unit's time constant of 0.2 s) and at a 20 ms time constant (4 ms steps)" };
for (const name of ["brain.json", "brain_oculomotor.json", "larva_brain.json"]) {
  const payload = JSON.parse(readFileSync(join(here, "..", "web", "data", name), "utf8"));
  const settle = new SettlingBrain(payload); settle.stimulate(payload.populations["_Int_"] ? "_Int_" : "PRC:left", 0.03); for (let i = 0; i < 100; i++) settle.step();
  const msPerStep = best(() => { const t0 = now(); for (let i = 0; i < 2000; i++) settle.step(); return (now() - t0) / 2000; });
  const row = { neurons: settle.n, classes: settle.edges, settling: { ms_per_step: msPerStep, steps_per_fish_second_declared: 1000 / STEP_MS, ms_per_fish_second_declared: msPerStep * 1000 / STEP_MS, steps_per_fish_second_tau20ms: 250, ms_per_fish_second_tau20ms: msPerStep * 250 }, spiking: {} };
  for (const w of [0.35, 2.7]) {
    const spike = new SpikingBrain(payload, { wSynMv: w, seed: 1 }); spike.drive(payload.populations["_Int_"] ? "_Int_" : "PRC:left", true); spike.run(200);
    const msPerSimMs = best(() => { const t0 = now(); spike.run(1000); return (now() - t0) / 1000; }, 2);
    const rate = spike.rates(500); let mean = 0; for (const r of rate) mean += r; mean /= rate.length;
    row.spiking["w_" + w + "_mV"] = { ms_per_sim_ms: msPerSimMs, ms_per_fish_second: msPerSimMs * 1000, steps_per_fish_second: 10000, mean_rate_hz: mean };
  }
  row.ratio_declared = row.spiking["w_0.35_mV"].ms_per_fish_second / row.settling.ms_per_fish_second_declared;
  row.ratio_tau20ms = row.spiking["w_0.35_mV"].ms_per_fish_second / row.settling.ms_per_fish_second_tau20ms;
  out.payloads[name] = row;
  console.log(`${name}: ${settle.n} neurons, ${settle.edges} classes | settling ${msPerStep.toFixed(3)} ms/step, ${row.settling.ms_per_fish_second_declared.toFixed(1)} ms per fish second (declared), ${row.settling.ms_per_fish_second_tau20ms.toFixed(1)} ms (tau 20 ms) | spiking 0.35 mV ${row.spiking["w_0.35_mV"].ms_per_fish_second.toFixed(1)} ms per fish second at ${row.spiking["w_0.35_mV"].mean_rate_hz.toFixed(1)} Hz mean; 2.7 mV ${row.spiking["w_2.7_mV"].ms_per_fish_second.toFixed(1)} ms at ${row.spiking["w_2.7_mV"].mean_rate_hz.toFixed(1)} Hz | ratio ${row.ratio_declared.toFixed(1)}x declared, ${row.ratio_tau20ms.toFixed(1)}x at tau 20 ms`);
}
out.node = process.version; out.date = new Date().toISOString().slice(0, 10);
writeFileSync(join(here, "..", "receipts", "cost.json"), JSON.stringify(out, null, 1));
console.log("wrote receipts/cost.json");
