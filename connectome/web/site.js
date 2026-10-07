// The shared shell of the explainer pages: the masthead with the title, the nav with the current
// page marked, the status strip with the credit, the collapsed info card, and the helpers every
// page uses. The words come from content/copy.js and are rendered verbatim.
import { TITLE, SUBTITLE, PAGES, APPENDIX } from "./content/copy.js";

export { TITLE, SUBTITLE, PAGES, APPENDIX };
export const $ = (id) => document.getElementById(id);
export const SKELETONS_URL = typeof DecompressionStream === "undefined" ? "./data/skeletons.json" : "./data/skeletons.json.gz";
export const SKELETONS_FALLBACK = "./data/skeletons.json";
export const BRAIN_URL = "./data/brain.json";
export const RECEIPT_URL = "./data/receipt_oculomotor.json";
export const PAPER_URL = "https://doi.org/10.1038/s41593-024-01784-3";
export const SOURCES = { Zfish_recon: "https://github.com/ashwinvish/Zfish_recon", "Connectome-Model": "https://github.com/goldman-lab/Connectome-Model" };
export const PAPERS = [
  { title: "Agreement and Surprise: Global Equilibrium from Local Repair", short: "Agreement and Surprise", url: "https://philpapers.org/rec/MUEAAS-2" },
  { title: "Cadence: Learning Through Local Patch Settlement", short: "Cadence", url: "https://philpapers.org/rec/MUECAP-2" },
];
export const CLASS_NAMES = { _Int_: "integrator", _Axl_: "axial", _DOs_: "DO", ABD_m: "abducens motor", ABD_i: "abducens internuclear", vSPNs: "vSPN", periphery: "periphery" };

// A link to another site opens in a new tab (inside an embedding frame the demo stays put); the demo's own pages open in place.
addEventListener("click", (e) => { const a = e.target.closest && e.target.closest("a[href]"); if (a && /^https?:/.test(a.href) && new URL(a.href).origin !== location.origin) { a.target = "_blank"; a.rel = "noopener"; } });

/** What the headless check reads: ready once the page has drawn, and every uncaught error. */
export const app = { ready: false, errors: [] };
window.__app = app;
addEventListener("error", (e) => app.errors.push(String(e.message || e)));
addEventListener("unhandledrejection", (e) => app.errors.push(String((e.reason && e.reason.message) || e.reason)));

/** An element with attributes and children; strings become text nodes, "html" sets innerHTML. */
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) if (c != null) node.append(c);
  return node;
}

export const pageById = (id) => PAGES.find((p) => p.id === id) || APPENDIX.find((p) => p.id === id) || null;
export const int = (n) => Number(n).toLocaleString("en-US");
/** A number for a table: integers with separators, large values to one decimal, the rest to `digits` significant figures. */
export function num(x, digits = 3) {
  if (x == null || Number.isNaN(Number(x))) return "n/a";
  x = Number(x);
  if (Number.isInteger(x)) return int(x);
  if (Math.abs(x) >= 100) return x.toLocaleString("en-US", { maximumFractionDigits: 1 });
  return String(Number(x.toPrecision(digits)));
}
export async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw Error(`${url}: ${r.status}`);
  return r.json();
}

/** The page's paragraphs, one <p> each, verbatim. */
export function renderParagraphs(container, page) {
  for (const text of page.paragraphs) container.append(el("p", {}, text));
  return container;
}

const credit = (options = {}) => `powered by <a href="https://github.com/muellerberndt/cadence"><b>Cadence</b></a> · <a href="https://github.com/muellerberndt/cadence-demos/tree/main/connectome">source</a> · preprints: <a href="${PAPERS[0].url}">${PAPERS[0].short}</a>, <a href="${PAPERS[1].url}">${PAPERS[1].short}</a> · made with <span style="color:#ff7850">♥</span> by <a href="https://floatingpragma.io">Pragma Research</a> · connectome: <a href="${options.connectomeUrl || PAPER_URL}">${options.connectome || "Vishwanathan et al. 2024"}</a>`;

/** Fill the masthead and the nav of the page `pageId`, append the status strip and the info card.
 *  Returns {page, status(text), card(content), open(flag)}; `card` takes html strings (one <p>
 *  each) or nodes. */
