// Isolated, fixed-model diagnostic. The historical engine/assets are never edited.
import {createHash} from 'node:crypto';
import {once} from 'node:events';
import {createWriteStream, existsSync, mkdirSync, readFileSync, readdirSync, renameSync, statSync, writeFileSync} from 'node:fs';
import {dirname, join, relative, resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {createGzip} from 'node:zlib';
import {pipeline} from 'node:stream/promises';

export const ARMS = Object.freeze(['intact', 'no_record', 'context_reset', 'both']);
export const CHOICES = Object.freeze([['argmax', 0], ['sample', 1], ['sample', 2], ['sample', 3], ['sample', 4]].map(Object.freeze));
const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '..');
const MODEL = 'amen/web/models/three-corpora';
const PARITY = 'amen/runs/record-composer-v12/parity.json';
const ENGINE = 'amen/web/engine.js';
const COLLECTOR = 'fast-slow/amen_legacy_ablation.mjs';
const TEST = 'fast-slow/test_amen_legacy_ablation.mjs';
const PINNED_ENGINE = '7a7bef9ae9005b8338b08921c4fff7e3b1c5d21a160023c227c6b0539bcfea85';
export const sha = value => createHash('sha256').update(value).digest('hex');
const json = value => JSON.stringify(value, null, 2) + '\n';
const requireThat = (ok, message) => { if (!ok) throw new Error(message); };
const write = (path, value) => { writeFileSync(path + '.tmp', json(value)); renameSync(path + '.tmp', path); };
export const inventory = () => [COLLECTOR, TEST, ENGINE, PARITY, 'amen/runs/record-composer-v12/receipt.json',
  'amen/web/index.html', 'amen/web/models/index.json', `${MODEL}/model.json`, `${MODEL}/params.f64`,
  `${MODEL}/records_y.f32`, `${MODEL}/records_mean.f64`, 'amen/web/kit/kit.json', 'amen/web/kit/break.wav', 'amen/web/kit/bass.wav'];
