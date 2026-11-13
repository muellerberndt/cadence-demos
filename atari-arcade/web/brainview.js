// The brain view: the arcade's Cadence brain drawn as a stylized brain seen from the left side.
// Every lit pixel comes from the brain's measured state (arcade_brain.BrainSide's view message):
// activations of the settled state, the settle replayed sweep by sweep, the current weights of the
// drawn synapses and their changes, the critic's value and dopamine, the phase (watching the teacher
// or at the controls), arousal when the brain lives calm or aroused. Each population is placed where
// the animal-brain region whose role it plays sits, and named as playing that role, not as being it.
// The outline, its folds and the gentle camera sway are drawing, not data.

import { brainColor } from "./cadence-palette.js";
const W = 960, H = 540;
const AMBER = brainColor("signal"), GOLD = brainColor("memory"), CYAN = brainColor("inhibit"), BLUE = brainColor("inhibit"),
  BONE = brainColor("white"), RED = brainColor("trace"), GREEN = brainColor("recall"), VIOLET = brainColor("trace");
const REST = brainColor("rest"), DIM = brainColor("dim");
const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
const clamp = (v, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, v));
const lerp = (a, b, t) => a + (b - a) * t;

function glowSprite(c) {
  const g = document.createElement('canvas');
  g.width = g.height = 64;
  const x = g.getContext('2d');
  const r = x.createRadialGradient(32, 32, 1, 32, 32, 31);
  r.addColorStop(0, rgba([255, 255, 255], 0.95));
  r.addColorStop(0.12, rgba(c, 0.9));
  r.addColorStop(0.4, rgba(c, 0.32));
  r.addColorStop(1, rgba(c, 0));
  x.fillStyle = r;
  x.fillRect(0, 0, 64, 64);
  return g;
}

// A point on a quadratic curve, for laying neurons along the cortex.
const quad = (p0, p1, p2, t) => [(1 - t) * (1 - t) * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
                                 (1 - t) * (1 - t) * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]];

export class BrainView {
  constructor(canvas, graph) {
    this.canvas = canvas;
    this.graph = graph;
    this.ctx = canvas.getContext('2d');
    this.dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = W * this.dpr;
    canvas.height = H * this.dpr;
    this.sprites = { amber: glowSprite(AMBER), cyan: glowSprite(CYAN), gold: glowSprite(GOLD), blue: glowSprite(BLUE),
                     red: glowSprite(RED), green: glowSprite(GREEN), violet: glowSprite(VIOLET) };
    this.pops = Object.fromEntries(graph.populations.map((p) => [p.name, p]));
    this.layout();
    this.viz = null;
    this.flash = new Float32Array(graph.edges.length);
    this.weights = Float32Array.from(graph.edges.map((e) => e[3]));
    this.replay = null; this.replayStart = 0;
    this.wash = 0; this.washSign = 1; this.lastLesson = 0; this.lessonPulse = 0;
    this.shown = null; this.retinaCanvas = null; this.retinaPixels = null;
    this.frames = []; this.lastFrame = 0;
  }

