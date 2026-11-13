// The room: a photographed room as the light and the backdrop (a CC0 light probe), a wooden table,
// a low T-perch on it, and the things the visitor places. World frame as the chamber's (INTERFACES
// P1): metres, y up, the table top at y = 0, the perch's bar along x at BAR_Y, the parrot faces +z.
import * as THREE from 'three';
import { GLTFLoader } from './vendor/three/jsm/loaders/GLTFLoader.js';
import { RGBELoader } from './vendor/three/jsm/loaders/RGBELoader.js';

export const BAR_Y = 0.13;
export const BAR_LEN = 0.30;
export const TABLE = { w: 1.6, d: 1.1, top: 0, thick: 0.035, height: 0.74 };
export const ZONE = { minR: 0.10, maxR: 0.72 }; // where things may stand: from the perch's post outward

// The kinds of things, each a CC0 model (assets/CREDITS.json) at its real size: the node to keep
// from the model's file, and its largest extent in metres.
export const KINDS = {
  apple: { file: 'apple', size: 0.08, label: 'apple' },
  ball: { file: 'ball', size: 0.074, label: 'ball' },
  cup: { file: 'cup', node: 'tea_set_01_cup_small_01', size: 0.10, label: 'cup' },
  banana: { file: 'banana', node: 'bananas_a', size: 0.19, label: 'banana' },
  block: { file: null, size: 0.05, label: 'block' },
  duck: { file: 'duck', size: 0.09, label: 'duck' },
  lemon: { file: 'lemon', size: 0.07, label: 'lemon' },
  pear: { file: 'pear', node: 'food_pears_asian_01_b', size: 0.085, label: 'pear' },
};

const texLoader = new THREE.TextureLoader();
function pbr(name, repeat, opts = {}) {
  const load = (suffix, srgb) => {
    const t = texLoader.load(`assets/tex/${name}_${suffix}.jpg`);
    t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(repeat[0], repeat[1]); t.anisotropy = 8;
    if (srgb) t.colorSpace = THREE.SRGBColorSpace;
    return t;
  };
  return new THREE.MeshStandardMaterial({ map: load('diff', true), normalMap: load('nor', false), roughnessMap: load('rough', false), roughness: 1, metalness: 0, ...opts });
}

export function makeRenderer(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance', preserveDrawingBuffer: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.25));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.95;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  // the shadow map is drawn once a frame by the page, and the eyes reuse it
  renderer.shadowMap.autoUpdate = false;
  return renderer;
}

export class Room {
  constructor(renderer) {
    this.renderer = renderer;
    this.scene = new THREE.Scene();
    this.things = new Map();
    this.models = new Map();
    this.gltf = new GLTFLoader();
    this.pickables = [];
    this.serial = 0;
  }

  async build() {
    const scene = this.scene;
    // light and backdrop: the room's light probe
    const hdr = await new RGBELoader().loadAsync('assets/room.hdr');
    hdr.mapping = THREE.EquirectangularReflectionMapping;
    const pmrem = new THREE.PMREMGenerator(this.renderer);
    this.envMap = pmrem.fromEquirectangular(hdr).texture;
    scene.environment = this.envMap;
    scene.background = hdr;
    scene.backgroundBlurriness = 0.035;
    scene.backgroundIntensity = 0.8;
    // a soft key light from the window's side, which casts the shadows
    const sun = new THREE.DirectionalLight(0xfff3e2, 1.6);
    sun.position.set(-1.1, 1.6, 0.9);
    sun.target.position.set(0, 0.1, 0);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    Object.assign(sun.shadow.camera, { left: -0.9, right: 0.9, top: 0.9, bottom: -0.9, near: 0.5, far: 4 });
    sun.shadow.bias = -0.0002; sun.shadow.normalBias = 0.004; sun.shadow.radius = 4;
    sun.shadow.camera.updateProjectionMatrix();
    scene.add(sun, sun.target);
    this.sun = sun;
    // the table: an oak top on four legs, its top at y = 0
    const top = new THREE.Mesh(new THREE.BoxGeometry(TABLE.w, TABLE.thick, TABLE.d), pbr('table', [2, 1.4]));
    top.position.y = -TABLE.thick / 2;
    top.receiveShadow = true; top.castShadow = true;
    scene.add(top);
    this.table = top;
    const legMat = pbr('table', [0.3, 2]);
    for (const [x, z] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
      const leg = new THREE.Mesh(new THREE.BoxGeometry(0.06, TABLE.height - TABLE.thick, 0.06), legMat);
      leg.position.set(x * (TABLE.w / 2 - 0.08), -TABLE.thick - (TABLE.height - TABLE.thick) / 2, z * (TABLE.d / 2 - 0.08));
      leg.castShadow = true; scene.add(leg);
    }
    // the floor under the table, wooden, fading into the backdrop
    const floor = new THREE.Mesh(new THREE.CircleGeometry(3.2, 64), pbr('floor', [5, 5], { transparent: false }));
    floor.rotation.x = -Math.PI / 2; floor.position.y = -TABLE.height; floor.receiveShadow = true;
    scene.add(floor);
    this.buildPerch();
    return this;
  }

