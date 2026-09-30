# Rover development screen

Both scheduled development seeds, 17 and 29, are present. Normal wheel strength
is 1.0 and weakened right-wheel strength is 0.35. The numerical protocol and
implementation hashes are in `freeze.json`; exact implementation files are in
`source/`. The bundle is under 10 MB and contains no external data dependency.

| Weakened-body outcome | Cadence learning | Cadence frozen | Adaptive RLS | MLP |
| --- | ---: | ---: | ---: | ---: |
| Targets reached | 10/10 | 5/10 | 10/10 | 5/10 |

The body-recovery checks pass for both seeds. The complete demonstration gate
fails on command latency and deadline misses. These are development outcomes;
they establish neither a reserved result nor a comparative commercial or
recursive-depth advantage. The restoration probe disables learning and keeps
the adapted model; save/resume tests address separate persistence behavior.

Verify from the package root:

```sh
python3 verify.py evidence/screen-02/seed-17.json evidence/screen-02/seed-29.json
```

To reproduce the exact recorded candidate, use `source/` as the working
directory and run `python3 evaluate.py --seeds 17 29 --out /tmp/rover-reproduction`.
Its local `cadence/` package contains the implementation pinned by the freeze.
Wall-clock measurements depend on host load and are not byte-reproducible.
