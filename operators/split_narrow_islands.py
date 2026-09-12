"""Find thin appendages in UV islands or seam-delimited mesh patches."""
import bpy
import bmesh
from mathutils import Vector

from ..core.narrow_regions import components, find_narrow_regions
from ..core.smart_seam_routing import route_seams


def uv_continuous(edge, layer):
    a, b = edge.link_faces
    for vertex in edge.verts:
        ua = next(loop[layer].uv for loop in a.loops if loop.vert == vertex)
        ub = next(loop[layer].uv for loop in b.loops if loop.vert == vertex)
        if (ua - ub).length_squared > 1e-12:
            return False
    return True


def island_graph(bm, source='UV'):
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.index_update()
    bm.edges.index_update()
    layer = bm.loops.layers.uv.active
    if source == 'UV' and layer is None:
        raise ValueError('Active UV map required; choose Mesh / Seams for an unwrapped mesh')
    faces = {face.index: face for face in bm.faces if not face.hide}
    graph = {index: set() for index in faces}
    boundary = set()
    edges = {}
    for edge in bm.edges:
        linked = [face.index for face in edge.link_faces if face.index in faces]
        connected = (len(linked) == 2 and edge.is_manifold and not edge.seam
                     and (source != 'UV' or uv_continuous(edge, layer)))
        if connected:
            a, b = linked
            graph[a].add(b)
            graph[b].add(a)
            edges.setdefault(frozenset((a, b)), set()).add(edge.index)
        else:
            boundary.update(linked)
    return graph, boundary, edges


def plan_cuts(bm, source='UV', width=3, min_faces=8, min_length=3,
              selected_only=False, uv_selection=False):
    graph, boundary, edges = island_graph(bm, source)
    faces = {index: bm.faces[index] for index in graph}
    layer = bm.loops.layers.uv.active
    islands = components(graph, graph)
    if selected_only:
        selected = {index for index, face in faces.items()
                    if (face.select or (not uv_selection and any(edge.select for edge in face.edges))) and (not uv_selection or
                       any(loop.uv_select_vert if hasattr(loop, 'uv_select_vert')
                           else loop[layer].select for loop in face.loops))}
        included = set().union(*(part for part in islands if part & selected))
        graph = {node: neighbors for node, neighbors in graph.items() if node in included}
        boundary &= included
    regions = find_narrow_regions(graph, boundary, width, min_faces, min_length)
    cuts = set()
    for _, attachments in regions:
        for pair in attachments:
            cuts.update(edges[frozenset(pair)])
    return cuts, regions, graph, edges


def refine_cuts(bm, cuts, graph, source='UV', create_edges=False):
    """Return a disposable optimized mesh; the input mesh is never modified.

    Keep original island boundaries as routing barriers, including UV-only
    boundaries. Temporary selection and seam markers never escape this stage.
    Validate that shortening still creates the same number of separate parts.
    """
    work = bm.copy()
    try:
        work.faces.ensure_lookup_table()
        work.edges.ensure_lookup_table()
        old_seams = {edge for edge in work.edges if edge.seam}
        selected_edges = {edge for edge in work.edges if edge.select}
        selected_verts = {vert for vert in work.verts if vert.select}
        selection = work.faces.layers.int.new('_narrow_saved_selection')
        island_tag = work.faces.layers.int.new('_narrow_original_island')
        for face in work.faces:
            face[selection] = int(face.select)
            face[island_tag] = 0
        islands = components(graph, graph)
        for label, island in enumerate(islands, 1):
            for index in island:
                work.faces[index][island_tag] = label
        full_graph, _, pair_edges = island_graph(work, source)
        internal = set().union(*pair_edges.values()) if pair_edges else set()
        barriers = {edge for edge in work.edges if edge.index not in internal}
        for edge in barriers:
            edge.seam = True
        for index in cuts:
            work.edges[index].seam = True
        touched = {face[island_tag] for index in cuts for face in work.edges[index].link_faces}
        layer = work.loops.layers.uv.active
        def uv_co(vertex):
            for face in vertex.link_faces:
                if face.select:
                    loop = next(loop for loop in face.loops if loop.vert == vertex)
                    uv = loop[layer].uv
                    return Vector((uv.x, uv.y, 0.0))
            return vertex.co
        rerouted = created = 0
        for label, island in enumerate(islands, 1):
            if label not in touched:
                continue
            for face in work.faces:
                face.select = face[island_tag] == label
            work.normal_update()
            routed, added = route_seams(
                work, 0.785, create_edges=create_edges, turn_weight=0.6,
                corridor_width=3.0, edge_preference=0.02, protected=old_seams | barriers,
                coordinates=uv_co if source == 'UV' else None,
                ridge_weight=0.0, deviation_weight=0.05, require_shorter=True,
            )
            rerouted += routed
            created += added
        new_seams = {edge for edge in work.edges if edge.seam} - old_seams - barriers
        for edge in work.edges:
            edge.seam = edge in old_seams
            edge.select = edge in selected_edges
        for vert in work.verts:
            vert.select = vert in selected_verts
        for face in work.faces:
            face.select = bool(face[selection])
        work.edges.index_update()
        work.edges.ensure_lookup_table()
        refined = {edge.index for edge in new_seams}
        new_graph, _, new_pairs = island_graph(work, source)
        def split_graph(adjacency, pairs, cut):
            return {a: {b for b in neighbors if not pairs[frozenset((a, b))] & cut}
                    for a, neighbors in adjacency.items()}
        before = split_graph(full_graph, pair_edges, cuts)
        after = split_graph(new_graph, new_pairs, refined)
        for label, island in enumerate(islands, 1):
            old_parts = components(island, before)
            new_faces = {face.index for face in work.faces if face[island_tag] == label}
            new_parts = components(new_faces, after)
            if len(old_parts) != len(new_parts) or min(map(len, new_parts)) < min(2, min(map(len, old_parts))):
                raise ValueError(f'Shortened cut did not preserve island separation ({list(map(len, old_parts))} -> {list(map(len, new_parts))})')
        work.faces.layers.int.remove(island_tag)
        work.faces.layers.int.remove(selection)
        return work, refined, new_graph, new_pairs, rerouted, created
    except Exception:
        work.free()
        raise


