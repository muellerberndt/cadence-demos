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
  if (b.decisions !== undefined && !b.same && b.slots) {
    if (b.decisions !== lastDecision) { view.setSnap(b); lastDecision = b.decisions; arrived = performance.now(); }
  }
  if (!b.slots) return;
  drawOverlay(b.fovea);
  document.querySelectorAll("#pad [data-b]").forEach((el) => el.classList.toggle("lit", (b.look ? b.look.played : b.buttons).includes(el.dataset.b)));
  drawSlots(b.slots, b.act);
  $("settle").textContent = `${b.sweeps ?? "?"} sweeps, ${b.act_ms} ms${b.qualified === false ? ", not settled" : ""}`;
}
frameImage.onload = () => screen.drawImage(frameImage, 0, 0);

// the brain view: a new decision restarts the settle animation (its sweeps over SETTLE_MS)
const view = new BrainView($("brainview"));
const SETTLE_MS = 600;
let lastDecision = -1, arrived = 0;
function fitBrain() {
  const c = $("brainview"), w = c.clientWidth, ratio = window.devicePixelRatio || 1;
  const [bw, bh] = window.BRAIN_VIEW_SIZE;
  c.width = Math.round(w * ratio); c.height = Math.round(w * bh / bw * ratio);
}
window.addEventListener("resize", fitBrain);
fitBrain();
function animate(now) {
  view.draw(Math.min(1, (now - arrived) / SETTLE_MS), now);
  requestAnimationFrame(animate);
}
requestAnimationFrame(animate);
frameImage.onload = () => screen.drawImage(frameImage, 0, 0);

async function loadMeta() {
  try {
    const m = await (await fetch("/api/meta")).json();
    const d = m.describe || {};
    const rc = m.receipt || {};
    if (m.lookahead) {
      document.querySelector("header h1").textContent = "Castlevania, played by a Cadence brain + look-ahead";
      document.querySelector("header .about").textContent = "The frozen brain proposes every press. Near enemies a look-ahead over the emulator's savestates plays its move and a few safer ones out and overrules it only when another loses clearly less health; the brain view marks those decisions amber.";
    }
    const rows = [
      ["brain file", m.brain], ["inputs", d.inputs], ["modules", JSON.stringify(d.modules)], ["neurons", d.neurons], ["synapses", d.synapses],
      ...(rc.summary ? Object.entries(rc.summary) : []),
    ].filter(([, v]) => v !== undefined);
    $("about-brain").innerHTML = `<table>${rows.map(([k, v]) => `<tr><td>${k}</td><td>${typeof v === "object" ? JSON.stringify(v) : v}</td></tr>`).join("")}</table>`;
  } catch (e) { $("about-brain").textContent = String(e); }
}

async function poll() {
  try {
    const s = await (await fetch(`/api/state?since=${lastDecision}`, { cache: "no-store" })).json();
    if (s.brain && s.brain.same) s.brain = view.snap || s.brain;
    draw(s);
  } catch (e) { /* server restarting */ }
  setTimeout(poll, 50);
}
loadMeta();
poll();
