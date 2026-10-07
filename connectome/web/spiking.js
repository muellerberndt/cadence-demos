// The spiking port in the browser: the leaky integrate-and-fire model of Shiu et al. (2024)
// on the wiring the rate model settles. The arithmetic is that of verify_lif.simulate in the
// connectome compiler, step for step and in its order, so tests/spiking_parity.mjs holds this
// engine to the Python port spike for spike.
//
//   dv/dt = (v0 - v + g) / t_mbr          held while refractory
//   dg/dt = -g / tau                      held while refractory
//   spike when v > v_th; then v = 0 (relative to rest), g = 0, refractory for t_rfc
//   a spike adds w_syn * (signed synapse count) to g of every target after t_dly
//   a driven neuron receives Poisson events at r_poi, each adding w_syn * f_poi to v,
//   and has no refractory period
//   a silenced neuron's outgoing weights are zero
//
// Within one step, as Brian2 and the Python port: the state update with the refractory hold,
// the threshold, the synapse arrivals and the Poisson kicks, the reset. Over a step the exact
// solution is v' = v * e_m + g * c and g' = g * e_s with e_m = exp(-dt / t_mbr),
// e_s = exp(-dt / tau) and c = tau / (tau - t_mbr) * (e_s - e_m). The payload is the rate
// model's (synapses by receiving neuron, engine/export.py); the outgoing lists per
// presynaptic neuron are built from it once, targets in increasing order, as the Python
// port's stable sort by sender gives them.
//
// Neurons are visited in the order the Python port gives them state: the driven and the
// silenced first in index order, then every other neuron in the order a spike first reaches
// it, index order within a step. That order fixes the order in which the spikes of one step
// arrive and add to g, and so the last bit of every sum.
import { decodeArray } from "./brain.js";

/** sfc32: a small PRNG with 128 bits of state, seeded from one integer; the returned function gives uniforms in [0, 1). */
export function sfc32(seed) {
  const s = seed >>> 0;
  let x = s, y = (s ^ 0x9e3779b9) >>> 0, z = Math.imul(s, 0x6c8e9cf5) >>> 0, w = 1;
  const next = () => {
    const t = (((x + y) | 0) + w) | 0;
    w = (w + 1) | 0;
    x = y ^ (y >>> 9);
    y = (z + (z << 3)) | 0;
    z = (z << 21) | (z >>> 11);
    z = (z + t) | 0;
    return (t >>> 0) / 4294967296;
  };
  for (let k = 0; k < 20; k++) next();  // mix the seed through the state
  return next;
}

