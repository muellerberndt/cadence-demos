// The JavaScript search (web/search.js) against connect4/search.py on recorded positions: the same
// column, reason, values, depth and node count. Run: node tests/parity_search.mjs
import { readFileSync } from 'node:fs';
import { choose } from '../web/search.js';
const cases = JSON.parse(readFileSync(new URL('./fixtures/search_parity.json', import.meta.url)));
let bad = 0, ms = 0;
for (const k of cases) {
  const t = performance.now();
  const r = choose(k.moves, k.motor, 0.2, k.nodes);
  ms += performance.now() - t;
  const values = Object.fromEntries(Object.entries(r.values).map(([c, v]) => [c, Math.round(v * 1e4) / 1e4]));
  const want = Object.fromEntries(Object.entries(k.values).map(([c, v]) => [c, Math.round(v * 1e4) / 1e4]));
  const same = r.column === k.column && r.brain === k.brain && r.reason === k.reason && r.depth === k.depth
    && r.nodes === k.searched && JSON.stringify(values) === JSON.stringify(want);
  if (!same) { bad++; if (bad <= 5) console.log('differs', JSON.stringify({ moves: k.moves, want: k, got: { column: r.column, reason: r.reason, depth: r.depth, nodes: r.nodes, values } })); }
}
console.log(JSON.stringify({ cases: cases.length, differ: bad, ms_total: Math.round(ms) }));
process.exit(bad ? 1 : 0);
