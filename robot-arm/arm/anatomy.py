"""One nervous system from the retinas to the joints, as one connectome settled by one graph.

The wiring follows the Eyes demo's visual brain and adds the body: a ``sensory`` population
holding the retinas and the body senses, a tied retinotopic V1 stage over the retinas, a
retinotopic map read topographically from V1, a dense association region that also hears the
body, a prefrontal trace returning to it, and one ``motor`` population grouped into slots: the
eye's readouts (what it is taught to see) and the motor pools (yaw, shoulder, elbow, wrist,
gripper). Every cortical projection is reciprocal, so a nudge on any slot reaches V1 through
the same settlement. The retinas and the body drive the cortex one way.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

import numpy as np
from cadence import Brain, Connectome, Learner

from .world import BODY_SENSES, POSITION_BINS

__all__ = ["Anatomy", "Stage", "EYE_SLOTS", "MOTOR_SLOTS", "build", "connectome_of", "describe", "freeze", "raising_config"]

EYE_SLOTS = (POSITION_BINS, POSITION_BINS, POSITION_BINS, POSITION_BINS, 2, 3)  # block x, y; hand x, y; held; order
MOTOR_SLOTS = (5, 5, 5, 5, 2)  # yaw, shoulder, elbow, wrist levels (two down to two up); gripper open/closed


@dataclass(frozen=True)
class Stage:
    features: int
    field: int = 5
    stride: int = 2


@dataclass(frozen=True)
class Anatomy:
    """The declared wiring. Every designed constant is a gene."""

    size: int = 40
    channels: int = 2
    eyes: int = 1  # how many eyes the channels come from, kind-major: every eye's brightness, then every eye's red
    eye_streams: bool = False  # with two eyes: one V1 per eye; the maps read the first eye's, the second's feeds the association
    priors: bool = False  # innate colour wiring: V1 feature pairs born on one cone each, maps born on one feature pair each
    depth_map: bool = False  # with eye streams: the second eye's V1 feeds a map of its own into the association, not a dense projection
    body: int = BODY_SENSES
    stages: tuple[Stage, ...] = (Stage(8, 5, 2),)
    kernels: str = "tied"
    sheet: int = 18  # side of the retinotopic maps; 0 wires V1 densely to the association
    sheets: int = 1  # maps read from V1: with 3, one each for the block, the hand and the lamps
    reach: float = 1.5  # map cells read V1 positions within this many strides
    lateral: tuple[float, float, float] | None = None  # map coupling: (excite, sigma, inhibit)
    readout: str = "dense"  # "dense": every slot from the association; "topographic": positions from their map
    readout_weight: float = 0.5
    readout_reciprocal: bool = True  # topographic readouts also feed their map back (the Eyes demo); False reads one way
    map_input_reciprocal: bool = True  # the maps also feed V1 back (the Eyes demo); False reads V1 one way
    map_reciprocal: bool = True  # maps and association coupled both ways, or the maps driving it forward
    map_density: float = 1.0  # share of map-to-association synapses kept
    hidden: int = 256
    deep: tuple[int, ...] = ()  # further association regions between the association and the slots, each reciprocal with the one below
    memory: bool = True
    memory_scale: float = 1.2
    slots: tuple[int, ...] = EYE_SLOTS + MOTOR_SLOTS
    motor_lateral: float | None = None  # None: -0.5 in slots of at most 8, else 0
    init: float = 1.0
    body_scale: float = 1.0

    @property
    def retina(self) -> int:
        return self.channels * self.size * self.size

    def to_dict(self) -> dict:
        out = asdict(self)
        out["stages"] = [asdict(s) for s in self.stages]
        out["deep"] = list(self.deep)
        return out


class _Wiring:
    def __init__(self) -> None:
        self.n = 0
        self.populations: dict[str, range] = {}
        self.pre: list[np.ndarray] = []
        self.post: list[np.ndarray] = []
        self.value: list[np.ndarray] = []
        self.tie: list[np.ndarray] = []
        self.groups = 0

    def add(self, name: str, size: int) -> range:
        span = range(self.n, self.n + size)
        self.populations[name] = span
        self.n += size
        return span

    def connect(self, pre, post, value, *, reciprocal: bool, tie=None) -> None:
        pre = np.asarray(pre, np.int64).ravel()
        post = np.asarray(post, np.int64).ravel()
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

    def fresh(self, count: int) -> int:
        start = self.groups
        self.groups += count
        return start


def _fan(rng, size, fan_in, fan_out, scale=1.0):
    magnitude = rng.uniform(0.0, 1.0, size) * np.sqrt(6.0 / (fan_in + fan_out)) * scale
    return np.where(rng.random(size) < 0.5, magnitude, -magnitude)


def _grid(stages: tuple[Stage, ...], size: int) -> list[tuple[int, float, float]]:
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


def connectome_of(a: Anatomy, seed: int = 0) -> tuple[Connectome, np.ndarray | None]:
    """Develop the anatomy into one connectome and its tie groups (None without tied kernels)."""
    rng = np.random.default_rng(seed)
    w = _Wiring()
    sensory = w.add("sensory", a.retina + a.body)
    retina_start, body_start = sensory.start, sensory.start + a.retina
    grids = _grid(a.stages, a.size)
    stage_spans = [w.add(f"visual/v{k + 1}", st.features * side * side)
                   for k, (st, (side, _, _)) in enumerate(zip(a.stages, grids, strict=True))]
    sheets = [w.add("visual/map" if k == 0 else f"visual/map{k}", a.sheet * a.sheet) for k in range(a.sheets)] if a.sheet else []
    sheet = sheets[0] if sheets else None
    assoc = w.add("association", a.hidden)
    prefrontal = w.add("prefrontal", a.hidden) if a.memory else None
    deeper = [w.add(f"association{k + 2}", width) for k, width in enumerate(a.deep)]
    motor = w.add("motor", int(sum(a.slots)))

    def stage(span: range, st: Stage, side: int, below_start: int, below_side: int, channel_index: np.ndarray,
              reciprocal: bool, kind_of: np.ndarray | None = None) -> None:
        """One retinotopic stage reading ``channel_index`` of the layer below, map by map. With
        priors, ``kind_of`` names each channel's kind (0 brightness, 1 red, 2 green, 3 blue) and
        feature pair k is born reading cone k + 1 alone, positively; the rest read brightness."""
        below_channels = len(channel_index)
        f, y, x, dy, dx, c = np.meshgrid(
            np.arange(st.features), np.arange(side), np.arange(side),
            np.arange(st.field), np.arange(st.field), np.arange(below_channels), indexing="ij",
        )
        pre = below_start + (channel_index[c] * below_side + (y * st.stride + dy)) * below_side + (x * st.stride + dx)
        post = span.start + (f * side + y) * side + x
        fan_in = below_channels * st.field * st.field
        fan_out = st.features * st.field * st.field
        if a.kernels == "tied":
            entry = ((f * st.field + dy) * st.field + dx) * below_channels + c
            base = w.fresh(int(entry.max()) + 1)
            kernel = _fan(rng, int(entry.max()) + 1, fan_in, fan_out, a.init)
            if kind_of is not None:
                ef, edy, edx, ec = np.meshgrid(np.arange(st.features), np.arange(st.field), np.arange(st.field),
                                               np.arange(below_channels), indexing="ij")
                wanted = np.minimum(ef // 2 + 1, 3)  # feature pairs 0, 1, 2 want cones 1, 2, 3; later pairs brightness
                wanted = np.where(ef // 2 >= 3, 0, wanted)
                own = kind_of[ec] == wanted
                prior = np.where(own, np.abs(kernel[((ef * st.field + edy) * st.field + edx) * below_channels + ec]) * 2.0, 0.0)
                kernel = prior.reshape(-1)[np.argsort((((ef * st.field + edy) * st.field + edx) * below_channels + ec).reshape(-1))]
            w.connect(pre, post, kernel[entry], reciprocal=reciprocal, tie=base + entry)
        else:
            w.connect(pre, post, _fan(rng, pre.size, fan_in, fan_out, a.init), reciprocal=reciprocal)

    streams = a.eye_streams and a.eyes > 1
    if streams and len(a.stages) != 1:
        raise ValueError("eye streams take one stage")
    kinds = a.channels // a.eyes
    if streams and kinds * a.eyes != a.channels:
        raise ValueError("channels must be the eyes' kinds times the eyes")
    if streams:
        # The first eye's stream is V1 proper; the other eyes get their own stage each.
        st, (side, _, _) = a.stages[0], grids[0]
        for e in range(1, a.eyes):
            stage_spans.append(w.add(f"visual/v1r{e if e > 1 else ''}", st.features * side * side))
        for e in range(a.eyes):
            channel_index = np.array([k * a.eyes + e for k in range(kinds)])
            kind_of = np.arange(kinds) if a.priors else None
            stage(stage_spans[e], st, side, retina_start, a.size, channel_index, reciprocal=False, kind_of=kind_of)
    else:
        below_start, below_side, channel_index = retina_start, a.size, np.arange(a.channels)
        for k, (st, (side, _, _)) in enumerate(zip(a.stages, grids, strict=True)):
            kind_of = (np.arange(a.channels) // a.eyes) if (a.priors and k == 0) else None
            stage(stage_spans[k], st, side, below_start, below_side, channel_index, reciprocal=k > 0, kind_of=kind_of)
            below_start, below_side, channel_index = stage_spans[k].start, side, np.arange(st.features)

    top, (top_side, top_stride, top_first) = (stage_spans[0], grids[0]) if streams else (stage_spans[-1], grids[-1])
    top_maps = a.stages[0].features if streams else a.stages[-1].features
    if streams and not a.depth_map:
        for span in stage_spans[1:]:
            pre, post = np.meshgrid(np.array(span), np.array(assoc), indexing="ij")
            keep = rng.random(pre.shape) < a.map_density
            w.connect(pre[keep], post[keep], _fan(rng, int(keep.sum()), len(span), len(assoc)), reciprocal=False)
    depth_spans = [w.add(f"visual/depth{e if e > 1 else ''}", a.sheet * a.sheet) for e in range(1, a.eyes)] if (streams and a.depth_map and a.sheet) else []
    if sheet is not None:
        cell = a.size / a.sheet
        f, y, x, i, j = np.meshgrid(
            np.arange(top_maps), np.arange(top_side), np.arange(top_side),
            np.arange(a.sheet), np.arange(a.sheet), indexing="ij",
        )
        ux, uy = top_first + x * top_stride, top_first + y * top_stride
        sx, sy = (j + 0.5) * cell, (i + 0.5) * cell
        near = np.maximum(np.abs(ux - sx), np.abs(uy - sy)) <= a.reach * top_stride
        pre_v = top.start + ((f * top_side + y) * top_side + x)[near]
        cells = (i * a.sheet + j)[near]
        per_cell = max(int(near.sum()) // (a.sheet * a.sheet), 1)
        key = np.stack([f[near], np.round(2 * (uy - sy)[near]).astype(int), np.round(2 * (ux - sx)[near]).astype(int)], axis=1)
        _, entry = np.unique(key, axis=0, return_inverse=True)
        entry = entry.ravel()
        for m, span in enumerate(sheets):  # each map reads V1 with its own kernels, so maps can specialize
            post = span.start + cells
            if a.kernels == "tied":
                base = w.fresh(int(entry.max()) + 1)
                kernel = _fan(rng, int(entry.max()) + 1, per_cell, per_cell)
                if a.priors:
                    feature_of_entry = np.zeros(int(entry.max()) + 1, dtype=np.int64)
                    feature_of_entry[entry] = f[near]
                    kernel = np.where(feature_of_entry // 2 == m, np.abs(kernel) * 2.0, 0.0)
                w.connect(pre_v, post, kernel[entry], reciprocal=a.map_input_reciprocal, tie=base + entry)
            else:
                w.connect(pre_v, post, _fan(rng, pre_v.size, per_cell, per_cell), reciprocal=a.map_input_reciprocal)
            if a.lateral is not None:
                excite, sigma, inhibit = a.lateral
                ii, jj = np.divmod(np.arange(len(span)), a.sheet)
                d2 = (ii[:, None] - ii[None, :]) ** 2 + (jj[:, None] - jj[None, :]) ** 2
                weight = excite * np.exp(-d2 / (2 * sigma * sigma)) - inhibit
                pre_l, post_l = np.nonzero((d2 > 0) & (weight != 0))
                w.connect(span.start + pre_l, span.start + post_l, weight[pre_l, post_l], reciprocal=False)
            pre, post = np.meshgrid(np.array(span), np.array(assoc), indexing="ij")
            keep = rng.random(pre.shape) < a.map_density
            w.connect(pre[keep], post[keep], _fan(rng, int(keep.sum()), len(span), len(assoc)), reciprocal=a.map_reciprocal)
    else:
        pre, post = np.meshgrid(np.array(top), np.array(assoc), indexing="ij")
        w.connect(pre, post, _fan(rng, pre.size, len(top), len(assoc)), reciprocal=True)

    for e, span in enumerate(depth_spans, start=1):
        other = stage_spans[e]
        pre_d = other.start + ((f * top_side + y) * top_side + x)[near]
        post_d = span.start + cells
        base = w.fresh(int(entry.max()) + 1)
        kernel = _fan(rng, int(entry.max()) + 1, per_cell, per_cell)
        if a.priors:
            feature_of_entry = np.zeros(int(entry.max()) + 1, dtype=np.int64)
            feature_of_entry[entry] = f[near]
            kernel = np.where(feature_of_entry // 2 == 0, np.abs(kernel) * 2.0, 0.0)  # the block's pair: depth of the block
        w.connect(pre_d, post_d, kernel[entry], reciprocal=False, tie=base + entry)
        pre, post = np.meshgrid(np.array(span), np.array(assoc), indexing="ij")
        keep = rng.random(pre.shape) < a.map_density
        w.connect(pre[keep], post[keep], _fan(rng, int(keep.sum()), len(span), len(assoc)), reciprocal=False)

    body = np.arange(body_start, body_start + a.body)
    pre, post = np.meshgrid(body, np.array(assoc), indexing="ij")
    w.connect(pre, post, _fan(rng, pre.size, a.body, len(assoc), a.body_scale), reciprocal=False)

    if prefrontal is not None:
        pre, post = np.meshgrid(np.array(prefrontal), np.array(assoc), indexing="ij")
        w.connect(pre, post, _fan(rng, pre.size, len(assoc), len(assoc), a.memory_scale), reciprocal=False)

    offsets = np.concatenate([[0], np.cumsum(a.slots)])[:-1] + motor.start
    if a.readout == "topographic" and sheets:
        # Block x, y from the first map and hand x, y from the second (or the first when there
        # is one): each readout neuron is excited by the map cells of its own bin and inhibited
        # equally by all others, so uniform map activity drives no slot.
        source = {0: sheets[0], 1: sheets[0], 2: sheets[min(1, len(sheets) - 1)], 3: sheets[min(1, len(sheets) - 1)]}
        for slot_index, span in source.items():
            bins = a.slots[slot_index]
            ii, jj = np.divmod(np.arange(len(span)), a.sheet)
            own = (jj * bins) // a.sheet if slot_index % 2 == 0 else (ii * bins) // a.sheet
            cell, gaze = np.meshgrid(np.arange(len(span)), np.arange(bins), indexing="ij")
            members = np.bincount(own, minlength=bins)[gaze]
            others = len(span) - members
            weight = np.where(own[cell] == gaze, a.readout_weight, -a.readout_weight * members / others)
            w.connect(span.start + cell, offsets[slot_index] + gaze, weight, reciprocal=a.readout_reciprocal)
        dense_slots = [k for k in range(len(a.slots)) if k not in source]
        if len(sheets) >= 3 and len(a.slots) > 5:  # the order lamp readout also hears the third map directly
            lamp_neurons = np.arange(offsets[5], offsets[5] + a.slots[5])
            pre, post = np.meshgrid(np.array(sheets[2]), lamp_neurons, indexing="ij")
            w.connect(pre, post, _fan(rng, pre.size, len(sheets[2]), len(lamp_neurons)), reciprocal=a.readout_reciprocal)
    else:
        dense_slots = list(range(len(a.slots)))
    below = assoc
    for region in deeper:  # each deeper region hears the one below and answers it
        pre, post = np.meshgrid(np.array(below), np.array(region), indexing="ij")
        w.connect(pre, post, _fan(rng, pre.size, len(below), len(region)), reciprocal=True)
        below = region
    if dense_slots:
        dense_neurons = np.concatenate([np.arange(offsets[k], offsets[k] + a.slots[k]) for k in dense_slots])
        pre, post = np.meshgrid(np.array(below), dense_neurons, indexing="ij")
        w.connect(pre, post, _fan(rng, pre.size, len(below), len(dense_neurons)), reciprocal=True)
    offset = motor.start
    for size in a.slots:
        lateral = a.motor_lateral
        if lateral is None:
            lateral = -0.5 if size <= 8 else 0.0
        if lateral:
            idx = np.arange(offset, offset + size)
            pre, post = np.meshgrid(idx, idx, indexing="ij")
            keep = pre != post
            w.connect(pre[keep], post[keep], np.full(int(keep.sum()), lateral), reciprocal=False)
        offset += size

    pre, post = np.concatenate(w.pre), np.concatenate(w.post)
    value, tie = np.concatenate(w.value), np.concatenate(w.tie)
    connectome = Connectome.from_synapses(
        w.n, pre=pre, post=post, sign=value, populations=w.populations,
        label=f"arm-with-eyes:{a.channels}x{a.size}px:{a.kernels}:{a.sheets}maps:{a.readout}{':streams' if streams else ''}{':priors' if a.priors else ''}",
    )
    if a.kernels != "tied":
        return connectome, None
    key = post * w.n + pre
    order = np.argsort(key)
    found = np.searchsorted(key[order], connectome.post * w.n + connectome.pre)
    return connectome, tie[order][found]


def tie_rates(connectome: Connectome, groups: np.ndarray, rule: str) -> np.ndarray | None:
    """Per-synapse step multipliers so a tied kernel steps by the sum of its members' contrasts."""
    if rule == "mean":
        return None
    key = connectome.post.astype(np.int64) * connectome.n + connectome.pre
    reverse_key = connectome.pre.astype(np.int64) * connectome.n + connectome.post
    order = np.argsort(key)
    hit = np.minimum(np.searchsorted(key[order], reverse_key), len(key) - 1)
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


