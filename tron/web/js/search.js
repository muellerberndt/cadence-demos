// The look-ahead the page's player runs beside the brain: the alpha-beta over rounds of
// tron/absearch.py, line for line (tests/parity_search.mjs checks every value against it).
//
// A round is my move, then the opponent's reply knowing it (the pessimistic reading of
// simultaneous moves). The leaf is the Voronoi territory: cells I reach before the opponent less
// the cells it reaches first, or, once the riders are walled apart, the difference of the rooms
// (times 4, less my free neighbours). Deaths score -BIG / +BIG, shifted by how soon they come.
// The brain proposes: its move gets `bonus` leaf units at the root. No neural evaluation runs
// inside the search; it knows only the rules of the game.

const INF = 1 << 20;
export const BIG = INF * 16;
const DR = [-1, 0, 1, 0];
const DC = [0, 1, 0, -1];
const ORDER = [1, 0, 2]; // straight, then left, then right

export class Search {
  constructor(n = 24) {
    this.n = n;
    this.a = new Int32Array(n * n);
    this.b = new Int32Array(n * n);
    this.queue = new Int32Array(n * n);
    this.nodes = 0;
  }

  dist(grid, r0, c0, out) {
    const n = this.n, q = this.queue;
    out.fill(INF);
    out[r0 * n + c0] = 0;
    let head = 0, tail = 0;
    q[tail++] = r0 * n + c0;
    while (head < tail) {
      const i = q[head++];
      const r = (i / n) | 0, c = i % n;
      const d = out[i] + 1;
      for (let k = 0; k < 4; k++) {
        const rr = r + DR[k], cc = c + DC[k];
        if (rr >= 0 && rr < n && cc >= 0 && cc < n) {
          const j = rr * n + cc;
          if (grid[j] === 0 && out[j] === INF) { out[j] = d; q[tail++] = j; }
        }
      }
    }
  }

  leaf(grid, heads, seat) {
    const n = this.n, a = this.a, b = this.b;
    this.nodes++;
    const [mr, mc] = heads[seat], [tr, tc] = heads[1 - seat];
    this.dist(grid, mr, mc, a);
    this.dist(grid, tr, tc, b);
    let shared = false;
    for (let k = 0; k < 4; k++) {
      const rr = tr + DR[k], cc = tc + DC[k];
      if (rr >= 0 && rr < n && cc >= 0 && cc < n && a[rr * n + cc] < INF) { shared = true; break; }
    }
    if (shared) {
      let score = 0;
      for (let i = 0; i < n * n; i++) { if (a[i] < b[i]) score++; else if (b[i] < a[i]) score--; }
      return 4 * score;
    }
    let mine = 0, theirs = 0;
    for (let i = 0; i < n * n; i++) {
      if (a[i] > 0 && a[i] < INF) mine++;
      if (b[i] > 0 && b[i] < INF) theirs++;
    }
    let free = 0;
    for (let k = 0; k < 4; k++) {
      const rr = mr + DR[k], cc = mc + DC[k];
      if (rr >= 0 && rr < n && cc >= 0 && cc < n && grid[rr * n + cc] === 0) free++;
    }
    return 4 * (mine - theirs) - free;
  }

  // Move one cycle; returns the undo record, or null if it dies.
  apply(grid, heads, headings, seat, action) {
    const n = this.n;
    const h = (headings[seat] + action - 1 + 4) % 4;
    const r = heads[seat][0] + DR[h], c = heads[seat][1] + DC[h];
    if (r < 0 || r >= n || c < 0 || c >= n || grid[r * n + c] !== 0) return null;
    const undo = [heads[seat][0], heads[seat][1], headings[seat], r * n + c];
    grid[r * n + c] = 1 + seat;
    heads[seat] = [r, c];
    headings[seat] = h;
    return undo;
  }

  undo(grid, heads, headings, seat, u) {
    grid[u[3]] = 0;
    heads[seat] = [u[0], u[1]];
    headings[seat] = u[2];
  }

