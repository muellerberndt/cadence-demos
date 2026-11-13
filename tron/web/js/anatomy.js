// The brain as anatomy. The same neurons, the same recorded sweeps and the same roles as the layer
// view (deep.js), laid out as a brain seen from the side, front to the left:
//
//   the field, the two foveas and the heading      -> the visual cortex, at the back
//   L1, L2, ... (module_0, module_1, ...), the top -> association cortex, back to front
//   the prefrontal population (the working trace)  -> the frontal pole; dark when the trace is off
//   the three motor neurons                        -> the motor strip, on top
//   the greedy pick among them                     -> drawn below as the selection nucleus (the
//                                                     role the basal ganglia play in an animal)
//   the dopamine nucleus                           -> drawn dark: this brain is frozen while you
//                                                     play, it receives no reward signal
//
// Every pathway of the connectome is a curved fibre tract between its regions; the field's
// projection into L1 passes through a relay point drawn where the thalamus would sit. A tract's
// brightness is the live sum of |weight x presynaptic activation| over its drawn synapses, warm
// for excitatory, cool for inhibitory. The settle plays as a wave: region by region, each neuron
// replaying its own recorded sweeps, with the largest potential repair per sweep falling to rest.
// The names say which role a population plays, not that it is that structure.

import { DeepView, EYE_TEXT, partText } from "./deep.js";
import { RippleView, glow, rgba, MOTOR_RGB, ARROWS, PLAY_MS } from "./ripple.js";

const MONO = "ui-monospace, Menlo, monospace";
const EXC_RGB = [255, 176, 92];
const INH_RGB = [120, 140, 255];
const AMBER = [255, 196, 90];
const FAMILY_NAME = { ahead: "ahead", left: "left", right: "right", edge: "edges", opponent: "opponent",
  territory: "territory", apart: "walled apart", cutoff: "cut-off", teacher: "teacher", other: "other roles",
  mixed: "mixed", silent: "silent", neurons: "neurons" };
const ROLE = { hidden: "association cortex", trace: "prefrontal: the working trace", motor: "motor strip" };

// Where a region sits in the side view (unit box, front at x = 0), by its place in the chain.
function slotsFor(hidden) {
  if (hidden <= 1) return [{ cx: 0.45, cy: 0.44, name: "association cortex" }];
  const out = [];
  for (let j = 0; j < hidden; j++) {
    const t = j / (hidden - 1);
    out.push({ cx: 0.63 - 0.39 * t, cy: 0.42 + 0.14 * Math.sin(Math.PI * t), name: j === 0 ? "posterior association"
      : j === hidden - 1 ? "frontal association" : "temporal association" });
  }
  return out;
}

export class AnatomyView extends DeepView {
  constructor(canvas, card) {
    super(canvas, card);
    this.anatomy = true;
    this.repair = null;
    this.selSprites = MOTOR_RGB.map((c) => glow(c, 96, 0.55));
    this.warm = glow(EXC_RGB, 64, 0.4);
  }

