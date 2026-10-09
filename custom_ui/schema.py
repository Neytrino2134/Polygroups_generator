"""Capture the existing Blender layouts as a tree, on Blender's main thread.

Unlike the detached-window protocol, this tree retains rows, columns, groups,
icons and native property editors. Bindings never leave the Blender process.
"""
from types import SimpleNamespace
import ast
from pathlib import Path
import bpy
from ..core.window_schema import plain


def _fold_names():
    source = Path(__file__).resolve().parents[1] / 'ui.py'
    names = set()
    for node in ast.walk(ast.parse(source.read_text(encoding='utf8'))):
        if (isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
                and node.func.attr=='prop' and len(node.args)>1
                and isinstance(node.args[1],ast.Constant) and isinstance(node.args[1].value,str)
                and any(k.arg=='icon' and 'TRIA_' in ast.unparse(k.value) for k in node.keywords)):
            names.add(node.args[1].value)
    return names


FOLD_NAMES = _fold_names()


class RNAProxy:
    """Read folded descendants without modifying any scene property."""
    def __init__(self, rna):
        self._rna = rna

    def __getattr__(self, name):
        value = getattr(self._rna,name)
        if name in FOLD_NAMES and isinstance(value,bool):
            return True
        return value


class SceneProxy(RNAProxy):
    def __getattr__(self,name):
        value = getattr(self._rna,name)
        return RNAProxy(value) if isinstance(value,bpy.types.PropertyGroup) else value


class ContextProxy:
    def __init__(self,context):
        self._context = context
        self.scene = SceneProxy(context.scene)

    def __getattr__(self,name):
        return getattr(self._context,name)