  // ---- anatomy: where each population sits -------------------------------------------------------
  layout() {
    const A = this.pops.association, T = this.pops.trace, M = this.pops.motor, Mem = this.pops.memory, V = this.pops.value;
    const pos = [];
    // association cortex: a sheet over the parietal and temporal lobes, rows following the surface
    const rowsA = 4, colsA = Math.ceil(A.count / rowsA);
    for (let i = 0; i < A.count; i++) {
      const r = Math.floor(i / colsA), c = i % colsA, t = (c + 0.5) / colsA;
      const p = quad([470, 120 + r * 26], [610, 52 + r * 26], [745, 150 + r * 24], t);
      pos[A.start + i] = [p[0] + (r % 2) * 6, p[1]];
    }
    // prefrontal cortex: the working trace, a sheet over the frontal pole
    const rowsT = 4, colsT = Math.ceil(T.count / rowsT);
    for (let i = 0; i < T.count; i++) {
      const r = Math.floor(i / colsT), c = i % colsT, t = (c + 0.5) / colsT;
      pos[T.start + i] = quad([168 + r * 22, 300 - r * 4], [150 + r * 24, 110 + r * 18], [350, 82 + r * 26], t);
    }
    // the motor strip: one neuron per action down the precentral gyrus
    for (let i = 0; i < M.count; i++) pos[M.start + i] = quad([420, 74], [398, 160], [356, 246], (i + 0.5) / M.count);
    // hippocampus: the associative memory, one cell per action, along a curl
    for (let i = 0; i < Mem.count; i++) pos[Mem.start + i] = quad([520, 352], [600, 300], [668, 350], (i + 0.5) / Mem.count);
    pos[V.start] = [470, 282];   // the critic's value, in the striatum
    this.pos = pos;
    this.retina = { x: 778, y: 168, w: 104, h: 124 };   // occipital: where the screen enters
    this.striatum = [470, 282]; this.vta = [560, 400]; this.cx = 500; this.cy = 240;
    // The parts of the brain the page explains (the question marks over the canvas): a box in the
    // view's own 960 x 540 units, a title and what the part does.
    this.regions = [
      { box: [455, 36, 310, 200], title: 'Association cortex', text: `${A.count} neurons that read the screen and settle together with the motor strip. Warm dots are active neurons, cool dots inhibited ones; the fibres light up with the signals they carry.` },
      { box: [140, 50, 205, 258], title: 'Working trace', text: `${T.count} neurons that hold what the association cortex did a moment before. They carry the brain's state from one screen to the next, so each answer starts from where the last one ended.` },
      { box: [348, 50, 104, 206], title: 'Motor strip', text: 'One neuron per joystick action, each named. The strongest neuron of the settled brain is the action. While the brain watches, the teacher\'s action glows green, and red marks an answer of its own that disagreed.' },
      { box: [425, 258, 100, 76], title: 'Critic', text: 'How much reward the brain expects from this screen. It plays the role of the striatum.' },
      { box: [528, 300, 162, 80], title: 'Associative memory', text: 'The reward the brain recalls for each action on screens like this one. It plays the role of the hippocampus.' },
      { box: [520, 382, 92, 58], title: 'Dopamine', text: 'The surprise after each outcome at the controls: the reward that came less the reward the critic expected. A gold wash means better than expected, blue worse. This signal moves the synapses.' },
      { box: [770, 100, 125, 200], title: 'The eye', text: 'Everything the brain sees: 7,056 sensory neurons, one per pixel of the screen shrunk to 84 by 84 grey pixels. No positions of anything in the game and no game memory: only pixels.' },
      { box: [12, 8, 536, 26], title: 'What it is doing', text: 'Watching the teacher: every screen is a lesson, and the brain learns the teacher\'s action for it. At the controls: the brain plays and learns from the reward its own actions bring.' },
      { box: [12, 462, 214, 60], title: 'Settling', text: 'How the brain reaches an answer: every neuron adjusts to its neighbours, sweep after sweep, until the largest change falls under the tolerance (the dotted line). The whole brain then agrees, and that agreement is the answer.' },
      { box: [698, 462, 250, 60], title: 'Learning, live', text: 'How many synapses changed since the last picture. While the brain watches: the lesson count and whether its own answer agreed. At the controls: the dopamine, the expected value and the reward.' },
    ];
    // where each drawn synapse starts and the tract it belongs to; tracts share control points
    this.edgeGeom = this.graph.edges.map(([k, s, t]) => {
      const P = pos[t] || [this.cx, this.cy];
      let S, core;
      if (k === 0) {
        S = [this.retina.x + ((s % 84) + 0.5) / 84 * this.retina.w, this.retina.y + (Math.floor(s / 84) + 0.5) / 84 * this.retina.h];
        core = [700, 236];
      } else {
        S = pos[s] || [this.cx, this.cy];
        // a tract between two regions bends through one waypoint, so its fibres run as a bundle
        const pair = [this.which(s), this.which(t)].sort().join('-');
        const way = { 'association-trace': [430, 205], 'association-motor': [452, 120], 'motor-motor': null };
        const mid = [(S[0] + P[0]) / 2, (S[1] + P[1]) / 2];
        core = way[pair] ? [lerp(way[pair][0], mid[0], 0.25), lerp(way[pair][1], mid[1], 0.25)] : [mid[0] + 26, mid[1]];
      }
      return { S, P, C: core };
    });
  }

  // Lay the explanation spots over the canvas, scaled to its size on the page (again on a resize).
  explain(host) {
    if (!window.CadenceExplain || !host) return;
    const place = () => {
      const k = this.canvas.clientWidth / W;
      if (!k) return;
      window.CadenceExplain.clearSpots(host);
      for (const r of this.regions) {
        const [x, y, w, h] = r.box;
        window.CadenceExplain.spot(host, { x: x * k, y: y * k, w: w * k, h: h * k }, r.text, { title: r.title });
      }
    };
    place();
    new ResizeObserver(place).observe(this.canvas);
  }

