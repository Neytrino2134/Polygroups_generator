"""Record existing add-on layouts for the standalone UI. Blender main thread only."""
from types import SimpleNamespace
import bpy


def plain(value):
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    try:
        return list(value)
    except TypeError:
        return str(value)


class Layout:
    def __init__(self, root=None, parent=None):
        self.root = root or self
        self.parent = parent
        self.enabled = True
        self.active = True
        self.operator_context = parent.operator_context if parent else 'INVOKE_DEFAULT'
        if root is None:
            self.items = []
            self.bindings = {}

    def usable(self):
        return self.enabled and self.active and (self.parent is None or self.parent.usable())

    def row(self, **kwargs):
        return Layout(self.root, self)

    column = box = split = row

    def add(self, kind, **data):
        key = str(len(self.root.items))
        item = dict(id=key, kind=kind, enabled=bool(self.usable()), **data)
        self.root.items.append(item)
        return item

    def separator(self, **kwargs):
        self.add('separator')

    separator_spacer = separator

    def label(self, *, text='', **kwargs):
        self.add('label', text=text)

    def progress(self, *, factor=0, text='', **kwargs):
        self.add('progress', value=factor, text=text)

    def operator(self, operator, *, text=None, **kwargs):
        params = SimpleNamespace()
        try:
            category, name = operator.split('.')
            op = getattr(getattr(bpy.ops, category), name)
            rna = op.get_rna_type()
            label = text or rna.name
            enabled = bool(op.poll()) and self.usable()
        except Exception:
            label, enabled = text or operator, False
        item = self.add('button', text=label)
        item['enabled'] = bool(enabled)
        self.root.bindings[item['id']] = ('operator', operator, params, self.operator_context)
        return params

    def prop(self, data, name, *, text=None, index=-1, **kwargs):
        rna = data.bl_rna.properties[name]
        value = getattr(data, name)
        if index >= 0:
            value = value[index]
        options = []
        if rna.type == 'ENUM':
            options = [(item.identifier, item.name) for item in rna.enum_items if item.identifier]
            if not options:
                deferred = getattr(type(data), '__annotations__', {}).get(name)
                callback = getattr(deferred, 'keywords', {}).get('items')
                if callable(callback):
                    options = [(entry[0], entry[1]) for entry in callback(data, bpy.context) if entry and entry[0]]
            if not options and isinstance(value, str) and value:
                options = [(value, value)]
        item = self.add('property', text=text if text is not None else rna.name,
                        value=plain(value), type=rna.type, options=options,
                        enum_flag=bool(getattr(rna, 'is_enum_flag', False)),
                        subtype=getattr(rna, 'subtype', '') if rna.type == 'STRING' or getattr(rna, 'is_array', False) else '',
                        min=getattr(rna, 'hard_min', None), max=getattr(rna, 'hard_max', None))
        item['enabled'] = item['enabled'] and not rna.is_readonly and rna.type not in {'POINTER', 'COLLECTION'}
        self.root.bindings[item['id']] = ('property', data, name, index)

    def prop_search(self, data, name, search_data, search_property, **kwargs):
        self.prop(data, name, **kwargs)
        item = self.root.items[-1]
        item['type'] = 'ENUM'
        item['options'] = [(entry.name, entry.name) for entry in getattr(search_data, search_property)]


def apply(binding, value=None):
    """Only server-generated bindings are actionable; never evaluate client code."""
    kind, target, name, extra = binding
    if kind == 'operator':
        category, operator = target.split('.')
        op = getattr(getattr(bpy.ops, category), operator)
        if not op.poll():
            raise RuntimeError('This tool is unavailable for the current selection or mode')
        result = op(extra, **vars(name))
        if 'CANCELLED' in result:
            raise RuntimeError('Operation cancelled; see Blender for details')
        return
    current = getattr(target, name)
    rna = target.bl_rna.properties[name]
    if rna.type == 'ENUM' and getattr(rna, 'is_enum_flag', False):
        value = set(value)
    if extra >= 0:
        current[extra] = value
    else:
        setattr(target, name, value)
