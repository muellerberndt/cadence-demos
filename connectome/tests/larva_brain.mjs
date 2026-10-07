// The compiled larva brain in the browser engine, through the dictionary: eye light reaches
// the band on the lit side more, a tap arrests the cilia and raises the parapodia, no ignition.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { SettlingBrain } from "../web/brain.js";
import { stimuli, commands, READOUTS } from "../web/larva_dictionary.js";
const here = dirname(fileURLToPath(import.meta.url));
globalThis.atob ??= (b) => Buffer.from(b, "base64").toString("binary");
const payload = JSON.parse(readFileSync(join(here, "..", "web", "data", "larva_brain.json"), "utf8"));
const brain = new SettlingBrain(payload);
const read = () => { const r = {}; for (const k of READOUTS) if (payload.populations[k]) r[k] = brain.mean(k); return r; };
function run(senses, steps = 150) { brain.reset(); brain.clearStimuli(); for (const [pop, level] of Object.entries(stimuli(senses))) brain.stimulate(pop, level); for (let i = 0; i < steps; i++) brain.step(); return read(); }
const dark = commands(run({}));
const left = run({ eye_left: 1, eyespot_left: 1 }); const right = run({ eye_right: 1, eyespot_right: 1 });
const cl = commands(left), cr = commands(right);
console.log(`dark: cilia ${dark.ciliaLeft.toFixed(3)}/${dark.ciliaRight.toFixed(3)} arrest ${dark.arrest.toFixed(3)} | left light: band L ${left["prototroch:left"].toFixed(4)} R ${left["prototroch:right"].toFixed(4)} -> cilia ${cl.ciliaLeft.toFixed(3)}/${cl.ciliaRight.toFixed(3)} | right light: band L ${right["prototroch:left"].toFixed(4)} R ${right["prototroch:right"].toFixed(4)} -> cilia ${cr.ciliaLeft.toFixed(3)}/${cr.ciliaRight.toFixed(3)}`);
if (!(left["prototroch:left"] > left["prototroch:right"] && right["prototroch:right"] > right["prototroch:left"])) { console.error("eye light should reach the lit side of the band more"); process.exit(1); }
const tap = run({ mechanical: 1 }); const ct = commands(tap);
console.log(`tap: MC ${tap.MC.toFixed(3)} Ser-h1 ${(tap["Ser-h1"] || 0).toFixed(3)} MUSlong ${tap["MUSlong:left"].toFixed(4)}/${tap["MUSlong:right"].toFixed(4)} parapodial ${tap.parapodial.toFixed(4)} -> arrest ${ct.arrest.toFixed(3)} parapodia ${ct.parapodia.toFixed(3)} cilia ${ct.ciliaLeft.toFixed(3)}`);
if (!(ct.arrest > 0.3 && ct.parapodia > 0.01)) { console.error("a tap should arrest the cilia and raise the parapodia"); process.exit(1); }
let hot = 0; for (const a of brain.s) if (a >= 0.5) hot++; console.log(`active cells at or above 0.5 under a tap: ${hot} of ${brain.n}`);
if (hot / brain.n > 0.2) { console.error("ignition"); process.exit(1); }
console.log("larva brain ok");
