import unittest
import numpy as np
from types import SimpleNamespace
from unittest.mock import patch
from .interface import History,fixed_normalizer
from .visible_novelty import scene_novelty,GENE,_Monitor


class NoveltyTests(unittest.TestCase):
    def history(self,value=0):
        a=np.full((4,161),value,dtype=float);a[:,-1]=.2;return a.reshape(-1)
    def test_static_and_missing_reference_zero(self):
        self.assertEqual(scene_novelty(np.zeros(160),self.history())['score'],0)
        self.assertEqual(scene_novelty(np.ones(160),np.zeros(644))['score'],0)
    def test_hud_weapon_region_excluded(self):
        a=np.zeros((10,16));a[5:]=1
        self.assertEqual(scene_novelty(a,self.history())['score'],0)
    def test_sparse_noise_trimmed_and_score_bounded(self):
        a=np.zeros((10,16));a[1,1]=1
        self.assertEqual(scene_novelty(a,self.history())['score'],0)
        self.assertEqual(scene_novelty(np.ones(160),self.history())['score'],1)
    def test_closest_visible_reference_wins(self):
        a=self.history().reshape(4,161);a[2,:160]=.3
        self.assertEqual(scene_novelty(np.full(160,.3),a)['score'],0)
        self.assertLessEqual(GENE['beta'],.05)

    def test_monitor_is_read_only_and_final_successor_scored_once(self):
        class Env:
            def __init__(self,*args,**kwargs):self.index=0;self.finished=False
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def observe(self):return np.full((240,320),self.index*12,dtype=np.uint8)
            def step(self,*args,**kwargs):self.index+=1;return {'tics':4}
            def facts(self):return {'index':self.index}
        actor=SimpleNamespace(history=History(),bundle={'normalization':fixed_normalizer()},pending='unchanged')
        with patch('v1.visible_novelty.DoomEnv',Env):
            monitor=_Monitor('navigation',1,False,actor,0)
            raw=monitor.observe();monitor.step(1);actor.history.acknowledge(raw,1,4)
            before=actor.history.encode(monitor.env.observe(),actor.bundle['normalization'])
            monitor.observe();monitor.facts();monitor.facts()
            self.assertEqual(len(monitor.observations),1)
            self.assertEqual(actor.history.executed_steps,1);self.assertEqual(actor.pending,'unchanged')
            self.assertEqual(before,actor.history.encode(monitor.env.observe(),actor.bundle['normalization']))
            raw=monitor.observe();monitor.step(1);actor.history.acknowledge(raw,1,4)
            monitor.facts();monitor.facts()
            self.assertEqual(len(monitor.observations),2)
            self.assertEqual(actor.history.executed_steps,2)


if __name__=='__main__':unittest.main()