  which(i) {
    for (const p of this.graph.populations) if (i >= p.start && i < p.start + p.count) return p.name;
    return '?';
  }

  // ---- data in ------------------------------------------------------------------------------------
  update(viz) {
    if (!viz || viz === this.viz) return;
    this.viz = viz;
    if (viz.drawn_weights && viz.drawn_weights.length === this.weights.length) {
      for (let i = 0; i < this.weights.length; i++) {
        const d = Math.abs(viz.drawn_weights[i] - this.weights[i]);
        if (d > 1e-4) this.flash[i] = Math.min(1, 0.35 + d * 400);
        this.weights[i] = viz.drawn_weights[i];
      }
    }
    if (viz.replay && viz.replay.frames && viz.replay.frames.length) { this.replay = viz.replay; this.replayStart = performance.now(); }
    const d = viz.dopamine || 0, r = viz.reward || 0;
    if (r !== 0 || Math.abs(d) > 0.05) {
      this.wash = Math.max(this.wash, clamp(Math.abs(d || r) * 1.2, 0.25, 1));
      this.washSign = (d || r) >= 0 ? 1 : -1;
    }
    if (viz.phase === 'watching' && viz.lessons !== this.lastLesson) { this.lessonPulse = 1; this.lastLesson = viz.lessons; }
  }

  // the activations to draw now: a replay frame while the settle wave plays, else the settled state
  current(now) {
    const v = this.viz, st = v ? v.state : [];
    const head = this.pops.association.count + this.pops.trace.count + this.pops.motor.count;
    let act = st, sweep = null, live = false;
    if (this.replay) {
      const R = this.replay, k = Math.floor((now - this.replayStart) / 70);
      if (k < R.frames.length) {
        act = [...R.frames[k].slice(0, head), ...st.slice(head)];
        sweep = { of: R.sweep_of_frame[k], sweeps: R.sweeps }; live = true;
      }
    }
    if (!this.shown || this.shown.length !== act.length) this.shown = Float32Array.from(act);
    const s = this.shown;
    for (let i = 0; i < act.length; i++) s[i] = live ? (act[i] ?? 0) : lerp(s[i], act[i] ?? 0, 0.25);
    return { act: s, sweep };
  }

  // ---- drawing --------------------------------------------------------------------------------------
  draw(meta = {}) {
    const now = performance.now();
    if (this.lastFrame) { this.frames.push(now - this.lastFrame); if (this.frames.length > 600) this.frames.shift(); }
    this.lastFrame = now;
    const ctx = this.ctx, v = this.viz || {}, t = now / 1000;
    const { act, sweep } = this.current(now);
    const phase = v.phase || 'watching';
    const live = v.mode != null;
    const calm = live && (v.mode === 'calm' || v.mode === 'routine');
    const tone = calm ? 0.55 : 1.0;   // learning on is bright; a calm brain, learning nothing, is dim
    this.wash *= 0.965; this.lessonPulse *= 0.9;
    for (let i = 0; i < this.flash.length; i++) this.flash[i] *= 0.93;

    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const sx = Math.sin(t * 0.23) * 5, sy = Math.sin(t * 0.17) * 3, sc = 1 + Math.sin(t * 0.11) * 0.008;
    ctx.save();
    ctx.translate(W / 2 + sx, H / 2 + sy); ctx.scale(sc, sc); ctx.translate(-W / 2, -H / 2);
    this.drawSilhouette(ctx, tone);
    this.drawWash(ctx);
    this.drawRetina(ctx, meta.retina);
    ctx.globalCompositeOperation = 'lighter';
    this.drawRegionGlow(ctx, act, tone);
    this.drawTracts(ctx, act, tone, t);
    this.drawNeurons(ctx, act, v, tone);
    ctx.globalCompositeOperation = 'source-over';
    this.drawLabels(ctx, v);
    ctx.restore();
    this.drawHud(ctx, v, sweep, phase, live, calm);
  }

