# Forced-recursion Basic development comparison

Two small depth3 models were trained with both direct pixel-to-policy and direct action-history-to-policy connections disabled. On the same16development Basic seeds, scale0.3/prior0.4 (b106afac) won9/16, mean native return-156.0625 and177.875tics; scale1/prior0.4(fc409482) won5/16, return-199 and218.375tics. All32episodes completed and all1,589queries qualified. Independent full trace/hash/native predicate verification passed. Total wave time55.07s;6,340native tics.

The scale0.3 actor used only turn_left andfire_left. The scale1actor also moved forward and turned right;11/16episodes contained sustained two-action alternation. These are descriptive behaviors, not success predicates. This repeated development comparison does not establish a generalization or recursive benefit. Parent-owned causal probes separately test whether latent paths affect choices; the subsequent boundednavigation diagnostic is retained in `../forced_navigation_01`.

AWS full evidence: `/home/ec2-user/doom-v3-20260929/runs/gpu_history_development_16_04`; source brainSHA `d91ec34db618ace4e9c6f9c95bd1b7960b741cd8543ac84ac758bf6771495b99`. No frozen training sources or active models were changed.
