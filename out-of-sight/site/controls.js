// The two simple controls the page draws beside the brain, given the same camera reports.
//
// `LastSeen` answers the last place the camera reported. `Kalman` is a constant-velocity filter:
// position and velocity on each axis, driven by white acceleration noise, corrected by every
// report and coasting on its velocity while the hand is out of view. Both start from the hand's
// starting position, as every learner in the tracking chamber does.

export class LastSeen {
  constructor(start) { this.place = start.slice(); }
  step(report) {
    if (report) this.place = report.slice();
    return this.place.slice();
  }
}

export class Kalman {
  /** `noise`: the report's standard deviation (m); `accel`: the acceleration's standard
   *  deviation (m a step squared); `speed`: the starting velocity's standard deviation (m a step). */
  constructor(start, { noise = 0.01, accel = 0.002, speed = 0.02 } = {}) {
    this.x = start.slice();
    this.v = [0, 0];
    this.r = noise * noise;
    this.q = accel * accel;
    this.p = [noise * noise, 0, speed * speed]; // p11, p12, p22: the same on both axes
  }

  step(report) {
    // predict: one step at constant velocity
    this.x = [this.x[0] + this.v[0], this.x[1] + this.v[1]];
    let [p11, p12, p22] = this.p;
    p11 = p11 + 2 * p12 + p22 + this.q / 4;
    p12 = p12 + p22 + this.q / 2;
    p22 = p22 + this.q;
    if (report) {
      const s = p11 + this.r, k1 = p11 / s, k2 = p12 / s;
      for (let a = 0; a < 2; a++) {
        const innovation = report[a] - this.x[a];
        this.x[a] += k1 * innovation;
        this.v[a] += k2 * innovation;
      }
      const n11 = (1 - k1) * p11, n12 = (1 - k1) * p12, n22 = p22 - k2 * p12;
      p11 = n11; p12 = n12; p22 = n22;
    }
    this.p = [p11, p12, p22];
    return this.x.slice();
  }

  /** The standard deviation of the position on each axis. */
  get sd() { return Math.sqrt(Math.max(0, this.p[0])); }
}

/** The radius factor of the circle that holds `rate` of a two-dimensional Gaussian. */
export const radiusAt = (rate) => Math.sqrt(-2 * Math.log(1 - rate));
