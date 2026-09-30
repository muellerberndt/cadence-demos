# Native feedback throughput

Use a **32-worker persistent pool** as the fastest tested setting for this workload. Every result below matched the serial action sequence, native event/reward vector, qualification, and work accounting exactly. Only wall-clock measurements were excluded from the comparison hashes.

| Worker limit | Cold pool: four contexts | Warm pool: one context | CPU seconds, both phases plus shutdown | Peak summed process-tree RSS |
|---:|---:|---:|---:|---:|
| 8 | 8.305 s | 1.912 s | 78.15 | 2.31 GiB |
| 16 | 5.900 s | 1.359 s | 99.50 | 4.37 GiB |
| **32** | **5.700 s** | **0.881 s** | 149.13 | 8.38 GiB |
| 48 | 6.366 s | 1.586 s | 171.69 | 10.55 GiB |

The cached serial reference took 53.641 seconds for the same four contexts, with 57.14 CPU seconds. The cold 32-worker batch was therefore 9.4 times faster on wall time. This is one measurement per setting under concurrent training, not a stable scaling law or evidence that 32 is universally optimal. The cold 16- and 32-worker results differ by only 0.20 seconds. Summed RSS counts resident mappings across processes and can double-count shared pages; it is not unique physical memory. Worker limits are requested pool ceilings; the benchmark did not separately record the number of initialized worker objects.

The actor was the immutable, untrained small depth-three Cadence control from `native_feedback_verify_01`, with four successive actual Basic contexts at seed `1100200000`, decisions zero through three. The first two complete experience records had to match the earlier verification exactly. These are correlated contexts chosen for throughput and custody, not independent performance evaluation episodes. Each action branch created a fresh native engine, replayed the exact experienced prefix, executed one four-tic intervention, then continued with the same frozen qualified Cadence actor up to 36 native tics. Worker-local Actor caching only avoids repeated parsing; history and pending proposals reset before every branch.

Across the serial reference and four measured pools, the run made **480 fresh engine initializations, 17,280 branch tics, 2,400 prefix-replay tics, and 3,840 qualified continuation queries out of 3,840 attempts**. All twenty-action contexts completed and matched; no failures were excluded. Each pool arm performed 80 cold-batch branches plus 20 warm single-context branches. The frozen producer, contexts, bundle and complete branch receipts remain on AWS at `/home/ec2-user/doom-v3-20260929/runs/native_feedback_benchmark_01` (2,963,345 bytes). Local `freeze.json` and `receipt.json` bind that evidence.

There were 12 concurrent single-thread training lives for the first three arms and 11 at the start of the 48-worker arm. Root also scheduled two native evaluation workers during this period. The short practice smoke completed with worker shutdown at 13:45:59.472 UTC, before the 32-worker summary at 13:46:35.746 UTC and the subsequent 48-worker start. Thus it did not add six practice workers to the largest arm. No running training or evaluation job was stopped for this benchmark. BLAS/OpenMP fan-out was capped at one thread.

The current practice learner labels one context at a time. It can adopt the tested 32-worker limit directly, but one context exposes only twenty independent branches. To improve sustained throughput, add a bounded `label_many([(record, contract), ...])` cohort of four contexts on the same fixed continuation founder. Return results and apply lessons in original input order, preserve whole-context refusal when any of its twenty branches fails, and retain separate context/work accounting. This changes prefetch scheduling, not the learner's admission batch or target semantics. A warm four-context throughput sample was not measured here; do not substitute the cold-batch time for that missing number.

The benchmark cwd already contained ViZDoom's native `_vizdoom` directory. A later evaluation in a new cwd exposed a native directory-creation race. Its fix and fresh-cwd regression are separate evidence; this throughput result does not establish safe first-start behavior of the older frozen constructor.
