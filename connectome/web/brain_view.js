// Cadence zebrafish brain view: the brainstem's reconstructed skeletons in three dimensions,
// lit by a live activity vector. Every skeleton is drawn as line segments in dim green inside
// one merged LineSegments geometry with per-vertex colours; a frame rewrites colours only, and
// only the vertex ranges of the neurons whose level changed. A neuron lights up in proportion
// to its activity in [0, 1]: brighter and a warmer green-white; a second channel, the repair
// (how much the cell moved its potential in the last step), flashes it gold and fades, so a
// stimulus shows as a wave of repairs sweeping through the net before it rests again.
// The display scale is a number or "auto", a slowly released peak, and a gamma below 1
// lifts the small activities of a graded net into view. The lines add up in a half-float
// target and a tone-map pass with a soft knee (1 - exp(-x * exposure)) brings them to the
// screen, so overlapping lit skeletons brighten toward white without clipping flat. A small
// sphere at every root node (the soma) carries its class colour, drawn straight after the
// tone map so the legend colours stay exact. Orbit by drag, zoom by wheel or pinch, pan by
// shift-drag or right-drag, a slow spin until the first drag. The overlay holds the legend with
// a checkbox per class, the "hot only" toggle that hides neurons below HOT, and the count of
// active neurons. Palette: the Matrix green of the fly pages; the view sits beside a main view.
// Payload: web/data/skeletons.json from tools/export_skeletons.py (cadence.zebrafish-skeletons/v1).
import * as THREE from "three";

export const VERSION = "cadence.zebrafish-brain-view/v1";
export const HOT = 0.05; // activity below this counts as resting
export const CLASSES = ["_Int_", "_Axl_", "_DOs_", "ABD_m", "ABD_i", "vSPNs", "periphery"];
export const CLASS_LABELS = {
  _Int_: "integrator", _Axl_: "axial", _DOs_: "DO", ABD_m: "abducens motor",
  ABD_i: "abducens internuclear", vSPNs: "vSPN", periphery: "periphery",
};
// soma and legend colours, RGB in 0..255: shades of the Matrix green, one warm accent for the descending outputs
export const CLASS_COLORS = {
  _Int_: [103, 231, 142], _Axl_: [184, 223, 129], _DOs_: [90, 220, 190], ABD_m: [210, 255, 120],
  ABD_i: [60, 170, 160], vSPNs: [255, 214, 102], periphery: [60, 92, 72],
};
const DEFAULTS = {
  rest: [0.02, 0.16, 0.06], // a resting skeleton, before the tone map
  lit: [0.64, 1.0, 0.5], // a fully active skeleton: warmer than rest; overlapping lit lines add up to a warm white
  exposure: 1.4, // the tone map's gain
  background: [0, 0.012, 0.004],
  somaRadius: 0.007, // in the payload's frame (the longest axis spans 2.0)
  spin: true,
  spinRate: 0.1, // radians per second
  spinAfter: 6, // seconds after the last drag before the spin resumes
  fov: 30,
  dpr: 2,
  controls: true, // the overlay with the legend, the filter and the counts; "legend" for the colour key alone
  hotOnly: false,
  gain: 1, // display gain on the activity before the scale
  scale: 1, // the activity that paints a cell fully lit; "auto" tracks the brightest cell and releases slowly
  floor: 0.05, // the auto scale never falls below this
  release: 0.995, // the auto scale's peak decays by this per reading
  gamma: 1, // below 1 lifts the small activities (level = (activity / scale) ^ gamma)
  flash: [1.0, 0.8, 0.3], // what a full repair adds to a cell's colour: gold, the site's burst colour, so a repair reads apart from lit activity
  fitScale: 1, // below 1 the resting view sits closer than the full frame
  pointRadius: 1, // the soma radius of a cell drawn as a point alone (no skeleton), as a fraction of somaRadius
  pointDim: 1, // the colour of such a point at rest, as a fraction; activity and repair bring it back
};
const STYLE = `
.bv-canvas{position:absolute;inset:0;width:100%;height:100%;display:block;cursor:grab;touch-action:none;border-radius:inherit}
.bv-canvas:active{cursor:grabbing}
.bv-overlay{position:absolute;inset:0;pointer-events:none;font:11px/1.5 "IBM Plex Mono",ui-monospace,Menlo,monospace;color:#a1d5b0}
.bv-legend{position:absolute;left:8px;bottom:8px;display:flex;flex-direction:column;gap:1px;padding:6px 8px;background:rgba(2,14,7,.84);border:1px solid rgba(97,186,121,.25);border-radius:5px;pointer-events:auto}
.bv-legend label{display:flex;align-items:center;gap:6px;cursor:pointer;white-space:nowrap;user-select:none}
.bv-legend label.off{opacity:.45}
.bv-legend input{appearance:none;width:9px;height:9px;margin:0;border:1px solid rgba(97,186,121,.5);border-radius:2px;background:transparent;flex-shrink:0}
.bv-legend input:checked{background:#67e78e;border-color:#67e78e}
.bv-legend i{display:inline-block;width:7px;height:7px;border-radius:50%;flex-shrink:0}
.bv-legend em{font-style:normal;color:#679774;margin-left:auto;padding-left:8px;font-variant-numeric:tabular-nums}
.bv-status{position:absolute;right:8px;top:8px;display:flex;flex-direction:column;align-items:flex-end;gap:3px;pointer-events:auto}
.bv-active{padding:3px 8px;background:rgba(2,14,7,.84);border:1px solid rgba(97,186,121,.25);border-radius:5px;color:#c8ffd8;font-variant-numeric:tabular-nums;white-space:nowrap}
.bv-active b{color:#67e78e;font-weight:500}
.bv-hot{display:flex;align-items:center;gap:6px;padding:3px 8px;background:rgba(2,14,7,.84);border:1px solid rgba(97,186,121,.25);border-radius:5px;cursor:pointer;user-select:none;white-space:nowrap}
.bv-hot input{appearance:none;width:9px;height:9px;margin:0;border:1px solid rgba(97,186,121,.5);border-radius:2px;background:transparent}
.bv-hot input:checked{background:#67e78e;border-color:#67e78e}
`;

