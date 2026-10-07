// The larva in the Matrix: a wireframe Platynereis larva 2 mm long in body coordinates (x
// forward, y left, z up, millimetres). The episphere as a dim fill with glowing edges, the
// prototroch as a ring of 23 short lines that beat with the ciliary drive of their side, the
// three chaetigerous segments and the pygidium as fills with rings, the paratroch bands as
// three smaller rings of beating lines, two eye cups, and the chaetae as fans of lines on each
// parapodium that spread when the parapodia rise. A longitudinal contraction shortens the body
// and bends the trunk toward the contracted side. The whole body spins about its axis by
// state.roll and nods by the helix angle, so the drawn axis is the one the body swims along.
// Beneath the larva a faint disc of light rests on the floor.
//
// update(state) takes larva_body.js state(): { time, position: [x, y, z], heading, pitch,
// roll, cilia: {left, right}, arrest, muscle: {left, right}, parapodia }.
import * as THREE from "three";
import { HELIX_ANGLE } from "./larva_body.js";
import { wire, lineMaterial, segments, radialTexture, dotTexture, MATRIX } from "./aquarium.js";

const TWO_PI = Math.PI * 2, DEG = Math.PI / 180;
export const PROTOTROCH_CELLS = 23;          // the reconstruction's count
export const PARATROCH_CELLS = 30;           // three bands of ten, near the reconstruction's 34
const PROTOTROCH_X = 0.12, PROTOTROCH_R = 0.44, CILIUM = 0.17;
const PARATROCH = [[-0.22, 0.33], [-0.54, 0.29], [-0.86, 0.22]];   // [x, radius] of each band
const SEGMENTS = [[-0.06, 0.34, 0.32], [-0.38, 0.30, 0.28], [-0.70, 0.26, 0.24]];   // [x, half width, half height]
const CHAETAE = 4, CHAETA = 0.5;             // lines per parapodium, their length in mm
const BEAT_HZ = 3.0;                         // the drawn beat, slower than the real 15 Hz so the eye follows it
const BEAT_REST = 0.5, BEAT_SWING = 0.5;     // rad, the cilia's backward tilt and the metachronal swing
const WAVES = 3;                             // metachronal waves around a band
const BEND = 0.35, SHORTEN = 0.12;           // rad per unit one-sided contraction, shortening per unit contraction
const MAX_LINES = PROTOTROCH_CELLS + PARATROCH_CELLS + 6 * CHAETAE;

const COLOURS = { edge: MATRIX.edge, bright: MATRIX.bright, fill: MATRIX.fill, eyeFill: 0x0b3a1c };

const lerp = (a, b, u) => a + (b - a) * u;
const smooth = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));

function ellipsoid(sx, sy, sz, x, y, z, edgeOpacity = 0.7, fillOpacity = 0.8, segs = 12, rings = 8) {
  const g = wire(new THREE.SphereGeometry(1, segs, rings), COLOURS.edge, edgeOpacity, COLOURS.fill, fillOpacity);
  g.scale.set(sx, sy, sz); g.position.set(x, y, z);
  return g;
}

// A ring of line segments of radius r in the plane x = x0.
function ring(x0, r, n = 16) {
  const pts = [];
  for (let j = 0; j < n; j++) { const a0 = j / n * TWO_PI, a1 = (j + 1) / n * TWO_PI; pts.push(x0, r * Math.cos(a0), r * Math.sin(a0), x0, r * Math.cos(a1), r * Math.sin(a1)); }
  return pts;
}

