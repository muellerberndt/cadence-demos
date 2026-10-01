"""Compare two fixed Amen brains under shared playing rules and a shared instrument.

This post-hoc diagnostic preserves the failed pilot. It neither trains nor exports
a release candidate. All WAVs use the historical Python literal instrument;
the richer browser audio renderer is explicitly NOT reproduced here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import select
import shutil
import subprocess
import sys
import time
from pathlib import Path

CHOICES = [("argmax", 0), *[("sample", seed) for seed in (1, 2, 3, 4)]]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def settings(mode, seed):
    return {
        "bars": 16,
        "mode": mode,
        "seed": seed,
        "energy": 1,
        "variation": 0.6 if mode == "sample" else 0,
        "riffBars": 2,
    }


def plain_old_inputs(previous, tick):
    # The original 80-port contract: wake, eight-position clock, previous event.
    return [
        float(tick == 0),
        *[float(k == tick % 8) for k in range(8)],
        *map(float, previous),
    ]


def modules(protocol):
    sys.path[:0] = [
        str(Path(protocol["core"]) / "src"),
        protocol["app"],
        str(Path(protocol["root"]) / "sources"),
    ]
    import numpy as np
    import soundfile as sf
    import texture_synth
    from drsn_amen import compose as C
    from drsn_amen import stream as S

    from cadence import Brain

    require(
        sha(texture_synth.__file__)
        == sha(Path(protocol["root"]) / "sources/texture_synth.py"),
        "Actual texture renderer differs from frozen copy",
    )
    return Brain, C, S, np, sf


def freeze(args):
    root = args.root.resolve()
    require(not root.exists(), "Diagnostic root already exists")
    (root / "sources").mkdir(parents=True)
    legacy = args.legacy.resolve()
    pilot = args.pilot.resolve()
    app = args.app.resolve()
    require(
        read(pilot / "verification.json")["valid"],
        "Pilot custody verification required",
    )
    for src, name in [
        (Path(__file__), "amen_matched_render.py"),
        (Path(__file__).with_suffix(".mjs"), "amen_matched_render.mjs"),
        (legacy / "web/engine.js", "legacy-engine.js"),
        (app / "page/engine.js", "pilot-engine.js"),
        (args.texture_source, "texture_synth.py"),
    ]:
        shutil.copy2(src, root / "sources" / name)
    shutil.copytree(legacy / "web/models/three-corpora", root / "legacy")
    shutil.copytree(legacy / "web/kit", root / "kit")
    shutil.copy2(
        legacy / "runs/record-composer-v12/parity.json", root / "legacy-parity.json"
    )
    for src, name in [
        (pilot / "verification.json", "pilot-verification.json"),
        (pilot / "runs/flat-1103/final.json", "pilot-final.json"),
        (pilot / "runs/flat-1103/receipt.json", "pilot-receipt.json"),
        (pilot / "runs/flat-1103/protocol.json", "pilot-protocol.json"),
    ]:
        shutil.copy2(src, root / name)
    report = read(root / "pilot-receipt.json")
    require(
        report["final_sha256"] == sha(root / "pilot-final.json"), "Pilot final hash"
    )
    require(
        read(root / "pilot-verification.json")["receipt_sha256"]
        == sha(root / "pilot-receipt.json"),
        "Pilot receipt binding",
    )
    # The same browser instrument really is available in both applications.
    renderer_hashes = {}
    for name, index in [
        ("legacy", legacy / "web/index.html"),
        ("pilot", app / "page/index.html"),
    ]:
        text = index.read_text()
        block = text[
            text.index("async function bandVoices") : text.index("function wavBlob")
        ]
        renderer_hashes[name] = hashlib.sha256(block.encode()).hexdigest()
    require(len(set(renderer_hashes.values())) == 1, "Browser renderer source mismatch")
    playing_hashes = {}
    for name in ("legacy", "pilot"):
        text = (root / f"sources/{name}-engine.js").read_text()
        block = text[text.index("export function executed") :]
        block = block[: block.index("\n}\n") + 3]
        playing_hashes[name] = hashlib.sha256(block.encode()).hexdigest()
    require(
        len(set(playing_hashes.values())) == 1, "Browser executed-event policies differ"
    )
    for name in ("kit.json", "break.wav", "bass.wav"):
        require(
            sha(root / "kit" / name) == sha(args.pilot_kit / name),
            "Browser kit mismatch",
        )
    protocol = {
        "schema": "amen-matched-render/1",
        "root": str(root),
        "core": str(args.core.resolve()),
        "app": str(app),
        "pilot": str(pilot),
        "node": str(args.node.resolve()),
        "choices": CHOICES,
        "conditions": ["plain/legacy", "plain/pilot", "web/legacy", "web/pilot"],
        "steps": 128,
        "web_settings": [settings(*v) for v in CHOICES],
        "scope": "Post-hoc descriptive comparison; zero learning. Both brains use the same plain Python playing rule, and separately their unchanged web playing policies. Every WAV uses one frozen Python literal instrument at 175 BPM, no key transposition, no normalization. Browser pad/texture audio is not reproduced. Architectures, acquisition, historical memory and capacity are unmatched. No subjective musical success or new acceptance gate is inferred.",
        "browser_renderer_sha256": renderer_hashes,
        "browser_executed_policy_sha256": playing_hashes,
        "original_pilot_musical_owner_verdict": "Rejected by owner after listening to all five raw WAVs; original failed numerical smoke remains unchanged.",
    }
    Brain, _C, S, np, _ = modules(protocol)
    brain = Brain.from_snapshot(
        (root / "pilot-final.json").read_text(), device="python"
    )
    info = brain.inspect()
    graph = brain.graph
    require(
        graph.n_inputs == 585
        and graph.n_patches == 71
        and len(graph.edges) == 41535
        and all(e[0] == "input" for e in graph.edges),
        "Expected original single-layer flat pilot",
    )
    offsets = {}
    at = 0
    for record in info["inputs"]:
        offsets[record["name"]] = at
        at += int(np.prod(record["shape"])) if record["shape"] else 1
    model = {
        "config": {
            k: brain.config[k]
            for k in (
                "tolerance",
                "state_prior",
                "state_bound",
                "step",
                "backtracks",
                "settle_budget",
                "parameter_prior",
                "seed",
            )
        },
        "graph": {
            "n_inputs": graph.n_inputs,
            "n_patches": graph.n_patches,
            "residual_order": list(graph.residual_order),
        },
        "senses": {"steps": 8, "block": 72, **offsets},
        "outputs": [{"name": "event", "patches": list(range(71))}],
        "layout": {
            "crops": 32,
            "notes": 24,
            "drum_on": 32,
            "drum_gain": 33,
            "note_start": 34,
            "bass_on": 58,
            "bass_hold": 59,
            "change": 60,
            "texture_start": 61,
            "texture_ports": 10,
            "event_ports": 71,
        },
        "count_in": S.COUNT_IN.tolist(),
        "retriggers": S.RETRIGGERS.tolist(),
        "target_scale": S.TARGET_SCALE,
    }
    arrays = {
        "kinds": [0] * len(graph.edges),
        "sources": [e[1] for e in graph.edges],
        "targets": [e[2] for e in graph.edges],
        "weights": list(brain.weights),
        "biases": list(brain.biases),
        "state": list(brain.state),
    }
    write(
        root / "pilot-model.json",
        {"model": model, "arrays": arrays, "diagnostic_only": True},
    )
    paths = [
        *sorted((Path(args.core) / "src/cadence").glob("*.py")),
        *sorted((app / "drsn_amen").glob("*.py")),
    ]
    paths += [
        app / "fixtures" / family / filename
        for family in ("phrase-source-v1", "bass-notes-v1")
        for filename in ("fixture.json", "arrays.npz")
    ]
    paths.append(app / "tools/texture_synth.py")
    paths += [
        pilot / "runs/flat-1103/eval" / f"{mode}-{seed}.wav" for mode, seed in CHOICES
    ]
    protocol["external_pins"] = {str(p.resolve()): sha(p) for p in paths}
    protocol["frozen_files"] = {
        str(p.relative_to(root)): sha(p) for p in root.rglob("*") if p.is_file()
    }
    protocol["node_sha256"] = sha(args.node)
    protocol["architecture"] = {
        "legacy": {
            "input_ports": 80,
            "gated_context": 128,
            "record_cells": 8192,
            "active_records": 48,
            "slow_parameters": 29895,
            "record_output_values": 581632,
            "total_learned_output_coefficients": 611527,
            "record_seen_is_not_a_presentation_count": True,
        },
        "pilot": {
            "input_ports": 585,
            "explicit_history_steps": 8,
            "patches": 71,
            "learned_coefficients": 41606,
            "persistent_learned_context": False,
        },
    }
    write(root / "protocol.json", protocol)
    print(
        json.dumps(
            {"frozen": str(root), "protocol_sha256": sha(root / "protocol.json")}
        ),
        flush=True,
    )


def bound(root, protocol):
    for name, value in protocol["frozen_files"].items():
        require(sha(root / name) == value, f"Frozen file changed: {name}")
    for name, value in protocol["external_pins"].items():
        require(sha(name) == value, f"External file changed: {name}")
    require(sha(protocol["node"]) == protocol["node_sha256"], "Node binary changed")


class RPC:
    def __init__(self, protocol, root):
        self.error = (root / "node-stderr.log").open("w")
        self.process = subprocess.Popen(
            [
                protocol["node"],
                str(root / "sources/amen_matched_render.mjs"),
                str(root),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.error,
            text=True,
            bufsize=1,
        )

    def call(self, **value):
        self.process.stdin.write(json.dumps(value) + "\n")
        self.process.stdin.flush()
        require(
            bool(select.select([self.process.stdout], [], [], 60)[0]),
            "Node operation timed out",
        )
        text = self.process.stdout.readline()
        require(bool(text), "Node exited without response")
        result = json.loads(text)
        require(result["ok"], result.get("error", "Node error"))
        return result["result"]

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.error.close()


def run(root):
    root = root.resolve()
    protocol = read(root / "protocol.json")
    bound(root, protocol)
    require(
        not (root / "receipt.json").exists(),
        "Do not overwrite a previous diagnostic receipt",
    )
    Brain, C, S, np, sf = modules(protocol)
    brain = Brain.from_snapshot(
        (root / "pilot-final.json").read_text(), device="python"
    )
    saved = brain.snapshot()
    instrument = C.load_instrument()
    verification = read(root / "pilot-verification.json")
    parity = read(root / "legacy-parity.json")
    cases = {
        f"{condition}/{mode}-{seed}": {"status": "not_started"}
        for condition in protocol["conditions"]
        for mode, seed in CHOICES
    }
    receipt = {
        "schema": "amen-matched-render-receipt/1",
        "protocol_sha256": sha(root / "protocol.json"),
        "musical_quality_assessed": False,
        "training_performed": False,
        "browser_audio_rendered": False,
        "cases": cases,
    }
    write(root / "receipt.json", receipt)
    rpc = RPC(protocol, root)
    started = time.monotonic()
    try:
        for condition in protocol["conditions"]:
            policy, kind = condition.split("/")
            for mode, seed in CHOICES:
                name = f"{condition}/{mode}-{seed}"
                row = cases[name]
                row["status"] = "started"
                write(root / "receipt.json", receipt)
                outputs = []
                events = []
                diagnostics = []
                traces = []
                if policy == "plain" and kind == "legacy":
                    rpc.call(kind="reset")
                    previous = S.COUNT_IN.copy()
                    rng = np.random.default_rng(seed)
                    for tick in range(128):
                        out = rpc.call(
                            kind="step", inputs=plain_old_inputs(previous, tick)
                        )["out"]
                        previous = S.executed(
                            out,
                            mode,
                            rng,
                            previous=previous if mode == "sample" else None,
                        )
                        outputs.append(out)
                        events.append(previous.tolist())
                elif policy == "plain":
                    scores, played, diagnostics = C.generate(
                        brain, 8, 128, mode=mode, seed=seed, trace=True
                    )
                    outputs = scores.tolist()
                    events = played.tolist()
                    require(
                        digest(events)
                        == verification["generation"][f"{mode}-{seed}"][
                            "events_sha256"
                        ],
                        "Pilot events differ from original frozen verification",
                    )
                    row["original_events_exact"] = True
                else:
                    traces = rpc.call(
                        kind="web", brain=kind, options=settings(mode, seed)
                    )["steps"]
                    outputs = [s["out"] for s in traces]
                    events = [s["played"] for s in traces]
                    row["web_options"] = settings(mode, seed)
                    if kind == "pilot":
                        gaps = []
                        for s in traces:
                            u = s["senses"]
                            inputs = {
                                "past": u[:504],
                                "heard": u[504:576],
                                "clock": u[576:584],
                                "wake": u[584],
                            }
                            result = brain.settle(inputs)
                            require(
                                result["qualified"], "Python refused a browser query"
                            )
                            gap = float(
                                np.max(
                                    np.abs(
                                        S.decode(result["outputs"]["event"]) - s["out"]
                                    )
                                )
                            )
                            require(
                                gap <= 1e-5 and s["stationarity"] <= 1e-6,
                                "Browser/reference query mismatch",
                            )
                            gaps.append(gap)
                        row["query_replay"] = {
                            "queries": 128,
                            "all_qualified": True,
                            "maximum_decoded_output_gap": max(gaps),
                        }
                require(len(events) == len(outputs) == 128, "Missing generation steps")
                if kind == "legacy" and mode == "argmax":
                    gap = float(
                        np.max(
                            np.abs(np.asarray(outputs) - np.asarray(parity["outputs"]))
                        )
                    )
                    require(
                        gap < 1e-5, "Legacy brain differs from archived Python parity"
                    )
                    e = np.asarray(events)
                    crops = np.where(
                        e[:, S.DRUM_ON] > 0.5, e[:, S.DRUM_ID].argmax(1), -1
                    ).tolist()
                    notes = np.where(
                        e[:, S.BASS_ON] > 0.5, e[:, S.NOTE_ID].argmax(1), -1
                    ).tolist()
                    require(
                        crops == parity["played_crop"]
                        and notes == parity["played_note"],
                        "Legacy event parity failed",
                    )
                    row["archived_argmax_maximum_gap"] = gap
                e = np.asarray(events)
                sound = C.render(e, instrument)
                stems = {}
                for stem in ("drum", "bass", "texture"):
                    isolated = e.copy()
                    if stem != "drum":
                        isolated[:, S.DRUM_ON] = 0
                    if stem != "bass":
                        isolated[:, S.BASS_ON] = 0
                    if stem != "texture":
                        isolated[:, S.TEXTURE] = 0
                    stems[stem] = C.render(isolated, instrument)
                recombined = sum(values.astype(float) for values in stems.values())
                stem_gap = float(np.max(np.abs(sound.astype(float) - recombined)))
                require(
                    stem_gap <= 2e-7, "Isolated stems do not reconstruct literal mix"
                )
                require(
                    brain.snapshot() == saved, "Pilot queries changed retained snapshot"
                )
                target = root / "outputs" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                sf.write(target.with_suffix(".wav"), sound, 22050, subtype="PCM_16")
                if policy == "plain" and kind == "pilot":
                    original = (
                        Path(protocol["pilot"])
                        / "runs/flat-1103/eval"
                        / f"{mode}-{seed}.wav"
                    )
                    old_sound, rate = sf.read(original, always_2d=True)
                    require(
                        rate == 22050
                        and old_sound.shape == sound.shape
                        and float(np.max(np.abs(old_sound - sound)))
                        <= 1 / 32768 + 1e-7,
                        "Original WAV mismatch beyond PCM16 quantization",
                    )
                    row["original_wav_sha256"] = sha(original)
                    row["original_wav_exact"] = sha(original) == sha(
                        target.with_suffix(".wav")
                    )
                write(
                    target.with_suffix(".json"),
                    {
                        "events": events,
                        "outputs": outputs,
                        "diagnostics": diagnostics,
                        "web_trace": traces,
                    },
                )
                bars = []
                for bar in range(16):
                    sl = e[8 * bar : 8 * (bar + 1)]
                    span = slice(8 * bar * 3780, 8 * (bar + 1) * 3780)
                    audio = sound[span]
                    bars.append(
                        {
                            "bar": bar + 1,
                            "drum_fraction": float(np.mean(sl[:, S.DRUM_ON] > 0.5)),
                            "bass_fraction": float(np.mean(sl[:, S.BASS_ON] > 0.5)),
                            "mean_played_drum_gain": float(np.mean(sl[:, S.DRUM_GAIN])),
                            "rms": float(np.sqrt(np.mean(audio.astype(float) ** 2))),
                            "stem_rms": {
                                k: float(np.sqrt(np.mean(v[span].astype(float) ** 2)))
                                for k, v in stems.items()
                            },
                        }
                    )
                row.update(
                    status="complete",
                    events_sha256=digest(events),
                    trace_sha256=sha(target.with_suffix(".json")),
                    wav_sha256=sha(target.with_suffix(".wav")),
                    wav_bytes=target.with_suffix(".wav").stat().st_size,
                    statistics=S.statistics(e),
                    per_bar=bars,
                    maximum_stem_reconstruction_gap=stem_gap,
                )
                write(root / "receipt.json", receipt)
                print(
                    json.dumps(
                        {
                            "case": name,
                            "status": row["status"],
                            "drum_events": row["statistics"]["drum_events"],
                            "bass_events": row["statistics"]["bass_events"],
                        }
                    ),
                    flush=True,
                )
        receipt["node_fixed_state"] = rpc.call(kind="custody")
        bound(root, protocol)
        receipt.update(
            valid=True,
            all_twenty_cases_complete=all(
                r["status"] == "complete" for r in cases.values()
            ),
            wall_seconds=time.monotonic() - started,
            pilot_snapshot_preserved=brain.snapshot() == saved,
        )
    except BaseException as error:
        receipt.update(
            valid=False, error=repr(error), wall_seconds=time.monotonic() - started
        )
        raise
    finally:
        rpc.close()
        write(root / "receipt.json", receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("freeze")
    p.add_argument("root", type=Path)
    for name in (
        "legacy",
        "pilot",
        "app",
        "core",
        "node",
        "texture-source",
        "pilot-kit",
    ):
        p.add_argument("--" + name, type=Path, required=True)
    p = sub.add_parser("run")
    p.add_argument("root", type=Path)
    args = parser.parse_args()
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(name, "1")
    freeze(args) if args.command == "freeze" else run(args.root)


if __name__ == "__main__":
    main()
