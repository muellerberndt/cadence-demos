// The arena renderer: a glowing floor, light walls with a cached glow, cycle heads that glide
// between ticks, the brain's eye footprint, crash explosions and a light screen shake.
// The game itself lives in the worker (tron/world.py); this only draws the states it returns.

const DR = [-1, 0, 1, 0];
const DC = [0, 1, 0, -1];

export const SEATS = [
  { name: "brain", main: "#ff4fd8", core: "#ffe8fb", rgb: [255, 79, 216] },
  { name: "you", main: "#2de2ff", core: "#eaffff", rgb: [45, 226, 255] },
];

const rgba = (rgb, a) => `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a})`;

function sprite(rgb, size) {
  // A soft radial light, drawn once and stamped with drawImage.
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d");
  const grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  grad.addColorStop(0, rgba(rgb, 1));
  grad.addColorStop(0.18, rgba(rgb, 0.55));
  grad.addColorStop(0.5, rgba(rgb, 0.14));
  grad.addColorStop(1, rgba(rgb, 0));
  g.fillStyle = grad;
  g.fillRect(0, 0, size, size);
  return c;
}

export class ArenaView {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.size = 24;
    this.paths = [[], []];
    this.headings = [0, 2];
    this.alive = [true, true];
    this.anim = null;
    this.particles = [];
    this.rings = [];
    this.flash = 0;
    this.shake = 0;
    this.derez = [null, null];
    this.showEye = false;
    this.eyeKind = "field";
    this.onCrash = null; // (seat) => void
    this.active = false;
    this.occupied = new Uint8Array(this.size * this.size);
    this.sprites = SEATS.map((s) => sprite(s.rgb, 128));
    this.white = sprite([255, 255, 255], 128);
    this.layers = [document.createElement("canvas"), document.createElement("canvas")];
    this.floor = document.createElement("canvas");
    this.last = performance.now();
    new ResizeObserver(() => this.resize()).observe(canvas);
    this.resize();
  }

  // ---- geometry ------------------------------------------------------------------------
  resize() {
    const rect = this.canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const W = Math.max(64, Math.round(rect.width * dpr));
    if (W === this.W) return;
    this.W = W;
    this.dpr = dpr;
    this.canvas.width = this.canvas.height = W;
    for (const layer of [...this.layers, this.floor]) layer.width = layer.height = W;
    this.pad = Math.round(W * 0.03);
    this.cell = (W - 2 * this.pad) / this.size;
    this.drawFloor();
    this.drawLayers();
  }

  x(c) { return this.pad + (c + 0.5) * this.cell; }
  y(r) { return this.pad + (r + 0.5) * this.cell; }

  drawFloor() {
    const g = this.floor.getContext("2d");
    const { W, pad, cell, size } = this;
    g.fillStyle = "#000000";
    g.fillRect(0, 0, W, W);
    let grad = g.createRadialGradient(W / 2, W / 2, 0, W / 2, W / 2, W * 0.75);
    grad.addColorStop(0, "rgba(16, 40, 80, 0.45)");
    grad.addColorStop(0.6, "rgba(6, 14, 32, 0.3)");
    grad.addColorStop(1, "rgba(0, 0, 0, 0)");
    g.fillStyle = grad;
    g.fillRect(0, 0, W, W);
    // Cells: faint lines, brighter every six, small lights at the crossings.
    for (let i = 0; i <= size; i++) {
      const major = i % 6 === 0;
      g.strokeStyle = major ? "rgba(90, 190, 255, 0.20)" : "rgba(70, 160, 255, 0.075)";
      g.lineWidth = major ? Math.max(1, this.dpr * 1.1) : Math.max(1, this.dpr * 0.6);
      const p = Math.round(pad + i * cell) + 0.5;
      g.beginPath(); g.moveTo(p, pad); g.lineTo(p, W - pad); g.stroke();
      g.beginPath(); g.moveTo(pad, p); g.lineTo(W - pad, p); g.stroke();
    }
    g.fillStyle = "rgba(150, 220, 255, 0.35)";
    for (let i = 0; i <= size; i += 6) {
      for (let j = 0; j <= size; j += 6) {
        g.beginPath();
        g.arc(pad + i * cell, pad + j * cell, 1.6 * this.dpr, 0, Math.PI * 2);
        g.fill();
      }
    }
    // The boundary wall.
    g.save();
    g.shadowColor = "rgba(110, 200, 255, 0.9)";
    g.shadowBlur = 16 * this.dpr;
    g.strokeStyle = "rgba(150, 220, 255, 0.85)";
    g.lineWidth = 2 * this.dpr;
    g.strokeRect(pad, pad, W - 2 * pad, W - 2 * pad);
    g.restore();
    // Vignette.
    grad = g.createRadialGradient(W / 2, W / 2, W * 0.35, W / 2, W / 2, W * 0.78);
    grad.addColorStop(0, "rgba(0,0,0,0)");
    grad.addColorStop(1, "rgba(0,0,0,0.55)");
    g.fillStyle = grad;
    g.fillRect(0, 0, W, W);
  }

  // The committed light wall of one seat, through every cell but the newest (the newest
  // segment is drawn live while the head glides into it).
  drawLayers() {
    for (let seat = 0; seat < 2; seat++) {
      const layer = this.layers[seat];
      const g = layer.getContext("2d");
      g.clearRect(0, 0, layer.width, layer.height);
      const path = this.paths[seat];
      const upto = this.anim && this.anim.grew[seat] ? path.length - 1 : path.length;
      if (upto < 2) continue;
      this.strokeTrail(g, seat, path, upto);
    }
  }

  strokeTrail(g, seat, path, upto, from = 0, tail = null) {
    const s = SEATS[seat];
    const trace = () => {
      g.beginPath();
      g.moveTo(this.x(path[from][1]), this.y(path[from][0]));
      for (let i = from + 1; i < upto; i++) g.lineTo(this.x(path[i][1]), this.y(path[i][0]));
      if (tail) g.lineTo(tail[0], tail[1]);
    };
    g.save();
    g.lineCap = "round";
    g.lineJoin = "round";
    g.shadowColor = s.main;
    g.shadowBlur = this.cell * 0.9;
    g.strokeStyle = rgba(s.rgb, 0.9);
    g.lineWidth = this.cell * 0.4;
    trace(); g.stroke();
    g.shadowBlur = this.cell * 0.3;
    g.shadowColor = s.core;
    g.strokeStyle = s.core;
    g.lineWidth = this.cell * 0.13;
    trace(); g.stroke();
    g.restore();
  }

  // ---- game events ---------------------------------------------------------------------
  clear(size = 24) {
    this.size = size;
    this.paths = [[], []];
    this.anim = null;
    this.alive = [true, true];
    this.derez = [null, null];
    this.active = false;
    this.occupied = new Uint8Array(size * size);
    this.cell = (this.W - 2 * this.pad) / size;
    this.drawFloor();
    this.drawLayers();
  }

  start(state) {
    this.clear(state.size || 24);
    this.active = true;
    this.paths = state.heads.map((h) => [h.slice()]);
    for (const [r, c] of state.heads) this.occupied[r * this.size + c] = 1;
    this.headings = state.headings.slice();
    this.angles = this.headings.map((h) => h * 90);
    this.alive = state.alive.slice();
    this.anim = null;
    this.drawLayers();
  }

  update(state, duration) {
    const now = performance.now();
    const from = this.paths.map((p) => p[p.length - 1]);
    const grew = [false, false];
    const angFrom = this.anim ? this.currentAngles(now) : this.headings.map((h) => h * 90);
    for (let seat = 0; seat < 2; seat++) {
      const [r, c] = state.heads[seat];
      const last = from[seat];
      if (r !== last[0] || c !== last[1]) {
        this.paths[seat].push([r, c]);
        this.occupied[r * this.size + c] = 1;
        grew[seat] = true;
      }
    }
    const angTo = state.headings.map((h, seat) => {
      const a = angFrom[seat];
      let d = ((h * 90 - a) % 360 + 540) % 360 - 180;
      return a + d;
    });
    this.headings = state.headings.slice();
    this.anim = { t0: now, dur: duration, grew, angFrom, angTo };
    this.drawLayers();
    for (let seat = 0; seat < 2; seat++) {
      if (this.alive[seat] && !state.alive[seat]) this.crash(seat, state);
    }
    this.alive = state.alive.slice();
  }

  crash(seat, state) {
    const [r, c] = state.heads[seat];
    const h = state.headings[seat];
    const px = this.x(c + DC[h] * 0.5);
    const py = this.y(r + DR[h] * 0.5);
    const s = SEATS[seat];
    const cell = this.cell;
    for (let i = 0; i < 110; i++) {
      const a = Math.random() * Math.PI * 2;
      const v = cell * (3 + Math.random() * 13);
      const life = 0.5 + Math.random() * 1.0;
      this.particles.push({
        x: px, y: py, vx: Math.cos(a) * v - DC[h] * cell * 2, vy: Math.sin(a) * v - DR[h] * cell * 2,
        life, max: life, rgb: Math.random() < 0.25 ? [255, 255, 255] : s.rgb, w: (0.6 + Math.random() * 1.4) * this.dpr,
      });
    }
    for (let i = 0; i < 18; i++) {
      const a = Math.random() * Math.PI * 2;
      const v = cell * (1.5 + Math.random() * 5);
      const life = 0.8 + Math.random() * 0.9;
      this.particles.push({
        x: px, y: py, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life, max: life, rgb: s.rgb,
        cube: cell * (0.15 + Math.random() * 0.2), spin: (Math.random() - 0.5) * 12, rot: Math.random() * 6,
      });
    }
    this.rings.push({ x: px, y: py, t: 0, rgb: s.rgb });
    this.flash = Math.max(this.flash, 0.45);
    this.shake = Math.max(this.shake, 10 * this.dpr);
    this.derez[seat] = performance.now();
    if (this.onCrash) this.onCrash(seat);
  }

  currentAngles(now) {
    const a = this.anim;
    if (!a) return this.headings.map((h) => h * 90);
    const p = Math.max(0, Math.min(1, (now - a.t0) / Math.max(1, a.dur * 0.35)));
    const e = 1 - (1 - p) * (1 - p);
    return a.angFrom.map((f, i) => f + (a.angTo[i] - f) * e);
  }

  headPositions(now) {
    const a = this.anim;
    const p = a ? Math.max(0, Math.min(1, (now - a.t0) / Math.max(1, a.dur))) : 1;
    return this.paths.map((path, seat) => {
      const end = path[path.length - 1];
      if (!end) return null;
      if (a && a.grew[seat] && path.length >= 2) {
        const prev = path[path.length - 2];
        return [this.x(prev[1] + (end[1] - prev[1]) * p), this.y(prev[0] + (end[0] - prev[0]) * p)];
      }
      return [this.x(end[1]), this.y(end[0])];
    });
  }

  // ---- the frame -----------------------------------------------------------------------
  frame(now) {
    const dt = Math.min(0.05, (now - this.last) / 1000);
    this.last = now;
    const g = this.ctx;
    const { W, cell } = this;
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalCompositeOperation = "source-over";
    g.globalAlpha = 1;
    if (this.shake > 0.3) {
      g.fillStyle = "#02040a";
      g.fillRect(0, 0, W, W);
      g.translate((Math.random() - 0.5) * this.shake, (Math.random() - 0.5) * this.shake);
      this.shake *= Math.pow(0.002, dt);
    } else this.shake = 0;
    g.drawImage(this.floor, 0, 0);

    // A slow light sweep across the floor.
    const sweep = ((now / 5200) % 1) * (W + W * 0.5) - W * 0.25;
    const sg = g.createLinearGradient(0, sweep - W * 0.12, 0, sweep + W * 0.12);
    sg.addColorStop(0, "rgba(60,160,255,0)");
    sg.addColorStop(0.5, this.active ? "rgba(60,160,255,0.035)" : "rgba(60,160,255,0.07)");
    sg.addColorStop(1, "rgba(60,160,255,0)");
    g.fillStyle = sg;
    g.fillRect(this.pad, this.pad, W - 2 * this.pad, W - 2 * this.pad);

    // A brain neuron's receptive field, when one is zoomed in (set by main.js each frame).
    if (this.overlay && this.overlay.values) {
      const o = this.overlay;
      g.globalCompositeOperation = "lighter";
      for (let q = 0; q < this.size * this.size; q++) {
        const v = o.values[q];
        const a = (Math.abs(v) - (o.floor || 0)) / (1 - (o.floor || 0));
        if (a <= 0) continue;
        const c = v > 0 ? o.exc : o.inh;
        g.fillStyle = `rgba(${c[0]},${c[1]},${c[2]},${0.12 + 0.4 * a})`;
        g.fillRect(this.pad + (q % this.size) * cell + 1, this.pad + Math.floor(q / this.size) * cell + 1, cell - 2, cell - 2);
      }
      g.globalCompositeOperation = "source-over";
    }

    const heads = this.headPositions(now);
    const angles = this.currentAngles(now);
    if (this.showEye && heads[0] && this.active && this.alive[0]) this.drawEye(g, heads[0], angles[0]);

    // Pools of light on the floor under each head.
    g.globalCompositeOperation = "lighter";
    for (let seat = 0; seat < 2; seat++) {
      if (!heads[seat]) continue;
      const r = cell * 7;
      g.globalAlpha = this.alive[seat] ? 0.22 : 0.08;
      g.drawImage(this.sprites[seat], heads[seat][0] - r, heads[seat][1] - r, 2 * r, 2 * r);
    }
    g.globalAlpha = 1;
    g.globalCompositeOperation = "source-over";

    // Light walls: the cached part, then the live newest segment.
    for (let seat = 0; seat < 2; seat++) {
      let alpha = 1;
      if (this.derez[seat] !== null) {
        const t = (now - this.derez[seat]) / 1000;
        alpha = t < 0.9 ? (Math.random() < 0.35 ? 0.25 : 0.95) : Math.max(0.22, 1 - (t - 0.9) * 1.2);
      }
      g.globalAlpha = alpha;
      g.drawImage(this.layers[seat], 0, 0);
      const path = this.paths[seat];
      if (this.anim && this.anim.grew[seat] && path.length >= 2 && heads[seat]) {
        this.strokeTrail(g, seat, path, path.length - 1, path.length - 2, heads[seat]);
      }
    }
    g.globalAlpha = 1;

    // The cycles.
    for (let seat = 0; seat < 2; seat++) {
      if (!heads[seat]) continue;
      this.drawCycle(g, seat, heads[seat], angles[seat], now);
    }

    // Explosions.
    g.globalCompositeOperation = "lighter";
    this.drawParticles(g, dt);
    g.globalCompositeOperation = "source-over";
    if (this.flash > 0.01) {
      g.setTransform(1, 0, 0, 1, 0, 0);
      g.fillStyle = `rgba(255,255,255,${this.flash})`;
      g.fillRect(0, 0, W, W);
      this.flash *= Math.pow(0.0005, dt);
    }
  }

  drawCycle(g, seat, [hx, hy], angle, now) {
    const s = SEATS[seat];
    const cell = this.cell;
    const alive = this.alive[seat];
    g.globalCompositeOperation = "lighter";
    const pulse = 1 + 0.08 * Math.sin(now / 90 + seat);
    const r = cell * 1.7 * pulse;
    g.globalAlpha = alive ? 0.9 : 0.25;
    g.drawImage(this.sprites[seat], hx - r, hy - r, 2 * r, 2 * r);
    g.globalAlpha = 1;
    g.globalCompositeOperation = "source-over";
    if (!alive) return;
    g.save();
    g.translate(hx, hy);
    g.rotate((angle * Math.PI) / 180);
    g.shadowColor = s.main;
    g.shadowBlur = cell * 0.8;
    // Body: a rounded capsule pointing forward (-y), with a bright nose.
    const L = cell * 0.98;
    const Wd = cell * 0.5;
    g.fillStyle = s.main;
    roundRect(g, -Wd / 2, -L * 0.62, Wd, L, Wd * 0.45);
    g.fill();
    g.shadowBlur = cell * 0.4;
    g.fillStyle = s.core;
    roundRect(g, -Wd * 0.22, -L * 0.6, Wd * 0.44, L * 0.62, Wd * 0.22);
    g.fill();
    g.fillStyle = "#ffffff";
    g.beginPath();
    g.arc(0, -L * 0.5, Wd * 0.2, 0, Math.PI * 2);
    g.fill();
    g.restore();
  }

  drawEye(g, [hx, hy], angle) {
    const cell = this.cell;
    g.save();
    g.beginPath();
    g.rect(this.pad, this.pad, this.W - 2 * this.pad, this.W - 2 * this.pad);
    g.clip();
    g.translate(hx, hy);
    g.rotate((angle * Math.PI) / 180);
    // Local frame: x = to the rider's right, y = backwards (so forward is up).
    const rgb = SEATS[0].rgb;
    // Periphery: 7 x 7 blocks of 5 x 5 cells, forward -2..+4 blocks, sideways -3..+3. A
    // full-field brain (eyeKind "field") sees every cell; only its fovea is drawn.
    const px0 = -17.5 * cell, px1 = 17.5 * cell, py0 = -22.5 * cell, py1 = 12.5 * cell;
    if (this.eyeKind !== "field") {
    g.fillStyle = rgba(rgb, 0.025);
    g.fillRect(px0, py0, px1 - px0, py1 - py0);
    g.strokeStyle = rgba(rgb, 0.16);
    g.lineWidth = Math.max(1, this.dpr * 0.8);
    g.setLineDash([cell * 0.35, cell * 0.35]);
    g.beginPath();
    for (let k = 0; k <= 7; k++) {
      const x = px0 + k * 5 * cell;
      g.moveTo(x, py0); g.lineTo(x, py1);
      const y = py0 + k * 5 * cell;
      g.moveTo(px0, y); g.lineTo(px1, y);
    }
    g.stroke();
    g.setLineDash([]);
    }
    // Fovea: 9 x 9 cells, forward -3..+5, sideways -4..+4.
    const fx0 = -4.5 * cell, fy0 = -5.5 * cell, fw = 9 * cell;
    g.fillStyle = rgba(rgb, 0.06);
    g.fillRect(fx0, fy0, fw, fw);
    g.strokeStyle = rgba(rgb, 0.12);
    g.beginPath();
    for (let k = 1; k < 9; k++) {
      g.moveTo(fx0 + k * cell, fy0); g.lineTo(fx0 + k * cell, fy0 + fw);
      g.moveTo(fx0, fy0 + k * cell); g.lineTo(fx0 + fw, fy0 + k * cell);
    }
    g.stroke();
    g.strokeStyle = rgba(rgb, 0.5);
    g.lineWidth = Math.max(1, this.dpr * 1.2);
    const corner = cell * 1.2;
    // Corner brackets around the fovea.
    g.beginPath();
    for (const [cx, cy, sx, sy] of [[fx0, fy0, 1, 1], [fx0 + fw, fy0, -1, 1], [fx0, fy0 + fw, 1, -1], [fx0 + fw, fy0 + fw, -1, -1]]) {
      g.moveTo(cx + sx * corner, cy); g.lineTo(cx, cy); g.lineTo(cx, cy + sy * corner);
    }
    g.stroke();
    g.restore();
  }

  drawParticles(g, dt) {
    const keep = [];
    for (const p of this.particles) {
      p.life -= dt;
      if (p.life <= 0) continue;
      p.vx *= Math.pow(0.12, dt);
      p.vy *= Math.pow(0.12, dt);
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      const a = Math.min(1, p.life / p.max * 1.4);
      if (p.cube) {
        p.rot += p.spin * dt;
        g.save();
        g.translate(p.x, p.y);
        g.rotate(p.rot);
        g.fillStyle = rgba(p.rgb, a * 0.9);
        g.fillRect(-p.cube / 2, -p.cube / 2, p.cube, p.cube);
        g.restore();
      } else {
        g.strokeStyle = rgba(p.rgb, a);
        g.lineWidth = p.w;
        g.beginPath();
        g.moveTo(p.x, p.y);
        g.lineTo(p.x - p.vx * 0.035, p.y - p.vy * 0.035);
        g.stroke();
      }
      keep.push(p);
    }
    this.particles = keep;
    const rings = [];
    for (const r of this.rings) {
      r.t += dt;
      if (r.t > 0.7) continue;
      const k = r.t / 0.7;
      g.strokeStyle = rgba(r.rgb, (1 - k) * 0.8);
      g.lineWidth = this.cell * 0.25 * (1 - k) + 1;
      g.beginPath();
      g.arc(r.x, r.y, this.cell * (0.5 + 5 * Math.sqrt(k)), 0, Math.PI * 2);
      g.stroke();
      const s = this.cell * 3 * (1 - k);
      g.globalAlpha = 1 - k;
      g.drawImage(this.white, r.x - s, r.y - s, 2 * s, 2 * s);
      g.globalAlpha = 1;
      rings.push(r);
    }
    this.rings = rings;
  }
}

function roundRect(g, x, y, w, h, r) {
  g.beginPath();
  g.moveTo(x + r, y);
  g.arcTo(x + w, y, x + w, y + h, r);
  g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r);
  g.arcTo(x, y, x + w, y, r);
  g.closePath();
}
