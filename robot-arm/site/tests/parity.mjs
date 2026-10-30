// Parity of site/sim.js with the Python cell (cadence-arm/arm2) on recorded trials of the real brain.
//   node tests/parity.mjs <mujoco.js> <cell_phys.mjb> <trial.json> [...]
// Per decision from the recorded state: the observation, the reflex target and the state after
// 100 physics steps; then the whole trial replayed open loop from its start (the recorded
// commands), which must grasp and place on the same decisions.
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { Cell } from '../sim.js';

const [mjPath, mjbPath, ...trials] = process.argv.slice(2);
const loadMujoco = (await import(pathToFileURL(resolve(mjPath)).href)).default;
const mujoco = await loadMujoco();
const vfs = new mujoco.MjVFS();
vfs.addBuffer('cell.mjb', new Uint8Array(readFileSync(mjbPath)));
const model = mujoco.MjModel.from_binary_path('cell.mjb', vfs);
const maxdiff = (a, b) => a.reduce((m, v, i) => Math.max(m, Math.abs(v - b[i])), 0);
let failed = false;
for (const path of trials) {
  const ref = JSON.parse(readFileSync(path, 'utf8'));
  const cell = new Cell(mujoco, model);
  cell.moveBin(ref.bin, ...ref.bin_xy);
  cell.setOrder(ref.bin);
  cell.placeBlock(...ref.block_xy);
  const x0 = cell.observe();
  let worst = { x: maxdiff(x0, ref.rows[0].x), target: 0, qTarget: 0, after: 0 }, events = 0;
  for (const row of ref.rows) {
    cell.setState(row.before);
    worst.x = Math.max(worst.x, maxdiff(cell.observe(), row.x));
    const out = cell.execute(row.answer);
    worst.target = Math.max(worst.target, maxdiff(out.target, row.target));
    worst.qTarget = Math.max(worst.qTarget, maxdiff(out.qTarget, row.q_target));
    worst.after = Math.max(worst.after, maxdiff(Array.from(cell.data.qpos), row.after.qpos));
    if ((out.event || null) !== (row.event || null)) events += 1;
  }
  // open loop from the start: the recorded commands, the cell stepping exactly as Python's does
  // (after mj_step the site positions lag the state by one physics step in both)
  const replay = new Cell(mujoco, model);
  replay.moveBin(ref.bin, ...ref.bin_xy); replay.setOrder(ref.bin); replay.placeBlock(...ref.block_xy);
  const seen = [];
  const drift = { x: 0, arm: 0, block: 0, x_first10: 0 };
  for (const row of ref.rows) {
    const dx = maxdiff(replay.observe(), row.x);
    drift.x = Math.max(drift.x, dx);
    if (row.d < 10) drift.x_first10 = Math.max(drift.x_first10, dx);
    const out = replay.execute(row.answer);
    if (out.event) seen.push(`${row.d}:${out.event}`);
    const q = Array.from(replay.data.qpos);
    drift.arm = Math.max(drift.arm, maxdiff(q.slice(0, 9), row.after.qpos.slice(0, 9)));
    // Python respawns a fresh block after a placement; the site leaves the placed block in its bin
    if (!(row.event || '').startsWith('placed')) drift.block = Math.max(drift.block, maxdiff(q.slice(9, 12), row.after.qpos.slice(9, 12)));
  }
  const want = ref.rows.filter((r) => r.event).map((r) => `${r.d}:${r.event}`);
  const ok = seen.join() === want.join() && drift.x_first10 < 1e-6 && drift.arm < 0.02 && drift.block < 0.01;
  failed ||= !ok;
  console.log(JSON.stringify({ trial: path.split('/').pop(), decisions: ref.rows.length, worst, event_mismatches: events,
    open_loop: { seen, want, drift }, ok }));
}
process.exit(failed ? 1 : 0);
