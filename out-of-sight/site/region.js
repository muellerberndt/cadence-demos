// An area given as a set of cells.
//
// A place module states where a thing is as a place and a circle around it. A belief over the
// plane is a sheet of cells, each with its share of the belief, and its stated area at a rate is
// the smallest set of cells that holds that share: the cells taken from the most believed down.
// Such an area is no circle. It may be two patches: "kept going" and "stopped".
//
// This file is the page's side of that seam. A host that states a sheet sends `cells` in its
// reply ({ nx, ny, plane: [x low, x high, y low, y high], rate }) with the array `cells`: nx * ny
// shares that sum to one, row by row from the lowest y, each row from the lowest x. The scene,
// the map and the small map draw the area from it; a host that sends none is drawn with its
// circle. No host of this pack states a sheet: the interface comes with the module that does.

/** The smallest set of cells that holds `rate` of a sheet's shares: `inside` marks its cells,
 *  `count` is how many, `held` the share they hold and `level` the share of the least believed
 *  cell among them. Cells of equal share are taken in the sheet's order. */
export function areaOf(share, rate = 0.9) {
  const n = share.length, order = Array.from({ length: n }, (_, k) => k).sort((a, b) => share[b] - share[a] || a - b);
  let total = 0;
  for (let k = 0; k < n; k++) total += Math.max(0, share[k]);
  const inside = new Uint8Array(n);
  let held = 0, count = 0, level = 0;
  for (const k of order) {
    if (total <= 0 || held >= rate * total - 1e-12 || share[k] <= 0) break;
    inside[k] = 1; held += share[k]; count += 1; level = share[k];
  }
  return { inside, count, held: total > 0 ? held / total : 0, level };
}

/** The patches of an area: its cells joined edge to edge. Gives how many there are. */
export function patches(inside, nx, ny) {
  const seen = new Uint8Array(inside.length);
  let found = 0;
  for (let start = 0; start < inside.length; start++) {
    if (!inside[start] || seen[start]) continue;
    found += 1;
    const stack = [start];
    seen[start] = 1;
    while (stack.length) {
      const k = stack.pop(), i = k % nx, j = (k - i) / nx;
      for (const [di, dj] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        const a = i + di, b = j + dj, q = b * nx + a;
        if (a < 0 || b < 0 || a >= nx || b >= ny || !inside[q] || seen[q]) continue;
        seen[q] = 1; stack.push(q);
      }
    }
  }
  return found;
}

/** A sheet as the page holds it: the shares, the area at the sheet's rate, its size in square
 *  metres, its patches, and `holds(point)`: whether a point of the plane lies in the area. */
export function sheetArea(meta, share) {
  const { nx, ny, plane } = meta, rate = meta.rate ?? 0.9;
  if (share.length !== nx * ny) throw new Error(`a sheet of ${nx} by ${ny} cells holds ${nx * ny} shares; this one holds ${share.length}`);
  const area = areaOf(share, rate);
  const dx = (plane[1] - plane[0]) / nx, dy = (plane[3] - plane[2]) / ny;
  let top = 0;
  for (let k = 0; k < share.length; k++) top = Math.max(top, share[k]);
  const cellAt = (point) => {
    const i = Math.floor((point[0] - plane[0]) / dx), j = Math.floor((point[1] - plane[2]) / dy);
    return i < 0 || j < 0 || i >= nx || j >= ny ? -1 : j * nx + i;
  };
  return { nx, ny, plane: plane.slice(), rate, share, inside: area.inside, count: area.count, held: area.held, level: area.level, top,
    dx, dy, area: area.count * dx * dy, patches: patches(area.inside, nx, ny),
    holds: (point) => { const k = cellAt(point); return k >= 0 && area.inside[k] === 1; } };
}

/** The outline of an area: the edges between a cell inside and a cell outside (or the sheet's
 *  rim), as segments [x0, y0, x1, y1] in the plane's metres. */
