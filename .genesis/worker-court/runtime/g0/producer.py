"""Custody of executable output. No intelligence or admission claims here."""
from __future__ import annotations

import json
from pathlib import PurePosixPath
from .bundle import Bundle
from .hashutil import canonical_json, sha256_bytes
from .runner import run_bundle


def files_digest(files: dict[str, str]) -> str:
    if not isinstance(files, dict) or not files:
        raise ValueError('no delivered files')
    rows = []
    for name, content in sorted(files.items()):
        if not isinstance(name, str) or not isinstance(content, str):
            raise ValueError('delivery must contain UTF-8 file bytes')
        p = PurePosixPath(name)
        if (p.is_absolute() or '..' in p.parts or '\\' in name
                or str(p) != name or name in ('.', '')):
            raise ValueError('invalid delivery path')
        rows.append((name, sha256_bytes(content.encode())))
    return sha256_bytes(canonical_json(rows))


def execute_producer(bundle: Bundle, frozen_request: dict, ledger) -> dict:
    """Bind actual process output to producer and request, before any edits.

    A source-specific execution receipt is only local custody evidence. An
    external witness/isolated evaluator remains required for strong credit.
    """
    request_digest = sha256_bytes(canonical_json(frozen_request))
    ledger.append('producer_started', {'producer_id':bundle.bundle_id,
                                      'request_digest':request_digest})
    output = run_bundle(bundle, frozen_request)
    delivery = output.get('delivery')
    files = delivery.get('files') if isinstance(delivery, dict) else None
    delivery_digest = files_digest(files) if files is not None else None
    receipt = {'producer_id':bundle.bundle_id, 'request_digest':request_digest,
               'output_digest':sha256_bytes(canonical_json(output)),
               'delivery_digest':delivery_digest, 'output':output,
               'origin':'EXECUTED_OPAQUE_PRODUCER', 'migi_credit':0}
    ledger.append('producer_completed', {k:v for k,v in receipt.items() if k!='output'})
    return receipt


def matches_delivery(receipt: dict, submitted_files: dict[str, str]) -> bool:
    """Any builder edit breaks producer attribution, even if CI is green."""
    try:
        output = receipt['output']
        original = output['delivery']['files']
        return (receipt.get('origin') == 'EXECUTED_OPAQUE_PRODUCER'
                and receipt['output_digest'] == sha256_bytes(canonical_json(output))
                and receipt['delivery_digest'] == files_digest(original)
                and receipt['delivery_digest'] == files_digest(submitted_files))
    except (KeyError, TypeError, ValueError):
        return False
