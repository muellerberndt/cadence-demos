"""Read the arousal law per moment in one royale: mode, want, surprise, error, the readings
it is measured against, and the sampling temperature. Usage:
    .venv/bin/python scripts/arousal_readings.py [league] [moments] [stage-json]
Example (the ring stage): scripts/arousal_readings.py league-evolved 600 '{"need":0,"reset":true}'
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import arena.brain as ab  # noqa: E402
from arena.league import League  # noqa: E402
from arena.royale import Fighter, run_royale  # noqa: E402

league = League(sys.argv[1] if len(sys.argv) > 1 else "league-evolved")
moments = int(sys.argv[2]) if len(sys.argv) > 2 else 600
stage = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
names = [n for n, _ in sorted(league.data["robots"].items(), key=lambda kv: -kv[1]["elo"])[:6]]
log: dict[str, list] = {n: [] for n in names}
original = ab.RobotBrain.moment


def moment(self, x, reward, done=False):
    out = original(self, x, reward, done)
    a = self.brain.last_arousal or {}
    ar = self.brain.arousal
    log[self.blueprint.name].append(
        (a.get("mode"), a.get("want", 0.0), a.get("surprise", 0.0), a.get("error", 0.0), ar.scale, ar.usual,
         ar.recent, ar.longrun, a.get("temperature"), ar.outcomes)
    )
    return out


ab.RobotBrain.moment = moment
fighters = [Fighter(n, league.blueprint(n), "brain", league.brain_path(n), stage=stage) for n in names]
out = run_royale(fighters, seed=77, duration=moments, zone_moments=int(moments * 5 / 6), workers=0, record=False, save=False)
print(f"{out['moments']} moments, stage {stage}")
print(f"{'robot':13} {'aroused':>7} {'want>0.2':>8} {'surp>0':>7} {'want':>6} {'surp':>6} {'|err|':>6} {'usual':>6} {'scale':>6} {'recent':>7} {'longrun':>7} {'own outcomes':>12} {'T sampled':>9}")
for n in names:
    rows = log[n]
    mode = np.array([r[0] == "aroused" for r in rows]); want = np.array([r[1] for r in rows]); surp = np.array([r[2] for r in rows])
    err = np.array([r[3] for r in rows]); last = rows[-1]; temps = [r[8] for r in rows if r[8] is not None]
    print(f"{n:13} {mode.mean():7.2f} {(want > 0.2).mean():8.2f} {(surp > 0).mean():7.2f} {want.mean():6.2f} {surp.mean():6.2f} "
          f"{err.mean():6.3f} {last[5]:6.3f} {last[4]:6.3f} {last[6]:7.3f} {last[7]:7.3f} {last[9]:12d} {np.mean(temps) if temps else 0:9.2f}")
