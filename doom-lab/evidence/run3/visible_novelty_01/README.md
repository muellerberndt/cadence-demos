# Visible novelty native smoke, 2026-09-29

A small explicitly versioned reward gene produced informative preferences on two recorded spinning states where all 20 native action returns tied. It has **not** been trained or shown to improve navigation.

The source states are decisions 64 and 256 of one already recorded navigation development episode, seed 1220000000, checkpoint b106afac. Each action was intervened for 4 tics, followed by the same frozen qualified Cadence continuation, for 36 tics total. Native rewards and visible novelty were computed from the **same** branches. The first 20 branches were also replayed with the unchanged native-only feedback implementation; every action, transition, native event and reward matched exactly.

For both states, all 20native returns equaled -0.0036. The novelty variant ranked strafe_left and fire_strafe_left jointly highest. Intrinsic scores at the two states were 0.602980 and 0.592841 for these actions, versus 0.218634 and 0.202101 for continuing the existing turn_left behavior. Turning right also earned 0.341561 and 0.447104. Therefore the signal can break the reward tie here, but **still rewards rotation**. This is not an anti-spin result, two independent episodes, or evidence of useful travel.

The gene uses exactly the actor’s four valid visual-history references, with the same frozen coarse-image conditioning. It compares scene pixels y24:120,x20:300, excluding the HUD and lower weapon region; the largest 10% coordinate differences are trimmed. Distance below 0.03 gives 0; 0.20 or higher gives 1. Per-branch reward uses the maximum successor score, not a sum, with explicit beta 0 control versus beta 0.05 candidate. All thresholds/crop/weight choices are hand-set candidate genes, not established optima. Navigation’s native +1 goal remains larger than the bounded bonus and is the sole competence criterion. No geometry, labels, native position or teacher actions enter the bonus or actor.

The four-reference memory can forget views and cannot represent episodic novelty. Dynamic textures, occlusion and rotation remain hazards. The four unit checks verify static/missing-reference zero reward, exclusion of lower-screen changes, sparse-noise trimming, nearest-reference comparison and bounded scores; they do not prove semantic exploration.

The 60 counterfactual branch engines completed 480 qualified continuation queries, 32,880 native replay/branch tics in 17.7243 seconds. The two source-context reconstruction engines add 2 qualified actor checks and 1,288 tics; total diagnostic work was 62 engines, 482 qualified actor queries and 34,168 tics. The original receipt’s `cost` covers counterfactual branches only; the separate cost-accounting receipt makes this explicit without altering prior bytes.

A next experiment, if authorized, should compare beta 0 and beta 0.05 on the same fixed real contexts and frozen continuation, retain the bootstrap skills with declared replay, and judge only fresh native navigation goals plus Basic retention. It must preserve rotation and wall-stick failures. No model should be promoted for higher novelty alone.

Full AWS evidence: `/home/ec2-user/doom-v3-20260929/runs/visible_novelty_01`. Freeze SHA`3db800f3ce0fdc42274f005d01125430d1027320134473114806f800630e38ca`. Small receipts are local; contexts, checkpoints and branch traces remain on AWS.
