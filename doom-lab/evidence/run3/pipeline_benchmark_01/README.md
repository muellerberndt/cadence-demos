# Scheduling-only native feedback comparison

Twenty workers processed the same four H144 contexts in ABBA order. Serial
per-context barriers took17.044/17.183seconds; multiple contexts in flight took
15.565/15.729seconds, a1.094× mean speedup under concurrent campaign load.
Fresh pool startup is included. Repair/feedback overlap was not tested.

All320fresh engines and10,468continuation queries qualified. After removing
only timing fields, every native branch witness, return, event, action and
qualification record matched exactly across all four trials. No parameters,
tolerances, native reward definitions or deployment changed. The modest gain
does not justify claiming a large end-to-end acceleration.

Compact freeze and receipt are local. Complete compressed native traces remain
AWS at`runs/pipeline_benchmark_01/`.
