// The brain view: the whole brain, live. Three parts, each the brain's own state as the host
// reports it:
// - the lexicon: every word neuron (a row, the word it holds), every concept neuron (a column:
//   the kinds, the colours, the places around the body, what a question asks, nothing found)
//   and every synapse between them (a cell: its strength, learned from naming);
// - the map: the map's sheet, 32 by 32 cells, each lit by the kind and the colour it holds;
// - the motor: the letters of the word it says.
// A question plays as it settled: the heard words' rows drive the concepts sweep by sweep, the
// map is asked, and each answer's concept drives the words until the motor says one.
import { drawThing, PAINT, VIEW } from './room.js';

const TEAL = [63, 224, 207], GOLD = [255, 206, 102], VIOLET = [183, 156, 255], ORANGE = [255, 159, 74], PISTACHIO = [160, 214, 98];
const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
const GROUP_TITLES = { kind: 'things', colour: 'colours', place: 'places', read: 'asks', none: '' };

export class BrainView {
  constructor(stage, canvas, onStage) {
    this.stage = stage; this.canvas = canvas; this.ctx = canvas.getContext('2d');
    this.onStage = onStage || (() => {});
    this.info = null; this.words = []; this.synapses = null; this.potential = null; this.clock = null;
    this.play = null; // the story playing: {story, began}
    this.hold = null; // the last frame of a story, kept until the next change
    this.taught = null; // a naming's word row, lit for a moment
    this.layout = null;
    new ResizeObserver(() => { this.resize(); }).observe(stage);
  }

  describe(info) { this.info = info; this.update(info); this.resize(); }

  update(state, arrays) {
    if (state.words) this.words = state.words;
    if (state.heading != null) this.heading = state.heading;
    if (arrays?.synapses) this.synapses = arrays.synapses;
    if (arrays?.potential) this.potential = arrays.potential;
    if (arrays?.clock) this.clock = arrays.clock;
    const rows = this.words.length;
    if (this.layout && rows !== this.layout.rows) this.resize(); else this.draw();
  }

  resize() {
    const r = this.stage.getBoundingClientRect();
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    this.canvas.width = Math.round(r.width * dpr); this.canvas.height = Math.round(r.height * dpr);
    this.canvas.style.width = r.width + 'px'; this.canvas.style.height = r.height + 'px';
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.w = r.width; this.h = r.height;
    this.layoutParts();
    this.draw();
  }

  layoutParts() {
    if (!this.info) return;
    const w = this.w, h = this.h, top = 62, pad = 14;
    const rows = Math.max(1, this.words.length);
    const cols = this.info.concepts;
    // the lexicon on the left, the map and the motor on the right
    const mapSide = Math.max(140, Math.min(w * 0.31, h - top - 150, 280));
    const lexW = w - mapSide - pad * 3;
    const labelW = 78;
    const cell = Math.max(5, Math.min(17, (lexW - labelW - 18) / (cols + 0.6 * 4), (h - top - 104 - pad) / rows));
    const groups = Object.entries(this.info.groups);
    const colX = [];
    let x = pad + labelW + 18;
    for (const [, [a, b]] of groups) { for (let c = a; c < b; c++) { colX[c] = x; x += cell; } x += cell * 0.6; }
    const lex = { x: pad, y: top, labelW, cell, colX, head: top + 46, dots: top + 64, body: top + 76, rows, right: x };
    const mapX = w - pad - mapSide;
    const map = { x: mapX, y: top + 18, side: mapSide };
    const motor = { x: mapX, y: map.y + mapSide + 40, w: mapSide, h: 54 };
    this.layout = { lex, map, motor, rows, groups };
    this.spots();
  }

