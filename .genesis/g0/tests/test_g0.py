from pathlib import Path
import json
from g0 import Bundle, Ecology, Court
from g0.ledger import Ledger
from g0.selection import ExternalEvidence, dominates, eligible_strong

ROOT=Path(__file__).resolve().parents[1]

def test_ledger_tamper_evident(tmp_path):
    l=Ledger(tmp_path/'l.jsonl'); l.append('a',{'x':1},ts_ns=1); l.append('b',{'x':2},ts_ns=2)
    assert l.verify()==(True,None)
    rows=l.path.read_text().splitlines(); obj=json.loads(rows[0]); obj['payload']['x']=9; rows[0]=json.dumps(obj)
    l.path.write_text('\n'.join(rows)+'\n')
    assert l.verify()[0] is False

def test_bundle_is_opaque_and_runnable(tmp_path):
    eco=Ecology(tmp_path/'eco')
    b=eco.admit_bundle(ROOT/'bootstrap'/'relational_seed')
    out=eco.ask(b,{'task_id':'x','raw':'alpha path fails, alpha path works elsewhere'})
    assert out['action']=='probe'

def test_generator_can_generate_candidate(tmp_path):
    eco=Ecology(tmp_path/'eco'); g=eco.admit_bundle(ROOT/'bootstrap'/'self_rewriting_generator',role='generator')
    succ=eco.generate_successors(g,{'poor_transfer':False},tmp_path/'s')
    assert len(succ)==1 and succ[0].kind=='candidate'
    assert eco.ask(succ[0],{'task_id':'t','x':1})['action']=='probe'

def test_generator_can_generate_replacement_generator(tmp_path):
    eco=Ecology(tmp_path/'eco'); g=eco.admit_bundle(ROOT/'bootstrap'/'self_rewriting_generator',role='generator')
    succ=eco.generate_successors(g,{'poor_transfer':True,'external_failure':'stale provider binding'},tmp_path/'s')
    assert len(succ)==1 and succ[0].kind=='generator'
    # Replacement generator is structurally different and can itself generate an executable candidate.
    succ2=eco.generate_successors(succ[0],{'external_failure':'provider stale wrong'},tmp_path/'s2')
    assert succ2 and succ2[0].kind=='candidate'

def test_external_evidence_only_selection():
    a=[ExternalEvidence('t','A',True,True,True,True,True,False,True,1)]
    b=[ExternalEvidence('t','B',True,True,True,True,False,False,True,1)]
    assert eligible_strong(a[0])
    assert not eligible_strong(b[0])
    assert dominates(a,b)

def test_court_freeze_custody(tmp_path):
    c=Court(tmp_path); f=c.freeze('t',{'raw':'x'},'external://issue',commit='abc',ts_ns=1)
    o=c.outcome('t',{'pass':True},['external://ci'],'independent_ci')
    assert o['freeze_digest']==f['freeze_digest']

def test_runner_uses_current_interpreter(tmp_path):
    eco=Ecology(tmp_path/'eco')
    b=eco.admit_bundle(ROOT/'bootstrap'/'intervention_seed')
    out=eco.ask(b,{'task_id':'portable','raw':'x'})
    assert out['action']=='probe'

def test_effect_relay_returns_external_receipt_to_opaque_bundle(tmp_path):
    from g0 import EffectRelay
    eco=Ecology(tmp_path/'eco')
    b=eco.admit_bundle(ROOT/'bootstrap'/'effect_echo_seed')
    relay=EffectRelay(eco.ledger, {'echo': lambda args: {'echoed': args['value']}}, authority=lambda name,args: True)
    out=relay.run(b, {'value':'reality'})
    assert out == {'final': True, 'observed': {'echoed':'reality'}, 'ok': True}
    assert eco.ledger.verify()==(True,None)


def test_effect_relay_respects_external_authority(tmp_path):
    from g0 import EffectRelay
    eco=Ecology(tmp_path/'eco')
    b=eco.admit_bundle(ROOT/'bootstrap'/'effect_echo_seed')
    relay=EffectRelay(
        eco.ledger,
        {'echo': lambda args: {'echoed': args['value']}},
        authority=lambda name,args: False,
    )
    out=relay.run(b, {'value':'blocked'})
    assert out['final'] is True
    assert out['ok'] is False
    assert out['observed'] is None


def test_effect_relay_is_budget_bounded(tmp_path):
    from g0 import EffectRelay, EffectError
    loop=tmp_path/'loop'; loop.mkdir()
    (loop/'bundle.json').write_text('{"entrypoint":"main.py","kind":"candidate"}')
    (loop/'main.py').write_text(
        "import json,sys\njson.load(sys.stdin)\nprint(json.dumps({'effect':{'name':'echo','args':{}}}))\n"
    )
    eco=Ecology(tmp_path/'eco')
    b=eco.admit_bundle(loop)
    relay=EffectRelay(eco.ledger, {'echo': lambda args: {}}, authority=lambda name,args: True)
    try:
        relay.run(b, {}, max_effects=2)
    except EffectError as exc:
        assert 'budget' in str(exc)
    else:
        raise AssertionError('expected bounded effect failure')
