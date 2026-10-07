// The disclaimers page: prose from content/disclaimers.js, every number in a table from a receipt in data/.
import { mountShell, app, el, $, fetchJSON, int } from "./site.js";
import { DISCLAIMERS } from "./content/disclaimers.js";
const num = (x, d = 3) => Number(x).toFixed(d);  // fixed decimals, the receipts' own precision
const pct = (x, d = 1) => `${(100 * Number(x)).toFixed(d)} %`;

const shell = mountShell("disclaimers", { status: "what is measured, what is declared, what is missing", connectome: "Verasztó et al. 2025 and Vishwanathan et al. 2024", connectomeUrl: "https://doi.org/10.7554/eLife.97964" });
$("page-title").textContent = DISCLAIMERS.title;
$("intro").textContent = DISCLAIMERS.intro;

function paragraphs(container, texts) { for (const t of texts) container.appendChild(el("p", {}, t)); }
function table(head, rows) {
  return el("table", {}, el("thead", {}, el("tr", {}, ...head.map((h) => el("th", {}, h)))), el("tbody", {}, ...rows.map((r) => el("tr", {}, ...r.map((c) => el("td", {}, String(c)))))));
}
const ROLE = { sensory: "sensory neurons", inter: "interneurons", motor: "motor neurons", effector: "effector cells (muscles, ciliated cells, glands)", unknown: "cells with no neuronal or effector role (epithelium, glia, pigment cells, untyped cells)" };

function censusTable(c) {
  const rows = [];
  for (const k of ["sensory", "inter", "motor", "effector", "unknown"]) rows.push([ROLE[k], int(c.by_role[k] || 0), int(c.without_a_synapse_by_role[k] || 0)]);
  rows.push(["all cells", int(c.cells), int(c.cells_without_a_synapse)]);
  return table(["cells of the compiled larva", "patches", "of them without a synapse in the data"], rows);
}
function gainTable(scan) {
  return table(["fraction of the selected gain", "gain", "startle: MC peak", "release after the tap", "eyespot light: left band", "right band"],
    scan.rows.map((r) => [num(r.factor, 1), num(r.gain, 4), num(r.mc_peak, 3), `${num(r.release_s, 1)} s`, num(r.band_left, 4), num(r.band_right, 4)]));
}
function nullsLine(receipt, label) {
  const tally = (prefix) => Object.entries(receipt.wirings).filter(([k]) => k.startsWith(prefix)).map(([, w]) => w.passed).join(", ");
  const m = receipt.wirings.measured;
  return `${label}: measured wiring ${m.passed} of ${m.counted} counted rows at gain ${num(m.selected_gain, 4)}; degree-only rewires ${tally("permuted")}; strength-matched rewires ${tally("matched")}.`;
}
function fish1Tables(frag, probe) {
  const parts = [];
  if (frag) {
    const s = frag.sample, c = frag.cached;
    parts.push(table(["Fish1, materialization 720", "synapses", "sender has a cell body", "receiver has a cell body", "both have one", "cell-to-cell connections"], [
      [`random sample of the synapse table`, int(s.synapses), pct(s.pre_with_soma), pct(s.post_with_soma), pct(s.both_with_soma, 2), int(s.soma_to_soma_connections)],
      [`every synapse onto ${int(c.post_roots)} cells with a cell body (${c.batches} cached batches)`, int(c.synapses), pct(c.pre_with_soma), pct(c.post_with_soma, 0), pct(c.both_with_soma), int(c.soma_to_soma_connections)],
    ]));
    parts.push(el("p", { class: "note" }, `${int(frag.somas)} segments carry a cell body in the somas table (data/fish1_fragmentation.json, ${frag.date}).`));
  }
  if (probe) {
    parts.push(table(["proofread segments", "value"], [
      ["segments with at least one proofreading edit", int(probe.edited_segments)],
      ["of them with a cell body", int(probe.edited_with_soma)],
      [`inputs per cell, median of ${probe.sample} sampled`, num(probe.inputs_per_cell_median, 1)],
      ["outputs per cell, median", num(probe.outputs_per_cell_median, 1)],
      ["share of a cell's inputs that come from a proofread cell", pct(probe.inputs_from_proofread)],
      ["share that come from any cell with a cell body", pct(probe.inputs_from_soma_cells)],
      ["share of a cell's outputs that land on a proofread cell", pct(probe.outputs_onto_proofread)],
      ["share that land on any cell with a cell body", pct(probe.outputs_onto_soma_cells)],
    ]));
    parts.push(el("p", { class: "note" }, "data/fish1_probe.json, the compiler's receipts/fish1_proofread_probe.json."));
  }
  return parts;
}

try {
  const [census, scan, larva, fish, frag, probe] = await Promise.all([
    fetchJSON("./data/larva_census.json"), fetchJSON("./data/larva_gain_scan.json"), fetchJSON("./data/receipt_platynereis.json"), fetchJSON("./data/receipt_oculomotor.json"),
    fetchJSON("./data/fish1_fragmentation.json").catch(() => null), fetchJSON("./data/fish1_probe.json").catch(() => null)]);
  const sections = $("sections");
  for (const s of DISCLAIMERS.sections) {
    sections.appendChild(el("h3", { id: s.id }, s.title));
    paragraphs(sections, s.paragraphs);
    if (s.id === "larva") {
      sections.appendChild(censusTable(census));
      sections.appendChild(el("p", { class: "note" }, `${int(census.connections)} connections carrying ${int(census.synapses)} synapses, every sender excitatory (${int(census.signs["1"] || 0)} of ${int(census.connections)} connections at +1). Critical gain of the unit ${num(census.critical_gain, 4)}; selected gain ${num(census.selected_gain, 4)} is ${num(census.selected_over_critical, 3)} of it, the page's gain ${num(census.gain, 4)} is ${num(census.gain_over_critical, 3)} of it (data/larva_census.json).`));
      sections.appendChild(gainTable(scan));
      sections.appendChild(el("p", { class: "note" }, `${scan.what}; release is ${scan.release} (data/larva_gain_scan.json).`));
      sections.appendChild(el("p", { class: "note" }, nullsLine(larva, "Facts (data/receipt_platynereis.json)")));
    }
    if (s.id === "fish") sections.appendChild(el("p", { class: "note" }, nullsLine(fish, "Facts (data/receipt_oculomotor.json)")));
    if (s.id === "wholefish") for (const part of fish1Tables(frag, probe)) sections.appendChild(part);
  }
  $("receipts-title").textContent = DISCLAIMERS.receipts.title;
  $("receipts").replaceChildren(...DISCLAIMERS.receipts.items.map(([href, text]) => el("a", { href }, text)));
  shell.card([`<b>Sources.</b> Verasztó et al. 2025, eLife 13:RP97964; Vishwanathan et al. 2024, Nature Neuroscience 27:2340; Petkova et al. 2025, bioRxiv 10.1101/2025.06.10.658982; the compiler at github.com/muellerberndt/cadence-connectome-compiler with its receipts; Cadence at github.com/muellerberndt/cadence.`]);
} catch (e) {
  app.errors.push(String(e.message || e));
  shell.status(`could not load the receipts: ${e.message || e}`);
}
app.ready = true;
