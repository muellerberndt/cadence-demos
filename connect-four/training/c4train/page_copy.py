"""A page copy of a Connect Four brain: the optimizer's running moments zeroed (what a fresh
optimizer starts from) and the synapses' efficacies and signs stored in float32 (the precision
the brain was trained in); biases and settings kept. The loader reads them back in float64. Lessons in the page start a new optimizer history.

    python -m c4train.page_copy IN.npz OUT.npz
"""
import sys

import numpy as np

ZEROED = ("velocity", "second_moment", "velocity_bias", "second_moment_bias")
SINGLE = ("efficacy", "sign")  # stored in float32, the precision the brain was trained in


def main(src: str, dst: str) -> None:
    z = np.load(src, allow_pickle=False)
    arrays = {k: (np.zeros_like(z[k]) if k in ZEROED else z[k]) for k in z.files}
    for k in SINGLE:
        arrays[k] = arrays[k].astype(np.float32)
    np.savez_compressed(dst, **arrays)


if __name__ == "__main__":
    main(*sys.argv[1:3])
