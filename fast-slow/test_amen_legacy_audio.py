"""Small exact-render and false-green checks; no native/model calls or long audio."""

from __future__ import annotations

import copy
import gzip
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import amen_legacy_audio as A
import numpy as np
import pytest

APP = Path(__file__).resolve().parents[2] / "cadence-amen"


def fixture():
    hop = 31
    crops = np.arange(32 * hop * 2, dtype=float).reshape(32, hop, 2)
    crops = 0.12 * np.sin(crops / 7)
    bass = [0.2 * np.sin(np.arange(103) / 4), 0.17 * np.cos(np.arange(181) / 9)]
    return crops, bass, np.array([24.0, 36.0])


def events():
    rows = np.zeros((32, 71))
    for i in range(len(rows)):
        rows[i, i % 32] = 1
        rows[i, A.DRUM_ON] = i % 5 != 0
        rows[i, A.DRUM_GAIN] = [-0.1, 0, 0.3, 0.9, 1.2][i % 5]
        rows[i, 34 + (0 if i < 12 else 12 if i < 20 else 7)] = 1
        rows[i, A.BASS_ON] = i not in (16, 17, 29)
        rows[i, A.BASS_HOLD] = i not in (8, 21)
    return rows


@pytest.fixture
def original_renderer(monkeypatch):
    # Import the original renderer as the independent oracle. Texture is explicitly
    # absent here; the production checker never imports Cadence or this module.
    monkeypatch.syspath_prepend(str(APP))
    monkeypatch.setitem(
        sys.modules,
        "texture_synth",
        SimpleNamespace(render_texture=lambda x, hop: np.zeros((len(x) * hop, 2))),
    )
    from drsn_amen.compose import render

    return render


@pytest.mark.parametrize("stem", ["drum", "bass", "combined_without_texture"])
def test_exact_float32_pcm_matches_unchanged_original(original_renderer, stem):
    rows, kit = events(), fixture()
    isolated = rows.copy()
    if stem == "drum":
        isolated[:, A.BASS_ON] = 0
    elif stem == "bass":
        isolated[:, A.DRUM_ON] = 0
    expected = original_renderer(isolated, kit)
    actual = np.concatenate([frame[stem] for frame in A.stem_frames(rows, kit)])
    assert actual.dtype == np.float32
    np.testing.assert_array_equal(actual, expected)


def test_rms_uses_actual_pcm_and_finite_voice_expiry(original_renderer):
    rows, kit = events(), fixture()
    rows[:, A.BASS_ON] = rows[:, A.BASS_HOLD] = 1
    rows[:, A.NOTE_ID] = 0
    rows[:, 34] = 1
    rows[:, A.DRUM_ON] = 0
    measured = A.summarize_events(rows, kit)
    pcm = original_renderer(rows, kit)
    hop = kit[0].shape[1]
    for i, bar in enumerate(measured["bars"]):
        block = pcm[i * 8 * hop : (i + 1) * 8 * hop].astype(np.float64)
        assert bar["rms"]["bass"] == pytest.approx(
            np.sqrt(np.mean(block**2)), abs=1e-16
        )
        assert bar["bass_flag_halfbeats"] == 8
    assert measured["bars"][0]["bass_onsets"] == 1
    assert measured["bars"][1]["bass_flag_but_zero_pcm_halfbeats"] == 8
    assert measured["bars"][1]["bass_voice_expired_halfbeats"] == 8
    assert measured["stems"]["bass"]["zero_pcm_bars"] == 3


def test_existing_small_kit_fixtures_match_original_without_texture(original_renderer):
    rows = events()[:8]
    kit = A.load_instrument(APP)
    expected = original_renderer(rows, kit)
    actual = np.concatenate(
        [frame["combined_without_texture"] for frame in A.stem_frames(rows, kit)]
    )
    np.testing.assert_array_equal(actual, expected)


def test_zero_gain_is_not_positive_drum_audio_and_null_ratio_is_explicit():
    rows = np.zeros((8, 71))
    rows[:, A.DRUM_ON] = 1
    result = A.summarize_events(rows, fixture())
    assert result["bars"][0]["drum_flag_halfbeats"] == 8
    assert result["bars"][0]["drum_gain_mean_all_halfbeats"] == 0
    assert result["stems"]["drum"] == {
        "first4_rms": 0,
        "last4_rms": 0,
        "last_first_ratio": None,
        "zero_pcm_bars": 1,
    }


