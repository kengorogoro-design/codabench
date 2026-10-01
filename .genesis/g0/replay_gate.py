from __future__ import annotations
from pathlib import Path
import subprocess, sys, json
root=Path(__file__).resolve().parent
steps=[
    [sys.executable,'check_integrity.py'],
    [sys.executable,'-m','pytest','-q'],
    [sys.executable,'run_g0.py'],
    [sys.executable,'audit_current_producers.py'],
    [sys.executable,'mutation_court.py'],
]
out=[]
for cmd in steps:
    p=subprocess.run(cmd,cwd=root,text=True,capture_output=True)
    out.append({'cmd':cmd,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
    if p.returncode!=0:
        print(json.dumps({'ok':False,'steps':out},indent=2))
        raise SystemExit(p.returncode)
print(json.dumps({'ok':True,'steps':out},indent=2))
