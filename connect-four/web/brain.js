// The whole brain, drawn from the running brain's own numbers.
// Every neuron is a point in its population's place: the sensory neurons as 6 x 7 boards (the
// brain's stones, yours and the playable cells), the first module as a field placed by the board
// cells it reads, the association region as a field sorted by its weights, the silent prefrontal
// region, the 7 column neurons in column order and the 3 verdict neurons (loss, draw, win). A synapse glows with
// the message it carries, |weight x presynaptic activation|; while a sweep changes a
// presynaptic neuron, a pulse runs along its synapses. Nothing is invented: the activations are
// the settle's own sweeps and the weights are the brain's own. WebGL2 draws it on a GPU; on a
// software renderer, or if frames get slow, a Canvas2D view draws the neurons and the
// strongest messages instead.

const COLOR = {
  own: [0.24, 0.89, 0.82],
  opp: [1.0, 0.68, 0.33],
  association: [0.56, 0.62, 1.0],
  prefrontal: [0.42, 0.47, 0.62],
  motor: [0.24, 0.89, 0.82],
  play: [0.78, 0.8, 0.5],
  module_0: [0.4, 0.74, 1.0],
  verdict: [1.0, 0.8, 0.42],
  other: [0.72, 0.72, 0.82],
  excite: [1.0, 0.62, 0.28],
  inhibit: [0.32, 0.58, 1.0],
  pulse: [1.0, 0.95, 0.86],
};
const css = (rgb, a = 1) => `rgba(${rgb.map((v) => Math.round(v * 255)).join(',')},${a})`;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const ease = (f) => f * f * (3 - 2 * f);
const ROWS = 6, COLUMNS = 7;
const BRIGHTNESS = { 'sensory>association': 0.55, 'association>motor': 0.9, 'motor>association': 0.45,
  'sensory>module_0': 0.22, 'module_0>association': 0.45, 'association>module_0': 0.3 };
const SIDES = ['own', 'opp', 'play'];
const VERDICT = ['loss', 'draw', 'win'];
const LEVEL_FLOOR = 0.08; // a population this quiet is drawn at its true, dim level

const SYNAPSE_VS = `#version 300 es
precision highp float; precision highp int;
layout(location=0) in float t;
layout(location=1) in vec4 ends;
layout(location=2) in vec4 info;   // weight, presynaptic index, unused, brightness
layout(location=3) in vec4 ctrl;   // the curve's two control points: the bundle it joins
uniform sampler2D state;
uniform int stateWidth;
uniform vec2 viewport;
uniform float anatomy;
uniform float pulseGain;
out float vGlow; out float vSign; out float vT; out float vPulse;
void main() {
  int i = int(info.y + 0.5);
  vec4 s = texelFetch(state, ivec2(i % stateWidth, i / stateWidth), 0);
  float message = info.x * s.r;
  vec2 a = ends.xy, b = ends.zw, c1 = ctrl.xy, c2 = ctrl.zw;
  float u = 1.0 - t;
  vec2 p = u * u * u * a + 3.0 * u * u * t * c1 + 3.0 * u * t * t * c2 + t * t * t * b;
  vec2 clip = p / viewport * 2.0 - 1.0;
  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
  vGlow = clamp(abs(message) * info.w, 0.0, 1.0) + abs(info.x) * anatomy;
  vSign = message >= 0.0 ? 1.0 : -1.0;
  vT = t;
  vPulse = clamp(abs(info.x) * s.g * pulseGain * info.w, 0.0, 1.0);
}`;
const SYNAPSE_FS = `#version 300 es
precision highp float;
in float vGlow; in float vSign; in float vT; in float vPulse;
uniform vec3 excite; uniform vec3 inhibit; uniform vec3 pulseColor; uniform float progress;
out vec4 color;
void main() {
  vec3 base = vSign > 0.0 ? excite : inhibit;
  float head = exp(-pow((vT - progress) * 7.0, 2.0)) * vPulse;
  color = vec4(base * vGlow + pulseColor * head, 1.0);
}`;
const NEURON_VS = `#version 300 es
precision highp float; precision highp int;
layout(location=0) in vec2 position;
layout(location=1) in vec2 meta;   // index, radius in CSS px
layout(location=2) in vec3 hue;
uniform sampler2D state;
uniform int stateWidth;
uniform vec2 viewport;
uniform float dpr;
uniform float maxPoint;
out vec3 vHue; out float vLevel; out float vChange;
void main() {
  int i = int(meta.x + 0.5);
  vec4 s = texelFetch(state, ivec2(i % stateWidth, i / stateWidth), 0);
  vec2 clip = position / viewport * 2.0 - 1.0;
  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
  gl_PointSize = min(maxPoint, meta.y * dpr * 4.8 * (1.0 + 0.18 * clamp(s.b, 0.0, 1.0)));
  vHue = hue; vLevel = s.b; vChange = s.a;
}`;
const NEURON_FS = `#version 300 es
precision highp float;
in vec3 vHue; in float vLevel; in float vChange;
out vec4 color;
void main() {
  vec2 q = gl_PointCoord * 2.0 - 1.0;
  float r = length(q);
  if (r > 1.0) discard;
  float level = clamp(vLevel, -0.2, 1.0);
  float lit = smoothstep(0.0, 0.75, level);
  vec3 dim = vHue * 0.2 + vec3(0.035, 0.04, 0.07);
  vec3 hot = mix(vHue, vec3(1.0), smoothstep(0.55, 1.0, level) * 0.7);
  vec3 c = mix(dim, hot, lit);
  if (level < 0.0) c = dim * (1.0 + level * 2.5);
  float coreR = 0.25 + 0.15 * lit;
  float core = 1.0 - smoothstep(coreR - 0.04, coreR + 0.03, r);
  float halo = exp(-r * r * 9.0) * (0.15 + 0.85 * lit) + clamp(vChange * 6.0, 0.0, 0.6) * exp(-r * r * 5.0);
  float a = clamp(core * (0.55 + 0.45 * lit) + halo, 0.0, 1.0);
  color = vec4(c * a, a);
}`;

// The synapses' summed light, tone mapped: dense bundles stay bright without clipping to white.
const QUAD_VS = `#version 300 es
out vec2 uv;
void main() {
  vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  uv = p;
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`;
const QUAD_FS = `#version 300 es
precision highp float;
in vec2 uv;
uniform sampler2D light;
uniform float exposure;
out vec4 color;
void main() {
  vec3 x = texture(light, uv).rgb * exposure;
  float l = max(max(x.r, x.g), x.b);
  vec3 c = l > 0.0 ? x * ((1.0 - exp(-l)) / l) : vec3(0.0);
  color = vec4(c, 1.0);
}`;

function shader(gl, type, source) {
  const s = gl.createShader(type);
  gl.shaderSource(s, source);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) || 'shader');
  return s;
}
function program(gl, vs, fs) {
  const p = gl.createProgram();
  gl.attachShader(p, shader(gl, gl.VERTEX_SHADER, vs));
  gl.attachShader(p, shader(gl, gl.FRAGMENT_SHADER, fs));
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p) || 'link');
  const uniforms = {};
  const count = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
  for (let k = 0; k < count; k++) {
    const name = gl.getActiveUniform(p, k).name;
    uniforms[name] = gl.getUniformLocation(p, name);
  }
  return { p, u: uniforms };
}
// A stable pseudo-random number per synapse, for its curvature only.
const hash = (k) => { let x = (k + 0x9e3779b9) | 0; x = Math.imul(x ^ (x >>> 16), 0x85ebca6b); x = Math.imul(x ^ (x >>> 13), 0xc2b2ae35); return ((x ^ (x >>> 16)) >>> 0) / 4294967296; };

