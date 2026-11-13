// The parrot's ears: a question asked aloud, as raw sound. The page records the microphone at
// 16 kHz, one channel, and hands the samples to the brain's host (`hear`), with no recogniser and
// no transcription in between (cadence#329). A brain with no ears refuses the sound; the button
// beside the question box opens only where the pack's brain has ears (`manifest.ears`).
export const RATE = 16000;

/** Whether this browser can record the microphone. */
export function canListen() {
  return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && (window.AudioContext || window.webkitAudioContext));
}

/** Records the microphone until `stop()` is called or `most` milliseconds pass; resolves with the
 *  samples at RATE, one channel, as a Float32Array. */
export async function listen({ most = 6000, onLevel = null } = {}) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: false } });
  const Context = window.AudioContext || window.webkitAudioContext;
  const context = new Context({ sampleRate: RATE });
  const source = context.createMediaStreamSource(stream);
  const taps = context.createScriptProcessor(2048, 1, 1);
  const chunks = [];
  let done;
  const finished = new Promise((resolve) => { done = resolve; });
  taps.onaudioprocess = (event) => {
    const data = event.inputBuffer.getChannelData(0);
    chunks.push(new Float32Array(data));
    if (onLevel) { let peak = 0; for (let i = 0; i < data.length; i++) peak = Math.max(peak, Math.abs(data[i])); onLevel(peak); }
  };
  source.connect(taps); taps.connect(context.destination);
  const timer = setTimeout(() => done(), most);
  const stop = () => { clearTimeout(timer); done(); };
  const samples = finished.then(async () => {
    source.disconnect(); taps.disconnect(); stream.getTracks().forEach((t) => t.stop()); await context.close();
    const out = new Float32Array(chunks.reduce((n, c) => n + c.length, 0));
    let at = 0; for (const c of chunks) { out.set(c, at); at += c.length; }
    return out;
  });
  return { stop, samples };
}
