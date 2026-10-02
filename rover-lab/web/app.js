"use strict";

// The viewer of the browser edition. The simulator runs in worker.js; every position, sample and patch state drawn
// here is read from the state it publishes. Rendering does not interpolate motion or advance the experiment clock.
const $ = (id) => document.getElementById(id);
const palette = {live: "#b3ddc7", frozen: "#d6b88e", adaptive: "#96b4cb", mlp: "#b4a9cc"};
let snapshot = null;
let pending = false;
let connected = false;
let busyMessage = "";
let baselineKey = "";
let patchKey = "";
let lastEventKey = "";
let resizeFrame;

const finite = (v) => typeof v === "number" && Number.isFinite(v);
const number = (v, digits = 2) => finite(v) ? v.toFixed(digits) : "—";
const text = (id, value) => { const node = $(id); if (node) node.textContent = value; };
const node = (tag, className, value) => {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (value !== undefined) element.textContent = value;
  return element;
};
function modelList(state) {
  if (Array.isArray(state?.models)) return state.models;
  return Object.entries(state?.models || {}).map(([id, value]) => ({id, ...value}));
}
function splitModels(state) {
  const all = modelList(state);
  const frozen = all.find((m) => /frozen/i.test(m.id + " " + m.label));
  const live = all.find((m) => m !== frozen && /cadence|live/i.test(m.id + " " + m.label)) || all[0];
  return {all, live, frozen, baselines: all.filter((m) => m !== live && m !== frozen)};
}
function modelColor(model, index = 0) {
  if (/frozen/i.test(model?.id + " " + model?.label)) return palette.frozen;
  if (/cadence|live/i.test(model?.id + " " + model?.label)) return palette.live;
  if (/mlp|neural/i.test(model?.id + " " + model?.label)) return palette.mlp;
  return index % 2 ? palette.mlp : palette.adaptive;
}
function showError(message) {
  text("error-banner", message);
  $("error-banner").hidden = !message;
}
function setConnection(ok, message) {
  connected = ok;
  $("connection-dot").className = "status-dot " + (ok ? "connected" : "failed");
  text("connection-status", message);
}
function updateControls() {
  const disabled = pending || !connected || !snapshot?.ready || Boolean(snapshot?.error);
  for (const id of ["auto-button", "play-button", "reset-button", "weaken-button", "restore-button", "relearn-button"]) $(id).disabled = disabled;
  $("relearn-button").hidden = snapshot?.phase !== "restored_probe";
  $("load-button").disabled = pending || !connected;
  $("wheel-gain").disabled = pending;
  for (const id of ["checkpoint-link", "receipt-link"]) $(id).disabled = disabled;
  text("play-button", snapshot?.running ? "Pause" : "Start");
}
let simulator = null;
let nextRequest = 1;
let latest = null;
let frame = 0;
const waiting = new Map();
function request(operation, data = null) {
  return new Promise((resolve, reject) => {
    if (!simulator) { reject(new Error("The simulator is not running")); return; }
    const id = nextRequest++;
    waiting.set(id, {resolve, reject});
    simulator.postMessage({id, operation, data});
  });
}
function startSimulator() {
  try {
    simulator = new Worker(new URL("./worker.js" + location.search, import.meta.url), {type: "module"});
  } catch (error) {
    setConnection(false, "Simulator unavailable");
    showError("This browser cannot start the simulator. Rover Lab needs module workers (Chrome 80, Safari 15, Firefox 114 or later).");
    return;
  }
  simulator.onmessage = (event) => {
    const message = event.data;
    if (message.type === "reply") {
      const entry = waiting.get(message.id);
      waiting.delete(message.id);
      if (!entry) return;
      if (message.error) entry.reject(new Error(message.error)); else entry.resolve(message.value);
    } else if (message.type === "state") {
      // Draw at most once per display frame, always from the newest published state.
      latest = message.state;
      if (!frame) frame = requestAnimationFrame(() => { frame = 0; if (latest) render(latest); });
    }
  };
  simulator.onerror = (event) => {
    setConnection(false, "Simulator stopped");
    showError(`The simulator stopped. ${event.message || "Reload the page to start again."}`);
    updateControls();
  };
  simulator.postMessage({id: nextRequest++, operation: "visibility", data: {hidden: document.hidden}});
}
function download(name, value) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([JSON.stringify(value)], {type: "application/json"}));
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 10000);
}
async function control(action) {
  if (pending) return;
  pending = true;
  busyMessage = ["auto", "reset"].includes(action) ? "Preparing a fresh life from measured motor experience…" : "";
  if (busyMessage) {text("notice", busyMessage); $("notice").hidden = false;}
  showError("");
  updateControls();
  try {
    await request("control", {action, weak_gain: Number($("wheel-gain").value)});
  } catch (error) { showError(error.message); }
  finally { pending = false; busyMessage = ""; updateControls(); }
}

