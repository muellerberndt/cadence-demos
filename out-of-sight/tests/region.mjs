// An area given as a set of cells (site/region.js), tried on sheets made here.
//   node tests/region.mjs
// No host of the pack states a sheet; this tests the page's side of the seam: the smallest set of
// cells that holds the stated share, its patches, its outline and whether a point lies in it.
import assert from 'node:assert/strict';
import { areaOf, patches, sheetArea, outline, contour } from '../site/region.js';

const nx = 40, ny = 32, plane = [-1.0, 1.0, -0.2, 1.4];
const bump = (cx, cy, sd, weight) => (x, y) => weight * Math.exp(-0.5 * (((x - cx) / sd) ** 2 + ((y - cy) / sd) ** 2));
function sheet(...bumps) {
  const share = new Float32Array(nx * ny);
  let total = 0;
  for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
    const x = plane[0] + ((i + 0.5) / nx) * (plane[1] - plane[0]), y = plane[2] + ((j + 0.5) / ny) * (plane[3] - plane[2]);
    let v = 0;
    for (const b of bumps) v += b(x, y);
    share[j * nx + i] = v; total += v;
  }
  for (let k = 0; k < share.length; k++) share[k] /= total;
  return share;
}

// one peak: the area holds the stated share, and no smaller set of cells does
const one = sheetArea({ nx, ny, plane, rate: 0.9 }, sheet(bump(-0.5, 0.7, 0.08, 1)));
assert.ok(one.held >= 0.9 && one.held < 0.99, `held ${one.held}`);
assert.equal(one.patches, 1);
const least = Math.min(...Array.from(one.share).filter((_, k) => one.inside[k]));
const most = Math.max(...Array.from(one.share).filter((_, k) => !one.inside[k]));
assert.ok(least >= most, 'every cell of the area is believed at least as much as any cell outside it');
assert.ok(one.held - least < 0.9, 'without its least believed cell the area holds under the stated share');
assert.ok(one.holds([-0.5, 0.7]) && !one.holds([0.5, 0.2]) && !one.holds([3, 3]));
// its size is near the circle a round belief of that width has at .90
const circle = Math.PI * (Math.sqrt(-2 * Math.log(0.1)) * 0.08) ** 2;
assert.ok(Math.abs(one.area - circle) / circle < 0.25, `area ${one.area} against the circle's ${circle}`);

// two peaks, "kept going" and "stopped": two patches, each holding its place
const two = sheetArea({ nx, ny, plane, rate: 0.9 }, sheet(bump(-0.52, 0.68, 0.05, 0.6), bump(-0.45, 0.2, 0.07, 0.4)));
assert.equal(two.patches, 2);
assert.ok(two.holds([-0.52, 0.68]) && two.holds([-0.45, 0.2]) && !two.holds([-0.48, 0.44]));
assert.ok(two.held >= 0.9);
// the outline closes around each patch: every corner of it is the end of an even number of edges
const ends = new Map();
for (const [ax, ay, bx, by] of outline(two)) for (const key of [`${ax.toFixed(6)},${ay.toFixed(6)}`, `${bx.toFixed(6)},${by.toFixed(6)}`]) ends.set(key, (ends.get(key) || 0) + 1);
assert.ok([...ends.values()].every((count) => count % 2 === 0));

// the smooth edge runs between the cells inside and the cells outside: every point of it lies
// within a cell's width of the cells' own edge, and it is drawn around both patches
const edges = outline(two), reach = Math.hypot(two.dx, two.dy);
const near = (x, y) => edges.some(([ax, ay, bx, by]) => Math.hypot(x - (ax + bx) / 2, y - (ay + by) / 2) <= reach);
const smooth = contour(two);
assert.ok(smooth.length > 20 && smooth.every(([ax, ay, bx, by]) => near(ax, ay) && near(bx, by)));
assert.ok(smooth.some(([, ay]) => ay > 0.55) && smooth.some(([, ay]) => ay < 0.35));

// a flat sheet at a rate of one: every cell; a sheet of nothing: no cell
assert.equal(areaOf(new Float32Array(12).fill(1 / 12), 1).count, 12);
assert.equal(areaOf(new Float32Array(12), 0.9).count, 0);
assert.equal(patches(new Uint8Array([1, 0, 1, 0, 0, 0, 1, 0, 1]), 3, 3), 4);
assert.throws(() => sheetArea({ nx: 3, ny: 3, plane }, new Float32Array(8)));
console.log(JSON.stringify({ passed: true, one: { cells: one.count, held: +one.held.toFixed(4), area_cm2: Math.round(one.area * 1e4) }, two: { cells: two.count, patches: two.patches, held: +two.held.toFixed(4) } }));
