// The inspected creature's brain, drawn as a brain seen from the side. Every light on it is the
// creature's real state at this moment, read in its worker (patchworld/inspect.py):
//   neurons     the activation of each neuron, sweep by sweep through the settle the action came from
//   tracts      the signal each bundle of synapses carried in the settled state (weight x presynaptic
//               activation), excitatory warm, inhibitory cool; flashes where this moment's lesson
//               changed synapses
//   dopamine    the critic's prediction error of this moment's lesson (gold burst, blue dip)
//   arousal     the arousal level; aroused = learning on
//   memory      the recall memory's attention over its slots, each read slot tied to the place it stored
// Regions are named for the role their Cadence population plays, not as claims of anatomy.

const TAU = Math.PI * 2;
const ACTIONS = ['north', 'east', 'south', 'west', 'eat', 'drink'];
const VISION_KINDS = ['berry', 'root', 'leaf', 'water', 'predator', 'creature'];
const DIRS = ['N', 'E', 'S', 'W'];
const BODY = ['energy', 'thirst', 'light', 'nausea', 'cold'];
const UNDER = ['berry', 'root', 'leaf', 'cache', 'water'];

// region centres in a 1000 x 560 frame; the front of the head is on the left. `role` names the
// Cadence population; `explain` is the card a visitor reads on the page.
const R = {
  prefrontal: { x: 205, y: 215, rx: 95, ry: 70, label: 'prefrontal cortex', role: 'population "prefrontal": the working trace',
    explain: 'The working trace: it carries what the brain made of the last moment into this one. A short-term memory of the creature’s own state.' },
  motor: { x: 395, y: 120, rx: 120, ry: 26, label: 'motor strip', role: 'population "motor": six motor neurons',
    explain: 'Six neurons, one for each action: north, east, south, west, eat, drink. The one brightest when the brain has settled is what the creature does; its name lights white.' },
  module_0: { x: 560, y: 175, rx: 85, ry: 55, label: 'parietal association cortex', role: 'population "module_0"',
    explain: 'A second association region, which some creatures inherit. It settles together with the rest of the brain.' },
  association: { x: 470, y: 265, rx: 120, ry: 75, label: 'association cortex', role: 'population "association"',
    explain: 'Where the senses, the memory and the motor strip meet. All of them settle together into one agreed state, and the action is read from it.' },
  vision: { x: 790, y: 245, rx: 85, ry: 80, label: 'visual cortex', role: 'sensory neurons 1-24',
    explain: 'What the creature sees in four directions: the nearest berry, root, leaf, water, predator and other creature within its sense range. At night it sees half as far.' },
  body: { x: 640, y: 120, rx: 70, ry: 30, label: 'insula: the body', role: 'sensory neurons 30-34',
    explain: 'How its body feels: energy, thirst, daylight, nausea while a poisoning lasts, and the cold of the air. Nothing here names the season.' },
  under: { x: 590, y: 350, rx: 55, ry: 26, label: 'taste and touch', role: 'sensory neurons 25-29',
    explain: 'What lies underfoot: a berry, a root, a leaf or a hidden cache, and water beside it.' },
  place: { x: 545, y: 412, rx: 42, ry: 20, label: 'entorhinal: place', role: 'sensory neurons 35-38',
    explain: 'Where the creature is in the world.' },
  hippo: { x: 430, y: 395, rx: 120, ry: 40, label: 'hippocampus', role: 'the recall memory’s slots and the associative store',
    explain: 'Its memory. It stores what an action brought in a situation (a purple ring flashes when it writes). With the recall gene it also keeps its recent moments in slots, which light gold when the brain reads them.' },
  recall: { x: 345, y: 455, rx: 55, ry: 22, label: 'recall read', role: 'population "recall"',
    explain: 'What the recall memory gives back this moment: a remembered moment that resembles this one.' },
  next: { x: 470, y: 470, rx: 55, ry: 20, label: 'recall: what came next', role: 'population "next"',
    explain: 'The moment that followed the remembered one: a hint of what may come next.' },
  striatum: { x: 345, y: 300, rx: 42, ry: 30, label: 'striatum', role: 'the critic and the actor',
    explain: 'The critic judges how good the situation is; the actor picks the action. Calm, the brain takes its settled answer; aroused, it tries alternatives.' },
  thalamus: { x: 560, y: 285, rx: 26, ry: 18, label: 'thalamus', role: 'where the observation enters',
    explain: 'Where each moment’s senses enter the brain.' },
  vta: { x: 455, y: 340, rx: 20, ry: 13, label: 'dopamine nucleus', role: 'the critic’s prediction error',
    explain: 'After each lesson it flashes gold when the outcome was better than the brain expected, blue when worse, as when a berry poisons. That signal tells the synapses which way to change.' },
  lc: { x: 560, y: 470, rx: 18, ry: 12, label: 'locus coeruleus', role: 'the arousal level',
    explain: 'Arousal. A surprise (a berry that poisons) or a want (too little food) raises it; above the creature’s threshold the brain learns from what its actions bring, and the whole brain glows gold. Calm, it acts and learns nothing.' },
};

