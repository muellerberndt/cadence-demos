// Display only: map actual effective-weight changes to their receiving cells.
// Each row scales by its own former incoming mass, never by another row or the
// brightest cell. This is a view of plasticity, not activity or a learning rule.
export function learningView(rowPtr, beforeWeights, afterWeights, { threshold = 1e-10, floor = 1e-9, gain = 40 } = {}) {
  if (!rowPtr || rowPtr.length < 1 || !beforeWeights || !afterWeights || beforeWeights.length !== afterWeights.length) throw new RangeError("invalid weight-change arrays");
  if (!Number.isFinite(threshold) || threshold < 0 || !Number.isFinite(floor) || floor <= 0 || !Number.isFinite(gain) || gain < 0) throw new RangeError("invalid weight-change display scale");
  const n = rowPtr.length - 1, edges = beforeWeights.length;
  if (rowPtr[0] !== 0 || rowPtr[n] !== edges) throw new RangeError("CSR rows must cover every weight");
  for (let i = 0; i <= n; i++) if (!Number.isInteger(rowPtr[i]) || rowPtr[i] < 0 || rowPtr[i] > edges || (i && rowPtr[i] < rowPtr[i - 1])) throw new RangeError("invalid CSR row boundary");
  const levels = new Float32Array(n);
  let changedEdges = 0, changedCells = 0;
  for (let i = 0; i < n; i++) {
    let mass = 0, change = 0, count = 0;
    for (let e = rowPtr[i]; e < rowPtr[i + 1]; e++) {
      const before = beforeWeights[e], after = afterWeights[e];
      if (!Number.isFinite(before) || !Number.isFinite(after)) throw new RangeError("display weights must be finite");
      mass += Math.abs(before);
      const delta = Math.abs(after - before);
      if (delta > threshold) { change += delta; count++; }
    }
    if (count) {
      levels[i] = Math.sqrt(Math.min(1, gain * (change / (mass + floor))));
      changedEdges += count; changedCells++;
    }
  }
  return { levels, changedEdges, changedCells };
}
