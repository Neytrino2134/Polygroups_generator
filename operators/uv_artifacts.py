"""Detection and cleanup of tiny malformed UV islands."""
import math
from statistics import median

import bmesh
import bpy

from .split_narrow_islands import island_graph
from ..core.narrow_regions import components
from ..core.double_walls import double_wall_groups


def _triangle_metrics(triangle, uv):
    a, b, c = triangle
    x, y = b.vert.co - a.vert.co, c.vert.co - a.vert.co
    cross = x.cross(y).length
    u, v = b[uv].uv - a[uv].uv, c[uv].uv - a[uv].uv
    determinant = abs(u.x * v.y - u.y * v.x)
    if cross <= 1e-20 or determinant <= 1e-20:
        return cross * .5, determinant * .5, math.inf
    length = x.length
    if length <= 1e-20:
        return cross * .5, determinant * .5, math.inf
    height = cross / length
    j1 = u / length
    j2 = (v - j1 * (x.dot(y) / length)) / height
    trace = j1.length_squared + j2.length_squared
    det = abs(j1.x * j2.y - j1.y * j2.x)
    largest = (trace + math.sqrt(max(0.0, trace * trace - 4.0 * det * det))) * .5
    return cross * .5, determinant * .5, largest / det if det > 1e-20 else math.inf


def find_uv_artifacts(bm, max_faces=7, stretch_threshold=8.0,
                      compactness_threshold=10.0, selected_only=False):
    """Return tiny UV islands with collapsed, stretched, or needle-like UV geometry."""
    graph, _boundary, _edges = island_graph(bm)
    uv = bm.loops.layers.uv.active
    if uv is None:
        raise ValueError('Active UV map required')
    islands = components(graph, graph)
    result = []
    triangles_by_face = {}
    metrics_by_face = {}
    densities = []
    for triangle in bm.calc_loop_triangles():
        triangles_by_face.setdefault(triangle[0].face.index, []).append(triangle)
        physical, mapped, stretch = _triangle_metrics(triangle, uv)
        metrics_by_face.setdefault(triangle[0].face.index, []).append((physical, mapped, stretch))
        if physical > 1e-20 and mapped > 1e-20 and math.isfinite(mapped / physical):
            densities.append(mapped / physical)
    reference_density = median(densities) if len(densities) >= 3 else None
    for indices in islands:
        if not indices or len(indices) > max_faces:
            continue
        faces = [bm.faces[index] for index in indices]
        if selected_only and not any(face.select for face in faces):
            continue
        mesh_area = uv_area = perimeter = 0.0
        worst_stretch = 1.0
        for face in faces:
            for triangle in triangles_by_face.get(face.index, ()):
                physical, mapped, stretch = _triangle_metrics(triangle, uv)
                mesh_area += physical
                uv_area += mapped
                worst_stretch = max(worst_stretch, stretch)
            for loop in face.loops:
                edge = loop.edge
                neighbor_inside = len(edge.link_faces) == 2 and all(
                    linked.index in indices for linked in edge.link_faces)
                if not neighbor_inside:
                    perimeter += (loop.link_loop_next[uv].uv - loop[uv].uv).length
        compactness = (perimeter * perimeter / (4.0 * math.pi * uv_area)
                       if uv_area > 1e-20 else math.inf)
        collapsed = mesh_area > 1e-20 and uv_area <= 1e-12
        if collapsed or worst_stretch >= stretch_threshold or compactness >= compactness_threshold:
            result.append({
                'faces': set(faces), 'face_count': len(faces),
                'stretch': worst_stretch, 'compactness': compactness,
                'mesh_area': mesh_area, 'uv_area': uv_area,
            })
    # A thin physical triangle can unwrap into a broad, regular UV triangle.
    # It may belong to a large island, so inspect these faces independently of
    # the island-size limit. Require both physical degeneracy and excessive UV
    # area per mesh area to avoid removing deliberately scaled valid islands.
    already_detected = {face for artifact in result for face in artifact['faces']}
    if reference_density is not None:
        for face in bm.faces:
            if (face.index not in graph or face in already_detected or len(face.verts) != 3
                    or (selected_only and not face.select)):
                continue
            physical, mapped, stretch = metrics_by_face[face.index][0]
            if mapped <= 1e-12:
                continue
            mesh_perimeter = sum(edge.calc_length() for edge in face.edges)
            mesh_compactness = (mesh_perimeter ** 2 / (4 * math.pi * physical)
                                if physical > 1e-20 else math.inf)
            density_ratio = (mapped / physical / reference_density
                             if physical > 1e-20 else math.inf)
            if (mesh_compactness >= compactness_threshold
                    and density_ratio >= stretch_threshold ** 2):
                result.append({
                    'faces': {face}, 'face_count': 1, 'stretch': stretch,
                    'compactness': mesh_compactness, 'mesh_area': physical,
                    'uv_area': mapped, 'density_ratio': density_ratio,
                    'reason': 'thin_mesh_uv_expansion',
                })
    for group in double_wall_groups(bm):
        if selected_only and not any(face.select for face in group):
            continue
        # Keep both sides in one artifact so cleanup cannot leave a second wall.
        for artifact in result:
            artifact['faces'].difference_update(group)
        result = [artifact for artifact in result if artifact['faces']]
        result.append({
            'faces': group, 'face_count': len(group), 'stretch': math.inf,
            'compactness': math.inf, 'mesh_area': sum(face.calc_area() for face in group),
            'uv_area': 0.0, 'reason': 'zero_thickness_double_wall',
        })
    # Never erase or collapse the complete analyzed mesh. A lone tiny object may
    # simply be a valid asset with an absent/unfinished UV map rather than debris.
    detected_faces = {face for artifact in result for face in artifact['faces']}
    if detected_faces and len(detected_faces) == len(graph):
        return []
    return result