export class SpikingBrain {
  /** `payload`: the rate model's payload, which must carry arrays.count and arrays.sign. Options: wSynMv (required,
   *  the synaptic weight in mV), dtMs, vThMv, tMbrMs, tauMs, tRfcMs, tDlyMs, rPoiHz, fPoi, seed (of the Poisson
   *  generator), eventSchedule (pre-drawn events [[step, neuron], ...] that replace the generator), historyMs (how far
   *  back spikes are kept for rates and rasters), constants ({eM, eS, c} overriding the computed step constants). */
  constructor(payload, options = {}) {
    const { wSynMv, dtMs = 0.1, vThMv = 7, tMbrMs = 20, tauMs = 5, tRfcMs = 2.2, tDlyMs = 1.8, rPoiHz = 150, fPoi = 250,
            seed = 0, eventSchedule = null, historyMs = 1000, constants = null } = options;
    if (!Number.isFinite(wSynMv)) throw new Error("SpikingBrain needs wSynMv, the synaptic weight in mV");
    const arrays = payload.arrays || {};
    if (!arrays.count || !arrays.sign) throw new Error("the spiking model needs arrays.count and arrays.sign in the payload");
    this.n = payload.n; this.edges = payload.edges; this.sets = payload.populations || {};
    const n = this.n, E = this.edges;
    const rowPtr = decodeArray(arrays.row_ptr, Int32Array), pre = decodeArray(arrays.pre, Int32Array);
    const count = decodeArray(arrays.count, Uint16Array);
    const sign = decodeArray(arrays.sign, arrays.sign_dtype === "int8" ? Int8Array : Float64Array);
    // outgoing lists by presynaptic neuron, a counting sort of the CSR by receiver: targets stay in increasing order
    const outPtr = new Int32Array(n + 1);
    for (let e = 0; e < E; e++) outPtr[pre[e] + 1]++;
    for (let i = 0; i < n; i++) outPtr[i + 1] += outPtr[i];
    const outPost = new Int32Array(E), outSigned = new Float64Array(E), next = outPtr.slice(0, n);
    for (let i = 0; i < n; i++) {
      for (let e = rowPtr[i], end = rowPtr[i + 1]; e < end; e++) { const k = next[pre[e]]++; outPost[k] = i; outSigned[k] = count[e] * sign[e]; }
    }
    this.outPtr = outPtr; this.outPost = outPost; this.outSigned = outSigned; this.outW = new Float64Array(E);
    // the model and the per-step constants, computed as the Python port computes them
    this.dtMs = dtMs; this.vThMv = vThMv; this.tMbrMs = tMbrMs; this.tauMs = tauMs; this.tRfcMs = tRfcMs; this.tDlyMs = tDlyMs;
    this.rPoiHz = rPoiHz; this.fPoi = fPoi;
    this.eM = Math.exp(-dtMs / tMbrMs);
    this.eS = Math.exp(-dtMs / tauMs);
    this.c = (tauMs / (tauMs - tMbrMs)) * (this.eS - this.eM);
    if (constants) { this.eM = constants.eM ?? this.eM; this.eS = constants.eS ?? this.eS; this.c = constants.c ?? this.c; }
    this.pEvent = rPoiHz * dtMs / 1000.0;
    this.delay = Math.max(1, Math.round(tDlyMs / dtMs));  // the Python port rounds half to even; no model constant falls on a half
    this.refractory = Math.round(tRfcMs / dtMs);
    this.setWeight(wSynMv);
    // the state, by neuron
    this.u = new Float64Array(n); this.g = new Float64Array(n); this.counts = new Int32Array(n);
    this.heldUntil = new Int32Array(n).fill(-1);
    this.driven = new Uint8Array(n); this.emits = new Uint8Array(n).fill(1);
    this.drivenList = new Int32Array(0);
    this.compactOf = new Int32Array(n).fill(-1); this.neuronAt = new Int32Array(n); this.used = 0;  // the visiting order
    this.ring = []; for (let s = 0; s < this.delay; s++) this.ring.push(new Int32Array(n));  // spikes in flight, one slot per step of delay
    this.ringLen = new Int32Array(this.delay);
    this.spiking = new Int32Array(n);
    this.steps = 0;
    this.seed = seed; this.rng = sfc32(seed);
    this.historySteps = Math.max(1, Math.round(historyMs / dtMs));
    this.histStep = new Int32Array(4096); this.histNeuron = new Int32Array(4096); this.histLen = 0;
    this.schedule = null; this.cursor = 0;
    if (eventSchedule) this.setSchedule(eventSchedule);
  }

  /** Simulated time in ms at the end of the last completed step. */
  get t() { return this.steps * this.dtMs; }

  /** The per-step constants and derived counts, for a parity check against the Python port. */
  get constants() {
    return { eM: this.eM, eS: this.eS, c: this.c, pEvent: this.pEvent, kickMv: this.kickMv, delay: this.delay, refractory: this.refractory };
  }

  /** The synaptic weight in mV: every outgoing weight becomes w_syn * count * sign and a Poisson event adds w_syn * f_poi. */
  setWeight(wSynMv) {
    this.wSynMv = wSynMv; this.kickMv = wSynMv * this.fPoi;
    const outW = this.outW, outSigned = this.outSigned;
    for (let e = 0; e < outW.length; e++) outW[e] = outSigned[e] * wSynMv;
  }

  /** Pre-drawn Poisson events, [[step, neuron], ...], replacing the generator: an event kicks its neuron at that
   *  step if the neuron is driven then. The order within a step does not matter. */
  setSchedule(events) {
    const sorted = Array.from(events).sort((a, b) => a[0] - b[0]);
    const step = new Int32Array(sorted.length), neuron = new Int32Array(sorted.length);
    for (let k = 0; k < sorted.length; k++) {
      const [s, i] = sorted[k];
      if (!(Number.isInteger(s) && s >= 0) || !(Number.isInteger(i) && i >= 0 && i < this.n)) throw new Error(`bad scheduled event [${s}, ${i}]`);
      step[k] = s; neuron[k] = i;
    }
    this.schedule = { step, neuron }; this.cursor = 0;
  }