export function outline(sheet) {
  const { nx, ny, plane, inside, dx, dy } = sheet, out = [];
  const is = (i, j) => i >= 0 && j >= 0 && i < nx && j < ny && inside[j * nx + i] === 1;
  for (let j = 0; j < ny; j++) {
    for (let i = 0; i < nx; i++) {
      if (!is(i, j)) continue;
      const x0 = plane[0] + i * dx, x1 = x0 + dx, y0 = plane[2] + j * dy, y1 = y0 + dy;
      if (!is(i - 1, j)) out.push([x0, y0, x0, y1]);
      if (!is(i + 1, j)) out.push([x1, y0, x1, y1]);
      if (!is(i, j - 1)) out.push([x0, y0, x1, y0]);
      if (!is(i, j + 1)) out.push([x0, y1, x1, y1]);
    }
  }
  return out;
}

/** The edge of an area as a smooth line: the contour of the sheet at the share of the area's
 *  least believed cell, drawn between the cells' centres (a cell inside lies on its inner side, a
 *  cell outside on its outer side). Segments [x0, y0, x1, y1] in the plane's metres. */
export function contour(sheet) {
  const { nx, ny, plane, share, inside, dx, dy } = sheet, out = [];
  if (!sheet.count) return out;
  // the level between the least believed cell inside and the most believed cell outside
  let most = 0;
  for (let k = 0; k < share.length; k++) if (!inside[k] && share[k] > most) most = share[k];
  const level = Math.min(sheet.level, (sheet.level + most) / 2);
  const at = (i, j) => (i < 0 || j < 0 || i >= nx || j >= ny ? 0 : share[j * nx + i]); // beyond the rim: nothing
  const X = (i) => plane[0] + (i + 0.5) * dx, Y = (j) => plane[2] + (j + 0.5) * dy;
  const cut = (a, b) => (a === b ? 0.5 : (level - a) / (b - a)); // where the level lies between two centres
  for (let j = -1; j < ny; j++) {
    for (let i = -1; i < nx; i++) {
      const a = at(i, j), b = at(i + 1, j), c = at(i + 1, j + 1), d = at(i, j + 1);
      const code = (a >= level ? 1 : 0) | (b >= level ? 2 : 0) | (c >= level ? 4 : 0) | (d >= level ? 8 : 0);
      if (code === 0 || code === 15) continue;
      const low = [X(i) + cut(a, b) * dx, Y(j)], right = [X(i + 1), Y(j) + cut(b, c) * dy];
      const high = [X(i) + cut(d, c) * dx, Y(j + 1)], left = [X(i), Y(j) + cut(a, d) * dy];
      const lines = { 1: [[left, low]], 2: [[low, right]], 3: [[left, right]], 4: [[right, high]], 5: [[left, high], [low, right]], 6: [[low, high]], 7: [[left, high]],
        8: [[left, high]], 9: [[low, high]], 10: [[left, low], [right, high]], 11: [[right, high]], 12: [[left, right]], 13: [[low, right]], 14: [[left, low]] }[code];
      for (const [p, q] of lines) out.push([p[0], p[1], q[0], q[1]]);
    }
  }
  return out;
}

/** A sheet as an image for a canvas: one pixel a cell, the top row the highest y. A cell of the
 *  area is drawn by its share of the most believed cell's; a cell outside it faintly, so that
 *  the area's edge is soft. `tint`: [r, g, b]. */
export function sheetImage(sheet, canvas, tint = [63, 224, 207]) {
  const { nx, ny, share, inside, top } = sheet;
  if (canvas.width !== nx || canvas.height !== ny) { canvas.width = nx; canvas.height = ny; }
  const c = canvas.getContext('2d'), image = c.createImageData(nx, ny);
  for (let j = 0; j < ny; j++) {
    for (let i = 0; i < nx; i++) {
      const k = j * nx + i, v = top > 0 ? Math.max(0, share[k]) / top : 0, o = 4 * ((ny - 1 - j) * nx + i);
      const light = Math.pow(v, 0.55);
      image.data[o] = tint[0] + (255 - tint[0]) * light * 0.55; image.data[o + 1] = tint[1] + (255 - tint[1]) * light * 0.55; image.data[o + 2] = tint[2] + (255 - tint[2]) * light * 0.55;
      image.data[o + 3] = 255 * (inside[k] ? 0.16 + 0.6 * light : 0.3 * light);
    }
  }
  c.putImageData(image, 0, 0);
  return canvas;
}
