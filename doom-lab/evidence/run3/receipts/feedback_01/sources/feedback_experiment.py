"""Frozen2x2 Basic feedback diagnostic; development selection, no live publication.

Both targets use the same reconstructible contexts, ordered batch boundaries,
initial checkpoint and public observe_batch repair. New targets never share a
head with legacy155-row labels. Output bundles deliberately use a v3 schema.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
import math
from pathlib import Path
import time

from feedback import FeedbackPool, CONTRACTS, HOLD, CONTINUE, V2, sha, target_contract
import numpy as np
from basic_env import identity, TRANSFORM, ACTION_NAMES
from exporter import atomic_json
from models import Brain, load_bundle, query
from online import validate_transition, promotion_gate

OLD_SEEDS = tuple(range(740000, 740008))
NEW_SEEDS = tuple(range(742000, 742024))
SEEDS = OLD_SEEDS + NEW_SEEDS


def contexts_from_journal(path, expected_sha, count=64):
    raw = Path(path).read_bytes()
    if str(path).endswith('.gz'):
        raw = gzip.decompress(raw)
    if sha(raw) != expected_sha:
        raise ValueError('Journal raw bytes differ from declared immutable source')
    if not raw.endswith(b'\n'):
        raise ValueError('Journal source ends with an incomplete record')
    queued, verified, selected = {}, set(), []
    for line in raw.splitlines():
        event = json.loads(line)
        if event['event'] == 'transition_queued':
            record = event['transition']
            key = (record['episode_id'], record['step_index'])
            if key in queued and queued[key] != record:
                raise ValueError('Repeated transition identity changed')
            queued[key] = record
        if event['event'] == 'transition_verified':
            key = (event['episode_id'], event['step_index'])
            if key not in queued:
                raise ValueError('Verified record has no queued prefix in this segment')
            if key not in verified:
                record = validate_transition(queued[key])
                if record.get('behavior_source') != 'autonomous':
                    raise ValueError('Diagnostic requires explicit autonomous actor provenance')
                selected.append(dict(record=record, original_hold_labels=event['targets']))
                verified.add(key)
                if len(selected) == count:
                    break
    if len(selected) != count:
        raise ValueError(f'Expected{count} verified contexts; found{len(selected)}')
    return selected


def strict_gate(anchor, champion, candidate, seeds=SEEDS, improvement=.1):
    result = promotion_gate(champion, candidate, seeds, improvement)
    byseed = {row['seed']: row for row in candidate}
    reference = {row['seed']: row for row in anchor}
    current = {row['seed']: row for row in champion}
    old = [seed for seed in OLD_SEEDS if seed in seeds]
    if any(seed not in byseed or seed not in reference or seed not in current for seed in old):
        result['reasons'].append('Original development seed coverage incomplete')
    elif old:
        if any(reference[s]['killed'] and not byseed[s]['killed'] for s in old):
            result['reasons'].append('Lost an original-anchor success')
        mean = sum(byseed[s]['return_'] for s in old) / len(old)
        for name, ref in [('starting_anchor', reference), ('current_champion', current)]:
            if mean + 1e-12 < sum(ref[s]['return_'] for s in old) / len(old):
                result['reasons'].append(f'Original eight mean regressed versus{name}')
    result['passed'] = not result['reasons']
    result['interpretation'] = 'repeated32-seed development selection only; no fresh confirmation'
    return result


def free_loss(brain, rows):
    values, sweeps = [], 0
    start = time.monotonic()
    for inputs, labels in rows:
        output, result = query(brain, inputs['sensors'])
        sweeps += result.get('sweeps',0)
        if not result['qualified']:
            return dict(mse=None, qualified=False, queries=len(values)+1,
                        sweeps=sweeps, seconds=time.monotonic()-start)
        values.append(float(np.mean((output - labels['utility'])**2)))
    return dict(mse=float(np.mean(values)), qualified=True, queries=len(values),
                sweeps=sweeps, seconds=time.monotonic()-start)


def v3_bundle(initial, snapshot, contract, continuation_sha, provenance):
    """v2 intentionally cannot import this bundle; target semantics travel with it."""
    norm = initial['normalization']
    return dict(schema='doom-feedback-diagnostic-bundle/1', snapshot=snapshot, normalization=norm,
                metadata=dict(scenario='basic', transform=TRANSFORM,
                    input_shape=246, output='utility', action_names=list(ACTION_NAMES),
                    repeat_tics=12, query_budget=512,
                    target_contract=target_contract(contract, continuation_sha),
                    initialization_checkpoint_sha256=sha(initial['snapshot']),
                    role='development_candidate_not_independently_confirmed',
                    hashes=dict(checkpoint_sha256=sha(snapshot),
                        normalization_values_sha256=sha(json.dumps(norm, sort_keys=True, separators=(',',':'), allow_nan=False))),
                    **provenance))


def run_arm(name, contract, lifetime, rows, initial, anchor, pool, out, protocol):
    destination = out / name
    destination.mkdir()
    champion = initial['snapshot']
    candidate = Brain.from_snapshot(champion, device='cpu')
    champion_rows = anchor
    baseline_loss = free_loss(candidate, rows)
    events, gates = [], []
    started = time.monotonic()
    starting_cost = dict(pool.cost)
    updates, presentations, promotions, block = 0, 0, 0, 0
    status = 'complete'
    try:
        for epoch in range(protocol['epochs']):
            for start in range(0, len(rows), protocol['batch_size']):
                batch = rows[start:start+protocol['batch_size']]
                begin = time.monotonic()
                admission = candidate.observe_batch(batch, budget=protocol['training_budget'], source='estimate')
                accepted = bool(admission['accepted'] and admission['qualified'] and not admission.get('duplicate',False))
                event = dict(epoch=epoch, batch_start=start, accepted=accepted,
                    examples=len(batch), seconds=time.monotonic()-begin,
                    sweeps=admission.get('sweeps'), reason=admission.get('reason'),
                    event_id=admission.get('event_id'), checkpoint_sha256=sha(candidate.snapshot()))
                events.append(event)
                if not accepted:
                    status = 'admission_refused'
                    break
                updates += 1
                presentations += len(batch)
                block += 1
                final_batch = epoch == protocol['epochs']-1 and start+len(batch) == len(rows)
                if block >= lifetime or final_batch:
                    snapshot = candidate.snapshot()
                    begin = time.monotonic()
                    outcomes = pool.evaluate(snapshot, protocol['gate_seeds'])
                    gate = strict_gate(anchor, champion_rows, outcomes, protocol['gate_seeds'])
                    record = dict(update=updates, block_updates=block,
                        checkpoint_sha256=sha(snapshot), seconds=time.monotonic()-begin,
                        candidate=outcomes, champion=champion_rows, gate=gate)
                    gates.append(record)
                    # Every assessed candidate is retained independently of success.
                    (destination/f'candidate_update{updates:03d}.json').write_text(snapshot)
                    if gate['passed']:
                        champion, champion_rows = snapshot, outcomes
                        promotions += 1
                    candidate = Brain.from_snapshot(champion, device='cpu')
                    block = 0
                atomic_json(destination/'status.json', dict(status='running', updates=updates,
                    presentations=presentations, promotions=promotions, gates=len(gates),
                    seconds=time.monotonic()-started))
            if status != 'complete':
                break
    except Exception as error:
        status = 'error'
        events.append(dict(error=f'{type(error).__name__}: {error}'))
    finally:
        summary = dict(arm=name, contract=contract, lifetime=lifetime, status=status,
            updates=updates, presentations=presentations, promotions=promotions,
            seconds=time.monotonic()-started, baseline_loss=baseline_loss,
            final_loss=free_loss(Brain.from_snapshot(champion,device='cpu'), rows),
            champion_sha256=sha(champion), champion=champion_rows, admissions=events, gates=gates,
            evaluation_cost={k:v-starting_cost.get(k,0) for k,v in pool.cost.items()},
            scheduled_updates=protocol['epochs']*math.ceil(len(rows)/protocol['batch_size']))
        atomic_json(destination/'receipt.json', summary)
        atomic_json(destination/'bundle.json', v3_bundle(initial, champion, contract,
            sha(initial['snapshot']),dict(arm=name, candidate_lifetime=lifetime,
                protocol_sha256=sha(json.dumps(protocol,sort_keys=True,separators=(',',':'))),
                promotions=promotions, status=status)))
        atomic_json(destination/'status.json', {k:v for k,v in summary.items() if k not in ('admissions','gates','champion')})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True)
    parser.add_argument('--journal', required=True)
    parser.add_argument('--journal-sha256', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--contexts', type=int, default=64)
    parser.add_argument('--epochs', type=int, default=2)
    parser.add_argument('--smoke', action='store_true', help='Explicit non-comparison smoke:2contexts,1epoch,2development seeds')
    args = parser.parse_args()
    if args.contexts < 1 or args.epochs < 1:
        raise ValueError('Context count and epoch count must be positive')
    out = Path(args.out)
    if out.exists():
        raise FileExistsError('Refusing to overwrite a frozen experiment')
    count = 2 if args.smoke else args.contexts
    contexts = contexts_from_journal(args.journal, args.journal_sha256, count)
    path = Path(args.bundle)
    if path.is_dir(): path = path/'bundle.json'
    initial = json.loads(path.read_text())
    _, normalizer, metadata = load_bundle(path)
    initial_sha = sha(initial['snapshot'])
    if any(x['record'].get('policy_checkpoint_sha256') != initial_sha for x in contexts):
        raise ValueError('Context behavior provenance differs from frozen continuation champion')
    seeds = list(OLD_SEEDS[:2] if args.smoke else SEEDS)
    protocol = dict(schema='doom-feedback-factorial/1', smoke=args.smoke,
        source_hashes={p.name:sha(p.read_bytes()) for p in (Path(__file__),Path(__file__).with_name('feedback.py'),V2/'models.py',V2/'basic_env.py',V2/'online.py')},
        journal_raw_sha256=args.journal_sha256, initial_checkpoint_sha256=initial_sha,
        contexts=count, context_selection='first unique verified transitions in immutable journal order',
        context_values_sha256=sha(json.dumps(contexts,sort_keys=True,separators=(',',':'))),
        epochs=1 if args.smoke else args.epochs, batch_size=8, training_budget=2048,
        query_budget=512, replay_rows=0, original_legacy_labels_used=False,
        gate_seeds=seeds, gate_min_mean_return_improvement=.1,
        candidate_lifetimes=[1,4], contracts=[target_contract(c,initial_sha) for c in CONTRACTS],
        branches_per_context=12, workers=args.workers, blas_threads_per_worker=1,
        order='fixed input order each epoch; identical across all arms',
        continuation_frozen_for_entire_experiment=True,
        retention='starting/current champion old8 success and mean; no lost current32 success',
        interpretation='development-only factorial diagnosis; no fresh confirmation or live promotion',
        engine=identity())
    out.mkdir(parents=True)
    atomic_json(out/'freeze.json', protocol)
    atomic_json(out/'contexts.json', contexts)
    results, feedback_rows = [], []
    started = time.monotonic()
    try:
        with FeedbackPool(initial['snapshot'], normalizer, args.workers) as pool:
            anchor = pool.evaluate(initial['snapshot'], seeds)
            atomic_json(out/'anchor.json', anchor)
            if any(r['status'] != 'complete' or r['qualified_queries'] != r['queries'] or r['fallback_actions'] for r in anchor):
                raise RuntimeError('Initial champion gate incomplete or unqualified')
            for index, item in enumerate(contexts):
                paired = dict(index=index, contracts={})
                for contract in CONTRACTS:
                    result = pool.label(item['record'], contract)
                    paired['contracts'][contract] = result
                    if not result['ok']:
                        feedback_rows.append(paired)
                        atomic_json(out/'feedback.json', feedback_rows)
                        raise RuntimeError(f'Feedback refused at context{index} contract{contract}')
                    if contract == HOLD and result['labels'] != item['original_hold_labels']:
                        raise RuntimeError('Segmented hold36 control differs from original verified labels')
                feedback_rows.append(paired)
                atomic_json(out/'feedback.json', feedback_rows)
                atomic_json(out/'status.json',dict(phase='feedback',completed_contexts=len(feedback_rows),seconds=time.monotonic()-started,cost=pool.cost))
            for contract in CONTRACTS:
                rows = [({'sensors':item['record']['inputs']}, {'utility':label['contracts'][contract]['labels']}) for item,label in zip(contexts,feedback_rows)]
                for lifetime in (1,4):
                    name = ('hold36' if contract == HOLD else 'continue36')+f'_life{lifetime}'
                    result = run_arm(name,contract,lifetime,rows,initial,anchor,pool,out,protocol)
                    results.append(result)
                    atomic_json(out/'status.json',dict(phase='training',completed_arms=len(results),seconds=time.monotonic()-started,cost=pool.cost))
            final_cost = pool.cost
        eligible = [r for r in results if r['status']=='complete' and r['promotions']>0]
        selected = max(eligible, key=lambda r:(sum(x['return_'] for x in r['champion']),r['champion_sha256'])) if eligible else None
        summary = dict(schema=protocol['schema'], status='complete',seconds=time.monotonic()-started,
            cost=final_cost, selected_development_arm=selected['arm'] if selected else None,
            selection=f'maximum final{len(seeds)}-seed mean among complete arms with at least one passed gate; SHA tie-break',
            arms=[{k:v for k,v in r.items() if k not in ('admissions','gates')} for r in results],
            interpretation='No fresh confirmation, no live promotion; selected bundle requires separate review')
        atomic_json(out/'receipt.json',summary)
        print(json.dumps({k:v for k,v in summary.items() if k!='arms'}))
    except Exception as error:
        atomic_json(out/'failure.json',dict(status='error',error=f'{type(error).__name__}: {error}',
            completed_arms=[r['arm'] for r in results],completed_feedback_contexts=len(feedback_rows),seconds=time.monotonic()-started))
        raise


if __name__ == '__main__':
    main()
