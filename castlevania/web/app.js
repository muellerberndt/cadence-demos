// Polls the local server for the newest frame and the brain's last decision, and draws them.
const $ = (id) => document.getElementById(id);
const screen = $("screen").getContext("2d");
const overlay = $("overlay").getContext("2d");
const frameImage = new Image();
const SLOT_NAMES = [["horizontal", ["left", "-", "right"]], ["vertical", ["up", "-", "down"]], ["whip", ["no", "yes"]], ["jump", ["no", "yes"]]];
const STATES = ["ground", "jump", "whip", "crouch", "stairs", "knocked back", "onto stairs", "falling", "other", "recovering"];

for (let i = 0; i <= 42; i++) $("idle").add(new Option(String(i), String(i)));

async function post(path, body) {
  await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
}
$("pause").onclick = async () => { await post("/api/pause", {}); };
$("restart").onclick = async () => { await post("/api/restart", { idle: Number($("idle").value) }); };
document.querySelectorAll("[data-speed]").forEach((b) => {
  b.onclick = async () => {
    document.querySelectorAll("[data-speed]").forEach((x) => x.classList.toggle("on", x === b));
    await post("/api/speed", { speed: Number(b.dataset.speed) });
  };
});

// a value in [-0.6, 0.6] (or any range) drawn as gray; signed maps use red/blue
function heat(canvas, values, w, h, signed, lo = -0.6, hi = 0.6) {
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(w, h);
  for (let i = 0; i < w * h; i++) {
    const v = values[i] ?? 0;
    let r, g, b;
    if (signed) {
      const a = Math.max(-1, Math.min(1, v * 2));
      r = a > 0 ? 40 + 215 * a : 40; b = a < 0 ? 40 - 215 * a : 40; g = 40 + 60 * Math.abs(a);
    } else {
      const t = Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
      r = g = b = Math.round(255 * t);
    }
    img.data.set([r, g, b, 255], i * 4);
  }
  ctx.putImageData(img, 0, 0);
}

function activity(canvas, values, w, h) {
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(w, h);
  for (let i = 0; i < w * h; i++) {
    const t = Math.max(0, Math.min(1, ((values[i] ?? 0) + 0.1) / 1.1));
    img.data.set([Math.round(30 + 212 * t), Math.round(20 + 173 * t * t), Math.round(40 + 38 * t), 255], i * 4);
  }
  ctx.putImageData(img, 0, 0);
}

function drawOverlay(f) {
  overlay.clearRect(0, 0, 240, 224);
  if (!f) return;
  overlay.save();
  overlay.translate(-8, -8); // RAM coordinates on the core's picture, which lost 8 px per edge
  const behind = f.facing > 0 ? [f.left - 32, f.right - 32] : [f.left + 32, f.right + 32];
  overlay.lineWidth = 1.5;
  overlay.strokeStyle = "#4fa3e0";
  overlay.strokeRect(behind[0] + 0.5, f.top + 0.5, behind[1] - behind[0], f.bottom - f.top);
  overlay.strokeStyle = "#e0444f";
  overlay.strokeRect(f.left + 0.5, f.top + 0.5, f.right - f.left, f.bottom - f.top);
  overlay.restore();
}

function drawSlots(slots, act) {
  const chosen = [act[0] + 1, act[1] + 1, act[2], act[3]];
  $("slots").innerHTML = slots.map((vals, k) => {
    const [name, labels] = SLOT_NAMES[k];
    const lo = Math.min(...vals, -0.1), hi = Math.max(...vals, 1);
    const bars = vals.map((v, j) => `<div class="bar${j === chosen[k] ? " win" : ""}"><i style="width:${(100 * (v - lo) / (hi - lo)).toFixed(0)}%"></i><em>${labels[j]}</em></div>`).join("");
    return `<div class="slot"><span>${name}</span><div class="bars">${bars}</div></div>`;
  }).join("");
}

