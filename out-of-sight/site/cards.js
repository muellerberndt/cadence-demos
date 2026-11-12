// What every part of the brain says about itself, and the path of a position through the brain.
//
// A card holds the part's name, the role it plays, one or two plain sentences on what it does,
// and what it is doing at this moment, written from the brain's live state. The same texts are
// reachable in order as the eight stages of "follow the position". Every sentence describes
// what the brain on this page does. COPY is keyed by the brain's kind. `baseline` is the plain
// composed brain; a stage whose `changes` is set is one the trained place module does another
// way, and its card says so. `place` is the trained place module: there a program beside the
// brain (the space) holds each place between moments, and the brain answers how far a place
// moves in a step, how far off it may be, and the place a cue names. Its texts are provisional
// until the module's own description of its stages replaces them.

import { radiusAt, RATE } from './controls.js';
import { metres, phrase } from './where.js';

const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const num = (v, d = 2) => (Object.is(Number(v.toFixed(d)), -0) ? 0 : v).toFixed(d);
export const at = (p) => `(${num(p[0])}, ${num(p[1])}) m`;
export const cm = (v) => (v < 0.1 ? `${(v * 100).toFixed(1)} cm` : `${Math.round(v * 100)} cm`);
const secs = (moments, dt) => `${(moments * dt).toFixed(1)} s`;
const area = (a) => (a >= 1 ? `${a.toFixed(2)} m²` : `${Math.round(a * 1e4).toLocaleString('en')} cm²`);
const WHY = { occluder: 'it is in the pillar’s shadow', arm: 'it is in the arm’s shadow', field: 'it is beside or behind the body, outside the camera’s field', off: 'the camera is off' };

/** One number for the answer's doubt: the radius of the circle as large as the area at RATE. */
export const uncertainty = (belief) => radiusAt(RATE) * Math.sqrt(Math.max(belief.sd[0], 1e-9) * Math.max(belief.sd[1], 1e-9));

function preferred(layout, reading) {
  const [lo, hi] = layout.ranges[reading];
  return Array.from({ length: layout.per }, (_, j) => lo + ((hi - lo) * j) / (layout.per - 1));
}
function nearest(values, v) {
  const order = values.map((p, j) => [Math.abs(p - v), j]).sort((a, b) => a[0] - b[0]).slice(0, 2).map((e) => values[e[1]]).sort((a, b) => a - b);
  return order;
}

/** A small drawing of a population code: one row of bars a reading, each bar a tuned unit at
 *  its activity at this moment. */
export function peakSvg(rows, color = '#66bdff') {
  const W = 300, rowH = 30, pad = 26, H = rows.length * (rowH + 14) + 4;
  let out = `<svg class="peak" viewBox="0 0 ${W} ${H}" role="img" aria-label="The peak over the tuned units at this moment">`;
  rows.forEach((row, r) => {
    const n = row.values.length, bw = (W - pad - 4) / n, y0 = r * (rowH + 14) + 2;
    let top = 1e-6;
    for (const v of row.values) top = Math.max(top, v);
    out += `<text x="0" y="${y0 + rowH - 2}">${esc(row.label)}</text>`;
    for (let j = 0; j < n; j++) {
      const v = Math.max(0, row.values[j]) / Math.max(top, row.floor ?? 0.2), h = Math.max(1.2, v * rowH);
      out += `<rect x="${(pad + j * bw + 0.8).toFixed(1)}" y="${(y0 + rowH - h).toFixed(1)}" width="${(bw - 1.6).toFixed(1)}" height="${h.toFixed(1)}" rx="1" fill="${color}" opacity="${(0.22 + 0.78 * Math.min(1, v)).toFixed(2)}"/>`;
    }
    out += `<text x="${pad}" y="${y0 + rowH + 10}">${num(row.lo, 1)}</text><text x="${W - 4}" y="${y0 + rowH + 10}" text-anchor="end">${num(row.hi, 1)} ${row.unit || 'm'}</text>`;
    if (row.mark !== null && row.mark !== undefined && Number.isFinite(row.mark)) {
      const x = pad + ((row.mark - row.lo) / (row.hi - row.lo)) * (W - pad - 4 - bw) + bw / 2;
      out += `<path d="M${x.toFixed(1)} ${y0 + rowH + 1} l-3 5 h6 z" fill="#e9edf7"/>`;
    }
  });
  return `${out}</svg>`;
}

// -- live sentences, shared by the parts' cards and the stages

