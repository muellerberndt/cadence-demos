// The room seen from above, the parrot on its perch, and what its two eyes see: the world of the
// page, none of the brain. A plane of 4 m by 4 m with the perch at its middle; a thing is a kind,
// a colour and a place. The parrot's eyes sit on the sides of its head: each sees a wide fan to its
// side, from 10 degrees across the beak's line to 150 degrees back, so it sees everything but a
// blind spot behind it (the same rule as `in_view` in pack/py/askbrain/world.py, which the brain's
// host uses for what the eyes report).
export const PLANE = [-2, 2, -2, 2];
export const EYE = (70 * Math.PI) / 180; // each eye looks out this far to its side
export const FIELD = (80 * Math.PI) / 180; // and sees this far either side of where it looks
export const VIEW = EYE + FIELD; // 150 degrees either side of the beak
export const RADIUS = 0.17; // a thing's radius, metres
export const BIRD = 1.9; // the parrot is drawn this many times its size, to be seen
export const PERCH = 0.24 * BIRD; // the perch's radius as drawn
export const KIND_WORDS = ['ball', 'cup', 'box', 'book', 'shoe', 'key', 'apple', 'lamp', 'kettle', 'drum', 'vase', 'clock'];
export const COLOUR_WORDS = ['red', 'blue', 'green', 'yellow', 'white', 'black'];
export const PLACE_WORDS = ['front', 'right', 'behind', 'left'];
export const NAMED = 8; // kinds 0 to 7 were named by the teacher; 8 to 11 are for the visitor
export const PAINT = ['#e5484d', '#3e7bfa', '#35c06a', '#f2c94c', '#eef1f4', '#262a33'];
const EDGE = ['#8f1f25', '#173f9c', '#18753c', '#9a7616', '#9aa3ad', '#aab3c0'];

export const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));

/** Whether the parrot's eyes see a place, facing `heading`. */
export function inView(heading, x, y) {
  return Math.abs(wrap(Math.atan2(y, x) - heading)) <= VIEW;
}