def build(anatomy: Anatomy, *, seed: int = 0, trace: tuple[float, float] | None = (3.0, 0.0),
          tie_rate: str = "sum", **options) -> Brain:
    """One continuing brain on the anatomy. ``trace`` is (amplitude, decay) of the working
    trace; ``options`` go to ``cadence.Brain`` (the episodic memory, arousal, rates)."""
    connectome, groups = connectome_of(anatomy, seed)
    if anatomy.memory and trace is not None:
        options.setdefault("working_memory_amplitude", trace[0])
        options.setdefault("working_memory_decay", trace[1])
    brain = Brain(connectome, seed=seed, slots=list(anatomy.slots), **options)
    if anatomy.memory and trace is None:
        brain.working_memory = None
    if groups is not None:
        learner = Learner(brain.brain, list(brain.motor_index), brain.learner.config,
                          tie_groups=groups, synapse_rate=tie_rates(connectome, groups, tie_rate),
                          slots=list(anatomy.slots))
        brain.learner = learner
        brain.basal_ganglia.learner = learner
    return brain


def raising_config(brain: Brain, eta: float = 0.1, decay: float = 0.0, scale_cap: float | None = None) -> None:
    """The Eyes demo's raising settings: a plain step, no momentum, a quadratic nudge; optional
    weight decay per update and a lower efficacy cap, both genes against runaway loops."""
    extra = {} if scale_cap is None else {"scale_cap": float(scale_cap)}
    if decay or hasattr(brain.learner.config, "decay"):  # 0.84 removed the weight decay gene
        extra["decay"] = float(decay)
    brain.learner.config = replace(brain.learner.config, eta=eta, eta_bias=None, momentum=0.0,
                                   nudge="quadratic", **extra)


