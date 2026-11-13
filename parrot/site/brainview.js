// The brain panel: every population the brain host names, lit by its activity each moment; the
// group of neurons the brain uses for distance with their tuning curves (#332 E7) and the switch
// that silences them; and the joints, each with its target and where it stands.
import { brainColor } from './cadence-palette.js';

const SIGNAL = brainColor('signal'), MEMORY = brainColor('memory'), RECALL = brainColor('recall'), INHIBIT = brainColor('inhibit');
const REGION_COLOUR = { retina: SIGNAL, tectum: SIGNAL, thalamus: SIGNAL, wulst: SIGNAL, hippocampus: RECALL, map: RECALL, ncl: INHIBIT, distance: MEMORY, motor: MEMORY };

function heat(t, base) {
  t = Math.max(0, Math.min(1, t));
  const dark = [22, 30, 36], hi = [240, 250, 255];
  const c = t < 0.65 ? dark.map((d, i) => d + (base[i] - d) * (t / 0.65)) : base.map((m, i) => m + (hi[i] - m) * ((t - 0.65) / 0.35));
  return `rgb(${c[0] | 0},${c[1] | 0},${c[2] | 0})`;
}

export class BrainView {
  constructor({ canvas, units, tuning, readout, silence, joints }) {
    this.canvas = canvas; this.ctx = canvas.getContext('2d');
    this.unitsCanvas = units; this.tuningCanvas = tuning; this.readoutEl = readout; this.silenceBtn = silence; this.jointsEl = joints;
    this.ready = false;
    this.activity = null; this.shown = null;
    this.tuningBins = 28;
    new ResizeObserver(() => this.layout()).observe(canvas.parentElement);
  }

  setup(desc, jointSpec) {
    this.desc = desc;
    this.pops = desc.populations;
    this.n = desc.neurons;
    this.activity = new Float32Array(this.n); this.shown = new Float32Array(this.n);
    this.group = (desc.groups || []).find((g) => g.variable === 'distance') || null;
    if (this.group) {
      const [lo, hi] = this.group.range || [0.1, 0.8];
      this.range = [lo, hi];
      this.sum = new Float32Array(this.group.units.length * this.tuningBins);
      this.count = new Float32Array(this.tuningBins);
    }
    this.jointSpec = jointSpec;
    this.buildJoints();
    this.ready = true;
    this.spotsW = 0;
    this.layout();
    document.fonts?.ready.then(() => { this.spotsW = 0; this.layout(); });
  }

  buildJoints() {
    const el = this.jointsEl; el.textContent = '';
    this.jointRows = this.jointSpec.map((j) => {
      const row = document.createElement('div'); row.className = 'joint';
      const name = document.createElement('span'); name.className = 'jn'; name.textContent = j.name.replace('_', ' ');
      const bar = document.createElement('span'); bar.className = 'jb';
      const pos = document.createElement('i'); pos.className = 'jp';
      const tgt = document.createElement('i'); tgt.className = 'jt';
      bar.append(pos, tgt);
      row.append(name, bar);
      el.append(row);
      return { pos, tgt, j };
    });
  }

  clearTuning() { if (this.sum) { this.sum.fill(0); this.count.fill(0); } }

  /** One moment: the host's reply and its arrays. `subject` is the true distance (m) of the thing the
   *  visitor moves, from the eyes' midpoint (the page's truth, for the tuning curve only). */
  update(reply, arrays, subject) {
    if (!this.ready) return;
    if (arrays.activity) this.activity.set(arrays.activity.subarray(0, this.n));
    this.groupNow = reply.group_activity?.distance || null;
    this.readout = reply.readout || {};
    this.subject = subject;
    if (this.group && this.groupNow && subject != null) {
      const [lo, hi] = this.range;
      const b = Math.floor(((subject - lo) / (hi - lo)) * this.tuningBins);
      if (b >= 0 && b < this.tuningBins) {
        const U = this.group.units.length;
        for (let u = 0; u < U; u++) this.sum[u * this.tuningBins + b] += this.groupNow[u];
        this.count[b] += 1;
      }
    }
  }

