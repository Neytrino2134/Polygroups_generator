"""Compare moved definitions with a Git baseline and inventory all Python code."""
import ast
import builtins
import copy
import json
from pathlib import Path
import subprocess
import symtable
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = sys.argv[1] if len(sys.argv) > 1 else '140a104'
STATE_FIELDS = {
    'drawing_section': '_DRAWING_SECTION', 'detached_target': '_DETACHED_TARGET',
    'detached_layout': '_DETACHED_LAYOUT', 'group_discovery': '_GROUP_DISCOVERY',
    'search_probing': '_SEARCH_PROBING', 'search_filter_groups': '_SEARCH_FILTER_GROUPS',
    'search_filter_terms': '_SEARCH_FILTER_TERMS', 'custom_capturing': '_CUSTOM_CAPTURING',
    'custom_header_only': '_CUSTOM_HEADER_ONLY', 'section_panel_classes': 'SECTION_PANEL_CLASSES',
}


class NormalizeDrawState(ast.NodeTransformer):
    """Permit only the documented global-name to state-field substitution."""

    def visit_Attribute(self, node):
        node = self.generic_visit(node)
        if isinstance(node.value, ast.Name) and node.value.id == 'state' and node.attr in STATE_FIELDS:
            return ast.Name(id=STATE_FIELDS[node.attr], ctx=node.ctx)
        return node

    def visit_Global(self, node):
        names = [name for name in node.names if name not in STATE_FIELDS.values()]
        return ast.Global(names=names) if names else None


def normalized(node):
    node = copy.deepcopy(node)
    node = NormalizeDrawState().visit(node)
    # Settings gained a package level; this is the only permitted AST change.
    for child in ast.walk(node):
        if isinstance(child, ast.ImportFrom) and child.level:
            child.level = 1
    return ast.dump(node)


files = sorted(p for p in ROOT.rglob('*.py') if '.git' not in p.parts)
inventory = []
for path in files:
    text = path.read_text(encoding='utf-8-sig')
    tree = ast.parse(text, filename=str(path))
    inventory.append({'file': path.relative_to(ROOT).as_posix(),
                      'lines': len(text.splitlines()),
                      'definitions': sum(isinstance(n, (ast.FunctionDef, ast.ClassDef)) for n in tree.body)})

# A matching body alone cannot catch a dependency omitted from the new module.
dependency_files = [*sorted((ROOT / 'settings').glob('*.py')),
                    *sorted((ROOT / 'ui_panels').glob('*.py')),
                    *sorted((ROOT / 'operators').glob('queue_*.py')),
                    *sorted((ROOT / 'operators').glob('bake_*.py')),
                    *sorted((ROOT / 'operators').glob('cutter_*.py'))]
for path in dependency_files:
    table = symtable.symtable(path.read_text(encoding='utf-8-sig'), str(path), 'exec')
    declared = {symbol.get_name() for symbol in table.get_symbols()
                if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()}
    allowed = declared | set(dir(builtins)) | {'__file__', '__name__', '__package__', '__class__'}

    def check_globals(scope):
        missing = {symbol.get_name() for symbol in scope.get_symbols()
                   if symbol.is_global() and symbol.is_referenced()} - allowed
        assert not missing, f'Unbound globals in {path.name}/{scope.get_name()}: {sorted(missing)}'
        for child in scope.get_children():
            check_globals(child)

    check_globals(table)

checked = 0
for original, targets in [
    ('properties.py', [ROOT / 'properties.py', *sorted((ROOT / 'settings').glob('*.py'))]),
    ('operators/object_seam_cutter.py', [ROOT / 'operators' / name for name in [
        'object_seam_cutter.py', 'cutter_screen.py', 'cutter_overlay.py',
        'cutter_constants.py', 'cutter_paths.py', 'cutter_objects.py',
        'cutter_mesh.py', 'cutter_draw.py',
    ]]),
    ('ui.py', [ROOT / 'ui.py', *sorted((ROOT / 'ui_panels').glob('*.py'))]),
    ('operators/baking.py', [ROOT / 'operators/baking.py', *sorted((ROOT / 'operators').glob('bake_*.py'))]),
    ('operators/import_queue.py', [ROOT / 'operators/import_queue.py', *sorted((ROOT / 'operators').glob('queue_*.py'))]),
]:
    baseline = subprocess.check_output(['git', 'show', f'{BASE}:{original}'], cwd=ROOT).decode('utf-8-sig')
    old_tree = ast.parse(baseline)
    definitions = {}
    for path in targets:
        if path.exists():
            for node in ast.parse(path.read_text(encoding='utf-8-sig')).body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    assert node.name not in definitions, f'Duplicate definition: {node.name}'
                    definitions[node.name] = node
    for node in old_tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            assert node.name in definitions, f'Missing: {node.name}'
            current = definitions[node.name]
            if original == 'operators/import_queue.py' and node.name == 'ImportQueue':
                current = copy.deepcopy(current)
                mixins = ['QueueProcessingMixin', 'QueueRedoMixin']
                assert [base.id for base in current.bases] == mixins
                methods = {}
                for part in [current, *(definitions[name] for name in mixins)]:
                    for method in part.body:
                        if isinstance(method, ast.FunctionDef):
                            assert method.name not in methods, f'Duplicate method: {method.name}'
                            methods[method.name] = method
                        else:
                            assert isinstance(method, ast.Expr) and isinstance(method.value, ast.Constant) and isinstance(method.value.value, str)
                assert set(methods) == {method.name for method in node.body if isinstance(method, ast.FunctionDef)}
                current.bases = node.bases
                current.body = [methods[method.name] if isinstance(method, ast.FunctionDef) else method for method in node.body]
            assert normalized(node) == normalized(current), f'Changed: {node.name}'
            checked += 1
    # Preserve ordered registration and literal constants as well as definitions.
    if original in {'properties.py', 'ui.py', 'operators/baking.py', 'operators/import_queue.py', 'operators/object_seam_cutter.py'}:
        new_assignments = {}
        for path in targets:
            if path.exists():
                for node in ast.parse(path.read_text(encoding='utf-8-sig')).body:
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                new_assignments[target.id] = node
        for node in old_tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if target.id in set(STATE_FIELDS.values()) - {'SECTION_PANEL_CLASSES'}:
                            continue
                        assert normalized(node) == normalized(new_assignments[target.id]), target.id

report = {'baseline': BASE, 'python_files': len(files),
          'total_lines': sum(row['lines'] for row in inventory),
          'unchanged_definitions': checked,
          'inventory': sorted(inventory, key=lambda row: (-row['lines'], row['file']))}
(ROOT / 'docs/refactor_inventory.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(f'Syntax OK: {len(files)} files; equivalent definitions: {checked}; constants/registration OK')
