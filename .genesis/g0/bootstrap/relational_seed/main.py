import json,sys,re
req=json.load(sys.stdin); text=json.dumps(req.get('task',{}),ensure_ascii=False).lower()
toks=re.findall(r'[a-z][a-z0-9_-]{2,}',text)
from collections import Counter
c=Counter(toks)
repeated=[x for x,n in c.items() if n>=2 and x not in {'expected','actual','issue','steps','behavior','response','version'}]
print(json.dumps({'action':'probe','focus':repeated[:5],'strategy':'contrast repeated identities across contexts'}))
