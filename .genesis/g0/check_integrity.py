from pathlib import Path
import hashlib,json,sys
root=Path(__file__).resolve().parent
m=json.loads((root/'manifest.json').read_text())
bad=[]
declared={r['path'] for r in m['files']}
actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()
        and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts
        and p.name!='manifest.json'}
for extra in sorted(actual-declared): bad.append([extra,'undeclared'])
for r in m['files']:
 p=root/r['path']
 if root.resolve() not in p.resolve().parents or p.is_symlink():
  bad.append([r['path'],'path']); continue
 if not p.is_file(): bad.append([r['path'],'missing']); continue
 h=hashlib.sha256(p.read_bytes()).hexdigest()
 if h!=r['sha256']: bad.append([r['path'],'hash'])
rows=[(r['path'],r['sha256']) for r in m['files']]
cr=hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()
if cr!=m['content_root']: bad.append(['content_root',cr])
print(json.dumps({'ok':not bad,'files':len(m['files']),'content_root':cr,'bad':bad},indent=2))
sys.exit(1 if bad else 0)
