// The page: the cell in three.js, the visitor's placements, and the run loop that asks the brain
// (in the worker) for one decision at a time and steps the physics in real time between them.
import * as THREE from 'three';
import { OrbitControls } from './vendor/three/jsm/controls/OrbitControls.js';
import { RoomEnvironment } from './vendor/three/jsm/environments/RoomEnvironment.js';
import { toCreasedNormals } from './vendor/three/jsm/utils/BufferGeometryUtils.js';
import { EffectComposer } from './vendor/three/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from './vendor/three/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from './vendor/three/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from './vendor/three/jsm/postprocessing/OutputPass.js';
import loadMujoco from './vendor/mujoco/mujoco.js';
import { Cell, BIN_SIDE, HOLD, LIFT, SPAWN_X, SPAWN_Y } from './sim.js';
import { BrainView } from './brainview.js';

// Where the visitor may put things: the block within the area it was raised on (plus 2 cm), the
// bins within the band in which this brain was tested to place 19-20 of 20 blocks.
const BLOCK_ZONE = { x: [SPAWN_X[0] - 0.02, SPAWN_X[1] + 0.02], y: [SPAWN_Y[0] - 0.02, SPAWN_Y[1] + 0.02] };
const BIN_ZONE = { x: [0.60, 0.72], y: [-0.33, 0.33] };
const CAP = 120; // decisions per run
const TRAIL = 240; // fingertip positions kept in the trail
const PHYSICS_DT = 0.002;
const $ = (id) => document.getElementById(id);

const ui = { status: $('status'), statusText: $('status-text'), run: $('run'), reset: $('reset'), shuffle: $('shuffle'), toast: $('toast'),
  targetA: $('target-A'), targetB: $('target-B'), sub: $('brain-sub'), decision: $('s-decision'), sweeps: $('s-sweeps'), ms: $('s-ms') };
const state = { phase: 'loading', speed: 1, decision: 0, placement: [0.45, 0.10], target: 'A', budget: 0, brainReady: false, events: [] };
let cell, mujoco, brain, view;

function setStatus(text, kind = 'busy') { ui.statusText.textContent = text; ui.status.className = `status ${kind}`; }
let toastTimer = null;
function toast(text, kind = '', ms = 2200) {
  ui.toast.textContent = text; ui.toast.className = `toast ${kind}`; ui.toast.hidden = false;
  clearTimeout(toastTimer);
  if (ms) toastTimer = setTimeout(() => { ui.toast.hidden = true; }, ms);
}

// --- the brain worker ---------------------------------------------------------------------------
class BrainWorker {
  constructor() {
    this.worker = new Worker(new URL('./worker.js', import.meta.url), { type: 'module' });
    this.rid = 0; this.pending = new Map();
    this.worker.onmessage = ({ data }) => {
      if (data.status) { if (!state.brainReady) setStatus(data.status, 'busy'); return; }
      const p = this.pending.get(data.rid);
      if (!p) return;
      this.pending.delete(data.rid);
      if (data.error) p.reject(new Error(data.error)); else p.resolve(data.result);
    };
  }
  call(command, payload) {
    const rid = ++this.rid;
    return new Promise((resolve, reject) => { this.pending.set(rid, { resolve, reject }); this.worker.postMessage({ rid, command, payload }); });
  }
}

// --- three.js -----------------------------------------------------------------------------------
const canvas = $('scene');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
const scene = new THREE.Scene();
scene.background = new THREE.Color('#0c0e11');
const camera = new THREE.PerspectiveCamera(36, 1, 0.01, 30);
camera.up.set(0, 0, 1);
camera.position.set(1.78, 0.92, 1.08);
const controls = new OrbitControls(camera, canvas);
controls.target.set(0.4, 0.0, 0.2);
controls.enableDamping = true;
controls.maxPolarAngle = Math.PI * 0.47;
controls.minDistance = 0.6; controls.maxDistance = 3.4;
controls.update();

