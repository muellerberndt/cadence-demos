// The larva in the Matrix: an articulated wireframe body about 4 mm long, in body coordinates
// (x forward, y left, z up, millimetres). Head, trunk and yolk as dim fills with glowing edges;
// the eyes brighter, each turning about its own axis; the swim bladder bright; a tail of twelve
// segments drawn as rings and longitudinal lines rewritten every frame, bent along a travelling
// wave during a bout and straight while gliding, with the fin fold and the caudal fin; two
// pectoral fins; glowing points at the myomere joints. Beneath the fish a faint disc of light
// rests on the floor.
//
// update(state) takes body.js state(): { position: [x, y, z], heading, pitch, roll, eyeLeft,
// eyeRight (degrees, positive converging), tailPhase, tailAmplitude (0..1), tailCurvature
// (-1..1, positive bending to the left) }.
import * as THREE from "three";
import { LENGTH, SNOUT, TAIL_SEGMENTS } from "./body.js";
import { wire, lineMaterial, segments, radialTexture, dotTexture, MATRIX } from "./aquarium.js";

const TWO_PI = Math.PI * 2, DEG = Math.PI / 180;
const TAIL_BASE = -0.1;                               // mm, where the tail leaves the trunk
const TAIL_LENGTH = LENGTH - SNOUT + TAIL_BASE;       // mm, 2.6: the tip sits at -2.7
const SEG = TAIL_LENGTH / TAIL_SEGMENTS;
const N_RING = 6;
const RING = Array.from({ length: N_RING }, (_, j) => (30 + 60 * j) * DEG);
const BEND_CURVE = 0.26;        // rad per segment at curvature 1: twelve segments close a C
const BEND_WAVE = 0.22;         // rad per segment at amplitude 1 at the tip
const WAVE_K = TWO_PI * 0.75 / TAIL_SEGMENTS;   // three quarters of a wavelength along the tail
const MAX_SEGMENTS = 320;

const COLOURS = { edge: MATRIX.edge, eye: MATRIX.bright, fill: MATRIX.fill, eyeFill: 0x0b3a1c, bladder: MATRIX.bright };

const _a = new THREE.Vector3(), _b = new THREE.Vector3(), _c = new THREE.Vector3();

// the tail's half width, half height and fin fold heights along it, u from 0 (base) to 1 (tip)
const halfWidth = (u) => 0.03 + 0.19 * Math.pow(1 - u, 1.2);
const halfHeight = (u) => 0.04 + 0.22 * (1 - u);
const dorsalFin = (u) => (u < 0.12 ? 0 : 0.2 * Math.sin(Math.PI * (u - 0.12) / 0.88));
const ventralFin = (u) => (u < 0.3 ? 0 : 0.16 * Math.sin(Math.PI * (u - 0.3) / 0.7));

function ellipsoid(sx, sy, sz, x, y, z, edge = COLOURS.edge, edgeOpacity = 0.75, fill = COLOURS.fill, fillOpacity = 0.8, segs = 12, rings = 8) {
  const g = wire(new THREE.SphereGeometry(1, segs, rings), edge, edgeOpacity, fill, fillOpacity);
  g.scale.set(sx, sy, sz); g.position.set(x, y, z);
  return g;
}

