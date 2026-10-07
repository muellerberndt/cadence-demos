// The Platynereis larva's body in node, without three.js.
//   node tests/larva.mjs
// With both cilia at 1 the larva covers the scaled speed, forward along a helix about its
// course; a left-right ciliary difference turns the course toward the stronger side at every
// step, a one-sided muscle contraction toward the contracted side; an arrest stops it within one
// step and it sinks at the scaled sinking speed, a contraction sinks it too; a tap's pulse is
// below 0.05 within 200 ms; a lamp to the left lights the left eye and not the right, the
// eyespots see wider, the cPRC answers the ultraviolet near the surface; the glass holds the
// larva over 10,000 random steps; the pilot startles at a tap, turns toward the lamp and lives
// 60 s in the tank.
import { LarvaBody, LarvaPilot, SPEED, SINK, SCALE, TURN, TURN_MUSCLE, ROLL, HELIX_ANGLE, PITCH_UP, TAP_END, COMMANDS, TANK, WATER, mulberry32, wrap, DEG } from "../web/larva_body.js";
import { senseLarva, SENSE_NAMES, MECHANICAL_DECAY } from "../web/larva_senses.js";

let failures = 0;
const fail = (msg) => { failures++; console.log("FAIL " + msg); };
const ok = (msg) => console.log("ok   " + msg);
const check = (cond, msg) => (cond ? ok(msg) : fail(msg));
const inside = (p) => p[0] >= 0 && p[0] <= TANK[0] && p[1] >= 0 && p[1] <= TANK[1] && p[2] >= 0 && p[2] <= WATER;
const FRAME = 1 / 60;
const run = (b, seconds, pilot = null) => { for (let k = 0; k < Math.round(seconds / FRAME); k++) { if (pilot) pilot.drive(b, FRAME); b.step(FRAME); } return b.state(); };

// -- both cilia on: the scaled speed, forward, along a helix -----------------------------------
{
  const b = new LarvaBody(1, [6, 5, 4], 0);
  const c = b.command({ ciliaLeft: 1, ciliaRight: 1 });
  let path = 0, prev = b.state().position, maxSide = 0;
  for (let k = 0; k < 60; k++) {
    b.step(FRAME);
    const p = b.state().position;
    path += Math.hypot(p[0] - prev[0], p[1] - prev[1], p[2] - prev[2]); prev = p;
    maxSide = Math.max(maxSide, Math.abs(p[1] - 5));
  }
  const s = b.state(), dx = s.position[0] - 6, dy = s.position[1] - 5, dz = s.position[2] - 4;
  const radius = SPEED * Math.sin(HELIX_ANGLE) / ROLL;
  check(c.ciliaLeft === 1 && c.ciliaRight === 1 && Math.abs(path - SPEED) < 0.02 * SPEED, `cilia    ${path.toFixed(2)} mm of path in 1 s: the scaled speed ${SPEED.toFixed(2)} mm/s (${(SPEED / SCALE).toFixed(1)} mm/s real, drawn ${SCALE.toFixed(2)} times larger)`);
  check(dx > 0.85 * SPEED && dx < SPEED && Math.abs(dy) < 0.1 && maxSide > 1.6 * radius && maxSide < 2.4 * radius, `cilia    ${dx.toFixed(2)} mm forward, ${dy.toFixed(2)} mm sideways at the end, ${maxSide.toFixed(2)} mm out at most: a helix of diameter ${(2 * radius).toFixed(2)} mm about the course`);
  check(dz > 0.3 && s.pitch > 0.5 * PITCH_UP && s.pitch < PITCH_UP, `cilia    ${dz.toFixed(2)} mm up: the course rises toward ${(PITCH_UP / DEG).toFixed(0)} degrees nose up while swimming`);
  check(Math.abs(s.speed - SPEED) < 1e-9 && Math.abs(wrap(s.roll - ROLL)) < 1e-6, `cilia    speed ${s.speed.toFixed(2)} mm/s now, one spin in 1 s`);
}

