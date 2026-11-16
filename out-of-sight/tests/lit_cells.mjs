// Which of the map's cells the camera sees at each step of a scene file, by the page's own rule
// (`visible` of site/world.js, the rule the worker gives the map at every moment).
//   node tests/lit_cells.mjs SCENE.json CENTERS.json   ->   one line of 0s and 1s a step
import { readFileSync } from 'node:fs';
import { readScene, visible, forward } from '../site/world.js';

const scene = readScene(JSON.parse(readFileSync(process.argv[2], 'utf8')));
const centers = JSON.parse(readFileSync(process.argv[3], 'utf8'));
const out = [];
for (let t = 0; t < scene.steps; t++) {
  const chain = forward(scene.geometry, scene.joints[t]);
  out.push(centers.map((p) => (visible(scene.geometry, p, scene.joints[t], false, chain) ? '1' : '0')).join(''));
}
process.stdout.write(out.join('\n') + '\n');
