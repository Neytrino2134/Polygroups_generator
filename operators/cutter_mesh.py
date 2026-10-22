"""Cutter mesh helpers."""
import bpy
from math import radians
from mathutils import Vector
from .mesh_checks import _delete_faces_by_indices
from .mesh_checks import _edge_face_data
from .mesh_checks import _select_edges
from .mesh_checks import _thin_protrusion_faces
from .relax_seams import relax_seams
from ..pin_edges import pin_layer, set_pinned
from .cutter_screen import (
    _view3d_under_mouse,
    _target_bounds,
    _axis_lock_mode,
    _axis_locked_region_pos,
    _surface_hit_from_region_pos,
    _target_ray_cast_world,
    _screen_cut_plane,
    _arc_center_2d,
    _angle_delta_ccw,
    _screen_arc_points,
    _screen_arc_surface,
    _screen_section_plane,
    _screen_local_ring_surface,
)
from .cutter_constants import (
    AUTOFIX_MAX_HOLE_EDGE_COUNT,
    AUTOFIX_MAX_HOLE_LOOPS,
    AUTOFIX_MAX_LOOSE_GEOMETRY,
    AUTOFIX_MAX_PROTRUSION_FACES,
    AUTOWELD_MODIFIER_NAME,
    AUTOWELD_VERTEX_GROUP_NAME,
    BOOLEAN_PATH_PLACEHOLDER_MATERIAL_NAME,
    BOOLEAN_PATH_TEMP_MATERIAL_NAME,
    CUTTER_PIN_SEAMS_PROP,
    CUTTER_PROP,
    CUTTER_SOLIDIFY_MODIFIER_NAME,
    CUTTER_SOURCE_TOOL_PROP,
    CUTTER_TYPE_PROP,
    DEFAULT_NON_PLANE_CUTTER_THICKNESS,
)
from .cutter_paths import (
    _cutter_planes_world,
)
from .cutter_objects import (
    _convert_draw_stroke_to_cutter_path,
    _draw_strokes_from_cutters,
    _ensure_local_contour_cutter,
)


def _cutter_mark_pinned(context, cutter):
    settings = context.scene.polygroups_object_seam_cutter_settings
    cutter_type = cutter.get(CUTTER_TYPE_PROP)
    if cutter_type == "LOCAL_RING":
        return settings.cutter_local_ring_mark_pinned
    if cutter_type == "LOCAL_CONTOUR":
        return settings.cutter_local_contour_mark_pinned
    if cutter_type == "PATH":
        source_tool = cutter.get(CUTTER_SOURCE_TOOL_PROP, "PATH")
        return (settings.cutter_draw_mark_pinned if source_tool == "DRAW"
                else settings.cutter_path_mark_pinned)
    if cutter_type == "DRAW_STROKE":
        return settings.cutter_draw_mark_pinned
    return bool(cutter.get(CUTTER_PIN_SEAMS_PROP, False))


def _sync_autoweld_vertex_group(target):
    """Put only vertices belonging directly to seam edges in the AutoWeld group."""
    group = target.vertex_groups.get(AUTOWELD_VERTEX_GROUP_NAME)
    if group is None:
        group = target.vertex_groups.new(name=AUTOWELD_VERTEX_GROUP_NAME)
    all_indices = list(range(len(target.data.vertices)))
    if all_indices:
        group.remove(all_indices)
    seam_indices = {index for edge in target.data.edges if edge.use_seam
                    for index in edge.vertices}
    if seam_indices:
        group.add(sorted(seam_indices), 1.0, "REPLACE")
    return group