def freeze(brain: Brain, pairs: tuple[tuple[str, str], ...]) -> Brain:
    """Keep the synapses between the named populations fixed from now on."""
    c = brain.connectome
    fixed = np.zeros(c.synapses, dtype=bool)
    for a, b in pairs:
        fixed |= np.isin(c.pre, np.asarray(c.populations[a])) & np.isin(c.post, np.asarray(c.populations[b]))
    old = brain.learner
    learner = Learner(brain.brain, list(brain.motor_index), old.config, plastic_synapses=~fixed,
                      tie_groups=old.tie_groups, synapse_rate=old.synapse_rate,
                      slots=[int(k) for k in old.slot_sizes])
    brain.learner = learner
    brain.basal_ganglia.learner = learner
    return brain


VISUAL_PATHWAY = (("sensory", "visual/v1"), ("visual/v1", "visual/map"), ("visual/map", "visual/v1"))


def describe(brain: Brain) -> dict:
    c = brain.connectome
    return {"neurons": int(c.n), "synapses": int(c.synapses),
            "populations": {k: len(v) for k, v in c.populations.items()}}


def pathway_masks(brain: Brain) -> tuple[np.ndarray, np.ndarray]:
    """The visual pathway's synapses and the rest. The pathway is the retina into V1, V1 and
    the maps among themselves, and the maps to and from the eye's readouts: what the eye is
    raised on. The rest is the body and the maps into the association, the trace, and the
    association to and from every slot: what the pools are raised on."""
    c = brain.connectome
    pops = c.populations
    visual = np.concatenate([np.asarray(v, dtype=np.int64) for k, v in pops.items() if k.startswith("visual/")])
    sensory = np.asarray(pops["sensory"], dtype=np.int64)
    eye = np.asarray(pops["motor"], dtype=np.int64)[: int(sum(EYE_SLOTS))]
    pre_v, post_v = np.isin(c.pre, visual), np.isin(c.post, visual)
    pathway = (np.isin(c.pre, sensory) & post_v) | (pre_v & post_v) | (pre_v & np.isin(c.post, eye)) | (np.isin(c.pre, eye) & post_v)
    return pathway, ~pathway


