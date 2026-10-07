// Shared, receipt-backed evidence for the explanation and the live comparison.
import { el, num, int, PAPERS, RECEIPT_URL } from "./site.js";

export const PROTOCOL_URL = "https://github.com/muellerberndt/cadence-connectome-compiler/blob/67cf9b81ad88e1f454eae3c27e5dcfa1ef2d7a4b/src/connectome_compiler/verify/brainstem.py";
const COMPILER = "https://github.com/muellerberndt/cadence-connectome-compiler";

export function paperCards() {
  const descriptions = [
    "The mathematical framework: fixed points, conditions for reaching them, and charge balance for spiking neurons. Rate closure is a separate assumption.",
    "Cadence's local settlement and learning framework. Each implementation must satisfy the assumptions of the theorem it invokes.",
  ];
  return el("section", { class: "paper-cards", "aria-label": "The two mathematical preprints" },
    ...PAPERS.map((p, i) => el("article", { class: "panel" }, el("p", { class: "h" }, `Preprint ${i + 1}`),
      el("a", { href: p.url }, p.title), el("p", {}, descriptions[i]))));
}

export function compilationDiagram() {
  return el("ol", { class: "compile-flow", "aria-label": "Compilation steps" },
    ...[
      ["Measured anatomy", "Cell identities, directed contacts and synapse counts"],
      ["Declared model", "Signs, gain, response law and sensory / motor interfaces"],
      ["Local repair", "One potential per patch; recurrent inputs determine each repair"],
      ["Test the function", "Model agreement, circuit checks and behavior are separate tests"],
    ].map(([title, body]) => el("li", {}, el("b", {}, title), el("span", {}, body))));
}

export function rateEquations() {
  return el("div", { class: "evidence-box" },
    el("p", { class: "h" }, "Exact identity for the implemented rate model"),
    el("pre", { class: "equation" }, "rᵢ = φ(uᵢ)\nRᵢ(u) = Σⱼ Wᵢⱼ φ(uⱼ) + dᵢ\nuᵢ ← uᵢ + η [Rᵢ(u) − uᵢ]\n\nAt a fixed point (η > 0):\nu* = W φ(u*) + d     and     r* = φ(W r* + d)"),
    el("p", {}, "Here d is fixed sensory drive plus bias; η = 0.2 in the exported payloads. The chosen φ is a rectified sigmoid with slope 0.25 and threshold 0. A fixed point leaves every update unchanged, so its local disagreement is zero. Conversely, zero disagreement leaves the state unchanged. The two equations therefore have corresponding solutions; this algebra alone says nothing about whether a run reaches one."),
    el("p", {}, "A sufficient condition is Lφ ‖W‖∞ < 1, with 0 < η ≤ 1. The current payloads do not satisfy that sufficient bound. Their measured persistence and settlement must be assessed directly."),
    el("p", { class: "evidence-links" }, el("a", { href: "./brain.js" }, "Browser update law"), " · ", el("a", { href: PAPERS[0].url }, "Existence and contraction assumptions")));
}

export function spikingEvidence(receipt) {
  const sp = receipt.spiking, se = sp.static_equivalence;
  const rows = [
    ["Sustained-drive spatial pattern", `cosine ${num(se.cosine, 4)} · Spearman ${num(se.spearman, 4)}`, `${int(se.neurons_compared)} undriven neurons, including silent cells; the 255 driven integrator cells are excluded.`],
    ["Post-burst spatial pattern", `cosine ${num(sp.ignited.cos_rate_held, 4)}`, `At ${num(sp.critical_weight_mv)} mV per synapse, a sustained LIF pattern resembles the rate model's held pattern. This does not establish matched graded retention.`],
    ["Circuit checks", `${receipt.wirings.measured.passed} / ${receipt.wirings.measured.counted} scored checks`, "Checks not used to select gain; exploratory runs preceded protocol design. Shuffled controls score lower."],
  ];
  return el("section", { class: "evidence-box", "aria-label": "Evidence and its scope" },
    el("p", { class: "h" }, "What the stored comparison actually measures"),
    el("div", { class: "table-scroll" }, el("table", {},
      el("thead", {}, el("tr", {}, ...["comparison", "stored result", "scope"].map(t => el("th", {}, t)))),
      el("tbody", {}, ...rows.map(row => el("tr", {}, ...row.map(t => el("td", {}, t))))))),
    el("p", {}, `Recipe: the 343-neuron oculomotor circuit; integrator drive; six 1-second LIF trials at ${sp.static_weight_mv} mV per synapse, averaging rates over the final 500 ms. Compare with 3,000 rate-model steps at drive level 0.3 and gain ${receipt.wirings.measured.selected_gain}. Cosine measures vector direction and Spearman measures rank; neither measures equality of rates in physical units.`),
    el("p", {}, "The live page uses one evolving trial and a 500 ms rolling window, with independently adjustable parameters. It is an illustration, not a replay of the stored experiment. Its rate payload rounds the gain to 0.3224; releasing a live burst also restores ordinary refractory behavior in previously driven cells."),
    el("p", { class: "evidence-links" }, el("a", { href: RECEIPT_URL }, "Download comparison receipt (JSON)"), " · ",
      el("a", { href: PROTOCOL_URL }, "Inspect protocol source"), " · ",
      el("a", { href: `${COMPILER}/blob/67cf9b81ad88e1f454eae3c27e5dcfa1ef2d7a4b/src/connectome_compiler/verify_lif.py` }, "Inspect spiking reference")),
    el("details", {}, el("summary", {}, "Provenance and reproduction limits"),
      el("p", {}, "The historical receipt contains table, connectome and protocol digests. Its protocol-file digest differs from the current repository version, and the matching historical source was not located during this audit. The linked source is pinned for inspection; it is not asserted to match that historical digest. tests/evidence.mjs recomputes the stored correlations from the archived rate vector and a fresh rate-model run."),
      el("p", { class: "digest" }, `Recorded protocol SHA-256: ${receipt.protocol_digest}`)));
}

export function chargeBalance() {
  return el("div", { class: "evidence-box" },
    el("p", { class: "h" }, "What the spiking theorem supplies"),
    el("pre", { class: "equation" }, "τₘ θ νᵢ = τₛ Σⱼ wᵢⱼ νⱼ − ūᵢ + O(1/T)"),
    el("p", {}, "For the preprint's bounded integrate-and-fire system with reset to zero, ν is firing rate over a window T, ū is mean membrane potential, θ is spike threshold, and τₘ and τₛ are membrane and synaptic time constants. External spike sources are included in the sum. The finite-window term comes from the endpoint potentials and currents."),
    el("p", {}, "Mean potential remains unknown. Refractory holds and discarded current add terms; both occur in the comparison model. Closing this balance with a valid stationary response curve is the extra step needed to derive rate equivalence. The demo's sigmoid has not been proved to be that curve."),
    el("p", { class: "evidence-links" }, el("a", { href: PAPERS[0].url }, "Agreement and Surprise: “Charge balance” and “Rate law”"), " · ",
      el("a", { href: "https://github.com/muellerberndt/everything-settles/blob/main/paper/sections/theorems.tex" }, "Read the theorem source")));
}
