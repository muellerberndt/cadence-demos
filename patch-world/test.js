// node test.js
// Checks core.js against reference values written by the population solver of
// cadence-net 0.70.0 (fixtures/, produced by parity.py), then checks the
// developed brains and the world: one connected settlement for every body plan,
// optional observers, exact derivatives, refusal custody, private imagination,
// conserved mass and a reproducible run.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const CW = require('./core.js');

const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'library-0.70.0.json'), 'utf8'));
const results = [];
function test(name, body) {
  const saved = Object.assign({}, CW.BRAIN);
  try { body(); results.push(['ok', name]); } catch (error) { results.push(['FAILED', name, error]); } finally { Object.assign(CW.BRAIN, saved); CW.exactTanh(false); }
}
const close = (actual, expected, tolerance, label) => assert.ok(Math.abs(actual - expected) <= tolerance, `${label}: ${actual} against ${expected}`);
const maxDiff = (a, b) => { let m = 0; for (let i = 0; i < b.length; i++) m = Math.max(m, Math.abs(a[i] - b[i])); return m; };
const senses = c => Float64Array.from([...c.senses, 0]); // the spare sense that unused slots read
// The library sums energies exactly and reached 1e-9 for the fixtures. core.js adds in floating
// point, so its comparison solves stop at 1e-8, still five decades below the page tolerance.
const TOLERANCE = 1e-8;

function genome(over) { return Object.assign({ radius: 0, width: 1, depth: 1, observers: 0, fanin: 1, prior: 1, horizon: 0, symbols: 0, splitAt: 0, eps: 2, gamma: 2, hue: 0.5, mask: 0xffff, wiring: 12345 }, over); }
const ALL_RULES = { ripen: true, rock: true, night: true, kinds: true, bite: true, carry: true, digest: true };
const rulesOf = r => Object.assign({}, CW.RULES, r);

// ---------- the library comparison ----------
for (const c of fixture.cases) {
  test(`${c.name}: energy, errors and derivatives equal the library's`, () => {
    CW.exactTanh(true);
    assert.equal(CW.BRAIN.statePrior, c.statePrior);
    const b = CW.Brain.fromGraph(c), F = b.F, x = senses(c);
    b.Bs.set(c.probe.biases); b.s.set(c.probe.state);
    for (let i = 0; i < b.D; i++) b.sig[i] = x[i];
    const energy = b.forward(b.s, b.e, b.pv);
    for (let i = 0; i < b.P * F; i++) b.Wa[i] = c.probe.anchorScale * b.W[i];
    b.Ba.fill(0);
    let anchor = 0;
    for (let i = 0; i < b.P * F; i++) anchor += (b.W[i] - b.Wa[i]) ** 2;
    for (let i = 0; i < b.P; i++) anchor += (b.Bs[i] - b.Ba[i]) ** 2;
    close(energy + 0.5 * c.parameterPrior * anchor, c.probe.energy, 1e-12, 'energy');
    b.gradient(b.s, b.e, b.pv, true, c.parameterPrior);
    assert.ok(maxDiff(b.e, c.probe.errors) < 1e-12, 'errors');
    assert.ok(maxDiff(b.gS, c.probe.gradientState) < 1e-12, 'state derivatives');
    assert.ok(maxDiff(b.gB, c.probe.gradientBiases) < 1e-12, 'bias derivatives');
    c.probe.gradientWeights.forEach((row, i) => row.forEach((g, j) => close(b.gW[i * F + j], g, 1e-12, `relation derivative ${i}.${j}`)));
  });

  test(`${c.name}: the settled state equals the library's`, () => {
    CW.exactTanh(true); Object.assign(CW.BRAIN, { tolerance: TOLERANCE, backtracks: 32 });
    const b = CW.Brain.fromGraph(c);
    const sweeps = b.repair(senses(c), b.s, b.e, b.pv, -1, 0, false, 2048);
    assert.ok(sweeps >= 0, 'the solve qualifies');
    assert.ok(maxDiff(b.s, c.settled.state) < 1e-7, `settled states differ by ${maxDiff(b.s, c.settled.state)}`);
  });

  test(`${c.name}: one admitted witness moves the relations as in the library`, () => {
    CW.exactTanh(true); Object.assign(CW.BRAIN, { tolerance: TOLERANCE, backtracks: 32 });
    const b = CW.Brain.fromGraph(c), F = b.F;
    const sweeps = b.repair(senses(c), b.s, b.e, b.pv, c.learned.clamp, c.learned.target, true, 8192);
    assert.ok(sweeps >= 0, 'the learning solve qualifies');
    assert.equal(b.s[c.learned.clamp], c.learned.target);
    assert.ok(maxDiff(b.s, c.learned.state) < 1e-7, `states differ by ${maxDiff(b.s, c.learned.state)}`);
    assert.ok(maxDiff(b.Bs, c.learned.biases) < 1e-7, `biases differ by ${maxDiff(b.Bs, c.learned.biases)}`);
    let worst = 0, moved = 0;
    c.learned.weights.forEach((row, i) => row.forEach((w, j) => { worst = Math.max(worst, Math.abs(b.W[i * F + j] - w)); moved = Math.max(moved, Math.abs(w - c.reads[i][j][2])); }));
    assert.ok(worst < 1e-7, `relations differ by ${worst}`);
    assert.ok(moved > 1e-3, 'the witness changed the relations');
  });
}