def separate_uv(bm, graph, edges, cuts):
    """Move detached pieces beside the existing layout without changing shape."""
    layer = bm.loops.layers.uv.active
    all_uvs = [loop[layer].uv.copy() for face in bm.faces for loop in face.loops]
    if not all_uvs:
        return 0
    xmin = min(uv.x for uv in all_uvs)
    xmax = max(uv.x for uv in all_uvs)
    ymin = min(uv.y for uv in all_uvs)
    ymax = max(uv.y for uv in all_uvs)
    gap = max(xmax - xmin, ymax - ymin, 1e-3) * 0.02
    cursor = xmax + gap
    split_graph = {node: {other for other in neighbors
                         if not (edges[frozenset((node, other))] & cuts)}
                   for node, neighbors in graph.items()}
    moved = 0
    for island in components(graph, graph):
        parts = sorted(components(island, split_graph), key=lambda part: (-len(part), min(part)))
        for part in parts[1:]:
            loops = [loop for index in part for loop in bm.faces[index].loops]
            left = min(loop[layer].uv.x for loop in loops)
            right = max(loop[layer].uv.x for loop in loops)
            for loop in loops:
                loop[layer].uv.x += cursor - left
            cursor += right - left + gap
            moved += 1
    return moved


class MESH_OT_polygroups_split_narrow_islands(bpy.types.Operator):
    bl_idname = 'mesh.polygroups_split_narrow_islands'
    bl_label = 'Split Narrow Island Parts'
    bl_description = 'Detect thin branches and bridges using face rows inside UV or seam islands'
    bl_options = {'REGISTER', 'UNDO'}

    source: bpy.props.EnumProperty(name='Analyze', items=[
        ('UV', 'UV Islands', 'Respect UV discontinuities and seams'),
        ('MESH', 'Mesh / Seams', 'Use mesh boundaries and existing seams; UV map not required')])
    action: bpy.props.EnumProperty(name='Action', items=[
        ('PREVIEW', 'Preview Cuts', 'Select candidate edges without changing seams or UV coordinates'),
        ('SEAMS', 'Mark Seams', 'Mark optimized cuts; Create New Edges allows diagonal face splits'),
        ('SPLIT', 'Split UV Islands', 'Mark seams and move detached UV pieces beside the layout; pack afterwards')])
    width: bpy.props.IntProperty(name='Thin Width (face rows)', default=3, min=1, max=12)
    min_faces: bpy.props.IntProperty(name='Minimum Part Faces', default=8, min=2, max=10000)
    min_length: bpy.props.IntProperty(name='Minimum Branch Depth', default=3, min=1, max=100,
        description='Distance in face steps from the attachment; for a bridge measured from its nearest end')
    selected_only: bpy.props.BoolProperty(name='Selected Islands Only', default=False,
        description='Analyze complete islands touched by selected faces; selection does not create artificial boundaries')
    create_edges: bpy.props.BoolProperty(name='Create New Edges', default=False,
        description='Allow diagonal cuts through convex polygons and across adjacent triangles; preview does not modify topology')

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and context.active_object.type == 'MESH'
                and context.mode in {'OBJECT', 'EDIT_MESH'})

    def invoke(self, context, event):
        if not context.active_object.data.uv_layers:
            self.source = 'MESH'
        return context.window_manager.invoke_props_dialog(self, width=390)

    def draw(self, context):
        for name in ('source', 'action', 'width', 'min_faces', 'min_length', 'selected_only', 'create_edges'):
            self.layout.prop(self, name)
        self.layout.label(text='Width is approximate; preview before splitting.', icon='INFO')
        if self.action == 'SPLIT':
            self.layout.label(text='Detached pieces move outside the layout. Pack afterwards.')

    def execute(self, context):
        obj = context.active_object
        edit = obj.mode == 'EDIT'
        if edit and len(context.objects_in_mode) > 1:
            self.report({'ERROR'}, 'Use a single active mesh')
            return {'CANCELLED'}
        if obj.data.users > 1:
            self.report({'ERROR'}, 'Make the mesh single-user before editing its islands')
            return {'CANCELLED'}
        if self.action == 'SPLIT' and self.source != 'UV':
            self.report({'ERROR'}, 'Choose UV Islands for UV splitting; Mesh / Seams supports seam marking')
            return {'CANCELLED'}
        from .narrow_cut_preview import clear_preview, show_preview
        clear_preview()
        live = bmesh.from_edit_mesh(obj.data) if edit else None
        bm = live.copy() if edit else bmesh.new()
        if not edit:
            bm.from_mesh(obj.data)
        try:
            cuts, regions, graph, edges = plan_cuts(
                bm, self.source, self.width, self.min_faces, self.min_length,
                self.selected_only, self.source == 'UV' and edit
                and context.area is not None and context.area.type == 'IMAGE_EDITOR'
                and not context.tool_settings.use_uv_select_sync)
            if not cuts:
                self.report({'INFO'}, 'No narrow parts found; increase width or lower minimum size/depth')
                return {'FINISHED'}
            raw_cuts = set(cuts)
            rerouted = created = 0
            try:
                optimized, optimized_cuts, optimized_graph, optimized_pairs, rerouted, created = refine_cuts(
                    bm, cuts, graph, self.source, self.create_edges,
                )
            except (ValueError, RuntimeError) as error:
                self.report({'WARNING'}, f'Using original cuts: {error}')
            else:
                bm.free()
                bm, cuts, graph, edges = optimized, optimized_cuts, optimized_graph, optimized_pairs
            if self.action == 'PREVIEW':
                if not edit:
                    bpy.ops.object.mode_set(mode='EDIT')
                    live = bmesh.from_edit_mesh(obj.data)
                live.edges.ensure_lookup_table()
                for face in live.faces:
                    face.select_set(False)
                for edge in live.edges:
                    edge.select_set(False)
                for vertex in live.verts:
                    vertex.select_set(False)
                # New diagonals exist only in the disposable mesh until Apply.
                for index in raw_cuts if created else cuts:
                    live.edges[index].select_set(True)
                # UV sync exposes candidate mesh edges in both editors.
                if context.area and context.area.type == 'IMAGE_EDITOR':
                    context.tool_settings.use_uv_select_sync = True
                context.tool_settings.mesh_select_mode = (False, True, False)
                live.select_mode = {'EDGE'}
                live.select_flush_mode()
                bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
                show_preview(obj, bm, cuts)
            else:
                for index in cuts:
                    bm.edges[index].seam = True
                if self.action == 'SPLIT':
                    separate_uv(bm, graph, edges, cuts)
                if edit and not created:
                    live.edges.ensure_lookup_table()
                    for edge in bm.edges:
                        live.edges[edge.index].seam = edge.seam
                    uv = bm.loops.layers.uv.active
                    live_uv = live.loops.layers.uv.active
                    if self.action == 'SPLIT':
                        for face, original in zip(bm.faces, live.faces):
                            for loop, target in zip(face.loops, original.loops):
                                target[live_uv].uv = loop[uv].uv
                    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
                else:
                    # BMesh.to_mesh requires Object Mode when topology changes.
                    if edit:
                        bpy.ops.object.mode_set(mode='OBJECT')
                    try:
                        bm.to_mesh(obj.data)
                        obj.data.update()
                    finally:
                        if edit:
                            bpy.ops.object.mode_set(mode='EDIT')
            verb = 'proposed' if self.action == 'PREVIEW' else 'created'
            self.report({'INFO'}, f'{len(regions)} narrow parts, {len(cuts)} cut edges; {rerouted} paths improved, {created} new edges {verb}')
        except ValueError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        finally:
            bm.free()
        return {'FINISHED'}


class IMAGE_PT_polygroups_narrow_islands(bpy.types.Panel):
    bl_label = 'Narrow Island Splitter'
    bl_idname = 'IMAGE_PT_polygroups_narrow_islands'
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'AI Retopo'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        self.layout.operator('mesh.polygroups_split_narrow_islands', icon='UV_EDGESEL')
