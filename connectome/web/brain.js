// A settling brain in the browser: the cadence rate model on a sparse connectome, with the
// arithmetic of the library in the library's order, so a parity test (parity.mjs) holds this
// engine to cadence.Brain to a relative difference near machine precision.
//
//   synaptic input_i = sum over synapses e into i of  w_e * s_pre(e)      (w = gain * count * exp(log_gain[pre]) * efficacy)
//   v_i <- v_i + dt * ( -v_i + input_i + stimulus_i + bias_i )
//   s_i = rectified sigmoid(v_i), exactly zero at rest (or, with a leak, negative below rest)
//
// The payload (export.py) stores the synapses by receiving neuron (CSR by post, senders in the
// library's order) and every population by name. The generic nudged settle supports
// cadence.Nudge; the fish lesson separately nudges a declared activity pattern.
import { createSettlementTrace } from "./settlement-trace.js";
import { createNeuralReplay } from "./neural-replay.js";

export function decodeArray(b64, T) {
  const bin = atob(b64); const buf = new ArrayBuffer(bin.length); const u = new Uint8Array(buf);
  for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  return new T(buf);
}

// A bounded control solve is distinct from the legacy activation-motion stopping rule.
export const MAX_CONTROL_STEPS = 1024;

export class SettlingBrain {
  constructor(payload) {
    const m = payload.model;
    this.n = payload.n; this.edges = payload.edges;
    this.dt = m.dt; this.slope = m.slope; this.threshold = m.threshold; this.gain = m.gain; this.amplitude = m.stimulus_amplitude;
    this.leak = m.leak || 0.0;  // >0: below rest the activation is negative, scaled by leak / rest (the library's leaky variant)
    if (m.adaptation) throw new Error("the browser engine settles without adaptation; export a model with adaptation=None");
    this.rest = 1.0 / (1.0 + Math.exp(this.slope * this.threshold));
    this.restScale = 1.0 / (1.0 - this.rest);
    this.leakScale = this.leak / this.rest;
    this.rowPtr = decodeArray(payload.arrays.row_ptr, Int32Array);
    this.pre = decodeArray(payload.arrays.pre, Int32Array);
    this.w = decodeArray(payload.arrays.weight, Float64Array);
    this.count = payload.arrays.count ? decodeArray(payload.arrays.count, Uint16Array) : null;  // synapses per class
    this.logGain = payload.arrays.log_gain ? decodeArray(payload.arrays.log_gain, Float64Array) : null;  // per neuron: a gain per cell class, selected by protocol
    this.gainPre = payload.arrays.gain_pre ? decodeArray(payload.arrays.gain_pre, Float64Array) : null;  // weight = gainPre * efficacy, when the payload carries the factor itself
    if (!this.gainPre && this.logGain) {  // the factor composed as the library does: gain * count * exp(log_gain[pre])
      this.gainPre = new Float64Array(this.edges);
      for (let e = 0; e < this.edges; e++) this.gainPre[e] = this.gain * (this.count ? this.count[e] : 1) * Math.exp(this.logGain[this.pre[e]]);
    }
    this.sign = payload.arrays.sign ? decodeArray(payload.arrays.sign, payload.arrays.sign_dtype === "int8" ? Int8Array : Float64Array) : null;
    this.efficacy0 = payload.arrays.efficacy ? decodeArray(payload.arrays.efficacy, Float64Array) : null;  // the efficacies the brain was exported with (signed)
    if (!this.efficacy0 && payload.arrays.efficacy_index) {  // the few synapses off their sign, as index and value
      this.efficacy0 = Float64Array.from(this.sign);
      const idx = decodeArray(payload.arrays.efficacy_index, Int32Array), val = decodeArray(payload.arrays.efficacy_value, Float64Array);
      for (let k = 0; k < idx.length; k++) this.efficacy0[idx[k]] = val[k];
    }
    this.bias = payload.arrays.bias ? decodeArray(payload.arrays.bias, Float64Array) : new Float64Array(this.n);
    this.bias0 = this.bias.slice();
    this.members = payload.arrays.members ? decodeArray(payload.arrays.members, Int32Array) : null;  // indices into a larger brain, when this is a sub-net
    this.sets = payload.populations || {};
    this.v = new Float64Array(this.n); this.s = new Float64Array(this.n);
    this.drive = new Float64Array(this.n); this.total = new Float64Array(this.n);
    this.steps = 0;
  }

  activation(v) {
    let r = Math.exp((-this.slope) * (v - this.threshold));
    r += 1.0; r = 1.0 / r; r -= this.rest;
    if (this.leak === 0.0) { if (r < 0.0) r = 0.0; return r * this.restScale; }
    return r > 0.0 ? r * this.restScale : r * this.leakScale;
  }

