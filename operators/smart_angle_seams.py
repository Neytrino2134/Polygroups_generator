"""Mark Smart UV Project island borders as seams without changing existing UVs."""
import bpy
import bmesh


def _edge_uv_is_split(edge, uv_layer, epsilon=1e-6):
    if len(edge.link_loops) != 2:
        return False
    values = []
    for loop in edge.link_loops:
        by_vertex = {
            loop.vert.index: loop[uv_layer].uv.copy(),
            loop.link_loop_next.vert.index: loop.link_loop_next[uv_layer].uv.copy(),
        }
        values.append(by_vertex)
    return any((values[0][index] - values[1][index]).length_squared > epsilon * epsilon
               for index in values[0])


class MESH_OT_polygroups_mark_smart_angle_seams(bpy.types.Operator):
    bl_idname = "mesh.polygroups_mark_smart_angle_seams"
    bl_label = "Mark Smart Angle Seams"
    bl_description = "Mark the Smart UV Project island boundaries as seams for the selected faces, preserving current UVs"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return (context.mode == "EDIT_MESH" and context.active_object is not None
                and context.active_object.type == "MESH" and len(context.objects_in_mode) == 1)

    def execute(self, context):
        obj = context.active_object
        settings = context.scene.polygroups_seam_preparation_settings
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        bm.verts.index_update()
        bm.faces.index_update()
        selected = {face.index for face in bm.faces if face.select and not face.hide}
        if not selected:
            self.report({'WARNING'}, "Select at least one face")
            return {'CANCELLED'}

        uv_layer = bm.loops.layers.uv.active
        created_uv = uv_layer is None
        if created_uv:
            uv_layer = bm.loops.layers.uv.new("Smart Angle Seam Preview")
        # Blender 5 stores UV selection/pin flags in separate generic layers;
        # BMLoopUV itself only exposes coordinates. Smart Project does not need
        # those flags here, so preserve the UV coordinates without touching the
        # version-dependent selection layers.
        snapshot = [(loop, loop[uv_layer].uv.copy())
                    for face in bm.faces for loop in face.loops]

        try:
            result = bpy.ops.uv.smart_project(
                angle_limit=settings.smart_seam_angle_limit,
                island_margin=0.0,
                correct_aspect=False,
                scale_to_bounds=False,
            )
            if 'FINISHED' not in result:
                raise RuntimeError("Smart UV Project did not finish")
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            bm.verts.index_update()
            marked = 0
            for edge in bm.edges:
                chosen = [face.index in selected for face in edge.link_faces]
                boundary = len(chosen) == 2 and chosen[0] != chosen[1]
                split = len(chosen) == 2 and all(chosen) and _edge_uv_is_split(edge, uv_layer)
                if (boundary or split) and not edge.seam:
                    edge.seam = True
                    marked += 1
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        finally:
            if created_uv:
                bm.loops.layers.uv.remove(uv_layer)
            else:
                for loop, uv in snapshot:
                    if loop.is_valid:
                        loop[uv_layer].uv = uv
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)

        self.report({'INFO'}, f"Marked {marked} Smart UV island boundary seam edge(s)")
        return {'FINISHED'}
