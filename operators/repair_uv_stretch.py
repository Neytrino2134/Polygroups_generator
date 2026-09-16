"""Detect compressed UV patches, isolate them and open a longitudinal cut."""
import math

import bmesh
import bpy

from ..core.narrow_regions import components
from ..core.uv_repair import distortion_scores, find_regions
from ..core.smart_seam_routing import route_seams
from ..pin_edges import pin_layer, set_pinned, is_pinned
from ..localization import t
from .split_narrow_islands import island_graph
from .mark_longitudinal_seam import (
    _selection_boundary_edges, _edge_components, _path_graph,
    _dijkstra, _edges_from_previous,
)
from .relax_seams import relax_seams
from .small_islands import plan_merge
from .uv_artifacts import find_uv_artifacts, apply_uv_artifacts


def analyze(bm, threshold, grow_threshold, min_faces, smooth_steps,
            surface_angle, selected_only=False):
    graph, _, _ = island_graph(bm)
    uv = bm.loops.layers.uv.active
    areas = dict.fromkeys(graph, 0.0)
    uv_areas = dict.fromkeys(graph, 0.0)
    shapes = dict.fromkeys(graph, 1.0)
    for triangle in bm.calc_loop_triangles():
        i = triangle[0].face.index
        if i not in graph:
            continue
        a, b, c = triangle
        x, y = b.vert.co - a.vert.co, c.vert.co - a.vert.co
        cross = x.cross(y).length
        if cross <= 1e-20:
            continue
        u, v = b[uv].uv - a[uv].uv, c[uv].uv - a[uv].uv
        determinant = abs(u.x * v.y - u.y * v.x)
        areas[i] += cross * 0.5
        uv_areas[i] += determinant * 0.5
        # Jacobian singular-value ratio, without numpy or UV scale assumptions.
        length = x.length
        height = cross / length
        j1 = u / length
        j2 = (v - j1 * (x.dot(y) / length)) / height
        trace = j1.length_squared + j2.length_squared
        det = abs(j1.x * j2.y - j1.y * j2.x)
        largest = (trace + math.sqrt(max(0.0, trace * trace - 4 * det * det))) * 0.5
        shapes[i] = max(shapes[i], largest / det if det > 1e-20 else math.inf)
    scores = distortion_scores(areas, uv_areas, shapes, components(graph, graph))
    eligible = {i for i in graph if not selected_only or bm.faces[i].select}
    adjacency = {i: {j for j in graph[i] if j in eligible
                     and bm.faces[i].normal.angle(bm.faces[j].normal, 0.0) <= surface_angle}
                 for i in eligible}
    regions = find_regions({i: scores[i] for i in eligible}, adjacency,
                           threshold, min(grow_threshold, threshold), min_faces, smooth_steps)
    return [{bm.faces[i] for i in part} for part in regions]


def longitudinal_cut(bm, faces, sharp_preference):
    if any(len(e.link_faces) > 2 or e.hide or any(v.hide for v in e.verts)
           for f in faces for e in f.edges):
        return set(), set()
    boundary = _selection_boundary_edges(bm, faces)
    loops = _edge_components(boundary)
    # Branching boundaries and closed surfaces need a different decomposition.
    if not loops or any(sum(e in boundary for e in v.link_edges) != 2
                        for e in boundary for v in e.verts):
        return set(), set()
    graph, _ = _path_graph(faces, boundary)
    graph = {v: [(w, length / (1.0 + sharp_preference *
                              (e.calc_face_angle(0.0) / math.pi)), e)
                 for w, length, e in links] for v, links in graph.items()}
    loops.sort(key=lambda part: (-len(part[0]), min(e.index for e in part[0])))
    connected = set(loops[0][1])
    cut = set()
    for _, target in loops[1:]:
        _, previous, found = _dijkstra(graph, sorted(connected, key=lambda v: v.index), target)
        if found is None:
            return set(), set()
        path = _edges_from_previous(previous, found)
        cut.update(path)
        connected.update(target)
        connected.update(v for e in path for v in e.verts)
    if len(loops) == 1:
        distances, previous, _ = _dijkstra(graph, sorted(connected, key=lambda v: v.index))
        interior = [v for v in distances if v not in connected]
        if not interior:
            return set(), set()
        tip = max(interior, key=lambda v: (distances[v], -v.index))
        cut.update(_edges_from_previous(previous, tip))
    return boundary, cut


