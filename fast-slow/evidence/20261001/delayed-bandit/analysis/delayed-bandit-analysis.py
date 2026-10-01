import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path('/home/ec2-user/cadence-060-delayed-bandit-20261001/run')
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def same_number(a, b):
    require(math.isclose(a, b, rel_tol=0, abs_tol=2e-14), (a, b))


def metric(rows, name):
    return statistics.mean(row[name] for row in rows)


def normalize(record):
    return {k: v for k, v in record.items() if k not in ('seconds', 'issued_tick', 'executed_tick', 'due_tick', 'outcome_tick')}


def journal_digest(records):
    return hashlib.sha256(('\n'.join(canonical(normalize(x)) for x in records) + '\n').encode()).hexdigest()


protocol = read(ROOT / 'protocol.json')
data = read(ROOT / 'data.json')
body = {r['id']: r for phase in data.values() for r in phase}
require(sha(ROOT / 'data.json') == protocol['data_sha256'], 'data identity')
require(all(sha(Path(p)) == h for p, h in protocol['sources'].items()), 'source identity')
execution = read(ROOT / 'execution.json')
require(len(execution) == 30 and all(x['code'] == 0 for x in execution), 'execution completeness')
totals = Counter()
cases = []
identities = {}
d0_actions = []
for seed in protocol['seeds']:
    for arm in protocol['arms']:
        for delay in protocol['delays']:
            folder = ROOT / f'{arm}-seed{seed}-delay{delay}'
            report = read(folder / 'result.json')
            require(report['status'] == 'complete' and report['sources_unchanged'], folder.name)
            require(report['protocol_sha256'] == sha(ROOT / 'protocol.json'), 'protocol identity')
            updates = read(folder / 'updates.json')
            evaluations = read(folder / 'evaluations.json')
            journals = {name: [json.loads(line) for line in (folder / f'{name}.jsonl').read_text().splitlines()] for name in ('calls', 'decisions', 'executions', 'outcomes', 'surprise')}
            for filename, expected in report['journals'].items():
                require(sha(folder / filename) == expected['sha256'] and (folder / filename).stat().st_size == expected['bytes'], 'journal identity')
            require(len(updates) == 192 and all(u['accepted'] and u['qualified'] and u['source'] == 'witness' and u['batch_size'] == 16 for u in updates), 'admissions')
            require(report['admission_counts'] == {'started':192, 'returned':192, 'accepted':192, 'refused':0, 'interrupted_unknown_work':0}, 'admission counts')
            require(len(evaluations) == 384 and all(q['qualified'] for q in evaluations), 'evaluations')
            require(len(journals['calls']) == 3840 and all(c['qualified'] for c in journals['calls']), 'all calls qualified')
            require(len(journals['decisions']) == len(journals['executions']) == len(journals['outcomes']) == 3456, 'episode cardinality')
            require(len(journals['surprise']) == 192, 'post-update diagnostic cardinality')
            require(report['body_ticks'] == 3456 * (delay + 1), 'actual delay ticks')
            outcomes = {}
            for index, (issue, execute, outcome) in enumerate(zip(journals['decisions'], journals['executions'], journals['outcomes'], strict=True)):
                row = body[issue['row']]
                require(issue['decision_id'] == execute['decision_id'] == outcome['decision_id'] == index + 1, 'decision order')
                require(all(execute[k] == v and outcome[k] == v for k, v in issue.items()), 'immutable proposal')
                require(all(outcome[k] == v for k, v in execute.items()), 'immutable execution')
                require(issue['issued_tick'] == execute['executed_tick'] == index * (delay + 1), 'issue/execute ticks')
                require(execute['due_tick'] == outcome['outcome_tick'] == index * (delay + 1) + delay, 'outcome delay')
                require(issue['inputs'] == {'u':[row['u']], 'v':[row['v']]}, 'only raw inputs')
                same_number(issue['actual_x'], math.tanh(math.tanh(row['u'])) + row['delta'])
                action = outcome['executed_action']
                same_number(outcome['reward'], (2*action - 1)*math.tanh(row['v'] + row['delta']))
                same_number(outcome['original_surprise'], outcome['reward'] - issue['original_forecasts'][action])
                outcomes[index + 1] = outcome
            for u, surprise in zip(updates, journals['surprise'], strict=True):
                outcome = outcomes[surprise['decision_id']]
                require(u['event_id'] == outcome['event_id'], 'update/decision custody')
                require(surprise['original_surprise'] == outcome['original_surprise'], 'unchanged historical surprise')
                require(surprise['current_model_id'] == u['after_sha256'], 'post-update model custody')
            group_rows = {name: [r for r in evaluations if r['check'] == name] for name in ('clean-gate', 'policy-before', 'clean-retention', 'policy-final')}
            metrics = {}
            for name, rows in group_rows.items():
                require(len(rows) == (64 if name.startswith('clean') else 128), 'evaluation group completeness')
                for r in rows:
                    outcome = outcomes[r['decision_id']]
                    bodyrow = body[r['row']]
                    require(r['executed_action'] == outcome['executed_action'], 'evaluation executed action')
                    same_number(r['reward'], outcome['reward'])
                    same_number(r['prediction_absolute_error'], abs(outcome['original_surprise']))
                    same_number(r['oracle_regret'], abs(math.tanh(bodyrow['v'] + bodyrow['delta'])) - outcome['reward'])
                    if name.startswith('policy'):
                        require(outcome['executed_action'] == outcome['proposed_action'], 'actual greedy policy execution')
                values = {field: metric(rows, field) for field in ('past_absolute_error', 'prediction_absolute_error', 'reward', 'oracle_regret')}
                head = [metric([r for r in rows if r['executed_action'] == action], 'prediction_absolute_error') for action in (0, 1)]
                clean_gate = values['past_absolute_error'] <= .03 and all(x <= .03 for x in head) if name.startswith('clean') else None
                if name.startswith('clean'):
                    require(clean_gate, 'clean acquisition/retention gate')
                metrics[name] = {'n':len(rows), **values, 'head_mae':head, 'clean_gate':clean_gate, 'optimal_actions':sum(r['oracle_regret'] < 1e-15 for r in rows)}
                saved = next(g for g in report['groups'] if g['check'] == name)
                require(saved['clean_gate'] == clean_gate, 'saved gate')
                for field in values:
                    same_number(values[field], saved['means'][field])
            require(metrics['policy-final']['prediction_absolute_error'] <= .03 and report['primary_learning_gate'], 'learning gate')
            work = defaultdict(Counter)
            for call in journals['calls']:
                work[call['kind']].update(call['work'])
            surprise_metrics = {}
            for phase in ('clean', 'mixed'):
                pairs = [(u, s) for u, s in zip(updates, journals['surprise'], strict=True) if u['phase'] == phase]
                surprise_metrics[phase] = {
                    'n':len(pairs),
                    'historical_surprise_mae':statistics.mean(abs(s['original_surprise']) for _, s in pairs),
                    'post_update_forecast_error_mae':statistics.mean(abs(s['post_update_prediction_error']) for _, s in pairs),
                    'post_update_internal_p_error_rms':math.sqrt(statistics.mean(s['current_internal_errors'][1]**2 for _, s in pairs)),
                }
            identity = {name: journal_digest(rows) for name, rows in journals.items()}
            identity.update({name: sha(folder / name) for name in ('updates.json','evaluations.json','checkpoint-clean.json','checkpoint-mixed.json')})
            identities[arm, seed, delay] = identity
            cases.append({'name':folder.name,'arm':arm,'seed':seed,'delay':delay,'status':report['status'],'seconds':report['seconds'],'body_ticks':report['body_ticks'],'metrics':metrics,'work':{k:dict(v) for k,v in work.items()},'surprise':surprise_metrics,'report_sha256':sha(folder/'result.json')})
            totals.update({'arms':1,'accepted_updates':192,'training_row_presentations':3072,'qualified_calls':3840,'qualified_forecasts_and_probes':3648,'completed_episodes':3456,'clean_gates':2,'primary_learning_gates':1})
            if delay == 0:
                d0_actions.append([r['executed_action'] for r in group_rows['policy-final']])
