// The brain inspector: senses as compass roses and bars, the association cortex as a settled
// grid, the motor cortex slot by slot with the chosen command, the arousal law's level against
// its threshold with the recent history of level and reward. Ported from the arena viewer.
import { Frame, MODE_NAME, PALETTE, Spec, THEME, modeColor } from "./types";

export type BrainHistory = { level: number[]; reward: number[] };

function section(c: CanvasRenderingContext2D, text: string, x: number, y: number) {
  c.fillStyle = THEME.ink; c.font = "600 13px Inter, system-ui"; c.textAlign = "left"; c.fillText(text, x, y + 6);
}
function rose(c: CanvasRenderingContext2D, cx0: number, cy0: number, R: number, cells: number[], color: string, title: string) {
  c.strokeStyle = THEME.line; c.lineWidth = 1; c.beginPath(); c.arc(cx0, cy0, R, 0, Math.PI * 2); c.stroke();
  const ang = [-Math.PI / 2, Math.PI, Math.PI / 2, 0];
  cells.forEach((v, k) => {
    const a = ang[k], rr = R * Math.max(0.06, Math.min(1, v));
    c.fillStyle = color; c.globalAlpha = 0.25 + 0.75 * Math.min(1, v);
    c.beginPath(); c.moveTo(cx0, cy0); c.arc(cx0, cy0, rr, a - 0.7, a + 0.7); c.closePath(); c.fill(); c.globalAlpha = 1;
  });
  c.fillStyle = THEME.ink; c.beginPath(); c.moveTo(cx0, cy0 - 7); c.lineTo(cx0 - 5, cy0 + 5); c.lineTo(cx0 + 5, cy0 + 5); c.closePath(); c.fill();
  c.fillStyle = THEME.muted; c.font = "12px Inter, system-ui"; c.textAlign = "center"; c.fillText(title, cx0, cy0 + R + 16); c.textAlign = "left";
}
function bars(c: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, names: string[], values: number[], color: string, lw = 92) {
  const n = names.length, rh = Math.min(17, h / Math.max(1, n));
  for (let k = 0; k < n; k++) {
    const yy = y + k * rh, v = Math.max(0, Math.min(1, values[k] ?? 0));
    c.fillStyle = THEME.muted; c.font = "11px Inter, system-ui"; c.textAlign = "right"; c.fillText(names[k], x + lw - 6, yy + rh - 5);
    c.fillStyle = THEME.line; c.fillRect(x + lw, yy + 3, w - lw, rh - 6);
    c.fillStyle = color; c.fillRect(x + lw, yy + 3, (w - lw) * v, rh - 6);
  }
  c.textAlign = "left";
}

