// The shapes of tracker/shapes.py and the same renderer: parts in units of the object's size,
// polygons turned by the object's angle, every pixel supersampled 4x4, holes showing the
// background. The brain was raised on pixels from the Python renderer; the page draws its
// surface with this port, and tests/test_shapes_js.py holds the two to the same pixels.

export const SUPERSAMPLE = 4;

const rect = (cx, cy, a, b) => [[cx - a, cy - b], [cx + a, cy - b], [cx + a, cy + b], [cx - a, cy + b]];

function star(points = 5, outer = 0.5, inner = 0.21) {
  const out = [];
  for (let k = 0; k < 2 * points; k++) {
    const t = -Math.PI / 2 + (k * Math.PI) / points;
    const r = k % 2 === 0 ? outer : inner;
    out.push([r * Math.cos(t), r * Math.sin(t)]);
  }
  return out;
}

// FaceShape defaults of tracker/world.py.
const F = { eye_dx: 0.21, eye_dy: 0.14, eye_r: 0.10, mouth_w: 0.40, mouth_dy: 0.27, mouth_h: 0.10, head_ry: 0.60 };

// A part is ["ellipse", cx, cy, a, b, hole] or ["poly", vertices, hole].
export const PARTS = {
  disc: [["ellipse", 0, 0, 0.5, 0.5, false]],
  ring: [["ellipse", 0, 0, 0.5, 0.5, false], ["ellipse", 0, 0, 0.26, 0.26, true]],
  square: [["poly", rect(0, 0, 0.42, 0.42), false]],
  frame: [["poly", rect(0, 0, 0.46, 0.46), false], ["poly", rect(0, 0, 0.24, 0.24), true]],
  triangle: [["poly", [[0, -0.5], [0.5, 0.4], [-0.5, 0.4]], false]],
  diamond: [["poly", [[0, -0.5], [0.36, 0], [0, 0.5], [-0.36, 0]], false]],
  cross: [["poly", rect(0, 0, 0.5, 0.14), false], ["poly", rect(0, 0, 0.14, 0.5), false]],
  bar: [["poly", rect(0, 0, 0.5, 0.15), false]],
  star: [["poly", star(), false]],
  tee: [["poly", rect(0, -0.36, 0.5, 0.14), false], ["poly", rect(0, 0.14, 0.14, 0.36), false]],
  ell: [["poly", rect(-0.3, 0, 0.14, 0.5), false], ["poly", rect(0.02, 0.36, 0.46, 0.14), false]],
  face: [
    ["ellipse", 0, 0, 0.5, F.head_ry, false],
    ["ellipse", -F.eye_dx, -F.eye_dy, F.eye_r, F.eye_r, true],
    ["ellipse", F.eye_dx, -F.eye_dy, F.eye_r, F.eye_r, true],
    ["poly", rect(0, F.mouth_dy, F.mouth_w / 2, F.mouth_h / 2), true],
  ],
};
export const TRAINED = ["disc", "ring", "square", "frame", "triangle", "diamond", "cross", "bar"];
export const HELD_OUT = ["star", "tee", "ell", "face"];
export const KINDS = [...TRAINED, ...HELD_OUT];
export const ROTATES = new Set(["square", "frame", "triangle", "diamond", "cross", "bar", "star", "tee", "ell"]);

// Even-odd rule for one point.
function insidePolygon(px, py, vx, vy) {
  let inside = false;
  for (let i = 0, j = vx.length - 1; i < vx.length; j = i++) {
    const crosses = (vy[i] > py) !== (vy[j] > py);
    if (!crosses) continue;
    const dy = vy[j] - vy[i];
    const xCross = vx[i] + ((py - vy[i]) * (vx[j] - vx[i])) / dy;
    if (px < xCross) inside = !inside;
  }
  return inside;
}

// Render things (surface coordinates) over a background (Float64Array, height*width) into a
// new Float64Array of the same size. Later things occlude earlier ones; a hole shows the background.
export function render(height, width, things, background) {
  const s = SUPERSAMPLE;
  const W = width * s;
  const H = height * s;
  const base = new Float64Array(H * W);
  for (let Y = 0; Y < H; Y++) {
    const row = background.subarray(Math.floor(Y / s) * width, Math.floor(Y / s) * width + width);
    for (let X = 0; X < W; X++) base[Y * W + X] = row[Math.floor(X / s)];
  }
  const canvas = base.slice();
  for (const t of things) {
    const cx = t.x;
    const cy = t.y;
    const reach = 0.75 * t.size + 0.5;
    const y0 = Math.max(Math.floor((cy - reach) * s), 0);
    const y1 = Math.min(Math.ceil((cy + reach) * s) + 1, H);
    const x0 = Math.max(Math.floor((cx - reach) * s), 0);
    const x1 = Math.min(Math.ceil((cx + reach) * s) + 1, W);
    if (y0 >= y1 || x0 >= x1) continue;
    const angle = ROTATES.has(t.kind) ? t.angle : 0.0;
    const c = Math.cos(angle);
    const sn = Math.sin(angle);
    for (const part of PARTS[t.kind]) {
      let test;
      let hole;
      if (part[0] === "ellipse") {
        const [, ex, ey, a, b, h] = part;
        hole = h;
        const px = cx + (ex * c - ey * sn) * t.size;
        const py = cy + (ex * sn + ey * c) * t.size;
        const ra = Math.max(a * t.size, 0.35);
        const rb = Math.max(b * t.size, 0.35);
        test = (gx, gy) => {
          const u = ((gx - px) * c + (gy - py) * sn) / ra;
          const v = (-(gx - px) * sn + (gy - py) * c) / rb;
          return u * u + v * v <= 1.0;
        };
      } else {
        const [, vertices, h] = part;
        hole = h;
        const vx = vertices.map(([x, y]) => cx + (x * t.size) * c - (y * t.size) * sn);
        const vy = vertices.map(([x, y]) => cy + (x * t.size) * sn + (y * t.size) * c);
        test = (gx, gy) => insidePolygon(gx, gy, vx, vy);
      }
      for (let Y = y0; Y < y1; Y++) {
        const gy = (Y + 0.5) / s;
        for (let X = x0; X < x1; X++) {
          const gx = (X + 0.5) / s;
          if (test(gx, gy)) canvas[Y * W + X] = hole ? base[Y * W + X] : t.level;
        }
      }
    }
  }
  const out = new Float64Array(height * width);
  const norm = 1 / (s * s);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      let sum = 0;
      for (let dy = 0; dy < s; dy++) {
        const r = (y * s + dy) * W + x * s;
        for (let dx = 0; dx < s; dx++) sum += canvas[r + dx];
      }
      out[y * width + x] = sum * norm;
    }
  }
  return out;
}

// A textured background like the world's: level plus Gaussian texture, clipped to [0, 1].
export function backdrop(height, width, level = 0.1, texture = 0.03, seed = 1) {
  let state = seed >>> 0 || 1;
  const uniform = () => {
    state ^= state << 13; state >>>= 0;
    state ^= state >>> 17;
    state ^= state << 5; state >>>= 0;
    return (state + 0.5) / 4294967296;
  };
  const out = new Float64Array(height * width);
  for (let i = 0; i < out.length; i++) {
    const g = Math.sqrt(-2 * Math.log(uniform())) * Math.cos(2 * Math.PI * uniform());
    out[i] = Math.min(Math.max(level + texture * g, 0), 1);
  }
  return out;
}
