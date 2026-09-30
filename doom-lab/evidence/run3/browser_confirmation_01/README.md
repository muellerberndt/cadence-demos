# Browser-acquired checkpoint: reserved confirmation fails retention

The frozen browser-acquired checkpoint `7613231af59eab636afd49751e8d1f489d5cef568f9ee7f21e8f3dc73573e9ea` was compared against its actual starting champion, ad9, on 64 reserved Basic seeds `1400300000..1400300063`. The earlier 307604 model is a retention ancestor, not the primary baseline. The prospective compound gate **failed** because five successes were lost, exceeding the allowed five percentage point loss.

| Native outcome | Starting ad9 | Browser 7613 |
|---|---:|---:|
| Wins | 64/64 | 59/64 |
| Mean return | -32.765625 | 17.625 |
| Mean executed tics | 103.453125 | 62.203125 |
| Qualified queries | 1,675/1,675 | 1,016/1,016 |

The primary paired native-return change was **+50.390625**, with the prespecified 10,000-resample paired-bootstrap 95% interval **[9.09375, 89.0]**. Executed tics decreased by 41.25, interval [-68.859375, -12.390625]. However, success declined by **7.8125 percentage points**, interval [-15.625, -1.5625]: 59 shared wins, five ad9-only wins, zero candidate-only wins. The lost-success seeds were 1400300020, 1400300027, 1400300040, 1400300044, and 1400300062. Candidate Wilson 95% success interval: [0.8298046, 0.9661688]. The candidate met the separate minimum58wins criterion, but not the retention criterion. A faster/higher-return policy is not an overall confirmed improvement when the declared reliability gate fails.

All 128 episodes completed, all 2,691 queries qualified, and there were no fallback actions, missing records, caps, or source changes. The two process groups completed in 26.28 seconds overall. Independent verification checked all native decision traces, model/source/origin hashes, native success predicates, and a separate NumPy reconstruction of the fixed bootstrap. Its integrity status is PASS; its `native_confirmation_passed` field is false. These are distinct conclusions.

The actual browser implementation `brain.py` d91ec34 was pinned for both pair members; its backward-compatible omitted-history-gene behavior had already been verified. Task, input/history, normalizer, and genome identity were matched. Bundle files were fixed before play, as were the selection rule, seeds, 58-win floor, at-most5percentage-point loss, all-qualified/no-fallback requirement, primary return criterion, and bootstrap seed717107. No subsequent browser promotion substituted a different candidate.

The origin freeze binds the development gate, practice wave, source manifest, copied native learning journals, and copied native traces from `runs/browser_promotion_7613_01`. The input gate is repeated development selection, not the reserved test. Reserved-integer auditing scanned 3,225 existing files / 706,577,860 decompressed bytes in the declared `runs` and `datasets` roots with no hits. That includes the copied browser evidence, but excludes live Lab journals under `models`; it does not establish global hidden-state independence. The 64 seeds produced 60 unique initial images per model, with paired images identical.

This runner performs no deployment or rollback. Root owns live model decisions. Full immutable artifacts stay on AWS at `/home/ec2-user/doom-v3-20260929/runs/browser_confirmation_01` (33,001,282 bytes at verification); local files contain only compact receipts. The execution source is isolated in `code/browser_confirmation_01`.

Freeze SHA256: `b56c8e51c2959af923986fc9d1b5400889b604ccda1128699034e58f3afe6844`.
Summary SHA256: `c30268ce76bf69e9351f977b4e036d482ceaf279d075aeba7f7ee82365e08473`.
Independent verification SHA256: `285a08f99191cbdc19a3f0b61649e386edef77bb267f4a40c8bb76f32d54ddbf`.


The five lost successes were genuine native 300-tic timeouts, with no deaths or query refusals. They have five distinct initial-image hashes. In all five, the learned candidate's first action changes from the starting model's `fire_right` (14) to `fire_left` (13), followed by firing/movement loops. This is a trace correlation, not a controlled proof that changing only the first action caused the failure; it does not justify hardcoded action rules. The compact extraction is preserved as `lost_success_trace_summary.json`.
