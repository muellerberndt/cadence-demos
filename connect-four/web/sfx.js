// Synthesized sound for Connect Four (Web Audio, nothing to license). Soft and short:
// a wooden "clack" for each disc (pitched by column), a quiet shimmer while the brain
// settles, and a small chord at the end of the game.
let ctx = null, bus = null, verb = null, hum = null;
let muted = false;
try { muted = localStorage.getItem('cadence-c4.muted') === '1'; } catch (_) {}

function unlock() {
  if (ctx) { if (ctx.state === 'suspended') ctx.resume(); return; }
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return;
  ctx = new AC();
  bus = ctx.createGain();
  bus.gain.value = muted ? 0 : 0.7;
  const lp = ctx.createBiquadFilter();
  lp.type = 'lowpass'; lp.frequency.value = 6000;
  bus.connect(lp).connect(ctx.destination);
  // tiny synthetic room
  verb = ctx.createConvolver();
  const len = ctx.sampleRate * 1.4, ir = ctx.createBuffer(2, len, ctx.sampleRate);
  for (let c = 0; c < 2; c++) { const d = ir.getChannelData(c); for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3); }
  verb.buffer = ir;
  const wet = ctx.createGain(); wet.gain.value = 0.25;
  verb.connect(wet).connect(bus);
}
addEventListener('pointerdown', unlock, { capture: true });
addEventListener('keydown', unlock, { capture: true });

function tone(type, f0, f1, dur, vol, when = 0, pan = 0, wet = 0.5) {
  if (!ctx) return;
  const t = ctx.currentTime + when;
  const o = ctx.createOscillator(); o.type = type;
  o.frequency.setValueAtTime(f0, t);
  o.frequency.exponentialRampToValueAtTime(Math.max(1, f1), t + dur);
  const g = ctx.createGain();
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(vol, t + 0.006);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  const p = ctx.createStereoPanner(); p.pan.value = pan;
  o.connect(g).connect(p).connect(bus);
  if (wet) { const w = ctx.createGain(); w.gain.value = wet; p.connect(w).connect(verb); }
  o.start(t); o.stop(t + dur + 0.05);
}

const PENT = [392, 440, 523.25, 587.33, 659.25, 783.99, 880];

export const sfx = {
  /** who: 'you' | 'brain' */
  drop(column, who) {
    const c = Math.max(0, Math.min(6, column | 0));
    const pan = (c - 3) / 4;
    const f = PENT[c] * (who === 'brain' ? 0.5 : 1);
    tone('triangle', f * 1.5, f, 0.16, 0.12, 0, pan);
    tone('sine', 180, 60, 0.12, 0.18, 0.02, pan, 0);
  },
  think() {
    if (!ctx) return;
    this.stopThink();
    const t = ctx.currentTime;
    const g = ctx.createGain(); g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.02, t + 0.4);
    const o1 = ctx.createOscillator(), o2 = ctx.createOscillator();
    o1.type = 'sine'; o2.type = 'sine'; o1.frequency.value = 523.25; o2.frequency.value = 526.5;
    o1.connect(g); o2.connect(g); g.connect(verb); g.connect(bus);
    o1.start(); o2.start();
    hum = { g, o: [o1, o2] };
  },
  stopThink() {
    if (!ctx || !hum) return;
    const { g, o } = hum; hum = null;
    const t = ctx.currentTime;
    g.gain.cancelScheduledValues(t); g.gain.setTargetAtTime(0.0001, t, 0.08);
    o.forEach((x) => x.stop(t + 0.5));
  },
  /** result from your side: 'win' | 'loss' | 'draw' */
  end(result) {
    this.stopThink();
    const notes = result === 'win' ? [523.25, 659.25, 783.99, 1046.5] : result === 'loss' ? [440, 392, 329.63, 261.63] : [440, 440];
    notes.forEach((f, k) => tone('triangle', f, f, 0.6, 0.07, 0.15 + k * 0.11, 0, 0.8));
  },
};