def _dissolve_degenerate_seam_geometry(target, distance):
    """Repair degenerate, concave, and locally flipped faces near seams."""
    import bmesh

    bm = bmesh.new()
    try:
        bm.from_mesh(target.data)
        seam_verts = {vert for edge in bm.edges if edge.seam for vert in edge.verts}
        if not seam_verts:
            return 0
        tolerance = max(float(distance) * 0.01, 1e-8)
        repaired = 0

        # A vertex pushed through a quad makes one corner turn in the opposite
        # direction. Triangulation gives Blender an unambiguous concave fill.
        folded_quads = []
        for face in bm.faces:
            if len(face.verts) != 4 or not any(vert in seam_verts for vert in face.verts):
                continue
            turns = []
            verts = list(face.verts)
            for index, vert in enumerate(verts):
                before = verts[index - 1].co - vert.co
                after = verts[(index + 1) % len(verts)].co - vert.co
                turns.append(before.cross(after).dot(face.normal))
            significant = [turn for turn in turns if abs(turn) > tolerance * tolerance]
            if significant and min(significant) < 0.0 < max(significant):
                folded_quads.append(face)
        if folded_quads:
            bmesh.ops.triangulate(
                bm, faces=folded_quads, quad_method="BEAUTY", ngon_method="BEAUTY",
            )
            repaired += len(folded_quads)
            bm.normal_update()

        # A triangle that has crossed into the neighboring surface points
        # against the surrounding faces. Collapse its shortest edge instead of
        # leaving an overlapping negative-orientation sliver.
        flipped_edges = []
        for face in list(bm.faces):
            if len(face.verts) != 3 or not any(vert in seam_verts for vert in face.verts):
                continue
            neighbors = {other for edge in face.edges for other in edge.link_faces if other != face}
            if len(neighbors) < 2:
                continue
            average = sum((other.normal * max(other.calc_area(), 1e-20) for other in neighbors), Vector())
            if average.length and face.normal.dot(average.normalized()) < -0.25:
                flipped_edges.append(min(face.edges, key=lambda edge: edge.calc_length()))
        for edge in flipped_edges:
            if edge.is_valid:
                bmesh.ops.collapse(bm, edges=[edge])
                repaired += 1
        if flipped_edges:
            bm.normal_update()

        candidates = []
        for face in bm.faces:
            if len(face.verts) != 3 or not any(vert in seam_verts for vert in face.verts):
                continue
            longest = max((edge.calc_length() for edge in face.edges), default=0.0)
            # triangle area = base * height / 2
            if longest > 0.0 and face.calc_area() * 2.0 <= longest * tolerance:
                candidates.extend(face.edges)
        candidates = list(set(candidates))
        if not candidates:
            if repaired:
                bm.to_mesh(target.data)
                target.data.update()
            return repaired
        before = len(bm.faces)
        bmesh.ops.dissolve_degenerate(bm, edges=candidates, dist=tolerance)
        repaired += max(0, before - len(bm.faces))
        if repaired:
            bm.normal_update()
            bm.to_mesh(target.data)
            target.data.update()
        return repaired
    finally:
        bm.free()


def _prepare_seam_band_autoweld(target, distance):
    """Create a final Weld modifier restricted to the expanded seam band."""
    group = _sync_autoweld_vertex_group(target)
    modifier = target.modifiers.get(AUTOWELD_MODIFIER_NAME)
    if modifier is None or modifier.type != "WELD":
        modifier = target.modifiers.new(AUTOWELD_MODIFIER_NAME, "WELD")
    modifier.merge_threshold = max(0.0, float(distance))
    modifier.vertex_group = group.name
    modifier_index = target.modifiers.find(modifier.name)
    if modifier_index != len(target.modifiers) - 1:
        target.modifiers.move(modifier_index, len(target.modifiers) - 1)
    return modifier


def _world_plane_to_local(target, plane_co, plane_no):
    matrix = target.matrix_world
    local_co = matrix.inverted() @ plane_co
    local_no = matrix.to_3x3().transposed() @ plane_no
    if local_no.length < 0.000001:
        return None
    local_no.normalize()
    return local_co, local_no


def _clear_mesh_component_selection(mesh):
    for vertex in mesh.vertices:
        vertex.select = False
    for edge in mesh.edges:
        edge.select = False
    for polygon in mesh.polygons:
        polygon.select = False
    mesh.update()