  // ---- layout ----------------------------------------------------------------------------
  layout() {
    if (!this.layers) return super.layout();
    const { W, H, dpr } = this;
    const n = this.n;
    this.px = new Float32Array(n);
    this.py = new Float32Array(n);
    this.pr = new Float32Array(n);
    this.disks = [];
    // The brain's box: as large as the panel allows, its aspect between 0.9 and 1.45.
    const m = 10 * dpr;
    const aspect = Math.max(0.9, Math.min(1.45, (W - 2 * m) / Math.max(1, H - 40 * dpr)));
    const bw = Math.min(W - 2 * m, (H - 40 * dpr) * aspect);
    const bh = bw / aspect;
    const ox = (W - bw) / 2, oy = Math.max(m + 26 * dpr, (H - 30 * dpr - bh) / 2);
    const P = (x, y) => [ox + x * bw, oy + y * bh];
    this.box = { ox, oy, bw, bh, P };
    // The visual cortex at the back: the field, then the foveas and the heading below it.
    const S = Math.min(bw * 0.24, bh * 0.28);
    const [fx, fy] = P(0.85, 0.4);
    const field = { x: fx - S / 2, y: fy - S / 2, S };
    const E = Math.min(S * 0.28, bh * 0.08);
    const eyes = [{ x: fx - S * 0.3, y: fy + S / 2 + E + 10 * dpr, R: E }, { x: fx + S * 0.3, y: fy + S / 2 + E + 10 * dpr, R: E }];
    const arrow = { x: fx, y: fy + S / 2 + E + 10 * dpr, R: Math.max(6 * dpr, E * 0.38) };
    this.placeInputs(field, eyes, arrow);
    // Association regions from the back to the front, sized by their neuron counts.
    const hidden = this.layers.filter((L) => L.kind === "hidden");
    const slots = slotsFor(hidden.length);
    const big = Math.max(...hidden.map((L) => L.count), 1);
    const bands = [];
    hidden.forEach((L, j) => {
      const s = slots[j];
      const k = Math.sqrt(L.count / big);
      const R = Math.min(bw, bh) * (0.07 + 0.075 * k);
      const rx = R * 1.15, ry = R;
      const [cx, cy] = P(s.cx, s.cy);
      bands.push(this.band(L, cx, cy, rx, ry, s.name));
    });
    const trace = this.layers.find((L) => L.kind === "trace");
    if (trace) {
      const [cx, cy] = P(0.1, 0.47);
      bands.push(this.band(trace, cx, cy, bw * 0.05, bh * 0.07, "frontal pole"));
    }
    const motor = this.layers.find((L) => L.kind === "motor");
    {
      const [cx, cy] = P(0.43, 0.13);
      bands.push(this.band(motor, cx, cy, bw * 0.1, bh * 0.035, "motor strip"));
    }
    this.bands = bands;
    for (const b of bands) this.placeLayer(b);
    // Nuclei that are drawn, not populations: the relay, the selection, the dopamine nucleus.
    const at = (x, y, r) => { const [X, Y] = P(x, y); return { x: X, y: Y, r: r * bw }; };
    this.nuclei = {
      relay: at(0.68, 0.64, 0.03),
      select: at(0.42, 0.72, 0.045),
      dopamine: at(0.56, 0.86, 0.024),
    };
    // Tracts: one per pathway between drawn regions.
    this.buildTracts();
    if (this.card) {
      const css = (v) => `${Math.round(v / dpr)}px`;
      Object.assign(this.card.style, { width: css(Math.min(260 * dpr, W * 0.42)), left: "auto", right: css(8 * dpr), top: css(8 * dpr) });
    }
    this.dots.width = this.dots.height = Math.max(8, Math.round(field.S));
  }

  band(L, cx, cy, rx, ry, where) {
    const dpr = this.dpr;
    // The neurons fill the rectangle inscribed in the region's ellipse.
    const iw = rx * 1.5, ih = ry * 1.45;
    const dots = { x: cx - iw / 2, y: cy - ih / 2 + 4 * dpr, w: iw, h: ih };
    return { L, where, shape: { cx, cy, rx, ry }, rect: { x: cx - rx, y: cy - ry, w: 2 * rx, h: 2 * ry },
      title: { x: cx, y: cy - ry - (L.kind === "motor" ? 24 : 4) * dpr }, dots, probe: { x: 0, y: 0, w: 0, h: 0 }, axis: "x" };
  }

  // Neurons fill the region's ellipse in a sunflower; role groups run outward in bands, like
  // cortical layers. The roles are on the hover card.
  placeLayer(b) {
    const { L, shape } = b;
    const dpr = this.dpr;
    if (L.kind === "motor") {
      for (let k = 0; k < L.count; k++) {
        const i = L.start + k;
        this.px[i] = shape.cx + (k - 1) * shape.rx * 0.8;
        this.py[i] = shape.cy;
        this.pr[i] = Math.max(4 * dpr, shape.ry * 0.55);
      }
      b.groupBoxes = [];
      return;
    }
    const order = [];
    for (const gr of L.groups) for (const k of gr.members) order.push(k);
    const N = order.length;
    const gold = Math.PI * (3 - Math.sqrt(5));
    const cell = Math.sqrt((Math.PI * shape.rx * shape.ry) / Math.max(1, N));
    order.forEach((k, t) => {
      const i = L.start + k;
      const r = Math.sqrt((t + 0.5) / N);
      const a = t * gold;
      this.px[i] = shape.cx + shape.rx * 0.95 * r * Math.cos(a);
      this.py[i] = shape.cy + shape.ry * 0.95 * r * Math.sin(a);
      this.pr[i] = Math.max(0.9 * dpr, Math.min(5 * dpr, cell * 0.32));
    });
    b.groupBoxes = [];
  }