export class BrainView {
  constructor({ canvas, overlay, tooltip, onFrame, renderer = 'auto' }) {
    this.canvas = canvas; this.overlay = overlay; this.tooltip = tooltip; this.onFrame = onFrame;
    this.stage = canvas.parentElement;
    this.ctx = overlay.getContext('2d');
    this.gl = null;
    if (renderer !== '2d') {
      try {
        // A software renderer would stall the page on a hundred thousand curves: ask for a
        // context without a major performance caveat unless WebGL is forced.
        this.gl = canvas.getContext('webgl2', { antialias: true, premultipliedAlpha: true, alpha: false,
          failIfMajorPerformanceCaveat: renderer !== 'webgl' });
        if (this.gl) this.initGL();
      } catch (error) { console.warn('WebGL2 unavailable; drawing with Canvas2D.', error); this.gl = null; }
    }
    if (!this.gl) this.use2D(renderer === '2d' ? 'requested' : 'no fast WebGL2');
    this.frames = 0;
    this.hover = -1; this.pinned = false;
    this.flashes = null;
    this.running = false;
    this.playhead = 0;
    this.timeline = null;
    this.slow = 0;
    this.reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    new ResizeObserver(() => this.resize()).observe(this.stage);
    this.stage.addEventListener('pointermove', (e) => this.pointer(e));
    this.stage.addEventListener('pointerdown', (e) => this.pointer(e, true));
    this.stage.addEventListener('pointerleave', () => { if (!this.pinned) this.setHover(-1); });
  }

  // Draw with Canvas2D from now on, on a fresh canvas when the old one holds a WebGL context.
  use2D(reason) {
    if (this.gl) {
      const fresh = document.createElement('canvas');
      fresh.id = this.canvas.id; fresh.setAttribute('aria-label', this.canvas.getAttribute('aria-label') || '');
      this.canvas.replaceWith(fresh);
      this.canvas = fresh;
      this.gl = null;
    }
    this.mode = 'canvas2d';
    this.fallback = reason;
    this.ctx2 = this.canvas.getContext('2d');
    if (this.width) this.resize();
  }

  // -- the brain's anatomy

  setBrain(brain, arrays) {
    this.brain = brain;
    const n = this.n = brain.neurons;
    this.pre = arrays.pre; this.post = arrays.post; this.weight = Float32Array.from(arrays.weight); this.bias = arrays.bias;
    const roles = this.roles = new Array(n).fill('other');
    this.cell = new Int16Array(n).fill(-1);
    this.column = new Int16Array(n).fill(-1);
    for (const p of brain.populations) for (let i = p.start; i < p.start + p.size; i++) roles[i] = p.name;
    brain.sensory.forEach((i, k) => { roles[i] = SIDES[Math.floor(k / 42)]; this.cell[i] = k % 42; });
    brain.motor.forEach((i, c) => { roles[i] = c < COLUMNS ? 'motor' : 'verdict'; this.column[i] = c; });
    this.silent = new Set(brain.silent || []);
    this.groups = { own: brain.sensory.slice(0, 42), opp: brain.sensory.slice(42, 84), motor: brain.motor.slice(0, COLUMNS) };
    if (brain.sensory.length > 84) this.groups.play = brain.sensory.slice(84, 126);
    if (brain.motor.length > COLUMNS) this.groups.verdict = brain.motor.slice(COLUMNS);
    for (const p of brain.populations) {
      const members = [];
      for (let i = p.start; i < p.start + p.size; i++) if (roles[i] === p.name) members.push(i);
      if (members.length) this.groups[p.name] = members;
    }
    this.inbound = this.lists(this.post, n);
    this.outbound = this.lists(this.pre, n);
    // per synapse: its block and how bright a typical message of that block should glow
    const m = this.pre.length;
    this.blockOf = new Uint8Array(m);
    this.blockNames = [];
    const index = new Map(), sums = [], counts = [];
    for (let k = 0; k < m; k++) {
      const key = `${this.family(this.pre[k])}>${this.family(this.post[k])}`;
      if (!index.has(key)) { index.set(key, this.blockNames.length); this.blockNames.push(key); sums.push(0); counts.push(0); }
      const b = index.get(key);
      this.blockOf[k] = b; sums[b] += Math.abs(this.weight[k]); counts[b]++;
    }
    this.blockScale = sums.map((s, b) => (counts[b] ? s / counts[b] : 1));
    this.associationOrder();
    // Brightness is relative to the most active neuron of the same population in this settle,
    // so a quiet region still shows its pattern; the tooltip reads the raw activation.
    this.popNames = Object.keys(this.groups);
    this.popOf = new Uint8Array(n);
    this.popNames.forEach((name, p) => { for (const i of this.groups[name]) this.popOf[i] = p; });
    this.levelScale = new Float32Array(this.popNames.length).fill(LEVEL_FLOOR);
    this.display = new Float32Array(n);
    this.change = new Float32Array(n);
    this.peak = new Float32Array(m);
    this.candidates = new Int32Array(0);
    this.timeline = null;
    this.playhead = 0;
    this.layout();
  }

  family(i) { const r = this.roles[i]; return SIDES.includes(r) ? 'sensory' : r === 'verdict' ? 'motor' : r; }

  lists(index, n) {
    const counts = new Int32Array(n + 1);
    for (let k = 0; k < index.length; k++) counts[index[k] + 1]++;
    for (let i = 0; i < n; i++) counts[i + 1] += counts[i];
    const order = new Int32Array(index.length), fill = counts.slice(0, n);
    for (let k = 0; k < index.length; k++) order[fill[index[k]]++] = k;
    return { start: counts, order };
  }

  // Association neurons sorted into a field: left to right by the column they excite most,
  // bottom to top by the board rows they read. Computed once from the loaded weights.
  associationOrder() {
    const members = this.groups.association || [];
    const N = members.length, place = new Map(members.map((i, k) => [i, k]));
    const colSum = new Float64Array(N), colW = new Float64Array(N), rowSum = new Float64Array(N), rowW = new Float64Array(N);
    for (let k = 0; k < this.pre.length; k++) {
      const p = this.pre[k], q = this.post[k], w = this.weight[k];
      if (this.column[q] >= 0 && w > 0 && place.has(p)) { const j = place.get(p); colSum[j] += w * this.column[q]; colW[j] += w; }
      if (this.cell[p] >= 0 && place.has(q)) { const j = place.get(q); rowSum[j] += Math.abs(w) * Math.floor(this.cell[p] / COLUMNS); rowW[j] += Math.abs(w); }
    }
    this.assocSorted = members.map((i, j) => ({ i, x: colW[j] > 0 ? colSum[j] / colW[j] : 3, y: rowW[j] > 0 ? rowSum[j] / rowW[j] : 2.5 }));
    // the first module of a deep brain reads the board: placed by the cells it reads, left to
    // right by their column and bottom to top by their row
    const first = this.groups.module_0 || [];
    const at = new Map(first.map((i, k) => [i, k]));
    const cx = new Float64Array(first.length), cy = new Float64Array(first.length), cw = new Float64Array(first.length);
    for (let k = 0; k < this.pre.length; k++) {
      const p = this.pre[k], q = this.post[k];
      if (this.cell[p] >= 0 && this.roles[p] !== 'play' && at.has(q)) {
        const j = at.get(q), w = Math.abs(this.weight[k]);
        cx[j] += w * (this.cell[p] % COLUMNS); cy[j] += w * Math.floor(this.cell[p] / COLUMNS); cw[j] += w;
      }
    }
    this.firstSorted = first.map((i, j) => ({ i, x: cw[j] > 0 ? cx[j] / cw[j] : 3, y: cw[j] > 0 ? cy[j] / cw[j] : 2.5 }));
  }

  setWeights(weight, bias) {
    this.weight = Float32Array.from(weight);
    this.bias = bias;
    if (this.gl) this.uploadSynapses();
    this.wake();
  }

  // -- layout in CSS pixels

