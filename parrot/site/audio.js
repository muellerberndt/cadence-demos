// The parrot's ear and voice on the page. The ear: the microphone (after the visitor's click; a page
// on localhost or https only) at 16,000 samples a second through an audio worklet that computes the
// library's log-mel frames (dsp.js); each moment the page sends the brain the last 0.1 s of samples
// and its ten frames. The voice: frames the brain's voice motor sends, in the same format, turned
// into sound by the filter-bank voice (dsp.js) and played through Web Audio; its loudness opens the
// beak. No speech synthesis: the parrot can only make sounds of the kind it hears.
import { synthesise, HOP, RATE, MELS } from './dsp.js';

const SILENT = Math.log(1e-6);

// --- the parrot's voice ------------------------------------------------------------------------------
// A parrot has no vocal folds: it imitates speech with its syrinx, a tonal source whose frequency it moves
// to trace our formants, so its words sound whistly, bright, nasal and a little buzzy. The page's parrot
// voice: the remembered word pitched up about four semitones, a sine-wave layer whose three tones follow
// the word's first formants, a high-pass at 300 Hz (a small body), a presence peak near 2.6 kHz and a
// touch of waveshaping (the syrinx's buzz).
export const PARROT = { pitch: 1.26, highpass: 300, peak: 2600, peakGain: 6, drive: 2.2, dry: 0.8, tones: [0.24, 0.17, 0.09] };
const RANGES = [[250, 900], [900, 2300], [2300, 3500]];
const formantCache = new WeakMap();
/** Each 10 ms of a word: the strongest frequency and its level in each formant range (its own spectrum). */
export function formantTracks(x, rate) {
  if (formantCache.has(x)) return formantCache.get(x);
  const n = 256, hop = Math.round(rate / 100), half = n / 2, win = new Float32Array(n), re = new Float32Array(half + 1), im = new Float32Array(half + 1);
  for (let i = 0; i < n; i++) win[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (n - 1));
  const cos = new Float32Array(n * (half + 1)), sin = new Float32Array(n * (half + 1));
  for (let k = 0; k <= half; k++) for (let i = 0; i < n; i++) { cos[k * n + i] = Math.cos((2 * Math.PI * k * i) / n); sin[k * n + i] = Math.sin((2 * Math.PI * k * i) / n); }
  const frames = [];
  for (let s0 = 0; s0 + n <= x.length; s0 += hop) {
    for (let k = 0; k <= half; k++) { let a = 0, b = 0; for (let i = 0; i < n; i++) { const v = x[s0 + i] * win[i]; a += v * cos[k * n + i]; b += v * sin[k * n + i]; } re[k] = a; im[k] = b; }
    const row = [];
    for (const [lo, hi] of RANGES) {
      let best = 0, at = lo; for (let k = Math.ceil(lo * n / rate); k <= Math.min(half, Math.floor(hi * n / rate)); k++) { const m = Math.hypot(re[k], im[k]); if (m > best) { best = m; at = k * rate / n; } }
      row.push([at, best]);
    }
    frames.push(row);
  }
  const tops = RANGES.map((_, j) => Math.max(1e-9, ...frames.map((r) => r[j][1])));
  const out = { hop: hop / rate, frames: frames.map((r) => r.map(([f, m], j) => [f, m / tops[j]])) };
  formantCache.set(x, out);
  return out;
}
function buzzCurve(drive) {
  const c = new Float32Array(1024);
  for (let i = 0; i < 1024; i++) { const x = (i / 1023) * 2 - 1; c[i] = Math.tanh(drive * x) / Math.tanh(drive); }
  return c;
}
/** The parrot voice's graph for one remembered word, in any audio context (live or offline). */
export function parrotVoice(ctx, buffer, dest, pitch = PARROT.pitch, when = 0, P = PARROT) {
  const t0 = when || ctx.currentTime, src = ctx.createBufferSource(); src.buffer = buffer; src.playbackRate.value = pitch;
  const hp = ctx.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = P.highpass; hp.Q.value = 0.7;
  const pk = ctx.createBiquadFilter(); pk.type = 'peaking'; pk.frequency.value = P.peak; pk.gain.value = P.peakGain; pk.Q.value = 1.1;
  const ws = ctx.createWaveShaper(); ws.curve = buzzCurve(P.drive); ws.oversample = '2x';
  const dry = ctx.createGain(); dry.gain.value = P.dry;
  src.connect(hp); hp.connect(pk); pk.connect(ws); ws.connect(dry); dry.connect(dest);
  const x = buffer.getChannelData(0), tr = formantTracks(x, buffer.sampleRate), dur = x.length / buffer.sampleRate / pitch;
  const tones = P.tones.map((level, j) => {
    const osc = ctx.createOscillator(), g = ctx.createGain(); osc.type = 'sine'; g.gain.value = 0;
    tr.frames.forEach((row, k) => { const t = t0 + (k * tr.hop) / pitch; osc.frequency.setValueAtTime(Math.min(3900, row[j][0] * pitch), t); g.gain.setTargetAtTime(level * row[j][1] ** 1.5, t, 0.006); });
    g.gain.setTargetAtTime(0, t0 + dur, 0.01);
    osc.connect(g); g.connect(hp); osc.start(t0); osc.stop(t0 + dur + 0.1);
    return osc;
  });
  src.start(t0);
  return { src, tones, duration: dur };
}

