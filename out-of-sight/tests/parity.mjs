// Parity of site/world.js with the tracking chamber's Python world, on steps it recorded.
//   node tests/parity.mjs [tests/fixtures/steps.json]
// Every scripted run is replayed with the same commands, moves, sounds and standard normal
// draws, one step() call a step; the record of every step is compared number by number: the
// true positions, the in-view flags, the camera's reports, the ear's cues, the joint readings.
// Then the helpers on sampled inputs, the camera's view over the whole plane, and scene files:
// the page's reader beside the Python world's own, and the stage's replay of every file.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { LastSeen, Kalman } from '../site/controls.js';
import { makeWorld, step, visible, smooth, pointSegment, segments, polar, cartesian, readScene, unseenSteps, Stage, HOME, RECORDED_THINGS } from '../site/world.js';

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
// scene files: the page's reader beside the Python world's own, and the stage's replay of each
for (const entry of data.files || []) {
  const want = entry.read, scene = readScene(entry.file);
  const worst = { truth: gap(scene.truth, want.truth), report: gap(scene.report, want.report), commands: gap(scene.commands, want.commands),
    joints: gap(scene.joints, want.joints), start: gap(scene.start, want.start), cue: gap(scene.cue || want.cue.map((row) => row.map(() => null)), want.cue) };
  let flags = 0, since = 0;
  const unseen = unseenSteps(scene);
  scene.in_view.forEach((row, t) => row.forEach((v, k) => { if (v !== want.in_view[t][k]) flags += 1; if (unseen[t][k] !== want.unseen[t][k]) since += 1; }));
  const same = scene.steps === want.steps && scene.things === want.things && scene.case === want.case && Math.abs(scene.dt - want.dt) < 1e-15
    && scene.kind === want.kind && scene.event === want.event && gap(scene.what, want.what) === 0
    && gap(scene.geometry.arm.base, want.geometry.arm.base) === 0 && gap(scene.geometry.arm.lengths, want.geometry.arm.lengths) === 0
    && gap(scene.geometry.arm.limits, want.geometry.arm.limits) === 0 && scene.geometry.arm.width === want.geometry.arm.width
    && gap(scene.geometry.occluders.map((o) => [...o.center, o.radius]), want.geometry.occluders.map((o) => [...o.center, o.radius])) === 0
    && gap(scene.geometry.plane, want.geometry.plane) === 0 && gap(scene.geometry.camera.position, want.geometry.camera.position) === 0
    && scene.geometry.camera.fov === want.geometry.camera.fov && scene.geometry.camera.heading === want.geometry.camera.heading
    && scene.geometry.camera.range === want.geometry.camera.range && gap(scene.geometry.ear, want.geometry.ear) === 0;
  // the stage replays the file: every step's record holds the file's own rows
  const stage = new Stage({ home: { ...HOME, things: RECORDED_THINGS } }); // room for every thing of a file of four
  stage.play(scene);
  let replay = 0;
  for (let t = 0; t < scene.steps; t++) {
    const record = stage.advance(), n = Math.min(scene.things, record.truth.length);
    replay = Math.max(replay, gap(record.truth.slice(0, n), scene.truth[t].slice(0, n)), gap(record.report.slice(0, n), scene.report[t].slice(0, n)),
      gap(record.joints, scene.joints[t]), gap(record.commands, scene.commands[t]));
    for (let k = 0; k < n; k++) if (record.in_view[k] !== scene.in_view[t][k]) replay = Infinity;
  }
  const ok = same && flags === 0 && since === 0 && replay < TOLERANCE && Object.values(worst).every((v) => v < TOLERANCE);
  failed ||= !ok;
  console.log(JSON.stringify({ file: entry.name, steps: scene.steps, things: scene.things, case: scene.case, fields_same: same,
    in_view_mismatches: flags, unseen_mismatches: since, worst, replay_worst: replay, ok }));
}
// the controls beside the brain: the last seen position and the constant-velocity Kalman filter
for (const entry of data.controls || []) {
  const scene = readScene(entry.file);
  const last = new LastSeen(scene.start[0]), kalman = new Kalman(scene.start[0], entry.settings);
  const worst = { last_seen: 0, kalman: 0, kalman_radius: 0 };
  for (let t = 0; t < scene.steps; t++) {
    worst.last_seen = Math.max(worst.last_seen, gap(last.step(scene.report[t][0]), entry.last_seen[t]));
    worst.kalman = Math.max(worst.kalman, gap(kalman.step(scene.report[t][0]), entry.kalman[t]));
    worst.kalman_radius = Math.max(worst.kalman_radius, Math.abs(kalman.radius - entry.kalman_radius[t]));
  }
  const ok = Object.values(worst).every((v) => v < TOLERANCE);
  failed ||= !ok;
  console.log(JSON.stringify({ controls: scene.kind, steps: scene.steps, out_of_view: scene.in_view.filter((r) => !r[0]).length, worst, ok }));
}
console.log(JSON.stringify({ world_sha256: data.world_sha256, source: data.source, runs: data.runs.length, files: (data.files || []).length, controls: (data.controls || []).length, tolerance: TOLERANCE, passed: !failed }));
process.exit(failed ? 1 : 0);
