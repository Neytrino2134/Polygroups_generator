from collections import defaultdict

import bpy
from mathutils import Vector


ZERO_AREA_EPSILON = 0.00000001
DUPLICATE_VERTEX_EPSILON = 0.00001
STATUS_OK = "Mesh OK"
STATUS_NOT_CHECKED = "Not checked"


def _active_mesh(context):
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        return None
    return obj


def _ensure_object_mode(obj):
    if obj.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def _edge_face_data(mesh):
    edge_to_faces = defaultdict(list)
    edge_directions = defaultdict(list)

    for polygon in mesh.polygons:
        vertices = list(polygon.vertices)
        for index, vertex_a in enumerate(vertices):
            vertex_b = vertices[(index + 1) % len(vertices)]
            key = tuple(sorted((vertex_a, vertex_b)))
            edge_to_faces[key].append(polygon.index)
            edge_directions[key].append((vertex_a, vertex_b))

    return edge_to_faces, edge_directions


def _count_boundary_loops(mesh, edge_to_faces):
    boundary_edges = {
        key
        for key, faces in edge_to_faces.items()
        if len(faces) == 1
    }
    if not boundary_edges:
        return 0

    vertex_to_edges = defaultdict(set)
    for edge in boundary_edges:
        vertex_a, vertex_b = edge
        vertex_to_edges[vertex_a].add(edge)
        vertex_to_edges[vertex_b].add(edge)

    visited = set()
    loops = 0
    for edge in boundary_edges:
        if edge in visited:
            continue

        loops += 1
        stack = [edge]
        visited.add(edge)
        while stack:
            current = stack.pop()
            for vertex_index in current:
                for next_edge in vertex_to_edges[vertex_index]:
                    if next_edge in visited:
                        continue
                    visited.add(next_edge)
                    stack.append(next_edge)

    return loops


def _inconsistent_normal_edge_count(edge_to_faces, edge_directions):
    count = 0
    for key, faces in edge_to_faces.items():
        if len(faces) != 2:
            continue

        direction_a, direction_b = edge_directions[key][:2]
        if direction_a == direction_b:
            count += 1

    return count


def _inward_normal_face_count(obj):
    mesh = obj.data
    if not mesh.polygons:
        return 0

    center = sum((vertex.co for vertex in mesh.vertices), Vector()) / len(mesh.vertices)
    count = 0
    for polygon in mesh.polygons:
        if polygon.area <= ZERO_AREA_EPSILON:
            continue
        direction = polygon.center - center
        if direction.length <= ZERO_AREA_EPSILON:
            continue
        if polygon.normal.dot(direction.normalized()) < -0.25:
            count += 1

    return count


def _duplicate_vertex_count(mesh):
    buckets = defaultdict(int)
    for vertex in mesh.vertices:
        key = tuple(round(component / DUPLICATE_VERTEX_EPSILON) for component in vertex.co)
        buckets[key] += 1

    return sum(count - 1 for count in buckets.values() if count > 1)


def _thin_protrusion_faces(mesh, edge_to_faces):
    face_boundary_counts = defaultdict(int)
    face_complex_counts = defaultdict(int)
    for key, faces in edge_to_faces.items():
        if len(faces) == 1:
            face_boundary_counts[faces[0]] += 1
        elif len(faces) > 2:
            for face_index in faces:
                face_complex_counts[face_index] += 1

    candidates = set()
    face_indices = set(face_boundary_counts) | set(face_complex_counts)
    for face_index in face_indices:
        boundary_count = face_boundary_counts[face_index]
        complex_count = face_complex_counts[face_index]
        polygon = mesh.polygons[face_index]
        if polygon.area <= ZERO_AREA_EPSILON:
            continue

        linked_faces = set()
        for edge_key, faces in edge_to_faces.items():
            if face_index not in faces:
                continue
            linked_faces.update(face for face in faces if face != face_index)

        # Open fin/T-like polygons are usually weakly attached to the mesh.
        # Plain border faces on a valid open shell should not be reported.
        if boundary_count >= 2 and len(linked_faces) <= 1:
            candidates.add(face_index)
        elif complex_count and len(polygon.vertices) <= 4 and len(linked_faces) <= 2:
            candidates.add(face_index)

    return candidates


def _fixable_issue_total(result):
    return sum(
        1
        for key in (
            "normal_issues",
            "ngons",
            "nonmanifold_edges",
            "boundary_loops",
            "loose_geometry",
            "zero_area_faces",
            "duplicate_vertices",
            "thin_protrusions",
        )
        if result.get(key, 0) > 0
    )