  /** Drive a population (by name) or an array of neuron indices: on, the neurons receive Poisson events and have no
   *  refractory period; off, they return to the plain model. Drive and silence before the first step for the
   *  Python port's visiting order. */
  drive(target, on = true) {
    const idx = this._resolve(target);
    for (const i of idx) this.driven[i] = on ? 1 : 0;
    if (on) this._reach(idx);
    let m = 0;
    for (let i = 0; i < this.n; i++) if (this.driven[i]) m++;
    const list = new Int32Array(m); m = 0;
    for (let i = 0; i < this.n; i++) if (this.driven[i]) list[m++] = i;
    this.drivenList = list;
  }

  /** No neuron driven. */
  clearDrive() { this.driven.fill(0); this.drivenList = new Int32Array(0); }

  /** Silence a population or an index array: the neurons still integrate and spike, but their spikes reach no target. */
  silence(target, on = true) {
    const idx = this._resolve(target);
    for (const i of idx) this.emits[i] = on ? 0 : 1;
    if (on) this._reach(idx);
  }

  /** Back to rest: potentials, conductances, counts, the spike history, the spikes in flight and the generator.
   *  The drive, the silencing and the schedule stay. */
  reset() {
    this.u.fill(0); this.g.fill(0); this.counts.fill(0); this.heldUntil.fill(-1);
    this.ringLen.fill(0); this.compactOf.fill(-1); this.used = 0;
    this.steps = 0; this.histLen = 0; this.cursor = 0; this.rng = sfc32(this.seed);
    const idx = [];
    for (let i = 0; i < this.n; i++) if (this.driven[i] || !this.emits[i]) idx.push(i);
    this._reach(idx);
  }

  /** `ms` of simulated time in steps of dt; returns the steps taken. */
  run(ms) {
    const k = Math.round(ms / this.dtMs);
    for (let s = 0; s < k; s++) this.step();
    return k;
  }

  /** One step of dt, in the Python port's order. */
  step() {
    const t = this.steps, u = this.u, g = this.g, heldUntil = this.heldUntil, neuronAt = this.neuronAt, used = this.used;
    const eM = this.eM, eS = this.eS, c = this.c;
    // 1. state update; a refractory neuron holds v and g
    for (let k = 0; k < used; k++) {
      const i = neuronAt[k];
      if (heldUntil[i] >= t) continue;
      u[i] = u[i] * eM + g[i] * c;
      g[i] *= eS;
    }
    // 2. threshold
    const spiking = this.spiking, vTh = this.vThMv;
    let nSpk = 0;
    for (let k = 0; k < used; k++) {
      const i = neuronAt[k];
      if (u[i] > vTh && heldUntil[i] < t) spiking[nSpk++] = i;
    }
    // 3. synapses: the spikes from `delay` steps ago arrive, then the Poisson kicks
    const slot = t % this.delay, arrive = this.ring[slot], nArr = this.ringLen[slot];
    if (nArr) {
      if (this.used < this.n) this._reachTargets(arrive, nArr);
      const outPtr = this.outPtr, outPost = this.outPost, outW = this.outW;
      for (let a = 0; a < nArr; a++) {
        const src = arrive[a];
        for (let e = outPtr[src], end = outPtr[src + 1]; e < end; e++) g[outPost[e]] += outW[e];
      }
    }
    const kick = this.kickMv, driven = this.driven;
    if (this.schedule) {
      const step = this.schedule.step, neuron = this.schedule.neuron;
      let cur = this.cursor;
      while (cur < step.length && step[cur] < t) cur++;
      while (cur < step.length && step[cur] === t) { const i = neuron[cur++]; if (driven[i]) u[i] += kick; }
      this.cursor = cur;
    } else if (this.drivenList.length) {
      const list = this.drivenList, p = this.pEvent, rng = this.rng;
      for (let k = 0; k < list.length; k++) if (rng() < p) u[list[k]] += kick;
    }
    // 4. reset; the slot read this step carries this step's spikes
    let nOut = 0;
    if (nSpk) {
      const counts = this.counts, emits = this.emits, refractory = this.refractory;
      for (let s = 0; s < nSpk; s++) {
        const i = spiking[s];
        u[i] = 0.0; g[i] = 0.0; counts[i]++;
        heldUntil[i] = t + (driven[i] ? 0 : refractory);
        if (emits[i]) arrive[nOut++] = i;
        this._record(t, i);
      }
    }
    this.ringLen[slot] = nOut;
    this.steps++;
  }

