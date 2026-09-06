"""Generate seams from large geometric surface regions without changing UVs."""
import bpy
import bmesh
from ..core.smart_seams import segment_surfaces
from ..core.smart_seam_routing import route_seams
from ..pin_edges import pin_layer, is_pinned, set_pinned

TOOL_ID = "polygroups_generator.smart_seams_generator_tool"


def select_linked_faces_by_seam(bm, select_mode=(True, True, True)):
    """Extend any vertex/edge/face selection through non-seam face adjacency."""
    use_vert, use_edge, use_face = select_mode
    seeds = ({face for face in bm.faces if face.select and not face.hide}
             if use_face else set())
    if use_edge:
        seeds.update(face for edge in bm.edges if edge.select and not edge.hide
                     for face in edge.link_faces if not face.hide)
    if use_vert:
        seeds.update(face for vert in bm.verts if vert.select and not vert.hide
                     for face in vert.link_faces if not face.hide)
    if not seeds:
        return set()

    linked = set(seeds)
    stack = list(seeds)
    while stack:
        face = stack.pop()
        for edge in face.edges:
            if edge.seam or edge.hide:
                continue
            for neighbor in edge.link_faces:
                if neighbor not in linked and not neighbor.hide:
                    linked.add(neighbor)
                    stack.append(neighbor)

    for face in linked:
        face.select_set(True)
    bm.select_flush_mode()
    return linked


class MESH_OT_polygroups_mark_smart_angle_seams(bpy.types.Operator):
    bl_idname = "mesh.polygroups_mark_smart_angle_seams"
    bl_label = "Generate Smart Seams"
    bl_description = "Select linked faces bounded by seams, then find broad surface regions and generate seams"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return (context.mode == "EDIT_MESH" and context.active_object is not None
                and context.active_object.type == "MESH" and len(context.objects_in_mode) == 1)

    def execute(self, context):
        obj = context.active_object
        settings = context.scene.polygroups_seam_preparation_settings
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.index_update()
        bm.normal_update()
        pins = pin_layer(bm, settings.smart_seam_pin_generated)
        initial_seams = {edge for edge in bm.edges if edge.seam}
        selected = select_linked_faces_by_seam(
            bm, tuple(context.tool_settings.mesh_select_mode))
        if not selected:
            self.report({'WARNING'}, "Select at least one vertex, edge, or face")
            return {'CANCELLED'}
        labels = segment_surfaces(bm, selected, settings.smart_seam_angle_limit,
                                  settings.smart_seam_filter_iterations,
                                  settings.smart_seam_min_area,
                                  settings.smart_seam_smoothness)
        region_count = len(set(labels.values()))
        protected = {e for e in bm.edges if is_pinned(e, pins)}
        if not settings.smart_seam_replace:
            protected.update(e for e in bm.edges if e.seam)
        marked = 0
        for edge in bm.edges:
            chosen = [face for face in edge.link_faces if face in selected]
            if not chosen or edge.hide:
                continue
            boundary = (len(chosen) != len(edge.link_faces) or len(edge.link_faces) != 2
                        or len({labels[f] for f in chosen}) > 1)
            if boundary:
                marked += not edge.seam
                edge.seam = True
            elif settings.smart_seam_replace and edge not in protected:
                edge.seam = False
        rerouted, cuts = route_seams(
            bm, settings.smart_seam_angle_limit,
            create_edges=settings.smart_seam_create_edges,
            turn_weight=settings.smart_seam_path_turn,
            corridor_width=settings.smart_seam_path_corridor,
            edge_preference=settings.smart_seam_edge_preference,
            protected=protected)
        if settings.smart_seam_pin_generated:
            # Routing can move or create seam edges after the first marking pass.
            set_pinned((edge for edge in bm.edges if edge.seam and edge not in initial_seams
                        and any(face in selected for face in edge.link_faces)), pins)
        bmesh.update_edit_mesh(obj.data, loop_triangles=bool(cuts), destructive=bool(cuts))
        self.report({'INFO'}, f"Generated {region_count} surface regions; marked {marked} seam edges; rerouted {rerouted} paths; created {cuts} diagonal edges")
        return {'FINISHED'}


class MESH_OT_polygroups_smart_seams_generator_click(bpy.types.Operator):
    bl_idname = "mesh.polygroups_smart_seams_generator_click"
    bl_label = "Generate Smart Seams from Point"
    bl_description = "Pick a vertex, select its seam-bounded island, and generate smart seams"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.type == "MESH"
                and context.mode == "EDIT_MESH"
                and context.area is not None and context.area.type == "VIEW_3D"
                and context.region is not None and context.region.type == "WINDOW")

    def invoke(self, context, event):
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        old_mode = tuple(context.tool_settings.mesh_select_mode)
        flags = [(item, item.select) for sequence in (bm.verts, bm.edges, bm.faces)
                 for item in sequence]
        history = list(bm.select_history)

        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="VERT")
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.view3d.select(
            location=(event.mouse_region_x, event.mouse_region_y),
            deselect_all=True,
        )
        bm = bmesh.from_edit_mesh(obj.data)
        picked = [vert for vert in bm.verts if vert.select and not vert.hide]
        if len(picked) != 1:
            for item, selected in flags:
                if item.is_valid:
                    item.select = selected
            bm.select_history.clear()
            for item in history:
                if item.is_valid and item.select:
                    bm.select_history.add(item)
            context.tool_settings.mesh_select_mode = old_mode
            bm.select_flush_mode()
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
            return {"CANCELLED"}

        return bpy.ops.mesh.polygroups_mark_smart_angle_seams()