def analyze_mesh(obj):
    mesh = obj.data
    mesh.update(calc_edges=True)
    edge_to_faces, edge_directions = _edge_face_data(mesh)

    used_edges = set(edge_to_faces.keys())
    loose_vertices = [
        vertex.index
        for vertex in mesh.vertices
        if vertex.index not in {index for edge in mesh.edges for index in edge.vertices}
    ]
    loose_edges = [
        edge.index
        for edge in mesh.edges
        if tuple(sorted(edge.vertices)) not in used_edges
    ]
    complex_nonmanifold_edges = [
        edge.index
        for edge in mesh.edges
        if len(edge_to_faces.get(tuple(sorted(edge.vertices)), [])) > 2
    ]
    boundary_edges = [
        edge.index
        for edge in mesh.edges
        if len(edge_to_faces.get(tuple(sorted(edge.vertices)), [])) == 1
    ]
    boundary_loops = _count_boundary_loops(mesh, edge_to_faces)
    inconsistent_normals = _inconsistent_normal_edge_count(edge_to_faces, edge_directions)
    inward_normals = _inward_normal_face_count(obj) if not boundary_edges else 0
    loose_vertex_count = len(loose_vertices)
    loose_edge_count = len(loose_edges)

    result = {
        "inconsistent_normals": inconsistent_normals,
        "inward_normals": inward_normals,
        "normal_issues": inconsistent_normals + inward_normals,
        "ngons": sum(1 for polygon in mesh.polygons if len(polygon.vertices) > 4),
        "nonmanifold_edges": len(complex_nonmanifold_edges),
        "boundary_edges": len(boundary_edges),
        "boundary_loops": boundary_loops,
        "loose_vertices": loose_vertex_count,
        "loose_edges": loose_edge_count,
        "loose_geometry": loose_vertex_count + loose_edge_count,
        "zero_area_faces": sum(1 for polygon in mesh.polygons if polygon.area <= ZERO_AREA_EPSILON),
        "duplicate_vertices": _duplicate_vertex_count(mesh),
        "thin_protrusions": len(_thin_protrusion_faces(mesh, edge_to_faces)),
    }
    return result


def _store_result(settings, result):
    settings.mesh_check_inconsistent_normals = result["inconsistent_normals"]
    settings.mesh_check_inward_normals = result["inward_normals"]
    settings.mesh_check_ngons = result["ngons"]
    settings.mesh_check_nonmanifold_edges = result["nonmanifold_edges"]
    settings.mesh_check_boundary_edges = result["boundary_edges"]
    settings.mesh_check_boundary_loops = result["boundary_loops"]
    settings.mesh_check_loose_vertices = result["loose_vertices"]
    settings.mesh_check_loose_edges = result["loose_edges"]
    settings.mesh_check_zero_area_faces = result["zero_area_faces"]
    settings.mesh_check_duplicate_vertices = result["duplicate_vertices"]
    settings.mesh_check_thin_protrusions = result["thin_protrusions"]

    total = _fixable_issue_total(result)
    if total == 0:
        settings.mesh_check_status = STATUS_OK
    else:
        settings.mesh_check_status = f"Found {total} issue(s)"


def _refresh_mesh_check(context, obj, fixed_message=None):
    settings = context.scene.polygroups_mesh_finalization_settings
    result = analyze_mesh(obj)
    total = _fixable_issue_total(result)
    _store_result(settings, result)
    if fixed_message:
        settings.mesh_check_status = fixed_message if total else f"{fixed_message} - Mesh OK"
    return result


def _fix_operator_finished(context, obj, previous_result, message):
    new_result = _refresh_mesh_check(context, obj)
    before = _fixable_issue_total(previous_result)
    after = _fixable_issue_total(new_result)
    fixed_count = max(0, before - after)
    settings = context.scene.polygroups_mesh_finalization_settings
    settings.mesh_check_status = f"Fixed {fixed_count} issue(s)" if fixed_count else "No issues fixed"
    if after == 0 and fixed_count:
        settings.mesh_check_status += " - Mesh OK"
    return f"{message}. Fixed {fixed_count} issue(s)"


def _clear_mesh_selection(mesh):
    for vertex in mesh.vertices:
        vertex.select = False
    for edge in mesh.edges:
        edge.select = False
    for polygon in mesh.polygons:
        polygon.select = False


def _select_faces(context, obj, face_indices):
    _ensure_object_mode(obj)
    mesh = obj.data
    _clear_mesh_selection(mesh)
    for face_index in face_indices:
        mesh.polygons[face_index].select = True
    mesh.update()
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="FACE")


def _select_edges(context, obj, edge_indices):
    _ensure_object_mode(obj)
    mesh = obj.data
    _clear_mesh_selection(mesh)
    for edge_index in edge_indices:
        mesh.edges[edge_index].select = True
    mesh.update()
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="EDGE")