// A studio environment for reflections, turned to MuJoCo's z-up world.
const pmrem = new THREE.PMREMGenerator(renderer);
const room = new RoomEnvironment(renderer);
room.rotation.x = Math.PI / 2;
scene.environment = pmrem.fromScene(room, 0.04).texture;
renderer.toneMappingExposure = 0.9;
const hemi = new THREE.HemisphereLight(0xe8edf5, 0x14171c, 0.35);
hemi.position.set(0, 0, 1);
scene.add(hemi);
const sun = new THREE.DirectionalLight(0xffffff, 1.7);
sun.position.set(1.1, -0.9, 2.2);
sun.target.position.set(0.45, 0, 0);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -1, right: 1, top: 1, bottom: -1, near: 0.5, far: 5 });
sun.shadow.bias = -0.0004;
sun.shadow.normalBias = 0.012;
sun.shadow.camera.updateProjectionMatrix();
scene.add(sun, sun.target);
const fill = new THREE.DirectionalLight(0xa9bcff, 0.6);
fill.position.set(-0.8, 1.2, 1.0);
scene.add(fill);
// The floor: a faint grid fading into the dark, and a shadow catcher above it.
const BG = new THREE.Color('#0c0e11');
const ground = new THREE.Mesh(new THREE.PlaneGeometry(8, 8), new THREE.ShaderMaterial({
  uniforms: { uBg: { value: BG.clone() }, uLine: { value: new THREE.Color('#3a4250') } },
  vertexShader: 'varying vec3 vPos; void main(){ vPos = (modelMatrix * vec4(position, 1.0)).xyz; gl_Position = projectionMatrix * viewMatrix * vec4(vPos, 1.0); }',
  fragmentShader: `varying vec3 vPos; uniform vec3 uBg; uniform vec3 uLine;
    void main(){
      vec2 p = vPos.xy * 10.0;
      vec2 g = abs(fract(p - 0.5) - 0.5) / fwidth(p);
      float line = 1.0 - min(min(g.x, g.y), 1.0);
      float fade = smoothstep(2.4, 0.3, length(vPos.xy - vec2(0.35, 0.0)));
      gl_FragColor = vec4(mix(uBg, uLine, line * fade * 0.55), 1.0);
      #include <colorspace_fragment>
    }`,
}));
ground.position.z = -0.0412;
scene.add(ground);
const catcher = new THREE.Mesh(new THREE.PlaneGeometry(8, 8), new THREE.ShadowMaterial({ opacity: 0.45 }));
catcher.position.z = -0.0405;
catcher.receiveShadow = true;
scene.add(catcher);

// Post-processing: bloom on what glows (the lamp, the target bin, the hand's aim and trail).
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.5, 0.4, 1.6);
composer.addPass(bloom);
composer.addPass(new OutputPass());

// The neural rim light: every Panda surface glows at its edges, brighter while the brain works.
const rim = { color: { value: new THREE.Color('#4fc3f7') }, strength: { value: 0.0 } };
const rimState = { level: 0.0, target: 0.08 };
function withRim(mat) {
  mat.onBeforeCompile = (shader) => {
    shader.uniforms.uRimColor = rim.color;
    shader.uniforms.uRimStrength = rim.strength;
    shader.fragmentShader = 'uniform vec3 uRimColor;\nuniform float uRimStrength;\n' + shader.fragmentShader.replace('#include <emissivemap_fragment>',
      '#include <emissivemap_fragment>\n  float rimDot = 1.0 - abs(dot(normal, normalize(vViewPosition)));\n  totalEmissiveRadiance += uRimColor * pow(rimDot, 2.6) * uRimStrength;');
  };
  mat.customProgramCacheKey = () => 'neural-rim';
  return mat;
}