  setJoints(pos, target) {
    if (!this.jointRows) return;
    this.jointRows.forEach((r, i) => {
      const j = r.j, f = (v) => `${(100 * (v - j.min)) / (j.max - j.min)}%`;
      r.pos.style.left = f(pos[i]);
      r.tgt.style.left = f(Math.max(j.min, Math.min(j.max, target[i])));
    });
  }

  layout() {
    const W = this.canvas.parentElement.clientWidth;
    if (!W || !this.ready) return;
    this.W = W;
    const pos = [];
    let y = 18;
    this.boxes = [];
    // populations in rows: each a grid of squares, at most two side by side
    const rowGap = 30, colGap = 18;
    let x = 0, rowH = 0;
    for (const p of this.pops) {
      const half = p.region === 'retina' ? p.size <= 1200 : p.size <= 160;
      const width = half ? (W - colGap) / 2 : W;
      if (x > 0 && (!half || x + width > W + 1)) { x = 0; y += rowH + rowGap; rowH = 0; }
      const cols = p.region === 'retina' ? Math.min(64, Math.max(8, Math.round(Math.sqrt(p.size * 2)))) : Math.max(4, Math.min(24, Math.ceil(Math.sqrt(p.size * 3))));
      const size = Math.max(2, Math.min(p.region === 'retina' ? 6 : 11, Math.floor(width / cols) - 1));
      const rows = Math.ceil(p.size / cols);
      for (let i = 0; i < p.size; i++) pos[p.start + i] = [x + (i % cols) * (size + 1), y + Math.floor(i / cols) * (size + 1)];
      const box = { p, x, y, w: cols * (size + 1) - 1, h: rows * (size + 1) - 1, size };
      this.boxes.push(box);
      rowH = Math.max(rowH, box.h);
      x = half ? x + width + colGap : W + 1;
    }
    y += rowH + 8;
    this.pos = pos; this.H = y;
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    this.canvas.width = Math.round(W * dpr); this.canvas.height = Math.round(this.H * dpr);
    this.canvas.style.height = `${this.H}px`;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    for (const c of [this.unitsCanvas, this.tuningCanvas]) {
      const w = c.parentElement.clientWidth || W, h = c === this.unitsCanvas ? 26 : 92;
      c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); c.style.height = `${h}px`;
      c.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0);
      c.dataset.w = w; c.dataset.h = h;
    }
    this.placeSpots();
  }

  placeSpots() {
    const ex = window.CadenceExplain, wrap = this.canvas.parentElement;
    if (!ex || this.spotsW === this.W) return;
    this.spotsW = this.W;
    ex.clearSpots(wrap);
    const g = this.ctx; g.font = '500 10.5px "IBM Plex Mono", monospace';
    for (const b of this.boxes) {
      const label = (b.p.title || b.p.name).toUpperCase();
      const lw = g.measureText(label).width;
      const text = b.p.explain || `${b.p.size} neurons of the brain, lit by their activity at each moment.`;
      const el = ex.spot(wrap, { x: b.x - 3, y: b.y - 17, w: Math.max(b.w, lw + 24) + 6, h: b.h + 20 }, text, { title: b.p.title || b.p.name, id: b.p.name });
      const q = el.querySelector('.cx-q');
      if (q) Object.assign(q.style, { left: `${Math.round(lw + 7)}px`, top: '1px', right: 'auto' });
    }
  }

  frame(dt) {
    if (!this.ready || !this.W) return;
    const a = 1 - Math.exp(-dt / 0.1);
    for (let i = 0; i < this.n; i++) this.shown[i] += (this.activity[i] - this.shown[i]) * a;
    const g = this.ctx;
    g.clearRect(0, 0, this.W, this.H);
    g.font = '500 10.5px "IBM Plex Mono", monospace';
    for (const b of this.boxes) {
      g.fillStyle = '#6c7583';
      g.fillText((b.p.title || b.p.name).toUpperCase(), b.x, b.y - 6);
      const base = REGION_COLOUR[b.p.region] || SIGNAL;
      for (let i = 0; i < b.p.size; i++) {
        const k = b.p.start + i, [x, y] = this.pos[k];
        g.fillStyle = heat(this.shown[k], base);
        g.fillRect(x, y, b.size, b.size);
      }
    }
    this.drawUnits(); this.drawTuning();
  }

  drawUnits() {
    const c = this.unitsCanvas, g = c.getContext('2d'), W = +c.dataset.w, H = +c.dataset.h;
    g.clearRect(0, 0, W, H);
    if (!this.group) return;
    const U = this.group.units.length, w = W / U;
    for (let u = 0; u < U; u++) {
      const v = this.groupNow ? this.groupNow[u] : 0;
      g.fillStyle = heat(v, MEMORY);
      g.fillRect(u * w + 1, 2, w - 2, H - 4);
    }
  }

  drawTuning() {
    const c = this.tuningCanvas, g = c.getContext('2d'), W = +c.dataset.w, H = +c.dataset.h;
    g.clearRect(0, 0, W, H);
    if (!this.group) return;
    const B = this.tuningBins, U = this.group.units.length, [lo, hi] = this.range;
    const padL = 4, padB = 16, w = W - padL - 4, h = H - padB - 4;
    g.strokeStyle = '#252a32'; g.lineWidth = 1;
    g.beginPath(); g.moveTo(padL, 4 + h + 0.5); g.lineTo(padL + w, 4 + h + 0.5); g.stroke();
    g.fillStyle = '#6c7583'; g.font = '400 9.5px "IBM Plex Mono", monospace';
    for (const d of [0.2, 0.4, 0.6, 0.8]) {
      if (d < lo || d > hi) continue;
      const x = padL + ((d - lo) / (hi - lo)) * w;
      g.fillText(`${Math.round(d * 100)} cm`, x - 12, H - 3);
    }
    let any = false;
    for (let u = 0; u < U; u++) {
      g.beginPath(); let started = false;
      for (let b = 0; b < B; b++) {
        if (!this.count[b]) continue;
        any = true;
        const v = this.sum[u * B + b] / this.count[b];
        const x = padL + ((b + 0.5) / B) * w, y = 4 + h - Math.min(1, v) * h;
        if (!started) { g.moveTo(x, y); started = true; } else g.lineTo(x, y);
      }
      const hue = 30 + (u / Math.max(1, U - 1)) * 170;
      g.strokeStyle = `hsla(${hue}, 70%, 62%, 0.85)`; g.lineWidth = 1.4; g.stroke();
    }
    if (!any) { g.fillStyle = '#6c7583'; g.font = '400 11px "IBM Plex Sans", sans-serif'; g.fillText('Drag a thing nearer or further to draw the curves.', padL + 6, 4 + h / 2); }
    if (this.subject != null && this.subject >= lo && this.subject <= hi) {
      const x = padL + ((this.subject - lo) / (hi - lo)) * w;
      g.strokeStyle = 'rgba(232,235,240,0.7)'; g.setLineDash([3, 3]); g.beginPath(); g.moveTo(x + 0.5, 4); g.lineTo(x + 0.5, 4 + h); g.stroke(); g.setLineDash([]);
    }
    const r = this.readout || {};
    const sense = r.distance == null ? '–' : `${Math.round(r.distance * 100)} cm`;
    const truth = this.subject == null ? '–' : `${Math.round(this.subject * 100)} cm`;
    const text = `Its sense of distance: <b>${sense}</b> · true: ${truth}`;
    if (this.readoutEl.dataset.text !== text) { this.readoutEl.innerHTML = text; this.readoutEl.dataset.text = text; }
  }
}