  // A low T-perch: a round foot on the table, an oak post, and a natural branch as the bar.
  buildPerch() {
    const g = new THREE.Group(); g.name = 'perch';
    const oak = pbr('post', [1, 1]);
    const foot = new THREE.Mesh(new THREE.CylinderGeometry(0.075, 0.08, 0.014, 48), oak);
    foot.position.y = 0.007;
    const post = new THREE.Mesh(new THREE.CylinderGeometry(0.0115, 0.013, BAR_Y - 0.014, 24), oak);
    post.position.y = 0.014 + (BAR_Y - 0.014) / 2 - 0.006;
    const barGeo = new THREE.CylinderGeometry(0.011, 0.011, BAR_LEN, 40, 24, false);
    // a little irregular, as a branch is
    const p = barGeo.attributes.position;
    for (let i = 0; i < p.count; i++) {
      const y = p.getY(i), x = p.getX(i), z = p.getZ(i);
      const r = 1 + 0.035 * Math.sin(y * 41 + 1.3) + 0.02 * Math.sin(y * 97 + Math.atan2(z, x) * 3);
      p.setX(i, x * r); p.setZ(i, z * r);
    }
    barGeo.computeVertexNormals();
    const bar = new THREE.Mesh(barGeo, pbr('bark', [0.6, 2.2]));
    bar.rotation.z = Math.PI / 2; bar.position.y = BAR_Y;
    for (const m of [foot, post, bar]) { m.castShadow = true; m.receiveShadow = true; g.add(m); }
    this.scene.add(g);
    this.perch = g;
    this.perchParts = [foot, post, bar];
    this.bar = bar;
  }

  /** The bar's radius, set by the parrot's look (the dowel its feet were made gripping). */
  setBarRadius(r) {
    const k = (r || 0.011) / 0.011;
    this.bar.scale.set(k, 1, k);
  }

  async model(kind) {
    const spec = KINDS[kind];
    if (!this.models.has(kind)) {
      this.models.set(kind, (async () => {
        let obj;
        if (!spec.file) { // a wooden toy block, painted blue
          const mat = pbr('block', [0.25, 0.25]);
          mat.color = new THREE.Color('#3f6fd1');
          mat.map.offset.set(0.31, 0.12);
          obj = new THREE.Mesh(new THREE.BoxGeometry(spec.size, spec.size, spec.size), mat);
          obj.position.y = spec.size / 2;
          const wrap = new THREE.Group(); wrap.add(obj); return wrap;
        }
        const gltf = await this.gltf.loadAsync(`assets/models/${spec.file}.glb`);
        let root = gltf.scene;
        if (spec.node) {
          const node = root.getObjectByName(spec.node);
          node.parent.remove(node); node.position.set(0, 0, 0); node.updateMatrixWorld(true);
          root = new THREE.Group(); root.add(node);
        }
        // its size and its base at y = 0, centred
        root.updateMatrixWorld(true);
        const box = new THREE.Box3().setFromObject(root), size = box.getSize(new THREE.Vector3());
        const k = spec.size / Math.max(size.x, size.y, size.z);
        const wrap = new THREE.Group();
        root.scale.setScalar(k);
        root.position.set(-(box.min.x + box.max.x) / 2 * k, -box.min.y * k, -(box.min.z + box.max.z) / 2 * k);
        wrap.add(root);
        return wrap;
      })());
    }
    return (await this.models.get(kind)).clone(true);
  }

  /** Put a thing on the table: kind, place (x, z), turn (degrees). Returns its id. */
  async place(kind, x, z, yaw = 0, id = null) {
    if (!KINDS[kind]) throw new Error(`No thing of kind ${kind}.`);
    id = id || `${kind}-${++this.serial}`;
    const obj = await this.model(kind);
    obj.name = id;
    obj.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; o.userData.thing = id; } });
    obj.userData = { thing: id, kind };
    obj.rotation.y = yaw * Math.PI / 180;
    this.scene.add(obj);
    this.things.set(id, { id, kind, obj });
    this.move(id, x, z);
    obj.traverse((o) => { if (o.isMesh) this.pickables.push(o); });
    return id;
  }

  /** The nearest allowed place to (x, z): on the table, clear of the perch's foot. */
  allowed(x, z) {
    x = Math.max(-TABLE.w / 2 + 0.05, Math.min(TABLE.w / 2 - 0.05, x));
    z = Math.max(-TABLE.d / 2 + 0.05, Math.min(TABLE.d / 2 - 0.05, z));
    const r = Math.hypot(x, z);
    if (r < ZONE.minR) { const k = ZONE.minR / Math.max(r, 1e-6); x *= k; z *= k; }
    if (r > ZONE.maxR) { const k = ZONE.maxR / r; x *= k; z *= k; }
    return [x, z];
  }

  move(id, x, z, yaw = null) {
    const t = this.things.get(id);
    if (!t) return;
    [x, z] = this.allowed(x, z);
    t.obj.position.set(x, 0, z);
    if (yaw !== null) t.obj.rotation.y = yaw * Math.PI / 180;
  }

  remove(id) {
    const t = this.things.get(id);
    if (!t) return;
    this.scene.remove(t.obj);
    this.pickables = this.pickables.filter((m) => m.userData.thing !== id);
    this.things.delete(id);
  }

  clear() { for (const id of [...this.things.keys()]) this.remove(id); }

  /** The scene as the chamber shares it (INTERFACES P4). */
  describe() {
    return { schema: 'parrot-scene/1', perch: { bar_y: BAR_Y, length: BAR_LEN, radius: 0.011 },
      things: [...this.things.values()].map((t) => ({ id: t.id, kind: t.kind, pos: t.obj.position.toArray().map((v) => +v.toFixed(4)), yaw: +(t.obj.rotation.y * 180 / Math.PI).toFixed(1), size: KINDS[t.kind].size })) };
  }

  async load(desc) {
    this.clear();
    for (const t of desc.things || []) await this.place(t.kind, t.pos[0], t.pos[2], t.yaw || 0, t.id);
  }
}
