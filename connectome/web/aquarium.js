// The aquarium in the Matrix: a glass tank of 20 by 10 by 10 mm as green wireframe in a black
// void, the water surface with its grid and ripple, the floor with the optomotor stripes, a lamp
// that moves, paramecia drifting, a tap on the glass, the camera. three.js, millimetres.
//
// Physics coordinates are x along the long glass, y along the short glass, z up (body.js).
// Everything in the tank lives inside `aquarium.world`, a group rotated so those coordinates
// apply unchanged; the camera lives in three.js coordinates, converted with toThree().
//
// The page drives it: aquarium.render(dt, fishPosition) once per frame.
import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { TANK, WATER, tapPosition } from "./body.js";

export const toThree = (x, y, z) => new THREE.Vector3(x, z, -y);
export const fromThree = (v) => [v.x, -v.z, v.y];

export const MATRIX = {
  background: 0x010603, edge: 0x39ff6a, bright: 0x9dffb0, dim: 0x1f8a3c, fill: 0x03150a,
  prey: 0xe8fff0, lamp: 0xd8ffe4, water: 0x39ff6a, rain: "#39ff6a", rainHead: "#d8ffe4",
};

export const STRIPE_PERIOD = 4;     // mm, one bright and one dark bar
export const PREY_MAX = 64;
export const PREY_SPEED = [0.3, 0.6]; // mm/s, a paramecium's drift
export const CAMERA = { distance: 26, follow: 9, min: 3, max: 90 };

const TWO_PI = Math.PI * 2;

// -- materials --------------------------------------------------------------------------------
// Lines are additive and never write depth; fills are dim, write depth and draw first, so the
// body of a shape hides the lines behind it.

const lineCache = new Map(), fillCache = new Map();
export function lineMaterial(color = MATRIX.edge, opacity = 0.9) {
  const key = color + ":" + opacity;
  if (!lineCache.has(key)) lineCache.set(key, new THREE.LineBasicMaterial({ color, transparent: true, opacity, blending: THREE.AdditiveBlending, depthWrite: false }));
  return lineCache.get(key);
}
export function fillMaterial(color = MATRIX.fill, opacity = 0.7) {
  const key = color + ":" + opacity;
  if (!fillCache.has(key)) fillCache.set(key, new THREE.MeshLambertMaterial({ color, emissive: color, emissiveIntensity: 0.6, transparent: true, opacity, depthWrite: true }));
  return fillCache.get(key);
}

// A shape as a dim fill and glowing edges. Returns the group with .fill and .edges.
export function wire(geometry, edgeColor = MATRIX.edge, edgeOpacity = 0.9, fillColor = MATRIX.fill, fillOpacity = 0.7, threshold = 1) {
  const g = new THREE.Group();
  g.fill = new THREE.Mesh(geometry, fillMaterial(fillColor, fillOpacity)); g.fill.renderOrder = 0;
  g.edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry, threshold), lineMaterial(edgeColor, edgeOpacity)); g.edges.renderOrder = 1;
  g.add(g.fill, g.edges);
  return g;
}

// Line segments from a flat array of xyz pairs.
export function segments(points, color = MATRIX.edge, opacity = 0.9, material = null) {
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(points, 3));
  const l = new THREE.LineSegments(g, material || lineMaterial(color, opacity)); l.renderOrder = 1;
  return l;
}

const seg = (out, a, b) => { out.push(a[0], a[1], a[2], b[0], b[1], b[2]); };
const boxEdges = (out, x0, x1, y0, y1, z0, z1) => {
  for (const z of [z0, z1]) { seg(out, [x0, y0, z], [x1, y0, z]); seg(out, [x1, y0, z], [x1, y1, z]); seg(out, [x1, y1, z], [x0, y1, z]); seg(out, [x0, y1, z], [x0, y0, z]); }
  for (const [x, y] of [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]) seg(out, [x, y, z0], [x, y, z1]);
};

