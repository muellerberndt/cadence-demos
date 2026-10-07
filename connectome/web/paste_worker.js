// The compiled brainstem settles here, off the drawing thread, with the gain free.
// {type:"init", url} -> {type:"ready", n, edges, gain, populations:{name: size}, meta}
// {type:"run", steps, stimuli:{left:{pop:level}, right:{pop:level}}} ->
//   {type:"state", steps, sides, trace, left, right}: trace holds, per step, the left half's
//   integrator, ABD_m and ABD_i means and its active count (four floats per step)
// {type:"gain", gain} -> {type:"gain", gain}: every weight rescaled by gain / old gain, the state kept
// {type:"reset"} -> rest
import { TwinBrain, SIDES } from "./twin.js";
import { decodeArray } from "./brain.js";

const TRACED = ["_Int_", "ABD_m", "ABD_i"];
let payload = null, twin = null;

/** The base64 of a typed array's bytes, the inverse of decodeArray. */
function encodeArray(typed) {
  const u = new Uint8Array(typed.buffer, typed.byteOffset, typed.byteLength);
  let s = "";
  for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000));
  return btoa(s);
}

/** A copy of the payload at another gain: model.gain replaced and arrays.weight rescaled, since
 *  weight = gain * count * exp(log_gain[pre]) * efficacy (brain.js reads arrays.weight). */
function withGain(base, gain) {
  const w = decodeArray(base.arrays.weight, Float64Array);
  const k = gain / base.model.gain;
  for (let e = 0; e < w.length; e++) w[e] *= k;
  return { ...base, gain, model: { ...base.model, gain }, arrays: { ...base.arrays, weight: encodeArray(w) } };
}

/** A new twin at `gain`, carrying the old twin's potentials, activities and step count. */
function rebuild(gain) {
  const old = twin;
  twin = new TwinBrain(gain === payload.model.gain ? payload : withGain(payload, gain));
  if (old) {
    for (const side of SIDES) { twin.halves[side].v.set(old.halves[side].v); twin.halves[side].s.set(old.halves[side].s); twin.halves[side].steps = old.halves[side].steps; }
    twin.steps = old.steps;
  }
}

self.onmessage = async (ev) => {
  const m = ev.data;
  try {
    if (m.type === "init") {
      const r = await fetch(m.url);
      if (!r.ok) throw Error(`${m.url}: ${r.status}`);
      payload = await r.json();
      rebuild(payload.model.gain);
      const { arrays, ...meta } = payload;
      const populations = {};
      for (const [name, idx] of Object.entries(payload.populations || {})) populations[name] = idx.length;
      self.postMessage({ type: "ready", n: twin.n, edges: payload.edges, gain: payload.model.gain, populations, meta });
    } else if (m.type === "run" && twin) {
      const steps = Math.max(0, m.steps | 0);
      const trace = new Float32Array(steps * 4);
      let state = null;
      for (let k = 0; k < steps; k++) {
        state = twin.run(m.stimuli, 1);
        const left = state.sides.left;
        for (let j = 0; j < 3; j++) trace[4 * k + j] = left.readouts[TRACED[j]] ?? 0;
        trace[4 * k + 3] = left.active;
      }
      if (!state) state = { steps: twin.steps, sides: {} };
      const left = Float32Array.from(twin.activity("left")), right = Float32Array.from(twin.activity("right"));
      self.postMessage({ type: "state", ...state, trace, left, right }, [trace.buffer, left.buffer, right.buffer]);
    } else if (m.type === "gain" && twin) {
      rebuild(Number(m.gain));
      self.postMessage({ type: "gain", gain: twin.halves.left.gain });
    } else if (m.type === "reset" && twin) {
      twin.reset();
      self.postMessage({ type: "state", steps: 0, sides: {}, trace: new Float32Array(0), left: new Float32Array(twin.n), right: new Float32Array(twin.n) });
    }
  } catch (e) {
    self.postMessage({ type: "error", reason: String((e && e.message) || e) });
  }
};