function seenLine(ctx) {
  const r = ctx.record;
  if (!r) return 'The brain has not been asked.';
  if (r.report[0]) return `The camera reports the hand at <span>${at(r.report[0])}</span>.`;
  return `No report: the camera does not see the hand (${WHY[ctx.why] || 'it is out of view'}). Out of view for <span>${ctx.unseen} moments (${secs(ctx.unseen, ctx.dt)})</span>.`;
}
function placeLine(ctx) {
  const b = ctx.belief;
  if (!b) return 'No answer.';
  const u = uncertainty(b);
  if (!ctx.unseen) return `It says the hand is at <span data-place="${num(b.place[0], 3)},${num(b.place[1], 3)}">${at(b.place)}</span>. The hand is in view. Uncertainty <span data-uncertainty="${u.toFixed(4)}">${cm(u)}</span>.`;
  const was = ctx.seenBelief ? uncertainty(ctx.seenBelief) : null;
  const trend = was === null ? '' : u > was * 1.05 ? `, up from ${cm(was)} when the hand was last seen` : u < was * 0.95 ? `, down from ${cm(was)} when the hand was last seen` : `, as when the hand was last seen`;
  return `It says the hand is at <span data-place="${num(b.place[0], 3)},${num(b.place[1], 3)}">${at(b.place)}</span>, unseen for <span data-unseen="${ctx.unseen}">${ctx.unseen} moments</span>. Uncertainty <span data-uncertainty="${u.toFixed(4)}">${cm(u)}</span>${trend}.`;
}
function codeLine(ctx, region) {
  const r = ctx.record;
  if (!r?.report[0]) return `All ${region.neurons.length} inputs are dark: there is no report to code.`;
  const [x, y] = r.report[0], px = nearest(preferred(region.layout, 0), x), py = nearest(preferred(region.layout, 1), y);
  return `x = ${num(x)} m: the peak stands between the inputs for ${num(px[0])} and ${num(px[1])} m. y = ${num(y)} m: between ${num(py[0])} and ${num(py[1])} m.`;
}
function commandLine(ctx) {
  const c = ctx.record?.commands || [];
  if (!c.some((v) => Math.abs(v) > 1e-6)) return 'The arm is at rest: every command is zero.';
  return `${c.map((v, k) => `Joint ${k + 1} is told to turn by ${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(3)} rad`).join(', ')} at this moment.`;
}
function lessonLine(ctx) {
  if (!ctx.teach) return 'Lessons are switched off.';
  if (ctx.record && !ctx.record.in_view[0]) return `No lesson: the hand is out of view. ${ctx.lessons.toLocaleString('en')} lessons so far.`;
  if (!ctx.lesson) return 'No lesson so far.';
  const ago = ctx.lesson.ageMs < 150 ? 'at this moment' : `${(ctx.lesson.ageMs / 1000).toFixed(1)} s ago`;
  return `The last lesson was ${ago} and changed <span>${ctx.lesson.changed.toLocaleString('en')}</span> synapses. The answer stood ${cm(ctx.lesson.mismatch)} from the report. ${ctx.lessons.toLocaleString('en')} lessons so far.`;
}
function doubtLine(ctx) {
  const b = ctx.belief;
  if (!b) return 'No answer.';
  const cover = ctx.coverage === null ? '' : ` Over the last ${ctx.coverage.moments} moments the true hand lay inside the area on ${Math.round(ctx.coverage.share * 100)} of 100.`;
  const width = b.cells ? `The area is ${b.cells.count} cells of the sheet, in ${b.cells.patches === 1 ? 'one patch' : `${b.cells.patches} patches`}.`
    : b.radius ? `Radius: ${cm(b.radius)}.` : `Width: ${cm(b.sd[0])} in x, ${cm(b.sd[1])} in y.`;
  return `${width} Area at nine in ten: <span>${area(b.area)}</span>.${cover}`;
}
function recordsLine(ctx) {
  // one line a kind: where it is around the body, and how the record came
  const lines = ctx.names.slice(1).map((name, i) => {
    const pin = ctx.pins[name], seen = ctx.record?.in_view[i + 1];
    if (!pin?.place) return `${name}: no record, never seen`;
    const rel = ctx.around(pin.place), how = seen ? 'in view' : `${pin.from === 'heard' ? 'heard' : 'seen'} ${secs(pin.unseen || 0, ctx.dt)} ago`;
    return `${name}: ${metres(rel.distance)}, ${phrase(rel.bearing)} · ${how}`;
  });
  return lines.map((l) => `<span data-record>${esc(l)}</span>`).join('<br>');
}
function answerLine(ctx) {
  const b = ctx.belief, s = ctx.sheet;
  if (!b || !s) return 'No answer.';
  const top = (p) => { let k = 0; for (let j = 1; j < p.length; j++) if (p[j] > p[k]) k = j; return k; };
  const ix = top(s.px), iy = top(s.py);
  return `x: the strongest unit prefers ${num(ctx.centres[0][ix])} m and holds ${Math.round(s.px[ix] * 100)}% of the vote. y: the strongest prefers ${num(ctx.centres[1][iy])} m and holds ${Math.round(s.py[iy] * 100)}%. Answer: <span>${at(b.place)}</span>.`;
}
function settleLine(ctx) {
  const s = ctx.settle;
  if (!s) return 'No settle so far.';
  if (s.sweeps === 0) return `No sweep was needed: the state of the moment before satisfied the brain’s equations as it stood (residual ${s.residual.toExponential(1)}).`;
  return `This moment’s settle took <span>${s.sweeps} sweeps</span> and came to rest with a residual of ${s.residual.toExponential(1)}.`;
}
function activity(ctx, name) {
  const a = ctx.act(name);
  let sum = 0, lit = 0;
  for (const v of a) { sum += Math.max(0, v); if (v > 0.05) lit += 1; }
  return `${lit} of ${a.length} neurons are active, at a mean of ${(sum / Math.max(1, a.length)).toFixed(2)}.`;
}
const codeRows = (ctx, name, labels, unit, marks) => {
  const region = ctx.regions[name], a = ctx.act(name), per = region.layout.per;
  return region.layout.ranges.map(([lo, hi], r) => ({ label: labels[r] || `${r + 1}`, values: a.subarray(r * per, (r + 1) * per), lo, hi, unit, mark: marks ? marks[r] : null, floor: 0.3 }));
};