function sunflower(n, rx, ry) {
  const out = [];
  for (let i = 0; i < n; i++) {
    const r = Math.sqrt((i + 0.5) / n), a = i * 2.39996323;
    out.push([Math.cos(a) * r * rx * 0.88, Math.sin(a) * r * ry * 0.85]);
  }
  return out;
}

function sprite(rgb, size = 32) {
  const c = document.createElement('canvas'); c.width = c.height = size;
  const g = c.getContext('2d'); const h = size / 2;
  const grad = g.createRadialGradient(h, h, 0, h, h, h);
  grad.addColorStop(0, `rgba(${rgb},1)`); grad.addColorStop(0.25, `rgba(${rgb},0.65)`); grad.addColorStop(1, `rgba(${rgb},0)`);
  g.fillStyle = grad; g.fillRect(0, 0, size, size);
  return c;
}

export class BrainView {
  constructor(canvas, wrap) {
    this.cv = canvas; this.g = canvas.getContext('2d'); this.wrap = wrap;
    this.W = 1000; this.H = 560;
    this.anat = null; this.kind = 'live'; this.layout = null;
    this.cur = null; this.prev = null; this.recvAt = 0; this.duration = 300;
    this.dopa = { v: 0, at: -1e9 }; this.changedTotal = 0; this.flash = new Map(); this.store = -1e9;
    this.particles = []; this.hover = null; this.terrain = null; this.world = { w: 48, h: 32 };
    this.sprites = { pos: sprite('80,240,225'), neg: sprite('255,110,140'), gold: sprite('255,206,102'), blue: sprite('110,170,255'), white: sprite('255,255,255') };
    this.frameMs = 0; this.frames = 0;
    this.silhouette = this.drawSilhouette();
    // the explanations: a spot over every region and its name (shared/cadence-explain.js), laid out
    // again when the canvas changes size
    if (window.ResizeObserver) new ResizeObserver(() => this.layoutSpots()).observe(canvas);
    requestAnimationFrame((t) => this.loop(t));
  }

  setAnatomy(anat, kind) {
    this.anat = anat; this.kind = kind; this.cur = null; this.prev = null; this.changedTotal = 0;
    this.flash.clear(); this.particles = [];
    if (!anat) { this.layout = null; this.layoutSpots(); return; }
    const P = anat.populations, L = {};
    const place = (key, region, n) => { const r = R[region]; L[key] = sunflower(n, r.rx, r.ry).map(([dx, dy]) => [r.x + dx, r.y + dy]); };
    // sensory neurons: vision as a 4 x 6 grid, the others in their own regions
    const s = [];
    for (let d = 0; d < 4; d++) for (let k = 0; k < 6; k++) s.push([R.vision.x - 62 + k * 25, R.vision.y - 48 + d * 30]);
    UNDER.forEach((_, i) => s.push([R.under.x - 44 + i * 22, R.under.y]));
    BODY.forEach((_, i) => s.push([R.body.x - 50 + i * 25, R.body.y]));
    for (let i = 0; i < 4; i++) s.push([R.place.x - 27 + i * 18, R.place.y]);
    L.sensory = s;
    if (P.module_0) place('module_0', 'module_0', P.module_0);
    place('association', 'association', P.association || 0);
    place('prefrontal', 'prefrontal', P.prefrontal || 0);
    L.motor = ACTIONS.map((_, i) => [R.motor.x - 100 + i * 40, R.motor.y + (i - 2.5) * 4]);
    if (P.recall) place('recall', 'recall', P.recall);
    if (P.next) place('next', 'next', P.next);
    // where each tract leaves and arrives; sensory bundles run from their region through the thalamus
    const SENSE_REGION = { vision: 'vision', underfoot: 'under', body: 'body', place: 'place' };
    const centre = (pop) => pop.startsWith('sensory:') ? [R[SENSE_REGION[pop.slice(8)]].x, R[SENSE_REGION[pop.slice(8)]].y]
      : pop === 'motor' ? [R.motor.x, R.motor.y + 10] : R[pop] ? [R[pop].x, R[pop].y] : null;
    this.tractEnds = {};
    for (const key of Object.keys(anat.tracts)) {
      const [a, b] = key.split('>');
      const c1 = centre(a), c2 = centre(b);
      if (!c1 || !c2) continue;
      // each tract leaves and enters at its own point of its regions
      let h = 0; for (const ch of key) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
      const reg = (pop) => pop.startsWith('sensory:') ? R[SENSE_REGION[pop.slice(8)]] : R[pop] || R.motor;
      const jit = (pt, r, salt) => [pt[0] + (((h >> salt) & 255) / 255 - 0.5) * r.rx * 0.8, pt[1] + (((h >> (salt + 8)) & 255) / 255 - 0.5) * r.ry * 0.8];
      const p1 = a === b ? c1 : jit(c1, reg(a), 0), p2 = a === b ? c2 : jit(c2, reg(b), 16);
      this.tractEnds[key] = { p1, p2, via: a.startsWith('sensory:') ? [R.thalamus.x, R.thalamus.y] : null, n: anat.tracts[key] };
    }
    // hippocampal slots along the hippocampus's curve
    const n = anat.slots || 0;
    this.slots = Array.from({ length: n }, (_, i) => {
      const t = i / Math.max(1, n - 1), a = Math.PI * (0.15 + 0.7 * t);
      return [R.hippo.x - Math.cos(a) * R.hippo.rx, R.hippo.y + 8 - Math.sin(a) * R.hippo.ry * 0.9];
    });
    this.layout = L;
    this.layoutSpots();
  }