def _delete_faces_by_indices(context, obj, face_indices):
    if not face_indices:
        return 0

    _select_faces(context, obj, face_indices)
    bpy.ops.mesh.delete(type="FACE")
    bpy.ops.object.mode_set(mode="OBJECT")
    return len(face_indices)


class OBJECT_OT_polygroups_check_mesh(bpy.types.Operator):
    bl_idname = "object.polygroups_check_mesh"
    bl_label = "Check Mesh"
    bl_description = "Analyze the active mesh for common export problems"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_mesh(context) is not None

    def execute(self, context):
        obj = _active_mesh(context)
        _ensure_object_mode(obj)
        result = analyze_mesh(obj)
        settings = context.scene.polygroups_mesh_finalization_settings
        _store_result(settings, result)

        if settings.mesh_check_status == STATUS_OK:
            self.report({"INFO"}, "Mesh OK: no issues found")
        else:
            self.report({"WARNING"}, settings.mesh_check_status)
        return {"FINISHED"}


class OBJECT_OT_polygroups_fix_mesh_normals(bpy.types.Operator):
    bl_idname = "object.polygroups_fix_mesh_normals"
    bl_label = "Fix Normals"
    bl_description = "Recalculate normals outside on the active mesh"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_mesh(context) is not None

    def execute(self, context):
        obj = _active_mesh(context)
        previous_result = analyze_mesh(obj)
        _ensure_object_mode(obj)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="FACE")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode="OBJECT")
        message = _fix_operator_finished(
            context,
            obj,
            previous_result,
            "Recalculated normals outside",
        )
        self.report({"INFO"}, message)
        return {"FINISHED"}


class OBJECT_OT_polygroups_triangulate_ngons(bpy.types.Operator):
    bl_idname = "object.polygroups_triangulate_ngons"
    bl_label = "Triangulate N-gons"
    bl_description = "Triangulate faces with more than four vertices"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_mesh(context) is not None

    def execute(self, context):
        obj = _active_mesh(context)
        previous_result = analyze_mesh(obj)
        _ensure_object_mode(obj)
        ngon_faces = [polygon.index for polygon in obj.data.polygons if len(polygon.vertices) > 4]
        if not ngon_faces:
            self.report({"INFO"}, "No n-gons found")
            return {"CANCELLED"}

        _select_faces(context, obj, ngon_faces)
        bpy.ops.mesh.quads_convert_to_tris(quad_method="BEAUTY", ngon_method="BEAUTY")
        bpy.ops.object.mode_set(mode="OBJECT")
        message = _fix_operator_finished(
            context,
            obj,
            previous_result,
            f"Triangulated {len(ngon_faces)} n-gon face(s)",
        )
        self.report({"INFO"}, message)
        return {"FINISHED"}


class OBJECT_OT_polygroups_fill_nonmanifold(bpy.types.Operator):
    bl_idname = "object.polygroups_fill_nonmanifold"
    bl_label = "Fill Non-Manifold"
    bl_description = "Try to fill boundary holes on the active mesh"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_mesh(context) is not None

    def execute(self, context):
        obj = _active_mesh(context)
        previous_result = analyze_mesh(obj)
        _ensure_object_mode(obj)
        edge_to_faces, _edge_directions = _edge_face_data(obj.data)
        boundary_edges = [
            edge.index
            for edge in obj.data.edges
            if len(edge_to_faces.get(tuple(sorted(edge.vertices)), [])) == 1
        ]
        if not boundary_edges:
            self.report({"INFO"}, "No boundary holes found")
            return {"CANCELLED"}

        _select_edges(context, obj, boundary_edges)
        try:
            bpy.ops.mesh.fill()
        except RuntimeError as error:
            self.report({"WARNING"}, f"Fill failed: {error}")
            return {"CANCELLED"}
        bpy.ops.object.mode_set(mode="OBJECT")
        message = _fix_operator_finished(
            context,
            obj,
            previous_result,
            f"Filled boundary selection from {len(boundary_edges)} edge(s)",
        )
        self.report({"INFO"}, message)
        return {"FINISHED"}


class OBJECT_OT_polygroups_delete_loose_geometry(bpy.types.Operator):
    bl_idname = "object.polygroups_delete_loose_geometry"
    bl_label = "Delete Loose"
    bl_description = "Delete loose vertices and edges from the active mesh"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_mesh(context) is not None

    def execute(self, context):
        obj = _active_mesh(context)
        previous_result = analyze_mesh(obj)
        _ensure_object_mode(obj)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        try:
            bpy.ops.mesh.delete_loose()
        except RuntimeError as error:
            self.report({"WARNING"}, f"Delete loose failed: {error}")
            return {"CANCELLED"}
        bpy.ops.object.mode_set(mode="OBJECT")
        message = _fix_operator_finished(
            context,
            obj,
            previous_result,
            "Deleted loose geometry",
        )
        self.report({"INFO"}, message)
        return {"FINISHED"}