test('the page tanh table stays within 1e-5 of tanh', () => {
  const b = CW.Brain.fromGraph({ inputs: 1, parameterPrior: 0.1, biases: [0], reads: [[['input', 0, 1]]] });
  let worst = 0;
  for (let v = -9; v <= 9; v += 0.00137) { b.sig[0] = v; b.forward(b.s, b.e, b.pv); worst = Math.max(worst, Math.abs(b.pv[0] - Math.tanh(v))); }
  assert.ok(worst < 1e-5, `table error ${worst}`);
});

// ---------- developed brains ----------
test('every body plan develops one connected settlement', () => {
  const rng = new CW.Mulberry(3); let built = 0;
  for (const rules of [{}, { ripen: true, rock: true, bite: true, carry: true }, ALL_RULES])
    for (let radius = 0; radius < CW.GENE.radius.length; radius++) for (let width = 0; width < CW.GENE.width.length; width++) for (let depth = 0; depth < CW.GENE.depth.length; depth++)
      for (let observers = 0; observers < CW.GENE.observers.length; observers++) for (let fanin = 0; fanin < CW.GENE.fanin.length; fanin++) for (const symbols of [0, 3]) {
        const b = new CW.Brain(genome({ radius, width, depth, observers, fanin, symbols, wiring: (rng.random() * 4294967296) >>> 0 }), rulesOf(rules));
        assert.ok(b.connected()); built++;
      }
  assert.equal(built, 3 * 2 * 4 * 4 * 5 * 4 * 2);
});

test('founders have no observers; observers add error reads to the top stages only', () => {
  const founder = CW.firstGenome(new CW.Mulberry(1));
  assert.equal(CW.G(founder, 'observers'), 0);
  const kinds = b => { const seen = b.pops.map(() => new Set()); b.pops.forEach((pop, s) => { for (let i = pop.off; i < pop.off + pop.n; i++) for (let j = 0; j < b.F; j++) { const k = b.cIdx[i * b.F + j]; seen[s].add(k < b.D ? 'sense' : k < b.D + b.P ? 'state' : 'error'); } }); return seen.map(s => [...s].sort().join('+')); };
  const plain = new CW.Brain(genome({ depth: 2, observers: 0 }), rulesOf({}));
  assert.equal(plain.observers, 0);
  assert.deepEqual(kinds(plain), ['sense', 'sense+state', 'sense+state', 'sense+state']);
  const one = new CW.Brain(genome({ depth: 2, observers: 1 }), rulesOf({}));
  assert.deepEqual(kinds(one), ['sense', 'sense+state', 'sense+state', 'error+sense+state']);
  const capped = new CW.Brain(genome({ depth: 0, observers: 4 }), rulesOf({}));
  assert.equal(capped.observers, 1); // never more observers than stages above perception
  assert.deepEqual(kinds(capped), ['sense', 'error+sense+state']);
  assert.equal(plain.P, one.P); assert.equal(plain.C, one.C); // the same structure price either way
});

test('relations start fan-in normalized with zero biases', () => {
  for (const fanin of [0, 3]) {
    const b = new CW.Brain(genome({ fanin, depth: 3, observers: 2 }), rulesOf({}));
    const bound = CW.BRAIN.initScale / Math.sqrt(b.F);
    assert.ok(b.W.every(w => Math.abs(w) <= bound)); assert.ok(b.W.some(w => Math.abs(w) > 0.5 * bound));
    assert.ok(b.Bs.every(v => v === 0));
  }
});