export class ParrotAudio {
  constructor() {
    this.ctx = null; this.mic = false; this.level = 0;
    this.frames = []; this.queue = []; this.pcmQueue = []; this.samples = new Float32Array(1600); this.heardLoud = false;
    this.speaking = null;
  }

  /** The page's whole sound output as a stream (for a recording of the page itself). */
  tap() {
    if (!this.ctx) return null;
    this.tapNode ||= this.ctx.createMediaStreamDestination();
    this.gain.connect(this.tapNode);
    return this.tapNode.stream;
  }
  /** A human voice clip (the questions' voiceover): played as recorded, through the page's output, unfiltered. */
  async playClip(url) {
    await this.unlock();
    this.clips ||= new Map();
    if (!this.clips.has(url)) this.clips.set(url, fetch(url).then((r) => r.arrayBuffer()).then((b) => this.ctx.decodeAudioData(b)));
    const buf = await this.clips.get(url), node = this.ctx.createBufferSource(); node.buffer = buf; node.connect(this.gain); node.start();
    return buf.duration;
  }
  /** A remembered word rendered offline through the parrot voice (for checks). */
  async renderParrot(pcm8k, rate = 8000, P = PARROT) {
    const pitch = P.pitch, len = Math.ceil((pcm8k.length / rate / pitch + 0.2) * 16000);
    const off = new OfflineAudioContext(1, len, 16000), buf = off.createBuffer(1, pcm8k.length, rate);
    let peak = 0; for (const v of pcm8k) peak = Math.max(peak, Math.abs(v));
    const ch = buf.getChannelData(0), g = peak > 0 ? Math.min(0.9 / peak, 30) : 1; for (let i = 0; i < pcm8k.length; i++) ch[i] = pcm8k[i] * g;
    parrotVoice(off, buf, off.destination, pitch, 0, P);
    return (await off.startRendering()).getChannelData(0);
  }

  /** Audio may start only from a visitor's gesture; the first click calls this. */
  async unlock() {
    if (!this.ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      this.ctx = new AC({ sampleRate: RATE });
      this.gain = this.ctx.createGain(); this.gain.gain.value = 0.9; this.gain.connect(this.ctx.destination);
    }
    if (this.ctx.state !== 'running') await this.ctx.resume();
    return this.ctx.state === 'running';
  }

