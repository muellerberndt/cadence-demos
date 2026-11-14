// The live layer of the 3D brain: what the brain host reports each moment, drawn where it happens.
//
// - Record slots: a ring at the records, one slot a sound kept, its picture the stored sound itself
//   (its code, never letters); larger the deeper, fainter the more faded; a gold rim once deep
//   enough to say back. A new record pops in, one told again flashes and grows.
// - A word stored: a packet flies from Field L to NCM to its slot. A word said: from its slot to
//   the vocal core to the voice, with how well it matched.
// - Word links: lines from each record to the thing units it names (synapses), brighter as the link
//   grows; the thing in focus lights.
// - Memory heads: a beam from the cue to each record a head read, as wide as its attention.
// - The map of things: the hippocampus's place cells, the things on the map, the head's heading and
//   its fields of view, the focus; a line from the tectum to the thing in focus.
// - Surprise: warm flashes where it arises. Neuromodulators: each a coloured wash from its nucleus
//   along its fibres. Repairs: the settle's residual per region and the corrections along tracts.
//
// It reads the host's `viz` block (VIZ_EVENTS.md) and, where `viz` lacks a part, the reply's own
// fields that carry it (memory, heard_sound, said, focus, things, startle, vta, paid). A part no field
// carries is not drawn, and the parts list says "not in this brain yet".
import * as THREE from 'three';
import { MOD, PATHS, SHORT } from './atlas.js';

export const PARTS = [
  { id: 'repairs', name: 'Repairs', colour: '#ffe2a8', explain: 'Each moment the brain settles: every region corrects itself toward agreement with the regions it hears from, and the corrections travel along the tracts until nothing changes. Drawn as a warm glow on each region that fades as it settles, and light running along the tracts. The host sends it as each region’s residual at each sweep of the settle.' },
  { id: 'surprise', name: 'Surprise', colour: '#ff7a3d', explain: 'What the brain did not expect: a sudden sound, a thing that appears or starts to move. A sharp warm flash where it arises, and it draws the focus there.' },
  { id: 'dopamine', name: 'Dopamine', colour: MOD.dopamine.colour, explain: MOD.dopamine.explain },
  { id: 'noradrenaline', name: 'Noradrenaline', colour: MOD.noradrenaline.colour, explain: MOD.noradrenaline.explain },
  { id: 'acetylcholine', name: 'Acetylcholine', colour: MOD.acetylcholine.colour, explain: MOD.acetylcholine.explain },
  { id: 'slots', name: 'Record slots', colour: '#b49cff', explain: 'The ring at the records: every sound the parrot kept, one slot each. The little picture in a slot is the stored sound itself (time left to right, pitch bottom to top), never letters. A slot is larger the deeper its record (heard again and again) and fainter the more it has faded; a gold rim means it is deep enough to say back.' },
  { id: 'stored', name: 'A word stored', colour: '#e9ddff', explain: 'When the parrot hears a word, a bright packet flies from Field L (the first hearing area of the forebrain) to NCM (where heard sounds are held) and on to its record slot: a new slot pops in, or the word’s slot flashes and grows ("told again").' },
  { id: 'links', name: 'Word links', colour: '#f2e48a', explain: 'The synapses from a sound’s record to the thing it names. Heard while the parrot looks at the apple, the sound’s record links to the apple’s unit; said again with the apple in view, the link grows brighter. The sound becomes the word for the apple.' },
  { id: 'heads', name: 'Memory heads', colour: '#ff9f43', explain: 'A head reads the records with a cue (a sound just heard) and attends to the records that match it. Drawn as a beam from the cue to each record it read, as wide as its attention. Several heads read different records at once, each in its own colour.' },
  { id: 'map', name: 'Map of things', colour: '#3fd6c2', explain: 'The hippocampus holds a map of the table: its place cells glow where things are. White dots are things in view, grey rings things held out of view; the lines from the centre are the head’s heading and the two eyes’ fields. The amber ring is the thing in focus, and the line to it comes from the tectum, which chose it.' },
  { id: 'saying', name: 'Saying', colour: '#ff8a5c', explain: 'When the parrot says a word it knows, the word is read out of its record to the vocal core and the voice: a packet flies from the slot to the voice, and the label shows how well the attempt matched the word it remembers.' },
];
const HEAD_COLOURS = ['#ff9f43', '#54a0ff', '#ff6bcb', '#7bed9f'];
// the association's populations (the whole brain's paid tracts) as atlas regions
const PAID_AREAS = { association: 'ncl', prefrontal: 'trace', history: 'trace', recall: 'records', next: 'records', recall_1: 'heads', next_1: 'heads', motor: 'arco' };
const TABLE = { x: 0.8, z: 0.55 };
const EYE = { field: 87.5, axis: 75 }; // the page's eye geometry (degrees): half-field and axis from the beak

const FX_CAP = 640;
const fxVertex = `attribute float size; attribute float alpha; attribute float shape; attribute vec3 acol;
varying vec3 vC; varying float vA; varying float vS; uniform float scale;
void main() { vec4 mv = modelViewMatrix * vec4(position, 1.0); gl_Position = projectionMatrix * mv;
  gl_PointSize = alpha > 0.0 ? size * scale / max(0.1, -mv.z) : 0.0; vC = acol; vA = alpha; vS = shape; }`;
const fxFragment = `varying vec3 vC; varying float vA; varying float vS;
void main() { vec2 p = gl_PointCoord * 2.0 - 1.0; float r = length(p); if (r > 1.0) discard;
  float a = vS < 0.5 ? pow(1.0 - r, 1.6) : vS < 1.5 ? smoothstep(0.62, 0.76, r) * (1.0 - smoothstep(0.88, 1.0, r)) : (1.0 - smoothstep(0.42, 0.56, r)) + 0.5 * pow(1.0 - r, 1.2);
  gl_FragColor = vec4(vC * a * vA, 1.0); }`;
const slotVertex = `attribute float size; attribute float alpha; attribute vec3 acol; attribute vec2 cell; attribute float rim; attribute float hot;
varying vec3 vC; varying float vA; varying vec2 vCell; varying float vRim; varying float vHot; uniform float scale;
void main() { vec4 mv = modelViewMatrix * vec4(position, 1.0); gl_Position = projectionMatrix * mv;
  gl_PointSize = alpha > 0.0 ? size * scale / max(0.1, -mv.z) : 0.0; vC = acol; vA = alpha; vCell = cell; vRim = rim; vHot = hot; }`;
