"""Uniform local prediction relations on a jointly repaired population graph.

Every patch has live state ``x``, retained incoming weights ``w`` and bias ``b``:
``p_i = tanh(b_i + sum(w_ij * signal_j))`` and ``e_i = x_i - p_i``.
A signal reads an input clamp, a live patch state, or an exactly recomputed
patch error. State connections may be recurrent. Error-readback dependencies
must be acyclic; this restriction concerns derived quantities, not the state
feedback graph. Observers use the same relation as other processing patches.

The energy is ``sum(e**2)/2 + state_prior*sum(x**2)/2``, plus a fixed proximal
parameter prior during an admitted learning solve. One projected-gradient
repair with a scalar secant step and Armijo backtracking updates the eligible
coordinates. A query freezes parameters; a learning solve repairs state and
parameters together. Batch repair gives each example private states and shares
one parameter set. It averages row energies and adds the parameter prior once.
This module does not admit evidence or mutate a caller's durable memory.

On the bounded boxes the energy is smooth. Ordinary accepted repairs decrease
it, with the bounded stationary finishing allowance documented below;
the usual projected-descent stationarity argument requires adequate line
search and continued iteration. Nonconvexity permits different stationary
points. Finite budgets can refuse, and neither uniqueness nor global optimality
is claimed. Qualification checks the complete projected gradient, including
derivatives through error readback, rather than requiring prediction errors
to vanish. The latter can remain nonzero at a qualified compromise.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from fractions import Fraction

from ._validation import integer, number


def _vector(values, length, name):
    if isinstance(values, (str, bytes, Mapping)):
        raise ValueError(f"{name} must contain {length} finite numbers")
    try:
        result = tuple(number(v, name) for v in values)
    except TypeError as error:
        raise ValueError(f"{name} must contain {length} finite numbers") from error
    if len(result) != length:
        raise ValueError(f"{name} must contain {length} finite numbers")
    return result


@dataclass(frozen=True, slots=True)
class Graph:
    """Immutable port topology; weights are supplied separately in edge order.

    ``edges`` contains ``(kind, source, target)`` triples. ``kind`` is ``input``,
    ``state`` or ``residual``. Input sources index ``n_inputs``; other sources
    and every target index ``n_patches``. Identical edges are rejected. The
    derived ``residual_order`` puts every error source before its consumer.
    """

    n_inputs: int
    n_patches: int
    edges: tuple[tuple[str, int, int], ...]
    residual_order: tuple[int, ...] = field(init=False)
    incoming: tuple[tuple[int, ...], ...] = field(init=False, repr=False)

    def __post_init__(self):
        n_inputs = integer(self.n_inputs, "n_inputs")
        n_patches = integer(self.n_patches, "n_patches", 1)
        if isinstance(self.edges, (str, bytes, Mapping)):
            raise ValueError("edges must contain (kind, source, target) triples")
        try:
            supplied = tuple(self.edges)
        except TypeError as error:
            raise ValueError("edges must be iterable") from error
        edges, seen = [], set()
        incoming = [[] for _ in range(n_patches)]
        descendants = [[] for _ in range(n_patches)]
        degree = [0] * n_patches
        for item in supplied:
            if not isinstance(item, (tuple, list)) or len(item) != 3:
                raise ValueError("Every edge must be a (kind, source, target) triple")
            kind, source, target = item
            if not isinstance(kind, str) or kind not in {"input", "state", "residual"}:
                raise ValueError("Edge kind must be input, state or residual")
            source = integer(source, "edge source")
            target = integer(target, "edge target")
            if source >= (n_inputs if kind == "input" else n_patches):
                raise ValueError("Edge source is outside its declared population")
            if target >= n_patches:
                raise ValueError("Edge target is outside its declared population")
            edge = (kind, source, target)
            if edge in seen:
                raise ValueError("Identical edges must not be repeated")
            seen.add(edge)
            incoming[target].append(len(edges))
            edges.append(edge)
            if kind == "residual":
                descendants[source].append(target)
                degree[target] += 1
        ready = deque(i for i, count in enumerate(degree) if count == 0)
        order = []
        while ready:
            source = ready.popleft()
            order.append(source)
            for target in descendants[source]:
                degree[target] -= 1
                if degree[target] == 0:
                    ready.append(target)
        if len(order) != n_patches:
            raise ValueError("Residual-readback dependencies must be acyclic")
        object.__setattr__(self, "n_inputs", n_inputs)
        object.__setattr__(self, "n_patches", n_patches)
        object.__setattr__(self, "edges", tuple(edges))
        object.__setattr__(self, "residual_order", tuple(order))
        object.__setattr__(self, "incoming", tuple(tuple(row) for row in incoming))


def _arguments(
    graph,
    inputs,
    state,
    weights,
    biases,
    anchor_weights,
    anchor_biases,
    *,
    batch_size=1,
):
    if not isinstance(graph, Graph):
        raise ValueError("graph must be a Graph")
    batch_size = integer(batch_size, "batch_size", 1)
    inputs = _vector(inputs, batch_size * graph.n_inputs, "inputs")
    state = _vector(state, batch_size * graph.n_patches, "state")
    weights = _vector(weights, len(graph.edges), "weights")
    biases = _vector(biases, graph.n_patches, "biases")
    if (anchor_weights is None) != (anchor_biases is None):
        raise ValueError("Supply both parameter anchors, or neither")
    if anchor_weights is not None:
        anchor_weights = _vector(anchor_weights, len(graph.edges), "anchor_weights")
        anchor_biases = _vector(anchor_biases, graph.n_patches, "anchor_biases")
    return inputs, state, weights, biases, anchor_weights, anchor_biases


def _evaluate(
    graph,
    inputs,
    state,
    weights,
    biases,
    state_prior,
    anchor_weights,
    anchor_biases,
    parameter_prior,
    visits=None,
    *,
    parameter_gradients=True,
):
    predictions = [0.0] * graph.n_patches
    errors = [0.0] * graph.n_patches
    signals = [0.0] * len(graph.edges)
    try:
        for target in graph.residual_order:
            if visits is not None:
                visits["patch_visits"] += 1
            terms = [biases[target]]
            for edge_index in graph.incoming[target]:
                if visits is not None:
                    visits["edge_visits"] += 1
                kind, source, _ = graph.edges[edge_index]
                signals[edge_index] = (
                    inputs[source]
                    if kind == "input"
                    else state[source]
                    if kind == "state"
                    else errors[source]
                )
                terms.append(weights[edge_index] * signals[edge_index])
            activation = math.fsum(terms)
            if not math.isfinite(activation):
                raise ValueError("A prediction exceeds the finite numeric range")
            predictions[target] = math.tanh(activation)
            errors[target] = state[target] - predictions[target]
        energy = 0.5 * math.fsum(e * e for e in errors)
        energy += 0.5 * state_prior * math.fsum(x * x for x in state)
        grad_state = [state_prior * x for x in state]
        grad_weights = [0.0] * len(weights) if parameter_gradients else []
        grad_biases = [0.0] * len(biases) if parameter_gradients else []
        adj_error = list(errors)
        for target in reversed(graph.residual_order):
            if visits is not None:
                visits["patch_visits"] += 1
            adj = adj_error[target]
            grad_state[target] += adj
            adj_prediction = -adj * (1.0 - predictions[target] ** 2)
            if parameter_gradients:
                grad_biases[target] += adj_prediction
            for edge_index in graph.incoming[target]:
                if visits is not None:
                    visits["edge_visits"] += 1
                kind, source, _ = graph.edges[edge_index]
                if parameter_gradients:
                    grad_weights[edge_index] += adj_prediction * signals[edge_index]
                if kind == "state":
                    grad_state[source] += adj_prediction * weights[edge_index]
                elif kind == "residual":
                    adj_error[source] += adj_prediction * weights[edge_index]
        if anchor_weights is not None:
            delta_weights = [
                w - a for w, a in zip(weights, anchor_weights, strict=True)
            ]
            delta_biases = [b - a for b, a in zip(biases, anchor_biases, strict=True)]
            energy += (
                0.5
                * parameter_prior
                * math.fsum(d * d for d in (*delta_weights, *delta_biases))
            )
            grad_weights = [
                g + parameter_prior * d
                for g, d in zip(grad_weights, delta_weights, strict=True)
            ]
            grad_biases = [
                g + parameter_prior * d
                for g, d in zip(grad_biases, delta_biases, strict=True)
            ]
        quantities = (
            energy,
            *predictions,
            *errors,
            *grad_state,
            *grad_weights,
            *grad_biases,
        )
        if not all(math.isfinite(x) for x in quantities):
            raise ValueError("Energy or gradient exceeds the finite numeric range")
    except (OverflowError, ArithmeticError) as error:
        raise ValueError(
            "Energy or gradient exceeds the finite numeric range"
        ) from error
    return {
        "energy": energy,
        "predictions": tuple(predictions),
        "errors": tuple(errors),
        "signals": tuple(signals),
        "gradient_state": tuple(grad_state),
        "gradient_weights": tuple(grad_weights),
        "gradient_biases": tuple(grad_biases),
    }


def evaluate(
    graph,
    inputs,
    state,
    weights,
    biases,
    *,
    state_prior=0.01,
    anchor_weights=None,
    anchor_biases=None,
    parameter_prior=0.1,
):
    """Recompute energy, exact error readback and all analytic derivatives.

    Supplied anchors add a fixed quadratic parameter prior. Without anchors,
    parameter derivatives still describe the unanchored energy, even if a
    caller will freeze those coordinates. Invalid or nonfinite inputs and
    nonrepresentable derived quantities raise ``ValueError``. No input changes.
    """
    args = _arguments(
        graph, inputs, state, weights, biases, anchor_weights, anchor_biases
    )
    inputs, state, weights, biases, anchor_weights, anchor_biases = args
    state_prior = number(state_prior, "state_prior", positive=True)
    parameter_prior = number(parameter_prior, "parameter_prior", positive=True)
    return _evaluate(
        graph,
        inputs,
        state,
        weights,
        biases,
        state_prior,
        anchor_weights,
        anchor_biases,
        parameter_prior,
    )


def _mean(values):
    """Average finite values without underflowing each term or overflowing sums."""
    values = tuple(values)
    try:
        return math.fsum(values) / len(values)
    except OverflowError:
        # Rare extreme-scale cancellation needs the exact sum before division.
        # Scaling each term first can silently discard a small real gradient.
        return float(sum(map(Fraction, values)) / len(values))


def _evaluate_batch(
    graph,
    inputs,
    state,
    weights,
    biases,
    state_prior,
    anchor_weights,
    anchor_biases,
    parameter_prior,
    visits=None,
    *,
    parameter_gradients=True,
    batch_size=None,
):
    """Mean row energy with private states and one shared parameter anchor.

    State, prediction and error arrays are flattened in example order. State
    derivatives belong to the mean objective (and therefore contain ``1/B``);
    original row derivatives are retained for activity moves and qualification,
    so averaging cannot hide a subnormal private-state residual.
    """
    if batch_size is None:
        batch_size = len(state) // graph.n_patches
    batch_size = integer(batch_size, "batch_size", 1)
    if (
        len(state) != batch_size * graph.n_patches
        or len(inputs) != batch_size * graph.n_inputs
    ):
        raise ValueError("Batch inputs and states must match the declared row count")
    rows = [
        _evaluate(
            graph,
            inputs[row * graph.n_inputs : (row + 1) * graph.n_inputs],
            state[row * graph.n_patches : (row + 1) * graph.n_patches],
            weights,
            biases,
            state_prior,
            None,
            None,
            parameter_prior,
            visits,
            parameter_gradients=parameter_gradients,
        )
        for row in range(batch_size)
    ]
    result = {
        key: tuple(value for row in rows for value in row[key])
        for key in ("predictions", "errors", "signals")
    }
    try:
        result["energy"] = _mean(row["energy"] for row in rows)
        result["gradient_state_unscaled"] = tuple(
            value for row in rows for value in row["gradient_state"]
        )
        result["gradient_state"] = tuple(
            value / batch_size for value in result["gradient_state_unscaled"]
        )
        for key, values, anchors in (
            ("gradient_weights", weights, anchor_weights),
            ("gradient_biases", biases, anchor_biases),
        ):
            gradient = (
                [_mean(row[key][i] for row in rows) for i in range(len(values))]
                if parameter_gradients
                else []
            )
            if anchors is not None:
                differences = [x - a for x, a in zip(values, anchors, strict=True)]
                result["energy"] += (
                    0.5
                    * parameter_prior
                    * math.fsum(delta * delta for delta in differences)
                )
                if parameter_gradients:
                    gradient = [
                        g + parameter_prior * delta
                        for g, delta in zip(gradient, differences, strict=True)
                    ]
            result[key] = tuple(gradient)
        if not all(
            math.isfinite(value)
            for value in (
                result["energy"],
                *result["gradient_state"],
                *result["gradient_weights"],
                *result["gradient_biases"],
            )
        ):
            raise ValueError("Energy or gradient exceeds the finite numeric range")
    except (ArithmeticError, OverflowError) as error:
        raise ValueError(
            "Energy or gradient exceeds the finite numeric range"
        ) from error
    return result


def _clip(value, bound):
    return min(bound, max(-bound, value))


def _projected_component(value, gradient, bound):
    # Stable form of x - clip(x-g): avoid cancellation of tiny g at large x.
    return (
        min(gradient, value + bound) if gradient >= 0 else max(gradient, value - bound)
    )


def _stationarity(
    state,
    weights,
    biases,
    evaluated,
    clamps,
    learn,
    state_bound,
    bound,
    *,
    state_scale=1,
):
    state_gradient = evaluated.get(
        "gradient_state_unscaled",
        (state_scale * g for g in evaluated["gradient_state"]),
    )
    residual = max(
        (
            abs(_projected_component(x, g, state_bound))
            for i, (x, g) in enumerate(zip(state, state_gradient, strict=True))
            if i not in clamps
        ),
        default=0.0,
    )
    if learn:
        for values, key in ((weights, "gradient_weights"), (biases, "gradient_biases")):
            residual = max(
                residual,
                max(
                    (
                        abs(_projected_component(x, g, bound))
                        for x, g in zip(values, evaluated[key], strict=True)
                    ),
                    default=0.0,
                ),
            )
    return residual


def _next_step(groups, current, proposed, step, backtracks, *, state_scale=1):
    """Use observed curvature, falling back to the configured step if unsafe."""
    try:
        changes = [
            (new - old, new_g - old_g, state_scale if key == "gradient_state" else 1)
            for old_values, new_values, key in groups
            for old, new, old_g, new_g in zip(
                old_values, new_values, current[key], proposed[key], strict=True
            )
            if new != old
        ]
        distance = math.fsum(s * s / scale for s, _, scale in changes)
        curvature = math.fsum(s * y for s, y, _ in changes)
        if curvature > 0:
            estimate = distance / curvature
            # The configured step remains reachable within the line-search budget.
            ceiling = math.ldexp(step, min(backtracks - 1, 1023))
            if math.isfinite(estimate) and estimate > 0:
                return min(estimate, ceiling)
    except (ArithmeticError, ValueError):
        pass
    return step


def settle(
    graph,
    inputs,
    state,
    weights,
    biases,
    *,
    clamps=None,
    learn=False,
    budget=2048,
    tolerance=1e-6,
    state_prior=0.01,
    parameter_prior=0.1,
    state_bound=1.0,
    parameter_bound=4.0,
    step=1.0,
    backtracks=32,
    anchor_weights=None,
    anchor_biases=None,
    _engine=None,
    _batch_size=1,
):
    """Repair eligible coordinates and freshly qualify the complete final state.

    A sweep proposes one simultaneous projected-gradient update and uses up to
    ``backtracks`` energy evaluations under the acceptance rule below. ``budget``
    bounds accepted sweeps. A zero budget can qualify an already stationary
    initial state. All returned arrays are tuples; caller-owned data is untouched.

    ``step`` is the initial and fallback trial size. Accepted displacement and
    gradient change estimate the next size; unsafe curvature uses ``step``.
    Growth is capped so backtracking can reach the configured step within its
    budget. A fully stationary proposal may finish within eight energy ulps of
    the current energy when roundoff prevents sufficient decrease. Qualification
    still uses the requested tolerance, independently recomputed at the end.

    ``clamps`` maps patch indices to witnessed fixed states. Inputs are always
    hard boundary values. Query solves freeze parameters; learning solves repair
    them with anchors fixed to their starting values unless explicitly supplied.
    Invalid starts, bounds or configuration raise ``ValueError``. A valid solve
    can return ``qualified=False`` with reason ``budget`` or ``line_search``.
    This is numerical qualification, not evidence admission or task success.
    Work counts include rejected proposals and final qualification; edge/patch
    visits count prediction-error traversal, not every Python operation.

    ``_batch_size`` flattens independent example states and inputs in row order,
    with one shared parameter set and fixed anchors. The objective is the mean
    row energy plus one prior. State moves and projected stationarity use each
    row's unaveraged gradient; the secant metric accounts for this scaling.
    """
    _batch_size = integer(_batch_size, "batch_size", 1)
    args = _arguments(
        graph,
        inputs,
        state,
        weights,
        biases,
        anchor_weights,
        anchor_biases,
        batch_size=_batch_size,
    )
    inputs, state, weights, biases, anchor_weights, anchor_biases = args
    if type(learn) is not bool:
        raise ValueError("learn must be a boolean")
    budget = integer(budget, "budget")
    backtracks = integer(backtracks, "backtracks", 1)
    tolerance = number(tolerance, "tolerance", positive=True)
    state_prior = number(state_prior, "state_prior", positive=True)
    parameter_prior = number(parameter_prior, "parameter_prior", positive=True)
    state_bound = number(state_bound, "state_bound", positive=True)
    parameter_bound = number(parameter_bound, "parameter_bound", positive=True)
    step = number(step, "step", positive=True)
    if any(abs(x) > state_bound for x in state):
        raise ValueError("Initial state exceeds state_bound")
    if any(abs(x) > parameter_bound for x in (*weights, *biases)):
        raise ValueError("Initial parameters exceed parameter_bound")
    if not learn and anchor_weights is not None:
        raise ValueError("Query solves freeze parameters and do not accept anchors")
    if learn and anchor_weights is None:
        anchor_weights, anchor_biases = weights, biases
    if anchor_weights is not None and any(
        abs(x) > parameter_bound for x in (*anchor_weights, *anchor_biases)
    ):
        raise ValueError("Parameter anchors exceed parameter_bound")
    if clamps is None:
        clamps = {}
    if not isinstance(clamps, Mapping):
        raise ValueError("clamps must map patch indices to fixed values")
    fixed = {}
    for index, value in clamps.items():
        index = integer(index, "clamp index")
        value = number(value, "clamp value")
        if index >= len(state) or abs(value) > state_bound:
            raise ValueError("Clamp index or value is outside its declared bounds")
        fixed[index] = value
    state = tuple(fixed.get(i, x) for i, x in enumerate(state))
    if _engine is not None:
        return _engine.settle(
            inputs,
            state,
            weights,
            biases,
            clamps=fixed,
            learn=learn,
            budget=budget,
            tolerance=tolerance,
            state_prior=state_prior,
            parameter_prior=parameter_prior,
            state_bound=state_bound,
            parameter_bound=parameter_bound,
            step=step,
            backtracks=backtracks,
            anchor_weights=anchor_weights,
            anchor_biases=anchor_biases,
            **({"_batch_size": _batch_size} if _batch_size > 1 else {}),
        )
    evaluations, proposals, rejected = 0, 0, 0
    visits = {"edge_visits": 0, "patch_visits": 0}

    def compute(x, w, b):
        nonlocal evaluations
        evaluations += 1
        evaluator = _evaluate if _batch_size == 1 else _evaluate_batch
        return evaluator(
            graph,
            inputs,
            x,
            w,
            b,
            state_prior,
            anchor_weights,
            anchor_biases,
            parameter_prior,
            visits,
            parameter_gradients=learn,
            **({"batch_size": _batch_size} if _batch_size > 1 else {}),
        )

    current = compute(state, weights, biases)
    history = [current["energy"]]
    sweeps, reason = 0, "budget"
    next_step = step
    for _ in range(budget):
        if (
            _stationarity(
                state,
                weights,
                biases,
                current,
                fixed,
                learn,
                state_bound,
                parameter_bound,
                state_scale=_batch_size,
            )
            <= tolerance
        ):
            reason = "qualified"
            break
        trial_step, accepted = next_step, False
        for _attempt in range(backtracks):
            proposals += 1
            state_gradient = current.get(
                "gradient_state_unscaled", current["gradient_state"]
            )
            next_state = tuple(
                fixed.get(i, _clip(x - trial_step * g, state_bound))
                for i, (x, g) in enumerate(zip(state, state_gradient, strict=True))
            )
            next_weights, next_biases = weights, biases
            if learn:
                next_weights = tuple(
                    _clip(x - trial_step * g, parameter_bound)
                    for x, g in zip(weights, current["gradient_weights"], strict=True)
                )
                next_biases = tuple(
                    _clip(x - trial_step * g, parameter_bound)
                    for x, g in zip(biases, current["gradient_biases"], strict=True)
                )
            groups = ((state, next_state, "gradient_state"),)
            if learn:
                groups += (
                    (weights, next_weights, "gradient_weights"),
                    (biases, next_biases, "gradient_biases"),
                )
            try:
                slope = math.fsum(
                    g * (new - old)
                    for old_values, new_values, key in groups
                    for old, new, g in zip(
                        old_values, new_values, current[key], strict=True
                    )
                )
                moved = (next_state, next_weights, next_biases) != (
                    state,
                    weights,
                    biases,
                )
                proposed = compute(next_state, next_weights, next_biases)
                accepted = (
                    moved
                    and math.isfinite(slope)
                    and slope < 0
                    and (
                        proposed["energy"] <= current["energy"] + 1e-4 * slope
                        or (
                            abs(proposed["energy"] - current["energy"])
                            <= 8 * math.ulp(current["energy"])
                            and _stationarity(
                                next_state,
                                next_weights,
                                next_biases,
                                proposed,
                                fixed,
                                learn,
                                state_bound,
                                parameter_bound,
                                state_scale=_batch_size,
                            )
                            <= tolerance
                        )
                    )
                )
            except (ValueError, OverflowError):
                accepted = False
            if accepted:
                next_step = _next_step(
                    groups,
                    current,
                    proposed,
                    step,
                    backtracks,
                    state_scale=_batch_size,
                )
                state, weights, biases = next_state, next_weights, next_biases
                current = proposed
                history.append(current["energy"])
                sweeps += 1
                break
            rejected += 1
            trial_step *= 0.5
        if not accepted:
            reason = "line_search"
            break
    final = compute(state, weights, biases)
    residual = _stationarity(
        state,
        weights,
        biases,
        final,
        fixed,
        learn,
        state_bound,
        parameter_bound,
        state_scale=_batch_size,
    )
    qualified = math.isfinite(residual) and residual <= tolerance
    if qualified:
        reason = "qualified"
    return {
        "state": state,
        "weights": weights,
        "biases": biases,
        "predictions": final["predictions"],
        "errors": final["errors"],
        "energy": final["energy"],
        "stationarity": residual,
        "prediction_residual": max(map(abs, final["errors"]), default=0.0),
        "qualified": qualified,
        "sweeps": sweeps,
        "reason": reason,
        "energy_history": tuple(history),
        "work": {
            "evaluations": evaluations,
            **visits,
            "proposals": proposals,
            "backtracks": rejected,
        },
    }