  resize() {
    const box = this.stage.getBoundingClientRect();
    const w = Math.max(240, Math.round(box.width)), h = Math.max(240, Math.round(box.height));
    this.dpr = Math.min(2, window.devicePixelRatio || 1);
    for (const c of [this.canvas, this.overlay]) {
      c.width = Math.round(w * this.dpr); c.height = Math.round(h * this.dpr);
      c.style.width = `${w}px`; c.style.height = `${h}px`;
    }
    this.width = w; this.height = h;
    if (this.brain) this.layout();
  }

  // The brain seen from the side, front to the left: each population sits in the region whose
  // role it plays (the page names the role, not an identity). Places come from the brain's own
  // weights: the first module by the board cells it reads, the association field by the columns
  // it drives.
  layout() {
    if (!this.width) { this.resize(); return; }
    const W = this.width, H = this.height, n = this.n;
    const pos = this.pos = new Float32Array(2 * n);
    const size = this.size = new Float32Array(n);
    const hue = this.hue = new Float32Array(3 * n);
    this.regions = [];
    const pad = Math.max(10, Math.round(W * 0.02));
    // the brain's box: aspect 1.45, centred, a little room above for the motor labels
    const bw = Math.min(W - 2 * pad, (H - 2 * pad - 18) * 1.45), bh = bw / 1.45;
    const bx = (W - bw) / 2, by = (H - bh) / 2 + 8;
    const at = (u, v) => [bx + u * bw, by + v * bh];
    this.brainBox = { x: bx, y: by, w: bw, h: bh };
    const ellipse = (members, cx, cy, rx, ry, key) => {
      // a hexagonal grid clipped to the ellipse, with at least as many places as members
      const N = members.length;
      if (!N) return;
      const [X, Y] = at(cx, cy), RX = rx * bw, RY = ry * bh;
      let step = Math.sqrt((Math.PI * RX * RY) / (N * 0.866)) * 1.02, places = [];
      for (let tries = 0; tries < 12; tries++) {
        places = [];
        const k = 0.866 * step;
        for (let y = -RY; y <= RY; y += k) {
          const odd = Math.round((y + RY) / k) % 2;
          for (let x = -RX + (odd ? step / 2 : 0); x <= RX; x += step) {
            if ((x * x) / (RX * RX) + (y * y) / (RY * RY) <= 1) places.push([X + x, Y + y]);
          }
        }
        if (places.length >= N) break;
        step *= 0.95;
      }
      // pair members and places column by column: x orders the columns, y the rows
      places.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
      const sorted = members.slice().sort((a, b) => a.x - b.x || a.i - b.i);
      const cols = Math.max(1, Math.round(Math.sqrt(N * (RX / RY))));
      for (let c = 0; c < cols; c++) {
        const lo = Math.floor((c * N) / cols), hi = Math.floor(((c + 1) * N) / cols);
        const plo = Math.floor((c * places.length) / cols), phi = Math.floor(((c + 1) * places.length) / cols);
        const ms = sorted.slice(lo, hi).sort((a, b) => b.y - a.y || a.i - b.i);
        const ps = places.slice(plo, phi).sort((a, b) => a[1] - b[1]);
        ms.forEach((m, r) => {
          const q = ps[Math.min(ps.length - 1, Math.floor((r * ps.length) / Math.max(1, ms.length)))];
          pos[2 * m.i] = q[0]; pos[2 * m.i + 1] = q[1]; size[m.i] = Math.max(1.1, step * 0.34);
        });
      }
      return { x: X, y: Y, rx: RX, ry: RY };
    };
    // the three input boards: the back of the brain, where vision is (one 6 x 7 patch each)
    const sides = SIDES.filter((side) => this.groups[side]);
    const cell = Math.min(bw * 0.034, (bh * 0.62) / (sides.length * ROWS + (sides.length - 1) * 1.2));
    const boardW = cell * COLUMNS, boardH = cell * ROWS;
    const [vx, vy] = at(0.885, 0.47);
    const top = vy - (sides.length * boardH + (sides.length - 1) * cell * 1.2) / 2;
    this.boards = [];
    sides.forEach((side, b) => {
      const x0 = vx - boardW / 2, y0 = top + b * (boardH + cell * 1.2);
      this.boards.push({ side, x: x0, y: y0, w: boardW, h: boardH, cell });
      for (const i of this.groups[side]) {
        const k = this.cell[i], r = Math.floor(k / COLUMNS), c = k % COLUMNS;
        pos[2 * i] = x0 + (c + 0.5) * cell; pos[2 * i + 1] = y0 + (ROWS - 1 - r + 0.5) * cell; size[i] = cell * 0.3;
      }
    });
    this.regions.push({ name: 'sensory', label: `visual cortex · sensory ${42 * sides.length}`, short: 'sensory', x: vx - boardW / 2, y: top - 30,
      role: 'Where the board enters: one neuron per cell of its stones, your stones and the playable cells (the role of a primary visual area).' });
    // the first module of a deep brain: the next stage of vision, placed by the cells it reads
    const first = ellipse(this.firstSorted || [], 0.70, 0.36, 0.10, 0.25);
    if (first) this.regions.push({ name: 'module_0', label: `module 0 · ${(this.groups.module_0 || []).length}`, short: 'module 0', x: first.x - first.rx, y: first.y - first.ry - 16,
      role: 'Reads the board cells directly and feeds the association field (the role of a higher visual area). Placed by the cells each neuron reads.' });
    // the association field, placed by the columns it drives
    const assoc = ellipse(this.assocSorted || [], 0.48, 0.42, 0.115, 0.26);
    if (assoc) this.regions.push({ name: 'association', label: `association · ${(this.groups.association || []).length}`, short: 'association', x: assoc.x - assoc.rx * 0.6, y: assoc.y - assoc.ry - 16,
      role: 'Reciprocal with the first module and the motor neurons: where the settle agrees on a move (the role of association cortex). Placed by the columns each neuron drives.' });
    // prefrontal: the working trace's target, silent in a memory-free settle
    const pf = this.groups.prefrontal || [];
    const pre = ellipse(pf.map((i, k) => ({ i, x: k % 32, y: Math.floor(k / 32) })), 0.17, 0.43, 0.115, 0.23);
    if (pre) this.regions.push({ name: 'prefrontal', label: `prefrontal · ${pf.length} · silent`, short: 'prefrontal · silent', x: pre.x - pre.rx, y: pre.y - pre.ry - 16, silent: true,
      role: 'Where Cadence’s working trace enters (the role of prefrontal cortex). This brain settles without memory, so it stays at rest.' });
    // the motor strip: one neuron per column along an arc in front of the association field
    const mR = clamp(bw * 0.014, 5, 11);
    this.groups.motor.forEach((i, c) => {
      const t = c / Math.max(1, COLUMNS - 1);
      const [x, y] = at(0.33 + 0.06 * Math.sin(Math.PI * t) - 0.02 * t, 0.12 + 0.52 * t);
      pos[2 * i] = x; pos[2 * i + 1] = y; size[i] = mR;
    });
    {
      const [x, y] = at(0.27, 0.06);
      this.regions.push({ name: 'motor', label: 'motor strip · 7 columns', short: 'motor', x, y,
        role: 'One neuron per column; the strongest one whose column has room is the brain’s move (the role of the motor cortex).' });
    }
    // the verdict: three neurons deep under the cortex, its judgement of the position
    const verdict = this.groups.verdict || [];
    verdict.forEach((i, k) => {
      const [x, y] = at(0.40 + 0.055 * k, 0.80 - 0.02 * Math.abs(k - 1));
      pos[2 * i] = x; pos[2 * i + 1] = y; size[i] = mR * 1.05;
    });
    if (verdict.length) {
      const [x, y] = at(0.53, 0.78);
      this.regions.push({ name: 'verdict', label: 'verdict', short: 'verdict', x, y: y - 6,
        role: 'Three motor neurons taught the solver’s result for the side to move (the role of a value judgement, as in orbitofrontal cortex and striatum). The move does not read them.' });
    }
    // any other population of another brain: a field under the association cortex
    const placed = new Set(['own', 'opp', 'play', 'module_0', 'association', 'prefrontal', 'motor', 'verdict']);
    const rest = Object.keys(this.groups).filter((g) => !placed.has(g));
    rest.forEach((g, k) => {
      const f = ellipse(this.groups[g].map((i, j) => ({ i, x: j, y: 0 })), 0.62 + 0.1 * k, 0.70, 0.06, 0.07);
      if (f) this.regions.push({ name: g, label: `${g} · ${this.groups[g].length}`, short: g, x: f.x - f.rx, y: f.y + f.ry + 3, role: 'A population of this brain.' });
    });
    for (let i = 0; i < n; i++) hue.set(COLOR[this.roles[i]] || COLOR.other, 3 * i);
    this.regionCentroids();
    if (this.gl) { this.uploadLayout(); this.uploadSynapses(); }
    this.drawOverlay();
    this.wake();
  }