  drawSilhouette(ctx, tone) {
    if (!this.outline) {
      const p = new Path2D();
      p.moveTo(150, 330);
      p.bezierCurveTo(108, 250, 120, 120, 230, 72);
      p.bezierCurveTo(330, 26, 520, 22, 640, 52);
      p.bezierCurveTo(780, 86, 900, 170, 892, 268);
      p.bezierCurveTo(886, 320, 850, 352, 800, 362);
      p.bezierCurveTo(740, 372, 690, 352, 640, 372);
      p.bezierCurveTo(600, 386, 560, 372, 520, 380);
      p.bezierCurveTo(430, 392, 330, 400, 250, 380);
      p.bezierCurveTo(200, 368, 168, 356, 150, 330);
      this.outline = p;
      const c = new Path2D();   // cerebellum
      c.moveTo(700, 368); c.bezierCurveTo(720, 440, 860, 446, 870, 360); c.bezierCurveTo(820, 380, 760, 382, 700, 368);
      this.cerebellum = c;
      const b = new Path2D();   // brainstem
      b.moveTo(540, 372); b.bezierCurveTo(548, 440, 560, 500, 576, 540); b.lineTo(626, 540);
      b.bezierCurveTo(616, 480, 616, 420, 630, 372);
      this.stem = b;
      const f = new Path2D();   // folds: fixed curves for the look of gyri (drawing, not data)
      const folds = [[[230, 110], [260, 180], [220, 260]], [[300, 70], [330, 150], [290, 230]], [[438, 60], [420, 150], [370, 260]],
        [[470, 64], [450, 160], [404, 262]], [[560, 46], [560, 120], [520, 190]], [[660, 66], [640, 140], [680, 210]],
        [[760, 120], [730, 180], [770, 260]], [[300, 330], [420, 300], [560, 330]], [[600, 250], [700, 260], [820, 300]]];
      for (const [a, m, z] of folds) { f.moveTo(...a); f.quadraticCurveTo(...m, ...z); }
      this.folds = f;
    }
    const g = ctx.createRadialGradient(480, 210, 30, 480, 230, 470);
    g.addColorStop(0, rgba(REST, 0.55 * tone));
    g.addColorStop(1, rgba(REST, 0.35));
    ctx.fillStyle = g;
    ctx.fill(this.outline);
    ctx.fillStyle = rgba(REST, 0.45 * tone);
    ctx.fill(this.cerebellum); ctx.fill(this.stem);
    ctx.lineWidth = 1.4;
    ctx.strokeStyle = rgba(DIM, 0.38 * tone);
    ctx.stroke(this.outline); ctx.stroke(this.cerebellum); ctx.stroke(this.stem);
    ctx.lineWidth = 1;
    ctx.strokeStyle = rgba(DIM, 0.12 * tone);
    ctx.stroke(this.folds);
    ctx.fillStyle = rgba(REST, 0.22 * tone);   // deep structures seen through the cortex
    ctx.beginPath(); ctx.ellipse(...this.striatum, 54, 30, -0.2, 0, 7); ctx.fill();
    ctx.beginPath(); ctx.ellipse(595, 330, 82, 26, 0.1, 0, 7); ctx.fill();
    ctx.beginPath(); ctx.ellipse(...this.vta, 22, 14, 0, 0, 7); ctx.fill();
  }

  drawWash(ctx) {
    if (this.wash < 0.02) return;
    // dopamine: a diffuse wash from the midbrain nucleus over the striatum and the cortex
    const c = this.washSign > 0 ? GOLD : BLUE;
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    const r = 120 + (1 - this.wash) * 420;
    const g = ctx.createRadialGradient(...this.vta, 4, ...this.vta, r);
    g.addColorStop(0, rgba(c, 0.2 * this.wash));
    g.addColorStop(0.6, rgba(c, 0.06 * this.wash));
    g.addColorStop(1, rgba(c, 0));
    ctx.fillStyle = g;
    ctx.clip(this.outline);
    ctx.fillRect(0, 0, W, H);
    ctx.restore();
  }

  drawRetina(ctx, retina) {
    const R = this.retina;
    if (retina && retina.length === 1764) {
      if (!this.retinaCanvas) { this.retinaCanvas = document.createElement('canvas'); this.retinaCanvas.width = this.retinaCanvas.height = 42; }
      const rc = this.retinaCanvas.getContext('2d'), im = rc.createImageData(42, 42);
      for (let i = 0; i < 1764; i++) { const q = retina[i]; im.data[i * 4] = q; im.data[i * 4 + 1] = q * 0.95; im.data[i * 4 + 2] = q; im.data[i * 4 + 3] = 255; }
      rc.putImageData(im, 0, 0);
      this.retinaPixels = retina;
    }
    ctx.save();
    ctx.transform(1, -0.08, 0.06, 1, 0, 40);   // the screen lies on the occipital surface
    ctx.globalAlpha = 0.92;
    if (this.retinaCanvas) { ctx.imageSmoothingEnabled = false; ctx.drawImage(this.retinaCanvas, R.x, R.y - 40, R.w, R.h); }
    ctx.strokeStyle = rgba(DIM, 0.45);
    ctx.strokeRect(R.x, R.y - 40, R.w, R.h);
    ctx.restore();
  }