  spots() {
    const E = window.CadenceExplain;
    if (!E || !this.layout) return;
    E.clearSpots(this.stage);
    const { lex, map, motor, groups } = this.layout;
    const bodyH = lex.rows * lex.cell;
    E.spot(this.stage, { x: lex.x, y: lex.body - 4, w: lex.labelW + 14, h: bodyH + 8 }, 'One neuron a word. A word takes a free neuron the first time the parrot hears it, and keeps it. The letters beside it are the ones the motor says for it.\n\nThe dot lights with the neuron\'s activity: driven when the word is heard, settled when a concept calls for a word.', { title: 'Word neurons', id: 'words' });
    E.spot(this.stage, { x: lex.colX[0] - 3, y: lex.body - 2, w: lex.right - lex.colX[0], h: bodyH + 4 }, 'Every synapse between a word and a concept, one cell each, drawn by its strength (teal: it excites, violet: it inhibits). All start at zero. Naming strengthens a word\'s synapses to what the parrot attends to while it hears the word; across namings a word keeps what they share.\n\nThe same synapses carry hearing (word to concept) and saying (concept to word). A cell glows while it carries a signal.', { title: 'The synapses: what words mean', id: 'synapses', mark: 'none' });
    const texts = {
      kind: 'One neuron for each kind of thing its eyes tell apart. Its icon is the program\'s drawing of that kind; the brain holds no name for it: the words for it are the synapses in its column.',
      colour: 'One neuron for each colour its eyes report. "Red" is whatever word the parrot heard while red things were in its attention.',
      place: 'One neuron for each place around the parrot\'s body: in front, to its right, behind it, to its left. The body tells the brain where a thing lies around it.',
      read: 'What a question asks for: a thing, its colour or its place. Question words such as "where" and "colour" learn these from answered questions, in the same synapses.',
      none: 'The concept for a question that finds nothing. Its word, "i do not know", was heard as the answer to questions about things that were not there.',
    };
    for (const [g, [a, b]] of groups) {
      E.spot(this.stage, { x: lex.colX[a] - 3, y: lex.head - 12, w: lex.colX[b - 1] - lex.colX[a] + lex.cell + 6, h: 36 }, texts[g], { title: { kind: 'Concepts: things', colour: 'Concepts: colours', place: 'Concepts: places', read: 'Concepts: what a question asks', none: 'Concept: nothing found' }[g], id: 'g-' + g });
    }
    E.spot(this.stage, { x: map.x, y: map.y, w: map.side, h: map.side }, 'Where everything is, in the brain\'s own state: a sheet of 32 by 32 cells over the room, each with a unit for every kind and every colour. A thing enters when its eyes first report it and stays at its last known place while out of view.\n\nA question asks the map by settling: the sheet settles on the units of a kind, of a colour or of the cells of a place around the body.', { title: 'The map of things', id: 'map' });
    E.spot(this.stage, { x: motor.x, y: motor.y - 18, w: motor.w, h: motor.h + 18 }, 'The motor says the most active word neuron\'s letters, one letter a slot. Every word the parrot says comes out here.', { title: 'The motor', id: 'motor' });
  }

  // -- a story: a question as the brain settled it

  playStory(story) {
    this.play = { story, began: performance.now(), plan: plan(story) };
    this.hold = null;
    this._done = null;
    this.tick();
  }

  playing() { return !!this.play; }

  /** Resolves when the story playing has played. */
  finished() { return this.play ? new Promise((resolve) => { this._done = resolve; }) : Promise.resolve(); }

  get speaking() { return !!(this.play && this.now && this.now.step.kind === 'motor'); }

  tick() {
    if (!this.play) return;
    const t = performance.now() - this.play.began;
    const { plan: p } = this.play;
    const now = p.find((s) => t >= s.from && t < s.to) || p[p.length - 1];
    this.now = { step: now, t: t - now.from, story: this.play.story };
    this.onStage(now, this.play.story, Math.min(1, (t - now.from) / Math.max(1, now.to - now.from)));
    this.draw();
    if (t < p[p.length - 1].to) requestAnimationFrame(() => this.tick());
    else {
      this.hold = this.now; this.play = null; this.onStage(null, this.hold.story, 1); this.draw();
      if (this._done) { const done = this._done; this._done = null; done(); }
    }
  }

  /** Light a word's row after a naming, and the synapses the naming changed. */
  named(unit, changed) { this.taught = { unit, began: performance.now() }; this.hold = null; this.lesson(changed, 'naming'); }

