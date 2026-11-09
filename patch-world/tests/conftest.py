import os
import sys
from pathlib import Path

for _name in ("OMP_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ.setdefault(_name, "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
