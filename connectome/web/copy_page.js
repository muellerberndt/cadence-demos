// Page 1: the reconstructed skeletons, and the ledger of a picked cell from the connectome's
// own arrays (brain.json, CSR by receiving neuron): incoming partners, outgoing partners,
// synapse counts and signs. The picked cell and its partners light up in the view.
import { mountShell, app, el, $, renderParagraphs, int, describePayload, sourcesList, fetchJSON, SKELETONS_URL, SKELETONS_FALLBACK, BRAIN_URL, CLASS_NAMES } from "./site.js";
import { BrainView, loadPayload, HOT } from "./brain_view.js";
import { decodeArray } from "./brain.js";

const PARTNER = 0.6; // the level a partner lights up with; the picked cell is 1
const shell = mountShell("copy", { status: "loading the skeletons" });
$("page-title").textContent = shell.page.title;
renderParagraphs($("prose"), shell.page);

const [skeletons, brain] = await Promise.all([
  loadPayload(SKELETONS_URL).catch(() => loadPayload(SKELETONS_FALLBACK)),
  fetchJSON(BRAIN_URL),
]);
const view = new BrainView($("view-host"), skeletons, { spin: true });
addEventListener("resize", () => view.resize());
$("fit").onclick = () => view.fit();
$("spin").onclick = () => { view.options.spin = !view.options.spin; $("spin").classList.toggle("on", view.options.spin); };
$("loading").classList.add("gone");

// the connectome's arrays: synapses by receiving neuron, and the same synapses indexed by sender
const n = brain.n;
const rowPtr = decodeArray(brain.arrays.row_ptr, Int32Array);
const pre = decodeArray(brain.arrays.pre, Int32Array);
const count = decodeArray(brain.arrays.count, Uint16Array);
const sign = decodeArray(brain.arrays.sign, brain.arrays.sign_dtype === "int8" ? Int8Array : Float64Array);
const post = new Int32Array(pre.length);
const outPtr = new Int32Array(n + 1);
for (let e = 0; e < pre.length; e++) outPtr[pre[e] + 1]++;
for (let i = 0; i < n; i++) outPtr[i + 1] += outPtr[i];
const outEdge = new Int32Array(pre.length);
const fill = outPtr.slice(0, n);
for (let i = 0; i < n; i++) for (let e = rowPtr[i]; e < rowPtr[i + 1]; e++) { post[e] = i; outEdge[fill[pre[e]]++] = e; }
const skeletonOf = new Int32Array(n).fill(-1);
skeletons.cells.forEach((cell, k) => { if (cell.index >= 0 && cell.index < n) skeletonOf[cell.index] = k; });
const indexOfId = new Map(brain.id.map((id, i) => [id, i]));
const className = (i) => CLASS_NAMES[brain.kind[i]] || brain.kind[i];

const c = skeletons.counts;
$("view-foot").textContent = `${int(c.skeletons)} skeletons drawn · ${int(c.matrix_neurons)} neurons in the matrix · ${int(brain.edges)} synapse classes`;
shell.status(`${int(brain.n)} neurons · ${int(brain.edges)} synapse classes · ${int(brain.synapses)} synapses · click a soma to read its ledger`);
shell.card([
  ...describePayload(brain),
  "<b>This page.</b> The ledger of a picked cell is read from the payload's arrays: row_ptr and pre list the senders of every receiving neuron, count the synapses of each class, sign the sender's transmitter. The outgoing list is the same arrays indexed by sender. Partners light up in the view at 0.6, the picked cell at 1; the hot-only switch then shows the cell and its partners alone.",
  sourcesList(),
]);