export function drawBrain(c: CanvasRenderingContext2D, W: number, H: number, i: number, f: Frame, spec: Spec, hist: BrainHistory) {
  const row = f.robots[i], b = row[9];
  c.fillStyle = THEME.panel; c.fillRect(0, 0, W, H);
  c.textBaseline = "alphabetic";
  const accent = PALETTE[i % PALETTE.length];
  if (!b) {
    c.fillStyle = THEME.muted; c.font = "18px Inter, system-ui"; c.textAlign = "left";
    c.fillText(row[4] === 9 ? `${spec.name} is out of the fight` : `${spec.name}: no brain activity in this moment`, 16, 40);
    return;
  }
  const [sens, assoc, motor, level, want, sweeps, learning, reward] = b;
  const mode = row[4];
  hist.level.push(level); hist.reward.push(reward); if (hist.level.length > 200) { hist.level.shift(); hist.reward.shift(); }
  let x0 = 16, y = 22;
  c.fillStyle = modeColor(mode); c.beginPath(); c.arc(x0 + 8, y + 6, 8, 0, Math.PI * 2); c.fill();
  c.fillStyle = THEME.ink; c.font = "600 18px Inter, system-ui"; c.textAlign = "left";
  c.fillText((MODE_NAME[mode] || "") + (mode === 1 ? " · sampling, learning" : mode === 0 ? " · routine, no learning" : ""), x0 + 26, y + 12);
  c.fillStyle = THEME.muted; c.font = "13px Inter, system-ui";
  c.fillText(`${sweeps} settling sweeps this moment${learning ? `, ${learning} learning sweeps` : ""} · reward ${reward >= 0 ? "+" : ""}${reward.toFixed(2)}`, x0 + 26, y + 32);
  y = 76; section(c, "Senses", x0, y);
  rose(c, x0 + 62, y + 84, 56, sens.slice(0, 4), accent, "nearest robot");
  rose(c, x0 + 196, y + 84, 56, sens.slice(4, 8), THEME.ring, "ring edge");
  bars(c, x0 + 262, y + 14, 150, 150, ["speed +", "speed -", "turn L", "turn R", "hit points", "pain", "dealt", "outside"], sens.slice(8, 16), "#8fa4c4", 62);
  const pnames = spec.inputs.slice(16, -1), pvals = sens.slice(16, -1);
  if (pnames.length) { section(c, "Proprioception", x0, y + 182); bars(c, x0, y + 196, 412, Math.min(190, 16 * pnames.length + 4), pnames, pvals, "#9fb8a1", 96); }
  x0 = 456; y = 22;
  section(c, `Association cortex · ${assoc.length} neurons, one settled state`, x0, y);
  const cols = 8, cell = Math.min(36, 360 / cols), rows = Math.ceil(assoc.length / cols);
  for (let k = 0; k < assoc.length; k++) {
    const v = Math.max(-1, Math.min(1, assoc[k])), cx0 = x0 + (k % cols) * cell, cy0 = y + 14 + Math.floor(k / cols) * cell;
    c.fillStyle = v >= 0 ? `rgba(255, 179, 71, ${0.06 + 0.94 * v})` : `rgba(79, 163, 255, ${0.06 + 0.94 * -v})`;
    c.fillRect(cx0 + 1, cy0 + 1, cell - 2, cell - 2);
  }
  c.fillStyle = THEME.muted; c.font = "12px Inter, system-ui"; c.textAlign = "left";
  c.fillText("orange active, blue below rest; the working trace carries it on", x0, y + 14 + rows * cell + 16);
  const my = y + 14 + rows * cell + 40;
  section(c, "Motor cortex · one slot per motor, the chosen command in white", x0, my);
  const slotW = Math.min(100, 372 / spec.slots.length); let k = 0;
  spec.slots.forEach((size, sidx) => {
    const sx = x0 + sidx * slotW, chosen = row[10] ? row[10][sidx] : null, kind = spec.motors[sidx].kind;
    const labels = size === 3 ? (kind === "arm" ? ["←", "hold", "→"] : kind === "leg" ? ["push", "hold", "swing"] : ["rev", "brake", "fwd"]) : ["off", "on"];
    for (let j = 0; j < size; j++, k++) {
      const v = motor[k] ?? 0, bw = (slotW - 10) / size - 3, bh = Math.max(0, Math.min(1, (v + 1) / 2)) * 54;
      c.fillStyle = j === chosen ? THEME.ink : (v >= 0 ? "rgba(255, 179, 71, 0.75)" : "rgba(79, 163, 255, 0.75)");
      c.fillRect(sx + j * (bw + 3), my + 70 - bh, bw, bh);
      c.fillStyle = THEME.muted; c.font = "10px Inter, system-ui"; c.textAlign = "center"; c.fillText(labels[j], sx + j * (bw + 3) + bw / 2, my + 82);
    }
    c.fillStyle = THEME.ink; c.font = "600 11px Inter, system-ui"; c.textAlign = "center"; c.fillText(spec.motors[sidx].label, sx + (slotW - 10) / 2, my + 96);
  });
  c.textAlign = "left";
  x0 = 860; y = 22; const gw = W - x0 - 16;
  section(c, "Arousal · routine or learning, decided by the brain's own law", x0, y);
  c.fillStyle = THEME.line; c.fillRect(x0, y + 20, gw, 12);
  c.fillStyle = mode === 1 ? THEME.aroused : THEME.calm; c.fillRect(x0, y + 20, gw * Math.min(1, level), 12);
  const thr = x0 + gw * 0.2; c.fillStyle = THEME.ink; c.fillRect(thr - 1, y + 16, 2, 20);
  c.fillStyle = THEME.muted; c.font = "12px Inter, system-ui";
  c.fillText(`level ${level.toFixed(2)} · threshold 0.20 · want ${want.toFixed(2)}`, x0, y + 50);
  const sh = 120, sy = y + 66; c.fillStyle = THEME.line; c.fillRect(x0, sy, gw, sh);
  const n = hist.level.length;
  for (let j = 0; j < n; j++) {
    const rx = x0 + j * gw / 200, rv = hist.reward[j];
    if (rv) { c.fillStyle = rv > 0 ? "rgba(90, 211, 122, 0.85)" : "rgba(255, 93, 93, 0.85)"; const rh = Math.min(sh / 2, Math.abs(rv) * sh); c.fillRect(rx, rv > 0 ? sy + sh / 2 - rh : sy + sh / 2, Math.max(1, gw / 200 - 1), rh); }
  }
  c.strokeStyle = THEME.aroused; c.lineWidth = 2; c.beginPath();
  for (let j = 0; j < n; j++) { const rx = x0 + j * gw / 200, ry = sy + sh - Math.min(1, hist.level[j]) * sh; j ? c.lineTo(rx, ry) : c.moveTo(rx, ry); }
  c.stroke();
  c.strokeStyle = THEME.ink; c.setLineDash([3, 3]); c.beginPath(); c.moveTo(x0, sy + sh * 0.8); c.lineTo(x0 + gw, sy + sh * 0.8); c.stroke(); c.setLineDash([]);
  c.fillStyle = THEME.muted; c.fillText("arousal level (orange) over the last 200 moments, dashed = threshold", x0, sy + sh + 16);
  c.fillText("reward per moment: green up, red down (damage dealt minus taken, /20, plus closing in)", x0, sy + sh + 32);
  const text = ["Calm: one settled state, the greedy command, no learning.", "A reward below what life usually pays, below the need, or an", "outcome that contradicts the forecast raises the level; above", "the threshold the brain samples wider, keeps eligibility and", "learns from every outcome until it is calm again."];
  text.forEach((t, j) => c.fillText(t, x0, sy + sh + 60 + j * 16));
  if (row[10]) {
    const ey = sy + sh + 150; section(c, "Efference · the command it just issued", x0, ey);
    c.fillStyle = THEME.ink; c.font = "13px Inter, system-ui"; c.fillText(row[10].map((cmd, sidx) => `${spec.motors[sidx].label}: ${cmd}`).join("  ·  ").slice(0, 70), x0, ey + 22);
  }
}
