from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import json, time
from .hashutil import canonical_json, sha256_bytes
from .storage import atomic_replace
from contextlib import contextmanager

@dataclass(frozen=True)
class Record:
    kind: str
    payload: dict
    prev: str
    ts_ns: int
    digest: str

class Ledger:
    def __init__(self, path: Path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_name(self.path.name+'.lock')
        with self._lock():
            if not self.path.exists(): atomic_replace(self.path, b'')
    @contextmanager
    def _lock(self):
        if __import__('os').name != 'posix':
            raise RuntimeError('ledger locking not implemented on this platform')
        import fcntl
        with self.lock_path.open('a+b') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    def records(self):
        out=[]
        for line in self.path.read_text(encoding='utf-8').splitlines():
            if line.strip(): out.append(json.loads(line))
        return out
    def head(self):
        r=self.records()
        return r[-1]['digest'] if r else '0'*64
    def append(self, kind:str, payload:dict, ts_ns:int|None=None):
        with self._lock():
            ok, err = self.verify()
            if not ok: raise ValueError('corrupt ledger: '+str(err))
            prev=self.head(); ts_ns=time.time_ns() if ts_ns is None else ts_ns
            body={'kind':kind,'payload':payload,'prev':prev,'ts_ns':ts_ns}
            digest=sha256_bytes(canonical_json(body))
            rec={**body,'digest':digest}
            data = self.path.read_bytes()+canonical_json(rec)+b'\n'
            atomic_replace(self.path, data, getattr(self, '_before_commit', None))
            return rec
    def verify(self):
        prev='0'*64
        try:
            for i,rec in enumerate(self.records()):
                body={k:rec[k] for k in ('kind','payload','prev','ts_ns')}
                if rec['prev'] != prev: return False, f'prev mismatch @{i}'
                if sha256_bytes(canonical_json(body)) != rec['digest']: return False, f'digest mismatch @{i}'
                prev=rec['digest']
        except (ValueError, KeyError, TypeError) as exc:
            return False, f'malformed ledger: {type(exc).__name__}'
        return True, None
