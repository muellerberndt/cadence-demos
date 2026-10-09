// The isometric ring, drawn on a canvas: floor, the closing burn, every robot part by part
// (wheels, legs with planted feet, arms with their weapons), mood halos, trails, sparks,
// flames and smoke. Ported from the arena viewer; one call per displayed frame.
import { Frame, PALETTE, Spec, THEME, modeColor } from "./types";

const COS30 = Math.cos(Math.PI / 6), SIN30 = 0.5, ARM_LENGTH = 0.8;
const HEIGHT: Record<string, number> = { light: 0.3, medium: 0.4, heavy: 0.5 };

export type Spark = { x: number; y: number; d?: number; age: number; kind: string; vx?: number; vy?: number; vz?: number; z?: number };
export type DrawState = {
  sparks: Spark[];
  trails: [number, number, number][][];
  spinAngle: number[];
};

export function newDrawState(n: number): DrawState {
  return { sparks: [], trails: Array.from({ length: n }, () => []), spinAngle: Array.from({ length: n }, () => 0) };
}

export function shade(hex: string, amount: number): string {
  const n = parseInt(hex.slice(1), 16), r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  const f = (v: number) => Math.max(0, Math.min(255, v + amount));
  return `rgb(${f(r)}, ${f(g)}, ${f(b)})`;
}
const hexa = (hex: string, alpha: number) => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
};

export class Projector {
  cx = 0; cy = 0; S = 1;
  constructor(public W: number, public H: number, public radius: number) {
    this.S = Math.min(W / (2 * radius * Math.SQRT2 * COS30 + 2), H / (2 * radius * Math.SQRT2 * SIN30 + 3.5));
    this.cx = W / 2; this.cy = H / 2 - 0.4 * this.S;
  }
  project(x: number, y: number, z = 0): [number, number] {
    return [this.cx + (x - y) * COS30 * this.S, this.cy + (x + y) * SIN30 * this.S - z * this.S];
  }
  ellipse(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, z = 0, append = false) {
    const [sx, sy] = this.project(x, y, z);
    if (!append) ctx.beginPath();
    ctx.ellipse(sx, sy, r * Math.SQRT2 * COS30 * this.S, r * Math.SQRT2 * SIN30 * this.S, 0, 0, Math.PI * 2);
  }
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath(); ctx.moveTo(x + r, y); ctx.lineTo(x + w - r, y); ctx.quadraticCurveTo(x + w, y, x + w, y + r); ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h); ctx.lineTo(x + r, y + h); ctx.quadraticCurveTo(x, y + h, x, y + h - r); ctx.lineTo(x, y + r); ctx.quadraticCurveTo(x, y, x + r, y); ctx.closePath();
}

