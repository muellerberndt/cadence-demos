// The brain panel: every neuron of the arm's brain, population by population, lit by its
// activity after each settle; the strongest synapses drawn with the signal they carry; the
// working-memory trace as a grid and as a history strip; the motor choices with the policy's
// probabilities and the chosen move.

const KIND = { // synapse pair -> drawing class
  'sensory>module_0': 'ff', 'module_0>module_1': 'ff', 'module_1>association': 'ff', 'association>motor': 'ff',
  'module_1>module_0': 'td', 'association>module_1': 'td', 'motor>association': 'td', 'prefrontal>association': 'mem',
};
const COLORS = { ff: [79, 195, 247], td: [180, 140, 255], mem: [79, 209, 181] };
const DESCRIPTIONS = {
  sensory: 'What the brain senses, 262 values: where its hand is; where the block and the target bin are relative to the hand; its seven joint angles and speeds; the gripper; its own last move; which lamp is lit.',
  module_0: 'Layer 1 of three deep layers. It settles together with the others: bottom-up input from the senses, top-down (apical) input from Layer 2.',
  module_1: 'Layer 2. Bottom-up from Layer 1, top-down (apical) from Layer 3.',
  association: 'Layer 3, the top layer. It drives the motor choices and receives the working memory.',
  prefrontal: 'Working memory: the brain’s short-term memory. A trace of recent moments enters Layer 3 here, so what just happened shapes the next move.',
  motor: 'The choice of each decision: move the hand −2 to +2 cm along x, y and z, and open or close the gripper. The tallest bar wins.',
};
const SENSE_GROUPS = [
  ['hand', 'Hand position', 3, 15], ['block_minus_hand', 'Block − hand', 3, 15], ['release_minus_hand', 'Target bin − hand', 3, 15],
  ['joints', 'Joints', 7, 7], ['velocity', 'Speeds', 7, 7], ['opening', 'Gripper opening', 1, 7], ['flags', 'Closed · holding', 1, 2],
  ['efference', 'Own last move', 1, 17], ['lamp', 'Lamp', 1, 3],
];
const MOVE_LABELS = ['−2', '−1', '0', '+1', '+2'];
const HISTORY = 48;

function heat(t, base) { // t in 0..1 -> rgb string along dark -> hue -> white
  t = Math.max(0, Math.min(1, t));
  const dark = [28, 34, 44];
  const mid = base, hi = [240, 250, 255];
  const c = t < 0.6 ? dark.map((d, i) => d + (mid[i] - d) * (t / 0.6)) : mid.map((m, i) => m + (hi[i] - m) * ((t - 0.6) / 0.4));
  return `rgb(${c[0] | 0},${c[1] | 0},${c[2] | 0})`;
}

export class BrainView {
  constructor(canvas, tip) {
    this.canvas = canvas;
    this.tip = tip;
    this.ctx = canvas.getContext('2d');
    this.ready = false;
    this.history = [];
    canvas.addEventListener('pointermove', (e) => this.hover(e));
    canvas.addEventListener('pointerleave', () => { this.tip.hidden = true; });
    new ResizeObserver(() => this.resize()).observe(canvas.parentElement);
  }

  setup(desc) {
    this.desc = desc;
    this.n = desc.neurons;
    this.pop = Object.fromEntries(desc.populations.map((p) => [p.name, p]));
    this.shown = new Float32Array(this.n).fill(-0.1);
    this.target = new Float32Array(this.n).fill(-0.1);
    this.top = desc.top;
    this.topKind = this.top.pre.map((pre, i) => KIND[`${this.popOf(pre)}>${this.popOf(this.top.post[i])}`] || 'ff');
    this.messages = new Float32Array(this.top.pre.length);
    this.shownMessages = new Float32Array(this.top.pre.length);
    this.probabilities = null;
    this.answer = null;
    this.ready = true;
    this.resize();
  }

  popOf(index) {
    for (const p of this.desc.populations) if (index >= p.start && index < p.start + p.size) return p.name;
    return null;
  }

  clear() {
    if (!this.ready) return;
    this.target.fill(-0.1); this.messages.fill(0); this.probabilities = null; this.answer = null; this.history = []; this.trace = null;
  }

