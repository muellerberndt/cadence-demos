// The brain as a scan: a translucent brain with its activity glowing where regions are active (a
// smooth dark-to-warm scale with a soft bloom), fine traces along its tracts with pulses travelling
// on them as the sending region fires, the concepts its state holds as tags over the association
// region, and its inputs and outputs as framed boxes at the edge of the view with thin leader lines
// into their regions. Everything is drawn from the running brain's reply of each moment and eased
// between moments by the frame's own time, so it breathes at the display's rate.
//
// The concept tags read the meaning lane's probes (the reply's `meaning.mind`, probes.json beside the
// trained brain): a tag for the thing the state holds and smaller tags for its properties the probes
// read (its colour, round, its material, "can eat"). A tag's brightness is the probe's answer against
// its next answer (1 - second / first), so a tag fades where the probe hesitates; nothing is tagged
// that the probes do not read, and nothing at all without them.
import * as THREE from 'three';

// a dark-to-warm scale (deep indigo, plum, ember, amber, pale gold)
const STOPS = [[0.0, [0.03, 0.03, 0.08]], [0.25, [0.20, 0.06, 0.30]], [0.5, [0.62, 0.13, 0.30]], [0.75, [0.98, 0.45, 0.16]], [1.0, [1.0, 0.92, 0.62]]];
export const LUT = (() => {
  const out = new Float32Array(256 * 3);
  for (let i = 0; i < 256; i++) {
    const t = i / 255;
    let k = 0; while (k < STOPS.length - 2 && t > STOPS[k + 1][0]) k++;
    const [t0, c0] = STOPS[k], [t1, c1] = STOPS[k + 1], u = (t - t0) / (t1 - t0);
    for (let j = 0; j < 3; j++) out[3 * i + j] = c0[j] + (c1[j] - c0[j]) * u;
  }
  return out;
})();
const ease = (cur, want, dt, tau) => cur + (want - cur) * (1 - Math.exp(-dt / tau));

function glowTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const g = c.getContext('2d'), grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  grad.addColorStop(0, 'rgba(255,255,255,0.9)'); grad.addColorStop(0.25, 'rgba(255,255,255,0.45)'); grad.addColorStop(0.6, 'rgba(255,255,255,0.08)'); grad.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grad; g.fillRect(0, 0, 128, 128);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

const FACET_TAG = { // a property tag for each facet's answer (only answers that name a property of the thing)
  colour: (v) => v, round: (v) => (v === 'True' ? 'round' : null), material: (v) => v, edible: (v) => (v === 'True' ? 'can eat' : null),
  direction: (v) => v,
};
const ASKED = [['colour', /\b(colou?r)\b/], ['round', /\b(shape|round)\b/], ['direction', /\b(where|left|right)\b/], ['edible', /\beat\b/], ['material', /\bmade\b/]];
const PULSES = 900;

