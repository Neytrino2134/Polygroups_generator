"""Plan seam removal on a region graph, retaining every original large region."""
import heapq

import bpy
import bmesh

PIN_LAYER = "polygroups_pin_edge"


def _pin_layer(bm):
    layers = getattr(bm.edges, "layers", None)
    return layers.int.get(PIN_LAYER) if layers is not None else None


def _is_pinned(edge, layer):
    return bool(layer is not None and edge[layer])


def plan_merge(bm, threshold, protect_sharp=True, protect_materials=False,
               selected_only=False, protect_pinned=True):
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.index_update()
    bm.edges.index_update()
    # Physical components and seam islands are independent partitions.
    included = {face for face in bm.faces if not selected_only or face.select}
    pins = _pin_layer(bm)

    def partition(cross_seams):
        labels = {}
        regions = []
        for face in included:
            if face.index in labels:
                continue
            label = len(regions)
            stack = [face]
            labels[face.index] = label
            region = []
            while stack:
                current = stack.pop()
                region.append(current)
                for edge in current.edges:
                    if not edge.is_manifold or (edge.seam and not cross_seams):
                        continue
                    for neighbor in edge.link_faces:
                        if neighbor in included and neighbor.index not in labels:
                            labels[neighbor.index] = label
                            stack.append(neighbor)
            regions.append(region)
        return labels, regions

    components, _ = partition(True)
    labels, regions = partition(False)
    areas = [sum(face.calc_area() for face in region) for region in regions]
    maxima = {}
    for index, region in enumerate(regions):
        component = components[region[0].index]
        maxima[component] = max(maxima.get(component, 0), areas[index])
    small = {i for i, region in enumerate(regions)
             if areas[i] < maxima[components[region[0].index]] * threshold / 100}
    parent = list(range(len(regions)))
    anchors = [None if i in small else i for i in range(len(regions))]
    adjacency = [dict() for _ in regions]
    for edge in bm.edges:
        if not edge.is_manifold or not edge.seam or any(face not in included for face in edge.link_faces):
            continue
        a, b = (labels[face.index] for face in edge.link_faces)
        if a == b:
            continue
        blocked = (protect_pinned and _is_pinned(edge, pins)) or (protect_sharp and not edge.smooth) or (
            protect_materials and edge.link_faces[0].material_index != edge.link_faces[1].material_index)
        data = adjacency[a].setdefault(b, [0.0, set(), False])
        data[0] += edge.calc_length()
        data[1].add(edge.index)
        data[2] |= blocked
        adjacency[b][a] = data

    versions = [0] * len(regions)
    queue = []
    def enqueue(a, b):
        data = adjacency[a][b]
        if data[2] or (anchors[a] is None) == (anchors[b] is None):
            return
        # Grow anchored regions over their strongest shared border first.
        heapq.heappush(queue, (-data[0], -max(areas[a], areas[b]), a, b, versions[a], versions[b]))
    for a in range(len(regions)):
        for b in adjacency[a]:
            if a < b:
                enqueue(a, b)
    removed = set()
    merged = 0
    while queue:
        _, _, a, b, va, vb = heapq.heappop(queue)
        if parent[a] != a or parent[b] != b or versions[a] != va or versions[b] != vb:
            continue
        if anchors[a] is None:
            a, b = b, a
        removed.update(adjacency[a][b][1])
        merged += 1
        parent[b] = a
        areas[a] += areas[b]
        versions[a] += 1
        adjacency[a].pop(b)
        for neighbor, data in list(adjacency[b].items()):
            if neighbor == a:
                continue
            adjacency[neighbor].pop(b)
            existing = adjacency[a].get(neighbor)
            if existing:
                existing[0] += data[0]
                existing[1].update(data[1])
                existing[2] |= data[2]
            else:
                adjacency[a][neighbor] = data
            adjacency[neighbor][a] = adjacency[a][neighbor]
        adjacency[b].clear()
        for neighbor in adjacency[a]:
            enqueue(a, neighbor)
    return removed, len(regions), len(small), merged


class MESH_OT_polygroups_merge_small_islands(bpy.types.Operator):
    bl_idname = "mesh.polygroups_merge_small_islands"
    bl_label = "Merge Small Seam Islands"
    bl_description = "Analyze seam islands or remove only borders attaching small islands to one large region"
    bl_options = {"REGISTER", "UNDO"}

    preview: bpy.props.BoolProperty(default=True, options={"SKIP_SAVE"})
    threshold_override: bpy.props.FloatProperty(
        default=-1.0, min=-1.0, max=100.0,
        options={"HIDDEN", "SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == "MESH" and context.mode in {'OBJECT', 'EDIT_MESH'}

    def execute(self, context):
        obj = context.active_object
        settings = context.scene.polygroups_generator_settings
        if obj.mode == 'EDIT' and len(context.objects_in_mode) > 1:
            self.report({'ERROR'}, "Use a single active mesh for island cleanup")
            return {'CANCELLED'}
        if obj.mode == 'EDIT':
            obj.update_from_editmode()
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            threshold = (
                self.threshold_override
                if self.threshold_override >= 0.0
                else settings.small_island_threshold
            )
            removed, total, small, merged = plan_merge(
                bm, threshold,
                settings.small_island_protect_sharp, settings.small_island_protect_materials,
                settings.small_island_selected_area and obj.mode == 'EDIT',
                settings.small_island_protect_pinned)
        finally:
            bm.free()
        settings.small_island_status = f"{total} → {total - merged} | Small: {small} | Merged: {merged} | Remaining: {small - merged}"
        if self.preview:
            if obj.mode != 'EDIT':
                bpy.ops.object.mode_set(mode='EDIT')
            context.tool_settings.mesh_select_mode = (False, True, False)
        if obj.mode == 'EDIT':
            live = bmesh.from_edit_mesh(obj.data)
            live.edges.ensure_lookup_table()
            if self.preview:
                for face in live.faces:
                    face.select_set(False)
                for edge in live.edges:
                    edge.select_set(False)
                for vertex in live.verts:
                    vertex.select_set(False)
            for index in removed:
                if self.preview:
                    live.edges[index].select_set(True)
                else:
                    live.edges[index].seam = False
            live.select_flush_mode()
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        elif not self.preview:
            for index in removed:
                obj.data.edges[index].use_seam = False
            obj.data.update()
        self.report({'INFO'}, settings.small_island_status)
        return {'FINISHED'}
