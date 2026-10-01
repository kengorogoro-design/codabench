import json,sys
req=json.load(sys.stdin); hist=req.get('history',{})
# This bootstrap does not define the ecology's cognition; it emits arbitrary executable bundles.
# If history reports poor contrast coverage, emit a structurally different generator that delegates
# candidate construction to data-derived token pairs rather than this template's fixed strategy.
poor=hist.get('poor_transfer',False)
if not poor:
    code="""import json,sys\nr=json.load(sys.stdin); t=r.get('task',{})\nprint(json.dumps({'action':'probe','strategy':'seek externally observable divergence before hypothesizing cause','task_keys':sorted(t)[:8]}))\n"""
    bundles=[{'files':{'bundle.json':'{"entrypoint":"main.py","kind":"candidate"}','main.py':code}}]
else:
    gen="""import json,sys,re\nr=json.load(sys.stdin); h=json.dumps(r.get('history',{}),ensure_ascii=False)\npairs=[]\nfor m in re.finditer(r'([A-Za-z_][A-Za-z0-9_-]{2,}).{0,40}(fail|pass|wrong|right|stale|fresh)',h,re.I|re.S): pairs.append(m.group(1))\ncode='import json,sys\\nr=json.load(sys.stdin); print(json.dumps({\\\"action\\\":\\\"probe\\\",\\\"learned_tokens\\\":'+repr(pairs[:12])+'}))\\n'\nprint(json.dumps({'bundles':[{'files':{'bundle.json':'{\\\"entrypoint\\\":\\\"main.py\\\",\\\"kind\\\":\\\"candidate\\\"}','main.py':code}}]}))\n"""
    bundles=[{'files':{'bundle.json':'{"entrypoint":"main.py","kind":"generator"}','main.py':gen}}]
print(json.dumps({'bundles':bundles}))