  async startMic() {
    // the context starts here; a browser lets it run only after a click or a key, so a page that opens
    // with the microphone on hears from the first click or key on
    if (!this.ctx) { const AC = window.AudioContext || window.webkitAudioContext; this.ctx = new AC({ sampleRate: RATE }); this.gain = this.ctx.createGain(); this.gain.gain.value = 0.9; this.gain.connect(this.ctx.destination); }
    if (this.ctx.state !== 'running') {
      this.ctx.resume().catch(() => {});
      const go = () => { this.ctx.resume().catch(() => {}); if (this.ctx.state === 'running') for (const ev of ['pointerdown', 'keydown']) window.removeEventListener(ev, go, true); };
      for (const ev of ['pointerdown', 'keydown']) window.addEventListener(ev, go, true);
    }
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) throw new Error('The microphone works only on localhost or https.');
    if (!this.workletReady) { await this.ctx.audioWorklet.addModule(new URL('./ear-worklet.js', import.meta.url)); this.workletReady = true; }
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: false, autoGainControl: true } });
    this.source = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, 'parrot-ear');
    this.node.port.onmessage = ({ data }) => this.heard(data);
    this.source.connect(this.node);
    this.mic = true;
  }

  stopMic() {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.source?.disconnect(); this.node?.disconnect();
    this.mic = false; this.level = 0;
  }

  heard({ samples, frame, rms }) {
    this.samples.copyWithin(0, HOP); this.samples.set(samples, 1600 - HOP);
    if (frame) {
      this.frames.push(frame); if (this.frames.length > 10) this.frames.shift(); // the ear's display
      this.queue.push(frame); if (this.queue.length > 300) this.queue.shift(); // every frame since the last moment, for the brain
      this.pcmQueue.push(samples); if (this.pcmQueue.length > 300) this.pcmQueue.shift(); // and its 160 samples of audio
    }
    this.level += (Math.min(1, rms * 6) - this.level) * 0.3;
    if (rms > 0.02) this.heardLoud = true;
  }

  /** The moment's sound for the brain: the last 1,600 samples and every log-mel frame heard since the
   *  last moment (frame-major), so no sound is lost when a moment takes longer than 100 ms. */
  moment() {
    let mel, pcm = new Float32Array(0);
    if (this.mic && this.queue.length) {
      mel = new Float32Array(this.queue.length * MELS);
      this.queue.forEach((f, i) => mel.set(f, i * MELS));
      if (this.pcmQueue.length === this.queue.length) {
        pcm = new Float32Array(this.pcmQueue.length * HOP);
        this.pcmQueue.forEach((a, i) => pcm.set(a, i * HOP));
      }
      this.queue = []; this.pcmQueue = [];
    } else mel = new Float32Array(10 * MELS).fill(SILENT);
    const audio = this.mic ? this.samples.slice() : new Float32Array(1600);
    const loud = this.heardLoud; this.heardLoud = false;
    return { mel, audio, loud, pcm };
  }

  /** Say frames (k x 40, frame-major) through the voice; returns the loudness every 10 ms. */
  speak(flat) {
    if (!this.ctx || this.ctx.state !== 'running' || !flat?.length) return null;
    const frames = [];
    for (let i = 0; i + MELS <= flat.length; i += MELS) frames.push(flat.subarray(i, i + MELS));
    const samples = synthesise(frames, { pitch: 560 + Math.random() * 180 });
    let peak = 0; for (const v of samples) peak = Math.max(peak, Math.abs(v));
    if (peak > 0.95) for (let i = 0; i < samples.length; i++) samples[i] *= 0.95 / peak;
    const buf = this.ctx.createBuffer(1, samples.length, RATE);
    buf.copyToChannel(samples, 0);
    const node = this.ctx.createBufferSource(); node.buffer = buf; node.connect(this.gain); node.start();
    const env = [];
    for (let i = 0; i < samples.length; i += HOP) { let e = 0; for (let k = i; k < Math.min(samples.length, i + HOP); k++) e += samples[k] * samples[k]; env.push(Math.sqrt(e / HOP)); }
    const top = Math.max(1e-6, ...env);
    this.speaking = { start: performance.now(), env: env.map((v) => v / top), node };
    return this.speaking;
  }

  /** Say a remembered sound as it was heard: its audio (8 kHz), played back as it is. */
  speakPcm(pcm8k, rate = 8000) {
    if (!this.ctx || this.ctx.state !== 'running' || !pcm8k?.length) return null;
    let peak = 0; for (const v of pcm8k) peak = Math.max(peak, Math.abs(v));
    const g = peak > 0 ? Math.min(0.9 / peak, 30) : 1;
    const buf = this.ctx.createBuffer(1, pcm8k.length, rate);
    const ch = buf.getChannelData(0); for (let i = 0; i < pcm8k.length; i++) ch[i] = pcm8k[i] * g;
    const vary = 1 + (Math.random() - 0.5) * 0.08; // recalled, never replayed exactly: a little higher or lower, faster or slower each time
    const v = parrotVoice(this.ctx, buf, this.gain, PARROT.pitch * vary), node = v.src, speed = PARROT.pitch * vary; // every word it says, in its parrot voice
    const env = [];
    const step = Math.max(1, Math.round((rate / 100) * speed)); // the loudness every 10 ms of the word as played
    for (let i = 0; i < ch.length; i += step) { let e = 0; for (let k = i; k < Math.min(ch.length, i + step); k++) e += ch[k] * ch[k]; env.push(Math.sqrt(e / step)); }
    const top = Math.max(1e-6, ...env);
    this.speaking = { start: performance.now(), env: env.map((v) => v / top), node };
    return this.speaking;
  }

  /** A word said without a sound (the page has none for it): the beak opens and closes once a syllable,
   *  about 180 ms each, with no sound played. */
  mouth(word) {
    const syl = Math.max(1, (String(word).toLowerCase().match(/[aeiouy]+/g) || []).length);
    const env = [];
    for (let s = 0; s < syl; s++) for (let i = 0; i < 18; i++) env.push(Math.sin(Math.PI * i / 18) ** 0.8 * 0.8);
    this.speaking = { start: performance.now(), env, node: null };
    return this.speaking;
  }

  /** The voice's loudness now, 0 to 1 (the beak opens with it). */
  loudness(now = performance.now()) {
    const s = this.speaking;
    if (!s) return 0;
    const i = Math.floor((now - s.start) / 10);
    if (i >= s.env.length) { this.speaking = null; return 0; }
    return s.env[i];
  }
}