export class LarvaMesh {
  constructor() {
    this.group = new THREE.Group();
    this.body = new THREE.Group();                     // nods by the helix angle inside the spinning group
    this.body.rotation.y = -HELIX_ANGLE;
    this.group.add(this.body);
    const body = this.body;

    // the episphere with the snout at x = 1, the prototroch's ring behind it
    body.add(ellipsoid(0.45, 0.42, 0.40, 0.55, 0, 0));
    body.add(segments(ring(PROTOTROCH_X, PROTOTROCH_R, 24), COLOURS.bright, 0.6));

    // the eye cups: a small circle on the episphere at 45 degrees out, a little dorsal, and a dot
    for (const side of [1, -1]) {
      const e = new THREE.Vector3(Math.cos(45 * DEG), side * Math.sin(45 * DEG), 0.3).normalize();
      const c = new THREE.Vector3(0.55 + 0.45 * e.x, 0.42 * e.y, 0.40 * e.z);
      const u = new THREE.Vector3(0, 0, 1).cross(e).normalize(), w = e.clone().cross(u).normalize();
      const pts = [];
      for (let j = 0; j < 8; j++) {
        const a0 = j / 8 * TWO_PI, a1 = (j + 1) / 8 * TWO_PI;
        pts.push(c.x + 0.07 * (u.x * Math.cos(a0) + w.x * Math.sin(a0)), c.y + 0.07 * (u.y * Math.cos(a0) + w.y * Math.sin(a0)), c.z + 0.07 * (u.z * Math.cos(a0) + w.z * Math.sin(a0)));
        pts.push(c.x + 0.07 * (u.x * Math.cos(a1) + w.x * Math.sin(a1)), c.y + 0.07 * (u.y * Math.cos(a1) + w.y * Math.sin(a1)), c.z + 0.07 * (u.z * Math.cos(a1) + w.z * Math.sin(a1)));
      }
      body.add(segments(pts, COLOURS.bright, 0.9));
      const dot = new THREE.Points(new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute([c.x + 0.02 * e.x, c.y + 0.02 * e.y, c.z + 0.02 * e.z], 3)), new THREE.PointsMaterial({ color: COLOURS.bright, size: 4, sizeAttenuation: false, map: dotTexture(), transparent: true, opacity: 0.95, blending: THREE.AdditiveBlending, depthWrite: false }));
      dot.renderOrder = 2; body.add(dot);
    }

    // the trunk: three segments, the pygidium, the rings between them; it bends with the muscles
    this.trunk = new THREE.Group(); this.trunk.position.set(0.1, 0, 0); body.add(this.trunk);
    const trunk = this.trunk, tx = (x) => x - 0.1;
    for (const [x, hw, hh] of SEGMENTS) trunk.add(ellipsoid(0.19, hw, hh, tx(x), 0, 0, 0.6, 0.75, 10, 7));
    trunk.add(ellipsoid(0.13, 0.17, 0.15, tx(-0.92), 0, 0, 0.6, 0.75, 8, 6));
    for (const [x, r] of PARATROCH) trunk.add(segments(ring(tx(x), r, 16), COLOURS.edge, 0.35));

    // the lines rewritten every frame: the prototroch cilia on the episphere's side, the
    // paratroch cilia and the chaetae on the trunk's side
    this.headPos = new Float32Array(6 * PROTOTROCH_CELLS);
    const headGeo = new THREE.BufferGeometry(); headGeo.setAttribute("position", new THREE.BufferAttribute(this.headPos, 3));
    this.headLines = new THREE.LineSegments(headGeo, lineMaterial(COLOURS.bright, 0.85)); this.headLines.frustumCulled = false; this.headLines.renderOrder = 1; body.add(this.headLines);
    this.trunkPos = new Float32Array(6 * (MAX_LINES - PROTOTROCH_CELLS));
    const trunkGeo = new THREE.BufferGeometry(); trunkGeo.setAttribute("position", new THREE.BufferAttribute(this.trunkPos, 3));
    this.trunkLines = new THREE.LineSegments(trunkGeo, lineMaterial(COLOURS.edge, 0.8)); this.trunkLines.frustumCulled = false; this.trunkLines.renderOrder = 1; trunk.add(this.trunkLines);

