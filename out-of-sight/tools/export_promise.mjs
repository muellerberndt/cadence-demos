// The page's promise scenario as scene files of the tracking chamber (cadence-tracking-scene/1).
//   node tools/export_promise.mjs
// The same stage, seed and route as `scenario` in site/app.js and `scripted` in
// tools/check_page.py: a person's hand crosses the room in view at 0.5 m/s, goes into the
// pillar's shadow at 0.5 m/s, rests there for 70 moments and comes back. Each file holds the
// hand alone (thing 0) with the page's geometry: the body in the room, the pillar of 0.10 m.
// Two scenes are written:
//   tests/fixtures/promise-scene.json                 the page's default scene: the arm folded
//                                                      along the near edge, light around the
//                                                      pillar's shadow
//   tests/fixtures/promise-merged-shadows-scene.json  the page's first scene: the arm's end
//                                                      under the pillar's shadow, so that the
//                                                      two shadows join
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { Stage, Random, DT, FORMAT, visible, MERGED_JOINTS, HOME, RECORDED_THINGS } from '../site/world.js';

const here = dirname(fileURLToPath(import.meta.url));

function record(joints, name, out) {
  const stage = new Stage({ home: { ...HOME, things: RECORDED_THINGS } }); // the stage the files were recorded on
  if (joints) stage.home.joints = joints.slice();
  stage.reset(); stage.random = new Random(320);
  const g = stage.geometry, o = g.occluders[0], eye = g.camera.position;
  const d = Math.hypot(o.center[0] - eye[0], o.center[1] - eye[1]);
  const shadow = [o.center[0] + ((o.center[0] - eye[0]) / d) * 0.32, o.center[1] + ((o.center[1] - eye[1]) / d) * 0.32];
  if (visible(g, shadow, stage.world.joints)) throw new Error('the point behind the pillar is in view');
  const cross = [[-0.3, 1.15], [-0.75, 1.2], [-0.45, 0.9], [-0.8, 1.3], [-0.2, 1.25], [-0.6, 1.0]];
  stage.route = [...cross.map((to) => ({ name: 'hand', to, speed: 0.5 })), { rest: 15 }, { name: 'hand', to: shadow, speed: 0.5 }, { rest: 70 },
    { name: 'hand', to: [-0.6, 1.0], speed: 0.5 }, { rest: 25 }];
  const scene = { format: FORMAT, units: { length: 'm', time: 's', angle: 'rad' }, dt: DT, case: 'other', kind: 'stop', event: -1, name,
    geometry: { plane: g.plane, camera: g.camera, ear: g.ear, occluders: g.occluders, arm: g.arm }, camera_noise: stage.world.cameraNoise,
    start: stage.world.things[0].slice(), report: [], in_view: [], commands: [], joints: [], truth: [] };
  let rested = false;
  while (stage.route.length) {
    const leg = stage.route[0];
    const r = stage.advance();
    if (!rested && leg.rest !== undefined && !r.in_view[0]) { scene.event = scene.truth.length; rested = true; } // the first moment at rest in the shadow
    scene.report.push(r.report[0]); scene.in_view.push(r.in_view[0]); scene.commands.push(r.commands); scene.joints.push(r.joints); scene.truth.push(r.truth[0]);
  }
  writeFileSync(out, JSON.stringify(scene) + '\n');
  console.log(JSON.stringify({ wrote: out, steps: scene.truth.length, out_of_view: scene.in_view.filter((v) => !v).length, rest_begins: scene.event, shadow, arm_rest: stage.home.joints }));
}

record(null, "the page's promise: into the pillar's shadow at 0.5 m/s, 70 moments at rest there, and back (the arm folded along the near edge)",
  resolve(here, '../tests/fixtures/promise-scene.json'));
record(MERGED_JOINTS, "the page's promise in its first scene: the arm's end under the pillar's shadow, the two shadows joined",
  resolve(here, '../tests/fixtures/promise-merged-shadows-scene.json'));
