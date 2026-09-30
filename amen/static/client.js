// The studio's line to the brain. The brain lives behind the local server: every half-beat
// is one pure settle query of the trained Cadence brain over the window of events the studio
// actually executed, the clock and the wake flag. Nothing here learns; queries admit nothing.
// The playing rule and the declared per-dub variety stay in this file, as the page's own moves
// on top of the brain's scores: they are rules of the instrument, not of the brain.

export function mulberry(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6D2B79F5) >>> 0;
    let t = Math.imul(state ^ (state >>> 15), state | 1) >>> 0;
    t = (t ^ ((t + (Math.imul(t ^ (t >>> 7), t | 61) >>> 0)) >>> 0)) >>> 0;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export class ServerBrain {
  constructor(meta) {
    this.meta = meta;               // one entry of /meta brains: layout, populations, steps, card numbers
    this.name = meta.name;
    this.layout = meta.layout;
    this.populations = meta.populations;
    this.countIn = meta.count_in;
    this.retriggers = meta.retriggers;
  }

  // One half-beat: the window of heard events (count-in first, newest last) in, the settled brain out.
  async step(window, t) {
    const reply = await fetch('/settle', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({brain: this.name, window: window.slice(-this.meta.steps), t}),
    });
    if (!reply.ok) throw new Error('settle failed: ' + reply.status + ' ' + (await reply.text()));
    const r = await reply.json();
    if (!r.qualified) throw new Error('the brain refused to settle: ' + r.reason);
    return r;                        // {out, state, errors, sweeps, energy, stationarity, seconds}
  }
}

const argmax = (a, s, e) => { let m = s; for (let i = s + 1; i < e; i++) if (a[i] > a[m]) m = i; return m; };
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));

// The event actually played from an output row (the same rule the training evaluation used).
// 'argmax' plays the highest-scoring slice; 'sample' draws a change point with the predicted
// probability times `energy` and there makes one of three moves from the slice heard before,
// with the dub's shares: a roll (repeat it), a retrigger (restart the break at a bar start) or
// a bar jump (the same position in another bar); where a move has a choice, squared scores decide.
// With `bassPower` set, a new bass note is drawn with probability proportional to score^power.
export function executed(out, L, retriggers, mode, random, previous, energy = 1, bassPower = 0, signature = null) {
  const e = new Array(L.event_ports).fill(0);
  const change = mode === 'sample' ? random() < clamp(out[L.change] * energy, 0, 1) : out[L.change] > 0.5;
  e[L.change] = change ? 1 : 0;
  for (let k = 0; k < L.texture_ports; k++) e[L.texture_start + k] = clamp(out[L.texture_start + k], 0, 1);
  if (out[L.drum_on] > 0.5) {
    const heard = previous && previous[L.drum_on] > 0.5; let crop;
    const pick = (options, prefer) => { const w = options.map((k, i) => (Math.pow(Math.max(out[k], 0), 2) + 1e-9) * (prefer ? prefer[i] : 1)), total = w.reduce((a, b) => a + b, 0); let draw = random() * total;
      for (let i = 0; i < w.length; i++) { draw -= w[i]; if (draw <= 0) return options[i]; } return options[options.length - 1]; };
    const move = mode === 'sample' && change ? random() : -1, shares = signature ? signature.moves : [1 / 3, 1 / 3, 1 / 3];
    if (move >= 0 && heard && move < shares[0]) crop = argmax(previous, 0, L.crops);
    else if (move >= 0 && heard && move >= shares[0] + shares[1]) { const next = (argmax(previous, 0, L.crops) + 1) % L.crops; crop = pick([8, 16, 24].map(d => (next + d) % L.crops), signature && signature.jumps); }
    else if (move >= 0) crop = pick(retriggers, signature && signature.retriggers);
    else crop = argmax(out, 0, L.crops);
    e[crop] = 1; e[L.drum_on] = 1; e[L.drum_gain] = clamp(out[L.drum_gain], 0, 1);
  }
  if (out[L.bass_on] > 0.5) {
    const hold = out[L.bass_hold] > 0.5; let note = argmax(out, L.note_start, L.note_start + L.notes);
    if (bassPower > 0 && !hold) {
      let total = 0; const w = []; for (let k = 0; k < L.notes; k++) { const v = Math.pow(Math.max(out[L.note_start + k], 0), bassPower); w.push(v); total += v; }
      if (total > 0) { let draw = random() * total; for (let k = 0; k < L.notes; k++) { draw -= w[k]; if (draw <= 0) { note = L.note_start + k; break; } } }
    }
    e[note] = 1; e[L.bass_on] = 1; e[L.bass_hold] = hold ? 1 : 0;
  }
  return e;
}

