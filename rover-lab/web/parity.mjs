// Check the JavaScript edition against values recorded with the Python edition on cadence-net 0.70.0.
//
//   node parity.mjs            (fixture: fixtures/parity.json, written by tools/make_parity_fixture.py)
//
// 1. Births are identical: wiring, residual order and every weight, bit for bit.
// 2. The solver is the same computation. The library takes two operations from the platform's C library (tanh, and
//    pow for squaring a prediction), whose last bit differs between platforms. With both replaced on both sides by
//    plain arithmetic, every solver call returns identical bits: states, errors, parameters, energy, stationarity
//    and sweep count.
// 3. With each side's own tanh, a solve stops within the solver's tolerance of the same stationary point, so values
//    agree closely and not bitwise. Whole lives then issue the same command at every step for every model and reach
//    the same targets.
import { readFileSync } from 'node:fs';
import { numerics } from './cadence.js';
import { makeModel } from './models.js';
import { ACTIONS, AUTOMATIC_STEPS, Life, PROTOCOL, route, summarize } from './rover.js';

const fixture = JSON.parse(readFileSync(new URL('./fixtures/parity.json', import.meta.url)));
const VALUES = 1e-3;         // solver values and final parameters, each side's own tanh
const FORECASTS = 1e-4;      // forecasts along a whole life
let failures = 0;
const check = (ok, message) => { if (!ok) { failures += 1; console.log(`  FAIL ${message}`); } };
const gap = (a, b) => (Array.isArray(a) ? a.reduce((m, v, i) => Math.max(m, gap(v, b[i])), 0) : Math.abs(a - b));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

console.log(`reference: cadence-net ${fixture.cadence}, Python ${fixture.python}`);
check(same(fixture.protocol, PROTOCOL), 'protocol differs from protocol.json');
check(same(fixture.actions, ACTIONS), 'candidate commands differ');
check(gap(fixture.route_17, route(17).slice(0, 8)) <= 1e-12, 'target route differs');

// ---- births ----
let exact = 0;
for (const record of fixture.births) {
  const brain = makeModel(record.kind, record.seed).brain;
  const ok = same(record.edges, brain.graph.edges) && same(record.residual_order, brain.graph.residualOrder)
    && record.weights.length === brain.weights.length && record.weights.every((w, i) => Object.is(w, brain.weights[i]));
  check(ok, `birth ${record.kind} seed ${record.seed}`);
  exact += ok ? 1 : 0;
}
console.log(`births: ${exact} of ${fixture.births.length} bit-identical`);

// ---- solver calls with one arithmetic-only tanh on both sides: every value must be identical ----
function arithmeticTanh(x) {
  const a = Math.abs(x);
  if (a > 20.0) return x > 0 ? 1.0 : -1.0;
  const y = 2.0 * a / 1024.0;
  let term = 1.0, total = 1.0;
  for (let k = 1; k < 14; k++) { term = term * y / k; total += term; }
  for (let i = 0; i < 10; i++) total = total * total;
  const result = (total - 1.0) / (total + 1.0);
  return x >= 0 ? result : -result;
}
const identical = (a, b) => a.length === b.length && a.every((v, i) => Object.is(v, b[i]) || (v === 0 && b[i] === 0));
const libraryTanh = numerics.tanh;
numerics.tanh = arithmeticTanh;
for (const record of fixture.solver_exact) {
  const model = makeModel(record.kind, record.seed);
  let equal = 0;
  record.calls.forEach((call, index) => {
    const inputs = { motors: call.action };
    const result = call.call === 'observe' ? model.brain.observe(inputs, { motion_readout: call.motion })
      : call.call === 'settle' ? model.brain.settle(inputs) : model.brain.step(inputs);
    let ok = result.qualified === call.qualified && result.reason === call.reason && result.sweeps === call.sweeps
      && result.energy === call.energy && result.stationarity === call.stationarity
      && identical(call.state, result.state) && identical(call.errors, result.errors);
    if (call.call === 'observe') ok &&= identical(call.weights, result.weights) && identical(call.biases, result.biases);
    if (ok) equal += 1; else if (equal === index) check(false, `${record.kind} exact call ${index} (${call.call}) differs`);
  });
  check(equal === record.calls.length, `${record.kind}: ${equal} of ${record.calls.length} solver calls bit-identical`);
  console.log(`solver ${record.kind}, shared arithmetic: ${equal} of ${record.calls.length} calls bit-identical`);
}
numerics.tanh = libraryTanh;

