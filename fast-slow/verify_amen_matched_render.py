"""Independently recheck saved event execution and every literal WAV; no learning.

The producer separately checks native engine parity and replays pilot web queries.
This verifier recomputes rendering, plain decoder execution, all descriptive
metrics and file custody. It does not claim to repeat historical training.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import amen_matched_render as m


def verify(root):
    root = root.resolve()
    protocol = m.read(root / "protocol.json")
    receipt = m.read(root / "receipt.json")
    m.bound(root, protocol)
    m.require(
        receipt["protocol_sha256"] == m.sha(root / "protocol.json"), "Protocol binding"
    )
    names = {
        f"{c}/{mode}-{seed}"
        for c in ("plain/legacy", "plain/pilot", "web/legacy", "web/pilot")
        for mode, seed in m.CHOICES
    }
    m.require(set(receipt["cases"]) == names, "Complete twenty-case census")
    m.require(
        receipt["valid"] and receipt["all_twenty_cases_complete"],
        "Incomplete producer result",
    )
    m.require(
        not receipt["training_performed"]
        and not receipt["musical_quality_assessed"]
        and not receipt["browser_audio_rendered"],
        "Unsupported claims",
    )
    _Brain, C, S, np, sf = m.modules(protocol)
    instrument = C.load_instrument()
    checked = {}
    for name in sorted(names):
        report = receipt["cases"][name]
        target = root / "outputs" / name
        m.require(report["status"] == "complete", "Incomplete case")
        for suffix, key in ((".json", "trace_sha256"), (".wav", "wav_sha256")):
            m.require(
                m.sha(target.with_suffix(suffix)) == report[key], "Output hash mismatch"
            )
        trace = m.read(target.with_suffix(".json"))
        events = np.asarray(trace["events"])
        m.require(events.shape == (128, 71), "Missing event inventory")
        m.require(m.digest(trace["events"]) == report["events_sha256"], "Event digest")
        m.require(
            S.statistics(events) == report["statistics"], "Descriptive event statistics"
        )
        policy, brain, choice = name.split("/")
        mode, seed = choice.split("-")
        if policy == "plain":
            previous = S.COUNT_IN.copy()
            rng = np.random.default_rng(int(seed))
            for tick, out in enumerate(trace["outputs"]):
                previous = S.executed(
                    out, mode, rng, previous=previous if mode == "sample" else None
                )
                m.require(
                    np.array_equal(previous, events[tick]),
                    "Plain execution differs from common decoder",
                )
            if brain == "pilot":
                original = m.read(root / "pilot-verification.json")["generation"][
                    choice
                ]
                m.require(
                    original["events_sha256"] == report["events_sha256"],
                    "Original pilot changed",
                )
        else:
            m.require(
                report["web_options"] == m.settings(mode, int(seed)),
                "Web options changed",
            )
            m.require(len(trace["web_trace"]) == 128, "Missing web trace")
            for tick, step in enumerate(trace["web_trace"]):
                m.require(
                    step["t"] == tick and step["played"] == trace["events"][tick],
                    "Web event custody",
                )
        sound = C.render(events, instrument)
        audio, rate = sf.read(target.with_suffix(".wav"), always_2d=True)
        m.require(rate == 22050 and audio.shape == sound.shape, "WAV dimensions")
        wav_gap = float(np.max(np.abs(sound.astype(float) - audio)))
        m.require(wav_gap <= 1 / 32768 + 1e-7, "WAV differs beyond PCM16 quantization")
        stems = {}
        for stem in ("drum", "bass", "texture"):
            e = events.copy()
            if stem != "drum":
                e[:, S.DRUM_ON] = 0
            if stem != "bass":
                e[:, S.BASS_ON] = 0
            if stem != "texture":
                e[:, S.TEXTURE] = 0
            stems[stem] = C.render(e, instrument)
        m.require(len(report["per_bar"]) == 16, "Missing bar inventory")
        for bar, reported in enumerate(report["per_bar"]):
            span = slice(bar * 8 * 3780, (bar + 1) * 8 * 3780)
            e = events[bar * 8 : (bar + 1) * 8]
            actual = {
                "bar": bar + 1,
                "drum_fraction": float(np.mean(e[:, S.DRUM_ON] > 0.5)),
                "bass_fraction": float(np.mean(e[:, S.BASS_ON] > 0.5)),
                "mean_played_drum_gain": float(np.mean(e[:, S.DRUM_GAIN])),
                "rms": float(np.sqrt(np.mean(sound[span].astype(float) ** 2))),
                "stem_rms": {
                    k: float(np.sqrt(np.mean(v[span].astype(float) ** 2)))
                    for k, v in stems.items()
                },
            }
            m.require(actual == reported, "Bar measurements differ")
        checked[name] = {
            "events": 128,
            "wav_maximum_quantization_gap": wav_gap,
            "last_bar": report["per_bar"][-1],
        }
    m.bound(root, protocol)
    result = {
        "schema": "amen-matched-render-verification/1",
        "valid": True,
        "verifier_sha256": m.sha(__file__),
        "receipt_sha256": m.sha(root / "receipt.json"),
        "protocol_sha256": m.sha(root / "protocol.json"),
        "cases": checked,
        "scope": __doc__,
    }
    m.write(root / "verification.json", result)
    print({"valid": True, "cases": len(checked), "events": len(checked) * 128})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    verify(parser.parse_args().root)
