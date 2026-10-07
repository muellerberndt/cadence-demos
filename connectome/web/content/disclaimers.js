// A concise boundary between the anatomical data and the running model.
export const DISCLAIMERS = {
  title: "What is measured, what is modeled",
  intro: "The wiring comes from animal tissue. The running circuit adds explicit model choices.",
  sections: [
    { id: "measured", title: "Measured anatomy", paragraphs: [
      "Cell identities, connection partners and synapse counts come from published reconstructions: the zebrafish hindbrain of Vishwanathan et al. (2024) and the Platynereis larva of Verasztó et al. (2025). The fish reconstruction covers one side; the display uses a copy for the other side. The larva includes non-neural cells as well as neurons.",
    ] },
    { id: "declared", title: "Declared dynamics and lessons", paragraphs: [
      "A synapse count is not a measured physiological weight. Signs, gains, neuron responses, timing, senses and body mechanics are declared. The fish's lessons compare internal circuit activity with a chosen target; they do not read camera pixels or retinal slip.",
    ] },
    { id: "behavior", title: "What learns", paragraphs: [
      "The fish's connections learn its gaze response. A fixed pilot supplies swimming, hunting and escape. The larva's connections stay fixed. These are working circuit models, not complete reconstructions of the animals' brains or behavior.",
    ] },
  ],
  receipts: { title: "Explore", items: [["./fish.html", "teach the fish"], ["./explain.html", "how it works"]] },
};
