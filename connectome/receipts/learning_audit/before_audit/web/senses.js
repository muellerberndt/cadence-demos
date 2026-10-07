// The senses: the tank's quantities onto named sensory populations, each a level in [0, 1].
// Pure functions of the body state (body.js state()) and the world:
//
//   world = { prey: [{x, y, z}],                       mm
//             tapSide: -1 | 0 | +1, tapAge: s,         the last tap: -1 the pane at x = 0,
//                                                      +1 the pane at x = TANK[0]
//             stripes: {on, direction: -1 | +1, speed}, the floor pattern, mm/s along x
//             light: {on, x, y, z} }                   the lamp
//
// Bearings are in the horizontal plane, positive to the fish's left.
import { tapPosition, wrap } from "./body.js";

export const SENSE_NAMES = [
  "vestibular_left", "vestibular_right",
  "lateral_line_left", "lateral_line_right",
  "optic_flow_left", "optic_flow_right",
  "prey_left", "prey_right",
  "light_left", "light_right",
  "acoustic",
];

export const VESTIBULAR_SATURATION = 8.0;        // rad/s of yaw
export const FLOW_SATURATION = 10.0;             // mm/s, lateral line and optic flow
export const PREY_RANGE = 6.0;                   // mm, the retina resolves a paramecium up to here
export const EYE_AZIMUTH = 45 * Math.PI / 180;   // the centre of each eye's prey field
export const LIGHT_AZIMUTH = 70 * Math.PI / 180; // the outward look of each eye
export const LIGHT_RANGE = 8.0;                  // mm, the lamp's half-brightness distance
export const TAP_DECAY = 0.07;                   // s, the tap's pulse: below 0.06 by 200 ms
export const TAP_GAIN = 1.0;

const sat = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);

/** The pulse of the last tap, 1 at the tap, decaying. */
export function tapPulse(world) {
  const side = Number(world?.tapSide) || 0;
  if (side === 0) return 0;
  const age = Math.max(0, Number(world.tapAge) || 0);
  return Math.exp(-age / TAP_DECAY);
}

/** The horizontal bearing of a point from the body, positive to the left. */
export function bearing(state, point) {
  const [x, y] = state.position;
  return wrap(Math.atan2(point[1] - y, point[0] - x) - state.heading);
}

/** The yaw rate as two populations: one for each turning side. */
export function vestibular(state) {
  const yaw = state.senses?.angularVelocity?.[2] ?? 0;
  return [sat(yaw / VESTIBULAR_SATURATION), sat(-yaw / VESTIBULAR_SATURATION)];
}

/** Water flow along each side: the body's own motion, more on the side that slips into the
 *  water, and the pressure pulse of a tap, more on the side that faces it. */
export function lateralLine(state, world) {
  const [vx, vy] = state.velocity, h = state.heading;
  const forward = vx * Math.cos(h) + vy * Math.sin(h), left = -vx * Math.sin(h) + vy * Math.cos(h);
  let l = Math.abs(forward) + 2 * Math.max(0, left), r = Math.abs(forward) + 2 * Math.max(0, -left);
  const pulse = tapPulse(world);
  if (pulse > 0) {
    const b = bearing(state, tapPosition(Number(world.tapSide)));
    l += TAP_GAIN * FLOW_SATURATION * pulse * (0.5 + 0.5 * Math.sin(b));
    r += TAP_GAIN * FLOW_SATURATION * pulse * (0.5 - 0.5 * Math.sin(b));
  }
  return [sat(l / FLOW_SATURATION), sat(r / FLOW_SATURATION)];
}

/** The ground's motion relative to the fish, in its frame: forward and leftward flow drive the
 *  optomotor populations; the backward flow of its own forward swimming does not. */
export function opticFlow(state, world) {
  const st = world?.stripes, [vx, vy] = state.velocity, h = state.heading;
  const texture = st && st.on ? (Number(st.direction) || 1) * (Number(st.speed) || 0) : 0;
  const fx = texture - vx, fy = -vy;
  const forward = fx * Math.cos(h) + fy * Math.sin(h), left = -fx * Math.sin(h) + fy * Math.cos(h);
  return [sat((Math.max(0, forward) + Math.max(0, left)) / FLOW_SATURATION), sat((Math.max(0, forward) + Math.max(0, -left)) / FLOW_SATURATION)];
}

/** The nearest prey on each retina: closer is stronger, each eye's field centred 45 degrees
 *  out, overlapping ahead and blind behind. Returns [left, right, nearest]. */
export function preyRetina(state, world) {
  const [x, y, z] = state.position;
  let nearest = null, best = Infinity;
  for (const q of world?.prey || []) {
    const d = Math.hypot(q.x - x, q.y - y, (q.z ?? z) - z);
    if (d < best) { best = d; nearest = q; }
  }
  if (!nearest || best >= PREY_RANGE) return [0, 0, null];
  const w = 1 - best / PREY_RANGE, b = bearing(state, [nearest.x, nearest.y]);
  const l = Math.max(0, Math.cos(b - EYE_AZIMUTH)), r = Math.max(0, Math.cos(b + EYE_AZIMUTH));
  return [sat(w * l * l), sat(w * r * r), { ...nearest, distance: best, bearing: b }];
}

/** The lamp on each eye: its bearing against the eye's outward look, with a little from all
 *  around, fading with distance. */
export function light(state, world) {
  const L = world?.light;
  if (!L || !L.on) return [0, 0];
  const [x, y, z] = state.position;
  const d = Math.hypot((Number(L.x) || 0) - x, (Number(L.y) || 0) - y, (Number(L.z) || 0) - z);
  const atten = 1 / (1 + (d / LIGHT_RANGE) ** 2), b = bearing(state, [Number(L.x) || 0, Number(L.y) || 0]);
  const l = 0.15 + 0.85 * Math.max(0, Math.cos(b - LIGHT_AZIMUTH)), r = 0.15 + 0.85 * Math.max(0, Math.cos(b + LIGHT_AZIMUTH));
  return [sat(atten * l), sat(atten * r)];
}

/** The ear: the tap's pressure wave, the same on both sides. */
export function acoustic(world) { return sat(tapPulse(world)); }

/** All populations from the body state and the world, keyed by SENSE_NAMES. */
export function sense(state, world = {}) {
  const [vl, vr] = vestibular(state);
  const [ll, lr] = lateralLine(state, world);
  const [fl, fr] = opticFlow(state, world);
  const [pl, pr] = preyRetina(state, world);
  const [gl, gr] = light(state, world);
  return {
    vestibular_left: vl, vestibular_right: vr,
    lateral_line_left: ll, lateral_line_right: lr,
    optic_flow_left: fl, optic_flow_right: fr,
    prey_left: pl, prey_right: pr,
    light_left: gl, light_right: gr,
    acoustic: acoustic(world),
  };
}
