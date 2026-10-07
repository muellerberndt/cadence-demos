// The compiled brainstem settles here, off the drawing thread.
// {type:"init", url} -> {type:"ready", n, edges, populations, kinds}
// {type:"run", steps, stimuli:{left:{pop:level}, right:{pop:level}}} ->
//   {type:"state", steps, sides:{left:{readouts, active}, right:{...}}, left: Float32Array, right: Float32Array}
// {type:"reset"} -> rest
import { TwinBrain } from "./twin.js";

let twin = null, payload = null;
self.onmessage = async (ev) => {
  const m = ev.data;
  if (m.type === "init") {
    payload = await (await fetch(m.url)).json();
    twin = new TwinBrain(payload);
    self.postMessage({ type: "ready", n: twin.n, edges: payload.edges, populations: Object.keys(payload.populations), kinds: payload.kind || null, gain: payload.gain, axial_attenuation: payload.axial_attenuation });
  } else if (m.type === "run" && twin) {
    const state = twin.run(m.stimuli, m.steps);
    const left = Float32Array.from(twin.activity("left")), right = Float32Array.from(twin.activity("right"));
    self.postMessage({ type: "state", ...state, left, right }, [left.buffer, right.buffer]);
  } else if (m.type === "reset" && twin) {
    twin.reset(); self.postMessage({ type: "state", steps: 0, sides: {}, left: new Float32Array(twin.n), right: new Float32Array(twin.n) });
  }
};
