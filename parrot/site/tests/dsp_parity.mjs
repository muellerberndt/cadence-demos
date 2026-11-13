// The page's ear against the library's: log_mel of 20 fixed clips (tests/fixtures/dsp_clips.json,
// made by tests/make_dsp_fixtures.py), the whole clip at once and as a stream. Fails when any value
// differs by more than 1e-3.  node parrot/site/tests/dsp_parity.mjs
import { readFileSync } from 'node:fs';
import { logMel, EarStream } from '../dsp.js';
const { clips } = JSON.parse(readFileSync(new URL('./fixtures/dsp_clips.json', import.meta.url)));
let worst = 0, worstStream = 0, count = 0;
for (const c of clips) {
  const x = Float64Array.from(c.samples);
  const got = logMel(x);
  if (got.length !== c.frames.length) throw new Error(`frame count ${got.length} != ${c.frames.length}`);
  got.forEach((f, i) => f.forEach((v, m) => { worst = Math.max(worst, Math.abs(v - c.frames[i][m])); count++; }));
  const ear = new EarStream(), streamed = [];
  for (let i = 0; i < x.length; i += 128) ear.push(x.subarray(i, i + 128), (f) => streamed.push(Float32Array.from(f)));
  streamed.forEach((f, i) => f.forEach((v, m) => { worstStream = Math.max(worstStream, Math.abs(v - c.frames[i][m])); }));
  if (streamed.length !== c.frames.length) throw new Error(`stream frames ${streamed.length} != ${c.frames.length}`);
}
const ok = worst <= 1e-3 && worstStream <= 1e-3;
console.log(JSON.stringify({ clips: clips.length, values: count, largest_difference: worst, largest_difference_streamed: worstStream, limit: 1e-3, ok }));
process.exit(ok ? 0 : 1);
