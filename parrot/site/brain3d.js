// The brain in 3D, beside the parrot: the planned parrot brain as a bird's brain (atlas.js: its
// regions where they sit in a bird's head, the tracts between them), filled with the running
// brain. Every population the brain host names joins its atlas region by its name; there each
// neuron is a point that glows with its activity at each moment, and the tracts out of it light
// with what it carries. Regions the running brain does not have yet are drawn faint and say
// "planned". A pistachio's dopamine washes out from the midbrain. Every region's name carries a
// question mark: what it is in a bird and what it does in this brain.
import * as THREE from 'three';
import { OrbitControls } from './vendor/three/jsm/controls/OrbitControls.js';
import { R, T, HUE, STN } from './atlas.js';

// Which atlas region a population of the running brain belongs to, by its name, then its region
// or area, then its title (the first region whose rule matches).
const MATCH = [
  ['retina', /retina/i], ['tectum', /tect|salien|isthm|focus/i], ['rotundus', /rotund|entopall|glimpse|categor/i],
  ['wulst', /wulst|binoc|dispar|parallax|two.?view/i], ['flow', /flow|nbor/i], ['place', /gaze.?to.?place|^place/i],
  ['map', /^map|hippo|what.?where/i], ['records', /record|recall|longterm/i], ['heads', /^heads|memory.?head/i],
  ['trace', /trace|prefront|working|delay/i], ['ncl', /ncl|assoc|nidopall|cortex|hub/i], ['words', /word|lexic/i],
  ['brainstem_aud', /cochlear.?nucl|magnocell|laminar/i], ['mld', /mld|ovoid/i], ['fieldl', /field.?l/i],
  ['ncm', /ncm|\bcm\b/i], ['vocal', /vocal|nlc|aac/i], ['voice', /^voice|syrinx/i], ['ear', /^ear|cochlea/i],
  ['arco', /arco|motor|slot|reach|distance/i], ['body', /^body|propri|head.?dir/i], ['joints', /^joint/i],
  ['cerebellum', /cerebell/i], ['striatum', /striat|actor/i], ['vta', /vta|dopamin|critic|snc/i],
];
function regionOf(p) {
  for (const key of [p.name, p.region || p.area, p.title]) {
    if (!key) continue;
    for (const [id, rule] of MATCH) if (rule.test(String(key))) return id;
  }
  return null;
}

function rnd(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }
function dotTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 64;
  const g = c.getContext('2d'), grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, 'rgba(255,255,255,1)'); grad.addColorStop(0.3, 'rgba(255,255,255,0.75)'); grad.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grad; g.fillRect(0, 0, 64, 64);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}
const SHORT = { tectum: 'Tectum', rotundus: 'Rotundus', wulst: 'Wulst', flow: 'Flow nuclei', place: 'Gaze to place', map: 'Hippocampus',
  records: 'Records', heads: 'Memory heads', ncl: 'NCL', trace: 'Trace', words: 'Words', ear: 'Ears', brainstem_aud: 'Cochlear nuclei',
  mld: 'MLd', fieldl: 'Field L', ncm: 'NCM, CM', vocal: 'Vocal core', voice: 'Voice', arco: 'Arcopallium', body: 'Body sense',
  joints: 'Joints', cerebellum: 'Cerebellum', striatum: 'Striatum', vta: 'VTA: dopamine', retina: 'Retina' };