const mats = new Map();
function material(rgba) { // the Panda's materials by tone: glossy white shell, satin graphite joints
  const key = rgba.map((v) => v.toFixed(3)).join();
  if (!mats.has(key)) {
    const lum = 0.2126 * rgba[0] + 0.7152 * rgba[1] + 0.0722 * rgba[2];
    const color = new THREE.Color().setRGB(rgba[0], rgba[1], rgba[2], THREE.SRGBColorSpace);
    const mat = lum > 0.7
      ? new THREE.MeshPhysicalMaterial({ color: color.lerp(new THREE.Color(0xf4f6f8), 0.3), roughness: 0.3, metalness: 0.0, clearcoat: 0.9, clearcoatRoughness: 0.12, envMapIntensity: 0.55, side: THREE.DoubleSide })
      : new THREE.MeshPhysicalMaterial({ color: lum < 0.15 ? new THREE.Color(0x16191e) : color, roughness: 0.42, metalness: 0.45, clearcoat: 0.35, clearcoatRoughness: 0.3, envMapIntensity: 0.8, side: THREE.DoubleSide });
    mats.set(key, withRim(mat));
  }
  return mats.get(key);
}
const quat = (q) => new THREE.Quaternion(q[1], q[2], q[3], q[0]);

const scenery = { bodies: [], bins: { A: [], B: [] }, lamps: {}, block: null, table: null, pickables: [] };
const binMat = { idle: new THREE.MeshPhysicalMaterial({ color: 0x23272e, roughness: 0.55, metalness: 0.2, clearcoat: 0.4 }),
  target: new THREE.MeshPhysicalMaterial({ color: 0x2c2720, roughness: 0.5, metalness: 0.2, clearcoat: 0.4, emissive: 0xf2b33d, emissiveIntensity: 0.18 }) };
const lampMat = { off: new THREE.MeshPhysicalMaterial({ color: 0x3a3f47, roughness: 0.35, clearcoat: 0.6 }),
  on: new THREE.MeshStandardMaterial({ color: 0xf2b33d, emissive: 0xf2b33d, emissiveIntensity: 6.0, roughness: 0.4 }) };
const hdr = (hex, k) => new THREE.Color(hex).multiplyScalar(k);

