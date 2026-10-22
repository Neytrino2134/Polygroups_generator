"""Static call-site coverage complements conditional live Blender snapshots."""
import ast
from pathlib import Path


def collect(root):
    records = []
    paths = [root/'ui.py',root/'preferences.py',root/'hotkeys.py',root/'pie_presets.py',root/'core/render_palettes.py']
    paths.extend(sorted((root / 'ui_panels').glob('*.py')))
    for path in paths:
        source = path.read_text(encoding='utf-8-sig')
        tree = ast.parse(source)
        def visit(node, scope='', conditions=()):
            if isinstance(node,(ast.FunctionDef,ast.ClassDef)):
                scope = scope+'.'+node.name if scope else node.name
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in {
                    'prop','prop_search','operator','label','progress','template_list','menu_contents'}:
                records.append(dict(file=path.relative_to(root).as_posix(),line=node.lineno,
                    scope=scope,kind=node.func.attr,call=ast.get_source_segment(source,node),
                    conditions=list(conditions)))
            if isinstance(node,ast.If):
                expression = ast.unparse(node.test)
                for child in node.body:
                    visit(child,scope,conditions+(expression,))
                for child in node.orelse:
                    visit(child,scope,conditions+('not ('+expression+')',))
            else:
                for child in ast.iter_child_nodes(node):
                    visit(child,scope,conditions)
        visit(tree)
    return records
