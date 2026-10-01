from concurrent.futures import ProcessPoolExecutor
import pytest
from g0.ledger import Ledger


def append_one(path, i):
    Ledger(path).append('parallel', {'i':i})


def test_interrupted_commit_preserves_previous_then_recovers(tmp_path):
    path=tmp_path/'ledger.jsonl'
    ledger=Ledger(path)
    ledger.append('first', {'i':1})
    old=path.read_bytes()
    def power_loss():
        raise OSError('injected precommit failure')
    ledger._before_commit=power_loss
    with pytest.raises(OSError):
        ledger.append('second', {'i':2})
    assert path.read_bytes()==old
    recovered=Ledger(path)
    assert recovered.verify()==(True,None)
    recovered.append('recovery', {'i':3})
    assert len(recovered.records())==2
    assert recovered.records()[-1]['prev']==recovered.records()[0]['digest']


def test_corruption_blocks_new_work_until_explicit_restore(tmp_path):
    path=tmp_path/'ledger.jsonl'
    ledger=Ledger(path)
    ledger.append('good', {'i':1})
    checkpoint=path.read_bytes()
    path.write_bytes(checkpoint+b'{"torn":')
    assert not ledger.verify()[0]
    with pytest.raises(ValueError,match='corrupt'):
        ledger.append('must-not-run', {})
    path.write_bytes(checkpoint)
    recovered=Ledger(path)
    recovered.append('after_explicit_rollback', {})
    assert recovered.verify()==(True,None)


def test_simultaneous_processes_do_not_lose_or_fork_records(tmp_path):
    path=tmp_path/'ledger.jsonl'
    with ProcessPoolExecutor(max_workers=4) as pool:
        list(pool.map(append_one,[path]*12,range(12)))
    ledger=Ledger(path)
    assert ledger.verify()==(True,None)
    assert {r['payload']['i'] for r in ledger.records()}==set(range(12))
    assert len(ledger.records())==12


def test_task_freeze_cannot_be_overwritten_and_tamper_blocks_outcome(tmp_path):
    from g0 import Court
    import json
    court=Court(tmp_path/'court')
    f=court.freeze('../external/task',{'raw':'original'},'external://task',ts_ns=1)
    assert court.freeze('../external/task',{'raw':'original'},'external://task')==f
    with pytest.raises(ValueError,match='cannot be replaced'):
        court.freeze('../external/task',{'raw':'later answer'},'external://task')
    path=next((tmp_path/'court').glob('*.freeze.json'))
    data=json.loads(path.read_text()); data['raw']='corrupted'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='corrupted'):
        court.outcome('../external/task',{'pass':True},['external://ci'],'external')
    assert not list((tmp_path/'court').glob('*.outcome.json'))
