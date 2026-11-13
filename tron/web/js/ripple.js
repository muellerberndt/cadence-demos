// The brain, rippling. Every live neuron of the brain is drawn where it sits in the flow: the
// inputs, then the association module, then the three motor neurons. The faint lines are the
// real strongest synapses of every pathway. A population the design switches off (Mako's working
// trace has amplitude 0) is left out, with its synapses.
//
// The 2,470 inputs are drawn as the sense lays them out, stylized: the four 24 x 24 planes of the
// field in the rider's frame (ahead up) merged into one glowing dot field (its trail pink, yours
// cyan, the two heads as lights); the two 9 x 9 foveas as radial eyes (each cell at its
// direction from the head, nearer cells closer to the centre); your heading as one arrow.
//
// Each move is one recorded settle (tron/fieldhost.py sends every neuron's state after every
// sweep), played as a wave. The front starts where the active inputs are (their centroid,
// weighted by how strongly each is wired in) and crosses the brain; when it reaches a neuron,
// that neuron plays its own recorded sweeps, so its brightness and halo track its real activation
// sweep by sweep. The neurons whose state moved most since the last move send out rings; beads
// run along the synapses carrying the most this settle (presynaptic activity times |weight|),
// arriving as the front arrives; the motor neuron the move was read from flashes when the front
// reaches it and its sweeps are done; the waves decay between moves.

export const MOTOR_RGB = [[120, 180, 255], [255, 230, 140], [255, 110, 210]];
const REGION_RGB = { association: [110, 170, 255], prefrontal: [80, 235, 200], other: [180, 190, 220] };
const YOU = [45, 226, 255];
const IT = [255, 79, 216];
export const FRONT_MS = 380;  // the front's time from the origin to the farthest neuron
export const PLAY_MS = 260;   // a neuron's own sweeps, once the front reaches it
const RING_MS = 760;
export const ARROWS = ["←", "↑", "→"];
const HEADING_DIR = [[0, -1], [1, 0], [0, 1], [-1, 0]]; // same, right, opposite, left (ahead is up)

export const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;

export function glow(rgb, size = 64, core = 0.5) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d");
  const grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  grad.addColorStop(0, rgba([255, 255, 255], 1));
  grad.addColorStop(0.12, rgba(rgb, 0.95));
  grad.addColorStop(core * 0.6, rgba(rgb, 0.32));
  grad.addColorStop(1, rgba(rgb, 0));
  g.fillStyle = grad;
  g.fillRect(0, 0, size, size);
  return c;
}