  update(reply, answer) {
    if (!this.ready || !reply.activation) return;
    this.target.set(reply.activation);
    this.messages.set(reply.top_messages);
    this.probabilities = reply.probabilities;
    this.answer = answer;
    this.trace = reply.trace;
    if (reply.trace) { this.history.push(reply.trace); if (this.history.length > HISTORY) this.history.shift(); }
  }

  // --- layout ---------------------------------------------------------------------------------
  resize() {
    const W = this.canvas.parentElement.clientWidth;
    if (!W || !this.ready) return;
    this.W = W;
    const pos = new Float32Array((this.n || 1) * 2);
    const boxes = [];
    const cellIn = (name, cols, rows, x0, y0, size, gap = 1, label = null, from = 0, count = null) => {
      const p = this.pop[name];
      count = count ?? p.size;
      for (let i = 0; i < count; i++) {
        const r = Math.floor(i / cols), c = i % cols;
        const k = p.start + from + i;
        pos[2 * k] = x0 + c * (size + gap) + size / 2; pos[2 * k + 1] = y0 + r * (size + gap) + size / 2;
      }
      return { x: x0, y: y0, w: cols * (size + gap) - gap, h: rows * (size + gap) - gap, size, gap };
    };
    let y = 22;
    // Motor: four slot groups
    const motor = this.pop.motor ? this.pop.motor : null;
    const slotW = Math.min(28, (W - 3 * 18) / 19);
    let x = 0;
    this.motorCells = [];
    if (motor) {
      let k = 0;
      (this.desc?.slots || [5, 5, 5, 2]).forEach((size, s) => {
        const cw = size === 2 ? 2 * slotW : slotW;
        for (let i = 0; i < size; i++) {
          const cx = x + i * cw;
          pos[2 * (motor.start + k)] = cx + cw / 2; pos[2 * (motor.start + k) + 1] = y + 18;
          this.motorCells.push({ slot: s, index: i, x: cx, y, w: cw - 2, h: 36 });
          k++;
        }
        x += size * cw + 18;
      });
      boxes.push({ name: 'motor', label: 'Motor · the next move', x: 0, y, w: x - 18, h: 52 });
    }
    y += 84;
    // Layer 3 and working memory
    const s3 = Math.floor(Math.min(12, (W - 120) / 20));
    const l3 = this.pop.association ? cellIn('association', 8, 8, 0, y, s3) : null;
    if (l3) boxes.push({ name: 'association', label: 'Layer 3', ...l3 });
    const wmX = l3 ? l3.w + 30 : 0;
    const wm = this.pop.prefrontal ? cellIn('prefrontal', 8, 8, wmX, y, s3) : null;
    if (wm) boxes.push({ name: 'prefrontal', label: 'Working memory', ...wm });
    this.historyBox = wm ? { x: wm.x + wm.w + 12, y, w: W - (wm.x + wm.w + 12), h: wm.h } : null;
    y += (l3 ? l3.h : 0) + 34;
    // Layer 2: 16 x 8
    const s2 = Math.floor(Math.min(12, (W - 15) / 16 - 1));
    const l2 = this.pop.module_1 ? cellIn('module_1', 16, 8, 0, y, s2) : null;
    if (l2) boxes.push({ name: 'module_1', label: 'Layer 2', ...l2 });
    y += (l2 ? l2.h : 0) + 34;
    // Layer 1: 32 x 8
    const s1 = Math.floor(Math.min(12, (W - 31) / 32 - 1));
    const l1 = this.pop.module_0 ? cellIn('module_0', 32, 8, 0, y, s1) : null;
    if (l1) boxes.push({ name: 'module_0', label: 'Layer 1', ...l1 });
    y += (l1 ? l1.h : 0) + 40;
    // Senses, grouped
    this.senseBoxes = [];
    const layout = this.desc?.layout || {};
    const ss = Math.floor(Math.min(8, (W - 2 * 14 - 45) / 45));
    const groupBox = (key, label, rows, cols, gx, gy) => {
      const [a] = layout[key] || [0];
      const b = cellIn('sensory', cols, rows, gx, gy, ss, 1, null, a, rows * cols);
      this.senseBoxes.push({ label, ...b });
      return b;
    };
    if (this.pop.sensory) {
      const groups = Object.fromEntries(SENSE_GROUPS.map((s) => [s[0], s]));
      let gx = 0;
      for (const key of ['hand', 'block_minus_hand', 'release_minus_hand']) {
        const [, label, rows, cols] = groups[key];
        const b = groupBox(key, label, rows, cols, gx, y);
        gx += b.w + 14;
      }
      y += 3 * (ss + 1) + 28;
      const rowY = y;
      gx = 0;
      for (const key of ['joints', 'velocity']) {
        const [, label, rows, cols] = groups[key];
        const b = groupBox(key, label, rows, cols, gx, rowY);
        gx += b.w + 18;
      }
      let cy = rowY;
      for (const key of ['opening', 'flags', 'lamp', 'efference']) {
        const [, label, rows, cols] = groups[key];
        groupBox(key, label, rows, cols, gx, cy);
        cy += ss + 1 + 20;
      }
      y = Math.max(...this.senseBoxes.map((b) => b.y + b.h));
      boxes.push({ name: 'sensory', label: 'Senses', x: 0, y: this.senseBoxes[0].y, w: W, h: y - this.senseBoxes[0].y });
    }
    this.H = y + 8;
    this.pos = pos;
    this.boxes = boxes;
    this.sizes = { s1, s2, s3, ss };
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = Math.round(W * dpr); this.canvas.height = Math.round(this.H * dpr);
    this.canvas.style.height = `${this.H}px`;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  // --- drawing --------------------------------------------------------------------------------
  frame(dt) {
    if (!this.ready || !this.W) return;
    const a = 1 - Math.exp(-dt / 0.12);
    for (let i = 0; i < this.n; i++) this.shown[i] += (this.target[i] - this.shown[i]) * a;
    for (let i = 0; i < this.messages.length; i++) this.shownMessages[i] += (this.messages[i] - this.shownMessages[i]) * a;
    this.draw();
  }

  draw() {
    const g = this.ctx, W = this.W, H = this.H, pos = this.pos;
    g.clearRect(0, 0, W, H);
    // synapses
    const per = 60, maxOf = [];
    for (let i = 0; i < this.shownMessages.length; i += per) {
      let m = 1e-6;
      for (let j = i; j < Math.min(i + per, this.shownMessages.length); j++) m = Math.max(m, Math.abs(this.shownMessages[j]));
      maxOf.push(m);
    }
    g.globalCompositeOperation = 'lighter';
    g.lineWidth = 1;
    for (let i = 0; i < this.top.pre.length; i++) {
      const v = Math.abs(this.shownMessages[i]) / maxOf[Math.floor(i / per)];
      if (v < 0.04) continue;
      const pre = this.top.pre[i], post = this.top.post[i];
      const [r, gg, b] = COLORS[this.topKind[i]];
      g.strokeStyle = `rgba(${r},${gg},${b},${(0.06 + 0.42 * v).toFixed(3)})`;
      g.beginPath();
      const x1 = pos[2 * pre], y1 = pos[2 * pre + 1], x2 = pos[2 * post], y2 = pos[2 * post + 1];
      const bend = this.topKind[i] === 'td' ? 26 : -26;
      g.moveTo(x1, y1);
      g.quadraticCurveTo((x1 + x2) / 2 + bend, (y1 + y2) / 2, x2, y2);
      g.stroke();
    }
    g.globalCompositeOperation = 'source-over';
    // labels
    g.font = '500 10.5px "IBM Plex Mono", monospace';
    g.fillStyle = '#6c7583';
    for (const b of this.boxes) {
      if (b.name === 'sensory') continue;
      g.fillText(b.label.toUpperCase(), b.x, b.y - 7);
    }
    g.font = '400 10px "IBM Plex Mono", monospace';
    for (const b of this.senseBoxes || []) g.fillText(b.label, b.x, b.y - 5);
    // neurons
    const draw = (name, size, base) => {
      const p = this.pop[name];
      if (!p) return;
      for (let i = 0; i < p.size; i++) {
        const k = p.start + i;
        const t = (this.shown[k] + 0.1) / 1.1;
        g.fillStyle = heat(t, base);
        g.fillRect(pos[2 * k] - size / 2, pos[2 * k + 1] - size / 2, size, size);
      }
    };
    draw('module_0', this.sizes.s1, [79, 195, 247]);
    draw('module_1', this.sizes.s2, [79, 195, 247]);
    draw('association', this.sizes.s3, [79, 195, 247]);
    draw('prefrontal', this.sizes.s3, [79, 209, 181]);
    draw('sensory', this.sizes.ss, [79, 195, 247]);
    this.drawMotor(g);
    this.drawHistory(g);
  }

  drawMotor(g) {
    const names = ['x', 'y', 'z', 'grip'];
    const p = this.probabilities, ans = this.answer;
    let lastSlot = -1;
    for (const c of this.motorCells || []) {
      if (c.slot !== lastSlot) {
        lastSlot = c.slot;
        g.fillStyle = '#a8b0bc'; g.font = '600 11px "IBM Plex Sans", sans-serif';
        g.fillText(c.slot < 3 ? `${names[c.slot]} (cm)` : 'gripper', c.x, c.y + c.h + 15);
      }
      g.fillStyle = '#191d23';
      g.fillRect(c.x, c.y, c.w, c.h);
      const prob = p ? p[c.slot][c.index] : 0;
      const chosen = ans && ans[c.slot] === c.index;
      g.fillStyle = chosen ? '#f2b33d' : 'rgba(242,179,61,0.35)';
      g.fillRect(c.x, c.y + c.h * (1 - prob), c.w, c.h * prob);
      if (chosen) { g.strokeStyle = '#f2b33d'; g.lineWidth = 1.5; g.strokeRect(c.x + 0.75, c.y + 0.75, c.w - 1.5, c.h - 1.5); }
      g.fillStyle = chosen ? '#e8ebf0' : '#6c7583';
      g.font = '500 9.5px "IBM Plex Mono", monospace';
      const label = c.slot < 3 ? MOVE_LABELS[c.index] : (c.index ? 'close' : 'open');
      g.textAlign = 'center';
      g.fillText(label, c.x + c.w / 2, c.y + c.h - 4);
      g.textAlign = 'start';
    }
  }

  drawHistory(g) {
    const b = this.historyBox;
    if (!b || b.w < 30) return;
    g.fillStyle = '#6c7583'; g.font = '500 10.5px "IBM Plex Mono", monospace';
    g.fillText('MEMORY OVER TIME', b.x, b.y - 7);
    g.fillStyle = '#191d23'; g.fillRect(b.x, b.y, b.w, b.h);
    const cols = HISTORY, cw = b.w / cols, rh = b.h / 64;
    const start = cols - this.history.length;
    this.history.forEach((trace, j) => {
      for (let i = 0; i < trace.length; i++) {
        g.fillStyle = heat(Math.abs(trace[i]), [79, 209, 181]);
        g.fillRect(b.x + (start + j) * cw, b.y + i * rh, Math.ceil(cw), Math.ceil(rh));
      }
    });
    g.fillStyle = '#6c7583'; g.font = '400 9.5px "IBM Plex Mono", monospace';
    g.textAlign = 'end'; g.fillText('now →', b.x + b.w, b.y + b.h + 12); g.textAlign = 'start';
  }

  hover(e) {
    if (!this.ready) return;
    const r = this.canvas.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    const hit = this.boxes.find((b) => x >= b.x - 4 && x <= b.x + b.w + 4 && y >= b.y - 14 && y <= b.y + b.h + 4);
    const inHistory = this.historyBox && x >= this.historyBox.x && y >= this.historyBox.y && y <= this.historyBox.y + this.historyBox.h;
    if (!hit && !inHistory) { this.tip.hidden = true; return; }
    let html;
    if (inHistory && (!hit || hit.name !== 'prefrontal')) {
      html = '<b>Memory over time</b><br>The working trace at each of the last decisions, oldest on the left. Each row is one of its 64 units.';
    } else {
      const p = this.pop[hit.name];
      let mean = 0;
      for (let i = 0; i < p.size; i++) mean += this.shown[p.start + i];
      mean /= p.size;
      html = `<b>${hit.label}</b> · ${p.size} neurons · mean activity ${mean.toFixed(2)}<br>${DESCRIPTIONS[hit.name]}`;
    }
    this.tip.innerHTML = html;
    this.tip.hidden = false;
    const tw = this.tip.offsetWidth;
    this.tip.style.left = `${Math.max(0, Math.min(x + 12, this.W - tw))}px`;
    this.tip.style.top = `${y + 14}px`;
  }
}
