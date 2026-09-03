"""Replace selected face patches with a triangular fill of their boundaries."""
from collections import Counter

import bmesh
import bpy
from mathutils import Vector

from ..localization import t
from .clear_edges_seam import editable_meshes


def _selected_regions(faces):
    remaining = set(faces)
    while remaining:
        start = remaining.pop()
        region, stack = {start}, [start]
        while stack:
            for edge in stack.pop().edges:
                for face in edge.link_faces:
                    if face in remaining:
                        remaining.remove(face)
                        region.add(face)
                        stack.append(face)
        yield region


def _single_boundary_loop(boundary):
    adjacency = {}
    for edge in boundary:
        a, b = edge.verts
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    if any(len(neighbors) != 2 for neighbors in adjacency.values()):
        return False
    visited, stack = set(), [next(iter(adjacency))]
    while stack:
        vert = stack.pop()
        if vert not in visited:
            visited.add(vert)
            stack.extend(adjacency[vert] - visited)
    return len(visited) == len(adjacency)


def _triangulate_boundary(boundary, normal):
    boundary_keys = {frozenset(edge.verts) for edge in boundary}
    # F-style hole fill followed by triangulation handles non-planar loops
    # without projecting them along the damaged source faces' average normal.
    # Multiple loops need triangle fill to preserve unselected inner islands.
    methods = ['HOLE', 'AUTO', 'NORMAL'] if _single_boundary_loop(boundary) else ['AUTO', 'NORMAL']
    for method in methods:
        scratch = bmesh.new()
        try:
            vertices = {vert for edge in boundary for vert in edge.verts}
            copies = {vert: scratch.verts.new(vert.co) for vert in vertices}
            originals = {copy: vert for vert, copy in copies.items()}
            edges = [scratch.edges.new([copies[v] for v in edge.verts]) for edge in boundary]
            if method == 'HOLE':
                result = bmesh.ops.holes_fill(scratch, edges=edges, sides=0)
                bmesh.ops.triangulate(scratch, faces=result['faces'], quad_method='BEAUTY', ngon_method='BEAUTY')
            else:
                bmesh.ops.triangle_fill(
                    scratch, edges=edges, use_beauty=True,
                    normal=normal if method == 'NORMAL' else Vector(),
                )
            triangles = [tuple(originals[v] for v in face.verts) for face in scratch.faces]
            uses = Counter(frozenset((a, b)) for tri in triangles
                           for a, b in zip(tri, tri[1:] + tri[:1]))
            if (triangles and all(len(tri) == 3 for tri in triangles)
                    and {key for key, count in uses.items() if count == 1} == boundary_keys
                    and all(count <= 2 for count in uses.values())):
                return triangles
        except (RuntimeError, ValueError):
            pass  # Try Blender's other fill method on a fresh boundary copy.
        finally:
            scratch.free()
    raise ValueError('delete_fill_invalid_boundary')


def _plan_fill(region):
    """Triangulate only a boundary copy so an invalid fill cannot delete input."""
    region_edges = {edge for face in region for edge in face.edges}
    # Find the edges that will be open after deletion, including edges with
    # multiple selected faces from overlapping/non-manifold damaged geometry.
    boundary = {edge for edge in region_edges
                if sum(face not in region for face in edge.link_faces) == 1
                or len(edge.link_faces) == 1}
    if not boundary:
        raise ValueError('delete_fill_no_boundary')
    normal = sum((face.normal * face.calc_area() for face in region), Vector())
    if normal.length:
        normal.normalize()
    triangles = _triangulate_boundary(boundary, normal)
    # Orient the replacement using surviving neighbors, not potentially
    # inconsistent normals in the damaged faces that are about to be deleted.
    direction, fallback = {}, {}
    for edge in boundary:
        for loop in edge.link_loops:
            pair = (loop.vert, loop.link_loop_next.vert)
            if loop.face in region:
                fallback[frozenset(edge.verts)] = pair
            else:
                direction[frozenset(edge.verts)] = tuple(reversed(pair))
    references = direction or fallback
    reversed_edges = []
    for tri in triangles:
        for a, b in zip(tri, tri[1:] + tri[:1]):
            expected = references.get(frozenset((a, b)))
            if expected is not None:
                reversed_edges.append(expected != (a, b))
    if sum(reversed_edges) > len(reversed_edges) / 2:
        triangles = [tuple(reversed(tri)) for tri in triangles]
    for tri in triangles:
        if any(face not in region and set(face.verts) == set(tri) for face in tri[0].link_faces):
            raise ValueError('delete_fill_invalid_boundary')
    return {
        'faces': region, 'edges': region_edges, 'boundary': boundary,
        'vertices': {v for face in region for v in face.verts},
        'triangles': triangles,
        'material': Counter(face.material_index for face in region).most_common(1)[0][0],
        'smooth': sum(face.smooth for face in region) > len(region) / 2,
    }


def _replace_region(bm, plan):
    bmesh.ops.delete(bm, geom=list(plan['faces']), context='FACES_ONLY')
    loose_edges = [edge for edge in plan['edges'] if edge.is_valid
                   and edge not in plan['boundary'] and not edge.link_faces]
    bmesh.ops.delete(bm, geom=loose_edges, context='EDGES')
    loose_vertices = [vert for vert in plan['vertices'] if vert.is_valid and not vert.link_edges]
    bmesh.ops.delete(bm, geom=loose_vertices, context='VERTS')
    created = []
    for triangle in plan['triangles']:
        face = bm.faces.new(triangle)
        face.material_index = plan['material']
        face.smooth = plan['smooth']
        face.select_set(True)
        created.append(face)
    return created


class MESH_OT_polygroups_delete_and_fill(bpy.types.Operator):
    bl_idname = 'mesh.polygroups_delete_and_fill'
    bl_label = 'Delete and Fill'
    bl_description = 'Replace selected faces with a triangular fill; keep other holes and mesh regions unchanged'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.active_object is not None

    def execute(self, context):
        pending = []
        try:
            for mesh, bm in editable_meshes(context):
                selected = {face for face in bm.faces if face.select and not face.hide}
                if selected:
                    bm.normal_update()
                    plans = [_plan_fill(region) for region in _selected_regions(selected)]
                    pending.append((mesh, bm, plans))
        except ValueError as error:
            self.report({'WARNING'}, t(context, str(error)))
            return {'CANCELLED'}
        if not pending:
            self.report({'WARNING'}, t(context, 'delete_fill_select_faces'))
            return {'CANCELLED'}
        removed = created = 0
        for mesh, bm, plans in pending:
            for elements in (bm.faces, bm.edges, bm.verts):
                for element in elements:
                    element.select_set(False)
            bm.select_history.clear()
            for plan in plans:
                removed += len(plan['faces'])
                faces = _replace_region(bm, plan)
                created += len(faces)
                bm.faces.active = faces[-1]
            bm.normal_update()
            bm.select_flush_mode()
            bmesh.update_edit_mesh(mesh, loop_triangles=True, destructive=True)
        self.report({'INFO'}, t(context, 'delete_fill_done', removed=removed, created=created))
        return {'FINISHED'}
