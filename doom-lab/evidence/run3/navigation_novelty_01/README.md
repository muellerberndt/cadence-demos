# Bounded navigation novelty comparison

The novelty gene generated learning signals but did not improve navigation and damaged Basic performance. No model was promoted or deployed.

All four prospectively selected collection episodes were completed by confirmed checkpoint ad9b330 on seeds 1320000000–1320000003: one native navigation goal and three native timeouts. Eight evenly spaced real contexts per episode were frozen, then a single shared set of 20-action H36 native branches was scored under frozen ad9 continuation. Both arms received identical native outcomes; the only new utility gene was beta 0 versus beta 0.05 for four-reference visible novelty.

| Repeated development result | Original founder | Confirmed ad9 / native control | Novelty candidate |
| --- | ---: | ---: | ---: |
| Basic wins / scheduled | 7/8 | 8/8 | 4/8 |
| Basic mean native return | -147.500 | -29.125 | -215.375 |
| Navigation wins / scheduled | 0/4 | 0/4 | 0/4 |
| Navigation mean native return | -0.210 | -0.210 | -0.210 |

The native-only arm had 32 tied vectors, skipped them all, and remained exactly ad9. The novelty arm had 21 informative contexts and 11 ties; two public repair batches were accepted, with five contexts left pending. Its end checkpoint is `f7b691ea1cfe862050eb881428e13097eb45de46295129ab405ddc0ee4b34072`. The four-repair lifetime was incomplete, so it could not qualify for promotion. Its prospectively required final diagnostic was nevertheless run; it lost four previously successful Basic cases and gained no navigation goal. No partial candidate was silently promoted or padded with synthetic rows.

Training used 8 new plus 8 old examples per repair, the same declared RNG, existing finite bootstrap preferences and prior same-arm experience when available. There were no new expert demonstrations, geometry inputs, altered patch rules, or hard-coded actor actions. Native navigation goals and skill retention were the only eligibility measures; intrinsic scores were not a promotion criterion.

Independent verification passed source/bundle hashes, all 32 selected action-prefix witnesses, 640 native branches, 4,480 qualified continuation queries, utility arithmetic, declared gates and 36 unique complete native evaluation traces. Collection used 1,679 queries and 6,715 tics. Branches used 535,040 prefix replay tics plus 20,460 branch tics. Unique gate traces used 7,283 queries and 29,101 tics. The campaign completed in 319.79s (supervisor 320.29s), without an external cutoff. All native diagnostic queries qualified.

The current four-reference bonus is informative but insufficient: it can reward visual change without establishing useful exploration, and short replay did not preserve existing skill. These results do not identify a successful novelty weight or guarantee that simply extending this candidate would work. Future comparisons must retain the unchanged native control and test stronger retention or memory changes as separate genes.

Full 33,389,732-byte AWS evidence: `/home/ec2-user/doom-v3-20260929/runs/navigation_novelty_01`. Compact receipts remain here. Freeze SHA `0f9ae32c5a78e7b0a6a9fcca0c97412ebfaa3859ec9b290d7f37791f70874fb3`; receipt SHA `8c2b402d479dce4da8a184486a7042fe92eaab2def6f0ae2411f11968c9cd368`. The separately timestamped implementation comparison matched core and native engine to the earlier confirmed implementation; it was observed after launch and is not represented as a preregistration.