  probeRows() { return []; } // the layer view shows what each layer knows; this view shows where

  regionCentre(name) {
    if (name === "sensory") return [this.field.x + this.field.S / 2, this.field.y + this.field.S / 2];
    const b = this.bands.find((q) => q.L.pop === name);
    return b ? [b.shape.cx, b.shape.cy] : null;
  }

  buildTracts() {
    const e = this.edges;
    const pops = this.desc.populations;
    const names = Object.keys(pops);
    const owner = new Int16Array(this.n).fill(-1);
    names.forEach((k, j) => { const [s, c] = pops[k]; for (let i = s; i < s + c; i++) owner[i] = j; });
    const map = new Map();
    for (let k = 0; k < e.m; k++) {
      const a = names[owner[e.pre[k]]], b = names[owner[e.post[k]]];
      if (a === b) continue;
      const key = `${a}>${b}`;
      if (!map.has(key)) map.set(key, { from: a, to: b, exc: [], inh: [] });
      (e.w[k] > 0 ? map.get(key).exc : map.get(key).inh).push(k);
    }
    const sizes = Object.fromEntries((this.desc.pathways || []).map((p) => [`${p.from}>${p.to}`, p.synapses]));
    this.tracts = [];
    for (const t of map.values()) {
      const A = this.regionCentre(t.from), B = this.regionCentre(t.to);
      if (!A || !B) continue;
      // A control point bowing the tract toward the brain's core; the field's projection runs
      // through the relay.
      let C;
      if (t.from === "sensory") C = [this.nuclei.relay.x, this.nuclei.relay.y];
      else {
        const mx = (A[0] + B[0]) / 2, my = (A[1] + B[1]) / 2;
        const core = [this.box.ox + this.box.bw * 0.45, this.box.oy + this.box.bh * 0.45];
        const back = t.from > t.to ? 0.22 : -0.22; // the two directions of a pair bow apart
        C = [mx + (core[0] - mx) * 0.35 + back * (B[1] - A[1]), my + (core[1] - my) * 0.35 - back * (B[0] - A[0])];
      }
      const syn = sizes[`${t.from}>${t.to}`] || t.exc.length + t.inh.length;
      this.tracts.push({ ...t, A, B, C, width: Math.max(1, Math.log10(1 + syn)), shown: [0, 0] });
    }
  }

