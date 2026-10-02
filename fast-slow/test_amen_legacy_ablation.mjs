import assert from 'node:assert/strict';
import {mkdtempSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname, join, resolve} from 'node:path';
import test from 'node:test';
import {fileURLToPath} from 'node:url';
import {ARMS, ablate, bound, cases, fixed, load, metrics, parityCheck, prepare, settings, slowOutput} from './amen_legacy_ablation.mjs';

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const engine = await load(REPO);
const input = (t = 0) => { const x = Array(80).fill(0); x[0] = Number(t === 0); x[1 + t % 8] = 1; x.splice(9, 71, ...engine.model.count_in); return x; };
test('exact preregistered twenty-case census and policy settings', () => {
  assert.equal(cases().length, 20);
  assert.equal(new Set(cases().map(c => c.id)).size, 20);
  for (const arm of ARMS) assert.equal(cases().filter(c => c.arm === arm).length, 5);
  assert.deepEqual(settings('sample', 4), {bars: 128, mode: 'sample', seed: 4, energy: 1, variation: 0.6, riffBars: 2, memory: false});
  assert.equal(settings('argmax', 0).variation, 0);
});
test('record ablation exactly omits additive read, preserves address/context and fixed values', () => {
  const full = engine.make(), off = engine.make();
  const before = fixed(off), work = ablate(off, 'no_record');
  for (const t of [0, 1, 2]) {
    const a = full.step(input(t)), b = off.step(input(t));
    assert.deepEqual(a.h, b.h); assert.deepEqual(a.read, b.read); assert.deepEqual(a.cells, b.cells);
    assert.deepEqual(b.out, slowOutput(full, a.h));
    assert.deepEqual(a.out, b.out.map((v, k) => v + b.read[k]));
  }
  assert.equal(fixed(off), before); assert.equal(work.steps, 3);
  assert.equal(work.extra_ablation_slow_terms, 3 * 128 * 71);
});
test('context reset changes only past context; record lookup and same current input remain', () => {
  const reset = engine.make(), cold = engine.make();
  const before = fixed(reset), work = ablate(reset, 'context_reset');
  reset.step(input()); const b = reset.step(input(1)); const a = cold.step(input(1));
  assert.deepEqual(a, b); assert.equal(work.context_resets, 2); assert.equal(fixed(reset), before);
  const both = engine.make(); ablate(both, 'both'); both.step(input());
  const c = both.step(input(1)); assert.deepEqual(c.h, a.h); assert.deepEqual(c.read, a.read);
  assert.deepEqual(c.out, slowOutput(cold, a.h));
});
test('intact wrapper exactly matches all128 archived event identities and float32 output tolerance', () => {
  const brain = engine.make(), before = fixed(brain), work = ablate(brain, 'intact');
  const rows = [...engine.compose(brain, {...settings('argmax', 0), bars: 16})];
  const parity = JSON.parse(readFileSync(join(REPO, 'amen/runs/record-composer-v12/parity.json')));
  const result = parityCheck(rows, parity, engine.model.layout);
  assert.equal(result.steps, 128); assert.ok(result.maximum_output_difference <= 5e-8);
  assert.equal(work.steps, 128); assert.equal(fixed(brain), before);
  const changed = structuredClone(rows); changed[0].out[0] += 1e-4;
  assert.throws(() => parityCheck(changed, parity, engine.model.layout), /output difference/);
  changed[0].out[0] = NaN;
  assert.throws(() => parityCheck(changed, parity, engine.model.layout), /nonfinite/);
});
test('command metrics do not equate an indefinitely held note with audible sound', () => {
  const L = engine.model.layout, rows = Array.from({length: 16}, (_, t) => {
    const played = Array(71).fill(0); played[L.bass_on] = 1; played[L.note_start] = 1; played[L.bass_hold] = Number(t > 0);
    return {played, returned: false};
  });
  const value = metrics(rows, L);
  assert.equal(value.whole.bass_on_fraction, 1); assert.equal(value.whole.bass_onsets, 1);
  assert.equal(value.whole.longest_bass_command_hold, 16); assert.match(value.scope, /does not imply/);
  assert.throws(() => metrics([], L), /empty/);
});
test('freeze refuses overwrite and source/protocol mutation', () => {
  const base = mkdtempSync(join(tmpdir(), 'amen-legacy-ablation-test-')), root = join(base, 'run');
  try {
    const receipt = prepare(root, REPO); assert.equal(receipt.cases, 20); assert.equal(bound(root).expected_steps, 20480);
    assert.throws(() => prepare(root, REPO), /already exists/);
    const source = join(root, 'sources/amen/web/engine.js'); const original = readFileSync(source);
    writeFileSync(source, 'changed'); assert.throws(() => bound(root), /source changed/);
    writeFileSync(source, original);
    const protocol = join(root, 'protocol.json'); const p = JSON.parse(readFileSync(protocol)); p.cases.pop(); writeFileSync(protocol, JSON.stringify(p));
    assert.throws(() => bound(root), /protocol changed/);
  } finally { rmSync(base, {recursive: true, force: true}); }
});