// -- textures ---------------------------------------------------------------------------------

export function canvasTexture(w, h, draw, srgb = true) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  draw(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export function hash(n) { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); }

export function radialTexture(inner, outer) {
  return canvasTexture(128, 128, (g, w, h) => {
    const r = g.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
    r.addColorStop(0, inner); r.addColorStop(1, outer);
    g.fillStyle = r; g.fillRect(0, 0, w, h);
  });
}

let _dot = null;
export function dotTexture() {
  if (_dot) return _dot;
  _dot = canvasTexture(64, 64, (g, w, h) => {
    const r = g.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
    r.addColorStop(0, "rgba(255,255,255,1)"); r.addColorStop(0.3, "rgba(255,255,255,.7)"); r.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = r; g.fillRect(0, 0, w, h);
  }, false);
  return _dot;
}

// The digital rain: columns of glyphs falling down a canvas, stepped about ten times a second.
function digitalRain(cols = 96, rows = 48) {
  const cw = 10, ch = 14, W = cols * cw, H = rows * ch;
  const c = document.createElement("canvas"); c.width = W; c.height = H;
  const g = c.getContext("2d");
  g.fillStyle = "#000"; g.fillRect(0, 0, W, H);
  const glyphs = "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ0123456789Z:・=*+-<>";
  const heads = new Float32Array(cols), speeds = new Float32Array(cols), tails = new Float32Array(cols);
  for (let i = 0; i < cols; i++) { heads[i] = -Math.floor(hash(i) * rows * 2); speeds[i] = 0.6 + 0.9 * hash(i + 99); tails[i] = 8 + 14 * hash(i + 199); }
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
  const pick = () => glyphs[Math.floor(Math.random() * glyphs.length)];
  const step = () => {
    g.fillStyle = "rgba(0,0,0,0.14)"; g.fillRect(0, 0, W, H);
    g.font = "bold 12px ui-monospace, Menlo, monospace"; g.textAlign = "center"; g.textBaseline = "top";
    for (let i = 0; i < cols; i++) {
      const row = Math.floor(heads[i]);
      if (row >= 0 && row < rows) {
        g.fillStyle = MATRIX.rain; g.fillText(pick(), i * cw + cw / 2, (row - 1) * ch);
        g.fillStyle = MATRIX.rainHead; g.fillText(pick(), i * cw + cw / 2, row * ch);
      }
      if (Math.random() < 0.06) { const rr = Math.floor(Math.random() * rows); g.fillStyle = "rgba(57,255,106,.55)"; g.fillText(pick(), i * cw + cw / 2, rr * ch); }
      heads[i] += speeds[i];
      if (heads[i] > rows + tails[i]) { heads[i] = -Math.floor(Math.random() * rows); speeds[i] = 0.6 + 0.9 * Math.random(); }
    }
    tex.needsUpdate = true;
  };
  for (let k = 0; k < 40; k++) step();
  return { tex, step };
}

// -- renderer and bloom -----------------------------------------------------------------------

export function createRenderer(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.shadowMap.enabled = false;
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.0;
  renderer.setClearColor(MATRIX.background, 1);
  return renderer;
}

// Bloom tuned for lines: the dim grids stay below the threshold, the bright edges glow. Softer
// than the fly's room, whose lines are sparser in the frame.
export function createComposer(renderer, scene, camera, strength = 0.35, threshold = 0.6) {
  const composer = new EffectComposer(renderer);
  const render = new RenderPass(scene, camera);
  const bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), strength, 0.4, threshold);
  composer.addPass(render); composer.addPass(bloom); composer.addPass(new OutputPass());
  return { composer, render, bloom };
}

// -- the aquarium -----------------------------------------------------------------------------

