# Deeper-path sensitivity on twelve fixed Basic contexts

All three original snapshots were preserved. These are detached, untrained
weight interventions, with every reported query qualified; they are not native
gameplay tests or candidates for deployment.

| Checkpoint | Remove latent readback into policy | Remove all residual reads | Rotate visible inputs, keep actual motor history |
| --- | ---: | ---: | ---: |
| Forced depth3, scale0.3/prior0.4, b106afac |12/12 changed actions |0/12 |0/12 |
| Forced depth3, scale1/prior0.4, fc409482 |12/12 |0/12 |7/12 |
| Confirmed H144 learner ad9b330c |1/12 |0/12 |6/12 |

Both forced-depth models have no direct pixel or motor-history policy edges;
those zero-edge controls changed no scores. The confirmed learner changed all
12 actions when its direct pixel-policy edges were removed and2/12 when direct
motor-history edges were removed. These results show sampled causal dependence,
not that recursive depth improves gameplay. In particular, the scale0.3 model
can depend on its latent population yet retain a constant action under this
limited visual permutation. Score sensitivity alone is insufficient.

The three JSON results and source/context/bundle freeze are retained here.
Full source copies and diagnostic log remain AWS under
`runs/forced_deep_causal_01/`; no altered model was exported.