export class Brain3D {
  constructor(canvas, labels) {
    this.canvas = canvas; this.labels = labels;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);
    this.camera.position.set(11.2, 4.8, 8.6);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.target.set(0, -0.35, -0.6); this.controls.enableDamping = true; this.controls.enablePan = false;
    this.controls.minDistance = 4; this.controls.maxDistance = 16; this.controls.autoRotate = true; this.controls.autoRotateSpeed = 0.5;
    canvas.addEventListener('pointerdown', () => { this.controls.autoRotate = false; });
    this.washAt = -1e9;
    this.build();
    new ResizeObserver(() => this.resize()).observe(canvas.parentElement);
    this.resize();
  }

  build() {
    const shellMat = new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      uniforms: { colour: { value: new THREE.Color('#6f8797') } },
      vertexShader: 'varying vec3 vN; varying vec3 vV; void main(){ vec4 mv = modelViewMatrix * vec4(position,1.0); vN = normalize(normalMatrix*normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix*mv; }',
      fragmentShader: 'uniform vec3 colour; varying vec3 vN; varying vec3 vV; void main(){ float f = pow(1.0 - abs(dot(vN, vV)), 2.4); gl_FragColor = vec4(colour * (0.03 + 0.45 * f), 1.0); }' });
    const shell = (at, r) => { const m = new THREE.Mesh(new THREE.SphereGeometry(1, 40, 28), shellMat); m.position.set(...at); m.scale.set(...r); this.scene.add(m); };
    // the atlas's outline: the hemispheres, the tecta, the cerebellum, the brainstem
    shell([0.82, 0.45, 0.2], [0.98, 1.1, 1.75]); shell([-0.82, 0.45, 0.2], [0.98, 1.1, 1.75]);
    shell([1.35, -0.65, -0.35], [0.62, 0.55, 0.62]); shell([-1.35, -0.65, -0.35], [0.62, 0.55, 0.62]);
    shell([0, 0.35, -2.0], [0.75, 0.6, 0.55]); shell([0, -1.0, -1.7], [0.42, 0.4, 1.0]);
    // neurons: points in each region's ellipsoid, on both sides for the paired regions
    const rand = rnd(332), pos = [], col = [];
    this.regions = R.map((spec) => {
      const sides = spec.bi ? [1, -1] : [0];
      const shown = Math.max(12, Math.min(420, Math.round(Math.sqrt(Math.max(spec.n, 1)) * 9)));
      const start = pos.length / 3, per = Math.round(shown / sides.length), side = [];
      for (const sx of sides) {
        const c = [sx ? Math.abs(spec.at[0]) * sx : spec.at[0], spec.at[1], spec.at[2]];
        for (let i = 0; i < per; i++) {
          let x, y, z; do { x = rand() * 2 - 1; y = rand() * 2 - 1; z = rand() * 2 - 1; } while (x * x + y * y + z * z > 1);
          pos.push(c[0] + x * spec.r[0], c[1] + y * spec.r[1], c[2] + z * spec.r[2]); col.push(0, 0, 0); side.push(sx);
        }
      }
      const count = pos.length / 3 - start;
      return { ...spec, start, count, side, base: new THREE.Color(HUE[spec.sys]), level: new Float32Array(count), src: [],
        centre: new THREE.Vector3(spec.bi ? Math.abs(spec.at[0]) : spec.at[0], spec.at[1] + spec.r[1] + 0.12, spec.at[2]) };
    });
    this.byId = Object.fromEntries(this.regions.map((r) => [r.id, r]));
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    this.colours = new THREE.Float32BufferAttribute(col, 3); geo.setAttribute('color', this.colours);
    this.points = new THREE.Points(geo, new THREE.PointsMaterial({ size: 0.1, map: dotTexture(), vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    this.scene.add(this.points);
    // the tracts: a curve per side, lit by what the source region carries
    this.tracts = [];
    for (const [a, b, w, what] of T) {
      const A = this.byId[a], Bv = this.byId[b];
      if (!A || !Bv) continue;
      const sides = A.bi || Bv.bi ? [1, -1] : [0];
      for (const sx of sides) {
        const pa = new THREE.Vector3(A.bi ? Math.abs(A.at[0]) * sx : A.at[0], A.at[1], A.at[2]);
        const crossed = a === 'retina' && b === 'tectum';
        const sb = crossed ? -sx : sx;
        const pb = new THREE.Vector3(Bv.bi ? Math.abs(Bv.at[0]) * sb : Bv.at[0], Bv.at[1], Bv.at[2]);
        const mid = pa.clone().add(pb).multiplyScalar(0.5); mid.y += 0.25 + 0.1 * w;
        if (crossed) mid.set(0, -1.15, 0.3);
        const curve = new THREE.QuadraticBezierCurve3(pa, mid, pb);
        const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(curve.getPoints(32)),
          new THREE.LineBasicMaterial({ color: A.base, transparent: true, opacity: 0.05, blending: THREE.AdditiveBlending, depthWrite: false }));
        this.scene.add(line);
        this.tracts.push({ line, from: A, side: sx, w, what });
      }
    }
    // the dopamine wash, from the midbrain outward
    this.washMesh = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 20), new THREE.MeshBasicMaterial({ color: new THREE.Color(HUE.reward), transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.BackSide }));
    const vta = this.byId.vta; this.washMesh.position.set(...vta.at);
    this.scene.add(this.washMesh);
    // the names, each with its explanation
    this.labelEls = this.regions.map((r) => {
      const el = document.createElement('span');
      el.className = 'b3-label planned'; el.textContent = SHORT[r.id] || r.name;
      el.dataset.region = r.id;
      this.labels.append(el);
      return el;
    });
    this.explain();
  }

  explain() {
    this.regions.forEach((r, i) => {
      const live = r.src.length > 0, el = this.labelEls[i];
      el.classList.toggle('planned', !live); el.classList.toggle('live', live);
      const status = live ? `In the running brain: ${r.src.map((p) => `${p.title || p.name} (${p.size})`).join(', ')}.` : `Not in the running brain yet (${STN[r.st]}): drawn faint.`;
      el.setAttribute('data-explain-title', r.name);
      el.setAttribute('data-explain', `In a bird: ${r.bird}.\n\nIn this brain: ${r.role}\n\n${status}`);
    });
  }

  /** The running brain's populations (describe().populations or .regions, each with start, size). */
  setup(desc) {
    for (const r of this.regions) r.src = [];
    for (const p of desc.populations || desc.regions || []) {
      const id = regionOf(p);
      if (id && p.start !== undefined && p.size) this.byId[id].src.push(p);
    }
    this.explain();
    this.ready = true;
  }

  update(activity) {
    if (!this.ready || !activity) return;
    for (const r of this.regions) {
      if (!r.src.length) continue;
      // a paired region with a left and a right population shows each on its side
      const lr = r.bi && r.src.length === 2 && /_l$|left/i.test(r.src[0].name + r.src[0].title) && /_r$|right/i.test(r.src[1].name + r.src[1].title);
      for (let i = 0; i < r.count; i++) {
        let p, frac;
        if (lr) { p = r.side[i] > 0 ? r.src[0] : r.src[1]; const half = r.count / 2; frac = (i % half) / half; }
        else {
          const total = r.src.reduce((a, q) => a + q.size, 0); let k = (i / r.count) * total; p = r.src[0];
          for (const q of r.src) { if (k < q.size) { p = q; break; } k -= q.size; }
          frac = k / p.size;
        }
        const v = activity[p.start + Math.min(p.size - 1, Math.floor(frac * p.size))];
        r.level[i] = Number.isFinite(v) ? Math.max(0, Math.min(1, v)) : 0;
      }
    }
  }

  /** The pistachio's dopamine: VTA flashes, a wave runs along its projections, and the tracts that
   *  were just active glow as they strengthen (in the composed brain; this view shows where). */
  reward() {
    this.washAt = performance.now();
    for (const t of this.tracts) t.paid = t.line.material.opacity > 0.12 || t.from.id === 'vta';
  }

  resize() {
    const w = this.canvas.parentElement.clientWidth, h = this.canvas.parentElement.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false); this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
  }

  frame(dt) {
    const a = 1 - Math.exp(-dt / 0.12), arr = this.colours.array;
    const since = (performance.now() - this.washAt) / 1000, wash = since < 2.4 ? Math.sin(Math.min(1, since / 2.4) * Math.PI) : 0;
    const rew = new THREE.Color(HUE.reward);
    for (const r of this.regions) {
      const live = r.src.length > 0, dim = live ? 0.12 : 0.035;
      for (let i = 0; i < r.count; i++) {
        const k = 3 * (r.start + i), t = dim + (live ? 0.95 * r.level[i] : 0);
        const tr = r.base.r * t + rew.r * 0.3 * wash, tg = r.base.g * t + rew.g * 0.3 * wash, tb = r.base.b * t + rew.b * 0.3 * wash;
        arr[k] += (tr - arr[k]) * a; arr[k + 1] += (tg - arr[k + 1]) * a; arr[k + 2] += (tb - arr[k + 2]) * a;
      }
    }
    this.colours.needsUpdate = true;
    const vtaGlow = since < 1.2 ? 1 - since / 1.2 : 0;
    const vta = this.byId.vta;
    for (let i = 0; i < vta.count; i++) { const k = 3 * (vta.start + i); arr[k] = Math.max(arr[k], rew.r * vtaGlow); arr[k + 1] = Math.max(arr[k + 1], rew.g * vtaGlow); arr[k + 2] = Math.max(arr[k + 2], rew.b * vtaGlow); }
    for (const t of this.tracts) {
      if (since < 2.6 && t.paid) { // the wave and the strengthening glow
        const glow = t.from.id === 'vta' ? Math.max(0, Math.sin(Math.min(1, since / 1.4) * Math.PI)) : Math.max(0, Math.sin(Math.min(1, (since - 0.5) / 2.0) * Math.PI));
        t.line.material.color.copy(t.from.base).lerp(rew, 0.6 * glow);
        t.line.material.opacity = Math.max(t.line.material.opacity, 0.15 + 0.75 * glow);
        continue;
      } else if (t.paid) { t.paid = false; t.line.material.color.copy(t.from.base); }
      let m = 0, n = 0; const L = t.from.level;
      for (let i = 0; i < L.length; i += 3) { if (t.from.side[i] === t.side || t.side === 0) { m += L[i]; n++; } }
      m = n ? m / n : 0;
      const want = t.from.src.length ? 0.06 + 0.7 * m * t.w : 0.025;
      t.line.material.opacity += (want - t.line.material.opacity) * a;
    }
    this.washMesh.scale.setScalar(0.2 + 3.2 * Math.min(1, since / 1.8));
    this.washMesh.material.opacity = 0.16 * wash;
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight, v = new THREE.Vector3();
    this.regions.forEach((r, i) => {
      v.copy(r.centre).project(this.camera);
      const el = this.labelEls[i], x = Math.round((v.x + 1) / 2 * w), y = Math.round((1 - v.y) / 2 * h), key = `${x},${y}`;
      if (el.dataset.at !== key) { el.style.transform = `translate(${x}px, ${y}px) translate(-50%, -50%)`; el.dataset.at = key; }
    });
  }
}
