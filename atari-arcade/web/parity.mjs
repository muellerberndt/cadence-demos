// The browser engine against the library. fixtures/parity_system1.json holds what the released Cadence 0.70.0
// package answered (tools/make_parity_fixture.py): the generator's first draws, digests of newborn efficacies, and
// two tapes driven through the calls the arcade makes. Births must match bit for bit. On the tapes every answer,
// sampled action and sweep count must be identical, and activations, values, dopamine and parameters must agree
// within BOUND; the two engines add the same products in a different order, so the last digits differ.
//   node parity.mjs            (from atari-arcade/web)
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Brain, Generator } from './cadence.js';

const root = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(join(root, 'fixtures/parity_system1.json'), 'utf8'));
const BOUND = 1e-9;
const report = [];
let failures = 0;
const check = (name, ok, detail = {}) => { report.push({ check: name, ok, ...detail }); if (!ok) failures++; };
const maxDiff = (a, b) => { if (a.length !== b.length) return Infinity; let m = 0; for (let i = 0; i < a.length; i++) m = Math.max(m, Math.abs(a[i] - b[i])); return m; };
const sum = a => { let s = 0; for (const v of a) s += v; return s; };
const absSum = a => { let s = 0; for (const v of a) s += Math.abs(v); return s; };
const compose = (inputs, actions) => Brain.compose(inputs, actions, { seed: 0, learning: fixture.learning, reward: fixture.reward });

// The screens of the tapes: the same integer formula as the fixture's.
function screen(t, n) {
  const x = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const h = (i * 73 + t * 151) % 997;
    if (h < 9) x[i] = 0.2 + 0.09 * h;
    else if (h > 990) x[i] = -0.04;
  }
  return x;
}

// 1. numpy's generator.
const rng = new Generator(fixture.generator.seed);
check('generator draws', fixture.generator.first.every(v => v === rng.random()));

// 2. Births: every efficacy, in the library's synapse order.
for (const [actions, want] of Object.entries(fixture.births)) {
  const brain = compose(84 * 84, Number(actions)), efficacy = brain.efficacy();
  const digest = createHash('sha256').update(Buffer.from(efficacy.buffer)).digest('hex');
  check(`birth ${actions} actions`, efficacy.length === want.synapses && digest === want.efficacy_sha256, { synapses: efficacy.length });
}

// 3. The tapes.
function summary(brain) {
  const efficacy = brain.efficacy(), stride = Math.max(1, Math.floor(efficacy.length / 1500)), sample = [];
  for (let k = 0; k < efficacy.length; k += stride) sample.push(efficacy[k]);
  return {
    bias_association: brain.bH, bias_motor: brain.bM, critic: [...brain.wCritic, brain.bCritic],
    working_trace: brain.workingTrace ?? [], memory_sum: sum(brain.consolidated), memory_abs: absSum(brain.consolidated),
    efficacy_sum: sum(efficacy), efficacy_abs: absSum(efficacy), efficacy_sample: sample,
  };
}

function compareSummary(name, got, want, brain) {
  const worst = Math.max(
    maxDiff(got.bias_association, want.bias_association), maxDiff(got.bias_motor, want.bias_motor),
    maxDiff(got.critic, want.critic), maxDiff(got.working_trace, want.working_trace),
    maxDiff(got.efficacy_sample, want.efficacy_sample),
    Math.abs(got.memory_sum - want.memory_sum), Math.abs(got.memory_abs - want.memory_abs),
    Math.abs(got.efficacy_sum - want.efficacy_sum) / want.efficacy_abs, Math.abs(got.efficacy_abs - want.efficacy_abs) / want.efficacy_abs);
  let blocks = 0;
  if (want.blocks) {
    for (const key of ['sa', 'am', 'ma', 'pa', 'mm']) blocks = Math.max(blocks, maxDiff(brain.w[key], want.blocks[key]));
    blocks = Math.max(blocks, maxDiff(brain.consolidated, want.memory));
  }
  check(name, worst <= BOUND && blocks <= BOUND, { worst, every_parameter: want.blocks ? blocks : undefined });
}

function runTape(name, tape) {
  const brain = compose(tape.inputs, tape.actions);
  let discrete = 0, continuous = 0, pending = false, frozenStarted = false;
  for (const event of tape.events) {
    const x = screen(event.t, tape.inputs);
    if (event.kind === 'watch') {
      const drive = brain.stimulus(x);
      const own = brain.act(x, { greedy: true });
      const motor = brain.free.sM.slice();
      const lesson = brain.teach(drive, event.label);
      if (own !== event.own || lesson.free_steps !== event.free_steps || lesson.nudged_steps !== event.nudged_steps) discrete++;
      continuous = Math.max(continuous, maxDiff(motor, event.motor));
    } else if (event.kind === 'play') {
      const action = pending ? brain.step(x, { reward: event.reward, done: event.done }) : brain.step(x);
      pending = true;
      if (action !== event.action || (event.free_steps ?? null) !== (brain.lastLearning.free_steps ?? null)) discrete++;
      continuous = Math.max(continuous, maxDiff(brain.free.sM, event.motor), Math.abs(brain.value(brain.free) - event.value));
      if (event.dopamine !== null && event.dopamine !== undefined) {
        continuous = Math.max(continuous, Math.abs(brain.lastLearning.dopamine - event.dopamine), Math.abs(brain.lastLearning.td_error - event.td_error));
      }
    } else {
      if (!frozenStarted) { compareSummary(`${name}: parameters after the lived stretch`, summary(brain), tape.after_play, brain); brain.reset(); frozenStarted = true; }
      const action = brain.act(x);
      if (action !== event.action) discrete++;
      continuous = Math.max(continuous, maxDiff(brain.free.sM, event.motor));
    }
  }
  check(`${name}: answers, actions and sweep counts`, discrete === 0, { events: tape.events.length, differing: discrete });
  check(`${name}: activations, values and dopamine`, continuous <= BOUND, { worst: continuous });
  compareSummary(`${name}: parameters at the end`, summary(brain), tape.after_frozen, brain);
}

runTape('small brain', fixture.small);
runTape('arcade brain', fixture.arcade);

for (const line of report) console.log(JSON.stringify(line));
console.log(failures === 0 ? `PARITY PASSED against cadence-net ${fixture.library}` : `PARITY FAILED: ${failures} check(s)`);
process.exit(failures === 0 ? 0 : 1);
