# Batch64/128 final-model development screen

All four frozen epoch004 GPU candidates were evaluated on CPU2 with their original query budget512, on Basic seeds1220100000..1220100015. This is reused development selection, not reserved confirmation.

| Model | Wins/16 | Mean return | Mean tics | Qualified queries |
|---|---:|---:|---:|---:|
| large_batch128 | 0 | -300.0 | 300.0 | 1200/1200 |
| large_batch64 | 5 | -189.25 | 209.875 | 841/841 |
| small_batch128 | 0 | -300.0 | 300.0 | 1200/1200 |
| small_batch64 | 15 | -39.25 | 100.5 | 406/406 |

All64episodes completed, all3647queries qualified, and no errors, refusals, or external caps occurred. The independent verifier checks the exact candidate/seed schedule, snapshots, source hashes, every action/native reward/tic, and native success predicate. Both batch128 models used turn_left for all1200decisions. Smallbatch64 used fire_strafe_right334 times and turn_left72 times; its15/16native performance alone does not establish visual responsiveness or useful recursion.

The entire screen took73.14seconds on AWS CPU2 (`i-0509b78c0f89f7542`,54.161.4.241). All source/checkpoint/native traces remain at `/home/ec2-user/doom-v3-20260929/runs/gpu_batch_development_16_08` (6,711,305bytes). A preceding repeated56-decision episode matched CPU1 frames/actions/native outcomes exactly after matching12Cadence sources, executable/pk3/extension hashes, Python3.11.16 and all package versions.

Changing batch size also changes the public-repair schedule and potentially exposure/updates. These four outcomes do not isolate a universal causal benefit of smaller batches. No model was trained, admitted, or deployed by this screen.