  drawTracts(ctx, act, tone, t) {
    const E = this.graph.edges, G = this.edgeGeom, w = this.weights, pix = this.retinaPixels;
    const buckets = new Map(), flashes = [];
    // each tract's brightness is relative to its strongest synapse: pixel synapses are small
    let maxIn = 1e-9, maxInner = 1e-9;
    for (let i = 0; i < E.length; i++) { const m = Math.abs(w[i]); if (E[i][0] === 0) maxIn = Math.max(maxIn, m); else maxInner = Math.max(maxInner, m); }
    for (let i = 0; i < E.length; i++) {
      const [k, s] = E[i];
      // a synapse's brightness is the message it carries: |weight x presynaptic activation|
      const pre = k === 0 ? (pix ? pix[Math.floor(Math.floor(s / 84) / 2) * 42 + Math.floor((s % 84) / 2)] / 255 : 0.2) : Math.abs(act[s] ?? 0);
      const a = clamp(Math.abs(w[i]) / (k === 0 ? maxIn : maxInner) * pre * (k === 0 ? 1.6 : 1.2)) * tone;
      if (this.flash[i] > 0.05) flashes.push(i);
      if (a < 0.03) continue;
      const col = k === 0 ? 'in' : (w[i] >= 0 ? 'ex' : 'ih');
      const level = Math.min(5, Math.floor(a * 6)), key = col + level;
      let b = buckets.get(key);
      if (!b) { b = { col, a: (level + 0.6) / 6, list: [] }; buckets.set(key, b); }
      b.list.push(i);
    }
    const COL = { in: AMBER, ex: AMBER, ih: CYAN };
    for (const b of buckets.values()) {
      ctx.strokeStyle = rgba(COL[b.col], (b.col === 'in' ? 0.5 : 0.42) * b.a);
      ctx.lineWidth = b.col === 'in' ? 0.6 : 0.5 + b.a * 0.9;
      ctx.beginPath();
      for (const i of b.list) { const g = G[i]; ctx.moveTo(...g.S); ctx.quadraticCurveTo(...g.C, ...g.P); }
      ctx.stroke();
    }
    // plasticity: synapses whose weight the last lessons or outcomes moved flash gold and thicken
    for (const i of flashes) {
      const g = G[i], f = this.flash[i];
      ctx.strokeStyle = rgba(GOLD, 0.85 * f);
      ctx.lineWidth = 1 + 2.5 * f;
      ctx.beginPath(); ctx.moveTo(...g.S); ctx.quadraticCurveTo(...g.C, ...g.P); ctx.stroke();
    }
    // impulses along the synapses carrying the largest messages
    ctx.setLineDash([3, 11]); ctx.lineDashOffset = -t * 60;
    ctx.strokeStyle = rgba([255, 230, 170], 0.45 * tone); ctx.lineWidth = 1;
    ctx.beginPath();
    let n = 0;
    for (let i = 0; i < E.length && n < 18; i++) {
      const [k, s] = E[i];
      if (k !== 0 && Math.abs(w[i] * (act[s] ?? 0)) > 0.25) { const g = G[i]; ctx.moveTo(...g.S); ctx.quadraticCurveTo(...g.C, ...g.P); n++; }
    }
    ctx.stroke(); ctx.setLineDash([]);
  }

  // each region glows with its population's mean activation
  drawRegionGlow(ctx, act, tone) {
    const P = this.pops;
    const mean = (p) => { let a = 0; for (let i = 0; i < p.count; i++) a += Math.abs(act[p.start + i] ?? 0); return a / p.count; };
    const glow = (at, rx, ry, c, m) => {
      ctx.save(); ctx.translate(...at); ctx.scale(1, ry / rx);
      const g = ctx.createRadialGradient(0, 0, 4, 0, 0, rx);
      g.addColorStop(0, rgba(c, 0.28 * clamp(m * 1.6) * tone)); g.addColorStop(1, rgba(c, 0));
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(0, 0, rx, 0, 7); ctx.fill(); ctx.restore();
    };
    glow([610, 112], 170, 80, AMBER, mean(P.association));
    glow([240, 200], 130, 120, AMBER, mean(P.trace));
    glow([395, 160], 60, 100, GOLD, mean(P.motor));
    glow([595, 330], 90, 34, VIOLET, mean(P.memory));
  }

