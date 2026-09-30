The matched experiment produced a guarded autonomous improvement with144-tic feedback. Its selected checkpoint was also selected by300-tic feedback; the36-tic control produced no promotion. These results use repeated development gates. Independent confirmation is a separate experiment and is not included in this receipt.

All three arms used the exact same128 actual founder contexts from ten episodes, in the same order. The source was the prespecified first256 lifetime1 transitions, selected without new branch labels. Per-episode quotas were allocated before evenly spacing selections across each recorded prefix. An earlier unlabeled subset with an early-prefix bias was retained as explicitly superseded; no arm trained on it.

| Native horizon | Informative / verified contexts | Qualified repair admissions | Example presentations | Selected promotions | Total seconds | Continuation queries |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 36 | 71 /128 | 8 | 128 | 0 | 387.61 | 20,030 |
| 144 | 128 /128 | 16 | 256 | 1 | 1007.91 | 73,719 |
| 300 | 128 /128 | 16 | 256 | 1 | 1277.49 | 103,993 |

Every context reconstructed exactly, and every continuation query qualified. Each arm used2,560 fresh engines and140,640 prefix-replay tics. Branch tics were90,235 /303,896 /424,044 respectively. All three processes exited normally, completed all scheduled contexts, and closed their feedback streams. The finite parallel campaign took1280.32seconds. The unmatched numbers of informative contexts and admissions are part of the horizon intervention; this is not a matched-update or matched-time comparison.

The unchanged gate retained every founder and current-champion success, required nondecreasing mean native return, and required strict improvement. The founder won7/8 with mean return−147.5. Both longer arms selected the **identical** checkpoint `ad9b330cd1c1c582a0bb135956f87a9f8e4c0f106d80c35bb60b39c0328ef2cc` after their first four public Cadence estimate repairs:8/8 wins and mean−29.125. These first repairs presented32 new native-preference examples and32 old replay examples. No new expert label or parameter-update shortcut was used.

Subsequent candidate win counts / mean returns were:

-36:6/8 /−58.5, then2/8 /−213.625; both rejected.
-144:initial8/8 /−29.125 accepted, then6/8 /−57.5,7/8 /−114.125,2/8 /−221.625 rejected.
-300:the same initial8/8 /−29.125 accepted, then7/8 /−46.625,5/8 /−134.75,5/8 /−73.0 rejected.

Across the same128 contexts, the preferred action set differed between36 and144 in105 cases, and between144 and300 in7 cases. Longer feedback therefore changed action supervision substantially; it did not simply rescale the same targets. The network still predicted centered policy preferences, not Q values or expected returns. The36 control kept its original native contract/divisor300;144/300 used the separately verified source-bound Basic contract and divisors864/1800.

The first promotion was independently restored and checked against its four public repair admissions,32 native contexts, original founder binding and exact gate digest. All eight gameplay traces passed file/content hashes, query-count checks, exact native reward summation, terminal status and positive native kill-delta checks. See `first_promotion_proof.json`. This verifies the recorded development gain; it does not guarantee unseen-seed success or broad Doom competence.

For the next bounded practice wave,144tics is the better tested cost choice:300tics selected the same final checkpoint and required41% more continuation queries and27% more wall time. Continued learning should freeze the new active champion as that next wave's continuation while retaining the original founder separately. A fixed-source within-wave control must remain explicit.

Full feedback, traces and every rejected candidate remain on AWS at `/home/ec2-user/doom-v3-20260929/runs/practice_horizon_01/` (132,463,477bytes); fixtures are6,639,672bytes. Local files are compact receipts only. No confirmation seed was consumed by this experiment.
