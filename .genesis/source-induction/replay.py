"""Re-execute the frozen producer and compare the checked-out product bytes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()

request = json.loads((root / 'input.json').read_text())
receipt = json.loads((root / 'receipt.json').read_text())
bundle = root / 'bundle'
rows = [(p.relative_to(bundle).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest())
        for p in sorted(bundle.rglob('*')) if p.is_file()]
assert digest(rows) == receipt['producer_id']
assert digest(request) == receipt['request_digest']
result = subprocess.run([sys.executable, str(bundle / 'main.py')],
                        input=json.dumps(request), text=True, capture_output=True,
                        check=True, timeout=20)
output = json.loads(result.stdout)
assert digest(output) == receipt['output_digest']
files = output['delivery']['files']
actual = {path: Path(path).read_text() for path in files}
assert actual == files, 'Checked-out delivery differs from executable output'
assert digest([(p, hashlib.sha256(s.encode()).hexdigest())
               for p, s in sorted(files.items())]) == receipt['delivery_digest']
request['task']['source_files'].pop('src/apps/api/serializers/leaderboards.py')
ablated = subprocess.run([sys.executable, str(bundle / 'main.py')],
                        input=json.dumps(request), text=True, capture_output=True,
                        check=True, timeout=20)
ablation = json.loads(ablated.stdout)
assert 'delivery' not in ablation, 'Repair unexpectedly survives donor removal'
print(json.dumps({'producer_id': receipt['producer_id'],
                  'delivery_digest': receipt['delivery_digest'],
                  'delivered_files': sorted(files), 'byte_replay': True,
                  'donor_ablation': ablation['failure'], 'migi_credit': 0}))
