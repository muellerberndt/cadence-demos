import gzip
import json
from pathlib import Path
import tempfile
import unittest
from .cached_feedback import CachedFeedback
from .interface import canonical,digest
from .test_practice import record

class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'cache.gz'
        self.records=[record('a'),record('b')];self.contract={'native_return_divisor':300}
        self.rows=[]
        for i,rec in enumerate(self.records):
            branches=[{'ok':True,'action':a,'label':a/300,'native_return':a,'continuation_queries':[{'qualified':True}]} for a in range(20)]
            self.rows.append({'index':i,'record_sha256':digest(canonical(rec)),
                 'feedback':{'ok':True,'contract':self.contract,'branches':branches,
                             'labels':[b['label'] for b in branches],'cost':{'engine_initializations':20}}})
    def tearDown(self):self.temp.cleanup()
    def cache(self):
        with gzip.open(self.path,'wt') as f:
            for row in self.rows:f.write(json.dumps(row)+'\n')
        return CachedFeedback(self.path,self.records,self.contract)
    def test_exact_reuse_no_new_engines_and_owned_return(self):
        cache=self.cache();first=cache.label(self.records[0],self.contract)
        self.assertEqual(first,self.rows[0]['feedback']);first['labels'][0]=99
        self.assertEqual(cache.rows[0]['feedback']['labels'][0],0)
        self.assertEqual(cache.cost['engine_initializations'],0)
        self.assertEqual(cache.reused_native_cost['engine_initializations'],20)
    def test_order_and_record_identity_refused(self):
        cache=self.cache()
        with self.assertRaises(ValueError):cache.label(self.records[1],self.contract)
        self.rows[0]['record_sha256']='f'*64
        with self.assertRaises(ValueError):self.cache()
    def test_contract_and_incomplete_vector_refused(self):
        self.rows[0]['feedback']['contract']={'native_return_divisor':864}
        with self.assertRaises(ValueError):self.cache()
        self.rows[0]['feedback']['contract']=self.contract
        self.rows[0]['feedback']['branches'].pop()
        with self.assertRaises(ValueError):self.cache()
    def test_refused_query_or_changed_native_value_refused(self):
        self.rows[0]['feedback']['branches'][0]['continuation_queries'][0]['qualified']=False
        with self.assertRaises(ValueError):self.cache()
        self.rows[0]['feedback']['branches'][0]['continuation_queries'][0]['qualified']=True
        self.rows[0]['feedback']['branches'][0]['native_return']=99
        with self.assertRaises(ValueError):self.cache()

    def test_nonfinite_native_value_refused(self):
        self.rows[0]['feedback']['branches'][0].update(native_return=float('inf'),label=float('inf'))
        self.rows[0]['feedback']['labels'][0]=float('inf')
        with self.assertRaises(ValueError):self.cache()

if __name__=='__main__':unittest.main()
