"""One world-space origin grid for a batch of differently sized asset packs."""
from mathutils import Vector


class SmartArrangeGrid:
    def __init__(self, context, sources, spacing_y=1.0, gap_x=.1, keep_rows=False):
        # keep_rows: an already arranged scene (ReBake) keeps each source's own
        # row; only the LOD columns follow the grid along X.
        self.keep_rows = keep_rows
        self.sources = list(dict.fromkeys(sources))
        if not self.sources:
            raise ValueError('Smart Arrange needs at least one source')
        context.view_layer.update()
        self.origin = self.sources[0].matrix_world.translation.copy()
        self.rows = {source: index for index, source in enumerate(self.sources)}
        # A common envelope relative to origins also protects off-centre meshes:
        # max(width) alone is insufficient when two assets offset opposite ways.
        depsgraph = context.evaluated_depsgraph_get()
        offsets = []
        for source in self.sources:
            evaluated = source.evaluated_get(depsgraph)
            corners = evaluated.bound_box
            if all(tuple(p) == (-1, -1, -1) for p in corners):
                corners = source.bound_box
            offsets.extend(source.matrix_world @ Vector(corner) - source.matrix_world.translation
                           for corner in corners)
        self.x_step = max(p.x for p in offsets)-min(p.x for p in offsets)+max(0, gap_x)
        self.y_step = max(p.y for p in offsets)-min(p.y for p in offsets)+max(0, spacing_y)

    def place(self, obj, source, column):
        matrix = obj.matrix_world.copy()
        if self.keep_rows:
            # Offset from the source itself, so an unaligned row stays intact.
            matrix.translation.x = source.matrix_world.translation.x + column*self.x_step
            matrix.translation.y = source.matrix_world.translation.y
        else:
            matrix.translation.x = self.origin.x + column*self.x_step
            matrix.translation.y = self.origin.y + self.rows[source]*self.y_step
        obj.matrix_world = matrix

    def arrange_sources(self, context):
        # Assign parents before children; all transforms use the frozen grid.
        def depth(obj):
            level = 0
            while obj.parent:
                obj = obj.parent
                level += 1
            return level
        for source in sorted(self.sources, key=depth):
            self.place(source, source, 0)
        context.view_layer.update()


def scene_lod_sources(context, target):
    """Shared frame for sequential ReBake/ReLOD and Phase 1 calls."""
    import re
    from ..operators.smart_decimate import generated_retopo_targets
    candidates = set(generated_retopo_targets(context.scene))
    families = {}
    for obj in context.scene.objects:
        if obj.type == 'MESH' and re.search(r'_(MID|HIGH)$', obj.name, re.I):
            key = re.sub(r'_(MID|HIGH)$', '', obj.name, flags=re.I).casefold()
            if key not in families or obj.name.upper().endswith('_MID'):
                families[key] = obj
        source = context.scene.objects.get(obj.get('polygroups_lod_source', ''))
        if source is not None and source.type == 'MESH':
            candidates.add(source)
    candidates.update(families.values())
    candidates.add(target)
    return sorted(candidates, key=lambda obj: obj.name.casefold())


def arrange_decimated(context, source, duplicate):
    """Arrange duplicate outputs together; source transforms remain unchanged."""
    from ..operators.smart_decimate import generated_retopo_targets
    settings = context.scene.polygroups_mesh_finalization_settings
    if not settings.smart_decimate_smart_arrange or source == duplicate:
        return
    duplicate['polygroups_decimate_source'] = source.name
    pairs = [(obj, context.scene.objects.get(obj.get('polygroups_decimate_source', '')))
             for obj in context.scene.objects if obj.type == 'MESH']
    pairs = [(obj, owner) for obj, owner in pairs if owner is not None and owner.type == 'MESH']
    sources = set(generated_retopo_targets(context.scene)) | {owner for obj, owner in pairs}
    grid = SmartArrangeGrid(context, sorted(sources, key=lambda obj: obj.name.casefold()), settings.smart_lods_spacing)
    for owner in sources:
        outputs = sorted((obj for obj, src in pairs if src == owner), key=lambda obj: obj.name.casefold())
        for column, obj in enumerate(outputs, 1):
            grid.place(obj, owner, column)
    context.view_layer.update()


def arrange_scene_lods(context, spacing_y):
    """Reflow retained Phase 1 LOD outputs after file groups were translated."""
    packs = {}
    for obj in context.scene.objects:
        if obj.type != 'MESH' or not isinstance(obj.get('polygroups_lod_index'), int):
            continue
        source = context.scene.objects.get(obj.get('polygroups_lod_source', ''))
        if source is not None:
            packs.setdefault(source, []).append(obj)
    if not packs:
        return
    grid = SmartArrangeGrid(context, sorted(packs, key=lambda obj: obj.name.casefold()), spacing_y)
    for source, lods in packs.items():
        for lod in lods:
            grid.place(lod, source, lod['polygroups_lod_index']+1)
    context.view_layer.update()
