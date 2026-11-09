// Every sound is synthesized with the Web Audio API: no samples, nothing to license. The
// context is created on the first user gesture (browsers keep audio locked until then).
//
//   engine   two hums (you on the left, the brain on the right); pitch follows the riding speed
//   turn     a short blip, rising for your turns, falling for the brain's
//   count    three beeps and a higher "go"
//   crash    a noise burst through a falling filter and a low thump, panned to the crash
//   stinger  win: a rising arpeggio; loss: a falling line; draw: two even notes
//   thinking a soft tone that swells with each settle and fades along its repair curve

const MUTE_KEY = "cadence-tron-play.muted";

export class Sound {
  constructor() {
    this.ctx = null;
    this.muted = false;
    try { this.muted = localStorage.getItem(MUTE_KEY) === "1"; } catch (_) { /* storage blocked */ }
  }

  /** Call from a user gesture. */
  unlock() {
    if (this.ctx) {
      if (this.ctx.state === "suspended") this.ctx.resume();
      return;
    }
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    const ctx = new AC();
    this.ctx = ctx;
    this.bus = ctx.createDynamicsCompressor();
    this.bus.threshold.value = -16;
    this.bus.ratio.value = 4;
    this.master = ctx.createGain();
    this.master.gain.value = this.muted ? 0 : 0.8;
    // A short feedback delay gives the stingers and blips a little space.
    this.delay = ctx.createDelay(1);
    this.delay.delayTime.value = 0.17;
    const fb = ctx.createGain();
    fb.gain.value = 0.28;
    const wet = ctx.createGain();
    wet.gain.value = 0.22;
    this.delay.connect(fb).connect(this.delay);
    this.delay.connect(wet).connect(this.bus);
    this.bus.connect(this.master).connect(ctx.destination);
    const len = Math.floor(ctx.sampleRate * 1.2);
    this.noise = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = this.noise.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    // Seat 0 is the brain (right), seat 1 you (left).
    this.engines = [this.voice(["sawtooth", "square"], 0.35, 61.7), this.voice(["sawtooth", "sawtooth"], -0.35, 55)];
    this.think = this.voice(["sine", "triangle"], 0, 196);
    this.think.filter.frequency.value = 900;
    this.think.filter.Q.value = 1;
  }

  get ready() { return !!this.ctx; }

  setMuted(m) {
    this.muted = m;
    try { localStorage.setItem(MUTE_KEY, m ? "1" : "0"); } catch (_) { /* storage blocked */ }
    if (this.ctx) this.master.gain.setTargetAtTime(m ? 0 : 0.8, this.ctx.currentTime, 0.03);
  }

  voice(types, pan, f) {
    const ctx = this.ctx;
    const gain = ctx.createGain();
    gain.gain.value = 0;
    const filter = ctx.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.value = 400;
    filter.Q.value = 4;
    const p = ctx.createStereoPanner();
    p.pan.value = pan;
    const osc = types.map((t, k) => {
      const o = ctx.createOscillator();
      o.type = t;
      o.frequency.value = f * (k ? 1.503 : 1);
      o.connect(filter);
      o.start();
      return o;
    });
    filter.connect(gain).connect(p).connect(this.bus);
    return { osc, gain, filter, pan: p, base: f };
  }

  // ---- engines ------------------------------------------------------------------------------
  /** speed: 1 at the nominal tick rate (lower when the brain takes longer); tick: into the game. */
  engine(seat, on, speed = 1, tick = 0) {
    if (!this.ctx) return;
    const v = this.engines[seat];
    const t = this.ctx.currentTime;
    const s = Math.min(1.4, Math.max(0.3, speed));
    const f = v.base * (0.8 + 0.2 * s) * (1 + Math.min(tick, 400) / 1400);
    v.osc[0].frequency.setTargetAtTime(f, t, 0.08);
    v.osc[1].frequency.setTargetAtTime(f * 1.503, t, 0.08);
    v.cutoff = on ? 280 + 520 * s : 120;
    v.filter.frequency.setTargetAtTime(v.cutoff, t, 0.1);
    v.gain.gain.setTargetAtTime(on ? (seat === 0 ? 0.045 : 0.055) : 0, t, on ? 0.15 : 0.05);
  }

  /** A small push of both hums each tick: the cycles move a cell. */
  pulse() {
    if (!this.ctx) return;
    const t = this.ctx.currentTime;
    for (const v of this.engines) {
      const f = v.cutoff || 400;
      v.filter.frequency.cancelScheduledValues(t);
      v.filter.frequency.setValueAtTime(f * 1.35, t);
      v.filter.frequency.setTargetAtTime(f, t + 0.01, 0.05);
    }
  }