  reset() { this.v.fill(0); this.s.fill(0); this.steps = 0; }

  /** Set the stimulus of a named population to a level in [0, 1] (scaled by the amplitude); levels combine by max. */
  stimulate(name, level) {
    const idx = this.sets[name]; if (!idx) return;
    const d = this.amplitude * level;
    for (const i of idx) if (d > this.drive[i]) this.drive[i] = d;
  }
  /** Set one neuron's stimulus level directly (the library's `stimulus_levels`: level times amplitude). */
  setDrive(index, level) { this.drive[index] = this.amplitude * level; }
  clearStimuli() { this.drive.fill(0); }
  /** The weight of one synapse from an efficacy: gain * count * exp(log_gain[pre]) * efficacy, as the library composes it. */
  setEfficacy(e, efficacy) { this.w[e] = (this.gainPre ? this.gainPre[e] : this.gain * (this.count ? this.count[e] : 1)) * efficacy; }

  /** One step of the neuron model under the current drive. */
  step() {
    const n = this.n, rowPtr = this.rowPtr, pre = this.pre, w = this.w, s = this.s, v = this.v, total = this.total;
    for (let i = 0; i < n; i++) {
      let sum = 0.0;
      for (let e = rowPtr[i], end = rowPtr[i + 1]; e < end; e++) sum += s[pre[e]] * w[e];
      total[i] = sum;
    }
    const dt = this.dt, drive = this.drive, bias = this.bias;
    for (let i = 0; i < n; i++) {
      let t = total[i];
      t += drive[i] + bias[i];   // standing = drive + bias, added as one number as the library does
      t -= v[i];
      t *= dt;
      v[i] += t;
      s[i] = this.activation(v[i]);
    }
    this.steps++;
  }

  /** The free phase: up to `steps` steps, stopping once no activation moves by `tolerance` or more
   *  (cadence.Brain.settle_batch with a tolerance). Returns the steps taken. */
  settleFree(steps, tolerance) {
    const prev = new Float64Array(this.n);
    for (let k = 0; k < steps; k++) {
      prev.set(this.s);
      this.step();
      if (tolerance === undefined || tolerance === null) continue;
      let movement = 0.0;
      for (let i = 0; i < this.n; i++) { const d = Math.abs(this.s[i] - prev[i]); if (d > movement) movement = d; }
      if (movement < tolerance) return k + 1;
    }
    return steps;
  }

  /** The potential equation residual ||W act(v) + drive + bias - v||_infinity.
   * This measures agreement with the current fixed-input equations. It is not an error
   * bound to a unique equilibrium unless a separate contraction certificate is available. */
  equationResidual() {
    const n = this.n;
    if (!this.controlActivation || this.controlActivation.length !== n) this.controlActivation = new Float64Array(n);
    const a = this.controlActivation;
    for (let i = 0; i < n; i++) {
      if (!Number.isFinite(this.v[i]) || !Number.isFinite(this.s[i])) return Infinity;
      a[i] = this.activation(this.v[i]);
    }
    return this._equationResidualFromActivation(a);
  }

  // Internal: a must equal act(v). Cache the equation defect already computed for the
  // residual, so the next Euler update needs neither another sparse product nor another
  // activation evaluation. The public residual always reconstructs act(v) first.
  _equationResidualFromActivation(a) {
    const n = this.n, v = this.v, drive = this.drive, bias = this.bias;
    const rowPtr = this.rowPtr, pre = this.pre, w = this.w;
    if (!this.controlDefect || this.controlDefect.length !== n) this.controlDefect = new Float64Array(n);
    const defects = this.controlDefect;
    let residual = 0;
    for (let i = 0; i < n; i++) {
      if (!Number.isFinite(v[i]) || !Number.isFinite(a[i]) || !Number.isFinite(drive[i]) || !Number.isFinite(bias[i])) return Infinity;
      let input = 0;
      for (let e = rowPtr[i], end = rowPtr[i + 1]; e < end; e++) input += a[pre[e]] * w[e];
      const defect = input + (drive[i] + bias[i]) - v[i];
      if (!Number.isFinite(defect)) return Infinity;
      defects[i] = defect;
      residual = Math.max(residual, Math.abs(defect));
    }
    return residual;
  }