// -- a left-right difference turns the course, every step the same way --------------------------
for (const [l, r] of [[1, 0.3], [0.3, 1]]) {
  const b = new LarvaBody(2, [10, 5, 5], 0.2);
  b.command({ ciliaLeft: l, ciliaRight: r });
  const h0 = b.state().heading;
  let prevH = h0, consistent = true;
  for (let k = 0; k < 60; k++) {
    b.step(FRAME);
    const h = b.state().heading;
    if (Math.sign(wrap(h - prevH)) !== Math.sign(l - r)) consistent = false;
    prevH = h;
  }
  const turned = wrap(b.state().heading - h0), want = TURN * (l - r);
  check(consistent && Math.abs(turned - want) < 1e-6 && inside(b.state().position), `turn     cilia ${l}/${r}: ${(turned / DEG).toFixed(1)} degrees in 1 s, every step to the ${l > r ? "left" : "right"}`);
}
{
  const b = new LarvaBody(2, [10, 5, 5], 0);
  b.command({ ciliaLeft: 0.8, ciliaRight: 0.8, muscleRight: 1 });
  const h0 = b.state().heading;
  b.step(0.1);
  const turned = wrap(b.state().heading - h0);
  check(Math.abs(turned + 0.1 * TURN_MUSCLE) < 1e-6 && b.state().sinking, `turn     right muscle: ${(turned / DEG).toFixed(1)} degrees in 100 ms, to the right, and the larva sinks`);
}

// -- an arrest stops the larva within one step and it sinks ------------------------------------
{
  const b = new LarvaBody(3, [10, 5, 6], 0);
  b.command({ ciliaLeft: 1, ciliaRight: 1 });
  const before = run(b, 0.5);
  b.command({ arrest: 1 });
  b.step(FRAME);
  const s1 = b.state();
  const moved = Math.hypot(s1.position[0] - before.position[0], s1.position[1] - before.position[1]);
  const sunk1 = before.position[2] - s1.position[2];
  check(before.speed > 6 && moved === 0 && s1.swim === 0 && s1.sinking && Math.abs(sunk1 - SINK * FRAME) < 1e-9, `arrest   from ${before.speed.toFixed(1)} mm/s to a stop within one step, sinking at ${SINK.toFixed(2)} mm/s (${(SINK / SCALE).toFixed(1)} mm/s real)`);
  const s2 = run(b, 1);
  check(Math.abs((s1.position[2] - s2.position[2]) - SINK) < 1e-6 && s2.roll === s1.roll, `arrest   ${(s1.position[2] - s2.position[2]).toFixed(2)} mm sunk in 1 s, no spin`);
  b.command({ arrest: 0 });
  b.step(FRAME);
  check(b.state().swim === SPEED && !b.state().sinking, "arrest   released: the cilia drive the larva again at once");
  b.command({ muscleLeft: 1, muscleRight: 1 });
  const vz0 = b.state().velocity[2];
  b.step(FRAME);
  const s3 = b.state();
  check(s3.sinking && s3.swim === SPEED && Math.abs((vz0 - s3.velocity[2]) - SINK) < 0.2, `arrest   a contraction of both muscles sinks the swimming larva by ${SINK.toFixed(2)} mm/s`);
}

// -- a tap's pulse decays below 0.05 within 200 ms -------------------------------------------------
{
  const b = new LarvaBody(4);
  b.tap(-1);
  const s0 = b.state();
  let below = null;
  for (let k = 0; k < 40; k++) { b.step(0.01); if (below === null && b.state().senses.mechanical < 0.05) below = (k + 1) * 0.01; }
  check(s0.senses.mechanical === 1 && s0.tap.side === -1 && below !== null && below <= 0.2, `tap      pulse 1 at the tap, below 0.05 after ${(below * 1e3).toFixed(0)} ms (tau ${MECHANICAL_DECAY} s)`);
  const w = senseLarva(s0, { light: { on: false }, tapSide: 1, tapAge: 0.2 });
  const live = b.state().tap !== null;
  b.step(0.2);
  check(w.mechanical < 0.05 && live && b.state().tap === null, `tap      senseLarva: ${w.mechanical.toFixed(3)} at 200 ms; the body forgets the tap after ${TAP_END} s`);
}

