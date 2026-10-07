// A short introduction; detailed protocols and measurements live with the source.
import { mountShell, app, el, $ } from "./site.js";
import { paperCards, compilationDiagram } from "./evidence.js";
import { EXPLAIN } from "./content/explain.js";

const shell = mountShell("explain", { status: "measured wiring · local activity · learned connections" });
$("page-title").textContent = EXPLAIN.title;
$("intro").textContent = EXPLAIN.intro;
$("intro").after(paperCards(), compilationDiagram());
for (const section of EXPLAIN.sections) {
  $("sections").appendChild(el("h3", { id: section.id }, section.title));
  for (const text of section.paragraphs) $("sections").appendChild(el("p", {}, text));
}
$("appendix-title").textContent = EXPLAIN.appendix.title;
$("appendix").replaceChildren(...EXPLAIN.appendix.items.map(([href, text]) => el("a", { href: `./${href}` }, text)));
shell.card(["Measured anatomy supplies the connections. Cadence runs the declared cell model and adjusts connection strengths during lessons. See the preprints above for the mathematical framework."]);
app.ready = true;