  // ---- the page's explanation spots ----------------------------------------------------------
  // Each part's box hugs its label, so its question mark sits beside the name drawn on the canvas.
  explainParts(search) {
    if (!this.bands || !this.field) return [];
    const d = this.dpr, g = this.ctx, out = [];
    const box = (x0, y0, x1, y1) => ({ x: x0 / d, y: y0 / d, w: Math.max(8, (x1 - x0) / d), h: Math.max(8, (y1 - y0) / d) });
    const width = (text, size, weight = 600) => { g.font = `${weight} ${size * d}px ${MONO}`; return g.measureText(text).width; };
    const label = (text, x, y, size, align = "center", lines = 1) => {
      const w = width(text, size);
      const x0 = align === "center" ? x - w / 2 : align === "right" ? x - w : x;
      return box(x0 - 3 * d, y - size * d * lines - 3 * d, x0 + w + 3 * d, y + 3 * d);
    };
    // the visual cortex: its label, where drawStatic puts it
    const f = this.field;
    const L1 = this.bands.find((q) => q.L.kind === "hidden");
    const fy = Math.min(f.y - 9 * d, L1 ? L1.title.y - 24 * d : f.y - 9 * d);
    const vis = this.W / d < 600 ? "visual cortex" : "visual cortex · the field";
    out.push({ box: label(vis, Math.min(this.W - 6 * d, f.x + f.S), fy, 8.5, "right"), title: "Visual cortex", text: EYE_TEXT.text });
    const hidden = this.layers.filter((L) => L.kind === "hidden");
    for (const b of this.bands) {
      const { L } = b;
      const off = L.kind === "trace" && this.hidden[L.start];
      const what = L.kind === "motor" ? "motor strip" : L.kind === "trace" ? (off ? "prefrontal · off" : `prefrontal · ${L.count}`) : `${L.name} · ${L.count}`;
      const two = L.kind === "hidden" ? Math.max(width(what, 8.5), width(b.where, 7.5, 500)) : width(what, 8.5);
      const top = b.title.y - (L.kind === "hidden" ? 20 : 11) * d;
      out.push({ box: box(b.title.x - two / 2 - 3 * d, top, b.title.x + two / 2 + 3 * d, b.title.y + 3 * d), ...partText(L, hidden, b.where) });
    }
    const N = this.nuclei;
    const nucleus = (q, text, title, card) => out.push({ box: label(text, q.x, q.y + q.r + 10 * d, 7.5), title, text: card });
    nucleus(N.relay, "relay", "Relay", "Where the eye's signals pass on their way into the first layer, drawn where the thalamus sits in an animal.");
    nucleus(N.select, "selection", "Selection", "The three motor neurons' activity and the brain's pick, which flares up to the motor strip. It plays the role the basal ganglia play in an animal.");
    nucleus(N.dopamine, "dopamine · frozen, no reward", "Dopamine", "Dark on purpose: the brain does not learn while you play, so no reward reaches it.");
    if (search && this.motor) {
      const top = this.motor.start;
      const colW = 14 * d;
      const right = this.px[top + 2] + this.pr[top + 2] * 3.2;
      const x0 = Math.min(this.W - 3 * colW - 8 * d, right + 10 * d), y0 = this.py[top + 1] - 11 * d;
      out.push({ box: label("look-ahead · 4 rounds", x0 - 4 * d, y0 - 6 * d, 7.5, "left"), title: "Look-ahead",
        text: "After each move of the brain, a look-ahead checks it. It plays four rounds ahead by the rules alone (each of its moves, your best reply, and so on) and counts the cells each rider reaches first; the brain's pick gets a head start of 8 cells. The bars are its values for the three moves; an amber arc means it overruled the brain." });
    }
    const h = 34 * d, y0 = this.H - h - 28 * d;
    out.push({ box: label("settling · sweep 00 of 00 · largest repair", 12 * d, y0 - 4 * d, 8, "left"), title: "Settling",
      text: "The last move's settle: the largest change of any neuron, sweep by sweep, falling until the whole brain agrees with itself. The brain's move is read from that settled state." });
    return out;
  }

