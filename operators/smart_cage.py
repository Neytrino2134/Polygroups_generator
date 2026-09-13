"""Adaptive, topology-preserving bake cages with editable Displace weights.

The solver is deliberately conservative: unresolved constraints are reported,
never advertised as a proof of complete enclosure.
"""
import re

import bpy
from mathutils.bvhtree import BVHTree
from ..core.generated_index import generated_collection_info

TAG = "polygroups_smart_cage"
WEIGHTS = "Smart Cage Weights"
HIGH_CONFLICTS = "Smart Cage Highpoly Intersections"
SELF_CONFLICTS = "Smart Cage Self Intersections"
MODIFIER = "Smart Cage Displace"
TRIM = "Smart Cage Extra Clearance"
BASE = "Smart Cage Minimum Clearance"
REDUCE_SELF = "Smart Cage Reduce Self Intersections"
START_WEIGHT = 0.001


def cage_name(target):
    """Insert _Cage before the lowpoly's final .NNN object index."""
    match = re.match(r"^(.*?)(\.\d+)$", target.name)
    if match:
        return f"{match.group(1)}_Cage{match.group(2)}"
    return f"{target.name}_Cage.001"


def cage_collection(target, context):
    collection, _ = generated_collection_info(target)
    return collection or next(iter(target.users_collection), context.collection)