def _path_boolean_material():
    material = bpy.data.materials.new(BOOLEAN_PATH_TEMP_MATERIAL_NAME)
    material.diffuse_color = (1.0, 0.08, 0.02, 1.0)
    material.use_nodes = False
    return material


def _path_placeholder_material():
    material = bpy.data.materials.new(BOOLEAN_PATH_PLACEHOLDER_MATERIAL_NAME)
    material.diffuse_color = (0.5, 0.5, 0.5, 1.0)
    material.use_nodes = False
    return material


def _ensure_material_slot(obj, material):
    for index, slot_material in enumerate(obj.data.materials):
        if slot_material == material or (slot_material and slot_material.name == material.name):
            return index

    obj.data.materials.append(material)
    return len(obj.data.materials) - 1


def _prepare_target_path_boolean_materials(target, temp_material):
    placeholder_material = None
    placeholder_index = None
    if not target.data.materials:
        placeholder_material = _path_placeholder_material()
        target.data.materials.append(placeholder_material)
        placeholder_index = 0
        for polygon in target.data.polygons:
            polygon.material_index = 0

    target.data.materials.append(temp_material)
    return len(target.data.materials) - 1, placeholder_index, placeholder_material


def _extend_arc_cutter_mesh_ends(obj, extension_distance):
    if obj.type != "MESH" or obj.get(CUTTER_TYPE_PROP) != "ARC" or extension_distance <= 0.0:
        return

    vertices = obj.data.vertices
    if len(vertices) < 4:
        return

    def pair_center(index):
        return (vertices[index].co + vertices[index + 1].co) * 0.5

    first_center = pair_center(0)
    second_center = pair_center(2)
    first_direction = first_center - second_center
    if first_direction.length > 0.000001:
        first_direction.normalize()
        vertices[0].co += first_direction * extension_distance
        vertices[1].co += first_direction * extension_distance

    last_index = len(vertices) - 2
    previous_index = len(vertices) - 4
    last_center = pair_center(last_index)
    previous_center = pair_center(previous_index)
    last_direction = last_center - previous_center
    if last_direction.length > 0.000001:
        last_direction.normalize()
        vertices[last_index].co += last_direction * extension_distance
        vertices[last_index + 1].co += last_direction * extension_distance

    obj.data.update()


def _duplicate_boolean_cutter_as_mesh(
    context,
    cutter,
    material,
    boolean_solidify_thickness=None,
    extension_distance=0.0,
):
    work = cutter.copy()
    work.data = cutter.data.copy()
    work.name = f"{cutter.name}_Boolean"
    work[CUTTER_PROP] = False
    work.hide_viewport = False
    work.hide_render = False
    work.hide_set(False)
    # Convert the unthickened surface first; Solidify is applied once below.
    for modifier in list(work.modifiers):
        if modifier.name == CUTTER_SOLIDIFY_MODIFIER_NAME:
            work.modifiers.remove(modifier)

    target_collection = cutter.users_collection[0] if cutter.users_collection else context.scene.collection
    target_collection.objects.link(work)

    bpy.ops.object.select_all(action="DESELECT")
    work.select_set(True)
    context.view_layer.objects.active = work
    _apply_object_scale(context, work)

    if work.type != "MESH":
        source_data = work.data
        if work.type == "CURVE":
            work.data.dimensions = "3D"
            if hasattr(work.data, "fill_mode"):
                work.data.fill_mode = "FULL"
        bpy.ops.object.convert(target="MESH")
        work = context.view_layer.objects.active
        if source_data and source_data.users == 0 and bpy.data.curves.get(source_data.name) == source_data:
            bpy.data.curves.remove(source_data)
        _apply_object_scale(context, work)

    if work is None or work.type != "MESH" or not work.data.polygons:
        if work is not None:
            bpy.data.objects.remove(work, do_unlink=True)
        return None

    _extend_arc_cutter_mesh_ends(work, extension_distance)

    work.data.materials.clear()
    material_index = _ensure_material_slot(work, material)
    for polygon in work.data.polygons:
        polygon.material_index = material_index
        polygon.select = True
    work.data.update()

    if boolean_solidify_thickness is not None:
        modifier = work.modifiers.get(CUTTER_SOLIDIFY_MODIFIER_NAME)
        if modifier is None:
            modifier = work.modifiers.new(CUTTER_SOLIDIFY_MODIFIER_NAME, "SOLIDIFY")
            modifier.thickness = boolean_solidify_thickness
            modifier.offset = 0.0
            if hasattr(modifier, "use_rim"):
                modifier.use_rim = True
        if modifier is not None:
            try:
                bpy.ops.object.modifier_apply(modifier=modifier.name)
            except RuntimeError:
                pass
        material_index = _ensure_material_slot(work, material)
        for polygon in work.data.polygons:
            polygon.material_index = material_index
            polygon.select = True
        work.data.update()

    return work


