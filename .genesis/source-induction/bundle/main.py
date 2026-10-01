"""Bootstrap producer: induce conditional expression transplants from source.

No issue-specific patch, field name, ORM function, null-order policy or donor
code is embedded. This is a bounded source-induction mechanism, not MIGI.
"""
import ast
import copy
import hashlib
import json
import sys


def same(a, b):
    return ast.dump(a, include_attributes=False) == ast.dump(b, include_attributes=False)


def names(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def unify(template, target, bindings):
    if isinstance(template, ast.Name) and isinstance(target, ast.Name):
        previous=bindings.get(template.id)
        if previous is not None and not same(previous,target):
            return False
        bindings[template.id]=target
        return True
    if type(template) is not type(target):
        return False
    if isinstance(template,ast.AST):
        return all(unify(getattr(template,k),getattr(target,k),bindings)
                   for k in template._fields)
    if isinstance(template,list):
        return len(template)==len(target) and all(unify(a,b,bindings) for a,b in zip(template,target))
    return template==target


class Substitute(ast.NodeTransformer):
    def __init__(self, bindings):
        self.bindings=bindings
    def visit_Name(self,node):
        return copy.deepcopy(self.bindings.get(node.id,node))


def parameter_role(node, guard_names):
    """Find a shared parameter in two call branches, distinct from the guard."""
    roles=[]
    for n in ast.walk(node):
        if isinstance(n,ast.Call):
            for arg in n.args:
                if isinstance(arg,ast.Name) and arg.id not in guard_names:
                    roles.append(arg.id)
    return set(roles)


def signed_selector(node):
    # A signed field selector is an observed syntax pattern, not a list of
    # permitted replacement operators. Replacement code must come from source.
    if not isinstance(node,ast.JoinedStr) or not node.values:
        return None
    first=node.values[0]
    if not isinstance(first,ast.FormattedValue) or not isinstance(first.value,ast.IfExp):
        return None
    conditional=first.value
    if not (isinstance(conditional.body,ast.Constant)
            and isinstance(conditional.orelse,ast.Constant)
            and {conditional.body.value,conditional.orelse.value}=={'-',''}):
        return None
    rest=node.values[1:]
    if len(rest)!=1:
        return None
    if isinstance(rest[0],ast.Constant) and isinstance(rest[0].value,str):
        field=ast.Constant(rest[0].value)
    elif isinstance(rest[0],ast.FormattedValue):
        field=rest[0].value
    else:
        return None
    return conditional,field


def imported_symbols(tree):
    result={}
    for node in tree.body:
        if isinstance(node,ast.ImportFrom):
            for alias in node.names:
                result[alias.asname or alias.name]=(node.module,node.level,alias.name,alias.asname)
    return result


def offset(source,node):
    # AST columns count UTF-8 bytes; preserve arbitrary Unicode source.
    lines=source.splitlines(keepends=True)
    start=sum(len(x) for x in lines[:node.lineno-1])
    end=sum(len(x) for x in lines[:node.end_lineno-1])
    start+=len(lines[node.lineno-1].encode()[:node.col_offset].decode())
    end+=len(lines[node.end_lineno-1].encode()[:node.end_col_offset].decode())
    return start,end


def induce(files):
    trees={path:ast.parse(source) for path,source in files.items()}
    donors=[]
    imports={path:imported_symbols(t) for path,t in trees.items()}
    for path,tree in trees.items():
        for n in ast.walk(tree):
            if not isinstance(n,ast.IfExp):
                continue
            if not isinstance(n.body,ast.Call) or not isinstance(n.orelse,ast.Call):
                continue
            roles=parameter_role(n.body,names(n.test)) & parameter_role(n.orelse,names(n.test))
            if len(roles)!=1:
                continue
            donors.append((path,n,next(iter(roles))))
    proposals={}
    evidence=[]
    needed={}
    for path,tree in trees.items():
        source=files[path]
        for node in ast.walk(tree):
            parsed=signed_selector(node)
            if parsed is None:
                continue
            conditional,field=parsed
            choices={}
            for donor_path,donor,role in donors:
                bindings={}
                if not unify(donor.test,conditional.test,bindings):
                    continue
                # The observed sign convention must agree with the donor's
                # observed branch choice; opposite cases remain ambiguous.
                if conditional.body.value!='-':
                    continue
                bindings[role]=field
                new=Substitute(bindings).visit(copy.deepcopy(donor))
                new.test=copy.deepcopy(conditional.test)
                ast.fix_missing_locations(new)
                code=ast.unparse(new)
                external_names=names(new)-names(conditional.test)-names(field)
                dependencies={}
                for name in external_names:
                    if name in imports[donor_path] and name not in imports[path]:
                        dependencies[name]=imports[donor_path][name]
                choices[code]=(donor_path,donor,dependencies)
            # Conflicting corpus rules do not become an arbitrary winner.
            if len(choices)!=1:
                evidence.append({'path':path,'line':node.lineno,'status':'ABSTAIN',
                                 'distinct_source_rules':len(choices)})
                continue
            replacement,(donor_path,donor,dependencies)=next(iter(choices.items()))
            start,end=offset(source,node)
            proposals.setdefault(path,[]).append((start,end,replacement))
            needed.setdefault(path,{}).update(dependencies)
            evidence.append({'path':path,'line':node.lineno,'status':'GENERATED',
                             'original':ast.get_source_segment(source,node),
                             'replacement':replacement,'donor_path':donor_path,
                             'donor_line':donor.lineno,
                             'donor_code':ast.get_source_segment(files[donor_path],donor)})
    delivery={}
    for path,replacements in proposals.items():
        source=files[path]
        # Preserve existing formatting and comments outside the expression.
        for start,end,code in sorted(replacements,reverse=True):
            source=source[:start]+code+source[end:]
        for name,(module,level,original,alias) in sorted(needed.get(path,{}).items()):
            statement=ast.ImportFrom(module=module,names=[ast.alias(name=original,asname=alias)],level=level)
            import_text=ast.unparse(statement)+'\n'
            tree=ast.parse(source)
            insert=0
            for n in tree.body:
                if isinstance(n,(ast.Import,ast.ImportFrom)) or (
                    isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant)
                    and isinstance(n.value.value,str)):
                    insert=offset(source,n)[1]
                    if source[insert:insert+1]=='\n':insert+=1
                else:
                    break
            source=source[:insert]+import_text+source[insert:]
        ast.parse(source)
        delivery[path]=source
    return delivery,evidence


request=json.load(sys.stdin)
files=request['task']['source_files']
if not isinstance(files,dict) or len(files)>100:
    raise ValueError('invalid source corpus')
delivery,evidence=induce(files)
result={'source_induced_changes':evidence,'scope':'BOUNDED_BOOTSTRAP_NOT_MIGI',
        'input_sha256':hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()}
if delivery:
    result['delivery']={'files':delivery}
else:
    result['failure']='NO_UNAMBIGUOUS_SOURCE_DERIVED_REPAIR'
print(json.dumps(result,ensure_ascii=False))
