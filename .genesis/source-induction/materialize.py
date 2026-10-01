"""Materialize only the two frozen baseline or executed-output source files."""
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
if sys.argv[1] == 'baseline':
    files = json.loads((root / 'input.json').read_text())['task']['source_files']
elif sys.argv[1] == 'delivery':
    files = json.loads((root / 'receipt.json').read_text())['output']['delivery']['files']
else:
    raise ValueError('unknown materialization mode')
assert set(files) == {
    'src/apps/api/serializers/leaderboards.py',
    'src/apps/leaderboards/strategies.py',
}
for path, source in files.items():
    Path(path).write_text(source)
print(json.dumps({'materialized': sys.argv[1], 'files': sorted(files)}))