def _apply_object_scale(context, obj):
    if obj is None or obj.name not in bpy.data.objects:
        return

    if context.object and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    context.view_layer.objects.active = obj
    try:
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    except RuntimeError:
        pass


def _mesh_has_selected_edges(mesh):
    return any(edge.select for edge in mesh.edges)


def _split_selected_edges(context, target, separate_objects):
    if not _mesh_has_selected_edges(target.data):
        return []

    if context.object and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    context.view_layer.objects.active = target

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_mode(type="EDGE")
    bpy.ops.mesh.edge_split()

    if separate_objects:
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.separate(type="LOOSE")
        bpy.ops.object.mode_set(mode="OBJECT")
        return [obj for obj in context.selected_objects if obj.type == "MESH"]

    bpy.ops.object.mode_set(mode="OBJECT")
    return [target]


def _fill_split_cut_boundaries(objects):
    import bmesh

    filled_faces = 0
    for obj in objects:
        if obj.type != "MESH":
            continue

        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        cut_boundary_edges = [
            edge
            for edge in bm.edges
            if edge.is_boundary and (edge.seam or edge.select)
        ]
        if not cut_boundary_edges:
            bm.free()
            continue

        result = bmesh.ops.holes_fill(
            bm,
            edges=cut_boundary_edges,
            sides=0,
        )
        filled_faces += sum(
            1
            for item in result.get("geom", ())
            if isinstance(item, bmesh.types.BMFace)
        )
        bm.normal_update()
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()

    return filled_faces


def _remove_material_slot_by_index(obj, material_index):
    if material_index < 0 or material_index >= len(obj.data.materials):
        return

    try:
        obj.data.materials.pop(index=material_index)
    except Exception:
        pass


def _remove_material_if_unused(material):
    if material is not None and bpy.data.materials.get(material.name) == material and material.users == 0:
        bpy.data.materials.remove(material)


def _material_slot_index(obj, material):
    for index, slot_material in enumerate(obj.data.materials):
        if slot_material == material or (slot_material and slot_material.name == material.name):
            return index
    return -1


def _apply_boolean_cutter_to_mesh(
    context, target, cutter, boolean_solidify_thickness=None,
    extension_distance=0.0, boolean_solver="FLOAT",
):
    thickness = boolean_solidify_thickness
    if thickness is None:
        thickness = _cutter_thickness(context)
    return _intersect_cutter_surface(
        context, target, cutter, "BOOLEAN", extension_distance,
        max(thickness, 0.000001), boolean_solver,
    )


def _apply_knife_intersect_cutter_to_mesh(
    context, target, cutter, extension_distance=0.0,
    boolean_solidify_thickness=None, boolean_solver="FLOAT",
):
    return _intersect_cutter_surface(
        context, target, cutter, "KNIFE", extension_distance, None, boolean_solver,
    )


