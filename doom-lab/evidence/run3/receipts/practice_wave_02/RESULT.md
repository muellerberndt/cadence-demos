The first trained depth3 Basic autonomous practice wave completed all three bounded processes without a promotion. This is not evidence of zero learning: several candidate policies improved mean native return substantially while losing founder wins.

The fixed founder checkpoint was `3076041351210d5818df542b23c167278a76ce59d7ceae531b52e05398f80ad8`. All new labels came from its actual qualified gameplay, reconstructed in fresh native engines, followed by 4 tics of the candidate action and frozen-founder continuation to a total36-tic horizon. The labels were converted to centered policy preferences; they were never called expected returns or Q values. Parameter changes used public Cadence batch repair only.

| Candidate lifetime | Accepted repairs | Example presentations | Processed contexts | Informative contexts | Queued contexts preserved | Promotions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 15 | 240 | 218 | 122 | 38 | 0 |
| 4 | 16 | 256 | 223 | 128 | 33 | 0 |
| 16 | 16 | 256 | 215 | 131 | 41 | 0 |

All three collectors recorded256 actual transitions. Collector episode wall timers included feedback queue backpressure; the arms therefore reached different points within episodes despite sharing a seed stream. These are bounded operational comparisons, not matched-exposure estimates of the causal effect of candidate lifetime. Process exit0 also does not mean all queued lessons were processed: the table reports the preserved pending work explicitly.

The repeated eight-seed development anchor won7/8 episodes with mean return−147.5. Lifetime1 gate15 won6/8 with mean−17.625; lifetime16's first gate won6/8 with mean−24.875. All reported candidate evaluations were complete, qualified, and free of fallback. The latter candidate lost two founder successes and gained the founder's previously failed seed. Full per-gate successes, returns and seed-level changes are in `gate_aggregate_diagnostic.json`.

The unchanged promotion rule requires each individual founder/champion success to survive, plus nondecreasing task mean return and strict improvement. It is stronger than an aggregate5-percentage-point retention rule. However, every candidate in this wave won at most6/8: the best loss was12.5percentage points. No observed candidate would have passed an aggregate5-point rule either. Zero promotions should be described as unsuccessful guarded policy improvement, not no change or no return improvement.

The original36-tic horizon frequently ends before founder kills (146–291 actual tics on several gate episodes). Short-horizon miss/living penalties may reward trajectories that avoid shooting while omitting delayed kills. This motivates a prospective horizon comparison; it does not by itself establish that longer horizons solve the problem.

The next immutable experiment reuses128 contexts selected without branch labels from the prespecified first256 lifetime1 transitions. It compares the original36-tic contract against separately source-bound144/300-tic native contracts, with lifetime4, identical ordered contexts and unchanged gates. Different horizons can still produce different tied contexts and admitted batches; report those counts and compute costs. No fresh confirmation seeds are used in either wave.

Bulk evidence remains on AWS at `/home/ec2-user/doom-v3-20260929/runs/practice_wave_02/` (107MiB after completion). This directory contains only compact copied receipts and this interpretation.