function buildPrimitives() {
  const m = cell.model;
  for (let g = 0; g < m.ngeom; g++) {
    const name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM.value, g) || '';
    const size = [m.geom_size[3 * g], m.geom_size[3 * g + 1], m.geom_size[3 * g + 2]];
    let mesh = null;
    if (name === 'table') {
      mesh = new THREE.Mesh(new THREE.BoxGeometry(2 * size[0], 2 * size[1], 2 * size[2]), new THREE.MeshPhysicalMaterial({ color: 0xc9ccd2, roughness: 0.75, clearcoat: 0.1, envMapIntensity: 0.5 }));
      mesh.receiveShadow = true; scenery.table = mesh;
    } else if (name.startsWith('bin_')) {
      mesh = new THREE.Mesh(new THREE.BoxGeometry(2 * size[0], 2 * size[1], 2 * size[2]), binMat.idle);
      mesh.castShadow = true; mesh.receiveShadow = true;
      const bin = name[4];
      mesh.userData = { kind: 'bin', name: bin, geom: g };
      scenery.bins[bin].push(mesh); scenery.pickables.push(mesh);
    } else if (name.startsWith('lamp_')) {
      mesh = new THREE.Mesh(new THREE.SphereGeometry(size[0], 24, 16), lampMat.off);
      scenery.lamps[name[5]] = mesh;
    } else if (name === 'block') {
      mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshPhysicalMaterial({ color: 0xe5484d, roughness: 0.35, clearcoat: 0.8, clearcoatRoughness: 0.2 }));
      mesh.castShadow = true; mesh.userData = { kind: 'block', geom: g };
      scenery.block = mesh; scenery.pickables.push(mesh);
    }
    if (mesh) {
      mesh.userData.geom = g;
      mesh.position.set(m.geom_pos[3 * g], m.geom_pos[3 * g + 1], m.geom_pos[3 * g + 2]);
      scene.add(mesh);
    }
  }
  // what the brain is told: the release point above the target bin, and the hand's commanded point
  scenery.release = new THREE.Mesh(new THREE.SphereGeometry(0.008, 16, 12), new THREE.MeshBasicMaterial({ color: hdr(0xf2b33d, 4.0) }));
  scenery.releaseLine = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]),
    new THREE.LineDashedMaterial({ color: 0xf2b33d, dashSize: 0.01, gapSize: 0.008, transparent: true, opacity: 0.5 }));
  scenery.aim = new THREE.Mesh(new THREE.SphereGeometry(0.0065, 16, 12), new THREE.MeshBasicMaterial({ color: hdr(0x4fc3f7, 5.0) }));
  scenery.aim.visible = false;
  // the hand's path: a fading trail of the fingertip
  const n = TRAIL;
  scenery.trailPos = new Float32Array(n * 3); scenery.trailCol = new Float32Array(n * 3);
  const tg = new THREE.BufferGeometry();
  tg.setAttribute('position', new THREE.BufferAttribute(scenery.trailPos, 3));
  tg.setAttribute('color', new THREE.BufferAttribute(scenery.trailCol, 3));
  scenery.trail = new THREE.Line(tg, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }));
  scenery.trail.frustumCulled = false;
  scenery.trailCount = 0;
  // a glowing outline around the target bin's rim
  const r = BIN_SIDE / 2 + 0.005;
  scenery.rimLine = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints([[-r, -r], [r, -r], [r, r], [-r, r]].map(([x, y]) => new THREE.Vector3(x, y, 0.0405))),
    new THREE.LineBasicMaterial({ color: hdr(0xf2b33d, 3.5), transparent: true }));
  scene.add(scenery.release, scenery.releaseLine, scenery.aim, scenery.trail, scenery.rimLine);
  scenery.zones = {
    block: zoneOutline(BLOCK_ZONE, 0xe5484d),
    bin: zoneOutline(BIN_ZONE, 0xf2b33d),
  };
}

function zoneOutline(z, color) {
  const pts = [[z.x[0], z.y[0]], [z.x[1], z.y[0]], [z.x[1], z.y[1]], [z.x[0], z.y[1]], [z.x[0], z.y[0]]].map(([x, y]) => new THREE.Vector3(x, y, 0.0015));
  const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineDashedMaterial({ color, dashSize: 0.012, gapSize: 0.01, transparent: true, opacity: 0.8 }));
  line.computeLineDistances(); line.visible = false; scene.add(line);
  return line;
}

async function buildPanda() {
  const [index, buffer] = await Promise.all([fetch('assets/panda_visual.json').then((r) => r.json()), fetch('assets/panda_visual.bin').then((r) => r.arrayBuffer())]);
  const V = new Float32Array(buffer, 0, index.vertices * 3);
  const I = new Uint32Array(buffer, index.vertices * 12, index.indices);
  const groups = new Map();
  for (const e of index.geoms) {
    if (!groups.has(e.body)) {
      const group = new THREE.Group();
      const id = mujoco.mj_name2id(cell.model, mujoco.mjtObj.mjOBJ_BODY.value, e.body);
      groups.set(e.body, group); scenery.bodies.push({ id, group }); scene.add(group);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(V.slice(e.voff * 3, (e.voff + e.vcount) * 3), 3));
    geometry.setIndex(new THREE.BufferAttribute(I.slice(e.ioff, e.ioff + e.icount), 1));
    const creased = toCreasedNormals(geometry, (35 * Math.PI) / 180); // smooth faces, sharp edges
    const mesh = new THREE.Mesh(creased, material(e.rgba));
    mesh.position.set(...e.pos); mesh.quaternion.copy(quat(e.quat));
    mesh.castShadow = true;
    groups.get(e.body).add(mesh);
  }
}