  shown(key) {
    const L = this.layout; if (!L) return false;
    if (key === 'module_0' || key === 'recall' || key === 'next') return !!L[key];
    return true;
  }

  layoutSpots() {
    const X = window.CadenceExplain, wrap = this.wrap;
    if (!X || !wrap) return;
    X.clearSpots(wrap);
    const w = this.cv.clientWidth;
    if (!this.layout || !w) return;
    const k = w / this.W, g = this.g;
    g.save(); g.setTransform(1, 0, 0, 1, 0, 0); g.font = '16px Inter, sans-serif';
    const add = (b, text, title, key, mark) => {
      const el = X.spot(wrap, { x: b.x * k, y: b.y * k, w: b.w * k, h: b.h * k }, text, { title, mark });
      if (key) {
        el.addEventListener('pointerenter', () => { this.hover = key; });
        el.addEventListener('pointerleave', () => { if (this.hover === key) this.hover = null; });
      }
    };
    // the regions, the largest first so that the small nuclei lie on top; then their names, each
    // with a question mark
    const keys = Object.keys(R).filter((key) => this.shown(key)).sort((a, b) => R[b].rx * R[b].ry - R[a].rx * R[a].ry);
    for (const key of keys) {
      const r = R[key];
      add({ x: r.x - r.rx * 0.9, y: r.y - r.ry * 0.9, w: r.rx * 1.8, h: r.ry * 1.8 }, r.explain, r.label, key, 'none');
    }
    for (const key of keys) {
      const r = R[key], tw = g.measureText(r.label).width, ly = r.y - r.ry - (key === 'motor' ? 30 : 8);
      add({ x: r.x - tw / 2 - 3, y: ly - 15, w: tw + 20, h: 20 }, r.explain, r.label, key, 'top-right');
    }
    g.restore();
    add({ x: 8, y: 8, w: 560, h: 38 }, 'Whether the brain is learning at this moment (gold: aroused, learning; grey: calm), its settle sweep by sweep (its neurons drive one another until they agree, and the largest change shrinks every sweep), and the dopamine of its last lesson.', 'This moment', null, 'top-left');
    add({ x: 470, y: 482, w: 522, h: 76 }, 'Counts from the brain: the synapses this moment’s lesson changed, and all it changed since you opened it; the surprise and the want that add up to its arousal; its size.', 'The counts', null, 'top-right');
    if (this.slots && this.slots.length) {
      add({ x: 36, y: 384, w: 226, h: 164 }, 'A small map of the world. A thread runs from each memory slot the brain reads to the place where it stored that moment; the teal dot is where the creature is.', 'Where its memories happened', null, 'top-right');
    }
  }