export function drawArena(
  ctx: CanvasRenderingContext2D, W: number, H: number, radius: number, f: Frame, specs: Spec[],
  state: DrawState, frameIndex: number, selected: number | null, dealtSoFar: number[],
) {
  const P = new Projector(W, H, radius), S = P.S;
  ctx.fillStyle = THEME.panel; ctx.fillRect(0, 0, W, H);
  // floor
  P.ellipse(ctx, 0, 0, radius);
  { const [gx, gy] = P.project(0, 0); const g = ctx.createRadialGradient(gx, gy, 0, gx, gy, radius * Math.SQRT2 * COS30 * S);
    g.addColorStop(0, shade(THEME.floor, 14)); g.addColorStop(1, shade(THEME.floor, -10)); ctx.fillStyle = g; }
  ctx.fill();
  ctx.strokeStyle = THEME.floorGrid; ctx.lineWidth = 1;
  for (let g = -radius; g <= radius; g += 2) {
    const h = Math.sqrt(Math.max(0, radius ** 2 - g * g));
    let p = P.project(g, -h), q = P.project(g, h); ctx.beginPath(); ctx.moveTo(...p); ctx.lineTo(...q); ctx.stroke();
    p = P.project(-h, g); q = P.project(h, g); ctx.beginPath(); ctx.moveTo(...p); ctx.lineTo(...q); ctx.stroke();
  }
  // the burn outside the ring
  if (f.zone < radius - 0.01) {
    P.ellipse(ctx, 0, 0, radius); P.ellipse(ctx, 0, 0, f.zone, 0, true);
    ctx.fillStyle = THEME.burn; ctx.fill("evenodd");
  }
  P.ellipse(ctx, 0, 0, f.zone); ctx.strokeStyle = THEME.ring; ctx.lineWidth = 2.5; ctx.setLineDash([8, 6]); ctx.lineDashOffset = -frameIndex * 0.8; ctx.stroke(); ctx.setLineDash([]);
  // trails
  specs.forEach((_, i) => {
    const row = f.robots[i]; const tr = state.trails[i];
    if (!row || row[4] === 9) return;
    if (!tr.length || tr[tr.length - 1][2] !== frameIndex) { if (tr.length && tr[tr.length - 1][2] > frameIndex) tr.length = 0; tr.push([row[0], row[1], frameIndex]); if (tr.length > 24) tr.shift(); }
  });
  // robots far to near
  const order = specs.map((_, i) => i).sort((a, b) => (f.robots[a][0] + f.robots[a][1]) - (f.robots[b][0] + f.robots[b][1]));
  for (const i of order) drawRobot(ctx, P, i, f.robots[i], specs[i], state, frameIndex, selected === i);
  // sparks
  for (const h of f.hits) {
    const big = h[2] >= 2.5;
    state.sparks.push({ x: h[0], y: h[1], d: h[2], age: 0, kind: "flash" });
    for (let k = 0; k < (big ? 8 : 3); k++) { const a = Math.random() * Math.PI * 2, v = 0.06 + Math.random() * 0.12; state.sparks.push({ x: h[0], y: h[1], vx: Math.cos(a) * v, vy: Math.sin(a) * v, vz: 0.1 + Math.random() * 0.15, z: 0.3, age: 0, kind: "spark" }); }
    if (big) state.sparks.push({ x: h[0], y: h[1], d: h[2], age: 0, kind: "number" });
  }
  state.sparks = state.sparks.filter((s) => s.age < 16);
  for (const s of state.sparks) {
    const life = 1 - s.age / 16;
    if (s.kind === "flash") {
      const [sx, sy] = P.project(s.x, s.y, 0.3), rad = Math.min(18, 4 + (s.d || 0) * 1.4) * (1 - s.age / 6);
      if (s.age < 6) { ctx.beginPath(); ctx.arc(sx, sy, rad, 0, Math.PI * 2); ctx.fillStyle = `rgba(255, 236, 160, ${1 - s.age / 6})`; ctx.fill(); }
    } else if (s.kind === "spark") {
      s.x += s.vx!; s.y += s.vy!; s.z! += s.vz!; s.vz! -= 0.03;
      const [sx, sy] = P.project(s.x, s.y, Math.max(0, s.z!));
      ctx.beginPath(); ctx.arc(sx, sy, 2 * life + 0.5, 0, Math.PI * 2); ctx.fillStyle = `rgba(255, ${160 + Math.round(80 * life)}, 60, ${life})`; ctx.fill();
    } else {
      const [sx, sy] = P.project(s.x, s.y, 0.8 + s.age * 0.05);
      ctx.fillStyle = `rgba(255, 240, 200, ${life})`; ctx.font = "bold 13px Inter, system-ui"; ctx.textAlign = "center";
      ctx.shadowColor = "rgba(0,0,0,0.7)"; ctx.shadowBlur = 3; ctx.fillText("-" + (s.d || 0).toFixed(0), sx, sy); ctx.shadowBlur = 0;
    }
    s.age++;
  }
  // flames outside the ring
  specs.forEach((spec, i) => {
    const row = f.robots[i]; if (row[4] === 9) return;
    if (Math.hypot(row[0], row[1]) > f.zone) {
      for (let k = 0; k < 4; k++) {
        const ph = ((frameIndex * 0.11) + k / 4) % 1, a = k * 1.7 + frameIndex * 0.2;
        const [sx, sy] = P.project(row[0] + 0.5 * spec.radius * Math.cos(a), row[1] + 0.5 * spec.radius * Math.sin(a), 0.1 + ph * 0.9);
        ctx.beginPath(); ctx.arc(sx, sy, (0.16 - 0.1 * ph) * S, 0, Math.PI * 2); ctx.fillStyle = `rgba(255, ${90 + Math.round(120 * (1 - ph))}, 40, ${0.8 * (1 - ph)})`; ctx.fill();
      }
    }
  });
  if (selected !== null && f.robots[selected]) {
    const row = f.robots[selected];
    P.ellipse(ctx, row[0], row[1], specs[selected].radius * 1.7); ctx.strokeStyle = THEME.ink; ctx.lineWidth = 1.5; ctx.setLineDash([3, 4]); ctx.stroke(); ctx.setLineDash([]);
  }
  void dealtSoFar;
}