/** Fetch a payload; a .gz URL is inflated in the browser (Python's http.server sends it raw). */
export async function loadPayload(url) {
  const response = await fetch(url);
  if (!response.ok) throw Error(`${url}: ${response.status}`);
  if (/\.gz$/.test(url)) {
    if (typeof DecompressionStream === "undefined") throw Error("no DecompressionStream for a .gz payload");
    return JSON.parse(await new Response(response.body.pipeThrough(new DecompressionStream("gzip"))).text());
  }
  return response.json();
}

function injectStyle() {
  if (document.getElementById("bv-style")) return;
  const style = document.createElement("style");
  style.id = "bv-style";
  style.textContent = STYLE;
  document.head.append(style);
}

const rawColor = (rgb) => new THREE.Color().setRGB(rgb[0], rgb[1], rgb[2]); // stored as given: the renderer's output is linear
const LINES = 1, SOMATA = 2; // the layers the two passes draw
const TONE_VERTEX = "varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }";
const TONE_FRAGMENT = `uniform sampler2D scene; uniform float exposure; uniform vec3 background; varying vec2 vUv;
void main() { vec3 s = texture2D(scene, vUv).rgb; gl_FragColor = vec4(background + (1.0 - exp(-s * exposure)), 1.0); }`;

export class BrainView {
  constructor(container, payload, options = {}) {
    if (payload.format !== "cadence.zebrafish-skeletons/v1") throw Error("Not a zebrafish skeleton payload");
    this.container = container;
    this.payload = payload;
    this.options = { ...DEFAULTS, ...options };
    this.cells = payload.cells;
    this.n = this.cells.length;
    this.classes = payload.classes || CLASSES;
    this.labels = { ...CLASS_LABELS, ...(payload.labels || {}) };
    this.colors = { ...CLASS_COLORS, ...(payload.colors || {}) };  // a payload may bring its own classes and colours
    this.matrixSize = payload.order ? payload.order.length : 0;
    this.filter = null; // a Set of visible classes, or null for all
    this.hotOnly = !!this.options.hotOnly;
    this.activity = null; // the last vector given
    this.level = new Float32Array(this.n); // the display level per skeleton, in [0, 1]
    this.raw = new Float32Array(this.n); // the activity per skeleton as given, for the counts
    this.repair = new Float32Array(this.n); // the repair flash per skeleton, in [0, 1]
    this.peak = 0; // the auto scale's tracked peak
    this.shown = new Uint8Array(this.n).fill(1);
    this.quant = new Uint8Array(this.n); // the level each skeleton was last painted with, in 255ths
    this.quantFlash = new Uint8Array(this.n); // the flash each skeleton was last painted with
    this.painted = new Uint8Array(this.n); // 1 + shown at the last paint, 0 before the first
    this.activeCount = 0; // skeletons at or above HOT
    this.vectorActiveCount = 0; // neurons of the vector at or above HOT
    this.onchange = null; // called with {filter, hotOnly} when the overlay changes them
    this.clock = 0;
    this.lastDrag = -1e9;
    this.pointers = new Map();
    this.fitted = true;
    this.view = { yaw: 0, pitch: 0, dist: 4, panX: 0, panY: 0 };
    this._buildDOM();
    this._buildScene();
    this.setFilter(null);
    this.resize();
  }

