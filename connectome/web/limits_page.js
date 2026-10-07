// Page 6: the paragraphs, a table of counts from the browser payload, and the digests of the
// receipt and the payload.
import { mountShell, app, el, $, renderParagraphs, int, num, fetchJSON, describePayload, sourcesList, BRAIN_URL, RECEIPT_URL, CLASS_NAMES } from "./site.js";
import { decodeArray } from "./brain.js";

const shell = mountShell("limits", { status: "loading the payload and the receipt" });
$("page-title").textContent = shell.page.title;
renderParagraphs($("prose"), shell.page);

const [brain, receipt] = await Promise.all([fetchJSON(BRAIN_URL), fetchJSON(RECEIPT_URL)]);
const sign = decodeArray(brain.arrays.sign, brain.arrays.sign_dtype === "int8" ? Int8Array : Float64Array);
const count = decodeArray(brain.arrays.count, Uint16Array);
let inhibitoryClasses = 0, inhibitorySynapses = 0;
for (let e = 0; e < sign.length; e++) if (sign[e] < 0) { inhibitoryClasses++; inhibitorySynapses += count[e]; }
const kinds = {};
for (const k of brain.kind || []) kinds[k] = (kinds[k] || 0) + 1;
const attenuated = brain.arrays.log_gain ? Array.from(decodeArray(brain.arrays.log_gain, Float64Array)).filter((g) => g !== 0).length : 0;
const m = brain.model || {};

const row = (label, value, cls = "num") => el("tr", {}, el("td", {}, label), el("td", { class: cls }, value));
$("counts").querySelector("tbody").replaceChildren(
  row("neurons", int(brain.n)),
  ...Object.keys(CLASS_NAMES).filter((k) => kinds[k]).map((k) => row(`    ${CLASS_NAMES[k]} (${k})`, int(kinds[k]))),
  row("synapse classes (sender to receiver pairs)", int(brain.edges)),
  row("synapses", int(brain.synapses)),
  row("inhibitory synapse classes", `${int(inhibitoryClasses)} (${int(inhibitorySynapses)} synapses)`),
  row("senders attenuated (axial, exp of minus the attenuation)", `${int(attenuated)} at exp(${-brain.axial_attenuation}) = ${num(Math.exp(-brain.axial_attenuation))}`),
  row("gain", num(brain.gain, 6)),
  row("unit: slope, threshold", `${num(m.slope)}, ${num(m.threshold)}`),
  row("step dt, stimulus amplitude", `${num(m.dt)}, ${num(m.stimulus_amplitude)}`),
  row("library", `Cadence ${brain.library?.version ?? ""}`),
  row("scope of the payload", String(brain.scope)));

const c = receipt.custody || {}, t = receipt.tables || {};
const drow = (label, value) => el("tr", {}, el("td", {}, label), el("td", { class: "digest" }, value));
$("digests").querySelector("tbody").replaceChildren(
  drow("protocol", receipt.protocol_digest),
  drow(`connectome, scope ${receipt.scope}`, receipt.connectome_digest),
  drow(`tables, scope ${receipt.scope} (${int(t.neurons)} neurons, ${int(t.connections)} connections)`, t.digest),
  drow(`tables, scope ${brain.scope} (the payload)`, brain.tables_digest),
  drow(`connectome, scope ${brain.scope} (the payload)`, brain.connectome_digest),
  ...Object.entries(c.files || {}).map(([file, sha]) => drow(`${file} (sha256)`, sha)),
  drow("Zfish_recon commit", c["Zfish_recon.commit"]),
  drow("Connectome-Model commit", c["Connectome-Model.commit"]),
  drow("skeletons in custody", int(c.skeletons)),
  drow("compiler package", receipt.package));

shell.status(`${int(brain.n)} neurons · ${int(brain.edges)} synapse classes · ${int(brain.synapses)} synapses · ${int(inhibitoryClasses)} inhibitory classes · protocol ${String(receipt.protocol_digest).slice(0, 12)}`);
shell.card([...describePayload(brain), sourcesList()]);
app.ready = true;
Object.assign(app, { brain: { n: brain.n, edges: brain.edges, synapses: brain.synapses, inhibitoryClasses, inhibitorySynapses, attenuated } });