// ---- solver calls with each side's own tanh ----
for (const record of fixture.solver) {
  const model = makeModel(record.kind, record.seed);
  let worst = 0, sweeps = 0, calls = 0;
  for (const call of record.calls) {
    const inputs = { motors: call.action };
    const result = call.call === 'observe' ? model.brain.observe(inputs, { motion_readout: call.motion })
      : call.call === 'settle' ? model.brain.settle(inputs) : model.brain.step(inputs);
    calls += 1;
    check(result.qualified === call.qualified && result.reason === call.reason, `${record.kind} ${call.call} ${calls}: qualification`);
    if (result.sweeps === call.sweeps) sweeps += 1;
    let distance = Math.max(gap(call.state, result.state), gap(call.errors, result.errors), Math.abs(call.energy - result.energy));
    if (call.call === 'observe') distance = Math.max(distance, gap(call.weights, result.weights), gap(call.biases, result.biases));
    worst = Math.max(worst, distance);
  }
  check(worst <= VALUES, `${record.kind} solver values differ by ${worst}`);
  console.log(`solver ${record.kind}, own tanh: ${calls} calls, same qualification on all, sweep counts equal on ${sweeps}, largest difference ${worst.toExponential(2)}`);
}

// ---- whole lives ----
for (const record of fixture.lives) {
  const started = performance.now();
  const life = new Life(record.seed, null, { observers: record.observers });
  check(same(record.bootstrap_schedule, life.bootstrapSchedule), `life ${record.seed}: bootstrap schedule`);
  check(gap(record.targets, life.targets.slice(0, 16)) <= 1e-12, `life ${record.seed}: targets`);
  while (life.step < AUTOMATIC_STEPS) life.tick();
  const seconds = (performance.now() - started) / 1000;
  check(same(record.events, life.events), `life ${record.seed}: run record`);
  for (const kind of Object.keys(record.rows)) {
    const rows = life.rows.filter(row => row.model === kind);
    let commands = 0, hits = 0, worst = 0;
    record.rows[kind].forEach(([action, forward, turn, hit], i) => {
      const row = rows[i];
      if (ACTIONS.findIndex(a => a[0] === row.action[0] && a[1] === row.action[1]) === action) commands += 1;
      if (Number(row.hit) === hit) hits += 1;
      worst = Math.max(worst, Math.abs(row.prediction[0] - forward), Math.abs(row.prediction[1] - turn));
    });
    const reference = record.metrics[kind], own = summarize(life.arms[kind].metrics);
    let targets = true;
    for (const phase of Object.keys(reference)) {
      for (const key of ['steps', 'targets', 'attempts', 'learning_presentations']) targets &&= reference[phase][key] === own[phase][key];
    }
    check(commands === rows.length, `life ${record.seed} ${kind}: ${commands} of ${rows.length} commands equal`);
    check(hits === rows.length && targets, `life ${record.seed} ${kind}: targets reached differ`);
    check(worst <= FORECASTS, `life ${record.seed} ${kind}: forecasts differ by ${worst}`);
    let line = `life seed ${record.seed} ${kind.padEnd(8)}: ${commands}/${rows.length} commands equal, largest forecast difference ${worst.toExponential(2)}`;
    if (record.final[kind]) {
      const brain = life.arms[kind].model.brain;
      const distance = Math.max(gap(record.final[kind].weights, brain.weights), gap(record.final[kind].biases, brain.biases),
                                gap(record.final[kind].state, brain.state), gap(record.final[kind].pose, life.arms[kind].pose));
      check(distance <= VALUES, `life ${record.seed} ${kind}: final brain differs by ${distance}`);
      line += `, final brain within ${distance.toExponential(2)}`;
    }
    console.log(line);
  }
  console.log(`life seed ${record.seed}: ${AUTOMATIC_STEPS} steps in ${seconds.toFixed(2)} s`);
}
console.log(failures ? `${failures} FAILURES` : 'parity: all checks passed');
process.exit(failures ? 1 : 0);
