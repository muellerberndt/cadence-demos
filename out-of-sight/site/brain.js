// The whole brain, drawn from the running brain's own numbers.
//
// Every neuron is a point in the region whose role its population plays (the page names the
// role; it claims nothing about what the neurons are). A synapse glows with the message it
// carries, |weight x presynaptic activation|; while a sweep changes a presynaptic neuron, a
// pulse runs along its synapses. A lesson's changed synapses flash, gold where they grew and
// blue where they shrank. The records beside the brain are drawn as cells of a hippocampus: a
// cell lights when its record is read or written, with a thumbnail of the place it holds.
// Every part (a region, the records, a tract) has a box and a button over it: pointing at it,
// tapping it or tabbing to it opens the card that explains it (cards.js).
// Nothing is invented: the activations are the settle's own, sweep by sweep, and the weights
// are the brain's own. WebGL2 draws it on a GPU; on a software renderer, or if frames get slow,
// a Canvas2D view draws the neurons and the strongest messages instead.

export const COLOR = {
  visual: [0.4, 0.74, 1.0],
  somatosensory: [0.78, 0.8, 0.5],
  motor: [1.0, 0.68, 0.33],
  association: [0.56, 0.62, 1.0],
  prefrontal: [0.66, 0.56, 0.98],
  place: [0.24, 0.89, 0.82],
  auditory: [0.95, 0.55, 0.78],
  hippocampus: [1.0, 0.8, 0.42],
  other: [0.72, 0.72, 0.82],
  excite: [1.0, 0.62, 0.28],
  inhibit: [0.32, 0.58, 1.0],
  pulse: [1.0, 0.95, 0.86],
};
export const ROLE = {
  visual: 'plays the role of the visual cortex',
  somatosensory: 'plays the role of the somatosensory strip, the sense of the body’s own posture',
  motor: 'plays the role of the motor strip and the copy of its commands',
  association: 'plays the role of association cortex',
  prefrontal: 'plays the role of prefrontal working memory',
  place: 'plays the role of the parietal and entorhinal map',
  auditory: 'plays the role of the auditory cortex',
  hippocampus: 'plays the role of the hippocampus',
};
const ANATOMY = { visual: 'visual cortex', somatosensory: 'somatosensory', motor: 'motor strip', association: 'association cortex',
  prefrontal: 'prefrontal cortex', place: 'parietal · entorhinal map', auditory: 'auditory cortex', hippocampus: 'hippocampus' };