def _remove_cutter_faces_and_mark_seams(mesh, material_index, merge_distance, mark_pinned=False):
    """Keep the shared intersection edges, deleting only cutter-owned geometry."""
    import bmesh

    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        cut_layer = bm.edges.layers.int.new("__cutter_new_seam")
        cutter_faces = {f for f in bm.faces if f.material_index == material_index}
        cutter_edges = {e for f in cutter_faces for e in f.edges}
        cutter_verts = {v for f in cutter_faces for v in f.verts}
        cut_edges = {
            e for e in cutter_edges
            if any(f not in cutter_faces for f in e.link_faces)
        }
        for edge in cut_edges:
            edge.seam = True
            edge[cut_layer] = 1
        # FACES_ONLY preserves edges shared with the target and their seam flag.
        bmesh.ops.delete(bm, geom=list(cutter_faces), context="FACES_ONLY")
        loose_edges = [e for e in cutter_edges if e.is_valid and not e.link_faces]
        bmesh.ops.delete(bm, geom=loose_edges, context="EDGES")
        loose_verts = [v for v in cutter_verts if v.is_valid and not v.link_edges]
        bmesh.ops.delete(bm, geom=loose_verts, context="VERTS")
        cut_verts = {v for e in cut_edges if e.is_valid for v in e.verts}
        # Boolean may triangulate the two sides of a filled cutter differently.
        # Remove redundant points on straight cut segments before welding, so
        # one side cannot leave a T-junction against an unsplit opposite edge.
        redundant = []
        for vert in cut_verts:
            if len(vert.link_edges) != 2 or not all(e[cut_layer] for e in vert.link_edges):
                continue
            a, b = [e.other_vert(vert).co - vert.co for e in vert.link_edges]
            if a.length_squared and b.length_squared and a.normalized().dot(b.normalized()) < -0.999999:
                redundant.append(vert)
        if redundant:
            bmesh.ops.dissolve_verts(bm, verts=redundant)
            cut_verts = {v for e in bm.edges if e[cut_layer] for v in e.verts}
        # Weld only the new cut, never unrelated open boundaries of the model.
        if cut_verts:
            bmesh.ops.remove_doubles(bm, verts=list(cut_verts), dist=merge_distance)
        marked = sum(1 for e in bm.edges if e[cut_layer])
        pins = pin_layer(bm, True) if mark_pinned else None
        for edge in bm.edges:
            if edge[cut_layer]:
                edge.seam = True
                edge.select_set(True)
                if pins is not None:
                    set_pinned((edge,), pins)
        bm.edges.layers.int.remove(cut_layer)
        bm.normal_update()
        bm.to_mesh(mesh)
        mesh.update()
        return marked
    finally:
        bm.free()


