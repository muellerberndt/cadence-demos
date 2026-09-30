"""Bounded model-intervention diagnostics, never training or deployable checkpoints.

Zeroing weights on detached diagnostic clones is intentionally a private-state
intervention. It is not a public Cadence admission and must never be promoted,
saved as a trained bundle, or confused with a learned ablation control. Every
reported score still comes from the ordinary qualified coupled settlement.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np

from .brain import Brain, load_bundle, query
from .interface import canonical, digest, validate_inputs


def intervention_indices(brain):
    policy = set(next(p['indices'] for p in brain.inspect()['populations'] if p['name'] == 'policy'))
    return {
        'zero_all_residual_reads': [i for i, (kind, _, _) in enumerate(brain.graph.edges) if kind == 'residual'],
        'zero_latent_readback_to_policy': [i for i, (kind, _, target) in enumerate(brain.graph.edges)
            if kind in ('state', 'residual') and target in policy],
        'zero_direct_current_pixels_to_policy': [i for i, (kind, source, target) in enumerate(brain.graph.edges)
            if kind == 'input' and source < 1024 and target in policy],
    }


def diagnostic_clone(brain, indices, *, device='cpu'):
    """Private experimental surgery; caller may query but must not deploy this object."""
    clone = Brain.from_snapshot(brain.snapshot(), device=device)
    weights = list(clone.weights)
    for index in indices:
        weights[index] = 0.
    clone._weights = tuple(weights)
    return clone


def measure(bundle, contexts, *, row_ids=None, device='cpu'):
    if not 1 <= len(contexts) <= 256:
        raise ValueError('Causal probe requires 1..256 prospectively chosen contexts')
    for inputs in contexts:
        validate_inputs(inputs)
    contexts = json.loads(canonical(contexts))
    if row_ids is None:
        row_ids = list(range(len(contexts)))
    if len(row_ids) != len(contexts):
        raise ValueError('Each context needs its exact source row identity')
    brain, data = load_bundle(bundle, device=device)
    before = brain.snapshot()
    budget = data['query_budget']
    started = time.monotonic()
    baseline = [query(brain, inputs, budget=budget) for inputs in contexts]
    rows = []
    for label, indices in intervention_indices(brain).items():
        clone = diagnostic_clone(brain, indices, device=device)
        answers = [query(clone, inputs, budget=budget) for inputs in contexts]
        comparisons = []
        for index, (reference, answer) in enumerate(zip(baseline, answers)):
            both = reference['qualified'] and answer['qualified']
            comparisons.append({'row_id': row_ids[index], 'baseline_qualified': reference['qualified'],
                'intervention_qualified': answer['qualified'], 'baseline_action': reference['action'],
                'intervention_action': answer['action'],
                'max_abs_score_delta': float(np.max(np.abs(np.asarray(reference['scores'])-
                    np.asarray(answer['scores'])))) if both else None,
                'action_changed': bool(reference['action'] != answer['action']) if both else None,
                'baseline_seconds': reference['query_seconds'], 'intervention_seconds': answer['query_seconds']})
        comparable = [r for r in comparisons if r['max_abs_score_delta'] is not None]
        rows.append({'intervention': label, 'zeroed_edges': len(indices),
            'intervened_weights_sha256': digest(canonical(clone.weights)),
            'queries': len(answers), 'qualified': sum(a['qualified'] for a in answers),
            'jointly_qualified': len(comparable), 'action_changes': sum(r['action_changed'] for r in comparable),
            'max_abs_score_delta': max((r['max_abs_score_delta'] for r in comparable), default=None),
            'mean_max_abs_score_delta': float(np.mean([r['max_abs_score_delta'] for r in comparable])) if comparable else None,
            'comparisons': comparisons})
    if brain.snapshot() != before:
        raise RuntimeError('Causal probe unexpectedly mutated the original brain')
    return {'schema': 'doom-v3-causal-probe/1', 'checkpoint_sha256': data['hashes']['checkpoint_sha256'],
        'genome': data['genome'], 'context_sha256': digest(canonical(contexts)), 'row_ids': row_ids,
        'query_budget': budget, 'device': device, 'baseline_qualified': sum(a['qualified'] for a in baseline),
        'queries_per_variant': len(contexts), 'results': rows, 'original_preserved': True,
        'wall_seconds': time.monotonic()-started,
        'interpretation': 'Detached model interventions, not admitted training. Qualified score/action sensitivity measures causal use on these contexts only; no learning, retention, recursion advantage or gameplay claim.'}


def main():
    from .collection import atomic_json
    from .tasks import sha_file
    from .training import unpack
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--rows', type=int, default=32)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError('Causal receipts are immutable')
    if not 1 <= args.rows <= 256:
        raise ValueError('Rows must be in 1..256')
    _, bundle = load_bundle(args.bundle, device='python')
    metadata = json.loads((args.dataset/'dataset.json').read_text())
    if metadata['normalizer'] != bundle['normalization'] or metadata['contract'] != bundle['contract']:
        raise ValueError('Dataset conditioning/history must match the exact deployed bundle')
    for name in ('inputs', 'rows'):
        path = args.dataset/('inputs.npy' if name == 'inputs' else 'rows.npz')
        if sha_file(path) != metadata[name+'_sha256']:
            raise ValueError('Dataset custody mismatch: '+name)
    with np.load(args.dataset/'rows.npz', allow_pickle=False) as rows:
        ids = np.flatnonzero(~rows['training_mask'])
    if len(ids) == 0:
        raise ValueError('Prepared dataset has no development contexts')
    ids = ids[np.linspace(0, len(ids)-1, min(args.rows, len(ids)), dtype=int)].tolist()
    inputs = np.load(args.dataset/'inputs.npy', mmap_mode='r', allow_pickle=False)
    result = measure(bundle, [unpack(inputs[i]) for i in ids], row_ids=ids)
    result.update(dataset_sha256=sha_file(args.dataset/'dataset.json'),
                  script_sha256=sha_file(__file__), selection='Evenly spaced development row IDs; no outcome selection')
    atomic_json(args.out, result)
    print(json.dumps({k: result[k] for k in ('checkpoint_sha256', 'baseline_qualified', 'wall_seconds')}))


if __name__ == '__main__':
    main()
