"""A narrow mathematical obstruction for the one-patch flat memory control.

No learning or empirical architecture comparison is performed. This does not
cover multi-patch acyclic graphs, observers, or changing external inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def projected(state, gradient):
    return abs(state - max(-1.0, min(1.0, state - gradient)))


def witness(alpha=0.01, tolerance=1e-6, bit_threshold=0.25):
    if not (alpha > 0 and 0 <= tolerance < 1 and 0 < bit_threshold <= 1):
        raise ValueError(
            "Require alpha>0, tolerance in[0,1), and bit threshold in(0,1]."
        )
    if not all(math.isfinite(v) for v in (alpha, tolerance, bit_threshold)):
        raise ValueError("Finite constants required")
    width = 2 * tolerance / (1 + alpha)
    return {
        "schema": "flat-blank-obstruction/1",
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "state_prior": alpha,
        "qualification_tolerance": tolerance,
        "bit_threshold": bit_threshold,
        "qualified_band_width_upper_bound": width,
        "required_opposed_response_separation": 2 * bit_threshold,
        "opposed_qualified_bit_responses_impossible": width < 2 * bit_threshold,
        "assumptions": [
            "One free scalar state x in[-1,1], fixed parameters, no output clamp, and the unchanged quadratic state prior.",
            "The flat control reads only cue and visible presence abs(cue). On every blank both inputs are zero, so p=tanh(b) is independent of retained state and earlier cue history.",
            "Both opposed histories must be answered by qualified free states of this same fixed model and identical blank input.",
        ],
        "derivation": [
            "For constant p=tanh(b), E(x)=0.5*(x-p)^2+0.5*alpha*x^2; E'(x)=(1+alpha)*x-p and E''=1+alpha>0.",
            "The unique minimizer is m=p/(1+alpha), inside the state interval. Parameters need not have been acquired by any particular training procedure.",
            "Qualification uses r=|x-clip(x-E'(x),-1,1)|. Since x-E'(x)=p-alpha*x and |p|<=1, upper clipping implies x<0 and r=1-x>1; lower clipping implies x>0 and r=1+x>1.",
            "For tolerance<1, a qualified state therefore uses the unclipped branch: r=(1+alpha)*|x-m|<=tolerance.",
            "Any two qualified responses differ by at most2*tolerance/(1+alpha), regardless of their initial retained states. Opposite signed responses of magnitude at least bit_threshold require separation at least2*bit_threshold.",
        ],
        "scope": "A one-patch fixed-parameter blank-input obstruction only. It is not a theorem that all acyclic coupled graphs lack memory, not residual-observer advantage, and not a contemporary matched performance comparison. Historical flat controls remain historical. A cyclic witness, if separately verified, establishes only a narrow temporal representation contrast under these declared conditions.",
        "training_performed": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = witness()
    with args.out.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