  ab(grid, heads, headings, seat, depth, alpha, beta, ply, deadline) {
    if (depth === 0) return this.leaf(grid, heads, seat);
    if (deadline && (this.nodes & 255) === 0 && performance.now() > deadline) throw TIMEOUT;
    let best = -BIG * 4;
    const o = 1 - seat;
    for (let ai = 0; ai < 3; ai++) {
      let value;
      const um = this.apply(grid, heads, headings, seat, ORDER[ai]);
      if (!um) value = -BIG + ply;
      else {
        let worst = BIG * 4;
        const lo = alpha > best ? alpha : best;
        for (let ri = 0; ri < 3; ri++) {
          const h = (headings[o] + ORDER[ri] - 1 + 4) % 4;
          const r = heads[o][0] + DR[h], c = heads[o][1] + DC[h];
          let v;
          if (r === heads[seat][0] && c === heads[seat][1]) v = Math.floor(-BIG / 2) + ply;
          else {
            const ut = this.apply(grid, heads, headings, o, ORDER[ri]);
            if (!ut) v = BIG - ply;
            else {
              const hi = beta < worst ? beta : worst;
              try {
                v = this.ab(grid, heads, headings, seat, depth - 1, lo, hi, ply + 1, deadline);
              } finally { this.undo(grid, heads, headings, o, ut); }
            }
          }
          if (v < worst) worst = v;
          if (worst <= lo) break;
        }
        value = worst;
        this.undo(grid, heads, headings, seat, um);
      }
      if (value > best) best = value;
      if (best >= beta) break;
    }
    return best;
  }

  // One full search at `depth` rounds: [move, values by action (0 left, 1 straight, 2 right)].
  root(grid0, heads0, headings0, seat, depth, prior = -1, bonus = 0, deadline = 0) {
    const grid = Int32Array.from(grid0);
    const heads = heads0.map((h) => [h[0], h[1]]);
    const headings = headings0.slice();
    const values = [-BIG * 8, -BIG * 8, -BIG * 8];
    let bestMove = 1, bestValue = -BIG * 8;
    const o = 1 - seat;
    for (let ai = 0; ai < 3; ai++) {
      const act = ORDER[ai];
      let value;
      const um = this.apply(grid, heads, headings, seat, act);
      if (!um) value = -BIG;
      else {
        let worst = BIG * 4;
        for (let ri = 0; ri < 3; ri++) {
          const h = (headings[o] + ORDER[ri] - 1 + 4) % 4;
          const r = heads[o][0] + DR[h], c = heads[o][1] + DC[h];
          let v;
          if (r === heads[seat][0] && c === heads[seat][1]) v = Math.floor(-BIG / 2);
          else {
            const ut = this.apply(grid, heads, headings, o, ORDER[ri]);
            if (!ut) v = BIG;
            else {
              try {
                v = this.ab(grid, heads, headings, seat, depth - 1, -BIG * 4, worst, 1, deadline);
              } finally { this.undo(grid, heads, headings, o, ut); }
            }
          }
          if (v < worst) worst = v;
        }
        value = worst;
        this.undo(grid, heads, headings, seat, um);
      }
      if (act === prior) value += bonus;
      values[act] = value;
      if (value > bestValue) { bestMove = act; bestValue = value; }
    }
    return [bestMove, values];
  }

  // The page's player: the deepest full search that finishes within `budgetMs`, up to `maxDepth`
  // rounds. Returns {move, values, depth, ms, nodes}; depth 0 (no search finished) keeps the prior.
  decide(grid, heads, headings, seat, { maxDepth = 5, budgetMs = 60, prior = -1, bonus = 8 } = {}) {
    const t0 = performance.now();
    const deadline = t0 + budgetMs;
    this.nodes = 0;
    let out = { move: prior >= 0 ? prior : 1, values: null, depth: 0 };
    for (let d = 1; d <= maxDepth; d++) {
      try {
        const [move, values] = this.root(grid, heads, headings, seat, d, prior, bonus, deadline);
        out = { move, values, depth: d };
      } catch (e) {
        if (e !== TIMEOUT) throw e;
        break;
      }
      if (performance.now() > deadline) break;
    }
    out.ms = performance.now() - t0;
    out.nodes = this.nodes;
    return out;
  }
}

const TIMEOUT = { timeout: true };