function drawRobot(ctx: CanvasRenderingContext2D, P: Projector, i: number, row: Frame["robots"][number], spec: Spec, state: DrawState, t: number, _sel: boolean) {
  const [x, y, heading, hp, mode, strides, planted, angles, spins] = row;
  const S = P.S, r = spec.radius, h = HEIGHT[spec.chassis] || 0.4, dead = mode === 9;
  const color = dead ? THEME.dead : PALETTE[i % PALETTE.length];
  const fx = Math.cos(heading), fy = Math.sin(heading);
  const tr = state.trails[i];
  if (!dead && tr && tr.length > 1) {
    ctx.lineWidth = Math.max(1, 0.06 * S); ctx.lineCap = "round";
    for (let k = 1; k < tr.length; k++) {
      const a = tr[k - 1], b = tr[k], p = P.project(a[0], a[1], 0.02), q = P.project(b[0], b[1], 0.02);
      ctx.strokeStyle = hexa(color, 0.35 * k / tr.length); ctx.beginPath(); ctx.moveTo(...p); ctx.lineTo(...q); ctx.stroke();
    }
  }
  P.ellipse(ctx, x + 0.15, y + 0.15, r * 1.08); ctx.fillStyle = "rgba(0,0,0,0.28)"; ctx.fill();
  if (!dead && (mode === 0 || mode === 1)) {
    const pulse = mode === 1 ? 0.5 + 0.5 * Math.sin(t * 0.6) : 0.3;
    P.ellipse(ctx, x, y, r * (1.35 + 0.1 * pulse));
    ctx.strokeStyle = mode === 1 ? `rgba(255, 179, 71, ${0.35 + 0.45 * pulse})` : "rgba(79, 163, 255, 0.35)";
    ctx.lineWidth = Math.max(2, 0.09 * S); ctx.stroke();
  }
  let legIndex = 0, armIndex = 0;
  const arms: { part: Spec["parts"][number]; phi: number; mx: number; my: number; angle: number; spin: number }[] = [];
  spec.parts.forEach((part) => {
    const phi = heading + part.mount * Math.PI / 180, mx = x + r * Math.cos(phi), my = y + r * Math.sin(phi);
    if (part.kind === "wheel") drawWheel(ctx, P, mx, my, fx, fy, S, dead, color);
    else if (part.kind === "leg") { const s = strides[legIndex] ?? 0, up = !(planted[legIndex] ?? 1); legIndex++; drawLeg(ctx, P, mx, my, phi, fx, fy, s, up, h, S, dead, color); }
    else if (part.kind === "arm") { arms.push({ part, phi, mx, my, angle: angles[armIndex] ?? 0, spin: spins[armIndex] ?? 0 }); armIndex++; }
  });
  const [bx, by] = P.project(x, y, 0), [tx, ty] = P.project(x, y, h);
  const ea = r * Math.SQRT2 * COS30 * S, eb = r * Math.SQRT2 * SIN30 * S;
  const wall = ctx.createLinearGradient(bx - ea, by, bx + ea, by);
  wall.addColorStop(0, shade(color, -75)); wall.addColorStop(0.45, shade(color, -40)); wall.addColorStop(1, shade(color, -85));
  ctx.fillStyle = dead ? shade(THEME.dead, -25) : wall;
  ctx.beginPath(); ctx.ellipse(bx, by, ea, eb, 0, 0, Math.PI); ctx.lineTo(tx + ea, ty); ctx.ellipse(tx, ty, ea, eb, 0, 0, Math.PI, true); ctx.closePath(); ctx.fill();
  const plate = ctx.createRadialGradient(tx - ea * 0.3, ty - eb * 0.5, 1, tx, ty, ea);
  plate.addColorStop(0, dead ? THEME.dead : shade(color, 35)); plate.addColorStop(1, dead ? shade(THEME.dead, -15) : shade(color, -15));
  ctx.beginPath(); ctx.ellipse(tx, ty, ea, eb, 0, 0, Math.PI * 2); ctx.fillStyle = plate; ctx.fill();
  ctx.strokeStyle = dead ? shade(THEME.dead, -40) : shade(color, -60); ctx.lineWidth = Math.max(1, 0.05 * S); ctx.stroke();
  ctx.beginPath(); ctx.ellipse(tx, ty, ea * 0.62, eb * 0.62, 0, 0, Math.PI * 2); ctx.strokeStyle = dead ? shade(THEME.dead, -35) : shade(color, -45); ctx.stroke();
  for (let k = 0; k < 6; k++) {
    const a = heading + k * Math.PI / 3 + Math.PI / 6, [sx, sy] = P.project(x + r * 0.8 * Math.cos(a), y + r * 0.8 * Math.sin(a), h);
    ctx.beginPath(); ctx.arc(sx, sy, Math.max(1, 0.05 * S), 0, Math.PI * 2); ctx.fillStyle = dead ? shade(THEME.dead, -40) : shade(color, -55); ctx.fill();
  }
  if (dead) {
    ctx.strokeStyle = shade(THEME.dead, -60); ctx.lineWidth = Math.max(1, 0.05 * S);
    ctx.beginPath(); ctx.moveTo(tx - ea * 0.5, ty - eb * 0.2); ctx.lineTo(tx - ea * 0.1, ty + eb * 0.1); ctx.lineTo(tx + ea * 0.3, ty - eb * 0.3); ctx.stroke();
    for (let k = 0; k < 3; k++) {
      const ph = ((t * 0.07) + k / 3) % 1, [sx, sy] = P.project(x + 0.2 * Math.sin(k + t * 0.05), y, h + 0.3 + ph * 1.2);
      ctx.beginPath(); ctx.arc(sx, sy, (0.12 + 0.2 * ph) * S, 0, Math.PI * 2); ctx.fillStyle = `rgba(120, 125, 135, ${0.35 * (1 - ph)})`; ctx.fill();
    }
  } else {
    const [vx, vy] = P.project(x + r * 0.78 * fx, y + r * 0.78 * fy, h);
    ctx.beginPath(); ctx.ellipse(vx, vy, Math.max(2, 0.16 * S), Math.max(1.5, 0.1 * S), 0, 0, Math.PI * 2); ctx.fillStyle = mode === 1 ? "#ffd27a" : "#dff3ff"; ctx.fill();
    ctx.beginPath(); ctx.arc(vx, vy, Math.max(1, 0.06 * S), 0, Math.PI * 2); ctx.fillStyle = "#1b2030"; ctx.fill();
    const [ax, ay] = P.project(x - r * 0.4 * fx, y - r * 0.4 * fy, h), [a2x, a2y] = P.project(x - r * 0.4 * fx, y - r * 0.4 * fy, h + 0.45);
    ctx.strokeStyle = "#5a6275"; ctx.lineWidth = Math.max(1, 0.04 * S); ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(a2x, a2y); ctx.stroke();
    ctx.beginPath(); ctx.arc(a2x, a2y, Math.max(2, 0.08 * S), 0, Math.PI * 2); ctx.fillStyle = modeColor(mode); ctx.fill();
  }
  for (const a of arms) drawArm(ctx, P, i, a, h, S, dead, color, state);
  const [lx, ly] = P.project(x, y, h + 1.1), w = Math.max(44, 1.5 * S);
  ctx.fillStyle = "rgba(0,0,0,0.45)"; roundRect(ctx, lx - w / 2 - 2, ly - 2, w + 4, 9, 3); ctx.fill();
  const share = Math.max(0, hp / spec.hp);
  ctx.fillStyle = dead ? THEME.dead : (share > 0.35 ? THEME.hp : THEME.hpLow); roundRect(ctx, lx - w / 2, ly, w * share, 5, 2); ctx.fill();
  ctx.fillStyle = dead ? THEME.muted : THEME.ink; ctx.font = `600 ${Math.max(10, 0.5 * S)}px Inter, system-ui`; ctx.textAlign = "center";
  ctx.shadowColor = "rgba(0,0,0,0.6)"; ctx.shadowBlur = 4; ctx.fillText(spec.name, lx, ly - 7); ctx.shadowBlur = 0;
  ctx.beginPath(); ctx.arc(lx + w / 2 + 9, ly + 2.5, 4, 0, Math.PI * 2); ctx.fillStyle = modeColor(mode); ctx.fill();
}