def _intersect_cutter_surface(
    context, target, cutter, method, extension_distance, thickness, solver,
):
    import bmesh

    material = _path_boolean_material()
    temp_index, placeholder_index, placeholder = _prepare_target_path_boolean_materials(target, material)
    work = None
    work_data = None
    previous_select_mode = tuple(context.tool_settings.mesh_select_mode)
    selection_attribute = target.data.attributes.new("__cutter_previous_selection", "INT", "EDGE")
    selection_name = selection_attribute.name
    selection_attribute.data.foreach_set("value", [int(e.select) for e in target.data.edges])
    try:
        work = _duplicate_boolean_cutter_as_mesh(
            context, cutter, material, boolean_solidify_thickness=thickness,
            extension_distance=extension_distance,
        )
        if work is None:
            return 0
        work_data = work.data
        bpy.ops.object.select_all(action="DESELECT")
        target.select_set(True)
        work.select_set(True)
        context.view_layer.objects.active = target
        bpy.ops.object.join()
        work = None  # Join removes the temporary object.
        temp_index = _material_slot_index(target, material)
        context.tool_settings.mesh_select_mode = (False, False, True)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="DESELECT")
        bm = bmesh.from_edit_mesh(target.data)
        for face in bm.faces:
            face.select_set(face.material_index == temp_index)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(target.data)
        if method == "BOOLEAN":
            bpy.ops.mesh.intersect_boolean(operation="UNION", solver=solver, threshold=0.000001)
        else:
            bpy.ops.mesh.intersect(
                mode="SELECT_UNSELECT", separate_mode="NONE",
                threshold=0.000001, solver=solver,
            )
        bpy.ops.object.mode_set(mode="OBJECT")
        _clear_mesh_component_selection(target.data)
        return _remove_cutter_faces_and_mark_seams(
            target.data, temp_index,
            thickness * 4.0 if method == "BOOLEAN" else 0.000001,
            mark_pinned=_cutter_mark_pinned(context, cutter),
        )
    finally:
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        context.tool_settings.mesh_select_mode = previous_select_mode
        selection_attribute = target.data.attributes.get(selection_name)
        if selection_attribute is not None:
            for edge, value in zip(target.data.edges, selection_attribute.data):
                if value.value:
                    edge.select = True
            target.data.attributes.remove(selection_attribute)
        if work is not None:
            bpy.data.objects.remove(work, do_unlink=True)
        # The join operator may already have freed this mesh datablock.
        try:
            if work_data is not None and work_data.users == 0:
                bpy.data.meshes.remove(work_data)
        except ReferenceError:
            pass
        temp_index = _material_slot_index(target, material)
        if temp_index >= 0:
            _remove_material_slot_by_index(target, temp_index)
        if placeholder_index is not None:
            _remove_material_slot_by_index(target, placeholder_index)
        _remove_material_if_unused(material)
        _remove_material_if_unused(placeholder)


def _cutter_apply_method(context):
    settings = getattr(context.scene, "polygroups_object_seam_cutter_settings", None)
    return getattr(settings, "cutter_apply_method", "BOOLEAN")


def _cutter_boolean_solver(context):
    settings = getattr(context.scene, "polygroups_object_seam_cutter_settings", None)
    solver = getattr(settings, "cutter_boolean_solver", "FLOAT")
    return solver if solver in {"FLOAT", "EXACT"} else "FLOAT"


def _cutter_thickness(context):
    settings = getattr(context.scene, "polygroups_object_seam_cutter_settings", None)
    thickness = getattr(settings, "cutter_thickness", DEFAULT_NON_PLANE_CUTTER_THICKNESS)
    return min(0.001, max(0.0001, float(thickness)))


def _count_open_boundary_edges(target):
    import bmesh

    bm = bmesh.new()
    bm.from_mesh(target.data)
    count = sum(1 for edge in bm.edges if len(edge.link_faces) < 2)
    bm.free()
    return count


def _delete_loose_geometry_for_autofix(context, target):
    import bmesh

    mesh = target.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    loose_edges = [edge for edge in bm.edges if edge.is_valid and not edge.link_faces]
    loose_verts = [vert for vert in bm.verts if vert.is_valid and not vert.link_edges]
    loose_total = len(loose_edges) + len(loose_verts)
    if not loose_total or loose_total > AUTOFIX_MAX_LOOSE_GEOMETRY:
        bm.free()
        return 0

    if loose_edges:
        bmesh.ops.delete(bm, geom=loose_edges, context="EDGES")
    loose_verts = [vert for vert in bm.verts if vert.is_valid and not vert.link_edges]
    if loose_verts:
        bmesh.ops.delete(bm, geom=loose_verts, context="VERTS")

    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return loose_total


