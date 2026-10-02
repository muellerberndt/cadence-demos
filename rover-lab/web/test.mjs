// Behaviour checks of the browser edition that need no reference values.   node test.mjs
import assert from 'node:assert/strict';
import { Brain, Cortex, SettlementError } from './cadence.js';
import { makeModel, modelFromSnapshot } from './models.js';
import { ACTIONS, AUTOMATIC_STEPS, Life, bodyMotion, demonstrationGate, summarize } from './rover.js';

const untimed = rows => rows.map(({ latency_ms, queue_delay_ms, command_age_ms, ...row }) => row);
let passed = 0;
const test = (name, body) => { body(); passed += 1; console.log(`ok  ${name}`); };

test('a life is a function of its seed', () => {
  const a = new Life(17), b = new Life(17);
  for (let i = 0; i < 200; i++) { a.tick(); b.tick(); }
  assert.deepEqual(untimed(a.rows), untimed(b.rows));
});

test('a saved life continues as the uninterrupted one does', () => {
  const whole = new Life(29);
  for (let i = 0; i < 260; i++) whole.tick();
  const resumed = Life.fromSnapshot(JSON.parse(JSON.stringify(whole.snapshot())));
  for (let i = 0; i < 260; i++) { whole.tick(); resumed.tick(); }
  assert.deepEqual(untimed(resumed.rows), untimed(whole.rows));
  for (const kind of ['cadence', 'frozen']) {
    assert.deepEqual(resumed.arms[kind].model.brain.weights, whole.arms[kind].model.brain.weights);
  }
});

test('the frozen copy never changes and starts as the live brain did', () => {
  const life = new Life(17);
  const birth = JSON.stringify(life.arms.frozen.model.brain.snapshot());
  assert.equal(JSON.stringify(life.arms.cadence.model.brain.snapshot()), birth);
  for (let i = 0; i < 240; i++) life.tick();
  const frozen = life.arms.frozen.model.brain.snapshot(), live = life.arms.cadence.model.brain.snapshot();
  assert.deepEqual([frozen.weights, frozen.biases, frozen.admissions], [JSON.parse(birth).weights, JSON.parse(birth).biases, JSON.parse(birth).admissions]);
  assert.notDeepEqual(live.weights, frozen.weights);
});

test('the return probe teaches no model', () => {
  const life = new Life(17);
  for (let i = 0; i < 200; i++) life.tick();
  life.auto = false;
  life.changePhase('restored_probe');
  const before = Object.fromEntries(Object.entries(life.arms).map(([kind, arm]) => [kind, arm.model.presentations]));
  for (let i = 0; i < 40; i++) life.tick();
  for (const [kind, arm] of Object.entries(life.arms)) assert.equal(arm.model.presentations, before[kind], kind);
});

test('models see commands and motion only; the body alone has the wheel gain', () => {
  const model = makeModel('coupled', 3);
  assert.equal(model.learn([0.4, 0.8], bodyMotion([0.4, 0.8], 0.35)), true);
  assert.throws(() => model.learn([0.9, 0.0], [0.1, 0.1]), /motor commands/);
  assert.throws(() => model.learn([0.4, 0.4], [1.5, 0.0]), /measured motion/);
});

test('a forecast is pure and a refused solve raises', () => {
  const model = makeModel('coupled', 5);
  for (const a of ACTIONS) model.learn(a, bodyMotion(a));
  const before = JSON.stringify(model.brain.snapshot());
  model.query(ACTIONS);
  assert.equal(JSON.stringify(model.brain.snapshot()), before);
  const refused = model.brain.settle({ motors: [0.8, 0.0] }, { budget: 1 });
  assert.equal(refused.qualified, false);
  assert.throws(() => model.constructor._qualified(refused), SettlementError);
  const admitted = model.brain.admissions;
  const result = model.brain.observe({ motors: [0.8, 0.0] }, { motion_readout: [0.4, -0.4] }, { budget: 1 });
  assert.equal(result.accepted, false);
  assert.equal(model.brain.admissions, admitted);
  assert.equal(JSON.stringify(model.brain.snapshot()), before);
});

test('a layout whose populations do not settle together is refused', () => {
  const cortex = new Cortex({ seed: 1 });
  const motors = cortex.input('motors', { shape: 2 });
  const alone = cortex.column('alone', { patches: 2, inputs: motors });
  cortex.output('out', { shape: 2, reads: alone });
  assert.throws(() => cortex.build(), /settles with no other population/);
});

test('checkpoints are validated', () => {
  const life = new Life(17);
  const data = life.snapshot();
  assert.throws(() => Life.fromSnapshot({ ...data, schema: 'rover-life-v2' }), /browser edition/);
  assert.throws(() => Life.fromSnapshot({ ...data, arms: { cadence: data.arms.cadence } }), /incomplete/);
  const broken = JSON.parse(JSON.stringify(data));
  broken.arms.cadence.model.brain.weights[0] = 9;
  assert.throws(() => Life.fromSnapshot(broken), /Invalid weights/);
  const model = modelFromSnapshot(data.arms.mlp.model);
  assert.equal(model.parameters(), 722);
  assert.ok(Brain.fromSnapshot(data.arms.frozen.model.brain));
});

test('the automatic demonstration passes its gate', () => {
  const life = new Life(17);
  while (life.step < AUTOMATIC_STEPS) life.tick();
  const metrics = Object.fromEntries(Object.entries(life.arms).map(([kind, arm]) => [kind, summarize(arm.metrics)]));
  const gate = demonstrationGate(metrics, life.auto);
  assert.equal(gate.complete, true);
  assert.equal(gate.passed, true);
  assert.ok(metrics.cadence.weakened.targets > metrics.frozen.weakened.targets);
});

console.log(`${passed} tests passed`);
