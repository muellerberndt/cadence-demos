// The scene from above, the map around the body, the map the brain holds, and the error chart:
// four Canvas2D views.
//
// SceneView draws the plane as it is (the arm, the hand, the things, the camera's light and its
// shadows) and, on top, what the brain says: the hand's place as a glowing peak inside the area
// that holds it at the stated rate, and a pin for every thing's record. MapView draws the place
// answer itself, straight from the place units' readout. ChartView draws each estimate's error
// against the true position over the last moments.

import { forward, litPolygon, cartesian, around } from './world.js';
import { radiusAt, RATE } from './controls.js';

const TEAL = [63, 224, 207], ORANGE = [255, 159, 74], GOLD = [255, 206, 102], VIOLET = [183, 156, 255];
export const THING_COLOR = { hand: ORANGE, cup: [127, 212, 255], apple: [255, 104, 116], bread: [236, 190, 124] };

/** A kind of thing as a small friendly glyph, drawn at the origin at size u: a cup seen from
 *  above, an apple, a slice of bread. `lit`: in the camera's view (solid and glowing); else it
 *  is what is really there, as a clear outline. */
export function glyph(c, name, u, lit = true) {
  const color = THING_COLOR[name] || [200, 200, 220];
  c.save();
  c.lineJoin = 'round'; c.lineCap = 'round';
  c.lineWidth = Math.max(1, u * 0.11);
  c.strokeStyle = rgba(color, lit ? 1 : 0.85); c.fillStyle = rgba(color, lit ? 0.3 : 0.1);
  if (lit) { c.shadowColor = rgba(color, 0.6); c.shadowBlur = u * 0.9; }
  if (name === 'apple') {
    const body = new Path2D();
    body.moveTo(0, -0.5 * u);
    body.bezierCurveTo(-0.5 * u, -1.0 * u, -1.2 * u, -0.5 * u, -1.02 * u, 0.2 * u);
    body.bezierCurveTo(-0.9 * u, 0.85 * u, -0.4 * u, 1.1 * u, 0, 0.88 * u);
    body.bezierCurveTo(0.4 * u, 1.1 * u, 0.9 * u, 0.85 * u, 1.02 * u, 0.2 * u);
    body.bezierCurveTo(1.2 * u, -0.5 * u, 0.5 * u, -1.0 * u, 0, -0.5 * u);
    if (lit) c.fillStyle = rgba(color, 0.9);
    c.fill(body); c.shadowBlur = 0; c.stroke(body);
    if (lit) { c.strokeStyle = 'rgba(255,220,220,0.75)'; c.beginPath(); c.arc(-0.42 * u, -0.05 * u, 0.36 * u, Math.PI * 0.95, Math.PI * 1.45); c.stroke(); }
    c.strokeStyle = lit ? 'rgba(150,104,60,1)' : rgba(color, 0.85);
    c.beginPath(); c.moveTo(0, -0.5 * u); c.quadraticCurveTo(0.02 * u, -0.9 * u, 0.2 * u, -1.12 * u); c.stroke();
    c.fillStyle = lit ? 'rgba(126,214,140,0.95)' : rgba(color, 0.1); c.strokeStyle = lit ? 'rgba(70,150,90,1)' : rgba(color, 0.85);
    c.beginPath(); c.ellipse(0.55 * u, -0.98 * u, 0.36 * u, 0.17 * u, -0.5, 0, Math.PI * 2); c.fill(); c.stroke();
  } else if (name === 'bread') {
    const slice = (k) => {
      const q = new Path2D();
      q.moveTo(-0.85 * u * k, 0.78 * u * k);
      q.lineTo(-0.85 * u * k, -0.12 * u * k);
      q.bezierCurveTo(-1.3 * u * k, -0.3 * u * k, -1.2 * u * k, -1.02 * u * k, -0.52 * u * k, -0.94 * u * k);
      q.bezierCurveTo(-0.3 * u * k, -1.14 * u * k, 0.3 * u * k, -1.14 * u * k, 0.52 * u * k, -0.94 * u * k);
      q.bezierCurveTo(1.2 * u * k, -1.02 * u * k, 1.3 * u * k, -0.3 * u * k, 0.85 * u * k, -0.12 * u * k);
      q.lineTo(0.85 * u * k, 0.78 * u * k);
      q.quadraticCurveTo(0.85 * u * k, 0.95 * u * k, 0.68 * u * k, 0.95 * u * k);
      q.lineTo(-0.68 * u * k, 0.95 * u * k);
      q.quadraticCurveTo(-0.85 * u * k, 0.95 * u * k, -0.85 * u * k, 0.78 * u * k);
      return q;
    };
    if (lit) c.fillStyle = 'rgba(206,140,72,0.95)';
    c.fill(slice(1)); c.shadowBlur = 0;
    c.strokeStyle = lit ? 'rgba(150,92,40,1)' : rgba(color, 0.85); c.stroke(slice(1));
    if (lit) { c.fillStyle = 'rgba(246,220,172,0.96)'; c.fill(slice(0.74)); }
    else { c.strokeStyle = rgba(color, 0.5); c.stroke(slice(0.74)); }
  } else {
    // a cup seen from above: its rim, its inside and its handle
    c.beginPath(); c.arc(0, 0, u, 0, Math.PI * 2); c.fill(); c.shadowBlur = 0; c.stroke();
    c.beginPath(); c.arc(0, 0, u * 0.68, 0, Math.PI * 2); c.stroke();
    c.beginPath(); c.arc(u * 1.25, 0, u * 0.42, -Math.PI * 0.62, Math.PI * 0.62); c.stroke();
  }
  c.restore();
}
const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const lerp = (a, b, f) => a + (b - a) * f;
const mix = (p, q, f) => [lerp(p[0], q[0], f), lerp(p[1], q[1], f)];

function fit(canvas) {
  const box = canvas.getBoundingClientRect();
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const w = Math.max(120, Math.round(box.width)), h = Math.max(80, Math.round(box.height));
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
  }
  const c = canvas.getContext('2d');
  c.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { c, w, h, dpr };
}

export class SceneView {
  constructor(canvas) {
    this.canvas = canvas;
    this.shade = document.createElement('canvas'); // the shadows inside the camera's field
    this.rings = [];  // sounds: { at, cue, start }
    this.trail = [];  // the brain's last answers for the hand
    this.shown = null; // the belief as it is drawn, flowing toward the latest answer
    this.calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.scale = 1; this.ox = 0; this.oy = 0;
    this.hatch = null;
  }

  // metres <-> CSS pixels (y up on the plane, down on the screen)
  toScreen(p) { return [this.ox + p[0] * this.scale, this.oy - p[1] * this.scale]; }
  toPlane(x, y) { return [(x - this.ox) / this.scale, (this.oy - y) / this.scale]; }