  // The centre of each region, and the bundled path every synapse takes between two regions: a
  // tract from one region to the other, curving to one side so that the reciprocal tract runs
  // beside it; a synapse leaves its neuron, joins the tract and leaves it at its target.
  region(i) { const r = this.roles[i]; return SIDES.includes(r) ? 'sensory' : r; }

  regionCentroids() {
    const sum = new Map();
    for (let i = 0; i < this.n; i++) {
      const r = this.region(i);
      const s = sum.get(r) || [0, 0, 0];
      s[0] += this.pos[2 * i]; s[1] += this.pos[2 * i + 1]; s[2]++; sum.set(r, s);
    }
    this.centroid = new Map([...sum].map(([r, s]) => [r, [s[0] / s[2], s[1] / s[2]]]));
    const order = ['sensory', 'module_0', 'association', 'motor', 'verdict', 'prefrontal', 'other'];
    const m = this.pre.length, ctrl = this.ctrl = new Float32Array(4 * m);
    for (let k = 0; k < m; k++) {
      const p = this.pre[k], q = this.post[k];
      const ra = this.region(p), rb = this.region(q);
      const A = this.centroid.get(ra), B = this.centroid.get(rb);
      const P0 = [this.pos[2 * p], this.pos[2 * p + 1]], P3 = [this.pos[2 * q], this.pos[2 * q + 1]];
      if (ra === rb || !A || !B) {
        ctrl[4 * k] = P0[0] + (P3[0] - P0[0]) / 3; ctrl[4 * k + 1] = P0[1] + (P3[1] - P0[1]) / 3;
        ctrl[4 * k + 2] = P0[0] + 2 * (P3[0] - P0[0]) / 3; ctrl[4 * k + 3] = P0[1] + 2 * (P3[1] - P0[1]) / 3;
        continue;
      }
      const dx = B[0] - A[0], dy = B[1] - A[1], len = Math.hypot(dx, dy) || 1;
      const side = order.indexOf(ra) < order.indexOf(rb) ? 1 : -1;
      const nx = -dy / len, ny = dx / len, bulge = 0.16 * len * side;
      const M = [(A[0] + B[0]) / 2 + nx * bulge, (A[1] + B[1]) / 2 + ny * bulge];
      const bez = (t) => [(1 - t) * (1 - t) * A[0] + 2 * (1 - t) * t * M[0] + t * t * B[0], (1 - t) * (1 - t) * A[1] + 2 * (1 - t) * t * M[1] + t * t * B[1]];
      const T1 = bez(0.3), T2 = bez(0.7);
      const j = (hash(k) - 0.5) * Math.min(14, len * 0.06), jx = nx * j, jy = ny * j;
      ctrl[4 * k] = P0[0] + (T1[0] - P0[0]) * 0.85 + jx; ctrl[4 * k + 1] = P0[1] + (T1[1] - P0[1]) * 0.85 + jy;
      ctrl[4 * k + 2] = P3[0] + (T2[0] - P3[0]) * 0.85 + jx; ctrl[4 * k + 3] = P3[1] + (T2[1] - P3[1]) * 0.85 + jy;
    }
  }

  // The outline of a brain seen from the side (front to the left), the frame the regions sit in.
  silhouette(c) {
    const b = this.brainBox;
    if (!b) return;
    const P = (u, v) => [b.x + u * b.w, b.y + v * b.h];
    const curve = (pts) => {
      c.beginPath();
      c.moveTo(...P(...pts[0]));
      for (let k = 1; k < pts.length; k++) {
        const [u0, v0] = pts[k - 1], [u1, v1] = pts[k];
        c.quadraticCurveTo(...P(u0, v0), ...P((u0 + u1) / 2, (v0 + v1) / 2));
      }
    };
    c.save();
    c.lineWidth = 1.2;
    // the cortex
    curve([[0.06, 0.52], [0.02, 0.36], [0.08, 0.16], [0.24, 0.04], [0.46, 0.0], [0.68, 0.03], [0.86, 0.14], [0.97, 0.34],
      [0.98, 0.56], [0.93, 0.72], [0.80, 0.80], [0.62, 0.82], [0.50, 0.92], [0.36, 0.86], [0.22, 0.80], [0.10, 0.70], [0.06, 0.52]]);
    c.closePath();
    const g = c.createRadialGradient(...P(0.5, 0.42), 10, ...P(0.5, 0.42), b.w * 0.6);
    g.addColorStop(0, 'rgba(60,70,110,0.10)'); g.addColorStop(1, 'rgba(20,24,40,0.02)');
    c.fillStyle = g; c.fill();
    c.strokeStyle = 'rgba(150,165,210,0.22)'; c.stroke();
    // the cerebellum and the brainstem (no populations of this brain sit there)
    curve([[0.70, 0.84], [0.82, 0.80], [0.92, 0.84], [0.90, 0.95], [0.76, 0.98], [0.66, 0.92], [0.70, 0.84]]);
    c.strokeStyle = 'rgba(150,165,210,0.12)'; c.stroke();
    curve([[0.56, 0.90], [0.60, 1.02], [0.64, 1.06]]);
    c.stroke();
    // the central and lateral sulci
    c.setLineDash([3, 5]);
    curve([[0.40, 0.02], [0.37, 0.24], [0.36, 0.48]]); c.strokeStyle = 'rgba(150,165,210,0.16)'; c.stroke();
    curve([[0.30, 0.62], [0.48, 0.64], [0.66, 0.58]]); c.stroke();
    c.restore();
  }

  // A hexagonally packed field of `count` places in a w x h box: odd rows shift half a step.
  grid(count, w, h) {
    const k = Math.sqrt(3) / 2;
    const cols = Math.max(1, Math.round(Math.sqrt(count * w / Math.max(1, h) * k)));
    const rows = Math.ceil(count / cols);
    const step = Math.min(w / (cols + 0.5), h / (rows * k));
    const x0 = (w - (cols + 0.5) * step) / 2, y0 = (h - rows * k * step) / 2;
    return { cols, rows, step, place: (c, r) => [x0 + (c + 0.5 + (r % 2) * 0.5) * step, y0 + (r + 0.5) * k * step] };
  }

  // The largest activation of each population over these frames sets its brightness scale.
  rescale(frames) {
    this.levelScale.fill(LEVEL_FLOOR);
    for (const frame of frames) {
      for (let i = 0; i < this.n; i++) {
        const p = this.popOf[i];
        if (frame[i] > this.levelScale[p]) this.levelScale[p] = frame[i];
      }
    }
  }

  // -- WebGL2

