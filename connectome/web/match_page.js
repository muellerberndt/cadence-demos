// Page 4: the facts of the receipt, a wiring switch that fills the result column with each
// row's pass or fail and its numbers, the totals, every wiring at a glance, and the numbers of
// the spiking twin. Everything on the page comes from data/receipt_oculomotor.json.
import { mountShell, app, el, $, renderParagraphs, int, num, fetchJSON, RECEIPT_URL, sourcesList } from "./site.js";

const shell = mountShell("match", { status: "loading the receipt" });
$("page-title").textContent = shell.page.title;
renderParagraphs($("prose"), shell.page);

const receipt = await fetchJSON(RECEIPT_URL);
const facts = receipt.facts, wirings = receipt.wirings;
const GROUPS = [["measured", ["measured"]], ["matched", []], ["permuted", []]];
for (const name of Object.keys(wirings)) { const g = name.split(":")[0]; const group = GROUPS.find(([k]) => k === g); if (group && name !== "measured") group[1].push(name); }
for (const group of GROUPS) group[1].sort((a, b) => Number(a.split(":")[1] || 0) - Number(b.split(":")[1] || 0));
const ORDER = GROUPS.flatMap(([, names]) => names);

const rowOf = (w, id) => (w.rows || []).find((r) => r.id === id) || null;
const t1Of = (w) => (w.selection_trace || []).find((t) => Math.abs(t.gain - w.selected_gain) < 1e-9) || null;
/** The row's numbers as one line; the known rows by name, any other row flattened. */
function describeRow(id, r) {
  if (!r) return "no row";
  try {
    switch (id) {
      case "T1": return `integrator at +200 steps ${num(r.int_200)} · at +600 ${num(r.int_600)} · ratio ${num(r.int_200 > 0 ? r.int_600 / r.int_200 : 0)}${r.runaway ? " · runaway" : ""}`;
      case "H1": return `held 0.01: ${num(r.held["0.01"])} · 0.03: ${num(r.held["0.03"])} · 0.1: ${num(r.held["0.1"])} · ratios ${r.ratios.map((v) => num(v)).join(", ")}`;
      case "H2": return `eigenvalues ${r.eigenvalues.map((v) => num(v, 4)).join(", ")} · ratio ${num(r.ratio)}`;
      case "S1": return `submodule 1 onto ABD_m ${num(r.block1_to.abd_m)}, ABD_i ${num(r.block1_to.abd_i)} · submodule 2 onto ABD_m ${num(r.block2_to.abd_m)}, ABD_i ${num(r.block2_to.abd_i)} (synapses per target)`;
      case "H4": return `undisturbed ${num(r.undisturbed)} · pushed ${num(r.pushed)} · ratio ${num(r.undisturbed > 0 ? r.pushed / r.undisturbed : 0)}`;
      case "H5": return `top decile share ${num(r.top_decile_share)}`;
      case "H6": return `ABD_m ${num(r.abd_m)} · ABD_i ${num(r.abd_i)} · integrator ${num(r.int)}`;
    }
  } catch (e) { /* a row shaped differently falls through to the flat list */ }
  const parts = [];
  const walk = (prefix, v) => { if (typeof v === "number") parts.push(`${prefix} ${num(v)}`); else if (Array.isArray(v)) parts.push(`${prefix} ${v.map((x) => (typeof x === "number" ? num(x) : String(x))).join(", ")}`); else if (v && typeof v === "object") for (const [k, x] of Object.entries(v)) walk(`${prefix} ${k}`.trim(), x); };
  for (const [k, v] of Object.entries(r)) if (!["id", "passed", "counted"].includes(k)) walk(k.replace(/_/g, " "), v);
  return parts.join(" · ");
}
/** The result of one fact on one wiring: {passed, counted, numbers}. */
function result(fact, w) {
  if (fact.role === "training") { const t = t1Of(w); return { passed: !!(t && t.passed), counted: false, numbers: describeRow("T1", t) }; }
  const r = rowOf(w, fact.id);
  return { passed: !!(r && r.passed), counted: r ? r.counted !== false : false, numbers: describeRow(fact.id, r) };
}
const verdict = (res) => el("span", { class: res.passed ? "pass" : "fail" }, res.passed ? "pass" : "fail");

