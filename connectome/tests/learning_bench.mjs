// The integrator learns to hold: one half of the compiled brainstem runs saccades (a burst to the
// integrator, alternating in sign as the two halves' bursts do), drifts for a window, and after each
// window takes one lesson of the library's rule toward the state it held when the burst ended, the
// neural-state drift as a surrogate error. A probe from rest after every lesson measures the hold: the ratio of the
// integrator's level a window after a standard burst to its level at the burst's end, and the time
// constant that ratio implies. Controls: no learning, reversed feedback, learning on a degree-preserving
// shuffle of the same wiring.
//   node tests/learning_bench.mjs --payload web/data/brain_oculomotor.json --eta 20 --beta 0.1 --saccades 30 [--shuffle 1] [--sign -1] [--learn 0] [--out receipts/x.json]
import { readFileSync, writeFileSync } from "node:fs";
import { SettlingBrain } from "../web/brain.js";
import { shuffleContacts } from "./learning_shuffle_helper.mjs";
globalThis.atob ??= (b) => Buffer.from(b, "base64").toString("binary");
const arg = (k, d) => { const i = process.argv.indexOf("--" + k); return i < 0 ? d : process.argv[i + 1]; };
const P = { payload: arg("payload", "web/data/brain_oculomotor.json"), start: +arg("start", 0.8), eta: +arg("eta", 0.2), beta: +arg("beta", 0.1), steps: +arg("steps", 50), tolerance: +arg("tolerance", 1e-4),
  drift: +arg("drift", 50), interval: +arg("interval", 100), saccades: +arg("saccades", 30), level: +arg("level", 0.1), levels: arg("levels", "0.1").split(",").map(Number), probeLevels: arg("probe-levels", "0.03,0.1").split(",").map(Number), seed: +arg("seed", 1), burst: +arg("burst", 5), sign: +arg("sign", 1), learn: +arg("learn", 1), shuffle: +arg("shuffle", 0), slipMin: +arg("slip-min", 0), levelMin: +arg("level-min", 0.01), cap: +arg("cap", 8), normalize: +arg("normalize", 0), decay: +arg("decay", 0), etaBias: arg("eta-bias", null), targetDelay: +arg("target-delay", 25), centered: +arg("centered", 1), keepSign: +arg("keep-sign", 0), massCap: +arg("mass-cap", 0), inhibit: +arg("inhibit", 1), relative: +arg("relative", 0), slipRel: +arg("slip-rel", 0), levelMax: +arg("level-max", 1), worlds: arg("worlds", ""), fixation: +arg("fixation", 0), intervalMin: +arg("interval-min", 0), intervalMax: +arg("interval-max", 0), probeWindow: +arg("probe-window", 300), out: arg("out", "") };
const STEP_S = 0.04;
const payload = JSON.parse(readFileSync(P.payload, "utf8"));
const brain = new SettlingBrain(payload);
brain.enableLearning();
// Version 1 learning receipts used a permutation that admitted duplicate contacts and
// non-involutive reverse mappings. Preserve those historical files, but do not treat
// their shuffled arms as validated same-rule controls. New runs bind this corrected null.
const shuffle = P.shuffle ? shuffleContacts(brain, P.shuffle) : null;
brain.setGain(P.start * payload.gain);
const Int = payload.populations._Int_, ABD = [...payload.populations.ABD_m, ...payload.populations.ABD_i];
const mean = (idx) => { let t = 0; for (const i of idx) t += brain.s[i]; return t / idx.length; };
const peak = () => { let m = 0; for (let i = 0; i < brain.n; i++) if (brain.s[i] > m) m = brain.s[i]; return m; };
/** The hold, probed from rest in a copy of the live state: a standard burst, a window of drift, the ratio. */
function probeAt(level) {
  brain.reset(); brain.clearStimuli(); brain.stimulate("_Int_", level);
  for (let i = 0; i < P.burst; i++) brain.step();
  brain.clearStimuli();
  for (let i = 0; i < P.targetDelay; i++) brain.step();  // the transient: the burst's pattern relaxes onto the slow mode
  const m0 = mean(Int), a0 = mean(ABD);
  for (let i = 0; i < P.probeWindow; i++) brain.step();
  const m1 = mean(Int), a1 = mean(ABD), top = peak();
  for (let i = 0; i < 600 - P.probeWindow - P.targetDelay; i++) brain.step(); const m600 = mean(Int);
  const ratio = m0 > 0 ? m1 / m0 : 0, tau = ratio >= 0.999 ? 999 : ratio <= 0 ? 0 : -(P.probeWindow * STEP_S) / Math.log(ratio);
  return { m0, m1, ratio, tau, abd0: a0, abd1: a1, peak: top, hold600: m0 > 0 ? m600 / m0 : 0 };
}
/** The hold, probed from rest in a copy of the live state at every probe level: the largest level's
 *  ratio and time constant, the smallest level's, and the graded ratio of the two held levels. */
