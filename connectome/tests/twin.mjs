// The twin: a saccadic burst to one half holds a level on that half only; a vestibular push lowers it.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { TwinBrain } from "../web/twin.js";
const here = dirname(fileURLToPath(import.meta.url));
globalThis.atob ??= (b) => Buffer.from(b, "base64").toString("binary");
const payload = JSON.parse(readFileSync(join(here, "..", "web", "data", "brain.json"), "utf8"));
const twin = new TwinBrain(payload);
let s = twin.run({ left: { _Int_: 0.03 } }, 20);
s = twin.run({}, 200);
const heldL = s.sides.left.readouts._Int_, heldR = s.sides.right.readouts._Int_;
console.log(`after a left burst: left integrator ${heldL.toFixed(4)}, right ${heldR.toFixed(4)}, left ABD_m ${s.sides.left.readouts.ABD_m.toFixed(4)} ABD_i ${s.sides.left.readouts.ABD_i.toFixed(4)}`);
if (!(heldL > 1e-3 && heldR === 0)) { console.error("the left half should hold and the right stay at rest"); process.exit(1); }
const s600 = twin.run({}, 400).sides.left.readouts._Int_;
console.log(`held at +600: ${s600.toFixed(4)} (ratio to +200 ${(s600 / heldL).toFixed(2)})`);
if (!(s600 > 0.25 * heldL)) { console.error("the hold decayed too fast"); process.exit(1); }
twin.reset(); twin.run({ left: { _Int_: 0.03 } }, 20); const und = twin.run({}, 300).sides.left.readouts._Int_;
twin.reset(); twin.run({ left: { _Int_: 0.03 } }, 20); twin.run({ left: { _DOs_: 0.03 } }, 100); const pushed = twin.run({}, 200).sides.left.readouts._Int_;
console.log(`vestibular push: undisturbed ${und.toFixed(4)}, pushed ${pushed.toFixed(4)}`);
if (!(pushed < 0.9 * und)) { console.error("the Ve2 push should lower the hold"); process.exit(1); }
console.log("twin ok");
