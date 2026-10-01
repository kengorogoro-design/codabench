import json,sys
r=json.load(sys.stdin)
if r.get('op')=='act':
    task=r.get('task',{})
    print(json.dumps({'effect':{'name':'echo','args':{'value':task.get('value')}},'continuation':{'phase':1}}))
else:
    receipt=r.get('receipt',{})
    print(json.dumps({'final':True,'observed':receipt.get('result'),'ok':receipt.get('ok')}))
