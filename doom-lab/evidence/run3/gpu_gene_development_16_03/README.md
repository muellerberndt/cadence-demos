# Initialization scales and recovered practice diagnostic

All48 scheduled Basic episodes completed; independent verification accounts for
2,232 qualified queries and8,898 native tics without missing episodes, refusals
or errors. The two no-sensor-connection models used GPU initialization
scales1 and2, with prior0.4. Both won3/16, matching the default-scale failure
count. Mean returns were−238.125 and−239.0625. Neither is a promising native
skill result; no additional causal probe was run for them.

The third model is the exact reconstructed checkpoint
`abdb48bacbf5e0e3a1aae7f42f0cd40122cccf672f259c70e5e63ed946cf1823`,
selected retrospectively from15 practice gates and previously rejected for
losing a native success. It is a diagnostic, not a deployment.

On these16 reused development cases it and the original founder both won13.
The candidate gained one success and lost one;12 returns improved,one worsened
and three tied. Mean return increased160.5625; mean native duration decreased
111.5 tics. Exploratory paired-bootstrap95% intervals were[73.5625,245.8125]
for return gain and[−170.1875,−53.125] for tic change. The10,000 resamples use
seed717006; these intervals do not convert retrospective development selection
into final confirmation.

The screen took120.22s; the recovered model's16 episodes took12.01s with four
workers. The subsequent additional24-case development screen in
`../practice_recovered_development_24_01/` found a real success tradeoff and
must accompany any interpretation of this favorable16-case result.
