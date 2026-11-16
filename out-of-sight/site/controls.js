// The two simple controls the page draws beside the brain, given the same camera reports: a port
// of the tracking chamber's controls that learn nothing (benchmarks/tracking/tracking.py in the
// Cadence library); tests/parity.mjs checks both against the Python ones on recorded scenes.
//
// `LastSeen` answers the last place the camera reported. `Kalman` is a constant-velocity Kalman
// filter: position and velocity on each axis, process noise `q` and report noise `r` (a standard
// deviation), corrected by every report and coasting on its velocity while the hand is out of
// view. Both start from the hand's starting position, as every learner in the chamber does: the
// first moment is the start itself, and every later moment predicts and then reads its report.

export const RATE = 0.9; // the rate an answer's area is stated at

/** The radius, in standard deviations, of the circle that holds `rate` of a Gaussian in a plane. */
export const radiusAt = (rate) => Math.sqrt(-2 * Math.log(1 - rate));

export class LastSeen {
  constructor(start) { this.place = start.slice(); this.radius = 0; this.first = true; }
  step(report) {
    if (this.first) { this.first = false; return this.place.slice(); }
    if (report) this.place = report.slice();
    return this.place.slice();
  }
}

export class Kalman {
  constructor(start, { q = 1e-5, r = 0.01 } = {}) {
    this.q = q; this.r = r;
    this.x = start.slice(); this.v = [0, 0];
    this.c = [r * r, 0, 0, 0.03 ** 2]; // c00, c01, c10, c11: one covariance for both axes
    this.first = true;
  }

  get place() { return this.x.slice(); }
  /** The radius of the answer's area at RATE. */
  get radius() { return radiusAt(RATE) * Math.sqrt(this.c[0]); }
  get sd() { return Math.sqrt(this.c[0]); }

  step(report) {
    if (this.first) { this.first = false; return this.place; }
    // predict: one step at constant velocity
    this.x = [this.x[0] + this.v[0], this.x[1] + this.v[1]];
    const [a, b, c, d] = this.c, q = this.q;
    this.c = [a + b + c + d + q / 3, b + d + q / 2, c + d + q / 2, d + q];
    if (report) {
      const [c00, c01, c10, c11] = this.c;
      const s = c00 + this.r * this.r, g0 = c00 / s, g1 = c10 / s;
      for (let k = 0; k < 2; k++) {
        const gap = report[k] - this.x[k];
        this.x[k] += gap * g0; this.v[k] += gap * g1;
      }
      this.c = [c00 - g0 * c00, c01 - g0 * c01, c10 - g1 * c00, c11 - g1 * c01];
    }
    return this.place;
  }
}
