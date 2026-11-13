// The planned parrot brain as an atlas: its regions placed as in a bird's head (x to the bird's left,
// y up, z toward the beak), each with its bird counterpart, its role, its status (in the library,
// being built, planned) and its size; and the tracts between them. The page's 3D brain view draws
// these and fills the regions the running brain has with its neurons.
export const SYS = { vision: 'Eyes and seeing', map: 'Map and memory', hearing: 'Hearing and voice', words: 'Words', motor: 'Body and movement', reward: 'Reward', mod: 'Neuromodulators' };
export const R = [
  // vision
  { id: 'retina', name: 'Retina', bird: 'the two eyes, on the sides of the head', sys: 'vision', st: 'wip', n: 1100, at: [2.7, -0.15, 1.1], r: [0.12, 0.55, 0.55], bi: true, issue: 332,
    role: 'Each eye sees 175 degrees. The two fields overlap 25 degrees in front of the beak and leave 35 degrees unseen behind. Each eye image is turned into contrast, colour and change, sharper at the eye’s axis.' },
  { id: 'tectum', name: 'Optic tectum and isthmi', bird: 'the midbrain’s map of the visual field; the isthmic nuclei pick a winner', sys: 'vision', st: 'wip', n: 1150, at: [1.35, -0.65, -0.35], r: [0.55, 0.5, 0.6], bi: true, issue: 333,
    role: 'Finds what stands out and lets one thing win: the parrot’s focus. Each eye feeds the opposite tectum. The winner turns the head and is the cue for memory and the voice.' },
  { id: 'rotundus', name: 'Rotundus to entopallium', bird: 'the tectofugal pathway: what a thing is', sys: 'vision', st: 'wip', n: 140, at: [1.15, 0.0, 0.55], r: [0.35, 0.3, 0.45], bi: true, issue: 330,
    role: 'Reads a glimpse at the winner and learns what the thing is: its form, colour and motion. Kinds are categories the brain learns.' },
  { id: 'wulst', name: 'Visual Wulst', bird: 'the thalamofugal pathway: two views of one thing', sys: 'vision', st: 'wip', n: 48, at: [0.6, 1.35, 0.95], r: [0.4, 0.18, 0.5], bi: true, issue: 332,
    role: 'Compares two views of the focused thing: the two eyes in the overlap, and one eye before and after the head moves. The distance at which the views agree is how far it is. Learned, never told.' },
  { id: 'flow', name: 'Optic-flow nuclei', bird: 'nBOR and LM: how the whole view moves', sys: 'vision', st: 'wip', n: 8, at: [0.85, -0.95, -0.15], r: [0.15, 0.12, 0.15], bi: true, issue: 332,
    role: 'The mean motion of each eye’s whole view: tells the brain its own head moved, so a thing at rest is not taken as moving.' },
  // map and memory
  { id: 'place', name: 'Gaze to place', bird: 'dorsolateral pallium, entorhinal-like', sys: 'map', st: 'wip', n: 32, at: [0.45, 1.05, -0.25], r: [0.2, 0.15, 0.2], bi: false, issue: 332,
    role: 'Turns where the eye looks and how far the thing is into a place on the table, written to the map.' },
  { id: 'map', name: 'Hippocampus: the map of things', bird: 'the hippocampal formation, the bird’s spatial memory', sys: 'map', st: 'built', n: 11264, at: [0, 1.25, -0.55], r: [0.55, 0.22, 0.55], bi: false, issue: 320,
    role: 'Holds what is where, in its own carried activity: a thing enters when seen, stays at its last known place out of view, and is asked by settling. Shipped in Cadence 0.99.0.' },
  { id: 'records', name: 'Recall memory: records', bird: 'memory of past moments', sys: 'map', st: 'built', n: 1200, at: [-0.6, 1.1, -1.0], r: [0.35, 0.25, 0.3], bi: false, issue: 310,
    role: 'Records of moments the parrot lived: what it heard (a word’s sound), what was in focus, and when. In the library since 0.95, at a million records since 0.98.' },
  { id: 'heads', name: 'Memory heads', bird: 'the readers that bring the past back', sys: 'map', st: 'wip', n: 64, at: [-0.95, 0.85, -0.85], r: [0.18, 0.15, 0.18], bi: false, issue: 325,
    role: 'Several heads each fetch a record into the active state: the focused thing fetches its word’s sound; a heard sound fetches its thing.' },
  { id: 'ncl', name: 'NCL: the association hub', bird: 'the caudolateral nidopallium, the bird’s prefrontal cortex', sys: 'map', st: 'built', n: 256, at: [1.25, 0.55, -0.95], r: [0.4, 0.4, 0.35], bi: true, issue: 331,
    role: 'Where sight, place, sound, body and reward meet in one settled state: the present moment. Holds a working trace of the moments just past.' },
  { id: 'trace', name: 'Working trace', bird: 'NCL delay cells', sys: 'map', st: 'built', n: 256, at: [1.45, 0.95, -1.15], r: [0.2, 0.2, 0.2], bi: true, issue: 331,
    role: 'Keeps what just happened active for a few moments, so a word heard a moment ago meets the thing in focus.' },
  // words
  { id: 'words', name: 'Words', bird: 'learned links between forms and things', sys: 'words', st: 'wip', n: 60, at: [-1.35, 0.45, -0.45], r: [0.25, 0.22, 0.25], bi: false, issue: 326,
    role: 'Links between a word’s forms (its sound, its written form) and the things and concepts they name. Tentative when heard with the focus on a thing; lasting when a pistachio follows a right answer.' },
  // hearing and voice
  { id: 'ear', name: 'Ears', bird: 'the cochleae, behind and below the eyes', sys: 'hearing', st: 'built', n: 80, at: [2.25, -0.75, -0.9], r: [0.12, 0.2, 0.2], bi: true, issue: 329,
    role: 'The raw sound split into frequency bands, moment by moment. The speech front end shipped in Cadence 0.98.0.' },
  { id: 'brainstem_aud', name: 'Cochlear nuclei', bird: 'nucleus magnocellularis, angularis and laminaris', sys: 'hearing', st: 'planned', n: 240, at: [0.3, -1.05, -1.65], r: [0.15, 0.15, 0.2], bi: true, issue: 329,
    role: 'The first relays of hearing: timing and loudness, and where a sound comes from (the time difference between the ears).' },
  { id: 'mld', name: 'MLd and ovoidalis', bird: 'the auditory midbrain and thalamus', sys: 'hearing', st: 'planned', n: 240, at: [0.75, -0.45, -0.95], r: [0.2, 0.2, 0.22], bi: true, issue: 329,
    role: 'Carries sound up to the forebrain, sharpening it by frequency and time.' },
  { id: 'fieldl', name: 'Field L', bird: 'the primary auditory forebrain', sys: 'hearing', st: 'wip', n: 512, at: [0.5, 0.3, -1.25], r: [0.22, 0.25, 0.2], bi: true, issue: 329,
    role: 'The first auditory area of the forebrain: learns the sound features its world is made of.' },
  { id: 'ncm', name: 'NCM and CM', bird: 'the secondary auditory forebrain: memory of heard sounds', sys: 'hearing', st: 'wip', n: 512, at: [0.4, 0.65, -1.55], r: [0.2, 0.22, 0.2], bi: true, issue: 329,
    role: 'Compresses a heard sound into a code that carries what it was, less who said it; in songbirds it holds the memory of heard songs. A heard word joins the present moment from here.' },
  { id: 'vocal', name: 'Vocal core and shell', bird: 'the parrot’s song system: NLC to AAC', sys: 'hearing', st: 'wip', n: 256, at: [1.2, 0.15, 0.25], r: [0.25, 0.2, 0.3], bi: true, issue: 329,
    role: 'Unique to parrots: a core like songbirds’ and a shell around it, larger in African Greys. Drives the voice from the word chosen.' },
  { id: 'voice', name: 'Voice', bird: 'the syrinx and its motor nucleus', sys: 'hearing', st: 'wip', n: 80, at: [0, -1.85, -1.4], r: [0.2, 0.12, 0.2], bi: false, issue: 329,
    role: 'Outputs the frequencies of a heard word, replayed from memory: the parrot repeats what it heard. No speech synthesis.' },
  // motor
  { id: 'arco', name: 'Arcopallium: the motor', bird: 'the bird’s motor output', sys: 'motor', st: 'wip', n: 70, at: [1.0, -0.35, -0.75], r: [0.3, 0.22, 0.3], bi: true, issue: 332,
    role: 'One slot per joint: head turn, tilt and roll, neck, beak, wings, grips and legs, and a reach that says how far the focused thing is.' },
  { id: 'body', name: 'Body sense', bird: 'proprioception and head-direction cells', sys: 'motor', st: 'wip', n: 148, at: [0, -1.25, -2.4], r: [0.25, 0.18, 0.25], bi: false, issue: 332,
    role: 'Where each joint is and how fast it moves, and which way the head points: the parrot feels its own body.' },
  { id: 'joints', name: 'Joints', bird: 'neck, beak, wings, legs', sys: 'motor', st: 'wip', n: 11, at: [0, -2.1, -2.3], r: [0.3, 0.1, 0.2], bi: false, issue: 332,
    role: 'Eleven joints the brain drives: head yaw, pitch and roll, neck, beak, two wings, two grips, two legs.' },
  { id: 'cerebellum', name: 'Cerebellum', bird: 'timing and fine control', sys: 'motor', st: 'planned', n: 0, at: [0, 0.35, -2.0], r: [0.75, 0.6, 0.55], bi: false, issue: 331,
    role: 'Planned for later: smooth, timed movement.' },
  // reward
  { id: 'striatum', name: 'Striatum', bird: 'the basal ganglia: the actor', sys: 'reward', st: 'built', n: 128, at: [0.7, -0.25, 0.95], r: [0.3, 0.22, 0.3], bi: true, issue: 331,
    role: 'Learns which choices pay. With the critic it is the actor-critic of the library.' },
  { id: 'vta', name: 'VTA and SNc: dopamine', bird: 'the midbrain’s dopamine', sys: 'reward', hue: '#ffc23d', st: 'built', n: 32, at: [0, -0.95, -0.4], r: [0.22, 0.15, 0.2], bi: false, issue: 326,
    role: 'The pistachio arrives here. The difference between the reward and what was expected turns tentative links into lasting ones.' },
  // the neuromodulators' nuclei (each sends one chemical far through the brain)
  { id: 'lc', name: 'Locus coeruleus: noradrenaline', bird: 'a small nucleus in the brainstem that sends noradrenaline to nearly the whole brain', sys: 'mod', hue: '#5b8cff', st: 'planned', n: 24, at: [0.22, -0.85, -1.95], r: [0.1, 0.08, 0.12], bi: true, issue: 337,
    role: 'Fires when something surprising happens and raises the brain’s alertness: learning is faster and the moment is kept more readily.' },
  { id: 'bf', name: 'Basal forebrain: acetylcholine', bird: 'cholinergic nuclei below the forebrain (and the isthmic nuclei for the tectum)', sys: 'mod', hue: '#5fd08e', st: 'planned', n: 24, at: [0.4, -0.7, 0.55], r: [0.14, 0.09, 0.14], bi: true, issue: 337,
    role: 'Turns up the gain where attention is: the place in focus is seen sharper and learned from more.' },
];
// The tracts (from -> to, a weight, what they carry)
export const T = [
  ['retina', 'tectum', 1.0, 'each eye to the opposite tectum'], ['retina', 'rotundus', 0.6, 'through the tectum to rotundus'], ['retina', 'wulst', 0.6, 'through the thalamus (GLd) to the Wulst'], ['retina', 'flow', 0.5, 'whole-field motion'],
  ['tectum', 'rotundus', 0.8, 'the glimpse at the winner'], ['tectum', 'arco', 0.6, 'the orienting reflex: turn the head to the winner'], ['tectum', 'ncl', 0.5, 'what is in focus'],
  ['rotundus', 'ncl', 0.7, 'what the thing is'], ['rotundus', 'place', 0.5, 'its kind'], ['wulst', 'place', 0.7, 'how far it is'], ['wulst', 'ncl', 0.6, 'two views agree'], ['ncl', 'wulst', 0.3, 'back to the Wulst'],
  ['flow', 'ncl', 0.4, 'my head moved'], ['body', 'ncl', 0.5, 'where my joints are'], ['body', 'place', 0.4, 'which way the head points'],
  ['place', 'map', 0.9, 'a thing written at its place'], ['map', 'ncl', 0.7, 'what is where'], ['map', 'tectum', 0.2, 'where held things should appear'],
  ['ncl', 'trace', 0.6, 'kept for a few moments'], ['trace', 'ncl', 0.6, 'what just happened'], ['ncl', 'arco', 0.7, 'what to do'], ['ncl', 'tectum', 0.3, 'where to look next'],
  ['ncl', 'heads', 0.6, 'the cue: what is in focus'], ['heads', 'records', 0.7, 'fetch'], ['records', 'heads', 0.7, 'the record found'], ['heads', 'ncl', 0.7, 'the past brought back'],
  ['ear', 'brainstem_aud', 1.0, 'the cochlea’s bands'], ['brainstem_aud', 'mld', 0.8, 'up the auditory midbrain'], ['mld', 'fieldl', 0.8, 'through ovoidalis to Field L'], ['fieldl', 'ncm', 0.8, 'to the secondary areas'],
  ['ncm', 'ncl', 0.6, 'a heard word joins the moment'], ['ncm', 'records', 0.5, 'a heard sound stored'], ['ncm', 'heads', 0.4, 'a heard sound as a cue'],
  ['ncl', 'words', 0.6, 'the thing in focus'], ['words', 'ncl', 0.6, 'what a word means'], ['heads', 'words', 0.5, 'a fetched word'], ['words', 'vocal', 0.7, 'the word chosen to say'],
  ['vocal', 'voice', 0.9, 'replay the heard frequencies'], ['voice', 'ear', 0.3, 'the parrot hears itself'],
  ['arco', 'joints', 0.9, 'joint targets'], ['joints', 'body', 0.7, 'the body moved'],
  ['vta', 'striatum', 0.6, 'dopamine'], ['vta', 'ncl', 0.4, 'dopamine'], ['vta', 'words', 0.4, 'dopamine: a link made lasting'], ['striatum', 'arco', 0.4, 'the choice that pays'], ['ncl', 'striatum', 0.4, 'the moment’s state'],
];
export const HUE = { vision: '#6cb6ff', map: '#3fd6c2', hearing: '#b49cff', words: '#f2e48a', motor: '#ffb454', reward: '#ff6b78', mod: '#9aa7b8' };
/** A region's own colour: its hue, else its system's. */
export const hueOf = (r) => r.hue || HUE[r.sys];