function syncScene() {
  const d = cell.data, m = cell.model;
  for (const { id, group } of scenery.bodies) {
    group.position.set(d.xpos[3 * id], d.xpos[3 * id + 1], d.xpos[3 * id + 2]);
    group.quaternion.set(d.xquat[4 * id + 1], d.xquat[4 * id + 2], d.xquat[4 * id + 3], d.xquat[4 * id]);
  }
  const b = cell.blockBody, block = scenery.block;
  block.position.set(d.xpos[3 * b], d.xpos[3 * b + 1], d.xpos[3 * b + 2]);
  block.quaternion.set(d.xquat[4 * b + 1], d.xquat[4 * b + 2], d.xquat[4 * b + 3], d.xquat[4 * b]);
  block.scale.setScalar(2 * cell.half);
  for (const k of ['A', 'B']) {
    const isTarget = state.target === k;
    for (const mesh of scenery.bins[k]) {
      const g = mesh.userData.geom;
      mesh.position.set(m.geom_pos[3 * g], m.geom_pos[3 * g + 1], m.geom_pos[3 * g + 2]);
      mesh.material = isTarget ? binMat.target : binMat.idle;
    }
    scenery.lamps[k].material = isTarget ? lampMat.on : lampMat.off;
  }
  const [rx, ry] = cell.bins[state.target];
  scenery.rimLine.position.set(rx, ry, 0);
  scenery.rimLine.material.opacity = 0.55 + 0.35 * Math.sin(performance.now() / 420);
  scenery.release.position.set(rx, ry, LIFT);
  const pts = scenery.releaseLine.geometry.attributes.position;
  pts.setXYZ(0, rx, ry, 0.0); pts.setXYZ(1, rx, ry, LIFT); pts.needsUpdate = true;
  scenery.releaseLine.computeLineDistances();
}

const fitted = { portrait: null };
function resize() {
  const stage = $('stage');
  const w = stage.clientWidth, h = stage.clientHeight;
  renderer.setSize(w, h, false);
  composer.setSize(w, h);
  camera.aspect = w / h; camera.updateProjectionMatrix();
  const portrait = w / h < 0.9; // frame the whole arm on tall screens
  if (portrait !== fitted.portrait) {
    fitted.portrait = portrait;
    camera.position.set(...(portrait ? [2.55, 1.25, 1.55] : [1.78, 0.92, 1.08]));
    controls.target.set(...(portrait ? [0.4, 0.0, 0.3] : [0.4, 0.0, 0.2]));
    controls.update();
  }
}
new ResizeObserver(resize).observe($('stage'));

// --- placing things ----------------------------------------------------------------------------
const clamp = (v, [lo, hi]) => Math.min(Math.max(v, lo), hi);
function blockAllowed(x, y) {
  return x >= BLOCK_ZONE.x[0] && x <= BLOCK_ZONE.x[1] && y >= BLOCK_ZONE.y[0] && y <= BLOCK_ZONE.y[1] && cell.inBin(x, y, 0.04) === null;
}
function binAllowed(name, x, y) {
  const other = cell.bins[name === 'A' ? 'B' : 'A'];
  if (Math.abs(x - other[0]) < BIN_SIDE + 0.03 && Math.abs(y - other[1]) < BIN_SIDE + 0.03) return false;
  const [bx, by, bz] = cell.blockPos();
  const resting = !cell.holding && bz < cell.half + 0.01;
  if (resting && Math.abs(bx - x) <= BIN_SIDE / 2 + 0.04 && Math.abs(by - y) <= BIN_SIDE / 2 + 0.04) return false;
  return true;
}
function binClamp(x, y) {
  x = clamp(x, BIN_ZONE.x); y = clamp(y, BIN_ZONE.y);
  if (x > 0.68 && Math.abs(y) > 0.27) y = Math.sign(y) * 0.27; // the far corners: tested at 10 of 20
  return [x, y];
}