  _buildDOM() {
    injectStyle();
    const c = this.container;
    if (getComputedStyle(c).position === "static") c.style.position = "relative";
    this.canvas = document.createElement("canvas");
    this.canvas.className = "bv-canvas";
    c.append(this.canvas);
    this.overlay = document.createElement("div");
    this.overlay.className = "bv-overlay";
    c.append(this.overlay);
    this.checkboxes = {};
    if (this.options.controls) {
      const simple = this.options.controls === "legend"; // the colour key alone: no filter, no counts
      const counts = this.payload.counts?.classes || {};
      const legend = document.createElement("div");
      legend.className = "bv-legend";
      for (const name of this.classes) {
        const label = document.createElement("label");
        if (simple) label.style.cursor = "default";
        const dot = document.createElement("i");
        dot.style.background = `rgb(${(this.colors[name] || CLASS_COLORS.periphery).join(",")})`;
        const text = document.createElement("span");
        text.textContent = this.labels[name] || name;
        if (simple) { label.append(dot, text); legend.append(label); continue; }
        const box = document.createElement("input");
        box.type = "checkbox"; box.checked = true; box.dataset.class = name;
        box.addEventListener("change", () => {
          const on = this.classes.filter((k) => this.checkboxes[k].checked);
          this.setFilter(on.length === this.classes.length ? null : on);
          if (this.onchange) this.onchange({ filter: this.filter, hotOnly: this.hotOnly });
        });
        const count = document.createElement("em");
        count.textContent = (counts[name] ?? 0).toLocaleString();
        label.append(box, dot, text, count);
        legend.append(label);
        this.checkboxes[name] = box;
      }
      if (simple) { this.overlay.append(legend); this._setupInteraction(); return; }
      const status = document.createElement("div");
      status.className = "bv-status";
      this.activeLabel = document.createElement("div");
      this.activeLabel.className = "bv-active";
      const hot = document.createElement("label");
      hot.className = "bv-hot";
      this.hotBox = document.createElement("input");
      this.hotBox.type = "checkbox"; this.hotBox.checked = this.hotOnly;
      this.hotBox.addEventListener("change", () => { this.setHotOnly(this.hotBox.checked); if (this.onchange) this.onchange({ filter: this.filter, hotOnly: this.hotOnly }); });
      hot.append(this.hotBox, document.createTextNode(`hot only (≥ ${HOT})`));
      status.append(this.activeLabel, hot);
      this.overlay.append(legend, status);
    }
    this._setupInteraction();
  }

