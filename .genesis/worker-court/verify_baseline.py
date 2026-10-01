import json
from pathlib import Path
import xml.etree.ElementTree as ET

cases = list(ET.parse('worker-upstream-baseline.xml').getroot().iter('testcase'))
expected = {'test_quiet_container_is_stopped_at_deadline', 'test_event_loop_progresses_during_blocking_log_stream'}
assert {c.attrib['name'] for c in cases} == expected
for case in cases:
    assert case.find('error') is None and case.find('skipped') is None
    failure = case.find('failure')
    assert failure is not None and failure.attrib.get('message', '').startswith('assert ')
print(json.dumps({'upstream_failures': sorted(expected), 'setup_errors': 0}))
