// The browser engine against the library. fixtures/parity_small.json holds what the reference engine answered for a
// miniature of the arcade layout (built, queried, taught in two batches, driven through Reinforcement with replay);
// fixtures/parity_arcade.json digests the full arcade brains at birth. Every wiring choice and newborn weight must
// match bit for bit (same seed, same Mersenne Twister draws). Settled states must agree within tolerance / state_prior,
// the distance a qualified equilibrium can sit from the exact stationary point. Admission decisions, action choices
// and replay samples must be identical; admitted parameters and replay targets must agree within PARAMETER_BOUND.
// Sweep counts are reported side by side: the browser engine sums each patch's drive with Neumaier compensation
// where the library rounds exactly, so the two line searches part at the last digit and finish a few sweeps apart.
//   node parity.mjs            (from atari-arcade/web)
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Cortex, Reinforcement } from './cadence.js';
import { buildBrain } from './arcade.js';

const root = dirname(fileURLToPath(import.meta.url));
const small = JSON.parse(readFileSync(join(root, 'fixtures/parity_small.json'), 'utf8'));
const arcade = JSON.parse(readFileSync(join(root, 'fixtures/parity_arcade.json'), 'utf8'));
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const pyJson = value => JSON.stringify(value).replaceAll(',', ', ');
const maxDiff = (a, b) => { let m = 0; for (let i = 0; i < a.length; i++) m = Math.max(m, Math.abs(a[i] - b[i])); return a.length === b.length ? m : Infinity; };
const PARAMETER_BOUND = 1e-4;
const report = [];
let failures = 0;
const check = (name, ok, detail) => { report.push({ check: name, ok, ...detail }); if (!ok) failures++; };

// 1. The full arcade brains at birth.
for (const n of [3, 4]) {
  const want = arcade[String(n)], brain = buildBrain(n), g = brain.graph;
  const edges = []; for (let e = 0; e < g.nEdges; e++) edges.push(g.edge(e));
  check(`arcade birth ${n} actions`,
    g.nInputs === want.n_inputs && g.nPatches === want.n_patches && g.nEdges === want.edges
      && sha(pyJson(edges)) === want.edge_digest
      && sha(pyJson(Array.from(g.residualOrder))) === want.residual_order_digest
      && sha(Buffer.from(brain.weights.buffer)) === want.weights_digest,
    { edges: g.nEdges, weights_head: Array.from(brain.weights.slice(0, 3)) });
}

// 2. The miniature: identical birth.
function smallBrain() {
  const c = new Cortex({ seed: 0, settle_budget: 4096, parameter_prior: 0.4 });
  const t0 = c.input('tile0', { shape: [4, 4] }), t1 = c.input('tile1', { shape: [4, 4] }), act = c.input('action', { shape: [3] });
  const c0 = c.column('t0', { patches: 4, inputs: [t0] }), c1 = c.column('t1', { patches: 4, inputs: [t1] });
  const r = c.observer('r', { patches: 3, observes: [c0, c1] });
  const p = c.observer('p', { patches: 4, observes: [c0, c1, r] });
  const v = c.observer('v', { patches: 2, inputs: [act], observes: [r, p] });
  c.output('motor', { shape: [3], reads: p });
  c.output('value', { shape: [1], reads: v });
  return c.build();
}
const b = smallBrain(), g = b.graph;
const edges = []; for (let e = 0; e < g.nEdges; e++) edges.push(g.edge(e));
check('small birth', JSON.stringify(edges) === JSON.stringify(small.edges) && maxDiff(b.weights, small.weights0) === 0
  && JSON.stringify(Array.from(g.residualOrder)) === JSON.stringify(small.residual_order), { edges: g.nEdges });
const bound = b.config.tolerance / b.config.state_prior;
const zero = [0, 0, 0];

// 3. A query.
let res = b.settle({ ...small.query0.inputs, action: zero }, { budget: 64 });
check('query before learning', res.qualified === small.query0.qualified && maxDiff(res.state, small.query0.state) <= bound,
  { sweeps: [res.sweeps, small.query0.sweeps], state_diff: maxDiff(res.state, small.query0.state), bound });

// 4. Two witness batches.
small.batches.forEach((batch, k) => {
  const examples = batch.examples.map(([inputs, targets]) => ({ inputs, targets }));
  const r = b.observeBatch(examples);
  const wd = maxDiff(b.weights, batch.weights), bd = maxDiff(b.biases, batch.biases);
  check(`batch ${k + 1} (${examples.length} witnesses)`, r.accepted === batch.accepted && wd <= PARAMETER_BOUND && bd <= PARAMETER_BOUND,
    { sweeps: [r.sweeps, batch.sweeps], accepted: [r.accepted, batch.accepted], weight_diff: wd, bias_diff: bd, energy: [r.energy, batch.energy] });
});

// 5. A query after learning.
res = b.settle({ ...small.query1.inputs, action: zero }, { budget: 64 });
check('query after learning', res.qualified === small.query1.qualified && maxDiff(res.state, small.query1.state) <= bound,
  { sweeps: [res.sweeps, small.query1.sweeps], state_diff: maxDiff(res.state, small.query1.state), bound });

// 6. Reinforcement: acting, feedback, replay.
const rf = new Reinforcement(b, { actions: 3, action_input: 'action', value_output: 'value', discount: 0.95, exploration: 0.05,
                                  reward_scale: 1.0, capacity: 2048, batch_size: 16, seed: 0 });
const actions = [], valueDiffs = [];
for (const step of small.reinforcement.steps) {
  const picked = rf.act(step.inputs, { budget: 256 });
  actions.push([picked.action, step.action, picked.exploratory, step.exploratory]);
  valueDiffs.push(maxDiff(picked.values, step.values));
  const fb = rf.feedback(step.reward, step.next, { terminal: step.terminal, learn: false });
  if (fb.transitions !== step.transitions) failures++;
}
check('acting matches', actions.every(([a, want, e, we]) => a === want && e === we), { actions, max_value_diff: Math.max(...valueDiffs) });
const rp = rf.replay({ budget: 2048 }), want = small.reinforcement.replay;
const wd = maxDiff(b.weights, want.weights);
check('replay matches', JSON.stringify(rp.indices) === JSON.stringify(want.indices) && rp.accepted === want.accepted
  && maxDiff(rp.targets, want.targets) <= PARAMETER_BOUND && wd <= PARAMETER_BOUND,
  { indices: [rp.indices, want.indices], targets_diff: maxDiff(rp.targets, want.targets), accepted: [rp.accepted, want.accepted],
    sweeps: [rp.sweeps, want.sweeps], weight_diff: wd });

for (const row of report) console.log((row.ok ? 'OK  ' : 'FAIL') + ' ' + JSON.stringify(row));
console.log(failures ? `PARITY FAILED: ${failures}` : 'PARITY PASSED');
process.exit(failures ? 1 : 0);