  push(reply, context) {
    if (!reply || !reply.brain) return;
    const b = reply.brain;
    this.prev = this.cur; this.cur = { ...b, action: reply.action, mode: reply.mode, context };
    this.recvAt = performance.now();
    this.duration = Math.max(120, Math.min(900, (context && context.tickMs) || 300) * 0.85);
    if (b.dopamine && Number.isFinite(b.dopamine.dopamine)) this.dopa = { v: b.dopamine.dopamine, at: this.recvAt, td: b.dopamine.td_error, value: b.dopamine.value };
    if (b.changed) {
      this.changedTotal += b.changed;
      for (const [k, [n, sum]] of Object.entries(b.changed_by_tract || {})) this.flash.set(k, { n, sum, at: this.recvAt });
    }
    if (b.arousal && b.arousal.recorded) this.store = this.recvAt;
  }

  drawSilhouette() {
    const c = document.createElement('canvas'); c.width = this.W; c.height = this.H;
    const g = c.getContext('2d');
    // cerebrum
    g.beginPath();
    g.moveTo(130, 300);
    g.bezierCurveTo(95, 170, 220, 60, 420, 55);
    g.bezierCurveTo(620, 45, 860, 90, 900, 230);
    g.bezierCurveTo(930, 320, 880, 380, 790, 395);
    g.bezierCurveTo(700, 410, 640, 420, 600, 440);
    g.bezierCurveTo(520, 480, 330, 500, 250, 440);
    g.bezierCurveTo(190, 400, 150, 360, 130, 300);
    const grad = g.createRadialGradient(480, 230, 40, 480, 260, 520);
    grad.addColorStop(0, 'rgba(48,62,104,0.55)'); grad.addColorStop(1, 'rgba(14,18,34,0.55)');
    g.fillStyle = grad; g.fill();
    g.strokeStyle = 'rgba(140,160,220,0.25)'; g.lineWidth = 2; g.stroke();
    // gyri: soft folds
    g.strokeStyle = 'rgba(160,180,240,0.07)'; g.lineWidth = 7; g.lineCap = 'round';
    for (let i = 0; i < 9; i++) {
      g.beginPath(); const x = 210 + i * 75;
      g.moveTo(x, 90 + (i % 3) * 10); g.bezierCurveTo(x + 40, 160, x - 30, 230, x + 15, 330 - (i % 2) * 30); g.stroke();
    }
    // central sulcus
    g.strokeStyle = 'rgba(160,180,240,0.12)'; g.lineWidth = 3;
    g.beginPath(); g.moveTo(470, 62); g.bezierCurveTo(450, 140, 500, 190, 470, 250); g.stroke();
    // cerebellum and brainstem
    g.beginPath(); g.ellipse(810, 440, 95, 55, -0.15, 0, TAU);
    g.fillStyle = 'rgba(40,52,90,0.5)'; g.fill(); g.strokeStyle = 'rgba(140,160,220,0.2)'; g.lineWidth = 1.5; g.stroke();
    for (let i = 0; i < 6; i++) { g.beginPath(); g.ellipse(810, 440, 85 - i * 12, 46 - i * 7, -0.15, Math.PI * 1.05, Math.PI * 1.95); g.strokeStyle = 'rgba(160,180,240,0.08)'; g.stroke(); }
    g.beginPath(); g.moveTo(560, 430); g.bezierCurveTo(580, 480, 600, 520, 610, 560); g.lineTo(670, 560); g.bezierCurveTo(660, 510, 650, 470, 640, 430);
    g.fillStyle = 'rgba(36,46,80,0.6)'; g.fill();
    return c;
  }

  loop(now) {
    requestAnimationFrame((t) => this.loop(t));
    if (!this.cv.isConnected || this.cv.offsetParent === null) return;
    const t0 = performance.now();
    this.draw(now);
    const dt = performance.now() - t0;
    this.frameMs = this.frames ? 0.95 * this.frameMs + 0.05 * dt : dt; this.frames += 1;
  }

  // the activation of population `pop` at the present point of the settle animation
  values(pop) {
    const c = this.cur; if (!c || !c.frames || !c.frames.length) return null;
    const k = Math.min(1, (performance.now() - this.recvAt) / this.duration);
    const f = k * (c.frames.length - 1), i = Math.floor(f), j = Math.min(c.frames.length - 1, i + 1), u = f - i;
    const A = c.frames[i][pop], B = c.frames[j][pop]; if (!A) return null;
    return A.map((v, n) => v + (B[n] - v) * u);
  }

