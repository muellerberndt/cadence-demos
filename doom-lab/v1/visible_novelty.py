"""Explicit short-memory visible novelty gene; never a native success predicate.

The references are exactly the actor's four causal visual-history samples.
This does not claim episodic novelty, a Markov state, or immunity to spinning.
"""
from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing
from pathlib import Path

import numpy as np

from .interface import canonical, features, digest
from .native_feedback import rollout_branch, target_contract as native_contract, validate_record
from .tasks import DoomEnv


GENE = dict(id='visible_four_reference_scene_novelty_v1',
    reference_source='exact actor visual_history four lagged samples with valid flags',
    scene_crop_coarse_rows=[1,5], scene_crop_coarse_columns=[1,15],
    scene_crop_pixels=[24,120,20,300],
    representation='frozen bundle conditioned 10x16 coarse grayscale; same conditioning as actor history',
    distance='minimum reference mean absolute difference after discarding largest floor(10percent) coordinate differences',
    discard_fraction=.1, deadband=.03, saturation=.20,
    aggregation='maximum successor novelty within one branch, bounded0..1, never cumulative',
    beta=.05, control_beta=0.,
    boundary='visible pixels and executed-action-derived history only; no position, geometry, labels, route or native fact inputs',
    limitations='Four sampled references forget older views; rotation/occlusion/texture noise can earn bonus. Measure these effects; no anti-spin guarantee.')


def scene_novelty(current_coarse, visual_history):
    """Deterministic bounded reward gene; no learned policy or action choice."""
    current = np.asarray(current_coarse, dtype=float).reshape(10,16)[1:5,1:15].reshape(-1)
    history = np.asarray(visual_history, dtype=float).reshape(4,161)
    distances = []
    for row in history:
        if row[160] <= 0: continue
        reference = row[:160].reshape(10,16)[1:5,1:15].reshape(-1)
        delta = np.sort(np.abs(current-reference))
        distances.append(float(delta[:len(delta)-int(len(delta)*GENE['discard_fraction'])].mean()))
    if not distances: return dict(score=0., distance=None, valid_references=0)
    distance = min(distances)
    score = float(np.clip((distance-GENE['deadband'])/(GENE['saturation']-GENE['deadband']), 0., 1.))
    return dict(score=score, distance=distance, valid_references=len(distances))


def target_contract(checkpoint, horizon_tics=36):
    return dict(id='native_navigation_plus_visible_four_reference_novelty_v1',
        native=native_contract('navigation', checkpoint, horizon_tics=horizon_tics),
        gene=GENE, target='compare same native branches with beta0 control and beta.05 candidate; bounded preference conversion is separate',
        success='native navigation exit remains the only competence/gate success',
        native_success_dominates='navigation native goal+1 and at most560tics cost.056; bonus<=.05 cannot outweigh a goal')


class _Monitor:
    def __init__(self, task, seed, teacher, actor, prefix):
        self.env=DoomEnv(task,seed,teacher=teacher);self.actor=actor;self.prefix=prefix
        self.steps=0;self.seen=set();self.observations=[]
    def __enter__(self): self.env.__enter__(); return self
    def __exit__(self,*args): return self.env.__exit__(*args)
    def __getattr__(self,name): return getattr(self.env,name)
    def step(self,*args,**kwargs):
        result=self.env.step(*args,**kwargs);self.steps+=1;return result
    def observe(self):
        raw=self.env.observe()
        if self.steps>self.prefix and self.steps not in self.seen:
            norms=self.actor.bundle['normalization']
            coarse=features(raw)['coarse']
            conditioned=np.clip((coarse-np.asarray(norms['mean']['coarse']))/np.asarray(norms['scale']['coarse']),-3,3)*.2
            inputs=self.actor.history.encode(raw,norms)
            value=scene_novelty(conditioned,inputs['visual_history'])
            self.observations.append(dict(step=self.steps-self.prefix,raw_sha256=digest(raw.tobytes()),**value))
            self.seen.add(self.steps)
        return raw
    def facts(self):
        # rollout_branch calls facts after acknowledgement of the final action;
        # observe the last successor too, if native termination leaves a frame.
        if self.steps>self.prefix and not self.env.finished:self.observe()
        return self.env.facts()


def _initialize(bundle):
    from .brain import Actor
    global _BUNDLE,_ACTOR
    _BUNDLE=bundle;_ACTOR=Actor(bundle,device='cpu')


def _branch(payload):
    record, action, contract=payload;monitors=[]
    if contract != target_contract(_ACTOR.checkpoint_hash,contract['native']['horizon_tics']):
        return dict(ok=False,action=action,error='Novelty contract mismatch',cost={})
    def factory(task,seed,teacher):
        monitor=_Monitor(task,seed,teacher,_ACTOR,len(record['prefix_actions']));monitors.append(monitor);return monitor
    row=rollout_branch(record,action,contract['native'],_BUNDLE,env_factory=factory,
                       actor_factory=lambda _bundle,device:_ACTOR)
    observations=monitors[0].observations if monitors else []
    bonus=max((v['score'] for v in observations),default=0.)
    row.update(visible_novelty=bonus,novelty_observations=observations)
    if row['ok']:
        row['native_control_utility']=row['native_return']
        row['novelty_utility']=row['native_return']+GENE['beta']*bonus
    return row


class VisibleNoveltyPool:
    def __init__(self,bundle,workers=8):
        if not 1<=workers<=32:raise ValueError('Workers1..32')
        self.bundle=json.loads(Path(bundle).read_text()) if isinstance(bundle,(str,Path)) else json.loads(canonical(bundle))
        self.pool=ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn'),initializer=_initialize,initargs=(self.bundle,))
    def label(self,record,contract):
        record=validate_record(record)
        if record['task']!='navigation':raise ValueError('Navigation-only explicit utility gene')
        futures=[self.pool.submit(_branch,(record,a,contract)) for a in range(20)]
        rows=[]
        for action,future in enumerate(futures):
            try:rows.append(future.result())
            except Exception as error:rows.append(dict(ok=False,action=action,error=repr(error),cost={}))
        ok=all(r.get('ok') and r['action']==i for i,r in enumerate(rows))
        return dict(ok=ok,contract=contract,branches=rows,
            native_control_labels=[r['native_control_utility'] for r in rows] if ok else None,
            novelty_labels=[r['novelty_utility'] for r in rows] if ok else None,
            scope='Same fresh native20branches, frozen qualified continuation, two explicitly separate utility genes. No training or promotion.')
    def close(self):self.pool.shutdown(wait=True)
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
