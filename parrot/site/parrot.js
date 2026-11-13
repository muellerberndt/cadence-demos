// The parrot: an African Grey on the perch, its skeleton, and the joints its brain drives.
//
// The rig (rig.json) is the one source of the bones, the eye sockets and the joint list: the page's
// placeholder body below is skinned to it, and a scanned or sculpted body made for the same rig
// (a .glb whose skin uses the same bone names) drops in through Parrot.useBody without a change to
// the joint driver. The driver turns each joint's angle into bone rotations about axes named in the
// parrot's own frame (y up, facing +z, its left +x), whatever the bones' own rest axes are.
//
// Joints move as servos: each moves toward its target at most at its rate and stays in its range.
// The brain sends targets on a [-1, 1] scale over each joint's range; the page reads back the
// angles and speeds (proprioception) on the same scale.
import * as THREE from 'three';

const D2R = Math.PI / 180;
const V = (a) => new THREE.Vector3(a[0], a[1], a[2]);
const smooth = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const mix = (a, b, t) => a + (b - a) * t;

// A small deterministic random source, so the plumage is the same on every visit.
function rng(seed) {
  let s = seed >>> 0;
  return () => { s = (s + 0x6d2b79f5) >>> 0; let t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

export async function loadRig(url = 'rig.json') {
  const r = await fetch(url);
  if (!r.ok) throw new Error('The parrot’s rig is missing.');
  return r.json();
}

// --- the joint driver ---------------------------------------------------------------------------
export class Joints {
  constructor(spec, combined = []) {
    this.spec = spec;
    this.combined = combined; // a large turn allows less tilt: [{joint, by, shrink}]
    this.n = spec.length;
    this.index = Object.fromEntries(spec.map((j, i) => [j.name, i]));
    this.pos = Float32Array.from(spec.map((j) => j.rest));
    this.vel = new Float32Array(this.n);
    this.target = Float32Array.from(spec.map((j) => j.rest));
  }
  toUnit(i, v) { const j = this.spec[i]; return (2 * (v - j.min)) / (j.max - j.min) - 1; }
  fromUnit(i, u) { const j = this.spec[i]; return j.min + ((Math.max(-1, Math.min(1, u)) + 1) / 2) * (j.max - j.min); }
  /** Targets on the [-1, 1] scale, one per joint (a NaN keeps that joint's target). */
  setUnitTargets(arr) { for (let i = 0; i < this.n && i < arr.length; i++) if (Number.isFinite(arr[i])) this.target[i] = this.fromUnit(i, arr[i]); }
  set(name, value) { const i = this.index[name]; const j = this.spec[i]; this.target[i] = Math.max(j.min, Math.min(j.max, value)); }
  get(name) { return this.pos[this.index[name]]; }
  /** Move every joint toward its target as a critically damped spring (no overshoot, no added noise),
   *  its speed held within the joint's rate. A step of 60 degrees of the head takes about 0.2 s. */
  step(dt) {
    const steps = Math.max(1, Math.ceil(dt / 0.006)), h = dt / steps;
    for (let i = 0; i < this.n; i++) {
      const j = this.spec[i];
      const w = j.omega || (j.unit === 'deg' ? 30 : 20);
      const [lo, hi] = this.limits(i);
      const want = Math.max(lo, Math.min(hi, this.target[i]));
      let x = this.pos[i], v = this.vel[i];
      for (let k = 0; k < steps; k++) {
        v += (w * w * (want - x) - 2 * w * v) * h;
        v = Math.max(-j.rate, Math.min(j.rate, v));
        x += v * h;
      }
      if (x <= lo || x >= hi) { x = Math.max(lo, Math.min(hi, x)); v = 0; }
      this.pos[i] = x; this.vel[i] = v;
    }
  }
  /** A joint's range now: its own, narrowed where another joint's position asks (the combined limits). */
  limits(i) {
    const j = this.spec[i];
    let k = 1;
    for (const c of this.combined) if (c.joint === j.name) { const b = this.spec[this.index[c.by]]; const f = this.pos[this.index[c.by]] / Math.max(Math.abs(b.min), Math.abs(b.max)); k *= 1 - c.shrink * f * f; }
    return [j.min * k, j.max * k];
  }
  /** Proprioception: the angles on the [-1, 1] scale, then the speeds over each joint's rate. */
  proprio(out = new Float32Array(2 * this.n)) {
    for (let i = 0; i < this.n; i++) { out[i] = this.toUnit(i, this.pos[i]); out[this.n + i] = this.vel[i] / this.spec[i].rate; }
    return out;
  }
}

// --- plumage textures, drawn once --------------------------------------------------------------
const C = (hex) => new THREE.Color(hex);
const REGION = {
  head: C('#8f9397'), neck: C('#878b8f'), back: C('#73777c'), rump: C('#b8bbbe'), belly: C('#83878b'),
  face: C('#ebe8e3'), vent: C('#a91d26'), fringe: C('#d9dbdc'),
};

function bodyColour(u, v) {
  // u: around the body (0 the left side, .25 the front, .5 the right side, .75 the back); v: tail base (0) to crown (1)
  const front = Math.cos((u - 0.25) * 2 * Math.PI); // 1 at the front, -1 at the back
  const back = Math.max(0, -front);
  const c = REGION.belly.clone();
  c.lerp(REGION.back, smooth(0.0, 0.6, back) * smooth(0.25, 0.4, v));
  c.lerp(REGION.rump, smooth(0.3, 0.8, back) * (1 - smooth(0.22, 0.4, v)) * smooth(0.02, 0.1, v));
  c.lerp(REGION.neck, smooth(0.5, 0.66, v));
  c.lerp(REGION.head, smooth(0.74, 0.82, v));
  c.lerp(REGION.vent, smooth(0.1, -0.05, v) * smooth(-0.6, 0.2, front));
  return c;
}

// The bare white patch round each eye and down to the beak's base (the lores).
function faceMask(u, v) {
  const e = (cu, cv, ru, rv) => { let du = u - cu; du -= Math.round(du); return Math.max(0, 1 - Math.hypot(du / ru, (v - cv) / rv)); };
  const eyes = Math.max(e(0.075, 0.862, 0.06, 0.05), e(0.425, 0.862, 0.06, 0.05));
  const lores = e(0.25, 0.842, 0.2, 0.026);
  return smooth(0.0, 0.25, Math.max(eyes, lores));
}

function plumageTextures(radiusAt, size = 1024) {
  const W = size, H = size;
  const col = document.createElement('canvas'); col.width = W; col.height = H;
  const hgt = document.createElement('canvas'); hgt.width = W; hgt.height = H;
  const g = col.getContext('2d'), h = hgt.getContext('2d');
  g.fillStyle = '#7d8185'; g.fillRect(0, 0, W, H);
  h.fillStyle = '#404040'; h.fillRect(0, 0, W, H);
  const rand = rng(7);
  const L = 0.26; // the spine's length in metres, for feather sizes
  // rows from the tail base (bottom of the canvas) up to the crown: later rows lie over the bases of earlier ones
  let v = -0.01;
  let row = 0;
  while (v < 1.02) {
    const fw = mix(0.0115, 0.0042, smooth(0.45, 0.88, v)); // a feather's visible width, metres
    const fl = fw * 1.05;
    const r = Math.max(0.006, radiusAt(Math.min(1, Math.max(0, v))));
    const ncol = Math.max(8, Math.round((2 * Math.PI * r) / fw));
    const wpx = W / ncol, hpx = (fl / L) * H * 1.6;
    for (let k = 0; k <= ncol; k++) {
      const u = (k + (row % 2 ? 0.5 : 0) + (rand() - 0.5) * 0.25) / ncol;
      const vv = v + (rand() - 0.5) * 0.004;
      const x = u * W, y = (1 - vv) * H;
      const uc = ((u % 1) + 1) % 1;
      const face = faceMask(uc, vv);
      if (face > 0.95) continue;
      const base = bodyColour(uc, vv);
      const j = 1 + (rand() - 0.5) * 0.08;
      base.multiplyScalar(j);
      const fringeK = mix(0.35, 0.85, smooth(0.45, 0.8, vv)) * (1 - smooth(0.0, 0.12, -Math.cos((uc - 0.25) * 2 * Math.PI) - 0.2) * 0.35);
      const fringe = base.clone().lerp(REGION.fringe, fringeK);
      const tw = wpx * 1.18, th = hpx;
      for (const dx of [0, -W, W]) {
        const cx = x + dx;
        if (cx < -tw || cx > W + tw) continue;
        // the feather's shape: straight sides from its hidden base, a rounded tip toward the tail
        const path = new Path2D();
        path.moveTo(cx - tw / 2, y - th);
        path.lineTo(cx - tw / 2, y);
        path.bezierCurveTo(cx - tw / 2, y + th * 0.62, cx + tw / 2, y + th * 0.62, cx + tw / 2, y);
        path.lineTo(cx + tw / 2, y - th);
        path.closePath();
        const grad = g.createLinearGradient(0, y - th, 0, y + th * 0.47);
        grad.addColorStop(0, `#${base.clone().multiplyScalar(0.82).getHexString()}`);
        grad.addColorStop(0.62, `#${base.getHexString()}`);
        grad.addColorStop(0.86, `#${fringe.getHexString()}`);
        grad.addColorStop(1, `#${fringe.clone().multiplyScalar(0.92).getHexString()}`);
        g.fillStyle = grad; g.fill(path);
        // a hint of the shaft
        g.strokeStyle = `rgba(40,42,46,${0.10 + 0.08 * rand()})`; g.lineWidth = Math.max(0.6, tw * 0.035);
        g.beginPath(); g.moveTo(cx, y - th * 0.4); g.lineTo(cx + (rand() - 0.5) * 2, y + th * 0.35); g.stroke();
        const hg = h.createLinearGradient(0, y - th, 0, y + th * 0.47);
        hg.addColorStop(0, '#2a2a2a'); hg.addColorStop(0.75, '#c8c8c8'); hg.addColorStop(1, '#e8e8e8');
        h.fillStyle = hg; h.fill(path);
      }
    }
    v += (fl / L) * 0.5;
    row++;
  }
  // the bare face: pale skin with fine wrinkles, under the feathers' edge
  const img = g.getImageData(0, 0, W, H), hi = h.getImageData(0, 0, W, H);
  const skin = REGION.face;
  for (let py = 0; py < H; py++) {
    const vv = 1 - py / H;
    if (vv < 0.78 || vv > 0.93) continue;
    for (let px = 0; px < W; px++) {
      const uu = px / W, m = faceMask(uu, vv);
      if (m <= 0) continue;
      const k = 4 * (py * W + px);
      const wr = 0.5 + 0.5 * Math.sin(px * 0.9 + Math.sin(py * 0.21) * 3.0) * Math.sin(py * 0.55);
      const s = 0.93 + 0.07 * wr;
      img.data[k] = mix(img.data[k], skin.r * 255 * s, m);
      img.data[k + 1] = mix(img.data[k + 1], skin.g * 255 * s, m);
      img.data[k + 2] = mix(img.data[k + 2], skin.b * 255 * s, m);
      const hv = 150 + 30 * wr;
      hi.data[k] = hi.data[k + 1] = hi.data[k + 2] = mix(hi.data[k], hv, m);
    }
  }
  g.putImageData(img, 0, 0);
  // a normal map from the height: each feather's tip stands a little off the one under it
  const nrm = document.createElement('canvas'); nrm.width = W; nrm.height = H;
  const nctx = nrm.getContext('2d'), out = nctx.createImageData(W, H);
  const hd = hi.data, od = out.data, s = 2.2 / 255;
  for (let y = 0; y < H; y++) {
    const y0 = Math.max(0, y - 1), y1 = Math.min(H - 1, y + 1);
    for (let x = 0; x < W; x++) {
      const x0 = (x - 1 + W) % W, x1 = (x + 1) % W;
      const dx = (hd[4 * (y * W + x1)] - hd[4 * (y * W + x0)]) * s;
      const dy = (hd[4 * (y1 * W + x)] - hd[4 * (y0 * W + x)]) * s;
      const nx = -dx, ny = dy, nz = 1, l = Math.hypot(nx, ny, nz);
      const k = 4 * (y * W + x);
      od[k] = (nx / l * 0.5 + 0.5) * 255; od[k + 1] = (ny / l * 0.5 + 0.5) * 255; od[k + 2] = (nz / l * 0.5 + 0.5) * 255; od[k + 3] = 255;
    }
  }
  nctx.putImageData(out, 0, 0);
  const map = new THREE.CanvasTexture(col); map.colorSpace = THREE.SRGBColorSpace;
  const normalMap = new THREE.CanvasTexture(nrm);
  for (const t of [map, normalMap]) { t.wrapS = THREE.RepeatWrapping; t.anisotropy = 4; }
  return { map, normalMap };
}

// One feather as a card's texture: a vane round a shaft, white, tinted per feather.
function featherTexture(kind) {
  const W = 128, H = 512;
  const c = document.createElement('canvas'); c.width = W; c.height = H;
  const g = c.getContext('2d');
  g.clearRect(0, 0, W, H);
  const rand = rng(kind === 'flight' ? 11 : 13);
  const path = new Path2D();
  if (kind === 'flight') { // long, its tip rounded, the outer vane narrower
    path.moveTo(W * 0.5, H * 0.02);
    path.bezierCurveTo(W * 0.92, H * 0.06, W * 0.86, H * 0.7, W * 0.62, H * 0.995);
    path.lineTo(W * 0.5, H * 0.995);
    path.bezierCurveTo(W * 0.26, H * 0.75, W * 0.04, H * 0.1, W * 0.5, H * 0.02);
  } else { // a covert: short and round
    path.moveTo(W * 0.5, H * 0.02);
    path.bezierCurveTo(W * 1.02, H * 0.05, W * 0.98, H * 0.8, W * 0.55, H * 0.995);
    path.lineTo(W * 0.45, H * 0.995);
    path.bezierCurveTo(W * 0.02, H * 0.8, W * -0.02, H * 0.05, W * 0.5, H * 0.02);
  }
  g.save(); g.clip(path);
  const grad = g.createLinearGradient(0, 0, 0, H);
  if (kind === 'flight') { grad.addColorStop(0, '#d6d6d6'); grad.addColorStop(0.75, '#f2f2f2'); grad.addColorStop(1, '#ffffff'); }
  else { grad.addColorStop(0, '#e2e2e2'); grad.addColorStop(0.08, '#ffffff'); grad.addColorStop(0.3, '#f4f4f4'); grad.addColorStop(1, '#bdbdbd'); }
  g.fillStyle = grad; g.fillRect(0, 0, W, H);
  // barbs
  for (let i = 0; i < 160; i++) {
    const y = rand() * H, side = rand() < 0.5 ? -1 : 1, a = 0.28 + rand() * 0.18;
    g.strokeStyle = `rgba(0,0,0,${0.05 + rand() * 0.07})`; g.lineWidth = 0.8;
    g.beginPath(); g.moveTo(W * 0.5, y); g.lineTo(W * 0.5 + side * W * 0.6, y - Math.tan(a) * W * 0.6 * -1); g.stroke();
  }
  g.restore();
  // the shaft
  g.strokeStyle = kind === 'flight' ? 'rgba(25,25,25,0.55)' : 'rgba(40,40,40,0.25)'; g.lineWidth = kind === 'flight' ? 2.4 : 1.4;
  g.beginPath(); g.moveTo(W * 0.5, H * 0.995); g.quadraticCurveTo(W * 0.53, H * 0.5, W * 0.5, H * 0.04); g.stroke();
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  return t;
}

// --- geometry helpers ---------------------------------------------------------------------------
// A tube along a curve with an elliptic section; returns positions, normals, uvs, indices and each
// vertex's curve parameter t (for skinning). sectionAt(t) -> [halfWidthAlongSide, halfDepthFront, halfDepthBack, dropOfCentre]
function loft(curve, sectionAt, rings, around, side = new THREE.Vector3(1, 0, 0), capEnd = true) {
  const pos = [], nor = [], uv = [], idx = [], ts = [];
  const p = new THREE.Vector3(), T = new THREE.Vector3(), N = new THREE.Vector3();
  for (let i = 0; i <= rings; i++) {
    const t = i / rings;
    curve.getPointAt(t, p); curve.getTangentAt(t, T);
    N.crossVectors(side, T).normalize();
    const [rx, rf, rb, drop] = sectionAt(t);
    for (let k = 0; k <= around; k++) {
      const phi = (k / around) * Math.PI * 2;
      const c = Math.cos(phi), s = Math.sin(phi);
      const rn = s >= 0 ? rf : rb;
      pos.push(p.x + side.x * rx * c + N.x * (rn * s - drop), p.y + side.y * rx * c + N.y * (rn * s - drop), p.z + side.z * rx * c + N.z * (rn * s - drop));
      nor.push(0, 0, 0);
      uv.push(k / around, t);
      ts.push(t);
    }
  }
  const row = around + 1;
  for (let i = 0; i < rings; i++) for (let k = 0; k < around; k++) {
    const a = i * row + k, b = a + 1, c2 = a + row, d = c2 + 1;
    idx.push(a, c2, b, b, c2, d);
  }
  if (capEnd) { // close the far end on its centre
    curve.getPointAt(1, p);
    const centre = pos.length / 3;
    pos.push(p.x, p.y, p.z); nor.push(0, 0, 0); uv.push(0.5, 1); ts.push(1);
    for (let k = 0; k < around; k++) idx.push(rings * row + k, centre, rings * row + k + 1);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  geo.setIndex(idx);
  geo.computeVertexNormals();
  geo.userData.t = ts;
  return geo;
}

function skin(geo, weightsOf) {
  const n = geo.attributes.position.count, si = new Uint16Array(4 * n), sw = new Float32Array(4 * n);
  const p = new THREE.Vector3();
  for (let i = 0; i < n; i++) {
    p.fromBufferAttribute(geo.attributes.position, i);
    const w = weightsOf(i, p); // [[boneIndex, weight], ...] up to 4
    let sum = 0;
    for (let k = 0; k < Math.min(4, w.length); k++) { si[4 * i + k] = w[k][0]; sw[4 * i + k] = w[k][1]; sum += w[k][1]; }
    for (let k = 0; k < 4; k++) sw[4 * i + k] /= sum || 1;
  }
  geo.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(si, 4));
  geo.setAttribute('skinWeight', new THREE.Float32BufferAttribute(sw, 4));
  return geo;
}

function merge(geos) {
  let count = 0;
  for (const g of geos) count += g.attributes.position.count;
  const out = new THREE.BufferGeometry();
  const names = ['position', 'normal', 'uv', 'skinIndex', 'skinWeight'];
  for (const name of names) {
    const a = geos[0].attributes[name];
    if (!a) continue;
    const arr = new a.array.constructor(count * a.itemSize);
    let off = 0;
    for (const g of geos) { arr.set(g.attributes[name].array, off); off += g.attributes[name].array.length; }
    out.setAttribute(name, new THREE.BufferAttribute(arr, a.itemSize));
  }
  const idx = []; let base = 0;
  for (const g of geos) { const ix = g.index.array; for (let i = 0; i < ix.length; i++) idx.push(ix[i] + base); base += g.attributes.position.count; }
  out.setIndex(idx);
  return out;
}

// --- the parrot ---------------------------------------------------------------------------------
export class Parrot {
  constructor(rig, { placeholder = true } = {}) {
    this.rig = rig;
    this.R = rig.bar_radius;
    this.group = new THREE.Group();
    this.group.name = 'parrot';
    this.joints = new Joints(rig.joints, rig.combined || []);
    this.bones = {};
    this.restAt = {};
    this.buildBones();
    this.sockets = {};
    for (const [name, s] of Object.entries(rig.sockets)) {
      const o = new THREE.Object3D(); o.name = name;
      const bq = this.restWorldQ[s.bone].clone().invert();
      o.position.copy(V(s.at).sub(this.restAt[s.bone]).applyQuaternion(bq));
      o.quaternion.copy(bq.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), s.yaw * D2R)));
      this.bones[s.bone].add(o);
      this.sockets[name] = o;
    }
    this.placeholder = new THREE.Group();
    this.group.add(this.placeholder);
    this.skinned = [];
    this.group.updateMatrixWorld(true);
    this.skeleton.calculateInverses(); // the bones at rest, where every body is bound
    if (placeholder) {
      this.buildBody();
      this.buildBeak();
      this.buildEyes();
      this.buildFeet();
      this.buildFeathers();
      for (const m of this.skinned) m.bind(this.skeleton, new THREE.Matrix4());
    }
    this.recordRest();
    this.update(0);
  }

  /** Bind a mesh made for this rig (its geometry carries skinIndex and skinWeight on this rig's
   *  bone order, its positions in the parrot's frame at rest) to the skeleton. */
  attach(geometry, material) {
    const pose = this.boneList.map((b) => [b.quaternion.clone(), b.position.clone()]);
    for (const b of this.boneList) { b.quaternion.copy(this.rest[b.name].q); b.position.copy(this.rest[b.name].p); }
    const mesh = new THREE.SkinnedMesh(geometry, material);
    mesh.castShadow = true; mesh.receiveShadow = true; mesh.frustumCulled = false;
    this.placeholder.add(mesh);
    mesh.bind(this.skeleton, new THREE.Matrix4());
    this.skinned.push(mesh);
    this.boneList.forEach((b, i) => { b.quaternion.copy(pose[i][0]); b.position.copy(pose[i][1]); });
    return mesh;
  }

  buildBones() {
    const list = [];
    // A body whose head was made turned (head_rest_yaw degrees) binds with its head bone turned so;
    // head_yaw 0 then faces forward, and the whole head turns rigidly on that bone.
    this.restWorldQ = {};
    const headRest = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), (this.rig.head_rest_yaw || 0) * D2R);
    const add = (name, parent, at) => {
      const b = new THREE.Bone(); b.name = name;
      this.restAt[name] = V(at);
      const pq = parent ? this.restWorldQ[parent] : new THREE.Quaternion();
      b.position.copy(parent ? V(at).sub(this.restAt[parent]).applyQuaternion(pq.clone().invert()) : V(at));
      if (name === 'head') b.quaternion.copy(pq.clone().invert().multiply(headRest));
      this.restWorldQ[name] = pq.clone().multiply(b.quaternion);
      if (parent) this.bones[parent].add(b);
      this.bones[name] = b; list.push(b);
    };
    for (const b of this.rig.bones) add(b.name, b.parent, b.at);
    // the toes: three segments each, along the toe's direction from the foot
    const tz = this.rig.toes;
    this.toes = [];
    for (const side of ['l', 'r']) {
      const sx = side === 'l' ? 1 : -1;
      for (const t of tz.toes) {
        const a = (t.dir + t.splay) * D2R;
        const d = new THREE.Vector3(Math.sin(a) * sx, 0, Math.cos(a)).normalize();
        const start = this.restAt[`foot_${side}`].clone().add(new THREE.Vector3(0, 0.0014, 0)).addScaledVector(d, 0.0015);
        let parent = `foot_${side}`, at = start.clone();
        const segs = [];
        tz.segments.forEach((len, k) => {
          const name = `toe_${side}_${t.n}${'abc'[k]}`;
          add(name, parent, at.toArray());
          segs.push({ name, len: len * t.scale, r: tz.radius[k] * Math.sqrt(t.scale), from: at.clone() });
          at = at.clone().addScaledVector(d, len * t.scale);
          parent = name;
        });
        this.toes.push({ side, n: t.n, d, axis: new THREE.Vector3(0, 1, 0).cross(d).normalize(), segs, tip: at });
      }
    }
    this.boneList = list;
    this.group.add(this.bones.root);
    this.skeleton = new THREE.Skeleton(list);
    this.boneIndex = Object.fromEntries(list.map((b, i) => [b.name, i]));
  }

  // The rest frames the driver needs: each driven bone's rest rotation and its parent's world rest rotation.
  recordRest() {
    this.group.updateMatrixWorld(true);
    this.rest = {};
    const inv = new THREE.Matrix4().copy(this.group.matrixWorld).invert();
    for (const b of this.boneList) {
      const m = new THREE.Matrix4().multiplyMatrices(inv, b.parent.matrixWorld);
      const pq = new THREE.Quaternion(); m.decompose(new THREE.Vector3(), pq, new THREE.Vector3());
      this.rest[b.name] = { q: b.quaternion.clone(), p: b.position.clone(), parentQ: pq, parentQi: pq.clone().invert() };
    }
  }

  // A rotation given in the parrot's frame, as the bone's parent sees it at rest, before its rest rotation.
  pose(name, qModel, offset = null, frame = 'model') {
    const b = this.bones[name], r = this.rest[name];
    if (!b) return;
    if (frame === 'local') { b.quaternion.copy(qModel).multiply(r.q); b.position.copy(r.p); return; }
    const q = r.parentQi.clone().multiply(qModel).multiply(r.parentQ);
    if (frame === 'absolute') b.quaternion.copy(q); else b.quaternion.copy(q).multiply(r.q);
    if (offset) b.position.copy(r.p).add(offset.clone().applyQuaternion(r.parentQi)); else b.position.copy(r.p);
  }

  buildBody() {
    const pts = [[0, 0.020, -0.054], [0, 0.036, -0.042], [0, 0.074, -0.018], [0, 0.114, 0.002], [0, 0.146, 0.013], [0, 0.170, 0.022], [0, 0.193, 0.029], [0, 0.213, 0.033]].map(V);
    const radii = [[0.012, 0.010, 0.010], [0.033, 0.035, 0.022], [0.047, 0.050, 0.029], [0.045, 0.047, 0.030], [0.034, 0.034, 0.027], [0.025, 0.027, 0.023], [0.0235, 0.031, 0.023], [0.004, 0.006, 0.004]];
    const curve = new THREE.CatmullRomCurve3(pts, false, 'centripetal');
    // radii along the curve's length: each control point's arc position
    const lens = curve.getLengths(400), total = lens[lens.length - 1];
    const knot = pts.map((p) => { let best = 0, bd = 1e9; for (let i = 0; i <= 400; i++) { const d = curve.getPoint(i / 400).distanceTo(p); if (d < bd) { bd = d; best = i; } } return lens[best] / total; });
    const radiusAt = (t) => {
      let k = 0; while (k < knot.length - 2 && t > knot[k + 1]) k++;
      const a = knot[k], b = knot[k + 1], x = Math.min(1, Math.max(0, (t - a) / (b - a)));
      const e = x * x * (3 - 2 * x);
      return radii[k].map((r, i) => mix(r, radii[k + 1][i], e));
    };
    this.bodyCurve = curve;
    const geo = loft(curve, (t) => [...radiusAt(t), 0], 96, 64);
    const ts = geo.userData.t, B = this.boneIndex;
    skin(geo, (i) => {
      const t = ts[i];
      const head = smooth(0.70, 0.80, t), neck = smooth(0.50, 0.64, t) * (1 - head), tail = 1 - smooth(0.0, 0.08, t);
      const body = Math.max(0, 1 - head - neck - tail);
      return [[B.body, body], [B.neck, neck], [B.head, head], [B.tail, tail]].filter((w) => w[1] > 1e-4).concat([[B.body, 1e-4]]);
    });
    const tex = plumageTextures((t) => { const r = radiusAt(t); return (r[0] + (r[1] + r[2]) / 2) / 2; });
    this.bodyMaterial = new THREE.MeshPhysicalMaterial({ map: tex.map, normalMap: tex.normalMap, normalScale: new THREE.Vector2(0.9, 0.9),
      roughness: 0.82, metalness: 0, sheen: 0.55, sheenColor: new THREE.Color('#c9cdd2'), sheenRoughness: 0.55 });
    const mesh = new THREE.SkinnedMesh(geo, this.bodyMaterial);
    mesh.name = 'body'; mesh.castShadow = true; mesh.receiveShadow = true; mesh.frustumCulled = false;
    this.placeholder.add(mesh);
    this.skinned.push(mesh);
  }

  buildBeak() {
    const B = this.boneIndex;
    const mat = new THREE.MeshPhysicalMaterial({ color: '#121314', roughness: 0.36, metalness: 0, clearcoat: 0.6, clearcoatRoughness: 0.35 });
    // the upper mandible: a deep hook over the lower
    const up = new THREE.CatmullRomCurve3([[0, 0.2005, 0.049], [0, 0.2015, 0.060], [0, 0.1965, 0.0705], [0, 0.1865, 0.0765], [0, 0.1745, 0.0755], [0, 0.1665, 0.0705]].map(V));
    const ug = loft(up, (t) => { const w = 0.0105 * Math.pow(1 - t, 0.75) + 0.0007; const hgt = 0.0105 * Math.pow(1 - t, 0.9) + 0.0008; return [w, 0.0012 + hgt * 0.15, hgt, 0]; }, 40, 24, new THREE.Vector3(1, 0, 0));
    skin(ug, () => [[B.upper_mandible, 1]]);
    const lo = new THREE.CatmullRomCurve3([[0, 0.1835, 0.0475], [0, 0.1795, 0.0575], [0, 0.1795, 0.0650], [0, 0.1825, 0.0690]].map(V));
    const lg = loft(lo, (t) => { const w = 0.0098 * Math.pow(1 - t, 0.6) + 0.0012; return [w, 0.0035 * (1 - t) + 0.001, 0.006 * (1 - t) + 0.001, 0]; }, 24, 20, new THREE.Vector3(1, 0, 0));
    skin(lg, () => [[B.lower_mandible, 1]]);
    // the cere: a dark band of bare skin at the upper mandible's base
    const cere = new THREE.SphereGeometry(0.0062, 20, 12, 0, Math.PI * 2, 0, Math.PI / 2);
    cere.scale(1.15, 0.5, 0.85); cere.rotateX(-0.25); cere.translate(0, 0.2008, 0.0498);
    skin(cere, () => [[B.upper_mandible, 1]]);
    const beak = new THREE.SkinnedMesh(merge([ug, lg]), mat);
    const cereMesh = new THREE.SkinnedMesh(cere, new THREE.MeshPhysicalMaterial({ color: '#2a2b2d', roughness: 0.6 }));
    for (const m of [beak, cereMesh]) { m.castShadow = true; m.frustumCulled = false; this.placeholder.add(m); this.skinned.push(m); }
  }

  buildEyes() {
    // the eyeball: a pale yellow-white iris round a black pupil, under a clear, glossy cornea
    for (const name of ['eye_l', 'eye_r']) {
      const geo = new THREE.SphereGeometry(0.0056, 48, 32);
      geo.rotateX(Math.PI / 2); // the sphere's pole looks along +z, the socket's axis
      const colors = [], p = new THREE.Vector3();
      const pupil = new THREE.Color('#050505'), iris = new THREE.Color('#efe6c8'), irisOut = new THREE.Color('#d9cf9f'), lid = new THREE.Color('#d8d3cb');
      for (let i = 0; i < geo.attributes.position.count; i++) {
        p.fromBufferAttribute(geo.attributes.position, i).normalize();
        const a = Math.acos(Math.max(-1, Math.min(1, p.z))) / D2R;
        const c = a < 17 ? pupil : a < 21 ? pupil.clone().lerp(iris, (a - 17) / 4) : a < 40 ? iris.clone().lerp(irisOut, (a - 21) / 19) : a < 44 ? new THREE.Color('#3a3530') : lid;
        colors.push(c.r, c.g, c.b);
      }
      geo.setAttribute('color', new THREE.Float32BufferAttribute(colors.map((x) => Math.pow(x, 2.2)), 3));
      const eye = new THREE.Mesh(geo, new THREE.MeshPhysicalMaterial({ vertexColors: true, roughness: 0.12, clearcoat: 1, clearcoatRoughness: 0.03, ior: 1.38, specularIntensity: 1 }));
      eye.position.set(0, 0, -0.0022); // sunk a little into the bare skin
      this.sockets[name].add(eye);
      // a bare-skin ring (the eyelids) round the eye
      const ring = new THREE.Mesh(new THREE.TorusGeometry(0.0057, 0.0013, 10, 36), new THREE.MeshPhysicalMaterial({ color: '#d7d2ca', roughness: 0.7 }));
      ring.position.set(0, 0, -0.0005);
      this.sockets[name].add(ring);
    }
  }

  buildFeet() {
    const B = this.boneIndex;
    const geos = [];
    for (const toe of this.toes) {
      toe.segs.forEach((s, k) => {
        const g = new THREE.CapsuleGeometry(s.r, s.len, 4, 10);
        g.rotateX(Math.PI / 2); // along +z
        const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), toe.d);
        g.applyQuaternion(q);
        g.translate(...s.from.clone().addScaledVector(toe.d, s.len / 2).toArray());
        skin(g, () => [[B[s.name], 1]]);
        geos.push(g);
        if (k === toe.segs.length - 1) { // the claw: dark, curved down
          const cg = new THREE.ConeGeometry(s.r * 0.75, 0.0065, 10, 1);
          cg.rotateX(Math.PI / 2 + 0.6);
          cg.applyQuaternion(q);
          cg.translate(...toe.tip.clone().addScaledVector(toe.d, 0.0022).add(new THREE.Vector3(0, -0.0012, 0)).toArray());
          skin(cg, () => [[B[s.name], 1]]);
          cg.userData.claw = true;
          geos.push(cg);
        }
      });
    }
    // the legs: a short scaly shank from each foot up into the belly's feathers
    for (const side of ['l', 'r']) {
      const top = this.restAt[`leg_${side}`], bottom = this.restAt[`foot_${side}`].clone().add(new THREE.Vector3(0, 0.002, 0));
      const len = top.distanceTo(bottom);
      const g = new THREE.CylinderGeometry(0.0042, 0.0036, len, 12, 4);
      g.translate(0, len / 2, 0);
      g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), top.clone().sub(bottom).normalize()));
      g.translate(...bottom.toArray());
      skin(g, (i, p) => { const f = Math.min(1, Math.max(0, (p.y - bottom.y) / (top.y - bottom.y))); return [[B[`leg_${side}`], f], [B[`foot_${side}`], 1 - f]]; });
      geos.push(g);
    }
    const claws = geos.filter((g) => g.userData.claw), skinGeos = geos.filter((g) => !g.userData.claw);
    for (const g of geos) if (!g.attributes.uv) g.setAttribute('uv', new THREE.Float32BufferAttribute(new Float32Array(2 * g.attributes.position.count), 2));
    const feet = new THREE.SkinnedMesh(merge(skinGeos.map((g) => g.index ? g : g)), new THREE.MeshPhysicalMaterial({ color: '#4a4b4f', roughness: 0.7, sheen: 0.2, sheenColor: new THREE.Color('#8a8a8a') }));
    const clawMesh = new THREE.SkinnedMesh(merge(claws), new THREE.MeshPhysicalMaterial({ color: '#16171a', roughness: 0.4, clearcoat: 0.4 }));
    for (const m of [feet, clawMesh]) { m.castShadow = true; m.frustumCulled = false; this.placeholder.add(m); this.skinned.push(m); }
  }

  // Wing and tail feathers: cards on the wing and tail bones, placed again every frame.
  buildFeathers() {
    const card = new THREE.PlaneGeometry(1, 1, 3, 8);
    card.translate(0, 0.5, 0); // the quill at the origin, the tip at +y
    const p = card.attributes.position;
    for (let i = 0; i < p.count; i++) { const x = p.getX(i), y = p.getY(i); p.setZ(i, 0.12 * (x * x) + 0.05 * y * y); }
    card.computeVertexNormals();
    const mk = (tex, n) => {
      const m = new THREE.InstancedMesh(card, new THREE.MeshPhysicalMaterial({ map: tex, alphaTest: 0.5, side: THREE.DoubleSide, roughness: 0.78, sheen: 0.4, sheenColor: new THREE.Color('#bfc3c8'), sheenRoughness: 0.6 }), n);
      m.castShadow = true; m.receiveShadow = true; m.frustumCulled = false;
      this.placeholder.add(m);
      return m;
    };
    const flight = featherTexture('flight'), covert = featherTexture('covert');
    this.feathers = [];
    const rand = rng(23);
    const A = new THREE.Vector3(0, -0.108, -0.092).normalize(); // a folded wing's long axis
    for (const side of ['l', 'r']) {
      const sx = side === 'l' ? 1 : -1;
      const out = new THREE.Vector3(0.96 * sx, 0.22, 0.12).normalize(); // the folded wing's outer face
      const across = new THREE.Vector3().crossVectors(out, A).normalize().multiplyScalar(sx); // toward the back edge
      const frame = (along, acrossBy, outBy) => new THREE.Vector3().addScaledVector(A, along).addScaledVector(across, acrossBy).addScaledVector(out, outBy);
      // primaries (dark), secondaries and coverts (grey), each [bone, base, length, width, colour, fan]
      const list = [];
      for (let i = 0; i < 9; i++) list.push({ bone: `wing_${side}_wrist`, base: frame(0.058 + i * 0.002, -0.004 + i * 0.0026, 0.0012 - i * 0.0006), len: 0.094 + 0.012 * Math.sin((i / 8) * Math.PI), wid: 0.019, col: '#3d4045', fan: (8 - i) * 6.5, tex: 'f' });
      for (let i = 0; i < 9; i++) list.push({ bone: `wing_${side}_elbow`, base: frame(0.026 + i * 0.0035, 0.010 + i * 0.0026, 0.0024 - i * 0.0002), len: 0.070, wid: 0.022, col: '#5f6368', fan: -i * 4, tex: 'f' });
      for (let r = 0; r < 3; r++) for (let i = 0; i < 7; i++) {
        list.push({ bone: r === 2 ? `wing_${side}_elbow` : `wing_${side}_shoulder`, base: frame(0.004 + r * 0.016 + rand() * 0.003, -0.014 + i * 0.0062, 0.0058 + r * 0.0016), len: 0.032 + r * 0.012, wid: 0.016 + r * 0.002, col: r === 2 ? '#6b6f74' : '#7b7f84', fan: (i - 3) * 2, tex: 'c' });
      }
      for (const f of list) {
        f.side = side; f.sx = sx; f.A = A; f.out = out; f.across = across;
        f.base.add(this.restAt[`wing_${side}_shoulder`]);
      }
      this.feathers.push(...list);
    }
    // the tail: twelve scarlet feathers, fanned a little, under red coverts
    const tailDir = new THREE.Vector3(0, -0.62, -0.78).normalize();
    for (let i = 0; i < 12; i++) {
      const fan = (i - 5.5) * 3.2;
      this.feathers.push({ bone: 'tail', base: this.restAt.tail.clone().add(new THREE.Vector3((i - 5.5) * 0.0026, 0.002 - Math.abs(i - 5.5) * 0.0003, 0.002)), len: 0.082, wid: 0.019, col: '#c0161f', fan, tex: 'f', tail: true, dir: tailDir });
    }
    for (let i = 0; i < 8; i++) {
      const fan = (i - 3.5) * 7;
      this.feathers.push({ bone: 'tail', base: this.restAt.tail.clone().add(new THREE.Vector3((i - 3.5) * 0.004, 0.006, 0.010)), len: 0.040, wid: 0.018, col: '#ae1a22', fan, tex: 'c', tail: true, under: true, dir: new THREE.Vector3(0, -0.8, -0.6).normalize() });
    }
    const flights = this.feathers.filter((f) => f.tex === 'f'), coverts = this.feathers.filter((f) => f.tex === 'c');
    this.flightMesh = mk(flight, flights.length); this.covertMesh = mk(covert, coverts.length);
    const c = new THREE.Color();
    flights.forEach((f, i) => { f.mesh = this.flightMesh; f.i = i; this.flightMesh.setColorAt(i, c.set(f.col)); });
    coverts.forEach((f, i) => { f.mesh = this.covertMesh; f.i = i; this.covertMesh.setColorAt(i, c.set(f.col)); });
    // each feather's rest transform in its bone's frame, and how it turns as the wing spreads
    for (const f of this.feathers) {
      const dir = f.tail ? f.dir.clone() : f.A.clone();
      const normal = f.tail ? (f.under ? new THREE.Vector3(0, -0.6, 0.8) : new THREE.Vector3(0, 0.78, -0.62)).normalize() : f.out.clone();
      const qFan = new THREE.Quaternion().setFromAxisAngle(normal, f.fan * D2R * (f.tail ? 1 : 0.15) * (f.sx || 1));
      dir.applyQuaternion(qFan);
      const x = new THREE.Vector3().crossVectors(dir, normal).normalize();
      const z = new THREE.Vector3().crossVectors(x, dir).normalize();
      f.basis = new THREE.Matrix4().makeBasis(x, dir, z);
      f.scale = new THREE.Vector3(f.wid, f.len, 1);
      f.normal = normal;
      f.local = f.base.clone().sub(this.restAt[f.bone]);
    }
  }

  // --- posing ----------------------------------------------------------------------------------
  update(dt) {
    this.joints.step(dt);
    const J = (n) => this.joints.get(n);
    const yaw = J('head_yaw') * D2R, pitch = J('head_pitch') * D2R, roll = J('head_roll') * D2R;
    const Q = (axis, a) => new THREE.Quaternion().setFromAxisAngle(axis, a);
    const X = new THREE.Vector3(1, 0, 0), Y = new THREE.Vector3(0, 1, 0), Z = new THREE.Vector3(0, 0, 1);
    const legL = J('leg_l'), legR = J('leg_r');
    // the body: lower as the legs bend, leaning to the more bent side
    const legRest = this.joints.spec[this.joints.index.leg_l].rest, crouch = (legL + legR) / 2 - legRest;
    this.pose('body', Q(Z, -(legL - legR) * 5 * D2R).multiply(Q(X, crouch * 4 * D2R)), new THREE.Vector3(0, -0.008 * crouch, 0));
    // the turn shared by the neck (three tenths) and the head; a head made turned (rest h) is at its
    // bind pose when head_yaw is h, and faces forward at 0
    const h = (this.rig.head_rest_yaw || 0) * D2R;
    const share = this.rig.share?.neck ?? 0.4;
    this.pose('neck', Q(Y, share * (yaw - h)).multiply(Q(X, J('neck_pitch') * D2R - share * pitch)).multiply(Q(Z, 0.3 * roll)));
    // the head: turned from facing forward (a head made turned drops its rest turn here)
    this.pose('head', Q(Y, yaw - share * (yaw - h)).multiply(Q(X, -(1 - share) * pitch)).multiply(Q(Z, 0.7 * roll)), null, h ? 'absolute' : 'model');
    // the beak, in the head's own frame: the lower mandible drops, the upper lifts a little (a parrot's
    // upper beak is hinged to its skull too)
    const open = J('beak_open') * D2R;
    if (this.mouthPlug) this.mouthPlug.visible = open > 0.02;
    this.pose('lower_mandible', Q(X, open), null, 'local');
    this.pose('upper_mandible', Q(X, -0.2 * open), null, 'local');
    // the wings: the shoulder swings the folded wing out and turns its face up; elbow and wrist open it
    for (const side of ['l', 'r']) {
      const s = J(`wing_${side}`), sx = side === 'l' ? 1 : -1;
      const A = new THREE.Vector3(0, -0.108, -0.092).normalize();
      const outA = new THREE.Vector3(0.93 * sx, 0.12, -0.35).normalize();
      const swing = new THREE.Quaternion().setFromUnitVectors(A, outA);
      const twist = Q(outA, -sx * 75 * D2R);
      const full = twist.multiply(swing);
      if (this.rig.wing_mode === 'lift') { // a body whose folded wings are part of its skin: the wing lifts off the side
        const lift = (this.rig.wing_lift ?? 10) * D2R;
        this.pose(`wing_${side}_shoulder`, Q(Z, sx * lift * s));
        this.pose(`wing_${side}_elbow`, new THREE.Quaternion());
        this.pose(`wing_${side}_wrist`, Q(Z, sx * 0.5 * lift * s));
      } else {
        this.pose(`wing_${side}_shoulder`, new THREE.Quaternion().slerp(full, s));
        this.pose(`wing_${side}_elbow`, Q(new THREE.Vector3(0.96 * sx, 0.22, 0.12).normalize(), sx * 18 * D2R * s));
        this.pose(`wing_${side}_wrist`, Q(new THREE.Vector3(0.96 * sx, 0.22, 0.12).normalize(), sx * 14 * D2R * s));
      }
      this.pose(`leg_${side}`, new THREE.Quaternion());
      this.pose(`foot_${side}`, new THREE.Quaternion());
    }
    // the toes curl round the bar: each joint by the arc its segments cover
    const rho = this.R + 0.0029;
    for (const toe of this.toes) {
      const g = J(`grip_${toe.side}`);
      if (this.rig.toe_rest === 'closed') { // a body modelled gripping: open lifts the toes off the bar
        toe.segs.forEach((s, k) => this.pose(s.name, Q(toe.axis, k === 0 ? (g - 1) * (this.rig.toe_open ?? 0.5) : 0)));
        continue;
      }
      toe.segs.forEach((s, k) => {
        const prev = k ? toe.segs[k - 1].len : 0;
        const arc = ((prev + s.len) / 2) / rho;
        const a = g * arc * (k === 0 ? 0.9 : 1.0) + (1 - g) * (k === 0 ? -0.12 : 0.05);
        this.pose(s.name, Q(toe.axis, a));
      });
    }
    this.pose('tail', new THREE.Quaternion());
    this.group.updateMatrixWorld(true);
    this.placeFeathers();
  }

  placeFeathers() {
    if (!this.feathers || !this.flightMesh) return;
    const inv = new THREE.Matrix4().copy(this.placeholder.matrixWorld).invert();
    const m = new THREE.Matrix4(), t = new THREE.Matrix4(), fanQ = new THREE.Quaternion(), local = new THREE.Vector3();
    for (const f of this.feathers) {
      const bone = this.bones[f.bone];
      let fanned = f.basis;
      if (!f.tail) {
        const s = this.joints.get(`wing_${f.side}`);
        if (s > 0) { fanQ.setFromAxisAngle(f.normal, f.fan * D2R * 0.9 * s * f.sx); fanned = new THREE.Matrix4().makeRotationFromQuaternion(fanQ).multiply(f.basis); }
      }
      local.copy(f.local);
      t.compose(local, new THREE.Quaternion(), new THREE.Vector3(1, 1, 1));
      m.multiplyMatrices(inv, bone.matrixWorld).multiply(t).multiply(fanned).scale(f.scale);
      f.mesh.setMatrixAt(f.i, m);
    }
    this.flightMesh.instanceMatrix.needsUpdate = true; this.covertMesh.instanceMatrix.needsUpdate = true;
  }

  /** Swap the placeholder for a body made for this rig: a glTF scene whose skinned meshes use the
   *  rig's bone names. Its bones are matched by name and driven by the same joints. */
  useBody(gltfScene) {
    const meshes = [];
    gltfScene.traverse((o) => { if (o.isSkinnedMesh) meshes.push(o); });
    if (!meshes.length) throw new Error('The body has no skinned mesh.');
    const missing = this.boneList.filter((b) => !b.name.startsWith('toe_')).map((b) => b.name).filter((n) => !meshes[0].skeleton.bones.some((b) => b.name === n));
    if (missing.length) throw new Error(`The body lacks bones: ${missing.join(', ')}`);
    this.group.remove(this.placeholder);
    this.group.remove(this.bones.root);
    const root = meshes[0].skeleton.bones.find((b) => b.name === 'root');
    this.bones = {}; this.boneList = [];
    root.traverse((b) => { if (b.isBone) { this.bones[b.name] = b; this.boneList.push(b); } });
    for (const [name, s] of Object.entries(this.rig.sockets)) this.bones[s.bone].add(this.sockets[name]);
    this.group.add(gltfScene);
    this.feathers = null;
    for (const m of meshes) { m.castShadow = true; m.receiveShadow = true; m.frustumCulled = false; }
    this.skinned = meshes;
    this.recordRest();
    this.update(0);
  }

  /** Where each eye is and which way it looks, in the world. */
  eyePose(name, pos, quat) {
    this.sockets[name].getWorldPosition(pos);
    this.sockets[name].getWorldQuaternion(quat);
  }
}
