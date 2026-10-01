"""Accept only the two expected ranking assertion failures, never setup errors."""
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET

report = ET.parse('src/producer-baseline.xml').getroot()
cases = list(report.iter('testcase'))
expected = {'test_missing_primary_score_is_ranked_after_scored_submission',
            'test_force_best_ignores_submission_missing_primary_score'}
assert {c.attrib['name'] for c in cases} == expected
assert len(cases) == 2
for case in cases:
    assert case.find('error') is None
    assert case.find('skipped') is None
    failure = case.find('failure')
    assert failure is not None
    operator = '<' if case.attrib['name'].startswith('test_missing_') else '=='
    assert re.fullmatch(r'assert -?\d+ ' + re.escape(operator) + r' -?\d+',
                        failure.attrib.get('message', ''))
    marker = 'assert ids.index(' if operator == '<' else 'assert best.pk =='
    assert marker in (failure.text or '')
print(json.dumps({'upstream_baseline': 'TWO_EXPECTED_ASSERTION_FAILURES',
                  'tests': sorted(expected), 'setup_errors': 0}))