// -- the copy

const MARK = 'Baseline brain: the trained place module does this stage another way.';
const PROVISIONAL = 'Provisional text: the trained module’s own description replaces it.';

const COPY = {
  baseline: {
    parts: {
      camera: {
        title: 'The camera’s report', role: 'visual',
        what: 'What the camera sees of the hand enters the brain here, as a position in the room. Its x and its y are each spread over 16 inputs. Every input has a favourite position and lights up when the hand is near it.',
        live: (ctx) => `${seenLine(ctx)} ${ctx.record?.report[0] ? '' : 'All of these inputs are dark.'}`,
        draw: (ctx) => peakSvg(codeRows(ctx, 'camera', ['x', 'y'], 'm', ctx.record?.report[0]), '#66bdff'),
      },
      joints: {
        title: 'The arm’s joint angles', role: 'somatosensory',
        what: 'The arm reports its own joint angles, as you feel where your elbow is with your eyes shut. Each angle is spread over 12 inputs, as the camera’s report is.',
        live: (ctx) => (ctx.record ? `${ctx.record.joints.map((q, k) => `Joint ${k + 1} at ${num(q)} rad`).join(', ')}. That puts the arm’s own hand at ${at(ctx.record.chain.at(-1))}.` : 'No reading.'),
        draw: (ctx) => peakSvg(codeRows(ctx, 'joints', ['j1', 'j2', 'j3'], 'rad', ctx.record?.joints), '#c7cc80'),
      },
      commands: {
        title: 'The arm’s commands, as a copy', role: 'motor',
        what: 'What the arm is told to do at this moment, joint by joint, handed to the brain as a copy. A brain that reads its own commands can know where its own hand goes without seeing it.',
        live: commandLine,
        draw: (ctx) => peakSvg(codeRows(ctx, 'commands', ['j1', 'j2', 'j3'], 'rad', ctx.record?.commands), '#ff9f4a'),
      },
      association: {
        title: 'The association region', role: 'association',
        what: '96 neurons between the inputs and the answer. They drive the answer units, and the answer units drive them back, sweep after sweep, until nothing changes. That resting state is the answer.',
        live: (ctx) => `${settleLine(ctx)} ${activity(ctx, 'association')}`,
      },
      prefrontal: {
        title: 'The working trace', role: 'prefrontal',
        what: 'A copy of the association region’s state from the moment before, fed back in as an input. It is the one thing this baseline brain carries from one moment to the next.',
        live: (ctx) => activity(ctx, 'prefrontal'),
      },
      place: {
        title: 'The place answer', role: 'place',
        what: 'The brain’s answer to “where is the hand?”: 20 units for x and 20 for y, each with a favourite position. After the brain settles, the peak over these units is where it says the hand is. The positions are the room’s own, so a turn of the camera moves no unit’s meaning.',
        live: placeLine,
        draw: (ctx) => (ctx.sheet ? peakSvg([{ label: 'x', values: ctx.sheet.px, lo: ctx.centres[0][0], hi: ctx.centres[0].at(-1), mark: ctx.belief?.place[0], floor: 0.05 },
          { label: 'y', values: ctx.sheet.py, lo: ctx.centres[1][0], hi: ctx.centres[1].at(-1), mark: ctx.belief?.place[1], floor: 0.05 }], '#3fe0cf') : ''),
      },
      records: {
        title: 'The records: what is where', role: 'hippocampus', provisional: true,
        what: 'A long-term memory beside the brain, with 12 slots: one record for each kind of thing. A record’s key says what the thing is (“apple”), and its value says where it is. The two sit in one record, so they are found together: ask for a kind and get its place; ask for a direction and get the kind that lies there.',
        live: recordsLine,
      },
    },
    tracts: {
      'camera>association': { title: 'From the camera to the association region', what: 'Carries the camera’s report into the brain. It goes dark the moment the hand leaves the camera’s view.' },
      'seen>association': { title: 'The “in view” line', what: 'One input that is on while the camera sees the hand, with a synapse to every association neuron. It tells the brain whether the report is there at all.' },
      'joints>association': { title: 'From the joint angles to the association region', what: 'Carries the arm’s posture into the brain at every moment, in view or out of it.' },
      'commands>association': { title: 'From the commands to the association region', what: 'Carries the copy of the arm’s commands into the brain. It carries most while the arm moves.' },
      'prefrontal>association': { title: 'From the working trace to the association region', what: 'Feeds the moment before back in. With the camera dark, this is what the answer leans on.' },
      'association>place': { title: 'From the association region to the place answer', what: 'Carries the association region’s state to the answer units. Lessons change these synapses at every seen moment.' },
      'place>association': { title: 'From the place answer back to the association region', what: 'Carries the answer units’ state back. With the tract beside it, it closes the loop that settles.' },
    },
    stages: [
      { id: 'report', parts: ['camera'], title: 'What the camera reports',
        body: 'The body in the room carries a camera. It reports one thing about the hand: where it is in the room, as two numbers, x and y in metres. Each report is about a centimetre off. In the blind spot (a shadow, or anywhere beside or behind the body) it reports nothing at all: no position and no guess. What the brain knows about a hidden hand, it has to hold by itself.',
        live: seenLine },
      { id: 'code', parts: ['camera'], title: 'A position becomes activity',
        body: 'A neuron cannot hold the number 0.42. So each number is spread over 16 inputs in a row. Every input has a favourite position and lights up when the hand is near it. The hand shows as a small peak, and where the peak stands is the position. This is called a population code.',
        live: (ctx) => codeLine(ctx, ctx.regions.camera),
        draw: (ctx) => peakSvg(codeRows(ctx, 'camera', ['x', 'y'], 'm', ctx.record?.report[0]), '#66bdff') },
      { id: 'hold', parts: ['place', 'prefrontal'], title: 'The place, and what holds it', changes: true,
        body: 'These 40 units are the brain’s answer: a peak over x and a peak over y. While the camera sees the hand, the report drives the peaks to the right place. With the camera dark, this baseline brain has one thing left, the working trace: a copy of the moment before, fed back in. Nothing in it holds a peak where it stood, so the answer slides away from the hand.',
        live: placeLine },
      { id: 'move', parts: ['commands', 'joints'], title: 'How the place moves while unseen', changes: true,
        body: 'For the arm’s own hand, the brain is given a copy of every command sent to the arm, and the arm’s joint angles. From these the hand’s place follows in the dark, and this brain learns that link while it watches its own hand. For a person’s hand there is no command to read. Carrying it on takes the hand’s last seen movement, held as a velocity, and this baseline brain holds none.',
        live: (ctx) => `${ctx.own ? 'The brain follows the arm’s own hand.' : 'The brain follows a person’s hand: no command says where it goes.'} ${commandLine(ctx)}` },
      { id: 'correct', parts: ['place', 'association'], tract: 'association>place', title: 'Sight corrects it',
        body: 'At every moment the camera sees the hand, the report is a lesson. The brain has given its answer; it settles once more with its answer units nudged toward the report, and every synapse changes a little, by what its own two neurons did differently between the two settles. No lesson uses a position the camera did not give. In the shadow there are no lessons, and the gold flashes stop.',
        live: lessonLine },
      { id: 'doubt', parts: ['place'], title: 'Doubt: how sure the brain is', changes: true,
        body: 'The answer is a peak, and a peak has a width. A narrow peak says the brain is sure; a wide one says it is unsure. The ring on the table is drawn from that width: the area the brain says holds the hand nine times in ten. In this baseline brain the width is whatever the settle leaves. With the camera dark, the peak tends to spread out.',
        live: doubtLine },
      { id: 'things', parts: ['records'], title: 'What is where, around the body', provisional: true, wide: true,
        body: 'An apple does not move by itself, so the brain does not follow it moment by moment. It keeps one record for each kind of thing: a key for what the thing is, and a value for where it is. In view, the record is rewritten at every moment. Out of view it is only read: turn the camera away, and the apple’s record stays. A knock reaches the ear as a direction and a distance, which name a point; the record is rewritten to it without sight. This baseline keeps places in the room’s own coordinates and works out “behind you” from the way the body faces. In the trained module’s design, a copy of the body’s own turn shifts every held place.',
        live: recordsLine },
      { id: 'answer', parts: ['place'], title: 'The answer',
        body: 'How does a peak become two numbers? On each axis the 20 units share one vote: the more active a unit, the larger its share. The answer is the average of the units’ favourite positions, weighted by their shares. The spread of the shares is the doubt of the stage before last.',
        live: answerLine,
        draw: (ctx) => COPY.baseline.parts.place.draw(ctx) },
    ],
  },
};