  /** Solve one frozen sensory input for control. No action sampling or learning occurs.
   * A successful result means only that the returned state meets the equation-residual
   * tolerance. The directed fly payload has no claimed global contraction certificate.
   * Invalid/nonfinite or exhausted solves return converged:false; callers must not actuate
   * from those results. Existing settleFree/settleNudged preserve their legacy semantics. */
  settleControl(maxSteps = 256, tolerance = 1e-6, traceOptions = null, replayOptions = null) {
    let iterations = 0, initialResidual = null;
    let observer = null, replay = null;
    // Internal synchronous observer. Its borrowed arrays are read-only; the
    // worker throttles and copies them before transfer. No message can provide
    // a callback. Recording is independent of convergence/control authority.
    const progress = typeof this.onSolveProgress === "function" ? this.onSolveProgress : null;
    let progressDelta = null, reported = -1;
    const report = residual => {
      if (!progress || !progressDelta || reported === iterations) return;
      reported = iterations;
      try { progress({ phase: "free", iteration: iterations, residual: Number.isFinite(residual) ? residual : null,
        tolerance, n: this.n, activity: this.s, deltaV: progressDelta }); } catch { /* diagnostics cannot abort computation */ }
    };
    const result = (converged, residual, reason) => {
      report(residual);
      const diagnostic = { converged, iterations, residual: Number.isFinite(residual) ? residual : null,
        initialResidual: Number.isFinite(initialResidual) ? initialResidual : null,
        tolerance: Number.isFinite(tolerance) ? tolerance : null, reason };
      return { ...diagnostic, ...(observer ? { trace: observer.finish(diagnostic) } : {}),
        ...(replay ? { replay: replay.finish(diagnostic) } : {}) };
    };
    const invalid = this._residualSolveError(maxSteps, tolerance);
    if (invalid) return result(false, null, invalid);
    if (traceOptions !== null && traceOptions !== false) observer = createSettlementTrace(this, traceOptions, maxSteps, tolerance);
    if (replayOptions !== null && replayOptions !== false) replay = createNeuralReplay(this, replayOptions, tolerance);
    if (progress) progressDelta = replay?.deltaV ?? new Float32Array(this.n);
    let residual = this.equationResidual();
    // Observer-only input mismatch: reuse the already computed all-neuron
    // defect before the first update. This is not novelty or an emotion model.
    initialResidual = residual;
    if (!Number.isFinite(residual)) { if (observer) observer.capture(0, residual); return result(false, residual, "nonfinite_state_or_equation"); }
    // A restored potential is authoritative; publish its activation before using the recurrence.
    this.s.set(this.controlActivation);
    report(residual);
    if (observer) observer.capture(0, residual);
    if (replay) replay.capture(0, residual);
    if (residual <= tolerance) return result(true, residual, "residual_tolerance");
    const n = this.n, v = this.v, s = this.s, dt = this.dt, defects = this.controlDefect;
    for (iterations = 1; iterations <= maxSteps; iterations++) {
      // Identical arithmetic/order to step(): defect = input + (drive + bias) - v.
      // Its sparse product was computed by the preceding residual check at this state.
      if (replay || progressDelta) for (let i = 0; i < n; i++) {
        const previous = v[i];
        let t = defects[i];
        t *= dt;
        v[i] += t;
        s[i] = this.activation(v[i]);
        if (replay) replay.deltaV[i] = v[i] - previous;
        else progressDelta[i] = v[i] - previous;
      } else for (let i = 0; i < n; i++) {
        let t = defects[i];
        t *= dt;
        v[i] += t;
        s[i] = this.activation(v[i]);
      }
      this.steps++;
      residual = this._equationResidualFromActivation(s);
      if (observer) observer.capture(iterations, residual);
      if (replay) replay.capture(iterations, residual);
      if (iterations % 16 === 0) report(residual);
      if (!Number.isFinite(residual)) return result(false, residual, "nonfinite_state_or_equation");
      if (residual <= tolerance) return result(true, residual, "residual_tolerance");
    }
    iterations = maxSteps;
    return result(false, residual, "iteration_limit");
  }

  _residualSolveError(maxSteps, tolerance) {
    if (!Number.isInteger(maxSteps) || maxSteps < 1 || maxSteps > MAX_CONTROL_STEPS) return "invalid_max_steps";
    if (!Number.isFinite(tolerance) || tolerance <= 0) return "invalid_tolerance";
    if (!Number.isInteger(this.n) || this.n < 1 || !Number.isInteger(this.edges) || this.edges < 0
        || this.rowPtr.length !== this.n + 1 || this.pre.length !== this.edges || this.w.length !== this.edges
        || this.v.length !== this.n || this.s.length !== this.n || this.drive.length !== this.n || this.bias.length !== this.n
        || this.rowPtr[0] !== 0 || this.rowPtr[this.n] !== this.edges) return "invalid_graph";
    if (!Number.isFinite(this.dt) || this.dt <= 0 || this.dt > 1
        || !Number.isFinite(this.slope) || this.slope < 0 || !Number.isFinite(this.threshold)
        || !Number.isFinite(this.leak) || this.leak < 0
        || !Number.isFinite(this.amplitude) || this.amplitude < 0
        || !Number.isFinite(this.restScale) || !Number.isFinite(this.leakScale)) return "invalid_model";
    for (let i = 0; i < this.n; i++) if (this.rowPtr[i] > this.rowPtr[i + 1]) return "invalid_graph";
    for (let e = 0; e < this.edges; e++) if (this.pre[e] < 0 || this.pre[e] >= this.n) return "invalid_graph";
    return null;
  }

