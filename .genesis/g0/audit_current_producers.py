"""Replay exposed real-task delivery boundary; no fresh-task credit."""
from pathlib import Path
import json
import tempfile
from g0 import Bundle
from g0.ledger import Ledger
from g0.producer import execute_producer, matches_delivery, files_digest

ROOT=Path(__file__).resolve().parent
task=json.loads((ROOT/'evidence/court_2512_raw.json').read_text())
subject=json.loads((ROOT/'evidence/external_subject_2512.json').read_text())
rows=[]
with tempfile.TemporaryDirectory() as td:
 ledger=Ledger(Path(td)/'ledger.jsonl')
 for name in ('relational_seed','intervention_seed'):
  b=Bundle.load(ROOT/'bootstrap'/name)
  receipt=execute_producer(b, {'op':'act','task':task}, ledger)
  matched=matches_delivery(receipt,subject['files'])
  rows.append({'seed':name,'producer_id':b.bundle_id,
               'output':receipt['output'],'delivery_digest':receipt['delivery_digest'],
               'matches_builder_feature':matched,'migi_credit':0})
 result={'court_class':task['court_class'],'subject_sha':subject['feature_sha'],
         'subject_files_digest':files_digest(subject['files']),
         'builder_feature_origin':subject['origin'],'producers':rows,
         'ledger_verified':ledger.verify()[0], 'autonomous_repair_credit':0,
         'ok':all(not r['matches_builder_feature'] for r in rows)}
print(json.dumps(result,indent=2))
raise SystemExit(0 if result['ok'] else 1)
