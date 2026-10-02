// node probe.js '{"ripen":true,"rock":true}' 8000 1 > out.jsonl
// One world under one rule set for T ticks; a line of population statistics every 500 ticks, and at
// the end the lifetime-at-death tables by patch count, by depth, by observer count, by width and by
// horizon, the mask census, the solve-qualification rates, and the symbol statistics over the last
// quarter of the run.
const CW = require('./core.js');
const rules = JSON.parse(process.argv[2] || '{}'), T = +process.argv[3] || 8000, seed = +process.argv[4] || 1;
const prices = JSON.parse(process.argv[5] || '{}'); Object.assign(CW.POP, prices); // optional price overrides, e.g. '{"read":0.0001}'
const sub = new CW.Substrate(seed, rules), pop = new CW.Population(sub, seed + 100); const m0 = pop.mass;
const lifeByPatches = {}, lifeByDepth = {}, lifeByObservers = {}, lifeByWidth = {}, lifeByHorizon = {}, lifeByRadius = {};
const push = (t, k, v) => (t[k] = t[k] || []).push(v);
const patchBin = p => p < 20 ? '<20' : p < 30 ? '20-29' : p < 45 ? '30-44' : p < 65 ? '45-64' : '65+';
pop.onDeath = c => { push(lifeByPatches, patchBin(c.brain.P), c.age); push(lifeByDepth, c.brain.depth, c.age); push(lifeByObservers, c.brain.observers, c.age); push(lifeByWidth, c.brain.width, c.age); push(lifeByHorizon, c.brain.horizon, c.age); push(lifeByRadius, c.brain.r, c.age); };
// symbol statistics over the last quarter: joint counts of (symbol uttered, food here > 0), (symbol, a neighbour present), (symbol, kin adjacent)
const K = 5, joint = { food: Array.from({ length: K }, () => [0, 0]), neighbour: Array.from({ length: K }, () => [0, 0]), kin: Array.from({ length: K }, () => [0, 0]) };
let heardReward = [0, 0], deafReward = [0, 0];
const t0 = Date.now();
const mean = (cs, f) => cs.length ? cs.reduce((a, c) => a + f(c), 0) / cs.length : 0;
for (let t = 1; t <= T; t++) {
  sub.step(); pop.step();
  if (t > 0.75 * T) {
    for (const c of pop.creatures) {
      if (c.brain.K > 0) {
        const here = c.y * CW.CFG.w + c.x, foodHere = sub.food[here] > 0 ? 1 : 0; let nb = 0, kin = 0;
        for (const [dx, dy] of CW.DIRS) { const j = pop.occ[((c.y + dy + CW.CFG.h) % CW.CFG.h) * CW.CFG.w + (c.x + dx + CW.CFG.w) % CW.CFG.w]; if (j >= 0) { nb = 1; if (pop.creatures[j].lineage === c.lineage) kin = 1; } }
        const s = Math.min(c.symbol, K - 1); joint.food[s][foodHere]++; joint.neighbour[s][nb]++; joint.kin[s][kin]++;
      }
      if (c.brain.hears) { heardReward[0] += c.reward; heardReward[1]++; } else { deafReward[0] += c.reward; deafReward[1]++; }
    }
  }
  if (t % 500 === 0 || t === T) {
    const cs = pop.creatures; const census = {};
    for (const c of cs) for (const name of CW.GROUP_NAMES) if (c.g.mask & CW.bit(name)) census[name] = (census[name] || 0) + 1;
    for (const k of Object.keys(census)) census[k] = +(census[k] / Math.max(cs.length, 1)).toFixed(2);
    const hist = (f) => { const h = {}; for (const c of cs) { const v = f(c); h[v] = (h[v] || 0) + 1; } return h; };
    const rate = (ok, tries) => tries ? +(ok / tries).toFixed(3) : null;
    let dOk = 0, dTr = 0, lOk = 0, lTr = 0, sw = 0;
    for (const c of cs) { dOk += c.brain.decideOk; dTr += c.brain.decides; lOk += c.brain.learnOk; lTr += c.brain.learns; sw += c.brain.sweepsTick; }
    console.log(JSON.stringify({ t, alive: cs.length, births: pop.births, deaths: pop.deaths, bites: pop.bites, mass_ok: pop.mass === m0, age: +mean(cs, c => c.age).toFixed(0),
      patches: +mean(cs, c => c.brain.P).toFixed(1), depth: +mean(cs, c => c.brain.depth).toFixed(2), observers: +mean(cs, c => c.brain.observers).toFixed(2), observing: +mean(cs, c => c.brain.observers > 0).toFixed(2), width: +mean(cs, c => c.brain.width).toFixed(1), fanin: +mean(cs, c => c.brain.F).toFixed(1),
      readUnits: +mean(cs, c => c.brain.readUnits).toFixed(0), radius: +mean(cs, c => c.brain.r).toFixed(2), horizon: +mean(cs, c => c.brain.horizon).toFixed(2), splitAt: +mean(cs, c => CW.G(c.g, 'splitAt')).toFixed(0),
      prior: +mean(cs, c => c.brain.prior).toFixed(2), gamma: +mean(cs, c => c.brain.gamma).toFixed(2), eps: +mean(cs, c => c.brain.eps).toFixed(3),
      settled: rate(dOk, dTr), learned: rate(lOk, lTr), sweepsTick: +(sw / Math.max(cs.length, 1)).toFixed(1),
      speak: +mean(cs, c => c.brain.K > 0).toFixed(2), symbolsMean: +mean(cs, c => c.brain.K).toFixed(2), hears: +mean(cs, c => c.brain.hears).toFixed(2),
      depthHist: hist(c => c.brain.depth), observerHist: hist(c => c.brain.observers), horizonHist: hist(c => c.brain.horizon), census, s: ((Date.now() - t0) / 1000) | 0 }));
  }
}
const table = t => { const out = {}; for (const k of Object.keys(t)) { const a = t[k]; a.sort((x, y) => x - y); out[k] = { n: a.length, median: a[a.length >> 1], mean: +(a.reduce((x, y) => x + y, 0) / a.length).toFixed(0) }; } return out; };
const shuffled = counts => { // the mutual information after the symbols are permuted: the chance level at this sample size
  const rng = new CW.Mulberry(7); const pairs = []; counts.forEach((r, i) => r.forEach((v, j) => { for (let q = 0; q < v; q++) pairs.push([i, j]); }));
  const sy = pairs.map(p => p[0]); for (let i = sy.length - 1; i > 0; i--) { const j = (rng.random() * (i + 1)) | 0; const t = sy[i]; sy[i] = sy[j]; sy[j] = t; }
  const c2 = counts.map(r => r.map(() => 0)); pairs.forEach((p, i) => { c2[sy[i]][p[1]]++; }); return CW.mutualInformation(c2);
};
const symbols = {}; for (const k of Object.keys(joint)) { const n = joint[k].flat().reduce((a, b) => a + b, 0); symbols[k] = { n, mi: +CW.mutualInformation(joint[k]).toFixed(4), chance: +shuffled(joint[k]).toFixed(4) }; }
console.log(JSON.stringify({ final: true, rules, seed, T, prices, lifeByPatches: table(lifeByPatches), lifeByDepth: table(lifeByDepth), lifeByObservers: table(lifeByObservers), lifeByWidth: table(lifeByWidth), lifeByHorizon: table(lifeByHorizon), lifeByRadius: table(lifeByRadius), symbols,
  rewardPerTick: { hears: heardReward[1] ? +(heardReward[0] / heardReward[1]).toFixed(4) : null, deaf: deafReward[1] ? +(deafReward[0] / deafReward[1]).toFixed(4) : null } }));
