from pathlib import Path
import hashlib
import json
ROOT=Path(__file__).resolve().parent
files=[]
for p in sorted(ROOT.rglob('*')):
 if (not p.is_file() or '__pycache__' in p.parts or '.pytest_cache' in p.parts
     or p.name=='manifest.json'):
  continue
 files.append({'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
rows=[(r['path'],r['sha256']) for r in files]
root=hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()
(ROOT/'manifest.json').write_text(json.dumps({'content_root':root,'files':files},indent=2)+'\n')
print(json.dumps({'content_root':root,'files':len(files)}))
