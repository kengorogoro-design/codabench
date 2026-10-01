from __future__ import annotations
from pathlib import Path
import json, shutil, tempfile, os
from .bundle import Bundle
from .runner import run_bundle
from .ledger import Ledger

class Ecology:
    def __init__(self, root:Path):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
        self.candidates=self.root/'candidates'; self.candidates.mkdir(exist_ok=True)
        self.ledger=Ledger(self.root/'ledger.jsonl')
    def admit_bundle(self, source:Path, role='candidate'):
        b=Bundle.load(source)
        dest=self.candidates/b.bundle_id
        if not dest.exists(): shutil.copytree(source,dest)
        if Bundle.load(dest).bundle_id != b.bundle_id:
            raise ValueError('candidate custody identity mismatch')
        self.ledger.append('bundle_admitted',{'bundle_id':b.bundle_id,'role':role})
        return Bundle.load(dest)
    def ask(self,bundle:Bundle,task:dict):
        out=run_bundle(bundle,{'op':'act','task':task})
        self.ledger.append('candidate_output',{'bundle_id':bundle.bundle_id,'task_id':task.get('task_id'),'output':out})
        return out
    def generate_successors(self,generator:Bundle,history:dict,dest_root:Path):
        out=run_bundle(generator,{'op':'generate','history':history})
        specs=out.get('bundles',[])
        if not isinstance(specs,list) or len(specs)>8:
            raise ValueError('invalid successor count')
        from .producer import files_digest
        dest_root=Path(dest_root); dest_root.mkdir(parents=True,exist_ok=True)
        created=[]
        with tempfile.TemporaryDirectory(prefix='.g0-generation-',dir=dest_root) as td:
            staged=[]
            # Validate and load the complete generation before installing any
            # content-addressed successor. Prior generations are never replaced.
            for i,spec in enumerate(specs):
                files=spec.get('files',{})
                files_digest(files)
                d=Path(td)/str(i); d.mkdir()
                for rel,content in files.items():
                    p=d/rel; p.parent.mkdir(parents=True,exist_ok=True)
                    p.write_text(content,encoding='utf-8')
                staged.append(Bundle.load(d))
            for b in staged:
                dest=dest_root/b.bundle_id
                if not dest.exists():
                    os.rename(b.root,dest)
                installed=Bundle.load(dest)
                if installed.bundle_id!=b.bundle_id:
                    raise ValueError('successor custody identity mismatch')
                created.append(installed)
        self.ledger.append('successors_generated',{'generator_id':generator.bundle_id,'successor_ids':[x.bundle_id for x in created]})
        return created
