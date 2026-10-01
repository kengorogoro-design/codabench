from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json, shutil
from .hashutil import tree_hash

@dataclass(frozen=True)
class Bundle:
    root: Path
    bundle_id: str
    entrypoint: str
    kind: str

    @staticmethod
    def load(root: Path):
        root=Path(root)
        m=json.loads((root/'bundle.json').read_text(encoding='utf-8'))
        entry = m.get('entrypoint')
        if not isinstance(entry, str) or not entry:
            raise ValueError('missing entrypoint')
        p = root / entry
        if root.resolve() not in p.resolve().parents or not p.is_file():
            raise ValueError('entrypoint escapes bundle or is missing')
        if any(x in p.parts for x in ('__pycache__', '.pytest_cache')):
            raise ValueError('entrypoint must be content-addressed')
        return Bundle(root=root,bundle_id=tree_hash(root),entrypoint=m['entrypoint'],kind=m.get('kind','candidate'))

    def snapshot_to(self, dest: Path):
        dest=Path(dest)
        if dest.exists(): shutil.rmtree(dest)
        shutil.copytree(self.root,dest)
        return Bundle.load(dest)