class Layout:
    def __init__(self, parent=None, kind='column', key='section', **options):
        self.parent = parent
        self.root = parent.root if parent else self
        self.enabled = True
        self.active = True
        self.operator_context = parent.operator_context if parent else 'INVOKE_DEFAULT'
        self.node = dict(kind=kind, id=key, children=[], **options)
        if parent:
            parent.node['children'].append(self.node)
        else:
            self.bindings = {}
            self.counts = {}
            self.errors = []

    def usable(self):
        return self.enabled and self.active and (not self.parent or self.parent.usable())

    def child(self, kind, **kwargs):
        return Layout(self, kind, self.node['id'] + '/' + kind, **kwargs)

    def row(self, **kwargs):
        return self.child('row', **kwargs)

    def column(self, **kwargs):
        return self.child('column', **kwargs)

    def box(self):
        return self.child('box')

    def split(self, **kwargs):
        return self.child('row', **kwargs)

    def add(self, kind, semantic='', **kwargs):
        base = self.node['id'] + '/' + (semantic or kind)
        count = self.root.counts.get(base, 0)
        self.root.counts[base] = count + 1
        key = base + ':' + str(count)
        node = dict(kind=kind, id=key, enabled=bool(self.usable()), **kwargs)
        self.node['children'].append(node)
        return node

    def separator(self, **kwargs):
        self.add('separator')

    separator_spacer = separator

    def label(self, text='', **kwargs):
        self.add('label', text, text=text, **kwargs)

    def progress(self, factor=0, text='', **kwargs):
        self.add('progress', text, value=factor, text=text)

    def operator(self, identifier, text=None, **kwargs):
        params = SimpleNamespace()
        try:
            category, name = identifier.split('.')
            op = getattr(getattr(bpy.ops, category), name)
            rna = op.get_rna_type()
            label = rna.name if text is None else text
            enabled = bool(op.poll()) and self.usable()
            description = rna.description
        except Exception:
            label, enabled, description = text or identifier, False, ''
        node = self.add('button', identifier, text=label, description=description, **kwargs)
        node['enabled'] = bool(enabled)
        self.root.bindings[node['id']] = ('operator', identifier, params, self.operator_context)
        return params

    def prop(self, data, name, text=None, index=-1, **kwargs):
        data = getattr(data,'_rna',data)
        rna = data.bl_rna.properties[name]
        value = getattr(data, name)
        if index >= 0:
            value = value[index]
        secret = (rna.type == 'STRING' and rna.subtype == 'PASSWORD') or 'api_key' in name
        if rna.type == 'POINTER':
            value = getattr(value, 'name', '') if value else ''
        elif secret:
            value = '••••••' if value else ''
        else:
            value = plain(value)
        try:
            owner = data.path_from_id()
        except Exception:
            owner = type(data).__name__
        if rna.type=='BOOLEAN' and str(kwargs.get('icon','')).startswith('TRIA_'):
            container = self
            while container.parent and container.node['kind'] not in {'box','group'}:
                container = container.parent
            if container.node['kind']=='box':
                key = owner+'.'+name
                container.node.update(kind='group',id=key,text=text or rna.name,
                                      icon=kwargs['icon'],opened=bool(value),enabled=self.usable())
                self.root.bindings[key] = ('property',data,name,index)
                return
        node = self.add('property', owner + '.' + name, text=rna.name if text is None else text,
                        value=value, type=rna.type,
                        subtype=rna.subtype if rna.type == 'STRING' or getattr(rna, 'is_array', False) else '',
                        unit=getattr(rna, 'unit', ''),
                        description=rna.description, readonly=rna.is_readonly,
                        index=index, owner=owner, property=name, secret=secret, **kwargs)
        node['enabled'] = self.usable() and not rna.is_readonly
        if rna.type in {'FLOAT', 'INT'} and not rna.is_array:
            node.update(min=rna.hard_min, max=rna.hard_max,
                        soft_min=rna.soft_min, soft_max=rna.soft_max)
        if rna.type == 'ENUM':
            options = [(item.identifier, item.name, item.description) for item in rna.enum_items if item.identifier]
            if not options:
                deferred = getattr(type(data), '__annotations__', {}).get(name)
                callback = getattr(deferred, 'keywords', {}).get('items')
                if callable(callback):
                    options = [(entry[0], entry[1], entry[2]) for entry in callback(data, bpy.context) if entry and entry[0]]
            node.update(options=options, enum_flag=rna.is_enum_flag)
        node['array'] = bool(getattr(rna, 'is_array', False))
        self.root.bindings[node['id']] = ('property', data, name, index)

    def prop_search(self, data, name, search_data, search_property, **kwargs):
        data = getattr(data,'_rna',data)
        search_data = getattr(search_data,'_rna',search_data)
        self.prop(data, name, **kwargs)
        node = self.node['children'][-1]
        self.root.bindings[node['id']] = ('search', data, name, (search_data, search_property))

    def grouped(self, settings, name, label, icon):
        settings = getattr(settings,'_rna',settings)
        key = settings.path_from_id() + '.' + name
        group = Layout(self, 'group', key, text=label, icon=icon,
                       enabled=self.usable(), opened=bool(getattr(settings, name)))
        group.root.bindings[key] = ('property', settings, name, -1)
        # Capture closed branches too; visibility is applied by the renderer.
        return group

    def template_list(self, listtype, list_id, data, property_name, active_data, active_property, **kwargs):
        data, active_data = getattr(data,'_rna',data),getattr(active_data,'_rna',active_data)
        entries = getattr(data, property_name)
        index = getattr(active_data, active_property)
        name = getattr(entries[index], 'name', '') if 0 <= index < len(entries) else 'None selected'
        node = self.add('list', property_name, text=name or property_name,
                        count=len(entries), property=property_name, value=index)
        self.root.bindings[node['id']] = ('list', (listtype, list_id, data, property_name, active_data, active_property), kwargs, None)


def walk(node):
    yield node
    for child in node.get('children', ()):
        yield from walk(child)


def capture(context, section):
    from .. import ui
    panel = ui.SECTION_PANEL_CLASSES[section]
    layout = Layout(key=panel.__name__)
    previous = ui._CUSTOM_CAPTURING
    ui._CUSTOM_CAPTURING = True
    try:
        ui.draw_section_panel_content(panel, ContextProxy(context), layout, panel.visibility_property)
    finally:
        ui._CUSTOM_CAPTURING = previous
    return layout