  layout(geometry, w, h) {
    const [lx, hx, ly, hy] = geometry.plane, margin = 0.05;
    this.scale = Math.min(w / (hx - lx + 2 * margin), h / (hy - ly + 2 * margin));
    this.ox = w / 2 - ((lx + hx) / 2) * this.scale;
    this.oy = h / 2 + ((ly + hy) / 2) * this.scale;
  }

  ring(at, cue, geometry) { this.rings.push({ at: at.slice(), heard: cartesian(geometry, cue), ear: geometry.ear.slice(), start: performance.now() }); }

  /** Draw one frame. `s` holds the stage's geometry, the two latest records (for motion
   *  between moments), the brain's latest answer and the page's toggles. */
  draw(s, now = performance.now()) {
    const { c, w, h, dpr } = fit(this.canvas);
    const g = s.geometry;
    this.layout(g, w, h);
    const S = (p) => this.toScreen(p), m = this.scale;
    const f = s.blend ?? 1, a = s.previous || s.record, b = s.record;
    const joints = b ? b.joints.map((q, k) => lerp(a.joints[k] ?? q, q, f)) : s.joints;
    const things = b ? b.truth.map((p, k) => mix(a.truth[k] || p, p, f)) : s.things;
    c.clearRect(0, 0, w, h);

    // the plane
    const [lx, hx, ly, hy] = g.plane;
    const [x0, y0] = S([lx, hy]), [x1, y1] = S([hx, ly]);
    const floor = c.createLinearGradient(0, y0, 0, y1);
    floor.addColorStop(0, '#0c1222'); floor.addColorStop(1, '#090d18');
    c.fillStyle = floor;
    c.beginPath(); c.roundRect(x0, y0, x1 - x0, y1 - y0, 10); c.fill();
    c.save();
    c.beginPath(); c.roundRect(x0, y0, x1 - x0, y1 - y0, 10); c.clip();
    c.strokeStyle = 'rgba(120,140,200,0.07)'; c.lineWidth = 1;
    c.beginPath();
    for (let x = Math.ceil(lx / 0.2) * 0.2; x <= hx + 1e-9; x += 0.2) { const [px] = S([x, 0]); c.moveTo(px, y0); c.lineTo(px, y1); }
    for (let y = Math.ceil(ly / 0.2) * 0.2; y <= hy + 1e-9; y += 0.2) { const [, py] = S([0, y]); c.moveTo(x0, py); c.lineTo(x1, py); }
    c.stroke();

    // the camera's light, and the shadows inside its field
    const cam = g.camera, eye = S(cam.position);
    if (s.cameraOn) {
      const lit = litPolygon(g, joints, w < 520 ? 140 : 220, s.own).map(S);
      const light = c.createRadialGradient(eye[0], eye[1], 0, eye[0], eye[1], cam.range * m * 0.9);
      light.addColorStop(0, 'rgba(175,235,255,0.46)'); light.addColorStop(0.3, 'rgba(125,195,255,0.22)'); light.addColorStop(1, 'rgba(90,150,255,0.10)');
      c.globalCompositeOperation = 'lighter';
      c.fillStyle = light;
      c.beginPath(); c.moveTo(eye[0], eye[1]); for (const p of lit) c.lineTo(p[0], p[1]); c.closePath(); c.fill();
      c.globalCompositeOperation = 'source-over';
      this.shadows(c, w, h, dpr, g, eye, lit, [x0, y0, x1, y1]);
      c.strokeStyle = 'rgba(140,210,255,0.16)'; c.lineWidth = 1;
      c.beginPath();
      for (const side of [-1, 1]) {
        const angle = cam.heading + (side * cam.fov) / 2;
        c.moveTo(eye[0], eye[1]); c.lineTo(eye[0] + Math.cos(angle) * cam.range * m, eye[1] - Math.sin(angle) * cam.range * m);
      }
      c.stroke();
    } else {
      c.fillStyle = 'rgba(2,3,8,0.42)'; c.fillRect(x0, y0, x1 - x0, y1 - y0);
    }
    c.restore();
    c.strokeStyle = 'rgba(150,165,210,0.28)'; c.lineWidth = 1.2;
    c.beginPath(); c.roundRect(x0, y0, x1 - x0, y1 - y0, 10); c.stroke();

    // the brain's belief of the hand: its haze lies under everything on the table
    const belief = s.belief?.place ? this.flow(s) : null;
    if (belief) {
      c.save(); c.beginPath(); c.roundRect(x0, y0, x1 - x0, y1 - y0, 10); c.clip();
      this.haze(c, belief, m);
      c.restore();
    }

    // the occluding discs
    for (const o of g.occluders) {
      const [ox, oy] = S(o.center), r = o.radius * m;
      const disc = c.createRadialGradient(ox - r * 0.3, oy - r * 0.3, r * 0.1, ox, oy, r);
      disc.addColorStop(0, '#39425e'); disc.addColorStop(1, '#161b2c');
      c.fillStyle = disc; c.beginPath(); c.arc(ox, oy, r, 0, Math.PI * 2); c.fill();
      c.strokeStyle = s.selected === 'pillar' ? 'rgba(255,255,255,0.9)' : 'rgba(170,185,225,0.55)'; c.lineWidth = 1.4; c.stroke();
    }

    // the things on the table and their pins
    for (let k = 1; k < things.length; k++) this.thing(c, s, k, things[k], m);
    for (let k = 1; k < things.length; k++) this.pin(c, s, k, things[k]);

    // the arm
    this.arm(c, g, joints, m, s.own);

    // the hand
    this.hand(c, s, things[0], m);

    // the belief's ring and its peak, over the hand: the brightest thing on the table
    if (belief) {
      c.save(); c.beginPath(); c.roundRect(x0, y0, x1 - x0, y1 - y0, 10); c.clip();
      this.peak(c, s, belief, m);
      c.restore();
    }

    // the comparison's markers
    if (s.compare && s.controls) {
      const { last, kalman, kalmanRadius } = s.controls;
      const [kx, ky] = S(kalman), [qx, qy] = S(last);
      c.lineWidth = 1;
      c.strokeStyle = rgba(VIOLET, 0.95);
      c.beginPath(); c.moveTo(kx, ky - 5); c.lineTo(kx + 5, ky); c.lineTo(kx, ky + 5); c.lineTo(kx - 5, ky); c.closePath(); c.stroke();
      c.strokeStyle = rgba(VIOLET, 0.3);
      c.beginPath(); c.arc(kx, ky, Math.max(2, kalmanRadius * m), 0, Math.PI * 2); c.stroke();
      c.strokeStyle = rgba(GOLD, 0.95);
      c.beginPath(); c.moveTo(qx - 4, qy - 4); c.lineTo(qx + 4, qy + 4); c.moveTo(qx + 4, qy - 4); c.lineTo(qx - 4, qy + 4); c.stroke();
    }

    // what was just asked about: a line from the body to the place the brain answered
    if (s.asked?.place) {
      const f = 1 - (now - s.asked.at) / 2200, [ax, ay] = S(s.asked.place);
      c.save();
      c.strokeStyle = rgba(GOLD, 0.8 * f); c.lineWidth = 1.4; c.setLineDash([3, 5]);
      c.beginPath(); c.moveTo(eye[0], eye[1]); c.lineTo(ax, ay); c.stroke(); c.setLineDash([]);
      c.beginPath(); c.arc(ax, ay, 16 + 10 * (1 - f), 0, Math.PI * 2); c.stroke();
      c.restore();
    }

    // the tutorial's guide: a ring on what to take hold of, and where to bring it
    if (s.guide) this.guide(c, s.guide, m, now);

    // the camera and the ear
    this.cameraGlyph(c, eye, cam.heading, s.cameraOn, s.selected === 'camera');

    // sounds: rings from where the thing is, and what the ear heard of it
    this.rings = this.rings.filter((r) => now - r.start < 1100);
    for (const r of this.rings) {
      const age = (now - r.start) / 1100, [rx, ry] = S(r.at), [hx2, hy2] = S(r.heard), [ex, ey] = S(r.ear);
      for (let k = 0; k < 3; k++) {
        const t = age * 1.4 - k * 0.18;
        if (t <= 0 || t >= 1) continue;
        c.strokeStyle = rgba(GOLD, 0.7 * (1 - t)); c.lineWidth = 1.5;
        c.beginPath(); c.arc(rx, ry, 6 + t * 0.32 * m, 0, Math.PI * 2); c.stroke();
      }
      c.strokeStyle = rgba(GOLD, 0.5 * (1 - age)); c.lineWidth = 1; c.setLineDash([2, 5]);
      c.beginPath(); c.moveTo(ex, ey); c.lineTo(hx2, hy2); c.stroke(); c.setLineDash([]);
      c.fillStyle = rgba(GOLD, 0.9 * (1 - age)); c.beginPath(); c.arc(hx2, hy2, 3, 0, Math.PI * 2); c.fill();
    }
  }