function drawWheel(ctx: CanvasRenderingContext2D, P: Projector, mx: number, my: number, fx: number, fy: number, S: number, dead: boolean, color: string) {
  const len = 0.22, z = 0.14;
  const a = P.project(mx + len * fx, my + len * fy, z), b = P.project(mx - len * fx, my - len * fy, z);
  ctx.lineCap = "round";
  ctx.lineWidth = Math.max(4, 0.3 * S); ctx.strokeStyle = dead ? shade(THEME.dead, -30) : "#1f232c"; ctx.beginPath(); ctx.moveTo(...a); ctx.lineTo(...b); ctx.stroke();
  ctx.lineWidth = Math.max(2, 0.16 * S); ctx.strokeStyle = dead ? THEME.dead : "#3b414e"; ctx.beginPath(); ctx.moveTo(...a); ctx.lineTo(...b); ctx.stroke();
  ctx.lineWidth = Math.max(1, 0.04 * S); ctx.strokeStyle = "#6b7383";
  for (let k = -1; k <= 1; k++) {
    const p = P.project(mx + k * 0.12 * fx, my + k * 0.12 * fy, z + 0.12), q = P.project(mx + k * 0.12 * fx, my + k * 0.12 * fy, z - 0.1);
    ctx.beginPath(); ctx.moveTo(...p); ctx.lineTo(...q); ctx.stroke();
  }
  const hub = P.project(mx, my, z);
  ctx.beginPath(); ctx.arc(hub[0], hub[1], Math.max(1.5, 0.06 * S), 0, Math.PI * 2); ctx.fillStyle = dead ? THEME.dead : color; ctx.fill();
}