  /** A copied-state solve of W act(v) + drive + bias + beta(target-softmax(act(v)/T)) - v = 0,
   * with the nudge restricted to the listed output cells. Positive and negative beta are allowed.
   * The nudge is the negative activation gradient of T times cross-entropy, not unscaled CE.
   * The returned residual includes the nudge and is not an activation-motion or dt-scaled test.
   * No live neuronal state, weight, bias, stimulus or step counter is modified. A directed graph
   * can support this local contrast computation without satisfying EP's energy/gradient hypotheses. */
  settleNudgedResidual(outputs, target, beta, T, maxSteps = 256, tolerance = 1e-6) {
    let iterations = 0, v = null, s = null;
    const progress = typeof this.onSolveProgress === "function" ? this.onSolveProgress : null;
    let progressDelta = null, reported = -1;
    const report = residual => {
      if (!progress || !progressDelta || reported === iterations) return;
      reported = iterations;
      try { progress({ phase: beta >= 0 ? "plus" : "minus", iteration: iterations,
        residual: Number.isFinite(residual) ? residual : null, tolerance, n: this.n,
        activity: s, deltaV: progressDelta }); } catch { /* diagnostics cannot abort computation */ }
    };
    const result = (converged, residual, reason) => {
      report(residual);
      return { converged, iterations, residual: Number.isFinite(residual) ? residual : null,
        tolerance: Number.isFinite(tolerance) ? tolerance : null, reason, v, s };
    };
    const invalid = this._residualSolveError(maxSteps, tolerance);
    if (invalid) return result(false, null, invalid);
    if (!(Array.isArray(outputs) || ArrayBuffer.isView(outputs)) || !outputs.length
        || !(Array.isArray(target) || ArrayBuffer.isView(target)) || target.length !== outputs.length
        || new Set(outputs).size !== outputs.length
        || !Array.from(outputs).every(i => Number.isInteger(i) && i >= 0 && i < this.n)
        || !Array.from(target).every(x => Number.isFinite(x) && x >= 0 && x <= 1)
        || Math.abs(Array.from(target).reduce((a, b) => a + b, 0) - 1) > 1e-12
        || !Number.isFinite(beta) || !Number.isFinite(T) || T <= 0) return result(false, null, "invalid_nudge");
    const n = this.n, rowPtr = this.rowPtr, pre = this.pre, w = this.w;
    v = Float64Array.from(this.v); s = new Float64Array(n);
    if (progress) progressDelta = new Float32Array(n);
    const defects = new Float64Array(n), probabilities = new Float64Array(outputs.length);
    const outputSlot = new Int32Array(n).fill(-1);
    for (let j = 0; j < outputs.length; j++) outputSlot[outputs[j]] = j;
    for (let i = 0; i < n; i++) {
      if (!Number.isFinite(v[i]) || !Number.isFinite(this.s[i])) return result(false, null, "nonfinite_state_or_equation");
      s[i] = this.activation(v[i]);
    }
    const residualAtState = () => {
      // Subtract before division to retain a finite softmax at very small positive T.
      let maximum = -Infinity, sum = 0;
      for (const i of outputs) maximum = Math.max(maximum, s[i]);
      for (let j = 0; j < outputs.length; j++) { probabilities[j] = Math.exp((s[outputs[j]] - maximum) / T); sum += probabilities[j]; }
      for (let j = 0; j < outputs.length; j++) probabilities[j] /= sum;
      let residual = 0;
      for (let i = 0; i < n; i++) {
        if (!Number.isFinite(v[i]) || !Number.isFinite(s[i]) || !Number.isFinite(this.drive[i]) || !Number.isFinite(this.bias[i])) return Infinity;
        let input = 0;
        for (let e = rowPtr[i], end = rowPtr[i + 1]; e < end; e++) input += s[pre[e]] * w[e];
        const slot = outputSlot[i];
        if (slot >= 0) input += beta * (target[slot] - probabilities[slot]);
        const defect = input + (this.drive[i] + this.bias[i]) - v[i];
        if (!Number.isFinite(defect)) return Infinity;
        defects[i] = defect; residual = Math.max(residual, Math.abs(defect));
      }
      return residual;
    };
    let residual = residualAtState();
    report(residual);
    if (!Number.isFinite(residual)) return result(false, residual, "nonfinite_state_or_equation");
    if (residual <= tolerance) return result(true, residual, "residual_tolerance");
    for (iterations = 1; iterations <= maxSteps; iterations++) {
      if (progressDelta) for (let i = 0; i < n; i++) {
        const previous = v[i];
        let t = defects[i]; t *= this.dt;
        v[i] += t;
        s[i] = this.activation(v[i]);
        progressDelta[i] = v[i] - previous;
      } else for (let i = 0; i < n; i++) {
        let t = defects[i]; t *= this.dt;
        v[i] += t;
        s[i] = this.activation(v[i]);
      }
      residual = residualAtState();
      if (iterations % 16 === 0) report(residual);
      if (!Number.isFinite(residual)) return result(false, residual, "nonfinite_state_or_equation");
      if (residual <= tolerance) return result(true, residual, "residual_tolerance");
    }
    iterations = maxSteps;
    return result(false, residual, "iteration_limit");
  }