const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
const tablePlane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
let drag = null;
function pick(e) {
  const r = canvas.getBoundingClientRect();
  pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  raycaster.setFromCamera(pointer, camera);
}
function onTable(e) { pick(e); const p = new THREE.Vector3(); return raycaster.ray.intersectPlane(tablePlane, p) ? p : null; }
function canDragBlock() { return !cell.holding && cell.blockPos()[2] < cell.half + 0.02 && state.phase !== 'loading'; }

canvas.addEventListener('pointerdown', (e) => {
  if (!cell) return;
  pick(e);
  const hit = raycaster.intersectObjects(scenery.pickables, false)[0];
  if (!hit) return;
  const data = hit.object.userData;
  if (data.kind === 'block' && !canDragBlock()) return;
  const p = onTable(e);
  if (!p) return;
  const origin = data.kind === 'block' ? cell.blockPos() : cell.bins[data.name];
  drag = { ...data, dx: origin[0] - p.x, dy: origin[1] - p.y, x0: e.clientX, y0: e.clientY, moved: false };
  controls.enabled = false;
  canvas.setPointerCapture(e.pointerId);
  canvas.classList.add('dragging');
  scenery.zones[data.kind === 'block' ? 'block' : 'bin'].visible = true;
});
canvas.addEventListener('pointermove', (e) => {
  if (!cell) return;
  if (!drag) {
    pick(e);
    canvas.classList.toggle('over', raycaster.intersectObjects(scenery.pickables, false).length > 0);
    return;
  }
  if (Math.hypot(e.clientX - drag.x0, e.clientY - drag.y0) > 4) drag.moved = true;
  if (!drag.moved) return;
  const p = onTable(e);
  if (!p) return;
  if (drag.kind === 'block') {
    const x = clamp(p.x + drag.dx, BLOCK_ZONE.x), y = clamp(p.y + drag.dy, BLOCK_ZONE.y);
    if (blockAllowed(x, y) && canDragBlock()) { cell.placeBlock(x, y); if (state.phase !== 'running') state.placement = [x, y]; }
  } else {
    const [x, y] = binClamp(p.x + drag.dx, p.y + drag.dy);
    if (binAllowed(drag.name, x, y)) cell.moveBin(drag.name, x, y);
  }
});
function endDrag(e) {
  if (!drag) return;
  if (!drag.moved && drag.kind === 'bin') setTarget(drag.name);
  drag = null;
  controls.enabled = true;
  canvas.classList.remove('dragging');
  scenery.zones.block.visible = false; scenery.zones.bin.visible = false;
  if (e?.pointerId !== undefined && canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId);
}
canvas.addEventListener('pointerup', endDrag);
canvas.addEventListener('pointercancel', endDrag);

function setTarget(name) {
  state.target = name;
  cell.setOrder(name);
  ui.targetA.setAttribute('aria-pressed', String(name === 'A'));
  ui.targetB.setAttribute('aria-pressed', String(name === 'B'));
}

// --- the run -----------------------------------------------------------------------------------
function holdAnswer() { return [HOLD, HOLD, HOLD, cell.closed ? 1 : 0]; }

async function resetScene() {
  cell.home();
  cell.placeBlock(...state.placement);
  cell.setOrder(state.target);
  state.decision = 0; state.budget = 0;
  scenery.aim.visible = false;
  scenery.trailCount = 0; scenery.trail.geometry.setDrawRange(0, 0);
  view?.clear();
  ui.decision.textContent = '–'; ui.sweeps.textContent = '–'; ui.ms.textContent = '–';
  if (state.brainReady) await brain.call('reset');
}

async function run() {
  if (!state.brainReady || state.phase === 'running') return;
  if (state.phase === 'done' || state.decision > 0) await resetScene();
  else await brain.call('reset');
  state.phase = 'running'; state.decision = 0; state.started = performance.now();
  ui.run.textContent = 'Stop'; ui.run.disabled = false;
  ui.toast.hidden = true;
  setStatus('Running', 'ready');
  think();
}

