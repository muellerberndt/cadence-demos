# Twelve-context paired causal diagnostic

This probe compares the unchanged founder307604 with recovered candidateabdb48
on12 prospectively chosen, evenly spaced **Basic-only development** rows from
the same frozen prepared dataset. All original models are preserved. Weight
knockouts are detached diagnostic interventions; no modified model was trained,
exported or deployed. The visual permutation is an off-manifold sensitivity
probe and is not a native gameplay experiment.

| Intervention | Founder action changes/12 | Recovered action changes/12 |
| --- | ---: | ---: |
| Remove all residual reads | 0 | 0 |
| Remove latent state/residual reads into policy | 0 | 0 |
| Remove direct current pixels into policy | 12 | 12 |
| Remove direct executed-action history into policy | 2 | 1 |
| Rotate visual inputs across contexts, hold motor history fixed | 3 | 5 |

All baseline and intervention queries qualified. Latent readback removal still
changes scores: its maximum change rises from0.01079 to0.01618 after repair.
That is a numerical causal effect, but it does not change any of the12 chosen
actions. Removing direct current pixels changes every chosen action. These
results do not demonstrate that the practical efficiency gain came from a
greater recursive contribution. They also do not prove that recursion is
irrelevant on all possible inputs.

The complete probe took16.19s on one CPU thread, with no additional native
gameplay. Full frozen contexts and copied models remain in AWS
`runs/recovered_causal_12_01`; only the small source-bound freeze, result and
comparison receipts are retained here.