  // ---- static: the silhouette, regions, nuclei, labels --------------------------------------
  drawStatic() {
    RippleView.prototype.drawStatic.call(this);
    if (!this.bands) return;
    const g = this.static.getContext("2d");
    const { dpr, box } = this;
    const { P, bw, bh } = box;
    // Under everything: the silhouette, the cerebellum and brainstem, faint gyri.
    g.save();
    g.globalCompositeOperation = "destination-over";
    const outline = (path, fill, stroke) => {
      g.fillStyle = fill; g.fill(path);
      if (stroke) { g.strokeStyle = stroke; g.lineWidth = 1.2 * dpr; g.stroke(path); }
    };
    // Brainstem and cerebellum first (destination-over draws under what is there).
    const [cx, cy] = P(0.5, 0.44);
    const cortex = new Path2D();
    cortex.ellipse(cx, cy, bw * 0.49, bh * 0.4, -0.04, 0, Math.PI * 2);
    const [kx, ky] = P(0.78, 0.79);
    const cereb = new Path2D();
    cereb.ellipse(kx, ky, bw * 0.15, bh * 0.12, -0.25, 0, Math.PI * 2);
    const [sx, sy] = P(0.6, 0.86);
    const stem = new Path2D();
    stem.ellipse(sx, sy, bw * 0.045, bh * 0.14, 0.35, 0, Math.PI * 2);
    // Gyri: soft arcs inside the cortex.
    g.strokeStyle = "rgba(140,170,230,0.05)";
    g.lineWidth = 1.4 * dpr;
    for (let k = 0; k < 9; k++) {
      const a0 = -Math.PI * 0.95 + k * 0.21;
      g.beginPath();
      g.ellipse(cx, cy, bw * (0.43 - 0.012 * (k % 3)), bh * (0.34 - 0.02 * (k % 4)), -0.04, a0, a0 + 0.42);
      g.stroke();
    }
    const grad = g.createRadialGradient(cx, cy - bh * 0.1, bh * 0.05, cx, cy, bw * 0.55);
    grad.addColorStop(0, "rgba(28,36,64,0.92)");
    grad.addColorStop(1, "rgba(10,13,26,0.92)");
    outline(cortex, grad, "rgba(130,160,230,0.16)");
    outline(cereb, "rgba(16,20,38,0.95)", "rgba(130,160,230,0.12)");
    outline(stem, "rgba(14,18,34,0.95)", "rgba(130,160,230,0.1)");
    g.restore();

    // Region fields: a soft glow under each population's neurons, coloured by layer.
    g.save();
    g.globalCompositeOperation = "destination-over";
    for (const b of this.bands) {
      const { cx: x, cy: y, rx, ry } = b.shape;
      const off = b.L.kind === "trace" && this.hidden[b.L.start];
      const gr = g.createRadialGradient(x, y, 0, x, y, Math.max(rx, ry) * 1.25);
      gr.addColorStop(0, rgba(off ? [90, 100, 120] : b.L.rgb, off ? 0.05 : 0.13));
      gr.addColorStop(1, rgba(b.L.rgb, 0));
      g.fillStyle = gr;
      g.beginPath(); g.ellipse(x, y, rx * 1.25, ry * 1.25, 0, 0, Math.PI * 2); g.fill();
    }
    // The tracts, faint and static, under the live ones.
    for (const t of this.tracts) {
      g.strokeStyle = "rgba(150,170,220,0.05)";
      g.lineWidth = t.width * 2.2 * dpr;
      g.beginPath(); g.moveTo(...t.A); g.quadraticCurveTo(...t.C, ...t.B); g.stroke();
    }
    g.restore();

    // On top: titles, group labels, faint neurons, supported roles, the nuclei.
    g.textBaseline = "alphabetic";
    g.textAlign = "center";
    for (const b of this.bands) {
      const { L } = b;
      const off = L.kind === "trace" && this.hidden[L.start];
      g.font = `600 ${8.5 * dpr}px ${MONO}`;
      g.fillStyle = rgba(L.rgb, off ? 0.35 : 0.72);
      const what = L.kind === "motor" ? "motor strip" : L.kind === "trace" ? (off ? "prefrontal · off" : `prefrontal · ${L.count}`)
        : `${L.name} · ${L.count}`;
      g.fillText(what, b.title.x, b.title.y);
      g.font = `500 ${7.5 * dpr}px ${MONO}`;
      g.fillStyle = "rgba(170,185,215,0.45)";
      if (L.kind === "hidden") g.fillText(b.where, b.title.x, b.title.y - 10 * dpr);
      if (off) g.fillText("working trace switched off", b.shape.cx, b.shape.cy + 3 * dpr);
      g.textAlign = "left";
      g.font = `500 ${7 * dpr}px ${MONO}`;
      for (const box of b.groupBoxes || []) {
        g.fillStyle = box.gr.family === "mixed" || box.gr.family === "silent" ? "rgba(150,165,190,0.32)" : "rgba(200,215,240,0.5)";
        g.fillText(`${FAMILY_NAME[box.gr.family] || box.gr.family}`, box.label[0], box.label[1]);
      }
      g.textAlign = "center";
      if (off) continue;
      g.fillStyle = rgba(L.rgb, 0.16);
      for (let k = 0; k < L.count; k++) {
        const i = L.start + k;
        g.beginPath(); g.arc(this.px[i], this.py[i], Math.max(0.8 * dpr, this.pr[i] * 0.7), 0, Math.PI * 2); g.fill();
      }
      if (L.labels) {
        g.strokeStyle = rgba(AMBER, 0.7);
        g.lineWidth = Math.max(1, 0.8 * dpr);
        L.labels.forEach((x, k) => {
          if (!x.supported) return;
          const i = L.start + k;
          g.beginPath(); g.arc(this.px[i], this.py[i], this.pr[i] + 1.4 * dpr, 0, Math.PI * 2); g.stroke();
        });
      }
    }
    // The visual cortex's label.
    const f = this.field;
    g.font = `600 ${8.5 * dpr}px ${MONO}`;
    g.fillStyle = "rgba(140,200,255,0.7)";
    g.textAlign = "right";
    const L1 = this.bands.find((q) => q.L.kind === "hidden");
    const fy = Math.min(f.y - 9 * dpr, L1 ? L1.title.y - 24 * dpr : f.y - 9 * dpr);
    g.fillText(this.W / dpr < 600 ? "visual cortex" : "visual cortex · the field", Math.min(this.W - 6 * dpr, f.x + f.S), fy);
    g.textAlign = "center";
    // Nuclei.
    const N = this.nuclei;
    const ring = (q, rgb, a) => {
      g.strokeStyle = rgba(rgb, a); g.lineWidth = dpr;
      g.beginPath(); g.ellipse(q.x, q.y, q.r * 1.25, q.r, 0, 0, Math.PI * 2); g.stroke();
    };
    ring(N.relay, [140, 200, 255], 0.22);
    ring(N.select, [230, 230, 255], 0.2);
    ring(N.dopamine, [120, 120, 140], 0.25);
    g.font = `500 ${7.5 * dpr}px ${MONO}`;
    g.fillStyle = "rgba(170,185,215,0.5)";
    g.fillText("relay", N.relay.x, N.relay.y + N.relay.r + 10 * dpr);
    g.fillText("selection", N.select.x, N.select.y + N.select.r + 10 * dpr);
    g.fillStyle = "rgba(150,155,175,0.4)";
    g.fillText("dopamine · frozen, no reward", N.dopamine.x, N.dopamine.y + N.dopamine.r + 10 * dpr);
    // Motor glyphs above the strip.
    g.font = `600 ${10 * dpr}px ${MONO}`;
    g.fillStyle = "rgba(220,230,255,0.45)";
    for (let k = 0; k < 3; k++) {
      const i = this.motor.start + k;
      g.fillText(ARROWS[k], this.px[i], this.py[i] - 11 * dpr);
    }
  }

