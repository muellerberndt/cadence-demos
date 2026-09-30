"""Declare populations and compile their wiring into one jointly settling brain.

``inputs`` read sensor or represented values. ``observes`` additionally reads
exact live prediction errors; feedback participates in the same settlement.
"""

from __future__ import annotations

import math
import random
import re
from itertools import islice
from types import MappingProxyType

from . import _repair
from ._validation import integer, number
from .brain import Brain
from .column import Population
from .ports import Input, Output, _shape


class Cortex:
    """Declare a population graph and compile it with :meth:`build`.

    ``seed`` fixes sampled wiring and initial relations. ``fan_in=None``
    connects every coordinate of each declared source to each target patch.
    A positive ``fan_in`` opts into sparse sampling, raised when necessary to
    cover every source coordinate across the destination population.
    ``initial_scale`` bounds random weights before fan-in normalization.

    ``settle_budget``, ``tolerance``, ``step`` and ``backtracks`` configure the
    common projected-gradient repair. ``state_prior`` penalizes activity;
    ``parameter_prior`` anchors relation changes to pre-experience parameters.
    Both priors are strictly positive. ``state_bound`` and ``parameter_bound``
    bound the state and relation boxes. Values outside them are rejected.

    ``max_inputs``, ``max_patches`` and ``max_connections`` bound construction.
    They count scalar sensor samples, processing patches and directed signal
    connections respectively, not physical process memory or latency.

    ``device`` selects ``python`` (default), tensor ``cpu``, Apple ``mps``, or
    NVIDIA ``cuda``/``cuda:N``. ``dtype`` defaults to float64 except on MPS,
    which requires float32. Tensor devices need the optional ``gpu`` extra;
    availability is checked on first solve. Final admission uses float64
    reference checks against the original inputs, witnesses and anchors.
    """

    def __init__(
        self,
        *,
        seed=0,
        fan_in=None,
        initial_scale=0.3,
        settle_budget=2048,
        tolerance=1e-6,
        state_prior=0.01,
        parameter_prior=0.1,
        state_bound=1.0,
        parameter_bound=4.0,
        step=1.0,
        backtracks=32,
        max_patches=10000,
        max_connections=1000000,
        max_inputs=1000000,
        device="python",
        dtype=None,
    ):
        if not isinstance(device, str) or not re.fullmatch(
            r"python|cpu|mps|cuda(?::[0-9]+)?", device
        ):
            raise ValueError("device must be python, cpu, mps, cuda or cuda:N")
        if device == "cuda":
            device = "cuda:0"
        dtype = (
            ("float32" if device == "mps" else "float64") if dtype is None else dtype
        )
        if dtype not in ("float32", "float64"):
            raise ValueError("dtype must be float32 or float64")
        if device == "python" and dtype != "float64":
            raise ValueError("The Python reference engine uses float64")
        if device == "mps" and dtype != "float32":
            raise ValueError("Metal (mps) requires float32; final checks use float64")
        config = {
            "device": device,
            "dtype": dtype,
            "seed": integer(seed, "seed"),
            "settle_budget": integer(settle_budget, "settle_budget"),
            "fan_in": None if fan_in is None else integer(fan_in, "fan_in", 1),
        }
        for name, value in (
            ("backtracks", backtracks),
            ("max_patches", max_patches),
            ("max_connections", max_connections),
            ("max_inputs", max_inputs),
        ):
            config[name] = integer(value, name, 1)
        for name, value in (
            ("initial_scale", initial_scale),
            ("tolerance", tolerance),
            ("state_prior", state_prior),
            ("parameter_prior", parameter_prior),
            ("state_bound", state_bound),
            ("parameter_bound", parameter_bound),
            ("step", step),
        ):
            config[name] = number(value, name, positive=True)
        if config["initial_scale"] > config["parameter_bound"]:
            raise ValueError("initial_scale must not exceed parameter_bound")
        self._config = MappingProxyType(config)
        self._nodes = {}
        self._inputs = []
        self._populations = []
        self._outputs = []
        self._built = False

    @property
    def config(self):
        """Read-only resolved construction and numerical configuration."""
        return self._config

    def _name(self, name, prefix):
        if self._built:
            raise ValueError("A built layout is frozen; create a new Cortex")
        if name is None:
            index = 1
            while f"{prefix}{index}" in self._nodes:
                index += 1
            name = f"{prefix}{index}"
        if not isinstance(name, str) or not name or len(name) > 256:
            raise ValueError("Names must be nonempty strings of at most 256 characters")
        try:
            name.encode("utf-8")
        except UnicodeEncodeError as error:
            raise ValueError("Names must be valid UTF-8 text") from error
        if name in self._nodes:
            raise ValueError(f"Duplicate layout name: {name}")
        return name

    def _sources(self, values, types):
        if isinstance(values, types):
            values = (values,)
        try:
            values = tuple(islice(values, len(self._nodes) + 1))
        except TypeError as error:
            raise ValueError("Connections require layout references") from error
        if len(values) > len(self._nodes):
            raise ValueError("Too many source references for this Cortex")
        for value in values:
            if (
                not isinstance(value, types)
                or not isinstance(value.name, str)
                or self._nodes.get(value.name) is not value
            ):
                raise ValueError(
                    "Connections must reference existing nodes in this Cortex"
                )
        if len(set(values)) != len(values):
            raise ValueError("Duplicate source reference")
        return values

    def input(self, name, *, shape):
        """Add a sensor with declared shape; samples stay fixed during a solve."""
        name, shape = self._name(name, "input"), _shape(shape)
        if (
            math.prod(shape) + sum(i.size for i in self._inputs)
            > self.config["max_inputs"]
        ):
            raise ValueError("Input sample budget exceeded")
        node = Input(name, shape)
        self._inputs.append(node)
        self._nodes[name] = node
        return node

    def _population(self, name, patches, inputs, observes):
        patches = integer(patches, "patches", 1)
        if (
            patches + sum(p.patches for p in self._populations)
            > self.config["max_patches"]
        ):
            raise ValueError("Processing patch budget exceeded")
        node = Population(name, patches, inputs, observes)
        self._populations.append(node)
        self._nodes[name] = node
        return node

    def column(self, name=None, *, patches, inputs=()):
        """Add processing patches reading sensor or represented data ports."""
        name = self._name(name, "column")
        inputs = self._sources(inputs, (Input, Population))
        return self._population(name, patches, inputs, ())

    def observer(self, name=None, *, patches, inputs=(), observes):
        """Add the same patches reading live states and exact prediction errors.

        Observed populations must already exist, so residual readback has an
        acyclic definition. Its energy feedback acts on lower populations in
        the same joint solve; it is not a post-processing mode switch.
        """
        name = self._name(name, "observer")
        inputs = self._sources(inputs, (Input, Population))
        observes = self._sources(observes, (Population,))
        if not observes:
            raise ValueError("An observer must observe at least one population")
        return self._population(name, patches, inputs, observes)

    def output(self, name, *, shape, reads, indices=None):
        """Expose selected patch coordinates; default indices start at zero."""
        name, shape = self._name(name, "output"), _shape(shape)
        (reads,) = self._sources((reads,), (Population,))
        count = math.prod(shape)
        if count > reads.patches:
            raise ValueError("Output size exceeds its source population")
        if indices is None:
            indices = tuple(range(count))
        else:
            try:
                indices = tuple(
                    integer(i, "output index") for i in islice(indices, count + 1)
                )
            except TypeError as error:
                raise ValueError(
                    "Output indices must be an integer sequence"
                ) from error
        if len(indices) != count or any(i >= reads.patches for i in indices):
            raise ValueError("Output indices do not match shape/source")
        if len(set(indices)) != len(indices):
            raise ValueError("Output indices must be distinct")
        node = Output(name, shape, reads, indices)
        self._outputs.append(node)
        self._nodes[name] = node
        return node

    def build(self):
        """Resolve declared wiring once and construct one jointly settling brain."""
        return self._compile(self.config["max_connections"])

    def _compile(self, edge_limit):
        if self._built or not self._populations or not self._outputs:
            raise ValueError(
                "Build requires an unbuilt layout with patches and outputs"
            )
        rng = random.Random(self.config["seed"])
        input_ranges, population_ranges = {}, {}
        n_inputs = n_patches = 0
        for source in self._inputs:
            input_ranges[source.name] = range(n_inputs, n_inputs + source.size)
            n_inputs += source.size
        for population in self._populations:
            population_ranges[population.name] = range(
                n_patches, n_patches + population.patches
            )
            n_patches += population.patches
        edges = []
        for population in self._populations:
            sources = [
                ("input" if isinstance(s, Input) else "state", s.name)
                for s in population.inputs
            ]
            sources += [
                (kind, s.name)
                for s in population.observes
                for kind in ("state", "residual")
            ]
            targets = population_ranges[population.name]
            for kind, name in dict.fromkeys(sources):
                ranges = input_ranges if kind == "input" else population_ranges
                indices = ranges[name]
                fan_in = len(indices)
                if self.config["fan_in"] is not None:
                    fan_in = min(
                        fan_in,
                        max(
                            self.config["fan_in"],
                            math.ceil(len(indices) / len(targets)),
                        ),
                    )
                if len(edges) + len(targets) * fan_in > edge_limit:
                    raise ValueError(
                        "Connection budget exceeded; use smaller populations, "
                        "an explicit sparse fan_in, or a higher max_connections"
                    )
                indices = list(indices)
                rng.shuffle(indices)
                for local_target, target in enumerate(targets):
                    for slot in range(fan_in):
                        source_index = indices[
                            (local_target * fan_in + slot) % len(indices)
                        ]
                        edges.append((kind, source_index, target))
        graph = _repair.Graph(n_inputs, n_patches, tuple(edges))
        scale = self.config["initial_scale"]
        weights = tuple(
            rng.uniform(-1.0, 1.0) * scale / math.sqrt(len(graph.incoming[t]))
            for _, _, t in edges
        )
        layout = {
            "inputs": [{"name": i.name, "shape": i.shape} for i in self._inputs],
            "populations": [
                {
                    "name": p.name,
                    "patches": p.patches,
                    "inputs": [s.name for s in p.inputs],
                    "observes": [s.name for s in p.observes],
                }
                for p in self._populations
            ],
            "outputs": [
                {
                    "name": o.name,
                    "shape": o.shape,
                    "reads": o.reads.name,
                    "indices": o.indices,
                }
                for o in self._outputs
            ],
        }
        brain = Brain(self, graph, weights, population_ranges, layout)
        self._built = True
        return brain