@pytest.mark.parametrize("problem", ["shape", "nan", "incomplete_bar", "loud"])
def test_invalid_signal_rejected(problem):
    rows, kit = events(), fixture()
    if problem == "shape":
        rows = rows[:, :-1]
    elif problem == "nan":
        rows[0, 0] = np.nan
    elif problem == "incomplete_bar":
        rows = rows[:-1]
    elif problem == "loud":
        kit = (np.full_like(kit[0], 10), *kit[1:])
    with pytest.raises(ValueError):
        A.summarize_events(rows, kit)


def write_journal(path, rows):
    with gzip.open(path, "wt") as stream:
        for row in rows:
            stream.write(json.dumps(row) + "\n")


@pytest.mark.parametrize(
    "problem", ["missing", "extra", "order", "bool", "nan", "shape"]
)
def test_journal_census_and_actual_fields_reject_mutations(tmp_path, problem):
    rows = [{"t": t, "played": event.tolist()} for t, event in enumerate(events()[:8])]
    if problem == "missing":
        rows.pop()
    elif problem == "extra":
        rows.append({"t": 8, "played": [0] * 71})
    elif problem == "order":
        rows[3]["t"] = 4
    elif problem == "bool":
        rows[0]["t"] = False
    elif problem == "nan":
        rows[0]["played"][0] = float("nan")
    elif problem == "shape":
        rows[0]["played"].pop()
    path = tmp_path / "case.jsonl.gz"
    write_journal(path, rows)
    with pytest.raises(ValueError):
        A.load_played(path, 8)


def test_journal_uses_played_not_predictions(tmp_path):
    rows = [
        {"t": t, "played": e.tolist(), "out": [999] * 71}
        for t, e in enumerate(events()[:8])
    ]
    path = tmp_path / "case.jsonl.gz"
    write_journal(path, rows)
    np.testing.assert_array_equal(A.load_played(path, 8), events()[:8])


def put(path, value):
    path.write_text(json.dumps(value))


@pytest.fixture
def campaign(tmp_path):
    (tmp_path / "sources").mkdir()
    source = tmp_path / "sources/engine.js"
    source.write_text("fixture-only")
    (tmp_path / "cases").mkdir()
    protocol = {
        "schema": "amen-legacy-ablation/1",
        "cases": A.expected_cases(),
        "expected_steps": 20480,
        "sources": {"engine.js": A.sha(source)},
    }
    put(tmp_path / "protocol.json", protocol)
    pin = A.sha(tmp_path / "protocol.json")
    put(tmp_path / "freeze.json", {"protocol_sha256": pin})
    cases = copy.deepcopy(A.expected_cases())
    for case in cases:
        path = tmp_path / "cases" / f"{case['id']}.jsonl.gz"
        # This tests metadata/file binding only; load_played independently checks
        # numeric row counts. Do not call analyze on this deliberately empty fixture.
        write_journal(path, [])
        case.update(
            status="complete",
            returned_steps=1024,
            fixed_before="same",
            fixed_after="same",
            work={"steps": 1024},
            journal_bytes=path.stat().st_size,
            journal_sha256=A.sha(path),
        )
    put(tmp_path / "progress.json", cases)
    put(
        tmp_path / "receipt.json",
        {
            "schema": "amen-legacy-ablation-result/1",
            "protocol_sha256": pin,
            "complete": True,
            "source_unchanged": True,
            "training_calls": 0,
            "record_writes": 0,
            "cases": cases,
        },
    )
    return tmp_path


def test_full_metadata_binding_and_all_paths_pinned(campaign):
    _, receipt, pins = A.campaign_binding(campaign)
    assert len(receipt["cases"]) == 20
    assert len(pins) == 25
    assert all(A.sha(path) == value for path, value in pins.items())


@pytest.mark.parametrize(
    "problem",
    ["partial", "omission", "duplicate", "source", "journal", "extra_file", "weights"],
)
def test_no_partial_or_tampered_campaign_promoted(campaign, problem):
    receipt = A.read(campaign / "receipt.json")
    if problem == "partial":
        receipt["cases"][0]["status"] = "failed"
    elif problem == "omission":
        receipt["cases"].pop()
    elif problem == "duplicate":
        receipt["cases"][-1] = receipt["cases"][0]
    elif problem == "source":
        (campaign / "sources/engine.js").write_text("changed")
    elif problem == "journal":
        (campaign / "cases/intact-argmax-0.jsonl.gz").write_bytes(b"changed")
    elif problem == "extra_file":
        (campaign / "cases/unclaimed.jsonl.gz").write_bytes(b"extra")
    elif problem == "weights":
        receipt["cases"][0]["fixed_after"] = "different"
    put(campaign / "receipt.json", receipt)
    put(campaign / "progress.json", receipt["cases"])
    with pytest.raises(ValueError):
        A.campaign_binding(campaign)
