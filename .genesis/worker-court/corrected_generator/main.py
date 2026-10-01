"""Bounded evidence-induced generator. No embedded task repair/operator menu.

This remains lower-order program induction, not MIGI. Source pairs are examples;
neither a schema change nor emitted code is evidence of a new intelligence class.
"""
import ast
import builtins
import copy
import hashlib
import json
from pathlib import Path
import sys


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def equal(a, b):
    return ast.dump(a, include_attributes=False) == ast.dump(b, include_attributes=False)


def node_size(node):
    return sum(1 for _ in ast.walk(node))


def named_units(tree):
    units = {}
    def visit(node, path):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                key = path + (child.name,)
                if not isinstance(child, ast.ClassDef):
                    units[key] = child
                visit(child, key)
            else:
                visit(child, path)
    visit(tree, ())
    return units


def changed_frontiers(left, right):
    if equal(left, right):
        return []
    if type(left) is not type(right):
        return [(left, right)]
    result = []
    for field in left._fields:
        a, b = getattr(left, field), getattr(right, field)
        if isinstance(a, ast.AST) and isinstance(b, ast.AST):
            result.extend(changed_frontiers(a, b))
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b) or any(type(x) is not type(y) for x, y in zip(a, b)):
                return [(left, right)]
            for x, y in zip(a, b):
                if isinstance(x, ast.AST) and isinstance(y, ast.AST):
                    result.extend(changed_frontiers(x, y))
                elif x != y:
                    return [(left, right)]
        elif a != b:
            return [(left, right)]
    # Lift a changed scalar/name/operator to its observed source context.
    if result and any(node_size(a) < 3 for a, _ in result):
        return [(left, right)]
    return result


def imports(tree):
    result = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                result[alias.asname or alias.name] = ast.unparse(
                    ast.ImportFrom(module=node.module, level=node.level, names=[alias]))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                result[alias.asname or alias.name.split('.')[0]] = ast.unparse(
                    ast.Import(names=[alias]))
    return result


def literal_key(value):
    return type(value).__name__ + ':' + repr(value)


def encode(node, shared_names, shared_literals):
    if isinstance(node, ast.Name) and node.id in shared_names:
        return {'meta': 'name:' + node.id, 'kind': 'name'}
    if isinstance(node, ast.Constant) and literal_key(node.value) in shared_literals:
        return {'meta': 'literal:' + literal_key(node.value), 'kind': 'literal'}
    if isinstance(node, ast.AST):
        return {'type': type(node).__name__, 'fields': {
            k: encode(getattr(node, k), shared_names, shared_literals) for k in node._fields}}
    if isinstance(node, list):
        return [encode(x, shared_names, shared_literals) for x in node]
    return node


def learn(examples):
    rules = {}
    for example in examples:
        before, after = ast.parse(example['before']), ast.parse(example['after'])
        left_units, right_units = named_units(before), named_units(after)
        before_imports, after_imports = imports(before), imports(after)
        for key in sorted(left_units.keys() & right_units.keys()):
            for left, right in changed_frontiers(left_units[key], right_units[key]):
                if not isinstance(left, (ast.expr, ast.stmt)) or node_size(left) < 3:
                    continue
                old_names = {n.id for n in ast.walk(left) if isinstance(n, ast.Name)}
                new_names = {n.id for n in ast.walk(right) if isinstance(n, ast.Name)}
                shared_names = (old_names & new_names) - set(before_imports)
                old_literals = {literal_key(n.value) for n in ast.walk(left) if isinstance(n, ast.Constant)}
                new_literals = {literal_key(n.value) for n in ast.walk(right) if isinstance(n, ast.Constant)}
                shared_literals = old_literals & new_literals
                pattern = encode(left, shared_names, shared_literals)
                replacement = encode(right, shared_names, shared_literals)
                if pattern == replacement:
                    continue
                dependencies = {n: after_imports[n] for n in new_names - old_names if n in after_imports}
                rule = {'pattern': pattern, 'replacement': replacement,
                        'dependencies': dependencies,
                        'example_id': example['example_id'],
                        'example_digest': digest({'before': example['before'], 'after': example['after']}),
                        'unit': list(key), 'observed_before': ast.unparse(left),
                        'observed_after': ast.unparse(right)}
                identity = digest({'pattern': pattern, 'replacement': replacement, 'dependencies': dependencies})
                rules[identity] = rule
    return [{'rule_id': k, **v} for k, v in sorted(rules.items())]


def match(pattern, target, bindings):
    if isinstance(pattern, dict) and 'meta' in pattern:
        kind = pattern['kind']
        if kind == 'name' and not isinstance(target, ast.Name):
            return False
        if kind == 'literal' and not isinstance(target, ast.Constant):
            return False
        old = bindings.get(pattern['meta'])
        if old is not None:
            if isinstance(old, ast.Name) and isinstance(target, ast.Name):
                if old.id != target.id:
                    return False
            elif not equal(old, target):
                return False
        bindings[pattern['meta']] = target
        return True
    if isinstance(pattern, dict) and 'type' in pattern:
        return isinstance(target, ast.AST) and type(target).__name__ == pattern['type'] and all(
            match(v, getattr(target, k), bindings) for k, v in pattern['fields'].items())
    if isinstance(pattern, list):
        return isinstance(target, list) and len(pattern) == len(target) and all(
            match(a, b, bindings) for a, b in zip(pattern, target))
    return pattern == target


