// The scene from above, the map the brain holds, and the error chart: three Canvas2D views.
//
// SceneView draws the plane as it is (the arm, the hand, the things, the camera's light and its
// shadows) and, on top, what the brain says: the hand's place as a glowing peak inside the area
// that holds it at the stated rate, and a pin for every thing's record. MapView draws the place
// answer itself, straight from the place units' readout. ChartView draws each estimate's error
// against the true position over the last moments.

import { forward, litPolygon, cartesian } from './world.js';
import { radiusAt } from './controls.js';

const TEAL = [63, 224, 207], ORANGE = [255, 159, 74], GOLD = [255, 206, 102], VIOLET = [183, 156, 255];
export const THING_COLOR = { hand: ORANGE, cup: [127, 212, 255], wrench: [201, 210, 232], box: [222, 178, 124] };
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
    this.scale = 1; this.ox = 0; this.oy = 0;
    this.hatch = null;
  }

  // metres <-> CSS pixels (y up on the plane, down on the screen)
  toScreen(p) { return [this.ox + p[0] * this.scale, this.oy - p[1] * this.scale]; }
  toPlane(x, y) { return [(x - this.ox) / this.scale, (this.oy - y) / this.scale]; }

  layout(geometry, w, h) {
    const [lx, hx, ly, hy] = geometry.plane, margin = 0.1;
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

    // the brain's belief of the hand, under the things
    if (s.belief?.place) {
      c.save(); c.beginPath(); c.roundRect(x0, y0, x1 - x0, y1 - y0, 10); c.clip();
      this.belief(c, s, m);
      c.restore();
    }

    // the occluding discs
    for (const o of g.occluders) {
      const [ox, oy] = S(o.center), r = o.radius * m;
      const disc = c.createRadialGradient(ox - r * 0.3, oy - r * 0.3, r * 0.1, ox, oy, r);
      disc.addColorStop(0, '#39425e'); disc.addColorStop(1, '#161b2c');
      c.fillStyle = disc; c.beginPath(); c.arc(ox, oy, r, 0, Math.PI * 2); c.fill();
      c.strokeStyle = s.selected === 'screen' ? 'rgba(255,255,255,0.9)' : 'rgba(170,185,225,0.55)'; c.lineWidth = 1.4; c.stroke();
    }

    // the things on the table and their pins
    for (let k = 1; k < things.length; k++) this.thing(c, s, k, things[k], m);
    for (let k = 1; k < things.length; k++) this.pin(c, s, k, things[k]);

    // the arm
    this.arm(c, g, joints, m, s.own);

    // the hand
    this.hand(c, s, things[0], m);

    // the comparison's markers
    if (s.compare && s.controls) {
      const { last, kalman, kalmanSd } = s.controls;
      const [kx, ky] = S(kalman), [qx, qy] = S(last);
      c.lineWidth = 1;
      c.strokeStyle = rgba(VIOLET, 0.95);
      c.beginPath(); c.moveTo(kx, ky - 5); c.lineTo(kx + 5, ky); c.lineTo(kx, ky + 5); c.lineTo(kx - 5, ky); c.closePath(); c.stroke();
      c.strokeStyle = rgba(VIOLET, 0.3);
      c.beginPath(); c.arc(kx, ky, Math.max(2, radiusAt(0.9) * kalmanSd * m), 0, Math.PI * 2); c.stroke();
      c.strokeStyle = rgba(GOLD, 0.95);
      c.beginPath(); c.moveTo(qx - 4, qy - 4); c.lineTo(qx + 4, qy + 4); c.moveTo(qx + 4, qy - 4); c.lineTo(qx - 4, qy + 4); c.stroke();
    }

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

  belief(c, s, m) {
    const { place, sd } = s.belief, [bx, by] = this.toScreen(place);
    const k = radiusAt(s.rate || 0.9);
    const rx = Math.max(3, k * sd[0] * m), ry = Math.max(3, k * sd[1] * m);
    const unseen = !s.record?.in_view?.[0];
    c.save();
    // the area that holds the hand at the stated rate
    c.beginPath(); c.ellipse(bx, by, rx, ry, 0, 0, Math.PI * 2);
    const area = c.createRadialGradient(bx, by, 0, bx, by, Math.max(rx, ry));
    area.addColorStop(0, rgba(TEAL, 0.16)); area.addColorStop(1, rgba(TEAL, 0.03));
    c.fillStyle = area; c.fill();
    c.strokeStyle = rgba(TEAL, 0.62); c.lineWidth = 1.3;
    if (unseen) c.setLineDash([5, 4]);
    c.stroke(); c.setLineDash([]);
    // the peak
    c.globalCompositeOperation = 'lighter';
    const r = clamp(Math.min(rx, ry) * 0.9, 12, 46);
    const peak = c.createRadialGradient(bx, by, 0, bx, by, r);
    peak.addColorStop(0, rgba([190, 255, 246], 0.95)); peak.addColorStop(0.25, rgba(TEAL, 0.6)); peak.addColorStop(1, rgba(TEAL, 0));
    c.fillStyle = peak; c.beginPath(); c.arc(bx, by, r, 0, Math.PI * 2); c.fill();
    c.restore();
    c.strokeStyle = rgba([210, 255, 250], 0.9); c.lineWidth = 1;
    c.beginPath(); c.moveTo(bx - 5, by); c.lineTo(bx + 5, by); c.moveTo(bx, by - 5); c.lineTo(bx, by + 5); c.stroke();
    if (s.showHidden && s.record) {
      // the error: a thin line from the belief to the true hand
      const [tx, ty] = this.toScreen(s.record.truth[0]);
      c.strokeStyle = rgba(TEAL, 0.35); c.setLineDash([2, 4]);
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

  hand(c, s, at, m) {
    const inView = !!s.record?.in_view?.[0];
    if (!inView && !s.showHidden) return;
    if (s.own) {
      if (!inView) {
        const [x, y] = this.toScreen(at);
        c.strokeStyle = rgba(ORANGE, 0.5); c.setLineDash([3, 3]); c.lineWidth = 1.2;
        c.beginPath(); c.arc(x, y, 0.045 * m, 0, Math.PI * 2); c.stroke(); c.setLineDash([]);
      }
      return;
    }
    const [x, y] = this.toScreen(at), u = 0.07 * m;
    // the hand points the way it last moved
    if (s.previous && s.record) {
      const dx = s.record.truth[0][0] - s.previous.truth[0][0], dy = s.record.truth[0][1] - s.previous.truth[0][1];
      if (Math.hypot(dx, dy) > 0.002) {
        const want = Math.atan2(dx, dy);
        let turn = want - (this.handAngle ?? want);
        turn = Math.atan2(Math.sin(turn), Math.cos(turn));
        this.handAngle = (this.handAngle ?? want) + turn * 0.12;
      }
    }
    c.save();
    c.translate(x, y); c.rotate(this.handAngle ?? 0);
    const body = () => {
      // a hand seen from above: the palm, four fingers and a thumb
      c.beginPath(); c.ellipse(0, u * 0.25, u * 0.62, u * 0.7, 0, 0, Math.PI * 2);
      for (let k = 0; k < 4; k++) {
        const fx = (k - 1.5) * u * 0.34, len = u * (1.25 - 0.14 * Math.abs(k - 1.4));
        c.roundRect(fx - u * 0.13, -u * 0.35 - len, u * 0.26, len, u * 0.13);
      }
      c.save(); c.rotate(-0.9); c.roundRect(-u * 0.95, -u * 0.25, u * 0.28, u * 0.8, u * 0.14); c.restore();
    };
    if (inView) {
      c.shadowColor = rgba(ORANGE, 0.75); c.shadowBlur = 16;
      body(); c.fillStyle = rgba(ORANGE, 0.95); c.fill();
      c.shadowBlur = 0;
      body(); c.strokeStyle = 'rgba(255,230,200,0.8)'; c.lineWidth = 1; c.stroke();
    } else {
      body(); c.fillStyle = rgba(ORANGE, 0.07); c.fill();
      c.setLineDash([3, 3]); c.strokeStyle = rgba(ORANGE, 0.55); c.lineWidth = 1.2; c.stroke();
    }
    if (s.selected === 'hand') { c.setLineDash([]); c.strokeStyle = 'rgba(255,255,255,0.85)'; c.lineWidth = 1.2; c.beginPath(); c.arc(0, -u * 0.3, u * 1.75, 0, Math.PI * 2); c.stroke(); }
    c.restore();
  }

  thing(c, s, k, at, m) {
    const name = s.names[k], inView = !!s.record?.in_view?.[k];
    if (!inView && !s.showHidden) return;
    const [x, y] = this.toScreen(at), u = 0.05 * m, color = THING_COLOR[name] || [200, 200, 220];
    const alpha = inView ? 1 : 0.5;
    c.save();
    c.translate(x, y);
    c.lineWidth = 1.4;
    if (!inView) c.setLineDash([3, 3]);
    c.strokeStyle = rgba(color, 0.95 * alpha); c.fillStyle = rgba(color, inView ? 0.22 : 0.05);
    if (inView) { c.shadowColor = rgba(color, 0.55); c.shadowBlur = 10; }
    if (name === 'cup') {
      c.beginPath(); c.arc(0, 0, u, 0, Math.PI * 2); c.fill(); c.stroke();
      c.shadowBlur = 0;
      c.beginPath(); c.arc(0, 0, u * 0.68, 0, Math.PI * 2); c.stroke();
      c.beginPath(); c.arc(u * 1.25, 0, u * 0.42, -Math.PI * 0.62, Math.PI * 0.62); c.stroke();
    } else if (name === 'wrench') {
      c.rotate(-0.6);
      c.beginPath(); c.roundRect(-u * 1.35, -u * 0.2, u * 2.1, u * 0.4, u * 0.2); c.fill(); c.stroke();
      c.shadowBlur = 0;
      c.beginPath(); c.arc(u * 1.05, 0, u * 0.52, Math.PI * 0.28, Math.PI * 1.72); c.stroke();
      c.beginPath(); c.arc(-u * 1.3, 0, u * 0.3, 0, Math.PI * 2); c.stroke();
    } else {
      c.rotate(0.25);
      c.beginPath(); c.roundRect(-u, -u * 0.85, u * 2, u * 1.7, u * 0.18); c.fill(); c.stroke();
      c.shadowBlur = 0;
      c.beginPath(); c.moveTo(-u, 0); c.lineTo(u, 0); c.moveTo(0, -u * 0.85); c.lineTo(0, u * 0.85); c.stroke();
    }
    c.setLineDash([]);
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
    c.beginPath(); c.arc(x, y - 21, 6.5, 0, Math.PI * 2);
    c.fillStyle = 'rgba(8,11,20,0.9)'; c.fill(); c.stroke(); c.setLineDash([]);
    c.fillStyle = rgba(color, 0.95);
    c.beginPath(); c.arc(x, y, 2.2, 0, Math.PI * 2); c.fill();
    c.font = '600 8.5px Inter, system-ui, sans-serif'; c.textAlign = 'center'; c.textBaseline = 'middle';
    c.fillText(name[0].toUpperCase(), x, y - 20.5);
    c.restore();
  }

  cameraGlyph(c, eye, heading, on, selected) {
    c.save();
    c.translate(eye[0], eye[1]); c.rotate(-heading);
    c.fillStyle = '#1a2136'; c.strokeStyle = selected ? 'rgba(255,255,255,0.9)' : on ? 'rgba(150,225,255,0.9)' : 'rgba(120,130,160,0.7)'; c.lineWidth = 1.4;
    c.beginPath(); c.roundRect(-16, -8, 16, 16, 3); c.fill(); c.stroke();
    c.beginPath(); c.moveTo(0, -5); c.lineTo(8, -8); c.lineTo(8, 8); c.lineTo(0, 5); c.closePath(); c.fill(); c.stroke();
    c.fillStyle = on ? 'rgba(150,235,255,0.95)' : 'rgba(90,100,130,0.8)';
    if (on) { c.shadowColor = 'rgba(150,235,255,0.9)'; c.shadowBlur = 10; }
    c.beginPath(); c.arc(-8, 0, 2.6, 0, Math.PI * 2); c.fill();
    c.restore();
  }

  /** What lies under a point of the canvas: a thing's name, 'screen', 'camera' or null. */
  hit(x, y, s) {
    const m = this.scale, near = (p, r) => { const q = this.toScreen(p); return Math.hypot(q[0] - x, q[1] - y) <= r; };
    const things = s.record ? s.record.truth : s.things;
    if (!s.own && near(things[0], 0.1 * m)) return 'hand';
    for (let k = 1; k < things.length; k++) if (near(things[k], 0.085 * m)) return s.names[k];
    for (const o of s.geometry.occluders) if (near(o.center, o.radius * m + 8)) return 'screen';
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
      c.beginPath(); c.arc(px, py, 5.5, 0, Math.PI * 2); c.fill(); c.stroke(); c.setLineDash([]);
      c.fillStyle = rgba(color, 0.95); c.font = '600 7.5px Inter, system-ui, sans-serif'; c.textAlign = 'center'; c.textBaseline = 'middle';
      c.fillText(name[0].toUpperCase(), px, py + 0.5);
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
