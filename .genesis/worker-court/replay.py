"""Regenerate delivered code from the corrected opaque generator on another host."""
import json
from pathlib import Path
import sys
import tempfile

here = Path(__file__).resolve().parent
sys.path.insert(0, str(here / 'runtime'))
from g0.bundle import Bundle
from g0.ecology import Ecology
from g0.ledger import Ledger
from g0.producer import execute_producer, matches_delivery

freeze = json.loads((here / 'regenerated_freeze.json').read_text())
generator = Bundle.load(here / 'corrected_generator')
assert generator.bundle_id == freeze['generator_id']
history = json.loads((here / 'successor_training.json').read_text())
request = json.loads((here / 'request.json').read_text())
expected = json.loads((here / 'regenerated_output.json').read_text())
with tempfile.TemporaryDirectory(prefix='worker-court-replay-') as directory:
    root = Path(directory)
    successor = Ecology(root / 'ecology').generate_successors(generator, history, root / 'successors')[0]
    assert successor.bundle_id == freeze['producer_id']
    receipt = execute_producer(successor, request, Ledger(root / 'execution.jsonl'))
    actual = {'compute_worker/compute_worker.py': Path('compute_worker/compute_worker.py').read_text()}
    assert matches_delivery(receipt, actual)
    assert receipt['output_digest'] == expected['output_digest']
    again = Ecology(root / 'descendant-ecology').generate_successors(successor, history, root / 'descendants')[0]
    assert again.bundle_id == successor.bundle_id
    print(json.dumps({'generator_id': generator.bundle_id, 'producer_id': successor.bundle_id,
                      'delivery_digest': receipt['delivery_digest'], 'exact_output_replay': True,
                      'selfhost_retry_identity': True, 'fresh_task_credit': 0, 'migi_credit': 0}))
