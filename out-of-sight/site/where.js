// Plain words for where a thing is around the body, and the two questions the page asks the
// brain: "where is the apple?" and "what is behind me?".

export const LABEL = { hand: 'hand', cup: 'cup', apple: 'apple', bread: 'slice of bread' };
export const the = (name) => `the ${LABEL[name] || name}`;
export const metres = (d) => `${d.toFixed(1)} m`;

/** A bearing from the way the body faces (0 ahead, positive to the left, pi behind), in words. */
export function phrase(bearing) {
  const degrees = (Math.abs(bearing) * 180) / Math.PI, side = bearing > 0 ? 'left' : 'right';
  if (degrees < 20) return 'in front of you';
  if (degrees < 70) return `in front of you, to the ${side}`;
  if (degrees < 110) return `to your ${side}`;
  if (degrees < 160) return `behind you, to the ${side}`;
  return 'behind you';
}

/** "0.8 m away, behind you, to the left": a place as the body has it. */
export const placed = (rel) => `${metres(rel.distance)} away, ${phrase(rel.bearing)}`;

const ago = (moments, dt) => `${(moments * dt).toFixed(0)} s ago`;

/** The answer to "where is this kind of thing?" as one sentence. `rel`: the record's place
 *  around the body; `record`: how the record came ({ from, unseen }); `seen`: in view at this moment. */
export function whereSentence(name, rel, record, seen, dt) {
  if (!rel) return `The brain holds no record of ${the(name)}: the camera has not seen it.`;
  // marked gone: the camera sees the place the record holds, and the thing is not there
  if (record.gone && !seen) return `${`${the(name)}`.replace(/^t/, 'T')} is not where the brain left it: the camera sees that place, and ${the(name)} is not there. The brain does not know where it is.`;
  const how = seen ? 'The camera sees it.' : record.from === 'heard' ? `It was heard ${ago(record.unseen || 0, dt)}.` : `The camera last saw it ${ago(record.unseen || 0, dt)}.`;
  const lead = `${the(name)}`.replace(/^t/, 'T');
  return `${lead} is ${placed(rel)}. ${how}`;
}

/** The answer to "what is that way?" as one sentence. */
export function whatSentence(bearing, name, rel) {
  const lead = phrase(bearing).replace(/^./, (ch) => ch.toUpperCase());
  if (!name) return `${lead}: nothing the brain remembers.`;
  return `${lead}: ${the(name)}, ${metres(rel.distance)} away.`;
}

/** The answer to "where is the hand?": the brain's own place answer, around the body. */
export function handSentence(rel, unseen, dt, gone = false) {
  if (!rel) return 'The brain has given no answer for the hand.';
  if (gone) return 'The hand is not where the brain left it: the camera sees that place, and no hand is there. The brain does not know where the hand is.';
  const how = unseen ? `The camera has not seen it for ${(unseen * dt).toFixed(1)} s.` : 'The camera sees it.';
  return `The brain says the hand is ${placed(rel)}. ${how}`;
}
