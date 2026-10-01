from __future__ import annotations
import hashlib, json
from pathlib import Path

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def canonical_json(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()

def tree_hash(root: Path) -> str:
    rows=[]
    for p in root.rglob('*'):
        if p.is_symlink():
            raise ValueError('bundle symlinks are not permitted')
    for p in sorted(x for x in root.rglob('*') if x.is_file() and '__pycache__' not in x.parts and '.pytest_cache' not in x.parts):
        rel=p.relative_to(root).as_posix()
        rows.append((rel, sha256_bytes(p.read_bytes())))
    return sha256_bytes(canonical_json(rows))
