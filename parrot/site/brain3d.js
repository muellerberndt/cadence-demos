// The brain in 3D, beside the parrot: the planned parrot brain as a bird's brain (atlas.js: its
// regions where they sit in a bird's head, the tracts between them), filled with the running
// brain. Every population the brain host names joins its atlas region by its name; there each
// neuron is a point that glows with its activity at each moment, and the tracts out of it carry a
// flow toward their target, brighter the more the source is active. Regions the running brain does
// not have are drawn faint and say "not in this brain yet". Every region's name carries a question
// mark: what it is in a bird and what it does in this brain.
//
// "How it connects" (atlas PATHS) lights the path of each kind of memory: images of things, sounds,
// words and saying. The live layer (brainlive.js) draws what the host reports each moment: the
// record slots, the links from a sound to a thing, a word stored and a word said, the map of
// things, the focus, surprise and the neuromodulators. The view's clock can pause and run ten
// times slower; the brain itself runs on.
//
// Draw calls: the outline shells, one cloud of every neuron, one set of every tract, and the live
// layer's few. Nothing is allocated per frame.
import * as THREE from 'three';
import { OrbitControls } from './vendor/three/jsm/controls/OrbitControls.js';
import { R, T, STN, SHORT, hueOf, PATHS } from './atlas.js';
import { Live, PARTS } from './brainlive.js';
import { Scan, LUT } from './brainscan.js';

// Which atlas region a population of the running brain belongs to, by its region, then its name,
// then its title (the first region whose rule matches).
const MATCH = [
  ['retina', /retina/i], ['tectum', /tect|salien|isthm|focus|elevation/i], ['rotundus', /rotund|entopall|glimpse|categor|^size|^look|^kind/i],
  ['wulst', /wulst|binoc|dispar|parallax|two.?view/i], ['flow', /flow|nbor/i], ['place', /gaze.?to.?place|^place/i],
  ['map', /^map|hippo|what.?where/i], ['records', /record|recall|longterm/i], ['heads', /^heads|memory.?head/i],
  ['trace', /trace|prefront|working|delay/i], ['ncl', /ncl|assoc|nidopall|cortex|hub/i], ['words', /word|lexic/i],
  ['brainstem_aud', /cochlear.?nucl|magnocell|laminar/i], ['mld', /mld|ovoid/i], ['fieldl', /field.?l/i],
  ['ncm', /ncm|\bcm\b/i], ['vocal', /vocal|nlc|aac/i], ['voice', /^voice|syrinx/i], ['ear', /^ear|cochlea/i],
  ['arco', /arco|motor|slot|reach|distance/i], ['body', /^body|propri|head.?dir/i], ['joints', /^joint/i],
  ['cerebellum', /cerebell/i], ['striatum', /striat|actor/i], ['vta', /vta|dopamin|critic|snc/i],
];
export function regionOf(p) {
  if (p.region && R.some((r) => r.id === p.region)) return p.region;
  for (const key of [p.region || p.area, p.name, p.title]) {
    if (!key) continue;
    for (const [id, rule] of MATCH) if (rule.test(String(key))) return id;
  }
  return null;
}
/** The regions whose drawing is the live layer's own (the record slots, the thing units). */
const OWN = new Set(['records', 'words']);
/** OrbitControls' turn speed for one turn a minute (2 is a turn in 30 s at 60 frames a second). */
const TURN = 1.0;
/** The radius the view fits to the pane: the brain fills it (the whole atlas fits in 3.3). */
const FIT = 2.45;

function rnd(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }
function dotTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 64;
  const g = c.getContext('2d'), grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, 'rgba(255,255,255,1)'); grad.addColorStop(0.3, 'rgba(255,255,255,0.75)'); grad.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grad; g.fillRect(0, 0, 64, 64);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