  drawNeurons(ctx, act, v, tone) {
    const S = this.sprites, pos = this.pos, P = this.pops;
    const dot = (p, val, sprite, base = 5, gain = 12) => {
      const m = clamp(Math.abs(val) / 0.8), R = base + gain * m;
      ctx.globalAlpha = (0.35 + 0.65 * m) * tone;
      ctx.drawImage(sprite, p[0] - R, p[1] - R, 2 * R, 2 * R);
    };
    for (const name of ['association', 'trace']) {
      const p = P[name];
      for (let i = 0; i < p.count; i++) { const val = act[p.start + i] ?? 0; dot(pos[p.start + i], val, val >= 0 ? S.amber : S.cyan, 6, 13); }
    }
    // motor strip: the executed action gold; while watching, the teacher's action green and a wrong own answer red
    const M = P.motor;
    for (let i = 0; i < M.count; i++) {
      const p = pos[M.start + i];
      dot(p, act[M.start + i] ?? 0, S.amber, 6, 16);
      if (v.action === i) { ctx.globalAlpha = 0.9; ctx.drawImage(S.gold, p[0] - 22, p[1] - 22, 44, 44); }
      if (v.phase === 'watching' && v.teacher === i) { ctx.globalAlpha = 0.5 + 0.5 * this.lessonPulse; ctx.drawImage(S.green, p[0] - 18, p[1] - 18, 36, 36); }
      if (v.phase === 'watching' && v.own != null && v.own !== v.teacher && v.own === i) { ctx.globalAlpha = 0.8; ctx.drawImage(S.red, p[0] - 16, p[1] - 16, 32, 32); }
    }
    const Mem = P.memory;
    for (let i = 0; i < Mem.count; i++) dot(pos[Mem.start + i], act[Mem.start + i] ?? 0, S.violet, 5, 14);
    const V = P.value, val = act[V.start] ?? 0;
    dot(pos[V.start], val, val >= 0 ? S.amber : S.cyan, 8, 18);
    const d = this.wash * this.washSign;
    ctx.globalAlpha = clamp(0.3 + Math.abs(d)) * tone;
    const R = 10 + 22 * Math.abs(d);
    ctx.drawImage(d >= 0 ? S.gold : S.blue, this.vta[0] - R, this.vta[1] - R, 2 * R, 2 * R);
    ctx.globalAlpha = 1;
  }

  drawLabels(ctx, v) {
    ctx.font = '10px ui-monospace, monospace';
    ctx.fillStyle = rgba(BONE, 0.55);
    const L = (s, x, y) => ctx.fillText(s, x, y);
    L('ASSOCIATION CORTEX', 560, 40); L('PREFRONTAL · WORKING TRACE', 150, 62); L('MOTOR STRIP', 418, 62);
    L('STRIATUM · CRITIC', 432, 324); L('DOPAMINE', 532, 432); L('HIPPOCAMPUS · MEMORY', 548, 372);
    L('RETINA → VISUAL CORTEX', 776, 116);
    const M = this.pops.motor, meanings = this.graph.meanings || [];
    ctx.font = '9px ui-monospace, monospace';
    ctx.textAlign = 'right';
    for (let i = 0; i < M.count; i++) {
      const p = this.pos[M.start + i];
      ctx.fillStyle = v.action === i ? rgba(GOLD, 0.95) : rgba(BONE, 0.45);
      ctx.fillText(meanings[i] || '', p[0] - 14, p[1] + 3);
    }
    ctx.textAlign = 'left';
  }

