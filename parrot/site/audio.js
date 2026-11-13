// The parrot's ear and voice on the page. The ear: the microphone (after the visitor's click; a page
// on localhost or https only) at 16,000 samples a second through an audio worklet that computes the
// library's log-mel frames (dsp.js); each moment the page sends the brain the last 0.1 s of samples
// and its ten frames. The voice: frames the brain's voice motor sends, in the same format, turned
// into sound by the filter-bank voice (dsp.js) and played through Web Audio; its loudness opens the
// beak. No speech synthesis: the parrot can only make sounds of the kind it hears.
import { synthesise, HOP, RATE, MELS } from './dsp.js';

const SILENT = Math.log(1e-6);

export class ParrotAudio {
  constructor() {
    this.ctx = null; this.mic = false; this.level = 0;
    this.frames = []; this.queue = []; this.pcmQueue = []; this.samples = new Float32Array(1600); this.heardLoud = false;
    this.speaking = null;
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
    await this.unlock();
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
    const node = this.ctx.createBufferSource(); node.buffer = buf;
    node.playbackRate.value = 1 + (Math.random() - 0.5) * 0.08; // recalled, never replayed exactly: a little higher or lower, faster or slower each time
    node.connect(this.gain); node.start();
    const env = [];
    const step = Math.round(rate / 100); // the loudness every 10 ms
    for (let i = 0; i < ch.length; i += step) { let e = 0; for (let k = i; k < Math.min(ch.length, i + step); k++) e += ch[k] * ch[k]; env.push(Math.sqrt(e / step)); }
    const top = Math.max(1e-6, ...env);
    this.speaking = { start: performance.now(), env: env.map((v) => v / top), node };
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
