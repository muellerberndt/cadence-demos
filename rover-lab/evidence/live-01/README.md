# One live server run on Cadence 0.70.0

`seed-17.json` is the receipt exported from the browser server after one
automatic demonstration (seed 17, right wheel at 35%), recorded while other
work used the same machine. `verification.json` holds the output of
`python3 verify.py evidence/live-01/seed-17.json`.

The receipt verifies. Learning Cadence reached 5/5 weakened-body targets
against 2/5 for its frozen copy, with a weakened-phase target distance of 0.855
of the frozen copy's. The demonstration gate fails on timing: the learning
arm's 95th-percentile command age was 159 ms in the normal phase, with 19
deadline misses in its 160 steps, and 11 to 28 ms in the later phases.