export class FishMesh {
  constructor() {
    this.group = new THREE.Group();
    const body = this.group;

    // the head with the snout at x = SNOUT, the trunk behind it, the yolk below, the bladder above
    body.add(ellipsoid(0.45, 0.3, 0.28, SNOUT - 0.45, 0, 0));
    body.add(ellipsoid(0.34, 0.2, 0.24, 0.12, 0, 0, COLOURS.edge, 0.6));
    body.add(ellipsoid(0.38, 0.2, 0.18, 0.55, 0, -0.26, COLOURS.edge, 0.55));
    body.add(ellipsoid(0.22, 0.09, 0.09, 0.05, 0, 0.1, COLOURS.bladder, 0.95, 0x0b3a1c, 0.6, 8, 5));

    // the eyes: each in its own group that turns about z, a lens ring and a pupil on its gaze
    this.eyes = [1, -1].map((side) => {
      const pivot = new THREE.Group(); pivot.position.set(0.95, side * 0.27, 0.03); body.add(pivot);
      const ball = wire(new THREE.SphereGeometry(0.16, 10, 7), COLOURS.eye, 0.95, COLOURS.eyeFill, 0.85); pivot.add(ball);
      const gaze = new THREE.Group(); gaze.rotation.z = side * 40 * DEG; pivot.add(gaze);
      const ring = [];
      for (let j = 0; j < 12; j++) { const a0 = j / 12 * TWO_PI, a1 = (j + 1) / 12 * TWO_PI; ring.push(0.15, 0.06 * Math.cos(a0), 0.06 * Math.sin(a0), 0.15, 0.06 * Math.cos(a1), 0.06 * Math.sin(a1)); }
      gaze.add(segments(ring, COLOURS.eye, 0.9));
      const pupil = new THREE.Points(new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute([0.165, 0, 0], 3)), new THREE.PointsMaterial({ color: COLOURS.eye, size: 4, sizeAttenuation: false, map: dotTexture(), transparent: true, opacity: 0.95, blending: THREE.AdditiveBlending, depthWrite: false }));
      pupil.renderOrder = 2; gaze.add(pupil);
      return { side, pivot };
    });

    // the pectoral fins: two small triangles at the trunk
    const fins = [];
    for (const s of [1, -1]) {
      const b0 = [0.22, s * 0.2, -0.05], t1 = [-0.12, s * 0.5, -0.12], t2 = [0.06, s * 0.52, 0.02];
      fins.push(...b0, ...t1, ...t1, ...t2, ...t2, ...b0);
    }
    body.add(segments(fins, COLOURS.edge, 0.7));

    // the tail as line segments rewritten every frame, and the joints as glowing points
    this.linePos = new Float32Array(6 * MAX_SEGMENTS);
    const lineGeo = new THREE.BufferGeometry(); lineGeo.setAttribute("position", new THREE.BufferAttribute(this.linePos, 3));
    this.lines = new THREE.LineSegments(lineGeo, lineMaterial(COLOURS.edge, 0.8)); this.lines.frustumCulled = false; this.lines.renderOrder = 1; body.add(this.lines);
    this.pointPos = new Float32Array(3 * (TAIL_SEGMENTS + 1));
    const pointGeo = new THREE.BufferGeometry(); pointGeo.setAttribute("position", new THREE.BufferAttribute(this.pointPos, 3));
    this.points = new THREE.Points(pointGeo, new THREE.PointsMaterial({ color: COLOURS.eye, size: 3, sizeAttenuation: false, map: dotTexture(), transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending, depthWrite: false }));
    this.points.frustumCulled = false; this.points.renderOrder = 2; body.add(this.points);
    this.spine = Array.from({ length: TAIL_SEGMENTS + 1 }, () => new THREE.Vector3());
    this.dorsal = Array.from({ length: TAIL_SEGMENTS + 1 }, () => new THREE.Vector3());
    this.ventral = Array.from({ length: TAIL_SEGMENTS + 1 }, () => new THREE.Vector3());
    this.ringPts = Array.from({ length: TAIL_SEGMENTS + 1 }, () => Array.from({ length: N_RING }, () => new THREE.Vector3()));