  /** Settle copies of the state for up to `steps` under the current drive with a cross-entropy nudge
   *  on `outputs` toward the one-hot `target` (strength beta, softmax temperature T), stopping when no
   *  activation moves by `tolerance` or more: the library's nudged phase, in its order of operations.
   *  Returns { s, taken } without touching the live state. */
  settleNudged(outputs, target, beta, T, steps, tolerance) {
    const n = this.n, rowPtr = this.rowPtr, pre = this.pre, w = this.w, dt = this.dt, drive = this.drive, bias = this.bias;
    const v = Float64Array.from(this.v), s = Float64Array.from(this.s), total = new Float64Array(n), prev = new Float64Array(n);
    const m = outputs.length, p = new Float64Array(m);
    let taken = 0;
    for (let k = 0; k < steps; k++) {
      let zmax = -Infinity;
      for (let j = 0; j < m; j++) { const z = s[outputs[j]] / T; if (z > zmax) zmax = z; }
      let sum = 0.0;
      for (let j = 0; j < m; j++) { p[j] = Math.exp(s[outputs[j]] / T - zmax); sum += p[j]; }
      for (let j = 0; j < m; j++) p[j] /= sum;
      for (let i = 0; i < n; i++) {
        let acc = 0.0;
        for (let e = rowPtr[i], end = rowPtr[i + 1]; e < end; e++) acc += s[pre[e]] * w[e];
        total[i] = acc;
      }
      for (let j = 0; j < m; j++) total[outputs[j]] += beta * (target[j] - p[j]);
      prev.set(s);
      let movement = 0.0;
      for (let i = 0; i < n; i++) {
        let t = total[i];
        t += drive[i] + bias[i];
        t -= v[i];
        t *= dt;
        v[i] += t;
        s[i] = this.activation(v[i]);
        const d = Math.abs(s[i] - prev[i]); if (d > movement) movement = d;
      }
      taken = k + 1;
      if (tolerance !== undefined && tolerance !== null && movement < tolerance) break;
    }
    return { s, taken };
  }

  // ---- learning: the library's free/nudged rule (cadence docs/learning.md), in its order of operations ----

  /** Give every synapse its own efficacy and every neuron a plastic bias. Reverse contacts
   *  receive the mean of their proposed updates, as in the library. This does not make an
   *  asymmetric measured graph reciprocal, nor make unequal initial efficacies equal. */
  enableLearning() {
    if (this.efficacy) return;
    const n = this.n, pre = this.pre, rowPtr = this.rowPtr;
    this.efficacy = Float64Array.from(this.efficacy0 || this.sign);
    if (!this.gainPre) { this.gainPre = new Float64Array(this.edges); for (let e = 0; e < this.edges; e++) this.gainPre[e] = this.gain * (this.count ? this.count[e] : 1); }
    const post = new Int32Array(this.edges);
    for (let i = 0; i < n; i++) for (let e = rowPtr[i], end = rowPtr[i + 1]; e < end; e++) post[e] = i;
    this.post = post;
    const key = new Map();
    for (let e = 0; e < this.edges; e++) key.set(post[e] * n + pre[e], e);
    this.reverse = new Int32Array(this.edges).fill(-1);
    for (let e = 0; e < this.edges; e++) { const r = key.get(pre[e] * n + post[e]); if (r !== undefined) this.reverse[e] = r; }
    this.lessons = 0;
    this.mass0 = null;  // each neuron's total input weight when learning began, for the mass cap
  }