  // ---- a move -------------------------------------------------------------------------------
  push(state) {
    super.push(state);
    if (state.repair && state.repair.length) this.repair = { values: state.repair, t0: performance.now() };
  }

  // The live activation of any neuron at `now`: the field's inputs as observed, the rest replayed.
  act(i, now) {
    if (i < this.offset) return this.obs ? this.obs[i] : 0;
    const got = this.value(i - this.offset, now);
    const reg = this.regionOf[i - this.offset];
    const v = got ? got.v : this.last[i - this.offset];
    return Math.max(0, v) / (this.scale[reg.name] || 1);
  }

  // Under the neurons: region waves, the live tracts and the selection nucleus.
  drawFronts(g, now) {
    if (!this.bands) return super.drawFronts(g, now);
    const { dpr } = this;
    for (const w of this.waves) {
      const dt0 = now - w.t0;
      if (dt0 < 0 || dt0 > this.frontMs + PLAY_MS + 200) continue;
      const f = this.field;
      const a0 = 0.16 * Math.max(0, 1 - dt0 / 300);
      if (a0 > 0) {
        const gr = g.createRadialGradient(f.x + f.S / 2, f.y + f.S / 2, 0, f.x + f.S / 2, f.y + f.S / 2, f.S);
        gr.addColorStop(0, `rgba(120,200,255,${a0})`);
        gr.addColorStop(1, "rgba(120,200,255,0)");
        g.fillStyle = gr;
        g.fillRect(f.x - f.S / 2, f.y - f.S / 2, f.S * 2, f.S * 2);
      }
      this.bands.forEach((b, j) => {
        const t = dt0 - (this.bandDelay ? this.bandDelay[j] : 0) * this.frontMs;
        if (t < 0 || t > 420) return;
        const p = t / 420;
        const { cx, cy, rx, ry } = b.shape;
        const R = Math.max(rx, ry) * (0.4 + 1.1 * p);
        const gr = g.createRadialGradient(cx, cy, R * 0.6, cx, cy, R);
        gr.addColorStop(0, rgba(b.L.rgb, 0));
        gr.addColorStop(0.8, rgba(b.L.rgb, 0.14 * (1 - p)));
        gr.addColorStop(1, rgba(b.L.rgb, 0));
        g.fillStyle = gr;
        g.beginPath(); g.ellipse(cx, cy, R * (rx / Math.max(rx, ry)) * 1.1, R * (ry / Math.max(rx, ry)) * 1.1, 0, 0, Math.PI * 2); g.fill();
      });
    }
    // Tracts: |weight x presynaptic activation| summed over each tract's drawn synapses.
    const e = this.edges;
    const pre = new Map();
    const a = (i) => { if (!pre.has(i)) pre.set(i, this.act(i, now)); return pre.get(i); };
    let peak = 1e-6;
    const flows = this.tracts.map((t) => {
      const s = [0, 0];
      for (const k of t.exc) s[0] += Math.abs(e.w[k]) * a(e.pre[k]);
      for (const k of t.inh) s[1] += Math.abs(e.w[k]) * a(e.pre[k]);
      peak = Math.max(peak, s[0], s[1]);
      return s;
    });
    this.flowPeak = Math.max(peak, (this.flowPeak || peak) * 0.985);
    g.lineCap = "round";
    this.tracts.forEach((t, j) => {
      for (const c of [0, 1]) {
        t.shown[c] += (flows[j][c] / this.flowPeak - t.shown[c]) * 0.3;
        const v = Math.min(1, t.shown[c]);
        if (v < 0.02) continue;
        const rgb = c === 0 ? EXC_RGB : INH_RGB;
        const off = (c === 0 ? -1 : 1) * t.width * 1.4 * dpr;
        g.strokeStyle = rgba(rgb, 0.08 + 0.42 * v);
        g.lineWidth = (0.6 + t.width * 1.2 * v) * dpr;
        g.beginPath();
        g.moveTo(t.A[0], t.A[1] + off);
        g.quadraticCurveTo(t.C[0], t.C[1] + off, t.B[0], t.B[1] + off);
        g.stroke();
      }
    });
    // The selection nucleus: the three motor neurons' live activations, the pick flaring.
    const N = this.nuclei.select;
    const latest = this.waves[this.waves.length - 1];
    for (let k = 0; k < 3; k++) {
      const j = this.motor.start + k;
      const v = Math.min(1, this.act(j, now));
      let flare = 0;
      if (latest && latest.flash && latest.flash.j === j) {
        const dt = now - latest.flash.t;
        if (dt >= 0) flare = Math.exp(-dt / 500);
      }
      const x = N.x + (k - 1) * N.r * 0.9, y = N.y;
      const R = N.r * (0.55 + 0.6 * v + 0.9 * flare);
      g.globalAlpha = Math.min(1, 0.15 + 0.6 * v + 0.6 * flare);
      g.drawImage(this.selSprites[k], x - R, y - R, 2 * R, 2 * R);
      // The pick runs up to the motor strip.
      if (flare > 0.05) {
        g.strokeStyle = rgba(MOTOR_RGB[k], 0.6 * flare);
        g.lineWidth = 2 * dpr * flare;
        g.beginPath(); g.moveTo(x, y); g.quadraticCurveTo(x, (y + this.py[j]) / 2, this.px[j], this.py[j]); g.stroke();
      }
    }
    g.globalAlpha = 1;
  }