class OBJECT_OT_polygroups_select_thin_protrusions(bpy.types.Operator):
    bl_idname = "object.polygroups_select_thin_protrusions"
    bl_label = "Select Thin Protrusions"
    bl_description = "Select open fin-like faces connected by narrow boundaries"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_mesh(context) is not None

    def execute(self, context):
        obj = _active_mesh(context)
        _ensure_object_mode(obj)
        edge_to_faces, _edge_directions = _edge_face_data(obj.data)
        face_indices = sorted(_thin_protrusion_faces(obj.data, edge_to_faces))
        if not face_indices:
            self.report({"INFO"}, "No thin protrusion candidates found")
            return {"CANCELLED"}

        _select_faces(context, obj, face_indices)
        self.report({"INFO"}, f"Selected {len(face_indices)} thin protrusion candidate face(s)")
        return {"FINISHED"}


class OBJECT_OT_polygroups_delete_thin_protrusions(bpy.types.Operator):
    bl_idname = "object.polygroups_delete_thin_protrusions"
    bl_label = "Delete Thin Protrusions"
    bl_description = "Delete detected open fin-like protrusion faces"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_mesh(context) is not None

    def execute(self, context):
        obj = _active_mesh(context)
        previous_result = analyze_mesh(obj)
        result = bpy.ops.object.polygroups_select_thin_protrusions()
        if "FINISHED" not in result:
            return result
        try:
            bpy.ops.mesh.delete(type="FACE")
        except RuntimeError as error:
            self.report({"WARNING"}, f"Delete protrusions failed: {error}")
            return {"CANCELLED"}
        bpy.ops.object.mode_set(mode="OBJECT")
        message = _fix_operator_finished(
            context,
            obj,
            previous_result,
            "Deleted thin protrusion candidate faces",
        )
        self.report({"INFO"}, message)
        return {"FINISHED"}


class OBJECT_OT_polygroups_clean_mesh(bpy.types.Operator):
    bl_idname = "object.polygroups_clean_mesh"
    bl_label = "Clean Mesh"
    bl_description = "Merge duplicate vertices, delete loose geometry, and recalculate normals"
    bl_options = {"UNDO"}

    merge_distance: bpy.props.FloatProperty(
        name="Merge Distance",
        default=DUPLICATE_VERTEX_EPSILON,
        min=0.0,
        precision=6,
    )

    @classmethod
    def poll(cls, context):
        return _active_mesh(context) is not None

    def execute(self, context):
        obj = _active_mesh(context)
        previous_result = analyze_mesh(obj)
        _ensure_object_mode(obj)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.remove_doubles(threshold=self.merge_distance)
        try:
            bpy.ops.mesh.delete_loose()
        except RuntimeError:
            pass
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode="OBJECT")

        edge_to_faces, _edge_directions = _edge_face_data(obj.data)
        protrusion_faces = sorted(_thin_protrusion_faces(obj.data, edge_to_faces))
        deleted_protrusions = _delete_faces_by_indices(context, obj, protrusion_faces)

        cleanup_message = "Cleaned mesh"
        if deleted_protrusions:
            cleanup_message = f"Cleaned mesh and deleted {deleted_protrusions} protrusion face(s)"
        message = _fix_operator_finished(
            context,
            obj,
            previous_result,
            cleanup_message,
        )
        self.report({"INFO"}, message)
        return {"FINISHED"}


class OBJECT_OT_polygroups_create_mesh_backup(bpy.types.Operator):
    bl_idname = "object.polygroups_create_mesh_backup"
    bl_label = "Create BKP"
    bl_description = "Create a hidden backup copy of the active mesh object"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_mesh(context) is not None

    def execute(self, context):
        obj = _active_mesh(context)
        _ensure_object_mode(obj)

        backup = obj.copy()
        backup.data = obj.data.copy()
        backup.animation_data_clear()
        backup.name = f"{obj.name}_BKP"
        backup.data.name = f"{obj.data.name}_BKP"

        collections = obj.users_collection or (context.scene.collection,)
        for collection in collections:
            collection.objects.link(backup)

        backup.hide_viewport = True
        backup.hide_render = True
        try:
            backup.hide_set(True)
        except RuntimeError:
            pass

        self.report({"INFO"}, f"Created hidden backup: {backup.name}")
        return {"FINISHED"}
