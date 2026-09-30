"""Estimated targets around one frozen, qualified Cadence policy.

No learning or private parameter access occurs here. Own-score rehearsal is a
model prediction, not a native reward witness or a teacher truth label.
"""
import numpy as np
from .practice import preference_target

ETAS = (0., .1, .25, 1.)
SCHEMA = 'doom-frozen-score-native-rank-blend/1'


def score_vector(scores):
    values = np.asarray(scores, dtype=np.float64)
    if values.shape != (20,) or not np.isfinite(values).all():
        raise ValueError('Twenty finite qualified policy scores are required')
    if (np.abs(values) > 1).any():
        raise ValueError('Qualified policy scores must respect the declared unit state bound')
    return values.copy()


def blend_native_target(scores, native_values, eta):
    """Ties skip; eta=0 and eta=1 preserve exact own-score and rank controls."""
    if isinstance(eta, bool) or eta not in ETAS:
        raise ValueError('Declare eta as one of 0, .1, .25 or 1 (hard-rank control)')
    baseline = score_vector(scores)
    lesson = preference_target(native_values)
    if lesson is None:
        return None
    preference = score_vector(lesson['targets'])
    target = baseline if eta == 0 else preference if eta == 1 else (1-eta)*baseline + eta*preference
    if (np.abs(target) > 1).any() or not np.isfinite(target).all():
        raise ValueError('Convex target left declared bounds; never clip silently')
    return dict(schema=SCHEMA, source='estimate', eta=float(eta),
        targets=target.tolist(), frozen_actor_scores=baseline.tolist(),
        native_rank_preferences=lesson['targets'], native_values=lesson['native_values'],
        best_actions=lesson['best_actions'], is_return_or_Q=False,
        interpretation='Estimated preference blend around a frozen qualified model prediction; not a native target witness')
