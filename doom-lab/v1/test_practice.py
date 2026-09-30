"""Contract and ownership tests; fake repairs never claim gameplay evidence."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from . import practice as p
from .interface import ACTION_BUTTONS, PORT_SHAPES, canonical, digest


def inputs():
    return {name: [0.] * width for name, width in PORT_SHAPES.items()}


def transition(action=12, *, terminal=False, tics=4, episode_tic=18):
    return dict(action=action, buttons=list(ACTION_BUTTONS[action]), requested_tics=4,
                tics=tics, rewards=[-1.] * tics, reward=-float(tics), terminal=terminal,
                dead=False, timeout=False, native_kill_delta=0., health_delta=0., episode_tic=episode_tic)


def record(episode='one', step=0):
    prior = [transition(episode_tic=18+4*i) for i in range(step)]
    return dict(task='basic', seed=1300000000, episode_id=episode, step_index=step,
                prefix_actions=[12] * step, prefix_outcomes=prior, raw_sha256='a' * 64,
                inputs=inputs(), executed_action=12, transition=transition(episode_tic=18+4*step),
                policy_checkpoint_sha256='b' * 64, qualified=True, fallback=False, behavior_source='autonomous')


def seed_row():
    return dict(source='bootstrap_seed', source_sha256='c'*64, row_id='c:0', split='training',
                task='basic', inputs=inputs(), targets=[.76]+[-.04]*19)


def result(value=0., success=True, seed=1220000000):
    return dict(task_id='basic', seed=seed, status='complete', queries=2, qualified_queries=2,
                fallback_actions=0, success=success, **{'return': value})


class FakeBrain:
    def __init__(self, generation=0):
        self.generation = generation
        self.owners = []

    def snapshot(self):
        return json.dumps({'generation': self.generation})

    def observe_batch(self, examples, *, event_id=None, budget, source):
        self.owners.append(threading.current_thread().name)
        assert source == 'estimate'
        self.generation += 1
        event_id = self.generation if event_id is None else event_id
        return dict(accepted=True, qualified=True, duplicate=False, event_id=event_id,
                    source=source, sweeps=1, stationarity=0.)


def bundle(generation=0):
    snapshot = FakeBrain(generation).snapshot()
    return dict(model_id='fixture', snapshot=snapshot, hashes={'checkpoint_sha256': digest(snapshot)},
                contract={'visual_lags': [1,4,16,64]}, normalization={}, genome={}, query_budget=512,
                target_contract={'target_gene': 'centered', 'is_return_or_Q': False}, metadata={})


def load(value, **_):
    value = p.copied(value)
    return FakeBrain(json.loads(value['snapshot'])['generation']), value


def make(brain, normalization, **kwargs):
    data = bundle(brain.generation)
    data.update(model_id=kwargs['model_id'], target_contract=kwargs['target_contract'], metadata=kwargs['metadata'])
    return data


class Teacher:
    def __init__(self, tied=False, block=None):
        self.tied, self.block = tied, block
    def label(self, row, contract):
        if self.block:
            self.block.wait(3)
        values = [0.] * 20
        if not self.tied:
            values[12] = 1.
        return {'ok': True, 'labels': values, 'contract': contract, 'branches': [], 'cost': {}}


class PracticeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patchers = [patch.object(p, 'load_bundle', load), patch.object(p, 'make_bundle', make),
                         patch.object(p, 'write_bundle', lambda path, data: p.atomic_json(path, data)),
                         patch.object(p, 'task_identity', lambda t: {'task_id': t})]
        for patcher in self.patchers:
            patcher.start()
        self.learners = []

    def tearDown(self):
        for learner in self.learners:
            learner.close(wait=True)
        for patcher in self.patchers:
            patcher.stop()
        self.temp.cleanup()

    def learner(self, **kwargs):
        config = kwargs.pop('config', p.PracticeConfig(new_rows=1, candidate_lifetime=1,
                            gate_tasks=('basic',), gate_seeds=(1220000000,)))
        evaluator = kwargs.pop('evaluator', lambda b: [result(float(json.loads(b['snapshot'])['generation']))])
        value = p.PracticeLearner.from_bundle(bundle(), journal_path=Path(self.temp.name)/f'{len(self.learners)}.jsonl',
                  config=config, seed_replay=[seed_row()], teacher=kwargs.pop('teacher', Teacher()), evaluator=evaluator, **kwargs)
        self.learners.append(value)
        return value

    def wait(self, learner, count):
        deadline = time.monotonic()+5
        while time.monotonic()<deadline:
            status = learner.status()
            if status['error']:
                self.fail(status['error'])
            if status['processed_transitions'] >= count and not status['busy']:
                return status
            time.sleep(.01)
        self.fail('worker did not complete fixture')

    def test_preference_winners_ties_and_no_information(self):
        self.assertIsNone(p.preference_target([4.]*20))
        unique = p.preference_target([0.]*12+[1.]+[0.]*7)
        self.assertAlmostEqual(unique['targets'][12], .76)
        self.assertAlmostEqual(sum(unique['targets']), 0.)
        tied = p.preference_target([1.,1.]+[0.]*18)
        self.assertAlmostEqual(tied['targets'][0], .36)
        self.assertEqual(tied['best_actions'], [0,1])

    def test_reject_nonfinite_values(self):
        with self.assertRaises(ValueError):
            p.preference_target([float('nan')]+[0.]*19)

    def test_executed_action_and_episode_alignment(self):
        p.validate_transition(record(step=2))
        broken = record(step=1)
        broken['transition']['action'] = 11
        with self.assertRaises(ValueError): p.validate_transition(broken)
        broken = record(step=1)
        broken['transition']['episode_tic'] += 1
        with self.assertRaises(ValueError): p.validate_transition(broken)

    def test_terminal_and_external_cutoff_contract(self):
        row = record()
        row['transition'] = transition(terminal=True,tics=2,episode_tic=16)
        row['transition']['timeout'] = True
        p.validate_transition(row)
        row['transition']['terminal'] = False
        with self.assertRaises(ValueError): p.validate_transition(row)
        row = record()
        row['collector_cutoff'] = True
        p.validate_transition(row)
        self.assertFalse(row['transition']['terminal'])
        row = record(step=1)
        row['transition']['terminal'] = True
        row['transition']['episode_tic'] = 0
        p.validate_transition(row)  # Real ViZDoom scenario success resets this clock.

    def test_history_cannot_cross_episode_terminal(self):
        row = record(step=1)
        row['prefix_outcomes'][0]['terminal'] = True
        with self.assertRaises(ValueError): p.validate_transition(row)
        p.validate_transition(record('new_episode',0))

    def test_retention_gate_keeps_each_success_and_task_return(self):
        config = p.PracticeConfig(gate_tasks=('basic',), gate_seeds=(1220000000,))
        self.assertFalse(p.promotion_gate([result(2,False)],[result(1)],[result(0)],config)['promote'])
        self.assertTrue(p.promotion_gate([result(2)],[result(1)],[result(0)],config)['promote'])
        self.assertFalse(p.promotion_gate([result(1)],[result(1)],[result(0)],config)['promote'])
        self.assertFalse(p.promotion_gate([result(2)],[result(1)],[result(3)],config)['promote'])

    def test_missing_refused_cutoff_not_success(self):
        config = p.PracticeConfig(gate_tasks=('basic',), gate_seeds=(1220000000,))
        self.assertFalse(p.promotion_gate([], [result()], [result()], config)['promote'])
        bad = result(10)
        bad['status'] = 'wall_cutoff'
        self.assertFalse(p.promotion_gate([bad], [result()], [result()], config)['promote'])
        bad = result(10)
        bad['qualified_queries'] = 1
        self.assertFalse(p.promotion_gate([bad], [result()], [result()], config)['promote'])

    def test_portable_bootstrap_custody(self):
        data = p.attach_seed_replay(bundle(), [seed_row()])
        self.assertEqual(data['metadata']['seed_replay_sha256'], digest(canonical(data['metadata']['seed_replay'])))
        bad = seed_row(); bad['split'] = 'development'
        with self.assertRaises(ValueError): p.validate_seed_replay([bad])
        bad = seed_row(); bad['targets'][0] = .6
        with self.assertRaises(ValueError): p.validate_seed_replay([bad])

    def test_async_owned_repair_and_immutable_promotion(self):
        learner = self.learner()
        initial = learner.champion['snapshot']
        self.assertFalse(learner.submit_transition(record()))
        learner.set_enabled(True)
        self.assertTrue(learner.submit_transition(record()))
        status = self.wait(learner,1)
        self.assertEqual(status['updates'],1)
        self.assertEqual(status['accepted_examples'],2)
        self.assertEqual(status['bootstrap_presentations'],1)
        promotion = learner.take_promotion()
        self.assertEqual(promotion['version'],1)
        self.assertNotEqual(promotion['snapshot'],initial)
        promotion['bundle']['metadata']['corruption'] = True
        self.assertNotIn('corruption',learner.champion['metadata'])
        self.assertIsNone(learner.take_promotion())

    def test_candidate_accumulates_before_gate(self):
        config = p.PracticeConfig(new_rows=1,candidate_lifetime=4,gate_tasks=('basic',),gate_seeds=(1220000000,))
        learner = self.learner(config=config)
        learner.set_enabled(True)
        for i in range(3):
            learner.submit_transition(record(str(i)))
        status = self.wait(learner,3)
        self.assertEqual(status['candidate_block_updates'],3)
        self.assertEqual(status['promotions'],0)
        self.assertEqual(learner.candidate.owners,['cadence-v3-practice']*3)
        learner.submit_transition(record('four'))
        self.assertEqual(self.wait(learner,4)['promotions'],1)

    def test_all_ties_never_admitted(self):
        learner = self.learner(teacher=Teacher(tied=True))
        learner.set_enabled(True)
        learner.submit_transition(record())
        status = self.wait(learner,1)
        self.assertEqual(status['uninformative_contexts'],1)
        self.assertEqual(status['updates'],0)

    def test_retry_exact_and_queue_durable(self):
        blocker = threading.Event()
        learner = self.learner(teacher=Teacher(block=blocker))
        learner.set_enabled(True)
        learner.submit_transition(record())
        self.assertEqual(len(list(learner.pending_dir.glob('*.json'))),1)
        self.assertTrue(learner.submit_transition(record()))
        broken = record(); broken['seed'] += 1
        with self.assertRaises(ValueError): learner.submit_transition(broken)
        blocker.set()
        self.wait(learner,1)
        self.assertEqual(len(list(learner.pending_dir.glob('*.json'))),0)

    def test_rollback_is_worker_handoff(self):
        learner = self.learner()
        learner.set_enabled(True)
        learner.submit_transition(record())
        self.wait(learner,1)
        learner.take_promotion()
        self.assertTrue(learner.rollback())
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            change=learner.take_promotion()
            if change:break
            time.sleep(.01)
        self.assertTrue(change['gate']['rollback'])
        self.assertEqual(change['version'],2)
        self.assertEqual(change['snapshot'],bundle()['snapshot'])

    def test_restart_restores_candidate_replay_and_processed_identity(self):
        config = p.PracticeConfig(new_rows=1,candidate_lifetime=4,gate_tasks=('basic',),gate_seeds=(1220000000,))
        learner = self.learner(config=config)
        learner.set_enabled(True)
        learner.submit_transition(record('a'))
        self.wait(learner,1)
        learner.close(wait=True)
        # Simulate a crash after continuation fsync but before pending unlink.
        key = learner._key(record('a'))
        p.atomic_json(learner.pending_dir/(key+'.json'), {'founder_checkpoint':bundle()['hashes']['checkpoint_sha256'],
                                                       'record':record('a')})
        resumed = p.PracticeLearner.from_bundle(bundle(),journal_path=learner.path,config=config,
                    seed_replay=[seed_row()],teacher=Teacher(),evaluator=lambda b:[result()])
        self.learners.append(resumed)
        self.assertEqual(resumed.candidate.generation,1)
        self.assertEqual(resumed.status()['candidate_block_updates'],1)
        self.assertEqual(resumed.status()['replay_rows'],1)
        self.assertEqual(resumed.status()['queue'],0)
        self.assertTrue(resumed.submit_transition(record('a')))
        self.assertEqual(len(list(resumed.pending_dir.glob('*.json'))),0)

    def test_restart_exposes_unconsumed_promotion_once(self):
        learner = self.learner()
        learner.set_enabled(True)
        learner.submit_transition(record())
        self.wait(learner,1)
        promoted=learner.champion['hashes']['checkpoint_sha256']
        learner.close(wait=True)
        resumed=p.PracticeLearner.from_bundle(bundle(),journal_path=learner.path,config=learner.config,
                   seed_replay=[seed_row()],teacher=Teacher(),evaluator=lambda b:[result()])
        self.learners.append(resumed)
        change=resumed.take_promotion()
        self.assertEqual(change['bundle']['hashes']['checkpoint_sha256'],promoted)
        self.assertEqual(change['version'],1)
        self.assertIsNone(resumed.take_promotion())

    def test_new_wave_continuation_does_not_replace_retention_founder(self):
        current=bundle(7)
        learner=self.learner(initial_bundle=current,continuation_bundle=current)
        self.assertEqual(learner.founder['hashes']['checkpoint_sha256'],bundle()['hashes']['checkpoint_sha256'])
        self.assertEqual(learner.status()['continuation_checkpoint'],current['hashes']['checkpoint_sha256'])
        self.assertEqual(learner.target['retention_founder_checkpoint_sha256'],bundle()['hashes']['checkpoint_sha256'])
        self.assertEqual(learner.status()['replay_rows'],0)

    def test_update_uses_public_integer_event_allocation_with_real_repair(self):
        from cadence import Cortex
        layout=Cortex(seed=0,settle_budget=2048,device='cpu')
        sensor=layout.input('x',shape=1)
        head=layout.column(patches=20,inputs=sensor)
        layout.output('action_scores',shape=20,reads=head)
        learner=self.learner(config=p.PracticeConfig(new_rows=1,candidate_lifetime=4,
                                                    gate_tasks=('basic',),gate_seeds=(1220000000,)))
        learner.candidate=layout.build()
        old={**seed_row(),'inputs':{'x':[.2]}}
        learner.seed_replay=[old]
        learner._new.append({**old,'source':'autonomous_native_rank','row_id':'native:0'})
        learner._update()
        self.assertEqual(learner.status()['updates'],1)
        events=[json.loads(line) for line in learner.path.read_text().splitlines()]
        admission=next(row for row in events if row['kind']=='admission')
        self.assertIs(type(admission['diagnostics']['event_id']),int)
        self.assertTrue(admission['diagnostics']['qualified'])


if __name__ == '__main__':
    unittest.main()