// the facts table
$("facts").querySelector("tbody").replaceChildren(...facts.map((f) => el("tr", { id: `fact-${f.id}` },
  el("td", { class: "id" }, f.id), el("td", {}, f.name), el("td", { class: "muted" }, f.role === "held-out" ? "scored; not gain selection" : f.role), el("td", { class: "pred" }, f.predicate), el("td", { class: "src" }, f.source), el("td", { class: "res", id: `res-${f.id}` }))));

// the wiring switch
const buttons = new Map();
$("wirings").replaceChildren(...GROUPS.filter(([, names]) => names.length).map(([label, names]) => el("div", { class: "group" }, label === "measured" ? null : el("span", {}, label), el("span", { class: "seg" }, ...names.map((name) => {
  const b = el("button", { type: "button", "data-wiring": name, onclick: () => select(name) }, name === "measured" ? "measured" : name.split(":")[1]);
  buttons.set(name, b);
  return b;
})))));
let current = null;
function select(name) {
  const w = wirings[name];
  if (!w) return;
  current = name;
  for (const [k, b] of buttons) b.classList.toggle("on", k === name);
  for (const f of facts) {
    const res = result(f, w);
    $(`res-${f.id}`).replaceChildren(verdict(res), res.counted ? "" : el("span", { class: "muted" }, " · not counted"), el("span", { class: "numbers" }, res.numbers));
  }
  const nr = w.null_report;
  $("totals").replaceChildren(`${w.label || name}: passed ${int(w.passed)} of ${int(w.counted)} counted · selected gain ${num(w.selected_gain, 6)}`,
    nr ? el("span", { class: "null" }, `shuffle: pairs kept ${num(nr.pairs_kept)} · in-degree ${nr.in_degree_kept ? "kept" : "changed"} · out-degree ${nr.out_degree_kept ? "kept" : "changed"} · median relative change of the excitatory in-strength ${num(nr.excitatory_in_strength_median_relative_change)}, of the inhibitory ${num(nr.inhibitory_in_strength_median_relative_change)}`) : "");
  for (const tr of $("glance").querySelectorAll("tr[data-wiring]")) tr.classList.toggle("on", tr.dataset.wiring === name);
  shell.status(`${w.label || name} · gain ${num(w.selected_gain, 6)} · passed ${int(w.passed)} of ${int(w.counted)} counted`);
}

// every wiring at a glance
$("glance").querySelector("thead").replaceChildren(el("tr", {}, el("th", {}, "wiring"), ...facts.map((f) => el("th", {}, f.id)), el("th", {}, "passed"), el("th", {}, "gain")));
$("glance").querySelector("tbody").replaceChildren(...ORDER.map((name) => {
  const w = wirings[name];
  return el("tr", { class: "pick", "data-wiring": name, onclick: () => select(name) }, el("td", {}, name),
    ...facts.map((f) => { const res = result(f, w); return el("td", { class: res.passed ? "pass" : "fail", title: `${f.id}: ${res.passed ? "pass" : "fail"}${res.counted ? "" : ", not counted"}` }, res.passed ? "✓" : "×"); }),
    el("td", {}, `${int(w.passed)}/${int(w.counted)}`), el("td", {}, num(w.selected_gain, 4)));
}));

