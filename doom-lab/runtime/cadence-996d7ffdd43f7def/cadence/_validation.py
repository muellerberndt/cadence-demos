"""Finite numeric and strict JSON validation for population brains."""

from __future__ import annotations

import json
import math
from decimal import Decimal
from numbers import Integral, Real


def integer(value, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


def number(value, name: str, *, positive: bool = False) -> float:
    if type(value) not in (float, int) and (
        isinstance(value, bool) or not isinstance(value, (Real, Decimal))
    ):
        raise ValueError(f"{name} must be a finite real number")
    try:
        result = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a finite real number") from error
    if not math.isfinite(result) or (positive and result <= 0):
        qualifier = "positive finite" if positive else "finite"
        raise ValueError(f"{name} must be a {qualifier} real number")
    return result


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def strict_json(text: str, max_bytes: int):
    if not isinstance(text, str) or len(text.encode("utf-8")) > max_bytes:
        raise ValueError("Checkpoint exceeds its text-size limit")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate checkpoint field: {key}")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError(f"Non-finite JSON value: {value}")

    try:
        return json.loads(text, object_pairs_hook=unique, parse_constant=invalid)
    except (TypeError, RecursionError, json.JSONDecodeError) as error:
        raise ValueError("Malformed checkpoint") from error
