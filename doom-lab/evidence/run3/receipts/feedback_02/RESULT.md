# Bounded Basic feedback comparison

**Neither proposed change improved the player in this experiment.** All four
arms completed 16 qualified public Cadence repairs and 128 presentations.
All 40 development gates rejected their candidate; the champion remained
`db6df682f3c4411e0a2d18ac4bcb9fff368bbdc6d7186391e9d100a5241050ac`.
No browser actor or live training contract was changed.

The immutable experiment used 64 newly collected autonomous Linux contexts,
sequential training seeds beginning910000000, batch8, two fixed-order passes,
the same starting checkpoint and 32 development seeds. The teacher measured
either holding an action for36tics, or acting for12tics followed by the frozen
champion for the remaining24tics. Candidate lifetimes were one or four admitted
updates before evaluation/reset. Neither arm used incompatible legacy labels.
The starting champion killed the monster on32/32development episodes with
mean return73.25. These were development comparisons, never fresh confirmation.

| Target / updates before gate | Best candidate mean-return delta | Last candidate training MSE, before → after | Best-label agreement, before → after |
| --- | ---: | ---: | ---: |
| hold36 /1 | -4.9375 | .02865 → .02475 | .766 → .531 |
| hold36 /4 | -33.7500 | .02865 → .02120 | .766 → .594 |
| champion continuation /1 | -15.5938 | .07294 → .03687 | .594 → .328 |
| champion continuation /4 | -150.0313 | .07294 → .03318 | .594 → .359 |

The training-row diagnostics were computed after the experiment, without
selecting another candidate. Their absolute MSE decreased while their action
ranking became worse, even on these training contexts. The continuation target
changed the label argmax in28/64contexts. Lower utility MSE therefore does not
justify promotion. Four-update accumulation alone also did not solve this
case. This small, fixed-order, replay-free64-context result does not establish
that longer curricula, other representations or better-balanced data cannot
work. The repeated second pass exactly retraces first-pass candidates when
the prior rejected block restored the same champion and receives identical
ordered examples; it is not independent replication.

Fixture collection took4.65seconds, the full comparison120.24seconds, and its
external supervisor129.37seconds overall. Comparison work:768fresh simulator
branches,555frozen-champion continuation queries/12,459sweeps,1,312evaluation
episodes including the32-episode anchor, and64admitted repairs. Every one of
the1,280candidate evaluation episodes completed with qualified queries and no
fallback; timeouts are complete native outcomes, not successes. No scheduled
candidate was omitted. Repair took11.30seconds across the64updates; assessment
and feedback dominate this small run.

The full run remains on AWS at
`/home/ec2-user/doom-v3-20260929/runs/feedback_02` (7.43MB when verified), with
the0.54MBfixture under `datasets/feedback_contexts_02.json`. Local files retain
the freeze, compact outcome summaries, verification and diagnostic receipts.
`verification.json` recomputes branch native-reward/tic sums, exact source
fixture binding, candidate checkpoint hashes and every scheduled outcome.

The preceding `feedback_01` attempt remains a separate failed custody test.
All six first-context branches refused the Mac archive's raw-frame hash on
Linux. Both packages reportedViZDoom1.3.1, but executable, extension and some
packaged-asset hashes differed. The Mac smoke reproduced that same archived
context exactly. We neither rewrote its hashes nor relaxed pixel tolerances;
the new Linux fixture was collected and frozen separately. Cross-platform
browser deployment therefore needs its own behavioral check and must not
inherit exact-frame replay claims solely from a version string.

The full-game training path should retain its distinct preference target and
measure class-specific recall, especially USE, alongside native autonomous
gameplay. Removing a common score offset is a candidate conditioning change,
not proof of improved action ranking. Selection needs successful unclamped
behavior and retention, rather than lower training error or more admissions.
