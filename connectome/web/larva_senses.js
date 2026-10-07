// The larva's senses: the tank's quantities onto named sensory populations, each a level in
// [0, 1]. Pure functions of the body state (larva_body.js state(), or any object with
// position, heading and pitch, plus the body axis if the body reports one) and the world:
//
//   world = { light: {on, x, y, z},                   the lamp, mm
//             uv: 0..1 or null,                       ultraviolet from above; null: 1 while the lamp is on
//             tapSide: -1 | 0 | +1, tapAge: s }       the last tap: -1 the pane at x = 0,
//                                                     +1 the pane at x = TANK[0]
//
// The adult eyes look forward and sideways at 45 degrees; a pigment cup shades each so it
// answers light from its own side only (Randel et al. 2014). The larval eyespots look further
// out with a wider field (Jekely et al. 2008). The ciliary photoreceptors (cPRC) answer the
// ultraviolet from above, strongest near the surface (Veraszto et al. 2018). Pressure rises
// with the depth. The mechanical sense is the pulse of a tap on the glass.
//
// The eyes ride the body axis the body reports (the nodding helix axis) but not its spin, so
// a light to the left stays on the left eye while the larva spins: the left-right comparison
// is a steady course signal for the brain. A declared abstraction, see larva_body.js.
import { WATER } from "./body.js";

export const SENSE_NAMES = ["eye_left", "eye_right", "eyespot_left", "eyespot_right", "cprc", "pressure", "mechanical"];

export const EYE_AZIMUTH = 45 * Math.PI / 180;      // the adult eyes' look, out from the body axis
export const EYESPOT_AZIMUTH = 70 * Math.PI / 180;  // the larval eyespots' look
export const LIGHT_RANGE = 8.0;                     // mm, the lamp's half-brightness distance
export const MECHANICAL_DECAY = 0.06;               // s, the tap's pulse: below 0.05 by 200 ms

const sat = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);
const num = (x) => { x = Number(x); return Number.isFinite(x) ? x : 0; };

/** The pulse of the last tap, 1 at the tap, decaying. */
export function tapPulse(world) {
  const side = num(world?.tapSide);
  if (side === 0) return 0;
  const age = Math.max(0, num(world.tapAge));
  return Math.exp(-age / MECHANICAL_DECAY);
}

/** The body axis as a unit vector in the world: the axis the body reports, else the course. */
export function bodyAxis(state) {
  const a = state.axis;
  if (a && a.length === 3) {
    const n = Math.hypot(a[0], a[1], a[2]);
    if (n > 0) return [a[0] / n, a[1] / n, a[2] / n];
  }
  const h = num(state.heading), p = num(state.pitch), cp = Math.cos(p);
  return [cp * Math.cos(h), cp * Math.sin(h), Math.sin(p)];
}

/** The looks of a pair of eyes `azimuth` out from the body axis, in the axis's horizontal
 *  plane: [left, right], unit vectors in the world. */
export function eyeAxes(state, azimuth) {
  const u = bodyAxis(state);
  let lx = -u[1], ly = u[0];
  const n = Math.hypot(lx, ly);
  if (n < 1e-9) { const h = num(state.heading); lx = -Math.sin(h); ly = Math.cos(h); } else { lx /= n; ly /= n; }
  const c = Math.cos(azimuth), s = Math.sin(azimuth);
  return [[c * u[0] + s * lx, c * u[1] + s * ly, c * u[2]], [c * u[0] - s * lx, c * u[1] - s * ly, c * u[2]]];
}

/** The lamp on each adult eye and each eyespot: its direction against the eye's look, the
 *  pigment cup shading everything behind the look, fading with distance. The eyespots' field
 *  is wider, with a little from all around. Returns { eye: [l, r], eyespot: [l, r] }. */
export function lightOnEyes(state, world) {
  const L = world?.light;
  if (!L || !L.on) return { eye: [0, 0], eyespot: [0, 0] };
  const [x, y, z] = state.position;
  const dx = num(L.x) - x, dy = num(L.y) - y, dz = num(L.z) - z, d = Math.hypot(dx, dy, dz);
  if (d < 1e-9) return { eye: [1, 1], eyespot: [1, 1] };
  const atten = 1 / (1 + (d / LIGHT_RANGE) ** 2);
  const dot = (e) => (e[0] * dx + e[1] * dy + e[2] * dz) / d;
  const eye = eyeAxes(state, EYE_AZIMUTH).map((e) => sat(atten * Math.max(0, dot(e)) ** 2));
  const eyespot = eyeAxes(state, EYESPOT_AZIMUTH).map((e) => sat(atten * (0.5 + 0.5 * dot(e)) ** 2));
  return { eye, eyespot };
}

/** The ciliary photoreceptors and the pressure: ultraviolet from above, strongest at the
 *  surface and gone at the floor; the depth below the surface as a share of the water. */
export function depthSenses(state, world) {
  const depth = sat((WATER - state.position[2]) / WATER);
  const L = world?.light;
  const uv = world?.uv == null ? (L && L.on ? 1 : 0) : sat(num(world.uv));
  return { cprc: sat(uv * (1 - depth)), pressure: depth };
}

/** The mechanical sense: the tap's pulse, the same on both sides. */
export function mechanical(world) { return sat(tapPulse(world)); }

/** All populations from the body state and the world, keyed by SENSE_NAMES. */
export function senseLarva(state, world = {}) {
  const { eye, eyespot } = lightOnEyes(state, world);
  const { cprc, pressure } = depthSenses(state, world);
  return {
    eye_left: eye[0], eye_right: eye[1],
    eyespot_left: eyespot[0], eyespot_right: eyespot[1],
    cprc, pressure,
    mechanical: mechanical(world),
  };
}
