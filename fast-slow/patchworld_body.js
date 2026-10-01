// A body adapter only: the original core.js physics is loaded without edits.
const readline = require('readline');
const crypto = require('crypto');
const CW = require(process.argv[2]);
CW.POP.initial = 0;
CW.POP.max = 1;
let sub, pop, creature, proxy, mass, ready = false;
function digest() {
  return crypto.createHash('sha256').update(JSON.stringify({
    tick: sub.tick, rng: sub.rng.s, popRng: pop.rng.s,
    soil: Array.from(sub.soil), food: Array.from(sub.food), green: Array.from(sub.green),
    creatures: pop.creatures.map(c => [c.x, c.y, c.energy, c.reward, c.last, c.outcome])
  })).digest('hex');
}
function sense() {
  if (ready) throw Error('Unconsumed observation');
  if (!pop.creatures.length) return {alive: false, mass: pop.mass, state_sha256: digest()};
  sub.step(); ready = true;
  const food = [];
  for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
    const x = (creature.x + dx + CW.CFG.w) % CW.CFG.w;
    const y = (creature.y + dy + CW.CFG.h) % CW.CFG.h;
    food.push(sub.food[y * CW.CFG.w + x]);
  }
  if (pop.mass !== mass) throw Error('Mass changed during substrate step');
  return {alive: true, tick: sub.tick, food, energy: creature.energy,
    position: [creature.x, creature.y], mass: pop.mass, state_sha256: digest()};
}
function command(q) {
  if (q.op === 'init') {
    if (sub) throw Error('Already initialized');
    sub = new CW.Substrate(q.seed, {});
    pop = new CW.Population(sub, q.seed + 100);
    const x = Math.floor(pop.rng.random() * CW.CFG.w), y = Math.floor(pop.rng.random() * CW.CFG.h);
    creature = pop.spawn(x, y, CW.POP.birth, pop.founder(), null, null);
    proxy = {r: 1, hears: false, actions: CW.actionsFor(sub.rules, 0),
      structurePrice: CW.POP.read * 9 + CW.POP.patch * q.patches + CW.POP.conn * q.connections,
      sweepsTick: 0, action: 5, read() {}, settleLive() {}, learn() {}, decide() {return this.action;}};
    creature.brain = proxy; pop.reindex(); mass = pop.mass;
    return {node: process.version, cfg: CW.CFG, prices: CW.POP, initial_mass: mass,
      actions: proxy.actions, structure_price: proxy.structurePrice, state_sha256: digest()};
  }
  if (!sub) throw Error('Initialize first');
  if (q.op === 'sense') return sense();
  if (q.op === 'step') {
    if (!ready || q.tick !== sub.tick) throw Error('Action lacks current observation');
    if (!Number.isInteger(q.action) || q.action < 0 || q.action > 5) throw Error('Invalid action');
    if (!Number.isInteger(q.sweeps) || q.sweeps < 0) throw Error('Invalid work');
    if (q.qualified !== true && q.action !== 5) throw Error('Unqualified action');
    const before = {energy: creature.energy, mass: pop.mass, state_sha256: digest()};
    proxy.action = q.action; proxy.sweepsTick = q.sweeps;
    pop.step(); ready = false;
    if (pop.mass !== mass) throw Error('Mass changed during body action');
    return {tick: sub.tick, action: q.action, name: proxy.actions[q.action], qualified: q.qualified,
      before, after: {energy: creature.energy, mass: pop.mass, state_sha256: digest()},
      alive: !!pop.creatures.length, outcome: creature.outcome, reward: creature.reward,
      eats: creature.eats, births: pop.births, deaths: pop.deaths};
  }
  throw Error('Unknown operation');
}
readline.createInterface({input: process.stdin}).on('line', line => {
  try {process.stdout.write(JSON.stringify(command(JSON.parse(line))) + '\n');}
  catch (error) {process.stdout.write(JSON.stringify({error: String(error)}) + '\n');}
});