/** The place around the parrot of a point: 0 in front, 1 to the right, 2 behind, 3 to the left. */
export function placeOf(heading, x, y) {
  const a = wrap(Math.atan2(y, x) - heading);
  const q = (((-a + Math.PI / 4) % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);
  return Math.floor(q / (Math.PI / 2));
}

/** The answers a teacher would give about a room: for the promise test and the tutorial. */
export function truth(things, heading) {
  return {
    where: (kind) => things.filter((t) => t.kind === kind).map((t) => PLACE_WORDS[placeOf(heading, t.x, t.y)]),
    colour: (kind) => things.filter((t) => t.kind === kind).map((t) => COLOUR_WORDS[t.colour]),
    byColour: (colour) => things.filter((t) => t.colour === colour).map((t) => t.kind),
    byPlace: (place) => things.filter((t) => placeOf(heading, t.x, t.y) === place).map((t) => t.kind),
  };
}

/** The first room: a red ball in front, a red book behind (in the blind spot), a blue cup and a
 *  yellow kettle (a kind the parrot has no word for) to the left, a green apple to the right. */
export function firstRoom() {
  const at = (deg, r) => [r * Math.cos((deg * Math.PI) / 180), r * Math.sin((deg * Math.PI) / 180)];
  const list = [[0, 0, at(14, 1.25)], [3, 0, at(178, 1.3)], [1, 1, at(96, 1.15)], [6, 2, at(-80, 1.2)], [8, 3, at(128, 1.5)]];
  return list.map(([kind, colour, [x, y]], id) => ({ id, kind, colour, x, y }));
}

/** A new room: four to six things of distinct kinds in drawn colours, one of them a kind the
 *  parrot has no word for, at least 0.6 m from the perch and 0.45 m from each other. */
export function newRoom(rand = Math.random) {
  const count = 4 + Math.floor(rand() * 3);
  const named = shuffle([0, 1, 2, 3, 4, 5, 6, 7], rand).slice(0, count - 1);
  const fresh = NAMED + Math.floor(rand() * 4);
  const kinds = shuffle([...named, fresh], rand);
  const things = [];
  for (const kind of kinds) {
    for (let k = 0; k < 1000; k++) {
      const r = 0.6 + rand() * 1.2, a = (rand() * 2 - 1) * Math.PI;
      const x = r * Math.cos(a), y = r * Math.sin(a);
      if (things.every((t) => Math.hypot(t.x - x, t.y - y) >= 0.45)) { things.push({ id: things.length, kind, colour: Math.floor(rand() * 6), x, y }); break; }
    }
  }
  return things;
}

function shuffle(list, rand) {
  for (let i = list.length - 1; i > 0; i--) { const j = Math.floor(rand() * (i + 1)); [list[i], list[j]] = [list[j], list[i]]; }
  return list;
}

/** Keeps a dragged thing on the floor: inside the room, off the perch. */
export function clampPlace(x, y) {
  const lim = PLANE[1] - RADIUS - 0.04;
  x = Math.max(-lim, Math.min(lim, x)); y = Math.max(-lim, Math.min(lim, y));
  const r = Math.hypot(x, y), least = 0.6;
  if (r < least) { const s = least / Math.max(r, 1e-6); x *= s; y *= s; }
  return [x, y];
}

// -- drawing

/** The transform from the room's metres to a canvas of `size` pixels, with a margin. */
export function frame(size, margin = 10) {
  const scale = (size - 2 * margin) / (PLANE[1] - PLANE[0]);
  const cx = size / 2, cy = size / 2;
  return { scale, toPx: (x, y) => [cx + x * scale, cy - y * scale], toRoom: (px, py) => [(px - cx) / scale, (cy - py) / scale] };
}

/** A thing seen from above: its kind's shape in its colour, centred at (px, py), of radius r. */
export function drawThing(ctx, kind, colour, px, py, r, opts = {}) {
  const fill = colour == null ? (opts.neutral || '#9fb0c4') : PAINT[colour];
  const edge = colour == null ? (opts.neutralEdge || '#41505f') : EDGE[colour];
  ctx.save();
  ctx.translate(px, py);
  ctx.globalAlpha = opts.alpha ?? 1;
  ctx.lineWidth = Math.max(1, r * 0.13);
  ctx.strokeStyle = edge; ctx.fillStyle = fill;
  if (opts.dashed) ctx.setLineDash([r * 0.35, r * 0.25]);
  const circle = (rr, f = true, s = true) => { ctx.beginPath(); ctx.arc(0, 0, rr, 0, 2 * Math.PI); if (f) ctx.fill(); if (s) ctx.stroke(); };
  const line = (pts) => { ctx.beginPath(); ctx.moveTo(pts[0], pts[1]); for (let k = 2; k < pts.length; k += 2) ctx.lineTo(pts[k], pts[k + 1]); ctx.stroke(); };
  switch (kind) {
    case 0: circle(r); ctx.beginPath(); ctx.arc(-r * 1.1, 0, r * 1.15, -0.75, 0.75); ctx.stroke(); break; // ball
    case 1: // cup: a handle, a rim and the drink inside
      ctx.beginPath(); ctx.arc(r * 0.98, 0, r * 0.32, -1.3, 1.3); ctx.lineWidth = r * 0.22; ctx.stroke(); ctx.lineWidth = Math.max(1, r * 0.13);
      circle(r * 0.86); ctx.fillStyle = 'rgba(20,24,30,0.45)'; circle(r * 0.6, true, false); break;
    case 2: // box with tape
      ctx.beginPath(); ctx.roundRect(-r * 0.86, -r * 0.86, r * 1.72, r * 1.72, r * 0.12); ctx.fill(); ctx.stroke();
      line([-r * 0.86, 0, r * 0.86, 0]); line([0, -r * 0.86, 0, r * 0.86]); break;
    case 3: // book with a spine
      ctx.beginPath(); ctx.roundRect(-r * 0.7, -r * 0.95, r * 1.4, r * 1.9, r * 0.1); ctx.fill(); ctx.stroke();
      ctx.fillStyle = edge; ctx.fillRect(-r * 0.7, -r * 0.95, r * 0.28, r * 1.9); break;
    case 4: // shoe: a sole and its opening
      ctx.beginPath(); ctx.ellipse(0, 0, r * 1.05, r * 0.55, -0.35, 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
      ctx.fillStyle = 'rgba(20,24,30,0.45)'; ctx.beginPath(); ctx.ellipse(-r * 0.32, r * 0.1, r * 0.4, r * 0.26, -0.35, 0, 2 * Math.PI); ctx.fill(); break;
    case 5: // key: a ring and a toothed shaft
      ctx.lineWidth = r * 0.26; ctx.strokeStyle = fill;
      ctx.beginPath(); ctx.arc(-r * 0.5, 0, r * 0.42, 0, 2 * Math.PI); ctx.stroke();
      line([-r * 0.08, 0, r * 1.0, 0]); line([r * 0.62, 0, r * 0.62, r * 0.36]); line([r * 0.9, 0, r * 0.9, r * 0.3]); break;
    case 6: // apple: round, a stem and a leaf
      circle(r * 0.92); ctx.strokeStyle = '#6b4a2b'; line([0, -r * 0.55, r * 0.08, -r * 1.05]);
      ctx.fillStyle = '#3aa35b'; ctx.beginPath(); ctx.ellipse(r * 0.38, -r * 0.88, r * 0.3, r * 0.14, -0.5, 0, 2 * Math.PI); ctx.fill(); break;
    case 7: // lamp: a shade with the bulb's light
      circle(r); ctx.fillStyle = 'rgba(255,248,214,0.85)'; circle(r * 0.4, true, false);
      for (let k = 0; k < 8; k++) { const a = (k * Math.PI) / 4; line([Math.cos(a) * r * 0.55, Math.sin(a) * r * 0.55, Math.cos(a) * r * 0.78, Math.sin(a) * r * 0.78]); } break;
    case 8: // kettle: a spout, a body and a handle
      ctx.beginPath(); ctx.moveTo(r * 0.6, -r * 0.25); ctx.lineTo(r * 1.15, -r * 0.55); ctx.lineTo(r * 1.15, -r * 0.3); ctx.lineTo(r * 0.6, r * 0.2); ctx.closePath(); ctx.fill(); ctx.stroke();
      circle(r * 0.82); ctx.lineWidth = r * 0.2; ctx.strokeStyle = edge; ctx.beginPath(); ctx.arc(0, 0, r * 0.45, Math.PI * 1.15, Math.PI * 1.85); ctx.stroke(); break;
    case 9: // drum: a skin, its hoop and two sticks
      circle(r); ctx.beginPath(); ctx.arc(0, 0, r * 0.72, 0, 2 * Math.PI); ctx.stroke();
      ctx.strokeStyle = '#c9a36a'; ctx.lineWidth = r * 0.12; line([-r * 0.9, -r * 0.2, r * 0.3, r * 0.9]); line([r * 0.9, -r * 0.2, -r * 0.3, r * 0.9]); break;
    case 10: // vase: a wide body, a narrow opening and a flower
      circle(r * 0.95); ctx.fillStyle = 'rgba(20,24,30,0.5)'; circle(r * 0.38, true, true);
      ctx.fillStyle = '#ff8fb1'; for (let k = 0; k < 5; k++) { const a = (k * 2 * Math.PI) / 5; ctx.beginPath(); ctx.arc(Math.cos(a) * r * 0.2, Math.sin(a) * r * 0.2, r * 0.13, 0, 2 * Math.PI); ctx.fill(); } break;
    case 11: // clock: a face with marks and two hands
      circle(r);
      for (let k = 0; k < 12; k++) { const a = (k * Math.PI) / 6; line([Math.cos(a) * r * 0.72, Math.sin(a) * r * 0.72, Math.cos(a) * r * 0.86, Math.sin(a) * r * 0.86]); }
      ctx.strokeStyle = edge; line([0, 0, 0, -r * 0.6]); line([0, 0, r * 0.42, r * 0.1]); break;
    default: circle(r);
  }
  ctx.restore();
}

/** A pistachio: two halves of its shell, the green nut between them. `open` from 0 (shut) to 1. */
export function drawPistachio(ctx, x, y, r, open = 0, alpha = 1) {
  ctx.save(); ctx.translate(x, y); ctx.globalAlpha = alpha;
  const gap = open * r * 1.4;
  for (const side of [-1, 1]) {
    ctx.save(); ctx.translate(0, side * gap); ctx.rotate(side * open * 0.6);
    ctx.fillStyle = '#e9d6ae'; ctx.strokeStyle = '#a88a5a'; ctx.lineWidth = Math.max(1, r * 0.12);
    ctx.beginPath(); ctx.ellipse(0, side * r * 0.12, r, r * 0.62, 0, side < 0 ? Math.PI : 0, side < 0 ? 2 * Math.PI : Math.PI); ctx.closePath(); ctx.fill(); ctx.stroke();
    ctx.restore();
  }
  if (open < 0.95) { ctx.fillStyle = '#8fbf4a'; ctx.beginPath(); ctx.ellipse(0, 0, r * 0.62, r * 0.3, 0, 0, 2 * Math.PI); ctx.fill(); }
  ctx.restore();
}

/** The African Grey from above, on its perch: grey feathers, a red tail, white skin around its
 *  eyes, a black hooked beak. `pose`: heading (where the head faces), body (where the body faces),
 *  tilt, blink (0 to 1), bob (0 to 1, while it speaks), beakOpen (0 to 1). Original drawing. */
export function drawParrot(ctx, px, py, scale, pose) {
  const { heading, body = heading, tilt = 0, blink = 0, bob = 0, beakOpen = 0, fluff = 0 } = pose;
  const s = scale * BIRD;
  const puff = 1 + 0.12 * fluff; // a happy parrot fluffs its feathers
  // the perch: a round stump of wood under the bird
  ctx.save(); ctx.translate(px, py);
  const pr = 0.24 * s;
  const wood = ctx.createRadialGradient(0, 0, pr * 0.1, 0, 0, pr);
  wood.addColorStop(0, '#a77b4f'); wood.addColorStop(0.75, '#7a5534'); wood.addColorStop(1, '#4f3520');
  ctx.fillStyle = wood; ctx.beginPath(); ctx.arc(0, 0, pr, 0, 2 * Math.PI); ctx.fill();
  ctx.strokeStyle = 'rgba(60,38,20,0.55)'; ctx.lineWidth = 1;
  for (const k of [0.35, 0.55, 0.75]) { ctx.beginPath(); ctx.arc(0, 0, pr * k, 0, 2 * Math.PI); ctx.stroke(); }
  ctx.restore();
  const grey = '#9ca3aa', dark = '#6f767e', light = '#c3c8cd';
  // the body, wings and tail, facing `body`
  ctx.save(); ctx.translate(px, py); ctx.rotate(-body);
  ctx.shadowColor = 'rgba(0,0,0,0.45)'; ctx.shadowBlur = s * 0.05; ctx.shadowOffsetY = s * 0.01;
  // tail: the red fan behind
  ctx.fillStyle = '#d4312d';
  ctx.beginPath(); ctx.moveTo(-s * 0.12, -s * 0.05); ctx.quadraticCurveTo(-s * 0.3, -s * 0.085, -s * 0.33, 0); ctx.quadraticCurveTo(-s * 0.3, s * 0.085, -s * 0.12, s * 0.05); ctx.closePath(); ctx.fill();
  ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
  ctx.strokeStyle = 'rgba(120,20,18,0.7)'; ctx.lineWidth = 1;
  for (const k of [-0.5, 0, 0.5]) { ctx.beginPath(); ctx.moveTo(-s * 0.15, k * s * 0.05); ctx.lineTo(-s * 0.31, k * s * 0.09); ctx.stroke(); }
  // body
  ctx.fillStyle = grey; ctx.beginPath(); ctx.ellipse(-s * 0.02, 0, s * 0.14 * puff, s * 0.1 * puff, 0, 0, 2 * Math.PI); ctx.fill();
  // wings: folded along the sides, darker, their feathers scalloped
  for (const side of [-1, 1]) {
    ctx.fillStyle = dark;
    const w = puff * puff;
    ctx.beginPath(); ctx.moveTo(s * 0.06, side * s * 0.06 * w); ctx.quadraticCurveTo(-s * 0.05, side * s * 0.125 * w, -s * 0.21, side * s * 0.05 * w); ctx.quadraticCurveTo(-s * 0.1, side * s * 0.04 * w, s * 0.06, side * s * 0.06 * w); ctx.fill();
    ctx.strokeStyle = 'rgba(40,44,50,0.5)'; ctx.lineWidth = 0.9;
    for (let k = 0; k < 4; k++) { const x = s * (0.03 - k * 0.05); ctx.beginPath(); ctx.arc(x, side * s * 0.075, s * 0.016, Math.PI * 0.5, Math.PI * 1.5); ctx.stroke(); }
  }
  // the back's feathers
  ctx.strokeStyle = 'rgba(70,76,84,0.45)'; ctx.lineWidth = 0.8;
  for (let r = 0; r < 3; r++) for (let c = -1; c <= 1; c++) { ctx.beginPath(); ctx.arc(-s * (0.08 + r * 0.04), c * s * 0.03, s * 0.018, Math.PI * 0.5, Math.PI * 1.5); ctx.stroke(); }
  ctx.restore();
  // the head, facing `heading`, a little tilted
  ctx.save(); ctx.translate(px, py); ctx.rotate(-heading);
  const hx = s * (0.1 + 0.012 * Math.max(bob, fluff));
  ctx.translate(hx, 0); ctx.rotate(tilt);
  ctx.fillStyle = light; ctx.beginPath(); ctx.arc(0, 0, s * 0.075, 0, 2 * Math.PI); ctx.fill();
  ctx.strokeStyle = 'rgba(110,116,124,0.5)'; ctx.lineWidth = 0.7;
  for (let k = 0; k < 3; k++) { ctx.beginPath(); ctx.arc(-s * (0.03 + k * 0.012), 0, s * (0.02 + k * 0.012), Math.PI * 0.6, Math.PI * 1.4); ctx.stroke(); }
  // the beak: black, hooked, pointing where the head faces
  ctx.fillStyle = '#18191c';
  ctx.beginPath(); ctx.moveTo(s * 0.05, -s * 0.032); ctx.quadraticCurveTo(s * 0.115, -s * 0.03, s * 0.125, s * 0.004); ctx.quadraticCurveTo(s * 0.105, s * 0.012, s * 0.09, s * 0.006); ctx.lineTo(s * 0.05, s * 0.032); ctx.closePath(); ctx.fill();
  if (beakOpen > 0) { ctx.fillStyle = '#3a2a2a'; ctx.beginPath(); ctx.moveTo(s * 0.055, 0); ctx.lineTo(s * 0.095, -s * 0.006 * beakOpen * 3); ctx.lineTo(s * 0.095, s * 0.006 * beakOpen * 3); ctx.closePath(); ctx.fill(); }
  ctx.fillStyle = 'rgba(255,255,255,0.18)'; ctx.beginPath(); ctx.ellipse(s * 0.075, -s * 0.014, s * 0.018, s * 0.006, -0.2, 0, 2 * Math.PI); ctx.fill();
  // the eyes on the sides of the head, in their white skin
  for (const side of [-1, 1]) {
    ctx.fillStyle = '#eef0f2'; ctx.beginPath(); ctx.ellipse(s * 0.022, side * s * 0.05, s * 0.034, s * 0.026, 0, 0, 2 * Math.PI); ctx.fill();
    if (blink > 0.5) { ctx.strokeStyle = '#4c5258'; ctx.lineWidth = 1.4; ctx.beginPath(); ctx.moveTo(s * 0.005, side * s * 0.06); ctx.lineTo(s * 0.04, side * s * 0.06); ctx.stroke(); }
    else {
      ctx.fillStyle = '#f2e3a0'; ctx.beginPath(); ctx.arc(s * 0.024, side * s * 0.06, s * 0.013, 0, 2 * Math.PI); ctx.fill();
      ctx.fillStyle = '#111'; ctx.beginPath(); ctx.arc(s * 0.024, side * s * 0.063, s * 0.0065, 0, 2 * Math.PI); ctx.fill();
      ctx.fillStyle = 'rgba(255,255,255,0.9)'; ctx.beginPath(); ctx.arc(s * 0.027, side * s * 0.058, s * 0.0025, 0, 2 * Math.PI); ctx.fill();
    }
  }
  ctx.restore();
}

/** The room: floor, the eyes' two fans and the blind spot, the four places around the parrot, the
 *  things, the parrot. `held` lists what the brain's map holds ({kind, place, colour}); a held
 *  place far from where its thing stands is drawn as a ghost: where the brain holds a thing it did
 *  not see move. */
export function drawRoom(ctx, size, state) {
  const { things, heading, pose, held = [], focus = null, ask = null, teach = null, hover = null, nut = null } = state;
  const f = frame(size);
  const s = f.scale;
  ctx.clearRect(0, 0, size, size);
  const [x0, y0] = f.toPx(PLANE[0], PLANE[3]);
  const side = (PLANE[1] - PLANE[0]) * s;
  const floor = ctx.createRadialGradient(size / 2, size / 2, side * 0.05, size / 2, size / 2, side * 0.75);
  floor.addColorStop(0, '#1d2a35'); floor.addColorStop(1, '#0f161f');
  ctx.fillStyle = floor; ctx.beginPath(); ctx.roundRect(x0, y0, side, side, 12); ctx.fill();
  ctx.strokeStyle = 'rgba(140,170,200,0.18)'; ctx.lineWidth = 1; ctx.stroke();
  ctx.save(); ctx.beginPath(); ctx.roundRect(x0, y0, side, side, 12); ctx.clip();
  ctx.strokeStyle = 'rgba(140,170,200,0.05)';
  for (let v = -1.5; v <= 1.5; v += 0.5) { let [a, b] = f.toPx(v, -2), [c, d] = f.toPx(v, 2); ctx.beginPath(); ctx.moveTo(a, b); ctx.lineTo(c, d); ctx.stroke(); [a, b] = f.toPx(-2, v); [c, d] = f.toPx(2, v); ctx.beginPath(); ctx.moveTo(a, b); ctx.lineTo(c, d); ctx.stroke(); }
  const [rx, ry] = f.toPx(0, 0);
  const far = side;
  const look = pose ? pose.heading : heading;
  // the two eyes' fans: each to its side, overlapping in front
  for (const sideSign of [1, -1]) {
    const centre = look + sideSign * EYE;
    ctx.beginPath(); ctx.moveTo(rx, ry); ctx.arc(rx, ry, far, -(centre + FIELD), -(centre - FIELD)); ctx.closePath();
    const fan = ctx.createRadialGradient(rx, ry, 0, rx, ry, far * 0.72);
    fan.addColorStop(0, 'rgba(255,236,170,0.12)'); fan.addColorStop(1, 'rgba(255,236,170,0.02)');
    ctx.fillStyle = fan; ctx.fill();
  }
  // the blind spot behind
  ctx.beginPath(); ctx.moveTo(rx, ry); ctx.arc(rx, ry, far, -(look + Math.PI + (Math.PI - VIEW)), -(look + Math.PI - (Math.PI - VIEW))); ctx.closePath();
  ctx.fillStyle = 'rgba(0,0,0,0.28)'; ctx.fill();
  // the four places around the parrot
  ctx.setLineDash([3, 6]); ctx.strokeStyle = 'rgba(160,190,220,0.16)'; ctx.lineWidth = 1;
  for (let k = 0; k < 4; k++) {
    const a = heading + Math.PI / 4 + (k * Math.PI) / 2;
    ctx.beginPath(); ctx.moveTo(rx + Math.cos(a) * PERCH * s * 1.15, ry - Math.sin(a) * PERCH * s * 1.15); ctx.lineTo(rx + Math.cos(a) * far, ry - Math.sin(a) * far); ctx.stroke();
  }
  ctx.setLineDash([]);
  const asked = ask && ask.place != null ? ask.place : null;
  ctx.font = `500 ${Math.max(10, Math.round(s * 0.085))}px Inter, system-ui, sans-serif`;
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  for (let k = 0; k < 4; k++) {
    const a = heading - (k * Math.PI) / 2;
    const pad = s * 0.3;
    const lx = Math.max(x0 + pad, Math.min(x0 + side - pad, rx + Math.cos(a) * s * 1.8));
    const ly = Math.max(y0 + pad * 0.5, Math.min(y0 + side - pad * 0.5, ry - Math.sin(a) * s * 1.8));
    if (asked === k) {
      ctx.beginPath(); ctx.moveTo(rx, ry); ctx.arc(rx, ry, far, -(a + Math.PI / 4), -(a - Math.PI / 4)); ctx.closePath();
      ctx.fillStyle = 'rgba(63,224,207,0.08)'; ctx.fill();
    }
    ctx.fillStyle = asked === k ? 'rgba(120,240,225,0.9)' : 'rgba(160,190,220,0.3)';
    ctx.fillText(['in front', 'right', 'behind', 'left'][k], lx, ly);
  }
  ctx.fillStyle = 'rgba(160,190,220,0.28)'; ctx.font = `500 ${Math.max(9, Math.round(s * 0.07))}px Inter, system-ui, sans-serif`;
  ctx.fillText('blind spot', rx - Math.cos(look) * s * 1.45, ry + Math.sin(look) * s * 1.45);
  ctx.restore();
  // what the brain's map holds where its thing is not
  for (const h of held) {
    if (!h.place) continue;
    const [hx, hy] = f.toPx(h.place[0], h.place[1]);
    const near = things.some((t) => t.kind === h.kind && Math.hypot(t.x - h.place[0], t.y - h.place[1]) < 0.2);
    const glow = ctx.createRadialGradient(hx, hy, 0, hx, hy, RADIUS * s * 2.2);
    glow.addColorStop(0, 'rgba(63,224,207,0.26)'); glow.addColorStop(1, 'rgba(63,224,207,0)');
    ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(hx, hy, RADIUS * s * 2.2, 0, 2 * Math.PI); ctx.fill();
    if (!near) drawThing(ctx, h.kind, h.colour, hx, hy, RADIUS * s, { alpha: 0.42, dashed: true });
  }
  for (const t of things) {
    const [px, py] = f.toPx(t.x, t.y);
    if (focus && focus.includes(t.id)) { ctx.beginPath(); ctx.arc(px, py, RADIUS * s * 1.65, 0, 2 * Math.PI); ctx.strokeStyle = 'rgba(255,206,102,0.9)'; ctx.lineWidth = 2; ctx.stroke(); }
    if (teach === t.id) { ctx.beginPath(); ctx.arc(px, py, RADIUS * s * 1.55, 0, 2 * Math.PI); ctx.strokeStyle = 'rgba(255,159,74,0.95)'; ctx.setLineDash([4, 3]); ctx.lineWidth = 2; ctx.stroke(); ctx.setLineDash([]); }
    else if (hover === t.id) { ctx.beginPath(); ctx.arc(px, py, RADIUS * s * 1.45, 0, 2 * Math.PI); ctx.strokeStyle = 'rgba(233,237,247,0.45)'; ctx.lineWidth = 1.5; ctx.stroke(); }
    drawThing(ctx, t.kind, t.colour, px, py, RADIUS * s, { alpha: inView(heading, t.x, t.y) ? 1 : 0.78 });
  }
  drawParrot(ctx, rx, ry, s, pose || { heading });
  if (nut) {
    const beak = [rx + Math.cos(look) * s * 0.22 * BIRD, ry - Math.sin(look) * s * 0.22 * BIRD];
    const t = nut.t; // 0 to 1: flies in, cracks, the shells fall
    const fly = Math.min(1, t / 0.4);
    const from = nut.from || [rx + s * 0.9, ry + s * 0.9];
    const x = from[0] + (beak[0] - from[0]) * easeOut(fly), y = from[1] + (beak[1] - from[1]) * easeOut(fly) - Math.sin(fly * Math.PI) * s * 0.25;
    drawPistachio(ctx, x, y, s * 0.05, Math.max(0, (t - 0.45) / 0.35), t > 0.85 ? (1 - t) / 0.15 : 1);
  }
  return f;
}

const easeOut = (t) => 1 - (1 - t) * (1 - t);

/** What the parrot's two eyes see, side by side as one panorama: the left eye from its back (the
 *  blind spot's edge) to across the beak, then the right eye from across the beak to its back.
 *  Each column is a ray from the eye: the nearest thing it meets in that thing's colour, or the
 *  wall, both taller the nearer they are. */
export function drawRetina(ctx, w, h, things, heading) {
  ctx.clearRect(0, 0, w, h);
  const gap = 6, half = (w - gap) / 2;
  const eyes = [[heading + EYE + FIELD, heading + EYE - FIELD, 0], [heading - EYE + FIELD, heading - EYE - FIELD, half + gap]];
  for (const [a0, a1, ox] of eyes) {
    ctx.save(); ctx.beginPath(); ctx.roundRect(ox, 0, half, h, 6); ctx.clip();
    const sky = ctx.createLinearGradient(0, 0, 0, h);
    sky.addColorStop(0, '#16202b'); sky.addColorStop(0.5, '#1d2a37'); sky.addColorStop(0.5, '#141c25'); sky.addColorStop(1, '#0c1218');
    ctx.fillStyle = sky; ctx.fillRect(ox, 0, half, h);
    const cols = Math.max(40, Math.round(half / 3)), cw = half / cols;
    for (let c = 0; c < cols; c++) {
      const a = a0 + ((c + 0.5) / cols) * (a1 - a0);
      const dx = Math.cos(a), dy = Math.sin(a);
      const tx = dx > 0 ? 2 / dx : dx < 0 ? -2 / dx : Infinity;
      const ty = dy > 0 ? 2 / dy : dy < 0 ? -2 / dy : Infinity;
      const wall = Math.min(tx, ty);
      const wh = Math.min(h, (h * 0.55) / Math.max(wall, 0.1));
      ctx.fillStyle = `rgba(150,175,205,${Math.max(0.12, Math.min(0.38, 0.5 / wall))})`;
      ctx.fillRect(ox + c * cw, h / 2 - wh / 2, cw + 0.6, wh);
      let best = null;
      for (const t of things) {
        const along = t.x * dx + t.y * dy;
        if (along <= 0) continue;
        const off = Math.abs(t.x * dy - t.y * dx);
        if (off > RADIUS) continue;
        const d = along - Math.sqrt(RADIUS * RADIUS - off * off);
        if (!best || d < best.d) best = { t, d };
      }
      if (best) {
        const th = Math.min(h * 0.95, (h * 0.42) / Math.max(best.d, 0.1));
        ctx.fillStyle = PAINT[best.t.colour];
        ctx.globalAlpha = Math.max(0.55, Math.min(1, 1.6 / (best.d + 0.6)));
        ctx.fillRect(ox + c * cw, h / 2 + wh / 2 - th * 0.92, cw + 0.6, th);
        ctx.globalAlpha = 1;
      }
    }
    ctx.restore();
  }
}