  initGL() {
    const gl = this.gl;
    this.mode = 'webgl2';
    this.synapseProgram = program(gl, SYNAPSE_VS, SYNAPSE_FS);
    this.neuronProgram = program(gl, NEURON_VS, NEURON_FS);
    this.stateTex = gl.createTexture();
    this.stateWidth = 1024;
    this.synapseVAO = gl.createVertexArray();
    this.neuronVAO = gl.createVertexArray();
    this.buffers = { t: gl.createBuffer(), ends: gl.createBuffer(), info: gl.createBuffer(), ctrl: gl.createBuffer(), position: gl.createBuffer(), meta: gl.createBuffer(), hue: gl.createBuffer() };
    this.maxPoint = gl.getParameter(gl.ALIASED_POINT_SIZE_RANGE)[1] || 64;
    this.hdr = !!(gl.getExtension('EXT_color_buffer_float') || gl.getExtension('EXT_color_buffer_half_float'));
    if (this.hdr) {
      this.compositeProgram = program(gl, QUAD_VS, QUAD_FS);
      this.quadVAO = gl.createVertexArray();
      this.fbo = gl.createFramebuffer();
      this.lightTex = gl.createTexture();
      this.fboSize = [0, 0];
    }
    this.canvas.addEventListener('webglcontextlost', (e) => { e.preventDefault(); this.use2D('context lost'); });
  }

  // The off-screen buffer the synapses add their light into, at the canvas's size.
  lightBuffer() {
    const gl = this.gl, w = this.canvas.width, h = this.canvas.height;
    if (this.fboSize[0] === w && this.fboSize[1] === h) return true;
    gl.bindTexture(gl.TEXTURE_2D, this.lightTex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, w, h, 0, gl.RGBA, gl.HALF_FLOAT, null);
    for (const p of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_2D, p, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, this.lightTex, 0);
    const ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE;
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    if (!ok) { this.hdr = false; return false; }
    this.fboSize = [w, h];
    return true;
  }