  guide(c, guide, m, now) {
    const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const beat = calm ? 0.5 : (now % 1500) / 1500;
    const [x, y] = this.toScreen(guide.ring), r = (guide.radius || 0.11) * m;
    c.save();
    c.lineWidth = 1.6;
    c.strokeStyle = `rgba(255,255,255,${calm ? 0.7 : 0.75 * (1 - beat)})`;
    c.beginPath(); c.arc(x, y, r * (calm ? 1 : 0.75 + 0.5 * beat), 0, Math.PI * 2); c.stroke();
    c.strokeStyle = 'rgba(255,255,255,0.5)';
    c.beginPath(); c.arc(x, y, r * 0.75, 0, Math.PI * 2); c.stroke();
    if (guide.turn) {
      // an arc around the body, from the way it faces to the way to turn it
      const from = guide.turn.from, gap = Math.atan2(Math.sin(guide.turn.to - from), Math.cos(guide.turn.to - from));
      const R = 0.34 * m, a0 = -from, a1 = -(from + gap);
      c.setLineDash([4, 5]); c.strokeStyle = 'rgba(255,255,255,0.7)';
      c.beginPath(); c.arc(x, y, R, a0, a1, gap > 0); c.stroke();
      c.setLineDash([]);
      const ex = x + Math.cos(a1) * R, ey = y + Math.sin(a1) * R, tangent = a1 + (gap > 0 ? -Math.PI / 2 : Math.PI / 2);
      c.beginPath();
      c.moveTo(ex, ey); c.lineTo(ex - Math.cos(tangent - 0.5) * 10, ey - Math.sin(tangent - 0.5) * 10);
      c.moveTo(ex, ey); c.lineTo(ex - Math.cos(tangent + 0.5) * 10, ey - Math.sin(tangent + 0.5) * 10);
      c.stroke();
    }
    if (guide.target) {
      const [tx, ty] = this.toScreen(guide.target), d = Math.hypot(tx - x, ty - y);
      c.setLineDash([4, 5]); c.strokeStyle = 'rgba(255,255,255,0.55)';
      c.beginPath(); c.arc(tx, ty, r * 0.7, 0, Math.PI * 2); c.stroke();
      if (d > r * 1.8) {
        const ux = (tx - x) / d, uy = (ty - y) / d;
        const ax = tx - ux * r * 0.9, ay = ty - uy * r * 0.9;
        c.beginPath(); c.moveTo(x + ux * r * 0.95, y + uy * r * 0.95); c.lineTo(ax, ay); c.stroke();
        c.setLineDash([]);
        c.beginPath(); c.moveTo(ax, ay); c.lineTo(ax - ux * 9 - uy * 5, ay - uy * 9 + ux * 5); c.moveTo(ax, ay); c.lineTo(ax - ux * 9 + uy * 5, ay - uy * 9 - ux * 5); c.stroke();
      }
    }
    c.restore();
  }

