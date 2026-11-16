// The parrot's ear and voice, the arithmetic: the library's speech front end in JavaScript
// (cadence.speech.frontend.log_mel at its defaults: 16,000 samples a second; frames of 400 samples,
// 25 ms, Hann window, every 160 samples, 10 ms; a 512-point spectrum; 40 triangular mel filters
// evenly spaced on the mel scale from 0 Hz to 8 kHz; natural log of the power in each filter plus
// 1e-6), and a filter-bank voice that turns frames of that format back into sound. Plain module:
// the page, the audio worklets and the tests (Node) import it.
export const RATE = 16000, FRAME = 400, HOP = 160, FFT = 512, MELS = 40, BINS = FFT / 2 + 1;

export function melBank(mels = MELS, rate = RATE, fft = FFT) {
  const mel = (hz) => 2595 * Math.log10(1 + hz / 700);
  const top = mel(rate / 2), edges = [];
  for (let i = 0; i < mels + 2; i++) edges.push(700 * (10 ** ((top * i) / (mels + 1) / 2595) - 1));
  const bins = fft / 2 + 1, bank = [];
  for (let m = 0; m < mels; m++) {
    const row = new Float64Array(bins), low = edges[m], mid = edges[m + 1], high = edges[m + 2];
    for (let j = 0; j < bins; j++) {
      const f = (j * rate) / fft;
      const rise = (f - low) / Math.max(mid - low, 1e-9), fall = (high - f) / Math.max(high - mid, 1e-9);
      row[j] = Math.max(0, Math.min(rise, fall));
    }
    bank.push(row);
  }
  return bank;
}

export function hann(n) { // numpy's np.hanning: symmetric
  const w = new Float64Array(n);
  if (n === 1) { w[0] = 1; return w; }
  for (let i = 0; i < n; i++) w[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (n - 1));
  return w;
}

// An iterative radix-2 FFT of a fixed size, in place on (re, im).
export class FFTn {
  constructor(n) {
    this.n = n; this.rev = new Uint32Array(n); this.cos = new Float64Array(n / 2); this.sin = new Float64Array(n / 2);
    const bits = Math.log2(n);
    for (let i = 0; i < n; i++) { let r = 0; for (let b = 0; b < bits; b++) r |= ((i >> b) & 1) << (bits - 1 - b); this.rev[i] = r; }
    for (let i = 0; i < n / 2; i++) { this.cos[i] = Math.cos((2 * Math.PI * i) / n); this.sin[i] = -Math.sin((2 * Math.PI * i) / n); }
  }
  transform(re, im, inverse = false) {
    const n = this.n, rev = this.rev;
    for (let i = 0; i < n; i++) { const j = rev[i]; if (j > i) { let t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; } }
    for (let size = 2; size <= n; size <<= 1) {
      const half = size >> 1, step = n / size;
      for (let start = 0; start < n; start += size) {
        for (let k = 0; k < half; k++) {
          const c = this.cos[k * step], s = inverse ? -this.sin[k * step] : this.sin[k * step];
          const a = start + k, b = a + half;
          const tr = re[b] * c - im[b] * s, ti = re[b] * s + im[b] * c;
          re[b] = re[a] - tr; im[b] = im[a] - ti; re[a] += tr; im[a] += ti;
        }
      }
    }
    if (inverse) for (let i = 0; i < n; i++) { re[i] /= n; im[i] /= n; }
  }
}

const shared = { bank: null, window: null, fft: null };
function tools() {
  if (!shared.bank) { shared.bank = melBank(); shared.window = hann(FRAME); shared.fft = new FFTn(FFT); }
  return shared;
}

/** One frame's log-mel values from FRAME samples starting at `offset`. */
export function logMelFrame(samples, offset = 0, out = new Float32Array(MELS)) {
  const { bank, window, fft } = tools();
  const re = new Float64Array(FFT), im = new Float64Array(FFT);
  for (let i = 0; i < FRAME; i++) re[i] = (samples[offset + i] || 0) * window[i];
  fft.transform(re, im);
  const power = new Float64Array(BINS);
  for (let j = 0; j < BINS; j++) power[j] = re[j] * re[j] + im[j] * im[j];
  for (let m = 0; m < MELS; m++) { let e = 0; const row = bank[m]; for (let j = 0; j < BINS; j++) e += power[j] * row[j]; out[m] = Math.log(e + 1e-6); }
  return out;
}

/** log_mel of a whole clip: frames x 40 (a clip shorter than a frame is padded with zeros). */
export function logMel(samples) {
  let x = samples;
  if (x.length < FRAME) { const p = new Float64Array(FRAME); p.set(x); x = p; }
  const count = 1 + Math.floor((x.length - FRAME) / HOP), out = [];
  for (let f = 0; f < count; f++) out.push(logMelFrame(x, f * HOP));
  return out;
}

/** The ear as a stream: samples in, a frame out every 160 samples once 400 are in (frames start
 *  where log_mel's do, at samples 0, 160, 320, ... of the stream). */
export class EarStream {
  constructor() { this.ring = new Float64Array(FRAME); this.pos = 0; this.n = 0; this.frame = new Float64Array(FRAME); }
  push(samples, onFrame) {
    for (let i = 0; i < samples.length; i++) {
      this.ring[this.pos] = samples[i]; this.pos = (this.pos + 1) % FRAME; this.n += 1;
      if (this.n >= FRAME && (this.n - FRAME) % HOP === 0) {
        for (let k = 0; k < FRAME; k++) this.frame[k] = this.ring[(this.pos + k) % FRAME];
        onFrame(logMelFrame(this.frame));
      }
    }
  }
}