  sweepNow() {
    const c = this.cur; if (!c || !c.frames) return null;
    const k = Math.min(1, (performance.now() - this.recvAt) / this.duration);
    const i = Math.round(k * (c.frames.length - 1));
    return { sweep: c.frame_sweeps[i], of: c.sweeps, movement: c.movement[i], done: k >= 1 };
  }

  draw(now) {
    const g = this.g, W = this.W, H = this.H;
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.clearRect(0, 0, W, H);
    g.fillStyle = '#05070d'; g.fillRect(0, 0, W, H);
    if (!this.layout) {
      g.fillStyle = '#5c6684'; g.font = '14px Inter, sans-serif'; g.textAlign = 'center';
      g.fillText(this.kind === 'random' ? 'A random walker has no brain.' : 'Reading the brain…', W / 2, H / 2); return;
    }
    // gentle camera: a slow breath of scale and drift
    const s = 1 + 0.012 * Math.sin(now / 3100), dx = 6 * Math.sin(now / 4700), dy = 4 * Math.sin(now / 3900);
    g.setTransform(s, 0, 0, s, (1 - s) * W / 2 + dx, (1 - s) * H / 2 + dy);
    const c = this.cur, ar = c?.arousal || {};
    const aroused = ar.mode === 'aroused';
    const level = Math.max(0, Math.min(1.5, ar.level || 0));
    // the whole brain brightens with arousal
    g.globalAlpha = 0.75 + 0.25 * Math.min(1, level);
    g.drawImage(this.silhouette, 0, 0);
    g.globalAlpha = 1;
    if (aroused) {
      const halo = g.createRadialGradient(R.lc.x, R.lc.y, 5, 480, 260, 520);
      halo.addColorStop(0, `rgba(255,206,102,${0.22 + 0.1 * Math.sin(now / 160)})`); halo.addColorStop(1, 'rgba(255,206,102,0)');
      g.fillStyle = halo; g.fillRect(0, 0, W, H);
    }
    // dopamine: a wash from the nucleus over striatum and cortex, fading over a second
    const dAge = (performance.now() - this.dopa.at) / 1100;
    if (dAge < 1) {
      const v = this.dopa.v, rgb = v >= 0 ? '255,206,102' : '110,170,255', a = Math.min(1, Math.abs(v)) * (1 - dAge) * 0.55;
      const wash = g.createRadialGradient(R.vta.x, R.vta.y, 4, R.vta.x, R.vta.y - 60, 380 * (0.4 + dAge));
      wash.addColorStop(0, `rgba(${rgb},${a})`); wash.addColorStop(0.5, `rgba(${rgb},${a * 0.35})`); wash.addColorStop(1, `rgba(${rgb},0)`);
      g.fillStyle = wash; g.fillRect(0, 0, W, H);
    }
    // labelled regions (soft outlines)
    g.font = '16px Inter, sans-serif'; g.textAlign = 'center';
    for (const [key, r] of Object.entries(R)) {
      if ((key === 'module_0' && !this.layout.module_0) || ((key === 'recall' || key === 'next') && !this.layout[key])) continue;
      g.beginPath(); g.ellipse(r.x, r.y, r.rx, r.ry, 0, 0, TAU);
      g.fillStyle = this.hover === key ? 'rgba(120,150,230,0.12)' : 'rgba(120,150,230,0.04)'; g.fill();
      g.strokeStyle = this.hover === key ? 'rgba(170,190,255,0.5)' : 'rgba(150,170,240,0.13)'; g.lineWidth = 1; g.stroke();
      g.fillStyle = this.hover === key ? '#e9edf7' : 'rgba(175,188,225,0.62)';
      g.fillText(r.label, r.x, r.y - r.ry - (key === 'motor' ? 30 : 8));
    }
    this.drawTracts(g, now, false);
    // the glowing layer (neurons, impulses, nuclei), drawn once sharp and once blurred for bloom
    if (!this.glow) { this.glow = document.createElement('canvas'); this.glow.width = W; this.glow.height = H; }
    const L = this.glow.getContext('2d');
    L.setTransform(1, 0, 0, 1, 0, 0); L.clearRect(0, 0, W, H);
    L.setTransform(s, 0, 0, s, (1 - s) * W / 2 + dx, (1 - s) * H / 2 + dy);
    L.globalCompositeOperation = 'lighter';
    this.drawTracts(L, now, true);
    this.drawNeurons(L);
    this.drawNuclei(L, now);
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalCompositeOperation = 'lighter';
    g.filter = 'blur(7px)'; g.globalAlpha = 0.9; g.drawImage(this.glow, 0, 0);
    g.filter = 'none'; g.globalAlpha = 1; g.drawImage(this.glow, 0, 0);
    g.globalCompositeOperation = 'source-over';
    g.setTransform(s, 0, 0, s, (1 - s) * W / 2 + dx, (1 - s) * H / 2 + dy);
    this.drawHippocampus(g, now);
    this.drawMotorLabels(g);
    g.setTransform(1, 0, 0, 1, 0, 0);
    this.drawHud(g, now);
  }

