// The brain panel: one card a region of the running brain, in the order a memory travels (seeing,
// then hearing, then keeping and saying), each named as the neurons of its region and drawn in the
// region's colour of the 3D view. Each card shows its populations' activity at every moment: an eye's
// retina as its image, the map of things as the table seen from above, a hearing area as a running
// picture of its bands, small populations as rows of neurons. The record slots and the word links
// come from the library's memories the host reports. Pointing at a card lights its region in the 3D
// view, and pointing at a region there lights its card here.
//
// Below the cards: the distance neurons with their tuning curves (#332 E7) and the switch that
// silences them; and the joints, each with its target and where it stands.
import { R, SHORT, DOES, hueOf } from './atlas.js';
import { regionOf } from './brain3d.js';

const STORY = ['retina', 'tectum', 'rotundus', 'wulst', 'arco', 'place', 'map', 'ear', 'fieldl', 'ncm', 'records', 'words', 'vocal', 'voice'];
const BYID = Object.fromEntries(R.map((r) => [r.id, r]));
const HIST = 64; // moments a hearing area's running picture keeps
const rgbOf = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));

/** A colour ramp from the dark ground through the region's colour to white. */
function ramp(base) {
  const out = new Uint8Array(256 * 3), dark = [16, 22, 27];
  for (let i = 0; i < 256; i++) {
    const t = i / 255, c = t < 0.7 ? dark.map((d, k) => d + (base[k] - d) * (t / 0.7)) : base.map((m, k) => m + (250 - m) * ((t - 0.7) / 0.3));
    out[3 * i] = c[0]; out[3 * i + 1] = c[1]; out[3 * i + 2] = c[2];
  }
  return out;
}

export class BrainView {
  constructor({ regions, units, tuning, readout, silence, joints }) {
    this.root = regions;
    this.unitsCanvas = units; this.tuningCanvas = tuning; this.readoutEl = readout; this.silenceBtn = silence; this.jointsEl = joints;
    this.ready = false;
    this.tuningBins = 28;
    this.labelBoxes = []; // the drawn labels a text check reads (the cards' text is in the page itself)
    new ResizeObserver(() => this.layoutTuning()).observe(units.parentElement);
    document.addEventListener('parrot:region', (e) => this.lit(e.detail?.id || null, e.detail?.from));
  }

  setup(desc, jointSpec) {
    this.desc = desc;
    this.n = desc.neurons;
    this.activity = new Float32Array(this.n);
    this.group = (desc.groups || []).find((g) => g.variable === 'distance') || null;
    if (this.group) {
      const [lo, hi] = this.group.range || [0.1, 0.8];
      this.range = [lo, hi];
      this.sum = new Float32Array(this.group.units.length * this.tuningBins);
      this.count = new Float32Array(this.tuningBins);
    }
    this.jointSpec = jointSpec;
    this.buildJoints();
    this.buildCards();
    this.ready = true;
    this.layoutTuning();
  }