  // The look-ahead's verdict on the brain's last proposal (main.js hands it over each tick):
  // its value for each move beside the motor strip, and an arc where it overruled the brain.
  deliberate(d) {
    this.decision = { ...d, t: performance.now() };
  }

  drawDecision(g, now) {
    const d = this.decision;
    if (!d || !d.values || !this.motor) return;
    const { dpr } = this;
    const age = now - d.t;
    if (age > 1400) return;
    const fade = age < 1000 ? 1 : 1 - (age - 1000) / 400;
    const vals = d.values;
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const top = this.motor.start;
    // A small panel to the right of the motor strip: one bar per move, the chosen one framed.
    const right = this.px[top + 2] + this.pr[top + 2] * 3.2;
    const colW = 14 * dpr, bandH = 22 * dpr;
    const x0 = Math.min(this.W - 3 * colW - 8 * dpr, right + 10 * dpr), y0 = this.py[top + 1] - bandH / 2;
    g.globalCompositeOperation = "source-over";
    g.fillStyle = `rgba(0,0,0,${0.55 * fade})`;
    const over = d.prior !== d.move && Number.isInteger(d.prior);
    g.fillRect(x0 - 6 * dpr, y0 - 16 * dpr, Math.max(3 * colW + 12 * dpr, over ? 104 * dpr : 0), bandH + (over ? 42 : 30) * dpr);
    g.font = `500 ${7.5 * dpr}px ${MONO}`;
    g.textAlign = "left";
    g.fillStyle = `rgba(200,215,240,${0.75 * fade})`;
    g.fillText(`look-ahead · ${d.depth} rounds`, x0 - 4 * dpr, y0 - 6 * dpr);
    for (let k = 0; k < 3; k++) {
      const x = x0 + (k + 0.5) * colW, y = y0;
      const t = hi > lo ? (vals[k] - lo) / (hi - lo) : 1;
      const dead = vals[k] < -(1 << 22);
      g.fillStyle = dead ? `rgba(255,90,120,${0.7 * fade})` : rgba(MOTOR_RGB[k], (0.3 + 0.65 * t) * fade);
      const w = 7 * dpr, h = Math.max(2 * dpr, bandH * (dead ? 0.12 : 0.15 + 0.85 * t));
      g.fillRect(x - w / 2, y + bandH - h, w, h);
      if (k === d.move) {
        g.strokeStyle = `rgba(255,255,255,${0.85 * fade})`;
        g.lineWidth = dpr;
        g.strokeRect(x - w / 2 - 2 * dpr, y - 2 * dpr, w + 4 * dpr, bandH + 4 * dpr);
      }
      g.textAlign = "center";
      g.fillStyle = `rgba(220,230,255,${(k === d.prior ? 0.9 : 0.45) * fade})`;
      g.fillText(ARROWS[k], x, y + bandH + 11 * dpr);
    }
    g.textAlign = "center";
    this.decisionX = x0 - 4 * dpr;
    this.decisionY = y0 + bandH + 23 * dpr;
    if (d.prior !== d.move && Number.isInteger(d.prior)) {
      const a = top + d.prior, b = top + d.move;
      const x0 = this.px[a], y0 = this.py[a] - this.pr[a] - 4 * dpr, x1 = this.px[b], y1 = this.py[b] - this.pr[b] - 4 * dpr;
      g.strokeStyle = rgba(AMBER, 0.85 * fade);
      g.lineWidth = 2 * dpr;
      g.beginPath();
      g.moveTo(x0, y0);
      g.quadraticCurveTo((x0 + x1) / 2, Math.min(y0, y1) - 26 * dpr, x1, y1);
      g.stroke();
      g.fillStyle = rgba(AMBER, 0.9 * fade);
      g.beginPath(); g.arc(x1, y1, 2.6 * dpr, 0, Math.PI * 2); g.fill();
      g.textAlign = "left";
      g.fillText("overruled the brain", this.decisionX, this.decisionY);
      g.textAlign = "center";
    }
  }

