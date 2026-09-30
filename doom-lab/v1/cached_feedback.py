"""Read-only replay of already verified native feedback; creates no game engines."""
import copy
import gzip
import json
import math
from .interface import canonical,digest

class CachedFeedback:
    def __init__(self,path,records,contract):
        with gzip.open(path,'rt') as stream:self.rows=[json.loads(line) for line in stream]
        if len(self.rows)!=len(records):raise ValueError('Cached feedback count differs from frozen actual experience')
        for index,(row,record) in enumerate(zip(self.rows,records)):
            feedback=row['feedback']
            if (row['index']!=index or row['record_sha256']!=digest(canonical(record))
                    or canonical(feedback['contract'])!=canonical(contract) or not feedback['ok']):
                raise ValueError('Cached feedback has a different record, order, native contract or refusal')
            branches=feedback['branches']
            if len(branches)!=20 or len(feedback['labels'])!=20:
                raise ValueError('A complete twenty-action native vector is required')
            for action,branch in enumerate(branches):
                if (not branch['ok'] or branch['action']!=action
                        or not math.isfinite(branch['native_return']) or not math.isfinite(branch['label'])
                        or branch['label']!=feedback['labels'][action]
                        or abs(branch['native_return']/contract['native_return_divisor']-branch['label'])>1e-12
                        or any(q['qualified']is not True for q in branch['continuation_queries'])):
                    raise ValueError('Cached native branch evidence differs from its qualified label')
        self.index=0
        self.cost={'engine_initialization_attempts':0,'engine_initializations':0,'continuation_queries':0,'qualified_continuation_queries':0,
                   'branch_tics':0,'replay_tics':0,'cached_contexts':0}
        self.reused_native_cost={}
    def label(self,record,contract):
        if self.index>=len(self.rows):raise ValueError('No cached label remains for this context')
        row=self.rows[self.index]
        if row['record_sha256']!=digest(canonical(record)) or canonical(row['feedback']['contract'])!=canonical(contract):
            raise ValueError('Cached feedback request changed the declared processing order or native contract')
        self.index+=1;self.cost['cached_contexts']+=1
        for key,value in row['feedback']['cost'].items():self.reused_native_cost[key]=self.reused_native_cost.get(key,0)+value
        return copy.deepcopy(row['feedback'])
    def close(self):pass