def geometry(context, obj):
    evaluated = obj.evaluated_get(context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        matrix = evaluated.matrix_world
        return ([matrix @ v.co for v in mesh.vertices],
                [tuple(t.vertices) for t in mesh.loop_triangles],
                [tuple(p.vertices) for p in mesh.polygons])
    finally:
        evaluated.to_mesh_clear()


def tree(vertices, triangles):
    return BVHTree.FromPolygons(vertices, triangles, all_triangles=True)


def closed(triangles):
    edges = {}
    for tri in triangles:
        for a, b in zip(tri, tri[1:] + tri[:1]):
            key = tuple(sorted((a, b)))
            edges[key] = edges.get(key, 0) + 1
    return bool(edges) and all(n == 2 for n in edges.values())


def sources_geometry(context, sources):
    vertices, triangles = [], []
    for source in sources:
        points, faces, _ = geometry(context, source)
        offset = len(vertices)
        vertices.extend(points)
        triangles.extend(tuple(i + offset for i in face) for face in faces)
    if not triangles:
        raise ValueError("No highpoly faces")
    return vertices, triangles


def samples(vertices, triangles, limit):
    # Deterministic stratification without materializing millions of centers.
    count = len(vertices) + len(triangles)
    result = []
    for k in range(min(count, limit)):
        index = k * count // min(count, limit)
        if index < len(vertices):
            result.append(vertices[index])
        else:
            a, b, c = triangles[index - len(vertices)]
            result.append((vertices[a] + vertices[b] + vertices[c]) / 3)
    return result


def conflicts(points, triangles, high_tree):
    cage_tree = tree(points, triangles)
    high_pairs = cage_tree.overlap(high_tree)
    self_pairs = [(a, b) for a, b in cage_tree.overlap(cage_tree)
                  if a < b and not set(triangles[a]).intersection(triangles[b])]
    # Folded/degenerate faces are unsafe even when adjacency masks an overlap.
    degenerate = [i for i, (a, b, c) in enumerate(triangles)
                  if (points[b] - points[a]).cross(points[c] - points[a]).length_squared < 1e-24]
    return cage_tree, high_pairs, self_pairs, degenerate


def solve(base, directions, triangles, high_vertices, high_triangles, settings, weight_scales):
    from mathutils import Vector
    lo = Vector(tuple(min(p[i] for p in base) for i in range(3)))
    hi = Vector(tuple(max(p[i] for p in base) for i in range(3)))
    diagonal = max((hi - lo).length, 1e-6)
    margin = max(settings.smart_cage_margin, diagonal * 1e-6)
    maximum = (settings.smart_cage_max or diagonal) - margin
    if maximum <= 0:
        raise ValueError("Maximum offset must be at least the minimum clearance")
    high_tree = tree(high_vertices, high_triangles)
    probes = samples(high_vertices, high_triangles, settings.smart_cage_samples)
    low_tree = tree(base, triangles)
    floors = [START_WEIGHT * scale for scale in weight_scales]
    caps = [min(maximum, scale) for scale in weight_scales]
    if settings.smart_cage_avoid_self:
        for i, (point, normal) in enumerate(zip(base, directions)):
            hit, _, _, distance = low_tree.ray_cast(point + normal * margin * .01, normal, maximum * 2)
            if hit is not None:
                caps[i] = min(caps[i], max(floors[i], distance * .45))
    adjacency = [set() for _ in base]
    for face in triangles:
        for i in face:
            adjacency[i].update(j for j in face if j != i)
    offsets = floors[:]
    best, best_score = offsets[:], None
    for _ in range(settings.smart_cage_iterations + 1):
        points = [p + n * d for p, n, d in zip(base, directions, offsets)]
        bvh, hp, sp, degenerate = conflicts(points, triangles, high_tree)
        requests = offsets[:]
        outside = 0
        total_deficit = 0.0
        for probe in probes:
            location, normal, face, _ = bvh.find_nearest(probe)
            deficit = (probe - location).dot(normal) + margin
            if deficit > margin * .02:
                outside += 1
                total_deficit += deficit
                for i in triangles[face]:
                    projection = directions[i].dot(normal)
                    if projection > .05:
                        requests[i] = max(requests[i], offsets[i] + deficit / projection * .5)
        score = (len(sp) + len(degenerate) if settings.smart_cage_avoid_self else 0,
                 outside + len(hp), total_deficit)
        if best_score is None or score < best_score:
            best_score, best = score, offsets[:]
        if not outside and not hp and not sp and not degenerate:
            break
        for face, _ in hp:
            for i in triangles[face]:
                requests[i] = max(requests[i], offsets[i] + margin)
        if settings.smart_cage_avoid_self:
            for a, b in sp:
                for i in set(triangles[a] + triangles[b]):
                    caps[i] = max(floors[i], min(caps[i], offsets[i] * .8))
        smooth = settings.smart_cage_smoothing
        offsets = [min(caps[i], offsets[i] + weight_scales[i] * .05,
                   max(floors[i], value, value * (1 - smooth) +
                   (sum(requests[j] for j in adjacency[i]) / len(adjacency[i]) if adjacency[i] else value) * smooth))
                   for i, value in enumerate(requests)]
    return best, margin


def _analyze(context, cage, target, sources, settings):
    points, triangles, faces = geometry(context, cage)
    low_points, _, low_faces = geometry(context, target)
    if len(points) != len(low_points) or faces != low_faces:
        raise ValueError("Cage topology differs from evaluated lowpoly; regenerate cage")
    high_vertices, high_triangles = sources_geometry(context, sources)
    bvh, hp, sp, degenerate = conflicts(points, triangles, tree(high_vertices, high_triangles))
    probes = samples(high_vertices, high_triangles, settings.smart_cage_samples)
    high_bad = set(i for face, _ in hp for i in triangles[face])
    self_bad = set()
    for a, b in sp:
        self_bad.update(triangles[a] + triangles[b])
    for face in degenerate:
        self_bad.update(triangles[face])
    flipped = []
    for face, (a, b, c) in enumerate(triangles):
        before = (low_points[b] - low_points[a]).cross(low_points[c] - low_points[a])
        after = (points[b] - points[a]).cross(points[c] - points[a])
        if before.dot(after) <= 0:
            flipped.append(face)
            self_bad.update((a, b, c))
    outside = 0
    clearance = cage.get("smart_cage_margin", settings.smart_cage_margin)
    near = 0
    for probe in probes:
        location, normal, face, _ = bvh.find_nearest(probe)
        signed = (probe - location).dot(normal)
        if signed > 1e-7:
            outside += 1
            high_bad.update(triangles[face])
        if signed + clearance > max(1e-7, clearance * .02):
            near += 1
            high_bad.update(triangles[face])
    low_outside = 0
    for probe in low_points:
        location, normal, face, _ = bvh.find_nearest(probe)
        if (probe - location).dot(normal) >= -1e-8:
            low_outside += 1
            high_bad.update(triangles[face])
    is_closed = closed(triangles)
    status = (f"Sample coverage {100 * (1 - outside / len(probes)):.2f}% | "
              f"HP intersections {len(hp)} | Self {len(sp)} | Clearance {near} | "
              f"Low outside {low_outside} | Folded {len(flipped)} | Degenerate {len(degenerate)}"
              + (" | Open/non-manifold cage" if not is_closed else ""))
    valid = not (outside or near or low_outside or hp or sp or flipped or degenerate) and is_closed
    return high_bad, self_bad, status, valid


def _set_conflict_group(cage, name, indices):
    group = cage.vertex_groups.get(name) or cage.vertex_groups.new(name=name)
    if len(cage.data.vertices):
        group.remove(list(range(len(cage.data.vertices))))
    if indices:
        group.add(sorted(indices), 1.0, "REPLACE")
    return group


def validate(context, cage, target, sources, settings):
    reducer = cage.modifiers.get(REDUCE_SELF)
    if reducer is None:
        group = _set_conflict_group(cage, SELF_CONFLICTS, set())
        reducer = cage.modifiers.new(REDUCE_SELF, "DISPLACE")
        reducer.direction = "NORMAL"
        reducer.mid_level = 0
        reducer.strength = -0.005
        reducer.vertex_group = group.name
    was_visible = reducer.show_viewport
    try:
        reducer.show_viewport = False
        context.view_layer.update()
        _, self_bad, _, _ = _analyze(context, cage, target, sources, settings)
        _set_conflict_group(cage, SELF_CONFLICTS, self_bad)
    finally:
        reducer.show_viewport = was_visible
        context.view_layer.update()
    high_bad, _, status, valid = _analyze(context, cage, target, sources, settings)
    _set_conflict_group(cage, HIGH_CONFLICTS, high_bad)
    settings.smart_cage_status = status
    cage["smart_cage_validation"] = status
    return valid


def generate(context, target, sources, settings):
    if target.get(TAG) or not sources:
        raise ValueError("Select highpoly meshes and make lowpoly active")
    if target.matrix_world.to_3x3().determinant() <= 1e-12:
        raise ValueError("Apply negative scale / correct zero scale on lowpoly before generating")
    evaluated = target.evaluated_get(context.evaluated_depsgraph_get())
    mesh = bpy.data.meshes.new_from_object(evaluated, depsgraph=context.evaluated_depsgraph_get())
    cage = None
    try:
        mesh.calc_loop_triangles()
        matrix = target.matrix_world
        base = [matrix @ v.co for v in mesh.vertices]
        vectors = [matrix.to_3x3() @ v.normal for v in mesh.vertices]
        if not base or not mesh.polygons or any(n.length < 1e-12 for n in vectors):
            raise ValueError("Lowpoly must have faces and valid vertex normals")
        triangles = [tuple(t.vertices) for t in mesh.loop_triangles]
        high_vertices, high_triangles = sources_geometry(context, sources)
        # Keep the evaluated lowpoly as an untouched snapshot. Displace remains live.
        cage = bpy.data.objects.new(cage_name(target), mesh)
        cage_collection(target, context).objects.link(cage)
        cage.matrix_world = matrix.copy()
        cage[TAG] = True
        cage["smart_cage_target"] = target.name
        cage["smart_cage_target_object"] = target
        cage["smart_cage_sources"] = {str(i): source for i, source in enumerate(sources)}
        cage.display_type = "WIRE"
        cage.show_in_front = True
        cage.hide_render = True
        cage.color = (0.1, 0.8, 1.0, 1.0)
        margin = settings.smart_cage_margin
        # A separate non-destructive baseline lets adaptive weights really start
        # at .001 without encoding the baseline into those editable weights.
        baseline_group = cage.vertex_groups.new(name="Smart Cage Baseline")
        baseline_strength = max(margin / n.length for n in vectors)
        for i, n in enumerate(vectors):
            baseline_group.add([i], margin / n.length / baseline_strength, "REPLACE")
        baseline = cage.modifiers.new(BASE, "DISPLACE")
        baseline.direction = "NORMAL"
        baseline.mid_level = 0
        baseline.strength = baseline_strength
        baseline.vertex_group = baseline_group.name
        context.view_layer.update()
        evaluated_cage = cage.evaluated_get(context.evaluated_depsgraph_get())
        baseline_mesh = evaluated_cage.to_mesh()
        try:
            base = [matrix @ v.co for v in baseline_mesh.vertices]
            vectors = [matrix.to_3x3() @ v.normal for v in baseline_mesh.vertices]
        finally:
            evaluated_cage.to_mesh_clear()
        strength = settings.smart_cage_started_clearance
        scales = [strength * n.length for n in vectors]
        offsets, margin = solve(base, [n.normalized() for n in vectors], triangles,
                                high_vertices, high_triangles, settings, scales)
        group = cage.vertex_groups.new(name=WEIGHTS)
        group.add(list(range(len(mesh.vertices))), START_WEIGHT, "REPLACE")
        for i, (value, scale) in enumerate(zip(offsets, scales)):
            group.add([i], min(1.0, max(START_WEIGHT, value / scale)), "REPLACE")
        mod = cage.modifiers.new(MODIFIER, "DISPLACE")
        mod.direction = "NORMAL"
        mod.mid_level = 0
        mod.strength = strength
        mod.vertex_group = group.name
        trim = cage.modifiers.new(TRIM, "DISPLACE")
        trim.direction = "NORMAL"
        trim.mid_level = 0
        trim.strength = 0
        self_group = cage.vertex_groups.new(name=SELF_CONFLICTS)
        reducer = cage.modifiers.new(REDUCE_SELF, "DISPLACE")
        reducer.direction = "NORMAL"
        reducer.mid_level = 0
        reducer.strength = -0.005
        reducer.vertex_group = self_group.name
        cage["smart_cage_margin"] = margin
        context.view_layer.update()
        validate(context, cage, target, sources, settings)
        settings.smart_cage_object = cage
        settings.use_smart_cage = True
        return cage
    except Exception:
        if cage is not None:
            bpy.data.objects.remove(cage, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        raise


def prepare_bake(context, target, sources, settings, report):
    try:
        if settings.autogenerate_smart_cage:
            generate(context, target, sources, settings)
        cage = settings.smart_cage_object
        if cage is None or not cage.get(TAG) or cage.get("smart_cage_target_object") != target:
            raise ValueError("Generate a Smart Cage for this lowpoly first")
        for obj in (target, cage, *sources):
            for mod in obj.modifiers:
                if mod.show_viewport != mod.show_render or (mod.type == "SUBSURF" and mod.levels != mod.render_levels):
                    raise ValueError(f"Match viewport/render modifier settings on {obj.name} before validating for bake")
        if not validate(context, cage, target, sources, settings):
            raise ValueError("Smart Cage has unresolved constraints. " + settings.smart_cage_status)
        return True
    except (ValueError, RuntimeError) as error:
        settings.smart_cage_status = str(error)
        report({"ERROR"}, str(error))
        return False


class OBJECT_OT_polygroups_generate_smart_cage(bpy.types.Operator):
    bl_idname = "object.polygroups_generate_smart_cage"
    bl_label = "Generate Smart Cage Object"
    bl_description = "Создать cage для активного lowpoly; при одном выделенном lowpoly найти highpoly по имени в той же Generated.N"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and obj.mode == "OBJECT" and not obj.get(TAG)

    def execute(self, context):
        from .baking import _source_meshes
        from .safety_checks import auto_select_matching_highpoly, report_missing_matching_highpoly
        settings = context.scene.polygroups_baking_settings
        target = context.active_object
        sources = _source_meshes(context, target)
        if not sources and len([obj for obj in context.selected_objects if obj.type == "MESH"]) == 1:
            source, expected_name, collection = auto_select_matching_highpoly(context, target)
            if source is None:
                report_missing_matching_highpoly(self, context, target, expected_name, collection)
                return {"CANCELLED"}
            sources = [source]
        try:
            generate(context, target, sources, settings)
        except (ValueError, RuntimeError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report({"INFO"}, settings.smart_cage_status)
        return {"FINISHED"}


class OBJECT_OT_polygroups_validate_smart_cage(bpy.types.Operator):
    bl_idname = "object.polygroups_validate_smart_cage"
    bl_label = "Validate Smart Cage"
    bl_description = "Проверить покрытие и пересечения после правок; проблемные вершины распределяются по группам Highpoly и Self Intersections"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.polygroups_baking_settings
        cage = settings.smart_cage_object
        target = cage.get("smart_cage_target_object") if cage else None
        if target is None:
            self.report({"ERROR"}, "No Smart Cage target")
            return {"CANCELLED"}
        try:
            sources = [obj for obj in cage.get("smart_cage_sources", {}).values() if obj is not None]
            valid = validate(context, cage, target, sources, settings)
        except (ValueError, RuntimeError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report({"INFO"} if valid else {"WARNING"}, settings.smart_cage_status)
        return {"FINISHED"}
