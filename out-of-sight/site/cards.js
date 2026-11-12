// What every part of the brain says about itself, and the path of a position through the brain.
//
// A card holds the part's name, the role it plays, one or two plain sentences on what it does,
// and what it is doing at this moment, written from the brain's live state. The same texts are
// reachable in order as the eight stages of "follow the position". Every sentence describes
// what the brain on this page does. COPY is keyed by the brain's kind: `baseline` is the plain
// composed brain; a stage whose `changes` is set is one the trained place module does another
// way, and its card says so.

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
  return `Width: ${cm(b.sd[0])} in x, ${cm(b.sd[1])} in y. Area at nine in ten: <span>${area(b.area)}</span>.${cover}`;
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

const ROLE = {
  visual: ['plays the role of the visual cortex', '#66bdff'],
  somatosensory: ['plays the role of the somatosensory strip, the sense of the body’s own posture', '#c7cc80'],
  motor: ['plays the role of the motor strip and the copy of its commands', '#ff9f4a'],
  association: ['plays the role of association cortex', '#8f9eff'],
  prefrontal: ['plays the role of prefrontal working memory', '#a88ffa'],
  place: ['plays the role of the parietal and entorhinal map', '#3fe0cf'],
  auditory: ['plays the role of the auditory cortex', '#f28cc7'],
  hippocampus: ['plays the role of the hippocampus', '#ffcc6b'],
};

export const copyFor = (kind) => COPY[kind] || COPY.baseline;
export const stagesFor = (kind) => copyFor(kind).stages;

/** A part's card, as HTML. `unit`: a line about the unit under the pointer, if any. */
export function partCard(kind, id, ctx, unit = '') {
  const part = copyFor(kind).parts[id];
  if (!part) return '';
  const [role, color] = ROLE[part.role] || ['is a population of this brain', '#8d97b2'];
  const stage = copyFor(kind).stages.findIndex((s) => s.parts[0] === id);
  return `<div style="--c:${color}" data-part="${id}"><h3>${part.title}</h3><p class="role">${role}</p><p>${part.what}</p>`
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
    + (stage.draw ? stage.draw(ctx) : '')
    + `<p class="live"><b>At this moment</b>${stage.live(ctx)}</p>`
    + (stage.changes ? `<p class="mark">${MARK}</p>` : '') + (stage.provisional ? `<p class="mark">${PROVISIONAL}</p>` : '') + '</div>';
}