  shadows(c, w, h, dpr, g, eye, lit, rect) {
    // the camera's field inside the plane, less the lit polygon: what is left is in shadow
    const sc = this.shade;
    if (sc.width !== Math.round(w * dpr) || sc.height !== Math.round(h * dpr)) { sc.width = Math.round(w * dpr); sc.height = Math.round(h * dpr); }
    const x = sc.getContext('2d');
    x.setTransform(dpr, 0, 0, dpr, 0, 0);
    x.clearRect(0, 0, w, h);
    if (!this.hatch) {
      const tile = document.createElement('canvas'); tile.width = tile.height = 7;
      const t = tile.getContext('2d');
      t.strokeStyle = 'rgba(120,135,190,0.22)'; t.lineWidth = 1;
      t.beginPath(); t.moveTo(-1, 8); t.lineTo(8, -1); t.stroke();
      this.hatch = x.createPattern(tile, 'repeat');
    }
    const cam = g.camera, far = cam.range * this.scale;
    x.save();
    x.beginPath(); x.rect(rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]); x.clip();
    x.beginPath(); x.moveTo(eye[0], eye[1]);
    x.arc(eye[0], eye[1], far, -(cam.heading + cam.fov / 2), -(cam.heading - cam.fov / 2));
    x.closePath();
    x.fillStyle = 'rgba(3,4,10,0.5)'; x.fill();
    x.fillStyle = this.hatch; x.fill();
    x.globalCompositeOperation = 'destination-out';
    x.fillStyle = '#000'; x.strokeStyle = '#000'; x.lineWidth = 1.5;
    x.beginPath(); x.moveTo(eye[0], eye[1]); for (const p of lit) x.lineTo(p[0], p[1]); x.closePath(); x.fill(); x.stroke();
    x.restore();
    c.drawImage(sc, 0, 0, w, h);
  }

  // The belief as it is shown: it flows from one moment's answer to the next, and keeps the
  // path of its last answers.
  flow(s) {
    const b = s.belief, f = this.shown;
    const far = !f || Math.hypot(f.place[0] - b.place[0], f.place[1] - b.place[1]) > 0.5;
    const k = far || this.calm ? 1 : 0.34;
    this.shown = far ? { place: b.place.slice(), sd: b.sd.slice() }
      : { place: [f.place[0] + (b.place[0] - f.place[0]) * k, f.place[1] + (b.place[1] - f.place[1]) * k], sd: [f.sd[0] + (b.sd[0] - f.sd[0]) * k, f.sd[1] + (b.sd[1] - f.sd[1]) * k] };
    const moment = s.record?.moment ?? 0;
    if (moment !== this.trailMoment) {
      this.trailMoment = moment;
      this.trail.push(b.place.slice());
      if (this.trail.length > 36) this.trail.shift();
    }
    return this.shown;
  }

  // The haze: the answer's own spread, drawn as light. The same light lies over a small area or
  // a large one, so a sure answer is a bright spot and an unsure one a wide, faint glow.
  haze(c, belief, m) {
    const [bx, by] = this.toScreen(belief.place), k = radiusAt(RATE);
    const rx = Math.max(9, k * belief.sd[0] * m), ry = Math.max(9, k * belief.sd[1] * m);
    const dense = clamp(Math.sqrt((34 * 34) / (rx * ry)), 0.16, 1);
    c.save();
    c.globalCompositeOperation = 'lighter';
    c.translate(bx, by); c.scale(rx, ry);
    const light = c.createRadialGradient(0, 0, 0, 0, 0, 1.75);
    light.addColorStop(0, rgba([170, 255, 244], 0.7 * dense)); light.addColorStop(0.3, rgba(TEAL, 0.42 * dense));
    light.addColorStop(0.62, rgba(TEAL, 0.17 * dense)); light.addColorStop(1, rgba(TEAL, 0));
    c.fillStyle = light; c.beginPath(); c.arc(0, 0, 1.75, 0, Math.PI * 2); c.fill();
    c.restore();
  }

  // The ring of doubt (the area that holds the hand at the stated rate), the path of the last
  // answers and the peak itself.
  peak(c, s, belief, m) {
    const [bx, by] = this.toScreen(belief.place), k = radiusAt(RATE);
    const rx = Math.max(7, k * belief.sd[0] * m), ry = Math.max(7, k * belief.sd[1] * m);
    c.save();
    c.globalCompositeOperation = 'lighter';
    // the path of the last answers, fading
    if (this.trail.length > 1) {
      c.lineCap = 'round'; c.lineJoin = 'round';
      for (let i = 1; i < this.trail.length; i++) {
        const a = this.toScreen(this.trail[i - 1]), b = this.toScreen(this.trail[i]), f = i / this.trail.length;
        if (Math.hypot(a[0] - b[0], a[1] - b[1]) > 0.4 * m) continue;
        c.strokeStyle = rgba(TEAL, 0.5 * f * f); c.lineWidth = 1 + 2.2 * f;
        c.beginPath(); c.moveTo(a[0], a[1]); c.lineTo(b[0], b[1]); c.stroke();
      }
    }
    // the ring
    c.shadowColor = rgba(TEAL, 0.9); c.shadowBlur = 12;
    c.strokeStyle = rgba([150, 250, 238], 0.85); c.lineWidth = 1.5;
    c.beginPath(); c.ellipse(bx, by, rx, ry, 0, 0, Math.PI * 2); c.stroke();
    c.shadowBlur = 0;
    // the peak
    const r = clamp(Math.min(rx, ry) * 0.7, 9, 20);
    const core = c.createRadialGradient(bx, by, 0, bx, by, r);
    core.addColorStop(0, 'rgba(255,255,255,0.98)'); core.addColorStop(0.28, rgba([170, 255, 244], 0.8)); core.addColorStop(1, rgba(TEAL, 0));
    c.fillStyle = core; c.beginPath(); c.arc(bx, by, r, 0, Math.PI * 2); c.fill();
    c.restore();
    if (s.showHidden && s.record && !s.record.in_view[0]) {
      // while the hand is hidden: a thin line from the belief to where the hand really is
      const [tx, ty] = this.toScreen(s.record.truth[0]);
      c.strokeStyle = 'rgba(255,255,255,0.4)'; c.setLineDash([2, 4]); c.lineWidth = 1;
      c.beginPath(); c.moveTo(bx, by); c.lineTo(tx, ty); c.stroke(); c.setLineDash([]);
    }
  }

  arm(c, g, joints, m, own) {
    const chain = forward(g, joints).map((p) => this.toScreen(p));
    const width = Math.max(5, g.arm.width * m);
    c.lineCap = 'round'; c.lineJoin = 'round';
    const path = () => { c.beginPath(); c.moveTo(chain[0][0], chain[0][1]); for (const p of chain.slice(1)) c.lineTo(p[0], p[1]); };
    path(); c.strokeStyle = 'rgba(4,6,12,0.9)'; c.lineWidth = width + 4; c.stroke();
    path(); c.strokeStyle = '#34405f'; c.lineWidth = width; c.stroke();
    path(); c.strokeStyle = 'rgba(170,190,240,0.32)'; c.lineWidth = width * 0.3; c.stroke();
    // the base and the joints
    const [bx, by] = chain[0];
    c.fillStyle = '#1b2236'; c.strokeStyle = 'rgba(170,185,225,0.6)'; c.lineWidth = 1.4;
    c.beginPath();
    for (let k = 0; k < 6; k++) { const a = (Math.PI / 3) * k + Math.PI / 6; c[k ? 'lineTo' : 'moveTo'](bx + Math.cos(a) * width * 1.15, by + Math.sin(a) * width * 1.15); }
    c.closePath(); c.fill(); c.stroke();
    chain.forEach((p, k) => {
      const tip = k === chain.length - 1;
      c.beginPath(); c.arc(p[0], p[1], tip ? width * 0.42 : width * 0.5, 0, Math.PI * 2);
      c.fillStyle = tip ? (own ? rgba(ORANGE, 0.95) : '#55628a') : '#11172a'; c.fill();
      c.strokeStyle = tip && own ? 'rgba(255,220,180,0.9)' : rgba(ORANGE, 0.75); c.lineWidth = 1.3; c.stroke();
    });
    c.lineCap = 'butt';
  }

  // A hand seen from above: a wrist, a palm, four fingers and a thumb. In view it is solid and
  // lit. Out of view it is what is really there: the same hand as a clear outline, unlit.
  hand(c, s, at, m) {
    const inView = !!s.record?.in_view?.[0];
    if (!inView && !s.showHidden) return;
    const [x, y] = this.toScreen(at);
    if (s.own) {
      if (!inView) {
        c.save();
        c.fillStyle = rgba(ORANGE, 0.16); c.strokeStyle = 'rgba(255,205,160,0.9)'; c.lineWidth = 1.4;
        c.beginPath(); c.arc(x, y, 0.045 * m, 0, Math.PI * 2); c.fill(); c.stroke();
        c.restore();
      }
      return;
    }
    const u = 0.066 * m;
    // the hand points the way it last moved
    if (s.previous && s.record) {
      const dx = s.record.truth[0][0] - s.previous.truth[0][0], dy = s.record.truth[0][1] - s.previous.truth[0][1];
      if (Math.hypot(dx, dy) > 0.002) {
        const want = Math.atan2(dx, dy);
        let turn = want - (this.handAngle ?? want);
        turn = Math.atan2(Math.sin(turn), Math.cos(turn));
        this.handAngle = (this.handAngle ?? want) + turn * (this.calm ? 1 : 0.1);
      }
    }
    // the pieces, each its own shape so that the fingers part
    const pieces = [];
    const piece = (make) => { const path = new Path2D(); make(path); pieces.push(path); };
    piece((q) => q.roundRect(-u * 0.42, u * 0.55, u * 0.84, u * 0.85, u * 0.3));            // the wrist
    piece((q) => q.roundRect(-u * 0.68, -u * 0.42, u * 1.36, u * 1.28, u * 0.46));           // the palm
    [[-0.51, 0.95], [-0.17, 1.2], [0.17, 1.12], [0.5, 0.86]].forEach(([fx, len]) =>
      piece((q) => q.roundRect(fx * u - u * 0.145, -u * 0.38 - len * u, u * 0.29, len * u + u * 0.2, u * 0.145)));
    piece((q) => {                                                                           // the thumb
      const t = new DOMMatrix().translate(-u * 0.62, u * 0.34).rotate(0, 0, -52);
      const thumb = new Path2D(); thumb.roundRect(-u * 0.16, -u * 0.86, u * 0.32, u * 0.95, u * 0.16);
      q.addPath(thumb, t);
    });
    c.save();
    c.translate(x, y); c.rotate(this.handAngle ?? 0);
    if (inView) {
      c.shadowColor = rgba(ORANGE, 0.8); c.shadowBlur = 18;
      c.fillStyle = rgba(ORANGE, 1);
      for (const q of pieces) c.fill(q);
      c.shadowBlur = 0;
      const skin = c.createLinearGradient(0, -u * 1.6, 0, u * 1.4);
      skin.addColorStop(0, '#ffc48a'); skin.addColorStop(1, '#ff8f3a');
      c.fillStyle = skin; c.strokeStyle = 'rgba(120,52,8,0.55)'; c.lineWidth = 1;
      for (const q of pieces) { c.fill(q); c.stroke(q); }
    } else {
      // what is really there, behind the shadow: unlit, but plain to see
      c.shadowColor = 'rgba(0,0,0,0.9)'; c.shadowBlur = 6;
      c.fillStyle = 'rgba(255,170,100,0.20)'; c.strokeStyle = 'rgba(255,208,165,0.92)'; c.lineWidth = 1.35;
      for (const q of pieces) c.fill(q);
      c.shadowBlur = 0;
      for (const q of pieces) c.stroke(q);
    }
    if (s.selected === 'hand') { c.strokeStyle = 'rgba(255,255,255,0.85)'; c.lineWidth = 1.2; c.beginPath(); c.arc(0, -u * 0.2, u * 2.0, 0, Math.PI * 2); c.stroke(); }
    c.restore();
  }

  thing(c, s, k, at, m) {
    const name = s.names[k], inView = !!s.record?.in_view?.[k];
    if (!inView && !s.showHidden) return;
    const [x, y] = this.toScreen(at), u = (name === 'cup' ? 0.05 : 0.058) * m;
    c.save();
    c.translate(x, y);
    glyph(c, name, u, inView);
    if (s.selected === name) { c.strokeStyle = 'rgba(255,255,255,0.85)'; c.lineWidth = 1.2; c.beginPath(); c.arc(0, 0, u * 1.9, 0, Math.PI * 2); c.stroke(); }
    c.restore();
  }

  // The record of a thing: a pin where the brain holds it. Solid while the record came from
  // sight, dashed while it came from a sound.
  pin(c, s, k, truth) {
    const name = s.names[k], rec = s.pins?.[name];
    if (!rec?.place) return;
    const [x, y] = this.toScreen(rec.place), color = THING_COLOR[name] || [200, 200, 220];
    const off = Math.hypot(rec.place[0] - truth[0], rec.place[1] - truth[1]);
    const inView = !!s.record?.in_view?.[k];
    if (inView && off < 0.03) return; // the pin sits on the thing the camera sees
    c.save();
    if (s.showHidden && off > 0.03) {
      const [tx, ty] = this.toScreen(truth);
      c.strokeStyle = rgba(color, 0.4); c.setLineDash([2, 4]); c.lineWidth = 1;
      c.beginPath(); c.moveTo(x, y); c.lineTo(tx, ty); c.stroke(); c.setLineDash([]);
    }
    const heard = rec.from === 'heard';
    c.strokeStyle = rgba(color, 0.95); c.fillStyle = rgba(color, 0.9); c.lineWidth = 1.5;
    c.beginPath(); c.moveTo(x, y); c.lineTo(x, y - 15); c.stroke();
    if (heard) c.setLineDash([2, 2]);
    c.beginPath(); c.arc(x, y - 21, 7.5, 0, Math.PI * 2);
    c.fillStyle = 'rgba(8,11,20,0.9)'; c.fill(); c.stroke(); c.setLineDash([]);
    c.fillStyle = rgba(color, 0.95);
    c.beginPath(); c.arc(x, y, 2.2, 0, Math.PI * 2); c.fill();
    c.translate(x - (name === 'cup' ? 0.8 : 0), y - 21 + (name === 'cup' ? 0 : 0.6));
    glyph(c, name, name === 'cup' ? 3.1 : 3.6, false);
    c.restore();
  }

  // The body, which carries the camera: a round body with its eye where it faces.
  cameraGlyph(c, eye, heading, on, selected) {
    c.save();
    c.translate(eye[0], eye[1]); c.rotate(-heading);
    c.lineWidth = 1.5;
    c.fillStyle = '#1a2136'; c.strokeStyle = selected ? 'rgba(255,255,255,0.95)' : on ? 'rgba(150,225,255,0.95)' : 'rgba(120,130,160,0.75)';
    if (on) { c.shadowColor = 'rgba(150,235,255,0.7)'; c.shadowBlur = 12; }
    c.beginPath(); c.arc(0, 0, 13, 0, Math.PI * 2); c.fill(); c.stroke();
    c.shadowBlur = 0;
    // the eye, at the front
    c.beginPath(); c.moveTo(6, -6.5); c.lineTo(17, -9); c.lineTo(17, 9); c.lineTo(6, 6.5); c.closePath();
    c.fillStyle = '#222b45'; c.fill(); c.stroke();
    c.fillStyle = on ? 'rgba(170,240,255,0.98)' : 'rgba(90,100,130,0.85)';
    if (on) { c.shadowColor = 'rgba(150,235,255,0.95)'; c.shadowBlur = 10; }
    c.beginPath(); c.arc(12.5, 0, 3, 0, Math.PI * 2); c.fill();
    c.shadowBlur = 0;
    // its back: a small mark, so that behind reads as behind
    c.strokeStyle = 'rgba(150,165,210,0.5)'; c.beginPath(); c.arc(0, 0, 8.5, Math.PI * 0.72, Math.PI * 1.28); c.stroke();
    // a grip ahead of it: the camera turns
    c.strokeStyle = 'rgba(190,225,255,0.4)'; c.lineWidth = 1.2;
    c.beginPath(); c.arc(0, 0, 30, -0.42, 0.42); c.stroke();
    for (const side of [-1, 1]) {
      const a = 0.42 * side, x = 30 * Math.cos(a), y = 30 * Math.sin(a), t = a + (side * Math.PI) / 2;
      c.beginPath(); c.moveTo(x - Math.cos(t - 0.6) * 5, y - Math.sin(t - 0.6) * 5); c.lineTo(x, y); c.lineTo(x - Math.cos(t + 0.6) * 5, y - Math.sin(t + 0.6) * 5); c.stroke();
    }
    c.restore();
  }

  /** What lies under a point of the canvas: a thing's name, 'pillar', 'camera' or null. */
  hit(x, y, s) {
    const m = this.scale, near = (p, r) => { const q = this.toScreen(p); return Math.hypot(q[0] - x, q[1] - y) <= r; };
    const things = s.record ? s.record.truth : s.things;
    if (!s.own && near(things[0], 0.1 * m)) return 'hand';
    for (let k = 1; k < things.length; k++) if (near(things[k], 0.085 * m)) return s.names[k];
    for (const o of s.geometry.occluders) if (near(o.center, o.radius * m + 8)) return 'pillar';
    if (near(s.geometry.camera.position, 20)) return 'camera';
    return null;
  }
}

