// The page's search (web/js/search.js) against tron/absearch.py on recorded positions:
// every move and every value at depths 1 to 4, with and without the brain's prior.
//   node tests/parity_search.mjs tests/fixtures/search.json
import { readFileSync } from "node:fs";
import { Search } from "../web/js/search.js";

const fx = JSON.parse(readFileSync(process.argv[2] || new URL("./fixtures/search.json", import.meta.url), "utf8"));
const s = new Search(fx.n);
let runs = 0, bad = 0;
const t0 = performance.now();
for (const c of fx.cases) {
  for (const r of c.runs) {
    const [move, values] = s.root(c.grid, c.heads, c.headings, 0, r.depth, r.prior, r.bonus);
    runs++;
    if (move !== r.move || values.some((v, k) => v !== r.values[k])) {
      bad++;
      if (bad <= 5) console.log("mismatch", { depth: r.depth, prior: r.prior, js: [move, values], py: [r.move, r.values] });
    }
  }
}
console.log(JSON.stringify({ positions: fx.cases.length, runs, mismatches: bad, ms: Math.round(performance.now() - t0) }));
process.exit(bad ? 1 : 0);
