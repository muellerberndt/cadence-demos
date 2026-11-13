// The scene from above and the error chart: two Canvas2D views.
//
// SceneView draws the plane as it is (the arm, the hand, the things, the camera's light and its
// shadows) and, on top, what the brain's map holds at this moment: every thing on the map as a
// soft patch of its cells with a pin at its place, and the hand as the scene's hero, a glowing
// peak over its cells. ChartView draws the hand's distance from the true hand over the last
// moments, beside last seen and the Kalman filter.

import { forward, litPolygon, cartesian } from './world.js';
import { contour, sheetImage } from './region.js';

const TEAL = [63, 224, 207], ORANGE = [255, 159, 74], GOLD = [255, 206, 102], VIOLET = [183, 156, 255];
export const THING_COLOR = { hand: ORANGE, own: ORANGE, cup: [127, 212, 255], apple: [255, 104, 116], bread: [236, 190, 124] };

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
    this.trail = [];  // the hand's last places on the map
    this.shown = null; // the hand's place as it is drawn, flowing toward the latest one
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
   *  between moments), the map's inventory at this moment and the page's toggles. */
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

    // what the map holds: each thing's cells as soft light, under everything on the table
    const entries = s.inventory || [], hand = s.hand;
    for (const e of entries) if (e.area) this.region(c, e.area, e === hand ? TEAL : (THING_COLOR[e.name] || TEAL), e === hand ? 1 : 0.7);
    c.restore();
    c.strokeStyle = 'rgba(150,165,210,0.28)'; c.lineWidth = 1.2;
    c.beginPath(); c.roundRect(x0, y0, x1 - x0, y1 - y0, 10); c.stroke();

    // the occluding discs
    for (const o of g.occluders) {
      const [ox, oy] = S(o.center), r = o.radius * m;
      const disc = c.createRadialGradient(ox - r * 0.3, oy - r * 0.3, r * 0.1, ox, oy, r);
      disc.addColorStop(0, '#39425e'); disc.addColorStop(1, '#161b2c');
      c.fillStyle = disc; c.beginPath(); c.arc(ox, oy, r, 0, Math.PI * 2); c.fill();
      c.strokeStyle = s.selected === 'pillar' ? 'rgba(255,255,255,0.9)' : 'rgba(170,185,225,0.55)'; c.lineWidth = 1.4; c.stroke();
    }

    // the things on the table as they are, the arm and the hand as they are, and over them the
    // map's pins for every thing but the hand
    this.words = []; // the words on the table: drawn last, over every piece of the scene
    for (let k = 1; k < things.length; k++) this.thing(c, s, k, things[k], m);
    this.arm(c, g, joints, m, s.own);
    this.hand(c, s, things[0], m);
    c.save(); c.beginPath(); c.roundRect(x0, y0, x1 - x0, y1 - y0, 10); c.clip(); // a pin's edge stays in the room
    for (const e of entries) if (e !== hand && e.place) this.pin(c, s, e, things);
    c.restore();

    // the hand as the map holds it: the brightest thing on the table
    c.save(); c.beginPath(); c.roundRect(x0, y0, x1 - x0, y1 - y0, 10); c.clip();
    if (hand?.place) this.peak(c, s, hand, things[0], m);
    c.restore();

    // the comparison's markers (Details)
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

    // what was just asked about: a line from the body to the place the map answered
    if (s.asked?.place) {
      const fade = 1 - (now - s.asked.at) / 2200, [ax, ay] = S(s.asked.place);
      c.save();
      c.strokeStyle = rgba(GOLD, 0.8 * fade); c.lineWidth = 1.4; c.setLineDash([3, 5]);
      c.beginPath(); c.moveTo(eye[0], eye[1]); c.lineTo(ax, ay); c.stroke(); c.setLineDash([]);
      c.beginPath(); c.arc(ax, ay, 16 + 10 * (1 - fade), 0, Math.PI * 2); c.stroke();
      c.restore();
    }

    // the tutorial's guide: a ring on what to take hold of, and where to bring it
    if (s.guide) this.guide(c, s.guide, m, now);

    // the camera, and quiet names on the robot and its arm
    this.cameraGlyph(c, eye, cam.heading, s.cameraOn, s.selected === 'camera');
    const base = S(g.arm.base);
    this.name(c, 'robot', eye[0], eye[1] + 26);
    this.name(c, 'robot’s arm', base[0], base[1] + Math.max(5, g.arm.width * m) * 1.15 + 13);

    // the words on the table, over everything
    for (const [text, x, y, color] of this.words) this.word(c, text, x, y, color);

    // beside the mouse: what a drag and a click do here
    if (s.hint) this.hintChip(c, s.hint, w, h);

    // sounds (a scene file may hold them): rings from where the thing is, and what the ear heard of it
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

  // A thing's cells as soft light: each cell by its activity on the map, with the edge of its
  // cells drawn around them. A thing in doubt may lie in two patches.
  region(c, sheet, tint, strength = 1) {
    const [x0, y1] = this.toScreen([sheet.plane[0], sheet.plane[2]]), [x1, y0] = this.toScreen([sheet.plane[1], sheet.plane[3]]);
    c.save();
    c.globalCompositeOperation = 'lighter';
    c.globalAlpha = strength;
    c.imageSmoothingEnabled = true; c.imageSmoothingQuality = 'high';
    c.drawImage(sheetImage(sheet, this.cellsCanvas(tint), tint), x0, y0, x1 - x0, y1 - y0);
    c.restore();
  }
  cellsCanvas(tint) {
    this.canvases = this.canvases || new Map();
    const key = tint.join();
    if (!this.canvases.has(key)) this.canvases.set(key, document.createElement('canvas'));
    return this.canvases.get(key);
  }

  // The edge of a thing's cells.
  regionEdge(c, sheet, tint, alpha = 0.8) {
    c.save();
    c.globalCompositeOperation = 'lighter';
    c.shadowColor = rgba(tint, 0.9); c.shadowBlur = 8;
    c.strokeStyle = rgba(tint.map((v) => Math.round(v + (255 - v) * 0.4)), alpha); c.lineWidth = 1.3; c.lineCap = 'round';
    c.beginPath();
    for (const [ax, ay, bx, by] of contour(sheet)) { const p = this.toScreen([ax, ay]), q = this.toScreen([bx, by]); c.moveTo(p[0], p[1]); c.lineTo(q[0], q[1]); }
    c.stroke();
    c.restore();
  }

  // The hand as the map holds it: the edge of its cells, the path of its last places, a bright
  // peak at its place, a word on how the map holds it, and, while the hand is hidden, a thin line
  // to where the hand really is.
  peak(c, s, e, truth, m) {
    const shown = this.flow(e.place, s.record?.moment ?? 0), [bx, by] = this.toScreen(shown);
    c.save();
    c.globalCompositeOperation = 'lighter';
    if (this.trail.length > 1) {
      c.lineCap = 'round'; c.lineJoin = 'round';
      for (let i = 1; i < this.trail.length; i++) {
        const a = this.toScreen(this.trail[i - 1]), b = this.toScreen(this.trail[i]), f = i / this.trail.length;
        if (Math.hypot(a[0] - b[0], a[1] - b[1]) > 0.4 * m) continue;
        c.strokeStyle = rgba(TEAL, 0.45 * f * f); c.lineWidth = 1 + 2 * f;
        c.beginPath(); c.moveTo(a[0], a[1]); c.lineTo(b[0], b[1]); c.stroke();
      }
    }
    if (e.area) this.regionEdge(c, e.area, TEAL, 0.85);
    const r = clamp(e.cells.length > 6 ? 16 : 12, 9, 20);
    const core = c.createRadialGradient(bx, by, 0, bx, by, r);
    core.addColorStop(0, 'rgba(255,255,255,0.98)'); core.addColorStop(0.28, rgba([170, 255, 244], 0.8)); core.addColorStop(1, rgba(TEAL, 0));
    c.fillStyle = core; c.beginPath(); c.arc(bx, by, r, 0, Math.PI * 2); c.fill();
    c.restore();
    const hidden = s.record && !s.record.in_view[0];
    if (hidden && s.showHidden) {
      const [tx, ty] = this.toScreen(truth), apart = Math.hypot(shown[0] - truth[0], shown[1] - truth[1]), span = Math.hypot(tx - bx, ty - by);
      c.save();
      c.strokeStyle = 'rgba(255,255,255,0.5)'; c.setLineDash([3, 4]); c.lineWidth = 1.1;
      c.beginPath(); c.moveTo(bx, by); c.lineTo(tx, ty); c.stroke(); c.setLineDash([]);
      if (apart >= 0.08 && span > 30) {
        const text = `${Math.round(apart * 100)} cm`, side = tx - bx >= 0 ? 1 : -1, off = (14 + 14 * Math.abs((ty - by) / span)) * side;
        const mx = (bx + tx) / 2 - ((ty - by) / span) * off, my = (by + ty) / 2 + ((tx - bx) / span) * off;
        this.tag(c, text, mx, my, 'rgba(255,255,255,0.86)');
      }
      c.restore();
    }
    if (hidden) this.tag(c, e.state === 'felt' ? 'felt: its joint readings' : e.state === 'near' ? `near where it vanished · ${this.ago(e.since, s.dt)}` : `last seen · ${this.ago(e.since, s.dt)}`, bx, by - r - 8, rgba([170, 255, 244], 0.95));
  }

  // A few words beside the mouse, kept inside the room's canvas.
  hintChip(c, hint, w, h) {
    c.save();
    c.font = '500 11px Inter, system-ui, sans-serif'; c.textAlign = 'left'; c.textBaseline = 'middle';
    const tw = c.measureText(hint.text).width + 14;
    const x = Math.min(hint.x + 14, w - tw - 4), y = Math.min(hint.y + 22, h - 12);
    c.fillStyle = 'rgba(6,8,14,0.88)'; c.strokeStyle = 'rgba(150,165,210,0.35)'; c.lineWidth = 1;
    c.beginPath(); c.roundRect(x, y - 10, tw, 20, 6); c.fill(); c.stroke();
    c.fillStyle = 'rgba(233,237,247,0.92)'; c.fillText(hint.text, x + 7, y + 0.5);
    c.restore();
  }

  // A part's name, small and quiet, with no ground under it.
  name(c, text, x, y) {
    c.save();
    c.font = '500 10px "JetBrains Mono", ui-monospace, monospace'; c.textAlign = 'center'; c.textBaseline = 'middle';
    c.fillStyle = 'rgba(141,151,178,0.72)'; c.fillText(text, x, y);
    c.restore();
  }

  ago(moments, dt) { return `${Math.max(0, Math.round((moments || 0) * (dt || 1 / 30)))} s`; }

  // A short word on the table, on a dark ground: kept to be drawn over all the scene's pieces.
  tag(c, text, x, y, color) { (this.words || (this.words = [])).push([text, x, y, color]); }

  word(c, text, x, y, color) {
    c.save();
    c.font = '500 10.5px "JetBrains Mono", ui-monospace, monospace'; c.textAlign = 'center'; c.textBaseline = 'middle';
    const w = c.measureText(text).width + 10;
    c.fillStyle = 'rgba(6,8,14,0.82)'; c.beginPath(); c.roundRect(x - w / 2, y - 8, w, 16, 5); c.fill();
    c.fillStyle = color; c.fillText(text, x, y + 0.5);
    c.restore();
  }

  // The place shown for the hand flows from one moment's place to the next, and keeps the path
  // of its last places.
  flow(place, moment) {
    const f = this.shown;
    const far = !f || Math.hypot(f[0] - place[0], f[1] - place[1]) > 0.5;
    const k = far || this.calm ? 1 : 0.4;
    this.shown = far ? place.slice() : [f[0] + (place[0] - f[0]) * k, f[1] + (place[1] - f[1]) * k];
    if (moment !== this.trailMoment) {
      this.trailMoment = moment;
      this.trail.push(place.slice());
      if (this.trail.length > 36) this.trail.shift();
    }
    return this.shown;
  }

  // A thing on the map other than the hand: a pin at its place, its glyph in the pin's head, and
  // a word on how the map holds it. Hidden where it sits on the thing the camera sees.
  pin(c, s, e, things) {
    // a person's hand, where the page follows the arm's: it is not in the room, and has no true place to show
    const k = e.name === 'hand' && s.own ? -1 : s.names.indexOf(e.name), color = THING_COLOR[e.name] || [200, 200, 220];
    // the arm's own hand, where the page follows a person's: the arm's end
    const arm = e.name === 'own' && !s.own ? s.record?.arm : null;
    const truth = arm ? arm.tip : k >= 0 ? things[k] : null, inView = arm ? arm.seen : k >= 0 && !!s.record?.in_view?.[k];
    const off = truth ? Math.hypot(e.place[0] - truth[0], e.place[1] - truth[1]) : Infinity;
    if (inView && off < 0.03) return;
    const [x, y] = this.toScreen(e.place);
    if (e.area && e.cells.length > 4) this.regionEdge(c, e.area, color, 0.55);
    c.save();
    if (s.showHidden && truth && off > 0.03) {
      const [tx, ty] = this.toScreen(truth);
      c.strokeStyle = rgba(color, 0.4); c.setLineDash([2, 4]); c.lineWidth = 1;
      c.beginPath(); c.moveTo(x, y); c.lineTo(tx, ty); c.stroke(); c.setLineDash([]);
    }
    c.strokeStyle = rgba(color, 0.95); c.lineWidth = 1.5;
    c.beginPath(); c.moveTo(x, y); c.lineTo(x, y - 15); c.stroke();
    if (e.state === 'heard' || e.state === 'near') c.setLineDash([2, 2]);
    c.beginPath(); c.arc(x, y - 21, 7.5, 0, Math.PI * 2);
    c.fillStyle = 'rgba(8,11,20,0.9)'; c.fill(); c.stroke(); c.setLineDash([]);
    c.fillStyle = rgba(color, 0.95);
    c.beginPath(); c.arc(x, y, 2.2, 0, Math.PI * 2); c.fill();
    c.translate(x, y - 20.4);
    if (e.name === 'hand' || e.name === 'own') { c.fillStyle = rgba(color, 0.9); c.beginPath(); c.arc(0, 0, 3.2, 0, Math.PI * 2); c.fill(); }
    else glyph(c, e.name, 3.6, false);
    c.restore();
    const word = e.state === 'near' ? `near · ${this.ago(e.since, s.dt)}` : e.state === 'held' ? `${this.ago(e.since, s.dt)} ago` : e.state;
    if (!inView) this.tag(c, word, x, y + 11, rgba(color, 0.95));
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

