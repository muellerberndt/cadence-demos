// The explanation page: prose from content/explain.js, numbers from the receipts in data/.
import { mountShell, app, el, $, fetchJSON } from "./site.js";
const num = (x, d = 3) => Number(x).toFixed(d);  // fixed decimals, the receipts' own precision
import { paperCards, compilationDiagram, rateEquations, chargeBalance, spikingEvidence } from "./evidence.js";
import { EXPLAIN } from "./content/explain.js";

const shell = mountShell("explain", { status: "measured anatomy → declared dynamics → local agreement → circuit tests" });
$("page-title").textContent = EXPLAIN.title;
$("intro").textContent = EXPLAIN.intro;
$("intro").after(paperCards(), compilationDiagram());

function paragraphs(container, texts) { for (const t of texts) container.appendChild(el("p", {}, t)); }

function costTable(cost) {
  const rows = [];
  for (const [name, r] of Object.entries(cost.payloads)) {
    const label = name.includes("larva") ? `Platynereis, ${r.neurons} cells` : name.includes("oculomotor") ? `oculomotor circuit, ${r.neurons} neurons` : `whole hindbrain reconstruction, ${r.neurons} neurons`;
    rows.push(el("tr", {}, el("td", {}, label), el("td", {}, num(r.settling.ms_per_step, 3)), el("td", {}, num(r.settling.ms_per_fish_second_declared, 1)),
      el("td", {}, num(r.spiking["w_0.35_mV"].ms_per_fish_second, 1)), el("td", {}, num(r.spiking["w_2.7_mV"].ms_per_fish_second, 1)), el("td", {}, `${num(r.ratio_declared, r.ratio_declared < 1 ? 3 : 1)}×`), el("td", {}, `${num(r.ratio_tau20ms, r.ratio_tau20ms < 1 ? 3 : 1)}×`)));
  }
  return el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "payload"), el("th", {}, "settling ms per step"), el("th", {}, "settling ms per simulated second"), el("th", {}, "spiking ms per simulated second, 0.35 mV"), el("th", {}, "spiking at 2.7 mV"), el("th", {}, "spiking / settling, 200 ms"), el("th", {}, "spiking / settling, 20 ms"))), el("tbody", {}, ...rows));
}

function feedForwardTable(ff) {
  const rows = [el("tr", {}, el("td", {}, "settling net (recurrent, keeps its state)"), el("td", {}, num(ff.settling.burst_end, 3)), el("td", {}, num(ff.settling.one_step_after, 3)), el("td", {}, num(ff.settling.steps_300_after, 3)))];
  for (const [k, v] of Object.entries(ff.feed_forward)) rows.push(el("tr", {}, el("td", {}, `feed-forward reading, ${k.replace("depth_", "")} layers deep`), el("td", {}, num(v.burst_on, 3)), el("td", {}, num(v.burst_off, 3)), el("td", {}, num(v.burst_off, 3))));
  return el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "the same wiring read as"), el("th", {}, "abducens while the burst is on"), el("th", {}, "the moment it ends"), el("th", {}, "300 steps later"))), el("tbody", {}, ...rows));
}

try {
  const [cost, ff, receipt] = await Promise.all([fetchJSON("./data/cost.json"), fetchJSON("./data/feedforward.json"), fetchJSON("./data/receipt_oculomotor.json")]);
  const sections = $("sections");
  for (const s of EXPLAIN.sections) {
    sections.appendChild(el("h3", { id: s.id }, s.title));
    paragraphs(sections, s.paragraphs);
    if (s.id === "feedforward") { sections.appendChild(el("div", { class: "table-scroll" }, feedForwardTable(ff))); sections.appendChild(el("p", { class: "note" }, `Burst to the ${ff.burst.population} population at level ${ff.burst.level} for ${ff.burst.steps} steps, readout the mean over the abducens cells, gain ${num(ff.gain, 4)} (data/feedforward.json).`)); }
    if (s.id === "paste") sections.appendChild(rateEquations());
    if (s.id === "spiking") sections.append(chargeBalance(), spikingEvidence(receipt));
    if (s.id === "cost") {
      sections.appendChild(el("div", { class: "table-scroll" }, costTable(cost)));
      sections.appendChild(el("p", { class: "note" }, s.costNote));
      sections.appendChild(el("p", { class: "evidence-links" }, el("a", { href: "./data/cost.json" }, "Download timing receipt (JSON)")));
    }
    if (s.id === "match") {
      const m = receipt.wirings.measured, counted = m.counted || 5;
      const tally = (prefix) => { const vals = []; for (const [k, w] of Object.entries(receipt.wirings)) if (k.startsWith(prefix)) vals.push(w.passed); return vals; };
      sections.appendChild(el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "wiring"), el("th", {}, "selected gain"), el("th", {}, `counted rows passed of ${counted}`))), el("tbody", {},
        el("tr", {}, el("td", {}, "measured"), el("td", {}, num(m.selected_gain, 4)), el("td", {}, String(m.passed))),
        el("tr", {}, el("td", {}, "approximately strength-matched shuffles, six seeds"), el("td", {}, "own"), el("td", {}, tally("matched").join(", "))),
        el("tr", {}, el("td", {}, "degree-only shuffles, six seeds"), el("td", {}, "own"), el("td", {}, tally("permuted").join(", "))))));
      sections.appendChild(el("p", { class: "evidence-links" }, el("a", { href: "./match.html" }, "Inspect every predicate, result and exploratory disclosure")));
    }
  }
  $("appendix-title").textContent = EXPLAIN.appendix.title;
  $("appendix").replaceChildren(...EXPLAIN.appendix.items.map(([href, text]) => el("a", { href: `./${href}` }, text)));
  shell.card([`<b>Sources.</b> <a href="https://doi.org/10.1038/s41593-024-01784-3">Vishwanathan et al. 2024</a>; the <a href="https://github.com/muellerberndt/cadence-connectome-compiler">connectome compiler</a>; <a href="https://github.com/muellerberndt/cadence">Cadence</a>.`]);
} catch (e) {
  app.errors.push(String(e.message || e));
  shell.status(`could not load the receipts: ${e.message || e}`);
}
app.ready = true;
