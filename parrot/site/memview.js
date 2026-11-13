// The memory view: what the parrot remembers of what it heard, as the library's stores hold it.
// Records (cadence.LongTermMemory): each a cell with a small picture of its sound, larger the
// deeper it is, fainter the more it has faded; a new record pops in, one told again flashes and
// grows. Each read: the heard sound (the cue) with lines to the records it attended, as wide as the
// attention. Synapses (cadence.SynapticMemory): sounds by things, the consolidated part and the
// fading residual side by side, brighter as a sound and a thing go together again and again.
const THING_LABEL = { apple: 'apple', ball: 'ball', cup: 'cup', banana: 'banana', block: 'block', duck: 'duck', lemon: 'lemon', pear: 'pear' };

function thumbCanvas(thumb) {
  const c = document.createElement('canvas'); c.width = 24; c.height = 20;
  const g = c.getContext('2d'), img = g.createImageData(24, 20);
  for (let x = 0; x < 24; x++) for (let y = 0; y < 20; y++) {
    const v = thumb[x * 20 + (19 - y)] / 255, k = 4 * (y * 24 + x);
    img.data[k] = 20 + 210 * v; img.data[k + 1] = 28 + 190 * v; img.data[k + 2] = 40 + 120 * v; img.data[k + 3] = 255;
  }
  g.putImageData(img, 0, 0);
  return c;
}

export class MemoryView {
  constructor(canvas) {
    this.canvas = canvas; this.ctx = canvas.getContext('2d');
    this.data = null; this.thumbs = new Map(); this.pop = new Map(); this.flash = new Map(); this.read = null; this.readAt = 0;
    new ResizeObserver(() => this.layout()).observe(canvas.parentElement);
  }

  update(mem) {
    if (!mem) return;
    const before = new Set((this.data?.records || []).map((r) => r.slot));
    this.data = mem;
    for (const r of mem.records) {
      const key = `${r.slot}:${r.thumb.slice(0, 12).join(',')}`;
      if (!this.thumbs.has(r.slot) || this.thumbs.get(r.slot).key !== key) this.thumbs.set(r.slot, { key, canvas: thumbCanvas(r.thumb) });
      if (!before.has(r.slot)) this.pop.set(r.slot, performance.now());
    }
    const readKey = mem.read ? JSON.stringify([mem.write, mem.read.slots, mem.read.weights]) : null;
    if (mem.write && mem.read && readKey !== this.lastRead) {
      this.lastRead = readKey;
      this.read = { ...mem.read, cueCanvas: thumbCanvas(mem.read.cue), write: mem.write };
      this.readAt = performance.now();
      if (mem.write.revised) this.flash.set(mem.write.slot, performance.now());
    }
    this.layout();
  }

