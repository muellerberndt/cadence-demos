// The closed loop without three.js: the body under the pilot, the compiled twin brain fed by
// the dictionary, the eyes from the brain. Checks: a saccade holds and decays slowly, a turn
// pushes the gaze against it, nothing ignites.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { TwinBrain } from "../web/twin.js";
import { stimuli, gaze, eyeAngles, Saccades, STEP_MS } from "../web/dictionary.js";
const here = dirname(fileURLToPath(import.meta.url));
globalThis.atob ??= (b) => Buffer.from(b, "base64").toString("binary");
const payload = JSON.parse(readFileSync(join(here, "..", "web", "data", "brain.json"), "utf8"));
const twin = new TwinBrain(payload);

// 1. one leftward saccade in a still fish: the gaze rises, then decays slowly
let s = twin.run(stimuli({ saccade: 1 }), 5);
const g0 = gaze(s.sides, 1); s = twin.run({}, 50); const g2 = gaze(s.sides); s = twin.run({}, 250); const g12 = gaze(s.sides);
console.log(`saccade: gaze after the burst ${g0.toFixed(1)}°, +2 s ${g2.toFixed(1)}°, +12 s ${g12.toFixed(1)}° (ratio ${(g12 / Math.max(g2, 1e-9)).toFixed(2)})`);
if (!(g2 > 3 && g12 > 0.4 * g2)) { console.error("the gaze should hold at least 3 degrees and keep 40 percent over ten seconds"); process.exit(1); }
const act = Float32Array.from(twin.activity("left")); let hot = 0; for (const a of act) if (a >= 0.5) hot++;
if (hot / act.length > 0.05) { console.error(`ignition: ${hot} of ${act.length} neurons at or above 0.5`); process.exit(1); }

// 2. a left turn pushes the gaze rightward (the vestibulo-ocular direction)
twin.reset(); twin.run(stimuli({ saccade: 1 }), 5); twin.run({}, 25); const before = gaze(twin.run({}, 1).sides);
twin.run(stimuli({ yawRate: 6 }), 10); const after = gaze(twin.run({}, 1).sides);
console.log(`left turn at 6 rad/s for 0.4 s: gaze ${before.toFixed(1)}° -> ${after.toFixed(1)}°`);
if (!(after < 0.9 * before)) { console.error("a left turn should lower a leftward gaze"); process.exit(1); }

// 3. sixty seconds of life through the Life module: the pilot swims, the brain runs at one step per 40 ms
twin.reset();
const { Life } = await import("../web/life.js");
const life = new Life(twin, 7); life.world.prey = [{ x: 12, y: 6, z: 4 }];
let maxGaze = 0, ignitions = 0; const dt = 0.01;
for (let t = 0; t < 60; t += dt) {
  life.step(dt); maxGaze = Math.max(maxGaze, Math.abs(life.gaze));
  if (life.clock < dt * 1000) { const a = twin.activity("left"); let n = 0; for (const x of a) if (x >= 0.5) n++; if (n / a.length > 0.05) ignitions++; }
}
console.log(`life: ${life.steps} brain steps in 60 s, ${life.saccades.count} saccades, ${life.body.state().bouts} bouts, peak |gaze| ${maxGaze.toFixed(1)}°, ignitions ${ignitions}`);
if (ignitions > 0 || life.saccades.count < 4 || maxGaze < 3) { console.error("the life loop should saccade several times, hold a gaze and never ignite"); process.exit(1); }
console.log("life ok");
