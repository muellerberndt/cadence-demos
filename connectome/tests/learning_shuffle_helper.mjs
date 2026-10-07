import { createHash } from "node:crypto";

function digest(brain) {
  const hash = createHash("sha256");
  for (const name of ["rowPtr", "pre", "count", "sign", "efficacy", "gainPre", "w"]) {
    const a = brain[name];
    hash.update(`${name}:${a ? a.constructor.name + ":" + a.length : "absent"}\n`);
    if (a) hash.update(Buffer.from(a.buffer, a.byteOffset, a.byteLength));
  }
  return hash.digest("hex");
}

/** A simple directed degree-preserving null. Swap the receivers of two source
 * contacts, rejecting self contacts and parallel contacts. Each original sender
 * keeps its count/sign/efficacy/gain/weight bundle; receivers' weighted input mass
 * and sign mixture may change. This is a finite edge-swap chain, not a claim of a
 * uniform sample from all graphs with those degrees. Use before any learning. */
export function shuffleContacts(brain, seed, attemptsPerEdge = 20) {
  if (!Number.isSafeInteger(seed) || seed < 0 || seed > 0xffffffff || !Number.isSafeInteger(attemptsPerEdge) || attemptsPerEdge < 0) throw new RangeError("invalid shuffle seed or budget");
  brain.enableLearning();
  if (brain.lessons || brain.mass0 || brain.contrastUpdates) throw new Error("shuffle before learning");
  const n = brain.n, E = brain.edges, keys = new Set();
  for (let e = 0; e < E; e++) {
    const key = brain.pre[e] * n + brain.post[e];
    if (brain.pre[e] === brain.post[e] || keys.has(key)) throw new Error("shuffle needs a simple directed graph without self contacts");
    keys.add(key);
  }
  const source = digest(brain), originalPost = brain.post.slice();
  const origin = Int32Array.from({ length: E }, (_, i) => i);
  const bundles = [brain.pre, brain.count, brain.sign, brain.efficacy, brain.efficacy0, brain.gainPre, brain.w, origin].filter(Boolean);
  let state = seed >>> 0, accepted = 0;
  const random = () => { state = (Math.imul(state, 1664525) + 1013904223) >>> 0; return state / 4294967296; };
  const attempts = attemptsPerEdge * E;
  for (let k = 0; k < attempts; k++) {
    const e = Math.floor(random() * E), f = Math.floor(random() * E);
    const a = brain.pre[e], b = brain.pre[f], x = brain.post[e], y = brain.post[f];
    if (a === b || x === y || b === x || a === y) continue;
    const nextE = b * n + x, nextF = a * n + y;
    if (keys.has(nextE) || keys.has(nextF)) continue;
    keys.delete(a * n + x); keys.delete(b * n + y);
    keys.add(nextE); keys.add(nextF);
    for (const values of bundles) { const old = values[e]; values[e] = values[f]; values[f] = old; }
    accepted++;
  }
  const contact = new Map();
  for (let e = 0; e < E; e++) contact.set(brain.pre[e] * n + brain.post[e], e);
  brain.reverse.fill(-1);
  let reassigned = 0;
  for (let e = 0; e < E; e++) {
    brain.reverse[e] = contact.get(brain.post[e] * n + brain.pre[e]) ?? -1;
    if (brain.post[e] !== originalPost[origin[e]]) reassigned++;
  }
  return { algorithm: "simple-directed-contact-swaps/1", seed, attempts, accepted_swaps: accepted,
    reassigned_contacts: reassigned, source_sha256: source, shuffled_sha256: digest(brain),
    preserved: "exact per-neuron in/out contact degree; each sender's count/sign/efficacy/gain/weight contact bundles",
    changed: "receiving partner, input weight sums, reciprocal-pair membership; finite swap chain is not certified uniform" };
}