  /** The synapses a lesson changed glow for a moment ([word, concept, change] each); a pistachio
   *  washes the brain in the colour of its reward. */
  lesson(changed, kind, dopamine) {
    const mine = { changed: changed || [], kind, dopamine, began: performance.now() };
    this.flash = mine;
    const run = () => {
      if (this.flash !== mine) return; // a later lesson took over
      this.draw();
      if (performance.now() - mine.began < 1800) requestAnimationFrame(run);
      else { this.flash = null; this.taught = null; this.draw(); }
    };
    run();
  }

  clearStory() { this.hold = null; this.draw(); }

  // -- drawing

  draw() {
    const ctx = this.ctx;
    if (!this.layout || !this.info) { ctx.clearRect(0, 0, this.w || 0, this.h || 0); return; }
    ctx.clearRect(0, 0, this.w, this.h);
    const cur = this.play ? this.now : this.hold;
    this.drawLexicon(ctx, cur);
    this.drawMap(ctx, cur);
    this.drawMotor(ctx, cur);
  }

  /** The activity of the concept and word neurons at the frame `cur` shows. */
  activity(cur) {
    const n = this.info.concepts, words = this.words.length;
    const concepts = new Float32Array(n), wordAct = new Float32Array(words);
    let driven = null, signal = null, chosen = null;
    if (!cur) return { concepts, wordAct, driven, signal, chosen };
    const { step, t, story } = cur;
    if (step.kind === 'hear' || step.kind === 'choose' || step.kind === 'map') {
      const sweeps = story.hear.sweeps;
      const k = step.kind === 'hear' ? Math.min(sweeps.length - 1, Math.floor((t / (step.to - step.from)) * sweeps.length)) : sweeps.length - 1;
      sweeps[k].forEach((v, c) => { concepts[c] = v; });
      for (const w of story.hear.words) if (w.unit != null && w.unit < words) wordAct[w.unit] = 1;
      driven = 'words';
      if (step.kind !== 'hear') {
        const reads = Object.entries(story.hear.reads || {}).sort((a, b) => b[1] - a[1]);
        const read = reads.length && reads[0][1] > 0.05 ? this.info.answers.indexOf(reads[0][0]) : null;
        chosen = { about: story.about, read: read != null && read >= 0 ? read : null };
      }
    } else if (step.kind === 'say' || step.kind === 'motor') {
      const sp = story.spoken[step.index];
      sp.concept.forEach((v, c) => { concepts[c] = v; });
      const k = step.kind === 'say' ? Math.min(sp.sweeps.length - 1, Math.floor((t / (step.to - step.from)) * sp.sweeps.length)) : sp.sweeps.length - 1;
      sp.sweeps[k].forEach((a, u) => { if (u < words) wordAct[u] = a; });
      driven = 'concept';
      signal = sp.concept;
      if (step.kind === 'motor') chosen = { word: sp.unit };
    }
    return { concepts, wordAct, driven, signal, chosen };
  }