def _boundary_hole_loops_for_autofix(mesh):
    edge_to_faces, _edge_directions = _edge_face_data(mesh)
    edge_by_key = {
        tuple(sorted(edge.vertices)): edge.index
        for edge in mesh.edges
    }
    boundary_edges = {
        edge_by_key[key]
        for key, faces in edge_to_faces.items()
        if len(faces) == 1 and key in edge_by_key
    }
    if not boundary_edges:
        return []

    vertex_to_edges = {}
    for edge_index in boundary_edges:
        edge = mesh.edges[edge_index]
        for vertex_index in edge.vertices:
            vertex_to_edges.setdefault(vertex_index, set()).add(edge_index)

    loops = []
    visited = set()
    for edge_index in boundary_edges:
        if edge_index in visited:
            continue

        component = []
        stack = [edge_index]
        visited.add(edge_index)
        while stack:
            current = stack.pop()
            component.append(current)
            for vertex_index in mesh.edges[current].vertices:
                for next_edge in vertex_to_edges.get(vertex_index, ()):
                    if next_edge in visited:
                        continue
                    visited.add(next_edge)
                    stack.append(next_edge)

        if len(component) <= AUTOFIX_MAX_HOLE_EDGE_COUNT:
            loops.append(sorted(component))

    loops.sort(key=len)
    return loops[:AUTOFIX_MAX_HOLE_LOOPS]


def _fill_boundary_hole_loop_for_autofix(context, target, edge_indices):
    if not edge_indices:
        return 0

    before_face_count = len(target.data.polygons)
    _select_edges(context, target, edge_indices)
    try:
        bpy.ops.mesh.fill()
    except RuntimeError:
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        return 0
    bpy.ops.object.mode_set(mode="OBJECT")

    return 1 if len(target.data.polygons) > before_face_count else 0


def _prepare_target_for_autofix(context, target):
    if context.object and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    context.view_layer.objects.active = target


def _fill_open_nonmanifold_boundaries(target):
    """Fill boundary loops only; leave loose and other damaged geometry intact."""
    import bmesh

    bm = bmesh.new()
    try:
        bm.from_mesh(target.data)
        boundary_edges = [edge for edge in bm.edges if len(edge.link_faces) == 1]
        if not boundary_edges:
            return 0
        result = bmesh.ops.holes_fill(bm, edges=boundary_edges, sides=0)
        filled_faces = len(result.get("faces", ()))
        if filled_faces:
            bm.normal_update()
            bm.to_mesh(target.data)
            target.data.update()
        return filled_faces
    finally:
        bm.free()


def _remove_fin_faces_for_autofix(context, target):
    """Remove detected dangling fin faces without running the full mesh check."""
    edge_to_faces, _edge_directions = _edge_face_data(target.data)
    fin_faces = sorted(_thin_protrusion_faces(target.data, edge_to_faces))
    if not fin_faces or len(fin_faces) > AUTOFIX_MAX_PROTRUSION_FACES:
        return 0
    return _delete_faces_by_indices(context, target, fin_faces)


def _triangulate_ngons_for_autofix(target):
    """Triangulate only faces with more than four sides, without mesh analysis."""
    import bmesh

    bm = bmesh.new()
    try:
        bm.from_mesh(target.data)
        ngons = [face for face in bm.faces if len(face.verts) > 4]
        if not ngons:
            return 0
        count = len(ngons)
        bmesh.ops.triangulate(bm, faces=ngons, quad_method="BEAUTY", ngon_method="BEAUTY")
        bm.normal_update()
        bm.to_mesh(target.data)
        target.data.update()
        return count
    finally:
        bm.free()


def _smart_relax_seams_for_autofix(context, target):
    """Run the fixed, lightweight Smart Relax pass used by cutter Autofix."""
    _prepare_target_for_autofix(context, target)
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        moved, _protected = relax_seams(
            context,
            "SMART",
            1,
            radians(90.0),
            1,
            use_corner_angle=False,
            select_result=False,
            selected_area_only=False,
        )
        return moved
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")


def _apply_arc_cutters_to_mesh(context, target, cutters):
    marked_edges = 0
    _center, target_diagonal = _target_bounds(target)
    knife_extension_distance = target_diagonal * 2.0
    apply_method = _cutter_apply_method(context)
    boolean_solver = _cutter_boolean_solver(context)
    for cutter in cutters:
        if apply_method == "BOOLEAN":
            marked_edges += _apply_boolean_cutter_to_mesh(
                context,
                target,
                cutter,
                boolean_solidify_thickness=None,
                extension_distance=0.0,
                boolean_solver=boolean_solver,
            )
        else:
            marked_edges += _apply_knife_intersect_cutter_to_mesh(
                context,
                target,
                cutter,
                extension_distance=knife_extension_distance,
                boolean_solver=boolean_solver,
            )
    return marked_edges