  // one tract: a bundle of fibres on a curve (a self-tract, such as the motor strip's lateral
  // inhibition, is an arc beside its region)
  tractPath(t, off) {
    const [x1, y1] = t.p1, [x2, y2] = t.p2;
    if (x1 === x2 && y1 === y2) return [[x1 - 40, y1 + off], [x1, y1 - 46 + off], [x1 + 40, y1 + off]];
    if (t.via) return [[x1, y1 + off], [t.via[0] + off * 0.6, t.via[1] + off], [x2, y2 + off]];
    const mx = (x1 + x2) / 2 + (y2 - y1) * 0.18, my = (y1 + y2) / 2 - Math.abs(x2 - x1) * 0.12;
    return [[x1, y1 + off], [mx, my + off], [x2, y2 + off]];
  }

  strokePath(g, [[x1, y1], [cx, cy], [x2, y2]]) { g.beginPath(); g.moveTo(x1, y1); g.quadraticCurveTo(cx, cy, x2, y2); g.stroke(); }

  pointOn([[x1, y1], [cx, cy], [x2, y2]], t) {
    return [(1 - t) ** 2 * x1 + 2 * (1 - t) * t * cx + t * t * x2, (1 - t) ** 2 * y1 + 2 * (1 - t) * t * cy + t * t * y2];
  }

  drawTracts(g, now, glow) {
    const c = this.cur; if (!c || !c.tracts) return;
    const top = Math.max(1e-6, ...Object.values(c.tracts).map(([e, i]) => Math.max(e, i)));
    for (const [key, [exc, inh]] of Object.entries(c.tracts)) {
      const t = this.tractEnds[key]; if (!t) continue;
      for (const [amount, rgb, side] of [[exc, '255,150,70', -1], [inh, '90,150,255', 1]]) {
        if (amount <= 1e-6) continue;
        const k = Math.sqrt(amount / top), fibres = 2 + Math.round(5 * k);
        g.lineWidth = 0.8 + 1.4 * k;
        for (let f = 0; f < fibres; f++) {
          const off = side * (2 + f * 1.8);
          g.strokeStyle = `rgba(${rgb},${0.07 + 0.32 * k})`;
          this.strokePath(g, this.tractPath(t, off));
        }
        if (!glow) continue;
        const path = this.tractPath(t, side * 4);
        const n = Math.round(1 + 6 * k);  // impulses: as many as the signal the tract carries
        for (let i = 0; i < n; i++) {
          const u = ((now / 1100) * (0.5 + k) + i / n + (side > 0 ? 0.5 : 0)) % 1;
          const [px, py] = this.pointOn(path, u);
          g.drawImage(side < 0 ? this.sprites.gold : this.sprites.blue, px - 6, py - 6, 12, 12);
        }
      }
      // synapses this moment's lesson changed: a white shimmer, as strong as the share changed
      const fl = this.flash.get(key), fAge = fl ? (performance.now() - fl.at) / 700 : 2;
      if (glow && fAge < 1) {
        const share = Math.min(1, fl.n / Math.max(1, t.n));
        const path = this.tractPath(t, 0);
        for (let i = 0; i < 6; i++) {
          const [px, py] = this.pointOn(path, (i + 0.5) / 6 + 0.04 * Math.sin(now / 90 + i));
          g.globalAlpha = (1 - fAge) * (0.25 + 0.75 * share);
          g.drawImage(this.sprites.white, px - 7, py - 7, 14, 14);
        }
        g.globalAlpha = 1;
      }
    }
  }