export class Aquarium {
  constructor(container, options = {}) {
    const [W, D, H] = TANK;
    this.container = container;
    const canvas = document.createElement("canvas");
    canvas.style.cssText = "display:block;width:100%;height:100%;touch-action:none;cursor:grab";
    container.appendChild(canvas);
    this.canvas = canvas;
    this.renderer = createRenderer(canvas);
    this.scene = new THREE.Scene(); this.scene.background = new THREE.Color(0x000000);
    this.world = new THREE.Group(); this.world.rotation.x = -Math.PI / 2; this.scene.add(this.world);
    this.tank = new THREE.Group(); this.world.add(this.tank);      // what a tap shakes
    this.camera = new THREE.PerspectiveCamera(42, 1, 0.05, 400);
    this.rig = { target: new THREE.Vector3(W / 2, D / 2, WATER / 2), az: -0.35, el: 0.4, d: CAMERA.distance, dWant: CAMERA.distance, follow: false, first: true };
    this.animations = [];                                           // (dt, time) => void
    this.clock = 0;
    this.stripes = { on: false, speed: 5, direction: 1 };
    this.light = { on: true, x: W / 2, y: D / 2, z: H + 3 };
    this.prey = new Map(); this.nextPreyId = 1;
    this.taps = [];
    this.shake = 0;
    this._build();
    this.composer = null;
    if (options.bloom !== false) { const c = createComposer(this.renderer, this.scene, this.camera, options.bloomStrength, options.bloomThreshold); this.composer = c.composer; this.bloom = c.bloom; }
    this._pointers();
    this._onResize = () => this.resize();
    addEventListener("resize", this._onResize);
    this.resize();
  }

  get following() { return this.rig.follow; }

