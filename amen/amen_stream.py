"""The Amen event encoding this demo serves, vendored from the training code.

These constants and functions are copied from ``cadence-amen`` (the private
development project), ``drsn_amen/stream.py`` and ``drsn_amen/model.py``, and
must stay byte-equivalent where they overlap: the served brain was trained on
exactly this encoding, and any drift here silently skews what it hears.

One row per half-beat, 71 event ports: soft crop scores over the break's 32
half-beat slices, drum presence and gain, 24 sub-bass semitones, bass presence
and sustain, a change flag and ten texture levels. The brain's inputs are the
history window of the last ``steps`` executed events (with presence masks),
split into the older blocks and the newest block, the eight-position clock and
a wake flag. Targets and outputs are encoded ``0.6 * (2 t - 1)``.
"""

from __future__ import annotations

import numpy as np

CROPS, NOTES = 32, 24
DRUM_ID, DRUM_ON, DRUM_GAIN = slice(0, CROPS), CROPS, CROPS + 1
NOTE_START = CROPS + 2
NOTE_ID = slice(NOTE_START, NOTE_START + NOTES)
BASS_ON, BASS_HOLD = NOTE_START + NOTES, NOTE_START + NOTES + 1
CHANGE = CROPS + 4 + NOTES
TEXTURE_PORTS = 10
TEXTURE = slice(CHANGE + 1, CHANGE + 1 + TEXTURE_PORTS)
EVENT_PORTS = CROPS + 5 + NOTES + TEXTURE_PORTS  # 71
# The count-in: at the wake the composer hears the break's last half-beat, so a stream
# starts on the break's first half-beat, as every transcribed region does.
COUNT_IN = np.zeros(EVENT_PORTS)
COUNT_IN[CROPS - 1] = 1.0
COUNT_IN[DRUM_ON] = 1.0
COUNT_IN[DRUM_GAIN] = 1.0
RETRIGGERS = np.arange(0, CROPS, 8)  # the break's bar-start crops
TARGET_SCALE = 0.6
CLOCK = 8
BLOCK = EVENT_PORTS + 1


def encode(t):
    """Units in [0, 1] to patch targets in [-0.6, 0.6]."""
    return TARGET_SCALE * (2.0 * np.asarray(t, dtype=float) - 1.0)


def decode(y):
    """Settled patch values back to [0, 1] units (unclipped)."""
    return (np.asarray(y, dtype=float) / TARGET_SCALE + 1.0) / 2.0


def senses(window, t, steps):
    """The brain's input mapping at half-beat ``t`` from the executed events so far.

    ``window`` lists the events heard, oldest to newest, the newest last: the
    count-in first, then each executed event. Only the last ``steps`` matter.
    """
    encoded = np.zeros(steps * BLOCK)
    recent = window[-steps:]
    for j, event in enumerate(recent):
        at = (steps - len(recent) + j) * BLOCK
        encoded[at:at + EVENT_PORTS] = event
        encoded[at + EVENT_PORTS] = 1.0
    clock = np.zeros(CLOCK)
    clock[t % CLOCK] = 1.0
    cut = (steps - 1) * BLOCK
    return {
        "past": encoded[:cut].tolist(),
        "heard": encoded[cut:].tolist(),
        "clock": clock.tolist(),
        "wake": 1.0 if t == 0 else 0.0,
    }