function stop(message, kind = '') {
  state.phase = 'done';
  document.body.dataset.result = message || '';
  document.body.dataset.decisions = String(state.decision);
  ui.run.textContent = 'Run again';
  setStatus('Ready', 'ready');
  if (message) toast(message, kind, 0);
}

async function think() {
  if (state.phase !== 'running') return;
  if (state.decision >= CAP) { stop(`Out of time after ${CAP} decisions`, 'bad'); return; }
  const x = cell.observe();
  state.awaiting = true;
  let reply;
  try { reply = await brain.call('act', { x: Array.from(x) }); } catch (error) { stop(`The brain stopped: ${error.message}`, 'bad'); return; }
  state.awaiting = false;
  if (state.phase !== 'running') return;
  const answer = reply.refused ? holdAnswer() : reply.answer;
  view.update(reply, reply.refused ? null : answer);
  if (reply.activation && view.pop?.association) {
    const p = view.pop.association;
    let mean = 0;
    for (let i = 0; i < p.size; i++) mean += Math.max(0, reply.activation[p.start + i]);
    rimState.target = 0.25 + 1.1 * Math.min(1, mean / p.size / 0.5);
  }
  ui.decision.textContent = String(state.decision + 1);
  ui.sweeps.textContent = reply.refused ? 'refused' : `${reply.sweeps}`;
  ui.ms.textContent = `${Math.round(reply.ms ?? reply.worker_ms)} ms`;
  (state.thinkMs ||= []).push(reply.ms ?? reply.worker_ms);
  const { target, qTarget } = cell.command(answer);
  scenery.aim.position.set(...target); scenery.aim.visible = true;
  cell.decideBegin(qTarget, answer[3]);
  state.phase = 'running'; state.moving = true;
}

function finishDecision() {
  state.moving = false;
  const out = cell.decideEnd();
  state.decision += 1;
  if (out.event === 'grasped') toast('Grasped', '', 1200);
  else if (out.event === 'slipped') toast('The block slipped. The brain tries again.', 'bad', 1800);
  else if (out.dropped) toast('Dropped outside a bin. The brain tries again.', 'bad', 1800);
  if (out.lost) { stop('The block left the table', 'bad'); return; }
  if (out.done) {
    const [, bin, verdict] = out.event.split(':');
    const seconds = (state.decision * 0.2).toFixed(1);
    if (verdict === 'right') stop(`Placed in bin ${bin} in ${state.decision} decisions (${seconds} s of arm time)`, 'good');
    else stop(`Placed in bin ${bin}, the other bin`, 'bad');
    return;
  }
  think();
}

ui.run.addEventListener('click', () => {
  if (state.phase === 'running') { stop('Stopped'); return; }
  run();
});
ui.reset.addEventListener('click', async () => { if (state.phase === 'running') stop(); await resetScene(); state.phase = state.brainReady ? 'idle' : state.phase; ui.run.textContent = 'Run'; ui.toast.hidden = true; });
ui.shuffle.addEventListener('click', async () => {
  if (state.phase === 'running') stop();
  for (let i = 0; i < 200; i++) {
    const x = SPAWN_X[0] + Math.random() * (SPAWN_X[1] - SPAWN_X[0]), y = SPAWN_Y[0] + Math.random() * (SPAWN_Y[1] - SPAWN_Y[0]);
    if (cell.inBin(x, y, 0.04) === null) { state.placement = [x, y]; break; }
  }
  setTarget(Math.random() < 0.5 ? 'A' : 'B');
  await resetScene();
  state.phase = state.brainReady ? 'idle' : state.phase; ui.run.textContent = 'Run'; ui.toast.hidden = true;
});
ui.targetA.addEventListener('click', () => setTarget('A'));
ui.targetB.addEventListener('click', () => setTarget('B'));
document.querySelectorAll('.speed .seg').forEach((b) => b.addEventListener('click', () => {
  state.speed = Number(b.dataset.speed);
  document.querySelectorAll('.speed .seg').forEach((o) => o.setAttribute('aria-pressed', String(o === b)));
}));

