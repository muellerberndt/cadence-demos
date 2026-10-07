// The short path from measured anatomy to a learned circuit response.
export const EXPLAIN = {
  title: "From wiring to a learning circuit",
  intro: "A connectome tells us which cells connect. Cadence turns that graph into interacting patches, then lets their connections change through practice.",
  sections: [
    { id: "compile", title: "1. Keep the wiring", paragraphs: [
      "Each represented cell becomes a patch. Each recorded connection stays connected to the same cells and carries its measured synapse count. Declared signs, gains and a neuron response turn those counts into a running model.",
    ] },
    { id: "activity", title: "2. Let activity flow", paragraphs: [
      "A patch reads its neighbors and adjusts its activity toward their combined input. Recurrent connections let a brief eye-movement signal leave activity behind after the signal ends. The fish reads that activity as a gaze response.",
      "For this rate model, fixed points satisfy u = Wφ(u) + d exactly. A spiking model shares those stationary rate solutions only when a justified rate reduction gives the same equation. This does not establish identical spike timing or animal behavior. The two preprints above develop the mathematical background.",
    ] },
    { id: "learning", title: "3. Change connections through practice", paragraphs: [
      "The lesson saves activity after an eye movement. Hold your gaze asks the circuit to retain most of it; let it return asks for less. A nudged phase is compared with a free phase of the same duration, and each connection changes using the activity of its two cells. The graph stays; its connection strengths learn.",
      "These lessons use a declared activity-based teacher, not camera pixels. The practice phases are finite; the learning rule and its bounds are model choices.",
    ] },
    { id: "response", title: "4. Try a different response", paragraphs: [
      "Teach hold your gaze, then let it return, then hold again on the same brain. Practice ends with a response test using copies of the learned and starting weights, so testing leaves the fish untouched. Pausing learning keeps what was learned; reset starts the connections over.",
      "The fish learns its gaze response. Swimming, hunting and escape come from a fixed pilot. The larva page shows a compiled circuit with fixed weights.",
    ] },
  ],
  appendix: { title: "Try it", items: [["fish.html", "teach the fish"], ["index.html", "explore the larva"], ["disclaimers.html", "what is modeled"]] },
};