/** The map the brain holds: the place answer drawn over the plane, straight from the place
 *  units' readout (each axis one softmax; the map is their product), with the records' pins. */
export class MapView {
  constructor(canvas) { this.canvas = canvas; this.image = null; this.buffer = document.createElement('canvas'); }

  draw(s) {
    const { c, w, h } = fit(this.canvas);
    c.clearRect(0, 0, w, h);
    const [lx, hx, ly, hy] = s.geometry.plane;
    const pad = 14, mw = w - 2 * pad - 6, mh = h - 2 * pad - 8;
    const scale = Math.min(mw / (hx - lx), mh / (hy - ly));
    const x0 = pad + 6 + (mw - (hx - lx) * scale) / 2, y0 = 6 + (mh - (hy - ly) * scale) / 2;
    const W = (hx - lx) * scale, H = (hy - ly) * scale;
    const P = (p) => [x0 + (p[0] - lx) * scale, y0 + H - (p[1] - ly) * scale];
    c.fillStyle = '#080b15'; c.beginPath(); c.roundRect(x0, y0, W, H, 6); c.fill();
    const sheet = s.sheet;
    if (sheet?.px) {
      const k = sheet.px.length, kb = this.buffer;
      if (kb.width !== k) { kb.width = k; kb.height = k; }
      const bc = kb.getContext('2d');
      const img = bc.createImageData(k, k);
      let max = 1e-9;
      for (let j = 0; j < k; j++) for (let i = 0; i < k; i++) max = Math.max(max, sheet.px[i] * sheet.py[j]);
      for (let j = 0; j < k; j++) {
        for (let i = 0; i < k; i++) {
          const v = Math.pow((sheet.px[i] * sheet.py[j]) / max, 0.6) * Math.min(1, max * k * 0.9 + 0.25);
          const o = 4 * ((k - 1 - j) * k + i);
          img.data[o] = 63 + 150 * v * v; img.data[o + 1] = 224 + 31 * v * v; img.data[o + 2] = 207 + 40 * v * v; img.data[o + 3] = 255 * clamp(v, 0, 1);
        }
      }
      bc.putImageData(img, 0, 0);
      c.save();
      c.beginPath(); c.roundRect(x0, y0, W, H, 6); c.clip();
      c.imageSmoothingEnabled = true; c.imageSmoothingQuality = 'high';
      // unit i is centred on its preferred value: the image spans half a bin beyond the plane
      const bw = W / (k - 1), bh = H / (k - 1);
      c.drawImage(kb, x0 - bw / 2, y0 - bh / 2, W + bw, H + bh);
      c.restore();
      // the two axes' readouts along the edges
      c.fillStyle = rgba(TEAL, 0.85);
      let mx = 1e-9, my = 1e-9;
      for (let i = 0; i < k; i++) { mx = Math.max(mx, sheet.px[i]); my = Math.max(my, sheet.py[i]); }
      for (let i = 0; i < k; i++) {
        const bx = x0 + (i / (k - 1)) * W, hgt = (sheet.px[i] / mx) * 10;
        c.fillRect(bx - bw * 0.3, y0 + H + 3, bw * 0.6, Math.max(0.6, hgt));
        const byy = y0 + H - (i / (k - 1)) * H, wid = (sheet.py[i] / my) * 10;
        c.fillRect(x0 - 3 - Math.max(0.6, wid), byy - bh * 0.3, Math.max(0.6, wid), bh * 0.6);
      }
    }
    c.strokeStyle = 'rgba(150,165,210,0.3)'; c.lineWidth = 1; c.beginPath(); c.roundRect(x0, y0, W, H, 6); c.stroke();
    // the camera's corner, for orientation
    const [cx, cy] = P(s.geometry.camera.position);
    c.fillStyle = 'rgba(150,225,255,0.7)'; c.beginPath(); c.arc(clamp(cx, x0 + 3, x0 + W - 3), clamp(cy, y0 + 3, y0 + H - 3), 2.2, 0, Math.PI * 2); c.fill();
    // the records' pins
    for (const [name, rec] of Object.entries(s.pins || {})) {
      if (!rec?.place) continue;
      const [px, py] = P(rec.place), color = THING_COLOR[name] || [200, 200, 220];
      c.strokeStyle = rgba(color, 0.95); c.fillStyle = 'rgba(8,11,20,0.9)'; c.lineWidth = 1.3;
      if (rec.from === 'heard') c.setLineDash([2, 2]);
      c.beginPath(); c.arc(px, py, 7, 0, Math.PI * 2); c.fill(); c.stroke(); c.setLineDash([]);
      c.save(); c.translate(px, py); glyph(c, name, 3, false); c.restore();
    }
    if (s.belief?.place) {
      const [bx, by] = P(s.belief.place);
      c.strokeStyle = 'rgba(220,255,250,0.95)'; c.lineWidth = 1;
      c.beginPath(); c.moveTo(bx - 4, by); c.lineTo(bx + 4, by); c.moveTo(bx, by - 4); c.lineTo(bx, by + 4); c.stroke();
    }
  }
}

