import json,sys
req=json.load(sys.stdin); t=req.get('task',{})
raw=json.dumps(t,ensure_ascii=False)
print(json.dumps({'action':'probe','strategy':'construct smallest A/B intervention preserving all but one observed difference','evidence_length':len(raw)}))