export function bytesOf(text) {
  const raw = atob(text);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

export class RippleView {
  constructor(canvas) {
    this.canvas = canvas;
    this.frontMs = FRONT_MS;
    this.ctx = canvas.getContext("2d");
    this.desc = null;
    this.waves = [];
    this.rings = [];
    this.beads = [];
    this.flashes = [];
    this.obs = null;
    this.info = {};
    this.static = document.createElement("canvas");
    this.layer = document.createElement("canvas");
    this.dots = document.createElement("canvas");
    this.sprites = {};
    for (const [k, v] of Object.entries(REGION_RGB)) this.sprites[k] = glow(v);
    this.motorSprites = MOTOR_RGB.map((c) => glow(c, 96, 0.7));
    this.white = glow([255, 255, 255]);
    this.pink = glow(IT);
    this.cyan = glow(YOU);
    new ResizeObserver(() => this.resize()).observe(canvas);
  }

  setBrain(desc) {
    this.desc = desc;
    this.n = desc.neurons;
    const [s0, sn] = desc.populations.sensory;
    this.offset = s0 + sn;
    this.m = this.n - this.offset;
    const off = desc.play && desc.play.working_memory_amplitude === 0;
    this.regions = Object.entries(desc.populations)
      .filter(([name]) => name !== "sensory")
      .map(([name, [start, count]]) => ({ name, start, count, off: off && name === "prefrontal" }))
      .sort((a, b) => a.start - b.start);
    this.motor = this.regions.find((r) => r.name === "motor");
    this.regionOf = new Array(this.m);
    this.hidden = new Uint8Array(this.n);
    for (const r of this.regions) {
      for (let i = r.start; i < r.start + r.count; i++) {
        this.regionOf[i - this.offset] = r;
        if (r.off) this.hidden[i] = 1;
      }
    }
    // Synapses to or from a population that is switched off are not drawn.
    const e = desc.edges;
    const keep = [];
    for (let k = 0; k < e.pre.length; k++) if (!this.hidden[e.pre[k]] && !this.hidden[e.post[k]]) keep.push(k);
    this.edges = {
      pre: Int32Array.from(keep, (k) => e.pre[k]), post: Int32Array.from(keep, (k) => e.post[k]),
      w: Float32Array.from(keep, (k) => e.w[k]), m: keep.length,
    };
    let max = 1e-9;
    for (let k = 0; k < this.edges.m; k++) max = Math.max(max, Math.abs(this.edges.w[k]));
    this.edges.max = max;
    this.reach = desc.reach ? bytesOf(desc.reach) : new Uint8Array(sn);
    this.spec = Object.fromEntries(desc.retina.map((g) => [g.key, g]));
    this.last = new Float32Array(this.m);
    this.shown = new Float32Array(this.m);
    this.scale = {};
    for (const r of this.regions) this.scale[r.name] = 0.15;
    this.W = 0;
    this.resize();
  }

  // ---- layout ----------------------------------------------------------------------------
  resize() {
    if (!this.desc) return;
    const rect = this.canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const W = Math.round(rect.width * dpr), H = Math.round(rect.height * dpr);
    if (W < 20 || H < 20 || (W === this.W && H === this.H)) return;
    this.W = W; this.H = H; this.dpr = dpr;
    for (const c of [this.canvas, this.static, this.layer]) { c.width = W; c.height = H; }
    this.layout();
    this.drawStatic();
    this.drawInputs();
    if (this.onLayout) this.onLayout(); // the page lays its explanation spots out again
  }

  layout() {
    const { W, H, dpr } = this;
    const n = this.n;
    this.px = new Float32Array(n);
    this.py = new Float32Array(n);
    this.pr = new Float32Array(n);
    const m = 16 * dpr;
    this.landscape = W > H * 1.15 && W / dpr >= 520;
    let field, eyes, arrow, disk;
    if (!this.landscape) {
      // Top: an eye, the field, an eye (and the heading arrow under it); then the association
      // module; the motor row at the bottom.
      const S = Math.min(W * 0.42, H * 0.28);
      field = { x: (W - S) / 2, y: m, S };
      const E = Math.min(S * 0.3, ((W - S) / 2 - m) * 0.42);
      const side = (W - S) / 4 + m * 0.25;
      eyes = [{ x: side, y: m + S * 0.42, R: E }, { x: W - side, y: m + S * 0.42, R: E }];
      arrow = { x: W - side, y: m + S * 0.42 + E + Math.max(16 * dpr, E * 0.75), R: Math.max(9 * dpr, E * 0.42) };
      const motorAt = H - m - 12 * dpr;
      const top = m + S + 18 * dpr, bottom = motorAt - 36 * dpr;
      const R = Math.min(W * 0.36, (bottom - top) * 0.48);
      disk = { cx: W / 2, cy: (top + bottom) / 2, R };
      const step = Math.min(W * 0.24, 110 * dpr);
      for (let k = 0; k < 3; k++) this.placeMotor(k, W / 2 + (k - 1) * step, motorAt, 9 * dpr);
    } else {
      // Left to right: the field with the eyes and the arrow beside it, the association
      // module, the motor column.
      const S = Math.min(H * 0.6, W * 0.24);
      field = { x: m, y: (H - S) / 2, S };
      const E = Math.min(S * 0.24, H * 0.14);
      const ex = m + S + E + 14 * dpr;
      eyes = [{ x: ex, y: H / 2 - E * 1.25 - 6 * dpr, R: E }, { x: ex, y: H / 2 + E * 1.25 + 6 * dpr, R: E }];
      arrow = { x: ex, y: H / 2, R: Math.max(8 * dpr, E * 0.35) };
      const motorAt = W - m - 14 * dpr;
      const x0 = ex + E + 20 * dpr, x1 = motorAt - 40 * dpr;
      const R = Math.min((x1 - x0) * 0.48, H * 0.44);
      disk = { cx: (x0 + x1) / 2, cy: H / 2, R };
      const step = Math.min(H * 0.27, 80 * dpr);
      for (let k = 0; k < 3; k++) this.placeMotor(k, motorAt, H / 2 + (k - 1) * step, 9 * dpr);
    }
    this.placeInputs(field, eyes, arrow);
    // The association module (and any other live population) as a disk.
    this.disks = [];
    const live = this.regions.filter((r) => r.name !== "motor" && !r.off);
    live.forEach((r, j) => {
      const R = disk.R / Math.sqrt(live.length);
      const cx = disk.cx + (live.length > 1 ? (j - (live.length - 1) / 2) * R * 2.3 : 0);
      this.disks.push({ r, cx, cy: disk.cy, R });
      const dot = Math.max(1.2 * dpr, Math.min(3.6 * dpr, (R / Math.sqrt(r.count)) * 0.55));
      for (let q = 0; q < r.count; q++) {
        const i = r.start + q;
        const rad = R * Math.sqrt((q + 0.5) / r.count);
        const a = q * 2.399963;
        this.px[i] = cx + rad * Math.cos(a);
        this.py[i] = disk.cy + rad * Math.sin(a);
        this.pr[i] = dot;
      }
    });
    this.dots.width = this.dots.height = Math.max(8, Math.round(field.S));
  }

  // The inputs where the sense lays them out: the field, the two eyes, the heading arrow.
  placeInputs(field, eyes, arrow) {
    this.field = field;
    this.eyes = eyes;
    this.arrow = arrow;
    // The field: the four planes share the cells.
    const c = field.S / 24;
    for (const key of ["blocked", "trail", "self", "you"]) {
      const g = this.spec[key];
      for (let r = 0; r < g.rows; r++) for (let k = 0; k < g.cols; k++) {
        const i = g.start + r * g.cols + k;
        this.px[i] = field.x + (k + 0.5) * c;
        this.py[i] = field.y + (r + 0.5) * c;
      }
    }
    // The foveas: radial eyes around the head cell (row 5, column 4).
    ["fovea", "fovea_you"].forEach((key, e) => {
      const g = this.spec[key];
      const eye = eyes[e];
      const [hr, hc] = g.head || [5, 4];
      const far = Math.hypot(Math.max(hr, g.rows - 1 - hr), Math.max(hc, g.cols - 1 - hc));
      for (let r = 0; r < g.rows; r++) for (let k = 0; k < g.cols; k++) {
        const i = g.start + r * g.cols + k;
        const dr = r - hr, dc = k - hc;
        const d = Math.hypot(dr, dc);
        const rad = d ? eye.R * 0.94 * Math.pow(d / far, 0.75) : 0;
        const a = Math.atan2(dr, dc);
        this.px[i] = eye.x + rad * Math.cos(a);
        this.py[i] = eye.y + rad * Math.sin(a);
      }
    });
    // The heading: its four inputs at the four directions of the arrow.
    const hg = this.spec.heading;
    for (let k = 0; k < 4; k++) {
      this.px[hg.start + k] = arrow.x + HEADING_DIR[k][0] * arrow.R;
      this.py[hg.start + k] = arrow.y + HEADING_DIR[k][1] * arrow.R;
    }
  }

  placeMotor(k, x, y, r) {
    const i = this.motor.start + k;
    this.px[i] = x;
    this.py[i] = y;
    this.pr[i] = r;
  }

  drawStatic() {
    const g = this.static.getContext("2d");
    const { W, H, dpr } = this;
    g.clearRect(0, 0, W, H);
    for (const d of this.disks) {
      const rgb = REGION_RGB[d.r.name] || REGION_RGB.other;
      const grad = g.createRadialGradient(d.cx, d.cy, 0, d.cx, d.cy, d.R * 1.5);
      grad.addColorStop(0, rgba(rgb, 0.07));
      grad.addColorStop(0.7, rgba(rgb, 0.025));
      grad.addColorStop(1, rgba(rgb, 0));
      g.fillStyle = grad;
      g.beginPath(); g.arc(d.cx, d.cy, d.R * 1.5, 0, Math.PI * 2); g.fill();
    }
    // The strongest synapses, very faint.
    const e = this.edges;
    g.lineWidth = Math.max(0.5, 0.5 * dpr);
    for (const sign of [1, -1]) {
      g.strokeStyle = sign > 0 ? "rgba(120,180,255,0.035)" : "rgba(255,100,200,0.03)";
      g.beginPath();
      for (let k = 0; k < e.m; k++) {
        if ((e.w[k] > 0) !== (sign > 0)) continue;
        g.moveTo(this.px[e.pre[k]], this.py[e.pre[k]]);
        g.lineTo(this.px[e.post[k]], this.py[e.post[k]]);
      }
      g.stroke();
    }
    // The field: a soft frame and a lattice of faint dots, brighter where the inputs are wired in.
    const f = this.field;
    const c = f.S / 24;
    const pad = c * 0.8;
    g.fillStyle = "rgba(0,0,0,0.6)";
    roundRect(g, f.x - pad, f.y - pad, f.S + 2 * pad, f.S + 2 * pad, 10 * dpr);
    g.fill();
    g.strokeStyle = "rgba(120,190,255,0.12)";
    g.lineWidth = dpr;
    g.stroke();
    const planes = ["blocked", "trail", "self", "you"].map((k) => this.spec[k].start);
    for (let r = 0; r < 24; r++) for (let k = 0; k < 24; k++) {
      let v = 0;
      for (const s of planes) v = Math.max(v, this.reach[s + r * 24 + k] / 255);
      g.fillStyle = `rgba(${140 + 60 * v},${150 + 30 * v},255,${0.06 + 0.22 * v})`;
      g.beginPath();
      g.arc(f.x + (k + 0.5) * c, f.y + (r + 0.5) * c, Math.max(0.6 * dpr, c * (0.08 + 0.08 * v)), 0, Math.PI * 2);
      g.fill();
    }
    // The eyes: two thin rings and the faint cells.
    this.eyes.forEach((eye, e) => {
      const rgb = e ? YOU : [210, 228, 255];
      const grad = g.createRadialGradient(eye.x, eye.y, 0, eye.x, eye.y, eye.R * 1.2);
      grad.addColorStop(0, "rgba(0,0,0,0.75)");
      grad.addColorStop(1, "rgba(0,0,0,0)");
      g.fillStyle = grad;
      g.beginPath(); g.arc(eye.x, eye.y, eye.R * 1.2, 0, Math.PI * 2); g.fill();
      for (const q of [1, 0.55]) {
        g.strokeStyle = rgba(rgb, q === 1 ? 0.22 : 0.1);
        g.lineWidth = dpr;
        g.beginPath(); g.arc(eye.x, eye.y, eye.R * q, 0, Math.PI * 2); g.stroke();
      }
      const spec = this.spec[e ? "fovea_you" : "fovea"];
      for (let j = 0; j < spec.rows * spec.cols; j++) {
        const i = spec.start + j;
        g.fillStyle = rgba(rgb, 0.08 + 0.2 * (this.reach[i] / 255));
        g.beginPath(); g.arc(this.px[i], this.py[i], Math.max(0.6 * dpr, eye.R * 0.025), 0, Math.PI * 2); g.fill();
      }
    });
    const a = this.arrow;
    g.strokeStyle = "rgba(45,226,255,0.16)";
    g.lineWidth = dpr;
    g.beginPath(); g.arc(a.x, a.y, a.R * 1.35, 0, Math.PI * 2); g.stroke();
    // Motor glyphs.
    g.font = `600 ${11 * dpr}px ui-monospace, Menlo, monospace`;
    g.fillStyle = "rgba(220,230,255,0.45)";
    g.textAlign = "center";
    g.textBaseline = "middle";
    for (let k = 0; k < 3; k++) {
      const i = this.motor.start + k;
      g.fillText(ARROWS[k], this.px[i], this.py[i] - 20 * dpr);
    }
  }

  // The inputs of the current settle, on their own layer: drawn once per move.
  drawInputs() {
    if (!this.W || !this.field) return;
    const g = this.layer.getContext("2d");
    const { dpr } = this;
    g.clearRect(0, 0, this.W, this.H);
    const x = this.obs;
    if (!x) return;
    const f = this.field;
    const c = f.S / 24;
    const sp = this.spec;
    // The field's dots on a small canvas, then laid down twice: blurred (the glow) and sharp.
    const d = this.dots.getContext("2d");
    d.clearRect(0, 0, this.dots.width, this.dots.height);
    d.globalCompositeOperation = "lighter";
    const heads = [];
    for (let r = 0; r < 24; r++) for (let k = 0; k < 24; k++) {
      const j = r * 24 + k;
      const cx = (k + 0.5) * c, cy = (r + 0.5) * c;
      if (x[sp.self.start + j]) heads.push([cx, cy, IT]);
      if (x[sp.you.start + j]) heads.push([cx, cy, YOU]);
      if (!x[sp.blocked.start + j]) continue;
      const yours = x[sp.trail.start + j];
      d.fillStyle = rgba(yours ? YOU : IT, 0.55);
      d.beginPath(); d.arc(cx, cy, c * 0.26, 0, Math.PI * 2); d.fill();
    }
    for (const [cx, cy, rgb] of heads) {
      const R = c * 2.2;
      d.drawImage(rgb === IT ? this.pink : this.cyan, cx - R, cy - R, 2 * R, 2 * R);
    }
    g.globalCompositeOperation = "lighter";
    g.save();
    g.filter = `blur(${Math.max(2, 3 * dpr)}px)`;
    g.globalAlpha = 0.8;
    g.drawImage(this.dots, f.x, f.y);
    g.restore();
    g.globalAlpha = 0.85;
    g.drawImage(this.dots, f.x, f.y);
    g.globalAlpha = 1;
    // The eyes.
    this.eyes.forEach((eye, e) => {
      const spec = sp[e ? "fovea_you" : "fovea"];
      const rgb = e ? YOU : [220, 232, 255];
      for (let j = 0; j < spec.rows * spec.cols; j++) {
        const i = spec.start + j;
        if (!x[i]) continue;
        const R = Math.max(2 * dpr, eye.R * (e ? 0.4 : 0.12));
        g.globalAlpha = e ? 1 : 0.75;
        g.drawImage(e ? this.cyan : this.white, this.px[i] - R, this.py[i] - R, 2 * R, 2 * R);
      }
      g.globalAlpha = 0.9;
      const R = Math.max(3 * dpr, eye.R * 0.16);
      g.drawImage(this.pink, eye.x - R, eye.y - R, 2 * R, 2 * R); // its head, the eye's centre
      void rgb;
    });
    g.globalAlpha = 1;
    // The heading: one arrow.
    let h = 0;
    for (let k = 0; k < 4; k++) if (x[sp.heading.start + k]) h = k;
    const a = this.arrow;
    const [ux, uy] = HEADING_DIR[h];
    g.globalCompositeOperation = "source-over";
    g.save();
    g.shadowColor = "rgba(45,226,255,0.9)";
    g.shadowBlur = 10 * dpr;
    g.strokeStyle = "#7ff0ff";
    g.lineWidth = 2 * dpr;
    g.lineCap = "round";
    g.lineJoin = "round";
    const L = a.R * 1.05;
    const tx = a.x + ux * L, ty = a.y + uy * L;
    g.beginPath();
    g.moveTo(a.x - ux * L, a.y - uy * L); g.lineTo(tx, ty);
    g.moveTo(tx - ux * L * 0.55 - uy * L * 0.45, ty - uy * L * 0.55 + ux * L * 0.45);
    g.lineTo(tx, ty);
    g.lineTo(tx - ux * L * 0.55 + uy * L * 0.45, ty - uy * L * 0.55 - ux * L * 0.45);
    g.stroke();
    g.restore();
  }

  // ---- a move ------------------------------------------------------------------------------
  /** One settle from the host (state.format "field"). */
  push(state) {
    if (!this.desc) return;
    this.info = state.brain || {};
    const now = performance.now();
    const before = this.obs;
    if (state.obs) {
      this.obs = bytesOf(state.obs);
      this.drawInputs();
    }
    if (!state.nframes || !state.frames || !this.obs) return;
    const m = this.m;
    const raw = bytesOf(state.frames);
    const frames = new Float32Array(raw.buffer, raw.byteOffset, raw.byteLength / 4);
    const nf = state.nframes;
    if (frames.length < nf * m) return;
    for (const r of this.regions) {
      let peak = 0;
      const lo = r.start - this.offset;
      for (let f = 0; f < nf; f++) for (let j = 0; j < r.count; j++) peak = Math.max(peak, frames[f * m + lo + j]);
      this.scale[r.name] = Math.max(0.03, peak, this.scale[r.name] * 0.9);
    }
    // The front starts where the active inputs are, weighted by how strongly each is wired in.
    let sx = 0, sy = 0, sw = 0;
    for (let i = 0; i < this.offset; i++) {
      if (!this.obs[i]) continue;
      const w = 0.05 + this.reach[i] / 255;
      sx += w * this.px[i]; sy += w * this.py[i]; sw += w;
    }
    const origin = sw ? [sx / sw, sy / sw] : [this.field.x + this.field.S / 2, this.field.y + this.field.S / 2];
    const { delay, far } = this.delays(origin);
    const final = (nf - 1) * m;
    const sweeps = Math.max(1, this.info.sweeps || nf - 1);
    const at = state.frame_sweeps || [...Array(nf).keys()];
    const wave = { t0: now, frames, nf, at, sweeps, dense: nf === sweeps + 1, origin, far, delay, prev: this.last.slice() };
    // Inputs that changed since the last move sparkle as the front leaves.
    if (before) {
      let shown = 0;
      for (let i = 0; i < this.obs.length && shown < 60; i++) {
        if (this.obs[i] !== before[i] && this.obs[i]) {
          this.flashes.push({ i, t: now + delay[i] * this.frontMs, life: 420 });
          shown++;
        }
      }
    }
    // Rings where the state moved most since the last move.
    const moved = [];
    for (let i = 0; i < m; i++) {
      const reg = this.regionOf[i];
      if (reg.off) continue;
      const d = Math.abs(frames[final + i] - this.last[i]) / this.scale[reg.name];
      if (d > 0.04) moved.push([d, i]);
    }
    moved.sort((a, b) => b[0] - a[0]);
    for (const [d, i] of moved.slice(0, 46)) {
      const j = i + this.offset;
      this.rings.push({ x: this.px[j], y: this.py[j], t: now + delay[j] * this.frontMs, d: Math.min(1, d),
        rgb: REGION_RGB[this.regionOf[i].name] || REGION_RGB.other, R: this.pr[j] * (5 + 7 * Math.min(1, d)) });
    }
    for (let i = 0; i < m; i++) this.last[i] = frames[final + i];
    // Beads along the synapses carrying the most this settle.
    const e = this.edges;
    const scored = [];
    for (let k = 0; k < e.m; k++) {
      const p = e.pre[k];
      const a = p < this.offset ? this.obs[p] : Math.max(0, this.last[p - this.offset]) / this.scale[this.regionOf[p - this.offset].name];
      if (a <= 0.1) continue;
      scored.push([(a * Math.abs(e.w[k])) / e.max, k]);
    }
    scored.sort((a, b) => b[0] - a[0]);
    const cap = this.W / this.dpr < 520 ? 90 : 170;
    for (const [s, k] of scored.slice(0, cap)) {
      const p = e.pre[k], q = e.post[k];
      this.beads.push({ k, t: now + delay[p] * this.frontMs, dur: Math.max(90, (delay[q] - delay[p]) * this.frontMs + 60), s: Math.min(1, 0.35 + s * 1.5) });
    }
    // The motor neuron the move was read from flashes when its sweeps are done.
    if (Number.isInteger(this.info.choice)) {
      const j = this.motor.start + this.info.choice;
      const t = now + delay[j] * this.frontMs + PLAY_MS;
      this.rings.push({ x: this.px[j], y: this.py[j], t, d: 1, rgb: MOTOR_RGB[this.info.choice], R: this.pr[j] * 3.6, motor: true });
      wave.flash = { j, t };
    }
    this.waves.push(wave);
    while (this.waves.length > 6) this.waves.shift();
    if (this.rings.length > 400) this.rings.splice(0, this.rings.length - 400);
    if (this.beads.length > 900) this.beads.splice(0, this.beads.length - 900);
  }

  // When the front reaches each neuron (0..1): by distance from the origin.
  delays(origin) {
    const delay = new Float32Array(this.n);
    let far = 1;
    for (let i = 0; i < this.n; i++) {
      if (this.hidden[i]) continue;
      delay[i] = Math.hypot(this.px[i] - origin[0], this.py[i] - origin[1]);
      if (delay[i] > far) far = delay[i];
    }
    for (let i = 0; i < this.n; i++) delay[i] /= far;
    return { delay, far };
  }

  clear() {
    this.waves = [];
    this.rings = [];
    this.beads = [];
    this.flashes = [];
    this.info = {};
    if (this.shown) this.shown.fill(0);
  }

  // The activation of non-sensory neuron i (0-based past the inputs) at time `now`.
  value(i, now) {
    const j = i + this.offset;
    for (let w = this.waves.length - 1; w >= 0; w--) {
      const wave = this.waves[w];
      const dt = now - wave.t0 - wave.delay[j] * this.frontMs;
      if (dt < 0) continue;
      const s = Math.min(1, dt / PLAY_MS) * wave.sweeps;
      let f1;
      if (wave.dense) f1 = Math.min(wave.nf - 1, Math.ceil(s));
      else { f1 = 0; while (f1 < wave.nf - 1 && wave.at[f1] < s) f1++; }
      const f0 = Math.max(0, f1 - 1);
      const span = wave.at[f1] - wave.at[f0];
      const t = span > 0 ? Math.min(1, Math.max(0, (s - wave.at[f0]) / span)) : 1;
      const a = wave.frames[f0 * this.m + i], b = wave.frames[f1 * this.m + i];
      return { v: a + (b - a) * t, since: dt, wave };
    }
    return null;
  }

  // The fronts: a ring of light per move, leaving the active inputs and crossing the brain.
  drawFronts(g, now) {
    const { dpr } = this;
    for (const w of this.waves) {
      const p = (now - w.t0) / (this.frontMs * 1.15);
      if (p < 0 || p > 1) continue;
      const [ox, oy] = w.origin;
      const R = p * w.far * 1.15;
      const a = 0.16 * (1 - p) * (1 - p);
      const band = 22 * dpr;
      const grad = g.createRadialGradient(ox, oy, Math.max(0, R - band), ox, oy, R + band * 0.4);
      grad.addColorStop(0, "rgba(80,160,255,0)");
      grad.addColorStop(0.75, `rgba(120,200,255,${a})`);
      grad.addColorStop(1, "rgba(120,200,255,0)");
      g.fillStyle = grad;
      g.beginPath(); g.arc(ox, oy, R + band * 0.4, 0, Math.PI * 2); g.fill();
    }
  }

  // ---- the frame ---------------------------------------------------------------------------
  frame(now) {
    if (!this.desc || !this.W) return;
    const g = this.ctx;
    const { W, H, dpr, m } = this;
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalCompositeOperation = "source-over";
    g.globalAlpha = 1;
    g.clearRect(0, 0, W, H);
    g.drawImage(this.static, 0, 0);
    g.drawImage(this.layer, 0, 0);
    g.globalCompositeOperation = "lighter";

    this.drawFronts(g, now);

    // Input sparkles.
    const keepF = [];
    for (const f of this.flashes) {
      const dt = now - f.t;
      if (dt > f.life) continue;
      keepF.push(f);
      if (dt < 0) continue;
      const a = 1 - dt / f.life;
      const r = (4 + 10 * a) * dpr;
      g.globalAlpha = a;
      g.drawImage(this.white, this.px[f.i] - r, this.py[f.i] - r, 2 * r, 2 * r);
    }
    this.flashes = keepF;
    g.globalAlpha = 1;

    // Beads along the synapses.
    const e = this.edges;
    const keepB = [];
    g.lineCap = "round";
    for (const b of this.beads) {
      const dt = now - b.t;
      if (dt > b.dur + 140) continue;
      keepB.push(b);
      if (dt < 0) continue;
      const k = b.k;
      const x0 = this.px[e.pre[k]], y0 = this.py[e.pre[k]];
      const x1 = this.px[e.post[k]], y1 = this.py[e.post[k]];
      const ph = Math.min(1, dt / b.dur);
      const fade = dt > b.dur ? 1 - (dt - b.dur) / 140 : 1;
      const tail = Math.max(0, ph - 0.22);
      const exc = e.w[k] > 0;
      g.strokeStyle = exc ? `rgba(150,210,255,${0.32 * b.s * fade})` : `rgba(255,110,200,${0.3 * b.s * fade})`;
      g.lineWidth = (0.8 + 1.4 * b.s) * dpr;
      g.beginPath();
      g.moveTo(x0 + (x1 - x0) * tail, y0 + (y1 - y0) * tail);
      g.lineTo(x0 + (x1 - x0) * ph, y0 + (y1 - y0) * ph);
      g.stroke();
      const r = (2.2 + 3.2 * b.s) * dpr;
      g.globalAlpha = Math.min(1, b.s * fade);
      g.drawImage(exc ? this.cyan : this.pink, x0 + (x1 - x0) * ph - r, y0 + (y1 - y0) * ph - r, 2 * r, 2 * r);
      g.globalAlpha = 1;
    }
    this.beads = keepB;

    // Neurons: brightness and halo track the recorded activation as the front plays it.
    for (let i = 0; i < m; i++) {
      const reg = this.regionOf[i];
      if (reg === this.motor || reg.off) continue;
      const j = i + this.offset;
      const got = this.value(i, now);
      const sc = this.scale[reg.name];
      let v = got ? Math.max(0, got.v) / sc : this.shown[i] * 0.98;
      let boost = 0;
      if (got && got.since < 300) boost = (Math.abs(got.v - got.wave.prev[i]) / sc) * (1 - got.since / 300);
      this.shown[i] += (v - this.shown[i]) * 0.5;
      v = Math.min(1, this.shown[i]);
      const spr = this.sprites[reg.name] || this.sprites.other;
      const r = this.pr[j];
      const halo = Math.min(1, v + boost * 1.5);
      if (halo > 0.03) {
        const R = r * (2 + 6 * halo);
        g.globalAlpha = Math.min(1, 0.12 + halo * 0.8);
        g.drawImage(spr, this.px[j] - R, this.py[j] - R, 2 * R, 2 * R);
      }
      g.globalAlpha = 0.18 + 0.82 * v;
      const R2 = r * 1.15;
      g.drawImage(v > 0.65 ? this.white : spr, this.px[j] - R2, this.py[j] - R2, 2 * R2, 2 * R2);
    }
    g.globalAlpha = 1;

    // Rings.
    const keepR = [];
    for (const ring of this.rings) {
      const dt = now - ring.t;
      const life = ring.motor ? RING_MS * 1.3 : RING_MS;
      if (dt > life) continue;
      keepR.push(ring);
      if (dt < 0) continue;
      const p = dt / life;
      const R = ring.R * (0.25 + Math.sqrt(p) * (ring.motor ? 1.8 : 1.2));
      g.strokeStyle = rgba(ring.rgb, (ring.motor ? 0.9 : 0.5) * ring.d * (1 - p) * (1 - p));
      g.lineWidth = (ring.motor ? 2.4 : 1.2) * dpr * (1 - p * 0.6);
      g.beginPath(); g.arc(ring.x, ring.y, R, 0, Math.PI * 2); g.stroke();
    }
    this.rings = keepR;

    // Motor neurons; the chosen one flashes when the front has reached it and settled.
    const latest = this.waves[this.waves.length - 1];
    for (let k = 0; k < 3; k++) {
      const j = this.motor.start + k;
      const got = this.value(j - this.offset, now);
      const v = got ? Math.min(1, Math.max(0, got.v) / this.scale.motor) : 0.1;
      let flare = 0;
      if (latest && latest.flash && latest.flash.j === j) {
        const dt = now - latest.flash.t;
        if (dt >= 0) flare = Math.exp(-dt / 420);
      }
      const x = this.px[j], y = this.py[j], r = this.pr[j];
      const R = r * (2.4 + 2.6 * v + 6 * flare);
      g.globalAlpha = Math.min(1, 0.25 + 0.55 * v + 0.6 * flare);
      g.drawImage(this.motorSprites[k], x - R, y - R, 2 * R, 2 * R);
      g.globalAlpha = 1;
      g.globalCompositeOperation = "source-over";
      g.fillStyle = flare > 0.4 ? "#ffffff" : rgba(MOTOR_RGB[k], 0.3 + 0.7 * v);
      g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill();
      g.strokeStyle = rgba(MOTOR_RGB[k], 0.6 + 0.4 * flare);
      g.lineWidth = 1.2 * dpr;
      g.beginPath(); g.arc(x, y, r + 3 * dpr + flare * 4 * dpr, 0, Math.PI * 2); g.stroke();
      g.globalCompositeOperation = "lighter";
    }
    g.globalCompositeOperation = "source-over";
    while (this.waves.length > 1 && now - this.waves[0].t0 > this.frontMs + PLAY_MS + 200) this.waves.shift();

    this.overlay(g, now);

    // The only words: sweeps and residual.
    const info = this.info;
    if (info && info.sweeps) {
      const res = typeof info.residual === "number" ? info.residual.toExponential(0) : "-";
      g.font = `500 ${10 * dpr}px ui-monospace, Menlo, monospace`;
      g.textAlign = "right";
      g.textBaseline = "bottom";
      g.fillStyle = "rgba(150,170,200,0.55)";
      g.fillText(`${info.sweeps} sweeps · residual ${res}`, W - 10 * dpr, H - 8 * dpr);
    }
  }
}

RippleView.prototype.overlay = function () {};

export function roundRect(g, x, y, w, h, r) {
  g.beginPath();
  g.moveTo(x + r, y);
  g.arcTo(x + w, y, x + w, y + h, r);
  g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r);
  g.arcTo(x, y, x + w, y, r);
  g.closePath();
}
