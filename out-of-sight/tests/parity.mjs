// Parity of site/world.js with the tracking chamber's Python world, on steps it recorded.
//   node tests/parity.mjs [tests/fixtures/steps.json]
// Every scripted run is replayed with the same commands, moves, sounds and standard normal
// draws, one step() call a step; the record of every step is compared number by number: the
// true positions, the in-view flags, the camera's reports, the ear's cues, the joint readings.
// Then the helpers on sampled inputs, and the camera's view over the whole plane.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { makeWorld, step, visible, smooth, pointSegment, segments, polar, cartesian } from '../site/world.js';

const here = dirname(fileURLToPath(import.meta.url));
const path = process.argv[2] || resolve(here, 'fixtures/steps.json');
const data = JSON.parse(readFileSync(path, 'utf8'));
const TOLERANCE = 1e-12;
let failed = false;
const gap = (a, b) => {
  if (a === null || b === null) return a === b ? 0 : Infinity;
  return a.reduce((m, v, i) => Math.max(m, Array.isArray(v) || v === null ? gap(v, b[i]) : Math.abs(v - b[i])), 0);
};
for (const run of data.runs) {
  const world = makeWorld({ geometry: run.geometry, joints: run.start.joints, things: run.start.things, own: run.start.own,
    noise: run.noise });
  const worst = { truth: 0, report: 0, cue: 0, joints: 0, commands: 0 };
  let flags = 0, outOfView = 0, heard = 0;
  for (const row of run.steps) {
    const record = step(world, row.command, row.moves, row.sounds, row.noise);
    for (const name of Object.keys(worst)) worst[name] = Math.max(worst[name], gap(record[name], row.record[name]));
    record.in_view.forEach((v, k) => { if (v !== row.record.in_view[k]) flags += 1; if (!v) outOfView += 1; });
    heard += record.cue.filter((c) => c !== null).length;
  }
  const ok = flags === 0 && Object.values(worst).every((v) => v < TOLERANCE);
  failed ||= !ok;
  console.log(JSON.stringify({ run: run.name, steps: run.steps.length, things: run.start.things.length, own: run.start.own,
    out_of_view_readings: outOfView, cues: heard, in_view_mismatches: flags, worst, ok }));
}
const h = data.helpers;
const worst = { smooth: 0, point_segment: 0, segments: 0, polar: 0, cartesian: 0, view_mismatches: 0 };
h.smooth.fraction.forEach((f, i) => { worst.smooth = Math.max(worst.smooth, Math.abs(smooth(f) - h.smooth.value[i])); });
h.point_segment.points.forEach((p, i) => { worst.point_segment = Math.max(worst.point_segment, Math.abs(pointSegment(p[0], p[1], p[2]) - h.point_segment.value[i])); });
h.segments.points.forEach((p, i) => { worst.segments = Math.max(worst.segments, Math.abs(segments(p[0], p[1], p[2], p[3]) - h.segments.value[i])); });
h.polar.points.forEach((p, i) => { worst.polar = Math.max(worst.polar, gap(polar(h.view.geometry, p), h.polar.value[i])); });
h.cartesian.cues.forEach((c, i) => { worst.cartesian = Math.max(worst.cartesian, gap(cartesian(h.view.geometry, c), h.cartesian.value[i])); });
let viewPoints = 0, lit = 0;
for (const v of h.view.views) {
  h.view.points.forEach((p, i) => { viewPoints += 1; lit += v.visible[i] ? 1 : 0; if (visible(h.view.geometry, p, v.pose) !== v.visible[i]) worst.view_mismatches += 1; });
}
const helpersOk = worst.view_mismatches === 0 && ['smooth', 'point_segment', 'segments', 'polar', 'cartesian'].every((k) => worst[k] < TOLERANCE);
failed ||= !helpersOk;
console.log(JSON.stringify({ helpers: worst, view_points: viewPoints, view_points_lit: lit, ok: helpersOk }));
console.log(JSON.stringify({ world_sha256: data.world_sha256, source: data.source, runs: data.runs.length, tolerance: TOLERANCE, passed: !failed }));
process.exit(failed ? 1 : 0);