  drawHud(ctx, v, sweep, phase, live, calm) {
    const chip = (x, y, text, c, on) => {
      ctx.font = '10px ui-monospace, monospace';
      const w = ctx.measureText(text).width + 16;
      ctx.fillStyle = rgba(c, on ? 0.18 : 0.05); ctx.strokeStyle = rgba(c, on ? 0.8 : 0.25);
      ctx.beginPath(); ctx.roundRect(x, y, w, 20, 10); ctx.fill(); ctx.stroke();
      ctx.fillStyle = rgba(c, on ? 1 : 0.4); ctx.fillText(text, x + 8, y + 14);
      return x + w + 8;
    };
    let x = chip(14, 12, 'WATCHING THE TEACHER · A LESSON PER SCREEN', GREEN, phase === 'watching');
    x = chip(x, 12, 'AT THE CONTROLS · LEARNING FROM REWARD', AMBER, phase === 'playing');
    if (live) chip(x, 12, calm ? 'CALM · NO LEARNING' : `AROUSED ${(v.arousal ?? 0).toFixed(2)} · LEARNING`, calm ? BONE : VIOLET, !calm);
    ctx.font = '10px ui-monospace, monospace';
    // the settle, sweep by sweep: the largest movement falling to the tolerance
    const R = this.replay, bx = 14, by = H - 76, bw = 210, bh = 56;
    ctx.fillStyle = rgba([10, 8, 6], 0.7); ctx.fillRect(bx, by, bw, bh);
    ctx.strokeStyle = rgba(BONE, 0.15); ctx.strokeRect(bx, by, bw, bh);
    ctx.fillStyle = rgba(BONE, 0.7);
    ctx.fillText(sweep ? `SETTLING FROM REST · SWEEP ${sweep.of + 1} OF ${sweep.sweeps}` : `SETTLED IN ${v.sweeps ?? '–'} SWEEPS`, bx + 8, by + 14);
    if (R && R.movement && R.movement.length) {
      const mv = R.movement, tol = R.tolerance || 3e-3;
      const lo = Math.log10(tol / 4), hi = Math.log10(Math.max(...mv, tol * 10));
      const X = (i) => bx + 8 + i / Math.max(1, mv.length - 1) * (bw - 16);
      const Y = (m) => by + bh - 6 - (Math.log10(Math.max(m, 1e-7)) - lo) / (hi - lo || 1) * (bh - 26);
      ctx.strokeStyle = rgba(CYAN, 0.45); ctx.setLineDash([2, 3]);
      ctx.beginPath(); ctx.moveTo(bx + 8, Y(tol)); ctx.lineTo(bx + bw - 8, Y(tol)); ctx.stroke(); ctx.setLineDash([]);
      ctx.strokeStyle = rgba(AMBER, 0.9); ctx.beginPath();
      const upto = sweep ? Math.min(mv.length, sweep.of + 1) : mv.length;
      for (let i = 0; i < upto; i++) { if (i) ctx.lineTo(X(i), Y(mv[i])); else ctx.moveTo(X(i), Y(mv[i])); }
      ctx.stroke();
    }
    // plasticity and dopamine numbers
    const nx = W - 260, ny = H - 76;
    ctx.fillStyle = rgba([10, 8, 6], 0.7); ctx.fillRect(nx, ny, 246, 56);
    ctx.strokeStyle = rgba(BONE, 0.15); ctx.strokeRect(nx, ny, 246, 56);
    ctx.fillStyle = rgba(GOLD, 0.85);
    ctx.fillText(`SYNAPSES CHANGED > 1e-4: ${(v.changed ?? 0).toLocaleString()}`, nx + 8, ny + 16);
    const d = v.dopamine ?? 0;
    ctx.fillStyle = rgba(d >= 0 ? GOLD : BLUE, 0.85);
    ctx.fillText(phase === 'playing' ? `DOPAMINE ${d >= 0 ? '+' : ''}${d.toFixed(3)}   VALUE ${(v.value ?? 0).toFixed(2)}`
      : `LESSON ${v.lessons ?? 0} · TEACHER'S ACTION GREEN`, nx + 8, ny + 32);
    ctx.fillStyle = rgba(BONE, 0.5);
    ctx.fillText(phase === 'playing' ? `REWARD SINCE THE LAST VIEW ${v.reward ?? 0}`
      : (v.own != null && v.own !== v.teacher ? 'ITS OWN ANSWER (RED) DISAGREED' : 'ITS OWN ANSWER AGREED'), nx + 8, ny + 48);
  }

  frameStats() {
    const f = this.frames.slice(-300).sort((a, b) => a - b);
    if (!f.length) return null;
    return { n: f.length, mean: f.reduce((a, b) => a + b, 0) / f.length, p95: f[Math.floor(f.length * 0.95)] };
  }
}
