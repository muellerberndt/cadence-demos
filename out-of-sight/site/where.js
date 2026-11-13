// Plain words for where a thing is around the body, and the two questions the page asks the
// map: "where is the apple?" and "what is there?".

export const LABEL = { hand: 'hand', own: 'arm’s own hand', apple: 'apple', bread: 'slice of bread' };
export const the = (name) => `the ${LABEL[name] || name}`;
const The = (name) => the(name).replace(/^t/, 'T');
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

const ago = (moments, dt) => `${Math.max(0, Math.round(moments * dt))} s ago`;

/** How the map came to hold a thing where it holds it, in a few words. */
export function how(entry, seen, dt) {
  if (!entry) return '';
  if (seen) return 'The camera sees it.';
  switch (entry.state) {
    case 'seen': return 'The camera sees it.';
    case 'felt': return 'The arm’s joint readings place it.';
    case 'heard': return 'A sound named the place.';
    case 'near': return `It vanished from where it was seen ${ago(entry.since, dt)}: the map holds it near there, out of sight.`;
    case 'held': return `The camera last saw it there ${ago(entry.since, dt)}.`;
    default: return '';
  }
}

/** The answer to "where is this thing?" as one sentence: from the places the map settled on
 *  with the thing's kind as its cue. */
export function whereSentence(name, rel, entry, seen, dt, count = 1) {
  if (entry?.state === 'not known where') return `The map holds ${the(name)} with no place: its place was seen empty, with no place out of sight near it. Not known where.`;
  if (!rel) return `The map holds no ${LABEL[name] || name}: no sense has reported one.`;
  const more = count > 1 ? ` The map holds ${count} places for it.` : '';
  return `${The(name)} is ${placed(rel)}. ${how(entry, seen, dt)}${more}`;
}

/** The answer to "what is there?" as one sentence: from the code the map settled on with the
 *  place as its cue. */
export function whatSentence(name, rel) {
  const lead = `${metres(rel.distance)} away, ${phrase(rel.bearing)}`;
  if (!name) return `${lead.replace(/^./, (c) => c.toUpperCase())}: nothing, as the map holds it.`;
  return `${lead.replace(/^./, (c) => c.toUpperCase())}: ${the(name)}, as the map holds it.`;
}
