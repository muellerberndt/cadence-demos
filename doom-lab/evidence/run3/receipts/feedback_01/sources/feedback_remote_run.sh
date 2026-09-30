#!/usr/bin/env bash
# One bounded authorized AWS experiment; GNU timeout also terminates its group.
set -u
task_root=/home/ec2-user/doom-v3-20260929
task_python=/home/ec2-user/venv/bin/python
task_bundle=/home/ec2-user/doom-v2-20260929/runs/practice_sweep/new2/exports/skip_observer_seed2_practice_epoch04_db6df682f3c4/bundle.json
cd "$task_root" || exit 2
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export CADENCE_SRC="$task_root/cadence/src"
mkdir -p runs
task_started=$(date +%s)
timeout --signal=TERM --kill-after=30s 1800s "$task_python" cadence-demos/doom-lab/v3/feedback_experiment.py \
  --bundle "$task_bundle" \
  --journal datasets/cadence-v3-feedback-journal.jsonl.gz \
  --journal-sha256 5878eab6af3cbad9aa667f8d10a5f6d845c612bc0bb7e3d5bd9abc939193080a \
  --out runs/feedback_01 --workers 6
task_exit=$?
"$task_python" - "$task_started" "$task_exit" <<'PY'
import json,os,sys,time
from pathlib import Path
started,code=int(sys.argv[1]),int(sys.argv[2])
value=dict(schema='doom-feedback-process/1',started_unix=started,ended_unix=time.time(),
           exit_code=code,timeout_seconds=1800,kill_grace_seconds=30,
           status='complete' if code==0 else ('wall_timeout' if code in (124,137) else 'process_failure'))
path=Path('runs/feedback_01.process.json')
with path.open('w') as stream:
    json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
print(json.dumps(value))
PY
exit "$task_exit"
