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
const SHORT = { visual: 'visual', somatosensory: 'body', motor: 'motor', association: 'association', prefrontal: 'prefrontal', place: 'map', auditory: 'hearing' };
const css = (rgb, a = 1) => `rgba(${rgb.map((v) => Math.round(v * 255)).join(',')},${a})`;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const ease = (f) => f * f * (3 - 2 * f);
const LEVEL_FLOOR = 0.08; // a population this quiet is drawn at its true, dim level
const FLASH_MS = 900;
const SIGNAL = 0.062;        // how bright a synapse's signal is drawn
const ANATOMY_LIGHT = 0.1;   // the wiring's own faint light, as a share of a full signal
const BLOOM = 0.8;           // how much of the blurred light is added back
// A population where most neurons are active at once would drown its tracts in light: its
// synapses are drawn at a lower, fixed gain.
const DENSE = { association: 0.42, prefrontal: 0.8 };
const GROUND = [0.024, 0.031, 0.055]; // the page's dark
const NEURON_DEPTH = 1.3;    // the neurons sit a little nearer than the tracts: they drift a little more
const OUTLINE_DEPTH = 0.45;  // the outline sits behind: it drifts less

// A synapse is a curve from its neuron into the tract and out at its target. Its light is the
// signal it carries, |weight x presynaptic activation|, in its source population's hue, warmer
// where the synapse excites and cooler where it inhibits; beside it a faint constant light of
// the weight alone, so the wiring shows at rest; and, while a settle plays, a pulse that runs
// along it where its presynaptic neuron changed in that sweep.
const SYNAPSE_VS = `#version 300 es
precision highp float; precision highp int;
layout(location=0) in float t;
layout(location=1) in vec4 ends;
layout(location=2) in vec4 info;   // weight, presynaptic index, unused, brightness
layout(location=3) in vec4 ctrl;   // the curve's two control points: the bundle it joins
layout(location=4) in vec3 tint;   // the source population's hue
uniform sampler2D state;
uniform int stateWidth;
uniform vec2 viewport;
uniform vec2 centre;
uniform vec3 cam;                  // the view's drift: offset x, y and scale
uniform float anatomy;
uniform float pulseGain;
out float vGlow; out float vRest; out float vSign; out float vT; out float vPulse; out vec3 vTint;
void main() {
  int i = int(info.y + 0.5);
  vec4 s = texelFetch(state, ivec2(i % stateWidth, i / stateWidth), 0);
  float message = abs(info.x * s.r) * info.w;
  vec2 a = ends.xy, b = ends.zw, c1 = ctrl.xy, c2 = ctrl.zw;
  float u = 1.0 - t;
  vec2 p = u * u * u * a + 3.0 * u * u * t * c1 + 3.0 * u * t * t * c2 + t * t * t * b;
  p = centre + (p - centre) * cam.z + cam.xy;
  vec2 clip = p / viewport * 2.0 - 1.0;
  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
  vGlow = pow(clamp(message, 0.0, 1.0), 0.72);
  vRest = min(abs(info.x) * info.w * anatomy, 0.12);
  vSign = info.x >= 0.0 ? 1.0 : -1.0;
  vT = t;
  vPulse = clamp(abs(info.x) * s.g * pulseGain * info.w, 0.0, 1.0);
  vTint = tint;
}`;
const SYNAPSE_FS = `#version 300 es
precision highp float;
in float vGlow; in float vRest; in float vSign; in float vT; in float vPulse; in vec3 vTint;
uniform vec3 excite; uniform vec3 inhibit; uniform vec3 pulseColor; uniform float progress;
out vec4 color;
void main() {
  vec3 base = mix(vSign > 0.0 ? excite : inhibit, vTint, 0.55);
  float head = exp(-pow((vT - progress) * 6.0, 2.0)) * vPulse;
  color = vec4(base * vGlow + mix(vTint, vec3(0.45, 0.55, 0.95), 0.6) * vRest + pulseColor * head * 1.6, 1.0);
}`;
const NEURON_VS = `#version 300 es
precision highp float; precision highp int;
layout(location=0) in vec2 position;
layout(location=1) in vec2 meta;   // index, radius in CSS px
layout(location=2) in vec3 hue;
uniform sampler2D state;
uniform int stateWidth;
uniform vec2 viewport;
uniform vec2 centre;
uniform vec3 cam;
uniform float dpr;
uniform float maxPoint;
out vec3 vHue; out float vLevel; out float vChange;
void main() {
  int i = int(meta.x + 0.5);
  vec4 s = texelFetch(state, ivec2(i % stateWidth, i / stateWidth), 0);
  vec2 p = centre + (position - centre) * cam.z + cam.xy;
  vec2 clip = p / viewport * 2.0 - 1.0;
  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
  gl_PointSize = min(maxPoint, meta.y * dpr * cam.z * 5.2 * (1.0 + 0.22 * clamp(s.b, 0.0, 1.0)));
  vHue = hue; vLevel = s.b; vChange = s.a;
}`;
// A neuron: a core lit by its activity and a halo; `light` 1 adds it to the light that blooms.
const NEURON_FS = `#version 300 es
precision highp float;
in vec3 vHue; in float vLevel; in float vChange;
uniform float light;
out vec4 color;
void main() {
  vec2 q = gl_PointCoord * 2.0 - 1.0;
  float r = length(q);
  if (r > 1.0) discard;
  float level = clamp(vLevel, -0.2, 1.0);
  float lit = smoothstep(0.0, 0.75, level);
  vec3 dim = vHue * 0.36 + vec3(0.04, 0.05, 0.085);
  vec3 hot = mix(vHue, vec3(1.0), smoothstep(0.5, 1.0, level) * 0.75);
  vec3 c = mix(dim, hot, lit);
  if (level < 0.0) c = dim * (1.0 + level * 2.5);
  float coreR = 0.26 + 0.16 * lit;
  float core = 1.0 - smoothstep(coreR - 0.04, coreR + 0.03, r);
  float halo = exp(-r * r * 8.0) * (0.2 + 0.8 * lit) + clamp(vChange * 6.0, 0.0, 0.7) * exp(-r * r * 4.5);
  float a = clamp(core * (0.6 + 0.4 * lit) + halo, 0.0, 1.0);
  if (light > 0.5) { color = vec4(hot * (lit * 0.9 + clamp(vChange * 4.0, 0.0, 0.5)) * exp(-r * r * 3.0), 1.0); return; }
  color = vec4(c * a, a);
}`;
const QUAD_VS = `#version 300 es
out vec2 uv;
void main() {
  vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  uv = p;
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`;
// One pass of a separable blur: nine taps along `step`, the weights of a Gaussian.
const BLUR_FS = `#version 300 es
precision highp float;
in vec2 uv;
uniform sampler2D source;
uniform vec2 step;
out vec4 color;
void main() {
  vec3 sum = texture(source, uv).rgb * 0.2270;
  sum += (texture(source, uv + step * 1.3846).rgb + texture(source, uv - step * 1.3846).rgb) * 0.3162;
  sum += (texture(source, uv + step * 3.2308).rgb + texture(source, uv - step * 3.2308).rgb) * 0.0703;
  color = vec4(sum, 1.0);
}`;
// The light and its bloom, tone mapped together: dense bundles stay bright without clipping to
// white, and what is bright glows into the dark around it.
const QUAD_FS = `#version 300 es
precision highp float;
in vec2 uv;
uniform sampler2D light;
uniform sampler2D bloom;
uniform sampler2D haze;
uniform float exposure;
uniform float bloomGain;
uniform vec3 ground;
out vec4 color;
void main() {
  vec3 x = texture(light, uv).rgb * exposure + texture(bloom, uv).rgb * bloomGain + texture(haze, uv).rgb * bloomGain * 0.9;
  float l = max(max(x.r, x.g), x.b);
  vec3 c = l > 0.0 ? x * ((1.0 - exp(-l)) / l) : vec3(0.0);
  color = vec4(ground + c, 1.0);
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
    this.cam = { x: 0, y: 0, s: 1 };
    this.inset = 0;        // room kept free at the bottom of the stage, for a sheet
    this.leader = null;    // a thin line from an open card to its part: { rect, id }
    this.settled = null;   // the latest settle's record: the largest change at every sweep
    this.resting = false;  // the moment on show needed no sweep: the state before it stood
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
    if (this.gl) this.uploadSynapses(true);
  }

  /** Keep `pixels` at the bottom of the stage free (a sheet stands there): the brain moves up. */
  setInset(pixels) {
    if (Math.abs((this.inset || 0) - pixels) < 2) return;
    this.inset = pixels;
    if (this.brain && this.width) this.layout();
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
    // The brain fills its pane: as wide as the pane, and as tall as a brain may be (the cortex
    // with the cerebellum and the stem below it spans 1.06 of the box's height). `inset` is
    // room kept free at the bottom for a sheet.
    const pad = Math.max(8, Math.round(W * 0.014)), above = 36, below = this.inset ? this.inset + 6 : 40;
    const room = Math.max(160, H - above - below);
    const aspect = clamp((W - 2 * pad) / (room / 1.06), 1.1, 1.5);
    const bw = Math.min(W - 2 * pad, (room / 1.06) * aspect), bh = bw / aspect;
    const bx = (W - bw) / 2, by = above + (room - bh * 1.06) / 2;
    const at = (u, v) => [bx + u * bw, by + v * bh];
    this.brainBox = { x: bx, y: by, w: bw, h: bh };
    const unitR = clamp(bw * 0.0088, 2.2, 7.5);
    this.compact = bw < 440; // a small brain: short labels, no settle trace

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
        line(row(0), 0.575, 0.345, 0.765, 0.345);
        if (rows > 1) line(row(1), 0.553, 0.318, 0.553, 0.075);
        this.placeBox = { region: r.index, x0: at(0.575, 0)[0], x1: at(0.765, 0)[0], y0: at(0, 0.318)[1], y1: at(0, 0.075)[1] };
        glow(r, 0.66, 0.2, 0.13, 0.18); label(r, 0.61, 0.03);
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
  playWave(frames, count, sweeps, of, move = null) {
    if (!this.brain || !count) return false;
    // the settle's own record, for the trace beside the readout: the largest change of any
    // neuron at every sweep
    if (move) this.settled = { move: Float32Array.from(move), of, sweeps: sweeps.slice(), at: performance.now() };
    if (this.reduced || this.wave) return false; // one wave at a time: a newer settle waits for the next one
    const n = this.n, list = [];
    for (let k = 0; k < count; k++) list.push(frames.subarray(k * n, (k + 1) * n));
    this.rescale(list);
    const all = [Float32Array.from(this.display), ...list];
    // the pulses are drawn relative to the largest change between two of the wave's frames
    let top = 1e-5;
    for (let k = 1; k < all.length; k++) for (let j = 0; j < n; j++) top = Math.max(top, Math.abs(all[k][j] - all[k - 1][j]));
    this.wave = { frames: all, sweeps: [0, ...sweeps], of, head: 0, top };
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
    this.buffers = { t: gl.createBuffer(), ends: gl.createBuffer(), info: gl.createBuffer(), ctrl: gl.createBuffer(), tint: gl.createBuffer(),
      position: gl.createBuffer(), meta: gl.createBuffer(), hue: gl.createBuffer() };
    this.maxPoint = gl.getParameter(gl.ALIASED_POINT_SIZE_RANGE)[1] || 64;
    this.hdr = !!(gl.getExtension('EXT_color_buffer_float') || gl.getExtension('EXT_color_buffer_half_float'));
    if (this.hdr) {
      this.compositeProgram = program(gl, QUAD_VS, QUAD_FS);
      this.blurProgram = program(gl, QUAD_VS, BLUR_FS);
      this.quadVAO = gl.createVertexArray();
      // the light at full size; its bloom at a quarter and its haze at an eighth, two buffers each
      this.targets = ['light', 'bloomA', 'bloomB', 'hazeA', 'hazeB'].map((name) => ({ name, fbo: gl.createFramebuffer(), tex: gl.createTexture(), w: 0, h: 0 }));
    }
    this.canvas.addEventListener('webglcontextlost', (e) => { e.preventDefault(); this.use2D('context lost'); });
  }

  // The off-screen buffers the light is gathered and blurred in, at the canvas's size.
  lightBuffers() {
    const gl = this.gl, W = this.canvas.width, H = this.canvas.height;
    const sizes = [[W, H], [W >> 2, H >> 2], [W >> 2, H >> 2], [W >> 3, H >> 3], [W >> 3, H >> 3]];
    let ok = true;
    this.targets.forEach((t, k) => {
      const [w, h] = sizes[k].map((v) => Math.max(2, v));
      if (t.w === w && t.h === h) return;
      gl.bindTexture(gl.TEXTURE_2D, t.tex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, w, h, 0, gl.RGBA, gl.HALF_FLOAT, null);
      for (const p of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_2D, p, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.bindFramebuffer(gl.FRAMEBUFFER, t.fbo);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t.tex, 0);
      ok = ok && gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE;
      t.w = w; t.h = h;
    });
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    if (!ok) this.hdr = false;
    return ok;
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

  // What each synapse's light is multiplied by: a wide fan of synapses glows fainter per synapse
  // than a narrow one, and every block is read against its own mean weight.
  gains() {
    // a small brain packs the same curves into fewer pixels: its light is turned down with its size
    const size = clamp(Math.pow((this.brainBox?.w || this.width) / 640, 1.3), 0.22, 1.25);
    return this.blockNames.map((name, b) => {
      const fan = clamp(Math.sqrt(1600 / Math.max(64, this.blockCount[b])), 0.3, 1.6);
      const from = this.regions[Number(name.split('>')[0])]?.role;
      return (0.5 / (this.blockScale[b] * 0.6 || 1)) * fan * size * SIGNAL * (DENSE[from] ?? 1);
    });
  }

  uploadSynapses(weightsOnly = false) {
    const gl = this.gl, m = this.pre.length;
    if (!this.pos || !gl) return;
    const gains = this.gains();
    const info = new Float32Array(4 * m);
    for (let k = 0; k < m; k++) { info[4 * k] = this.weight[k]; info[4 * k + 1] = this.pre[k]; info[4 * k + 3] = gains[this.blockOf[k]]; }
    if (weightsOnly && this.synapseCount === m) { // a lesson changed weights: the curves stand as they are
      gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers.info); gl.bufferSubData(gl.ARRAY_BUFFER, 0, info);
      return;
    }
    this.segments = m > 120000 ? 6 : 10;
    const t = new Float32Array(2 * this.segments);
    for (let k = 0; k < this.segments; k++) { t[2 * k] = k / this.segments; t[2 * k + 1] = (k + 1) / this.segments; }
    const ends = new Float32Array(4 * m), tint = new Float32Array(3 * m);
    for (let k = 0; k < m; k++) {
      const p = this.pre[k], q = this.post[k];
      ends[4 * k] = this.pos[2 * p]; ends[4 * k + 1] = this.pos[2 * p + 1]; ends[4 * k + 2] = this.pos[2 * q]; ends[4 * k + 3] = this.pos[2 * q + 1];
      tint.set(COLOR[this.regions[this.regionOf[p]]?.role] || COLOR.other, 3 * k);
    }
    gl.bindVertexArray(this.synapseVAO);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers.t); gl.bufferData(gl.ARRAY_BUFFER, t, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 1, gl.FLOAT, false, 0, 0); gl.vertexAttribDivisor(0, 0);
    const instanced = (buffer, data, loc, width, usage = gl.STATIC_DRAW) => {
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer); gl.bufferData(gl.ARRAY_BUFFER, data, usage);
      gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, width, gl.FLOAT, false, 0, 0); gl.vertexAttribDivisor(loc, 1);
    };
    instanced(this.buffers.ends, ends, 1, 4);
    instanced(this.buffers.info, info, 2, 4, gl.DYNAMIC_DRAW);
    instanced(this.buffers.ctrl, this.ctrl, 3, 4);
    instanced(this.buffers.tint, tint, 4, 3);
    gl.bindVertexArray(null);
    this.synapseCount = m;
  }

  drawGL(progress) {
    const gl = this.gl, s = this.stateData, n = this.n, last = this.levelScale.length - 1;
    const changeGain = this.wave ? 1 / this.wave.top : 1;
    for (let i = 0; i < n; i++) {
      const scale = this.levelScale[this.regionOf[i] < 0 ? last : this.regionOf[i]];
      s[4 * i] = this.display[i]; s[4 * i + 1] = this.change[i] * changeGain;
      s[4 * i + 2] = this.display[i] / scale; s[4 * i + 3] = this.wave ? this.change[i] * changeGain * 0.25 : this.change[i] / scale;
    }
    gl.bindTexture(gl.TEXTURE_2D, this.stateTex);
    gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, this.stateWidth, this.stateHeight, gl.RGBA, gl.FLOAT, s);
    const hdr = this.hdr && this.lightBuffers();
    const cam = this.cam, b = this.brainBox, cx = b.x + b.w / 2, cy = b.y + b.h / 2;
    const W = this.canvas.width, H = this.canvas.height;
    gl.viewport(0, 0, W, H);
    if (hdr) { gl.bindFramebuffer(gl.FRAMEBUFFER, this.targets[0].fbo); gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT); }
    else { gl.clearColor(...GROUND, 1); gl.clear(gl.COLOR_BUFFER_BIT); }
    gl.enable(gl.BLEND);
    // the synapses' light
    const sp = this.synapseProgram;
    gl.useProgram(sp.p);
    gl.blendFunc(gl.ONE, gl.ONE);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.stateTex);
    gl.uniform1i(sp.u.state, 0); gl.uniform1i(sp.u.stateWidth, this.stateWidth);
    gl.uniform2f(sp.u.viewport, this.width, this.height);
    gl.uniform2f(sp.u.centre, cx, cy); gl.uniform3f(sp.u.cam, cam.x, cam.y, cam.s);
    gl.uniform1f(sp.u.anatomy, ANATOMY_LIGHT);
    gl.uniform1f(sp.u.pulseGain, this.reduced || !this.wave ? 0 : 14); // pulses run while a settle plays
    gl.uniform1f(sp.u.progress, progress);
    gl.uniform3fv(sp.u.excite, COLOR.excite); gl.uniform3fv(sp.u.inhibit, COLOR.inhibit); gl.uniform3fv(sp.u.pulseColor, COLOR.pulse);
    gl.bindVertexArray(this.synapseVAO);
    gl.drawArraysInstanced(gl.LINES, 0, 2 * this.segments, this.synapseCount);
    const np = this.neuronProgram;
    const neurons = (light, depth) => {
      gl.useProgram(np.p);
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.stateTex);
      gl.uniform1i(np.u.state, 0); gl.uniform1i(np.u.stateWidth, this.stateWidth);
      gl.uniform2f(np.u.viewport, this.width, this.height);
      gl.uniform2f(np.u.centre, cx, cy); gl.uniform3f(np.u.cam, cam.x * depth, cam.y * depth, cam.s);
      gl.uniform1f(np.u.dpr, this.dpr); gl.uniform1f(np.u.maxPoint, this.maxPoint);
      gl.uniform1f(np.u.light, light);
      gl.bindVertexArray(this.neuronVAO);
      gl.drawArrays(gl.POINTS, 0, n);
    };
    if (hdr) {
      // the neurons' own light joins the synapses' before it blooms
      gl.blendFunc(gl.ONE, gl.ONE);
      neurons(1, NEURON_DEPTH);
      // the bloom: the light blurred at a quarter of the size, and the haze at an eighth
      const bp = this.blurProgram, [light, a1, a2, h1, h2] = this.targets;
      gl.disable(gl.BLEND);
      gl.useProgram(bp.p);
      gl.bindVertexArray(this.quadVAO);
      gl.activeTexture(gl.TEXTURE1);
      gl.uniform1i(bp.u.source, 1);
      const blur = (from, to, dx, dy) => {
        gl.bindFramebuffer(gl.FRAMEBUFFER, to.fbo); gl.viewport(0, 0, to.w, to.h);
        gl.bindTexture(gl.TEXTURE_2D, from.tex);
        gl.uniform2f(bp.u.step, dx / from.w, dy / from.h);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
      };
      blur(light, a1, 2, 0); blur(a1, a2, 0, 1); blur(a2, a1, 1.5, 0); blur(a1, a2, 0, 1.5);
      blur(a2, h1, 2, 0); blur(h1, h2, 0, 1.5); blur(h2, h1, 2, 0); blur(h1, h2, 0, 2);
      // the light, its bloom and its haze together, tone mapped
      gl.bindFramebuffer(gl.FRAMEBUFFER, null); gl.viewport(0, 0, W, H);
      const cp = this.compositeProgram;
      gl.useProgram(cp.p);
      gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, light.tex);
      gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, a2.tex);
      gl.activeTexture(gl.TEXTURE3); gl.bindTexture(gl.TEXTURE_2D, h2.tex);
      gl.uniform1i(cp.u.light, 1); gl.uniform1i(cp.u.bloom, 2); gl.uniform1i(cp.u.haze, 3);
      gl.uniform1f(cp.u.exposure, 1.0); gl.uniform1f(cp.u.bloomGain, BLOOM);
      gl.uniform3fv(cp.u.ground, GROUND);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      gl.activeTexture(gl.TEXTURE0);
      gl.enable(gl.BLEND);
    }
    // the neurons themselves, crisp, a little nearer than the tracts
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    neurons(0, NEURON_DEPTH);
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
    c.fillStyle = '#06080e'; c.fillRect(0, 0, this.width, this.height);
    this.view(c, 1);
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
    c.restore();
  }

  // -- one frame

  frame(now, interval) {
    if (!this.brain || !this.width) return;
    const dt = Math.min(64, interval);
    let progress = 0;
    const w = this.wave;
    if (w) {
      // one recorded sweep every 70 ms, eased from one to the next; a pulse runs each tract per sweep
      const limit = w.frames.length - 1;
      w.head = Math.min(limit, w.head + dt / 70);
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
    }
    // the view drifts a little, slowly, and the layers part: the outline behind, the neurons in front
    const t = now / 1000;
    this.cam = this.reduced ? { x: 0, y: 0, s: 1 } : { x: 5 * Math.sin(t / 4.7), y: 3.2 * Math.sin(t / 6.1 + 1.3), s: 1 + 0.007 * Math.sin(t / 8.3) };
    if (this.partsRoot && this.brainBox) {
      const b = this.brainBox;
      this.partsRoot.style.transformOrigin = `${b.x + b.w / 2}px ${b.y + b.h / 2}px`;
      this.partsRoot.style.transform = `translate(${(this.cam.x * NEURON_DEPTH).toFixed(2)}px, ${(this.cam.y * NEURON_DEPTH).toFixed(2)}px) scale(${this.cam.s.toFixed(4)})`;
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

  // The view's drift for a layer at `depth`: saves the context; the caller restores it.
  view(c, depth) {
    const b = this.brainBox, cx = b.x + b.w / 2, cy = b.y + b.h / 2, k = this.cam;
    c.save();
    c.translate(cx + k.x * depth, cy + k.y * depth); c.scale(k.s, k.s); c.translate(-cx, -cy);
  }

  /** Where a point of a layer stands on the stage at this frame. */
  onStage(x, y, depth) {
    const b = this.brainBox, cx = b.x + b.w / 2, cy = b.y + b.h / 2, k = this.cam;
    return [cx + k.x * depth + (x - cx) * k.s, cy + k.y * depth + (y - cy) * k.s];
  }

  // The outline of a brain seen from the side (front to the left): the frame the populations sit
  // in. Its light follows the brain's mean activity, and it glows gold for the half second after
  // a lesson that changed synapses: the learning state, on.
  silhouette(c, learning = 0, level = 0) {
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
    const cortex = [[0.06, 0.52], [0.02, 0.36], [0.08, 0.16], [0.24, 0.04], [0.46, 0.0], [0.68, 0.03], [0.86, 0.14], [0.97, 0.34],
      [0.98, 0.56], [0.93, 0.72], [0.80, 0.80], [0.62, 0.82], [0.50, 0.92], [0.36, 0.86], [0.22, 0.80], [0.10, 0.70], [0.06, 0.52]];
    c.save();
    // a soft light behind the whole brain
    const [mx, my] = P(0.5, 0.45);
    const air = c.createRadialGradient(mx, my, b.w * 0.05, mx, my, b.w * 0.78);
    air.addColorStop(0, `rgba(72,96,190,${0.2 + 0.16 * level})`); air.addColorStop(0.55, `rgba(46,62,140,${0.08 + 0.06 * level})`); air.addColorStop(1, 'rgba(20,28,70,0)');
    c.fillStyle = air; c.fillRect(0, 0, this.width, this.height);
    // the cortex: a body with depth, lit from within
    curve(cortex); c.closePath();
    const body = c.createRadialGradient(...P(0.46, 0.34), b.w * 0.04, ...P(0.5, 0.45), b.w * 0.62);
    body.addColorStop(0, 'rgba(84,100,176,0.26)'); body.addColorStop(0.6, 'rgba(40,52,104,0.16)'); body.addColorStop(1, 'rgba(14,18,40,0.10)');
    c.fillStyle = body; c.fill();
    c.save();
    c.shadowColor = learning > 0 ? `rgba(255,206,102,${0.5 + 0.4 * learning})` : 'rgba(110,140,255,0.6)'; c.shadowBlur = 16 + 10 * learning;
    c.lineWidth = 1.6; c.strokeStyle = learning > 0 ? `rgba(${Math.round(170 + 85 * learning)},${Math.round(186 + 20 * learning)},${Math.round(236 - 130 * learning)},0.72)` : 'rgba(170,186,236,0.62)';
    c.stroke();
    c.restore();
    // the folds of the surface, faint, inside the outline
    c.save();
    curve(cortex); c.closePath(); c.clip();
    c.lineWidth = 1; c.strokeStyle = 'rgba(150,168,225,0.085)';
    for (const fold of [
      [[0.10, 0.30], [0.20, 0.22], [0.27, 0.36], [0.20, 0.52]], [[0.13, 0.62], [0.24, 0.56], [0.33, 0.66]], [[0.26, 0.10], [0.33, 0.22], [0.30, 0.40]],
      [[0.50, 0.03], [0.53, 0.20], [0.50, 0.40]], [[0.60, 0.44], [0.72, 0.40], [0.80, 0.50]], [[0.74, 0.10], [0.80, 0.26], [0.76, 0.42]],
      [[0.84, 0.20], [0.92, 0.36], [0.90, 0.56]], [[0.70, 0.62], [0.80, 0.66], [0.90, 0.62]], [[0.30, 0.74], [0.42, 0.78], [0.56, 0.74], [0.66, 0.70]],
      [[0.05, 0.44], [0.12, 0.42], [0.16, 0.48]], [[0.36, 0.52], [0.44, 0.60], [0.56, 0.56]],
    ]) { curve(fold); c.stroke(); }
    // an inner contour: the far side of the surface
    c.translate(...P(0.5, 0.44)); c.scale(0.94, 0.93); c.translate(-P(0.5, 0.44)[0], -P(0.5, 0.44)[1]);
    curve(cortex); c.closePath(); c.strokeStyle = 'rgba(150,168,225,0.07)'; c.stroke();
    c.restore();
    // the cerebellum and the brainstem (no populations of this brain sit there)
    curve([[0.70, 0.84], [0.82, 0.80], [0.92, 0.84], [0.90, 0.95], [0.76, 0.98], [0.66, 0.92], [0.70, 0.84]]);
    c.closePath(); c.fillStyle = 'rgba(40,52,104,0.12)'; c.fill();
    c.lineWidth = 1.2; c.strokeStyle = 'rgba(160,176,228,0.3)'; c.stroke();
    c.strokeStyle = 'rgba(150,168,225,0.12)'; c.lineWidth = 1;
    for (const leaf of [[[0.70, 0.88], [0.80, 0.84], [0.90, 0.87]], [[0.69, 0.91], [0.80, 0.88], [0.90, 0.91]], [[0.71, 0.945], [0.80, 0.92], [0.88, 0.945]]]) { curve(leaf); c.stroke(); }
    curve([[0.55, 0.90], [0.585, 1.0], [0.62, 1.06]]); c.strokeStyle = 'rgba(160,176,228,0.26)'; c.lineWidth = 1.2; c.stroke();
    curve([[0.615, 0.89], [0.645, 0.98], [0.685, 1.04]]); c.stroke();
    // the central and lateral sulci
    c.setLineDash([3, 5]); c.lineWidth = 1.1; c.strokeStyle = 'rgba(160,176,228,0.26)';
    curve([[0.42, 0.01], [0.405, 0.3], [0.385, 0.62]]); c.stroke();
    curve([[0.24, 0.66], [0.44, 0.67], [0.60, 0.62]]); c.stroke();
    c.restore();
  }

  drawOverlay(now = performance.now()) {
    const c = this.ctx, dpr = this.dpr;
    if (!this.labels) return;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, this.width, this.height);
    const learning = clamp(1 - (now - this.learning) / 500, 0, 1);
    // every region's level: its population's mean activation, relative to its most active neuron
    let mean = 0;
    for (const g of this.glows) {
      const members = this.regions[g.region].neurons;
      let sum = 0;
      for (const i of members) sum += Math.max(0, this.display[i] / this.levelScale[g.region]);
      g.level = clamp((sum / members.length) * 2.2, 0, 1);
      mean += g.level / this.glows.length;
      // while a settle plays: how much this region's neurons changed in the sweep on show,
      // relative to the settle's largest change
      g.ripple = 0;
      if (this.wave) { let moved = 0; for (const i of members) moved = Math.max(moved, this.change[i]); g.ripple = clamp(moved / this.wave.top, 0, 1); }
    }
    this.view(c, OUTLINE_DEPTH);
    this.silhouette(c, learning, mean);
    c.restore();
    // each region: a faint plate where its population sits, glowing with its level
    this.view(c, NEURON_DEPTH);
    c.globalCompositeOperation = 'lighter';
    for (const g of this.glows) {
      const grad = c.createRadialGradient(g.x, g.y, 0, g.x, g.y, Math.max(g.rx, g.ry) * 1.3);
      grad.addColorStop(0, css(g.hue, 0.1 + 0.3 * g.level)); grad.addColorStop(0.7, css(g.hue, 0.04 + 0.08 * g.level)); grad.addColorStop(1, css(g.hue, 0));
      c.fillStyle = grad;
      c.beginPath(); c.ellipse(g.x, g.y, g.rx * 1.3, g.ry * 1.3, 0, 0, Math.PI * 2); c.fill();
      if (g.ripple > 0.04) {
        // the settle's wave reaching this region: a ring as bright as its neurons' change
        c.strokeStyle = css(g.hue.map((v) => 0.5 + 0.5 * v), 0.85 * g.ripple); c.lineWidth = 1 + 2 * g.ripple;
        c.shadowColor = css(g.hue, 0.9); c.shadowBlur = 14 * g.ripple;
        c.beginPath(); c.ellipse(g.x, g.y, g.rx * (1.12 + 0.1 * g.ripple), g.ry * (1.12 + 0.1 * g.ripple), 0, 0, Math.PI * 2); c.stroke();
        c.shadowBlur = 0;
      }
    }
    c.globalCompositeOperation = 'source-over';
    // the place answer as the map it is: the product of its two axes, inside the axes
    this.drawPlace(c);
    // labels
    c.font = `600 ${this.compact ? 9 : 10.5}px Inter, system-ui, sans-serif`;
    c.textBaseline = 'alphabetic';
    if (!this.labelsPlaced) {
      // labels that would run into each other on one line step up, one above the other
      for (const l of this.labels) { l.text = (this.compact ? SHORT[l.region.role] || l.region.label : `${ANATOMY[l.region.role] || l.region.label} · ${l.region.neurons.length}`).toUpperCase(); l.w = c.measureText(l.text).width + 8; }
      const rows = this.labels.slice().sort((a, b) => a.x - b.x);
      for (let k = 1; k < rows.length; k++) {
        for (let j = 0; j < k; j++) {
          const a = rows[j], b = rows[k];
          if (Math.abs(a.y - b.y) < 15 && b.x < a.x + a.w + 4) b.y = a.y - 17;
        }
      }
      for (const l of this.labels) l.x = clamp(l.x, 6, Math.max(6, this.width - l.w - 6));
      this.labelsPlaced = true;
    }
    for (const l of this.labels) {
      c.fillStyle = 'rgba(6,8,14,0.6)';
      c.beginPath(); c.roundRect(l.x - 4, l.y - 1, l.w, 15, 4); c.fill();
      c.fillStyle = css(COLOR[l.region.role] || COLOR.other, 0.95);
      c.fillText(l.text, l.x, l.y + 10);
    }
    this.drawCells(c, now);
    this.drawSpots(c, now);
    c.restore();
    // a lesson's changed synapses, on the tracts' own layer
    this.view(c, 1);
    c.globalCompositeOperation = 'lighter';
    for (const fl of this.flashes) {
      const age = (now - fl.start) / FLASH_MS;
      if (age >= 1) continue;
      const fade = Math.pow(1 - age, 1.4);
      const count = Math.min(fl.index.length, 220);
      for (let j = 0; j < count; j++) {
        const k = fl.index[j], p = this.pre[k], q = this.post[k], r = Math.abs(fl.delta[j]) / fl.max;
        c.lineWidth = 0.7 + 2.4 * r;
        c.strokeStyle = fl.delta[j] >= 0 ? `rgba(255,206,102,${(0.1 + 0.7 * r) * fade})` : `rgba(150,200,255,${(0.1 + 0.7 * r) * fade})`;
        c.beginPath(); c.moveTo(this.pos[2 * p], this.pos[2 * p + 1]);
        c.bezierCurveTo(this.ctrl[4 * k], this.ctrl[4 * k + 1], this.ctrl[4 * k + 2], this.ctrl[4 * k + 3], this.pos[2 * q], this.pos[2 * q + 1]);
        c.stroke();
      }
    }
    c.restore();
    this.flashes = this.flashes.filter((fl) => now - fl.start < FLASH_MS);
    this.drawSettle(c);
    this.drawLeader(c);
  }

  // The latest settle, sweep by sweep: one bar a sweep, as tall as the largest change of any
  // neuron in that sweep (ten times smaller is one step lower). While the settle plays, the bar
  // of the sweep on show is lit.
  drawSettle(c) {
    const s = this.settled;
    if (!s || !s.move.length || this.compact || this.inset) return;
    const n = s.move.length, x0 = 14, w = Math.min(150, this.width * 0.3), h = 30, y1 = this.height - 34 - (this.inset || 0);
    const playing = this.wave ? this.wave.sweeps[Math.min(this.wave.sweeps.length - 1, Math.floor(this.wave.head) + 1)] : 0;
    const bars = Math.min(n, 64), bw = w / bars;
    c.save();
    for (let k = 0; k < bars; k++) {
      const i = Math.min(n - 1, Math.round((k * (n - 1)) / Math.max(1, bars - 1)));
      const f = clamp((Math.log10(Math.max(s.move[i], 1e-9)) + 7) / 7, 0.04, 1);
      const here = playing && Math.abs(i + 1 - playing) <= Math.max(0.5, n / bars / 2), done = !playing || i + 1 <= playing;
      c.fillStyle = here ? 'rgba(255,244,220,0.98)' : this.resting && !playing ? 'rgba(63,224,207,0.2)' : done ? 'rgba(63,224,207,0.62)' : 'rgba(63,224,207,0.2)';
      if (here) { c.shadowColor = 'rgba(255,230,180,0.9)'; c.shadowBlur = 8; } else c.shadowBlur = 0;
      c.fillRect(x0 + k * bw, y1 - f * h, Math.max(1, bw - 1), f * h);
    }
    c.shadowBlur = 0;
    c.font = '500 10.5px "JetBrains Mono", ui-monospace, monospace'; c.textBaseline = 'alphabetic';
    c.fillStyle = playing ? 'rgba(255,236,200,0.95)' : 'rgba(141,151,178,0.85)';
    c.fillText(playing ? `sweep ${playing} of ${s.of}` : this.resting ? 'at rest: no sweep needed' : `settled in ${s.of} sweeps`, x0 + w + 8, y1 - 2);
    c.restore();
  }

  // A thin line from an open card to the part it explains.
  drawLeader(c) {
    const l = this.leader, part = l && this.part(l.id);
    if (!part) return;
    const [px, py] = this.onStage(part.x + part.w / 2, part.y + part.h / 2, NEURON_DEPTH);
    const hw = (part.w / 2) * this.cam.s, hh = (part.h / 2) * this.cam.s, r = l.rect;
    // from the card's edge nearest the part to the part's edge nearest the card
    const cx = clamp(px, r.left, r.left + r.w), cy = clamp(py, r.top, r.top + r.h);
    const ex = clamp(cx, px - hw, px + hw), ey = clamp(cy, py - hh, py + hh);
    if (Math.hypot(ex - cx, ey - cy) < 6) return;
    c.save();
    c.strokeStyle = 'rgba(255,255,255,0.55)'; c.lineWidth = 1;
    c.beginPath(); c.moveTo(cx, cy); c.lineTo(ex, ey); c.stroke();
    c.fillStyle = 'rgba(255,255,255,0.9)';
    c.beginPath(); c.arc(ex, ey, 2.4, 0, Math.PI * 2); c.fill();
    c.restore();
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
      c.font = `600 ${this.compact ? 9 : 10.5}px Inter, system-ui, sans-serif`;
      const text = this.compact ? 'HIPPOCAMPUS' : `HIPPOCAMPUS · RECORDS ${this.cells.filter((x) => x.record).length} OF ${this.cells.length}`;
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

  /** Where a card goes: beside the first of the parts it explains, never over any of them. The
   *  places around the part are tried in turn (right, left, below, above, then the stage's
   *  corners); the first that covers no named part wins, else the one that covers least. */
  cardBeside(ids, w, h) {
    const W = this.width, H = this.height - (this.inset || 0), m = 8, gap = 22;
    const boxes = ids.map((id) => this.part(id)).filter(Boolean).map((p) => {
      const [x, y] = this.onStage(p.x, p.y, NEURON_DEPTH);
      return p.kind === 'tract' ? { x: x - 8, y: y - 8, w: p.w + 16, h: p.h + 16 } : { x: x - 4, y: y - 4, w: p.w + 8, h: p.h + 8 };
    });
    if (!boxes.length) return { left: m, top: m + 30 };
    const a = boxes[0], ax = a.x + a.w / 2, ay = a.y + a.h / 2;
    const fit = ([x, y]) => [clamp(x, m, Math.max(m, W - w - m)), clamp(y, m + 26, Math.max(m + 26, H - h - m - 26))];
    const spots = [[a.x + a.w + gap, ay - h / 2], [a.x - w - gap, ay - h / 2], [ax - w / 2, a.y + a.h + gap], [ax - w / 2, a.y - h - gap],
      [a.x + a.w + gap, a.y - h * 0.8], [a.x - w - gap, a.y - h * 0.8], [a.x + a.w + gap, a.y + a.h - h * 0.2], [a.x - w - gap, a.y + a.h - h * 0.2],
      [m, m + 26], [W - w - m, m + 26], [m, H - h - m - 26], [W - w - m, H - h - m - 26]].map(fit);
    const over = (x, y, r) => Math.max(0, Math.min(x + w, r.x + r.w) - Math.max(x, r.x)) * Math.max(0, Math.min(y + h, r.y + r.h) - Math.max(y, r.y));
    let best = spots[0], least = Infinity;
    for (const [x, y] of spots) {
      const cost = boxes.reduce((sum, r) => sum + over(x, y, r), 0);
      if (cost < least - 1) { least = cost; best = [x, y]; }
      if (cost === 0) break;
    }
    return { left: best[0], top: best[1] };
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