// --- the voice: frames of the ear's format back into sound ----------------------------------------
// Each frame's 40 band powers become a power spectrum over the 257 bins (a non-negative mix of the
// same triangular filters whose band sums match the frame), shaped onto a source that is part
// harmonic (a parrot-high pitch with a little vibrato) and part noise; an inverse FFT, a Hann
// window, and overlap-add every 160 samples. It sounds buzzy and breathy, like a parrot imitating.
export class VoiceSynth {
  constructor({ pitch = 620, noise = 0.35, seed = 1 } = {}) {
    const t = tools();
    this.bank = t.bank; this.fft = t.fft; this.window = t.window;
    this.pitch = pitch; this.noise = noise;
    this.s = seed >>> 0;
    this.out = new Float64Array(FFT + HOP); // overlap-add accumulator
    this.ready = []; // samples ready to play
    this.phase = 0; this.t = 0;
    this.area = this.bank.map((row) => row.reduce((a, b) => a + b, 0));
    this.gain = 1.0;
  }
  rand() { this.s = (this.s * 1664525 + 1013904223) >>> 0; return this.s / 4294967296; }

  /** The power spectrum whose filter sums are the frame's band powers. */
  spectrum(frame) {
    const P = new Float64Array(MELS);
    for (let m = 0; m < MELS; m++) P[m] = Math.max(Math.exp(frame[m]) - 1e-6, 0);
    const c = new Float64Array(MELS);
    for (let m = 0; m < MELS; m++) c[m] = P[m] / Math.max(this.area[m] * this.area[m] * 0.5, 1e-12);
    const S = new Float64Array(BINS), E = new Float64Array(MELS);
    for (let it = 0; it < 12; it++) { // multiplicative steps toward band sums equal to P
      S.fill(0);
      for (let m = 0; m < MELS; m++) { const row = this.bank[m]; for (let j = 0; j < BINS; j++) S[j] += c[m] * row[j]; }
      for (let m = 0; m < MELS; m++) { const row = this.bank[m]; let e = 0; for (let j = 0; j < BINS; j++) e += row[j] * S[j]; E[m] = e; }
      for (let m = 0; m < MELS; m++) c[m] *= E[m] > 1e-12 ? P[m] / E[m] : 0;
    }
    S.fill(0);
    for (let m = 0; m < MELS; m++) { const row = this.bank[m]; for (let j = 0; j < BINS; j++) S[j] += c[m] * row[j]; }
    return S;
  }

  /** Add one frame (40 log-mel values); its 160 samples become ready. */
  push(frame) {
    const S = this.spectrum(frame);
    // the source: harmonics of the pitch (with vibrato) and noise, each bin's share
    const f0 = this.pitch * (1 + 0.04 * Math.sin(this.t * 2 * Math.PI * 5.5 * HOP / RATE));
    this.t += 1;
    const re = new Float64Array(FFT), im = new Float64Array(FFT), df = RATE / FFT;
    // the source's share in each bin, then each band set back to the frame's power, so the
    // harmonics move the sound's fine grain and leave its band levels as they were
    const H = new Float64Array(BINS), combOf = new Float64Array(BINS);
    for (let j = 1; j < BINS - 1; j++) {
      const f = j * df, k = Math.round(f / f0), near = Math.abs(f - k * f0) / df;
      combOf[j] = k >= 1 ? Math.exp(-0.5 * near * near) : 0;
      H[j] = S[j] * (this.noise + (1 - this.noise) * combOf[j]);
    }
    const P = new Float64Array(MELS);
    for (let m = 0; m < MELS; m++) P[m] = Math.max(Math.exp(frame[m]) - 1e-6, 0);
    for (let it = 0; it < 4; it++) {
      const r = new Float64Array(MELS);
      for (let m = 0; m < MELS; m++) { const row = this.bank[m]; let e = 0; for (let j = 0; j < BINS; j++) e += row[j] * H[j]; r[m] = e > 1e-15 ? P[m] / e : 0; }
      for (let j = 0; j < BINS; j++) { let num = 0, den = 0; for (let m = 0; m < MELS; m++) { const w = this.bank[m][j]; if (w) { num += w * r[m]; den += w; } } if (den > 0) H[j] *= num / den; }
    }
    for (let j = 1; j < BINS - 1; j++) {
      const comb = combOf[j], k = Math.round((j * df) / f0);
      const mag = Math.sqrt(H[j]) * this.gain;
      const ph = comb > 0.5 ? this.phase * k + k * 0.3 : this.rand() * 2 * Math.PI;
      re[j] = mag * Math.cos(ph); im[j] = mag * Math.sin(ph);
      re[FFT - j] = re[j]; im[FFT - j] = -im[j];
    }
    this.phase += (2 * Math.PI * f0 * HOP) / RATE;
    this.fft.transform(re, im, true);
    // windowed, scaled so the ear's Hann frame reads the frame's power back
    const out = this.out;
    for (let i = 0; i < FRAME; i++) out[i] += re[i] * this.window[i] * SCALE;
    const ready = out.slice(0, HOP);
    out.copyWithin(0, HOP); out.fill(0, out.length - HOP);
    this.ready.push(ready);
    return ready;
  }
}
// The overlap-add's level, measured once by the round-trip test (tests/voice_roundtrip.mjs) so the
// ear reads back the frame's own level.
export const SCALE = 2.07;

/** Synthesise a clip from frames (frames x 40): Float32Array of samples at 16 kHz. */
export function synthesise(frames, opts) {
  const v = new VoiceSynth(opts), parts = [];
  for (const f of frames) parts.push(v.push(f));
  for (let i = 0; i < 3; i++) parts.push(v.push(new Float32Array(MELS).fill(Math.log(1e-6))));
  const out = new Float32Array(parts.length * HOP);
  parts.forEach((p, i) => out.set(p, i * HOP));
  return out;
}