// Short names (the 3D labels) and what each region does, in a few words (the right panel's cards)
export const SHORT = { tectum: 'Tectum', rotundus: 'Rotundus', wulst: 'Wulst', flow: 'Flow nuclei', place: 'Gaze to place', map: 'Hippocampus',
  records: 'Records', heads: 'Memory heads', ncl: 'NCL', trace: 'Trace', words: 'Words', ear: 'Ears', brainstem_aud: 'Cochlear nuclei',
  mld: 'MLd', fieldl: 'Field L', ncm: 'NCM, CM', vocal: 'Vocal core', voice: 'Voice', arco: 'Arcopallium', body: 'Body sense',
  joints: 'Joints', cerebellum: 'Cerebellum', striatum: 'Striatum', vta: 'VTA: dopamine', retina: 'Retina', lc: 'Locus coeruleus', bf: 'Basal forebrain' };
export const DOES = { retina: 'what each eye sees', tectum: 'what stands out, the focus', rotundus: 'what a thing looks like, its kind', wulst: 'two views compared',
  arco: 'how far, the moves', map: 'the map of things', ear: 'the sound’s bands', fieldl: 'sound features', ncm: 'heard sound, held', voice: 'the bands it says',
  records: 'sounds kept', words: 'links from sounds to things', vocal: 'the word chosen to say', place: 'where it is', ncl: 'the present moment' };