// the ledger
const activity = new Float32Array(n);
let picked = -1, mode = "both";
function partners(i) {
  const incoming = [], outgoing = [];
  for (let e = rowPtr[i]; e < rowPtr[i + 1]; e++) incoming.push({ index: pre[e], count: count[e], sign: sign[e] });
  for (let k = outPtr[i]; k < outPtr[i + 1]; k++) { const e = outEdge[k]; outgoing.push({ index: post[e], count: count[e], sign: sign[e] }); }
  const byCount = (a, b) => b.count - a.count || a.index - b.index;
  return { incoming: incoming.sort(byCount), outgoing: outgoing.sort(byCount) };
}
function fillTable(table, rows) {
  const body = table.querySelector("tbody");
  body.replaceChildren(...rows.map((r) => el("tr", { class: `pick${skeletonOf[r.index] < 0 ? " dim" : ""}`, "data-index": r.index, title: skeletonOf[r.index] < 0 ? "no reconstructed skeleton" : "read this cell" },
    el("td", { class: "id" }, String(brain.id[r.index])), el("td", {}, className(r.index)), el("td", { class: "num" }, String(r.count)), el("td", { class: "num" }, r.sign < 0 ? "-" : "+"))));
  body.onclick = (e) => { const tr = e.target.closest("tr[data-index]"); if (tr) show(Number(tr.dataset.index)); };
}
const sum = (rows) => rows.reduce((t, r) => t + r.count, 0);
function show(i) {
  if (!(i >= 0 && i < n)) return;
  picked = i;
  const { incoming, outgoing } = partners(i);
  const sub = brain.submodule ? brain.submodule[i] : -1;
  $("pick-empty").hidden = true;
  $("pick-body").hidden = false;
  $("pick-head").replaceChildren("cell ", el("b", {}, String(brain.id[i])), ` · ${className(i)} (${brain.kind[i]})`, sub >= 0 ? ` · submodule ${sub}` : "", skeletonOf[i] < 0 ? " · no skeleton in the view" : "");
  $("in-sum").textContent = `${int(incoming.length)} cells, ${int(sum(incoming))} synapses`;
  $("out-sum").textContent = `${int(outgoing.length)} cells, ${int(sum(outgoing))} synapses`;
  $("in-count").textContent = `(${int(incoming.length)})`;
  $("out-count").textContent = `(${int(outgoing.length)})`;
  fillTable($("in-table"), incoming);
  fillTable($("out-table"), outgoing);
  light();
  shell.status(`cell ${brain.id[i]} · ${className(i)} · listens to ${int(incoming.length)} cells (${int(sum(incoming))} synapses) · talks to ${int(outgoing.length)} cells (${int(sum(outgoing))} synapses)`);
}
function light() {
  activity.fill(0);
  if (picked >= 0) {
    if (mode !== "out") for (let e = rowPtr[picked]; e < rowPtr[picked + 1]; e++) activity[pre[e]] = PARTNER;
    if (mode !== "in") for (let k = outPtr[picked]; k < outPtr[picked + 1]; k++) activity[post[outEdge[k]]] = PARTNER;
    activity[picked] = 1;
  }
  view.setActivity(activity);
}
for (const b of $("light-mode").querySelectorAll("button")) b.onclick = () => { mode = b.dataset.mode; for (const o of $("light-mode").querySelectorAll("button")) o.classList.toggle("on", o === b); light(); };
const find = () => { const i = indexOfId.get(Number($("find").value.trim())); if (i === undefined) { shell.status(`no cell ${$("find").value.trim()} in the matrix`); return; } show(i); };
$("find-go").onclick = find;
$("find").addEventListener("keydown", (e) => { if (e.key === "Enter") find(); });

// a click on a soma, as opposed to a drag of the view
let down = null;
view.canvas.addEventListener("pointerdown", (e) => { down = [e.clientX, e.clientY]; });
view.canvas.addEventListener("pointerup", (e) => {
  if (!down) return;
  const moved = Math.hypot(e.clientX - down[0], e.clientY - down[1]);
  down = null;
  if (moved > 4) return;
  const r = view.canvas.getBoundingClientRect();
  const hit = view.pick(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  if (hit && hit.index >= 0) show(hit.index);
});

// the loop
let last = performance.now(), windowStart = last, windowFrames = 0, frames = 0;
function frame(now) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.1, (now - last) / 1000);
  last = now;
  view.render(dt);
  frames++; windowFrames++;
  if (now - windowStart >= 1000) { $("fps").textContent = `${Math.round((windowFrames * 1000) / (now - windowStart))} fps · active ${view.activeCount} (≥ ${HOT})`; windowStart = now; windowFrames = 0; }
  if (!app.ready && frames >= 3) app.ready = true;
}
requestAnimationFrame(frame);
Object.assign(app, { view, pick: show, picked: () => picked, partners });