  drawLexicon(ctx, cur) {
    const { lex } = this.layout;
    const info = this.info, words = this.words, cell = lex.cell;
    const act = this.activity(cur);
    ctx.save();
    ctx.font = '600 11px Inter, system-ui, sans-serif'; ctx.fillStyle = '#c7d0ea'; ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
    ctx.fillText('The lexicon', lex.x, lex.y + 4);
    ctx.font = '500 10px Inter, system-ui, sans-serif'; ctx.fillStyle = '#5c6684';
    ctx.fillText(`${words.length} words of ${info.capacity} word neurons, ${info.concepts} concepts`, lex.x, lex.y + 17);
    // group titles and concept icons
    for (const [g, [a, b]] of this.layout.groups) {
      ctx.fillStyle = '#6f7a98'; ctx.font = '500 9.5px Inter, system-ui, sans-serif';
      ctx.fillText(GROUP_TITLES[g], lex.colX[a], lex.head - 12);
      for (let c = a; c < b; c++) this.icon(ctx, g, c - a, lex.colX[c] + cell / 2, lex.head + 4, Math.min(7, cell * 0.48));
    }
    // concept neurons' activity
    let top = 1e-6;
    act.concepts.forEach((v) => { top = Math.max(top, Math.abs(v)); });
    for (let c = 0; c < info.concepts; c++) {
      const v = Math.max(0, act.concepts[c]) / top;
      const cx = lex.colX[c] + cell / 2, cy = lex.dots;
      ctx.beginPath(); ctx.arc(cx, cy, Math.max(2, cell * 0.32), 0, 2 * Math.PI);
      ctx.fillStyle = v > 0.02 ? rgba(TEAL, 0.25 + 0.75 * v) : '#1b2333'; ctx.fill();
      if (v > 0.3) { ctx.shadowColor = rgba(TEAL, 0.9); ctx.shadowBlur = 8 * v; ctx.fill(); ctx.shadowBlur = 0; }
    }
    if (act.chosen && act.chosen.about) this.ring(ctx, lex.colX[this.info.groups[act.chosen.about[0]][0] + act.chosen.about[1]] + cell / 2, lex.dots, cell * 0.62, TEAL);
    if (act.chosen && act.chosen.read != null) this.ring(ctx, lex.colX[this.info.groups.read[0] + act.chosen.read] + cell / 2, lex.dots, cell * 0.62, GOLD);
    // the synapses
    const syn = this.synapses;
    let peak = 1e-6;
    if (syn) for (let i = 0; i < syn.length; i++) peak = Math.max(peak, Math.abs(syn[i]));
    let wordTop = 1e-6;
    act.wordAct.forEach((v) => { wordTop = Math.max(wordTop, v); });
    for (let u = 0; u < words.length; u++) {
      const y = lex.body + u * cell;
      const wv = Math.max(0, act.wordAct[u]) / wordTop;
      const taught = this.taught && this.taught.unit === u ? Math.max(0, 1 - (performance.now() - this.taught.began) / 1400) : 0;
      // the word's label and neuron
      ctx.font = `${cell >= 11 ? 500 : 400} ${Math.min(11, Math.max(7, cell - 2))}px "JetBrains Mono", ui-monospace, monospace`;
      ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
      ctx.fillStyle = taught > 0 ? rgba(ORANGE, 0.5 + 0.5 * taught) : wv > 0.05 ? rgba(TEAL, 0.5 + 0.5 * wv) : '#8d97b2';
      ctx.fillText(words[u], lex.x + lex.labelW, y + cell / 2);
      ctx.beginPath(); ctx.arc(lex.x + lex.labelW + 9, y + cell / 2, Math.max(1.8, cell * 0.3), 0, 2 * Math.PI);
      ctx.fillStyle = taught > 0 ? rgba(ORANGE, 0.4 + 0.6 * taught) : wv > 0.02 ? rgba(TEAL, 0.25 + 0.75 * wv) : '#1b2333'; ctx.fill();
      if (act.chosen && act.chosen.word === u) this.ring(ctx, lex.x + lex.labelW + 9, y + cell / 2, cell * 0.6, GOLD);
      if (!syn) continue;
      for (let c = 0; c < info.concepts; c++) {
        const e = syn[u * info.concepts + c] / peak;
        let carry = 0;
        if (act.driven === 'words' && act.wordAct[u] > 0) carry = Math.max(0, e);
        if (act.driven === 'concept' && act.signal[c] > 0) carry = Math.max(0, e) * act.signal[c];
        const x = lex.colX[c];
        const a = Math.min(1, Math.abs(e));
        if (a > 0.015) {
          ctx.fillStyle = e > 0 ? rgba(TEAL, 0.08 + 0.62 * a) : rgba(VIOLET, 0.08 + 0.5 * a);
          ctx.fillRect(x + 0.5, y + 0.5, cell - 1, cell - 1);
        } else { ctx.fillStyle = 'rgba(40,52,74,0.35)'; ctx.fillRect(x + cell * 0.35, y + cell * 0.35, cell * 0.3, cell * 0.3); }
        if (carry > 0.05) { ctx.fillStyle = rgba(GOLD, 0.25 + 0.75 * carry); ctx.fillRect(x + 1, y + 1, cell - 2, cell - 2); }
      }
    }
    if (this.flash && syn) {
      const t = (performance.now() - this.flash.began) / 1800;
      const fade = Math.max(0, 1 - t);
      const colour = this.flash.kind === 'naming' ? ORANGE : PISTACHIO;
      let top = 1e-9;
      for (const [, , d] of this.flash.changed) top = Math.max(top, Math.abs(d));
      for (const [u, c, d] of this.flash.changed) {
        if (u >= words.length) continue;
        const a = Math.min(1, 0.35 + Math.abs(d) / top) * fade;
        ctx.strokeStyle = rgba(colour, a); ctx.lineWidth = 1.5;
        ctx.strokeRect(lex.colX[c] + 0.5, lex.body + u * cell + 0.5, cell - 1, cell - 1);
      }
      if (this.flash.kind !== 'naming') {
        const wash = ctx.createRadialGradient(this.w * 0.35, this.h * 0.5, 10, this.w * 0.35, this.h * 0.5, this.w * 0.7);
        wash.addColorStop(0, rgba(PISTACHIO, 0.16 * fade)); wash.addColorStop(1, rgba(PISTACHIO, 0));
        ctx.fillStyle = wash; ctx.fillRect(0, 0, this.w, this.h);
        ctx.font = '600 12px Inter, system-ui, sans-serif'; ctx.fillStyle = rgba(PISTACHIO, fade); ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
        const n = this.flash.changed.length;
        const label = this.flash.kind === 'dopamine' ? `the reward arrives: dopamine ${this.flash.dopamine != null ? this.flash.dopamine.toFixed(2) : ''}` : 'a pistachio: the answer taken as right';
        ctx.fillText(`${label} · ${n} synapses change`, lex.x, lex.body + words.length * cell + 18);
      }
    }
    ctx.restore();
  }

