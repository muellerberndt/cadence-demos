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
    // Warm the top end and add a small synthetic hall so nothing sounds dry or harsh.
    this.tone_lp = ctx.createBiquadFilter();
    this.tone_lp.type = "lowpass";
    this.tone_lp.frequency.value = 7000;
    this.bus.connect(this.tone_lp).connect(this.master).connect(ctx.destination);
    this.verb = ctx.createConvolver();
    const irLen = Math.floor(ctx.sampleRate * 1.8);
    const ir = ctx.createBuffer(2, irLen, ctx.sampleRate);
    for (let c = 0; c < 2; c++) { const d = ir.getChannelData(c); for (let i = 0; i < irLen; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / irLen, 2.5); }
    this.verb.buffer = ir;
    const vg = ctx.createGain();
    vg.gain.value = 0.3;
    this.verb.connect(vg).connect(this.bus);
    this.delay.connect(this.verb);
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
    if (wet) { p.connect(this.delay); p.connect(this.verb); }
    o.start(t);
    o.stop(t + dur + 0.03);
  }

  turn(seat) {
    // A two-step chip blip: up a fifth for you, down a fourth for the brain.
    if (seat === 1) {
      this.tone("triangle", 1046.5, 1046.5, 0.04, 0.09, 0, -0.3);
      this.tone("square", 1568, 1568, 0.05, 0.025, 0.035, -0.3, true);
    } else {
      this.tone("triangle", 784, 784, 0.04, 0.08, 0, 0.3);
      this.tone("square", 587.3, 587.3, 0.05, 0.02, 0.035, 0.3, true);
    }
  }

  count(go) {
    if (go) {
      [880, 1108.7, 1318.5, 1760].forEach((f, k) => this.tone("square", f, f, 0.09, 0.06, k * 0.045, 0, true));
      this.tone("triangle", 220, 110, 0.5, 0.25, 0);
    } else {
      this.tone("square", 440, 440, 0.12, 0.06, 0, 0, true);
      this.tone("triangle", 110, 110, 0.12, 0.2, 0);
    }
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
    // A falling square "derez" sweep, the classic 8-bit explosion tail.
    for (let k = 0; k < 6; k++) this.tone("square", 1400 / (k + 1), 1400 / (k + 2), 0.07, 0.05, 0.04 + k * 0.06, pan, true);
    this.duck(1.2);
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

  // ---- music: "Grid Runner", an original chiptune sequenced live (CC0) -----------------------
  // Four bars in A minor (Am F C G) at 150 bpm: pulse bass on eighths, an arpeggio on
  // sixteenths, a triangle lead every other loop, and a noise hat / kick.
  music(on) {
    if (!this.ctx) return;
    if (!this.mus) {
      this.mus = this.ctx.createGain();
      this.mus.gain.value = 0;
      this.mus.connect(this.master);
      const mv = this.ctx.createGain(); mv.gain.value = 0.25; this.mus.connect(mv).connect(this.verb);
    }
    const t = this.ctx.currentTime;
    this.mus.gain.cancelScheduledValues(t);
    this.mus.gain.setTargetAtTime(on ? 0.5 : 0, t, on ? 0.3 : 0.4);
    if (on && !this.seq) {
      this.step = 0;
      this.nextAt = t + 0.05;
      this.seq = setInterval(() => this.schedule(), 25);
    } else if (!on && this.seq) {
      const id = this.seq;
      this.seq = null;
      setTimeout(() => { if (!this.seq) clearInterval(id); }, 1500);
      clearInterval(id);
    }
  }

  duck(sec) {
    if (!this.mus || !this.seq) return;
    const t = this.ctx.currentTime;
    this.mus.gain.cancelScheduledValues(t);
    this.mus.gain.setTargetAtTime(0.12, t, 0.02);
    this.mus.gain.setTargetAtTime(0.5, t + sec, 0.3);
  }

  note(type, f, at, dur, vol, pan = 0) {
    const ctx = this.ctx;
    const o = ctx.createOscillator();
    o.type = type;
    o.frequency.value = f;
    const g = ctx.createGain();
    g.gain.setValueAtTime(vol, at);
    g.gain.exponentialRampToValueAtTime(0.0001, at + dur);
    const p = ctx.createStereoPanner();
    p.pan.value = pan;
    o.connect(g).connect(p).connect(this.mus);
    o.start(at);
    o.stop(at + dur + 0.02);
  }

  schedule() {
    const ctx = this.ctx;
    const s16 = 60 / 150 / 4;
    const mtof = (m) => 440 * Math.pow(2, (m - 69) / 12);
    const chords = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]];
    const lead = [76, 0, 74, 76, 0, 79, 0, 76, 72, 0, 74, 0, 72, 69, 0, 0];
    while (this.nextAt < ctx.currentTime + 0.12) {
      const at = this.nextAt;
      const i = this.step;
      const bar = Math.floor(i / 16) % 4;
      const loop = Math.floor(i / 64);
      const c = chords[bar];
      const b = i % 16;
      if (b % 2 === 0) this.note("square", mtof(c[0] - 24 + (b % 4 === 2 ? 12 : 0)), at, s16 * 1.6, 0.05, 0);
      this.note("square", mtof(c[[0, 1, 2, 1][b % 4]] + 12), at, s16 * 0.8, 0.018, (b % 2 ? 0.25 : -0.25));
      if (loop % 2 === 1 && lead[(b + bar * 4) % 16]) this.note("triangle", mtof(lead[(b + bar * 4) % 16]), at, s16 * 1.8, 0.07, 0);
      if (b % 4 === 0) {
        const o = ctx.createOscillator();
        o.frequency.setValueAtTime(150, at);
        o.frequency.exponentialRampToValueAtTime(40, at + 0.12);
        const g = ctx.createGain();
        g.gain.setValueAtTime(0.25, at);
        g.gain.exponentialRampToValueAtTime(0.0001, at + 0.14);
        o.connect(g).connect(this.mus);
        o.start(at); o.stop(at + 0.16);
      }
      if (b % 2 === 1) {
        const src = ctx.createBufferSource();
        src.buffer = this.noise;
        const f = ctx.createBiquadFilter();
        f.type = "highpass"; f.frequency.value = 7000;
        const g = ctx.createGain();
        g.gain.setValueAtTime(b % 4 === 3 ? 0.05 : 0.025, at);
        g.gain.exponentialRampToValueAtTime(0.0001, at + 0.04);
        src.connect(f).connect(g).connect(this.mus);
        src.start(at, Math.random()); src.stop(at + 0.05);
      }
      this.nextAt += s16;
      this.step += 1;
    }
  }

  quiet() {
    if (!this.ctx) return;
    this.music(false);
    const t = this.ctx.currentTime;
    this.think.gain.gain.cancelScheduledValues(t);
    this.think.gain.gain.setTargetAtTime(0, t, 0.12);
    this.engine(0, false);
    this.engine(1, false);
  }
}