  // --- the cards ------------------------------------------------------------------------------------
  buildCards() {
    this.root.textContent = '';
    const byRegion = new Map();
    for (const p of this.desc.populations || []) {
      const id = regionOf(p) || 'other';
      if (!byRegion.has(id)) byRegion.set(id, []);
      byRegion.get(id).push(p);
    }
    // the records and the word links are the library's memories, reported with the reply
    byRegion.set('records', byRegion.get('records') || []); byRegion.set('words', byRegion.get('words') || []);
    const ids = [...byRegion.keys()].sort((a, b) => (STORY.indexOf(a) + 1 || 99) - (STORY.indexOf(b) + 1 || 99));
    this.cards = []; this.byRegion = {};
    const eye = this.desc.eye || { w: 64, h: 32 };
    for (const id of ids) {
      const spec = BYID[id], pops = byRegion.get(id), colour = spec ? hueOf(spec) : '#9aa7b8';
      const card = document.createElement('section'); card.className = 'rcard'; card.dataset.region = id; card.style.setProperty('--rc', colour);
      const head = document.createElement('h4');
      const neurons = pops.reduce((a, p) => a + p.size, 0);
      const name = spec ? (SHORT[id] || spec.name) : 'Other', does = DOES[id] || (spec ? spec.name.split(':').pop().trim() : '');
      const count = id === 'records' ? 'records' : id === 'words' ? 'synapses' : `${neurons.toLocaleString('en')} neuron${neurons === 1 ? '' : 's'}`;
      head.innerHTML = `<i></i><b></b><span class="does"></span><em></em>`;
      head.querySelector('b').textContent = name; head.querySelector('.does').textContent = does; head.querySelector('em').textContent = count;
      head.setAttribute('data-explain-title', spec ? spec.name : name);
      const live = id === 'records' ? 'The records are the Cadence library’s long-term memory: one record a sound kept, its picture the sound itself (time left to right, pitch bottom to top), larger the deeper. A gold outline: deep enough to say back.'
        : id === 'words' ? 'The synapses from each sound’s record (rows) to each kind of thing (columns): bright where the sound was heard while the parrot looked at that thing. The column of the thing in focus is outlined.'
          : `Its populations: ${pops.map((p) => `${p.title || p.name} (${p.size.toLocaleString('en')})`).join(', ')}. Each square is one neuron, brighter the more active it is at this moment.`;
      head.setAttribute('data-explain', `${spec ? `In a bird: ${spec.bird}.\n\nIn this brain: ${spec.role}\n\n` : ''}${live}`);
      card.append(head);
      const grids = document.createElement('div'); grids.className = 'pops';
      card.append(grids);
      const entry = { id, card, pops: [], colour: rgbOf(colour), ramp: ramp(rgbOf(colour)) };
      for (const p of pops) {
        const shape = this.shapeOf(p, id, eye);
        const fig = document.createElement('figure'); fig.className = `pop ${shape.kind}`;
        const c = document.createElement('canvas'); c.width = shape.w; c.height = shape.h;
        if (shape.kind === 'rows') c.style.width = `${Math.min(100, shape.w * 12)}px`;
        if (shape.kind !== 'bands') c.style.aspectRatio = `${shape.w} / ${shape.h}`;
        const cap = document.createElement('figcaption'); cap.textContent = this.captionOf(p, id);
        fig.append(c, cap); grids.append(fig);
        entry.pops.push({ p, c, g: c.getContext('2d'), img: null, ...shape, hist: shape.kind === 'bands' ? new Float32Array(HIST * p.size) : null });
      }
      if (id === 'records' || id === 'words') {
        const fig = document.createElement('figure'); fig.className = `pop ${id}`;
        const c = document.createElement('canvas'); c.width = id === 'records' ? 300 : 300; c.height = id === 'records' ? 46 : 92;
        const cap = document.createElement('figcaption'); cap.textContent = id === 'records' ? 'no sound kept so far: say a short word a few times' : 'no links so far';
        fig.append(c, cap); grids.append(fig);
        entry.mem = { c, g: c.getContext('2d'), cap };
      }
      card.addEventListener('pointerenter', () => this.point(id));
      card.addEventListener('pointerleave', () => this.point(null));
      this.root.append(card);
      this.cards.push(entry); this.byRegion[id] = entry;
    }
    // the distance card is the arcopallium's distance neurons
    const dist = document.getElementById('dist-card'), arco = BYID.arco;
    if (dist && this.group) {
      dist.style.setProperty('--rc', hueOf(arco)); dist.dataset.region = 'arco'; dist.classList.add('rcard-like');
      const t = document.getElementById('dist-title');
      if (t) t.textContent = `Arcopallium: ${this.group.title.replace(/^./, (c) => c.toLowerCase())} (${this.group.units.length} neurons)`;
      dist.setAttribute('data-explain-title', this.group.title); dist.setAttribute('data-explain', this.group.explain || 'The neurons the brain uses for distance.');
      dist.onpointerenter = () => this.point('arco'); dist.onpointerleave = () => this.point(null);
    }
  }