/** Each estimate's distance from the true hand over the last moments; the moments the hand was
 *  out of view are shaded. */
export class ChartView {
  constructor(canvas, { span = 300, top = 0.6 } = {}) { this.canvas = canvas; this.span = span; this.top = top; }

  draw(history, { compare = true, dt = 1 / 30 } = {}) {
    const { c, w, h } = fit(this.canvas);
    c.clearRect(0, 0, w, h);
    const left = 34, right = 8, topPad = 8, bottom = 16;
    const W = w - left - right, H = h - topPad - bottom, n = this.span;
    const X = (k) => left + (k / (n - 1)) * W;
    // a square-root axis: centimetres near zero stay readable beside half a metre
    const Y = (v) => topPad + H - Math.sqrt(clamp(v, 0, this.top) / this.top) * H;
    const rows = history.slice(-n), start = n - rows.length;
    c.fillStyle = 'rgba(8,11,21,0.9)'; c.beginPath(); c.roundRect(left, topPad, W, H, 4); c.fill();
    // out of view
    c.fillStyle = 'rgba(120,135,190,0.13)';
    let from = -1;
    rows.forEach((r, k) => {
      if (!r.seen && from < 0) from = k;
      if ((r.seen || k === rows.length - 1) && from >= 0) {
        const to = r.seen ? k : k + 1;
        c.fillRect(X(start + from), topPad, Math.max(1, X(start + to) - X(start + from)), H); from = -1;
      }
    });
    c.font = '500 9.5px "JetBrains Mono", ui-monospace, monospace'; c.textBaseline = 'middle'; c.textAlign = 'right';
    for (const v of [0, 0.05, 0.2, 0.6]) {
      if (v > this.top) continue;
      c.strokeStyle = 'rgba(120,140,200,0.12)'; c.beginPath(); c.moveTo(left, Y(v)); c.lineTo(left + W, Y(v)); c.stroke();
      c.fillStyle = 'rgba(141,151,178,0.9)'; c.fillText(`${Math.round(v * 100)}`, left - 5, Y(v));
    }
    c.textAlign = 'left'; c.fillText('cm', 2, topPad + 4);
    const line = (key, color, width) => {
      c.strokeStyle = color; c.lineWidth = width; c.lineJoin = 'round';
      c.beginPath();
      let pen = false;
      rows.forEach((r, k) => {
        const v = r[key];
        if (v === null || v === undefined) { pen = false; return; }
        c[pen ? 'lineTo' : 'moveTo'](X(start + k), Y(v)); pen = true;
      });
      c.stroke();
    };
    if (compare) { line('last', rgba(GOLD, 0.9), 1.1); line('kalman', rgba(VIOLET, 0.95), 1.1); }
    line('brain', rgba(TEAL, 1), 1.8);
    c.fillStyle = 'rgba(141,151,178,0.8)'; c.textAlign = 'right'; c.textBaseline = 'alphabetic';
    c.fillText(`the last ${Math.round(n * dt)} s`, left + W, h - 3);
  }
}