def instantiate(template, bindings):
    if isinstance(template, dict) and 'meta' in template:
        return copy.deepcopy(bindings[template['meta']])
    if isinstance(template, dict) and 'type' in template:
        cls = getattr(ast, template['type'])
        return cls(**{k: instantiate(v, bindings) for k, v in template['fields'].items()})
    if isinstance(template, list):
        return [instantiate(x, bindings) for x in template]
    return template


def offsets(source, node):
    lines = source.splitlines(keepends=True)
    start = sum(len(x) for x in lines[:node.lineno - 1])
    end = sum(len(x) for x in lines[:node.end_lineno - 1])
    start += len(lines[node.lineno - 1].encode()[:node.col_offset].decode())
    end += len(lines[node.end_lineno - 1].encode()[:node.end_col_offset].decode())
    return start, end


def deliver(rules, sources):
    files, evidence = {}, []
    for path, source in sources.items():
        tree = ast.parse(source)
        present_imports = imports(tree)
        present_names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        available = present_names | set(dir(builtins))
        edits, dependencies = [], {}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.expr, ast.stmt)):
                continue
            choices = {}
            for rule in rules:
                bindings = {}
                if not match(rule['pattern'], node, bindings):
                    continue
                replacement = instantiate(rule['replacement'], bindings)
                ast.fix_missing_locations(replacement)
                needed = rule['dependencies']
                conflicts = {n for n, stmt in needed.items()
                             if n in present_imports and present_imports[n] != stmt}
                new_names = {n.id for n in ast.walk(replacement) if isinstance(n, ast.Name)}
                introduced = {n.id for n in ast.walk(replacement)
                              if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
                introduced.update(n.name for n in ast.walk(replacement)
                                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
                introduced.update(n.arg for n in ast.walk(replacement) if isinstance(n, ast.arg))
                introduced.update(n.name for n in ast.walk(replacement)
                                  if isinstance(n, ast.ExceptHandler) and n.name)
                if conflicts or new_names - available - set(needed) - introduced:
                    continue
                code = ast.unparse(replacement)
                if code != ast.unparse(node):
                    choices[code] = (rule, needed)
            if len(choices) != 1:
                if choices:
                    evidence.append({'path': path, 'line': node.lineno, 'status': 'AMBIGUOUS', 'alternatives': len(choices)})
                continue
            code, (rule, needed) = next(iter(choices.items()))
            start, end = offsets(source, node)
            pieces = code.splitlines()
            code = pieces[0] + ''.join('\n' + ' ' * node.col_offset + line for line in pieces[1:])
            edits.append((start, end, code))
            dependencies.update({k: v for k, v in needed.items() if k not in present_imports})
            evidence.append({'path': path, 'line': node.lineno, 'status': 'GENERATED',
                             'rule_id': rule['rule_id'], 'source_example': rule['example_id'],
                             'original': ast.get_source_segment(source, node), 'replacement': code})
        ordered = sorted(edits)
        if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
            evidence.append({'path': path, 'status': 'OVERLAPPING_RULES_ABSTAIN'})
            continue
        if not edits:
            continue
        for start, end, code in reversed(ordered):
            source = source[:start] + code + source[end:]
        for statement in sorted(set(dependencies.values())):
            current_tree = ast.parse(source)
            insert = 0
            for top in current_tree.body:
                if isinstance(top, (ast.Import, ast.ImportFrom)) or (
                    isinstance(top, ast.Expr) and isinstance(top.value, ast.Constant) and isinstance(top.value.value, str)):
                    insert = offsets(source, top)[1]
                    if source[insert:insert + 1] == '\n':
                        insert += 1
                else:
                    break
            source = source[:insert] + statement + '\n' + source[insert:]
        ast.parse(source)
        files[path] = source
    result = {'evidence': evidence, 'rule_ids': [r['rule_id'] for r in rules],
              'scope': 'BOUNDED_SOURCE_PAIR_LEARNING_NOT_MIGI'}
    if files:
        result['delivery'] = {'files': files}
    else:
        result['failure'] = 'NO_APPLICABLE_UNAMBIGUOUS_LEARNED_RULE'
    return result


RULES = []


def main():
    request = json.load(sys.stdin)
    if request.get('op') == 'generate':
        examples = request['history']['examples']
        if not isinstance(examples, list) or len(examples) > 32:
            raise ValueError('invalid example count')
        rules = learn(examples)
        # The generator itself emits an executable rule-bearing successor.
        source = Path(__file__).read_text()
        prefix = source[:source.index('\nRULES = ')]
        entry = source[source.index('\ndef main():'):]
        program = prefix + '\nRULES = ' + repr(rules) + '\n' + entry
        out = {'bundles': [{'files': {'main.py': program,
                'bundle.json': '{"entrypoint":"main.py","kind":"generator"}'}}],
               'learned_rules': rules, 'training_digest': digest(examples), 'migi_credit': 0}
    else:
        out = deliver(RULES, request['task']['source_files'])
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
