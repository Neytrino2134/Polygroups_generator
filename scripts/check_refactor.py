"""Compare moved definitions with a Git baseline and inventory all Python code."""
import ast
import copy
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = sys.argv[1] if len(sys.argv) > 1 else '140a104'


def normalized(node):
    node = copy.deepcopy(node)
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

checked = 0
for original, targets in [
    ('properties.py', [ROOT / 'properties.py', *sorted((ROOT / 'settings').glob('*.py'))]),
    ('operators/object_seam_cutter.py', [ROOT / 'operators/object_seam_cutter.py', ROOT / 'operators/cutter_screen.py', ROOT / 'operators/cutter_overlay.py']),
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
            assert normalized(node) == normalized(definitions[node.name]), f'Changed: {node.name}'
            checked += 1
    # Preserve ordered registration and literal constants as well as definitions.
    if original == 'properties.py':
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
                        assert normalized(node) == normalized(new_assignments[target.id]), target.id

report = {'baseline': BASE, 'python_files': len(files),
          'total_lines': sum(row['lines'] for row in inventory),
          'unchanged_definitions': checked,
          'inventory': sorted(inventory, key=lambda row: (-row['lines'], row['file']))}
(ROOT / 'docs/refactor_inventory.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(f'Syntax OK: {len(files)} files; unchanged definitions: {checked}; constants/registration OK')
