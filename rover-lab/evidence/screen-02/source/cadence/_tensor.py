"""Optional tensor execution of the same patch energy and analytic derivatives.

Tensors propose repairs; the Python float64 engine checks every final candidate
against original inputs, witnesses and anchors before it can be admitted.
No autograd, optimizer, policy network or learning rule is supplied by PyTorch.
"""

from __future__ import annotations

import math

from . import _repair


class TensorEngine:
    """Cache residual levels and device indices for one immutable topology."""

    def __init__(self, graph, device, dtype):
        try:
            import torch
        except ImportError as error:
            raise ImportError(
                'Tensor execution requires the optional extra: pip install "cadence-net[gpu]"'
            ) from error
        self.torch, self.graph, self.device = torch, graph, device
        self.dtype_name, self.dtype = dtype, getattr(torch, dtype)
        try:
            torch.empty(0, device=device, dtype=self.dtype)
        except (RuntimeError, AssertionError) as error:
            raise ValueError(
                f"Cadence device {device!r} with {dtype} is unavailable: {error}"
            ) from error
        depth = [0] * graph.n_patches
        for target in graph.residual_order:
            depth[target] = max(
                (
                    depth[graph.edges[e][1]] + 1
                    for e in graph.incoming[target]
                    if graph.edges[e][0] == "residual"
                ),
                default=0,
            )
        self.levels = []
        for level in range(max(depth) + 1):
            nodes = [i for i in graph.residual_order if depth[i] == level]
            local = {node: i for i, node in enumerate(nodes)}
            edges = [e for node in nodes for e in graph.incoming[node]]
            sources = []
            kinds = {"state": ([], []), "residual": ([], [])}
            for position, e in enumerate(edges):
                kind, source, _ = graph.edges[e]
                sources.append(
                    source
                    + (
                        0
                        if kind == "input"
                        else graph.n_inputs
                        if kind == "state"
                        else graph.n_inputs + graph.n_patches
                    )
                )
                if kind in kinds:
                    kinds[kind][0].append(position)
                    kinds[kind][1].append(source)

            def indices(values):
                return torch.tensor(values, dtype=torch.long, device=device)

            self.levels.append(
                (
                    indices(nodes),
                    indices(edges),
                    indices(sources),
                    indices([local[graph.edges[e][2]] for e in edges]),
                    tuple(
                        (indices(positions), indices(sources))
                        for positions, sources in kinds.values()
                    ),
                )
            )

    def tensor(self, values):
        return self.torch.tensor(values, dtype=self.dtype, device=self.device)

    def evaluate(
        self,
        inputs,
        state,
        weights,
        biases,
        state_prior,
        anchors,
        parameter_prior,
        learn,
        *,
        batch_size=1,
    ):
        """Device-resident energy and exact analytic derivative of the tensor law."""
        if batch_size != 1:
            return self._evaluate_batch(
                inputs,
                state,
                weights,
                biases,
                state_prior,
                anchors,
                parameter_prior,
                learn,
                batch_size,
            )
        t = self.torch
        predictions = t.zeros_like(state)
        sources_live = t.cat((inputs, state, t.zeros_like(state)))
        errors = sources_live[inputs.numel() + state.numel() :]
        signals = t.empty_like(weights) if learn else None
        finite_drives = t.ones((), dtype=t.bool, device=self.device)
        for nodes, edges, sources, targets, _ in self.levels:
            signal = sources_live[sources]
            if learn:
                signals[edges] = signal
            drive = t.zeros_like(nodes, dtype=self.dtype).index_add_(
                0, targets, weights[edges] * signal
            )
            drive += biases[nodes]
            # Keep this check before tanh can hide infinities, but collect the
            # flag on-device rather than synchronizing each observer level.
            finite_drives &= t.isfinite(drive).all()
            predictions[nodes] = t.tanh(drive)
            errors[nodes] = state[nodes] - predictions[nodes]
        energy = 0.5 * (errors.square().sum() + state_prior * state.square().sum())
        grad_state, adj = state_prior * state, errors.clone()
        grad_weights = t.empty_like(weights) if learn else weights.new_empty(0)
        grad_biases = t.empty_like(biases) if learn else biases.new_empty(0)
        for nodes, edges, _, targets, (
            (state_pos, state_src),
            (error_pos, error_src),
        ) in reversed(self.levels):
            q = adj[nodes]
            grad_state[nodes] += q
            h = -q * (1 - predictions[nodes].square())
            if learn:
                grad_weights[edges] = h[targets] * signals[edges]
                grad_biases[nodes] = h
            if state_src.numel():
                grad_state.index_add_(
                    0, state_src, h[targets[state_pos]] * weights[edges[state_pos]]
                )
            if error_src.numel():
                adj.index_add_(
                    0, error_src, h[targets[error_pos]] * weights[edges[error_pos]]
                )
        if anchors is not None:
            dw, db = weights - anchors[0], biases - anchors[1]
            energy += 0.5 * parameter_prior * (dw.square().sum() + db.square().sum())
            grad_weights += parameter_prior * dw
            grad_biases += parameter_prior * db
        if not bool(
            finite_drives
            & t.isfinite(
                t.cat((energy.reshape(1), grad_state, grad_weights, grad_biases))
            ).all()
        ):
            raise ValueError(
                "Tensor prediction, energy or gradient exceeds the finite numeric range"
            )
        return energy, (grad_state, grad_weights, grad_biases)

    def _evaluate_batch(
        self,
        inputs,
        state,
        weights,
        biases,
        state_prior,
        anchors,
        parameter_prior,
        learn,
        batch_size,
    ):
        """Vectorize private row states with shared relations and one anchor.

        Row energies are averaged. Returned state derivatives therefore carry
        1/B; the solver scales their proposals and stationarity back by B.
        Traversal loops over residual levels, never over the batch's examples.
        """
        t, graph = self.torch, self.graph
        states = state.reshape(batch_size, graph.n_patches)
        predictions = t.zeros_like(states)
        sources_live = t.cat(
            (inputs.reshape(batch_size, graph.n_inputs), states, t.zeros_like(states)),
            dim=1,
        )
        errors = sources_live[:, graph.n_inputs + graph.n_patches :]
        signals = weights.new_empty((batch_size, weights.numel())) if learn else None
        finite_drives = t.ones((), dtype=t.bool, device=self.device)
        for nodes, edges, sources, targets, _ in self.levels:
            signal = sources_live[:, sources]
            if learn:
                signals[:, edges] = signal
            drive = states.new_zeros((batch_size, nodes.numel())).index_add_(
                1,
                targets,
                weights[edges] * signal,
            )
            drive += biases[nodes]
            finite_drives &= t.isfinite(drive).all()
            predictions[:, nodes] = t.tanh(drive)
            errors[:, nodes] = states[:, nodes] - predictions[:, nodes]
        # Scale finite row contributions before reduction: their sum can
        # overflow even when the declared mean objective is representable.
        row_energy = 0.5 * errors.square().sum(dim=1)
        row_energy += 0.5 * state_prior * states.square().sum(dim=1)
        energy = (row_energy / batch_size).sum()
        grad_state, adj = state_prior * states, errors.clone()
        grad_weights = t.empty_like(weights) if learn else weights.new_empty(0)
        grad_biases = t.empty_like(biases) if learn else biases.new_empty(0)
        for nodes, edges, _, targets, (
            (state_pos, state_src),
            (error_pos, error_src),
        ) in reversed(self.levels):
            q = adj[:, nodes]
            grad_state[:, nodes] += q
            h = -q * (1 - predictions[:, nodes].square())
            if learn:
                grad_weights[edges] = (
                    h[:, targets] * signals[:, edges] / batch_size
                ).sum(dim=0)
                grad_biases[nodes] = (h / batch_size).sum(dim=0)
            if state_src.numel():
                grad_state.index_add_(
                    1,
                    state_src,
                    h[:, targets[state_pos]] * weights[edges[state_pos]],
                )
            if error_src.numel():
                adj.index_add_(
                    1,
                    error_src,
                    h[:, targets[error_pos]] * weights[edges[error_pos]],
                )
        grad_state = grad_state.reshape(-1) / batch_size
        if anchors is not None:
            dw, db = weights - anchors[0], biases - anchors[1]
            energy += 0.5 * parameter_prior * (dw.square().sum() + db.square().sum())
            grad_weights += parameter_prior * dw
            grad_biases += parameter_prior * db
        if not bool(
            finite_drives
            & t.isfinite(
                t.cat((energy.reshape(1), grad_state, grad_weights, grad_biases))
            ).all()
        ):
            raise ValueError(
                "Tensor prediction, energy or gradient exceeds the finite numeric range"
            )
        return energy, (grad_state, grad_weights, grad_biases)

    def settle(self, inputs, state, weights, biases, **options):
        """Repair on-device, then qualify/refine using original float64 data."""
        with self.torch.inference_mode():
            return self._settle(inputs, state, weights, biases, **options)

    def _settle(self, inputs, state, weights, biases, **o):
        t, graph = self.torch, self.graph
        learn, fixed, budget = o["learn"], o["clamps"], o["budget"]
        batch_size = o.get("_batch_size", 1)
        batch_options = {"batch_size": batch_size} if batch_size != 1 else {}
        evaluate_reference = (
            _repair._evaluate_batch if batch_size != 1 else _repair._evaluate
        )
        reference_start = evaluate_reference(
            graph,
            inputs,
            state,
            weights,
            biases,
            o["state_prior"],
            o["anchor_weights"],
            o["anchor_biases"],
            o["parameter_prior"],
            parameter_gradients=learn,
            **batch_options,
        )
        if (
            budget == 0
            or _repair._stationarity(
                state,
                weights,
                biases,
                reference_start,
                fixed,
                learn,
                o["state_bound"],
                o["parameter_bound"],
                state_scale=batch_size,
            )
            <= o["tolerance"]
        ):
            result = _repair.settle(
                graph, inputs, state, weights, biases, **{**o, "budget": 0}
            )
            result["work"]["evaluations"] += 1
            result["work"]["patch_visits"] += 2 * batch_size * graph.n_patches
            result["work"]["edge_visits"] += 2 * batch_size * len(graph.edges)
            result["execution"] = {
                "device": self.device,
                "dtype": self.dtype_name,
                "torch": t.__version__,
                "tensor_sweeps": 0,
                "reference_sweeps": 0,
                "reference_evaluations": result["work"]["evaluations"],
                "reference_restart": False,
            }
            return result
        sensor = self.tensor(inputs)
        values = tuple(map(self.tensor, (state, weights, biases)))
        anchors = (
            tuple(map(self.tensor, (o["anchor_weights"], o["anchor_biases"])))
            if learn
            else None
        )
        if not all(
            bool(t.isfinite(v).all()) for v in (sensor, *values, *(anchors or ()))
        ):
            raise ValueError(
                "Inputs/parameters are not representable in the selected dtype; use float64"
            )
        mask = t.ones(batch_size * graph.n_patches, dtype=t.bool, device=self.device)
        if fixed:
            mask[t.tensor(list(fixed), dtype=t.long, device=self.device)] = False
        bounds = (o["state_bound"], o["parameter_bound"], o["parameter_bound"])
        active = 3 if learn else 1
        evaluations, proposals, rejected, sweeps = 0, 0, 0, 0

        def compute(v):
            nonlocal evaluations
            evaluations += 1
            return self.evaluate(
                sensor,
                *v,
                o["state_prior"],
                anchors,
                o["parameter_prior"],
                learn,
                **batch_options,
            )

        def stationarity(v, gradients):
            pieces = []
            for i in range(active):
                g, x, bound = gradients[i], v[i], bounds[i]
                if i == 0:
                    g = g * batch_size
                projected = t.where(
                    g >= 0, t.minimum(g, x + bound), t.maximum(g, x - bound)
                )
                if i == 0:
                    projected = t.where(mask, projected, 0)
                if projected.numel():
                    pieces.append(projected.abs().max())
            return float(t.stack(pieces).max()) if pieces else 0.0

        # This is only a device stopping hint. It never relaxes admission tolerance.
        precision = t.finfo(self.dtype)
        hint = max(o["tolerance"], 64 * precision.eps)
        # Low precision is a proposal stage. Reserve half the allowance for
        # exact-data refinement rather than spending it all near a device floor.
        tensor_budget = max(1, budget // 2) if self.dtype_name == "float32" else budget
        try:
            ceiling = math.ldexp(o["step"], min(o["backtracks"] - 1, 1023))
        except OverflowError:
            ceiling = o["step"]
        energy, gradient = compute(values)
        current_energy = float(energy)
        history, next_step = [current_energy], o["step"]
        for _ in range(tensor_budget):
            if stationarity(values, gradient) <= hint:
                break
            trial_step, accepted = next_step, False
            for _ in range(o["backtracks"]):
                proposals += 1
                proposal = list(values)
                for i in range(active):
                    scale = batch_size if i == 0 else 1
                    proposal[i] = (values[i] - trial_step * scale * gradient[i]).clamp(
                        -bounds[i], bounds[i]
                    )
                proposal[0] = t.where(mask, proposal[0], values[0])
                displacement = [proposal[i] - values[i] for i in range(active)]
                slope_tensor = sum(
                    (gradient[i] * displacement[i]).sum() for i in range(active)
                )
                try:
                    proposed_energy, proposed_gradient = compute(proposal)
                    new_energy, slope = (
                        t.stack((proposed_energy, slope_tensor)).cpu().tolist()
                    )
                    # Rounding allowance is in the selected arithmetic, not a proof
                    # of float64 decrease at every intermediate device step.
                    ulps = 8 * max(abs(current_energy), precision.tiny) * precision.eps
                    accepted = (
                        math.isfinite(slope)
                        and slope < 0
                        and (
                            new_energy <= current_energy + 1e-4 * slope
                            or (
                                abs(new_energy - current_energy) <= ulps
                                and stationarity(proposal, proposed_gradient) <= hint
                            )
                        )
                    )
                except ValueError:
                    accepted = False
                if accepted:
                    distance, curvature = (
                        t.stack(
                            (
                                sum(
                                    (d.square() / (batch_size if i == 0 else 1)).sum()
                                    for i, d in enumerate(displacement)
                                ),
                                sum(
                                    (
                                        displacement[i]
                                        * (proposed_gradient[i] - gradient[i])
                                    ).sum()
                                    for i in range(active)
                                ),
                            )
                        )
                        .cpu()
                        .tolist()
                    )
                    next_step = o["step"]
                    if curvature > 0:
                        estimate = distance / curvature
                        if math.isfinite(estimate) and estimate > 0:
                            next_step = min(estimate, ceiling)
                    values, gradient, current_energy = (
                        tuple(proposal),
                        proposed_gradient,
                        new_energy,
                    )
                    history.append(new_energy)
                    sweeps += 1
                    break
                rejected += 1
                trial_step *= 0.5
            if not accepted:
                break

        candidate = [
            tuple(_repair._clip(x, bound) for x in v.cpu().tolist())
            for v, bound in zip(values, bounds, strict=True)
        ]
        candidate[0] = tuple(fixed.get(i, x) for i, x in enumerate(candidate[0]))
        if not learn:
            candidate[1:] = [weights, biases]
        # A zero-budget reference solve performs an independent final check.
        reference = _repair.settle(graph, inputs, *candidate, **{**o, "budget": 0})
        start_energy = reference_start["energy"]
        reset = reference["energy"] > start_energy + 8 * math.ulp(start_energy)
        reference_work = dict(reference["work"])
        reference_history = ()
        refinement_sweeps = 0
        remaining = budget - sweeps
        if (reset or not reference["qualified"]) and remaining:
            result = _repair.settle(
                graph,
                inputs,
                *((state, weights, biases) if reset else candidate),
                **{**o, "budget": remaining},
            )
            for key, value in result["work"].items():
                reference_work[key] += value
            reference_history = result["energy_history"]
            refinement_sweeps = result["sweeps"]
            reference = result
        elif reset:
            reference = _repair.settle(
                graph, inputs, state, weights, biases, **{**o, "budget": 0}
            )
            for key, value in reference["work"].items():
                reference_work[key] += value
        reference["sweeps"] = sweeps + refinement_sweeps
        reference["energy_history"] = tuple(history) + tuple(reference_history)
        reference["work"] = {
            "evaluations": evaluations + reference_work["evaluations"] + 1,
            "patch_visits": 2 * batch_size * graph.n_patches * (evaluations + 1)
            + reference_work["patch_visits"],
            "edge_visits": 2 * batch_size * len(graph.edges) * (evaluations + 1)
            + reference_work["edge_visits"],
            "proposals": proposals + reference_work["proposals"],
            "backtracks": rejected + reference_work["backtracks"],
        }
        reference["execution"] = {
            "device": self.device,
            "dtype": self.dtype_name,
            "torch": t.__version__,
            "tensor_sweeps": sweeps,
            "reference_sweeps": refinement_sweeps,
            "reference_evaluations": reference_work["evaluations"] + 1,
            "reference_restart": reset,
        }
        return reference
