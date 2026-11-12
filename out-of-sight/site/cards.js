// What every part of the brain says about itself, and the path of a position through the map.
//
// A card holds the part's name, the role it plays, what it holds and what it is doing at this
// moment, written from the map's live state. The same texts are reachable in order as the
// stages of "follow the position". The texts are the library guide's own, word for word
// (docs/space.md of the commit the pack's wheel is built from, GUIDE below): the regions' table
// for the parts, the eight steps of "How a position travels" for the stages, and the rows of
// "What the brain does and what the program does" beside the steps they belong to.

import { metres, phrase, LABEL } from './where.js';

export const GUIDE = 'lane-099-space bff49e22';

const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const num = (v, d = 2) => (Object.is(Number(v.toFixed(d)), -0) ? 0 : v).toFixed(d);
const at = (p) => `(${num(p[0])}, ${num(p[1])}) m`;
const secs = (moments, dt) => `${Math.max(0, Math.round(moments * dt))} s`;
const name = (n) => LABEL[n] || n;
const code = (s) => s.replace(/`([^`]+)`/g, '<code>$1</code>');

// -- live sentences

function stateWords(e, dt) {
  if (!e) return 'not on the map';
  switch (e.state) {
    case 'seen': return 'seen at this moment';
    case 'felt': return 'placed at this moment by the arm’s joint readings';
    case 'heard': return 'placed at this moment by a sound';
    case 'held': return `held where last seen, ${secs(e.since, dt)} ago`;
    case 'near': return `near where it vanished ${secs(e.since, dt)} ago, out of sight`;
    default: return 'known, not known where';
  }
}
function thingLine(e, ctx) {
  const where = e.place ? `${metres(ctx.around(e.place).distance)} away, ${phrase(ctx.around(e.place).bearing)}` : 'no place';
  const pieces = e.pieces && e.pieces.length > 1 ? ` in ${e.pieces.length} pieces` : '';
  return `the ${name(e.name)}: ${stateWords(e, ctx.dt)}, ${where} (${e.cells.length} cells${pieces})`;
}
function inventoryLine(ctx) {
  if (!ctx.inventory.length) return 'The map holds no thing: no sense has reported one.';
  return `The map holds ${ctx.inventory.length === 1 ? 'one thing' : `${ctx.inventory.length} things`}:<br>${ctx.inventory.map((e) => `<span data-record>${esc(thingLine(e, ctx))}</span>`).join('<br>')}`;
}
function handLine(ctx) {
  const e = ctx.hand;
  if (!e) return `The map holds no ${name(ctx.handName)}.`;
  const p = e.place ? ` at <span data-place="${num(e.place[0], 3)},${num(e.place[1], 3)}">${at(e.place)}</span>` : '';
  return `The ${name(e.name)}: ${stateWords(e, ctx.dt)}${p}, on <span data-cells="${e.cells.length}">${e.cells.length} cells</span>${e.pieces?.length > 1 ? ` in ${e.pieces.length} pieces` : ''}.`;
}
function reportLine(ctx) {
  const r = ctx.record;
  if (!r) return 'No moment so far.';
  const seen = r.report.map((p, k) => (p ? `the ${name(k === 0 ? ctx.handName : ctx.names[k])} at ${at(p)}` : null)).filter(Boolean);
  const felt = ctx.own ? ` The arm’s joint readings name its hand’s place: ${at(r.chain?.at(-1) || r.truth[0])}.` : '';
  if (!ctx.cameraOn) return `The camera is off: it reports nothing.${felt}`;
  return `${seen.length ? `The camera reports ${seen.join(', ')}.` : 'The camera reports nothing at this moment.'}${felt}`;
}
function activity(ctx, region) {
  const a = ctx.act(region);
  let lit = 0;
  for (const v of a) if (v > 1e-4) lit += 1;
  return `${lit.toLocaleString('en')} of ${a.length.toLocaleString('en')} neurons are above rest.`;
}
function askedLine(ctx) {
  const q = ctx.asked;
  if (!q || performance.now() - q.at > 4000) return 'No question at this moment. Tap a thing on the scene to ask where it is, or the floor to ask what is there.';
  return q.kind === 'where' ? `Asked: where is the ${name(q.name)}? The map settled with its kind as the cue.` : `Asked: what is there? The map settled with the place as the cue${q.name ? `, on the ${name(q.name)}` : ', on nothing'}.`;
}
function strongest(ctx, region) {
  const a = ctx.act(region);
  let k = -1, top = 1e-4;
  a.forEach((v, j) => { if (v > top) { top = v; k = j; } });
  if (k < 0) return 'Every unit is at rest.';
  const kind = Object.entries(ctx.describe.codes || {}).find(([, u]) => u.includes(k))?.[0];
  return `The most active unit is unit ${k}${kind ? `, the ${name(kind)}’s code` : ''}.`;
}
function doubtLine(ctx) {
  const a = ctx.act('doubt');
  let lit = 0;
  for (const v of a) if (v > 0.1) lit += 1;
  return lit ? `${lit} cells hold a thing that was not seen to be there.` : 'No cell holds a thing that was not seen to be there.';
}
function lostLine(ctx) {
  const lost = ctx.inventory.filter((e) => !e.place);
  return lost.length ? `Known with no place: ${lost.map((e) => `the ${name(e.name)}`).join(', ')}.` : 'No kind is known with no place.';
}
function clockLine(ctx) {
  const held = ctx.inventory.filter((e) => e.place && e.since !== null);
  return held.length ? `${held.map((e) => `The ${name(e.name)}’s cells: written ${e.since ? `${secs(e.since, ctx.dt)} ago` : 'at this moment'}`).join('. ')}.` : 'No cell holds a thing.';
}

// -- the parts: the guide's table "The regions", word for word in "What it holds"

const PARTS = {
  map: { title: 'The map', role: 'map', holds: 'The sheet: a unit at a cell is active where a thing whose kind’s code holds the unit is at the cell. At each moment its drive is its own potentials of the moment before',
    live: (ctx) => `${handLine(ctx)} ${activity(ctx, 'map')}` },
  held: { title: 'The map replayed for a question', role: 'recall', holds: 'The question’s input: for “where is” it is driven by the sheet’s carried potentials and projects onto the sheet cell to cell',
    live: (ctx) => `${askedLine(ctx)} ${activity(ctx, 'held')}` },
  reference: { title: 'A question’s kind', role: 'attention', holds: 'One a code unit; a question’s kind drives the references of its code',
    live: (ctx) => `${askedLine(ctx)} ${strongest(ctx, 'reference')}` },
  where: { title: 'Where', role: 'placecells', holds: 'One a cell, reading `map` over the code units',
    live: (ctx) => `${activity(ctx, 'where')} ${askedLine(ctx)}` },
  what: { title: 'What', role: 'objects', holds: 'One a code unit, reading `map` over the cells',
    live: (ctx) => `${strongest(ctx, 'what')} ${askedLine(ctx)}` },
  clock: { title: 'The clock', role: 'timer', holds: 'One a cell: the moments since a sense wrote the cell. It carries its own potential and a bias of one',
    live: clockLine },
  doubt: { title: 'Doubt', role: 'doubt', holds: 'One a cell: a one where the cell holds a thing that was not seen to be there', live: doubtLine },
  lost: { title: 'A kind with no place', role: 'lost', holds: 'One a code unit: a one where a thing of the kind is known with no place', live: lostLine },
  // learned physics (cadence.space.physics, the module's docstring word for word)
  physics: { title: 'How things move, learned', role: 'motion',
    holds: 'The mass on each moving velocity is the next moment’s drive on `went`, and one kernel of three by three cells for each velocity, tied across every cell and every kind, drives `moving`. The kernels are born as “stay”: a brain that has watched nothing answers as the map does. Whenever a thing is seen at two moments in a row, the mass it carried the moment before (its place and velocities) is the drive and the same mass moved by the motion seen is the target. Each velocity’s kernel learns where the mass of things seen moving at that velocity is found a moment later: going on, stopping, or turning',
    live: physicsLine },
};

function physicsLine(ctx) {
  const ph = ctx.physics;
  if (!ph) return 'This map has no learned physics.';
  const e = ph.errors.at(-1), hand = ctx.hand;
  const v = hand?.velocity ? ` The ${name(hand.name)}’s moving mass carries it at ${(Math.hypot(...hand.velocity) / ctx.dt * 100).toFixed(0)} cm a second, ${Math.round((hand.moving || 0) * 100)} of 100 of its mass moving.` : '';
  return `${ph.lessons.toLocaleString('en')} lessons taught so far${e === undefined ? '' : `; the latest batch’s error ${e.toFixed(2)}${ph.errors.length > 3 ? `, from ${ph.errors[0].toFixed(2)} at the first` : ''}`}.${v}`;
}

const ROLE = {
  map: ['plays the role of the parietal map of where things are', '#3fe0cf'],
  recall: ['plays the role of recall: the map replayed for a question', '#a88ffa'],
  attention: ['plays the role of attention to one kind', '#ffcc6b'],
  placecells: ['plays the role of place cells: where a kind is', '#f28cc7'],
  objects: ['plays the role of object cells: what a thing is', '#66bdff'],
  timer: ['plays the role of a timer, drawn where the cerebellum sits', '#9eb8db'],
  doubt: ['plays the role of a confidence estimate: the cells of doubt', '#a88ffa'],
  lost: ['plays the role of knowing a thing with no place', '#9eb8db'],
  motion: ['plays the role of motion-selective cells: where a thing moving at each velocity is found a moment later', '#8cf299'],
};

// The guide's table "What the brain does and what the program does", row by row.
const TABLE = {
  held: ['Where things are held between moments', 'Copies the sheet’s potentials to the next moment’s drive on the same neurons', 'In the settled activity of `map`, with `clock`, `doubt` and `lost`'],
  list: ['The list of things', 'None: no cast, no rows', 'The peaks of the sheet'],
  report: ['A report from a sense', 'Turns the kind and the place into a drive on four cells', 'The cells settle on it'],
  holding: ['Holding a place', 'Nothing beyond the copy', 'A neuron driven by its own last potential, with no synapse into it, settles at that potential: the place stays exactly'],
  empty: ['A place seen empty', 'Passes the cells in sight as the settle’s mask; finds a piece of activity with no report of its kind and drives it onto the unseen cells within reach', 'A seen cell is held at zero in every sweep'],
  which: ['Which report is which thing', 'Compares a report’s place with the pieces of its kind (`step`, `stride`)', 'Two things of a kind are two peaks'],
  questions: ['Questions', 'Sets the cue: the kind’s code drives the pools’ references, or the mask keeps the cells around a place', '`where` and `what` settle on the answer'],
  inventory: ['The inventory', 'Reads the peaks, their cells and the clock', 'Holds them'],
  kinds: ['Kinds', 'Takes each thing’s kind from the caller as a number', 'Holds a kind as a code over the sheet’s units'],
  lessons: ['Lessons', 'None', 'None: the map’s graph has no taught synapse'],
};
const rows = (...keys) => keys.map((k) => `<p class="who"><b>${TABLE[k][0]}.</b> <i>The program beside the map:</i> ${code(TABLE[k][1])}. <i>The brain (the map’s graph):</i> ${code(TABLE[k][2])}.</p>`).join('');

// -- the path of a position: the guide's "How a position travels", word for word

const STAGES = [
  { id: 'report', parts: ['map'], title: 'A sense reports a thing',
    body: 'A report is a kind and a place: the camera’s “a hand at this place”, the place a sound names, the place the body’s own readings name. The caller gives the kind as a number.',
    table: ['report'], live: reportLine },
  { id: 'enters', parts: ['map'], title: 'The report enters the map',
    body: 'The place becomes weights on the four cells around it, whose mean is the place, and drives those cells on the units of the kind’s code. A kind the map has not held enters the same way. No thing is announced beforehand.',
    table: ['kinds'], live: handLine },
  { id: 'carries', parts: ['map', 'clock'], title: 'The map carries itself',
    body: 'At the next moment the potentials the sheet settled to drive the same neurons, and a neuron with that drive and no synapse into it settles at that potential. With no report and no sight of the cell nothing changes, to the bit: the last known place is the place in the state.',
    table: ['held', 'holding'], live: handLine },
  { id: 'again', parts: ['map'], title: 'Sight again',
    body: 'A report within `step` of a piece of its kind’s activity is that thing. Its old cells are cleared and the report’s cells are written, so in view a thing’s place is the latest report.',
    table: ['which'], live: (ctx) => `${reportLine(ctx)} ${handLine(ctx)}` },
  { id: 'empty', parts: ['map', 'doubt'], title: 'A place seen empty',
    body: 'A cell the camera sees loses what the map carried into it. A thing whose place is seen empty, with no report of its kind near, is not where it was seen. The map drives it onto the cells out of sight within reach of that place and marks those cells as doubt. With no such cell the thing is kept by its kind with no place.',
    also: (ctx) => `On this page the map is set as the guide’s founder: “It is driven onto the cells out of sight around where it was held, as a peak <code>reach</code> metres wide; cells farther than two reaches take none. With no such cell it is kept by its kind with no place”, with <code>reach</code> ${ctx.describe.settings?.reach ?? '–'} m. This uses sight alone and no model of movement.`,
    table: ['empty'], live: (ctx) => `${handLine(ctx)} ${doubtLine(ctx)}` },
  { id: 'found', parts: ['map', 'doubt'], title: 'It is found',
    body: 'A report of the kind ends the doubt: the cells of doubt that hold the kind are cleared, and so is the nearest piece of the kind within `stride`, as the same thing moved unseen. With none of its kind that near, the report is a new thing.',
    table: ['which'], live: (ctx) => `${handLine(ctx)} ${lostLine(ctx)}` },
  { id: 'questions', parts: ['reference', 'held', 'where', 'what'], title: 'Questions',
    body: '“Where is the apple”: the carried potentials drive `held`, the apple’s code opens the pools of its units, the sheet settles on those units alone and `where` holds the apple’s places. “What is there”: the settle keeps the cells around the place and `what` holds the code of the thing there.',
    table: ['questions'], live: askedLine },
  { id: 'inventory', parts: ['map', 'clock'], title: 'The inventory',
    body: 'Every piece of activity is a thing: its kind, its place (the mean of the piece), its cells, the moments since a sense wrote it, and its state.',
    also: () => 'The map is wiring and carried activity. Recognising a thing from pixels is another module’s work: the caller says “a thing of this kind at this place”.',
    table: ['inventory', 'list', 'lessons'], live: inventoryLine },
];

export const stagesFor = () => STAGES;

/** A part's card, as HTML. `unit`: a line about the unit under the pointer, if any. */
export function partCard(id, ctx, unit = '') {
  const part = PARTS[id];
  if (!part) return '';
  const [role, color] = ROLE[part.role] || ['is a population of the map’s graph', '#8d97b2'];
  const n = ctx.regions[id]?.neurons.length;
  const stage = STAGES.findIndex((s) => s.parts[0] === id);
  return `<div style="--c:${color}" data-part="${id}"><h3>${part.title}</h3><p class="role">${role}</p>`
    + `<p>${code(part.holds)}.${n ? ` ${n.toLocaleString('en')} neurons.` : ''}</p>`
    + `<p class="live"><b>At this moment</b>${part.live(ctx)}</p>`
    + (unit ? `<p class="unit">${unit}</p>` : '')
    + (stage >= 0 ? `<p class="unit">Stage ${stage + 1} of ${STAGES.length} on the path of a position.</p>` : '') + '</div>';
}

const TRACTS = {
  'held>map': ['From the replay to the map', 'For a question by kind, the carried potentials drive the replay, which projects onto the sheet cell to cell.'],
  'map>where': ['From the map to where', 'Each cell’s code units project onto that cell’s neuron of where.'],
  'map>what': ['From the map to what', 'Each code unit, at every cell, projects onto that unit’s neuron of what.'],
};

/** A tract's card. `flow`: its live numbers ({ signal, synapses, excite, inhibit }). */
export function tractCard(key, flow) {
  const [title, what] = TRACTS[key] || [`Synapses from ${key.replace('>', ' to ')}`, 'A bundle of synapses of the map’s graph.'];
  const quiet = flow.signal < 1e-9;
  return `<div style="--c:#ff9e48" data-tract="${key}"><h3>${title}</h3><p class="role">a fibre tract: ${flow.synapses.toLocaleString('en')} synapses, each at an efficacy of 2, the inverse of the neuron’s slope at rest; none is taught</p><p>${what}</p>`
    + `<p class="live"><b>At this moment</b>${quiet ? 'Silent: the neurons it starts from are at rest.' : `It carries a signal of <span>${flow.signal.toPrecision(2)}</span>: every synapse’s strength times the activity of the neuron it starts from, added up.`}</p></div>`;
}

/** A stage of the path, as HTML, with its place in the order. */
export function stageCard(index, ctx) {
  const stage = STAGES[index], part = PARTS[stage.parts[0]];
  const [role, color] = ROLE[part.role] || ['', '#8d97b2'];
  return `<div style="--c:${color}" data-stage="${stage.id}"><p class="kicker">The path of a position · ${index + 1} of ${STAGES.length}</p><h3>${stage.title}</h3>`
    + `<p class="role">${part.title}: ${role}</p><p>${code(stage.body)}</p>`
    + (stage.also ? `<p>${stage.also(ctx)}</p>` : '')
    + rows(...stage.table)
    + `<p class="live"><b>At this moment</b>${stage.live(ctx)}</p></div>`;
}