function drawMemory(m) {
  if (!m || !m.capacity) { $("memory").innerHTML = "<p>no recall memory</p>"; return; }
  let read = new Set();
  if (m.focus) m.focus.forEach((row) => { const j = row.indexOf(Math.max(...row)); if (row[j] > 0.2) read.add(j); });
  let cells = "";
  for (let i = 0; i < m.capacity; i++) cells += `<i class="${read.has(i) ? "read" : i < m.held ? "held" : ""}"></i>`;
  $("memory").innerHTML = cells + `<p>${m.held} of ${m.capacity} slots hold moments of this game; ${m.heads} read heads. The memory is written as the game goes and cleared at a new game.</p>`;
}

function draw(s) {
  if (s.frame) { frameImage.src = "data:image/png;base64," + s.frame; }
  const b = s.brain || {};
  const r = s.run || {};
  const g = b.game || {};
  $("pause").textContent = s.paused ? "Resume" : "Pause";
  document.querySelectorAll("[data-speed]").forEach((x) => x.classList.toggle("on", Number(x.dataset.speed) === s.speed));
  if (r.idle !== undefined && document.activeElement !== $("idle")) $("idle").value = String(r.idle);
  $("stats").innerHTML = [
    ["stage", g.stage ?? "-"], ["world x", g.world_x ?? "-"], ["health", g.health ?? "-"], ["lives", g.lives ?? "-"],
    ["furthest stage", r.furthest_stage ?? "-"], ["lives lost", r.lives_lost ?? 0], ["decisions", b.decisions ?? 0],
  ].map(([k, v]) => `<span>${k} <b>${v}</b></span>`).join("") + (r.over ? ` <span><b>game over</b></span>` : "");
  if (!b.slots) return;
  drawOverlay(b.fovea);
  document.querySelectorAll("#pad [data-b]").forEach((el) => el.classList.toggle("lit", b.buttons.includes(el.dataset.b)));
  drawSlots(b.slots, b.act);
  $("settle").textContent = `${b.sweeps ?? "?"} sweeps, ${b.act_ms} ms${b.qualified === false ? ", not settled" : ""}`;
  heat($("eye-scene"), b.eye.scene, 16, 12, false);
  heat($("eye-motion"), b.eye.motion, 16, 12, true);
  heat($("eye-ahead"), b.eye.ahead, 16, 12, false);
  heat($("eye-behind"), b.eye.behind, 16, 12, false);
  const hot = (v) => v.indexOf(Math.max(...v));
  $("readings").innerHTML = [["stage", hot(b.eye.stage)], ["block", hot(b.eye.block)], ["body", STATES[hot(b.eye.state)]], ["floor", hot(b.eye.floor)]]
    .map(([k, v]) => `<span>${k} <b>${v}</b></span>`).join("");
  for (const name of ["module_0", "association", "prefrontal"]) {
    const c = $("r-" + name);
    if (c && b.regions[name]) activity(c, b.regions[name], c.width, c.height);
  }
  drawMemory(b.memory);
}
frameImage.onload = () => screen.drawImage(frameImage, 0, 0);

async function loadMeta() {
  try {
    const m = await (await fetch("/api/meta")).json();
    const d = m.describe || {};
    const rc = m.receipt || {};
    const rows = [
      ["brain file", m.brain], ["inputs", d.inputs], ["modules", JSON.stringify(d.modules)], ["neurons", d.neurons], ["synapses", d.synapses],
      ...(rc.summary ? Object.entries(rc.summary) : []),
    ].filter(([, v]) => v !== undefined);
    $("about-brain").innerHTML = `<table>${rows.map(([k, v]) => `<tr><td>${k}</td><td>${typeof v === "object" ? JSON.stringify(v) : v}</td></tr>`).join("")}</table>`;
  } catch (e) { $("about-brain").textContent = String(e); }
}

async function poll() {
  try { draw(await (await fetch("/api/state", { cache: "no-store" })).json()); } catch (e) { /* server restarting */ }
  setTimeout(poll, 50);
}
loadMeta();
poll();
