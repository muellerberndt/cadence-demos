// The search of connect4/search.py, ported to JavaScript so it runs at native speed in the worker.
// It visits the same positions in the same order and returns the same values, depth and node
// count: the tests compare the two on many positions (tests/parity_search.mjs). The leaf values
// come from a table NumPy computed (squash.js), so no floating-point function differs.
//
// A board is two sets of cells (the side to move, all stones), each as two 32-bit words over the
// 42 cells numbered column * 6 + row, row 0 at the bottom.
import { SQUASH } from './squash.js';

const ROWS = 6, COLUMNS = 7, CELLS = 42;
export const WIN = 1000;
export const MARGIN = 0.25;
export const NODES = 120000;
const ORDER = [3, 2, 4, 1, 5, 0, 6];

const pc = (x) => { x -= (x >>> 1) & 0x55555555; x = (x & 0x33333333) + ((x >>> 2) & 0x33333333); return (((x + (x >>> 4)) & 0x0f0f0f0f) * 0x01010101) >>> 24; };
const bit = (i) => (i < 32 ? [(1 << i) >>> 0, 0] : [0, (1 << (i - 32)) >>> 0]);
const cellOf = (c, r) => c * ROWS + r;

// every four-in-a-row as a mask, and per cell the lines through it
const LINE_LIST = [];
for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLUMNS; c++) for (const [dr, dc] of [[0, 1], [1, 0], [1, 1], [1, -1]]) {
  const cells = [0, 1, 2, 3].map((k) => [r + k * dr, c + k * dc]);
  if (cells.every(([rr, cc]) => rr >= 0 && rr < ROWS && cc >= 0 && cc < COLUMNS)) {
    let lo = 0, hi = 0;
    for (const [rr, cc] of cells) { const [a, b] = bit(cellOf(cc, rr)); lo |= a; hi |= b; }
    LINE_LIST.push([lo >>> 0, hi >>> 0]);
  }
}
const NL = LINE_LIST.length;
const LLO = Uint32Array.from(LINE_LIST.map((l) => l[0])), LHI = Uint32Array.from(LINE_LIST.map((l) => l[1]));
const mk = (pred) => { let lo = 0, hi = 0; for (let c = 0; c < COLUMNS; c++) for (let r = 0; r < ROWS; r++) if (pred(c, r)) { const [a, b] = bit(cellOf(c, r)); lo |= a; hi |= b; } return [lo >>> 0, hi >>> 0]; };
const ODD = mk((c, r) => r % 2 === 0);        // rows 1, 3 and 5, counted from the bottom
const CENTRE = mk((c) => c === 3);
const ALL = mk(() => true);
const COLUMN = Array.from({ length: COLUMNS }, (_, c) => mk((cc) => cc === c));

// The empty cells where a stone of p completes four (into the registers WLO, WHI).
let WLO = 0, WHI = 0;
function winsInto(pLo, pHi, mLo, mHi) {
  let lo = 0, hi = 0;
  for (let k = 0; k < NL; k++) {
    const a = LLO[k], b = LHI[k];
    if (pc(a & pLo) + pc(b & pHi) !== 3) continue;
    const eLo = a & ~mLo, eHi = b & ~mHi;
    if (pc(eLo) + pc(eHi) === 1) { lo |= eLo; hi |= eHi; }
  }
  WLO = lo >>> 0; WHI = hi >>> 0;
}
function wins(pLo, pHi, mLo, mHi) { winsInto(pLo, pHi, mLo, mHi); return [WLO, WHI]; }