// -- the trained place module

function heldLine(ctx) {
  const b = ctx.belief;
  if (!b) return 'No place is held.';
  const u = uncertainty(b);
  // held back by the sight evidence: the camera would see the hand where its movement leads, and no report came
  const asked = ctx.held ? HELD[ctx.sight] || HELD.flags
    : ctx.asked ? 'The brain was asked for its step at this moment.' : 'The brain was not asked at this moment: nothing says the place moved.';
  if (!ctx.unseen) return `The space holds the hand at <span data-place="${num(b.place[0], 3)},${num(b.place[1], 3)}">${at(b.place)}</span>, written by the camera’s report. Its area’s radius is <span data-uncertainty="${u.toFixed(4)}">${cm(u)}</span>.`;
  return `The space holds the hand at <span data-place="${num(b.place[0], 3)},${num(b.place[1], 3)}">${at(b.place)}</span>, unseen for <span data-unseen="${ctx.unseen}">${ctx.unseen} moments</span>. Its area’s radius is <span data-uncertainty="${u.toFixed(4)}">${cm(u)}</span>. ${asked}`;
}
const HELD = {
  function: 'The hand went out of view while it moved and has not come out: the program carries its place no farther than the middle of its hidden stretch and holds it there, with a radius that reaches .90 of the way back to where it was last seen.',
  flags: 'The camera would see the hand where its movement leads, and no report comes: it did not come out there. The program holds the place halfway along its hidden path, with a radius that reaches both ends, and rests it.',
};
const askedLine = (ctx) => (ctx.asked ? `The brain was asked at this moment and answered in ${ctx.settle ? ctx.settle.sweeps : 0} sweeps.` : 'The brain was not asked at this moment. It is asked only for a thing whose place may have moved: one with a command, a seen movement or a cue.');
// The sight evidence, where the library's space takes it. The sentences follow the docstring of
// `Space.observe` on the branch the wheel is built from.
const SIGHT = {
  // the guide's "Sight that does not come" (docs/space.md of the branch the wheel is built from)
  function: 'Sight that does not come is evidence. The page gives the program a function that says whether the camera would see a thing at a place: the camera’s field, the pillar and the arm’s shadow, as they stand. A thing that goes out of view while moving is looked ahead for along its seen movement: its hidden stretch ends where it would come back into view, or at the room’s edge. It is carried no farther than the middle of that stretch and waits there, and its radius reaches .90 of the way back to where it was last seen.',
  flags: 'The page also tells the program, at every step, whether the camera would see a thing at its predicted place: the camera’s field, the pillar and the arm’s shadow, as they stand. In sight for three steps in a row with no report, the thing did not come out where its movement carries it. The program puts it halfway between where it was last seen and where it was before those steps, with a radius that reaches both, and rests it.',
};
// The course setting (`course=True`), where the pack runs the module with it.
const COURSE = 'This module is run on its course: a thing that moves by itself is moved by its last seen movement times the share the brain’s keep answers, in place of the shift. The brain says when to hold it back.';
const sightLine = (ctx) => (ctx.held ? ' The hand’s place is held back in this way at this moment.' : '');
const answers = (ctx) => (ctx.regions.keep ? 'four' : 'three');
const region = (title, role, what, live = askedLine, draw = null) => ({ title, role, what, live, draw });
const axes = (name, labels, unit, color) => (ctx) => peakSvg(codeRows(ctx, name, labels, unit, null), color);

