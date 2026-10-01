"""Same-author semantic falsification; never independent MIGI admission."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parent
MUTANTS=[
 ('allow-unset-effects','g0/effects.py',
  "else (lambda _name, _args: False)","else (lambda _name, _args: True)",
  'tests/test_selection_adversarial.py::test_unset_or_nonboolean_authority_executes_no_effect'),
 ('truthy-authority','g0/effects.py',
  'self.authority(name, args) is True','bool(self.authority(name, args))',
  'tests/test_selection_adversarial.py::test_unset_or_nonboolean_authority_executes_no_effect'),
 ('skip-regression-veto','g0/selection.py',
  'e.accepted_or_merged, e.regression_free))','e.accepted_or_merged))',
  'tests/test_selection_adversarial.py::test_production_never_compensates_for_required_gate'),
 ('intersect-away-missing-tasks','g0/selection.py',
  'set(ma) != set(mb)','not (set(ma) & set(mb))',
  'tests/test_selection_adversarial.py::test_missing_court_and_duplicates_block_selection'),
 ('ignore-source-identity','g0/runner.py',
  'actual = Bundle.load(bundle.root)','actual = Bundle.load(bundle.root)\n    bundle = actual',
  'tests/test_execution_custody.py::test_changed_source_cannot_execute_as_old_identity'),
]
results=[]
for name,file,old,new,test in MUTANTS:
 with tempfile.TemporaryDirectory(prefix='g0-mutant-') as td:
  d=Path(td)/'source'
  shutil.copytree(ROOT,d,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache'))
  p=d/file; text=p.read_text()
  if text.count(old)!=1: raise RuntimeError('mutation target not unique: '+name)
  p.write_text(text.replace(old,new))
  r=subprocess.run([sys.executable,'-m','pytest','-q',test],cwd=d,capture_output=True,text=True)
  killed=r.returncode==1 and 'failed' in r.stdout
  results.append({'name':name,'killed':killed,'returncode':r.returncode,'output':r.stdout[-2500:]})
print(json.dumps({'same_author':True,'ok':all(x['killed'] for x in results),'mutants':results},indent=2))
raise SystemExit(0 if all(x['killed'] for x in results) else 1)