  _buildScene() {
    const o = this.options;
    this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas, antialias: false, alpha: false, powerPreference: "high-performance" });
    this.renderer.outputColorSpace = THREE.LinearSRGBColorSpace; // colours written are colours shown
    this.renderer.toneMapping = THREE.NoToneMapping;
    this.renderer.setPixelRatio(Math.min(devicePixelRatio || 1, o.dpr));
    this.renderer.setClearColor(0x000000, 1); // the lines accumulate from zero; the background enters in the tone map
    this.scene = new THREE.Scene();
    // the accumulation target and the tone-map quad; without float targets the sum clips at 1 before the knee
    const floatTargets = this.renderer.capabilities.isWebGL2 && (this.renderer.extensions.has("EXT_color_buffer_float") || this.renderer.extensions.has("EXT_color_buffer_half_float"));
    this.target = new THREE.WebGLRenderTarget(1, 1, { type: floatTargets ? THREE.HalfFloatType : THREE.UnsignedByteType, format: THREE.RGBAFormat, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter, depthBuffer: false, stencilBuffer: false, generateMipmaps: false });
    this.toneMaterial = new THREE.ShaderMaterial({
      uniforms: { scene: { value: this.target.texture }, exposure: { value: o.exposure }, background: { value: new THREE.Vector3(...o.background) } },
      vertexShader: TONE_VERTEX, fragmentShader: TONE_FRAGMENT, depthTest: false, depthWrite: false,
    });
    this.toneScene = new THREE.Scene();
    this.toneScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.toneMaterial));
    this.toneCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    this._size = new THREE.Vector2();
    this.group = new THREE.Group(); // the whole anatomy; the orbit rotates it
    this.group.rotation.order = "XYZ";
    this.scene.add(this.group);
    this.camera = new THREE.PerspectiveCamera(o.fov, 1, 0.02, 60);

    // the merged line geometry: one segment per node with a parent, every skeleton a contiguous vertex range
    const cells = this.cells;
    let segments = 0;
    for (const cell of cells) segments += cell.n - 1;
    this.segments = segments;
    const positions = new Float32Array(segments * 6);
    this.colors = new Uint8Array(segments * 6);
    this.vertexStart = new Uint32Array(this.n);
    this.vertexCount = new Uint32Array(this.n);
    this.matrixIndex = new Int32Array(this.n);
    this.classIndex = new Uint8Array(this.n);
    this.roots = new Float32Array(this.n * 3);
    let radius = 0, v = 0;
    const half = [0, 0, 0]; // the half-extents of the anatomy, for the frame
    cells.forEach((cell, i) => {
      const xyz = cell.xyz, parent = cell.parent;
      this.vertexStart[i] = v;
      this.matrixIndex[i] = cell.index ?? -1;
      this.classIndex[i] = Math.max(0, this.classes.indexOf(cell.class));
      this.roots.set([xyz[0], xyz[1], xyz[2]], 3 * i);
      for (let k = 0; k < cell.n; k++) {
        const p = parent[k];
        const r = Math.hypot(xyz[3 * k], xyz[3 * k + 1], xyz[3 * k + 2]);
        if (r > radius) radius = r;
        for (let d = 0; d < 3; d++) { const e = Math.abs(xyz[3 * k + d]); if (e > half[d]) half[d] = e; }
        if (p < 0) continue;
        positions[3 * v] = xyz[3 * p]; positions[3 * v + 1] = xyz[3 * p + 1]; positions[3 * v + 2] = xyz[3 * p + 2];
        positions[3 * v + 3] = xyz[3 * k]; positions[3 * v + 4] = xyz[3 * k + 1]; positions[3 * v + 5] = xyz[3 * k + 2];
        v += 2;
      }
      this.vertexCount[i] = v - this.vertexStart[i];
    });
    this.radius = radius || 1;
    this.half = half;
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    this.colorAttribute = new THREE.BufferAttribute(this.colors, 3, true);
    this.colorAttribute.setUsage(THREE.DynamicDrawUsage);
    geometry.setAttribute("color", this.colorAttribute);
    geometry.computeBoundingSphere();
    this.lines = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ vertexColors: true, blending: THREE.AdditiveBlending, transparent: true, depthTest: false, depthWrite: false, toneMapped: false }));
    this.lines.layers.set(LINES);
    this.group.add(this.lines);

    // the somata: one instanced sphere per skeleton, coloured by class, swelling and whitening with activity
    this.somata = new THREE.InstancedMesh(new THREE.SphereGeometry(1, 10, 7), new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: false }), this.n);
    this.somata.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.somata.frustumCulled = false;
    this.somata.layers.set(SOMATA);
    this._matrix = new THREE.Matrix4();
    this._color = new THREE.Color();
    for (let i = 0; i < this.n; i++) this.somata.setColorAt(i, this._color.setRGB(0, 0, 0));
    this.group.add(this.somata);
    this._paintAll();
  }

  // ---- colours: the only thing a frame updates ----

  /** Paint skeleton i from its level and visibility: its vertex colours and its soma. */
  _paint(i) {
    const o = this.options, a = this.level[i], f = this.repair[i], on = this.shown[i];
    let r = 0, g = 0, b = 0;
    if (on) { r = o.rest[0] + (o.lit[0] - o.rest[0]) * a + o.flash[0] * f; g = o.rest[1] + (o.lit[1] - o.rest[1]) * a + o.flash[1] * f; b = o.rest[2] + (o.lit[2] - o.rest[2]) * a + o.flash[2] * f; }
    const R = Math.min(255, Math.round(255 * r)), G = Math.min(255, Math.round(255 * g)), B = Math.min(255, Math.round(255 * b));
    const c = this.colors, s = 3 * this.vertexStart[i], e = s + 3 * this.vertexCount[i];
    for (let k = s; k < e; k += 3) { c[k] = R; c[k + 1] = G; c[k + 2] = B; }
    const cls = this.colors[this.classes[this.classIndex[i]]] || CLASS_COLORS.periphery;
    const point = this.vertexCount[i] === 0, lift = Math.max(a, f); // a cell drawn as a point alone sits dim and small until it moves
    const dim = point ? o.pointDim + (1 - o.pointDim) * lift : 1;
    const w = 0.55 * lift; // toward white with activity, and with a repair
    this._color.setRGB(dim * ((cls[0] / 255) * 0.8 * (1 - w) + w), dim * ((cls[1] / 255) * 0.8 * (1 - w) + w), dim * ((cls[2] / 255) * 0.8 * (1 - w) + w));
    this.somata.setColorAt(i, this._color);
    const size = on ? o.somaRadius * (point ? o.pointRadius + (1 - o.pointRadius) * lift : 1) * (1 + 0.8 * a + 1.2 * f) : 0;
    this._matrix.makeScale(size, size, size).setPosition(this.roots[3 * i], this.roots[3 * i + 1], this.roots[3 * i + 2]);
    this.somata.setMatrixAt(i, this._matrix);
    this.quant[i] = Math.round(255 * a);
    this.quantFlash[i] = Math.round(255 * f);
    this.painted[i] = 1 + on;
  }

  _paintAll() {
    for (let i = 0; i < this.n; i++) this._paint(i);
    this.colorAttribute.clearUpdateRanges?.();
    this.fullUpload = true;
    this.colorAttribute.needsUpdate = true;
    this.somata.instanceMatrix.needsUpdate = true;
    this.somata.instanceColor.needsUpdate = true;
    this._count();
  }

  /** Repaint the skeletons whose level or visibility changed; adjacent ones share one upload range. */
  _paintChanged() {
    const ranges = [];
    let start = -1, end = 0, changed = 0;
    for (let i = 0; i < this.n; i++) {
      const same = this.painted[i] === 1 + this.shown[i] && this.quant[i] === Math.round(255 * this.level[i]) && this.quantFlash[i] === Math.round(255 * this.repair[i]);
      if (same) continue;
      this._paint(i);
      changed++;
      const s = 3 * this.vertexStart[i], e = s + 3 * this.vertexCount[i];
      if (start >= 0 && s === end) end = e;
      else { if (start >= 0) ranges.push([start, end - start]); start = s; end = e; }
    }
    if (start >= 0) ranges.push([start, end - start]);
    if (!changed) return;
    this._upload(ranges);
    this.somata.instanceMatrix.needsUpdate = true;
    this.somata.instanceColor.needsUpdate = true;
    this._count();
  }

  /** Queue vertex colour ranges for the next render. Ranges accumulate across calls until
   *  three.js uploads them (it clears them after the upload); too many of them, or an
   *  older three.js, and the whole array goes up instead, which stays decided until the
   *  next render so a later call cannot narrow it back down. */
  _upload(ranges) {
    const attr = this.colorAttribute;
    if (attr.addUpdateRange && !this.fullUpload) {
      if (attr.updateRanges.length + ranges.length > 256) { attr.clearUpdateRanges(); this.fullUpload = true; }
      else for (const [s, n] of ranges) attr.addUpdateRange(s, n);
    }
    attr.needsUpdate = true;
  }

  _count() {
    let active = 0;
    for (let i = 0; i < this.n; i++) if (this.raw[i] >= HOT) active++;
    this.activeCount = active;
    if (this.activeLabel) {
      const vector = this.activity ? ` · ${this.vectorActiveCount.toLocaleString()} of ${this.matrixSize.toLocaleString()}` : "";
      this.activeLabel.innerHTML = `active <b>${active.toLocaleString()}</b> / ${this.n.toLocaleString()}${vector}`;
      this.activeLabel.title = `${active} skeletons at or above ${HOT}${this.activity ? `; ${this.vectorActiveCount} of the ${this.matrixSize} neurons in the vector` : ""}`;
    }
  }

  _visible(i) {
    if (this.filter && !this.filter.has(this.classes[this.classIndex[i]])) return 0;
    if (this.hotOnly && this.raw[i] < HOT) return 0;
    return 1;
  }

  // ---- the interface ----

  /** The live activity: one float per neuron in the matrix order, clamped to [0, 1]; `repair`,
   *  when given, one float per neuron in [0, 1] that flashes the cell toward white. */
  setActivity(activity, repair = null) {
    this.activity = activity;
    const m = activity.length, o = this.options;
    let vectorActive = 0, top = 0;
    for (let k = 0; k < m; k++) { const a = activity[k]; if (a >= HOT) vectorActive++; if (a > top) top = a; }
    this.vectorActiveCount = vectorActive;
    if (o.scale === "auto") this.peak = Math.max(o.floor, top, this.peak * o.release);
    const scale = o.scale === "auto" ? this.peak : o.scale, gamma = o.gamma, gain = o.gain;
    for (let i = 0; i < this.n; i++) {
      const k = this.matrixIndex[i];
      let a = k >= 0 && k < m ? activity[k] : 0;
      a = a > 1 ? 1 : a < 0 || a !== a ? 0 : a;
      this.raw[i] = a;
      let l = (a * gain) / scale; if (l > 1) l = 1;
      this.level[i] = gamma === 1 ? l : Math.pow(l, gamma);
      let f = repair && k >= 0 && k < m ? repair[k] : 0;
      f = f > 1 ? 1 : f < 0 || f !== f ? 0 : f;
      this.repair[i] = f;
      this.shown[i] = this._visible(i);
    }
    this._paintChanged();
  }

  /** The classes to draw: a Set or array of class names, or null for all. */
  setFilter(classes) {
    this.filter = classes == null ? null : new Set(classes);
    for (const name of this.classes) {
      const box = this.checkboxes[name];
      if (!box) continue;
      box.checked = !this.filter || this.filter.has(name);
      box.parentElement.classList.toggle("off", !box.checked);
    }
    for (let i = 0; i < this.n; i++) this.shown[i] = this._visible(i);
    this._paintChanged();
  }

  /** Hide the neurons below HOT. */
  setHotOnly(flag) {
    this.hotOnly = !!flag;
    if (this.hotBox) this.hotBox.checked = this.hotOnly;
    for (let i = 0; i < this.n; i++) this.shown[i] = this._visible(i);
    this._paintChanged();
  }

  /** The shown skeleton whose soma projects nearest to the screen point (NDC, x right, y up),
   *  within `radius` CSS pixels; ties go to the nearer soma. Returns {cell, index, id, class,
   *  distance} with `cell` the position in payload.cells and `index` the matrix index (-1 when
   *  the cell is not in the matrix), or null when nothing is within the radius. */
  pick(ndcX, ndcY, radius = 14) {
    this.group.updateMatrixWorld(true);
    this.camera.updateMatrixWorld(true);
    const w = Math.max(1, this.canvas.clientWidth) / 2, h = Math.max(1, this.canvas.clientHeight) / 2;
    const p = this._pickPoint || (this._pickPoint = new THREE.Vector3());
    let best = -1, bestD = radius * radius, bestZ = Infinity;
    for (let i = 0; i < this.n; i++) {
      if (!this.shown[i]) continue;
      p.set(this.roots[3 * i], this.roots[3 * i + 1], this.roots[3 * i + 2]).applyMatrix4(this.group.matrixWorld).project(this.camera);
      if (p.z > 1 || p.z < -1) continue;
      const dx = (p.x - ndcX) * w, dy = (p.y - ndcY) * h, d = dx * dx + dy * dy;
      if (d < bestD || (d === bestD && p.z < bestZ)) { best = i; bestD = d; bestZ = p.z; }
    }
    if (best < 0) return null;
    const cell = this.cells[best];
    return { cell: best, index: this.matrixIndex[best], id: cell.id, class: cell.class, distance: Math.sqrt(bestD) };
  }

  resize() {
    const w = Math.max(1, this.container.clientWidth), h = Math.max(1, this.container.clientHeight);
    this.renderer.setSize(w, h, false);
    this.renderer.getDrawingBufferSize(this._size);
    this.target.setSize(Math.max(1, this._size.x), Math.max(1, this._size.y));
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    if (this.fitted) this._fitDistance();
  }

  /** Back to the resting view: the anatomy from above, anterior up, framed to fit. */
  fit() {
    this.view.yaw = 0; this.view.pitch = 0; this.view.panX = 0; this.view.panY = 0;
    this.fitted = true;
    this._fitDistance();
  }

  /** The distance that fits the anatomy's box at the resting pitch through a full yaw spin:
   *  its height, and the widest silhouette the spin shows, with room for the perspective. */
  _fitDistance() {
    const vertical = Math.tan((this.options.fov / 2) * (Math.PI / 180)), horizontal = vertical * this.camera.aspect;
    const [hx, hy, hz] = this.half;
    const width = Math.hypot(hx, hz), depth = Math.hypot(hx, hz);
    this.view.dist = (Math.max((hy * 1.08) / vertical, (width * 1.08) / horizontal) + depth) * this.options.fitScale;
    this.fitDist = this.view.dist;
  }

  /** Advance the spin by dt seconds and draw a frame: the lines into the accumulation
   *  target, the tone map to the screen, the somata straight on top. */
  render(dt = 0) {
    this.clock += dt;
    if (this.options.spin && this.clock - this.lastDrag > this.options.spinAfter) this.view.yaw += this.options.spinRate * dt;
    this.group.rotation.set(this.view.pitch, this.view.yaw, 0);
    this.camera.position.set(this.view.panX, this.view.panY, this.view.dist);
    this.camera.lookAt(this.view.panX, this.view.panY, 0);
    const r = this.renderer;
    this.toneMaterial.uniforms.exposure.value = this.options.exposure;
    r.setRenderTarget(this.target);
    r.clear(true, false, false);
    this.camera.layers.set(LINES);
    r.render(this.scene, this.camera);
    r.setRenderTarget(null);
    r.render(this.toneScene, this.toneCamera);
    r.autoClear = false;
    r.clear(false, true, false);
    this.camera.layers.set(SOMATA);
    r.render(this.scene, this.camera);
    r.autoClear = true;
    this.fullUpload = false; // the colours are on the GPU; the next change may go up as ranges again
  }

  /** A self-driven loop for pages without one of their own. */
  start() {
    if (this._raf) return;
    let last = performance.now();
    const tick = (now) => { this._raf = requestAnimationFrame(tick); this.render(Math.min(0.1, (now - last) / 1000)); last = now; };
    this._raf = requestAnimationFrame(tick);
  }

  stop() { if (this._raf) cancelAnimationFrame(this._raf); this._raf = 0; }

  dispose() {
    this.stop();
    this._teardownInteraction?.();
    this.lines.geometry.dispose(); this.lines.material.dispose();
    this.somata.geometry.dispose(); this.somata.material.dispose();
    this.toneMaterial.dispose(); this.target.dispose();
    this.renderer.dispose();
    this.canvas.remove(); this.overlay.remove();
  }

  // ---- orbit, zoom, pan ----

  _setupInteraction() {
    const target = this.canvas;
    const worldPerPixel = () => (2 * this.view.dist * Math.tan((this.options.fov / 2) * (Math.PI / 180))) / Math.max(1, target.clientHeight);
    const onWheel = (e) => { e.preventDefault(); this._zoom(Math.exp(e.deltaY * 0.0012)); };
    const onDown = (e) => { target.setPointerCapture(e.pointerId); this.pointers.set(e.pointerId, [e.clientX, e.clientY]); };
    const onMove = (e) => {
      if (!this.pointers.has(e.pointerId)) return;
      const old = this.pointers.get(e.pointerId);
      const dx = e.clientX - old[0], dy = e.clientY - old[1];
      if (this.pointers.size === 1) {
        if (e.shiftKey || e.buttons === 2) { this.view.panX -= dx * worldPerPixel(); this.view.panY += dy * worldPerPixel(); this.fitted = false; }
        else { this.view.yaw += dx * 0.008; this.view.pitch = Math.max(-1.5, Math.min(1.5, this.view.pitch + dy * 0.008)); }
        this.lastDrag = this.clock;
      } else if (this.pointers.size === 2) {
        const [a, b] = [...this.pointers.values()];
        const before = Math.hypot(a[0] - b[0], a[1] - b[1]);
        this.pointers.set(e.pointerId, [e.clientX, e.clientY]);
        const [a2, b2] = [...this.pointers.values()];
        const after = Math.hypot(a2[0] - b2[0], a2[1] - b2[1]);
        if (before > 0 && after > 0) this._zoom(before / after);
        return;
      }
      this.pointers.set(e.pointerId, [e.clientX, e.clientY]);
    };
    const onUp = (e) => this.pointers.delete(e.pointerId);
    const onMenu = (e) => e.preventDefault();
    target.addEventListener("wheel", onWheel, { passive: false });
    target.addEventListener("pointerdown", onDown);
    target.addEventListener("pointermove", onMove);
    for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) target.addEventListener(type, onUp);
    target.addEventListener("contextmenu", onMenu);
    this._teardownInteraction = () => {
      target.removeEventListener("wheel", onWheel);
      target.removeEventListener("pointerdown", onDown);
      target.removeEventListener("pointermove", onMove);
      for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) target.removeEventListener(type, onUp);
      target.removeEventListener("contextmenu", onMenu);
    };
  }

  _zoom(factor) {
    const base = this.fitDist || this.view.dist;
    this.view.dist = Math.max(0.15 * base, Math.min(4 * base, this.view.dist * factor));
    this.fitted = false;
    this.lastDrag = this.clock;
  }
}