    // the light on the floor beneath the larva
    this.floorLight = new THREE.Mesh(new THREE.CircleGeometry(1, 28), new THREE.MeshBasicMaterial({ map: radialTexture("rgba(57,255,106,.55)", "rgba(57,255,106,0)"), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    this.floorLight.renderOrder = 1;

    this.phase = [0, 0];            // the beat phase of the left and the right cilia
    this.lastTime = null;
    this.update({ time: 0, position: [10, 5, 4.5], heading: 0, pitch: 0, roll: 0, cilia: { left: 0, right: 0 }, arrest: 0, muscle: { left: 0, right: 0 }, parapodia: 0 });
  }

  addTo(world) { world.add(this.group, this.floorLight); return this; }

  update(state) {
    const [x, y, z] = state.position;
    this.group.position.set(x, y, z);
    this.group.rotation.set(state.roll || 0, -(state.pitch || 0), state.heading || 0, "ZYX");

    // the beat advances with each side's drive, and stops in an arrest
    const time = Number(state.time) || 0;
    const dt = this.lastTime === null ? 0 : Math.min(0.1, Math.max(0, time - this.lastTime));
    this.lastTime = time;
    const arrest = state.arrest || 0;
    const level = [((state.cilia && state.cilia.left) || 0) * (1 - arrest), ((state.cilia && state.cilia.right) || 0) * (1 - arrest)];
    for (let s = 0; s < 2; s++) { this.phase[s] += TWO_PI * BEAT_HZ * level[s] * dt; if (this.phase[s] > TWO_PI) this.phase[s] -= TWO_PI; }

    // a cilium at angle a around the axis at (x0, r): tilted backward by the beat of its side
    const put = (pos, n, x0, r, a, lv, ph, len) => {
      const ca = Math.cos(a), sa = Math.sin(a);
      const beta = BEAT_REST + BEAT_SWING * lv * Math.sin(ph - WAVES * a);
      const cb = Math.cos(beta), sb = Math.sin(beta);
      pos[n] = x0; pos[n + 1] = r * ca; pos[n + 2] = r * sa;
      pos[n + 3] = x0 - len * sb; pos[n + 4] = (r + len * cb) * ca; pos[n + 5] = (r + len * cb) * sa;
      return n + 6;
    };
    const sideOf = (a) => (Math.cos(a) >= 0 ? 0 : 1);     // y = r cos a: left when positive
    let n = 0;
    for (let j = 0; j < PROTOTROCH_CELLS; j++) {
      const a = (j + 0.5) / PROTOTROCH_CELLS * TWO_PI, s = sideOf(a);
      n = put(this.headPos, n, PROTOTROCH_X, PROTOTROCH_R, a, level[s], this.phase[s], CILIUM);
    }
    this.headLines.geometry.attributes.position.needsUpdate = true;

    n = 0;
    const per = PARATROCH_CELLS / PARATROCH.length;
    for (const [x0, r] of PARATROCH) {
      for (let j = 0; j < per; j++) {
        const a = (j + 0.5) / per * TWO_PI, s = sideOf(a);
        n = put(this.trunkPos, n, x0 - 0.1, r, a, level[s], this.phase[s], 0.55 * CILIUM);
      }
    }

    // the chaetae: a fan on each parapodium, backward at rest, out and up when the parapodia rise
    const e = smooth(((state.parapodia || 0) - 0.3) / 0.4);
    const az = lerp(35, 85, e) * DEG, el = lerp(-10, 25, e) * DEG, spread = lerp(10, 25, e) * DEG;
    for (const [x0, hw] of SEGMENTS) {
      for (const side of [1, -1]) {
        const bx = x0 - 0.1, by = side * (hw - 0.02), bz = -0.04;
        for (let i = 0; i < CHAETAE; i++) {
          const f = (i - (CHAETAE - 1) / 2) / ((CHAETAE - 1) / 2);
          const a = az + f * spread, l = el + f * 0.4 * spread, cl = Math.cos(l);
          this.trunkPos[n++] = bx; this.trunkPos[n++] = by; this.trunkPos[n++] = bz;
          this.trunkPos[n++] = bx - CHAETA * cl * Math.cos(a); this.trunkPos[n++] = by + side * CHAETA * cl * Math.sin(a); this.trunkPos[n++] = bz + CHAETA * Math.sin(l);
        }
      }
    }
    this.trunkLines.geometry.setDrawRange(0, n / 3);
    this.trunkLines.geometry.attributes.position.needsUpdate = true;

    // the longitudinal muscles: the body shortens, the trunk bends toward the contracted side
    const ml = (state.muscle && state.muscle.left) || 0, mr = (state.muscle && state.muscle.right) || 0;
    this.body.scale.x = 1 - SHORTEN * Math.max(ml, mr);
    this.trunk.rotation.z = -BEND * (ml - mr);

    // the light on the floor: wider and fainter the higher the larva swims
    this.floorLight.position.set(x, y, 0.02);
    const r = 0.9 + 0.2 * z;
    this.floorLight.scale.set(r, r, 1);
    this.floorLight.material.opacity = 0.45 / (1 + 0.35 * z);
  }
}