export const settings = (mode, seed) => ({bars: 128, mode, seed, energy: 1, variation: mode === 'sample' ? 0.6 : 0, riffBars: 2, memory: false});
export const cases = () => ARMS.flatMap(arm => CHOICES.map(([mode, seed]) => ({id: `${arm}-${mode}-${seed}`, arm, mode, seed, options: settings(mode, seed)})));
export function diskBytes(root) {
  let total = 0;
  for (const entry of readdirSync(root, {withFileTypes: true})) {
    const path = join(root, entry.name);
    requireThat(!entry.isSymbolicLink(), `symlink in output: ${path}`);
    total += entry.isDirectory() ? diskBytes(path) : statSync(path).size;
  }
  return total;
}
const bytes = path => { const b = readFileSync(path); return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength); };
export async function load(root) {
  const module = await import(pathToFileURL(join(root, ENGINE)));
  const model = JSON.parse(readFileSync(join(root, MODEL, 'model.json')));
  return {...module, model, make: () => new module.Brain(model, bytes(join(root, MODEL, model.files.params)),
    bytes(join(root, MODEL, model.files.records_y)), bytes(join(root, MODEL, model.files.records_mean)))};
}
export function fixed(brain) {
  const h = createHash('sha256');
  for (const a of [...Object.values(brain.p), brain.y, brain.mean, brain.projection, brain.offset, brain.scale])
    h.update(new Uint8Array(a.buffer, a.byteOffset, a.byteLength));
  h.update(JSON.stringify([brain.seen, brain.inputNorm, brain.inputScale]));
  return h.digest('hex');
}
export function slowOutput(brain, context) {
  const {C, c} = brain.p, H = brain.hidden;
  return Array.from({length: brain.outputs}, (_, k) => {
    let value = c[k];
    for (let j = 0; j < H; j++) value += C[k * H + j] * context[j];
    return value;
  });
}
export function ablate(brain, arm) {
  requireThat(ARMS.includes(arm), 'unknown ablation');
  const original = brain.step.bind(brain), codeOf = brain.codeOf.bind(brain);
  const work = {steps: 0, context_resets: 0, context_updates: 0, record_codes: 0,
    record_cells_scored: 0, projection_coefficient_visits: 0, record_output_terms: 0,
    slow_output_terms: 0, extra_ablation_slow_terms: 0, address_instrumentation_checks: 0};
  brain.codeOf = reading => {
    work.record_codes++; work.record_cells_scored += brain.cells;
    for (let i = 0; i < brain.reading; i++) {
      work.address_instrumentation_checks++;
      if (reading[i] - brain.mean[i] !== 0) work.projection_coefficient_visits += brain.cells;
    }
    return codeOf(reading);
  };
  brain.step = inputs => {
    if (arm === 'context_reset' || arm === 'both') { brain.h.fill(0); work.context_resets++; }
    const result = original(inputs);
    work.steps++; work.context_updates += brain.hidden;
    work.record_output_terms += brain.active * brain.outputs;
    work.slow_output_terms += brain.hidden * brain.outputs;
    if (arm === 'no_record' || arm === 'both') {
      // Repeat the engine's identical C*h+c accumulation, then omit the final +read.
      // This avoids subtracting read from an already-rounded sum. The retrieved read
      // remains in the trace, and lookup, context, records and running mean are intact.
      result.out = slowOutput(brain, result.h);
      work.extra_ablation_slow_terms += brain.hidden * brain.outputs;
    }
    return result;
  };
  return work;
}
export function parityCheck(rows, parity, layout) {
  requireThat(rows.length >= parity.steps, 'missing parity prefix');
  let maximum = 0;
  for (let t = 0; t < parity.steps; t++) {
    const row = rows[t], event = row.played;
    const crop = event[layout.drum_on] > 0.5 ? event.slice(0, layout.crops).indexOf(1) : -1;
    const note = event[layout.bass_on] > 0.5 ? event.slice(layout.note_start, layout.note_start + layout.notes).indexOf(1) : -1;
    requireThat(crop === parity.played_crop[t] && note === parity.played_note[t]
      && Number(event[layout.change] > 0.5) === parity.played_change[t], `parity event mismatch ${t}`);
    requireThat(row.out.length === parity.outputs[t].length, 'parity output shape');
    row.out.forEach((v, k) => { requireThat(Number.isFinite(v), 'nonfinite parity output'); maximum = Math.max(maximum, Math.abs(v - parity.outputs[t][k])); });
  }
  requireThat(maximum <= 5e-8, `parity output difference ${maximum}`);
  return {steps: parity.steps, maximum_output_difference: maximum, exact_played_identities: true};
}
export function metrics(rows, L) {
  const block = selected => {
    let previous = null, onsets = 0, longest = 0, held = 0;
    const notes = new Set(), crops = new Set();
    for (const row of selected) {
      const e = row.played, note = e.slice(L.note_start, L.note_start + L.notes).indexOf(1);
      if (e[L.drum_on] > 0.5) crops.add(e.slice(0, L.crops).indexOf(1));
      if (e[L.bass_on] > 0.5) {
        notes.add(note);
        const continues = previous && previous[L.bass_on] > 0.5 && e[L.bass_hold] > 0.5
          && previous.slice(L.note_start, L.note_start + L.notes).indexOf(1) === note;
        if (!continues) { onsets++; held = 1; } else held++;
        longest = Math.max(longest, held);
      } else held = 0;
      previous = e;
    }
    const mean = fn => selected.reduce((s, r) => s + fn(r), 0) / selected.length;
    return {steps: selected.length, drum_on_fraction: mean(r => Number(r.played[L.drum_on] > 0.5)),
      bass_on_fraction: mean(r => Number(r.played[L.bass_on] > 0.5)),
      mean_drum_gain_including_rest: mean(r => r.played[L.drum_on] * r.played[L.drum_gain]),
      bass_onsets: onsets, longest_bass_command_hold: longest, unique_notes: notes.size,
      unique_crops: crops.size, pattern_returns: selected.filter(r => r.returned).length,
      change_fraction: mean(r => Number(r.played[L.change] > 0.5))};
  };
  requireThat(rows.length > 0, 'empty trajectory');
  return {whole: block(rows), startup_16_bars: block(rows.slice(0, 128)), tail_16_bars: block(rows.slice(-128)),
    bars: Array.from({length: Math.ceil(rows.length / 8)}, (_, b) => ({bar: b, ...block(rows.slice(b * 8, b * 8 + 8))})),
    scope: 'Command statistics only; hold lengths/onsets reset at each summary window. Positive bass_on does not imply an unexpired audible voice. No PCM or musical-quality assessment.'};
}
export function prepare(output, repo = REPO) {
  requireThat(!existsSync(output), 'output already exists');
  requireThat(sha(readFileSync(join(repo, ENGINE))) === PINNED_ENGINE, 'historical engine differs');
  const historical = JSON.parse(readFileSync(join(repo, 'amen/runs/record-composer-v12/receipt.json')));
  requireThat(historical.verified === true && historical.environment.library_commit === '02fec624648d421e02ecb00f52f3d3072e9fe9ae'
    && historical.results.run_receipt_sha256 === '3d922b65884a39dc247804032a9734480df96c6ed94124a7ffd3ac088a3c700c', 'historical checkpoint identity');
  for (const [name, hash] of Object.entries(historical.sources))
    requireThat(sha(readFileSync(join(repo, 'amen', name))) === hash, `historical asset changed: ${name}`);
  const pins = Object.fromEntries(inventory().map(name => [name, sha(readFileSync(join(repo, name)))]));
  const protocol = {schema: 'amen-legacy-ablation/1', cases: cases(), expected_steps: 20480,
    record_writes: false, training_calls: 0, sources: pins, node: process.version, node_binary_sha256: sha(readFileSync(process.execPath)),
    limits: {output_bytes: 80_000_000, total_seconds: 600, case_seconds: 60},
    intervention: {no_record: 'Omit additive retrieved record read; recompute C*h+c in original accumulation order. All record lookup work still runs; no table/mean mutation.',
      context_reset: 'Zero only the 128 persistent context values before every Brain.step, leaving executed-event history, clock/wake, records, RNG and opening-pattern controller unchanged.'},
    scope: 'Fixed-checkpoint component ablation, not Cadence0.60 learning or architecture impossibility. Same seeded policy; branch-dependent RNG consumption can diverge after output changes. No audio render, subjective quality or speed advantage claim.',
    work_scope: 'Algorithmic selected kernel counters plus wall time. Includes repeated slow-readout and address-count instrumentation; does not count every JS allocation, arithmetic operation, trace/hash/gzip operation or RNG draw. No speed comparison.'};
  mkdirSync(join(output, 'sources'), {recursive: true});
  for (const name of inventory()) { const dest = join(output, 'sources', name); mkdirSync(dirname(dest), {recursive: true}); writeFileSync(dest, readFileSync(join(repo, name))); }
  write(join(output, 'protocol.json'), protocol);
  const protocolSha = sha(readFileSync(join(output, 'protocol.json')));
  write(join(output, 'freeze.json'), {protocol_sha256: protocolSha, prepared_bytes: diskBytes(output)});
  requireThat(diskBytes(output) < protocol.limits.output_bytes, 'frozen sources exceed storage cap');
  return {protocol_sha256: protocolSha, cases: protocol.cases.length, bytes: diskBytes(output)};
}
export function bound(output) {
  const p = JSON.parse(readFileSync(join(output, 'protocol.json'))), freeze = JSON.parse(readFileSync(join(output, 'freeze.json')));
  requireThat(sha(readFileSync(join(output, 'protocol.json'))) === freeze.protocol_sha256, 'protocol changed');
  requireThat(JSON.stringify(p.cases) === JSON.stringify(cases()) && p.expected_steps === 20480, 'case census changed');
  requireThat(sha(readFileSync(fileURLToPath(import.meta.url))) === p.sources[COLLECTOR], 'collector changed');
  requireThat(p.node === process.version && p.node_binary_sha256 === sha(readFileSync(process.execPath)), 'Node runtime changed');
  for (const [name, hash] of Object.entries(p.sources)) requireThat(sha(readFileSync(join(output, 'sources', name))) === hash, `source changed: ${name}`);
  requireThat(p.sources[ENGINE] === PINNED_ENGINE, 'legacy engine pin changed');
  return p;
}
export async function run(output) {
  const p = bound(output), started = performance.now();
  requireThat(!existsSync(join(output, 'progress.json')), 'run already attempted; no retry');
  mkdirSync(join(output, 'cases'));
  const progress = p.cases.map(c => ({...c, status: 'not_started'}));
  write(join(output, 'progress.json'), progress);
  const engine = await load(join(output, 'sources'));
  const parity = JSON.parse(readFileSync(join(output, 'sources', PARITY)));
  let failure = null;
  for (const item of progress) {
    const caseStart = performance.now();
    let gzip, done, streamError = null;
    try {
      bound(output);
      requireThat((caseStart - started) / 1000 <= p.limits.total_seconds, 'total soft deadline');
      requireThat(diskBytes(output) < p.limits.output_bytes, 'storage cap');
      item.status = 'started'; write(join(output, 'progress.json'), progress);
      const brain = engine.make(), initial = fixed(brain), work = ablate(brain, item.arm), rows = [];
      const path = join(output, 'cases', item.id + '.jsonl.gz');
      gzip = createGzip({level: 6});
      done = pipeline(gzip, createWriteStream(path, {flags: 'wx'})).catch(e => { streamError = e; });
      let logicalBytes = 0;
      for (const step of engine.compose(brain, item.options)) {
        const row = {t: step.t, out: step.out, played: Array.from(step.played), heard: step.heard,
          returned: Boolean(step.played.returned), record_read: step.read,
          context_rms: Math.sqrt(step.h.reduce((s, v) => s + v * v, 0) / step.h.length),
          ...(step.t === 0 ? {signature: step.signature} : {})};
        requireThat(row.out.length === 71 && [...row.out, ...row.played, ...row.heard, ...row.record_read, row.context_rms].every(Number.isFinite), 'invalid numeric output');
        const line = JSON.stringify(row) + '\n'; logicalBytes += Buffer.byteLength(line); rows.push(row);
        if (!gzip.write(line)) await once(gzip, 'drain');
        requireThat(!streamError, 'journal write failed');
        item.returned_steps = rows.length;
        if (rows.length % 64 === 0) {
          write(join(output, 'progress.json'), progress);
          requireThat(diskBytes(output) < p.limits.output_bytes - 1_000_000, 'storage guard');
          requireThat((performance.now() - caseStart) / 1000 <= p.limits.case_seconds && (performance.now() - started) / 1000 <= p.limits.total_seconds, 'soft deadline');
        }
      }
      gzip.end(); await done; requireThat(!streamError, 'journal write failed');
      requireThat(rows.length === 1024 && fixed(brain) === initial, 'incomplete path or changed fixed model');
      const parityResult = item.arm === 'intact' && item.mode === 'argmax' ? parityCheck(rows, parity, engine.model.layout) : null;
      bound(output);
      Object.assign(item, {status: 'complete', fixed_before: initial, fixed_after: fixed(brain), work,
        journal_sha256: sha(readFileSync(path)), journal_bytes: statSync(path).size, logical_bytes: logicalBytes,
        metrics: metrics(rows, engine.model.layout), parity: parityResult});
    } catch (error) {
      if (gzip) gzip.destroy(); if (done) await done;
      Object.assign(item, {status: 'failed', error: String(error.stack || error), unknown_inflight_work: true});
      failure = item.error;
    }
    item.wall_seconds = (performance.now() - caseStart) / 1000;
    if (item.status === 'complete' && (item.wall_seconds > p.limits.case_seconds || (performance.now() - started) / 1000 > p.limits.total_seconds || diskBytes(output) >= p.limits.output_bytes)) {
      item.status = 'censored'; failure = 'post-case soft deadline/storage veto';
    }
    write(join(output, 'progress.json'), progress);
    process.stdout.write(JSON.stringify({id: item.id, status: item.status, steps: item.returned_steps || 0, seconds: item.wall_seconds}) + '\n');
    if (failure) break;
  }
  let sourceUnchanged = true;
  try { bound(output); } catch (e) { sourceUnchanged = false; failure = String(e); }
  const receipt = {schema: 'amen-legacy-ablation-result/1', protocol_sha256: sha(readFileSync(join(output, 'protocol.json'))),
    complete: sourceUnchanged && progress.length === 20 && progress.every(c => c.status === 'complete' && c.returned_steps === 1024),
    source_unchanged: sourceUnchanged, cases: progress, failure, wall_seconds: (performance.now() - started) / 1000,
    bytes_before_receipt: diskBytes(output), training_calls: 0, record_writes: 0, musical_quality_assessed: false, audio_rendered: false};
  write(join(output, 'receipt.json'), receipt);
  requireThat(diskBytes(output) <= p.limits.output_bytes, 'final storage limit');
  return {complete: receipt.complete, cases: progress.filter(c => c.status === 'complete').length,
    protocol_sha256: receipt.protocol_sha256, receipt_sha256: sha(readFileSync(join(output, 'receipt.json'))), bytes: diskBytes(output)};
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [command, output] = process.argv.slice(2);
  requireThat(['prepare', 'run'].includes(command) && output, 'usage: node fast-slow/amen_legacy_ablation.mjs prepare|run OUTPUT');
  const result = command === 'prepare' ? prepare(resolve(output)) : await run(resolve(output));
  process.stdout.write(JSON.stringify(result) + '\n');
  if (result.complete === false) process.exitCode = 1;
}
