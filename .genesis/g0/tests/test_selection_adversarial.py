from dataclasses import replace
import pytest
from g0.selection import ExternalEvidence, dominates, eligible_strong


def evidence(task='t', candidate='A', **kw):
    e = ExternalEvidence(task, candidate, True, True, True, True,
                         True, False, True, 1.0)
    return replace(e, **kw)


@pytest.mark.parametrize('field', [
    'externally_owned', 'freeze_before_reveal', 'production_faithful',
    'independent_judge', 'accepted_or_merged', 'regression_free',
])
def test_production_never_compensates_for_required_gate(field):
    a = evidence(production_outcome=True, **{field: False})
    b = evidence(candidate='B', accepted_or_merged=False)
    assert not eligible_strong(a)
    assert not dominates([a], [b])


def test_cost_tradeoff_does_not_silently_become_a_win():
    a = evidence(production_outcome=True, cost=100)
    b = evidence(candidate='B', cost=1)
    assert not dominates([a], [b])


def test_missing_court_and_duplicates_block_selection():
    a = evidence(production_outcome=True)
    b = evidence(candidate='B')
    assert not dominates([a, evidence('second')], [b])
    assert not dominates([a], [b, evidence('second', 'B')])
    assert not dominates([a, a], [b])
    assert not dominates([a], [b, b])


def test_mixed_candidate_and_self_comparison_block_selection():
    a = evidence(production_outcome=True)
    assert not dominates([a], [evidence()])
    assert not dominates([a, evidence('second', 'C')],
                         [evidence(candidate='B'), evidence('second', 'B')])


@pytest.mark.parametrize('cost', [float('nan'), float('inf'), -1, True])
def test_invalid_cost_blocks_selection(cost):
    a = evidence(production_outcome=True, cost=cost)
    assert not eligible_strong(a)
    assert not dominates([a], [evidence(candidate='B')])


@pytest.mark.parametrize('value', ['false', 1, None])
def test_truthy_non_boolean_is_not_attestation(value):
    assert not eligible_strong(evidence(independent_judge=value))


def test_same_resource_matched_win_and_tie():
    a = [evidence('one', production_outcome=True), evidence('two')]
    b = [evidence('two', 'B'), evidence('one', 'B')]
    assert dominates(a, b)
    assert not dominates(b, a)
    assert not dominates([evidence()], [evidence(candidate='B')])


@pytest.mark.parametrize('authority', [None, lambda n,a: 'yes', lambda n,a: 1])
def test_unset_or_nonboolean_authority_executes_no_effect(tmp_path, authority):
    from g0.effects import EffectRelay
    from g0.ledger import Ledger
    calls = []
    relay = EffectRelay(Ledger(tmp_path/'ledger.jsonl'),
                        {'write': lambda args: calls.append(args)}, authority)
    receipt = relay._receipt('A', {'name': 'write', 'args': {}})
    assert receipt['error'] == 'authority_denied'
    assert calls == []


def test_authority_failure_is_denial(tmp_path):
    from g0.effects import EffectRelay
    from g0.ledger import Ledger
    def broken(name, args):
        raise RuntimeError('authority offline')
    calls = []
    relay = EffectRelay(Ledger(tmp_path/'ledger.jsonl'),
                        {'write': lambda args: calls.append(args)}, broken)
    assert relay._receipt('A', {'name':'write'})['error'] == 'authority_denied'
    assert calls == []