// The neuromodulators: each a nucleus, a colour, and where its fibres go (weights for the wash)
export const MOD = {
  dopamine: { name: 'Dopamine', from: 'vta', colour: '#ffc23d', to: { striatum: 1, ncl: 0.8, vocal: 0.6, words: 0.6, records: 0.4, map: 0.3 },
    explain: 'Dopamine, from the VTA in the midbrain. It answers a reward against what was expected: more than expected (a pistachio after a good try) and it surges, less and it dips. Where it arrives, the synapses that just fired are made lasting. Drawn as a gold wash travelling out from the VTA.' },
  noradrenaline: { name: 'Noradrenaline', from: 'lc', colour: '#5b8cff', to: { ncl: 1, map: 0.8, tectum: 0.8, fieldl: 0.6, ncm: 0.6, rotundus: 0.5, cerebellum: 0.5 },
    explain: 'Noradrenaline, from the locus coeruleus in the brainstem. It fires when something surprising happens and wakes the whole brain up: what follows is learned faster and kept more readily. Drawn as a blue wash.' },
  acetylcholine: { name: 'Acetylcholine', from: 'bf', colour: '#5fd08e', to: { tectum: 1, ncl: 0.8, rotundus: 0.6, fieldl: 0.6, map: 0.5 },
    explain: 'Acetylcholine, from the basal forebrain. It turns up the gain where attention is: the thing in focus is seen sharper and learned from more. Drawn as a green wash toward the focus.' },
};