// The cell each column with room would take next (registers PLO, PHI), and the cells directly
// below a set (BLO, BHI), by per-column bit arithmetic.
let PLO = 0, PHI = 0, BLO = 0, BHI = 0;
const COLLO = new Uint32Array(COLUMNS), COLHI = new Uint32Array(COLUMNS), SHIFT = new Int32Array(COLUMNS);
for (let c = 0; c < COLUMNS; c++) SHIFT[c] = c * ROWS;
function column6(lo, hi, c) { // the 6 bits of column c as an integer, row 0 the lowest bit
  const s = c * ROWS;
  if (s + ROWS <= 32) return (lo >>> s) & 63;
  if (s >= 32) return (hi >>> (s - 32)) & 63;
  return ((lo >>> s) | (hi << (32 - s))) & 63;
}
function setColumn(c, bits6) { // OR bits6 into column c of the (BLO, BHI) / (PLO, PHI) scratch
  const s = c * ROWS;
  if (s + ROWS <= 32) return [(bits6 << s) >>> 0, 0];
  if (s >= 32) return [0, (bits6 << (s - 32)) >>> 0];
  return [(bits6 << s) >>> 0, (bits6 >>> (32 - s)) >>> 0];
}
const PUT = Array.from({ length: COLUMNS }, (_, c) => Array.from({ length: 64 }, (_, b) => setColumn(c, b)));
function playableInto(mLo, mHi) {
  let lo = 0, hi = 0;
  for (let c = 0; c < COLUMNS; c++) {
    const col = column6(mLo, mHi, c);
    const next = (col + 1) & 63 & ~col; // the lowest empty cell above a filled stack
    if (next) { const v = PUT[c][next]; lo |= v[0]; hi |= v[1]; }
  }
  PLO = lo >>> 0; PHI = hi >>> 0;
}
function belowInto(lo, hi) {
  let oLo = 0, oHi = 0;
  for (let c = 0; c < COLUMNS; c++) {
    const col = column6(lo, hi, c);
    if (col) { const v = PUT[c][(col >>> 1) & 63]; oLo |= v[0]; oHi |= v[1]; }
  }
  BLO = oLo >>> 0; BHI = oHi >>> 0;
}
function playable(mLo, mHi) {
  let lo = 0, hi = 0;
  for (let c = 0; c < COLUMNS; c++) {
    for (let r = 0; r < ROWS; r++) {
      const i = cellOf(c, r), occupied = i < 32 ? (mLo >>> i) & 1 : (mHi >>> (i - 32)) & 1;
      if (!occupied) { if (i < 32) lo |= 1 << i; else hi |= 1 << (i - 32); break; }
    }
  }
  return [lo >>> 0, hi >>> 0];
}

// The cells directly below the cells of a set (the next cell down in the same column).
function below(lo, hi) {
  let oLo = 0, oHi = 0;
  for (let i = 0; i < CELLS; i++) {
    const on = i < 32 ? (lo >>> i) & 1 : (hi >>> (i - 32)) & 1;
    if (on && i % ROWS !== 0) { const j = i - 1; if (j < 32) oLo |= 1 << j; else oHi |= 1 << (j - 32); }
  }
  return [oLo >>> 0, oHi >>> 0];
}

function leaf(pLo, pHi, mLo, mHi, stones) {
  const oLo = (pLo ^ mLo) >>> 0, oHi = (pHi ^ mHi) >>> 0;
  const [aLo, aHi] = wins(pLo, pHi, mLo, mHi), [bLo, bHi] = wins(oLo, oHi, mLo, mHi);
  const first = stones % 2 === 0;
  const gm = first ? ODD : [(ALL[0] ^ ODD[0]) >>> 0, (ALL[1] ^ ODD[1]) >>> 0];
  const gt = [(ALL[0] ^ gm[0]) >>> 0, (ALL[1] ^ gm[1]) >>> 0];
  let score = (pc(aLo) + pc(aHi) + pc(aLo & gm[0]) + pc(aHi & gm[1])) - (pc(bLo) + pc(bHi) + pc(bLo & gt[0]) + pc(bHi & gt[1]));
  score += 0.25 * (pc(pLo & CENTRE[0]) + pc(pHi & CENTRE[1]) - pc(oLo & CENTRE[0]) - pc(oHi & CENTRE[1]));
  return SQUASH[Math.round(score * 4) + 400];
}

