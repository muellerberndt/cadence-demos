"""Adversarial corpus-boundary and replay checks using small synthetic fixtures."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from .collection import atomic_json
from .interface import History, contract
from .tasks import sha_file
from .training import prepare, split_episodes, balanced_order, unpack, episode_arrays


class DatasetBoundaryTests(unittest.TestCase):
    def fixture(self, root):
        corpus=root/'corpus';corpus.mkdir();atomic_json(corpus/'freeze.json',{'fixture':True,'contract':contract()})
        for index,pixel in enumerate((250,20,40)):
            folder=corpus/f'episode-{index:04d}';folder.mkdir()
            (folder/'events.jsonl.gz').write_bytes(b'synthetic events fixture')
            np.savez_compressed(folder/'frames.npz',
                frames=np.full((4,240,320),pixel,dtype=np.uint8),
                teacher_actions=np.array([11,11,1,1],dtype=np.int16),
                executed_actions=np.array([2,3,4,5],dtype=np.int16),tics=np.array([4,3,2,1]))
            atomic_json(folder/'receipt.json',{'task':'doors','seed':100+index,'status':'complete',
                        'decisions':4,'outcome':{'success':True},'frames_sha256':sha_file(folder/'frames.npz'),
                        'events_sha256':sha_file(folder/'events.jsonl.gz')})
        return corpus

    def test_development_pixels_never_fit_normalization_and_actual_actions_form_history(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);corpus=self.fixture(root)
            result=prepare([corpus],root/'prepared',sample_stride=1)
            self.assertEqual(result['normalizer']['frames'],8)
            self.assertAlmostEqual(result['normalizer']['mean']['periphery'][0],30/255)
            self.assertEqual([r['split'] for r in result['episodes']],['development','training','training'])
            encoded=np.load(root/'prepared/inputs.npy')
            second=unpack(encoded[1]);history=History()
            history.acknowledge(np.full((240,320),250,dtype=np.uint8),2,4)
            expected=history.encode(np.full((240,320),250,dtype=np.uint8),result['normalizer'])
            self.assertEqual(second['executed_action_history'],expected['executed_action_history'])
            self.assertEqual(second['visual_history'],expected['visual_history'])

    def test_duplicate_episode_seed_refused(self):
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            split_episodes([{'task':'doors','seed':1,'path':str(i)} for i in range(2)])

    def test_changed_dataset_and_failed_teacher_are_not_silently_admitted(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);corpus=self.fixture(root)
            bad=corpus/'episode-0002/receipt.json';receipt=json.loads(bad.read_text())
            receipt['outcome']['success']=False;atomic_json(bad,receipt)
            result=prepare([corpus],root/'prepared',sample_stride=1)
            self.assertEqual(len(result['excluded']),1)
            row=result['episodes'][0]
            with (Path(row['path'])/'frames.npz').open('ab') as stream:stream.write(b'tampered')
            with self.assertRaisesRegex(ValueError,'custody'):
                episode_arrays(row)

    def test_balanced_sampling_has_no_development_ids_and_is_reproducible(self):
        rows={'task_ids':np.array([0]*100+[1]*2),'actions':np.array([1]*100+[11]*2)}
        eligible=np.arange(101)
        first=balanced_order(rows,eligible,1000,73)
        self.assertTrue(np.array_equal(first,balanced_order(rows,eligible,1000,73)))
        self.assertNotIn(101,first)
        self.assertGreater(np.count_nonzero(first==100),400)
        self.assertLess(np.count_nonzero(first==100),600)


if __name__=='__main__':unittest.main()
