"""Topology Guard: automatic Boundary + Longitudinal seams for non-disk charts."""
import bmesh
import bpy

from ..core.chart_cuts import GuardOptions, kind_counts, topology_guard, analyze_charts
from ..core.chart_topology import charts
from ..core.knot_repair import collapse_knots, find_knots
from ..core.smart_seam_routing import route_seams
from ..pin_edges import pin_layer, set_pinned


def guard_options(settings):
    return GuardOptions(
        fix_handles=settings.topology_guard_fix_handles,
        fix_annuli=settings.topology_guard_fix_annuli,
        fix_closed=settings.topology_guard_fix_closed,
        fix_necks=settings.topology_guard_fix_necks,
        hole_ratio=settings.topology_guard_hole_ratio,
        lip_angle=settings.topology_guard_lip_angle,
        max_flare=settings.topology_guard_max_flare,
        sharp_preference=settings.topology_guard_sharp_preference,
        neck_angle=settings.topology_guard_neck_angle,
        neck_elongation=settings.topology_guard_neck_elongation,
        neck_max_share=settings.topology_guard_neck_max_share,
        tube_tolerance=settings.topology_guard_tube_tolerance,
        cup_min_height=settings.topology_guard_cup_min_height,
        max_passes=12,
        fix_bridges=settings.topology_guard_fix_bridges,
        bridge_max_edges=settings.topology_guard_bridge_max_edges,
        bridge_min_share=settings.topology_guard_bridge_min_share,
    )


def scope_faces(bm, selected_only):
    """All visible faces, or whole charts touched by the selection."""
    visible = [f for f in bm.faces if not f.hide]
    if not selected_only:
        return set(visible)
    touched = set()
    for chart in charts(bm, visible):
        if any(f.select for f in chart):
            touched.update(chart)
    return touched


def run_guard(bm, faces, settings, pin=None):
    """Mark guard seams on ``faces`` and smooth them. Returns (result, created_edges, generated)."""
    initial = {e for e in bm.edges if e.seam}
    result = topology_guard(bm, faces, guard_options(settings))
    created = 0
    generated = result.rings | result.longitudinal | result.bridges
    if generated and settings.topology_guard_create_edges:
        routed = set(result.longitudinal)
        if settings.topology_guard_smooth_rings:
            routed |= result.rings
        selection = {f for f in bm.faces if f.select}
        for face in bm.faces:
            face.select_set(face in faces)
        protected = {e for e in bm.edges if e.seam and e not in routed}
        _rerouted, created = route_seams(
            bm, settings.topology_guard_neck_angle, create_edges=True,
            turn_weight=6.0, corridor_width=2.5, edge_preference=0.35,
            ridge_weight=settings.topology_guard_sharp_preference, protected=protected)
        for face in bm.faces:
            face.select_set(face in selection)
        if created or _rerouted:
            # Smoothing must never reopen a chart; re-check the split faces as well.
            pool = {f for f in bm.faces if not f.hide and (f in faces or any(
                e.seam and e not in initial for e in f.edges))}
            topology_guard(bm, pool, guard_options(settings)._replace(fix_necks=False))
    generated = {e for e in bm.edges if e.seam and e not in initial}
    if generated and (settings.topology_guard_pin_generated if pin is None else pin):
        bm.edges.index_update()
        indices = {e.index for e in generated}
        # Adding a layer reallocates edge data; look the edges up again afterwards.
        layer = pin_layer(bm, True)
        bm.edges.ensure_lookup_table()
        generated = {bm.edges[i] for i in indices}
        set_pinned(generated, layer)
    return result, created, generated


def guard_charts(bm, generated, faces):
    """Faces of the charts that received generated seams (diagonal splits included)."""
    pool = {f for f in bm.faces if not f.hide and (f in faces or any(
        e in generated for e in f.edges))}
    return {f for chart in charts(bm, pool) if any(e in generated for f2 in chart for e in f2.edges)
            for f in chart}


def unwrap_faces(context, obj, face_indices, pack=False):
    """Angle Based unwrap of the given faces, keeping the edit selection."""
    if obj.data.uv_layers.active is None:
        obj.data.uv_layers.new(name="UVMap")
    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    selection = {f.index for f in bm.faces if f.select}
    mode = tuple(context.tool_settings.mesh_select_mode)
    try:
        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="FACE")
        for face in bm.faces:
            face.select_set(face.index in face_indices)
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=0.001)
        if pack:
            bpy.ops.mesh.select_all(action="SELECT")
            try:
                bpy.ops.uv.select_all(action="SELECT")
            except Exception:
                pass
            bpy.ops.uv.average_islands_scale()
            bpy.ops.uv.pack_islands()
    finally:
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        for face in bm.faces:
            face.select_set(face.index in selection)
        context.tool_settings.mesh_select_mode = mode
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)