  drawNeurons(g) {
    const L = this.layout;
    for (const pop of ['sensory', 'module_0', 'association', 'prefrontal', 'motor', 'recall', 'next']) {
      const pos = L[pop]; if (!pos) continue;
      const v = this.values(pop);
      const size = pop === 'motor' ? 40 : pop === 'sensory' ? 28 : 26;
      pos.forEach(([x, y], i) => {
        const a = v ? v[i] : 0;
        g.globalAlpha = 0.18;
        g.drawImage(this.sprites.white, x - 3, y - 3, 6, 6); // the cell body, even at rest
        const m = Math.min(1, Math.abs(a));
        if (m > 0.02) { g.globalAlpha = m; g.drawImage(a >= 0 ? this.sprites.pos : this.sprites.neg, x - size / 2, y - size / 2, size, size); }
      });
    }
    g.globalAlpha = 1;
  }

  drawNuclei(g, now) {
    const c = this.cur, ar = c?.arousal || {};
    const nuc = (r, sp, a, scale = 1) => { if (a <= 0.01) return; g.globalAlpha = Math.min(1, a); const s = 70 * scale; g.drawImage(sp, r.x - s / 2, r.y - s / 2, s, s); g.globalAlpha = 1; };
    // locus coeruleus: the arousal level
    nuc(R.lc, this.sprites.gold, Math.min(1, (ar.level || 0) / 0.4), 0.8 + 0.2 * Math.sin(now / 200));
    // dopamine nucleus
    const dAge = (performance.now() - this.dopa.at) / 1100;
    if (dAge < 1) nuc(R.vta, this.dopa.v >= 0 ? this.sprites.gold : this.sprites.blue, (1 - dAge) * Math.min(1, 0.3 + Math.abs(this.dopa.v)), 1.1);
    // striatum: the chosen action's motor activation
    const m = this.values('motor');
    if (m && c && c.action !== undefined) nuc(R.striatum, this.sprites.pos, Math.min(1, Math.max(0, m[c.action])), 0.9);
    // thalamus: the observation entering (the mean drive of the sensory neurons)
    const s = this.values('sensory');
    if (s) nuc(R.thalamus, this.sprites.white, Math.min(0.8, s.reduce((x, y) => x + Math.abs(y), 0) / s.length * 3), 0.7);
  }

  drawHippocampus(g, now) {
    const c = this.cur, r = R.hippo;
    // the associative store's write flashes the hippocampus
    const sAge = (performance.now() - this.store) / 1200;
    if (sAge < 1) { g.strokeStyle = `rgba(190,140,255,${0.8 * (1 - sAge)})`; g.lineWidth = 3; g.beginPath(); g.ellipse(r.x, r.y, r.rx + 6 * sAge, r.ry + 4 * sAge, 0, 0, TAU); g.stroke(); }
    if (!this.slots || !this.slots.length) {
      g.fillStyle = 'rgba(175,188,225,0.5)'; g.font = '14px Inter, sans-serif'; g.textAlign = 'center';
      g.fillText('no recall memory: the associative store only', r.x, r.y + 4); return;
    }
    const read = new Map(((c && c.recall && c.recall.read) || []).map((e) => [e.slot, e]));
    const ages = (c && c.recall && c.recall.ages) || null;
    g.globalCompositeOperation = 'lighter';
    this.slots.forEach(([x, y], i) => {
      const e = read.get(i);
      const fresh = ages ? Math.max(0, 1 - ages[i] / this.slots.length) : 0.3;  // newer moments brighter
      g.globalAlpha = e ? Math.min(1, 0.35 + e.weight) : 0.08 + 0.4 * fresh;
      const sz = e ? 20 : 5 + 4 * fresh;
      g.drawImage(e ? this.sprites.gold : this.sprites.pos, x - sz / 2, y - sz / 2, sz, sz);
    });
    g.globalAlpha = 1; g.globalCompositeOperation = 'source-over';
    // threads from the read slots to the places they remember, on a small map
    const map = { x: 40, y: 400, w: 216, h: 144 };
    if (this.terrain) {
      g.globalAlpha = 0.85; g.drawImage(this.terrain, map.x, map.y, map.w, map.h); g.globalAlpha = 1;
      g.strokeStyle = 'rgba(150,170,240,0.35)'; g.lineWidth = 1; g.strokeRect(map.x, map.y, map.w, map.h);
      g.fillStyle = 'rgba(175,188,225,0.7)'; g.font = '14px Inter, sans-serif'; g.textAlign = 'left';
      g.fillText('where the recalled moments happened', map.x, map.y - 5);
      const here = c && c.context && c.context.here;
      if (here) { g.fillStyle = '#3fe0cf'; g.beginPath(); g.arc(map.x + (here.x + 0.5) / this.world.w * map.w, map.y + (here.y + 0.5) / this.world.h * map.h, 3.5, 0, TAU); g.fill(); }
      for (const e of read.values()) {
        if (e.x === undefined) continue;
        const [sx, sy] = this.slots[e.slot];
        const px = map.x + (e.x + 0.5) / this.world.w * map.w, py = map.y + (e.y + 0.5) / this.world.h * map.h;
        g.strokeStyle = `rgba(255,206,102,${0.25 + 0.6 * e.weight})`; g.lineWidth = 1 + 2 * e.weight;
        g.beginPath(); g.moveTo(sx, sy); g.quadraticCurveTo((sx + px) / 2, Math.max(sy, py) + 30, px, py); g.stroke();
        g.fillStyle = '#ffce66'; g.beginPath(); g.arc(px, py, 2.5 + 3 * e.weight, 0, TAU); g.fill();
        if (e.weight > 0.3) {
          g.fillStyle = '#ffe6a8'; g.font = '13px Inter, sans-serif';
          g.fillText(`${e.age} moment${e.age === 1 ? '' : 's'} ago${e.underfoot && e.underfoot.length ? `, ${e.underfoot.join(' + ')} underfoot` : ''}${e.nausea > 0 ? ', sick' : ''}`, px + 8, py + 4);
        }
      }
    }
  }