class Timeout extends Error {}

export class Searcher {
  constructor(nodes = NODES) { this.limit = nodes; this.table = new Map(); this.nodes = 0; }

  negamax(pLo, pHi, mLo, mHi, stones, depth, alpha, beta, ply) {
    this.nodes++;
    if (this.nodes > this.limit) throw new Timeout();
    playableInto(mLo, mHi);
    let qLo = PLO, qHi = PHI;
    winsInto(pLo, pHi, mLo, mHi);
    if ((WLO & qLo) | (WHI & qHi)) return WIN - ply - 1;
    if (stones >= CELLS - 1) return 0;
    const oLo = (pLo ^ mLo) >>> 0, oHi = (pHi ^ mHi) >>> 0;
    winsInto(oLo, oHi, mLo, mHi);
    const tLo = WLO, tHi = WHI;
    const fLo = (qLo & tLo) >>> 0, fHi = (qHi & tHi) >>> 0;
    if (fLo | fHi) {
      if (pc(fLo) + pc(fHi) > 1) return -(WIN - ply - 2);
      qLo = fLo; qHi = fHi;
    }
    belowInto(tLo, tHi);
    qLo = (qLo & ~BLO) >>> 0; qHi = (qHi & ~BHI) >>> 0;
    if (!(qLo | qHi)) return -(WIN - ply - 2);
    if (depth === 0) return leaf(pLo, pHi, mLo, mHi, stones);
    const k1 = mHi * 4294967296 + mLo, k2 = pHi * 4294967296 + pLo;
    let inner = this.table.get(k1);
    const hit = inner ? inner.get(k2) : undefined;
    let first = -1;
    if (hit) {
      first = hit[3] === null ? -1 : hit[3];
      if (hit[0] >= depth) {
        if (hit[2] === 0) return hit[1];
        if (hit[2] === 1 && hit[1] >= beta) return hit[1];
        if (hit[2] === -1 && hit[1] <= alpha) return hit[1];
      }
    }
    let best = -2 * WIN, bestMove = null;
    const startAlpha = alpha;
    for (let j = -1; j < COLUMNS; j++) {
      let c;
      if (j < 0) { if (first < 0) continue; c = first; } else { c = ORDER[j]; if (c === first) continue; }
      const cLo = qLo & COLUMN[c][0], cHi = qHi & COLUMN[c][1];
      if (!(cLo | cHi)) continue;
      const value = -this.negamax(oLo, oHi, (mLo | cLo) >>> 0, (mHi | cHi) >>> 0, stones + 1, depth - 1, -beta, -alpha, ply + 1);
      if (value > best) { best = value; bestMove = c; }
      if (value > alpha) alpha = value;
      if (alpha >= beta) break;
    }
    const flag = startAlpha < best && best < beta ? 0 : (best >= beta ? 1 : -1);
    if (!inner) { inner = new Map(); this.table.set(k1, inner); }
    inner.set(k2, [depth, best, flag, bestMove]);
    return best;
  }

  root(board) {
    const { pLo, pHi, mLo, mHi, stones, legal, winning } = board;
    const began = performance.now();
    this.nodes = 0;
    const cols = [];
    for (let c = 0; c < COLUMNS; c++) if (legal[c]) cols.push(c);
    const immediate = cols.filter((c) => winning[c]);
    if (immediate.length) {
      const values = {};
      for (const c of cols) values[c] = immediate.includes(c) ? WIN - 1 : -2 * WIN;
      return { values, depth: 0, nodes: 0, ms: 0, immediate: true };
    }
    let values = {}, depthDone = 0;
    const [qLo, qHi] = playable(mLo, mHi);
    const oLo = (pLo ^ mLo) >>> 0, oHi = (pHi ^ mHi) >>> 0;
    try {
      for (let depth = 1; depth <= Math.min(42, CELLS - stones); depth++) {
        const found = {};
        for (const c of cols) {
          const cLo = qLo & COLUMN[c][0], cHi = qHi & COLUMN[c][1];
          found[c] = -this.negamax(oLo, oHi, (mLo | cLo) >>> 0, (mHi | cHi) >>> 0, stones + 1, depth - 1, -2 * WIN, 2 * WIN, 1);
        }
        values = found; depthDone = depth;
        const vs = Object.values(found);
        if (vs.every((v) => Math.abs(v) >= WIN - 50) || Math.max(...vs) >= WIN - 50) break;
      }
    } catch (error) { if (!(error instanceof Timeout)) throw error; }
    return { values, depth: depthDone, nodes: this.nodes, ms: Math.round((performance.now() - began) * 10) / 10, immediate: false };
  }
}