  _build() {
    const [W, D, H] = TANK, tank = this.tank, world = this.world;

    // the void: a black shell far outside, so the page's background never shows
    const voidBox = new THREE.Mesh(new THREE.BoxGeometry(400, 400, 400), new THREE.MeshBasicMaterial({ color: MATRIX.background, side: THREE.BackSide }));
    voidBox.position.set(W / 2, D / 2, H / 2); world.add(voidBox);

    // the digital rain as a backdrop behind the tank
    {
      const rain = digitalRain();
      const mat = new THREE.MeshBasicMaterial({ map: rain.tex, transparent: true, opacity: 0.35, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });
      const back = new THREE.Mesh(new THREE.PlaneGeometry(90, 45), mat);
      back.rotation.x = Math.PI / 2; back.position.set(W / 2, D + 14, H / 2 + 2); back.renderOrder = 1; world.add(back);
      let due = 0;
      this.animations.push((dt) => { due += dt; if (due >= 0.1) { due = 0; rain.step(); } });
      this.rain = rain;
    }

    // the floor: a dim fill the lamp lights, a grid with minor lines every millimetre
    {
      const floor = new THREE.Mesh(new THREE.PlaneGeometry(W, D), fillMaterial(MATRIX.fill, 0.7));
      floor.position.set(W / 2, D / 2, -0.01); floor.renderOrder = 0; tank.add(floor);
      const minor = [], major = [];
      for (let i = 0; i <= W; i++) seg(i % 5 ? minor : major, [i, 0, 0], [i, D, 0]);
      for (let j = 0; j <= D; j++) seg(j % 5 ? minor : major, [0, j, 0], [W, j, 0]);
      tank.add(segments(minor, MATRIX.edge, 0.1), segments(major, MATRIX.edge, 0.3));
    }

    // the optomotor stripes on the floor: bars across x, moved by sliding the texture
    {
      const bars = Math.round(W / STRIPE_PERIOD);
      this.stripeTexture = canvasTexture(1024, 64, (g, w, h) => {
        g.fillStyle = "#000"; g.fillRect(0, 0, w, h);
        const pw = w / bars;
        for (let i = 0; i < bars; i++) { g.fillStyle = "rgba(57,255,106,0.95)"; g.fillRect(i * pw, 0, pw / 2, h); }
      });
      this.stripeTexture.wrapS = THREE.RepeatWrapping; this.stripeTexture.wrapT = THREE.ClampToEdgeWrapping;
      this.stripeMesh = new THREE.Mesh(new THREE.PlaneGeometry(W, D), new THREE.MeshBasicMaterial({ map: this.stripeTexture, transparent: true, opacity: 0.3, blending: THREE.AdditiveBlending, depthWrite: false }));
      this.stripeMesh.position.set(W / 2, D / 2, 0.015); this.stripeMesh.renderOrder = 1; this.stripeMesh.visible = false; tank.add(this.stripeMesh);
      this.animations.push((dt) => { if (this.stripes.on) this.stripeTexture.offset.x -= this.stripes.direction * this.stripes.speed / W * dt; });
    }

    // the glass: the tank's edges bright, sparse lines across the panes, faint panes that can flash
    {
      const edges = [], sparse = [];
      boxEdges(edges, 0, W, 0, D, 0, H);
      for (const z of [2, 4, 6, 8]) { seg(sparse, [0, 0, z], [W, 0, z]); seg(sparse, [0, D, z], [W, D, z]); seg(sparse, [0, 0, z], [0, D, z]); seg(sparse, [W, 0, z], [W, D, z]); }
      for (let x = 5; x < W; x += 5) { seg(sparse, [x, 0, 0], [x, 0, H]); seg(sparse, [x, D, 0], [x, D, H]); }
      for (let y = 5; y < D; y += 5) { seg(sparse, [0, y, 0], [0, y, H]); seg(sparse, [W, y, 0], [W, y, H]); }
      tank.add(segments(edges, MATRIX.edge, 0.75), segments(sparse, MATRIX.edge, 0.1));
      const pane = () => new THREE.MeshBasicMaterial({ color: MATRIX.edge, transparent: true, opacity: 0.025, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });
      this.panes = [];
      for (const [x, side] of [[0, -1], [W, 1]]) {
        const m = new THREE.Mesh(new THREE.PlaneGeometry(H, D), pane());
        m.rotation.y = Math.PI / 2; m.position.set(x, D / 2, H / 2); m.renderOrder = 1; m.userData.side = side; tank.add(m); this.panes.push(m);
      }
      for (const y of [0, D]) {
        const m = new THREE.Mesh(new THREE.PlaneGeometry(W, H), pane());
        m.rotation.x = Math.PI / 2; m.position.set(W / 2, y, H / 2); m.renderOrder = 1; tank.add(m);
      }
      // the rings of a tap, three per pane, reused
      const ringPts = [];
      for (let i = 0; i < 40; i++) { const a0 = i / 40 * TWO_PI, a1 = (i + 1) / 40 * TWO_PI; ringPts.push(Math.cos(a0), Math.sin(a0), 0, Math.cos(a1), Math.sin(a1), 0); }
      this.tapRings = this.panes.map((p) => [0, 1, 2].map(() => {
        const mat = new THREE.LineBasicMaterial({ color: MATRIX.bright, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false });
        const r = segments(ringPts, MATRIX.bright, 0, mat);
        r.rotation.y = Math.PI / 2; const q = tapPosition(p.userData.side); r.position.set(q[0], q[1], q[2]); r.visible = false; tank.add(r);
        return r;
      }));
    }

    // the water surface: a rippling grid, a faint fill, the water line on the glass
    {
      const N = 1;                                                  // segments per millimetre
      const lines = [];
      for (let i = 0; i <= W; i++) for (let k = 0; k < D * N; k++) lines.push([i, k / N, i, (k + 1) / N]);
      for (let j = 0; j <= D; j++) for (let k = 0; k < W * N; k++) lines.push([k / N, j, (k + 1) / N, j]);
      this.surfacePos = new Float32Array(6 * lines.length);
      this.surfaceXY = lines;
      const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.BufferAttribute(this.surfacePos, 3));
      this.surface = new THREE.LineSegments(geo, lineMaterial(MATRIX.water, 0.12)); this.surface.renderOrder = 1; this.surface.frustumCulled = false; tank.add(this.surface);
      const fill = new THREE.Mesh(new THREE.PlaneGeometry(W, D), new THREE.MeshBasicMaterial({ color: MATRIX.water, transparent: true, opacity: 0.05, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
      fill.position.set(W / 2, D / 2, WATER); fill.renderOrder = 1; tank.add(fill);
      const line = []; boxEdges(line, 0, W, 0, D, WATER, WATER);
      tank.add(segments(line, MATRIX.bright, 0.5));
      this.animations.push((dt, time) => this._ripple(time));
      this._ripple(0);
    }

    // the lamp: a bright bulb on a cord, a soft glow, a point light the fills answer to
    {
      const lamp = new THREE.Group();
      lamp.add(segments([0, 0, 0, 0, 0, 10], MATRIX.edge, 0.4));
      const bulb = new THREE.Points(new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute([0, 0, 0], 3)), new THREE.PointsMaterial({ color: MATRIX.lamp, size: 10, sizeAttenuation: false, map: dotTexture(), transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }));
      bulb.renderOrder = 2; lamp.add(bulb);
      const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: radialTexture("rgba(57,255,106,.5)", "rgba(57,255,106,0)"), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0.8 }));
      glow.scale.set(3, 3, 1); lamp.add(glow);
      const light = new THREE.PointLight(MATRIX.edge, 140, 0, 2); lamp.add(light);
      world.add(lamp);
      this.lamp = { group: lamp, bulb, glow, light };
      this.animations.push((dt, time) => { glow.material.opacity = 0.65 + 0.15 * Math.sin(time * 6.3); });
      this.setLight(this.light);
    }
    world.add(new THREE.AmbientLight(MATRIX.edge, 0.35));

    // the prey: bright points with a short body each, drifting slowly through the water
    {
      this.preyPos = new Float32Array(3 * PREY_MAX);
      const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.BufferAttribute(this.preyPos, 3)); geo.setDrawRange(0, 0);
      this.preyPoints = new THREE.Points(geo, new THREE.PointsMaterial({ color: MATRIX.prey, size: 6, sizeAttenuation: false, map: dotTexture(), transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false }));
      this.preyPoints.frustumCulled = false; this.preyPoints.renderOrder = 2; tank.add(this.preyPoints);
      this.preyBodyPos = new Float32Array(6 * PREY_MAX);
      const bgeo = new THREE.BufferGeometry(); bgeo.setAttribute("position", new THREE.BufferAttribute(this.preyBodyPos, 3)); bgeo.setDrawRange(0, 0);
      this.preyBodies = new THREE.LineSegments(bgeo, lineMaterial(MATRIX.prey, 0.8)); this.preyBodies.frustumCulled = false; this.preyBodies.renderOrder = 1; tank.add(this.preyBodies);
      this.animations.push((dt, time) => this._drift(dt, time));
    }

    // motes suspended in the water
    {
      const N = 160, pos = new Float32Array(3 * N), vel = new Float32Array(3 * N), ph = new Float32Array(N);
      for (let i = 0; i < N; i++) { pos[3 * i] = hash(i) * W; pos[3 * i + 1] = hash(i + N) * D; pos[3 * i + 2] = hash(i + 2 * N) * WATER; vel[3 * i] = 0.05 * (hash(i + 3 * N) - 0.5); vel[3 * i + 1] = 0.05 * (hash(i + 4 * N) - 0.5); vel[3 * i + 2] = -0.01 - 0.03 * hash(i + 5 * N); ph[i] = TWO_PI * hash(i + 6 * N); }
      const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      const motes = new THREE.Points(geo, new THREE.PointsMaterial({ color: MATRIX.edge, size: 0.12, map: dotTexture(), transparent: true, opacity: 0.5, depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true }));
      motes.frustumCulled = false; motes.renderOrder = 2; tank.add(motes);
      this.animations.push((dt, time) => {
        for (let i = 0; i < N; i++) {
          pos[3 * i] += (vel[3 * i] + 0.02 * Math.sin(time * 0.2 + ph[i])) * dt; pos[3 * i + 1] += (vel[3 * i + 1] + 0.02 * Math.cos(time * 0.17 + ph[i])) * dt; pos[3 * i + 2] += vel[3 * i + 2] * dt;
          if (pos[3 * i] < 0) pos[3 * i] += W; if (pos[3 * i] > W) pos[3 * i] -= W; if (pos[3 * i + 1] < 0) pos[3 * i + 1] += D; if (pos[3 * i + 1] > D) pos[3 * i + 1] -= D; if (pos[3 * i + 2] < 0) pos[3 * i + 2] += WATER;
        }
        geo.attributes.position.needsUpdate = true;
      });
    }

    // the taps' rings and the glass shaking
    this.animations.push((dt) => this._taps(dt));
  }

  _ripple(time) {
    const pos = this.surfacePos, lines = this.surfaceXY;
    const zAt = (x, y) => WATER + 0.035 * Math.sin(0.9 * x + 2.1 * time) * Math.cos(0.7 * y + 1.4 * time) + 0.02 * Math.sin(1.7 * x - 1.1 * y + 3.0 * time);
    for (let i = 0; i < lines.length; i++) {
      const [x0, y0, x1, y1] = lines[i];
      pos[6 * i] = x0; pos[6 * i + 1] = y0; pos[6 * i + 2] = zAt(x0, y0);
      pos[6 * i + 3] = x1; pos[6 * i + 4] = y1; pos[6 * i + 5] = zAt(x1, y1);
    }
    this.surface.geometry.attributes.position.needsUpdate = true;
  }

  _drift(dt, time) {
    const [W, D] = TANK;
    let i = 0;
    for (const q of this.prey.values()) {
      q.heading += (Math.random() - 0.5) * 2.5 * dt;
      q.pitch += (Math.random() - 0.5) * 1.5 * dt; q.pitch *= 1 - 0.5 * dt;
      q.next -= dt;
      if (q.next <= 0) { q.next = 2 + 3 * Math.random(); q.heading = TWO_PI * Math.random(); q.pitch = 0.8 * (Math.random() - 0.5); }
      const cp = Math.cos(q.pitch);
      q.p[0] += q.speed * cp * Math.cos(q.heading) * dt; q.p[1] += q.speed * cp * Math.sin(q.heading) * dt; q.p[2] += q.speed * Math.sin(q.pitch) * dt;
      if (q.p[0] < 0.3) { q.p[0] = 0.3; q.heading = Math.PI - q.heading; } else if (q.p[0] > W - 0.3) { q.p[0] = W - 0.3; q.heading = Math.PI - q.heading; }
      if (q.p[1] < 0.3) { q.p[1] = 0.3; q.heading = -q.heading; } else if (q.p[1] > D - 0.3) { q.p[1] = D - 0.3; q.heading = -q.heading; }
      if (q.p[2] < 0.3) { q.p[2] = 0.3; q.pitch = Math.abs(q.pitch); } else if (q.p[2] > WATER - 0.3) { q.p[2] = WATER - 0.3; q.pitch = -Math.abs(q.pitch); }
      const bx = 0.11 * cp * Math.cos(q.heading), by = 0.11 * cp * Math.sin(q.heading), bz = 0.11 * Math.sin(q.pitch);
      this.preyPos[3 * i] = q.p[0]; this.preyPos[3 * i + 1] = q.p[1]; this.preyPos[3 * i + 2] = q.p[2];
      this.preyBodyPos[6 * i] = q.p[0] - bx; this.preyBodyPos[6 * i + 1] = q.p[1] - by; this.preyBodyPos[6 * i + 2] = q.p[2] - bz;
      this.preyBodyPos[6 * i + 3] = q.p[0] + bx; this.preyBodyPos[6 * i + 4] = q.p[1] + by; this.preyBodyPos[6 * i + 5] = q.p[2] + bz;
      i++;
    }
    this.preyPoints.geometry.setDrawRange(0, i); this.preyPoints.geometry.attributes.position.needsUpdate = true;
    this.preyBodies.geometry.setDrawRange(0, 2 * i); this.preyBodies.geometry.attributes.position.needsUpdate = true;
    this.preyPoints.material.opacity = 0.75 + 0.2 * Math.sin(time * 9.0);
  }

  _taps(dt) {
    for (const t of this.taps) t.t += dt;
    this.taps = this.taps.filter((t) => t.t < 0.8);
    for (const pane of this.panes) {
      const side = pane.userData.side, rings = this.tapRings[side < 0 ? 0 : 1];
      const tap = this.taps.find((t) => t.side === side);
      pane.material.opacity = 0.025 + (tap ? 0.3 * Math.exp(-tap.t / 0.12) : 0);
      rings.forEach((r, k) => {
        const radius = tap ? Math.max(0, tap.t - 0.09 * k) * 14 : 0;
        r.visible = radius > 0 && radius < 7;
        if (r.visible) { r.scale.set(radius, radius, 1); r.material.opacity = 0.8 * (1 - radius / 7); }
      });
    }
    if (this.shake > 0) {
      this.shake -= dt;
      if (this.shake > 0) this.tank.position.set(0.05 * (Math.random() - 0.5), 0.05 * (Math.random() - 0.5), 0.02 * (Math.random() - 0.5));
      else this.tank.position.set(0, 0, 0);
    }
  }

  // -- the controls ---------------------------------------------------------------------------

  setStripes(opts = {}) {
    if (opts.on != null) this.stripes.on = !!opts.on;
    if (opts.speed != null && Number.isFinite(Number(opts.speed))) this.stripes.speed = Math.max(0, Number(opts.speed));
    if (opts.direction != null) this.stripes.direction = Number(opts.direction) < 0 ? -1 : 1;
    this.stripeMesh.visible = this.stripes.on;
    return { ...this.stripes };
  }

  setLight(opts = {}) {
    for (const k of ["x", "y", "z"]) if (opts[k] != null && Number.isFinite(Number(opts[k]))) this.light[k] = Number(opts[k]);
    if (opts.on != null) this.light.on = !!opts.on;
    const L = this.lamp;
    L.group.position.set(this.light.x, this.light.y, this.light.z);
    L.light.visible = this.light.on; L.bulb.visible = this.light.on; L.glow.visible = this.light.on;
    return { ...this.light };
  }

  // Adds a paramecium at [x, y, z] (mm, inside the water) and returns its id.
  addPrey(position) {
    if (this.prey.size >= PREY_MAX) return null;
    const [W, D] = TANK;
    const p = [Math.min(W - 0.3, Math.max(0.3, position[0])), Math.min(D - 0.3, Math.max(0.3, position[1])), Math.min(WATER - 0.3, Math.max(0.3, position[2]))];
    const id = this.nextPreyId++;
    this.prey.set(id, { id, p, heading: TWO_PI * Math.random(), pitch: 0, speed: PREY_SPEED[0] + (PREY_SPEED[1] - PREY_SPEED[0]) * Math.random(), next: 1 + 3 * Math.random() });
    return id;
  }

  removePrey(id) { return this.prey.delete(id); }

  preyList() { return [...this.prey.values()].map((q) => ({ id: q.id, x: q.p[0], y: q.p[1], z: q.p[2] })); }

  // A tap on the glass: "left" or -1 is the pane at x = 0, "right" or +1 the pane at x = 20.
  tap(side) {
    const s = side === "left" || Number(side) < 0 ? -1 : 1;
    this.taps.push({ side: s, t: 0 });
    this.shake = 0.12;
    return { side: s, position: tapPosition(s), time: this.clock };
  }

  setFollow(on) {
    const r = this.rig;
    r.follow = !!on;
    r.dWant = r.follow ? CAMERA.follow : CAMERA.distance;
    return r.follow;
  }
  toggleFollow() { return this.setFollow(!this.rig.follow); }

  // -- the camera: drag to orbit, wheel to zoom, pinch to zoom --------------------------------

  _pointers() {
    const c = this.canvas, r = this.rig, active = new Map();
    let pinch = 0;
    c.addEventListener("pointerdown", (e) => {
      active.set(e.pointerId, { x: e.clientX, y: e.clientY });
      c.setPointerCapture(e.pointerId); c.style.cursor = "grabbing";
      if (active.size === 2) { const [a, b] = [...active.values()]; pinch = Math.hypot(a.x - b.x, a.y - b.y); }
    });
    c.addEventListener("pointermove", (e) => {
      const p = active.get(e.pointerId); if (!p) return;
      const dx = e.clientX - p.x, dy = e.clientY - p.y; p.x = e.clientX; p.y = e.clientY;
      if (active.size === 1) { r.az -= dx * 0.006; r.el = Math.min(1.5, Math.max(-0.15, r.el + dy * 0.006)); }
      else if (active.size === 2) { const [a, b] = [...active.values()]; const d = Math.hypot(a.x - b.x, a.y - b.y); if (pinch > 0 && d > 0) r.dWant = Math.min(CAMERA.max, Math.max(CAMERA.min, r.dWant * pinch / d)); pinch = d; }
    });
    const up = (e) => { active.delete(e.pointerId); if (active.size === 0) c.style.cursor = "grab"; };
    c.addEventListener("pointerup", up); c.addEventListener("pointercancel", up);
    c.addEventListener("wheel", (e) => { r.dWant = Math.min(CAMERA.max, Math.max(CAMERA.min, r.dWant * Math.exp(e.deltaY * 0.0015))); e.preventDefault(); }, { passive: false });
  }

  _camera(dt, focus) {
    const [W, D] = TANK, r = this.rig, cam = this.camera;
    const want = r.follow && focus ? _want.set(focus[0], focus[1], focus[2]) : _want.set(W / 2, D / 2, WATER / 2);
    const k = r.first ? 1 : 1 - Math.exp(-dt / 0.25);
    r.target.lerp(want, k);
    r.d += (r.dWant - r.d) * (r.first ? 1 : 1 - Math.exp(-dt / 0.3));
    const ce = Math.cos(r.el);
    _pos.set(r.target.x + r.d * ce * Math.sin(r.az), r.target.y - r.d * ce * Math.cos(r.az), r.target.z + r.d * Math.sin(r.el));
    cam.position.copy(toThree(_pos.x, _pos.y, _pos.z)); cam.up.set(0, 1, 0);
    cam.lookAt(toThree(r.target.x, r.target.y, r.target.z));
    cam.near = Math.max(0.02, r.d * 0.01); cam.updateProjectionMatrix();
    r.first = false;
  }

  resize() {
    const w = this.container.clientWidth || innerWidth, h = this.container.clientHeight || innerHeight;
    this.renderer.setSize(w, h, false);
    if (this.composer) { this.composer.setSize(w, h); this.bloom.resolution.set(w / 2, h / 2); }
    this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
  }

  // Advances the water, the prey, the lamp and the taps by dt and draws. `focus` is the fish's
  // position [x, y, z], the orbit's centre when following.
  render(dt, focus = null) {
    dt = Math.min(0.05, Math.max(0, Number(dt) || 0));
    this.clock += dt;
    for (const a of this.animations) a(dt, this.clock);
    this._camera(dt, focus);
    if (this.composer) this.composer.render(); else this.renderer.render(this.scene, this.camera);
  }
}

const _want = new THREE.Vector3(), _pos = new THREE.Vector3();