def collapse_scope_knots(bm, settings, selected_only):
    """Collapse knots (pinched holes, folded faces) in the guard scope. Returns the count."""
    if not settings.topology_guard_collapse_knots:
        return 0
    faces = scope_faces(bm, selected_only)
    merged = collapse_knots(bm, faces, settings.topology_guard_knot_max_verts)
    if merged:
        bm.normal_update()
    return len(merged)


def apply_topology_guard(context, obj, settings, selected_only, unwrap=True, pin=None):
    """Edit Mode entry point shared with Smart UV Repair. Returns (result, created, generated_count)."""
    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.index_update()
    bm.normal_update()
    knots = collapse_scope_knots(bm, settings, selected_only)
    faces = scope_faces(bm, selected_only)
    result, created, generated = run_guard(bm, faces, settings, pin)
    result = result._replace(knots=knots)
    bm.faces.index_update()
    bm.edges.index_update()
    fixed = {f.index for f in guard_charts(bm, generated, faces)} if generated else set()
    generated_indices = {e.index for e in generated}
    changed = bool(created or knots)
    bmesh.update_edit_mesh(obj.data, loop_triangles=changed, destructive=changed)
    if generated and settings.topology_guard_smart_relax:
        from .relax_seams import relax_seams
        prep = context.scene.polygroups_seam_preparation_settings
        target = bmesh.from_edit_mesh(obj.data)
        target.edges.ensure_lookup_table()
        relax_seams(context, "SMART", prep.seam_relax_iterations, prep.seam_relax_corner_angle,
                    prep.seam_relax_protection_radius, prep.seam_relax_use_corner_angle,
                    select_result=False,
                    relax_edges={target.edges[i] for i in generated_indices})
    if unwrap and fixed:
        unwrap_faces(context, obj, fixed, pack=settings.topology_guard_pack)
    return result, created, len(generated_indices)


def summary(entries):
    counts = kind_counts(entries)
    bad = {k: v for k, v in counts.items() if k != "DISK"}
    if not bad:
        return "all disks"
    return ", ".join(f"{v} {k.lower()}" for k, v in sorted(bad.items()))


class MESH_OT_polygroups_topology_guard(bpy.types.Operator):
    bl_idname = "mesh.polygroups_topology_guard"
    bl_label = "Topology Guard"
    bl_description = ("Find charts that are not disks (tubes, through holes, handles, closed parts, "
                      "protrusions) and add boundary rings plus longitudinal seams")
    bl_options = {"REGISTER", "UNDO"}

    action: bpy.props.EnumProperty(name="Action", items=(
        ("APPLY", "Fix Charts", "Add boundary and longitudinal seams"),
        ("SELECT", "Select Problem Charts", "Select charts that are not disks without changing seams"),
    ), default="APPLY")

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and obj.mode == "EDIT"

    def execute(self, context):
        obj = context.active_object
        settings = context.scene.polygroups_seam_finalization_settings
        if self.action == "SELECT":
            bm = bmesh.from_edit_mesh(obj.data)
            faces = scope_faces(bm, settings.topology_guard_selected_only)
            entries = analyze_charts(bm, faces, settings.topology_guard_hole_ratio)
            problem = {f for chart, kind in entries if kind != "DISK" for f in chart}
            knots = find_knots(bm, faces, settings.topology_guard_knot_max_verts) \
                if settings.topology_guard_collapse_knots else []
            for knot in knots:
                problem.update(knot)
            for face in bm.faces:
                face.select_set(face in problem)
            context.tool_settings.mesh_select_mode = (False, False, True)
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
            self.report({"INFO"}, f"{len(entries)} charts: {summary(entries)}; {len(knots)} knots")
            return {"FINISHED"}
        result, created, generated = apply_topology_guard(
            context, obj, settings, settings.topology_guard_selected_only,
            unwrap=settings.topology_guard_unwrap)
        self.report({"INFO"}, (
            f"Before: {summary(result.before)}; after: {summary(result.after)}. "
            f"{generated} seam edges ({len(result.rings)} ring, {len(result.longitudinal)} longitudinal, "
            f"{len(result.bridges)} bridge before smoothing), {created} diagonal edges, "
            f"{result.knots} knots collapsed"))
        return {"FINISHED"}
