// The larva's body in node, without three.js.
//   node tests/body.mjs
// A scoot moves the fish forward at a peak inside its range; the drag stops it (below 0.5 mm/s
// within 0.6 s of the bout's end); a C-start turns at least 90 degrees within 30 ms of the
// command; the glass holds the fish over 10,000 steps of random commands; the instincts bout
// between 0.3 and 1.5 times a second over 60 s; the senses stay in [0, 1] and point the right
// way; the instincts escape a tap and turn toward prey.
import { Body, Instincts, TANK, WATER, DT, BOUTS, mulberry32, wrap, DEG } from "../web/body.js";
import { sense, SENSE_NAMES, TAP_DECAY } from "../web/senses.js";

let failures = 0;
const fail = (msg) => { failures++; console.log("FAIL " + msg); };
const ok = (msg) => console.log("ok   " + msg);
const check = (cond, msg) => (cond ? ok(msg) : fail(msg));
const inside = (p) => p[0] >= 0 && p[0] <= TANK[0] && p[1] >= 0 && p[1] <= TANK[1] && p[2] >= 0 && p[2] <= WATER;
const QUIET = { prey: [], tapSide: 0, tapAge: 0, stripes: { on: false, direction: 1, speed: 0 }, light: { on: false, x: 10, y: 5, z: 13 } };

// -- a scoot moves the fish forward -----------------------------------------------------------
{
  const b = new Body(1, [10, 5, 5], 0);
  const started = b.command({ type: "scoot", direction: 0, vigour: 0.6 });
  let peak = 0;
  for (let k = 0; k < 300; k++) { b.step(DT); peak = Math.max(peak, b.state().speed); }
  const s = b.state(), dx = s.position[0] - 10, dy = s.position[1] - 5;
  check(started && dx > 0.5 && Math.abs(dy) < 0.05, `scoot    ${dx.toFixed(2)} mm forward in 300 ms, ${Math.abs(dy).toFixed(3)} mm sideways`);
  check(peak >= BOUTS.scoot.peak[0] && peak <= BOUTS.scoot.peak[1] * 1.1, `scoot    peak ${peak.toFixed(1)} mm/s, inside ${BOUTS.scoot.peak[0]} to ${BOUTS.scoot.peak[1]} mm/s`);
}

// -- the drag stops the glide -----------------------------------------------------------------
{
  const b = new Body(2, [6, 5, 5], 0);
  b.command({ type: "scoot", direction: 0, vigour: 1 });
  let guard = 0;
  while (b.state().busy && guard++ < 1000) b.step(DT);
  const end = b.state();
  let stopped = null;
  for (let k = 0; k < 600; k++) {
    b.step(DT);
    if (stopped === null && b.state().speed < 0.5) stopped = (k + 1) * DT;
  }
  const s = b.state();
  check(end.speed > 5 && s.speed < 0.5, `glide    ${end.speed.toFixed(1)} mm/s at the bout's end, ${s.speed.toFixed(2)} mm/s 0.6 s later${stopped !== null ? `, below 0.5 mm/s after ${(stopped * 1e3).toFixed(0)} ms` : ""}`);
  check(stopped !== null && stopped <= 0.5, `glide    stopped within 0.5 s`);
}

// -- the C-start turns within 30 ms -----------------------------------------------------------
for (const [direction, want] of [[1, 180], [-0.5, 135]]) {
  const b = new Body(3, [10, 5, 5], 0.3);
  const h0 = b.state().heading;
  b.command({ type: "cstart", direction, vigour: 1 });
  let turnedAt = null, peak = 0;
  for (let k = 0; k < 30; k++) {
    b.step(DT);
    const s = b.state();
    peak = Math.max(peak, s.speed);
    const turned = Math.abs(wrap(s.heading - h0)) / DEG;
    if (turnedAt === null && turned >= 90) turnedAt = (k + 1) * DT;
  }
  const turned = wrap(b.state().heading - h0) / DEG;
  check(turnedAt !== null && Math.sign(turned) === Math.sign(direction) && Math.abs(Math.abs(turned) - want) < 5, `C-start  direction ${direction}: ${turned.toFixed(0)} degrees, 90 reached at ${(turnedAt * 1e3).toFixed(0)} ms`);
  for (let k = 0; k < 200; k++) { b.step(DT); peak = Math.max(peak, b.state().speed); }
  check(peak >= 60 && peak <= 110, `C-start  peak ${peak.toFixed(0)} mm/s`);
}

// -- the glass holds the fish under random commands -------------------------------------------
{
  const b = new Body(7, [3, 2, 1], 2.0), rng = mulberry32(99), types = ["scoot", "turn", "jturn", "cstart", "rest"];
  let outside = 0, issued = 0, startles = 0, lastStartled = -Infinity;
  for (let k = 0; k < 10000; k++) {
    if (b.command({ type: types[Math.floor(rng() * types.length)], direction: 2 * rng() - 1, vigour: rng(), climb: 2 * rng() - 1 })) issued++;
    b.step(1 / 60);
    const s = b.state();
    if (!inside(s.position)) outside++;
    if (s.startled !== lastStartled) { startles++; lastStartled = s.startled; }
    for (const x of [...s.position, ...s.velocity, s.heading, s.pitch, s.roll, ...s.senses.angularVelocity, ...s.senses.acceleration]) if (!Number.isFinite(x)) throw new Error(`state is not finite at step ${k}`);
  }
  check(outside === 0, `walls    inside the tank for 10,000 steps (${issued} bouts commanded, ${startles} startles at the glass)`);
}