delay_matches = []
for arm in protocol['arms']:
    for seed in protocol['seeds']:
        matches = identities[arm,seed,0] == identities[arm,seed,2] == identities[arm,seed,4]
        require(matches, f'delay trajectory mismatch {arm} {seed}')
        delay_matches.append({'arm':arm,'seed':seed,'exact_except_declared_time_fields':matches,'normalized_hashes':identities[arm,seed,0]})
d0 = [case for case in cases if case['delay'] == 0]
means = {}
for arm in protocol['arms']:
    arm_cases = [c for c in d0 if c['arm'] == arm]
    means[arm] = {phase:{name:statistics.mean(c['metrics'][phase][name] for c in arm_cases) for name in ('prediction_absolute_error','reward','oracle_regret','optimal_actions')} for phase in ('policy-before','policy-final')}
    means[arm]['work'] = {kind:{field:sum(c['work'][kind].get(field,0) for c in arm_cases) for field in ('evaluations','edge_visits','patch_visits','proposals','backtracks')} for kind in ('forecast','admission','post-update-forecast')}
    means[arm]['surprise'] = {phase:{field:statistics.mean(c['surprise'][phase][field] for c in arm_cases) for field in ('historical_surprise_mae','post_update_forecast_error_mae','post_update_internal_p_error_rms')} for phase in ('clean','mixed')}
paired = []
for seed in protocol['seeds']:
    a,b = [next(c for c in d0 if c['arm']==arm and c['seed']==seed) for arm in ('ordinary','observer')]
    paired.append({'seed':seed,'regret_reduction':a['metrics']['policy-final']['oracle_regret']-b['metrics']['policy-final']['oracle_regret'],'mae_reduction':a['metrics']['policy-final']['prediction_absolute_error']-b['metrics']['policy-final']['prediction_absolute_error']})
print(json.dumps({'schema':'delayed-bandit-independent-aggregate-v1','protocol_sha256':sha(ROOT/'protocol.json'),'source_identity_verified':True,'totals':dict(totals),'cases':cases,'delay_matches':delay_matches,'unique_d0_means':means,'unique_d0_pairs':paired,'all_final_policy_actions_identical':all(x==d0_actions[0] for x in d0_actions),'architecture_regret_criterion_met':statistics.mean(p['regret_reduction'] for p in paired)>=.005 and all(p['regret_reduction']>0 for p in paired),'limits':['Independent raw arithmetic/custody aggregation; no numerical settlement or learning replay.','Delayed ownership is explicit single-flight collector memory, not learned temporal memory.','Original surprise and post-update mismatch remain distinct; post-update probe is on a training-batch member.','Architecture comparison uses five D0 seed pairs; delays do not add independent evidence.']},sort_keys=True))