  /** The grid a population is drawn on: an eye's image, the map's table, bands over time, or rows. */
  shapeOf(p, id, eye) {
    if (id === 'retina') {
      for (let pool = 1; pool <= 8; pool++) { // the eye's image pooled pool by pool pixels
        const w = Math.floor(eye.w / pool), h = Math.floor(eye.h / pool);
        if (w * h === p.size) return { kind: 'image', w, h, mirror: /_r$|right/i.test(p.name + p.title) };
      }
    }
    if (id === 'map' && p.size === 54 * 37) return { kind: 'table', w: 54, h: 37 };
    if (p.size === 40 && ['ear', 'fieldl', 'ncm', 'voice'].includes(id)) return { kind: 'bands', w: HIST, h: 40 };
    const w = Math.min(p.size, p.size > 48 ? 24 : 16), h = Math.ceil(p.size / w);
    return { kind: 'rows', w, h };
  }
  captionOf(p, id) {
    const t = (p.title || p.name).replace(/^(Left|Right) eye[’']?s? retina/i, '$1 eye').replace(/^(Left|Right) eye: .*/i, '$1 eye');
    if (id === 'map') return 'place cells over the table, seen from above (the parrot at the middle, its beak down)';
    if (['ear', 'fieldl', 'ncm', 'voice'].includes(id)) return `${t.replace(/:.*$/, '')}: its 40 bands over the last 6 s (low pitch at the bottom)`;
    return t;
  }

  point(id) { document.dispatchEvent(new CustomEvent('parrot:region', { detail: { id, from: 'panel' } })); }
  lit(id, from) {
    for (const e of this.cards || []) e.card.classList.toggle('hot', e.id === id);
    document.getElementById('dist-card')?.classList.toggle('hot', id === 'arco');
    clearTimeout(this.scrollTimer);
    if (id && from === '3d') this.scrollTimer = setTimeout(() => this.byRegion?.[id]?.card.scrollIntoView({ block: 'nearest', behavior: 'smooth' }), 450);
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
    this.groupNow = reply.group_activity?.distance?.length ? reply.group_activity.distance : null;
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
    if (reply.memory) { this.memory = reply.memory; this.memDirty = true; }
    const focus = window.parrotPage?.state?.focus?.id || null;
    if (focus !== this.focusId) { this.focusId = focus; this.memDirty = true; }
    this.drawCards();
    this.memDirty = false;
  }

  drawCards() {
    const a = this.activity;
    for (const e of this.cards) {
      for (const q of e.pops) {
        const { p, w, h, g } = q;
        q.img ||= g.createImageData(w, h);
        const d = q.img.data, rp = e.ramp;
        if (q.kind === 'bands') { // the running picture: the newest moment at the right
          q.hist.copyWithin(0, p.size); q.hist.set(a.subarray(p.start, p.start + p.size), (HIST - 1) * p.size);
          for (let x = 0; x < HIST; x++) for (let y = 0; y < 40; y++) {
            const v = q.hist[x * 40 + (39 - y)], k = Math.max(0, Math.min(255, (v * 255) | 0)), j = 4 * (y * w + x);
            d[j] = rp[3 * k]; d[j + 1] = rp[3 * k + 1]; d[j + 2] = rp[3 * k + 2]; d[j + 3] = 255;
          }
        } else {
          for (let i = 0; i < w * h; i++) {
            let src = i;
            if (q.kind === 'table') { const x = i % 54, z = (i / 54) | 0; src = x * 37 + z; } // the map's cells run x-major
            else if (q.mirror) { const x = i % w, y = (i / w) | 0; src = y * w + (w - 1 - x); }
            const v = src < p.size ? a[p.start + src] : 0, k = Number.isFinite(v) ? Math.max(0, Math.min(255, (v * 255) | 0)) : 0, j = 4 * i;
            d[j] = rp[3 * k]; d[j + 1] = rp[3 * k + 1]; d[j + 2] = rp[3 * k + 2]; d[j + 3] = src < p.size ? 255 : 0;
          }
        }
        g.putImageData(q.img, 0, 0);
      }
      if (e.mem && this.memory && this.memDirty) this.drawMemory(e);
    }
  }

  /** The records (each its sound's picture, its depth) or the word links (records by things). */
  drawMemory(e) {
    const m = this.memory, { c, g, cap } = e.mem, W = c.width, H = c.height, recs = m.records || [];
    g.clearRect(0, 0, W, H);
    const level = m.level || 2.5;
    if (e.id === 'records') {
      const cell = 24, gap = 4, per = Math.floor((W + gap) / (cell + gap));
      recs.slice(0, per).forEach((r, i) => {
        const x = i * (cell + gap), t = r.thumb || [], frames = Math.max(1, Math.round(t.length / 20));
        const faded = r.faded / (r.faded + 600);
        g.globalAlpha = Math.max(0.25, 1 - faded);
        for (let fx = 0; fx < frames; fx++) for (let y = 0; y < 20; y++) {
          const v = (t[fx * 20 + (19 - y)] || 0) / 255, k = Math.min(255, (v * 255) | 0);
          g.fillStyle = `rgb(${e.ramp[3 * k]},${e.ramp[3 * k + 1]},${e.ramp[3 * k + 2]})`;
          g.fillRect(x + (fx * cell) / frames, 2 + (y * cell) / 20, cell / frames + 0.5, cell / 20 + 0.5);
        }
        g.globalAlpha = 1;
        if (r.deep >= level) { g.strokeStyle = '#f2b33d'; g.lineWidth = 1.5; g.strokeRect(x + 0.75, 2.75, cell - 1.5, cell - 1.5); }
        g.fillStyle = '#f2b33d'; g.fillRect(x, cell + 6, cell * Math.min(1, r.deep / (level * 4)), 3);
        g.fillStyle = '#6c7583'; g.font = '500 9px "IBM Plex Mono", monospace'; g.fillText(r.deep.toFixed(1), x, cell + 19);
      });
      const text = recs.length ? `${recs.length} sound${recs.length === 1 ? '' : 's'} kept; the number is each record’s depth` : 'no sound kept so far: say a short word a few times';
      if (cap.textContent !== text) cap.textContent = text;
      return;
    }
    // the word links: one row a record, one column a kind of thing
    const things = m.things || [], focus = window.parrotPage?.state?.focus?.id ? window.parrotPage.room.things.get(window.parrotPage.state.focus.id)?.kind : null;
    const rows = Math.min(recs.length, 6), colW = Math.floor((W - 4) / Math.max(1, things.length)), rowH = 9;
    g.font = '500 9px "IBM Plex Mono", monospace';
    things.forEach((name, k) => {
      const x = 2 + k * colW;
      g.fillStyle = name === focus ? '#f2b33d' : '#6c7583'; g.fillText(name.slice(0, 6), x + 1, 10);
      if (name === focus) { g.strokeStyle = '#f2b33d'; g.lineWidth = 1; g.strokeRect(x + 0.5, 13.5, colW - 2, rows * rowH + 2); }
    });
    let any = false;
    for (let i = 0; i < rows; i++) {
      const r = recs[i];
      things.forEach((_, k) => {
        const v = Math.max(0, (r.slow?.[k] || 0) + (r.fast?.[k] || 0)), u = Math.min(1, v / 0.4), q = Math.min(255, (u * 255) | 0);
        if (u > 0.04) any = true;
        g.fillStyle = `rgb(${e.ramp[3 * q]},${e.ramp[3 * q + 1]},${e.ramp[3 * q + 2]})`;
        g.fillRect(3 + k * colW, 15 + i * rowH, colW - 4, rowH - 2);
      });
    }
    const text = !recs.length ? 'no links so far' : any ? 'each row a sound kept, each column a thing; bright: the sound names that thing' : 'say a word while the parrot looks at a thing';
    if (cap.textContent !== text) cap.textContent = text;
  }

  setJoints(pos, target) {
    if (!this.jointRows) return;
    this.jointRows.forEach((r, i) => {
      const j = r.j, f = (v) => `${(100 * (v - j.min)) / (j.max - j.min)}%`;
      r.pos.style.left = f(pos[i]);
      r.tgt.style.left = f(Math.max(j.min, Math.min(j.max, target[i])));
    });
  }

  layoutTuning() {
    if (!this.ready) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    for (const c of [this.unitsCanvas, this.tuningCanvas]) {
      const w = c.parentElement.clientWidth || 300, h = c === this.unitsCanvas ? 26 : 92;
      c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); c.style.height = `${h}px`;
      c.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0);
      c.dataset.w = w; c.dataset.h = h;
    }
  }

  frame() {
    if (!this.ready) return;
    this.drawUnits(); this.drawTuning();
  }

  drawUnits() {
    const c = this.unitsCanvas, g = c.getContext('2d'), W = +c.dataset.w, H = +c.dataset.h;
    g.clearRect(0, 0, W, H);
    if (!this.group) return;
    const U = this.group.units.length, w = W / U, rp = this.arcoRamp ||= ramp(rgbOf(hueOf(BYID.arco)));
    for (let u = 0; u < U; u++) {
      const v = this.groupNow ? this.groupNow[u] : 0, k = Math.max(0, Math.min(255, (v * 255) | 0));
      g.fillStyle = `rgb(${rp[3 * k]},${rp[3 * k + 1]},${rp[3 * k + 2]})`;
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
    for (const d of [0.2, 0.4, 0.6, 0.8, 1.0]) {
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