def share_graph(brain: Brain, learner: Learner) -> None:
    """Hand the eye learner's updated graph to the brain's own learner (they are one brain)."""
    brain.learner.brain = learner.brain


def pool_phase(brain: Brain) -> Brain:
    """From now on the visual pathway is fixed and everything else learns: the brain's own
    learner, over every slot, with the pathway masked out. ``Brain.load`` keeps the mask."""
    _, rest = pathway_masks(brain)
    old = brain.learner
    learner = Learner(brain.brain, list(brain.motor_index), old.config, plastic_synapses=rest,
                      tie_groups=old.tie_groups, synapse_rate=old.synapse_rate,
                      slots=[int(k) for k in old.slot_sizes])
    brain.learner = learner
    brain.basal_ganglia.learner = learner
    return brain


def map_cells(brain: Brain) -> list[np.ndarray]:
    """The cells of every retinotopic map, in map order."""
    pops = brain.connectome.populations
    names = [k for k in pops if k.startswith("visual/map")]
    names.sort(key=lambda k: (len(k), k))  # visual/map, visual/map1, visual/map2
    return [np.asarray(pops[k], dtype=np.int64) for k in names]


def eye_learner(brain: Brain, teach_maps: bool = False) -> Learner:
    """A learner over the eye's readouts alone, plastic on the visual pathway alone: the eye is
    raised first, as vision develops before reaching, and nothing else moves meanwhile. With
    ``teach_maps`` the maps are outputs too, one slot per map whose label is the cell under the
    object the map is for, so the map learns a blob where the block, the hand and the lit lamp
    are, and the readouts read it. A learner replaces its graph on every update, and the brain
    reads its graph through its own learner, so after each lesson call ``share_graph``."""
    pathway, _ = pathway_masks(brain)
    old = brain.learner
    eye = list(np.asarray(brain.motor_index)[: int(sum(EYE_SLOTS))])
    outputs, slots = [], []
    if teach_maps:
        for cells in map_cells(brain):
            outputs.extend(int(v) for v in cells)
            slots.append(len(cells))
    outputs.extend(int(v) for v in eye)
    slots.extend(EYE_SLOTS)
    return Learner(brain.brain, outputs, old.config, plastic_synapses=pathway, tie_groups=old.tie_groups,
                   synapse_rate=old.synapse_rate, slots=slots)


def map_label(px: float, py: float, size: int, sheet: int) -> int:
    """The map cell under an image point (column, row in pixels of the first eye)."""
    col = int(np.clip(np.floor(px / size * sheet), 0, sheet - 1))
    row = int(np.clip(np.floor(py / size * sheet), 0, sheet - 1))
    return row * sheet + col