    // the light on the floor beneath the fish
    this.floorLight = new THREE.Mesh(new THREE.CircleGeometry(1, 28), new THREE.MeshBasicMaterial({ map: radialTexture("rgba(57,255,106,.55)", "rgba(57,255,106,0)"), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    this.floorLight.renderOrder = 1;
    this.update({ position: [10, 5, 4.5], heading: 0, pitch: 0, roll: 0, eyeLeft: 0, eyeRight: 0, tailPhase: 0, tailAmplitude: 0, tailCurvature: 0 });
  }

  addTo(world) { world.add(this.group, this.floorLight); return this; }

  update(state) {
    const [x, y, z] = state.position;
    this.group.position.set(x, y, z);
    this.group.rotation.set(state.roll || 0, -(state.pitch || 0), state.heading || 0, "ZYX");
    for (const e of this.eyes) e.pivot.rotation.z = -e.side * (e.side > 0 ? state.eyeLeft || 0 : state.eyeRight || 0) * DEG;

    // the spine: a chain of segments turning by the C-bend and the travelling wave
    const amp = state.tailAmplitude || 0, curve = state.tailCurvature || 0, phase = state.tailPhase || 0;
    let psi = Math.PI;
    this.spine[0].set(TAIL_BASE, 0, 0);
    for (let i = 1; i <= TAIL_SEGMENTS; i++) {
      const u = i / TAIL_SEGMENTS;
      psi += -curve * (0.5 + 0.5 * u) * BEND_CURVE + amp * (0.15 + 0.85 * u * u) * BEND_WAVE * Math.sin(phase - WAVE_K * i);
      this.spine[i].set(this.spine[i - 1].x + SEG * Math.cos(psi), this.spine[i - 1].y + SEG * Math.sin(psi), 0);
      const nx = -Math.sin(psi), ny = Math.cos(psi), rw = halfWidth(u), rh = halfHeight(u);
      for (let j = 0; j < N_RING; j++) this.ringPts[i][j].set(this.spine[i].x + nx * rw * Math.cos(RING[j]), this.spine[i].y + ny * rw * Math.cos(RING[j]), rh * Math.sin(RING[j]));
      this.dorsal[i].set(this.spine[i].x, this.spine[i].y, rh + dorsalFin(u));
      this.ventral[i].set(this.spine[i].x, this.spine[i].y, -rh - ventralFin(u));
    }
    for (let j = 0; j < N_RING; j++) this.ringPts[0][j].set(TAIL_BASE, halfWidth(0) * Math.cos(RING[j]), halfHeight(0) * Math.sin(RING[j]));
    this.dorsal[0].set(TAIL_BASE, 0, halfHeight(0)); this.ventral[0].set(TAIL_BASE, 0, -halfHeight(0));

    const pos = this.linePos; let n = 0;
    const put = (a, b) => { pos[n++] = a.x; pos[n++] = a.y; pos[n++] = a.z; pos[n++] = b.x; pos[n++] = b.y; pos[n++] = b.z; };
    for (let i = 0; i <= TAIL_SEGMENTS; i++) {
      const ring = this.ringPts[i];
      for (let j = 0; j < N_RING; j++) put(ring[j], ring[(j + 1) % N_RING]);
      if (i === 0) continue;
      const prev = this.ringPts[i - 1];
      for (let j = 0; j < N_RING; j++) put(prev[j], ring[j]);
      put(this.spine[i - 1], this.spine[i]);
      put(this.dorsal[i - 1], this.dorsal[i]); put(this.ventral[i - 1], this.ventral[i]);
    }
    // the caudal fin: a fan past the tip, joined to the fin fold
    const tip = this.spine[TAIL_SEGMENTS], tx = Math.cos(psi), ty = Math.sin(psi);
    _a.set(tip.x + 0.2 * tx, tip.y + 0.2 * ty, 0.22); _b.set(tip.x + 0.3 * tx, tip.y + 0.3 * ty, 0); _c.set(tip.x + 0.2 * tx, tip.y + 0.2 * ty, -0.22);
    put(tip, _a); put(tip, _b); put(tip, _c); put(_a, _b); put(_b, _c);
    put(this.dorsal[TAIL_SEGMENTS], _a); put(this.ventral[TAIL_SEGMENTS], _c);
    this.lines.geometry.setDrawRange(0, n / 3);
    this.lines.geometry.attributes.position.needsUpdate = true;
    for (let i = 0; i <= TAIL_SEGMENTS; i++) { this.pointPos[3 * i] = this.spine[i].x; this.pointPos[3 * i + 1] = this.spine[i].y; this.pointPos[3 * i + 2] = this.spine[i].z; }
    this.points.geometry.attributes.position.needsUpdate = true;

    // the light on the floor: wider and fainter the higher the fish swims
    this.floorLight.position.set(x, y, 0.02);
    const r = 1.2 + 0.25 * z;
    this.floorLight.scale.set(r, r, 1);
    this.floorLight.material.opacity = 0.5 / (1 + 0.35 * z);
  }
}
