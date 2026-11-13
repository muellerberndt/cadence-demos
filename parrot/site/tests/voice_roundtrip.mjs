// The voice's round trip: frames of the ear's format -> the page's filter-bank voice -> the page's
// ear -> frames, against the frames put in. Over the fixture clips with a sound a voice can make
// (tones, chirps, noise, a voiced buzz; the clicks and the silent clips are left out: a click is
// shorter than a frame) it reads the error in each band that carries sound (within 6 nats of the
// frame's loudest band): the mean offset (the voice's level) and the mean absolute error once the
// offset is taken out. A voice from band levels alone draws its fine grain anew (part noise), and a
// noise's power in one narrow band varies about its mean by about one nat, so the error has that
// floor. Fails when the offset exceeds 0.5 nat or the error 1.3 nats.  node parrot/site/tests/voice_roundtrip.mjs
import { readFileSync } from 'node:fs';
import { logMel, synthesise } from '../dsp.js';
const { clips } = JSON.parse(readFileSync(new URL('./fixtures/dsp_clips.json', import.meta.url)));
let n = 0, sum = 0, sumAbs = 0;
const diffs = [];
clips.forEach((c, k) => {
  if (k % 6 === 3) return; // clicks
  const peak = Math.max(...c.frames.flat());
  if (peak < Math.log(1e-3)) return; // silent clips carry no voice
  const out = logMel(synthesise(c.frames.map((f) => Float32Array.from(f))));
  for (let i = 2; i < c.frames.length - 2; i++) {
    const top = Math.max(...c.frames[i]);
    for (let m = 0; m < 40; m++) {
      if (c.frames[i][m] < top - 6) continue;
      const d = out[i][m] - c.frames[i][m]; diffs.push(d); sum += d; n++;
    }
  }
});
const offset = sum / n;
for (const d of diffs) sumAbs += Math.abs(d - offset);
const error = sumAbs / n, ok = Math.abs(offset) <= 0.5 && error <= 1.3;
console.log(JSON.stringify({ bands: n, mean_offset_nats: +offset.toFixed(3), mean_abs_error_nats: +error.toFixed(3), limits: { offset: 0.5, error: 1.3 }, ok }));
process.exit(ok ? 0 : 1);
