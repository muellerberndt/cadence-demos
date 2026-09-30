# Medium and large GPU-trained development candidates

All four frozen models completed the same16 Basic development seeds used in
the earlier screen. This is repeated development selection, not fresh
confirmation. All were evaluated on CPU.

| Model | Native wins/16 | Mean return | Mean native tics |
| --- | ---: | ---: | ---: |
| Medium depth3, sensor connections | 14 | −137.6875 | 168.5625 |
| Medium depth3, no sensor connections | 3 | −238.1250 | 244.8750 |
| Large depth3, sensor connections | 11 | −165.8125 | 174.6250 |
| Large depth3, no sensor connections | 3 | −238.1250 | 244.8750 |

The screen took101.19s. Independent verification checks all64 episodes,
3,343/3,343 qualified queries and13,327 native tics. There are no missing
episodes, query refusals or execution errors. Source, bundle and trace hashes,
native returns and strict success predicates are consistent.

Both models without sensor connections have the same aggregate return and
success count, but their full raw-frame/action/native-transition traces match
only on the three successful episodes. Their13 failures are not byte-identical
policies. These weak results do not justify an additional causal diagnostic as
a promising no-skip candidate. Increasing total patches alone has not resolved
the default-scale failure; separate initialization-scale candidates remain a
different development experiment.

The medium connected model's14/16 is an exploratory result selected from
multiple candidates on this same seed set. It is not evidence of a reliable
advantage over the13/16 small model. Full records remain at AWS
`/home/ec2-user/doom-v3-20260929/runs/gpu_development_16_02`; this directory holds
the small frozen protocol, summary and independent consistency receipt.
