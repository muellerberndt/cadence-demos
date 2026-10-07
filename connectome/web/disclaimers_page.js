import { mountShell, app, el, $ } from "./site.js";
import { DISCLAIMERS } from "./content/disclaimers.js";

const shell = mountShell("disclaimers", { status: "measured anatomy · declared model · learned gaze" });
$("page-title").textContent = DISCLAIMERS.title;
$("intro").textContent = DISCLAIMERS.intro;
for (const section of DISCLAIMERS.sections) {
  $("sections").appendChild(el("h3", { id: section.id }, section.title));
  for (const text of section.paragraphs) $("sections").appendChild(el("p", {}, text));
}
$("receipts-title").textContent = DISCLAIMERS.receipts.title;
$("receipts").replaceChildren(...DISCLAIMERS.receipts.items.map(([href, text]) => el("a", { href }, text)));
shell.card(["Anatomy: Vishwanathan et al. 2024, Nature Neuroscience 27:2443–2454; Verasztó et al. 2025, eLife 13:RP97964. The running dynamics and lesson targets are model choices."]);
app.ready = true;