// How the memories connect: the path of each kind of memory through the regions, in order
export const PATHS = [
  { id: 'images', name: 'Images', colour: '#6cb6ff', via: ['retina', 'rotundus', 'map'],
    steps: ['eyes', 'what it looks like, its kind', 'where it is'],
    explain: 'How the parrot keeps a thing it sees. The eyes’ images reach the retina; rotundus and the entopallium learn what the thing looks like and which kind it is; the hippocampus writes it on the map of things at its place, and holds it there when it goes out of view.' },
  { id: 'sounds', name: 'Sounds', colour: '#b49cff', via: ['ear', 'fieldl', 'ncm', 'records'],
    steps: ['the ear’s bands', 'sound features', 'the sound, held', 'a record slot'],
    explain: 'How the parrot keeps a sound. The ear splits it into frequency bands; Field L and NCM compress it; the whole sound is kept in a record slot, as a sound and never as letters. Heard again, its record grows deeper and fades more slowly.' },
  { id: 'words', name: 'Words', colour: '#f2e48a', via: ['records', 'words', 'rotundus'],
    steps: ['the sound’s record', 'its link', 'the thing in focus'],
    explain: 'How a sound comes to mean a thing. When a sound is heard while the parrot looks at a thing, synapses link the sound’s record to that thing. Said again while it looks at the same thing, the link grows: the sound becomes the thing’s word.' },
  { id: 'saying', name: 'Saying', colour: '#ff8a5c', via: ['records', 'vocal', 'voice'],
    steps: ['the word’s record', 'the vocal core', 'the voice'],
    explain: 'How the parrot says a word. Its record is read out to the vocal core, which drives the voice with the bands it remembers. It hears itself, compares, and says it a little better the next time.' },
];
export const STC = { built: '#3fd6c2', wip: '#ffb454', planned: '#6c737c' };
export const STN = { built: 'in the library', wip: 'being built', planned: 'planned' };