def _apply_plane_cutters_to_mesh(target, cutters):
    import bmesh

    mesh = target.data
    bm = bmesh.new()
    bm.from_mesh(mesh)

    marked_edges = 0
    for cutter in cutters:
        for plane in _cutter_planes_world(cutter):
            local_plane = _world_plane_to_local(target, plane[0], plane[1])
            if local_plane is None:
                continue

            geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
            result = bmesh.ops.bisect_plane(
                bm,
                geom=geom,
                plane_co=local_plane[0],
                plane_no=local_plane[1],
                clear_inner=False,
                clear_outer=False,
            )

            for element in result.get("geom_cut", ()):
                if isinstance(element, bmesh.types.BMEdge):
                    if not element.seam:
                        marked_edges += 1
                    element.seam = True
                    element.select_set(True)

    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return marked_edges


def _prepare_cutters_for_apply(context, cutters):
    for cutter in cutters:
        _ensure_local_contour_cutter(cutter)
    settings = context.scene.polygroups_object_seam_cutter_settings
    if settings.auto_convert_draw_strokes_on_apply:
        converted_cutters = []
        for stroke in _draw_strokes_from_cutters(cutters):
            cutter = _convert_draw_stroke_to_cutter_path(context, stroke)
            if cutter is not None:
                converted_cutters.append(cutter)
        cutters = [
            cutter
            for cutter in cutters
            if cutter.get(CUTTER_TYPE_PROP) != "DRAW_STROKE"
        ] + converted_cutters
    return cutters


def _apply_cutters_to_mesh(context, target, cutters):
    settings = context.scene.polygroups_object_seam_cutter_settings
    cutters = _prepare_cutters_for_apply(context, cutters)

    grid_cutters = [cutter for cutter in cutters if cutter.get(CUTTER_TYPE_PROP) == "GRID_PLANE"]
    grid_method = getattr(settings, "cutter_grid_apply_method", "BISECT")
    plane_cutters = [cutter for cutter in cutters if cutter.get(CUTTER_TYPE_PROP) == "PLANE"]
    if grid_method == "BISECT":
        plane_cutters.extend(grid_cutters)
    arc_cutters = [cutter for cutter in cutters if cutter.get(CUTTER_TYPE_PROP) == "ARC"]
    boolean_cutters = [
        cutter
        for cutter in cutters
        if cutter.get(CUTTER_TYPE_PROP) in {"PATH", "LOCAL_RING", "LOCAL_CONTOUR"}
    ]

    marked_edges = 0
    if plane_cutters:
        marked_edges += _apply_plane_cutters_to_mesh(target, plane_cutters)
    if arc_cutters:
        marked_edges += _apply_arc_cutters_to_mesh(context, target, arc_cutters)

    apply_method = _cutter_apply_method(context)
    boolean_solver = _cutter_boolean_solver(context)
    for cutter in boolean_cutters:
        if apply_method == "KNIFE":
            marked_edges += _apply_knife_intersect_cutter_to_mesh(
                context,
                target,
                cutter,
                boolean_solver=boolean_solver,
            )
        else:
            marked_edges += _apply_boolean_cutter_to_mesh(
                context,
                target,
                cutter,
                boolean_solidify_thickness=None,
                boolean_solver=boolean_solver,
            )
    if grid_method == "KNIFE_INTERSECT":
        for cutter in grid_cutters:
            marked_edges += _apply_knife_intersect_cutter_to_mesh(
                context, target, cutter, boolean_solver=boolean_solver,
            )

    return marked_edges


def _split_supported_cutters(cutters):
    return [
        cutter
        for cutter in cutters
        if cutter.get(CUTTER_TYPE_PROP) in {"PLANE", "ARC"}
    ]
