"""A census of the compiled larva net, read back from the payload the page runs: cells by
role, synapses and connections, the cells the data leaves without a synapse, the sign of
every sender, and the critical gain of the unit against the selected and the demo gain.
Writes receipts/larva_census.json and web/data/larva_census.json.

    python tools/larva_census.py
"""
from __future__ import annotations

import base64
import collections
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "web" / "data" / "larva_brain.json"


def decode(s: str, dtype: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(s), dtype=dtype)


def largest_eigenvalue(n: int, post: np.ndarray, pre: np.ndarray, w: np.ndarray, iterations: int = 20000, tol: float = 1e-12):
    """Power iteration on the post-by-pre matrix; every weight is positive here, so the
    iteration converges to the largest (Perron) eigenvalue."""
    v = np.full(n, 1.0 / np.sqrt(n))
    lam = 0.0
    for k in range(iterations):
        u = np.bincount(post, weights=w * v[pre], minlength=n)
        norm = float(np.linalg.norm(u))
        if norm == 0.0:
            return 0.0, k, 0.0
        u /= norm
        new = float(v @ np.bincount(post, weights=w * v[pre], minlength=n))
        done = abs(new - lam) <= tol * max(1.0, abs(new))
        lam, v = new, u
        if done and k > 10:
            return lam, k, 0.0
    residual = float(np.linalg.norm(np.bincount(post, weights=w * v[pre], minlength=n) - lam * v))
    return lam, iterations, residual


def main() -> None:
    p = json.loads(PAYLOAD.read_text())
    n, a = int(p["n"]), p["arrays"]
    row_ptr = decode(a["row_ptr"], "<i4"); pre = decode(a["pre"], "<i4"); count = decode(a["count"], "<u2").astype(float)
    sign = decode(a["sign"], "i1" if a.get("sign_dtype") == "int8" else "<f8").astype(float)  # one sign per connection, the sender's
    indeg = np.diff(row_ptr); outdeg = np.bincount(pre, minlength=n); post = np.repeat(np.arange(n), indeg)
    touched = (indeg > 0) | (outdeg > 0)
    role = np.array(p["role"]); kind = np.array(p["kind"])
    by_role = collections.Counter(role.tolist()); silent_by_role = collections.Counter(role[~touched].tolist())
    lam, iterations, residual = largest_eigenvalue(n, post, pre, count * sign)
    slope = float(p["model"]["slope"]); critical = 1.0 / (lam * slope / 2.0) if lam > 0 else None
    out = {
        "payload": str(PAYLOAD.relative_to(ROOT)), "source": p["source"], "format": p["format"],
        "tables_digest": p["tables_digest"], "connectome_digest": p["connectome_digest"], "protocol_digest": p["protocol_digest"],
        "cells": n, "connections": int(len(pre)), "synapses": int(count.sum()),
        "by_role": {k: int(v) for k, v in sorted(by_role.items())},
        "typed_cells": int((kind != "untyped").sum()), "untyped_cells": int((kind == "untyped").sum()),
        "cells_with_a_synapse": int(touched.sum()), "cells_without_a_synapse": int((~touched).sum()),
        "without_a_synapse_by_role": {k: int(v) for k, v in sorted(silent_by_role.items())},
        "signs": {str(int(k)): int(v) for k, v in collections.Counter(sign.tolist()).items()},
        "weight_is_gain_times_count": bool(np.allclose(decode(a["weight"], "<f8"), float(p["gain"]) * count * sign)),
        "unit": p["unit"], "model": p["model"],
        "largest_eigenvalue": lam, "power_iterations": iterations, "power_residual": residual,
        "critical_gain": critical, "selected_gain": p["selected_gain"], "gain": p["gain"], "demo_gain_factor": p["demo_gain_factor"],
        "selected_over_critical": (p["selected_gain"] / critical) if critical else None, "gain_over_critical": (p["gain"] / critical) if critical else None,
        "critical_gain_rule": "1 / (largest eigenvalue of the signed synapse-count matrix x slope / 2); below it a push decays, above it the net ignites",
    }
    text = json.dumps(out, indent=1)
    (ROOT / "receipts" / "larva_census.json").write_text(text); (ROOT / "web" / "data" / "larva_census.json").write_text(text)
    print(json.dumps({k: out[k] for k in ("cells", "connections", "synapses", "by_role", "cells_without_a_synapse", "without_a_synapse_by_role", "signs", "weight_is_gain_times_count", "largest_eigenvalue", "power_iterations", "power_residual", "critical_gain", "selected_over_critical", "gain_over_critical")}, indent=1))


if __name__ == "__main__":
    main()
