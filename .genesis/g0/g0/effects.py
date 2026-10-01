from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Any
from .hashutil import sha256_bytes, canonical_json
from .runner import run_bundle


class EffectError(RuntimeError):
    pass


@dataclass(frozen=True)
class Capability:
    name: str
    fn: Callable[[dict], Any]


class EffectRelay:
    """Thin operational relay between opaque bundles and registered effects.

    The relay does not interpret goals, plans, memory, or reasoning. A bundle may
    emit either a final JSON object or an `effect` envelope naming a runtime-
    registered capability. The capability receipt is then returned to the same
    bundle for its next opaque turn.
    """

    def __init__(self, ledger, capabilities: dict[str, Callable[[dict], Any]], authority=None):
        self.ledger = ledger
        self.capabilities = dict(capabilities)
        self.authority = authority if authority is not None else (lambda _name, _args: False)

    def _receipt(self, bundle_id: str, effect: dict) -> dict:
        if not isinstance(effect, dict):
            raise EffectError('effect must be an object')
        name = effect.get('name')
        args = effect.get('args', {})
        if not isinstance(name, str) or not name:
            raise EffectError('effect.name must be a non-empty string')
        if not isinstance(args, dict):
            raise EffectError('effect.args must be an object')
        req = {'candidate_id': bundle_id, 'name': name, 'args': args}
        request_digest = sha256_bytes(canonical_json(req))
        self.ledger.append('effect_requested', {**req, 'request_digest': request_digest})
        try:
            allowed = self.authority(name, args) is True
        except Exception:
            allowed = False
        if not allowed:
            receipt = {
                'ok': False,
                'name': name,
                'request_digest': request_digest,
                'error': 'authority_denied',
            }
            self.ledger.append('effect_receipt', receipt)
            return receipt
        fn = self.capabilities.get(name)
        if fn is None:
            receipt = {
                'ok': False,
                'name': name,
                'request_digest': request_digest,
                'error': 'capability_unavailable',
            }
            self.ledger.append('effect_receipt', receipt)
            return receipt
        try:
            result = fn(args)
            receipt = {
                'ok': True,
                'name': name,
                'request_digest': request_digest,
                'result': result,
                'result_digest': sha256_bytes(canonical_json(result)),
            }
        except Exception as exc:
            receipt = {
                'ok': False,
                'name': name,
                'request_digest': request_digest,
                'error': f'{type(exc).__name__}: {exc}',
            }
        self.ledger.append('effect_receipt', receipt)
        return receipt

    def run(self, bundle, initial: dict, max_effects: int = 8, timeout_s: int = 20) -> dict:
        request = {'op': 'act', 'task': initial}
        for step in range(max_effects + 1):
            out = run_bundle(bundle, request, timeout_s=timeout_s)
            self.ledger.append('candidate_turn', {
                'bundle_id': bundle.bundle_id,
                'step': step,
                'output': out,
            })
            effect = out.get('effect')
            if effect is None:
                return out
            if step >= max_effects:
                raise EffectError('effect budget exhausted')
            receipt = self._receipt(bundle.bundle_id, effect)
            request = {
                'op': 'effect_result',
                'receipt': receipt,
                'continuation': out.get('continuation'),
            }
        raise EffectError('unreachable')
