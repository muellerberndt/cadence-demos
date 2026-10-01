// Diagnostic transport around the unchanged historical and candidate engines.
// No training, record writes, output repair, or audio implementation lives here.
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {createInterface} from 'node:readline';
import {join, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

const root = resolve(process.argv[2]);
const old = await import(pathToFileURL(join(root, 'sources/legacy-engine.js')));
const modern = await import(pathToFileURL(join(root, 'sources/pilot-engine.js')));
const legacyModel = JSON.parse(readFileSync(join(root, 'legacy/model.json')));
const bytes = file => { const b = readFileSync(join(root, 'legacy', file)); return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength); };
const legacy = new old.Brain(legacyModel, bytes(legacyModel.files.params), bytes(legacyModel.files.records_y), bytes(legacyModel.files.records_mean));
const bundle = JSON.parse(readFileSync(join(root, 'pilot-model.json')));
const a = bundle.arrays;
const pilot = new modern.Brain(bundle.model, {kinds: Int8Array.from(a.kinds), sources: Int32Array.from(a.sources), targets: Int32Array.from(a.targets), weights: Float64Array.from(a.weights), biases: Float64Array.from(a.biases), state: Float64Array.from(a.state)});
const hash = values => { const h = createHash('sha256'); for (const v of values) h.update(new Uint8Array(v.buffer, v.byteOffset, v.byteLength)); return h.digest('hex'); };
const fixed = () => ({legacy: hash([...Object.values(legacy.p), legacy.y, legacy.mean]), pilot: hash([pilot.weights, pilot.biases, pilot.live])});
const initial = fixed();
const lines = createInterface({input: process.stdin});
for await (const line of lines) {
  try {
    const request = JSON.parse(line); let result;
    if (request.kind === 'reset') { legacy.forget(); legacy.reset(); result = {ok: true}; }
    else if (request.kind === 'step') result = {out: legacy.step(request.inputs).out};
    else if (request.kind === 'web') {
      const name = request.brain;
      if (!['legacy', 'pilot'].includes(name)) throw new Error('Unknown brain');
      const brain = name === 'legacy' ? legacy : pilot, engine = name === 'legacy' ? old : modern;
      const steps = [...engine.compose(brain, request.options)].map(s => ({t: s.t, out: Array.from(s.out), played: Array.from(s.played), returned: !!s.played.returned, heard: Array.from(s.heard), signature: s.signature, ...(name === 'pilot' ? {senses: Array.from(s.senses), state: Array.from(s.state), stationarity: s.stationarity, sweeps: s.sweeps, evaluations: s.evaluations} : {})}));
      result = {steps};
    } else if (request.kind === 'custody') result = {initial, current: fixed(), legacy_record_seen: legacy.seen};
    else throw new Error('Unknown operation');
    if (JSON.stringify(fixed()) !== JSON.stringify(initial)) throw new Error('Fixed parameters/records or pilot retained state mutated');
    process.stdout.write(JSON.stringify({ok: true, result}) + '\n');
  } catch (error) { process.stdout.write(JSON.stringify({ok: false, error: String(error.stack || error)}) + '\n'); }
}