// -- the instincts bout at a plausible rate ---------------------------------------------------
{
  const b = new Body(5), pilot = new Instincts(5), dt = 1 / 60, seconds = 60;
  const mix = {}; let last = 0, inWater = true;
  for (let k = 0; k < seconds / dt; k++) {
    pilot.drive(b, QUIET, dt);
    b.step(dt);
    const s = b.state();
    if (s.bouts !== last) { last = s.bouts; mix[s.lastBout.type] = (mix[s.lastBout.type] || 0) + 1; }
    if (!inside(s.position)) inWater = false;
  }
  const rate = last / seconds;
  check(rate >= 0.3 && rate <= 1.5 && inWater, `pilot    ${rate.toFixed(2)} bouts per second over ${seconds} s: ${Object.entries(mix).map(([t, n]) => `${n} ${t}`).join(", ")}`);
}

// -- the senses -------------------------------------------------------------------------------
{
  const b = new Body(11, [10, 5, 5], 0);
  const s0 = b.state();
  const quiet = sense(s0, QUIET);
  check(SENSE_NAMES.length === 11 && SENSE_NAMES.every((n) => n in quiet) && Object.keys(quiet).length === 11, `senses   ${SENSE_NAMES.length} named populations`);
  check(Object.values(quiet).every((v) => v === 0), "senses   all zero for a still fish in a quiet tank");
  const world = { prey: [{ x: 11.5, y: 6.5, z: 5 }], tapSide: -1, tapAge: 0, stripes: { on: true, direction: 1, speed: 5 }, light: { on: true, x: 10, y: 9, z: 7 } };
  const loud = sense(s0, world);
  check(Object.values(loud).every((v) => v >= 0 && v <= 1), "senses   every level inside [0, 1]");
  check(loud.prey_left > loud.prey_right && loud.prey_left > 0.3, `senses   prey ahead-left: left ${loud.prey_left.toFixed(2)}, right ${loud.prey_right.toFixed(2)}`);
  check(loud.optic_flow_left === loud.optic_flow_right && loud.optic_flow_left > 0.3, `senses   stripes moving ahead: both ${loud.optic_flow_left.toFixed(2)}`);
  check(loud.light_left > loud.light_right, `senses   lamp to the left: left ${loud.light_left.toFixed(2)}, right ${loud.light_right.toFixed(2)}`);
  check(loud.acoustic > 0.99 && loud.lateral_line_left < loud.lateral_line_right, `senses   tap behind, from the right: acoustic ${loud.acoustic.toFixed(2)}, lateral line ${loud.lateral_line_left.toFixed(2)} / ${loud.lateral_line_right.toFixed(2)}`);
  const later = sense(s0, { ...world, tapAge: 0.2 });
  check(later.acoustic < 0.1, `senses   the tap decays to ${later.acoustic.toFixed(3)} by 200 ms (tau ${TAP_DECAY} s)`);
  b.command({ type: "turn", direction: 1, vigour: 0.5 });
  for (let k = 0; k < 60; k++) b.step(DT);
  const turning = sense(b.state(), QUIET);
  check(turning.vestibular_left > 0.2 && turning.vestibular_right === 0, `senses   turning left: vestibular ${turning.vestibular_left.toFixed(2)} / ${turning.vestibular_right.toFixed(2)}`);
  const stripesLeft = sense(s0, { ...QUIET, stripes: { on: true, direction: -1, speed: 5 } });
  const s90 = { ...s0, heading: -Math.PI / 2 };
  const flowLeft = sense(s90, { ...QUIET, stripes: { on: true, direction: 1, speed: 5 } });
  check(stripesLeft.optic_flow_left === 0 && stripesLeft.optic_flow_right === 0 && flowLeft.optic_flow_left > flowLeft.optic_flow_right, "senses   stripes toward the tail drive nothing, stripes to the left drive the left");
}

// -- the instincts answer a tap and prey -------------------------------------------------------
{
  const b = new Body(13, [10, 5, 5], Math.PI), pilot = new Instincts(13);
  const world = { ...QUIET, tapSide: -1, tapAge: 0 };
  const d = pilot.drive(b, world, 1 / 60);
  const h0 = b.state().heading;
  for (let k = 0; k < 50; k++) b.step(DT);
  const turned = Math.abs(wrap(b.state().heading - h0)) / DEG;
  for (let k = 0; k < 500; k++) b.step(DT);
  check(d.command?.type === "cstart" && d.issued && turned >= 90 && b.state().position[0] > 10.5, `tap      escape: ${turned.toFixed(0)} degrees in 50 ms, then ${(b.state().position[0] - 10).toFixed(1)} mm away from the tapped pane`);
  const c = new Body(17, [10, 5, 5], 0), hunter = new Instincts(17);
  const prey = { prey: [{ x: 11.5, y: 6.3, z: 5 }] };
  let first = null;
  for (let k = 0; k < 120 && !first; k++) { const r = hunter.drive(c, { ...QUIET, ...prey }, 1 / 60); if (r.command) first = r; c.step(1 / 60); }
  check(first?.command?.type === "jturn" && first.command.direction > 0 && first.eyes.left === 30, `prey     J-turn toward prey at 40 degrees left: direction ${first?.command?.direction?.toFixed(2)}, eyes converged`);
}

if (failures) { console.log(`${failures} failure(s)`); process.exit(1); }
console.log("all passed");