function trailStep() {
  if (state.phase !== 'running') return;
  const [x, y, z] = cell.tip();
  const n = TRAIL, P = scenery.trailPos, C = scenery.trailCol;
  if (scenery.trailCount < n) scenery.trailCount += 1; else P.copyWithin(0, 3);
  const k = scenery.trailCount - 1;
  P[3 * k] = x; P[3 * k + 1] = y; P[3 * k + 2] = z;
  const c = new THREE.Color(0x4fc3f7);
  for (let i = 0; i < scenery.trailCount; i++) {
    const a = Math.pow(i / Math.max(1, scenery.trailCount - 1), 1.6) * 3.2;
    C[3 * i] = c.r * a; C[3 * i + 1] = c.g * a; C[3 * i + 2] = c.b * a;
  }
  const g = scenery.trail.geometry;
  g.attributes.position.needsUpdate = true; g.attributes.color.needsUpdate = true;
  g.setDrawRange(0, scenery.trailCount);
}

// --- the frame loop ----------------------------------------------------------------------------
let last = performance.now();
function frame(now) {
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  if (cell && state.phase === 'running' && state.moving) {
    state.budget += (dt / PHYSICS_DT) * state.speed;
    const steps = Math.min(Math.floor(state.budget), 200);
    state.budget -= steps;
    if (steps > 0 && cell.stepPhysics(steps) === 0) finishDecision();
  }
  if (cell) { syncScene(); trailStep(); }
  rimState.level += (rimState.target - rimState.level) * (1 - Math.exp(-dt / 0.18));
  rimState.target += (0.08 - rimState.target) * (1 - Math.exp(-dt / 0.6));
  rim.strength.value = rimState.level;
  controls.update();
  composer.render(dt);
  view?.frame(dt);
  requestAnimationFrame(frame);
}

// --- start -------------------------------------------------------------------------------------
async function start() {
  try {
    setStatus('Loading physics');
    mujoco = await loadMujoco();
    const bytes = new Uint8Array(await (await fetch('assets/cell.mjb')).arrayBuffer());
    const vfs = new mujoco.MjVFS();
    vfs.addBuffer('cell.mjb', bytes);
    const model = mujoco.MjModel.from_binary_path('cell.mjb', vfs);
    cell = new Cell(mujoco, model);
    buildPrimitives();
    await buildPanda();
    cell.placeBlock(...state.placement);
    setTarget('A');
    resize();
    requestAnimationFrame(frame);
    window.cadenceArm = { cell, state, run, setTarget, resetScene, get view() { return view; }, // for the page check
      screenOf(x, y, z) { const v = new THREE.Vector3(x, y, z).project(camera); const r = canvas.getBoundingClientRect(); return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; } };
  } catch (error) {
    setStatus(`Physics failed to load: ${error.message}`, 'error');
    throw error;
  }
  view = new BrainView($('brain'), $('brain-tip'));
  brain = new BrainWorker();
  try {
    const desc = await brain.call('init');
    view.setup(desc);
    const r = desc.recipe || {};
    ui.sub.textContent = `Deep, three layers (${(r.modules || []).join(', ')}) · ${desc.neurons} neurons · ${desc.synapses.toLocaleString('en')} synapses`;
    state.brainReady = true;
    if (state.phase === 'loading') state.phase = 'idle';
    ui.run.disabled = false;
    setStatus('Ready', 'ready');
    ui.status.title = `Brain loaded in ${(desc.startup_ms / 1000).toFixed(1)} s`;
    document.body.dataset.ready = '1';
    const auto = new URLSearchParams(location.search).get('autorun');
    if (new URLSearchParams(location.search).has('still')) document.body.dataset.result = 'still';
    if (auto) { if (auto === 'A' || auto === 'B') setTarget(auto); state.speed = 4; run(); }
  } catch (error) {
    setStatus(`The brain failed to load: ${error.message}`, 'error');
  }
}
start();
