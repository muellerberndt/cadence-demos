"""Parity cases for the spiking port (web/spiking.js) on the oculomotor scope.

Runs ``verify_lif.simulate`` of the connectome compiler on the 343 neurons of the paper's model
scope for one 300 ms trial, Poisson drive to ``_Int_`` for 200 ms at w_syn 0.35 mV, and writes

- tests/spiking_parity_cases.json: the Poisson events the simulation consumed (drawn again from
  the same seed with the generator logic of ``simulate``), every neuron's spike count per 100 ms
  bin, the exact spike events on the 0.1 ms grid, and the constants;
- web/data/brain_oculomotor.json: the same wiring as the rate model's payload, for the page.

The seed is the one ``binned_rates`` gives trial 0 of this condition, and its rates are checked
against the counts. The runaway cut of ``Lif`` (a trial past a 30 Hz mean rate stops at the next
100 ms) would stop this trial at 100 ms, since 255 of the 343 neurons are driven at 150 Hz; it
is disabled with a runaway rate no trial reaches, and the file says so.

Run from the cadence-zebrafish folder:
    CONNECTOME_DATA=../connectome-research/data ../cadence/.venv/bin/python tools/spiking_parity_cases.py
"""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path
from zlib import crc32

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cadence-examples"))
from engine.export import write_payload  # noqa: E402
from connectome_compiler import compile, brain  # noqa: E402
from connectome_compiler.sources import zebrafish_brainstem as zb  # noqa: E402
from connectome_compiler.verify.burst import GRADED_UNIT  # noqa: E402
from connectome_compiler.verify_lif import _EVENT_CHUNK, Lif, binned_rates, simulate  # noqa: E402

SOURCE = "Vishwanathan et al. 2024, Nat Neurosci 27:2340 (doi 10.1038/s41593-024-01784-3)"
NO_RUNAWAY_HZ = 1e9  # no trial reaches this mean rate


def outgoing(c, w_syn_mv):
    """Every neuron's outgoing synapse classes with weights in mV, as binned_rates builds them."""
    order = np.argsort(c.pre, kind="stable")
    out_ptr = np.concatenate([[0], np.cumsum(np.bincount(c.pre, minlength=c.n))])
    return out_ptr, np.ascontiguousarray(c.post[order]), np.ascontiguousarray((c.count * c.sign)[order] * w_syn_mv)