  uploadLayout() {
    const gl = this.gl, n = this.n;
    const meta = new Float32Array(2 * n);
    for (let i = 0; i < n; i++) { meta[2 * i] = i; meta[2 * i + 1] = this.size[i]; }
    gl.bindVertexArray(this.neuronVAO);
    const attr = (buffer, data, loc, width) => {
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer); gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
      gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, width, gl.FLOAT, false, 0, 0);
    };
    attr(this.buffers.position, this.pos, 0, 2);
    attr(this.buffers.meta, meta, 1, 2);
    attr(this.buffers.hue, this.hue, 2, 3);
    gl.bindVertexArray(null);
    this.stateHeight = Math.ceil(n / this.stateWidth);
    this.stateData = new Float32Array(4 * this.stateWidth * this.stateHeight);
    gl.bindTexture(gl.TEXTURE_2D, this.stateTex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA32F, this.stateWidth, this.stateHeight, 0, gl.RGBA, gl.FLOAT, this.stateData);
    for (const p of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_2D, p, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  }

  uploadSynapses() {
    const gl = this.gl, m = this.pre.length;
    if (!this.pos || !gl) return;
    this.segments = m > 120000 ? 6 : 8;
    const t = new Float32Array(2 * this.segments);
    for (let k = 0; k < this.segments; k++) { t[2 * k] = k / this.segments; t[2 * k + 1] = (k + 1) / this.segments; }
    const ends = new Float32Array(4 * m), info = new Float32Array(4 * m);
    const gains = this.blockNames.map((name, b) => (BRIGHTNESS[name] ?? 0.3) / (this.blockScale[b] * 0.6 || 1) * this.synapseGain(name));
    for (let k = 0; k < m; k++) {
      const p = this.pre[k], q = this.post[k], b = this.blockOf[k], name = this.blockNames[b];
      ends[4 * k] = this.pos[2 * p]; ends[4 * k + 1] = this.pos[2 * p + 1]; ends[4 * k + 2] = this.pos[2 * q]; ends[4 * k + 3] = this.pos[2 * q + 1];
      const bend = (hash(k) - 0.5) * (name.includes('motor') ? 0.18 : 0.32);
      info[4 * k] = this.weight[k]; info[4 * k + 1] = p; info[4 * k + 2] = bend; info[4 * k + 3] = gains[b];
    }
    gl.bindVertexArray(this.synapseVAO);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers.t); gl.bufferData(gl.ARRAY_BUFFER, t, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 1, gl.FLOAT, false, 0, 0); gl.vertexAttribDivisor(0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers.ends); gl.bufferData(gl.ARRAY_BUFFER, ends, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1, 4, gl.FLOAT, false, 0, 0); gl.vertexAttribDivisor(1, 1);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers.info); gl.bufferData(gl.ARRAY_BUFFER, info, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(2); gl.vertexAttribPointer(2, 4, gl.FLOAT, false, 0, 0); gl.vertexAttribDivisor(2, 1);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers.ctrl); gl.bufferData(gl.ARRAY_BUFFER, this.ctrl, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(3); gl.vertexAttribPointer(3, 4, gl.FLOAT, false, 0, 0); gl.vertexAttribDivisor(3, 1);
    gl.bindVertexArray(null);
    this.synapseCount = m;
  }

  // A wide fan of synapses into one neuron glows fainter per synapse than a narrow one.
  synapseGain(block) {
    const N = (this.groups.association || []).length || 64;
    const F = (this.groups.module_0 || []).length || N;
    const fan = { 'sensory>association': N, 'association>motor': N / 7, 'motor>association': N,
      'sensory>module_0': 126, 'module_0>association': F, 'association>module_0': N };
    return clamp(Math.sqrt(256 / (fan[block] || 64)), 0.35, 1.6) * clamp(this.width / 640, 0.6, 1.2) * 0.5;
  }

  drawGL(progress) {
    const gl = this.gl, s = this.stateData, n = this.n;
    for (let i = 0; i < n; i++) {
      const scale = this.levelScale[this.popOf[i]];
      s[4 * i] = this.display[i]; s[4 * i + 1] = this.change[i];
      s[4 * i + 2] = this.display[i] / scale; s[4 * i + 3] = this.change[i] / scale;
    }
    gl.bindTexture(gl.TEXTURE_2D, this.stateTex);
    gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, this.stateWidth, this.stateHeight, gl.RGBA, gl.FLOAT, s);
    const hdr = this.hdr && this.lightBuffer();
    gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    if (hdr) { gl.bindFramebuffer(gl.FRAMEBUFFER, this.fbo); gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT); }
    else { gl.clearColor(0.027, 0.035, 0.063, 1); gl.clear(gl.COLOR_BUFFER_BIT); }
    gl.enable(gl.BLEND);
    const sp = this.synapseProgram;
    gl.useProgram(sp.p);
    gl.blendFunc(gl.ONE, gl.ONE);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.stateTex);
    gl.uniform1i(sp.u.state, 0); gl.uniform1i(sp.u.stateWidth, this.stateWidth);
    gl.uniform2f(sp.u.viewport, this.width, this.height);
    gl.uniform1f(sp.u.anatomy, 0.05 / Math.max(1, Math.sqrt(this.synapseCount / 2000)));
    gl.uniform1f(sp.u.pulseGain, this.reduced ? 0 : 9);
    gl.uniform1f(sp.u.progress, progress);
    gl.uniform3fv(sp.u.excite, COLOR.excite); gl.uniform3fv(sp.u.inhibit, COLOR.inhibit); gl.uniform3fv(sp.u.pulseColor, COLOR.pulse);
    gl.bindVertexArray(this.synapseVAO);
    gl.drawArraysInstanced(gl.LINES, 0, 2 * this.segments, this.synapseCount);
    if (hdr) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.clearColor(0.027, 0.035, 0.063, 1); gl.clear(gl.COLOR_BUFFER_BIT);
      const cp = this.compositeProgram;
      gl.useProgram(cp.p);
      gl.blendFunc(gl.ONE, gl.ONE);
      gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, this.lightTex);
      gl.uniform1i(cp.u.light, 1); gl.uniform1f(cp.u.exposure, 1.35);
      gl.bindVertexArray(this.quadVAO);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      gl.activeTexture(gl.TEXTURE0);
    }
    const np = this.neuronProgram;
    gl.useProgram(np.p);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.uniform1i(np.u.state, 0); gl.uniform1i(np.u.stateWidth, this.stateWidth);
    gl.uniform2f(np.u.viewport, this.width, this.height);
    gl.uniform1f(np.u.dpr, this.dpr); gl.uniform1f(np.u.maxPoint, this.maxPoint);
    gl.bindVertexArray(this.neuronVAO);
    gl.drawArrays(gl.POINTS, 0, n);
    gl.bindVertexArray(null);
  }

  // -- Canvas2D: the neurons and the strongest messages of the settle

  // The synapses whose messages peaked highest so far in this settle, at most `limit` of them.
  selectCandidates(limit = 2400) {
    const m = this.peak.length;
    if (m <= limit) { this.candidates = Int32Array.from({ length: m }, (_, k) => k); return; }
    const sorted = Float32Array.from(this.peak).sort();
    const threshold = Math.max(1e-6, sorted[m - limit]);
    const out = [];
    for (let k = 0; k < m && out.length < limit; k++) if (this.peak[k] >= threshold) out.push(k);
    this.candidates = Int32Array.from(out);
    this.peakMax = sorted[m - 1] || 1;
  }

  draw2D() {
    const c = this.ctx2, n = this.n, dpr = this.dpr;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.fillStyle = '#07090f'; c.fillRect(0, 0, this.width, this.height);
    const levels = 6, paths = [[], []];
    for (let b = 0; b < levels; b++) { paths[0].push(new Path2D()); paths[1].push(new Path2D()); }
    const scale = this.peakMax || 1;
    for (const k of this.candidates) {
      const v = this.weight[k] * this.display[this.pre[k]];
      const level = Math.min(levels - 1, Math.floor(levels * Math.abs(v) / scale));
      if (Math.abs(v) < scale * 0.03) continue;
      const path = paths[v >= 0 ? 0 : 1][level];
      path.moveTo(this.pos[2 * this.pre[k]], this.pos[2 * this.pre[k] + 1]);
      path.bezierCurveTo(this.ctrl[4 * k], this.ctrl[4 * k + 1], this.ctrl[4 * k + 2], this.ctrl[4 * k + 3], this.pos[2 * this.post[k]], this.pos[2 * this.post[k] + 1]);
    }
    c.globalCompositeOperation = 'lighter'; c.lineWidth = 0.7;
    for (let b = 0; b < levels; b++) {
      c.strokeStyle = css(COLOR.excite, 0.05 + 0.5 * (b + 0.5) / levels); c.stroke(paths[0][b]);
      c.strokeStyle = css(COLOR.inhibit, 0.05 + 0.5 * (b + 0.5) / levels); c.stroke(paths[1][b]);
    }
    c.globalCompositeOperation = 'source-over';
    for (let i = 0; i < n; i++) {
      const level = clamp(this.display[i] / this.levelScale[this.popOf[i]], -0.2, 1), h = COLOR[this.roles[i]] || COLOR.other;
      const lit = clamp(level / 0.75, 0, 1);
      c.fillStyle = css(h.map((v) => 0.035 + v * (0.2 + 0.8 * lit)), 1);
      const r = this.size[i] * (1 + 0.2 * lit);
      if (r < 2.2) c.fillRect(this.pos[2 * i] - r, this.pos[2 * i + 1] - r, 2 * r, 2 * r);
      else { c.beginPath(); c.arc(this.pos[2 * i], this.pos[2 * i + 1], r, 0, Math.PI * 2); c.fill(); }
    }
  }

  // -- the settle, sweep by sweep

  // A new settle starts from rest: the shown state releases to rest, then the sweeps play.
  beginSettle() {
    this.timeline = { frames: [Float32Array.from(this.display), new Float32Array(this.n)], movement: [null, null], complete: false, final: null };
    this.playhead = 0;
    this.msPerSweep = 40;
    this.playing = true;
    this.peak.fill(0); this.candidates = new Int32Array(0);
    this.donePromise = new Promise((resolve) => { this.resolveDone = resolve; });
    if (!this.pinned) this.setHover(-1);
    this.wake();
  }

  pushFrames(frames, movement) {
    const tl = this.timeline, n = this.n;
    if (!tl) return;
    const k = frames.length / n;
    for (let j = 0; j < k; j++) {
      const frame = frames.slice(j * n, (j + 1) * n);
      tl.frames.push(frame); tl.movement.push(movement[j]);
      if (!this.gl) for (let s = 0; s < this.peak.length; s++) { const v = Math.abs(this.weight[s] * frame[this.pre[s]]); if (v > this.peak[s]) this.peak[s] = v; }
    }
    if (!this.gl) this.selectCandidates();
    this.rescale(tl.frames.slice(1));
    this.wake();
  }

  endSettle(final) {
    const tl = this.timeline;
    if (!tl) return;
    tl.complete = true; tl.final = final;
    const remaining = tl.frames.length - 1 - this.playhead;
    this.msPerSweep = this.reduced ? 1 : clamp(1050 / Math.max(1, remaining), 12, 120);
    this.wake();
  }

  finished() { return this.donePromise || Promise.resolve(); }

  show(activation) {
    this.timeline = null; this.playing = false;
    this.display.set(activation); this.change.fill(0);
    this.rescale([activation]);
    if (!this.gl) { for (let s = 0; s < this.peak.length; s++) this.peak[s] = Math.abs(this.weight[s] * activation[this.pre[s]]); this.selectCandidates(); }
    this.wake();
  }

  rest() { this.show(new Float32Array(this.n)); }

  flash(changed, delta, count = 0) {
    let max = 0;
    for (const d of delta) max = Math.max(max, Math.abs(d));
    this.flashes = { changed, delta, max: max || 1, start: performance.now(), count };
    this.wake();
  }

  wake() {
    if (this.running) return;
    this.running = true;
    this.last = null;
    requestAnimationFrame((t) => this.tick(t));
  }

  tick(now) {
    // a frame's timestamp can precede the call that woke the loop: never step backwards
    const interval = this.last === null ? 16 : Math.max(0, now - this.last);
    const dt = Math.min(64, interval);
    this.last = now;
    let progress = 0, busy = false;
    const tl = this.timeline;
    if (tl && this.playing) {
      const limit = tl.frames.length - 1;
      const speed = this.playhead < 1 ? 130 : this.msPerSweep;
      this.playhead = Math.min(limit, this.playhead + dt / speed);
      const i = Math.min(limit, Math.floor(this.playhead)), f = this.playhead - i;
      const a = tl.frames[i], b = tl.frames[Math.min(limit, i + 1)], e = ease(f);
      const real = i >= 1;
      for (let j = 0; j < this.n; j++) {
        this.display[j] = a[j] + (b[j] - a[j]) * e;
        this.change[j] = real ? Math.abs(b[j] - a[j]) : 0;
      }
      progress = f;
      if (this.playhead >= limit && tl.complete) {
        this.playing = false;
        this.change.fill(0);
        this.resolveDone?.();
      }
      busy = true;
      if (this.hover >= 0) this.renderTooltip();
      const sweep = Math.max(0, this.playhead - 1);
      this.onFrame?.({
        sweep, sweeps: tl.complete ? tl.final.sweeps : null, playing: this.playing,
        movement: tl.movement.slice(2, 2 + Math.floor(sweep + 1e-9)),
        motor: this.groups.motor.map((m) => this.display[m]),
      });
      // a GPU that cannot keep up with the curves hands over to the Canvas2D view
      if (this.gl && this.frames > 2) {
        this.slow = interval > 160 ? this.slow + 1 : 0;
        if (this.slow >= 3) { this.use2D('slow frames'); this.peak.fill(0); for (const fr of tl.frames) for (let s = 0; s < this.peak.length; s++) { const v = Math.abs(this.weight[s] * fr[this.pre[s]]); if (v > this.peak[s]) this.peak[s] = v; } this.selectCandidates(); }
      }
    }
    if (this.gl) this.drawGL(progress); else this.draw2D();
    this.frames++;
    const flashing = this.flashes && now - this.flashes.start < 3600;
    if (flashing || this.overlayDirty || busy) this.drawOverlay(now);
    if (!flashing && this.flashes) { this.flashes = null; this.drawOverlay(now); }
    if (busy || flashing) requestAnimationFrame((t) => this.tick(t));
    else this.running = false;
  }

  // -- the overlay: labels, the sensory boards, the hovered neuron, a lesson's changes

  drawOverlay(now = performance.now()) {
    const c = this.ctx, dpr = this.dpr;
    if (!this.regions) return;
    this.overlayDirty = false;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, this.width, this.height);
    this.silhouette(c);
    c.font = '600 10.5px Inter, system-ui, sans-serif';
    c.textBaseline = 'alphabetic';
    for (const r of this.regions) {
      let text = r.label.toUpperCase();
      // a label wider than its region loses its count, then its note
      const room = this.width - r.x - 8;
      if (c.measureText(text).width > room && r.short) text = r.short.toUpperCase();
      if (c.measureText(text).width > room) text = r.name.toUpperCase();
      const w = c.measureText(text).width;
      c.fillStyle = 'rgba(6,8,14,0.72)';
      c.beginPath(); c.roundRect(r.x - 4, r.y - 1, w + 8, 15, 4); c.fill();
      c.fillStyle = r.silent || r.faint ? 'rgba(150,160,190,0.62)' : 'rgba(190,200,228,0.9)';
      c.fillText(text, r.x, r.y + 10);
    }
    for (const b of this.boards || []) {
      c.strokeStyle = { own: 'rgba(63,224,207,0.3)', opp: 'rgba(255,159,74,0.3)', play: 'rgba(200,204,128,0.3)' }[b.side]; c.lineWidth = 1;
      c.beginPath(); c.roundRect(b.x - 3, b.y - 3, b.w + 6, b.h + 6, 5); c.stroke();
    }
    c.font = '600 10px Inter, system-ui, sans-serif'; c.textAlign = 'center';
    c.textAlign = 'right';
    this.groups.motor.forEach((i, col) => {
      c.fillStyle = col === this.chosen ? 'rgba(120,255,235,0.98)' : 'rgba(150,165,200,0.7)';
      c.fillText(String(col + 1), this.pos[2 * i] - this.size[i] - 6, this.pos[2 * i + 1] + 3.5);
    });
    c.textAlign = 'center';
    this.drawDeliberation(c);
    (this.groups.verdict || []).forEach((i, k) => {
      c.fillStyle = 'rgba(255,214,140,0.85)';
      c.fillText(VERDICT[k], this.pos[2 * i], this.pos[2 * i + 1] - this.size[i] - 7);
    });
    c.textAlign = 'left';
    if (this.flashes) {
      const age = (now - this.flashes.start) / 3600, fade = Math.pow(1 - clamp(age, 0, 1), 1.4);
      c.globalCompositeOperation = 'lighter';
      const { changed, delta, max } = this.flashes;
      for (let j = 0; j < Math.min(changed.length, 480); j++) {
        const k = changed[j], p = this.pre[k], q = this.post[k], r = Math.abs(delta[j]) / max;
        c.lineWidth = 0.6 + 2.4 * r;
        c.strokeStyle = delta[j] >= 0 ? `rgba(255,206,102,${(0.1 + 0.7 * r) * fade})` : `rgba(150,200,255,${(0.1 + 0.7 * r) * fade})`;
        c.beginPath(); c.moveTo(this.pos[2 * p], this.pos[2 * p + 1]);
        c.bezierCurveTo(this.ctrl[4 * k], this.ctrl[4 * k + 1], this.ctrl[4 * k + 2], this.ctrl[4 * k + 3], this.pos[2 * q], this.pos[2 * q + 1]);
        c.stroke();
      }
      c.globalCompositeOperation = 'source-over';
      if (this.flashes.count) {
        c.font = '600 11px Inter, system-ui, sans-serif';
        c.fillStyle = `rgba(255,214,140,${0.95 * fade})`;
        c.fillText(`lesson · ${this.flashes.count.toLocaleString()} synapses changed (strongest drawn: gold stronger, blue weaker)`, 12, this.height - 12);
      }
    }
    if (this.hover >= 0) this.drawHover(c);
  }

  drawHover(c) {
    const i = this.hover, x = this.pos[2 * i], y = this.pos[2 * i + 1];
    c.lineWidth = 1.4;
    for (const s of this.strongest(i, 12)) {
      const o = s.other;
      c.strokeStyle = s.value >= 0 ? 'rgba(110,220,255,0.85)' : 'rgba(200,140,255,0.85)';
      c.beginPath(); c.moveTo(this.pos[2 * o], this.pos[2 * o + 1]); c.lineTo(x, y); c.stroke();
      c.fillStyle = 'rgba(255,255,255,0.9)';
      c.beginPath(); c.arc(this.pos[2 * o], this.pos[2 * o + 1], 2.2, 0, Math.PI * 2); c.fill();
    }
    c.strokeStyle = 'rgba(255,255,255,0.95)'; c.lineWidth = 1.6;
    c.beginPath(); c.arc(x, y, Math.max(5, this.size[i] + 3), 0, Math.PI * 2); c.stroke();
  }

  // The synapses that matter most to neuron i now: inbound (outbound for the sensory and
  // silent populations, which hear nothing) by |weight x presynaptic activation|, or by |weight|.
  strongest(i, count) {
    const role = this.roles[i];
    const outward = SIDES.includes(role) || this.silent.has(role);
    const list = outward ? this.outbound : this.inbound;
    const items = [];
    for (let k = list.start[i]; k < list.start[i + 1]; k++) {
      const s = list.order[k], other = outward ? this.post[s] : this.pre[s];
      const value = this.weight[s] * (outward ? this.display[i] : this.display[other]);
      items.push({ s, other, weight: this.weight[s], value, rank: Math.abs(value) > 1e-6 ? Math.abs(value) : Math.abs(this.weight[s]) * 1e-3 });
    }
    items.sort((a, b) => b.rank - a.rank);
    return items.slice(0, count).map((it) => ({ ...it, outward }));
  }

  name(i) {
    const role = this.roles[i];
    if (SIDES.includes(role)) {
      const k = this.cell[i], at = `row ${Math.floor(k / COLUMNS) + 1}, column ${k % COLUMNS + 1}`;
      return role === 'play' ? `Sensory neuron · a stone would land at ${at}` : `Sensory neuron · ${role === 'own' ? 'its' : 'your'} stone at ${at}`;
    }
    if (role === 'motor') return `Motor neuron · column ${this.column[i] + 1}`;
    if (role === 'verdict') return `Verdict neuron · ${VERDICT[this.column[i] - COLUMNS]} for the side to move`;
    const group = this.groups[role] || [];
    return `${role[0].toUpperCase()}${role.slice(1)} neuron ${group.indexOf(i) + 1} of ${group.length}`;
  }

  shortName(i) {
    const role = this.roles[i];
    if (SIDES.includes(role)) { const k = this.cell[i]; return `${{ own: 'its stone', opp: 'your stone', play: 'playable' }[role]} r${Math.floor(k / COLUMNS) + 1} c${k % COLUMNS + 1}`; }
    if (role === 'motor') return `motor ${this.column[i] + 1}`;
    if (role === 'verdict') return `verdict ${VERDICT[this.column[i] - COLUMNS]}`;
    const group = this.groups[role] || [];
    return `${role.slice(0, 5)}. ${group.indexOf(i) + 1}`;
  }

  pointer(event, tap = false) {
    if (!this.pos) return;
    const box = this.canvas.getBoundingClientRect();
    const x = event.clientX - box.left, y = event.clientY - box.top;
    let best = -1, bestD = Infinity;
    for (let i = 0; i < this.n; i++) {
      const dx = this.pos[2 * i] - x, dy = this.pos[2 * i + 1] - y, d = dx * dx + dy * dy;
      const reach = Math.max(7, this.size[i] + 4);
      if (d < reach * reach && d < bestD) { best = i; bestD = d; }
    }
    if (tap) this.pinned = best >= 0;
    if (tap || !this.pinned) this.setHover(best);
  }

  setHover(i) {
    if (i === this.hover && i < 0) return;
    this.hover = i;
    this.overlayDirty = true;
    this.renderTooltip();
    if (!this.running) this.drawOverlay();
  }

  renderTooltip() {
    const tip = this.tooltip, i = this.hover;
    if (i < 0 || !this.pos) { tip.hidden = true; return; }
    const role = this.roles[i];
    const rows = this.strongest(i, 5);
    const outward = rows[0]?.outward;
    const lines = rows.map((r) => `<li><span>${this.shortName(r.other)}</span><b class="${r.value >= 0 ? 'pos' : 'neg'}">${r.value >= 0 ? '+' : '−'}${Math.abs(r.value).toFixed(3)}</b><i>w ${r.weight.toFixed(3)}</i></li>`).join('');
    const list = outward ? this.outbound : this.inbound;
    const count = list.start[i + 1] - list.start[i];
    let note = '';
    if (this.silent.has(role)) note = '<p class="note">Cadence’s working trace drives this region. This brain settles without memory (a Connect Four position is fully observed), so the region stays at rest and its synapses carry nothing. Drawn: its strongest synapses.</p>';
    if (role === 'motor') note = `<p class="note">Drives column ${this.column[i] + 1}. The strongest motor neuron whose column has room is the move.</p>`;
    if (role === 'verdict') note = '<p class="note">The brain’s judgement of the position for the side to move, taught beside the move from the perfect solver’s result. The move does not read it.</p>';
    const region = (this.regions || []).find((r) => r.name === (SIDES.includes(role) ? 'sensory' : role));
    if (region && region.role) note += `<p class="note">${region.role}</p>`;
    tip.innerHTML = `<h4>${this.name(i)}</h4><p class="act">activation <b>${this.display[i].toFixed(3)}</b> · bias ${Number(this.bias[i]).toFixed(3)}</p>`
      + `<p class="sub">${outward ? 'strongest outputs now' : 'strongest inputs now'} <span>(of ${count.toLocaleString()} drawn)</span></p><ul>${lines}</ul>${note}`;
    tip.hidden = false;
    const x = this.pos[2 * i], y = this.pos[2 * i + 1];
    const w = tip.offsetWidth || 240, h = tip.offsetHeight || 140;
    let left = x + 14, topY = y - h - 10;
    if (left + w > this.width - 6) left = x - w - 14;
    if (left < 6) left = 6;
    if (topY < 6) topY = y + 14;
    if (topY + h > this.height - 6) topY = Math.max(6, this.height - h - 6);
    tip.style.left = `${left}px`; tip.style.top = `${topY}px`;
  }

  setChosen(column) { this.chosen = column; this.overlayDirty = true; this.wake(); }

  // The deliberation after a settle: the verdict neurons' judgement, and what the search (a
  // look-ahead over the rules, not neurons) did with the column neurons' proposal.
  setDeliberation(final) { this.deliberation = final || null; this.overlayDirty = true; this.wake(); }

  drawDeliberation(c) {
    const d = this.deliberation, b = this.brainBox;
    if (!d || !b) return;
    const x0 = b.x + b.w * 0.02, y0 = b.y + b.h * 0.86, w = Math.min(210, b.w * 0.3);
    c.save();
    c.textAlign = 'left';
    c.font = '600 10px Inter, system-ui, sans-serif';
    if (d.verdict) {
      const [loss, draw, win] = d.verdict;
      c.fillStyle = 'rgba(255,214,140,0.9)';
      c.fillText(`verdict  win ${Math.round(100 * win)}% · draw ${Math.round(100 * draw)}% · loss ${Math.round(100 * loss)}%`, x0, y0);
    }
    const s = d.search;
    if (s && s.values) {
      const top = y0 + 8, h = 26, bw = w / 7;
      // values short of a proven result are scaled to the largest of them
      const soft = Object.values(s.values).filter((v) => Math.abs(v) < 950).map(Math.abs);
      const scale = Math.max(1e-3, ...soft);
      c.fillStyle = 'rgba(190,200,228,0.75)';
      c.fillText(s.immediate ? 'search (rules, not neurons): a win now' : `search (rules, not neurons): ${s.depth} moves ahead · ${(s.nodes || 0).toLocaleString()} positions`, x0, top + h + 14);
      for (let col = 0; col < 7; col++) {
        const v = s.values[col];
        if (v === undefined) continue;
        if (s.immediate && v < 950) continue; // a win now: the other columns were not searched
        const proven = Math.abs(v) >= 950, val = proven ? Math.sign(v) : Math.max(-1, Math.min(1, v / scale)) * 0.8;
        const hgt = Math.abs(val) * h / 2, mid = top + h / 2;
        c.fillStyle = proven ? (val > 0 ? 'rgba(120,255,200,0.9)' : 'rgba(255,110,120,0.85)') : (val >= 0 ? 'rgba(255,170,90,0.75)' : 'rgba(110,160,255,0.75)');
        c.fillRect(x0 + col * bw + 2, val >= 0 ? mid - hgt : mid, bw - 4, Math.max(1, hgt));
        if (col === d.column) { c.strokeStyle = 'rgba(120,255,235,0.95)'; c.lineWidth = 1.2; c.strokeRect(x0 + col * bw + 1, top - 1, bw - 2, h + 2); }
        if (col === d.brain_column && d.brain_column !== d.column) { c.setLineDash([2, 2]); c.strokeStyle = 'rgba(255,214,140,0.9)'; c.strokeRect(x0 + col * bw + 1, top - 1, bw - 2, h + 2); c.setLineDash([]); }
      }
      c.strokeStyle = 'rgba(150,165,210,0.25)'; c.beginPath(); c.moveTo(x0, top + h / 2); c.lineTo(x0 + w, top + h / 2); c.stroke();
      // an overruled proposal: a line from the brain's column neuron to the played one
      if (d.brain_column !== d.column && this.groups.motor[d.brain_column] !== undefined) {
        const a = this.groups.motor[d.brain_column], z = this.groups.motor[d.column];
        c.strokeStyle = 'rgba(255,214,140,0.85)'; c.lineWidth = 1.5; c.setLineDash([4, 3]);
        c.beginPath(); c.moveTo(this.pos[2 * a] - 10, this.pos[2 * a + 1]);
        c.quadraticCurveTo(this.pos[2 * a] - 40, (this.pos[2 * a + 1] + this.pos[2 * z + 1]) / 2, this.pos[2 * z] - 10, this.pos[2 * z + 1]);
        c.stroke(); c.setLineDash([]);
      }
    }
    c.restore();
  }

  // For the page check: draw now and read the pixels back (a fresh frame, so no preserved buffer).
  sample() {
    if (this.gl) this.drawGL(0); else this.draw2D();
    const w = this.canvas.width, h = this.canvas.height;
    let pixels;
    if (this.gl) { pixels = new Uint8Array(w * h * 4); this.gl.readPixels(0, 0, w, h, this.gl.RGBA, this.gl.UNSIGNED_BYTE, pixels); }
    else pixels = this.ctx2.getImageData(0, 0, w, h).data;
    let sum = 0, lit = 0, hashValue = 0;
    for (let k = 0; k < pixels.length; k += 16) {
      const v = pixels[k] + pixels[k + 1] + pixels[k + 2];
      sum += v; if (v > 120) lit++;
      hashValue = (hashValue * 31 + v) >>> 0;
    }
    const count = pixels.length / 16;
    return { mean: sum / count / 3, litShare: lit / count, hash: hashValue };
  }

  stats() {
    let lit = 0;
    for (let i = 0; i < (this.n || 0); i++) if (this.display[i] > 0.05) lit++;
    return { mode: this.mode, hdr: !!this.hdr, fallback: this.fallback || null, frames: this.frames, lit, playhead: this.playhead,
      playing: !!this.playing, synapses: (this.gl ? this.synapseCount : this.candidates?.length) ?? 0 };
  }
}