export class Brain3D {
  constructor(canvas, labels, options = {}) {
    this.canvas = canvas; this.labels = labels; this.host = canvas.parentElement;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);
    this.home = new THREE.Vector3(11.2, 4.8, 8.6).normalize();
    this.camera.position.copy(this.home).multiplyScalar(12);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.target.set(0, 0.5, -0.5); this.controls.enableDamping = true; this.controls.enablePan = false;
    this.controls.minDistance = 3; this.controls.maxDistance = 18; this.controls.autoRotate = true; this.controls.autoRotateSpeed = TURN;
    // a slow turn, about one a minute: it pauses while the visitor turns the brain and takes up again
    // a few seconds after, unless its switch is off
    this.turning = true;
    this.controls.addEventListener('start', () => { this.controls.autoRotate = false; clearTimeout(this.resumeTimer); });
    this.controls.addEventListener('end', () => { clearTimeout(this.resumeTimer); this.resumeTimer = setTimeout(() => { this.controls.autoRotate = this.turning; }, 4000); });
    this.clock = { vt: 0, speed: 1, paused: false, slow: false };
    this.hover = null; this.hoverFrom = null; this.path = null; this.pathPinned = null;
    this.washAt = -1e9;
    this.build();
    this.live = new Live(this);
    this.scanMode = !!options.scan;
    this.traceCol = new THREE.Color('#8a6fb0'); // the scan's fine traces: one cool tone; the pulses carry the warmth
    if (this.scanMode) { this.scan = new Scan(this, this.host); this.live.mapSprite.visible = false; this.shellMat.uniforms.colour.value.set('#5d6f8f'); }
    this.ui();
    new ResizeObserver(() => this.resize()).observe(this.host);
    this.resize();
  }

  /** A region's centre on a side (+1 the bird's left, -1 its right, 0 the midline). */
  centre(id, side = 1, out = new THREE.Vector3()) {
    const r = this.byId[id];
    if (!r) return out.set(0, 0, 0);
    return out.set(r.bi ? Math.abs(r.at[0]) * (side || 1) : r.at[0], r.at[1], r.at[2]);
  }

  build() {
    const shellMat = this.shellMat = new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      uniforms: { colour: { value: new THREE.Color('#6f8797') } },
      vertexShader: 'varying vec3 vN; varying vec3 vV; void main(){ vec4 mv = modelViewMatrix * vec4(position,1.0); vN = normalize(normalMatrix*normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix*mv; }',
      fragmentShader: 'uniform vec3 colour; varying vec3 vN; varying vec3 vV; void main(){ float f = pow(1.0 - abs(dot(vN, vV)), 2.4); gl_FragColor = vec4(colour * (0.03 + 0.45 * f), 1.0); }' });
    const sphere = new THREE.SphereGeometry(1, 40, 28);
    const shell = (at, r) => { const m = new THREE.Mesh(sphere, shellMat); m.position.set(...at); m.scale.set(...r); this.scene.add(m); };
    // the atlas's outline: the hemispheres, the tecta, the cerebellum, the brainstem
    shell([0.82, 0.45, 0.2], [0.98, 1.1, 1.75]); shell([-0.82, 0.45, 0.2], [0.98, 1.1, 1.75]);
    shell([1.35, -0.65, -0.35], [0.62, 0.55, 0.62]); shell([-1.35, -0.65, -0.35], [0.62, 0.55, 0.62]);
    shell([0, 0.35, -2.0], [0.75, 0.6, 0.55]); shell([0, -1.0, -1.7], [0.42, 0.4, 1.0]);
    // neurons: points in each region's ellipsoid, on both sides for the paired regions
    const rand = rnd(332), pos = [];
    this.regions = R.map((spec, index) => {
      const sides = spec.bi ? [1, -1] : [0];
      const shown = OWN.has(spec.id) ? 0 : Math.max(12, Math.min(420, Math.round(Math.sqrt(Math.max(spec.n, 1)) * 9)));
      const start = pos.length / 3, per = Math.round(shown / sides.length), side = [];
      for (const sx of sides) {
        const c = [sx ? Math.abs(spec.at[0]) * sx : spec.at[0], spec.at[1], spec.at[2]];
        for (let i = 0; i < per; i++) {
          let x, y, z; do { x = rand() * 2 - 1; y = rand() * 2 - 1; z = rand() * 2 - 1; } while (x * x + y * y + z * z > 1);
          pos.push(c[0] + x * spec.r[0], c[1] + y * spec.r[1], c[2] + z * spec.r[2]); side.push(sx);
        }
      }
      const count = pos.length / 3 - start;
      return { ...spec, index, start, count, side, base: new THREE.Color(hueOf(spec)), level: new Float32Array(count), neuron: new Int32Array(count).fill(-1),
        src: [], live: false, glow: 0, mean: 0,
        top: new THREE.Vector3(spec.bi ? Math.abs(spec.at[0]) : spec.at[0], spec.at[1] + spec.r[1] + 0.12, spec.at[2]) };
    });
    this.byId = Object.fromEntries(this.regions.map((r) => [r.id, r]));
    this.points = pos.length / 3;
    this.flash = new Float32Array(this.points); // the live layer's per-neuron flashes (surprise)
    this.tint = new Float32Array(this.regions.length * 4); // the live layer's per-region wash: r, g, b, amount
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    this.colours = new THREE.Float32BufferAttribute(new Float32Array(pos.length), 3); geo.setAttribute('color', this.colours);
    this.cloud = new THREE.Points(geo, new THREE.PointsMaterial({ size: 0.1, map: dotTexture(), vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    this.scene.add(this.cloud);
    // the tracts: a curve per side, all in one set of line segments, each lit by its source
    const SEG = 24, verts = [], us = [];
    this.tracts = [];
    const pa = new THREE.Vector3(), pb = new THREE.Vector3(), mid = new THREE.Vector3(), p = new THREE.Vector3(), q = new THREE.Vector3();
    for (const [a, b, w, what] of T) {
      const A = this.byId[a], Bv = this.byId[b];
      if (!A || !Bv) continue;
      for (const sx of (A.bi || Bv.bi ? [1, -1] : [0])) {
        const crossed = a === 'retina' && b === 'tectum';
        this.centre(a, sx, pa); this.centre(b, crossed ? -sx : sx, pb);
        mid.copy(pa).add(pb).multiplyScalar(0.5); mid.y += 0.25 + 0.1 * w;
        if (crossed) mid.set(0, -1.15, 0.3);
        const curve = new THREE.QuadraticBezierCurve3(pa.clone(), mid.clone(), pb.clone());
        const v0 = verts.length / 3;
        for (let k = 0; k < SEG; k++) {
          curve.getPoint(k / SEG, p); curve.getPoint((k + 1) / SEG, q);
          verts.push(p.x, p.y, p.z, q.x, q.y, q.z); us.push(k / SEG, (k + 1) / SEG);
        }
        this.tracts.push({ from: A, to: Bv, a, b, side: sx, w, what, v0, nv: SEG * 2, curve, level: 0, paths: [] });
      }
    }
    this.tractU = new Float32Array(us);
    const tg = new THREE.BufferGeometry();
    tg.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3));
    this.tractColours = new THREE.Float32BufferAttribute(new Float32Array(verts.length), 3); tg.setAttribute('color', this.tractColours);
    this.tractLines = new THREE.LineSegments(tg, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }));
    this.scene.add(this.tractLines);
    // which tracts each memory path runs along (in order, the bird's left side and the midline)
    this.pathColour = {};
    for (const P of PATHS) {
      this.pathColour[P.id] = new THREE.Color(P.colour);
      for (let i = 0; i + 1 < P.via.length; i++) for (const t of this.tracts) {
        if (t.side < 0) continue;
        if ((t.a === P.via[i] && t.b === P.via[i + 1]) || (t.b === P.via[i] && t.a === P.via[i + 1])) t.paths.push(P.id);
      }
    }
    // the names, each with its explanation
    this.labelEls = this.regions.map((r) => {
      const el = document.createElement('span');
      el.className = 'b3-label planned'; el.textContent = SHORT[r.id] || r.name;
      el.dataset.region = r.id; el.style.setProperty('--rc', hueOf(r));
      el.addEventListener('pointerenter', () => this.setHover(r.id, '3d'));
      el.addEventListener('pointerleave', () => this.setHover(null, '3d'));
      this.labels.append(el);
      return el;
    });
    this.labelW = new Float32Array(this.regions.length); this.labelX = new Float32Array(this.regions.length); this.labelY = new Float32Array(this.regions.length);
    this.explain();
    // hovering near a region's neurons names it and lights its card in the right panel
    this.canvas.addEventListener('pointermove', (e) => this.pick(e));
    this.canvas.addEventListener('pointerleave', () => { if (this.hoverFrom === '3d') this.setHover(null, '3d'); });
    document.addEventListener('parrot:region', (e) => { if (e.detail?.from !== '3d') { this.hover = e.detail?.id || null; this.hoverFrom = e.detail?.from || null; } });
  }

  explain() {
    this.regions.forEach((r, i) => {
      const live = r.live, el = this.labelEls[i];
      el.classList.toggle('planned', !live); el.classList.toggle('live', live);
      const what = r.src.length ? `In the running brain: ${r.src.map((p) => `${p.title || p.name} (${p.size.toLocaleString('en')} neurons)`).join(', ')}.`
        : live ? `In the running brain: ${r.liveNote || 'its live layer'}.` : `Not in this brain yet (${STN[r.st]}): drawn faint.`;
      el.setAttribute('data-explain-title', r.name);
      el.setAttribute('data-explain', `In a bird: ${r.bird}.\n\nIn this brain: ${r.role}\n\n${what}`);
    });
  }

  /** The running brain's populations (describe().populations, each with start, size). */
  setup(desc) {
    for (const r of this.regions) { r.src = []; r.live = false; }
    for (const p of desc.populations || desc.regions || []) {
      const id = regionOf(p);
      if (id && this.byId[id] && p.start !== undefined && p.size) this.byId[id].src.push(p);
    }
    for (const r of this.regions) {
      r.live = r.src.length > 0;
      if (!r.src.length || !r.count) continue;
      // each drawn point stands for one neuron of the region's populations; a paired region with a
      // left and a right population shows each on its side
      const lr = r.bi && r.src.length === 2 && /_l$|left/i.test(r.src[0].name + r.src[0].title) && /_r$|right/i.test(r.src[1].name + r.src[1].title);
      const total = r.src.reduce((a, q) => a + q.size, 0);
      for (let i = 0; i < r.count; i++) {
        let p, frac;
        if (lr) { p = r.side[i] > 0 ? r.src[0] : r.src[1]; const half = r.count / 2; frac = (i % half) / half; }
        else {
          let k = (i / r.count) * total; p = r.src[0];
          for (const q of r.src) { if (k < q.size) { p = q; break; } k -= q.size; }
          frac = k / p.size;
        }
        r.neuron[i] = p.start + Math.min(p.size - 1, Math.floor(frac * p.size));
      }
    }
    this.desc = desc;
    this.live.setup(desc);
    this.explain();
    this.ready = true;
  }

  /** Mark a region live from the live layer (the record slots, the word links). */
  markLive(id, note) { const r = this.byId[id]; if (r && !r.live) { r.live = true; r.liveNote = note; this.explain(); } }

  /** One moment: every neuron's activity, and the host's whole reply for the live layer. */
  update(activity, reply) {
    if (!this.ready) return;
    reply ||= window.parrotPage?.state?.lastReply || null;
    if (activity) {
      this.activity = activity;
      for (const r of this.regions) {
        if (!r.src.length) continue;
        let sum = 0;
        for (let i = 0; i < r.count; i++) { const v = activity[r.neuron[i]]; r.level[i] = Number.isFinite(v) ? Math.max(0, Math.min(1, v)) : 0; sum += r.level[i]; }
        r.mean = r.count ? sum / r.count : 0;
      }
    }
    if (reply) { this.live.moment(reply, activity); this.scan?.moment(reply); }
  }

  /** The pistachio reaches the beak: the reward arrives at the VTA. */
  reward() { this.live.reward(); this.scan?.reward(); }

  // --- hover: a region named in the 3D view lights its card on the right, and back ----------------
  setHover(id, from) {
    if (this.hover === id && this.hoverFrom === from) return;
    this.hover = id; this.hoverFrom = id ? from : null;
    document.dispatchEvent(new CustomEvent('parrot:region', { detail: { id, from } }));
  }
  pick(e) {
    if (e.buttons) return;
    const rect = this.canvas.getBoundingClientRect(), mx = e.clientX - rect.left, my = e.clientY - rect.top;
    let best = null, bd = 28 * 28;
    const v = this._v ||= new THREE.Vector3();
    for (const r of this.regions) {
      if (!r.live) continue;
      for (const sx of (r.bi ? [1, -1] : [0])) {
        this.centre(r.id, sx, v).project(this.camera);
        const x = (v.x + 1) / 2 * rect.width, y = (1 - v.y) / 2 * rect.height, d = (x - mx) ** 2 + (y - my) ** 2;
        if (d < bd) { bd = d; best = r.id; }
      }
    }
    this.setHover(best, '3d');
  }

  // --- the overlay: how it connects, the live parts, the clock ----------------------------------
  ui() {
    const el = (tag, cls, text) => { const x = document.createElement(tag); if (cls) x.className = cls; if (text) x.textContent = text; return x; };
    const how = el('div', 'b3-how');
    const lead = el('span', 'b3-lead', 'How it connects');
    lead.setAttribute('data-explain-title', 'How it connects');
    lead.setAttribute('data-explain', 'The path each kind of memory takes through the brain. Point at one to light its path; click to keep it lit. Images of things: what the eyes saw and where. Sounds: what the ear heard, kept whole in a record slot. Words: the links from a sound to the thing it names. Saying: a word read out of its record to the voice.');
    how.append(lead, el('span', 'b3-break'));
    this.pathButtons = PATHS.map((P) => {
      const b = el('button', 'b3-path'); b.type = 'button'; b.dataset.path = P.id; b.style.setProperty('--pc', P.colour);
      b.append(el('i'), document.createTextNode(P.name));
      b.setAttribute('aria-pressed', 'false');
      const q = el('span', 'b3-q'); q.setAttribute('data-explain-title', P.name); q.setAttribute('data-explain', `${P.explain}\n\nIts path: ${P.via.map((id) => SHORT[id] || id).join(' to ')}.`);
      b.addEventListener('pointerenter', () => { this.path = P.id; });
      b.addEventListener('pointerleave', () => { this.path = this.pathPinned; });
      b.addEventListener('click', () => { this.pathPinned = this.pathPinned === P.id ? null : P.id; this.path = this.pathPinned; for (const x of this.pathButtons) x.setAttribute('aria-pressed', String(x.dataset.path === this.pathPinned)); });
      how.append(b, q);
      return b;
    });
    this.host.append(how);
    this.stepEls = [];
    // the clock and the live parts
    const bar = el('div', 'b3-bar');
    const pause = el('button', 'b3-btn', 'Pause'); pause.type = 'button'; pause.setAttribute('aria-pressed', 'false');
    pause.setAttribute('data-explain', 'Holds the picture: the brain runs on, and the view takes up the latest moment when you press again.'); pause.setAttribute('data-explain-mark', 'none');
    pause.addEventListener('click', () => { this.clock.paused = !this.clock.paused; pause.setAttribute('aria-pressed', String(this.clock.paused)); pause.textContent = this.clock.paused ? 'Play' : 'Pause'; this.clockChanged(); });
    const turn = el('button', 'b3-btn', 'Turning'); turn.type = 'button'; turn.setAttribute('aria-pressed', 'true');
    turn.setAttribute('data-explain', 'The brain turns slowly, about once a minute. Drag it to turn it yourself; it takes up its turn a few seconds after. Press to stop or start the turn.'); turn.setAttribute('data-explain-mark', 'none');
    turn.addEventListener('click', () => { this.turning = !this.turning; this.controls.autoRotate = this.turning; turn.setAttribute('aria-pressed', String(this.turning)); turn.textContent = this.turning ? 'Turning' : 'Still'; });
    const slow = el('button', 'b3-btn', 'Slow ×10'); slow.type = 'button'; slow.setAttribute('aria-pressed', 'false');
    slow.setAttribute('data-explain', 'Runs the view ten times slower, so a word flying to its record or a wash of dopamine can be followed. The brain runs on at its own pace.'); slow.setAttribute('data-explain-mark', 'none');
    slow.addEventListener('click', () => { this.clock.slow = !this.clock.slow; slow.setAttribute('aria-pressed', String(this.clock.slow)); this.clockChanged(); });
    const partsBtn = el('button', 'b3-btn', 'What it shows'); partsBtn.type = 'button'; partsBtn.setAttribute('aria-expanded', 'false');
    partsBtn.setAttribute('data-explain', 'Every part of the live picture, its colour, and whether this brain has it. A part this brain does not have is drawn faint and says so.'); partsBtn.setAttribute('data-explain-mark', 'none');
    const list = el('div', 'b3-parts'); list.hidden = true;
    partsBtn.addEventListener('click', () => { list.hidden = !list.hidden; partsBtn.setAttribute('aria-expanded', String(!list.hidden)); });
    this.partRows = {};
    for (const P of PARTS) {
      const row = el('div', 'b3-part'); row.style.setProperty('--pc', P.colour);
      row.append(el('i'), el('b', '', P.name), el('span', 'st', 'not in this brain yet'));
      row.setAttribute('data-explain-title', P.name); row.setAttribute('data-explain', P.explain); row.setAttribute('data-explain-mark', 'corner');
      list.append(row); this.partRows[P.id] = row;
    }
    bar.append(pause, slow, turn, partsBtn);
    this.host.append(list, bar);
    this.clockEl = el('span', 'b3-clock'); bar.append(this.clockEl);
  }
  clockChanged() {
    this.clock.speed = this.clock.paused ? 0 : this.clock.slow ? 0.1 : 1;
    this.clockEl.textContent = this.clock.paused ? 'paused' : this.clock.slow ? 'ten times slower' : '';
  }
  /** The live layer says which parts this brain has (status text "live: ..." or absent). */
  partStatus(id, text) {
    const row = this.partRows[id];
    if (!row) return;
    const live = !!text, st = row.querySelector('.st'), want = text || 'not in this brain yet';
    if (st.textContent !== want) st.textContent = want;
    row.classList.toggle('live', live);
  }

  resize() {
    const w = this.host.clientWidth, h = this.host.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false); this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
    this._rect = { width: w, height: h }; if (this.scan) this.scan.rects = false;
    // fit the brain to the panel: its bounding sphere within the narrower field of view
    const room = Math.max(0.5, (h - 110) / h), vf = 2 * Math.atan(Math.tan(this.camera.fov * Math.PI / 360) * room), hf = 2 * Math.atan(Math.tan(this.camera.fov * Math.PI / 360) * this.camera.aspect);
    const fit = (this.scanMode ? 2.05 : FIT) / Math.sin(Math.min(vf, hf) / 2);
    if (!this.fitted || Math.abs(fit - this.fitted) > 0.5) {
      const dir = this.camera.position.clone().sub(this.controls.target).normalize();
      this.camera.position.copy(this.controls.target).addScaledVector(dir, fit);
      this.fitted = fit; this.controls.maxDistance = Math.max(18, fit * 1.6);
    }
    this.live.resize(w, h);
  }

  frame(dt) {
    const c = this.clock, vdt = dt * c.speed; c.vt += vdt;
    const a = 1 - Math.exp(-vdt / 0.12), arr = this.colours.array, flash = this.flash, tint = this.tint;
    this.live.frame(vdt, c.vt, dt);
    const path = this.path ? PATHS.find((P) => P.id === this.path) : null, onPath = path ? new Set(path.via) : null;
    const hov = this.hover;
    // the neurons: the region's colour by each neuron's activity, the live layer's washes and flashes
    for (const r of this.regions) {
      if (!r.count) continue;
      const live = r.live, k4 = 4 * r.index;
      let dim = live ? 0.12 : 0.035, gain = live ? 0.95 : 0;
      if (onPath) { if (onPath.has(r.id)) { dim = Math.max(dim, 0.3); gain = Math.max(gain, 0.4); } else { dim *= 0.35; gain *= 0.35; } }
      if (hov === r.id) { dim = Math.max(dim, 0.45); gain = 1; }
      const tr = tint[k4], tg = tint[k4 + 1], tb = tint[k4 + 2], ta = tint[k4 + 3];
      const br = r.base.r, bg = r.base.g, bb = r.base.b;
      const scan = this.scanMode;
      for (let i = 0; i < r.count; i++) {
        const j = r.start + i, k = 3 * j, t = dim + gain * r.level[i], f = flash[j];
        let wr, wg, wb;
        if (scan) { // the scan's dark-to-warm scale: the neuron's activity, the settle's flash brightening it
          const q = Math.min(255, Math.round(Math.min(1, (live ? r.level[i] : 0) * 1.3 + f * 0.6) * 255)) * 3, lift = live ? 0.25 + 0.95 * Math.min(1, r.level[i] * 1.4 + f) : 0.06;
          wr = LUT[q] * lift + tr * ta + f * 0.4; wg = LUT[q + 1] * lift + tg * ta + f * 0.3; wb = LUT[q + 2] * lift + tb * ta + f * 0.2;
          if (onPath && !onPath.has(r.id)) { wr *= 0.35; wg *= 0.35; wb *= 0.35; }
        } else { wr = br * t + tr * ta + f; wg = bg * t + tg * ta + f * 0.62; wb = bb * t + tb * ta + f * 0.3; }
        arr[k] += (wr - arr[k]) * a; arr[k + 1] += (wg - arr[k + 1]) * a; arr[k + 2] += (wb - arr[k + 2]) * a;
        if (f > 0) { arr[k] = Math.max(arr[k], wr); arr[k + 1] = Math.max(arr[k + 1], wg); arr[k + 2] = Math.max(arr[k + 2], wb); }
      }
    }
    this.colours.needsUpdate = true;
    // the tracts: a flow from source to target, brighter the more the source is active; a lit path
    // runs in its own colour
    const tc = this.tractColours.array, U = this.tractU, phase = c.vt * 1.1;
    for (const t of this.tracts) {
      const src = t.from;
      let want = src.live ? 0.05 + 0.75 * src.mean * t.w : 0.018;
      if (src.live && t.to.live) want += 0.03;
      want += this.live.tractBoost(t);
      t.level += (want - t.level) * a;
      let col = this.scanMode ? this.traceCol : src.base, lvl = this.scanMode ? 0.12 + 0.6 * t.level : t.level, flow = this.scanMode ? 0.25 : 0.55;
      if (onPath) {
        if (path && t.paths.includes(path.id)) { col = this.pathColour[path.id]; lvl = Math.max(lvl, 0.75); flow = 0.85; }
        else lvl *= 0.25;
      }
      if (hov && (t.a === hov || t.b === hov)) lvl = Math.max(lvl, 0.5);
      const reverse = path && t.paths.includes(path.id) && path.via.indexOf(t.a) > path.via.indexOf(t.b);
      for (let v = 0; v < t.nv; v++) {
        const u = reverse ? 1 - U[t.v0 + v] : U[t.v0 + v];
        const wave = 1 - flow + flow * (0.5 + 0.5 * Math.cos(6.283 * (u * 2.2 - phase)));
        const s = lvl * wave, k = 3 * (t.v0 + v);
        tc[k] = col.r * s; tc[k + 1] = col.g * s; tc[k + 2] = col.b * s;
      }
    }
    this.tractColours.needsUpdate = true;
    if (this.controls.autoRotate) this.controls.autoRotateSpeed = c.paused ? 0 : TURN;
    this.controls.update(dt); // the turn by the frame's own time: about one a minute, never per brain moment
    if (this.scan) this.scan.frame(dt, c.vt, this._rect || (this._rect = { width: this.host.clientWidth, height: this.host.clientHeight }));
    this.renderer.render(this.scene, this.camera);
    this.placeLabels(onPath);
  }

  /** The names: each over its region, the live first; a name that would cover another is left out. */
  placeLabels(onPath) {
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight, v = this._lv ||= new THREE.Vector3();
    const order = this._order ||= this.regions.map((r, i) => i);
    order.sort((i, j) => this.prio(this.regions[j], onPath) - this.prio(this.regions[i], onPath));
    const placed = this._placed ||= [];
    placed.length = 0;
    for (const i of order) {
      const r = this.regions[i], el = this.labelEls[i];
      v.copy(r.top).project(this.camera);
      const x = Math.round((v.x + 1) / 2 * w), y = Math.round((1 - v.y) / 2 * h);
      if (!this.labelW[i]) this.labelW[i] = el.offsetWidth || 60;
      const half = this.labelW[i] / 2 + 3;
      let free = v.z < 1 && x > half - 20 && x < w - half + 20 && y > 54 && y < h - 40;
      if (free) for (const p of placed) if (Math.abs(p[0] - x) < p[2] + half && Math.abs(p[1] - y) < 15) { free = false; break; }
      if (free && !r.live && this.hover !== r.id && !(onPath && onPath.has(r.id)) && placed.length > 14) free = false;
      el.classList.toggle('off', !free);
      el.classList.toggle('hot', this.hover === r.id || !!(onPath && onPath.has(r.id)));
      if (!free) continue;
      placed.push([x, y, half]);
      if (this.labelX[i] !== x || this.labelY[i] !== y) { el.style.transform = `translate(${x}px, ${y}px) translate(-50%, -50%)`; this.labelX[i] = x; this.labelY[i] = y; }
    }
  }
  prio(r, onPath) { return (this.hover === r.id ? 100 : 0) + (onPath && onPath.has(r.id) ? 50 : 0) + (r.live ? 10 : 0) + Math.min(5, r.n / 2000); }
}
