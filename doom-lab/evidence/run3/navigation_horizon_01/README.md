# Native navigation credit-horizon diagnosis

Status: complete; independent verification passed. This is a diagnostic, not a trained-policy evaluation or promotion.

The exact 32 qualified autonomous contexts from `runs/navigation_novelty_01` are reused in their original order. They come from four complete ad9 navigation episodes, including one native goal success. Each horizon evaluates all 20 legal first actions, then continues with the same frozen ad9 Cadence actor. Every branch starts a fresh native engine and reproduces the exact actual prefix, pixels, and action history. No teacher, novelty bonus, new experience collection, repair, or model deployment is included.

The existing H36 labels are the cached native-only component of the earlier novelty comparison. H144 and H600 use a separately versioned navigation contract. Exact installed `my_way_home` source gives one +1 goal reward followed by `Exit_Normal` and a living reward of -0.0001 per tic. Therefore the H-tic native-return bound is [-0.0001H, 1], with divisor 1. Navigation's goal-success outcome is recorded separately from its native-exit flag.

Both horizons and all inputs, model, source, core, engine, and scenario hashes were frozen before either run. Each horizon has 20 workers, 32 scheduled contexts, and 640 scheduled native branches. External process-group caps are 1,200 seconds per horizon and 2,500 seconds overall. Partial results and missing-context accounting are retained.

The postlaunch precondition audit additionally checks the complete model-file hash against the original fixture's freeze and checks every cached H36 native contract and branch action order. These were added after launch and are explicitly not retrospective preregistration. Four focused boundary, history/transition custody, refused-query, and goal-versus-exit tests passed locally and on AWS. An initial AWS test invocation lacked the shared fake fixture; supplying that test-only dependency resolved the import error before gameplay.

Full immutable artifacts remain on AWS at `/home/ec2-user/doom-v3-20260929/runs/navigation_horizon_01`; the isolated execution source is `code/navigation_horizon_01`. Local files contain only small protocol and verification receipts.


## Results

| Horizon | Valid contexts | Informative action returns | Mixed goal/no-goal choices | Wall time |
|---|---:|---:|---:|---:|
| 36 (cached) | 32/32 | 0 | 0 | Previously collected |
| 144 | 32/32 | 2 | 2 | 142.48 s |
| 600 | 32/32 | 14 | 14 | 459.54 s |

All 1,280 new native branches completed: 90,254/90,254 continuation queries were qualified, without missing results, refusals, or external cutoffs. The query budget was 512; actual used solver sweeps were not logged. The median continuation query took about 0.091 seconds under concurrent host load. H144 used 79,817 branch tics plus 535,040 replay tics; H600 used 286,144 plus 535,040 replay tics. Independent verification checked 1,920 exact shorter-horizon prefixes and confirmed that unchanged-action branches reproduce the original actual episode continuations.

H600 supplied mixed goal/no-goal labels at context indices `0,1,4,5,8,9,12,13,16,17,20,21,24,25`: seven contexts each from seeds 1320000000 and 1320000001. The former's actual episode had failed; counterfactual actions can nevertheless reach its goal under the fixed continuation. The other two episodes supplied no informative labels. One final near-goal context had all 20 actions succeed with tied return at both longer horizons.

This establishes a credit-horizon defect in H36 for this fixture, not learned navigation competence. These values assume subsequent frozen-ad9 behavior. Updating the learner also changes its continuation, so global policy drift and Basic retention still need independent native gates. No model was trained or promoted here.

The AWS run occupies 12,326,758 bytes. Summary SHA256: `a14e7758e2875650a3246a88536c917e1def412ba28b8a19d90bab4753ada77a`. Independent verification SHA256: `6a5a574b27f0a324a0cf26714cd332491c63df83422d2df661fcb72718e624a7`.