/** The map as the body has it. "Around me": the body at the centre, facing up, and every thing
 *  the brain holds a record of at its direction and distance, inside a soft ring as wide as the
 *  record's own spread; the hand's answer with its ring. "Room": the same map over the room. A
 *  tap on a thing asks where it is; a tap on an empty direction asks what is there. */
export class AroundView {
  constructor(canvas) { this.canvas = canvas; this.marks = []; this.reach = 1.35; this.mode = 'me'; this.asked = null; }

  /** A tapped direction is shown for a moment: { bearing, start }. */
  ask(bearing) { this.asked = { bearing, start: performance.now() }; }

  draw(s, now = performance.now()) {
    const { c, w, h } = fit(this.canvas);
    c.clearRect(0, 0, w, h);
    this.marks = [];
    this.size = [w, h];
    if (this.mode === 'room') { this.room(c, s, w, h); return; }
    const cx = w / 2, cy = h / 2, R = Math.min(w, h) / 2 - 2, k = R / this.reach, fov = s.geometry.camera.fov;
    c.save();
    c.beginPath(); c.arc(cx, cy, R, 0, Math.PI * 2);
    c.fillStyle = 'rgba(8,11,21,0.94)'; c.fill();
    c.clip();
    if (s.cameraOn) {
      // what the camera sees lies ahead: up
      const light = c.createRadialGradient(cx, cy, 0, cx, cy, R);
      light.addColorStop(0, 'rgba(150,225,255,0.3)'); light.addColorStop(1, 'rgba(90,150,255,0.06)');
      c.fillStyle = light;
      c.beginPath(); c.moveTo(cx, cy); c.arc(cx, cy, R, -Math.PI / 2 - fov / 2, -Math.PI / 2 + fov / 2); c.closePath(); c.fill();
    }
    c.strokeStyle = 'rgba(130,150,210,0.16)'; c.lineWidth = 1;
    for (const ring of [0.5, 1.0]) { c.beginPath(); c.arc(cx, cy, ring * k, 0, Math.PI * 2); c.stroke(); }
    if (this.asked && now - this.asked.start < 1600) {
      // the direction just asked about
      const f = 1 - (now - this.asked.start) / 1600, a = -Math.PI / 2 - this.asked.bearing;
      c.fillStyle = `rgba(255,206,102,${0.22 * f})`;
      c.beginPath(); c.moveTo(cx, cy); c.arc(cx, cy, R, a - 0.45, a + 0.45); c.closePath(); c.fill();
    }
    // a thing further than the map reaches is drawn at its rim, in its direction
    const at = (rel) => { const r = Math.min(this.reach * 0.9, rel.distance) * k; return [cx - Math.sin(rel.bearing) * r, cy - Math.cos(rel.bearing) * r]; };
    for (let i = 1; i < s.names.length; i++) {
      const name = s.names[i], pin = s.pins?.[name];
      if (!pin?.place) continue;
      const [x, y] = at(around(s.geometry, pin.place)), color = THING_COLOR[name] || [200, 200, 220];
      const ring = clamp(radiusAt(RATE) * (pin.spread ?? 0.01) * k, 9.5, R * 0.6);
      const soft = c.createRadialGradient(x, y, 0, x, y, ring * 1.25);
      soft.addColorStop(0, rgba(color, 0.42)); soft.addColorStop(0.7, rgba(color, 0.14)); soft.addColorStop(1, rgba(color, 0));
      c.fillStyle = soft; c.beginPath(); c.arc(x, y, ring * 1.25, 0, Math.PI * 2); c.fill();
      if (pin.from === 'heard') { c.setLineDash([2, 3]); c.strokeStyle = rgba(color, 0.7); c.beginPath(); c.arc(x, y, ring, 0, Math.PI * 2); c.stroke(); c.setLineDash([]); }
      c.save(); c.translate(x, y); glyph(c, name, name === 'cup' ? 4.6 : 5.4, !!s.record?.in_view?.[i]); c.restore();
      this.marks.push({ name, x, y });
    }
    if (s.belief?.place) {
      // the hand: the brain's answer and its ring of doubt
      const [x, y] = at(around(s.geometry, s.belief.place));
      const ring = clamp(radiusAt(RATE) * Math.sqrt(s.belief.sd[0] * s.belief.sd[1]) * k, 4, R * 0.95);
      c.strokeStyle = rgba(TEAL, 0.7); c.lineWidth = 1.1; c.beginPath(); c.arc(x, y, ring, 0, Math.PI * 2); c.stroke();
      c.fillStyle = 'rgba(200,255,248,0.98)'; c.shadowColor = rgba(TEAL, 0.9); c.shadowBlur = 8;
      c.beginPath(); c.arc(x, y, 3, 0, Math.PI * 2); c.fill(); c.shadowBlur = 0;
      this.marks.push({ name: 'hand', x, y });
    }
    // the body, facing up
    c.fillStyle = 'rgba(214,228,255,0.96)'; c.strokeStyle = 'rgba(8,11,21,0.9)'; c.lineWidth = 1;
    c.beginPath(); c.moveTo(cx, cy - 7.5); c.lineTo(cx + 5.5, cy + 5.5); c.lineTo(cx, cy + 2.8); c.lineTo(cx - 5.5, cy + 5.5); c.closePath(); c.fill(); c.stroke();
    c.restore();
    c.strokeStyle = 'rgba(150,165,210,0.4)'; c.lineWidth = 1.1; c.beginPath(); c.arc(cx, cy, R, 0, Math.PI * 2); c.stroke();
    this.dial = { cx, cy, R };
  }