export function mountShell(pageId, options = {}) {
  const page = pageById(pageId);
  document.title = page ? `${page.nav.replace(/^\d+\.\s*/, "")} · ${TITLE}` : TITLE;
  $("mast").replaceChildren(el("h1", {}, el("a", { href: "./index.html" }, TITLE)), el("p", { class: "sub" }, SUBTITLE),
    el("p", { class: "papers" }, "the preprints: ", el("a", { href: PAPERS[0].url }, PAPERS[0].title), " · ", el("a", { href: PAPERS[1].url }, PAPERS[1].title)));
  $("nav").replaceChildren(...PAGES.map((p) => el("a", { href: `./${p.id}.html`, "aria-current": p.id === pageId ? "page" : null }, p.nav)));
  const statusText = el("span", { id: "status-text" }, options.status || "");
  const toggle = el("button", { id: "card-toggle", type: "button", "aria-expanded": "false", "aria-controls": "card", title: "what is running here" }, "about");
  document.body.append(el("footer", { id: "status" }, statusText, toggle, el("p", { id: "credit", html: credit(options) })));
  const close = el("button", { class: "close", type: "button", "aria-label": "Close" }, "×");
  const body = el("div", { id: "card-body" });
  document.body.append(el("aside", { id: "card", class: "glass", role: "dialog", "aria-label": "What is running here" }, el("h3", {}, close, "What is running here"), body));
  const open = (flag) => { document.body.classList.toggle("card-open", flag); toggle.setAttribute("aria-expanded", String(flag)); toggle.classList.toggle("on", flag); };
  toggle.onclick = () => open(!document.body.classList.contains("card-open"));
  close.onclick = () => open(false);
  const card = (content) => body.replaceChildren(...[content].flat().map((c) => (typeof c === "string" ? el("p", { html: c }) : c)));
  if (options.card) card(options.card);
  return { page, status: (text) => { statusText.textContent = text; }, card, open };
}

/** Hover explanations: every element with a data-tip inside `root` shows it in one shared box above
 *  itself (below, with data-tip-side="below"), kept inside root's box so nothing clips at an edge. */
export function tooltips(root) {
  const box = el("div", { class: "tip", role: "tooltip" });
  root.append(box);
  const show = (e) => {
    const t = e.currentTarget;
    box.textContent = t.dataset.tip; box.style.visibility = "hidden"; box.classList.add("show");
    const r = root.getBoundingClientRect(), b = t.getBoundingClientRect(), w = box.offsetWidth, h = box.offsetHeight;
    const x = Math.max(8, Math.min(r.width - w - 8, b.left - r.left + b.width / 2 - w / 2));
    const y = t.dataset.tipSide === "below" ? b.bottom - r.top + 8 : b.top - r.top - h - 8;
    box.style.left = `${x}px`; box.style.top = `${Math.max(4, y)}px`; box.style.visibility = "";
  };
  const hide = () => box.classList.remove("show");
  for (const t of root.querySelectorAll("[data-tip]")) { t.addEventListener("pointerenter", show); t.addEventListener("focus", show); t.addEventListener("pointerleave", hide); t.addEventListener("blur", hide); t.addEventListener("click", hide); }
  return box;
}

/** The card's standard lines from a brain payload (web/data/brain.json). */
export function describePayload(p) {
  const kinds = {};
  for (const k of p.kind || []) kinds[k] = (kinds[k] || 0) + 1;
  const classes = Object.keys(CLASS_NAMES).filter((k) => kinds[k]).map((k) => `${CLASS_NAMES[k]} ${int(kinds[k])}`).join(", ");
  const m = p.model || {};
  return [
    `<b>The data.</b> ${p.source}: one side of the hindbrain, ${int(p.n)} neurons and ${int(p.edges)} synapse classes carrying ${int(p.synapses)} synapses. Classes: ${classes}.`,
    `<b>The brain.</b> The Cadence ${p.library?.version ?? ""} rate model in the browser engine (brain.js): every neuron holds one activity in [0, 1]; a step moves its potential by dt ${m.dt} toward its synaptic input, and a rectified sigmoid of slope ${m.slope} at threshold ${m.threshold} reads the activity. A synapse class weighs gain ${num(p.gain, 6)} times its synapse count, negative from an inhibitory sender; the axial senders are attenuated by exp(${-p.axial_attenuation}). One step is dt ${m.dt} of the unit's time constant; the pages count steps.`,
  ];
}

/** The sources, for the card. */
export function sourcesList() {
  return el("ul", {},
    el("li", { html: `<a href="${PAPER_URL}">Vishwanathan et al. 2024, Nat Neurosci 27:2340</a>: the reconstruction, the classes, the imaging.` }),
    el("li", { html: `<a href="${SOURCES.Zfish_recon}">Zfish_recon</a> (skeletons and classes) and <a href="${SOURCES["Connectome-Model"]}">Connectome-Model</a> (the matrix and the imaged sensitivities).` }),
    el("li", { html: `<a href="https://github.com/muellerberndt/cadence">Cadence</a>: the library whose rate model the browser engine reproduces.` }));
}
