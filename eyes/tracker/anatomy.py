"""The brains: the existing System 1 image brain and a hand-wired visual brain.

Both are one connectome settled by one ``NeuralGraph`` inside ``cadence.Brain``. The control
is ``Brain.build`` with an image input: retina, one ``visual_cortex`` stage, an association
region and the motor slots. The visual brain keeps the same population contract
(``visual/input``, ``association``, ``prefrontal``, ``motor``) and adds what the animal
reference suggests: several retinotopic stages in series, an optional retinotopic position
map with lateral coupling, topographic working memory and a topographic gaze readout.

Every projection between cortical populations is reciprocal, so a nudge on the gaze slots
reaches the earliest visual stage through the same settlement. The retina drives V1 one way,
as in ``visual_cortex``. Nothing is solved stage by stage.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
from cadence import Brain, Connectome, Learner

__all__ = ["Anatomy", "Stage", "build", "control", "describe", "freeze", "visual_connectome"]


@dataclass(frozen=True)
class Stage:
    """One retinotopic stage: feature maps reading a ``field``-square window of the stage below."""

    features: int
    field: int = 3
    stride: int = 1


@dataclass(frozen=True)
class Anatomy:
    """The declared wiring of a visual brain. Every designed constant is a gene."""

    size: int = 16
    bins: int = 8
    channels: int = 1  # retina channels per receptor, e.g. brightness and change
    stages: tuple[Stage, ...] = (Stage(8, 3, 1),)
    kernels: str = "local"  # "local": one efficacy per synapse; "tied": one per kernel entry
    sheet: int = 0  # side of a retinotopic position map; 0 keeps a dense association region
    hidden: int = 64  # association width when ``sheet`` is 0
    sheet_input: str = "dense"  # "dense" or "topographic" from the top visual stage
    reach: float = 1.5  # topographic reach, in units of the top stage's stride
    lateral: tuple[float, float, float] | None = None  # (excite, sigma in cells, inhibit)
    memory: str | None = "dense"  # working memory into the association: "dense", "topographic"
    memory_scale: float = 12.0
    memory_sigma: float = 1.0
    readout: str = "dense"  # gaze slots from the association: "dense" or "topographic"
    readout_weight: float = 0.5
    motor_lateral: float | None = None  # None follows Brain.build: -0.5 up to 8 bins, else 0
    init: float = 1.0
    density: float = 1.0

    def to_dict(self) -> dict:
        out = asdict(self)
        out["stages"] = [asdict(s) for s in self.stages]
        return out

    @staticmethod
    def from_dict(d: dict) -> Anatomy:
        d = dict(d)
        d["stages"] = tuple(Stage(**s) for s in d["stages"])
        if d.get("lateral") is not None:
            d["lateral"] = tuple(d["lateral"])
        return Anatomy(**d)


@dataclass
class _Wiring:
    """Synapse lists under construction, with an optional tie group per synapse."""

    n: int = 0
    populations: dict[str, range] = field(default_factory=dict)
    pre: list[np.ndarray] = field(default_factory=list)
    post: list[np.ndarray] = field(default_factory=list)
    value: list[np.ndarray] = field(default_factory=list)
    tie: list[np.ndarray] = field(default_factory=list)
    groups: int = 0

    def add_population(self, name: str, size: int) -> range:
        span = range(self.n, self.n + size)
        self.populations[name] = span
        self.n += size
        return span

    def connect(self, pre, post, value, *, reciprocal: bool, tie=None) -> None:
        pre, post = np.asarray(pre, np.int64).ravel(), np.asarray(post, np.int64).ravel()
        value = np.asarray(value, float).ravel()
        tie = np.full(pre.size, -1, np.int64) if tie is None else np.asarray(tie, np.int64).ravel()
        self.pre.append(pre)
        self.post.append(post)
        self.value.append(value)
        self.tie.append(tie)
        if reciprocal:
            self.pre.append(post)
            self.post.append(pre)
            self.value.append(value)
            self.tie.append(np.full(pre.size, -1, np.int64))

    def fresh_groups(self, count: int) -> int:
        start = self.groups
        self.groups += count
        return start


def _fan(rng, size, fan_in, fan_out, scale=1.0, sign=0.0):
    """Library convention: magnitudes U(0, sqrt(6/(in+out))) times scale, sign with mean ``sign``."""
    magnitude = rng.uniform(0.0, 1.0, size) * np.sqrt(6.0 / (fan_in + fan_out)) * scale
    positive = rng.random(size) < (1.0 + sign) / 2.0
    return np.where(positive, magnitude, -magnitude)


def _grid(stages: tuple[Stage, ...], size: int) -> list[tuple[int, float, float]]:
    """Side, stride and first receptive-field centre (in pixels) of every stage."""
    out = []
    side, stride, first = size, 1.0, 0.5
    for st in stages:
        new_side = (side - st.field) // st.stride + 1
        if new_side < 1:
            raise ValueError("a stage's field does not fit the stage below")
        first = first + (st.field - 1) / 2 * stride
        stride = stride * st.stride
        side = new_side
        out.append((side, stride, first))
    return out


def visual_connectome(anatomy: Anatomy, seed: int = 0) -> tuple[Connectome, np.ndarray | None]:
    """Develop the declared anatomy into one connectome and its tie groups (or None)."""
    a = anatomy
    rng = np.random.default_rng(seed)
    w = _Wiring()
    retina = w.add_population("visual/input", a.channels * a.size * a.size)
    grids = _grid(a.stages, a.size)
    stage_spans = []
    for k, (st, (side, _, _)) in enumerate(zip(a.stages, grids, strict=True)):
        stage_spans.append(w.add_population(f"visual/v{k + 1}", st.features * side * side))
    visual_end = w.n
    assoc_size = a.sheet * a.sheet if a.sheet else a.hidden
    assoc = w.add_population("association", assoc_size)
    prefrontal = w.add_population("prefrontal", assoc_size) if a.memory else None
    motor = w.add_population("motor", 2 * a.bins)
    w.populations["visual"] = range(0, visual_end)

    # Serial retinotopic stages with local windows.
    below_start, below_side, below_channels = retina.start, a.size, a.channels
    for k, (st, (side, _, _)) in enumerate(zip(a.stages, grids, strict=True)):
        f, y, x, dy, dx, c = np.meshgrid(
            np.arange(st.features), np.arange(side), np.arange(side),
            np.arange(st.field), np.arange(st.field), np.arange(below_channels), indexing="ij",
        )
        # The stage below is laid out map by map: index = (channel * side + row) * side + col.
        pre = below_start + (c * below_side + (y * st.stride + dy)) * below_side + (x * st.stride + dx)
        post = stage_spans[k].start + (f * side + y) * side + x
        fan_in = below_channels * st.field * st.field
        fan_out = st.features * st.field * st.field
        if a.kernels == "tied":
            entry = ((f * st.field + dy) * st.field + dx) * below_channels + c
            base = w.fresh_groups(st.features * st.field * st.field * below_channels)
            kernel = _fan(rng, entry.max() + 1, fan_in, fan_out, a.init)
            value, tie = kernel[entry], base + entry
        else:
            value, tie = _fan(rng, pre.size, fan_in, fan_out, a.init), None
        w.connect(pre, post, value, reciprocal=k > 0, tie=tie)
        below_start, below_side, below_channels = stage_spans[k].start, side, st.features

    # The top visual stage reaches the association region.
    top, (top_side, top_stride, top_first) = stage_spans[-1], grids[-1]
    top_maps = a.stages[-1].features
    if a.sheet and a.sheet_input == "topographic":
        cell = a.size / a.sheet
        f, y, x, i, j = np.meshgrid(
            np.arange(top_maps), np.arange(top_side), np.arange(top_side),
            np.arange(a.sheet), np.arange(a.sheet), indexing="ij",
        )
        ux, uy = top_first + x * top_stride, top_first + y * top_stride
        sx, sy = (j + 0.5) * cell, (i + 0.5) * cell
        near = np.maximum(np.abs(ux - sx), np.abs(uy - sy)) <= a.reach * top_stride
        pre = top.start + ((f * top_side + y) * top_side + x)[near]
        post = assoc.start + (i * a.sheet + j)[near]
        per_cell = max(int(near.sum()) // assoc_size, 1)
        if a.kernels == "tied":
            # One shared kernel per map and relative offset (in half pixels): every map
            # position reads its neighbourhood with the same learned weights.
            key = np.stack([f[near], np.round(2 * (uy - sy)[near]).astype(int),
                            np.round(2 * (ux - sx)[near]).astype(int)], axis=1)
            _, entry = np.unique(key, axis=0, return_inverse=True)
            entry = entry.ravel()
            base = w.fresh_groups(int(entry.max()) + 1)
            kernel = _fan(rng, int(entry.max()) + 1, per_cell, per_cell)
            w.connect(pre, post, kernel[entry], reciprocal=True, tie=base + entry)
        else:
            w.connect(pre, post, _fan(rng, pre.size, per_cell, per_cell), reciprocal=True)
    else:
        pre, post = np.meshgrid(np.array(top), np.array(assoc), indexing="ij")
        keep = rng.random(pre.shape) < a.density
        w.connect(pre[keep], post[keep], _fan(rng, int(keep.sum()), len(top), len(assoc)),
                  reciprocal=True)

    # Lateral coupling inside a retinotopic map: local excitation, broad inhibition.
    if a.sheet and a.lateral is not None:
        excite, sigma, inhibit = a.lateral
        i, j = np.divmod(np.arange(assoc_size), a.sheet)
        d2 = (i[:, None] - i[None, :]) ** 2 + (j[:, None] - j[None, :]) ** 2
        weight = excite * np.exp(-d2 / (2 * sigma * sigma)) - inhibit
        pre, post = np.nonzero((d2 > 0) & (weight != 0))
        # Symmetric pairs are listed in both directions already.
        w.connect(assoc.start + pre, assoc.start + post, weight[pre, post], reciprocal=False)

    # Working memory returns to the association region.
    if prefrontal is not None:
        if a.memory == "topographic" and a.sheet:
            # Centre-surround and balanced: a uniform trace adds nothing, a remembered bump
            # raises its own place against the rest of the map.
            i, j = np.divmod(np.arange(assoc_size), a.sheet)
            d2 = (i[:, None] - i[None, :]) ** 2 + (j[:, None] - j[None, :]) ** 2
            weight = np.exp(-d2 / (2 * a.memory_sigma ** 2))
            weight = weight - weight.mean(axis=1, keepdims=True)
            weight = a.memory_scale * weight / weight.max()
            pre, post = np.nonzero(np.abs(weight) > 1e-9)
            w.connect(prefrontal.start + pre, assoc.start + post, weight[pre, post],
                      reciprocal=False)
        else:
            pre, post = np.meshgrid(np.array(prefrontal), np.array(assoc), indexing="ij")
            w.connect(pre, post, _fan(rng, pre.size, assoc_size, assoc_size, a.memory_scale),
                      reciprocal=False)

    # Gaze slots: x bins then y bins, reciprocal with the association region.
    if a.readout == "topographic" and a.sheet:
        # Balanced: each gaze neuron is excited by the map cells of its own bin and inhibited
        # equally by all others, so uniform map activity drives no slot and the excitatory
        # loop through the map cannot run away.
        i, j = np.divmod(np.arange(assoc_size), a.sheet)
        cells = np.arange(assoc_size)
        for offset, own in ((0, (j * a.bins) // a.sheet), (a.bins, (i * a.bins) // a.sheet)):
            b = np.arange(a.bins)
            cell, gaze = np.meshgrid(cells, b, indexing="ij")
            members = np.bincount(own, minlength=a.bins)[gaze]
            others = assoc_size - members
            weight = np.where(own[cell] == gaze, a.readout_weight,
                              -a.readout_weight * members / others)
            w.connect(assoc.start + cell, motor.start + offset + gaze, weight, reciprocal=True)
    else:
        pre, post = np.meshgrid(np.array(assoc), np.array(motor), indexing="ij")
        w.connect(pre, post, _fan(rng, pre.size, assoc_size, len(motor)), reciprocal=True)
    lateral = a.motor_lateral
    if lateral is None:
        lateral = -0.5 if a.bins <= 8 else 0.0
    if lateral:
        for start in (motor.start, motor.start + a.bins):
            idx = np.arange(start, start + a.bins)
            pre, post = np.meshgrid(idx, idx, indexing="ij")
            keep = pre != post
            w.connect(pre[keep], post[keep], np.full(int(keep.sum()), lateral), reciprocal=False)

    pre, post = np.concatenate(w.pre), np.concatenate(w.post)
    value, tie = np.concatenate(w.value), np.concatenate(w.tie)
    connectome = Connectome.from_synapses(
        w.n, pre=pre, post=post, sign=value, populations=w.populations,
        label=f"object-tracker:{a.size}px:{len(a.stages)}stages:{a.kernels}",
    )
    if a.kernels != "tied":
        return connectome, None
    # from_synapses sorts and merges; recover each synapse's group by its (pre, post) key.
    key = post * w.n + pre
    order = np.argsort(key)
    found = np.searchsorted(key[order], connectome.post * w.n + connectome.pre)
    groups = tie[order][found]
    return connectome, groups


def tie_rates(connectome: Connectome, groups: np.ndarray, rule: str) -> np.ndarray | None:
    """Per-synapse step multipliers for tied kernels.

    A tie group moves by the mean of its members' contrasts; a convolution's gradient is their
    sum. ``sum`` multiplies each member's step by its group's size (counting reciprocal
    partners), which restores the summed step; ``sqrt`` by the square root of that size;
    ``mean`` keeps the library's rule (no multiplier).
    """
    if rule == "mean":
        return None
    key = connectome.post.astype(np.int64) * connectome.n + connectome.pre
    reverse_key = connectome.pre.astype(np.int64) * connectome.n + connectome.post
    order = np.argsort(key)
    hit = np.searchsorted(key[order], reverse_key)
    hit = np.minimum(hit, len(key) - 1)
    has_reverse = key[order][hit] == reverse_key
    reverse = np.where(has_reverse, order[hit], -1)
    tied = groups >= 0
    counts = np.bincount(groups[tied], minlength=int(groups.max()) + 1).astype(float)
    reciprocal = np.zeros(len(counts), dtype=bool)
    reciprocal[groups[tied & (reverse >= 0)]] = True
    size = counts * np.where(reciprocal, 2.0, 1.0)
    member = np.full(connectome.synapses, -1, dtype=np.int64)
    member[tied] = groups[tied]
    partners = reverse[tied]
    member[partners[partners >= 0]] = groups[tied][partners >= 0]
    rate = np.ones(connectome.synapses)
    scale = size if rule == "sum" else np.sqrt(size)
    rate[member >= 0] = scale[member[member >= 0]]
    return rate


def build(
    anatomy: Anatomy,
    *,
    seed: int = 0,
    trace: tuple[float, float] | None = (1.0, 0.8),
    tie_rate: str = "mean",
    **options,
) -> Brain:
    """One continuing System 1 brain on the declared anatomy.

    ``trace`` is (amplitude, decay) of the working trace when the anatomy has memory.
    ``options`` go to ``cadence.Brain``. Tied kernels install a learner with tie groups (and,
    for ``tie_rate`` other than ``mean``, per-synapse step multipliers) on the brain's own
    configuration, the same swap ``Brain.load`` performs.
    """
    connectome, groups = visual_connectome(anatomy, seed)
    if anatomy.memory and trace is not None:
        options.setdefault("working_memory_amplitude", trace[0])
        options.setdefault("working_memory_decay", trace[1])
    brain = Brain(connectome, seed=seed, slots=(anatomy.bins, anatomy.bins), **options)
    if anatomy.memory and trace is None:
        brain.working_memory = None
    if groups is not None:
        learner = Learner(
            brain.brain, list(brain.motor_index), brain.learner.config,
            tie_groups=groups, synapse_rate=tie_rates(connectome, groups, tie_rate),
            slots=[anatomy.bins, anatomy.bins],
        )
        brain.learner = learner
        brain.basal_ganglia.learner = learner
    return brain


def control(
    size: int, bins: int, *, seed: int = 0, hidden: int = 64,
    trace: tuple[float, float] | None = (1.0, 0.8), features: int = 8, field: int = 3,
    lateral: float | None = None, **options,
) -> Brain:
    """The existing System 1 image brain, ``Brain.build``, with x/y gaze slots."""
    if trace is not None:
        options.setdefault("working_memory_amplitude", trace[0])
        options.setdefault("working_memory_decay", trace[1])
    return Brain.build(
        (size, size), 2 * bins, slots=(bins, bins), hidden=hidden, lateral=lateral,
        working_memory=trace is not None, features=features, field=field, seed=seed, **options,
    )


def freeze(brain: Brain, pairs: tuple[tuple[str, str], ...]) -> Brain:
    """Keep the synapses between the named populations fixed: designed wiring, not learned.

    Installs a learner with a plastic-synapse mask on the brain's own configuration, tie
    groups and slots; ``Brain.load`` restores the mask from the checkpoint.
    """
    c = brain.connectome
    fixed = np.zeros(c.synapses, dtype=bool)
    for a, b in pairs:
        fixed |= np.isin(c.pre, np.asarray(c.populations[a])) & np.isin(
            c.post, np.asarray(c.populations[b]))
    old = brain.learner
    learner = Learner(
        brain.brain, list(brain.motor_index), old.config, plastic_synapses=~fixed,
        tie_groups=old.tie_groups, synapse_rate=old.synapse_rate,
        slots=[int(k) for k in old.slot_sizes],
    )
    brain.learner = learner
    brain.basal_ganglia.learner = learner
    return brain


def describe(brain: Brain) -> dict:
    """Population sizes and synapse counts of a brain."""
    c = brain.connectome
    pops = {k: len(v) for k, v in c.populations.items()}
    return {"neurons": int(c.n), "synapses": int(c.synapses), "populations": pops}