class MESH_OT_polygroups_repair_uv_stretch(bpy.types.Operator):
    bl_idname = 'mesh.polygroups_repair_uv_stretch'
    bl_label = 'Smart UV Repair'
    bl_description = 'Find distorted UV patches, add boundary and longitudinal seams, and unwrap affected faces'
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.EnumProperty(name='Action', items=(
        ('REPAIR', 'Repair UV', 'Generate seams and unwrap detected patches'),
        ('SELECT', 'Select Regions', 'Inspect detected faces without changing seams or UVs')))
    threshold: bpy.props.FloatProperty(name='Critical Stretch Ratio', default=4.0, min=1.1, max=1000)
    grow_threshold: bpy.props.FloatProperty(name='Region Growth Ratio', default=1.8, min=1.01, max=1000)
    min_faces: bpy.props.IntProperty(name='Minimum Region Faces', default=6, min=1)
    smooth_steps: bpy.props.IntProperty(name='Boundary Smoothing', default=2, min=0, max=20)
    surface_angle: bpy.props.FloatProperty(name='Surface Angle', default=math.radians(45),
                                          subtype='ANGLE', min=0, max=math.pi)
    sharp_preference: bpy.props.FloatProperty(name='Prefer Sharp Longitudinal Edges', default=3, min=0, max=20)
    selected_only: bpy.props.BoolProperty(name='Selected Faces Only', default=False)
    create_edges: bpy.props.BoolProperty(name='Create New Edges', default=True,
        description='Allow smart routing to split faces; vertex positions are unchanged by routing')
    pin_generated: bpy.props.BoolProperty(name='Pin Generated Seams', default=True,
        description='Protect generated edges using the toolkit seam pin attribute, not UV pins')
    merge_small_islands: bpy.props.BoolProperty(name='Merge Small UV Islands', default=True,
        description='Merge small islands created inside each repaired region before pinning generated seams')
    small_island_threshold: bpy.props.FloatProperty(name='Small Island Area (%)', default=3.0,
        min=0.0, max=49.0, precision=2,
        description='Maximum island area relative to the repaired region, not the whole mesh')
    average_island_scale: bpy.props.BoolProperty(name='Average Island Scale', default=True,
        description='Average texel density across all UV islands after repair')
    native_pack: bpy.props.BoolProperty(name='Native Blender Pack', default=True,
        description='Pack all UV islands with Blender native Pack Islands after repair')
    cleanup_artifacts: bpy.props.BoolProperty(name='Clean UV Artifacts During Repair', default=True)
    artifact_method: bpy.props.EnumProperty(name='Artifact Fix Method', items=(
        ('DELETE', 'Delete Faces', 'Delete artifact faces from mesh geometry'),
        ('MERGE_CENTER', 'Merge to Center', 'Collapse each connected artifact to its center')),
        default='MERGE_CENTER')
    artifact_max_faces: bpy.props.IntProperty(name='Maximum Island Faces', default=7, min=1, max=100)
    artifact_stretch: bpy.props.FloatProperty(name='Artifact Stretch', default=8.0, min=1.1, max=10000)
    artifact_compactness: bpy.props.FloatProperty(name='Needle Compactness', default=10.0, min=1.0, max=10000)
    smart_relax: bpy.props.BoolProperty(name='Smart Relax Generated', default=True,
        description='Move generated seam vertices along the mesh surface, preserving junctions')

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'EDIT'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        for name in ('action', 'threshold', 'grow_threshold', 'min_faces', 'smooth_steps',
                     'surface_angle', 'selected_only', 'sharp_preference', 'create_edges',
                     'merge_small_islands', 'small_island_threshold',
                     'pin_generated', 'smart_relax',
                     'average_island_scale', 'native_pack', 'cleanup_artifacts',
                     'artifact_method', 'artifact_max_faces', 'artifact_stretch',
                     'artifact_compactness'):
            self.layout.prop(self, name, text=t(context, 'uv_repair_' + name))

    def execute(self, context):
        obj = context.active_object
        if len(context.objects_in_mode) != 1 or obj.data.users > 1:
            self.report({'ERROR'}, 'Use a single mesh in Edit Mode with single-user data')
            return {'CANCELLED'}
        live = bmesh.from_edit_mesh(obj.data)
        if live.loops.layers.uv.active is None:
            self.report({'ERROR'}, 'An existing active UV map is required')
            return {'CANCELLED'}
        original = live.copy()
        bm = live.copy()
        committed = False
        original_select_mode = tuple(context.tool_settings.mesh_select_mode)
        try:
            pins_layer = pin_layer(bm, True) if self.pin_generated else pin_layer(bm)
            artifact_fixed = 0
            if self.action == 'REPAIR' and self.cleanup_artifacts:
                artifacts = find_uv_artifacts(
                    bm, self.artifact_max_faces, self.artifact_stretch,
                    self.artifact_compactness, self.selected_only,
                )
                artifact_fixed = apply_uv_artifacts(bm, artifacts, self.artifact_method)
                bm.faces.ensure_lookup_table()
                bm.edges.ensure_lookup_table()
                bm.faces.index_update()
                bm.edges.index_update()
            region_layer = bm.faces.layers.int.new('polygroups_uv_repair_region')
            regions = analyze(bm, self.threshold, self.grow_threshold, self.min_faces,
                              self.smooth_steps, self.surface_angle, self.selected_only)
            if not regions:
                if not artifact_fixed:
                    self.report({'INFO'}, 'No critical UV regions or tiny UV artifacts found')
                    return {'FINISHED'}
                bm.faces.layers.int.remove(region_layer)
                bpy.ops.object.mode_set(mode='OBJECT')
                committed = True
                bm.to_mesh(obj.data)
                obj.data.update()
                bpy.ops.object.mode_set(mode='EDIT')
                if self.average_island_scale or self.native_pack:
                    bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type='FACE')
                    bpy.ops.mesh.select_all(action='SELECT')
                    try:
                        bpy.ops.uv.select_all(action='SELECT')
                    except Exception:
                        pass
                    if self.average_island_scale:
                        bpy.ops.uv.average_islands_scale()
                    if self.native_pack:
                        bpy.ops.uv.pack_islands()
                self.report({'INFO'}, f'Fixed {artifact_fixed} tiny UV artifact island(s); no stretch regions found')
                return {'FINISHED'}
            if self.action == 'SELECT':
                indices = {f.index for region in regions for f in region}
                for f in live.faces:
                    f.select_set(False)
                for f in live.faces:
                    if f.index in indices:
                        f.select_set(True)
                context.tool_settings.mesh_select_mode = (False, False, True)
                bmesh.update_edit_mesh(obj.data)
                self.report({'INFO'}, f'Selected {len(regions)} UV regions')
                return {'FINISHED'}
            existing = {e for e in bm.edges if e.seam or is_pinned(e, pins_layer)}
            repaired = set()
            boundaries = set()
            count = 0
            for region_number, region in enumerate(regions, 1):
                boundary, cut = longitudinal_cut(bm, region, self.sharp_preference)
                if not cut:
                    continue
                for face in region:
                    face[region_layer] = region_number
                for edge in boundary | cut:
                    edge.seam = True
                repaired.update(region)
                boundaries.update(boundary)
                count += 1
            if not repaired:
                if artifact_fixed:
                    bm.faces.layers.int.remove(region_layer)
                    bpy.ops.object.mode_set(mode='OBJECT')
                    committed = True
                    bm.to_mesh(obj.data)
                    obj.data.update()
                    bpy.ops.object.mode_set(mode='EDIT')
                    self.report({'INFO'}, f'Fixed {artifact_fixed} tiny UV artifact island(s); stretch regions had no safe path')
                    return {'FINISHED'}
                self.report({'WARNING'}, 'Detected regions have no safe longitudinal path; use Select Regions to inspect')
                return {'FINISHED'}
            for f in bm.faces:
                f.select_set(False)
            for f in repaired:
                f.select_set(True)
            _, created = route_seams(bm, self.surface_angle, create_edges=self.create_edges,
                                     turn_weight=6.0, corridor_width=2.5,
                                     ridge_weight=self.sharp_preference,
                                     protected=existing | boundaries)
            generated = {e for e in bm.edges if e.seam and e not in existing}
            merged_small = 0
            if self.merge_small_islands and self.small_island_threshold > 0.0:
                generated_indices = {edge.index for edge in generated}
                for region_number in range(1, len(regions) + 1):
                    local_faces = [face for face in bm.faces if face[region_layer] == region_number]
                    if not local_faces:
                        continue
                    for face in bm.faces:
                        face.select_set(False)
                    for face in local_faces:
                        face.select_set(True)
                    removed, _total, _small, merged = plan_merge(
                        bm, self.small_island_threshold,
                        protect_sharp=False, protect_materials=False,
                        selected_only=True, protect_pinned=True,
                        threshold_basis='TOTAL', removable_edges=generated_indices,
                    )
                    for edge_index in removed:
                        bm.edges[edge_index].seam = False
                    merged_small += merged
                generated = {e for e in bm.edges if e.seam and e not in existing}
            if self.pin_generated:
                set_pinned(generated, pins_layer)
            for face in bm.faces:
                face.select_set(face[region_layer] > 0)
            bm.faces.layers.int.remove(region_layer)
            bm.edges.index_update()
            generated_indices = {e.index for e in generated}
            bpy.ops.object.mode_set(mode='OBJECT')
            committed = True
            bm.to_mesh(obj.data)
            obj.data.update()
            bpy.ops.object.mode_set(mode='EDIT')
            context.tool_settings.mesh_select_mode = (False, False, True)
            if self.smart_relax:
                target = bmesh.from_edit_mesh(obj.data)
                target.edges.ensure_lookup_table()
                settings = context.scene.polygroups_seam_preparation_settings
                relax_seams(context, 'SMART', settings.seam_relax_iterations,
                            settings.seam_relax_corner_angle, settings.seam_relax_protection_radius,
                            settings.seam_relax_use_corner_angle, select_result=False,
                            relax_edges={target.edges[i] for i in generated_indices})
            target = bmesh.from_edit_mesh(obj.data)
            uv = target.loops.layers.uv.active
            pins = [(loop, loop[uv].pin_uv) for f in target.faces if f.select for loop in f.loops]
            try:
                for loop, _ in pins:
                    loop[uv].pin_uv = False
                bmesh.update_edit_mesh(obj.data)
                result = bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=0.001)
                if result != {'FINISHED'}:
                    raise RuntimeError('UV unwrap did not finish')
            finally:
                for loop, pinned in pins:
                    loop[uv].pin_uv = pinned
                bmesh.update_edit_mesh(obj.data)
            if self.average_island_scale or self.native_pack:
                repaired_selection = {face.index for face in target.faces if face.select}
                selection_mode = tuple(context.tool_settings.mesh_select_mode)
                try:
                    bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type='FACE')
                    bpy.ops.mesh.select_all(action='SELECT')
                    try:
                        bpy.ops.uv.select_all(action='SELECT')
                    except Exception:
                        pass
                    if self.average_island_scale:
                        result = bpy.ops.uv.average_islands_scale()
                        if result != {'FINISHED'}:
                            raise RuntimeError('Average Islands Scale did not finish')
                    if self.native_pack:
                        result = bpy.ops.uv.pack_islands()
                        if result != {'FINISHED'}:
                            raise RuntimeError('Native Blender Pack did not finish')
                finally:
                    target = bmesh.from_edit_mesh(obj.data)
                    target.faces.ensure_lookup_table()
                    for face in target.faces:
                        face.select_set(face.index in repaired_selection)
                    context.tool_settings.mesh_select_mode = selection_mode
                    bmesh.update_edit_mesh(obj.data)
            post_process = []
            if self.average_island_scale:
                post_process.append('scale averaged')
            if self.native_pack:
                post_process.append('UV packed')
            suffix = f"; {', '.join(post_process)}" if post_process else '. Pack UV islands if needed'
            self.report({'INFO'}, f'Repaired {count}/{len(regions)} regions; {len(generated_indices)} seam edges, '
                         f'{created} new edges, {merged_small} small islands merged, '
                         f'{artifact_fixed} UV artifacts fixed{suffix}')
        except Exception as error:
            import traceback
            traceback.print_exc()
            if committed:
                if obj.mode == 'EDIT':
                    bpy.ops.object.mode_set(mode='OBJECT')
                original.to_mesh(obj.data)
                obj.data.update()
                bpy.ops.object.mode_set(mode='EDIT')
                context.tool_settings.mesh_select_mode = original_select_mode
            self.report({'ERROR'}, f'UV repair cancelled: {error}')
            return {'CANCELLED'}
        finally:
            bm.free()
            original.free()
        return {'FINISHED'}


class IMAGE_PT_polygroups_uv_repair(bpy.types.Panel):
    bl_label = 'Smart UV Repair'
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'AI Retopo'

    def draw(self, context):
        self.layout.operator('mesh.polygroups_repair_uv_stretch', text=t(context, 'uv_repair'), icon='UV')