const css = (rgb, a = 1) => `rgba(${rgb.map((v) => Math.round(v * 255)).join(',')},${a})`;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const ease = (f) => f * f * (3 - 2 * f);
const LEVEL_FLOOR = 0.08; // a population this quiet is drawn at its true, dim level
const FLASH_MS = 900;

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
uniform vec2 texel;
void main() {
  vec3 x = texture(light, uv).rgb * exposure;
  // bloom: the same light, gathered from a ring around the pixel, adds a soft glow to bright tracts
  vec3 b = vec3(0.0);
  for (int k = 0; k < 12; k++) {
    float a = 6.2831853 * float(k) / 12.0;
    vec2 d = vec2(cos(a), sin(a)) * texel;
    b += texture(light, uv + d * 3.0).rgb + 0.6 * texture(light, uv + d * 7.0).rgb;
  }
  x += b * exposure * 0.035;
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
// A stable pseudo-random number per synapse, for its place in the bundle only.
const hash = (k) => { let x = (k + 0x9e3779b9) | 0; x = Math.imul(x ^ (x >>> 16), 0x85ebca6b); x = Math.imul(x ^ (x >>> 13), 0xc2b2ae35); return ((x ^ (x >>> 16)) >>> 0) / 4294967296; };

export class BrainView {
  constructor({ canvas, overlay, parts, renderer = 'auto' }) {
    this.canvas = canvas; this.overlay = overlay; this.partsRoot = parts;
    this.stage = canvas.parentElement;
    this.ctx = overlay.getContext('2d');
    this.gl = null;
    if (renderer !== '2d') {
      try {
        // A software renderer would stall the page on tens of thousands of curves: ask for a
        // context without a major performance caveat unless WebGL is forced.
        this.gl = canvas.getContext('webgl2', { antialias: true, premultipliedAlpha: true, alpha: false,
          failIfMajorPerformanceCaveat: renderer !== 'webgl' });
        if (this.gl) this.initGL();
      } catch (error) { console.warn('WebGL2 unavailable; drawing with Canvas2D.', error); this.gl = null; }
    }
    if (!this.gl) this.use2D(renderer === '2d' ? 'requested' : 'no fast WebGL2');
    this.frames = 0;
    this.flashes = [];
    this.wave = null;
    this.slow = 0;
    this.learning = 0; // the time of the latest lesson that changed synapses
    this.cells = [];
    this.parts = [];       // what explains itself: regions, the records and the tracts
    this.spot = new Set(); // the parts a card or the tutorial points at
    this.onPart = null;    // (id, 'enter' | 'leave' | 'tap', event) from the pointer or the keyboard
    this.reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    new ResizeObserver(() => this.resize()).observe(this.stage);
    // a tract has no box of its own: the pointer is tested against its curve
    this.stage.addEventListener('pointermove', (e) => this.overTract(e));
    this.stage.addEventListener('pointerleave', () => this.overTract(null));
    this.stage.addEventListener('pointerdown', (e) => { if (e.target === this.stage || e.target === this.partsRoot) this.overTract(e, true); });
  }

  // Draw with Canvas2D from here on, on a fresh canvas when the old one holds a WebGL context.
  use2D(reason) {
    if (this.gl) {
      const fresh = document.createElement('canvas');
      fresh.id = this.canvas.id; fresh.setAttribute('aria-hidden', 'true');
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
    this.regionOf = new Int16Array(n).fill(-1);
    this.regions = brain.regions.map((r, k) => { for (const i of r.neurons) this.regionOf[i] = k; return { ...r, index: k }; });
    this.unit = new Array(n).fill(null); // what a tuned unit prefers: { reading, value }
    for (const r of this.regions) {
      if (r.layout?.kind !== 'axes') continue;
      const { per, ranges } = r.layout;
      r.neurons.forEach((i, k) => {
        const reading = Math.floor(k / per), j = k % per, [lo, hi] = ranges[reading];
        this.unit[i] = { reading, value: lo + ((hi - lo) * j) / (per - 1), index: j };
      });
    }
    this.records = brain.records || null;
    this.cells = Array.from({ length: this.records?.capacity || 0 }, () => ({ lit: 0, write: 0, record: null }));
    this.inbound = this.lists(this.post, n);
    this.outbound = this.lists(this.pre, n);
    // per synapse: its block (a pair of regions) and how bright a typical message of it glows
    const m = this.pre.length;
    this.blockOf = new Uint8Array(m);
    this.blockNames = [];
    const index = new Map(), sums = [], counts = [];
    for (let k = 0; k < m; k++) {
      const key = `${this.regionOf[this.pre[k]]}>${this.regionOf[this.post[k]]}`;
      if (!index.has(key)) { index.set(key, this.blockNames.length); this.blockNames.push(key); sums.push(0); counts.push(0); }
      const b = index.get(key);
      this.blockOf[k] = b; sums[b] += Math.abs(this.weight[k]); counts[b]++;
    }
    this.blockScale = sums.map((s, b) => (counts[b] ? s / counts[b] : 1));
    this.blockCount = counts;
    this.blockSynapses = counts.map((count) => new Int32Array(count));
    const fill = counts.map(() => 0);
    for (let k = 0; k < m; k++) { const b = this.blockOf[k]; this.blockSynapses[b][fill[b]++] = k; }
    this.levelScale = new Float32Array(this.regions.length + 1).fill(LEVEL_FLOOR);
    this.display = new Float32Array(n);
    this.target = new Float32Array(n);
    this.change = new Float32Array(n);
    this.peak = new Float32Array(m);
    this.candidates = new Int32Array(0);
    this.sortFields();
    this.layout();
  }

  lists(index, n) {
    const counts = new Int32Array(n + 1);
    for (let k = 0; k < index.length; k++) counts[index[k] + 1]++;
    for (let i = 0; i < n; i++) counts[i + 1] += counts[i];
    const order = new Int32Array(index.length), fill = counts.slice(0, n);
    for (let k = 0; k < index.length; k++) order[fill[index[k]]++] = k;
    return { start: counts, order };
  }

  // A field's neurons are placed by the place they drive: left to right by the x their
  // strongest synapses onto the place units name, bottom to top by the y. Read once from the
  // loaded weights; a working trace takes its association field's places (unit k follows unit k).
  sortFields() {
    const place = this.regions.find((r) => r.role === 'place');
    this.fieldPlace = new Map();
    if (!place) return;
    for (const r of this.regions) {
      if (r.layout?.kind !== 'field') continue;
      const at = new Map(r.neurons.map((i, k) => [i, k]));
      const N = r.neurons.length;
      const sx = new Float64Array(N), wx = new Float64Array(N), sy = new Float64Array(N), wy = new Float64Array(N);
      for (let k = 0; k < this.pre.length; k++) {
        const p = this.pre[k], q = this.post[k], w = this.weight[k];
        const u = this.unit[q];
        if (w <= 0 || !u || this.regionOf[q] !== place.index || !at.has(p)) continue;
        const j = at.get(p);
        if (u.reading === 0) { sx[j] += w * u.index; wx[j] += w; } else { sy[j] += w * u.index; wy[j] += w; }
      }
      const any = wx.some((v) => v > 0);
      this.fieldPlace.set(r.name, r.neurons.map((i, j) => ({ i, x: any && wx[j] > 0 ? sx[j] / wx[j] : j % 12, y: any && wy[j] > 0 ? sy[j] / wy[j] : Math.floor(j / 12) })));
    }
    const assoc = this.fieldPlace.get('association'), trace = this.regions.find((r) => r.role === 'prefrontal');
    if (assoc && trace && trace.neurons.length === assoc.length) {
      this.fieldPlace.set(trace.name, trace.neurons.map((i, j) => ({ i, x: assoc[j].x, y: assoc[j].y })));
    }
  }

  setWeights(weight) {
    this.weight = Float32Array.from(weight);
    if (this.gl) this.uploadSynapses();
  }

  // -- layout in CSS pixels

  resize() {
    const box = this.stage.getBoundingClientRect();
    const w = Math.max(240, Math.round(box.width)), h = Math.max(200, Math.round(box.height));
    this.dpr = Math.min(2, window.devicePixelRatio || 1);
    for (const c of [this.canvas, this.overlay]) {
      c.width = Math.round(w * this.dpr); c.height = Math.round(h * this.dpr);
      c.style.width = `${w}px`; c.style.height = `${h}px`;
    }
    this.width = w; this.height = h;
    if (this.brain) this.layout();
  }

  // The brain seen from the side, front to the left: each population sits in the region whose
  // role it plays.
  layout() {
    if (!this.width) { this.resize(); return; }
    const W = this.width, H = this.height, n = this.n;
    const pos = this.pos = new Float32Array(2 * n);
    const size = this.size = new Float32Array(n);
    const hue = this.hue = new Float32Array(3 * n);
    this.labels = []; this.labelsPlaced = false;
    this.glows = [];
    const pad = Math.max(10, Math.round(W * 0.02));
    const bw = Math.min(W - 2 * pad, (H - 2 * pad - 14) * 1.45), bh = bw / 1.45;
    const bx = (W - bw) / 2, by = (H - bh) / 2 + 4;
    const at = (u, v) => [bx + u * bw, by + v * bh];
    this.brainBox = { x: bx, y: by, w: bw, h: bh };
    const unitR = clamp(bw * 0.0085, 2.2, 7);

    const ellipse = (members, cx, cy, rx, ry) => {
      // a hexagonal grid clipped to the ellipse, with at least as many places as members
      const N = members.length;
      if (!N) return null;
      const [X, Y] = at(cx, cy), RX = rx * bw, RY = ry * bh;
      let step = Math.sqrt((Math.PI * RX * RY) / (N * 0.866)) * 1.02, places = [];
      for (let tries = 0; tries < 14; tries++) {
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
    // tuned units along a line from (u0, v0) to (u1, v1), bowed by `bow` of the box's width
    const line = (ids, u0, v0, u1, v1, bow = 0, r = unitR) => {
      ids.forEach((i, k) => {
        const t = ids.length > 1 ? k / (ids.length - 1) : 0.5;
        const [x, y] = at(u0 + (u1 - u0) * t + bow * Math.sin(Math.PI * t), v0 + (v1 - v0) * t);
        pos[2 * i] = x; pos[2 * i + 1] = y; size[i] = r;
      });
    };
    const label = (region, u, v, align = 'left') => {
      const [x, y] = at(u, v);
      this.labels.push({ region, x, y, align });
    };
    const glow = (region, u, v, ru, rv) => {
      const [x, y] = at(u, v);
      this.glows.push({ region: region.index, x, y, rx: ru * bw, ry: rv * bh, hue: COLOR[region.role] || COLOR.other });
    };
    const seen = { visual: 0, somatosensory: 0, motor: 0, place: 0, association: 0, prefrontal: 0, other: 0 };
    for (const r of this.regions) {
      const kind = r.layout?.kind, per = r.layout?.per || r.neurons.length;
      const rows = kind === 'axes' ? Math.round(r.neurons.length / per) : 1;
      const row = (k) => r.neurons.slice(k * per, (k + 1) * per);
      const nth = seen[r.role in seen ? r.role : 'other']++;
      if (r.role === 'visual' && kind === 'axes') {
        // the camera's report at the back of the brain: x units across, y units up
        line(row(0), 0.795, 0.49, 0.935, 0.49);
        if (rows > 1) line(row(1), 0.865, 0.68, 0.865, 0.30);
        glow(r, 0.865, 0.49, 0.09, 0.22); label(r, 0.80, 0.215);
      } else if (r.role === 'visual') {
        line(r.neurons, 0.935, 0.32 + 0.05 * nth, 0.935, 0.32 + 0.05 * nth, 0, unitR * 1.5);
      } else if (r.role === 'somatosensory') {
        // the joint readings behind the central sulcus, one arc a joint
        for (let k = 0; k < rows; k++) line(row(k), 0.425 + 0.03 * k, 0.60, 0.455 + 0.03 * k, 0.085, 0.035);
        glow(r, 0.47, 0.34, 0.05, 0.27); label(r, 0.405, 0.03);
      } else if (r.role === 'motor') {
        // the arm's commands in front of the central sulcus, one arc a joint
        for (let k = 0; k < rows; k++) line(row(k), 0.305 + 0.03 * k, 0.60, 0.335 + 0.03 * k, 0.085, 0.035);
        glow(r, 0.35, 0.34, 0.05, 0.27); label(r, 0.215, 0.03);
      } else if (r.role === 'place' && kind === 'axes') {
        // the place answer over the parietal region: x units across, y units up, as a map's axes
        line(row(0), 0.585, 0.335, 0.745, 0.335);
        if (rows > 1) line(row(1), 0.565, 0.31, 0.565, 0.085);
        this.placeBox = { region: r.index, x0: at(0.585, 0)[0], x1: at(0.745, 0)[0], y0: at(0, 0.31)[1], y1: at(0, 0.085)[1] };
        glow(r, 0.655, 0.21, 0.11, 0.16); label(r, 0.61, 0.03);
      } else if (r.role === 'place' && kind === 'grid') {
        const { width: gw, height: gh } = r.layout;
        r.neurons.forEach((i, k) => {
          const [x, y] = at(0.585 + 0.16 * ((k % gw) + 0.5) / gw, 0.31 - 0.225 * (Math.floor(k / gw) + 0.5) / gh);
          pos[2 * i] = x; pos[2 * i + 1] = y; size[i] = clamp((0.16 * bw) / gw * 0.36, 1.1, unitR);
        });
        this.placeBox = null;
        glow(r, 0.665, 0.2, 0.1, 0.15); label(r, 0.61, 0.03);
      } else if (r.role === 'association') {
        const f = ellipse(this.fieldPlace.get(r.name) || r.neurons.map((i, k) => ({ i, x: k % 12, y: Math.floor(k / 12) })), 0.655, 0.575, 0.085, 0.155);
        if (f) { this.glows.push({ region: r.index, ...f, hue: COLOR.association }); label(r, 0.75, 0.70); }
      } else if (r.role === 'prefrontal') {
        const f = ellipse(this.fieldPlace.get(r.name) || r.neurons.map((i, k) => ({ i, x: k % 12, y: Math.floor(k / 12) })), 0.165, 0.43, 0.1, 0.22);
        if (f) { this.glows.push({ region: r.index, ...f, hue: COLOR.prefrontal }); label(r, 0.075, 0.175); }
      } else {
        const f = ellipse(r.neurons.map((i, k) => ({ i, x: k % 10, y: Math.floor(k / 10) })), 0.80 + 0.06 * nth, 0.74, 0.05, 0.05);
        if (f) label(r, 0.76 + 0.06 * nth, 0.80);
      }
    }
    for (let i = 0; i < n; i++) hue.set(COLOR[this.regions[this.regionOf[i]]?.role] || COLOR.other, 3 * i);
    // the hippocampus: one cell a record slot, along an arc in the temporal lobe
    const count = this.cells.length;
    this.cells.forEach((cell, k) => {
      const t = count > 1 ? k / (count - 1) : 0.5;
      const [x, y] = at(0.27 + 0.30 * t, 0.735 + 0.035 * Math.sin(Math.PI * t) - 0.02 * t);
      cell.x = x; cell.y = y; cell.r = clamp(bw * 0.011, 3.2, 8);
    });
    if (count) { const [x, y] = at(0.30, 0.86); this.cellLabel = { x, y }; }
    this.tracts();
    this.placeParts();
    if (this.gl) { this.uploadLayout(); this.uploadSynapses(); }
  }

  // The centre of each region, and the bundled path every synapse takes between two regions: a
  // tract from one region to the other, curving to one side so that the reciprocal tract runs
  // beside it; a synapse leaves its neuron, joins the tract and leaves it at its target.
  tracts() {
    const sum = new Map();
    for (let i = 0; i < this.n; i++) {
      const r = this.regionOf[i];
      const s = sum.get(r) || [0, 0, 0];
      s[0] += this.pos[2 * i]; s[1] += this.pos[2 * i + 1]; s[2]++; sum.set(r, s);
    }
    this.centroid = new Map([...sum].map(([r, s]) => [r, [s[0] / s[2], s[1] / s[2]]]));
    this.bundle = new Map(); // block -> the curve its tract follows: [A, M, B]
    const m = this.pre.length, ctrl = this.ctrl = new Float32Array(4 * m);
    for (let k = 0; k < m; k++) {
      const p = this.pre[k], q = this.post[k];
      const ra = this.regionOf[p], rb = this.regionOf[q];
      const A = this.centroid.get(ra), B = this.centroid.get(rb);
      const P0 = [this.pos[2 * p], this.pos[2 * p + 1]], P3 = [this.pos[2 * q], this.pos[2 * q + 1]];
      if (ra === rb || !A || !B) {
        ctrl[4 * k] = P0[0] + (P3[0] - P0[0]) / 3; ctrl[4 * k + 1] = P0[1] + (P3[1] - P0[1]) / 3;
        ctrl[4 * k + 2] = P0[0] + 2 * (P3[0] - P0[0]) / 3; ctrl[4 * k + 3] = P0[1] + 2 * (P3[1] - P0[1]) / 3;
        continue;
      }
      const dx = B[0] - A[0], dy = B[1] - A[1], len = Math.hypot(dx, dy) || 1;
      const side = ra < rb ? 1 : -1;
      const nx = -dy / len, ny = dx / len, bulge = 0.16 * len * side;
      const M = [(A[0] + B[0]) / 2 + nx * bulge, (A[1] + B[1]) / 2 + ny * bulge];
      if (!this.bundle.has(this.blockOf[k])) this.bundle.set(this.blockOf[k], [A, M, B]);
      const bez = (t) => [(1 - t) * (1 - t) * A[0] + 2 * (1 - t) * t * M[0] + t * t * B[0], (1 - t) * (1 - t) * A[1] + 2 * (1 - t) * t * M[1] + t * t * B[1]];
      const T1 = bez(0.3), T2 = bez(0.7);
      const j = (hash(k) - 0.5) * Math.min(30, len * 0.11), jx = nx * j, jy = ny * j; // its place across the bundle
      ctrl[4 * k] = P0[0] + (T1[0] - P0[0]) * 0.85 + jx; ctrl[4 * k + 1] = P0[1] + (T1[1] - P0[1]) * 0.85 + jy;
      ctrl[4 * k + 2] = P3[0] + (T2[0] - P3[0]) * 0.85 + jx; ctrl[4 * k + 3] = P3[1] + (T2[1] - P3[1]) * 0.85 + jy;
    }
  }

  // The largest activation of each region in these frames sets its brightness scale, so a quiet
  // region shows its pattern; a part's card reads the raw activation.
  rescale(frames) {
    const scale = this.levelScale;
    const next = new Float32Array(scale.length).fill(LEVEL_FLOOR);
    for (const frame of frames) {
      for (let i = 0; i < this.n; i++) {
        const r = this.regionOf[i] < 0 ? scale.length - 1 : this.regionOf[i];
        if (frame[i] > next[r]) next[r] = frame[i];
      }
    }
    for (let r = 0; r < scale.length; r++) scale[r] = Math.max(next[r], scale[r] * 0.97); // eases down, jumps up
  }

  // -- the brain's state

  /** The latest settled state. It is shown as it is, after any wave that is playing. */
  update(activation) {
    if (!this.brain) return;
    this.target.set(activation);
    this.rescale([activation]);
    if (!this.gl) this.pick(activation);
  }

  /** Play a moment's settle sweep by sweep (the worker's exact replay). */
  playWave(frames, count, sweeps, of) {
    if (!this.brain || !count || this.reduced) return false;
    if (this.wave) return false; // one wave at a time: a newer settle waits for the next one
    const n = this.n, list = [];
    for (let k = 0; k < count; k++) list.push(frames.subarray(k * n, (k + 1) * n));
    this.rescale(list);
    this.wave = { frames: [Float32Array.from(this.display), ...list], sweeps: [0, ...sweeps], of, head: 0 };
    return true;
  }

  flash(index, delta, count) {
    let max = 0;
    for (const d of delta) max = Math.max(max, Math.abs(d));
    this.flashes.push({ index, delta, max: max || 1, start: performance.now(), count });
    if (this.flashes.length > 3) this.flashes.shift();
    this.learning = performance.now();
  }

  /** The records as the brain holds them: per thing its slot, its place and how it came. */
  setRecords(things, now = performance.now()) {
    for (const t of things || []) {
      if (t.slot === undefined || t.slot < 0 || !this.cells[t.slot]) continue;
      const cell = this.cells[t.slot];
      cell.record = t;
      if (t.write) cell.write = now; else cell.lit = now;
    }
  }

  sweepInfo() { return this.wave ? { sweep: this.wave.sweeps[Math.min(this.wave.sweeps.length - 1, Math.floor(this.wave.head) + 1)], of: this.wave.of } : null; }

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
    for (const p of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_2D, p, gl.LINEAR);
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
    // a wide fan of synapses glows fainter per synapse than a narrow one
    const gains = this.blockNames.map((name, b) => {
      const fan = clamp(Math.sqrt(1600 / Math.max(64, this.blockCount[b])), 0.3, 1.6);
      return (0.5 / (this.blockScale[b] * 0.6 || 1)) * fan * clamp(this.width / 640, 0.6, 1.2) * 0.032;
    });
    for (let k = 0; k < m; k++) {
      const p = this.pre[k], q = this.post[k], b = this.blockOf[k];
      ends[4 * k] = this.pos[2 * p]; ends[4 * k + 1] = this.pos[2 * p + 1]; ends[4 * k + 2] = this.pos[2 * q]; ends[4 * k + 3] = this.pos[2 * q + 1];
      info[4 * k] = this.weight[k]; info[4 * k + 1] = p; info[4 * k + 2] = 0; info[4 * k + 3] = gains[b];
    }
    gl.bindVertexArray(this.synapseVAO);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers.t); gl.bufferData(gl.ARRAY_BUFFER, t, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 1, gl.FLOAT, false, 0, 0); gl.vertexAttribDivisor(0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers.ends); gl.bufferData(gl.ARRAY_BUFFER, ends, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1, 4, gl.FLOAT, false, 0, 0); gl.vertexAttribDivisor(1, 1);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers.info); gl.bufferData(gl.ARRAY_BUFFER, info, gl.DYNAMIC_DRAW);
    gl.enableVertexAttribArray(2); gl.vertexAttribPointer(2, 4, gl.FLOAT, false, 0, 0); gl.vertexAttribDivisor(2, 1);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers.ctrl); gl.bufferData(gl.ARRAY_BUFFER, this.ctrl, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(3); gl.vertexAttribPointer(3, 4, gl.FLOAT, false, 0, 0); gl.vertexAttribDivisor(3, 1);
    gl.bindVertexArray(null);
    this.synapseCount = m;
  }

  drawGL(progress) {
    const gl = this.gl, s = this.stateData, n = this.n, last = this.levelScale.length - 1;
    for (let i = 0; i < n; i++) {
      const scale = this.levelScale[this.regionOf[i] < 0 ? last : this.regionOf[i]];
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
    gl.uniform1f(sp.u.pulseGain, this.reduced || !this.wave ? 0 : 9); // pulses run while a settle plays
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
      gl.uniform1i(cp.u.light, 1); gl.uniform1f(cp.u.exposure, 1.0);
      gl.uniform2f(cp.u.texel, 1 / this.canvas.width, 1 / this.canvas.height);
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

  // -- Canvas2D: the neurons and the strongest messages of the state

  pick(activation, limit = 1800) {
    const m = this.peak.length;
    for (let s = 0; s < m; s++) this.peak[s] = Math.abs(this.weight[s] * activation[this.pre[s]]);
    if (m <= limit) { this.candidates = Int32Array.from({ length: m }, (_, k) => k); this.peakMax = Math.max(1e-6, ...this.peak); return; }
    const sorted = Float32Array.from(this.peak).sort();
    const threshold = Math.max(1e-6, sorted[m - limit]);
    const out = [];
    for (let k = 0; k < m && out.length < limit; k++) if (this.peak[k] >= threshold) out.push(k);
    this.candidates = Int32Array.from(out);
    this.peakMax = sorted[m - 1] || 1;
  }

  draw2D() {
    const c = this.ctx2, n = this.n, dpr = this.dpr, last = this.levelScale.length - 1;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.fillStyle = '#07090f'; c.fillRect(0, 0, this.width, this.height);
    const levels = 6, paths = [[], []];
    for (let b = 0; b < levels; b++) { paths[0].push(new Path2D()); paths[1].push(new Path2D()); }
    const scale = this.peakMax || 1;
    for (const k of this.candidates) {
      const v = this.weight[k] * this.display[this.pre[k]];
      if (Math.abs(v) < scale * 0.03) continue;
      const level = Math.min(levels - 1, Math.floor(levels * Math.abs(v) / scale));
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
      const r = this.regionOf[i];
      const level = clamp(this.display[i] / this.levelScale[r < 0 ? last : r], -0.2, 1), h = COLOR[this.regions[r]?.role] || COLOR.other;
      const lit = clamp(level / 0.75, 0, 1);
      c.fillStyle = css(h.map((v) => 0.035 + v * (0.2 + 0.8 * lit)), 1);
      const rad = this.size[i] * (1 + 0.2 * lit);
      if (rad < 2.2) c.fillRect(this.pos[2 * i] - rad, this.pos[2 * i + 1] - rad, 2 * rad, 2 * rad);
      else { c.beginPath(); c.arc(this.pos[2 * i], this.pos[2 * i + 1], rad, 0, Math.PI * 2); c.fill(); }
    }
  }

  // -- one frame

  frame(now, interval) {
    if (!this.brain || !this.width) return;
    const dt = Math.min(64, interval);
    let progress = 0;
    const w = this.wave;
    if (w) {
      // one recorded sweep every 45 ms, eased from one to the next
      const limit = w.frames.length - 1;
      w.head = Math.min(limit, w.head + dt / 45);
      const i = Math.min(limit, Math.floor(w.head)), f = w.head - i;
      const a = w.frames[i], b = w.frames[Math.min(limit, i + 1)], e = ease(f);
      for (let j = 0; j < this.n; j++) { this.display[j] = a[j] + (b[j] - a[j]) * e; this.change[j] = Math.abs(b[j] - a[j]); }
      progress = f;
      if (w.head >= limit) this.wave = null;
    } else {
      const k = this.reduced ? 1 : 1 - Math.exp(-dt / 70);
      for (let j = 0; j < this.n; j++) {
        const d = this.target[j] - this.display[j];
        this.display[j] += d * k; this.change[j] = Math.abs(d) * 0.2;
      }
      progress = (now % 700) / 700;
    }
    if (this.gl) {
      this.drawGL(progress);
      // a GPU that cannot keep up with the curves hands over to the Canvas2D view
      if (this.frames > 30) { this.slow = interval > 160 ? this.slow + 1 : 0; if (this.slow >= 5) { this.use2D('slow frames'); this.pick(this.target); } }
    } else this.draw2D();
    this.frames++;
    this.drawOverlay(now);
  }

  // -- the overlay: the outline, the labels, the records, a lesson's changes, the parts pointed at

  // The outline of a brain seen from the side (front to the left). It glows gold for the half
  // second after a lesson that changed synapses: the learning state, on.
  silhouette(c, learning = 0) {
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
    curve([[0.06, 0.52], [0.02, 0.36], [0.08, 0.16], [0.24, 0.04], [0.46, 0.0], [0.68, 0.03], [0.86, 0.14], [0.97, 0.34],
      [0.98, 0.56], [0.93, 0.72], [0.80, 0.80], [0.62, 0.82], [0.50, 0.92], [0.36, 0.86], [0.22, 0.80], [0.10, 0.70], [0.06, 0.52]]);
    c.closePath();
    const g = c.createRadialGradient(...P(0.5, 0.42), 10, ...P(0.5, 0.42), b.w * 0.6);
    g.addColorStop(0, 'rgba(60,70,110,0.10)'); g.addColorStop(1, 'rgba(20,24,40,0.02)');
    c.fillStyle = g; c.fill();
    c.strokeStyle = 'rgba(150,165,210,0.22)'; c.stroke();
    if (learning > 0) {
      c.save(); c.shadowColor = 'rgba(255,206,102,0.9)'; c.shadowBlur = 18 * learning;
      c.strokeStyle = `rgba(255,206,102,${0.55 * learning})`; c.lineWidth = 1.6; c.stroke(); c.restore();
    }
    // the cerebellum and the brainstem (no populations of this brain sit there)
    curve([[0.70, 0.84], [0.82, 0.80], [0.92, 0.84], [0.90, 0.95], [0.76, 0.98], [0.66, 0.92], [0.70, 0.84]]);
    c.strokeStyle = 'rgba(150,165,210,0.12)'; c.stroke();
    curve([[0.56, 0.90], [0.60, 1.02], [0.64, 1.06]]);
    c.stroke();
    // the central and lateral sulci
    c.setLineDash([3, 5]);
    curve([[0.42, 0.01], [0.405, 0.3], [0.385, 0.62]]); c.strokeStyle = 'rgba(150,165,210,0.16)'; c.stroke();
    curve([[0.24, 0.66], [0.44, 0.67], [0.60, 0.62]]); c.stroke();
    c.restore();
  }

  drawOverlay(now = performance.now()) {
    const c = this.ctx, dpr = this.dpr;
    if (!this.labels) return;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, this.width, this.height);
    // each region glows with its population's mean activation, relative to its most active neuron
    c.save();
    c.globalCompositeOperation = 'lighter';
    const learning = clamp(1 - (now - this.learning) / 500, 0, 1);
    for (const g of this.glows) {
      const members = this.regions[g.region].neurons;
      let sum = 0;
      for (const i of members) sum += Math.max(0, this.display[i] / this.levelScale[g.region]);
      const level = clamp(sum / members.length * 2.2, 0, 1);
      if (level < 0.01) continue;
      const r = Math.max(g.rx, g.ry) * 1.25;
      const grad = c.createRadialGradient(g.x, g.y, 0, g.x, g.y, r);
      grad.addColorStop(0, css(g.hue, 0.26 * level));
      grad.addColorStop(1, css(g.hue, 0));
      c.fillStyle = grad;
      c.beginPath(); c.ellipse(g.x, g.y, g.rx * 1.25, g.ry * 1.25, 0, 0, Math.PI * 2); c.fill();
    }
    c.restore();
    this.silhouette(c, learning);
    // the place answer as the map it is: the product of its two axes, inside the axes
    this.drawPlace(c);
    // labels
    c.font = '600 10.5px Inter, system-ui, sans-serif';
    c.textBaseline = 'alphabetic';
    if (!this.labelsPlaced) {
      // labels that would run into each other on one line step up, one above the other
      for (const l of this.labels) { l.text = `${ANATOMY[l.region.role] || l.region.label} · ${l.region.neurons.length}`.toUpperCase(); l.w = c.measureText(l.text).width + 8; }
      const rows = this.labels.slice().sort((a, b) => a.x - b.x);
      for (let k = 1; k < rows.length; k++) {
        for (let j = 0; j < k; j++) {
          const a = rows[j], b = rows[k];
          if (Math.abs(a.y - b.y) < 15 && b.x < a.x + a.w + 4) b.y = a.y - 17;
        }
      }
      this.labelsPlaced = true;
    }
    for (const l of this.labels) {
      const text = l.text;
      const w = c.measureText(text).width;
      c.fillStyle = 'rgba(6,8,14,0.72)';
      c.beginPath(); c.roundRect(l.x - 4, l.y - 1, w + 8, 15, 4); c.fill();
      c.fillStyle = css(COLOR[l.region.role] || COLOR.other, 0.88);
      c.fillText(text, l.x, l.y + 10);
    }
    this.drawCells(c, now);
    // a lesson's changed synapses
    c.globalCompositeOperation = 'lighter';
    for (const fl of this.flashes) {
      const age = (now - fl.start) / FLASH_MS;
      if (age >= 1) continue;
      const fade = Math.pow(1 - age, 1.4);
      const count = Math.min(fl.index.length, 220);
      for (let j = 0; j < count; j++) {
        const k = fl.index[j], p = this.pre[k], q = this.post[k], r = Math.abs(fl.delta[j]) / fl.max;
        c.lineWidth = 0.6 + 2.2 * r;
        c.strokeStyle = fl.delta[j] >= 0 ? `rgba(255,206,102,${(0.08 + 0.6 * r) * fade})` : `rgba(150,200,255,${(0.08 + 0.6 * r) * fade})`;
        c.beginPath(); c.moveTo(this.pos[2 * p], this.pos[2 * p + 1]);
        c.bezierCurveTo(this.ctrl[4 * k], this.ctrl[4 * k + 1], this.ctrl[4 * k + 2], this.ctrl[4 * k + 3], this.pos[2 * q], this.pos[2 * q + 1]);
        c.stroke();
      }
    }
    c.globalCompositeOperation = 'source-over';
    this.flashes = this.flashes.filter((fl) => now - fl.start < FLASH_MS);
    this.drawSpots(c, now);
  }

  drawPlace(c) {
    const box = this.placeBox;
    if (!box) return;
    const r = this.regions[box.region], per = r.layout.per;
    const scale = this.levelScale[box.region];
    const cw = (box.x1 - box.x0) / per, ch = (box.y0 - box.y1) / per;
    c.save();
    c.globalCompositeOperation = 'lighter';
    for (let j = 0; j < per; j++) {
      const ay = Math.max(0, this.display[r.neurons[per + j]] / scale);
      if (ay < 0.04) continue;
      for (let i = 0; i < per; i++) {
        const ax = Math.max(0, this.display[r.neurons[i]] / scale);
        const v = ax * ay;
        if (v < 0.03) continue;
        c.fillStyle = css(COLOR.place, 0.55 * v);
        c.fillRect(box.x0 + i * cw, box.y0 - (j + 1) * ch, cw + 0.5, ch + 0.5);
      }
    }
    c.restore();
    c.strokeStyle = 'rgba(63,224,207,0.16)'; c.lineWidth = 1;
    c.strokeRect(box.x0, box.y1, box.x1 - box.x0, box.y0 - box.y1);
  }

  // The records' cells. A cell lights for a read (gold) or a write (white), and the latest
  // record's thumbnail hangs from it by a thread: the place it holds on the plane.
  drawCells(c, now) {
    if (!this.cells.length) return;
    const plane = this.records?.value?.plane || [-1, 1, -0.2, 1.4];
    for (const cell of this.cells) {
      const read = clamp(1 - (now - cell.lit) / 400, 0, 1), write = clamp(1 - (now - cell.write) / 700, 0, 1);
      const held = cell.record ? 1 : 0;
      const level = Math.max(read * 0.75, write, held * 0.22);
      c.beginPath(); c.arc(cell.x, cell.y, cell.r * (1 + 0.25 * write), 0, Math.PI * 2);
      c.fillStyle = held ? css(COLOR.hippocampus.map((v) => v * (0.25 + 0.75 * level) + write * 0.3), 1) : 'rgba(60,66,90,0.55)';
      c.fill();
      if (level > 0.25) {
        const grad = c.createRadialGradient(cell.x, cell.y, 0, cell.x, cell.y, cell.r * 4);
        grad.addColorStop(0, css(COLOR.hippocampus, 0.45 * level)); grad.addColorStop(1, css(COLOR.hippocampus, 0));
        c.fillStyle = grad; c.beginPath(); c.arc(cell.x, cell.y, cell.r * 4, 0, Math.PI * 2); c.fill();
      }
    }
    // the thumbnails: the plane with each record's place, in a row under the cells, each on a
    // thread to its cell
    const held = this.cells.filter((cell) => cell.record?.place);
    const tw = clamp(this.brainBox.w * 0.066, 26, 46), th = tw * 0.8, gap = 8;
    const rowY = Math.max(...this.cells.map((cell) => cell.y)) + this.cells[0].r + 16;
    held.forEach((cell, k) => {
      const read = clamp(1 - (now - cell.lit) / 400, 0, 1), write = clamp(1 - (now - cell.write) / 700, 0, 1), lit = Math.max(read, write);
      const tx = this.cells[0].x - this.cells[0].r + k * (tw + gap), ty = rowY;
      c.strokeStyle = css(COLOR.hippocampus, 0.22 + 0.6 * lit); c.lineWidth = 1;
      c.beginPath(); c.moveTo(cell.x, cell.y + cell.r); c.quadraticCurveTo(cell.x, ty - 4, tx + tw / 2, ty); c.stroke();
      c.fillStyle = 'rgba(10,14,25,0.92)'; c.strokeStyle = css(COLOR.hippocampus, 0.3 + 0.6 * lit);
      c.beginPath(); c.roundRect(tx, ty, tw, th, 3); c.fill(); c.stroke();
      const px = tx + ((cell.record.place[0] - plane[0]) / (plane[1] - plane[0])) * tw;
      const py = ty + th - ((cell.record.place[1] - plane[2]) / (plane[3] - plane[2])) * th;
      c.fillStyle = css(COLOR.hippocampus, 0.95);
      c.beginPath(); c.arc(clamp(px, tx + 2, tx + tw - 2), clamp(py, ty + 2, ty + th - 2), 2.2, 0, Math.PI * 2); c.fill();
      c.font = '600 9px Inter, system-ui, sans-serif'; c.textAlign = 'center';
      c.fillStyle = cell.record.from === 'heard' ? 'rgba(255,224,160,0.95)' : 'rgba(255,224,160,0.8)';
      c.fillText(cell.record.from === 'heard' ? `${cell.record.name} ♪` : cell.record.name, tx + tw / 2, ty + th + 10);
      c.textAlign = 'left';
    });
    {
    if (this.cellLabel) {
      c.font = '600 10.5px Inter, system-ui, sans-serif';
      const text = `HIPPOCAMPUS · RECORDS ${this.cells.filter((x) => x.record).length} OF ${this.cells.length}`;
      const y = this.cells[0].y - this.cells[0].r - 16, x = this.cells[0].x - this.cells[0].r;
      const w = c.measureText(text).width;
      c.fillStyle = 'rgba(6,8,14,0.72)'; c.beginPath(); c.roundRect(x - 4, y - 1, w + 8, 15, 4); c.fill();
      c.fillStyle = css(COLOR.hippocampus, 0.88); c.fillText(text, x, y + 10);
    }
    }
  }

  // -- the parts that explain themselves

  // A part is a region (the single "in view" input belongs to the camera's part), the records,
  // or a tract. Each gets a box over the brain and a button in it, so the pointer, a finger and
  // the keyboard reach the same card.
  placeParts() {
    const parts = [];
    const box = (ids, pad) => {
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (const i of ids) { x0 = Math.min(x0, this.pos[2 * i]); x1 = Math.max(x1, this.pos[2 * i]); y0 = Math.min(y0, this.pos[2 * i + 1]); y1 = Math.max(y1, this.pos[2 * i + 1]); }
      return { x: x0 - pad, y: y0 - pad, w: x1 - x0 + 2 * pad, h: y1 - y0 + 2 * pad };
    };
    const owner = (r) => (r.layout?.kind === 'point' ? this.regions.find((q) => q.role === r.role && q.layout?.kind !== 'point') || r : r);
    const byPart = new Map();
    for (const r of this.regions) {
      const o = owner(r);
      if (!byPart.has(o.name)) byPart.set(o.name, { region: o, neurons: [] });
      byPart.get(o.name).neurons.push(...r.neurons);
    }
    for (const [id, part] of byPart) parts.push({ id, kind: 'region', label: part.region.label, region: part.region, neurons: part.neurons, ...box(part.neurons, 9) });
    if (this.cells.length) {
      const xs = this.cells.map((c) => c.x), ys = this.cells.map((c) => c.y), r = this.cells[0].r;
      parts.push({ id: 'records', kind: 'records', label: 'the records of things', x: Math.min(...xs) - r - 6, y: Math.min(...ys) - r - 6,
        w: Math.max(...xs) - Math.min(...xs) + 2 * r + 12, h: Math.max(...ys) - Math.min(...ys) + 2 * r + 56 });
    }
    this.tractParts = [];
    for (const [b, curve] of this.bundle) {
      const [ra, rb] = this.blockNames[b].split('>').map(Number);
      const key = `${this.regions[ra]?.name}>${this.regions[rb]?.name}`;
      const [A, M, B] = curve;
      const mid = [0.25 * A[0] + 0.5 * M[0] + 0.25 * B[0], 0.25 * A[1] + 0.5 * M[1] + 0.25 * B[1]];
      const part = { id: `tract:${key}`, kind: 'tract', key, block: b, curve, label: `the tract from ${this.regions[ra]?.label} to ${this.regions[rb]?.label}`, x: mid[0] - 11, y: mid[1] - 11, w: 22, h: 22 };
      parts.push(part); this.tractParts.push(part);
    }
    this.parts = parts;
    if (!this.partsRoot) return;
    this.partsRoot.replaceChildren();
    for (const part of parts) {
      const b = document.createElement('button');
      b.type = 'button'; b.className = `part ${part.kind}`; b.dataset.part = part.id;
      b.setAttribute('aria-label', `Explain ${part.label}`);
      Object.assign(b.style, { left: `${part.x}px`, top: `${part.y}px`, width: `${part.w}px`, height: `${part.h}px` });
      b.addEventListener('pointerenter', (e) => { if (e.pointerType === 'mouse') this.onPart?.(part.id, 'enter', e); });
      b.addEventListener('pointerleave', (e) => { if (e.pointerType === 'mouse') this.onPart?.(part.id, 'leave', e); });
      b.addEventListener('pointermove', (e) => { this.pointerAt = this.local(e); });
      b.addEventListener('focus', () => { if (b.matches(':focus-visible')) this.onPart?.(part.id, 'enter', null); });
      b.addEventListener('blur', () => this.onPart?.(part.id, 'leave', null));
      b.addEventListener('click', (e) => { this.pointerAt = this.local(e); this.onPart?.(part.id, 'tap', e); });
      this.partsRoot.append(b);
      part.button = b;
    }
  }

  local(event) {
    const box = this.stage.getBoundingClientRect();
    return [event.clientX - box.left, event.clientY - box.top];
  }

  part(id) { return this.parts.find((p) => p.id === id) || null; }

  // The tract whose bundle runs under the pointer, where no region's box does.
  overTract(event, tap = false) {
    let found = null;
    if (event && (event.target === this.stage || event.target === this.partsRoot)) {
      const [x, y] = this.local(event);
      let best = 9;
      for (const part of this.tractParts || []) {
        const [A, M, B] = part.curve;
        for (let k = 0; k <= 24; k++) {
          const t = 0.08 + (0.84 * k) / 24, u = 1 - t;
          const d = Math.hypot(u * u * A[0] + 2 * u * t * M[0] + t * t * B[0] - x, u * u * A[1] + 2 * u * t * M[1] + t * t * B[1] - y);
          if (d < best) { best = d; found = part; }
        }
      }
      this.pointerAt = [x, y];
    }
    const id = found ? found.id : null;
    if (tap) { this.onPart?.(id, 'tap', event); return; }
    if (id === this.tractHover) return;
    if (this.tractHover) this.onPart?.(this.tractHover, 'leave', event);
    this.tractHover = id;
    if (id) this.onPart?.(id, 'enter', event);
  }

  /** A tract's live numbers: the signal it carries and its synapses by sign. */
  flow(key) {
    const part = this.part(`tract:${key}`);
    if (!part) return { signal: 0, synapses: 0, excite: 0, inhibit: 0 };
    let signal = 0, excite = 0, inhibit = 0;
    for (const k of this.blockSynapses[part.block]) {
      const w = this.weight[k];
      signal += Math.abs(w * this.display[this.pre[k]]);
      if (w > 0) excite += 1; else if (w < 0) inhibit += 1;
    }
    return { signal, synapses: this.blockSynapses[part.block].length, excite, inhibit };
  }

  /** A region's activations as they are drawn, in the region's own order. */
  activity(name) {
    const r = this.regions.find((q) => q.name === name);
    const out = new Float32Array(r ? r.neurons.length : 0);
    if (r) r.neurons.forEach((i, k) => { out[k] = this.display[i]; });
    return out;
  }

  /** One plain line about the unit under the pointer inside a part, or ''. */
  unitLine(id) {
    const part = this.part(id);
    if (!part || part.kind !== 'region' || !this.pointerAt) return '';
    const [x, y] = this.pointerAt;
    let best = -1, bestD = 14 * 14;
    for (const i of part.neurons) {
      const d = (this.pos[2 * i] - x) ** 2 + (this.pos[2 * i + 1] - y) ** 2;
      if (d < bestD) { best = i; bestD = d; }
    }
    if (best < 0) return '';
    this.unitAt = best;
    const r = this.regions[this.regionOf[best]], u = this.unit[best], a = this.display[best].toFixed(2);
    if (r.layout?.kind === 'point') return `The unit under your pointer is on while the camera sees the hand. Its activity is ${a}.`;
    if (u) {
      const place = r.role === 'visual' || r.role === 'place';
      const what = place ? (u.reading === 0 ? 'x' : 'y') : `joint ${u.reading + 1}`;
      return `The unit under your pointer prefers ${what} = ${u.value.toFixed(2)} ${place ? 'm' : 'rad'}. Its activity is ${a}.`;
    }
    return `The neuron under your pointer has an activity of ${a}.`;
  }

  /** Where a card for a part goes: beside the part, inside the stage. */
  cardPlace(id, w, h) {
    const part = this.part(id);
    if (!part) return { left: 10, top: 10 };
    let left = part.x + part.w + 12, top = part.y + part.h / 2 - h / 2;
    if (left + w > this.width - 8) left = part.x - w - 12;
    if (left < 8) { left = clamp(part.x + part.w / 2 - w / 2, 8, this.width - w - 8); top = part.y + part.h + 10; if (top + h > this.height - 8) top = part.y - h - 10; }
    return { left: clamp(left, 8, Math.max(8, this.width - w - 8)), top: clamp(top, 8, Math.max(8, this.height - h - 8)) };
  }

  /** Where a pinned card goes so that it covers none of the parts it speaks of: the corner or
   *  edge of the stage that hides the least of them and of the brain. */
  cardClear(ids, w, h) {
    const W = this.width, H = this.height, m = 12, b = this.brainBox || { x: 0, y: 0, w: W, h: H };
    const boxes = ids.map((id) => this.part(id)).filter(Boolean);
    const overlap = (x, y, r) => Math.max(0, Math.min(x + w, r.x + r.w) - Math.max(x, r.x)) * Math.max(0, Math.min(y + h, r.y + r.h) - Math.max(y, r.y));
    const spots = [[m, m + 26], [W - w - m, m + 26], [m, H - h - m - 22], [W - w - m, H - h - m - 26], [(W - w) / 2, m + 26], [(W - w) / 2, H - h - m - 22]];
    let best = spots[0], least = Infinity;
    for (const [x, y] of spots) {
      const cost = boxes.reduce((sum, r) => sum + 20 * overlap(x, y, r), 0) + overlap(x, y, b);
      if (cost < least) { least = cost; best = [x, y]; }
    }
    return { left: clamp(best[0], 8, Math.max(8, W - w - 8)), top: clamp(best[1], 8, Math.max(8, H - h - 8)) };
  }

  drawSpots(c, now) {
    if (!this.spot.size) return;
    const pulse = this.reduced ? 0.8 : 0.62 + 0.3 * Math.sin(now / 420);
    c.save();
    for (const id of this.spot) {
      const part = this.part(id);
      if (!part) continue;
      c.strokeStyle = `rgba(255,255,255,${0.75 * pulse})`; c.lineWidth = 1.4;
      c.shadowColor = 'rgba(255,255,255,0.6)'; c.shadowBlur = 10;
      if (part.kind === 'tract') {
        const [A, M, B] = part.curve;
        c.lineWidth = 9; c.strokeStyle = `rgba(255,255,255,${0.16 * pulse})`; c.lineCap = 'round';
        c.beginPath(); c.moveTo(A[0], A[1]); c.quadraticCurveTo(M[0], M[1], B[0], B[1]); c.stroke();
      } else {
        c.beginPath(); c.roundRect(part.x, part.y, part.w, part.h, 12); c.stroke();
      }
    }
    c.restore();
  }

  // For the page check: draw the brain and read the pixels back.
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
    return { mode: this.mode, hdr: !!this.hdr, fallback: this.fallback || null, frames: this.frames, lit,
      wave: !!this.wave, synapses: (this.gl ? this.synapseCount : this.candidates?.length) ?? 0 };
  }
}