def apply_uv_artifacts(bm, artifacts, method):
    faces = {face for artifact in artifacts for face in artifact['faces'] if face.is_valid}
    if not faces:
        return 0
    if method == 'DELETE':
        bmesh.ops.delete(bm, geom=list(faces), context='FACES')
    elif method == 'MERGE_CENTER':
        # Merge each physical vertex component once. UV islands may share seam vertices.
        verts = {vert for face in faces for vert in face.verts if vert.is_valid}
        remaining = set(verts)
        groups = []
        while remaining:
            seed = remaining.pop()
            group = {seed}
            stack = [seed]
            while stack:
                vert = stack.pop()
                for edge in vert.link_edges:
                    other = edge.other_vert(vert)
                    if other in remaining and any(face in faces for face in edge.link_faces):
                        remaining.remove(other)
                        group.add(other)
                        stack.append(other)
            groups.append(group)
        for group in groups:
            valid = [vert for vert in group if vert.is_valid]
            if len(valid) < 2:
                continue
            center = sum((vert.co for vert in valid), valid[0].co.copy() * 0.0) / len(valid)
            bmesh.ops.pointmerge(bm, verts=valid, merge_co=center)
    else:
        raise ValueError(f'Unknown artifact cleanup method: {method}')
    bm.normal_update()
    return len(artifacts)


class MESH_OT_polygroups_uv_artifact_cleanup(bpy.types.Operator):
    bl_idname = 'mesh.polygroups_uv_artifact_cleanup'
    bl_label = 'UV Artifact Cleanup'
    bl_description = 'Find tiny malformed UV islands and select, delete, or collapse their mesh faces'
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.EnumProperty(items=(
        ('SELECT', 'Select Artifacts', 'Select detected faces without changing geometry'),
        ('APPLY', 'Apply Cleanup', 'Apply the selected cleanup method')))
    method: bpy.props.EnumProperty(name='Fix Method', items=(
        ('DELETE', 'Delete Faces', 'Delete artifact faces from the mesh'),
        ('MERGE_CENTER', 'Merge to Center', 'Collapse each connected artifact to its center')),
        default='MERGE_CENTER')
    max_faces: bpy.props.IntProperty(name='Maximum Island Faces', default=7, min=1, max=100)
    stretch_threshold: bpy.props.FloatProperty(name='Artifact Stretch', default=8.0, min=1.1, max=10000)
    compactness_threshold: bpy.props.FloatProperty(name='Needle Compactness', default=10.0, min=1.0, max=10000)
    selected_only: bpy.props.BoolProperty(name='Selected Faces Only', default=False)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'EDIT'

    def execute(self, context):
        obj = context.active_object
        if len(context.objects_in_mode) != 1 or obj.data.users > 1:
            self.report({'ERROR'}, 'Use one mesh in Edit Mode with single-user data')
            return {'CANCELLED'}
        bm = bmesh.from_edit_mesh(obj.data)
        if bm.loops.layers.uv.active is None:
            self.report({'ERROR'}, 'An active UV map is required')
            return {'CANCELLED'}
        artifacts = find_uv_artifacts(bm, self.max_faces, self.stretch_threshold,
                                      self.compactness_threshold, self.selected_only)
        if not artifacts:
            self.report({'INFO'}, 'No tiny UV artifacts found')
            return {'FINISHED'}
        for face in bm.faces:
            face.select_set(False)
        if self.action == 'SELECT':
            for artifact in artifacts:
                for face in artifact['faces']:
                    face.select_set(True)
            context.tool_settings.mesh_select_mode = (False, False, True)
        else:
            apply_uv_artifacts(bm, artifacts, self.method)
        bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=self.action == 'APPLY')
        verb = 'Selected' if self.action == 'SELECT' else 'Fixed'
        self.report({'INFO'}, f'{verb} {len(artifacts)} UV artifact island(s)')
        return {'FINISHED'}
