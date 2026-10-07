// The larva with its compiled connectome in the loop: a lamp on one side bends the course
// consistently, a tap arrests the cilia and sinks the body, sixty seconds pass with no ignition.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { SettlingBrain } from "../web/brain.js";
import { LarvaLife } from "../web/larva_life.js";
const here = dirname(fileURLToPath(import.meta.url));
globalThis.atob ??= (b) => Buffer.from(b, "base64").toString("binary");
const payload = JSON.parse(readFileSync(join(here, "..", "web", "data", "larva_brain.json"), "utf8"));
const brain = new SettlingBrain(payload);
const dt = 0.01;
function headingChange(lightSide, seconds = 1.5) {
  brain.reset(); brain.clearStimuli();
  const life = new LarvaLife(brain, 3, [4, 5, 4], 0);  // heading along +x, 16 mm of tank ahead
  life.setLight({ on: true, x: 4 + 0.001, y: 5 + lightSide * 4.5, z: 6 });  // a lamp beside the larva, one side or the other
  const h0 = life.body.state().heading; let eyeL = 0, eyeR = 0, n = 0;
  for (let t = 0; t < seconds; t += dt) { life.step(dt); if (life.senses) { eyeL += life.senses.eye_left; eyeR += life.senses.eye_right; n++; } }
  const h1 = life.body.state().heading; let d = h1 - h0; while (d > Math.PI) d -= 2 * Math.PI; while (d < -Math.PI) d += 2 * Math.PI;
  return { turn: d * 180 / Math.PI, eyeL: eyeL / n, eyeR: eyeR / n, ciliaL: life.command.ciliaLeft, ciliaR: life.command.ciliaRight, muscleL: life.command.muscleLeft, muscleR: life.command.muscleRight };
}
const L = headingChange(+1), R = headingChange(-1);
console.log(`lamp left: eyes ${L.eyeL.toFixed(2)}/${L.eyeR.toFixed(2)} cilia ${L.ciliaL.toFixed(4)}/${L.ciliaR.toFixed(4)} muscles ${L.muscleL.toFixed(4)}/${L.muscleR.toFixed(4)} turn ${L.turn.toFixed(1)}° | lamp right: eyes ${R.eyeL.toFixed(2)}/${R.eyeR.toFixed(2)} cilia ${R.ciliaL.toFixed(4)}/${R.ciliaR.toFixed(4)} muscles ${R.muscleL.toFixed(4)}/${R.muscleR.toFixed(4)} turn ${R.turn.toFixed(1)}°`);
const litL = L.eyeL > L.eyeR ? "left" : "right", litR = R.eyeL > R.eyeR ? "left" : "right";
if (!(litL !== litR && Math.sign(L.turn) === -Math.sign(R.turn) && Math.abs(L.turn) > 1 && Math.abs(R.turn) > 1)) { console.error("a lamp on one side should bend the course consistently, mirrored for the other side"); process.exit(1); }
brain.reset(); brain.clearStimuli();
const life = new LarvaLife(brain, 5, [10, 5, 5], 0.5);
for (let t = 0; t < 2; t += dt) life.step(dt);
const z0 = life.body.state().position[2]; life.tap(-1);
let maxArrest = 0; for (let t = 0; t < 1; t += dt) { life.step(dt); maxArrest = Math.max(maxArrest, life.command.arrest); }
const z1 = life.body.state().position[2];
console.log(`tap: peak arrest ${maxArrest.toFixed(3)}, depth change ${(z1 - z0).toFixed(3)} mm in 1 s, swim speed now ${life.body.state().swim.toFixed(2)} mm/s`);
if (!(maxArrest > 0.3 && z1 < z0)) { console.error("a tap should arrest the cilia and sink the larva"); process.exit(1); }
let hot = 0, arrested = 0, samples = 0;
for (let t = 0; t < 60; t += dt) { life.step(dt); if (life.clock < dt * 1000) { let n = 0; for (const a of brain.s) if (a >= 0.5) n++; if (n / brain.n > 0.2) hot++; samples++; if (life.command.arrest > 0.5) arrested++; } }
const st = life.body.state(); console.log(`60 s of life: ${life.steps} brain steps, position ${st.position.map((x) => x.toFixed(1)).join(",")}, ignitions ${hot}, arrested ${(100 * arrested / samples).toFixed(0)} % of steps, on the floor ${st.onFloor}`);
if (hot > 0 || st.onFloor || arrested / samples > 0.3) { console.error("the larva should keep swimming: no ignition, not on the floor, arrested less than a third of the time"); process.exit(1); }
console.log("larva life ok");
