// Shared page copy. Detailed test records remain in the repository.
export const TITLE = "From connectome to Cadence";
export const SUBTITLE = "measured wiring, running patches, connections that learn";

export const APPENDIX = [
  { id: "copy", nav: "1. Copy", title: "Start with measured wiring",
    paragraphs: [
      "This reconstruction contains 2,884 neurons from one side of a larval zebrafish hindbrain. Its connection partners and synapse counts were measured in tissue.",
      "Click a neuron to see its connections. The compiler keeps that graph: one patch per cell, one relation per recorded connection.",
    ] },
  { id: "paste", nav: "2. Paste", title: "Give the wiring activity",
    paragraphs: [
      "Declared signs, gains and neuron responses turn the anatomical graph into a rate patch net. Each patch reads its neighbors and adjusts its potential toward their input.",
      "Try the gain slider. A weak circuit lets a pulse fade; stronger recurrence can retain activity or drive it too high. This page keeps weights fixed. The fish page lets them learn.",
    ] },
  { id: "why", nav: "3. Why", title: "Compare spikes and rates",
    paragraphs: [
      "The same anatomical graph runs in two models: spiking neurons on the left and rate patches on the right. Drive the circuit and compare their activity patterns.",
      "The models use different response laws and time scales. Similar patterns are useful evidence for a rate abstraction, not proof that the models behave identically.",
    ],
    advantages: {
      title: "What the rate model makes visible",
      items: [
        "One activity value per cell, so the whole circuit can be inspected.",
        "Recurrent activity that continues after a brief input ends.",
        "Connection strengths that can change through practice on the fish page.",
      ],
      kept: "Individual spike timing is left out. The how-it-works page explains the mathematical connection.",
      costNote: "Timings depend on the model, activity and time step; they are not a universal speed comparison.",
    } },
  { id: "match", nav: "4. Match", title: "Which circuit properties survive?",
    paragraphs: [
      "Compare the recorded circuit checks for measured wiring and shuffled connections. Each wiring uses the same gain-selection procedure.",
      "These checks concern selected circuit properties. They do not establish a complete reconstruction of the animal's behavior.",
    ] },
  { id: "fish", nav: "the fish", title: "The fish: teach its gaze",
    paragraphs: [
      "The fish carries two copies of a measured half-brainstem. Its connections can learn the gaze response; a fixed pilot supplies swimming, hunting and escape.",
      "Practice hold your gaze, then let it return, then hold again on the same brain. Each practice ends with a response test. Pausing learning keeps what was learned; reset restores the starting connections.",
    ] },
  { id: "limits", nav: "6. Limits", title: "The model choices",
    paragraphs: [
      "The data supplies connection partners and contact counts. Signs, gains, neuron responses, timing and the link to the body are declared.",
      "The fish's teacher reads internal circuit activity. It does not see camera pixels. The larva's compiled connections stay fixed.",
    ] },
];

const fishEntry = APPENDIX.find((p) => p.id === "fish");
export const PAGES = [
  { id: "index", nav: "the larva", title: "The larva: a whole-body connectome", paragraphs: [] },
  { id: "fish", nav: "the fish", title: fishEntry.title, paragraphs: fishEntry.paragraphs },
  { id: "explain", nav: "how it works", title: "From wiring to a learning circuit", paragraphs: [] },
  { id: "disclaimers", nav: "model choices", title: "What is measured, what is modeled", paragraphs: [] },
];