  // ---- one-shots ----------------------------------------------------------------------------
  tone(type, f0, f1, dur, vol, when = 0, pan = 0, wet = false) {
    const ctx = this.ctx;
    if (!ctx) return;
    const t = ctx.currentTime + when;
    const o = ctx.createOscillator();
    o.type = type;
    o.frequency.setValueAtTime(f0, t);
    o.frequency.exponentialRampToValueAtTime(Math.max(1, f1), t + dur);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol, t + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    const p = ctx.createStereoPanner();
    p.pan.value = pan;
    o.connect(g).connect(p).connect(this.bus);
    if (wet) p.connect(this.delay);
    o.start(t);
    o.stop(t + dur + 0.03);
  }

  turn(seat) {
    if (seat === 1) this.tone("sine", 900, 1500, 0.07, 0.11, 0, -0.3, true);
    else this.tone("triangle", 640, 400, 0.08, 0.09, 0, 0.3, true);
  }

  count(go) {
    if (go) {
      this.tone("square", 880, 880, 0.34, 0.07, 0, 0, true);
      this.tone("sine", 1320, 1320, 0.4, 0.08, 0, 0, true);
    } else this.tone("square", 440, 440, 0.13, 0.065, 0, 0, true);
  }

  crash(seat) {
    const ctx = this.ctx;
    if (!ctx) return;
    const t = ctx.currentTime;
    const pan = seat === 0 ? 0.4 : -0.4;
    const src = ctx.createBufferSource();
    src.buffer = this.noise;
    const f = ctx.createBiquadFilter();
    f.type = "lowpass";
    f.frequency.setValueAtTime(5200, t);
    f.frequency.exponentialRampToValueAtTime(80, t + 0.95);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.55, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + 1.05);
    const p = ctx.createStereoPanner();
    p.pan.value = pan;
    src.connect(f).connect(g).connect(p).connect(this.bus);
    src.start(t);
    src.stop(t + 1.15);
    this.tone("sine", 140, 32, 0.75, 0.6, 0, pan);
    this.tone("sawtooth", 260, 55, 0.38, 0.1, 0.02, pan);
    this.engine(seat, false);
  }

  /** result from your side: "win" | "loss" | "draw" */
  stinger(result) {
    if (result === "win") {
      [523.25, 659.25, 783.99, 1046.5].forEach((f, k) => {
        this.tone("triangle", f, f, 0.45, 0.12, 0.35 + k * 0.09, 0, true);
        this.tone("sine", 2 * f, 2 * f, 0.3, 0.035, 0.47 + k * 0.09, 0, true);
      });
    } else if (result === "loss") {
      [440, 349.23, 293.66, 220].forEach((f, k) => this.tone("sawtooth", f, f * 0.97, 0.5, 0.05, 0.35 + k * 0.14, 0, true));
    } else {
      [392, 392].forEach((f, k) => this.tone("triangle", f, f, 0.3, 0.08, 0.35 + k * 0.2, 0, true));
    }
  }

  /** The thinking tone: swells with a settle and fades along its repair curve (the largest
   *  potential repair per sweep, log scale), over `dur` seconds; the move picks the note. */
  thinking(repair, dur, choice) {
    const ctx = this.ctx;
    const v = this.think;
    if (!ctx || !v) return;
    const t = ctx.currentTime;
    const f = [196, 246.94, 293.66][choice == null ? 1 : choice];
    v.osc[0].frequency.setTargetAtTime(f, t, 0.03);
    v.osc[1].frequency.setTargetAtTime(2 * f, t, 0.03);
    const logs = (repair && repair.length ? repair : [1, 1e-6]).map((x) => Math.log10(Math.max(x, 1e-9)));
    const hi = Math.max(...logs);
    const lo = Math.min(hi - 1, ...logs);
    const n = Math.max(2, Math.min(24, logs.length));
    const curve = new Float32Array(n);
    for (let k = 0; k < n; k++) {
      const x = logs[Math.min(logs.length - 1, Math.round((k / (n - 1)) * (logs.length - 1)))];
      curve[k] = 0.003 + 0.028 * ((x - lo) / (hi - lo));
    }
    v.gain.gain.cancelScheduledValues(t);
    v.gain.gain.setValueAtTime(Math.max(0.0001, v.gain.gain.value), t);
    try { v.gain.gain.setValueCurveAtTime(curve, t + 0.004, Math.max(0.06, dur)); } catch (_) { /* overlapping */ }
    v.filter.frequency.setTargetAtTime(600 + 1500 * Math.min(1, logs.length / 96), t, 0.05);
  }

  quiet() {
    if (!this.ctx) return;
    const t = this.ctx.currentTime;
    this.think.gain.gain.cancelScheduledValues(t);
    this.think.gain.gain.setTargetAtTime(0, t, 0.12);
    this.engine(0, false);
    this.engine(1, false);
  }
}