// A board from the columns played so far, read from the side to move.
export function fromMoves(moves) {
  const heights = new Array(COLUMNS).fill(0);
  const owner = new Int8Array(CELLS).fill(-1);
  moves.forEach((c, k) => { owner[cellOf(c, heights[c])] = k % 2; heights[c]++; });
  const mover = moves.length % 2;
  let pLo = 0, pHi = 0, mLo = 0, mHi = 0;
  for (let i = 0; i < CELLS; i++) {
    if (owner[i] < 0) continue;
    const [a, b] = bit(i);
    mLo |= a; mHi |= b;
    if (owner[i] === mover) { pLo |= a; pHi |= b; }
  }
  [pLo, pHi, mLo, mHi] = [pLo >>> 0, pHi >>> 0, mLo >>> 0, mHi >>> 0];
  const legal = heights.map((h) => h < ROWS);
  const [wLo, wHi] = wins(pLo, pHi, mLo, mHi), [qLo, qHi] = playable(mLo, mHi);
  const winning = Array.from({ length: COLUMNS }, (_, c) => !!(((wLo & qLo & COLUMN[c][0]) | (wHi & qHi & COLUMN[c][1])) >>> 0));
  return { pLo, pHi, mLo, mHi, stones: moves.length, legal, winning };
}

export function priors(motor, legal, temperature) {
  const z = motor.slice(0, COLUMNS).map((v, c) => (legal[c] ? v / temperature : -Infinity));
  const top = Math.max(...z.filter((v, c) => legal[c]));
  const e = z.map((v) => Math.exp(v - top));
  const sum = e.reduce((a, b) => a + b, 0);
  return e.map((v) => v / sum);
}

// The brain-plus-search move, as connect4/search.py's choose().
export function choose(moves, motor, temperature, nodes = NODES) {
  const board = fromMoves(moves);
  const p = priors(motor, board.legal, temperature);
  let brain = -1;
  for (let c = 0; c < COLUMNS; c++) if (board.legal[c] && (brain < 0 || motor[c] > motor[brain])) brain = c;
  const s = new Searcher(nodes).root(board);
  const values = s.values, keys = Object.keys(values).map(Number);
  if (!keys.length) return { column: brain, brain, reason: 'brain', priors: p, ...s };
  const best = Math.max(...keys.map((c) => values[c]));
  let column, reason;
  const byPrior = (cs) => cs.reduce((a, c) => (p[c] > p[a] ? c : a));
  if (best >= WIN - 50) { column = byPrior(keys.filter((c) => values[c] === best)); reason = 'win'; }
  else {
    let alive = keys.filter((c) => values[c] > -(WIN - 50));
    if (!alive.length) alive = keys;
    const top = Math.max(...alive.map((c) => values[c]));
    if (alive.includes(brain) && values[brain] >= top - MARGIN) { column = brain; reason = 'brain'; }
    else { column = byPrior(alive.filter((c) => values[c] >= top - MARGIN)); reason = column !== brain ? 'search' : 'brain'; }
  }
  return { column, brain, reason, priors: p, values, depth: s.depth, nodes: s.nodes, ms: s.ms, immediate: s.immediate };
}