function probe() {
  const v = Float64Array.from(brain.v), s = Float64Array.from(brain.s), d = Float64Array.from(brain.drive);
  const at = P.probeLevels.map(probeAt);
  brain.v.set(v); brain.s.set(s); brain.drive.set(d);
  const big = at[at.length - 1], small = at[0];
  return { ...big, tauSmall: small.tau, ratioSmall: small.ratio, graded: big.m1 > 0 ? small.m1 / big.m1 : 0, peakSmall: small.peak };
}
const rows = [];
let t0 = performance.now(), lessonMs = 0, lessons = 0, seedState = P.seed >>> 0;
rows.push({ saccade: 0, ...probe(), slip: 0, scaleStep: 0 });
for (let saccade = 1; saccade <= P.saccades; saccade++) {
  const k = saccade;
  const sgn = k % 2 ? 1 : -P.inhibit;  // the two halves' bursts, seen from one half: excitation for its own saccades, inhibition (a declared fraction) for the other side's
  seedState = (seedState * 1664525 + 1013904223) >>> 0; const level = P.levels[Math.floor((seedState / 4294967296) * P.levels.length)];  // a saccade of one of the declared sizes
  brain.clearStimuli(); if (sgn !== 0) for (const i of Int) brain.setDrive(i, sgn * level);
  for (let i = 0; i < P.burst; i++) brain.step();
  brain.clearStimuli();
  for (let i = 0; i < P.targetDelay; i++) brain.step();  // the target is the state the eye came to after the saccade, not the burst's peak
  const target = Float64Array.from(brain.s), m0 = mean(Int);
  seedState = (seedState * 1664525 + 1013904223) >>> 0;
  const interval = P.intervalMax > 0 ? Math.round(P.intervalMin + (seedState / 4294967296) * (P.intervalMax - P.intervalMin)) : P.interval;
  const window = P.fixation ? Math.max(1, interval - P.targetDelay) : P.drift;  // the slip over the whole fixation, or over the declared drift window
  for (let i = 0; i < window; i++) brain.step();
  const slip = mean(Int) - m0;
  let report = { scaleStep: 0, plusSteps: 0, minusSteps: 0 };
  if (P.learn && Math.abs(slip) >= P.slipMin && Math.abs(slip) >= P.slipRel * m0 && m0 >= P.levelMin && m0 <= P.levelMax) {  // a lesson needs a held level in the fixation range and a slip above the dead zone: a calm net learns nothing
    const tl = performance.now();
    // --sign -1: reversed feedback, the slip read backwards (the goldfish control). --worlds by saccade count: "n:m0.25" settles the
    // image at a fraction of the state the eye landed in (a world that drifts back), "n:k2" shows the drift k times (against the eye)
    let world = { m: 1 };
    if (P.worlds) { let acc = 0; for (const part of P.worlds.split(",")) { const [n, spec] = part.split(":"); acc += +n; if (saccade <= acc) { world = spec[0] === "k" ? { k: +spec.slice(1) } : { m: +spec.slice(1) }; break; } } }
    const tgt = P.sign < 0 ? Float64Array.from(brain.s, (x, i) => 2 * x - target[i]) : world.k ? Float64Array.from(brain.s, (x, i) => x + world.k * (target[i] - x)) : world.m === 1 ? target : Float64Array.from(target, (x) => world.m * x);
    report = brain.lesson(Int, tgt, { beta: P.beta, eta: P.eta, etaBias: P.etaBias === null ? P.eta / 10 : +P.etaBias, steps: P.steps, tolerance: P.tolerance, cap: P.cap, normalize: P.normalize, decay: P.decay, centered: !!P.centered, keepSign: !!P.keepSign, massCap: P.massCap, relative: !!P.relative });
    lessonMs += performance.now() - tl; lessons++;
  }
  for (let i = 0; i < (P.fixation ? 0 : interval); i++) brain.step();
  const pr = probe();
  rows.push({ saccade: k, ...pr, slip, scaleStep: report.scaleStep, plusSteps: report.plusSteps, minusSteps: report.minusSteps, live: mean(Int), livePeak: peak() });
}
const wall = performance.now() - t0;
// where the learning went: the mean efficacy by sender and receiver class
const cls = new Array(brain.n).fill("other"); for (const [name, key] of [["_Int_", "Int"], ["ABD_m", "ABD"], ["ABD_i", "ABD"], ["_DOs_", "DO"], ["_Axl_", "Axl"]]) for (const i of payload.populations[name] || []) cls[i] = key;
const byClass = {}; for (let e = 0; e < brain.edges; e++) { const k = cls[brain.pre[e]] + ">" + cls[brain.post[e]]; const r = byClass[k] || (byClass[k] = { n: 0, eff: 0, abs: 0 }); r.n++; r.eff += brain.efficacy[e] * brain.sign[e]; r.abs += Math.abs(brain.efficacy[e]); }
const classes = Object.fromEntries(Object.entries(byClass).sort((a, b) => b[1].n - a[1].n).map(([k, r]) => [k, { n: r.n, eff: +(r.eff / r.n).toFixed(3) }]));
const at = (k) => rows[Math.min(k, rows.length - 1)];
const summary = { params: P, shuffle, neurons: brain.n, synapses: brain.edges, lessons, lesson_ms: lessons ? lessonMs / lessons : 0, wall_ms: wall,
  tau: Object.fromEntries([0, 1, 2, 3, 5, 10, 20, 30, 50, 100].filter((k) => k <= P.saccades).map((k) => [k, +at(k).tau.toFixed(2)])),
  tau_small: Object.fromEntries([0, 10, 20, 30, 50, 100].filter((k) => k <= P.saccades).map((k) => [k, +at(k).tauSmall.toFixed(2)])),
  graded: Object.fromEntries([0, 10, 20, 30, 50, 100].filter((k) => k <= P.saccades).map((k) => [k, +at(k).graded.toFixed(3)])),
  ratio: Object.fromEntries([0, 5, 10, 20, 30, 50, 100].filter((k) => k <= P.saccades).map((k) => [k, +at(k).ratio.toFixed(4)])),
  hold600_last: +at(P.saccades).hold600.toFixed(4), peak_last: +at(P.saccades).peak.toFixed(4), live_peak_max: +Math.max(...rows.slice(1).map((r) => r.livePeak)).toFixed(4),
  classes, efficacy_abs_mean: +(() => { let t = 0; for (let e = 0; e < brain.edges; e++) t += Math.abs(brain.efficacy[e]); return t / brain.edges; })().toFixed(5), rows };
console.log(JSON.stringify({ eta: P.eta, beta: P.beta, centered: P.centered, keepSign: P.keepSign, massCap: P.massCap, inhibit: P.inhibit, relative: P.relative, slipRel: P.slipRel, levelMax: P.levelMax, worlds: P.worlds, fixation: P.fixation, probeWindow: P.probeWindow, lessons, etaBias: P.etaBias, delay: P.targetDelay, cap: P.cap, normalize: P.normalize, decay: P.decay, sign: P.sign, learn: P.learn, shuffle: P.shuffle, levels: P.levels, tau: summary.tau, tauSmall: summary.tau_small, graded: summary.graded, ratio: summary.ratio, hold600: summary.hold600_last, peak: summary.peak_last, livePeakMax: summary.live_peak_max, eff: summary.efficacy_abs_mean, lessonMs: +summary.lesson_ms.toFixed(1), wallMs: +wall.toFixed(0), classes }));
if (P.out) writeFileSync(P.out, JSON.stringify(summary, null, 1));
