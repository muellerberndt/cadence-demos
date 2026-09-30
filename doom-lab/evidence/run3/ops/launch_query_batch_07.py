"""Bounded GPU-host launcher; the earlier wrapper syntax failure is retained."""
import json
import os
from pathlib import Path
import subprocess
import time

root = Path('/home/ec2-user/doom-gpu-bench')
prior = json.loads((root / 'runs/gpu_exposure_batch_05/receipt.json').read_text())
assert prior['status'] == 'complete'
bundle = next((root / 'runs/gpu_exposure_04/small_depth3_no_skip_centered_cuda_seed0_scale0.3_prior0.4_historyomit/checkpoints').glob('*epoch008*.json'))
code = root / 'code_gpu_query_batch_06'
env = dict(os.environ, PYTHONPATH=str(code) + ':' + str(root / 'cadence/src'),
           OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
command = ['/opt/pytorch/bin/python', '-m', 'v3.query_batch_benchmark', '--bundle', str(bundle),
           '--dataset', str(root / 'dataset_baby_02'), '--out', str(root / 'runs/gpu_query_batch_07'),
           '--wall-seconds', '600']
result = subprocess.call(['timeout', '--signal=TERM', '--kill-after=15', '620', *command], cwd=code, env=env)
(root / 'gpu_query_batch_07_exit.json').write_text(json.dumps(dict(returncode=result, ended_unix=time.time())) + '\n')
raise SystemExit(result)