const slotFragment = `varying vec3 vC; varying float vA; varying vec2 vCell; varying float vRim; varying float vHot; uniform sampler2D atlas;
void main() { vec2 p = gl_PointCoord; vec2 q = abs(p * 2.0 - 1.0); float r = max(q.x, q.y); if (r > 1.0) discard;
  vec2 uv = vec2((vCell.x + 0.12 + 0.76 * p.x) / 8.0, 1.0 - (vCell.y + 0.12 + 0.76 * p.y) / 6.0);
  float img = r < 0.76 ? texture2D(atlas, uv).r : 0.0;
  vec3 c = vC * (0.18 + 1.05 * img) + vec3(vHot);
  float edge = smoothstep(0.8, 0.86, r) * (1.0 - smoothstep(0.94, 1.0, r));
  c = mix(c, mix(vC * 0.7, vec3(1.0, 0.78, 0.3), vRim), edge * (0.55 + 0.45 * vRim));
  gl_FragColor = vec4(c, vA * (r < 0.76 ? 0.95 : edge * 0.95 + 0.25 * (1.0 - edge))); }`;

const ease = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));
const env = (age, rise, fall) => (age < 0 ? 0 : age < rise ? age / rise : Math.max(0, 1 - (age - rise) / fall));

export class Live {
  constructor(b) {
    this.b = b;
    this.slots = new Map(); // slot -> { slot, deep, faded, heard, match, thumb, born, flash, k (ring order), size }
    this.things = [];       // the thing units' names (the word links' targets)
    this.level = 2.5;
    this.packets = []; this.beams = []; this.washes = []; this.flashes = []; this.notes = [];
    this.focus = null; this.mapThings = null; this.heading = 0; this.settle = null;
    this.upV = new THREE.Vector3(0, 1, 0);
    this.status = {}; this.stepText = ['', '', '', '']; this.stepAt = [null, null, null, null];
    this.tmp = [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()];
    this.build();
  }

