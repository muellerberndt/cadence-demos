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
export const SACCADE_INHIBITION = 1.0;     // declared: the burst inhibits the other half's integrator by this fraction of its drive (the inhibitory burst neurons; push and pull keep both halves bounded); 0 is the control
export const SACCADE_SIZES = [0.2, 0.4, 0.7]; // declared: a spontaneous saccade takes one of these sizes (a full one is about 22 degrees), so the integrator is asked to hold different levels within the eye's range
export const CENTERING = { beyond: 10, probability: 0.9, degreesPerUnit: 22 }; // declared: beyond this gaze (degrees) a spontaneous saccade goes back toward the centre with this probability, sized to land near it (a full saccade is about 22 degrees), as a fish's saccades in the dark re-centre the eye; without it a good integrator makes random saccades a walk to the eye's limit

/** The synapses learn to hold the gaze: the declared genes of the lesson (tests/learning_bench.mjs,
 *  receipts/learning.json). The fish starts with every synapse at LEARN.start of the selected gain, a
 *  leaky integrator whose gaze drifts back within a second. One second after a saccade the integrator's
 *  state is the target; at the next saccade the slip is what the state did since, and if it moved by more
 *  than the dead zone the net takes a finite contrastive lesson toward a declared target: every synapse
 *  reads its own two endpoints in the nudged phase and the free phase and moves, biases stay, a synapse
 *  keeps its declared sign, and a receiver-local mass adjustment targets a bounded band
 *  (the efficacy cap has priority). Each contact scales the step by its own phase products. */
export const LEARN = {
  start: 0.8,            // the fraction of the selected gain the fish starts at
  outputs: "_Int_",      // the population the slip reaches: the integrator neurons
  targetDelay: 25,       // steps after the burst at which the target is taken: one second, after the burst's transient
  minFixation: 1.0,      // s: a fixation shorter than this teaches nothing
  turn: 1.0,             // rad/s of yaw: faster, and the eyes move for the vestibular reason; the fixation ends and a new one begins when the head is still
  maxFixation: 10.0,     // s: a fixation this long takes its lesson without waiting for a saccade
  deadZone: 0.05,        // the slip must exceed this fraction of the level
  levelMin: 0.001,       // and the level must be above this
  beta: 3.0, eta: 0.01, etaBias: 0.0, steps: 50, tolerance: 1e-4, cap: 8.0,
  centered: false, relative: true, keepSign: true, massCap: 1.5,
};
/** Declared teaching feedback, expressed in integrator activity units, not rendered visual input.
 *  Hold targets 95% of the saved post-saccade activity; its 5% dead zone favours slight decay. return targets one quarter of it.
 *  Amplified feedback extrapolates the correction by two. Its effect depends on the
 *  acquired state and learning step; alternating instability or recovery is not guaranteed. */
export const WORLDS = { still: { m: 0.95 }, back: { m: 0.25 }, against: { k: 2 } };
export const QUICK_PHASE = { beyond: 24, after: 0.5 }; // declared: at the eye's limit (degrees) a re-centring saccade comes within this time (s) of the last one, the quick phase of a nystagmus, from the same burst generator outside the reconstruction; without it an integrator that runs on leaves the eye parked at its limit until the next spontaneous saccade
export const HUNT_SACCADE = 0.5;            // declared: the pilot's saccade toward prey takes this size

/** Stimuli for the twin brain from a saccade command and the body's senses. */
export function stimuli({ saccade = 0, yawRate = 0 }) {
  const out = { left: {}, right: {} };
  if (saccade > 0) { out.left._Int_ = SACCADE_LEVEL * Math.min(1, saccade); if (SACCADE_INHIBITION > 0) out.right._Int_ = -SACCADE_INHIBITION * SACCADE_LEVEL * Math.min(1, saccade); }
  if (saccade < 0) { out.right._Int_ = SACCADE_LEVEL * Math.min(1, -saccade); if (SACCADE_INHIBITION > 0) out.left._Int_ = -SACCADE_INHIBITION * SACCADE_LEVEL * Math.min(1, -saccade); }
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
  constructor(seed = 1) { this.rng = seed; this.next = 2 + 3 * fract(seed * 0.618); this.pending = 0; this.stepsLeft = 0; this.sign = 0; this.size = 0; this.count = 0; this.spontaneous = true; this.last = -Infinity; this.quick = 0; }
  /** Called once per brain step with the fish's time (s), the pilot's wish (-1..1 or 0) and the current
   *  gaze in degrees (positive leftward); returns the burst for this step (-1..1, 0 for none). */
  tick(time, wish = 0, gazeDeg = 0) {
    if (this.stepsLeft > 0) { this.stepsLeft--; return this.sign * this.size; }
    let want = this.pending || wish; this.pending = 0;
    if (want === 0 && this.spontaneous && Math.abs(gazeDeg) >= QUICK_PHASE.beyond && time - this.last >= QUICK_PHASE.after) {  // the quick phase: the eye at its limit comes back toward the centre
      want = -Math.sign(gazeDeg) * Math.min(1, Math.abs(gazeDeg) / CENTERING.degreesPerUnit); this.quick++;
    }
    if (want === 0 && this.spontaneous && time >= this.next) {
      this.rng = (this.rng * 9301 + 49297) % 233280; const u = this.rng / 233280;
      this.rng = (this.rng * 9301 + 49297) % 233280; const size = SACCADE_SIZES[Math.floor((this.rng / 233280) * SACCADE_SIZES.length)];
      this.rng = (this.rng * 9301 + 49297) % 233280; const centre = this.rng / 233280 < CENTERING.probability;
      const centring = Math.abs(gazeDeg) > CENTERING.beyond && centre;
      const direction = centring ? -Math.sign(gazeDeg) : u < 0.5 ? -1 : 1;
      want = direction * (centring ? Math.min(1, Math.abs(gazeDeg) / CENTERING.degreesPerUnit) : size);
    }
    if (want !== 0) {
      this.sign = Math.sign(want); this.size = Math.min(1, Math.abs(want)); this.stepsLeft = SACCADE_STEPS - 1; this.count++; this.last = time;
      this.rng = (this.rng * 9301 + 49297) % 233280; this.next = time + 3 + 5 * (this.rng / 233280);
      return this.sign * this.size;
    }
    return 0;
  }
  /** A direction asked from outside (-1 right .. +1 left); fires on the next step. */
  request(direction) { this.pending = Math.max(-1, Math.min(1, direction)); }
}
function fract(x) { return x - Math.floor(x); }