// -- the senses ------------------------------------------------------------------------------------
{
  const b = new LarvaBody(5, [10, 5, 5], 0);
  const s = b.state();
  const dark = senseLarva(s, { light: { on: false, x: 10, y: 5, z: 13 } });
  check(SENSE_NAMES.length === 7 && SENSE_NAMES.every((n) => n in dark) && Object.keys(dark).length === 7, `senses   ${SENSE_NAMES.length} named populations: ${SENSE_NAMES.join(", ")}`);
  check(dark.eye_left === 0 && dark.eye_right === 0 && dark.eyespot_left === 0 && dark.cprc === 0 && dark.mechanical === 0 && Math.abs(dark.pressure - 4 / 9) < 1e-12, `senses   lamp off: dark eyes, no ultraviolet, pressure ${dark.pressure.toFixed(2)} at 4 mm depth`);
  const left = senseLarva(s, { light: { on: true, x: 10, y: 9, z: 7 } });
  check(left.eye_left > 0.2 && left.eye_right === 0, `senses   lamp to the left: eye ${left.eye_left.toFixed(2)} / ${left.eye_right.toFixed(2)}, the right eye shaded by its cup`);
  check(left.eyespot_left > left.eyespot_right && left.eyespot_right > 0, `senses   lamp to the left: eyespots ${left.eyespot_left.toFixed(2)} / ${left.eyespot_right.toFixed(2)}, the wider field sees a little`);
  const right = senseLarva(s, { light: { on: true, x: 10, y: 1, z: 7 } });
  check(right.eye_right > right.eye_left && Math.abs(right.eye_right - left.eye_left) < 1e-12 && Math.abs(right.eyespot_right - left.eyespot_left) < 1e-12, "senses   lamp to the right: the mirror image");
  const ahead = senseLarva(s, { light: { on: true, x: 16, y: 5, z: 5 } });
  check(Math.abs(ahead.eye_left - ahead.eye_right) < 1e-12 && ahead.eye_left > 0.2, `senses   lamp ahead: both eyes ${ahead.eye_left.toFixed(2)}`);
  const behind = senseLarva(s, { light: { on: true, x: 2, y: 5, z: 5 } });
  check(behind.eye_left === 0 && behind.eye_right === 0 && behind.eyespot_left > 0, `senses   lamp behind: the eyes see nothing, the eyespots ${behind.eyespot_left.toFixed(3)}`);
  const uv = { light: { on: true, x: 10, y: 5, z: 13 } };
  const deep = senseLarva({ ...s, position: [10, 5, 1] }, uv), shallow = senseLarva({ ...s, position: [10, 5, 8.5] }, uv);
  check(shallow.cprc > 0.9 && deep.cprc < 0.15 && deep.pressure > shallow.pressure, `senses   ultraviolet: cPRC ${shallow.cprc.toFixed(2)} near the surface, ${deep.cprc.toFixed(2)} near the floor; pressure ${deep.pressure.toFixed(2)} / ${shallow.pressure.toFixed(2)}`);
  const noUv = senseLarva({ ...s, position: [10, 5, 8.5] }, { ...uv, uv: 0 });
  check(noUv.cprc === 0 && noUv.eye_left === 0, "senses   uv 0 with the lamp on: no cPRC drive, the lamp overhead on neither eye");
  const all = [dark, left, right, ahead, behind, deep, shallow].every((w) => Object.values(w).every((v) => v >= 0 && v <= 1));
  check(all, "senses   every level inside [0, 1]");
  b.setWorld({ light: { on: true, x: 10, y: 9, z: 7 } });
  const own = b.state().senses;
  check(Math.abs(own.eye_left - left.eye_left) < 1e-12 && own.cprc > 0, `senses   the body's own state carries them from its world: eye ${own.eye_left.toFixed(2)}, cPRC ${own.cprc.toFixed(2)}`);
}

