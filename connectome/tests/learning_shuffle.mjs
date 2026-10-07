import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { SettlingBrain } from "../web/brain.js";
import { shuffleContacts } from "./learning_shuffle_helper.mjs";

const load = file => new SettlingBrain(JSON.parse(readFileSync(new URL(`../web/data/${file}`, import.meta.url), "utf8")));
const degrees = b => {
  const incoming = new Int32Array(b.n), outgoing = new Int32Array(b.n);
  for (let e = 0; e < b.edges; e++) { incoming[b.post[e]]++; outgoing[b.pre[e]]++; }
  return { incoming, outgoing };
};
const bundles = b => Array.from({ length: b.edges }, (_, e) =>
  JSON.stringify([b.pre[e], b.count?.[e], b.sign?.[e], b.efficacy[e], b.efficacy0?.[e], b.gainPre[e], b.w[e]])).sort();

let swaps = 0;
for (const [file, seed] of [["brain_oculomotor.json", 1], ["brain_oculomotor.json", 2], ["brain_oculomotor.json", 3], ["brain.json", 1]]) {
  const b = load(file); b.enableLearning();
  const before = { degrees: degrees(b), bundles: bundles(b), rowPtr: b.rowPtr.slice(), post: b.post.slice() };
  const receipt = shuffleContacts(b, seed);
  assert.deepEqual(degrees(b), before.degrees, "both contact degree sequences are exact");
  assert.deepEqual(bundles(b), before.bundles, "sender signs/counts/efficacies/gains stay coupled to their original contact");
  assert.deepEqual(b.rowPtr, before.rowPtr); assert.deepEqual(b.post, before.post);
  const keys = new Set();
  for (let e = 0; e < b.edges; e++) {
    assert.notEqual(b.pre[e], b.post[e], "no self contacts");
    const key = `${b.pre[e]}:${b.post[e]}`;
    assert.ok(!keys.has(key), "no parallel contacts"); keys.add(key);
    if (b.reverse[e] >= 0) {
      const r = b.reverse[e];
      assert.equal(b.reverse[r], e, "reverse relation remains an involution");
      assert.equal(b.pre[r], b.post[e]); assert.equal(b.post[r], b.pre[e]);
    }
  }
  assert.ok(receipt.accepted_swaps > b.edges);
  assert.ok(receipt.reassigned_contacts > .9 * b.edges);
  assert.notEqual(receipt.source_sha256, receipt.shuffled_sha256);
  const repeat = load(file);
  assert.deepEqual(shuffleContacts(repeat, seed), receipt, "seed and source reproduce the graph and provenance");
  swaps += receipt.accepted_swaps;
}
const malformed = load("brain_oculomotor.json"); malformed.enableLearning();
malformed.pre[0] = malformed.post[0];
assert.throws(() => shuffleContacts(malformed, 1), /simple directed graph/);
const duplicate = load("brain_oculomotor.json"); duplicate.enableLearning();
const row = Array.from({ length: duplicate.n }, (_, i) => i).find(i => duplicate.rowPtr[i + 1] - duplicate.rowPtr[i] >= 2);
duplicate.pre[duplicate.rowPtr[row] + 1] = duplicate.pre[duplicate.rowPtr[row]];
assert.throws(() => shuffleContacts(duplicate, 1), /simple directed graph/);
console.log(`learning shuffle ok: both degrees and sender bundles exact; no duplicate/self contacts; ${swaps} accepted swaps across four seeded checks`);