  // On top: the settle's largest repair per sweep, falling as the wave plays.
  overlay(g, now) {
    super.overlay(g, now);
    this.drawDecision(g, now);
    const r = this.repair;
    if (!r || !this.box) return;
    const { dpr, box } = this;
    const vals = r.values;
    const n = vals.length;
    const p = Math.min(1, (now - r.t0) / (this.frontMs + PLAY_MS));
    const w = Math.min(190 * dpr, box.bw * 0.3), h = 34 * dpr;
    const x0 = 12 * dpr, y0 = this.H - h - 28 * dpr;
    const lo = Math.log10(1e-6), hi = Math.log10(Math.max(...vals, 1e-5));
    const Y = (v) => y0 + h - ((Math.log10(Math.max(v, 1e-6)) - lo) / Math.max(1e-9, hi - lo)) * h;
    g.globalCompositeOperation = "source-over";
    g.strokeStyle = "rgba(120,200,255,0.75)";
    g.lineWidth = 1.2 * dpr;
    g.beginPath();
    const shownN = Math.max(1, Math.round(p * n));
    for (let k = 0; k < shownN; k++) {
      const X = x0 + (n > 1 ? (k / (n - 1)) * w : 0);
      if (k === 0) g.moveTo(X, Y(vals[k])); else g.lineTo(X, Y(vals[k]));
    }
    g.stroke();
    g.font = `500 ${8 * dpr}px ${MONO}`;
    g.textAlign = "left";
    g.textBaseline = "alphabetic";
    g.fillStyle = "rgba(150,170,200,0.55)";
    g.fillText(`settling · sweep ${Math.min(n, shownN)} of ${n} · largest repair`, x0, y0 - 4 * dpr);
  }
}