// -- the glass holds the larva under random commands ---------------------------------------------
{
  const b = new LarvaBody(7, [3, 2, 1], 2.0), rng = mulberry32(99);
  let outside = 0, hits = 0, lastHit = -1, taps = 0;
  for (let k = 0; k < 10000; k++) {
    const c = {};
    for (const name of COMMANDS) c[name] = rng() < 0.5 ? rng() : 0;
    b.command(c);
    if (rng() < 0.002) { b.tap(rng() < 0.5 ? -1 : 1); taps++; }
    b.step(FRAME);
    const s = b.state();
    if (!inside(s.position)) outside++;
    if (s.wallHit && s.wallHit.time !== lastHit) { hits++; lastHit = s.wallHit.time; }
    for (const x of [...s.position, ...s.velocity, ...s.axis, s.heading, s.pitch, s.roll, ...Object.values(s.senses)]) if (!Number.isFinite(x)) throw new Error(`state is not finite at step ${k}`);
  }
  check(outside === 0, `walls    inside the tank for 10,000 random steps (${hits} reflections at the glass, ${taps} taps)`);
}

// -- the pilot: a startle at a tap, a turn toward the lamp, sixty seconds of life ----------------
{
  const b = new LarvaBody(8, [10, 5, 6], 0), pilot = new LarvaPilot(8);
  run(b, 0.5, pilot);
  const z0 = b.state().position[2];
  b.tap(-1);
  const d = pilot.drive(b, FRAME); b.step(FRAME);
  const s1 = b.state();
  const s2 = run(b, 0.3, pilot);
  check(d.mode === "startle" && d.arrest === 1 && d.muscleLeft === 1 && d.muscleRight === 1 && d.parapodia === 1 && s1.swim === 0 && z0 - s2.position[2] > 0.15, `pilot    tap: arrest, contraction, parapodia up; stopped and sank ${(z0 - s2.position[2]).toFixed(2)} mm in 0.3 s`);
  const s3 = run(b, 0.5, pilot);
  check(pilot.mode !== "startle" && s3.swim > 0, "pilot    swims again after the startle");

  const c = new LarvaBody(9, [8, 5, 5], 0), p2 = new LarvaPilot(9);
  c.setWorld({ light: { on: true, x: 8, y: 9.5, z: 7 } });
  const h0 = c.state().heading;
  const s4 = run(c, 1, p2);
  const turned = wrap(s4.heading - h0);
  check(turned > 0.3 && p2.mode === "steer" && s4.cilia.left > s4.cilia.right, `pilot    lamp to the left: turned ${(turned / DEG).toFixed(0)} degrees toward it in 1 s, cilia ${s4.cilia.left.toFixed(2)} / ${s4.cilia.right.toFixed(2)}`);

  const e = new LarvaBody(10), p3 = new LarvaPilot(10);
  e.setWorld({ light: { on: true, x: 10, y: 5, z: 13 } });
  let inWater = true, swimming = 0, dives = 0, lastMode = "swim";
  const N = Math.round(60 / FRAME);
  for (let k = 0; k < N; k++) {
    p3.drive(e, FRAME); e.step(FRAME);
    const s = e.state();
    if (!inside(s.position)) inWater = false;
    if (s.swim > 0) swimming++;
    if (p3.mode === "dive" && lastMode !== "dive") dives++;
    lastMode = p3.mode;
  }
  check(inWater && swimming / N > 0.6 && dives >= 1, `pilot    60 s under the lamp: in the tank, swimming ${(100 * swimming / N).toFixed(0)} % of the time, ${dives} dives from the ultraviolet near the surface`);
}

if (failures) { console.log(`${failures} failure(s)`); process.exit(1); }
console.log("all passed");