  /** Restore exported parameters and clear learning history, preserving the live neural state. */
  resetLearning(gain = this.gain) {
    if (!Number.isFinite(gain) || gain < 0) throw new RangeError("gain must be finite and nonnegative");
    this.enableLearning();
    this.efficacy.set(this.efficacy0 || this.sign);
    this.bias.set(this.bias0);
    this.mass0 = null;
    this.lessons = 0;
    delete this.secondMoment; delete this.secondMomentBias; delete this.contrastUpdates;
    this.setGain(gain);
  }

  /** Set the gain the whole net runs at: every synapse's factor becomes gain * count * exp(log_gain[pre]),
   *  as the library composes it, and the weights follow from the current efficacies. */
  setGain(gain) {
    if (!Number.isFinite(gain) || gain < 0) throw new RangeError("gain must be finite and nonnegative");
    this.enableLearning();
    this.gain = gain;
    for (let e = 0; e < this.edges; e++) {
      this.gainPre[e] = gain * (this.count ? this.count[e] : 1) * (this.logGain ? Math.exp(this.logGain[this.pre[e]]) : 1);
      this.w[e] = this.gainPre[e] * this.efficacy[e];
    }
  }

  /** A nudged phase (a copy of the live state): settle under the current drive with the extra drive
   *  beta * (target[i] - s[i]) on the output neurons, up to `steps` steps or until no activation moves by
   *  `tolerance`, in the library's order: synaptic input, standing drive, nudge, minus v, times dt. */
  nudgedPhase(outputs, target, beta, steps, tolerance) {
    const n = this.n, rowPtr = this.rowPtr, pre = this.pre, w = this.w, dt = this.dt, drive = this.drive, bias = this.bias;
    const v = Float64Array.from(this.v), s = Float64Array.from(this.s), total = new Float64Array(n), prev = new Float64Array(n);
    const mask = new Float64Array(n); for (const i of outputs) mask[i] = 1.0;
    let taken = 0;
    for (let k = 0; k < steps; k++) {
      for (let i = 0; i < n; i++) { let sum = 0.0; for (let e = rowPtr[i], end = rowPtr[i + 1]; e < end; e++) sum += s[pre[e]] * w[e]; total[i] = sum; }
      for (let i = 0; i < n; i++) {
        let t = total[i];
        t += drive[i] + bias[i];
        t += beta * (target[i] - s[i]) * mask[i];
        t -= v[i];
        t *= dt;
        v[i] += t;
      }
      prev.set(s);
      let movement = 0.0;
      for (let i = 0; i < n; i++) { s[i] = this.activation(v[i]); const d = Math.abs(s[i] - prev[i]); if (d > movement) movement = d; }
      taken = k + 1;
      if (tolerance !== undefined && tolerance !== null && movement < tolerance) break;
    }
    return { s, v, taken };
  }