def poisson_events(seed, steps, width, p_event, drive_until):
    """The events simulate consumes for one row: per chunk of _EVENT_CHUNK steps it draws
    random((chunk, width)) < p_event from the row's generator; an event at step t hits the
    t-th row's stimulated neuron at position k, and only steps before drive_until reach the neuron."""
    gen = np.random.default_rng(np.random.SeedSequence(list(seed)))
    events = []
    for start in range(0, steps, _EVENT_CHUNK):
        chunk = min(_EVENT_CHUNK, steps - start)
        drawn = gen.random((chunk, width)) < p_event
        local, k = np.nonzero(drawn)
        for t, j in zip(local.tolist(), k.tolist()):
            if start + t < drive_until:
                events.append((start + t, j))
    return events


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--w-syn", type=float, default=0.35, help="synaptic weight in mV")
    p.add_argument("--t-run", type=float, default=300.0, help="trial length in ms")
    p.add_argument("--drive", type=float, default=200.0, help="Poisson drive for this many ms from the start")
    p.add_argument("--bin", type=float, default=100.0, help="bin width in ms for the counts")
    p.add_argument("--population", default="_Int_")
    p.add_argument("--seed", type=int, default=0, help="Lif.seed")
    p.add_argument("--trial", type=int, default=0, help="the trial index in binned_rates' seed")
    p.add_argument("--gain", type=float, default=0.3224, help="the rate model's gain in the exported payload")
    p.add_argument("--payload", type=Path, default=Path("web/data/brain_oculomotor.json"))
    p.add_argument("--out", type=Path, default=Path("tests/spiking_parity_cases.json"))
    a = p.parse_args(argv)

    t = zb.load(scope="oculomotor"); c = compile(t)
    stim = np.asarray(c.populations[a.population], dtype=np.int64)
    m = Lif(t_run_ms=a.t_run, seed=a.seed, runaway_hz=NO_RUNAWAY_HZ)
    steps = int(round(m.t_run_ms / m.dt_ms)); per_bin = int(round(a.bin / m.dt_ms))
    bins = list(range(0, steps, per_bin)) + [steps]
    if bins[-2] == steps:
        bins = bins[:-1]
    drive_until = int(round(a.drive / m.dt_ms))
    seed = (m.seed, crc32(repr((tuple(int(i) for i in stim), a.w_syn)).encode()), a.trial)  # binned_rates' seed for this trial
    out_ptr, out_post, out_w = outgoing(c, a.w_syn)
    # Per-step bins expose exact spike times through the existing independent
    # Python simulator. Aggregate those bins for the older rate/count checks.
    per_step, ran_away = simulate(
        c.n, out_ptr, out_post, out_w, [stim], [np.zeros(0, dtype=np.int64)], m, a.w_syn * m.f_poi, [seed],
        drive_until=drive_until, bins=range(steps + 1),
    )
    if ran_away.any():
        raise SystemExit("the trial ran away; the runaway cut is meant to be disabled here")
    per_step = per_step[0]  # (steps, neurons)
    if not np.isin(per_step, [0, 1]).all():
        raise SystemExit("a neuron may spike at most once per simulation step")
    counts = np.stack([per_step[start:end].sum(axis=0) for start, end in zip(bins, bins[1:])])
    spike_step, spike_neuron = np.nonzero(per_step)
    if a.trial == 0:  # binned_rates draws trial 0 from the same seed: its rates are these counts over the bin width
        rates, _ = binned_rates(c, m, a.w_syn, [stim], drive_ms=a.drive, bin_ms=a.bin, trials=1)
        widths = np.diff(bins) * m.dt_ms / 1000.0
        if not np.array_equal(np.rint(rates[0] * widths[:, None]), counts):
            raise SystemExit("binned_rates disagrees with simulate; the seed convention has changed")
    p_event = m.r_poi_hz * m.dt_ms / 1000.0
    events = poisson_events(seed, steps, len(stim), p_event, drive_until)
    e_m = float(np.exp(-m.dt_ms / m.t_mbr_ms)); e_s = float(np.exp(-m.dt_ms / m.tau_ms))
    c_step = (m.tau_ms / (m.tau_ms - m.t_mbr_ms)) * (e_s - e_m)
    others = np.setdiff1d(np.arange(c.n), stim)
    cases = {
        "format": "cadence.spiking-parity-cases/2",
        "source": SOURCE, "scope": "oculomotor", "n": int(c.n), "classes": int(c.synapses),
        "tables_digest": t.digest(), "connectome_digest": c.digest(),
        "w_syn_mv": a.w_syn, "population": a.population, "stimulated": stim.tolist(),
        "t_run_ms": m.t_run_ms, "drive_ms": a.drive, "bin_ms": a.bin, "steps": steps, "drive_until": drive_until, "bins": bins,
        "seed": [int(s) for s in seed], "lif": m.to_dict(),
        "runaway": f"disabled: runaway_hz {NO_RUNAWAY_HZ:g}; the default 30 Hz cut stops this trial at 100 ms",
        "constants": {
            "e_m": e_m, "e_s": e_s, "c": c_step, "p_event": p_event, "kick_mv": a.w_syn * m.f_poi,
            "delay_steps": max(1, int(round(m.t_dly_ms / m.dt_ms))), "refractory_steps": int(round(m.t_rfc_ms / m.dt_ms)),
        },
        "events": [[int(s), int(stim[j])] for s, j in events],
        "spikes": [[int(s), int(i)] for s, i in zip(spike_step, spike_neuron)],
        "counts": counts.astype(int).tolist(),
        "mean_hz": {
            "stimulated": (counts[:, stim].mean(axis=1) / (per_bin * m.dt_ms / 1000.0)).tolist(),
            "others": (counts[:, others].mean(axis=1) / (per_bin * m.dt_ms / 1000.0)).tolist(),
        },
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(cases, separators=(",", ":")))

    b = brain(c, a.gain, backend="cpu", **GRADED_UNIT)
    extra = {"source": SOURCE, "scope": "oculomotor", "gain": a.gain, "unit": GRADED_UNIT,
             "kind": t.neurons.kind.tolist(), "id": t.neurons.id.tolist(), "tables_digest": t.digest(), "connectome_digest": c.digest()}
    out = write_payload(b, a.payload, extra=extra)
    print(f"cases {a.out}: {c.n} neurons, {len(events)} events over {drive_until} steps, spikes per bin {counts.sum(axis=1).astype(int).tolist()},",
          f"{a.population} mean Hz {[round(x, 2) for x in cases['mean_hz']['stimulated']]}, others {[round(x, 2) for x in cases['mean_hz']['others']]}")
    print(f"payload {out}: {out.stat().st_size // 1024} KB, {c.n} neurons, {c.synapses} classes, gain {a.gain}")


if __name__ == "__main__":
    main()
