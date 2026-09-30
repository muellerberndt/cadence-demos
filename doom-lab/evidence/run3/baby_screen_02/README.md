# First bootstrap development screen

All twelve trained candidates and one untrained control completed their frozen
Basic/navigation four-seed schedules: 104 episodes in332.89s. Independent
verification found28,003 qualified queries out of28,003 attempts,111,963 executed
native tics, no missing outcomes, and consistent hashes, rewards and native
success predicates. This is development selection, not confirmation.

| Candidate | Basic wins/4 | Navigation wins/4 |
| --- | ---: | ---: |
| Untrained small depth2 seed0 | 1 | 1 |
| Small depth1 seed0 | 3 | 0 |
| Small depth1 seed1 | 3 | 0 |
| Small depth2 seed0 | 2 | 1 |
| Small depth2 seed1 | 4 | 0 |
| Small depth3 seed0 | 4 | 0 |
| Small depth3 seed1 | 4 | 0 |
| Medium depth1 seed0 | 3 | 1 |
| Medium depth1 seed1 | 3 | 0 |
| Medium depth2 seed0 | 1 | 0 |
| Medium depth2 seed1 | 2 | 1 |
| Medium depth3 seed0 | 4 | 0 |
| Medium depth3 seed1 | 4 | 1 |

The matched untrained comparison applies only to small depth2 seed0. Several
models achieved4/4 Basic kills, but their mean return was−222.25: eventual kills
after many wasted tics and shots are not accurate, efficient aiming. Four test
seeds cannot identify a reliable architecture winner.

Navigation remains unsuccessful. For small depth3 seed0, one525-decision
timeout held forward514 times, including502 consecutive forward decisions;
another alternated left/right turns for525 decisions with only8 distinct raw
frames. These were fully qualified Cadence actions. Longer runs of a constant
action are not themselves failure predicates, but in these native timeouts they
explain the lack of progress. Sparse36-tic native feedback far from the goal will
usually tie and cannot by itself tell the actor how to leave such states.

The immutable full trajectories remain at AWS
`/home/ec2-user/doom-v3-20260929/runs/baby_screen_02`. The producer ran from
`code/evaluation_02`, with the native startup race fixed before this screen.
Earlier failed `baby_screen_01` records remain preserved. Local
`consistency_verification.json` is a read-only evidence audit, not additional
native gameplay.