  /** Finite-phase contrast update. Defaults reproduce the library's centered arithmetic; one-sided
   *  matched-duration continuation and relative/mass/sign constraints are experimental adapters.
   *  The live state is untouched. scaleStep/biasStep retain the library's proposed-step convention;
   *  appliedScaleStep/appliedBiasStep measure the parameter change after every constraint. These
   *  finite phases on a directed measured graph carry no equilibrium-gradient guarantee. */
  lesson(outputs, target, { beta = 0.1, eta = 0.2, etaBias = eta / 10, steps = 50, tolerance = 1e-4, cap = 8.0, normalize = 0.0, normalizeFloor = 1e-3, decay = 0.0, centered = true, keepSign = false, massCap = 0, relative = false } = {}) {
    // Refuse malformed lessons before any parameters or optimizer history can change.
    if (!outputs || !Number.isInteger(outputs.length) || outputs.length === 0) throw new RangeError("outputs must be a nonempty index vector");
    const seen = new Set();
    for (const i of outputs) {
      if (!Number.isInteger(i) || i < 0 || i >= this.n || seen.has(i)) throw new RangeError("outputs must contain distinct valid neuron indices");
      seen.add(i);
    }
    if (!target || target.length !== this.n || !Array.from(target).every(Number.isFinite)) throw new RangeError("target must be a finite value per neuron");
    if (!Number.isFinite(beta) || beta <= 0 || !Number.isFinite(eta) || eta < 0 || !Number.isFinite(etaBias) || etaBias < 0) throw new RangeError("beta must be positive and learning rates nonnegative and finite");
    if (!Number.isSafeInteger(steps) || steps < 0 || (tolerance != null && (!Number.isFinite(tolerance) || tolerance < 0))) throw new RangeError("phase budget and tolerance must be nonnegative and finite");
    if (!Number.isFinite(cap) || cap <= 0 || !Number.isFinite(normalizeFloor) || normalizeFloor <= 0 || !Number.isFinite(normalize) || normalize < 0 || normalize >= 1 || !Number.isFinite(decay) || decay < 0 || decay >= 1) throw new RangeError("invalid learning bounds or normalization");
    if (!Number.isFinite(massCap) || (massCap !== 0 && massCap < 1)) throw new RangeError("massCap must be zero or at least one");
    if (typeof centered !== "boolean" || typeof relative !== "boolean" || typeof keepSign !== "boolean") throw new TypeError("learning switches must be boolean");
    for (const values of [this.v, this.s, this.drive, this.bias, this.w]) if (!values.every(Number.isFinite)) throw new RangeError("learning requires a finite live state and weights");
    this.enableLearning();
    let mass0 = this.mass0;
    if (massCap > 0 && !mass0) { mass0 = new Float64Array(this.n); for (let i = 0; i < this.n; i++) { let m = 0; for (let e = this.rowPtr[i], end = this.rowPtr[i + 1]; e < end; e++) m += Math.abs(this.w[e]); mass0[i] = m; } }
    if (mass0 && !mass0.every(Number.isFinite)) throw new RangeError("reference input masses must be finite");
    // centred (the library's default): the +beta phase against the -beta phase over 2 beta. One-sided: the +beta phase
    // against a free continuation over beta. Run that continuation for exactly the plus phase's
    // actual step count, without its own early stop: both trajectories start from the same state
    // and cover the same elapsed time. This finite-continuation adapter differs from library s0.
    const plus = this.nudgedPhase(outputs, target, beta, steps, tolerance);
    const minus = this.nudgedPhase(outputs, target, centered ? -beta : 0.0, centered ? steps : plus.taken, centered ? tolerance : null);
    for (const phase of [plus, minus]) if (!phase.s.every(Number.isFinite) || !phase.v.every(Number.isFinite)) throw new RangeError("learning phase became nonfinite; no update applied");
    const sp = plus.s, sm = minus.s, span = centered ? 2.0 * beta : beta, n = this.n, E = this.edges, pre = this.pre, post = this.post;
    const contrast = new Float64Array(E), neuron = new Float64Array(n);
    for (let e = 0; e < E; e++) {
      const ap = sp[pre[e]], am = sm[pre[e]], bp = sp[post[e]], bm = sm[post[e]];
      contrast[e] = (ap * (bp - bm) + (ap - am) * bm) / span;
    }
    for (let i = 0; i < n; i++) neuron[i] = (sp[i] - sm[i]) / span;
    const delta = new Float64Array(E), deltaBias = new Float64Array(n);
    let secondMoment = null, secondMomentBias = null, contrastUpdates = null;
    if (relative) {  // Contact-local scale: only this contact's two phase products enter its step.
      // For the displayed nonnegative activations, the proposed one-sided step is at most eta
      // in magnitude (centered: eta/2). Subsequent row-mass adjustments have a separate contract.
      const floor2 = normalizeFloor * normalizeFloor;
      for (let e = 0; e < E; e++) {
        const scale = Math.max(Math.abs(sp[pre[e]] * sp[post[e]]), Math.abs(sm[pre[e]] * sm[post[e]])) + floor2;
        delta[e] = eta * (contrast[e] * beta / scale);
      }
      for (let i = 0; i < n; i++) {
        const scale = Math.max(Math.abs(sp[i]), Math.abs(sm[i])) + normalizeFloor;
        deltaBias[i] = etaBias * (neuron[i] * beta / scale);
      }
    } else if (normalize > 0) {  // the library's RMS normalization: each synapse's step divided by the running RMS of its own contrast, bias-corrected
      secondMoment = this.secondMoment ? this.secondMoment.slice() : new Float64Array(E);
      secondMomentBias = this.secondMomentBias ? this.secondMomentBias.slice() : new Float64Array(n);
      const rho = normalize, count = (this.contrastUpdates || 0) + 1, correction = 1.0 - Math.pow(rho, count);
      for (let e = 0; e < E; e++) { secondMoment[e] = rho * secondMoment[e] + (1 - rho) * contrast[e] * contrast[e]; delta[e] = eta * (contrast[e] / (Math.sqrt(secondMoment[e] / correction) + normalizeFloor)); }
      for (let i = 0; i < n; i++) { secondMomentBias[i] = rho * secondMomentBias[i] + (1 - rho) * neuron[i] * neuron[i]; deltaBias[i] = etaBias * (neuron[i] / (Math.sqrt(secondMomentBias[i] / correction) + normalizeFloor)); }
      contrastUpdates = count;
    } else {
      for (let e = 0; e < E; e++) delta[e] = eta * contrast[e];
      for (let i = 0; i < n; i++) deltaBias[i] = etaBias * neuron[i];
    }
    for (const values of [contrast, neuron, delta, deltaBias, secondMoment, secondMomentBias]) if (values && !values.every(Number.isFinite)) throw new RangeError("learning update became nonfinite; no update applied");
    const paired = this.reverse, mean = new Float64Array(E);
    for (let e = 0; e < E; e++) mean[e] = paired[e] >= 0 ? 0.5 * (delta[e] + delta[paired[e]]) : delta[e];
    let scaleStep = 0.0, biasStep = 0.0;
    const sign = this.sign, efficacy = this.efficacy.slice(), weight = new Float64Array(E), bias = this.bias.slice();
    for (let e = 0; e < E; e++) {
      let scale = this.efficacy[e] + mean[e];
      if (decay > 0) scale *= 1.0 - decay;
      if (scale > cap) scale = cap; else if (scale < -cap) scale = -cap;
      if (keepSign && sign && scale * sign[e] < 0) scale = 0;  // Dale's law, declared: a synapse keeps its measured sign and weakens at most to nothing
      efficacy[e] = scale; weight[e] = this.gainPre[e] * scale;
      scaleStep += Math.abs(mean[e]);
    }
    let massLowerUnmetRows = 0;
    if (massCap > 0) {  // Receiver-local input-mass adjustment after the proposed reciprocal-pair average.
      // The hard efficacy cap takes precedence over restoring the lower mass target; a zero row
      // cannot be revived by scaling. These constraints need not preserve paired update equality.
      const rowPtr = this.rowPtr;
      for (let i = 0; i < n; i++) {
        let m = 0; for (let e = rowPtr[i], end = rowPtr[i + 1]; e < end; e++) m += Math.abs(weight[e]);
        const upper = massCap * mass0[i], lower = mass0[i] / massCap;
        const f = m > upper ? upper / m : m < lower && m > 0 ? lower / m : 1;
        let after = 0;
        for (let e = rowPtr[i], end = rowPtr[i + 1]; e < end; e++) {
          efficacy[e] = Math.max(-cap, Math.min(cap, efficacy[e] * f));
          weight[e] = this.gainPre[e] * efficacy[e];
          after += Math.abs(weight[e]);
        }
        if (lower > after * (1 + 8 * Number.EPSILON)) massLowerUnmetRows++;
      }
    }
    for (let i = 0; i < n; i++) { let b = this.bias[i] + deltaBias[i]; if (decay > 0) b *= 1.0 - decay; bias[i] = b; biasStep += Math.abs(deltaBias[i]); }
    for (const values of [efficacy, weight, bias]) if (!values.every(Number.isFinite)) throw new RangeError("learning parameters became nonfinite; no update applied");
    let appliedScaleStep = 0, appliedBiasStep = 0;
    for (let e = 0; e < E; e++) appliedScaleStep += Math.abs(efficacy[e] - this.efficacy[e]);
    for (let i = 0; i < n; i++) appliedBiasStep += Math.abs(bias[i] - this.bias[i]);
    this.efficacy.set(efficacy); this.w.set(weight); this.bias.set(bias); this.mass0 = mass0;
    if (secondMoment) { this.secondMoment = secondMoment; this.secondMomentBias = secondMomentBias; this.contrastUpdates = contrastUpdates; }
    this.lessons++;
    return { scaleStep: E ? scaleStep / E : 0, biasStep: n ? biasStep / n : 0,
      appliedScaleStep: E ? appliedScaleStep / E : 0, appliedBiasStep: n ? appliedBiasStep / n : 0,
      massLowerUnmetRows,
      plusSteps: plus.taken, minusSteps: minus.taken, plus: sp, minus: sm };
  }

  mean(name) { const idx = this.sets[name]; if (!idx || !idx.length) return 0; let t = 0; for (const i of idx) t += this.s[i]; return t / idx.length; }
  peak(name) { const idx = this.sets[name]; let m = 0; if (!idx) return 0; for (const i of idx) if (this.s[i] > m) m = this.s[i]; return m; }
  activeCount(level = 0.5) { let c = 0; for (let i = 0; i < this.n; i++) if (this.s[i] >= level) c++; return c; }
}
