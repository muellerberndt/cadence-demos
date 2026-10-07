// The explainer's words, one entry per page. Plain prose; numbers come from the receipts.
export const TITLE = "From connectome to Cadence";
export const SUBTITLE = "how to compile a biological connectome into a Cadence patch net";

export const APPENDIX = [
  { id: "copy", nav: "1. Copy", title: "Copy: the wiring of a living brain, cell by cell",
    paragraphs: [
      "This is one side of the hindbrain of a larval zebrafish, five to seven days old: 2,884 neurons and 75,195 synapses, reconstructed from electron microscopy and proofread by hand (Vishwanathan et al. 2024). Every line is a real neuron. Every connection in the table behind this page was seen in the tissue.",
      "Six hundred and nine of these cells carry a name. Two hundred and fifty-five form the oculomotor integrator, the circuit that holds the eye still between saccades. Thirty-four are vestibular neurons, fifty-four drive or relay to the eye muscles, two hundred and fifty-one belong to the module that moves the body.",
      "Click a neuron. What you see on the right is the connectome's own ledger for that cell: who it listens to, who it talks to, how many synapses each connection carries. That ledger supplies the anatomy. Declared signs, gain, neuron dynamics and sensory and motor mappings turn it into a runnable model.",
    ] },
  { id: "paste", nav: "2. Paste", title: "Paste: the connectome becomes a patch net",
    paragraphs: [
      "The compiler preserves the recorded partners and synapse counts. In this rate-model demonstration, every neuron becomes a patch with a potential and an activity readout. Each connection receives a weight from its count, a declared sender sign and gain; the displayed full brainstem also attenuates the body module. Within the tested oculomotor circuit, the authors' sign rule makes the vestibular cells inhibitory. The demo does not train these weights.",
      "Each patch locally adjusts its potential toward its current synaptic input. When these coupled adjustments converge, the net reaches a state consistent with its declared dynamics. A new stimulus disturbs that state and the patches adjust again. Convergence and matching the living circuit are separate questions.",
      "With the neuron model and sign rule fixed, the protocol selects the gain, how strongly a synapse counts. Slide it. Too low and a burst to the integrator fades quickly. Near the critical value the model retains a graded level over the measured hold window. Too high and it ignites into a persistent bright state. The protocol selects a gain using one training fact on a one percent grid; the other scored checks ask what else the resulting model reproduces.",
    ] },
  { id: "why", nav: "3. Why", title: "Why an abstraction works",
    paragraphs: [
      "The rate model has an exact fixed-point identity: a settled potential equals its weighted activity inputs plus external drive. A spiking model can share this stationary-rate description when a justified input-output law and rate reduction apply. The sigmoid used here is a declared approximation, so the following experiment tests correspondence rather than exact functional equivalence.",
      "Here the same anatomical wiring runs twice, with separately declared dynamics and scales. On the left, leaky integrate-and-fire neurons driven by Poisson spikes. On the right, the rate patch net. Drive the integrator and watch the scatter. The recorded sustained-drive comparison reports cosine similarity 0.965 and rank correlation 0.97 over 88 undriven cells, including silent cells. These describe the relative activity pattern; they do not establish equal firing rates, spike times or behavior, and the live run can differ.",
      "Both tested models can ignite into persistent high activity. The recorded spiking scan reaches ignition at 2.7 millivolts per synapse, with a persistent activity pattern similar to the rate model's held pattern (cosine 0.94). That spiking scan did not reproduce the rate model's graded persistence window. This is a limitation of the tested model and parameters, not a general prohibition on small steady firing rates.",
    ],
    advantages: {
      title: "What the abstraction buys",
      items: [
        "A coarser time step in this demo. The implemented spiking port uses 10,000 steps per simulated second. The rate model uses 25 at the declared 200 ms time constant, or 250 at 20 ms. These are model and solver choices, not a bound on all spiking simulators.",
        "Predictable work per rate step. This rate engine visits every connection each step. The spiking port can skip inactive cells but delivers spikes along their outgoing connections, so its cost depends on activity. The measured winner depends on the circuit and input.",
        "A directly inspectable state. The rate model exposes one activity per cell; the spiking comparison estimates rates over windows and trials. Browser/library parity checks validate the rate implementation. They do not establish that its state is the animal's answer.",
        "A foundation for learning experiments. Cadence provides local learning machinery, but these compiled-circuit comparisons keep their weights fixed. Learning and preservation of biological function would need their own declared protocol.",
        "A graded persistence window in the tested rate model. Near critical gain, different bursts leave different held levels. Reproducing that response in a spiking model remains an additional test, not a consequence of matching an activity pattern.",
      ],
      kept: "This one-rate-per-cell abstraction drops individual spike timing and synchrony. See the explanation page for the exact rate fixed-point identity, the additional assumptions a spike-to-rate reduction needs, and what the recorded comparisons establish.",
      costNote: "The table is a recorded benchmark in one process, with both engines on each listed payload (data/cost.json). It does not measure equal biological accuracy or prove a universal speedup. One rate step is a fifth of its declared time constant: 25 steps per simulated second at 200 ms, or 250 at 20 ms.",
    } },
  { id: "match", nav: "4. Match", title: "Which circuit properties does the compiled model reproduce?",
    paragraphs: [
      "The authors imaged 648 cells of this circuit in fixating fish and measured each cell's eye-position sensitivity. From their paper and that table the protocol specifies one gain-selection check, five scored checks and one uncounted structural row, each with a predicate a program can check. Five further checks are not used for gain selection, but the protocol records exploratory measured runs and some null comparisons before its freeze.",
      "The compiled wiring is scored against two shuffled versions of itself. One keeps every neuron's number of inputs and outputs and redraws who connects to whom. The other also approximately matches each neuron's excitatory and inhibitory input strengths using strength bins. Each shuffle selects its own gain by the same rule. A difference under these controls is evidence that the connection partners contribute to the measured properties beyond those preserved statistics.",
      "The measured wiring passes every counted row. The strength-matched shuffles pass all but one: the second slow mode, the two-cycle organisation the authors found in the circuit, which the tested shuffles do not pass. The degree-only shuffles also lose the concentration of sensitivity that the imaging shows. Switch the wiring and read the rows.",
    ] },
  { id: "fish", nav: "the fish", title: "The fish, with the compiled brainstem in it",
    paragraphs: [
      "The larva in the tank has two copies of the compiled half-brainstem, one per side, since the reconstruction covers one side. A declared burst drives one side's integrator and a declared pulse produces the initial eye jump. The subsequent hold and drift use the compiled abducens activity through a declared eye model. Turning the body drives the vestibular neurons, which push the held level down and move the eyes against the turn.",
      "Everything else the fish does, the swim bouts, the hunt, the escape from a tap, is a declared pilot, labelled as such on the page. The brain on the right shows every neuron of the reconstruction as the compiled net settles.",
    ] },
  { id: "limits", nav: "6. Limits", title: "What the data does not give",
    paragraphs: [
      "Signs. The dataset names which cells are vestibular; it does not name a transmitter for the body-movement module or the 2,275 unclassified cells. Compiled as excitatory, the body module's loop is stronger than the integrator's and ignites the net at the integrator's gain. The demo lowers that module's gain by the smallest amount on a declared grid that keeps the net from igniting; the protocol runs on the oculomotor circuit alone, which is the authors' own model scope.",
      "Halves. One side of the brain was reconstructed. The other half here is a mirror copy, and the inhibition between the halves is absent from the data.",
      "What this rate model leaves out: electrical synapses, neuromodulators, individual spike timing. The imaged sensitivities are relative per cell, so only the shape of their distribution is compared, not its scale.",
      "The public compiler, source data and retained receipts make the declared circuit experiments inspectable. Receipts identify the recorded source and protocol digests; current code may differ, so a fresh reproduction must check those versions. Those experiments test selected circuit properties; they do not establish a complete reconstruction of the living animal's behavior.",
    ] },
];

// The two pages in the navigation. The fish entry's prose is shared with the index page.
const fishEntry = APPENDIX.find((p) => p.id === "fish");
export const PAGES = [
  { id: "index", nav: "the larva", title: "A whole-body connectome: the Platynereis larva", paragraphs: [] },
  { id: "fish", nav: "the fish", title: fishEntry.title, paragraphs: fishEntry.paragraphs },
  { id: "explain", nav: "how it works", title: "From measured wiring to local patch constraints", paragraphs: [] },
  { id: "disclaimers", nav: "disclaimers", title: "Disclaimers: what is measured, what is declared, what is missing", paragraphs: [] },
];
