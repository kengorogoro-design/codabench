from pathlib import Path
import json,tempfile
from g0 import Ecology
ROOT=Path(__file__).resolve().parent
with tempfile.TemporaryDirectory() as td:
    eco=Ecology(Path(td)/'eco')
    species=[]
    for p in ['relational_seed','intervention_seed']:
        b=eco.admit_bundle(ROOT/'bootstrap'/p); species.append({'id':b.bundle_id,'name':p,'out':eco.ask(b,{'task_id':'reality_probe','raw':'same object succeeds in context A and fails in context B'})})
    g=eco.admit_bundle(ROOT/'bootstrap'/'self_rewriting_generator',role='generator')
    s1=eco.generate_successors(g,{'poor_transfer':True,'external_failure':'explicit provider became default'},Path(td)/'g1')[0]
    s2=eco.generate_successors(s1,{'external_failure':'provider stale wrong'},Path(td)/'g2')[0]
    ok,err=eco.ledger.verify()
    print(json.dumps({'species':species,'generator':g.bundle_id,'replacement_generator':s1.bundle_id,'descendant_candidate':s2.bundle_id,'ledger_ok':ok,'ledger_error':err},indent=2))