COPY.place = {
  parts: {
    place: region('The held place, as the brain is given it', 'place',
      (ctx) => `The place is held nowhere in the brain. A program beside the brain keeps it between moments, as the long-term records are kept, and this region shows the program’s place to the brain at each step: a peak over 16 tuned inputs for x and 16 for y. The brain’s own states are the hidden region and its ${answers(ctx)} answers.`,
      heldLine, axes('place', ['x', 'y'], 'm', '#3fe0cf')),
    moved: region('The arm’s command, as a copy', 'motor',
      'For the arm’s own hand, what the arm is told to do at this moment, joint by joint. It is dark for a person’s hand and for an arm at rest.',
      (ctx) => `${commandLine(ctx)} ${ctx.own ? '' : 'The brain follows a person’s hand: these inputs are dark.'}`, axes('moved', ['j1', 'j2', 'j3'], 'rad', '#ff9f4a')),
    motion: region('The last seen movement', 'visual',
      'How the thing moved while the camera saw it: the slope of the line through its last reports, a peak for x and a peak for y, with how many reports the line holds. The program fits the line; the brain is given it. It is dark until three reports in a row.'),
    unseen: region('The moments since it was seen', 'timer',
      'How long the camera has not reported the thing, over 8 tuned inputs.',
      (ctx) => (ctx.unseen ? `Unseen for ${ctx.unseen} moments (${secs(ctx.unseen, ctx.dt)}).` : 'The hand is in view: zero moments.')),
    heard: region('A cue: its direction and distance', 'auditory',
      'What the ear hears of a thing that sounds: a direction and a distance, one unit for each pair of them. It is dark while nothing sounds.'),
    felt: region('The arm’s joint readings', 'somatosensory',
      'For the arm’s own hand, the arm’s posture: one unit for each pair of joint angles. It is dark for a person’s hand.'),
    hidden: region('The hidden region', 'association',
      (ctx) => `The neurons between what the brain is given and what it answers. Every input region drives them, and they drive the ${answers(ctx)} answers.`),
    shift: region('How far the place moves in this step', 'shift',
      'The brain’s first answer: a step in x and a step in y, 32 tuned units each, up to 6 cm. The program adds the step to the place it holds. This is how a place moves while nothing is seen.',
      askedLine, axes('shift', ['dx', 'dy'], 'm', '#5cdb9e')),
    spread: region('How far off the place may be', 'doubt',
      'The brain’s second answer: how far from the truth a place predicted here is found to be, from 2 mm to 2 m. It is taught whenever the thing comes back into view, by how far off the prediction was. The ring on the table is drawn from it.',
      (ctx) => (ctx.belief ? `The radius of the area that holds the hand nine times in ten: <span>${cm(uncertainty(ctx.belief))}</span>. ${askedLine(ctx)}` : askedLine(ctx))),
    found: region('The place another sense names', 'found',
      'The brain’s third answer: the place a cue, or the arm’s own joint readings, names. It is taught at moments a thing is heard and seen at once.'),
    keep: region('How much of its seen movement a thing keeps', 'keep',
      'The brain’s fourth answer: the share of its last seen movement that a thing which moves by itself keeps in this step, from 0 to 1, over 8 tuned units. It is taught the share the camera’s reports show, at the steps a thing’s seen movement is above its noise.',
      (ctx) => `${ctx.course ? 'The program moves a thing that moves by itself by its seen movement times this share.' : 'The program moves a place by the shift; this answer is not read.'} ${askedLine(ctx)}`,
      axes('keep', ['share'], ' ', '#c7e66b')),
    records: { title: 'The places of things: what is where', role: 'hippocampus',
      what: 'Each thing has one row in the space: what it looks like, and where it is. A thing in view is written by the camera’s report. A thing at rest out of view costs nothing: its row stays as it is, and the brain is not asked. A cue rewrites a row without sight.',
      live: recordsLine },
  },
  tracts: {},
  // The stages are the library guide's "How a position travels" (docs/space.md of the branch
  // the module comes from), word for word but for one phrase: where the guide says the brain
  // "settles on" what the regions hold, the card says it "reads" it. The third stage adds the
  // course setting where the pack runs the module with it (COURSE above), and the fourth the
  // sight evidence where the pack's library takes it (SIGHT above).
  stages: [
    { id: 'report', parts: ['place'], title: 'The camera’s report',
      body: 'A report is a position in the plane. The program writes it into the thing’s place. The place region shows that place to the brain as a peak on each axis: the units within two spacings of the position are lit, five at most, and the rest are silent. A thing that is not seen changes nothing here: there is no “nothing seen” pattern.',
      live: seenLine, draw: axes('place', ['x', 'y'], 'm', '#3fe0cf') },
    { id: 'hold', parts: ['place'], title: 'The place is held',
      body: 'The program keeps the place between moments. With no report, no command, no seen movement and no cue it is not touched, and the brain is not asked. A thing at rest in view takes the mean of its reports, which is sharper than one report.',
      live: heldLine },
    { id: 'move', parts: ['shift', 'motion'], title: 'Movement while unseen',
      body: 'The brain reads what the regions hold and its shift answers how far the place moves in this step. For the arm’s own end the moved region holds the copy of the command. For a thing that moves by itself the motion region holds its last seen movement: the slope of the line through its reports in a row. The program adds the shift to the place.',
      also: (ctx) => (ctx.course ? COURSE : ''),
      live: askedLine, draw: axes('shift', ['dx', 'dy'], 'm', '#5cdb9e') },
    { id: 'correct', parts: ['place'], title: 'Correction by sight',
      body: 'When the thing is seen again its report writes the place. The lessons happen only then: the movement the reports show teaches shift, and the distance from the predicted place to the report teaches spread. A lesson is made of six reports in a row, so it lands a few moments after them.',
      also: (ctx) => (ctx.sight ? SIGHT[ctx.sight] || SIGHT.flags : ''),
      live: (ctx) => lessonLine(ctx) + sightLine(ctx) },
    { id: 'doubt', parts: ['spread'], title: 'The uncertainty',
      body: 'Spread is a belief over distances. The program reads the distance that holds .90 of the belief, takes out the camera’s own noise, and reports a circle of that radius around the place. The circle grows while the thing is unseen and shrinks to the camera’s noise when it is seen.',
      live: doubtLine },
    { id: 'things', parts: ['records'], title: 'Things that stay put', wide: true,
      body: 'Every thing has a row of its own in the program: what it looks like, and its place. A thing with a look of its own that rests is also filed in a long-term memory: the key is a code of what it looks like and the value is its place and the number of reports the place is a mean of. The record is revised as the mean sharpens and when the thing is seen elsewhere. The places are the room’s own, so a turn of the camera changes what is seen and not the stored places; the small map turns them for display.',
      live: recordsLine },
    { id: 'cue', parts: ['heard', 'found'], title: 'A cue from another sense',
      body: 'A cue is a direction and a distance from the ear. It lights one neighbourhood of the heard sheet, the brain’s found answers the place it names, and the program writes that place. The same holds for the arm’s joint readings in felt.',
      live: recordsLine },
    { id: 'answer', parts: ['place'], title: 'The answer',
      body: 'The program gives each place and its radius. Asked for a kind, it answers with its places; asked for a place, it answers with the kind held there. The glow on the table is the hand’s place, and the ring its radius.',
      live: heldLine },
  ],
};

