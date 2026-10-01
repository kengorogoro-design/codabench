from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ExternalEvidence:
    """Imported court assertions; flags alone do not authenticate a provider.

    The trusted importer must establish provenance and verifier independence.
    This decision preflight cannot admit MIGI or promote a runtime by itself.
    """
    task_id: str
    candidate_id: str
    externally_owned: bool
    freeze_before_reveal: bool
    production_faithful: bool
    independent_judge: bool
    accepted_or_merged: bool
    production_outcome: bool
    regression_free: bool
    cost: float = 0.0


def _valid(e: ExternalEvidence) -> bool:
    if not isinstance(e, ExternalEvidence):
        return False
    flags = (e.externally_owned, e.freeze_before_reveal,
             e.production_faithful, e.independent_judge,
             e.accepted_or_merged, e.production_outcome, e.regression_free)
    return (isinstance(e.task_id, str) and bool(e.task_id)
            and isinstance(e.candidate_id, str) and bool(e.candidate_id)
            and all(type(v) is bool for v in flags)
            and type(e.cost) in (int, float)
            and math.isfinite(e.cost) and e.cost >= 0
            and (not e.production_outcome or e.accepted_or_merged))


def eligible_strong(e: ExternalEvidence) -> bool:
    return _valid(e) and all((e.externally_owned, e.freeze_before_reveal,
                             e.production_faithful, e.independent_judge,
                             e.accepted_or_merged, e.regression_free))


def evidence_vector(e: ExternalEvidence) -> tuple:
    if not _valid(e):
        raise ValueError('invalid external evidence')
    return (int(e.production_outcome), int(e.accepted_or_merged),
            int(e.regression_free), -float(e.cost))


def _index(records):
    if not records or any(not _valid(e) for e in records):
        return None
    if len({e.candidate_id for e in records}) != 1:
        return None
    if len({e.task_id for e in records}) != len(records):
        return None
    return {e.task_id: e for e in records}


def dominates(a: list[ExternalEvidence], b: list[ExternalEvidence]) -> bool:
    """Full matched courts, mandatory winner gates, componentwise dominance.

    Missing/duplicate/mixed evidence cannot disappear. A production outcome
    cannot compensate for regression or higher cost. This is a preflight only.
    """
    ma, mb = _index(a), _index(b)
    if ma is None or mb is None or set(ma) != set(mb):
        return False
    if a[0].candidate_id == b[0].candidate_id:
        return False
    if not all(eligible_strong(e) for e in a):
        return False
    if not all(e.externally_owned and e.freeze_before_reveal
               and e.production_faithful and e.independent_judge for e in b):
        return False
    strict = False
    for task_id in ma:
        va, vb = evidence_vector(ma[task_id]), evidence_vector(mb[task_id])
        if any(x < y for x, y in zip(va, vb)):
            return False
        strict |= any(x > y for x, y in zip(va, vb))
    return strict