$("auto-button").addEventListener("click", () => control("auto"));
$("play-button").addEventListener("click", () => control(snapshot?.running ? "pause" : "start"));
$("reset-button").addEventListener("click", () => control("reset"));
$("weaken-button").addEventListener("click", () => control("weaken"));
$("restore-button").addEventListener("click", () => control("restore"));
$("relearn-button").addEventListener("click", () => control("relearn"));
for (const [id, operation] of [["checkpoint-link", "checkpoint"], ["receipt-link", "receipt"]]) {
  $(id).addEventListener("click", async () => {
    try { download(`rover-${operation}.json`, await request(operation)); }
    catch (error) { showError(error.message); }
  });
}
$("load-button").addEventListener("click", () => $("checkpoint-file").click());
$("checkpoint-file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file || pending) return;
  pending = true;
  updateControls();
  try {
    const checkpoint = JSON.parse(await file.text());
    await request("restore", checkpoint);
    showError("");
  } catch (error) { showError(`Checkpoint could not be loaded: ${error.message}`); }
  finally { pending = false; event.target.value = ""; updateControls(); }
});

function clockValue(seconds) {
  if (!finite(seconds)) return "00:00.0";
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${(seconds % 60).toFixed(1).padStart(4, "0")}`;
}
function phaseIndex(state) {
  const name = String(state.phase || "").toLowerCase();
  if (/restore|return|retention/.test(name)) return 2;
  if (/weak|change|perturb|adapt|recover/.test(name) || (finite(state.wheel_gain) && state.wheel_gain < .999)) return 1;
  return 0;
}
function updateArenaMetrics(prefix, model) {
  $(prefix + "-empty").hidden = Boolean(model?.pose);
  if (!model) return;
  const targets = finite(model.targets) ? model.targets : model.targets_reached;
  const targetNode = $(prefix + "-targets");
  targetNode.replaceChildren(document.createTextNode(finite(targets) ? targets : "—"), node("small", "", ` / ${finite(model.attempts) ? model.attempts : "—"}`));
  const measured = Boolean(model.error_history?.length);
  text(prefix + "-error", measured ? number(model.prediction_error, 4) : "—");
  $(prefix + "-latency").replaceChildren(document.createTextNode(measured ? number(model.latency_ms, 1) : "—"), node("small", "", " ms"));
  ["left", "right"].forEach((side, index) => {
    const value = model.command?.[index];
    text(prefix + "-" + side, finite(value) ? value.toFixed(2) : "—");
    const bar = $(prefix + "-" + side + "-bar");
    const normalized = finite(value) ? Math.max(-1, Math.min(1, value)) : 0;
    bar.style.width = `${Math.abs(normalized) * 50}%`;
    bar.style.left = `${normalized < 0 ? 50 + normalized * 50 : 50}%`;
  });
}
function canvasContext(canvas) {
  const bounds = canvas.getBoundingClientRect();
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.max(1, bounds.width);
  const height = Math.max(1, bounds.height);
  if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);
  return {ctx, width, height};
}
function drawArena(canvas, model, color, compact = false) {
  const {ctx, width, height} = canvasContext(canvas);
  const trail = (model?.trail || []).filter((p) => Array.isArray(p) && finite(p[0]) && finite(p[1]));
  const pose = model?.pose;
  const target = model?.target;
  // One shared view keeps the paired rover positions directly comparable.
  const allPoints = modelList(snapshot).flatMap((m) => [m.pose, m.target, ...(m.trail || [])]).filter((p) => Array.isArray(p) && finite(p[0]) && finite(p[1]));
  let extent = 4;
  allPoints.forEach((p) => { extent = Math.max(extent, Math.abs(p[0]) + .6, Math.abs(p[1]) + .6); });
  const scale = (Math.min(width, height) - (compact ? 20 : 56)) / (2 * extent);
  const point = (p) => [width / 2 + p[0] * scale, height / 2 - p[1] * scale];
  ctx.lineWidth = 1;
  const gridStep = extent > 12 ? 4 : extent > 6 ? 2 : 1;
  for (let value = -Math.ceil(extent); value <= extent; value += gridStep) {
    ctx.strokeStyle = value === 0 ? "#303d33" : "#26312a";
    const [x, y] = point([value, value]);
    ctx.beginPath(); ctx.moveTo(x, compact ? 8 : 32); ctx.lineTo(x, height - (compact ? 8 : 21)); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(compact ? 8 : 21, y); ctx.lineTo(width - (compact ? 8 : 21), y); ctx.stroke();
  }
  if (!compact) {
    ctx.fillStyle = "#647368"; ctx.font = "8px monospace";
    ctx.fillText(`${gridStep} m grid`, 18, height - 13);
    ctx.textAlign = "right"; ctx.fillText("x →", width - 17, height - 13); ctx.textAlign = "left";
  }
  if (trail.length > 1) {
    ctx.beginPath(); trail.forEach((p, index) => { const [x, y] = point(p); if (!index) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
    ctx.strokeStyle = color; ctx.globalAlpha = .58; ctx.lineWidth = compact ? 1.2 : 1.7; ctx.lineJoin = "round"; ctx.stroke(); ctx.globalAlpha = 1;
    const origin = point(trail[0]); ctx.beginPath(); ctx.arc(...origin, 2, 0, 2 * Math.PI); ctx.fillStyle = color; ctx.fill();
  }
  if (Array.isArray(target) && target.every(finite)) {
    const [tx, ty] = point(target); const radius = compact ? 5 : 9;
    ctx.strokeStyle = "#d6b88e"; ctx.fillStyle = "#d6b88e12"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.arc(tx, ty, radius, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(tx - radius - 4, ty); ctx.lineTo(tx + radius + 4, ty); ctx.moveTo(tx, ty - radius - 4); ctx.lineTo(tx, ty + radius + 4); ctx.stroke();
    if (!compact) { ctx.fillStyle = "#a7967a"; ctx.font = "8px monospace"; ctx.fillText("TARGET", tx + 15, ty + 3); }
  }
  if (Array.isArray(pose) && pose.every(finite)) {
    const [x, y] = point(pose);
    ctx.save(); ctx.translate(x, y); ctx.rotate(-pose[2]);
    const size = compact ? 5 : 8;
    ctx.fillStyle = "#19251d"; ctx.strokeStyle = color; ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.moveTo(size + 3, 0); ctx.lineTo(size - 1, -size + 1); ctx.lineTo(-size, -size + 1); ctx.lineTo(-size, size - 1); ctx.lineTo(size - 1, size - 1); ctx.closePath(); ctx.fill(); ctx.stroke();
    ctx.fillStyle = color; ctx.fillRect(-size + 1, -size - 3, size + 3, 3);
    ctx.fillStyle = snapshot?.wheel_gain < .999 ? "#dfa988" : color;
    ctx.fillRect(-size + 1, size, size + 3, 3);
    ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(size + 6, 0); ctx.stroke(); ctx.restore();
  }
}
function historyValues(model) {
  return (model?.error_history || []).map((entry) => finite(entry) ? entry : Array.isArray(entry) ? entry[entry.length - 1] : entry?.error).filter(finite);
}
function drawChart(models) {
  const {ctx, width, height} = canvasContext($("error-chart"));
  const left = 42, right = width - 8, top = 9, bottom = height - 20;
  const histories = models.map(historyValues);
  const values = histories.flat();
  const upper = Math.max(.001, ...values);
  ctx.font = "8px monospace"; ctx.lineWidth = 1;
  for (let i = 0; i <= 3; i++) {
    const y = top + (bottom - top) * i / 3;
    ctx.strokeStyle = "#30392f"; ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke();
    ctx.fillStyle = "#778573"; ctx.textAlign = "right";
    const value = upper * (1 - i / 3);
    ctx.fillText(value < .1 ? value.toFixed(3) : value.toFixed(2), left - 8, y + 3);
  }
  ctx.textAlign = "left";
  if (!values.length) {
    ctx.fillStyle = "#7b897b"; ctx.fillText("Awaiting measured transitions", left + 8, top + (bottom - top) / 2);
    return;
  }
  histories.forEach((history, index) => {
    if (!history.length) return;
    ctx.strokeStyle = modelColor(models[index], index); ctx.lineWidth = 1.4; ctx.beginPath();
    history.forEach((value, i) => {
      const x = left + (right - left) * i / Math.max(history.length - 1, 1);
      const y = bottom - (bottom - top) * value / upper;
      if (!i) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }); ctx.stroke();
    if (history.length === 1) {ctx.fillStyle = ctx.strokeStyle; ctx.beginPath(); ctx.arc(left, bottom - (bottom - top) * history[0] / upper, 2, 0, Math.PI * 2); ctx.fill();}
  });
  ctx.fillStyle = "#697767"; ctx.font = "8px monospace";
  ctx.fillText("older", left, height - 4); ctx.textAlign = "right"; ctx.fillText("most recent", right, height - 4); ctx.textAlign = "left";
}
function updatePatches(model) {
  const patches = Array.isArray(model?.activity) ? model.activity : [];
  const key = patches.map((patch) => patch.name).join("|");
  if (key !== patchKey) {
    patchKey = key;
    $("patches").replaceChildren(...patches.map((patch) => {
      const card = node("div", "patch");
      card.append(node("div", "patch-name", patch.name || "Patch"));
      const reading = node("div", "patch-reading"); reading.append(node("strong"), node("span", "", "STATE")); card.append(reading);
      card.append(node("div", "state-cells"), node("div", "patch-error"));
      return card;
    }));
  }
  if (!patches.length) return;
  patches.forEach((patch, index) => {
    const card = $("patches").children[index];
    const states = Array.isArray(patch.state) ? patch.state.flat(Infinity).filter(finite) : finite(patch.state) ? [patch.state] : [];
    const average = states.length ? states.reduce((sum, value) => sum + value, 0) / states.length : undefined;
    card.querySelector("strong").textContent = number(average, 3);
    card.querySelector(".patch-error").textContent = `error ${number(patch.error, 4)}`;
    card.querySelector(".state-cells").replaceChildren(...states.slice(0, 24).map((value) => {
      const cell = node("i"); cell.style.height = `${2 + Math.min(1, Math.abs(value)) * 15}px`; cell.title = value.toFixed(5); return cell;
    }));
  });
}
function updateBaselines(models) {
  const key = models.map((model) => model.id).join("|");
  if (key !== baselineKey) {
    baselineKey = key;
    $("baselines").replaceChildren(...models.map((model, index) => {
      const card = node("article", "baseline-card"); card.style.setProperty("--model-color", modelColor(model, index));
      const canvas = node("canvas", "baseline-canvas"); canvas.setAttribute("aria-label", `${model.label} rover path and target`); card.append(canvas);
      const content = node("div", "baseline-content"); const title = node("div", "baseline-title");
      title.append(node("i", "model-dot"), node("h3", "", model.label || model.id)); content.append(title);
      content.append(node("p", "baseline-subtitle", /mlp|neural/i.test(model.id + " " + model.label) ? "Small neural motion model" : "Adaptive dynamics estimator"));
      const metrics = node("div", "baseline-numbers");
      ["Targets", "Prediction error"].forEach((label) => {const metric = node("div"); metric.append(node("span", "", label), node("strong")); metrics.append(metric);});
      content.append(metrics, node("div", "baseline-cost")); card.append(content); return card;
    }));
  }
  models.forEach((model, index) => {
    const card = $("baselines").children[index]; const metrics = card.querySelectorAll(".baseline-numbers strong");
    metrics[0].textContent = `${finite(model.targets) ? model.targets : "—"} / ${finite(model.attempts) ? model.attempts : "—"}`;
    metrics[1].textContent = model.error_history?.length ? number(model.prediction_error, 4) : "—";
    card.querySelector(".baseline-cost").textContent = `${model.error_history?.length ? number(model.latency_ms, 1) : "—"} ms / step · ${finite(model.deadline_misses) ? model.deadline_misses : "—"} deadline misses`;
    drawArena(card.querySelector("canvas"), model, modelColor(model, index), true);
  });
}
function updateEvents(state) {
  const events = (state.events || []).slice(-5).reverse();
  const key = JSON.stringify(events);
  if (key === lastEventKey) return;
  lastEventKey = key;
  if (!events.length) {$("events").replaceChildren(node("li", "", "No recorded events."));return;}
  $("events").replaceChildren(...events.map((event) => {
    const item = node("li"); item.append(node("span", "", `#${event.step ?? "—"}`), node("p", "", event.text || event.event || "Recorded transition")); return item;
  }));
}
function updateProtocol(state) {
  const protocol = state.protocol || {};
  const entries = Object.entries({ engine: state.engine, ...protocol }).filter(([, value]) => value === null || ["string", "number", "boolean"].includes(typeof value));
  $("protocol-data").replaceChildren(...entries.map(([key, value]) => {
    const item = node("div"); item.append(node("dt", "", key.replaceAll("_", " ")), node("dd", "", String(value))); return item;
  }));
}
function updateOutcomes(models) {
  const phases = ["normal", "weakened", "restored_probe", "restored_learning"];
  if (!models.length) return;
  $("phase-outcomes").replaceChildren(...models.map((model, index) => {
    const row = node("tr");
    const label = node("th", "", model.label || model.id); label.scope = "row"; label.style.setProperty("--model-color", modelColor(model, index)); row.append(label);
    phases.forEach((phase) => {
      const outcome = model.phase_metrics?.[phase];
      const cell = node("td");
      if (!outcome?.attempts) cell.textContent = "—";
      else {
        cell.append(node("strong", "", `${outcome.targets} / ${outcome.attempts}`));
        cell.append(node("span", "", `error ${number(outcome.prediction_rmse, 4)}`));
        cell.title = `Motion prediction RMSE: ${number(outcome.prediction_rmse, 4)}. Accumulated target distance: ${number(outcome.distance_integral, 2)} m·s. Deadline misses: ${outcome.deadline_misses ?? "—"}.`;
      }
      cell.classList.toggle("current-phase", snapshot?.phase === phase);
      row.append(cell);
    });
    return row;
  }));
}
function render(state) {
  snapshot = state;
  const {all, live, frozen, baselines} = splitModels(state);
  setConnection(!state.error || state.ready, !state.ready ? "Preparing models" : state.running ? "Simulator running" : "Simulator paused");
  text("simulation-clock", clockValue(state.sim_time)); text("step-count", `STEP ${state.step || 0}`);
  text("phase-badge", state.phase_label || (state.ready ? "Ready to run" : "Preparing models"));
  text("gain-readout", finite(state.wheel_gain) ? `${Math.round(state.wheel_gain * 100)}%` : "—");
  text("seed-label", `SEED ${state.seed ?? "—"}`);
  $("notice").hidden = Boolean(state.ready) && !busyMessage;
  text("notice", busyMessage || state.status || "Preparing the learned body models. The first checkpoint may take a moment.");
  if (state.error) showError(state.error);
  const phase = phaseIndex(state);
  document.querySelectorAll(".phase").forEach((element, index) => {element.classList.toggle("active", index === phase);element.classList.toggle("done", index < phase);});
  updateControls(); updateArenaMetrics("live", live); updateArenaMetrics("frozen", frozen);
  if (live) text("live-learning", state.phase === "restored_probe" ? "PROBE · LEARNING OFF" : live.learning === false ? "LEARNING PAUSED" : "LEARNING ENABLED");
  $("return-note").hidden = state.phase !== "restored_probe";
  text("restore-phase-detail", state.phase === "restored_probe" ? "Return probe · learning off" : state.phase === "restored_learning" ? "Relearning · state preserved" : "Probe first, then relearn");
  drawArena($("live-arena"), live, palette.live); drawArena($("frozen-arena"), frozen, palette.frozen);
  drawChart(all); updatePatches(live); updateBaselines(baselines); updateEvents(state); updateProtocol(state); updateOutcomes(all);
  $("chart-legend").replaceChildren(...all.map((model, index) => {
    const label = node("span"); const swatch = node("i");swatch.style.setProperty("--legend-color", modelColor(model, index));label.append(swatch, document.createTextNode(model.label || model.id));return label;
  }));
  const misses = all.reduce((sum, model) => sum + (model.deadline_misses || 0), 0);
  text("footer-status", `Step ${state.step || 0} · ${misses} recorded deadline misses · simulated in this page`);
}
window.addEventListener("resize", () => {
  cancelAnimationFrame(resizeFrame);
  resizeFrame = requestAnimationFrame(() => {
    if (snapshot) render(snapshot);
    else {drawArena($("live-arena"), null, palette.live); drawArena($("frozen-arena"), null, palette.frozen); drawChart([]);}
  });
});
document.addEventListener("visibilitychange", () => {
  if (simulator) simulator.postMessage({id: nextRequest++, operation: "visibility", data: {hidden: document.hidden}});
});
drawArena($("live-arena"), null, palette.live); drawArena($("frozen-arena"), null, palette.frozen); drawChart([]);
startSimulator();