function drawLeg(ctx: CanvasRenderingContext2D, P: Projector, mx: number, my: number, phi: number, fx: number, fy: number, s: number, up: boolean, h: number, S: number, dead: boolean, color: string) {
  const out = 0.55, footX = mx + out * Math.cos(phi) + 0.35 * s * fx, footY = my + out * Math.sin(phi) + 0.35 * s * fy;
  const kneeX = mx + 0.5 * (footX - mx), kneeY = my + 0.5 * (footY - my);
  const hip = P.project(mx, my, h * 0.55), knee = P.project(kneeX, kneeY, h * 0.55 + (up ? 0.4 : 0.28)), foot = P.project(footX, footY, up ? 0.2 : 0);
  const bone = dead ? THEME.dead : shade(color, -40), joint = dead ? shade(THEME.dead, -20) : shade(color, -70);
  ctx.lineCap = "round"; ctx.lineJoin = "round";
  ctx.lineWidth = Math.max(3, 0.14 * S); ctx.strokeStyle = joint; ctx.beginPath(); ctx.moveTo(...hip); ctx.lineTo(...knee); ctx.lineTo(...foot); ctx.stroke();
  ctx.lineWidth = Math.max(1.5, 0.08 * S); ctx.strokeStyle = bone; ctx.beginPath(); ctx.moveTo(...hip); ctx.lineTo(...knee); ctx.lineTo(...foot); ctx.stroke();
  ctx.beginPath(); ctx.arc(knee[0], knee[1], Math.max(1.5, 0.07 * S), 0, Math.PI * 2); ctx.fillStyle = joint; ctx.fill();
  const cw = 0.12, c1 = P.project(footX + cw * Math.cos(phi + 0.9), footY + cw * Math.sin(phi + 0.9), up ? 0.2 : 0), c2 = P.project(footX + cw * Math.cos(phi - 0.9), footY + cw * Math.sin(phi - 0.9), up ? 0.2 : 0);
  ctx.lineWidth = Math.max(1.5, 0.07 * S); ctx.strokeStyle = up ? bone : joint;
  ctx.beginPath(); ctx.moveTo(...c1); ctx.lineTo(...foot); ctx.lineTo(...c2); ctx.stroke();
  if (!up) { ctx.beginPath(); ctx.arc(foot[0], foot[1], Math.max(2, 0.08 * S), 0, Math.PI * 2); ctx.fillStyle = joint; ctx.fill(); }
}