const ROLE = {
  visual: ['plays the role of the visual cortex', '#66bdff'],
  somatosensory: ['plays the role of the somatosensory strip, the sense of the body’s own posture', '#c7cc80'],
  motor: ['plays the role of the motor strip and the copy of its commands', '#ff9f4a'],
  association: ['plays the role of association cortex', '#8f9eff'],
  prefrontal: ['plays the role of prefrontal working memory', '#a88ffa'],
  place: ['plays the role of the parietal and entorhinal map', '#3fe0cf'],
  auditory: ['plays the role of the auditory cortex', '#f28cc7'],
  hippocampus: ['plays the role of the hippocampus', '#ffcc6b'],
  timer: ['plays the role of a timer, drawn where the cerebellum sits', '#9eb8db'],
  shift: ['plays the role of path integration: the step that moves a place on the map', '#5cdb9e'],
  doubt: ['plays the role of a confidence estimate', '#a88ffa'],
  found: ['plays the role of the map’s entry from the other senses', '#f28cc7'],
  keep: ['plays the role of a brake on the carried movement', '#c7e66b'],
};

/** What the pack's module is run with, known once the brain has described itself: on its
 *  course, the third stage rings the keep answer in place of the shift. */
export function configure(kind, { course = false } = {}) {
  const move = COPY[kind]?.stages.find((s) => s.id === 'move');
  if (!move || kind !== 'place') return;
  const answer = course && COPY.place.parts.keep ? 'keep' : 'shift';
  move.parts = [answer, 'motion'];
  move.draw = answer === 'keep' ? axes('keep', ['share'], ' ', '#c7e66b') : axes('shift', ['dx', 'dy'], 'm', '#5cdb9e');
}