  /** Firing rate in Hz of every neuron over the last `windowMs` (clipped to the time run; at most the kept history). */
  rates(windowMs) {
    const w = Math.max(1, Math.round(windowMs / this.dtMs));
    if (w > this.historySteps) throw new Error(`rates over ${windowMs} ms need a history of at least that; this brain keeps ${this.historySteps * this.dtMs} ms`);
    const out = new Float64Array(this.n), span = Math.min(w, this.steps);
    if (!span) return out;
    const from = this.steps - span, histStep = this.histStep, histNeuron = this.histNeuron;
    for (let k = this.histLen - 1; k >= 0 && histStep[k] >= from; k--) out[histNeuron[k]] += 1;
    const seconds = span * this.dtMs / 1000.0;
    for (let i = 0; i < this.n; i++) out[i] /= seconds;
    return out;
  }

  /** The spikes at or after `tMs` (on the step grid; a spike at step k has time k * dt), oldest first, within the
   *  kept history: { times (ms), neurons }. For a raster, pass the time of the previous call. */
  spikesSince(tMs) {
    const from = Math.round(tMs / this.dtMs), histStep = this.histStep, histNeuron = this.histNeuron;
    let first = this.histLen;
    while (first > 0 && histStep[first - 1] >= from) first--;
    const m = this.histLen - first, times = new Float64Array(m), neurons = new Int32Array(m);
    for (let k = 0; k < m; k++) { times[k] = histStep[first + k] * this.dtMs; neurons[k] = histNeuron[first + k]; }
    return { times, neurons };
  }

  _resolve(target) {
    if (typeof target === "string") {
      const idx = this.sets[target];
      if (!idx) throw new Error(`unknown population ${target}`);
      return idx;
    }
    for (const i of target) if (!(Number.isInteger(i) && i >= 0 && i < this.n)) throw new Error(`neuron index ${i} out of range`);
    return target;
  }

  /** Give the listed neurons a place in the visiting order, those without one in index order. */
  _reach(idx) {
    const compactOf = this.compactOf, fresh = [];
    for (const i of idx) if (compactOf[i] === -1) { compactOf[i] = -2; fresh.push(i); }
    fresh.sort((a, b) => a - b);
    for (const i of fresh) { compactOf[i] = this.used; this.neuronAt[this.used++] = i; }
  }

  /** The targets of the arriving spikes that have no place yet, in index order, as the Python port reaches them. */
  _reachTargets(arrive, nArr) {
    const compactOf = this.compactOf, outPtr = this.outPtr, outPost = this.outPost;
    let fresh = null;
    for (let a = 0; a < nArr; a++) {
      const src = arrive[a];
      for (let e = outPtr[src], end = outPtr[src + 1]; e < end; e++) {
        const j = outPost[e];
        if (compactOf[j] === -1) { compactOf[j] = -2; (fresh ??= []).push(j); }
      }
    }
    if (!fresh) return;
    fresh.sort((a, b) => a - b);
    for (const j of fresh) { compactOf[j] = this.used; this.neuronAt[this.used++] = j; }
  }

  _record(t, i) {
    if (this.histLen === this.histStep.length) this._pruneHistory(t);
    this.histStep[this.histLen] = t; this.histNeuron[this.histLen] = i; this.histLen++;
  }

  /** Drop spikes older than the kept history; grow the buffer when the history alone fills more than half of it. */
  _pruneHistory(t) {
    const keepFrom = t - this.historySteps, histStep = this.histStep, histNeuron = this.histNeuron, len = this.histLen;
    let first = 0;
    while (first < len && histStep[first] < keepFrom) first++;
    const remaining = len - first;
    if (remaining * 2 > histStep.length) {
      const cap = histStep.length * 2, step = new Int32Array(cap), neuron = new Int32Array(cap);
      step.set(histStep.subarray(first, len)); neuron.set(histNeuron.subarray(first, len));
      this.histStep = step; this.histNeuron = neuron;
    } else {
      histStep.copyWithin(0, first, len); histNeuron.copyWithin(0, first, len);
    }
    this.histLen = remaining;
  }
}
