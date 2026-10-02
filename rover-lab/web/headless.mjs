// Run the automatic demonstration of the browser edition without a browser and write its measurements.
//
//   node headless.mjs                 seeds 17 29 101 211 307, receipts/automatic.json
//   node headless.mjs 17 --paced      one seed at the page's real-time pace (ten control steps per second)
//
// Unpaced runs step as fast as the machine allows; the sensing-to-command time of every step is still measured.
import { createHash } from 'node:crypto';
import { writeFileSync } from 'node:fs';
import { AUTOMATIC_STEPS, ENGINE, Life, PROTOCOL } from './rover.js';

const args = process.argv.slice(2);
const paced = args.includes('--paced');
const seeds = args.filter(a => /^\d+$/.test(a)).map(Number);
if (!seeds.length) seeds.push(17, 29, 101, 211, 307);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

const outcomes = [];
for (const seed of seeds) {
  const started = performance.now();
  const life = new Life(seed);
  let deadline = performance.now();
  while (life.step < AUTOMATIC_STEPS) {
    let queueDelay = 0;
    if (paced) {
      const wait = deadline - performance.now();
      if (wait > 0) await sleep(wait);
      queueDelay = Math.max(0, performance.now() - deadline);
    }
    life.tick(queueDelay);
    deadline = Math.max(deadline + 1000 * PROTOCOL.dt, performance.now());
  }
  const receipt = life.receipt();
  const { transitions, ...summary } = receipt;
  // The step record without wall-clock fields: the same seed gives the same hash on the same JavaScript engine.
  const record = transitions.map(({ latency_ms, queue_delay_ms, command_age_ms, ...row }) => row);
  outcomes.push({ ...summary, elapsed_seconds: (performance.now() - started) / 1000, paced,
                  transition_sha256: createHash('sha256').update(JSON.stringify(record)).digest('hex') });
  const live = receipt.metrics.cadence, frozen = receipt.metrics.frozen;
  const row = arm => PROTOCOL.phases.map(([phase]) => `${arm[phase].targets}/${arm[phase].attempts}`).join('  ');
  console.log(`seed ${seed}: gate ${receipt.gate.passed ? 'PASS' : 'FAIL'}, weak distance ratio ${receipt.gate.weak_distance_ratio.toFixed(3)}; `
    + `targets live ${row(live)}, frozen ${row(frozen)}; p95 step ${Math.max(...Object.values(live).map(v => v.latencies_p95_ms)).toFixed(2)} ms`);
}
const path = new URL(`./receipts/${paced ? 'paced' : 'automatic'}.json`, import.meta.url);
writeFileSync(path, JSON.stringify({ engine: ENGINE, runtime: `node ${process.version}`, outcomes }, null, 1) + '\n');
console.log(`wrote ${path.pathname}`);
