"""Cadence robot arena: robots assembled from parts, each with one continuing Cadence brain
wired to every motor, bootstrapped in an accelerated nursery and ranked in battle royales.

A robot never resets: the brain that walks in the nursery is the brain that fights, and it
learns from every fight it survives or loses, within the arousal law of ``Brain.live``.
"""

import os as _os

# small dense brains settle faster on one BLAS thread; parallel robots are separate processes
for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    _os.environ.setdefault(_name, "1")

from .parts import Blueprint, blueprint_from_dict, stock_designs
from .world import DT, Arena, Robot
from .senses import observe, input_count

__all__ = [
    "Arena",
    "Blueprint",
    "DT",
    "Robot",
    "blueprint_from_dict",
    "input_count",
    "observe",
    "stock_designs",
]