  drawMotorLabels(g) {
    const L = this.layout, c = this.cur; if (!L.motor) return;
    g.font = '14px Inter, sans-serif'; g.textAlign = 'center';
    L.motor.forEach(([x, y], i) => {
      const chosen = c && c.action === i && (this.sweepNow()?.done);
      g.fillStyle = chosen ? '#ffffff' : 'rgba(175,188,225,0.6)';
      g.font = `${chosen ? 600 : 400} 14px Inter, sans-serif`;
      g.fillText(ACTIONS[i], x, y - 14);
    });
  }

  drawHud(g, now) {
    const c = this.cur, ar = c?.arousal || {}, sw = this.sweepNow();
    g.font = '17px Inter, sans-serif'; g.textAlign = 'left';
    const learning = ar.mode === 'aroused';
    const pill = (x, y, text, on, rgb) => {
      const w = g.measureText(text).width + 18;
      g.fillStyle = on ? `rgba(${rgb},0.2)` : 'rgba(255,255,255,0.05)'; g.strokeStyle = on ? `rgba(${rgb},0.8)` : 'rgba(255,255,255,0.12)';
      g.beginPath(); g.roundRect(x, y, w, 30, 15); g.fill(); g.stroke();
      g.fillStyle = on ? `rgb(${rgb})` : '#8d97b2'; g.fillText(text, x + 9, y + 21); return w;
    };
    let x = 14;
    x += pill(x, 12, learning ? 'aroused: learning on' : this.kind === 'frozen' ? 'frozen: never learns' : 'calm: not learning', learning, '255,206,102') + 8;
    if (sw) x += pill(x, 12, sw.done ? `settled in ${sw.of} sweeps` : `settling: sweep ${sw.sweep} of ${sw.of}`, !sw.done, '63,224,207') + 8;
    if (sw && sw.movement !== null && sw.movement !== undefined) x += pill(x, 12, `largest change ${sw.movement.toExponential(1)}`, false, '63,224,207') + 8;
    const dAge = (performance.now() - this.dopa.at) / 1100;
    if (dAge < 2.5) x += pill(x, 12, `last lesson's dopamine ${this.dopa.v >= 0 ? '+' : ''}${this.dopa.v.toFixed(2)}`, true, this.dopa.v >= 0 ? '255,206,102' : '110,170,255') + 8;
    g.textAlign = 'right'; g.fillStyle = '#8d97b2'; g.font = '16px Inter, sans-serif';
    g.fillText(`synapses changed this moment: ${(c && c.changed) || 0}  ·  since selected: ${this.changedTotal.toLocaleString()}`, this.W - 14, this.H - 56);
    g.fillText(`surprise ${(ar.surprise || 0).toFixed(2)}  ·  want ${(ar.want || 0).toFixed(2)}  ·  arousal level ${(ar.level || 0).toFixed(2)}`, this.W - 14, this.H - 35);
    if (this.anat) g.fillText(`${this.anat.neurons} neurons · ${this.anat.synapses.toLocaleString()} synapses`, this.W - 14, this.H - 14);
  }
}

export { R as REGIONS, VISION_KINDS, DIRS };