test('analytic derivatives match finite differences in a developed observer brain', () => {
  CW.exactTanh(true);
  const b = new CW.Brain(genome({ depth: 3, observers: 2, fanin: 2, width: 2 }), rulesOf(ALL_RULES)), rng = new CW.Mulberry(9), P = b.P, F = b.F;
  const x = new Uint8Array(b.D); for (let i = 0; i < b.D; i++) x[i] = rng.random() < 0.3 ? 1 : 0;
  for (let i = 0; i < b.D; i++) b.sig[i] = x[i];
  for (let i = 0; i < P; i++) { b.s[i] = rng.random() * 1.6 - 0.8; b.Bs[i] = rng.random() * 0.2 - 0.1; }
  b.Wa.set(b.W); b.Ba.set(b.Bs); // anchored at the relations: the anchor term and its derivative vanish
  b.forward(b.s, b.e, b.pv); b.gradient(b.s, b.e, b.pv, true, b.prior);
  const gS = Float64Array.from(b.gS), gW = Float64Array.from(b.gW), gB = Float64Array.from(b.gB), h = 1e-6;
  const energy = () => b.forward(b.s, new Float64Array(P), new Float64Array(P));
  const numeric = (array, i) => { const v = array[i]; array[i] = v + h; const up = energy(); array[i] = v - h; const down = energy(); array[i] = v; return (up - down) / (2 * h); };
  for (let i = 0; i < P; i++) { close(numeric(b.s, i), gS[i], 1e-7, `state ${i}`); close(numeric(b.Bs, i), gB[i], 1e-7, `bias ${i}`); }
  for (let i = 0; i < P * F; i += 7) close(numeric(b.W, i), gW[i], 1e-7, `relation ${i}`);
});

test('a refused solve retains nothing', () => {
  const b = new CW.Brain(genome({ depth: 2, observers: 1 }), rulesOf({}));
  const x = new Uint8Array(b.D); x[3] = 1; x[40] = 1;
  const s = Float64Array.from(b.s), W = Float64Array.from(b.W), Bs = Float64Array.from(b.Bs);
  assert.equal(b.repair(x, b.s, b.e, b.pv, b.polOff, 0.8, true, 0), -1); // no sweeps allowed: the clamp cannot qualify
  assert.deepEqual(b.s, s); assert.deepEqual(b.W, W); assert.deepEqual(b.Bs, Bs);
});

test('imagined settles leave the live state and relations untouched', () => {
  const b = new CW.Brain(genome({ depth: 2, observers: 1, horizon: 2 }), rulesOf({}));
  b.x[3] = 1; b.settleLive(); assert.ok(b.settledOk);
  const s = Float64Array.from(b.s), W = Float64Array.from(b.W), q = Float32Array.from(b.q);
  const moved = b.imagine(b.x, 1); assert.ok(moved);
  assert.ok(b.settleImagined(moved, 0)); b.lookahead(moved, 2, 0);
  assert.deepEqual(b.s, s); assert.deepEqual(b.W, W); assert.deepEqual(b.q, q);
});

test('mutation keeps every gene in range and can add or remove observers', () => {
  const rng = new CW.Mulberry(5), available = CW.layoutFor(rulesOf({}), 1, 0).available; let g = CW.firstGenome(rng, available); const seen = new Set();
  for (let i = 0; i < 4000; i++) { g = CW.mutate(g, rng, available); for (const k of Object.keys(CW.GENE)) assert.ok(Number.isInteger(g[k]) && g[k] >= 0 && g[k] < CW.GENE[k].length, k); seen.add(g.observers); }
  assert.ok(seen.has(0) && seen.size > 2);
});

// ---------- the world ----------
function run(seed, rules, ticks) {
  const sub = new CW.Substrate(seed, rules), pop = new CW.Population(sub, seed + 100), mass = pop.mass;
  let decides = 0, qualified = 0;
  for (let t = 0; t < ticks; t++) { sub.step(); pop.step(); assert.equal(pop.mass, mass, `mass at tick ${t}`); }
  for (const c of pop.creatures) { decides += c.brain.decides; qualified += c.brain.decideOk; assert.ok(c.brain.connected()); }
  return { alive: pop.creatures.length, births: pop.births, deaths: pop.deaths, bites: pop.bites, settled: qualified / Math.max(decides, 1),
    signature: pop.creatures.map(c => `${c.id}:${c.x},${c.y},${c.energy},${c.brain.depth},${c.brain.observers}`).join('|') };
}

test('mass is conserved and the run is reproducible under every rule', () => {
  const a = run(4, ALL_RULES, 150), b = run(4, ALL_RULES, 150);
  assert.deepEqual(a, b);
  assert.ok(a.alive > 0 && a.settled > 0.9, `alive ${a.alive}, settled ${a.settled}`);
});

test('the page world lives through its first 300 ticks', () => {
  const r = run(1, { ripen: true, rock: true, bite: true, carry: true }, 300);
  assert.ok(r.alive > 50 && r.births > 0 && r.settled > 0.9, JSON.stringify({ alive: r.alive, births: r.births, settled: r.settled }));
});

let failed = 0;
for (const [status, name, error] of results) { console.log(`${status}  ${name}`); if (error) { failed++; console.log(`      ${error.message}`); } }
console.log(`${results.length - failed} of ${results.length} checks passed against ${fixture.library}`);
process.exit(failed ? 1 : 0);