  ring(ctx, x, y, r, c) { ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI); ctx.strokeStyle = rgba(c, 0.95); ctx.lineWidth = 1.6; ctx.stroke(); }

  icon(ctx, group, v, x, y, r) {
    ctx.save();
    if (group === 'kind') drawThing(ctx, v, null, x, y, r * 0.95, { neutral: '#9fb0c4', neutralEdge: '#3b4a5a' });
    else if (group === 'colour') { ctx.fillStyle = PAINT[v]; ctx.strokeStyle = 'rgba(200,210,230,0.5)'; ctx.lineWidth = 1; ctx.beginPath(); ctx.roundRect(x - r * 0.8, y - r * 0.8, r * 1.6, r * 1.6, 2); ctx.fill(); ctx.stroke(); }
    else if (group === 'place') {
      // a body and the quarter around it: the arrow points to the place, the body faces up
      const a = [-Math.PI / 2, 0, Math.PI / 2, Math.PI][v];
      ctx.fillStyle = '#56708e'; ctx.beginPath(); ctx.arc(x, y, r * 0.38, 0, 2 * Math.PI); ctx.fill();
      ctx.fillStyle = '#9fb0c4'; ctx.fillRect(x - r * 0.12, y - r * 0.55, r * 0.24, r * 0.2);
      ctx.strokeStyle = '#9fb0c4'; ctx.lineWidth = 1.4;
      const ex = x + Math.cos(a) * r, ey = y + Math.sin(a) * r;
      ctx.beginPath(); ctx.moveTo(x + Math.cos(a) * r * 0.5, y + Math.sin(a) * r * 0.5); ctx.lineTo(ex, ey); ctx.stroke();
      ctx.beginPath(); ctx.arc(ex, ey, 1.6, 0, 2 * Math.PI); ctx.fillStyle = '#c7d0ea'; ctx.fill();
    } else if (group === 'read') {
      ctx.font = `700 ${Math.round(r * 1.5)}px Inter, system-ui, sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillStyle = '#ffce66';
      if (v === 0) { drawThing(ctx, 0, null, x - r * 0.25, y, r * 0.6, { neutral: '#9fb0c4' }); }
      else if (v === 1) { ctx.fillStyle = PAINT[0]; ctx.fillRect(x - r * 0.85, y - r * 0.5, r * 0.5, r); ctx.fillStyle = PAINT[1]; ctx.fillRect(x - r * 0.35, y - r * 0.5, r * 0.5, r); }
      else { ctx.strokeStyle = '#9fb0c4'; ctx.lineWidth = 1.3; ctx.beginPath(); ctx.arc(x - r * 0.3, y, r * 0.5, 0, 2 * Math.PI); ctx.stroke(); ctx.beginPath(); ctx.moveTo(x - r * 0.3, y); ctx.lineTo(x + r * 0.05, y - r * 0.35); ctx.stroke(); }
      ctx.fillStyle = '#ffce66'; ctx.font = `700 ${Math.round(r * 1.1)}px Inter, system-ui, sans-serif`; ctx.fillText('?', x + r * 0.62, y);
    } else { ctx.strokeStyle = '#9fb0c4'; ctx.lineWidth = 1.3; ctx.beginPath(); ctx.arc(x, y, r * 0.6, 0, 2 * Math.PI); ctx.moveTo(x - r * 0.8, y + r * 0.8); ctx.lineTo(x + r * 0.8, y - r * 0.8); ctx.stroke(); }
    ctx.restore();
  }

  drawMap(ctx, cur) {
    const { map } = this.layout;
    const info = this.info, [nx, ny] = info.cells, width = info.width, units = info.units;
    const colours = info.values.colour;
    ctx.save();
    ctx.font = '600 11px Inter, system-ui, sans-serif'; ctx.fillStyle = '#c7d0ea'; ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
    ctx.fillText('The map of things', map.x, map.y - 6);
    ctx.fillStyle = '#0b111a'; ctx.strokeStyle = '#1f2a3d'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.roundRect(map.x, map.y, map.side, map.side, 8); ctx.fill(); ctx.stroke();
    const cs = map.side / nx;
    const pot = this.potential, clock = this.clock;
    let step = cur && (cur.step.kind === 'map') ? cur : null;
    const calls = step ? step.story.map_calls : (cur && cur.story && (cur.step.kind === 'say' || cur.step.kind === 'motor') ? cur.story.map_calls : null);
    let cueUnit = null, quarter = null;
    if (calls && calls.length) {
      const first = calls[0];
      if (first.call === 'where_is') cueUnit = first.kind;
      else if (first.call === 'where_is_value') cueUnit = colours[0] + first.value;
      else if (cur.story.about && cur.story.about[0] === 'place') quarter = cur.story.about[1];
    }
    if (pot) {
      let top = 1e-9;
      for (let i = 0; i < pot.length; i++) top = Math.max(top, pot[i]);
      for (let i = 0; i < nx; i++) for (let j = 0; j < ny; j++) {
        const cellIdx = i * ny + j, base = cellIdx * width;
        let best = -1, bv = 0;
        for (let k = 0; k < units; k++) { const v = pot[base + k]; if (v > bv) { bv = v; best = k; } }
        let colour = -1, cvv = 0;
        for (let k = colours[0]; k < colours[1]; k++) { const v = pot[base + k]; if (v > cvv) { cvv = v; colour = k - colours[0]; } }
        if (bv / top < 0.04) continue;
        const a = Math.min(1, Math.sqrt(bv / top));
        const px = map.x + i * cs, py = map.y + (ny - 1 - j) * cs;
        const hex = colour >= 0 ? PAINT[colour] : '#3fe0cf';
        ctx.globalAlpha = 0.2 + 0.8 * a * (clock && clock[cellIdx] > 0.5 ? 0.72 : 1);
        ctx.fillStyle = hex; ctx.fillRect(px + 0.4, py + 0.4, cs - 0.8, cs - 0.8);
        if (cueUnit != null && pot[base + cueUnit] / top > 0.04) { ctx.globalAlpha = 1; ctx.strokeStyle = rgba(GOLD, 0.95); ctx.lineWidth = 1.2; ctx.strokeRect(px + 0.6, py + 0.6, cs - 1.2, cs - 1.2); }
      }
      ctx.globalAlpha = 1;
    }
    // the body at the middle, its view and the place a question names
    const [x0, x1, y0, y1] = info.plane;
    const toPx = (x, y) => [map.x + ((x - x0) / (x1 - x0)) * map.side, map.y + ((y1 - y) / (y1 - y0)) * map.side];
    const [rx, ry] = toPx(0, 0);
    const heading = this.heading || 0;
    ctx.save(); ctx.beginPath(); ctx.roundRect(map.x, map.y, map.side, map.side, 8); ctx.clip();
    ctx.strokeStyle = 'rgba(255,236,170,0.28)'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(rx, ry); ctx.lineTo(rx + Math.cos(heading + VIEW) * map.side, ry - Math.sin(heading + VIEW) * map.side); ctx.moveTo(rx, ry); ctx.lineTo(rx + Math.cos(heading - VIEW) * map.side, ry - Math.sin(heading - VIEW) * map.side); ctx.stroke();
    ctx.restore();
    if (quarter != null) {
      const a = heading - (quarter * Math.PI) / 2;
      ctx.save(); ctx.beginPath(); ctx.roundRect(map.x, map.y, map.side, map.side, 8); ctx.clip();
      ctx.beginPath(); ctx.moveTo(rx, ry); ctx.arc(rx, ry, map.side, -(a + Math.PI / 4), -(a - Math.PI / 4)); ctx.closePath();
      ctx.fillStyle = rgba(GOLD, 0.12); ctx.fill(); ctx.strokeStyle = rgba(GOLD, 0.6); ctx.stroke(); ctx.restore();
    }
    ctx.fillStyle = '#8fb3d9'; ctx.beginPath(); ctx.arc(rx, ry, 3.5, 0, 2 * Math.PI); ctx.fill();
    if (cur && cur.story && cur.story.places && (cur.step.kind === 'map' || cur.step.kind === 'say' || cur.step.kind === 'motor')) {
      const shown = cur.step.kind === 'map' ? cur.story.places : cur.story.places.slice(cur.step.index, cur.step.index + 1);
      for (const p of shown) { const [px, py] = toPx(p[0], p[1]); this.ring(ctx, px, py, cs * 2.2, GOLD); }
    }
    ctx.font = '500 10px Inter, system-ui, sans-serif'; ctx.fillStyle = '#5c6684';
    ctx.fillText(`${nx} × ${ny} cells, ${width} units a cell`, map.x, map.y + map.side + 14);
    ctx.restore();
  }

  drawMotor(ctx, cur) {
    const { motor } = this.layout;
    ctx.save();
    ctx.font = '600 11px Inter, system-ui, sans-serif'; ctx.fillStyle = '#c7d0ea'; ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
    ctx.fillText('The motor', motor.x, motor.y - 6);
    const slots = 16, sw = motor.w / slots, sh = Math.min(24, sw * 1.5);
    let letters = [], shown = 0;
    if (cur && cur.step.kind === 'motor') {
      const sp = cur.story.spoken[cur.step.index];
      letters = sp.letters; shown = Math.floor((cur.t / (cur.step.to - cur.step.from)) * (letters.filter((c) => c < 28).length + 1));
    } else if (cur && !this.play && cur.story && cur.story.spoken.length) {
      const sp = cur.story.spoken[cur.story.spoken.length - 1];
      letters = sp.letters; shown = 99;
    }
    const LETTERS = 'abcdefghijklmnopqrstuvwxyz \'';
    for (let k = 0; k < slots; k++) {
      const x = motor.x + k * sw;
      ctx.fillStyle = '#0b111a'; ctx.strokeStyle = '#1f2a3d'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.roundRect(x + 1, motor.y, sw - 2, sh, 3); ctx.fill(); ctx.stroke();
      const c = letters[k];
      if (c != null && c < 28 && k < shown) {
        ctx.fillStyle = rgba(GOLD, 0.95); ctx.font = `600 ${Math.round(sh * 0.62)}px "JetBrains Mono", ui-monospace, monospace`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(LETTERS[c] === ' ' ? '·' : LETTERS[c], x + sw / 2, motor.y + sh / 2 + 1);
      }
    }
    ctx.restore();
  }
}

/** The steps of a story and their times in milliseconds. */
function plan(story) {
  const out = [];
  let t = 0;
  const add = (kind, ms, extra = {}) => { out.push({ kind, from: t, to: t + ms, ...extra }); t += ms; };
  add('hear', 900);
  add('choose', 500);
  add('map', story.map_calls.length ? 900 : 300);
  story.spoken.forEach((sp, index) => {
    add('say', 650, { index });
    add('motor', 120 + 70 * Math.max(1, sp.letters.filter((c) => c < 28).length), { index });
  });
  return out;
}
