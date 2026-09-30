# Expanded Basic development screen

Five frozen bundles each played the same16 development seeds1220100000–15.
All80 episodes completed in66.18s. Independent verification found3,936 qualified
queries out of3,936 attempts,15,684 native tics, no errors or missing outcomes,
and consistent source/checkpoint hashes, rewards and native kill predicates.

| Candidate | Native wins/16 | Mean native return | Mean native tics |
| --- | ---: | ---: | ---: |
| CPU-trained small depth3 seed0 | 13 | −150.500 | 177.875 |
| CPU-trained medium depth3 seed1 | 13 | −144.750 | 170.250 |
| Untrained small depth3 seed0 | 6 | −215.875 | 209.375 |
| GPU-trained small depth3 with sensor connections | 13 | −150.500 | 177.875 |
| GPU-trained small depth3 without sensor connections | 3 | −238.125 | 244.875 |

All policies were evaluated on CPU through the same qualified Cadence Actor.
The CPU-trained small model and GPU-trained model with sensor connections
produced exactly the same raw-frame/action/native-transition trace on all16
episodes, despite having different checkpoint hashes. This supports behavioral
equivalence on these cases, not universal numerical equality.

The matched trained/untrained small comparison has9 cases gained and2 lost.
Its two-sided exact paired-binomial/McNemar p-value is0.06543 before accounting
for candidate selection. These16 cases are development selection and do not
establish a reliable architecture winner or the final competency gate.

The trained small policy used `fire_left`518/715 decisions and
`fire_strafe_right`102/715;7/16 episodes contained a run of at least16 identical
actions. The model without sensor connections used `turn_left`871/981 times,
with such runs in13/16 episodes and13 native timeouts. Holding an action is
not inherently a failure; here the action records explain many wasted tics.
Native kills still often arrive late, so13/16 does not mean efficient aiming.

The independent effective-seed probe in
`../../ops/seed_alias_summary_01.json` found no initial-frame overlap between
the investigated gate/practice/new-development/bootstrap families, and no
modular alias at offsets256,1024 or80million. Identical returns do not imply
identical situations. Future confirmation should still freeze its own seeds
and check actual state/trajectory custody before making independence claims.

Full immutable records remain on AWS at
`/home/ec2-user/doom-v3-20260929/runs/basic_development_16_01` (8,055,799 bytes).
Local summary, freeze and consistency receipts are complete. No extra native
gameplay was used by the consistency verifier.
