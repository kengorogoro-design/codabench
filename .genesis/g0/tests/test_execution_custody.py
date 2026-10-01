import json
from pathlib import Path
import pytest
from g0 import Bundle
from g0.ledger import Ledger
from g0.runner import run_bundle, RunError
from g0.producer import execute_producer, matches_delivery, files_digest


def bundle(tmp_path, source):
    d = tmp_path/'candidate'
    d.mkdir()
    (d/'bundle.json').write_text('{"entrypoint":"main.py","kind":"candidate"}')
    (d/'main.py').write_text(source)
    return Bundle.load(d)


def test_changed_source_cannot_execute_as_old_identity(tmp_path):
    b = bundle(tmp_path, 'print("{}")')
    (b.root/'main.py').write_text('print("{\\"fake\\":true}")')
    with pytest.raises(RunError, match='identity'):
        run_bundle(b, {})


def test_candidate_working_files_do_not_modify_original_bundle(tmp_path):
    b = bundle(tmp_path, 'from pathlib import Path\nPath("scratch").write_text("x")\nprint("{}")')
    assert run_bundle(b, {}) == {}
    assert not (b.root/'scratch').exists()
    assert Bundle.load(b.root).bundle_id == b.bundle_id


def test_symlink_and_unhashed_entrypoints_rejected(tmp_path):
    b = bundle(tmp_path, 'print("{}")')
    (b.root/'alias.py').symlink_to('main.py')
    with pytest.raises(ValueError, match='symlink'):
        Bundle.load(b.root)


def test_timeout_and_output_are_bounded(tmp_path):
    b = bundle(tmp_path, 'import time\ntime.sleep(5)\nprint("{}")')
    with pytest.raises(RunError, match='timeout'):
        run_bundle(b, {}, timeout_s=0.1)
    (b.root/'main.py').write_text('print("x"*10000)')
    b = Bundle.load(b.root)
    with pytest.raises(RunError, match='bound'):
        run_bundle(b, {}, max_output_bytes=4096)


def test_nonfinite_candidate_output_is_rejected(tmp_path):
    b = bundle(tmp_path, 'print(\'{"x":NaN}\')')
    with pytest.raises(RunError, match='finite JSON'):
        run_bundle(b, {})


def test_probe_output_cannot_claim_builder_patch(tmp_path):
    root = Path(__file__).resolve().parents[1]
    b = Bundle.load(root/'bootstrap'/'intervention_seed')
    receipt = execute_producer(b, {'task':{'raw':'external task'}}, Ledger(tmp_path/'l'))
    assert receipt['delivery_digest'] is None
    assert not matches_delivery(receipt, {'repair.py':'print("real fix")'})


def test_actual_process_delivery_is_bound_and_builder_edits_break_it(tmp_path):
    files = {'repair.py':'print("fixture only")\n'}
    source = 'import json\nprint(json.dumps('+repr({'delivery':{'files':files}})+'))'
    b = bundle(tmp_path, source)
    ledger = Ledger(tmp_path/'l')
    receipt = execute_producer(b, {'task':{'raw':'fixture'}}, ledger)
    assert matches_delivery(receipt, files)
    assert not matches_delivery(receipt, {'repair.py':'print("builder edited")\n'})
    assert ledger.verify() == (True, None)
    # A modified stored output must not match its old receipt.
    receipt['output']['delivery']['files']['repair.py'] = 'changed'
    assert not matches_delivery(receipt, {'repair.py':'changed'})


@pytest.mark.parametrize('name', ['../outside', '/outside', 'a\\b', 'a/../b', 'a//b'])
def test_delivered_path_cannot_escape_or_alias(name):
    with pytest.raises(ValueError):
        files_digest({name:'x'})
