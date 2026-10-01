"""Reject semantic watchdog and responsiveness faults, using assertion failures."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

subject = Path('compute_worker/compute_worker.py').read_text()
mutations = [
    ('missing-watchdog', 'watchdog.start()', 'None',
     'test_quiet_container_is_stopped_at_deadline'),
    ('blocking-log-iteration', 'log = await asyncio.to_thread(next_log)', 'log = next_log()',
     'test_event_loop_progresses_during_blocking_log_stream'),
]
results = []
for label, old, new, test in mutations:
    assert subject.count(old) == 1
    mutated = subject.replace(old, new, 1)
    ast.parse(mutated)
    with tempfile.TemporaryDirectory(prefix='worker-mutant-') as directory:
        root = Path(directory)
        file = root / 'worker.py'
        report = root / 'junit.xml'
        file.write_text(mutated)
        env = dict(os.environ, WORKER_SUBJECT=str(file))
        env.pop('REAL_DOCKER', None)
        result = subprocess.run([sys.executable, '-m', 'pytest', '-c', '/dev/null', '-q',
                                 '.genesis/worker-court/tests.py::' + test,
                                 '--junitxml=' + str(report)], env=env, text=True, capture_output=True, timeout=12)
        assert result.returncode == 1, result.stdout + result.stderr
        cases = list(ET.parse(report).getroot().iter('testcase'))
        assert len(cases) == 1 and cases[0].find('error') is None
        failure = cases[0].find('failure')
        assert failure is not None and failure.attrib.get('message', '').startswith('assert ')
        results.append({'mutant': label, 'test': test, 'rejected_by_assertion': True})
print(json.dumps(results))
