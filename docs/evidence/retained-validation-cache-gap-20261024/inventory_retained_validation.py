"""Bounded conservative source inventory; unresolved calls stay explicit."""
import ast
import hashlib
import json
from pathlib import Path


ROOT = Path('/home/sicarii/Work/sia-assurance-kernel-20261019/bin')
OUT = Path(__file__).resolve().parent / 'retained-validation-dependency-inventory.json'
MAX_NODES = 1024
MAX_MODULES = 64


def import_names(nodes):
    result = {}
    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                result[alias.asname or alias.name] = alias.name.split('.')
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                result[alias.asname or alias.name] = node.module.split('.') + [alias.name]
    return result


def load_module(name, modules):
    if name in modules:
        return modules[name]
    path = ROOT / (name + '.py')
    if not path.is_file():
        return None
    if len(modules) >= MAX_MODULES or path.stat().st_size > 2097152:
        raise ValueError('module inventory capacity')
    raw = path.read_bytes()
    tree = ast.parse(raw, filename=str(path))
    module = {'functions': {node.name: node for node in tree.body
                           if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))},
              'imports': import_names(tree.body), 'sha256': hashlib.sha256(raw).hexdigest()}
    modules[name] = module
    return module


def parts(node):
    result = []
    for _step in range(8):
        if isinstance(node, ast.Name):
            return [node.id, *reversed(result)]
        if not isinstance(node, ast.Attribute):
            return None
        result.append(node.attr)
        node = node.value
    return None


def resolve(module_name, reference, imports, modules):
    if not reference:
        return None
    current = load_module(module_name, modules)
    if len(reference) == 1 and reference[0] in current['functions']:
        return module_name, reference[0]
    bound = imports.get(reference[0])
    if bound is None:
        return None
    path = bound + reference[1:]
    for _step in range(8):
        if len(path) < 2:
            return None
        current = load_module(path[0], modules)
        if current is None:
            return None
        if len(path) == 2 and path[1] in current['functions']:
            return path[0], path[1]
        bound = current['imports'].get(path[1])
        if bound is None:
            return None
        path = bound + path[2:]
    return None


def inspect_function(module_name, name, modules):
    module = load_module(module_name, modules)
    node = module['functions'][name]
    nodes = list(ast.walk(node))
    imports = {**module['imports'], **import_names(nodes)}
    edges, frontier, owner = set(), [], set()
    for item in nodes:
        if isinstance(item, ast.Subscript) and ast.unparse(item.value) in ('owner', 'self.owner'):
            owner.add(item.slice.value if isinstance(item.slice, ast.Constant)
                      and isinstance(item.slice.value, str) else '<dynamic key>')
        if isinstance(item, ast.Call):
            target = resolve(module_name, parts(item.func), imports, modules)
            if target is not None:
                edges.add(target)
            else:
                frontier.append({'line': item.lineno, 'call': ast.unparse(item.func)})
    return {'module': module_name, 'function': name, 'line': node.lineno,
            'end_line': node.end_lineno, 'direct_owner_subscripts': sorted(owner),
            'static_edges': sorted([list(edge) for edge in edges]),
            'unresolved_or_external_calls': frontier}, edges


def main():
    if OUT.exists():
        raise FileExistsError('preserve source inventory')
    modules, reached = {}, {}
    pending = [('siasourcebatch', '_validate_batch_image'),
               ('siasourcecheckpoint', '_validate_capture_image')]
    while pending:
        if len(reached) >= MAX_NODES or len(pending) > MAX_NODES:
            raise ValueError('call graph inventory capacity')
        key = pending.pop()
        if key in reached:
            continue
        row, edges = inspect_function(*key, modules)
        reached[key] = row
        pending.extend(sorted(edges - reached.keys()))
    report = {'status': 'SOURCE_INVENTORY_WITH_EXPLICIT_FRONTIERS_NOT_PROOF',
              'roots': ['siasourcebatch._validate_batch_image', 'siasourcecheckpoint._validate_capture_image'],
              'limitations': ['Top-level static calls only; method dispatch, local nested functions, owner callbacks and native dependencies remain explicit frontiers.',
                             'Static overapproximation includes imports inside nested scopes. It is not a complete semantic dependency proof.',
                             'No callback globals, closures or runtime policy values are treated as immutable.'],
              'source_sha256': {name + '.py': value['sha256'] for name, value in sorted(modules.items())},
              'functions': [reached[key] for key in sorted(reached)]}
    OUT.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'modules_read': len(modules), 'functions_reached': len(reached),
                      'status': report['status']}))


if __name__ == '__main__':
    main()