function drawArm(ctx: CanvasRenderingContext2D, P: Projector, i: number, a: { part: Spec["parts"][number]; phi: number; mx: number; my: number; angle: number; spin: number }, h: number, S: number, dead: boolean, color: string, state: DrawState) {
  const dir = a.phi + a.angle, L = ARM_LENGTH, tipX = a.mx + L * Math.cos(dir), tipY = a.my + L * Math.sin(dir);
  const base = P.project(a.mx, a.my, h), tip = P.project(tipX, tipY, h * 0.95), elbow = P.project(a.mx + 0.5 * L * Math.cos(dir), a.my + 0.5 * L * Math.sin(dir), h + 0.12);
  ctx.lineCap = "round"; ctx.lineJoin = "round";
  ctx.lineWidth = Math.max(4, 0.2 * S); ctx.strokeStyle = dead ? shade(THEME.dead, -30) : "#232834"; ctx.beginPath(); ctx.moveTo(...base); ctx.lineTo(...elbow); ctx.lineTo(...tip); ctx.stroke();
  ctx.lineWidth = Math.max(2, 0.1 * S); ctx.strokeStyle = dead ? THEME.dead : "#5c6577"; ctx.beginPath(); ctx.moveTo(...base); ctx.lineTo(...elbow); ctx.lineTo(...tip); ctx.stroke();
  ctx.beginPath(); ctx.arc(base[0], base[1], Math.max(2.5, 0.12 * S), 0, Math.PI * 2); ctx.fillStyle = dead ? THEME.dead : shade(color, -50); ctx.fill(); ctx.strokeStyle = "#1b2030"; ctx.lineWidth = 1; ctx.stroke();
  ctx.lineWidth = 1; ctx.strokeStyle = "#1b2030";
  if (a.part.weapon === "spike") {
    const ex = P.project(tipX + 0.38 * Math.cos(dir), tipY + 0.38 * Math.sin(dir), h * 0.95);
    const px = -(tip[1] - base[1]), py = tip[0] - base[0], n = Math.hypot(px, py) || 1, w = 0.11 * S;
    const g = ctx.createLinearGradient(tip[0] + px / n * w, tip[1] + py / n * w, tip[0] - px / n * w, tip[1] - py / n * w);
    g.addColorStop(0, "#f4f7fb"); g.addColorStop(0.5, "#aab3c3"); g.addColorStop(1, "#6a7383");
    ctx.fillStyle = dead ? THEME.dead : g;
    ctx.beginPath(); ctx.moveTo(tip[0] + px / n * w, tip[1] + py / n * w); ctx.lineTo(...ex); ctx.lineTo(tip[0] - px / n * w, tip[1] - py / n * w); ctx.closePath(); ctx.fill(); ctx.stroke();
  } else if (a.part.weapon === "hammer") {
    const w = 0.2, d = 0.16, z0 = h * 0.95, z1 = z0 + 0.3;
    const ux = Math.cos(dir + Math.PI / 2), uy = Math.sin(dir + Math.PI / 2), vx = Math.cos(dir), vy = Math.sin(dir);
    const corner = (su: number, sv: number, z: number) => P.project(tipX + su * w * ux + sv * d * vx, tipY + su * w * uy + sv * d * vy, z);
    const faces = [
      { pts: [corner(-1, 1, z0), corner(1, 1, z0), corner(1, 1, z1), corner(-1, 1, z1)], col: "#b8955a" },
      { pts: [corner(1, -1, z0), corner(1, 1, z0), corner(1, 1, z1), corner(1, -1, z1)], col: "#8f7142" },
      { pts: [corner(-1, -1, z0), corner(-1, 1, z0), corner(-1, 1, z1), corner(-1, -1, z1)], col: "#8f7142" },
      { pts: [corner(-1, -1, z1), corner(1, -1, z1), corner(1, 1, z1), corner(-1, 1, z1)], col: "#e8d3a6" },
    ];
    for (const fc of faces) { ctx.beginPath(); ctx.moveTo(...fc.pts[0]); for (const p of fc.pts.slice(1)) ctx.lineTo(...p); ctx.closePath(); ctx.fillStyle = dead ? THEME.dead : fc.col; ctx.fill(); ctx.stroke(); }
  } else {
    const rr = 0.32; state.spinAngle[i] = (state.spinAngle[i] + a.spin * 0.9) % (Math.PI * 2);
    if (a.spin > 0.05 && !dead) { ctx.beginPath(); ctx.ellipse(tip[0], tip[1], (rr + 0.12) * Math.SQRT2 * COS30 * S, (rr + 0.12) * Math.SQRT2 * SIN30 * S, 0, 0, Math.PI * 2); ctx.fillStyle = `rgba(255, 150, 60, ${0.25 * a.spin})`; ctx.fill(); }
    ctx.beginPath(); ctx.ellipse(tip[0], tip[1] + 0.06 * S, rr * Math.SQRT2 * COS30 * S, rr * Math.SQRT2 * SIN30 * S, 0, 0, Math.PI * 2); ctx.fillStyle = "#2a2f3a"; ctx.fill();
    ctx.beginPath(); ctx.ellipse(tip[0], tip[1], rr * Math.SQRT2 * COS30 * S, rr * Math.SQRT2 * SIN30 * S, 0, 0, Math.PI * 2);
    ctx.fillStyle = dead ? THEME.dead : (a.spin > 0.05 ? `rgb(255, ${Math.round(215 - 130 * a.spin)}, 90)` : "#9aa3b5"); ctx.fill(); ctx.stroke();
    ctx.strokeStyle = "#1b2030"; ctx.lineWidth = Math.max(1, 0.06 * S);
    for (let k = 0; k < 4; k++) { const t = state.spinAngle[i] + k * Math.PI / 2, [ex, ey] = P.project(tipX + rr * Math.cos(t), tipY + rr * Math.sin(t), h * 0.95); ctx.beginPath(); ctx.moveTo(...tip); ctx.lineTo(ex, ey); ctx.stroke(); }
    ctx.beginPath(); ctx.arc(tip[0], tip[1], Math.max(2, 0.08 * S), 0, Math.PI * 2); ctx.fillStyle = "#e6e9ef"; ctx.fill();
  }
}

export function pickRobot(W: number, H: number, radius: number, f: Frame, px: number, py: number): number | null {
  const P = new Projector(W, H, radius); let best: number | null = null, bestD = 40;
  f.robots.forEach((row, i) => { const [sx, sy] = P.project(row[0], row[1], 0.3); const d = Math.hypot(sx - px, sy - py); if (d < bestD) { best = i; bestD = d; } });
  return best;
}
