"""Sensory and output boundaries, with shape and sample validation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Integral

from ._validation import integer, number
from .column import Population


@dataclass(frozen=True, slots=True, eq=False)
class Input:
    """A named sensor boundary; ``shape`` describes externally clamped data."""

    name: str
    shape: tuple[int, ...]

    @property
    def size(self):
        """Number of scalar sensor samples, independent of processing capacity."""
        return math.prod(self.shape)


@dataclass(frozen=True, slots=True, eq=False)
class Output:
    """A shaped selection of settled patch values, without a separate policy head."""

    name: str
    shape: tuple[int, ...]
    reads: Population
    indices: tuple[int, ...]


def _shape(shape):
    if isinstance(shape, Integral):
        shape = (shape,)
    if not isinstance(shape, (tuple, list)) or len(shape) > 8:
        raise ValueError("shape must have at most eight positive dimensions")
    return tuple(integer(n, "shape dimension", 1) for n in shape)


def _values(value, shape, name):
    """Accept a shaped nested array or an explicitly flattened numeric vector."""
    count = math.prod(shape)
    if callable(getattr(value, "tolist", None)):
        array_shape = getattr(value, "shape", None)
        if array_shape is not None:
            if not isinstance(array_shape, (tuple, list)) or tuple(array_shape) not in (
                shape,
                (count,),
            ):
                raise ValueError(f"{name} does not match shape {shape}")
        value = value.tolist()
    if not shape:
        return (number(value, name),)
    if isinstance(value, (list, tuple)) and len(value) == count:
        if all(not isinstance(v, (list, tuple)) for v in value):
            return tuple(number(v, name) for v in value)

    def flatten(item, dimensions):
        if not dimensions:
            return [number(item, name)]
        if not isinstance(item, (list, tuple)) or len(item) != dimensions[0]:
            raise ValueError(f"{name} does not match shape {shape}")
        return [v for child in item for v in flatten(child, dimensions[1:])]

    return tuple(flatten(value, shape))
