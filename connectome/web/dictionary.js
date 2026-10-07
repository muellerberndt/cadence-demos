// The declared dictionary between the fish and the compiled brainstem.
//
// Time: one brain step is a fifth of the unit's time constant; the unit's time constant is
// declared as 0.2 s, so one step is 40 ms of the fish's time and the held gaze decays with
// the compiled net's own constant (about 17 s at the selected gain).
//
// In: a saccade is a burst to one half's integrator, leftward saccades to the left half
// (ipsiversive: a half's abducens cells move both eyes toward that side). The yaw rate
// drives the Ve2 vestibular neurons of the half the head turns toward; they inhibit that
// half's integrator, so the eyes move against the turn, the vestibulo-ocular direction.
// Out: the conjugate gaze angle is the difference of the two halves' abducens readouts
// (motor plus internuclear), scaled to degrees. Vergence toward prey is the pilot's.
//
// Not in the compiled data: lateral line, optic flow, prey, light, the tap. Those senses
// stay with the pilot and are labelled so on the page.
export const STEP_MS = 40;                 // fish time per brain step
export const SACCADE_STEPS = 5;            // 200 ms burst
export const SACCADE_LEVEL = 0.1;          // integrator stimulus level for a full saccade
export const GAZE_DEGREES_PER_UNIT = 65;   // degrees of conjugate gaze per unit of abducens readout difference (0.35 after a full saccade = 22 degrees)
export const GAZE_MAX = 25;                // degrees, the conjugate range the eyes can take
export const PULSE_DEGREES = 15;           // declared: the burst's direct path to the motor neurons (outside the volume) moves the eye during the burst; the hold is the compiled integrator's
export const VESTIBULAR_SATURATION = 8.0;  // rad/s of yaw at full Ve2 drive
export const VESTIBULAR_LEVEL = 0.15;      // Ve2 stimulus level at saturation

/** Stimuli for the twin brain from a saccade command and the body's senses. */
export function stimuli({ saccade = 0, yawRate = 0 }) {
  const out = { left: {}, right: {} };
  if (saccade > 0) out.left._Int_ = SACCADE_LEVEL * Math.min(1, saccade);
  if (saccade < 0) out.right._Int_ = SACCADE_LEVEL * Math.min(1, -saccade);
  const v = VESTIBULAR_LEVEL * Math.min(1, Math.abs(yawRate) / VESTIBULAR_SATURATION);
  if (yawRate > 0) out.left._DOs_ = v;      // a left turn drives the left Ve2: the eyes go right
  if (yawRate < 0) out.right._DOs_ = v;
  return out;
}

/** Conjugate gaze in degrees (positive = leftward): the compiled step from the two halves'
 *  abducens readouts, plus the declared pulse while a burst is on. */
export function gaze(sides, burst = 0) {
  const abd = (s) => (s && s.readouts ? (s.readouts.ABD_m || 0) + (s.readouts.ABD_i || 0) : 0);
  const g = GAZE_DEGREES_PER_UNIT * (abd(sides.left) - abd(sides.right)) + PULSE_DEGREES * burst;
  return Math.max(-GAZE_MAX, Math.min(GAZE_MAX, g));
}

/** Eye angles for body.eyes(): positive converges nasally; a leftward gaze turns the left eye
 *  temporally and the right eye nasally. */
export function eyeAngles(gazeDeg, vergenceDeg = 0) {
  return { left: vergenceDeg - gazeDeg, right: vergenceDeg + gazeDeg };
}

/** A saccade scheduler: the pilot's gaze targets and a requested direction become bursts.
 *  Spontaneous saccades every 3 to 8 s in the dark (off when `spontaneous` is false),
 *  toward prey when the pilot hunts. A request fires on the next step and restarts the
 *  spontaneous clock. */
export class Saccades {
  constructor(seed = 1) { this.rng = seed; this.next = 2 + 3 * fract(seed * 0.618); this.pending = 0; this.stepsLeft = 0; this.sign = 0; this.size = 0; this.count = 0; this.spontaneous = true; }
  /** Called once per brain step with the fish's time (s) and the pilot's wish (-1..1 or 0);
   *  returns the burst for this step (-1..1, 0 for none). */
  tick(time, wish = 0) {
    if (this.stepsLeft > 0) { this.stepsLeft--; return this.sign * this.size; }
    let want = this.pending || wish; this.pending = 0;
    if (want === 0 && this.spontaneous && time >= this.next) {
      this.rng = (this.rng * 9301 + 49297) % 233280; const u = this.rng / 233280;
      want = u < 0.5 ? -1 : 1;
    }
    if (want !== 0) {
      this.sign = Math.sign(want); this.size = Math.min(1, Math.abs(want)); this.stepsLeft = SACCADE_STEPS - 1; this.count++;
      this.rng = (this.rng * 9301 + 49297) % 233280; this.next = time + 3 + 5 * (this.rng / 233280);
      return this.sign * this.size;
    }
    return 0;
  }
  /** A direction asked from outside (-1 right .. +1 left); fires on the next step. */
  request(direction) { this.pending = Math.max(-1, Math.min(1, direction)); }
}
function fract(x) { return x - Math.floor(x); }