  layout() {
    const W = this.canvas.parentElement.clientWidth, H = this.canvas.parentElement.clientHeight;
    if (!W || !H) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    if (this.canvas.width !== Math.round(W * dpr) || this.canvas.height !== Math.round(H * dpr)) {
      this.canvas.width = Math.round(W * dpr); this.canvas.height = Math.round(H * dpr);
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0); this.spotsAt = null;
    }
    this.W = W; this.H = H;
    this.placeSpots();
  }

  placeSpots() {
    const ex = window.CadenceExplain, wrap = this.canvas.parentElement;
    const key = `${this.W}x${this.H}`;
    if (!ex || this.spotsAt === key || !this.W) return;
    this.spotsAt = key;
    for (const s of wrap.querySelectorAll('.cx-spot')) s.remove();
    const top = this.H * 0.56;
    ex.spot(wrap, { x: 8, y: 8, w: this.W - 16, h: top - 16 }, 'Every sound the parrot heard is a record here: a little picture of the sound. A record grows each time the sound is heard again (told again), and the parrot can say a sound back once its record is deep (the yellow outline). Records nobody hears again fade and are replaced first.\n\nEvery time you say a word, the parrot’s memory of it grows stronger. Words you say once fade. It ignores noise such as a fan, clicks or hum.', { title: 'Its records', id: 'records' });
    ex.spot(wrap, { x: 8, y: top, w: this.W - 16, h: this.H - top - 8 }, 'The links from each heard sound (rows) to the thing the parrot looked at while it heard it (columns). Left: the lasting, consolidated links, which grow each time a sound and a thing come together again. Right: the quick part that fades within moments.', { title: 'Its synapses', id: 'synapses' });
  }

  frame() {
    const g = this.ctx, W = this.W, H = this.H;
    if (!W) return;
    g.clearRect(0, 0, W, H);
    const now = performance.now();
    g.font = '500 10.5px "IBM Plex Mono", monospace'; g.fillStyle = '#6c7583';
    g.fillText('RECORDS (LongTermMemory)', 12, 20);
    const recs = this.data?.records || [];
    if (!recs.length) {
      g.font = '400 12px "IBM Plex Sans", sans-serif'; g.fillStyle = '#6c7583';
      g.fillText('Nothing heard yet. Turn on the microphone and say a word a few times.', 12, 44);
    }
    // records in a grid; the cue above, with lines to what it attended
    const top = H * 0.56, cueH = 54, cols = Math.max(4, Math.floor((W - 24) / 62)), cell = Math.min(56, (W - 24) / cols - 6);
    const pos = new Map();
    recs.forEach((r, i) => {
      const cx = 12 + (i % cols) * (cell + 6), cy = 34 + cueH + Math.floor(i / cols) * (cell + 18);
      if (cy + cell > top - 6) return;
      const level = this.data.level || 2.5;
      const grow = 0.55 + 0.45 * Math.min(1, r.deep / (level * 3));
      const popT = this.pop.has(r.slot) ? Math.min(1, (now - this.pop.get(r.slot)) / 400) : 1;
      const s = cell * grow * (0.3 + 0.7 * popT), x = cx + (cell - s) / 2, y = cy + (cell - s) / 2;
      const faded = r.faded / (r.faded + 600);
      g.globalAlpha = Math.max(0.15, 1 - faded);
      const t = this.thumbs.get(r.slot);
      if (t) { g.imageSmoothingEnabled = false; g.drawImage(t.canvas, x, y, s, s * 0.8); }
      g.globalAlpha = 1;
      if (r.deep >= level) { g.strokeStyle = '#f2b33d'; g.lineWidth = 1.5; g.strokeRect(x - 1, y - 1, s + 2, s * 0.8 + 2); }
      // depth bar
      g.fillStyle = '#1f242b'; g.fillRect(cx, cy + cell * 0.82, cell, 4);
      g.fillStyle = '#f2b33d'; g.fillRect(cx, cy + cell * 0.82, cell * Math.min(1, r.deep / (level * 4)), 4);
      g.fillStyle = '#6c7583'; g.font = '400 9px "IBM Plex Mono", monospace';
      g.fillText(`depth ${r.deep.toFixed(1)}`, cx, cy + cell * 0.82 + 13);
      if (this.flash.has(r.slot) && now - this.flash.get(r.slot) < 1400) {
        g.fillStyle = `rgba(242,179,61,${1 - (now - this.flash.get(r.slot)) / 1400})`; g.font = '600 10px "IBM Plex Sans", sans-serif';
        g.fillText('told again', cx, cy - 2);
      }
      pos.set(r.slot, [cx + cell / 2, y + s * 0.4]);
    });
    // the read: the cue and the attention
    const age = (now - this.readAt) / 1000;
    if (this.read && age < 4) {
      const a = Math.max(0, 1 - age / 4), cx = W / 2 - 20, cy = 28;
      g.globalAlpha = a;
      g.imageSmoothingEnabled = false; g.drawImage(this.read.cueCanvas, cx, cy, 40, 32);
      g.fillStyle = '#4fc3f7'; g.font = '500 9.5px "IBM Plex Mono", monospace'; g.fillText('heard', cx + 46, cy + 12);
      g.fillText(this.read.write.revised ? 'told again' : 'a new record', cx + 46, cy + 25);
      this.read.slots.forEach((slot, k) => {
        const p = pos.get(slot), w = this.read.weights[k];
        if (!p || w < 0.01) return;
        g.strokeStyle = `rgba(79,195,247,${0.25 + 0.7 * w})`; g.lineWidth = 1 + 7 * w;
        g.beginPath(); g.moveTo(cx + 20, cy + 32); g.lineTo(p[0], p[1]); g.stroke();
      });
      g.globalAlpha = 1;
    }
    // the synapses: sounds by things, consolidated and residual
    g.fillStyle = '#6c7583'; g.font = '500 10.5px "IBM Plex Mono", monospace';
    g.fillText('SYNAPSES (SynapticMemory): SOUND TO THING', 12, top + 14);
    const things = this.data?.things || [], rows = recs.slice(0, 10);
    const halfW = (W - 36) / 2, colW = Math.max(10, (halfW - 30) / Math.max(1, things.length)), rowH = Math.max(8, Math.min(16, (H - top - 60) / Math.max(1, rows.length)));
    for (const [k, label, field] of [[0, 'lasting', 'slow'], [1, 'fading', 'fast']]) {
      const x0 = 12 + k * (halfW + 12) + 30, y0 = top + 40;
      g.fillStyle = '#a8b0bc'; g.font = '500 10px "IBM Plex Sans", sans-serif'; g.fillText(label, x0 - 30, top + 30);
      things.forEach((t, j) => {
        g.save(); g.translate(x0 + j * colW + colW / 2, y0 - 3); g.rotate(-0.6); g.fillStyle = '#6c7583'; g.font = '400 8.5px "IBM Plex Mono", monospace'; g.fillText(THING_LABEL[t] || t, 0, 0); g.restore();
      });
      rows.forEach((r, i) => {
        const t = this.thumbs.get(r.slot);
        if (t && k === 0) { g.imageSmoothingEnabled = false; g.drawImage(t.canvas, x0 - 28, y0 + i * rowH, 24, rowH - 1); }
        r[field].forEach((v, j) => {
          const m = Math.max(0, Math.min(1, Math.abs(v) / 0.6));
          g.fillStyle = k === 0 ? `rgb(${30 + 212 * m},${34 + 145 * m},${44 + 17 * m})` : `rgb(${30 + 49 * m},${34 + 161 * m},${44 + 203 * m})`;
          g.fillRect(x0 + j * colW, y0 + i * rowH, colW - 1, rowH - 1);
        });
      });
    }
  }
}