// Sixteen bars (or more) from silence. An async generator: each next() asks the brain for one
// half-beat and yields its trace step. `variation` in [0, 1] lets each dub differ: over the first
// `riffBars` the bass is drawn from the brain's note scores (power 8 at 0+, down to 2 at 1), which
// sets the key and the riff it then hears and continues; afterwards a note is drawn only where a
// change point fires. At 0 every choice is the highest score.
// Each dub draws a signature from its seed: which bar of the break it enters on, its shares of the
// three departure moves and its preferred targets. The dub's drum pattern is its own opening: over
// the first `signature.loopBars` bars departures are drawn at a raised probability, and afterwards
// the slice played at the cycle start and at each of the opening's departures returns at the same
// place in every cycle, unless the brain draws a fresh departure there. Between those places the
// brain plays on from what it hears, so a fill stays local and the groove comes back.
export async function* compose(brain, {bars = 16, mode = 'sample', energy = 1, seed = 1, variation = 0, riffBars = 2} = {}) {
  const L = brain.layout, random = mulberry(seed), horizon = 8 * bars;
  const dice = mulberry((seed ^ 0x2c1b3c6d) >>> 0), v = mode === 'sample' ? Math.min(1, Math.max(0, variation)) : 0;
  const spread = n => { const d = Array.from({length: n}, () => -Math.log(1 - dice())), total = d.reduce((a, b) => a + b, 0); return d.map(x => (1 - v) / n + v * x / total); };
  const signature = v > 0 ? {entry: Math.floor(dice() * 4), moves: spread(3), retriggers: spread(brain.retriggers.length), jumps: spread(3), loopBars: [1, 2, 2, 2, 4, 4][Math.floor(dice() * 6)]} : null;
  const cycle = signature ? 8 * signature.loopBars : 0, pattern = [];
  const countIn = Array.from(brain.countIn);
  if (signature) { const was = argmax(countIn, 0, L.crops); countIn[was] = 0; countIn[(8 * signature.entry + L.crops - 1) % L.crops] = 1; }
  const window = [countIn];
  for (let t = 0; t < horizon; t++) {
    const heard = window[window.length - 1];
    const step = await brain.step(window, t);
    const power = variation > 0 && mode === 'sample' ? 8 - 6 * Math.min(1, variation) : 0, riff = t < 8 * riffBars;
    const setting = cycle > 0 && t < cycle;
    const heat = setting && energy > 0 ? Math.max(energy, 1) * (1 + 4 * v) : energy;
    let event = executed(step.out, L, brain.retriggers, mode, random, mode === 'sample' ? heard : null, heat, riff ? power : 0, signature);
    if (!riff && power > 0 && event[L.change] > 0.5) { const drawn = executed(step.out, L, brain.retriggers, 'argmax', random, null, energy, power); for (let k = L.note_start; k < L.note_start + L.notes; k++) event[k] = drawn[k]; }
    if (cycle > 0 && event[L.drum_on] > 0.5) {
      const crop = argmax(event, 0, L.crops), fresh = event[L.change] > 0.5;
      if (setting) pattern[t] = {crop, edit: fresh};
      else { const want = pattern[t % cycle]; if (want && !fresh && (t % cycle === 0 || want.edit) && crop !== want.crop) { event[crop] = 0; event[want.crop] = 1; event[L.change] = 1; event.returned = true; } }
    }
    window.push(event);
    yield Object.assign(step, {t, phase: 'generated', heard: Array.from(heard), clock: t % 8, played: event, signature});
  }
}
