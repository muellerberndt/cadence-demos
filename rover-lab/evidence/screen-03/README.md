# Rover development screen on Cadence 0.70.0

Both scheduled development seeds, 17 and 29, are present, each with the optional
observer arm. Normal wheel strength is 1.0 and weakened right-wheel strength is
0.35. The numerical protocol, the app source hashes and the hashes of the
installed `cadence-net==0.70.0` population-solver files are in `freeze.json`.
The run was a serial headless process on macOS 15.3 (arm64), Python 3.13.7 and
NumPy 2.5.3.

| Weakened-body outcome | Cadence learning | Cadence frozen | Adaptive RLS | MLP | Cadence with observers |
| --- | ---: | ---: | ---: | ---: | ---: |
| Targets reached | 10/10 | 5/10 | 10/10 | 5/10 | 10/10 |
| Deadline misses in 800 steps | 8 | 16 | 16 | 19 | 29 |

The default Cadence arm is the state-coupled brain. Its weakened-phase target
distance was 0.855 and 0.868 of its frozen copy's in the two seeds. The complete
demonstration gate passes for both seeds, including the 100 ms timing checks:
the learning arm's 95th-percentile command age stayed between 3 and 27 ms per
phase. Arms are served in order within a step, so the observer arm's command
age includes the four arms before it.

These are development outcomes. They establish neither a reserved result nor an
advantage over the adaptive estimator or from observers. The restoration probe
disables learning and keeps the adapted model; save/resume tests address
separate persistence behavior.

Verify from the package root:

```sh
python3 verify.py evidence/screen-03/seed-17.json evidence/screen-03/seed-29.json
```

`verification.json` holds that command's output. To reproduce, install
`requirements.txt` and run
`python3 evaluate.py --seeds 17 29 --observers --out /tmp/rover-reproduction`.
Wall-clock measurements depend on host load and are not byte-reproducible.
