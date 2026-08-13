import bpy
from bpy.types import WorkSpaceTool


class VIEW3D_WST_polygroups_knife_seam(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "EDIT_MESH"
    bl_idname = "polygroups_generator.knife_seam_tool"
    bl_label = "Knife Seam"
    bl_description = "Knife cut through the entire mesh and mark the new cut edges as seams"
    bl_icon = "ops.mesh.knife_tool"
    bl_cursor = "KNIFE"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        (
            "mesh.polygroups_knife_seam",
            {"type": "LEFTMOUSE", "value": "PRESS"},
            None,
        ),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        del context
        props = tool.operator_properties("mesh.polygroups_knife_seam")
        layout.prop(props, "use_occlude_geometry")
        layout.prop(props, "only_selected")
        layout.prop(props, "xray")
        layout.prop(props, "mark_seam")
        layout.prop(props, "clear_selection_after_cutting")


class VIEW3D_WST_polygroups_quick_knife_seam(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "EDIT_MESH"
    bl_idname = "polygroups_generator.quick_knife_seam_tool"
    bl_label = "Quick Knife Seam"
    bl_description = "Single-gesture cut through the full mesh, then mark the cut as seams"
    bl_icon = "ops.mesh.bisect"
    bl_cursor = "KNIFE"
    bl_options = {"KEYMAP_FALLBACK"}
    bl_widget = None
    bl_keymap = (
        (
            "mesh.polygroups_quick_knife_seam",
            {"type": "LEFTMOUSE", "value": "PRESS"},
            None,
        ),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        del context
        props = tool.operator_properties("mesh.polygroups_quick_knife_seam")
        layout.prop(props, "use_fill")
        layout.prop(props, "threshold")
        layout.prop(props, "mark_seam")
        layout.prop(props, "clear_selection_after_cutting")


def register():
    bpy.utils.register_tool(
        VIEW3D_WST_polygroups_knife_seam,
        after={"builtin.bevel"},
        separator=True,
        group=False,
    )
    bpy.utils.register_tool(
        VIEW3D_WST_polygroups_quick_knife_seam,
        after={"polygroups_generator.knife_seam_tool"},
        separator=False,
        group=False,
    )


def unregister():
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_quick_knife_seam)
    bpy.utils.unregister_tool(VIEW3D_WST_polygroups_knife_seam)
