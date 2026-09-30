"""Local platform receipts must prove their fixed schedule before registration."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import deployment as d
from .evaluate import summarize
from .practice import atomic_json
from .tasks import sha_file


class EvidenceTests(unittest.TestCase):
    def fixture(self, root, wins=12):
        bundle = root/'original.json'; bundle.write_text('immutable-checkpoint')
        active = {'hashes': {'checkpoint_sha256': 'a'*64}}
        platform = {'system':'test'}; identity = {'task':'basic'}; sources = {'module':'b'*64}
        protocol={'schema':'doom-v1-local-operational-validation/1', 'criteria': {
            'all_scheduled_complete':True,'all_queries_qualified':True,'fallback_actions':0,
            'minimum_successes':12,'scheduled':16}, 'seeds':list(range(16)),
            'checkpoint_sha256':'a'*64,'bundle_sha256':sha_file(bundle), 'platform':platform,
            'task_identity':identity,'source_sha256':sources}
        atomic_json(root/'protocol.json',protocol)
        atomic_json(root/'native/freeze.json',{'source':'fixed'})
        rows=[]
        for seed in range(16):
            trace=root/'native/episodes'/f'basic_{seed}'/'decisions.jsonl'
            atomic_json(trace,{'qualified':True})
            rows.append({'task_id':'basic','seed':seed,'status':'complete','queries':1,'qualified_queries':1,
                'fallback_actions':0,'checkpoint_sha256':'a'*64,'success':seed<wins,
                'decisions_sha256':sha_file(trace)})
        outcomes=root/'native/outcomes.jsonl';outcomes.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        native={**summarize(rows,[('basic',s) for s in range(16)]), 'freeze_sha256':sha_file(root/'native/freeze.json')}
        atomic_json(root/'native/summary.json',native)
        receipt={**protocol,'status':'passed','training_performed':False,'summary':native,
            'native_summary_sha256':sha_file(root/'native/summary.json'), 'outcomes_sha256':sha_file(outcomes),
            'protocol_sha256':sha_file(root/'protocol.json')}
        atomic_json(root/'receipt.json',receipt)
        self.enterContext(patch.object(d,'platform_identity',return_value=platform))
        self.enterContext(patch.object(d,'task_identity',return_value=identity))
        self.enterContext(patch.object(d,'source_identity',return_value=sources))
        return root/'receipt.json',bundle,active,receipt

    def test_real_outcomes_override_edited_outer_pass_status(self):
        with tempfile.TemporaryDirectory() as directory:
            args=self.fixture(Path(directory),wins=11)
            with self.assertRaisesRegex(ValueError,'outcomes do not satisfy'):
                d.validate_evidence(*args[:3])

    def test_passed_receipt_requires_bound_summary_schedule_and_traces(self):
        with tempfile.TemporaryDirectory() as directory:
            path,bundle,active,receipt=self.fixture(Path(directory))
            self.assertEqual(d.validate_evidence(path,bundle,active),receipt)
            changed=copy.deepcopy(receipt);changed['summary']['successes']=16;atomic_json(path,changed)
            with self.assertRaisesRegex(ValueError,'outcomes do not satisfy'):
                d.validate_evidence(path,bundle,active)
            atomic_json(path,receipt)
            (path.parent/'native/episodes/basic_0/decisions.jsonl').write_text('tampered')
            with self.assertRaisesRegex(ValueError,'trace differs'):
                d.validate_evidence(path,bundle,active)

    def test_qualification_refusal_and_duplicates_fail_even_with_wins(self):
        rows=[{'seed':i,'task_id':'basic','status':'complete','queries':2,'qualified_queries':2,
            'fallback_actions':0,'checkpoint_sha256':'a','success':True} for i in range(16)]
        protocol={'seeds':list(range(16)),'checkpoint_sha256':'a'}
        self.assertTrue(d._passing_rows(rows,protocol))
        rows[-1]['qualified_queries']=1;self.assertFalse(d._passing_rows(rows,protocol))
        rows[-1]['qualified_queries']=2;rows[-1]['seed']=0;self.assertFalse(d._passing_rows(rows,protocol))

if __name__=='__main__':unittest.main()
