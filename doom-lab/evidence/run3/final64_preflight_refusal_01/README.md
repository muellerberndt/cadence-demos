# Preserved preflight refusal

The first final64 launch attempt stopped before freezing or playing any episode because the historical H300 feedback gzip writer had not closed. Its missing gzip footer caused the reserved-seed audit to fail. The scan read 1,733 prior files and 374,825,908 decompressed bytes, finding no reserved seed integers. The sole parsing error was the open `runs/practice_horizon_01/h300/feedback.jsonl.gz`.

The original failed attempt remains unchanged on AWS at `/home/ec2-user/doom-v3-20260929/runs/final64_confirmation_01`, with no child processes or gameplay. After H300 completed, the identical code, checkpoint pair, 64 seeds and criteria passed the audit and ran once in `final64_confirmation_02`. No parser relaxation or candidate substitution was used.