  build() {
    const scene = this.b.scene;
    // one cloud of every effect: thing units, packets, beams, washes, rings
    const geo = new THREE.BufferGeometry();
    this.fxPos = new Float32Array(FX_CAP * 3); this.fxCol = new Float32Array(FX_CAP * 3);
    this.fxSize = new Float32Array(FX_CAP); this.fxAlpha = new Float32Array(FX_CAP); this.fxShape = new Float32Array(FX_CAP);
    geo.setAttribute('position', new THREE.BufferAttribute(this.fxPos, 3).setUsage(THREE.DynamicDrawUsage));
    geo.setAttribute('acol', new THREE.BufferAttribute(this.fxCol, 3).setUsage(THREE.DynamicDrawUsage));
    geo.setAttribute('size', new THREE.BufferAttribute(this.fxSize, 1).setUsage(THREE.DynamicDrawUsage));
    geo.setAttribute('alpha', new THREE.BufferAttribute(this.fxAlpha, 1).setUsage(THREE.DynamicDrawUsage));
    geo.setAttribute('shape', new THREE.BufferAttribute(this.fxShape, 1).setUsage(THREE.DynamicDrawUsage));
    geo.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 50);
    this.scaleU = { value: 600 };
    this.fx = new THREE.Points(geo, new THREE.ShaderMaterial({ uniforms: { scale: this.scaleU }, vertexShader: fxVertex, fragmentShader: fxFragment,
      transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending }));
    this.fx.renderOrder = 5; this.fx.frustumCulled = false;
    scene.add(this.fx);
    // the record slots, each with the picture of its sound
    this.atlasCanvas = document.createElement('canvas'); this.atlasCanvas.width = 256; this.atlasCanvas.height = 192;
    this.atlas = new THREE.CanvasTexture(this.atlasCanvas); this.atlas.magFilter = THREE.LinearFilter;
    const sg = new THREE.BufferGeometry(), S = 48;
    this.slotPos = new Float32Array(S * 3); this.slotCol = new Float32Array(S * 3); this.slotSize = new Float32Array(S); this.slotAlpha = new Float32Array(S);
    this.slotCell = new Float32Array(S * 2); this.slotRim = new Float32Array(S); this.slotHot = new Float32Array(S);
    for (const [name, arr, n] of [['position', this.slotPos, 3], ['acol', this.slotCol, 3], ['size', this.slotSize, 1], ['alpha', this.slotAlpha, 1], ['cell', this.slotCell, 2], ['rim', this.slotRim, 1], ['hot', this.slotHot, 1]]) {
      sg.setAttribute(name, new THREE.BufferAttribute(arr, n).setUsage(THREE.DynamicDrawUsage));
    }
    sg.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 50);
    this.slotPoints = new THREE.Points(sg, new THREE.ShaderMaterial({ uniforms: { scale: this.scaleU, atlas: { value: this.atlas } }, vertexShader: slotVertex, fragmentShader: slotFragment,
      transparent: true, depthWrite: false, depthTest: false }));
    this.slotPoints.renderOrder = 6; this.slotPoints.frustumCulled = false;
    scene.add(this.slotPoints);
    // the lines: word links (record to thing), the focus line (tectum to the map), the ring's rim
    const LINES = 48 * 8 + 4 + 64;
    this.linePos = new Float32Array(LINES * 6); this.lineCol = new Float32Array(LINES * 6);
    const lg = new THREE.BufferGeometry();
    lg.setAttribute('position', new THREE.BufferAttribute(this.linePos, 3).setUsage(THREE.DynamicDrawUsage));
    lg.setAttribute('color', new THREE.BufferAttribute(this.lineCol, 3).setUsage(THREE.DynamicDrawUsage));
    lg.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 50);
    this.lines = new THREE.LineSegments(lg, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending }));
    this.lines.renderOrder = 4; this.lines.frustumCulled = false;
    scene.add(this.lines);
    // the map of things, a card that faces the viewer inside the hippocampus
    this.mapCanvas = document.createElement('canvas'); this.mapCanvas.width = 232; this.mapCanvas.height = 176;
    this.mapSheet = document.createElement('canvas'); this.mapSheet.width = 54; this.mapSheet.height = 37;
    this.mapTex = new THREE.CanvasTexture(this.mapCanvas); this.mapTex.colorSpace = THREE.SRGBColorSpace;
    this.mapSprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.mapTex, transparent: true, depthTest: false, depthWrite: false, opacity: 0.95 }));
    this.mapSprite.scale.set(1.9, 1.44, 1); this.mapSprite.renderOrder = 3;
    const m = this.b.byId.map; this.mapSprite.position.set(m.at[0], m.at[1] + 1.15, m.at[2]);
    m.top.set(m.at[0], m.at[1] + 1.15 + 0.82, m.at[2]);
    scene.add(this.mapSprite);
    this.drawMap();
    // labels for what happens (a pool of four), and the thing unit in focus
    this.noteEls = [0, 1, 2, 3].map(() => { const el = document.createElement('span'); el.className = 'b3-note'; el.hidden = true; this.b.labels.append(el); return el; });
    this.thingEl = document.createElement('span'); this.thingEl.className = 'b3-note thing'; this.thingEl.hidden = true; this.b.labels.append(this.thingEl);
    this.stepEls = [0, 1, 2, 3].map(() => { const el = document.createElement('span'); el.className = 'b3-step'; el.hidden = true; this.b.labels.append(el); return el; });
    this.colour = (hex) => new THREE.Color(hex);
    this.cHear = this.colour('#b49cff'); this.cWhite = this.colour('#ffffff'); this.cWarm = this.colour('#ff7a3d'); this.cLink = this.colour('#f2e48a');
    this.cThing = this.colour('#6cb6ff'); this.cFocus = this.colour('#f2b33d'); this.cSay = this.colour('#ff8a5c'); this.cGold = this.colour(MOD.dopamine.colour);
    this.modColour = Object.fromEntries(Object.entries(MOD).map(([k, v]) => [k, this.colour(v.colour)]));
    this.headColour = HEAD_COLOURS.map((h) => this.colour(h));
  }

  resize(w, h) { this.scaleU.value = (h * this.b.renderer.getPixelRatio()) / (2 * Math.tan((this.b.camera.fov * Math.PI) / 360)); this.viewH = h; }

  setup(desc) {
    this.desc = desc;
    this.mapPop = (desc.populations || []).find((p) => p.region === 'map' || /^map/.test(p.name)) || null;
    this.composed = !desc.placeholder;
    // neuron index -> drawn point, for flashes at given units
    const pairs = [];
    for (const r of this.b.regions) for (let i = 0; i < r.count; i++) if (r.neuron[i] >= 0) pairs.push([r.neuron[i], r.start + i]);
    pairs.sort((x, y) => x[0] - y[0]);
    this.unitN = Int32Array.from(pairs.map((p) => p[0])); this.unitP = Int32Array.from(pairs.map((p) => p[1]));
    this.setStatus('map', this.mapPop ? `live: ${this.mapPop.size.toLocaleString('en')} place cells` : null);
    this.drawMap();
  }
  setStatus(id, text) { this.status[id] = text; this.b.partStatus(id, text); }

  /** The drawn point nearest a neuron of the running brain. */
  pointOf(unit) {
    const N = this.unitN; if (!N || !N.length) return -1;
    let lo = 0, hi = N.length - 1;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (N[mid] < unit) lo = mid + 1; else hi = mid; }
    if (lo > 0 && Math.abs(N[lo - 1] - unit) < Math.abs(N[lo] - unit)) lo -= 1;
    return Math.abs(N[lo] - unit) <= 64 ? this.unitP[lo] : -1;
  }

  // --- each moment ------------------------------------------------------------------------------
  moment(reply, activity) {
    const vt = this.b.clock.vt, viz = reply.viz || {};
    if (this.b.clock.paused) { // the picture holds; the latest state waits for the play
      this.held = { reply, activity, memory: reply.memory || this.held?.memory || null };
      return;
    }
    if (this.held) { const h = this.held; this.held = null; if (h.memory && !reply.memory) this.memory(h.memory, null, vt, false); }
    const animate = true;
    // the memory: the records, their links, the read and the write
    const mem = reply.memory;
    if (mem) this.memory(mem, viz.memory, vt, animate);
    if (viz.memory?.slots) this.vizSlots(viz.memory, vt);
    // a word stored: from the ear to its slot
    const stored = viz.words?.stored || (reply.heard_sound ? { slot: reply.heard_sound.slot, revised: !!mem?.write?.revised } : null);
    if (stored && stored.slot != null && this.b.scanMode && !stored.revised) { // the scan: a sound it does not know lights the ear and Field L only
      this.flashes.push({ region: 'ear', t0: vt, level: 0.8 }); this.flashes.push({ region: 'fieldl', t0: vt + 0.08, level: 0.7 });
    } else if (stored && stored.slot != null) {
      this.packets.push({ path: ['fieldl', 'ncm', `slot:${stored.slot}`], t0: vt, dur: 1.6, colour: this.cHear, slot: stored.slot });
      this.note(`slot:${stored.slot}`, stored.revised ? 'told again' : 'a new record', vt + 1.3, 2.2);
      const s = this.slots.get(stored.slot); if (s) s.arrive = vt + 1.45;
      this.setStatus('stored', 'live');
    }
    // the heads: the read with the heard sound as its cue, or the host's several heads
    const heads = viz.memory?.heads || (reply.heard_sound && mem?.read?.slots?.length ? [{ cue: 'the sound just heard', from: 'ncm', weights: mem.read.slots.map((s, k) => [s, mem.read.weights[k]]) }] : null);
    if (heads) {
      heads.forEach((h, i) => { for (const [slot, w] of h.weights || []) if (w > 0.02) this.beams.push({ from: h.from || 'heads', slot, w, head: i, t0: vt + 0.6, dur: 2.2 }); });
      this.setStatus('heads', `live: ${heads.length} head${heads.length === 1 ? '' : 's'}`);
    }
    // a word said: from its slot to the voice; a call or a babble from the vocal core
    const call = viz.words?.attempt || (reply.said && typeof reply.said === 'object' ? reply.said : reply.said_sound);
    if (call) {
      const slot = call.slot ?? (typeof call.id === 'string' && call.id.startsWith('you-') ? Number(call.id.slice(4)) : null);
      if (slot != null && this.slots.has(slot)) {
        this.packets.push({ path: [`slot:${slot}`, 'vocal', 'voice'], t0: vt, dur: 1.4, colour: this.cSay, slot });
        if (call.match != null) this.note('voice', `said it, ${Math.round(call.match * 100)} % like the word`, vt + 1.2, 2.6);
        this.setStatus('saying', 'live');
      } else this.packets.push({ path: ['vocal', 'voice'], t0: vt, dur: 0.9, colour: this.cSay });
    }
    // surprise: a sudden sound, a thing that appears or moves, or the host's units
    if (!this.status.surprise && 'startle' in reply) this.setStatus('surprise', 'live: a sudden sound');
    if (reply.startle) { this.flashes.push({ region: 'ear', t0: vt, level: 1 }); this.flashes.push({ region: 'tectum', t0: vt + 0.08, level: 0.7 }); this.note('ear', 'a sudden sound', vt, 1.8); }
    const f = reply.focus;
    const why = f?.why;
    if (!this.status.surprise && (why === 'appeared' || why === 'moved') && !this.b.scanMode) this.setStatus('surprise', 'live: what appears or moves');
    // a surprise is shown once its reason has held for two moments (a one-moment flicker of the focus's
    // reason is not shown)
    const surprising = f && (why === 'appeared' || why === 'moved');
    this.surpriseRun = surprising && this.surpriseWhy === why ? (this.surpriseRun || 0) + 1 : surprising ? 1 : 0;
    this.surpriseWhy = surprising ? why : null;
    if (surprising && this.surpriseRun === 2 && !this.b.scanMode) { // (the scan shows no surprise: on the page the body's focus reports a still thing as moved)
      this.flashes.push({ region: 'tectum', t0: vt, level: 0.9 }); this.note('tectum', why === 'appeared' ? 'surprise: it appeared' : 'surprise: it moved', vt, 1.6);
    }
    for (const [unit, level] of viz.surprise?.units || []) this.flashes.push({ unit, t0: vt, level: Math.min(1, (level - 1) / 2) });
    if (viz.surprise) this.setStatus('surprise', 'live');
    if (viz.words?.segment?.on) this.flashes.push({ region: 'fieldl', t0: vt, level: 0.3 }); // a sound being heard
    this.focus = f && f.place ? { place: f.place, why, kind: f.kind } : viz.surprise?.focus?.place ? viz.surprise.focus : null;
    // the map: the things it holds, the head's heading, the place cells
    if (viz.map?.things || reply.things) this.mapThings = viz.map?.things || reply.things;
    if (viz.map?.pose?.heading != null) this.heading = viz.map.pose.heading;
    else if (reply.arrays?.angles?.length) this.heading = reply.arrays.angles[0];
    else if (window.parrotPage?.parrot) this.heading = window.parrotPage.parrot.joints.get('head_yaw');
    this.activity = activity;
    this.drawMap();
    // the neuromodulators
    const dop = viz.modulators?.dopamine || (typeof reply.vta === 'number' && (reply.vta !== 0 || reply.reward) ? { level: reply.vta, why: reply.reward ? 'pistachio' : 'prediction', paid: reply.paid } : null);
    if (typeof reply.vta === 'number' || viz.modulators?.dopamine) this.setStatus('dopamine', 'live');
    for (const [name, m] of [['dopamine', dop], ['noradrenaline', viz.modulators?.noradrenaline], ['acetylcholine', viz.modulators?.acetylcholine]]) {
      if (viz.modulators?.[name]) this.setStatus(name, 'live');
      if (!m || !(Math.abs(m.level) > 0.05)) continue;
      if (this.b.scanMode && name !== 'dopamine') continue; // the scan keeps one colour family: only dopamine washes it
      const paid = (m.paid || []).map((p) => [PAID_AREAS[p.from] || p.from, PAID_AREAS[p.to] || p.to, p.change]).filter((p) => this.b.byId[p[0]] && this.b.byId[p[1]]);
      this.washes.push({ name, level: Math.max(-1, Math.min(1, m.level)), targets: m.targets || MOD[name].to, from: MOD[name].from, t0: vt, paid });
    }
    // the settle: each region's residual through the moment's sweeps
    // a settle plays out over 0.1 s of the view's clock; one arriving while another plays waits its turn
    // (at ten times slower the view shows about one moment's settle in ten, each whole)
    if (viz.settle?.regions && (!this.settle || vt - this.settle.t0 >= 0.1)) { this.settle = { ...viz.settle, t0: vt }; this.setStatus('repairs', 'live'); this.scaleSettle(); }
  }

  focusPlaceChanged(f) { const a = this.focus?.place, b = f.place; return !a || !b || Math.hypot(a[0] - b[0], a[1] - b[1]) > 0.05; }

  memory(mem, vmem, vt, animate) {
    if (mem.level) this.level = mem.level;
    if (mem.things) this.things = mem.things;
    const seen = new Set();
    let dirty = false;
    for (const r of mem.records || []) {
      seen.add(r.slot);
      let s = this.slots.get(r.slot);
      if (!s) { s = { slot: r.slot, born: animate ? vt : -10, flash: -10, size: 0 }; this.slots.set(r.slot, s); dirty = true; }
      else if (r.deep > s.deep + 0.5 && animate) s.flash = vt;
      if (JSON.stringify(r.thumb) !== s.thumbKey) { s.thumb = r.thumb; s.thumbKey = JSON.stringify(r.thumb); dirty = true; }
      Object.assign(s, { deep: r.deep, faded: r.faded, heard: r.heard, match: r.match, links: (r.slow || []).map((v, k) => Math.max(0, v + (r.fast?.[k] || 0))) });
    }
    for (const slot of [...this.slots.keys()]) if (!seen.has(slot)) { this.slots.delete(slot); dirty = true; }
    const n = this.slots.size;
    if (n) { this.b.markLive('records', `${n} record${n === 1 ? '' : 's'} of sounds`); this.b.markLive('words', 'the links from each sound to the things'); }
    this.setStatus('slots', `live: ${n} record${n === 1 ? '' : 's'}`);
    this.setStatus('links', 'live');
    // the hearing layer keeps, reads and says its records: those parts are this brain's
    this.setStatus('stored', 'live'); this.setStatus('saying', 'live');
    if (!this.status.heads) this.setStatus('heads', 'live: 1 head');
    if (dirty) this.drawAtlas();
    void vmem;
  }

  /** The host's own record slots (viz.memory.slots: id, kind, depth, faded, kept), when it sends them. */
  vizSlots(vm, vt) {
    const seen = new Set();
    for (const r of vm.slots) {
      seen.add(r.id);
      let s = this.slots.get(r.id);
      if (!s) { s = { slot: r.id, born: vt, flash: -10, size: 0 }; this.slots.set(r.id, s); }
      Object.assign(s, { deep: r.depth, faded: (r.faded || 0) * 600, kind: r.kind, kept: !!r.kept });
    }
    for (const e of vm.events || []) { const s = this.slots.get(e.slot); if (s && (e.what === 'revise' || e.what === 'kept')) s.flash = vt; }
    this.setStatus('slots', `live: ${this.slots.size} records`);
  }

  drawAtlas() {
    const g = this.atlasCanvas.getContext('2d');
    g.fillStyle = '#000'; g.fillRect(0, 0, 256, 192);
    let k = 0;
    for (const s of [...this.slots.values()].sort((a, b) => a.slot - b.slot)) {
      s.cell = k; k += 1;
      const t = s.thumb; if (!t || !t.length) continue;
      const frames = Math.max(1, Math.round(t.length / 20)), cx = (s.cell % 8) * 32, cy = Math.floor(s.cell / 8) * 32;
      const img = g.createImageData(frames, 20);
      for (let x = 0; x < frames; x++) for (let y = 0; y < 20; y++) { const v = t[x * 20 + (19 - y)], j = 4 * (y * frames + x); img.data[j] = img.data[j + 1] = img.data[j + 2] = v; img.data[j + 3] = 255; }
      const tmp = this._thumb ||= document.createElement('canvas'); tmp.width = frames; tmp.height = 20;
      tmp.getContext('2d').putImageData(img, 0, 0);
      g.imageSmoothingEnabled = true; g.drawImage(tmp, cx, cy, 32, 32);
    }
    this.atlas.needsUpdate = true;
  }

  reward() {
    const vt = this.b.clock.vt;
    this.pistachioAt = vt;
    this.flashes.push({ region: 'vta', t0: vt, level: 0.8, colour: this.cGold });
    this.note('vta', this.status.dopamine ? 'a pistachio' : 'a pistachio (no dopamine in this brain yet)', vt, 2.4);
  }

  note(at, text, t0, dur) {
    const n = this.notes.find((x) => x.at === at) || (this.notes.length < 4 ? (this.notes.push({}), this.notes[this.notes.length - 1]) : this.notes.reduce((a, b) => (a.t0 < b.t0 ? a : b)));
    Object.assign(n, { at, text, t0, dur });
  }

  scaleSettle() {
    const s = this.settle; let rm = 1e-9, tm = 1e-9;
    for (const v of Object.values(s.regions)) for (const x of v) rm = Math.max(rm, x);
    for (const t of s.tracts || []) for (let i = 1; i < t.carried.length; i++) tm = Math.max(tm, Math.abs(t.carried[i] - t.carried[i - 1]));
    this.rScale = Math.max(rm, (this.rScale || 0) * 0.97); this.tScale = Math.max(tm, (this.tScale || 0) * 0.97);
    s.byPair = new Map((s.tracts || []).map((t) => [`${t.from}>${t.to}`, t.carried]));
  }
  /** Where the settle is in its sweeps (0 to frames - 1), or -1 when it is over. */
  settlePhase(vt, delay = 0) {
    const s = this.settle; if (!s) return -1;
    const x = (vt - s.t0 - delay) / 0.1; if (x < 0 || x > 1.6) return -1;
    return Math.min(1, x) * ((s.frames || s.regions[Object.keys(s.regions)[0]].length) - 1);
  }
  static at(arr, phi) { const i = Math.floor(phi), u = phi - i; return i + 1 < arr.length ? arr[i] + (arr[i + 1] - arr[i]) * u : arr[arr.length - 1]; }

  /** Extra light on a tract: dopamine paying it, or the settle's corrections along it. */
  tractBoost(t) {
    let x = 0;
    for (const w of this.washes) {
      if (w.name !== 'dopamine' || w.level <= 0) continue;
      for (const [a, b] of w.paid) if ((t.a === a && t.b === b) || (t.a === b && t.b === a)) x += 0.7 * env(this.b.clock.vt - w.t0 - 0.6, 0.3, 1.6) * w.level;
    }
    const carried = this.settle?.byPair?.get(`${t.a}>${t.b}`);
    if (carried) { const phi = this.settlePhase(this.b.clock.vt, 0.02); if (phi >= 0) { const i = Math.max(1, Math.round(phi)); x += 0.8 * Math.abs(carried[Math.min(i, carried.length - 1)] - carried[i - 1]) / this.tScale; } }
    return x;
  }

  // --- each frame ----------------------------------------------------------------------------------
  /** One effect point (a disc, a ring or a dot with a halo). */
  put(p, col, size, alpha, shape = 0) {
    const n = this.nFx; if (n >= FX_CAP) return;
    this.fxPos[3 * n] = p.x; this.fxPos[3 * n + 1] = p.y; this.fxPos[3 * n + 2] = p.z;
    this.fxCol[3 * n] = col.r; this.fxCol[3 * n + 1] = col.g; this.fxCol[3 * n + 2] = col.b;
    this.fxSize[n] = size; this.fxAlpha[n] = alpha; this.fxShape[n] = shape; this.nFx = n + 1;
  }
  /** One line segment, its two ends' colours. */
  seg(p, q, cp, cq) {
    const L = this.nLines; if (L * 6 >= this.linePos.length) return;
    const k = L * 6;
    this.linePos[k] = p.x; this.linePos[k + 1] = p.y; this.linePos[k + 2] = p.z; this.linePos[k + 3] = q.x; this.linePos[k + 4] = q.y; this.linePos[k + 5] = q.z;
    this.lineCol[k] = cp.r; this.lineCol[k + 1] = cp.g; this.lineCol[k + 2] = cp.b; this.lineCol[k + 3] = cq.r; this.lineCol[k + 4] = cq.g; this.lineCol[k + 5] = cq.b;
    this.nLines = L + 1;
  }

  /** A named place in the 3D view: a region's centre (its left side), or `slot:<n>`. */
  where(name, out) {
    if (name.startsWith('slot:')) { const s = this.slots.get(Number(name.slice(5))); return s?.pos ? out.copy(s.pos) : this.b.centre('records', 0, out); }
    if (name === 'map') return out.copy(this.mapSprite.position).addScaledVector(this.upV, -0.5 * this.mapSprite.scale.y); // the map card's lower edge
    return this.b.centre(name, 1, out);
  }

  frame(vdt, vt) {
    const b = this.b, cam = b.camera;
    cam.updateMatrixWorld();
    const right = this.tmp[0].setFromMatrixColumn(cam.matrixWorld, 0), up = this.tmp[1].setFromMatrixColumn(cam.matrixWorld, 1);
    this.upV = up;
    this.nFx = 0; this.nLines = 0;
    const P = this.tmp[2], Q = this.tmp[3], C1 = this._c1 ||= new THREE.Color(), C2 = this._c2 ||= new THREE.Color();
    const pathOn = b.path, words = pathOn === 'words', sounds = pathOn === 'sounds', saying = pathOn === 'saying';
    const dimAll = pathOn && !(words || sounds || saying) ? 0.3 : 1;

    // the record slots: a ring facing the viewer, at the records
    const ring = b.centre('records', 0, this._ring ||= new THREE.Vector3());
    if (b.scanMode) { ring.copy(b.controls.target).project(cam); ring.x = -0.17; ring.y = -0.42; ring.unproject(cam); } // the scan: the records as a small grid low in the view, clear of the concept tags and the chat
    const list = this._list ||= []; list.length = 0;
    for (const s of this.slots.values()) list.push(s);
    list.sort((a, c) => a.slot - c.slot);
    const count = list.length, radius = 0.5 + Math.min(0.3, count * 0.012), step = (2 * Math.PI) / Math.max(count, 6);
    for (let i = 0; i < 48; i++) this.slotAlpha[i] = 0;
    list.forEach((s, i) => {
      if (i >= 48) return;
      const ang = -2.4 + i * step; // the first record low on the ring, clear of the region's name
      s.pos ||= new THREE.Vector3();
      if (b.scanMode) s.pos.copy(ring).addScaledVector(right, ((i % 12) - 5.5) * 0.085).addScaledVector(up, -Math.floor(i / 12) * 0.085);
      else s.pos.copy(ring).addScaledVector(right, Math.cos(ang) * radius).addScaledVector(up, Math.sin(ang) * radius);
      const grow = Math.min(1, Math.log1p(s.deep || 0) / Math.log1p(this.level * 4));
      let size = b.scanMode ? 0.05 + 0.028 * grow : 0.16 + 0.22 * grow;
      const born = vt - s.born; if (born < 0.5) size *= ease(born / 0.35) * (1 + 0.4 * Math.max(0, 1 - born / 0.5));
      const fl = env(vt - s.flash, 0.05, 0.6), arrive = s.arrive != null ? env(vt - s.arrive, 0.05, 0.7) : 0;
      size *= 1 + 0.35 * Math.max(fl, arrive);
      const faded = (s.faded || 0) / ((s.faded || 0) + 600);
      this.slotPos[3 * i] = s.pos.x; this.slotPos[3 * i + 1] = s.pos.y; this.slotPos[3 * i + 2] = s.pos.z;
      const c = s.kind === 'place' ? b.byId.map.base : s.kind === 'thing' ? this.cThing : this.cHear;
      this.slotCol[3 * i] = c.r; this.slotCol[3 * i + 1] = c.g; this.slotCol[3 * i + 2] = c.b;
      this.slotSize[i] = size; this.slotAlpha[i] = Math.max(0.25, 1 - faded) * (pathOn && !(words || sounds || saying) ? 0.35 : 1);
      this.slotCell[2 * i] = (s.cell ?? i) % 8; this.slotCell[2 * i + 1] = Math.floor((s.cell ?? i) / 8);
      this.slotRim[i] = s.kept || (s.deep || 0) >= this.level ? 1 : 0; this.slotHot[i] = 0.7 * Math.max(fl, arrive);
    });
    for (const name of ['position', 'acol', 'size', 'alpha', 'cell', 'rim', 'hot']) this.slotPoints.geometry.attributes[name].needsUpdate = true;
    // the ring's own faint circle, so an empty memory reads as a place
    const rc = C1.copy(this.cHear).multiplyScalar(count ? 0.16 : 0.08);
    for (let k = 0; k < (b.scanMode ? 0 : 40); k++) { // (the scan's grid has no circle)
      const a0 = (k / 40) * 2 * Math.PI, a1 = ((k + 1) / 40) * 2 * Math.PI;
      P.copy(ring).addScaledVector(right, Math.cos(a0) * radius).addScaledVector(up, Math.sin(a0) * radius);
      Q.copy(ring).addScaledVector(right, Math.cos(a1) * radius).addScaledVector(up, Math.sin(a1) * radius);
      this.seg(P, Q, rc, rc);
    }

    // the thing units in Words: one a kind of thing, the one in focus lit
    const wc = b.centre('words', 0, this._w ||= new THREE.Vector3());
    const focusKind = this.focusKind();
    const thingPos = this._tp ||= [];
    const T = this.things.length || 8;
    for (let k = 0; k < T; k++) {
      const p = thingPos[k] ||= new THREE.Vector3();
      p.copy(wc).addScaledVector(right, (k - (T - 1) / 2) * 0.17).addScaledVector(up, -0.02 * ((k % 2) * 2 - 1));
      const lit = this.things[k] && this.things[k] === focusKind;
      const has = this.things.length > 0;
      this.put(p, lit ? this.cFocus : this.cThing, lit ? 0.28 : 0.15, (has ? (lit ? 1 : 0.45) : 0.12) * (words || !pathOn ? 1 : dimAll), lit ? 2 : 0);
    }
    if (focusKind && this.things.includes(focusKind)) {
      const k = this.things.indexOf(focusKind); this.thingAt = thingPos[k]; this.thingText = window.parrotPage?.label?.(focusKind) || focusKind;
    } else this.thingAt = null;

    // word links: each record to each thing it names, as bright as the link
    for (const s of list) {
      if (!s.links || !s.pos) continue;
      for (let k = 0; k < s.links.length && k < T; k++) {
        const v = Math.min(1, s.links[k] / 0.4); if (v < 0.04) continue;
        const lit = this.things[k] === focusKind, bright = (0.25 + 0.75 * v) * (lit ? 1.3 : 0.8) * (words ? 1.4 : pathOn ? 0.3 : 1);
        C1.copy(this.cLink).multiplyScalar(bright); C2.copy(this.cThing).multiplyScalar(bright);
        this.seg(s.pos, thingPos[k], C1, C2);
        // a bead travels along a link that is strengthening
        if (lit && v > 0.04) { const u = (vt * 0.7 + s.slot * 0.13) % 1; P.copy(s.pos).lerp(thingPos[k], u); this.put(P, this.cLink, 0.07 + 0.08 * v, 0.9 * bright); }
      }
    }

    // the map card's tether to the hippocampus
    const hc = b.centre('map', 0, this._hc ||= new THREE.Vector3());
    C1.copy(b.byId.map.base).multiplyScalar(this.mapPop ? 0.5 : 0.15); C2.copy(C1).multiplyScalar(0.4);
    if (this.mapSprite.visible) { P.copy(this.mapSprite.position).addScaledVector(up, -this.mapSprite.scale.y / 2); this.seg(hc, P, C1, C2); }
    // a lit path: light flowing from step to step, each step named
    const lit = pathOn ? PATHS.find((x) => x.id === pathOn) : null;
    if (lit) {
      const col = this._pc ||= new THREE.Color(); col.set(lit.colour);
      for (let j = 0; j < 36; j++) { const u = (j / 36 + vt * 0.12) % 1; this.along(lit.via, u, P); this.put(P, col, 0.13, 0.95 * Math.sin(Math.PI * ((j / 36 + vt * 0.12 * 3) % 1)) ** 2 + 0.25); }
      lit.via.forEach((id, i) => { const el = this.stepEls[i]; if (!el) return; el.style.setProperty('--pc', lit.colour); this.stepText[i] = `${i + 1}. ${SHORT[id] || id}: ${lit.steps[i]}`; this.stepAt[i] = id; });
      for (let i = lit.via.length; i < 4; i++) this.stepAt[i] = null;
    } else this.stepAt.fill(null);
    // the focus: a line from the tectum (the side that sees it) to the thing on the map
    if (this.focus?.place && this.mapPop && this.mapSprite.visible) { // (the scan view has no map card: no tether to it)
      const [x, z] = this.focus.place;
      this.mapPoint(x, z, right, up, P);
      const side = Math.atan2(x, z) - (this.heading * Math.PI) / 180 > 0 ? -1 : 1; // a thing to the left is seen by the left eye, which feeds the right tectum
      b.centre('tectum', side, Q);
      C1.copy(this.cFocus).multiplyScalar(0.5); C2.copy(this.cFocus);
      this.seg(Q, P, C1, C2);
      this.put(P, this.cFocus, 0.2, 0.9, 1);
    }

    // packets: a word stored, a word said
    for (let i = this.packets.length - 1; i >= 0; i--) {
      const k = this.packets[i], age = vt - k.t0;
      if (age > k.dur + 0.3) { this.packets.splice(i, 1); continue; }
      for (let tr = 0; tr < 7; tr++) {
        const u = (age - tr * 0.035) / k.dur; if (u < 0 || u > 1) continue;
        this.along(k.path, u, P);
        this.put(P, tr ? k.colour : this.cWhite, tr ? 0.16 * (1 - tr / 8) : 0.2, tr ? 0.75 * (1 - tr / 7) : 1);
      }
    }
    // beams: a head's attention from its cue to the records it read
    for (let i = this.beams.length - 1; i >= 0; i--) {
      const m = this.beams[i], age = vt - m.t0;
      if (age > m.dur) { this.beams.splice(i, 1); continue; }
      if (age < 0) continue;
      const s = this.slots.get(m.slot); if (!s?.pos) continue;
      b.centre(m.from, 1, Q);
      const e = env(age, 0.25, m.dur - 0.25), col = this.headColour[m.head % 4];
      for (let j = 0; j < 6; j++) {
        const u = ((age * 0.8 + j / 6) % 1);
        P.copy(Q).lerp(s.pos, u); P.y += Math.sin(u * Math.PI) * 0.15;
        this.put(P, col, 0.05 + 0.16 * Math.sqrt(m.w), 0.85 * e);
      }
    }
    // washes: a neuromodulator from its nucleus along its fibres; each target tinted as it arrives
    const tint = b.tint; tint.fill(0);
    for (let i = this.washes.length - 1; i >= 0; i--) {
      const w = this.washes[i], age = vt - w.t0;
      if (age > 2.8) { this.washes.splice(i, 1); continue; }
      const col = this.modColour[w.name], dip = w.level < 0, amp = Math.abs(w.level);
      b.centre(w.from, 1, Q);
      this.put(Q, col, 0.35 + 0.3 * amp, (dip ? 0.25 : 0.9) * env(age, 0.1, 1.2), dip ? 1 : 0);
      for (const [to, wt] of Object.entries(w.targets)) {
        const r = b.byId[to]; if (!r) continue;
        b.centre(to, 1, P);
        const travel = 0.35 + 0.12 * Q.distanceTo(P);
        for (let j = 0; j < 5; j++) {
          const u = (age - j * 0.06) / travel; if (u < 0 || u > 1) continue;
          const X = this._x ||= new THREE.Vector3(); X.copy(Q).lerp(P, ease(u)); X.y += Math.sin(u * Math.PI) * 0.25;
          this.put(X, col, (0.09 + 0.06 * wt) * (dip ? 0.6 : 1), 0.8 * amp * (1 - j / 6) * (dip ? 0.4 : 1));
        }
        const e = env(age - travel, 0.15, 1.6) * amp * wt * (dip ? -0.35 : 0.55), k4 = 4 * r.index;
        if (e !== 0) { tint[k4] += col.r; tint[k4 + 1] += col.g; tint[k4 + 2] += col.b; tint[k4 + 3] = Math.max(-0.2, tint[k4 + 3] + e); }
      }
    }
    // surprise and the pistachio: flashes on the neurons where they arise
    const flash = b.flash; flash.fill(0);
    for (let i = this.flashes.length - 1; i >= 0; i--) {
      const f = this.flashes[i], age = vt - f.t0;
      if (age > 0.9) { this.flashes.splice(i, 1); continue; }
      const e = env(age, 0.03, 0.8) * f.level;
      if (f.unit != null) { const p = this.pointOf(f.unit); if (p >= 0) flash[p] = Math.max(flash[p], e * 1.2); continue; }
      const r = b.byId[f.region]; if (!r) continue;
      for (let j = 0; j < r.count; j++) flash[r.start + j] = Math.max(flash[r.start + j], e * 0.9);
      b.centre(f.region, f.region === 'vta' ? 0 : 1, P);
      this.put(P, f.colour || this.cWarm, 0.25 + 0.5 * ease(age / 0.5), (1 - age / 0.9) * f.level, 1);
    }
    // the settle: each region glows with what it has left to repair, and settles out
    const phi = this.settlePhase(vt);
    if (phi >= 0 || (this.settle && vt - this.settle.t0 < 0.4)) {
      const ph = phi >= 0 ? phi : (this.settle.frames || 2) - 1, fade = phi >= 0 ? 1 : Math.max(0, 1 - (vt - this.settle.t0 - 0.16) / 0.24);
      for (const [id, arr] of Object.entries(this.settle.regions)) {
        const r = b.byId[id]; if (!r) continue;
        const v = (Live.at(arr, ph) / this.rScale) * fade * 0.8;
        for (let j = 0; j < r.count; j++) flash[r.start + j] = Math.max(flash[r.start + j], v);
      }
    }

    // finish the buffers
    const n = this.nFx, L = this.nLines;
    for (let i = n; i < FX_CAP; i++) this.fxAlpha[i] = 0;
    const ga = this.fx.geometry.attributes;
    ga.position.needsUpdate = ga.acol.needsUpdate = ga.size.needsUpdate = ga.alpha.needsUpdate = ga.shape.needsUpdate = true;
    for (let i = L * 6; i < this.lineUsed * 6; i++) { this.linePos[i] = 0; this.lineCol[i] = 0; }
    this.lineUsed = L;
    this.lines.geometry.attributes.position.needsUpdate = this.lines.geometry.attributes.color.needsUpdate = true;
    this.lines.geometry.setDrawRange(0, L * 2);
    this.mapSprite.material.opacity = (this.mapPop ? 0.95 : 0.35) * (pathOn && pathOn !== 'images' ? 0.3 : 1);
    this.placeNotes(vt);
  }

  /** The thing in focus, by its kind's name (the page's room names the thing the focus lies on). */
  focusKind() {
    const pg = window.parrotPage, id = pg?.state?.focus?.id;
    return id ? pg.room.things.get(id)?.kind || null : null;
  }

  /** A point along a path of named places, u from 0 to 1, each leg eased. */
  along(path, u, out) {
    const legs = path.length - 1, x = Math.min(legs - 1e-6, u * legs), i = Math.floor(x), f = ease(x - i);
    const A = this.where(path[i], this._a ||= new THREE.Vector3()), B = this.where(path[i + 1], this._b ||= new THREE.Vector3());
    out.copy(A).lerp(B, f); out.y += Math.sin(f * Math.PI) * 0.18;
    return out;
  }

  /** A place on the table (x, z in metres) as a point on the map card in the hippocampus. */
  mapPoint(x, z, right, up, out) {
    const sp = this.mapSprite, u = 0.5 + (x / TABLE.x) * 0.5 * (216 / 232), v = (8 + 18 + (z + TABLE.z) / (2 * TABLE.z) * 148) / 176;
    return out.copy(sp.position).addScaledVector(right, (u - 0.5) * sp.scale.x).addScaledVector(up, (0.5 - v) * sp.scale.y);
  }

  /** The map card: the hippocampus's place cells, the things it holds, the head and its fields. */
  drawMap() {
    const c = this.mapCanvas, g = c.getContext('2d'), W = c.width, H = c.height, ox = 8, oy = 26, mw = 216, mh = 148;
    g.clearRect(0, 0, W, H);
    g.fillStyle = 'rgba(8,20,22,0.88)'; g.strokeStyle = this.mapPop ? 'rgba(63,214,194,0.7)' : 'rgba(108,117,131,0.6)'; g.lineWidth = 2;
    g.beginPath(); g.roundRect(1, 1, W - 2, H - 2, 10); g.fill(); g.stroke();
    g.font = '600 15px "IBM Plex Mono", monospace'; g.fillStyle = this.mapPop ? '#3fd6c2' : '#6c7583';
    g.fillText('map of things', 10, 18);
    if (!this.mapPop) { g.font = '500 14px "IBM Plex Mono", monospace'; g.fillText('not in this brain yet', 10, 96); this.mapTex.needsUpdate = true; return; }
    // the place cells, 54 by 37 over the table (x to the parrot's left drawn right, the beak's way down)
    const a = this.activity, p = this.mapPop;
    if (a && p.size === 54 * 37) {
      const sg = this.mapSheet.getContext('2d'), img = this._img ||= sg.createImageData(54, 37);
      for (let ix = 0; ix < 54; ix++) for (let iz = 0; iz < 37; iz++) {
        const v = Math.max(0, Math.min(1, a[p.start + ix * 37 + iz] || 0)), j = 4 * (iz * 54 + ix);
        img.data[j] = 20 + 43 * v; img.data[j + 1] = 40 + 174 * v; img.data[j + 2] = 44 + 150 * v; img.data[j + 3] = 255;
      }
      sg.putImageData(img, 0, 0);
      g.imageSmoothingEnabled = true; g.drawImage(this.mapSheet, ox, oy, mw, mh);
    } else { g.fillStyle = '#10272a'; g.fillRect(ox, oy, mw, mh); }
    const sx = (x) => ox + (x / TABLE.x * 0.5 + 0.5) * mw, sz = (z) => oy + (z / TABLE.z * 0.5 + 0.5) * mh;
    const cx = sx(0), cz = sz(0), Rr = 64, yaw = (this.heading * Math.PI) / 180, dir = (h) => Math.PI / 2 - h;
    const f = (EYE.field * Math.PI) / 180, ax = (EYE.axis * Math.PI) / 180;
    for (const [side, col] of [[1, 'rgba(79,195,247,0.16)'], [-1, 'rgba(242,179,61,0.16)']]) {
      const mid = yaw + side * ax; g.beginPath(); g.moveTo(cx, cz); g.arc(cx, cz, Rr, dir(mid + f), dir(mid - f), false); g.closePath(); g.fillStyle = col; g.fill();
    }
    g.fillStyle = '#e8ebf0'; g.beginPath(); g.arc(cx, cz, 4, 0, 7); g.fill();
    g.strokeStyle = '#e8ebf0'; g.lineWidth = 2; g.beginPath(); g.moveTo(cx, cz); g.lineTo(cx + Math.cos(dir(yaw)) * 14, cz + Math.sin(dir(yaw)) * 14); g.stroke();
    for (const t of this.mapThings || []) {
      if (!t.place) continue;
      const x = sx(t.place[0]), z = sz(t.place[1]), held = t.state && t.state !== 'seen' && t.seen !== true;
      if (t.forecast) { g.strokeStyle = 'rgba(232,235,240,0.35)'; g.setLineDash([3, 3]); g.beginPath(); g.moveTo(x, z); g.lineTo(sx(t.forecast[0]), sz(t.forecast[1])); g.stroke(); g.setLineDash([]); g.fillStyle = 'rgba(232,235,240,0.3)'; g.beginPath(); g.arc(sx(t.forecast[0]), sz(t.forecast[1]), 4, 0, 7); g.fill(); }
      if (held) { g.strokeStyle = '#9aa3b0'; g.lineWidth = 2; g.beginPath(); g.arc(x, z, 4.5, 0, 7); g.stroke(); }
      else { g.fillStyle = '#ffffff'; g.beginPath(); g.arc(x, z, 4.5, 0, 7); g.fill(); }
    }
    for (const [x, z, st] of this.focus?.returned || []) { g.strokeStyle = `rgba(242,179,61,${0.15 + 0.3 * (st ?? 0.5)})`; g.lineWidth = 1.5; g.beginPath(); g.arc(sx(x), sz(z), 7, 0, 7); g.stroke(); } // inhibition of return
    if (this.focus?.place) { g.strokeStyle = '#f2b33d'; g.lineWidth = 2.5; g.beginPath(); g.arc(sx(this.focus.place[0]), sz(this.focus.place[1]), 9, 0, 7); g.stroke(); }
    this.mapTex.needsUpdate = true;
  }

  placeNotes(vt) {
    const w = this.b.canvas.clientWidth, h = this.b.canvas.clientHeight, v = this._nv ||= new THREE.Vector3();
    const show = (el, p, text, dy = -14) => {
      v.copy(p).project(this.b.camera);
      if (v.z > 1) { el.hidden = true; return; }
      const x = Math.round((v.x + 1) / 2 * w), y = Math.round((1 - v.y) / 2 * h) + dy;
      el.hidden = false; if (el.textContent !== text) el.textContent = text;
      el.style.transform = `translate(${x}px, ${y}px) translate(-50%, -100%)`;
    };
    this.notes.forEach((n, i) => {
      const el = this.noteEls[i], age = vt - n.t0;
      if (age < 0 || age > n.dur) { el.hidden = true; return; }
      show(el, this.where(n.at, this._np ||= new THREE.Vector3()), n.text);
      el.style.opacity = String(Math.min(1, 4 * (1 - age / n.dur)));
    });
    if (this.thingAt) show(this.thingEl, this.thingAt, `${this.thingText}: in focus`, -8); else this.thingEl.hidden = true;
    this.stepEls.forEach((el, i) => { if (!this.stepAt[i]) { el.hidden = true; return; } show(el, this.where(this.stepAt[i], this._sp ||= new THREE.Vector3()), this.stepText[i], 18); });
  }
}