  // the same map over the room: the body where it stands, facing the way it faces
  room(c, s, w, h) {
    const [lx, hx, ly, hy] = s.geometry.plane, pad = 3;
    const k = Math.min((w - 2 * pad) / (hx - lx), (h - 2 * pad) / (hy - ly));
    const x0 = (w - (hx - lx) * k) / 2, y0 = (h - (hy - ly) * k) / 2;
    const P = (p) => [x0 + (p[0] - lx) * k, y0 + (hy - p[1]) * k];
    this.plane = { toPlane: (x, y) => [lx + (x - x0) / k, hy - (y - y0) / k] };
    c.save();
    c.fillStyle = 'rgba(8,11,21,0.94)'; c.beginPath(); c.roundRect(x0, y0, (hx - lx) * k, (hy - ly) * k, 5); c.fill(); c.clip();
    const cam = s.geometry.camera, [bx, by] = P(cam.position);
    if (s.cameraOn) {
      const light = c.createRadialGradient(bx, by, 0, bx, by, cam.range * k * 0.7);
      light.addColorStop(0, 'rgba(150,225,255,0.3)'); light.addColorStop(1, 'rgba(90,150,255,0.05)');
      c.fillStyle = light;
      c.beginPath(); c.moveTo(bx, by); c.arc(bx, by, cam.range * k, -(cam.heading + cam.fov / 2), -(cam.heading - cam.fov / 2)); c.closePath(); c.fill();
    }
    for (let i = 1; i < s.names.length; i++) {
      const name = s.names[i], pin = s.pins?.[name];
      if (!pin?.place) continue;
      const [x, y] = P(pin.place), color = THING_COLOR[name] || [200, 200, 220];
      const ring = clamp(radiusAt(RATE) * (pin.spread ?? 0.01) * k, 7, 40);
      const soft = c.createRadialGradient(x, y, 0, x, y, ring * 1.25);
      soft.addColorStop(0, rgba(color, 0.42)); soft.addColorStop(1, rgba(color, 0));
      c.fillStyle = soft; c.beginPath(); c.arc(x, y, ring * 1.25, 0, Math.PI * 2); c.fill();
      c.save(); c.translate(x, y); glyph(c, name, name === 'cup' ? 3.4 : 4, !!s.record?.in_view?.[i]); c.restore();
      this.marks.push({ name, x, y });
    }
    if (s.belief?.place) {
      const [x, y] = P(s.belief.place), u = radiusAt(RATE);
      c.strokeStyle = rgba(TEAL, 0.7); c.lineWidth = 1.1;
      c.beginPath(); c.ellipse(x, y, Math.max(4, u * s.belief.sd[0] * k), Math.max(4, u * s.belief.sd[1] * k), 0, 0, Math.PI * 2); c.stroke();
      c.fillStyle = 'rgba(200,255,248,0.98)'; c.beginPath(); c.arc(x, y, 2.8, 0, Math.PI * 2); c.fill();
      this.marks.push({ name: 'hand', x, y });
    }
    c.translate(bx, by); c.rotate(Math.PI / 2 - cam.heading);
    c.fillStyle = 'rgba(214,228,255,0.96)'; c.strokeStyle = 'rgba(8,11,21,0.9)'; c.lineWidth = 1;
    c.beginPath(); c.moveTo(0, -7); c.lineTo(5, 5); c.lineTo(0, 2.6); c.lineTo(-5, 5); c.closePath(); c.fill(); c.stroke();
    c.restore();
    c.strokeStyle = 'rgba(150,165,210,0.4)'; c.lineWidth = 1.1; c.beginPath(); c.roundRect(x0, y0, (hx - lx) * k, (hy - ly) * k, 5); c.stroke();
    this.dial = null;
  }

  /** The thing drawn under a point of the canvas, or null. */
  hit(x, y) {
    let best = null, near = 15;
    for (const mark of this.marks) { const d = Math.hypot(mark.x - x, mark.y - y); if (d < near) { near = d; best = mark.name; } }
    return best;
  }

  /** The point of the room that a point of the canvas stands for (within the map's reach). */
  pointAt(x, y, geometry) {
    if (!this.dial) return this.plane ? this.plane.toPlane(x, y) : null;
    const d = this.dial, far = (Math.hypot(x - d.cx, y - d.cy) / d.R) * this.reach;
    if (far > this.reach * 0.9) return null; // the rim stands for everything further
    const a = geometry.camera.heading + this.bearingAt(x, y, geometry);
    return [geometry.camera.position[0] + far * Math.cos(a), geometry.camera.position[1] + far * Math.sin(a)];
  }

  /** The bearing, from the way the body faces, that a point of the canvas stands for. */
  bearingAt(x, y, geometry) {
    if (this.dial) return Math.atan2(-(x - this.dial.cx), -(y - this.dial.cy));
    return this.plane ? around(geometry, this.plane.toPlane(x, y)).bearing : 0;
  }
}