// the spiking twin
const sp = receipt.spiking || {};
const se = sp.static_equivalence || {}, ig = sp.ignited || {};
const kv = (label, value) => el("div", { class: "kv" }, el("span", {}, label), el("b", {}, value));
$("spiking-kv").replaceChildren(
  kv("weight for the rate comparison", `${num(sp.static_weight_mv)} mV per synapse`),
  kv("stored spatial-pattern agreement", `cosine ${num(se.cosine)} · Spearman ${num(se.spearman)} · ${int(se.neurons_compared || 0)} neurons`),
  kv("first sustained scan weight", `${num(sp.critical_weight_mv)} mV per synapse`),
  kv("ignited integrator rate", `${num(ig.int_300_500_hz)} Hz at 300 to 500 ms · ${num(ig.int_1200_1500_hz)} Hz at 1200 to 1500 ms`),
  kv("ignited pattern against the patch net's", `cosine ${num(ig.cos_rate_held)}`));
const scan = sp.scan || [];
if (scan.length) {
  const xs = scan.map((s) => s.w_syn_mv), ys = scan.map((s) => s.int_300_500_hz || 0);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), ymax = Math.max(1, ...ys);
  const X = (v) => 36 + ((v - x0) / (x1 - x0 || 1)) * 356, Y = (v) => 8 + (1 - v / ymax) * 92;
  const svg = $("scan");
  const node = (tag, attrs, text) => { const e = document.createElementNS("http://www.w3.org/2000/svg", tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (text != null) e.textContent = text; return e; };
  svg.replaceChildren(
    node("line", { x1: 36, y1: Y(0), x2: 392, y2: Y(0), stroke: "rgba(97,186,121,.35)" }),
    node("text", { x: 32, y: Y(0) + 3, fill: "#679774", "font-size": "9", "text-anchor": "end" }, "0"),
    node("text", { x: 32, y: Y(ymax) + 4, fill: "#679774", "font-size": "9", "text-anchor": "end" }, num(ymax, 3)),
    node("text", { x: 36, y: 118, fill: "#679774", "font-size": "9" }, `${num(x0)} mV`),
    node("text", { x: 392, y: 118, fill: "#679774", "font-size": "9", "text-anchor": "end" }, `${num(x1)} mV`),
    node("polyline", { points: scan.map((s) => `${X(s.w_syn_mv)},${Y(s.int_300_500_hz || 0)}`).join(" "), fill: "none", stroke: "#67e78e", "stroke-width": "1.5" }),
    ...scan.map((s) => node("circle", { cx: X(s.w_syn_mv), cy: Y(s.int_300_500_hz || 0), r: 2, fill: s.w_syn_mv >= sp.critical_weight_mv ? "#ffd166" : "#67e78e" })));
  $("scan-note").textContent = `the scan: the integrator's rate at 300 to 500 ms against the synaptic weight, ${int(scan.length)} weights from ${num(x0)} to ${num(x1)} mV; the rate stays at zero until ${num(scan.find((s) => (s.int_300_500_hz || 0) > 0)?.w_syn_mv ?? x1)} mV`;
}

// the card
const t = receipt.tables || {}, grid = receipt.gain_grid || [];
shell.card([
  `<b>The protocol.</b> Scope ${receipt.scope}: ${int(t.neurons)} neurons, ${int(t.connections)} connections, ${int(t.synapses)} synapses (${Object.entries(t.classes || {}).map(([k, v]) => `${k} ${int(v)}`).join(", ")}); ${int(t.inhibitory_neurons)} inhibitory neurons. The gain grid runs from ${num(grid[0], 4)} to ${num(grid[1], 4)} in ${int(grid[2])} one percent steps; a burst is ${int(receipt.burst_steps)} steps at level ${num(receipt.level)}; a hold is ${int(receipt.hold)} steps. Protocol digest ${receipt.protocol_digest}.`,
  `<b>Model declarations.</b> ${Object.values(receipt.declarations || {}).join(" ")}`,
  `<b>Looked at before the freeze.</b> ${Object.values(receipt.explored || {}).join("; ")}.`,
  sourcesList(),
]);
select("measured");
app.ready = true;
Object.assign(app, { select, current: () => current, receipt });
