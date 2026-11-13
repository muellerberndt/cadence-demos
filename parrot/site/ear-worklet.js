// The parrot's ear in the audio thread: the microphone's samples (16 kHz) into log-mel frames, one
// every 10 ms, each sent to the page with its 160 new samples and their loudness.
import { EarStream, HOP } from './dsp.js';

class ParrotEar extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ear = new EarStream();
    this.hop = new Float32Array(HOP); this.fill = 0;
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      this.hop[this.fill++] = ch[i];
      if (this.fill === HOP) {
        const samples = this.hop.slice(); this.fill = 0;
        let e = 0; for (let k = 0; k < HOP; k++) e += samples[k] * samples[k];
        let frame = null;
        this.ear.push(samples, (f) => { frame = Float32Array.from(f); });
        this.port.postMessage({ samples, frame, rms: Math.sqrt(e / HOP) }, frame ? [samples.buffer, frame.buffer] : [samples.buffer]);
      }
    }
    return true;
  }
}
registerProcessor('parrot-ear', ParrotEar);