export const copyFor = (kind) => COPY[kind] || COPY.baseline;
export const stagesFor = (kind) => copyFor(kind).stages;

/** A part's card, as HTML. `unit`: a line about the unit under the pointer, if any. */
export function partCard(kind, id, ctx, unit = '') {
  const part = copyFor(kind).parts[id];
  if (!part) return '';
  const [role, color] = ROLE[part.role] || ['is a population of this brain', '#8d97b2'];
  const stage = copyFor(kind).stages.findIndex((s) => s.parts[0] === id);
  return `<div style="--c:${color}" data-part="${id}"><h3>${part.title}</h3><p class="role">${role}</p><p>${typeof part.what === 'function' ? part.what(ctx) : part.what}</p>`
    + (part.more ? `<p>${part.more}</p>` : '')
    + (part.draw ? part.draw(ctx) : '')
    + `<p class="live"><b>At this moment</b>${part.live(ctx)}</p>`
    + (unit ? `<p class="unit">${unit}</p>` : '')
    + (part.provisional ? `<p class="mark">${PROVISIONAL}</p>` : '')
    + (stage >= 0 ? `<p class="unit">Stage ${stage + 1} of ${copyFor(kind).stages.length} on the path of a position.</p>` : '') + '</div>';
}

/** A tract's card. `flow`: its live numbers ({ signal, synapses, excite, inhibit }). */
export function tractCard(kind, key, flow) {
  const tract = copyFor(kind).tracts[key] || { title: `Synapses from ${key.replace('>', ' to ')}`, what: 'A bundle of synapses between two populations of this brain.' };
  const quiet = flow.signal < 1e-3;
  return `<div style="--c:#ff9e48" data-tract="${key}"><h3>${tract.title}</h3><p class="role">a fibre tract: ${flow.synapses.toLocaleString('en')} synapses, ${flow.excite.toLocaleString('en')} that excite and ${flow.inhibit.toLocaleString('en')} that inhibit</p><p>${tract.what}</p>`
    + `<p class="live"><b>At this moment</b>${quiet ? 'Silent: the neurons it starts from are at rest.' : `It carries a signal of <span>${flow.signal.toFixed(1)}</span>: every synapse’s strength times the activity of the neuron it starts from, added up. The brighter the bundle, the more it carries.`}</p></div>`;
}

/** A stage of the path, as HTML, with its place in the order. */
export function stageCard(kind, index, ctx) {
  const stages = copyFor(kind).stages, stage = stages[index];
  const part = copyFor(kind).parts[stage.parts[0]];
  const [role, color] = ROLE[part.role] || ['', '#8d97b2'];
  return `<div style="--c:${color}" data-stage="${stage.id}"><p class="kicker">The path of a position · ${index + 1} of ${stages.length}</p><h3>${stage.title}</h3>`
    + `<p class="role">${part.title}: ${role}</p><p>${stage.body}</p>`
    + (stage.also && stage.also(ctx) ? `<p>${stage.also(ctx)}</p>` : '')
    + (stage.draw ? stage.draw(ctx) : '')
    + `<p class="live"><b>At this moment</b>${stage.live(ctx)}</p>`
    + (stage.changes ? `<p class="mark">${MARK}</p>` : '') + (stage.provisional ? `<p class="mark">${PROVISIONAL}</p>` : '') + '</div>';
}
