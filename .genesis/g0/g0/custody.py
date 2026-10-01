from __future__ import annotations
from pathlib import Path
import json, time
from .hashutil import sha256_bytes, canonical_json
from .storage import atomic_replace
from .ledger import Ledger

class Court:
    def __init__(self, root:Path):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
        self.mutex=Ledger(self.root/'custody-ledger.jsonl')
    def _freeze_path(self, task_id):
        if not isinstance(task_id,str) or not task_id:
            raise ValueError('invalid task identity')
        return self.root/(sha256_bytes(task_id.encode())+'.freeze.json')
    def _read_freeze(self, task_id):
        f=json.loads(self._freeze_path(task_id).read_text(encoding='utf-8'))
        body={k:v for k,v in f.items() if k!='freeze_digest'}
        if f.get('task_id')!=task_id or f.get('freeze_digest')!=sha256_bytes(canonical_json(body)):
            raise ValueError('freeze custody corrupted')
        return f
    def freeze(self, task_id:str, raw:dict, source_ref:str, commit:str|None=None, ts_ns:int|None=None):
        ts_ns=time.time_ns() if ts_ns is None else ts_ns
        body={'task_id':task_id,'raw':raw,'source_ref':source_ref,'commit':commit,'frozen_at_ns':ts_ns}
        body['freeze_digest']=sha256_bytes(canonical_json(body))
        p=self._freeze_path(task_id)
        with self.mutex._lock():
            if p.exists():
                old=self._read_freeze(task_id)
                if any(old[k]!=body[k] for k in ('task_id','raw','source_ref','commit')):
                    raise ValueError('frozen task cannot be replaced')
                return old
            atomic_replace(p,canonical_json(body)+b'\n')
            return body
    def outcome(self, task_id:str, outcome:dict, external_refs:list[str], judge_type:str):
        f=self._read_freeze(task_id)
        body={'task_id':task_id,'freeze_digest':f['freeze_digest'],'outcome':outcome,
              'external_refs':external_refs,'judge_type':judge_type}
        body['outcome_digest']=sha256_bytes(canonical_json(body))
        p=self.root/(sha256_bytes(task_id.encode())+'.'+body['outcome_digest']+'.outcome.json')
        with self.mutex._lock():
            if p.exists():
                if p.read_bytes()!=canonical_json(body)+b'\n':
                    raise ValueError('outcome custody corrupted')
            else:
                atomic_replace(p,canonical_json(body)+b'\n')
        return body
