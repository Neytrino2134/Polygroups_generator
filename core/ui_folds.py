"""Progressive fold commands derived from the shared, fully captured UI tree."""
from dataclasses import dataclass, field


def fold_key(event):
    if event.value != 'PRESS' or event.ctrl or event.alt or event.oskey:
        return None
    if event.type == 'EQUAL' and event.shift:
        return True
    if not event.shift and event.type in {'NUMPAD_PLUS', 'NUMPAD_MINUS', 'MINUS'}:
        return event.type == 'NUMPAD_PLUS'
    return None


@dataclass
class Fold:
    owner: object
    name: str
    bit: int = 0
    children: list = field(default_factory=list)

    def opened(self):
        value = getattr(self.owner, self.name)
        return bool(value & self.bit) if self.bit else bool(value)

    def set(self, opened):
        if self.bit:
            value = getattr(self.owner, self.name)
            value = value | self.bit if opened else value & ~self.bit
        else:
            value = opened
        setattr(self.owner, self.name, value)

    def close_children(self):
        for child in self.children:
            child.set(False)
            child.close_children()


def model_folds(model, context=None):
    roots = []

    def visit(node, parent):
        children = parent.children if parent else roots
        binding = model.bindings.get(node['id'])
        if node['kind'] == 'group' and binding and binding[0] == 'property':
            fold = Fold(binding[1], binding[2])
            children.append(fold)
            parent = fold
        elif binding and binding[0] == 'operator' and binding[1] == 'object.polygroups_toggle_batch_stage':
            # Import and Batch Import share stage folds stored as bits.
            stage = binding[2].stage
            if context is None:
                from bpy import context as active_context
                settings = active_context.scene.polygroups_model_preparation_settings
            else:
                settings = context.scene.polygroups_model_preparation_settings
            children.append(Fold(settings, 'batch_expanded_stages', 1 << (stage-1)))
        for child in node.get('children', ()):
            visit(child, parent)

    visit(model.node, None)
    return roots


def section_folds(context, section=None, include_sections=True):
    from ..custom_ui.schema import capture
    from ..properties import SECTION_VISIBILITY_PROPERTIES
    visibility = context.scene.airetopo_panel_visibility_settings
    roots = []
    indices = range(13) if section is None else (section,)
    for index in indices:
        model = capture(context, index)
        if model.errors:
            raise RuntimeError('Cannot discover section folds: ' + '; '.join(map(str, model.errors)))
        groups = model_folds(model, context)
        if include_sections:
            roots.append(Fold(visibility, SECTION_VISIBILITY_PROPERTIES[index], children=groups))
        else:
            roots.extend(groups)
    return roots


def step_folds(roots, opened):
    """Change one visible depth. Closed ancestors never consume a '-' click."""
    candidates = []

    def visit(fold, depth):
        state = fold.opened()
        if state != opened:
            candidates.append((depth, fold))
        if state:
            for child in fold.children:
                visit(child, depth+1)

    for root in roots:
        visit(root, 1)
    if not candidates:
        return None
    depth = (min if opened else max)(level for level, _ in candidates)
    for level, fold in candidates:
        if level == depth:
            # Normalize latent child states so opening never skips a floor.
            fold.close_children()
            fold.set(opened)
    return depth