export class Scan {
  constructor(b, host) {
    this.b = b; this.host = host;
    const tex = glowTexture();
    // hotspots: one soft glow a region side, its colour and size by the region's eased activity
    this.spots = [];
    for (const r of b.regions) {
      if (!r.count) continue;
      for (const sx of (r.bi ? [1, -1] : [0])) {
        const m = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending, opacity: 0 }));
        b.centre(r.id, sx, m.position);
        const size = 1.5 * Math.max(r.r[0], r.r[1], r.r[2]) + 0.35;
        m.scale.set(size, size, 1); m.renderOrder = 4;
        b.scene.add(m);
        this.spots.push({ r, m, size, level: 0 });
      }
    }
    // pulses: bright points travelling along the tracts, more and faster the more the sender fires
    const pos = new Float32Array(PULSES * 3), col = new Float32Array(PULSES * 3);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3)); geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
    this.pulses = new THREE.Points(geo, new THREE.PointsMaterial({ size: 0.075, map: tex, vertexColors: true, transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending }));
    this.pulses.renderOrder = 5; b.scene.add(this.pulses);
    this.pulseOf = []; // [tract index, phase, speed]
    const per = Math.max(1, Math.floor(PULSES / Math.max(1, b.tracts.length)));
    b.tracts.forEach((t, i) => { for (let k = 0; k < per && this.pulseOf.length < PULSES; k++) this.pulseOf.push([i, (k + Math.random()) / per, 0.35 + 0.3 * Math.random()]); });
    this.tmp = new THREE.Vector3(); this.tmp2 = new THREE.Vector3();
    // the overlay: concept tags, the I/O boxes and their leader lines
    this.overlay = document.createElement('div'); this.overlay.className = 'scan-overlay'; host.append(this.overlay);
    this.svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); this.svg.setAttribute('class', 'scan-lines'); this.overlay.append(this.svg);
    this.boxes = {};
    for (const [id, title, region, side] of [['retinaL', 'Retina L', 'retina', 1], ['retinaR', 'Retina R', 'retina', -1], ['ears', 'Ears', 'ear', 1], ['voice', 'Voice', 'voice', 0], ['dopamine', 'Dopamine', 'vta', 0]]) {
      const box = document.createElement('div'); box.className = `scan-box ${id}`;
      const h = document.createElement('span'); h.className = 'sb-title'; h.textContent = title; box.append(h);
      const body = document.createElement('div'); body.className = 'sb-body'; box.append(body);
      this.overlay.append(box);
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line'); this.svg.append(line);
      const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle'); dot.setAttribute('r', '2.5'); this.svg.append(dot);
      this.boxes[id] = { box, body, line, dot, region, side, glow: 0 };
    }
    // the ears' running spectrogram
    this.ear = document.createElement('canvas'); this.ear.width = 96; this.ear.height = 40; this.boxes.ears.body.append(this.ear);
    this.earG = this.ear.getContext('2d'); this.earImg = this.earG.createImageData(1, 40);
    this.voiceWord = document.createElement('b'); this.voiceWord.className = 'sb-word'; this.voiceWord.textContent = '·';
    this.voiceBar = document.createElement('i'); this.voiceBar.className = 'sb-bar';
    this.boxes.voice.body.append(this.voiceWord, this.voiceBar);
    this.dopBar = document.createElement('i'); this.dopBar.className = 'sb-bar dop'; this.boxes.dopamine.body.append(this.dopBar);
    this.tags = [];
    for (let i = 0; i < 6; i++) { const t = document.createElement('span'); t.className = `scan-tag${i === 0 ? ' main' : ''}`; this.overlay.append(t); this.tags.push({ el: t, text: '', alpha: 0, want: 0, x: 0, y: 0 }); }
    this.concept = null; this.asked = null; this.dop = 0; this.said = 0;
  }

  /** The page's eye canvases (the brain's two eye images) shown in the retina boxes. */
  eyes(left, right) { this.boxes.retinaL.body.append(left); this.boxes.retinaR.body.append(right); }

  /** One moment's reply: the concept the state holds (the probes' facets), the dopamine. */
  moment(reply) {
    const mind = reply?.meaning?.mind;
    if (mind?.facets) this.concept = mind.facets;
    if (typeof reply?.vta === 'number' && reply.vta > 0.05) this.dop = Math.max(this.dop, Math.min(1, reply.vta));
  }
  /** The question being asked, for the property it asks about. */
  question(text) { this.asked = null; for (const [f, re] of ASKED) if (re.test(text || '')) { this.asked = f; break; } }
  /** The word the voice says (the box shows it while it plays). */
  say(word) { this.voiceWord.textContent = word; this.said = 2.4; }
  reward() { this.dop = 1; }
  /** A heard sound: the ear and Field L light; a sound it knows (its record told again) lights NCM and its
   *  record; a known sound linked to a thing (the hearing memory's sound-to-thing synapses) lights that
   *  thing's concept tag, marked heard, with a pulse from NCM to the association region. */
  heardSound({ recognized, kind, strength, slot }) {
    const L = this.b.live, vt = this.b.clock.vt;
    L.flashes.push({ region: 'ear', t0: vt, level: 0.9 }); L.flashes.push({ region: 'fieldl', t0: vt + 0.08, level: 0.8 });
    if (!recognized) return;
    L.flashes.push({ region: 'ncm', t0: vt + 0.2, level: 0.9 });
    const s = L.slots?.get(slot); if (s) s.flash = vt + 0.3;
    if (!kind) return;
    L.packets.push({ path: ['ncm', 'ncl'], t0: vt + 0.3, dur: 1.0, colour: L.cHear });
    this.heardTag = { text: window.parrotPage?.label?.(kind) || kind, k: Math.max(0.35, Math.min(1, strength)), until: performance.now() + 3800 };
  }
  clearConcept() { this.concept = null; }

  /** The boxes' places in the view (read once in a while, never in the middle of a frame's writes). */
  layout() {
    const h = this.host.getBoundingClientRect();
    for (const box of Object.values(this.boxes)) { const r = box.box.getBoundingClientRect(); box.rect = [r.left - h.left, r.top - h.top, r.right - h.left, r.bottom - h.top]; }
    this.rects = true; this.rectsAt = 0;
  }

  conf(f) { // the probe's answer against its next answer, 0 to 1
    const p = f?.p ?? 0, q = f?.p2 ?? 0;
    return p > 0 ? Math.max(0, Math.min(1, 1 - q / p)) : 0;
  }

  frame(dt, vt, rect) {
    const b = this.b, W = rect.width, H = rect.height;
    // hotspots: the region's eased activity on the warm scale
    for (const s of this.spots) {
      const r = s.r, want = r.live ? Math.min(1, r.mean * 1.8) : 0;
      s.level = ease(s.level, want, dt, 0.18);
      const k = Math.min(255, Math.max(0, Math.round(s.level * 255))) * 3;
      s.m.material.color.setRGB(LUT[k], LUT[k + 1], LUT[k + 2]);
      s.m.material.opacity = r.live ? 0.06 + 0.7 * s.level : 0;
      const g = 0.75 + 0.5 * s.level; s.m.scale.set(s.size * g, s.size * g, 1);
    }
    // pulses along the tracts
    const pa = this.pulses.geometry.attributes.position, ca = this.pulses.geometry.attributes.color, P = pa.array, C = ca.array;
    for (let i = 0; i < this.pulseOf.length; i++) {
      const q = this.pulseOf[i], t = b.tracts[q[0]], src = t.from;
      const act = src.live && t.to.live ? Math.min(1, src.mean * 2 + b.live.tractBoost(t) * 0.6) : 0;
      q[1] += dt * q[2] * (0.25 + 1.6 * act); if (q[1] > 1) q[1] -= 1;
      t.curve.getPoint(q[1], this.tmp);
      P[3 * i] = this.tmp.x; P[3 * i + 1] = this.tmp.y; P[3 * i + 2] = this.tmp.z;
      const k = Math.min(255, Math.round((0.35 + 0.65 * act) * 255)) * 3, a = act * (0.4 + 0.6 * Math.sin(Math.PI * q[1]));
      C[3 * i] = LUT[k] * a; C[3 * i + 1] = LUT[k + 1] * a; C[3 * i + 2] = LUT[k + 2] * a;
    }
    pa.needsUpdate = true; ca.needsUpdate = true;
    // the I/O boxes' leader lines: from the box's edge to its region on screen
    if (!this.rects || (this.rectsAt = (this.rectsAt || 0) + dt) > 2) this.layout();
    for (const box of Object.values(this.boxes)) {
      b.centre(box.region, box.side, this.tmp).project(b.camera);
      const x = (this.tmp.x + 1) / 2 * W, y = (1 - this.tmp.y) / 2 * H, br = box.rect;
      const bx = Math.min(Math.max(x, br[0]), br[2]), by = Math.min(Math.max(y, br[1]), br[3]);
      box.line.setAttribute('x1', bx.toFixed(1)); box.line.setAttribute('y1', by.toFixed(1)); box.line.setAttribute('x2', x.toFixed(1)); box.line.setAttribute('y2', y.toFixed(1));
      box.dot.setAttribute('cx', x.toFixed(1)); box.dot.setAttribute('cy', y.toFixed(1));
    }
    // the ears' spectrogram: one column a frame from the page's latest ear frame
    const f = window.parrotPage?.audio?.frames?.at(-1), mic = window.parrotPage?.audio?.mic;
    this.earTick = (this.earTick || 0) + 1;
    if (this.earTick % 2) { // a column every second frame: about three seconds of sound in the box
    this.earG.drawImage(this.ear, -1, 0);
    for (let m = 0; m < 40; m++) {
      // from silence (the front end's floor, -13.8) up
      const v = f && mic ? Math.max(0, Math.min(1, (f[m] + 13.8) / 9)) : 0, k = Math.round(v * 255) * 3, j = 4 * (39 - m);
      this.earImg.data[j] = 255 * LUT[k]; this.earImg.data[j + 1] = 255 * LUT[k + 1]; this.earImg.data[j + 2] = 255 * LUT[k + 2]; this.earImg.data[j + 3] = 255;
    }
    this.earG.putImageData(this.earImg, this.ear.width - 1, 0);
    }
    // the voice and the dopamine
    const loud = window.parrotPage?.audio?.loudness(performance.now()) || 0;
    this.voiceBar.style.transform = `scaleX(${Math.max(0.02, loud).toFixed(3)})`;
    this.said = Math.max(0, this.said - dt); this.boxes.voice.box.classList.toggle('on', this.said > 0 || loud > 0.05);
    this.dop = Math.max(0, this.dop - dt * 0.45);
    this.dopBar.style.transform = `scaleX(${Math.max(0.02, this.dop).toFixed(3)})`; this.boxes.dopamine.box.classList.toggle('on', this.dop > 0.1);
    // the concept tags: the thing the state holds over the association region, its properties around it
    const c = this.concept, wants = [];
    const heard = this.heardTag && performance.now() < this.heardTag.until ? this.heardTag : null;
    if (heard) wants.push([`${heard.text} · heard`, heard.k, true]); // a word heard: its thing alone (the probes' facets read the state, not the word)
    else if (c?.kind) wants.push([c.kind.value, this.conf(c.kind), true]);
    for (const name of ['colour', 'round', 'material', 'edible', 'direction']) {
      const f2 = !heard && c?.[name]; if (!f2) continue;
      if (name === 'direction' && this.asked !== 'direction') continue; // its place is tagged when a question asks where
      const text = FACET_TAG[name](f2.value); if (!text) continue;
      let k = this.conf(f2); if (this.asked === name) k = Math.min(1, k * 1.6 + 0.15);
      wants.push([text, k, false, this.asked === name]);
    }
    b.centre('ncl', 1, this.tmp).project(b.camera);
    const cx = (this.tmp.x + 1) / 2 * W, cy = (1 - this.tmp.y) / 2 * H;
    this.tags.forEach((t, i) => {
      const w = wants[i];
      if (w && t.text !== w[0]) { t.text = w[0]; t.el.textContent = w[0]; }
      t.want = w ? (w[1] < 0.12 ? 0 : 0.25 + 0.75 * w[1]) : 0;
      t.alpha = ease(t.alpha, t.want, dt, 0.25);
      t.el.classList.toggle('asked', !!(w && w[3]));
      const ang = i === 0 ? 0 : -Math.PI / 2 + (i - 1) * (2 * Math.PI / 5), rad = i === 0 ? 0 : 88;
      const x = cx + Math.cos(ang) * rad * 1.25, y = cy - 26 + Math.sin(ang) * rad * 0.8;
      t.el.style.opacity = t.alpha.toFixed(3);
      t.el.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) translate(-50%, -50%)`;
    });
  }
}
