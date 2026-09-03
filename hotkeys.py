import bpy

from .localization import get_preferences
from .localization import t
from .tools import DRAW_CUTTER_ARC_TOOL_ID
from .tools import DRAW_CUTTER_DRAW_TOOL_ID
from .tools import DRAW_CUTTER_LOCAL_CONTOUR_TOOL_ID
from .tools import DRAW_CUTTER_LOCAL_RING_TOOL_ID
from .tools import DRAW_CUTTER_PATH_TOOL_ID
from .tools import DRAW_CUTTER_TOOL_ID
from .tools import CUTTER_TOOL_ORDER
from .operators.section_hotkeys import AIRETOPO_OT_section_number
from .operators.section_hotkeys import DIGIT_KEYS, cancel_pending_sections


KEYMAP_ITEMS = []

# Blender consumes pie entries in W, E, S, N, NW, NE, SW, SE order.
# User slots run clockwise from the top: N, NE, E, SE, S, SW, W, NW.
PIE_SLOT_DRAW_ORDER = (7, 3, 5, 1, 8, 2, 6, 4)

CUTTER_TOOL_ITEMS = (
    (DRAW_CUTTER_TOOL_ID, "Plane", "Start cycling from the cutter plane tool"),
    (DRAW_CUTTER_LOCAL_RING_TOOL_ID, "Local Ring", "Start cycling from the local ring cutter tool"),
    (DRAW_CUTTER_ARC_TOOL_ID, "Arc", "Start cycling from the cutter arc tool"),
    (DRAW_CUTTER_PATH_TOOL_ID, "Path", "Start cycling from the cutter path tool"),
    (DRAW_CUTTER_DRAW_TOOL_ID, "Draw", "Start cycling from the freehand cutter draw tool"),
    (DRAW_CUTTER_LOCAL_CONTOUR_TOOL_ID, "Local Contour", "Start cycling from the fitted local contour cutter"),
)

PIE_COMMAND_ITEMS = (
    ("NONE", "Empty", "Leave this pie slot empty"),
    ("IMPORT_FILES", "Import Files", "Open the multi-file import browser"),
    ("APPLY_CUTTER_SEAMS", "Apply Cutter Seams", "Apply selected cutter seams to the active mesh"),
    ("GENERATE_POLYGROUPS", "Generate PolyGroups", "Generate PolyGroups on the active mesh"),
    ("RENAME_WELD", "Rename + Weld", "Rename selected meshes and apply Weld"),
    ("REMESH", "Remesh It", "Run Quad Remesher through the safety check"),
    ("UV_PACK", "UVPackmaster PACK", "Run UVPackmaster Pack"),
    ("CHECK_MATERIALS", "Check Material/Textures", "Fix material texture connections"),
    ("PREPARE_BAKE", "Prepare And Bake", "Prepare selected-to-active baking and bake"),
    ("SAVE_TEXTURES", "Save Textures", "Save active bake textures"),
    ("CLEAR_BAKE_IMAGES", "Clear Bake Images", "Delete Bake_Temp images"),
    ("CUTTER_TWEAK", "Cutter Tweak Tool", "Select the configured Cutter Tweak tool"),
)

PIE_COMMANDS = {
    "IMPORT_FILES": {
        "label": "import_files",
        "icon": "FILE_FOLDER",
        "operator": "object.polygroups_batch_import",
        "properties": {"use_file_selection": True},
    },
    "APPLY_CUTTER_SEAMS": {
        "label": "apply_cutter_seams",
        "icon": "MOD_BOOLEAN",
        "operator": "object.polygroups_apply_cutter_seams",
    },
    "GENERATE_POLYGROUPS": {
        "label": "generate_polygroups",
        "icon": "GROUP_VERTEX",
        "operator": "object.polygroups_checked_generate_polygroups",
    },
    "RENAME_WELD": {
        "label": "rename_apply_weld",
        "icon": "AUTOMERGE_ON",
        "operator": "object.polygroups_rename_and_apply_weld",
    },
    "REMESH": {
        "label": "remesh_it",
        "icon": "MOD_REMESH",
        "operator": "object.polygroups_checked_quad_remesh",
    },
    "UV_PACK": {
        "label": "uvpackmaster_pack",
        "icon": "UV",
        "operator": "uvpackmaster4.pack",
        "properties": {"mode_id": "__active__", "pack_op_type": "0"},
    },
    "CHECK_MATERIALS": {
        "label": "check_material_textures",
        "icon": "NODE_MATERIAL",
        "operator": "object.polygroups_check_material_textures",
    },
    "PREPARE_BAKE": {
        "label": "prepare_and_bake",
        "icon": "RENDER_RESULT",
        "operator": "object.polygroups_checked_prepare_and_bake",
    },
    "SAVE_TEXTURES": {
        "label": "save_textures",
        "icon": "FILE_FOLDER",
        "operator": "object.polygroups_save_bake_textures",
    },
    "CLEAR_BAKE_IMAGES": {
        "label": "clear_all_bake_images",
        "icon": "TRASH",
        "operator": "object.polygroups_clear_bake_temp_images",
    },
    "CUTTER_TWEAK": {
        "label": "select_cutter_tweak_tool",
        "icon": "TOOL_SETTINGS",
        "operator": "wm.airetopo_select_cutter_tweak",
    },
}


# Keep existing command IDs and enum positions above unchanged for saved slots.
_EXTRA_PIE_COMMANDS = (
    ("SELECT_MORE", "Select More", "select_more", "ADD", "mesh.select_more", {}),
    ("SELECT_LESS", "Select Less", "select_less", "REMOVE", "mesh.select_less", {}),
    ("SELECT_LINKED_SEAM", "Select Linked (Seam)", "select_linked_seam", "LINKED", "mesh.select_linked", {"delimit": {"SEAM"}}),
    ("SMOOTH_SELECTION", "Smooth Face Selection", "smooth_face_selection", "MOD_SMOOTH", "mesh.polygroups_smooth_face_selection", {}),
    ("DELETE_FILL", "Delete and Fill", "delete_and_fill", "MESH_DATA", "mesh.polygroups_delete_and_fill", {}),
    ("MARK_SEAM", "Mark Selected Edges Seam", "mark_selected_edges_seam", "EDGE_SEAM", "mesh.polygroups_mark_selected_edges_seam", {}),
    ("MARK_BOUNDARY_SEAM", "Mark Selection Boundary Seam", "mark_selection_boundary_seam", "EDGESEL", "mesh.polygroups_mark_selection_boundary_seam", {}),
    ("MARK_MATERIAL_SEAMS", "Generate Seams From Materials", "generate_seams_materials", "MATERIAL", "mesh.polygroups_mark_material_boundaries_seam", {}),
    ("CLEAR_SELECTED_SEAMS", "Clear Selected Edges Seam", "clear_selected_edges_seam", "X", "mesh.polygroups_clear_selected_edges_seam", {}),
    ("CLEAR_INSIDE_SEAMS", "Clear Inside Edges Seam", "clear_inside_edges_seam", "X", "mesh.polygroups_clear_inside_edges_seam", {}),
    ("CHECK_SEAM_GAPS", "Check Seam Gaps", "check_seam_gaps", "VIEWZOOM", "mesh.polygroups_check_seam_gaps", {"mode": "SELECT"}),
    ("CLOSE_SEAM_GAPS", "Close Seam Gaps", "close_seam_gaps", "EDGE_SEAM", "mesh.polygroups_check_seam_gaps", {"mode": "MARK"}),
    ("CONNECT_SEAM_GAPS", "Connect Seam Gap Pairs", "connect_seam_gap_pairs", "AUTOMERGE_ON", "mesh.polygroups_connect_seam_gap_pairs", {}),
    ("CONNECT_VERTEX_SEAM", "Connect Vertices with Seam", "connect_vertices_seam", "EDGE_SEAM", "mesh.polygroups_connect_vertex_seam", {}),
    ("VERTEX_SEAM_TOOL", "Vertex Seam Path Tool", "select_vertex_seam_tool", "VERTEXSEL", "mesh.polygroups_select_seam_tool", {"tool_id": "polygroups_generator.connect_vertex_seam_tool"}),
    ("KNIFE_SEAM_TOOL", "Knife Seam Tool", "select_knife_tool", "SCULPTMODE_HLT", "mesh.polygroups_select_seam_tool", {"tool_id": "polygroups_generator.knife_seam_tool"}),
    ("QUICK_KNIFE_TOOL", "Quick Knife Seam Tool", "select_quick_knife_tool", "MOD_BEVEL", "mesh.polygroups_select_seam_tool", {"tool_id": "polygroups_generator.quick_knife_seam_tool"}),
    ("COPY_MIRROR_CUTTERS", "Copy Mirror Cutters", "copy_mirror_cutters", "MOD_MIRROR", "object.polygroups_copy_mirror_cutters", {}),
    ("APPLY_WELD", "Apply Weld", "apply_weld", "AUTOMERGE_ON", "object.polygroups_apply_weld", {}),
    ("RENAME_OBJECTS", "Rename Objects", "rename_objects", "OUTLINER_COLLECTION", "object.polygroups_rename_objects", {}),
    ("UNWRAP", "Unwrap Angle Based", "unwrap_angle_based", "UV", "object.polygroups_unwrap_angle_based", {}),
    ("CHECKER", "Apply Checker Material", "apply_checker_material", "TEXTURE", "object.polygroups_apply_checker_material", {}),
    ("CHECK_MESH", "Check Mesh", "check_mesh", "VIEWZOOM", "object.polygroups_check_mesh", {}),
    ("FIX_NORMALS", "Fix Normals", "fix_normals", "NORMALS_FACE", "object.polygroups_fix_mesh_normals", {}),
    ("TRIANGULATE_NGONS", "Triangulate N-gons", "triangulate_ngons", "MESH_DATA", "object.polygroups_triangulate_ngons", {}),
    ("FILL_NONMANIFOLD", "Fill Non-Manifold", "fill_nonmanifold", "MESH_DATA", "object.polygroups_fill_nonmanifold", {}),
    ("DELETE_LOOSE", "Delete Loose", "delete_loose", "X", "object.polygroups_delete_loose_geometry", {}),
)
PIE_COMMAND_ITEMS += tuple((key, name, name) for key, name, *_ in _EXTRA_PIE_COMMANDS)
PIE_COMMANDS.update({key: {"label": label, "icon": icon, "operator": operator, "properties": properties}
                     for key, name, label, icon, operator, properties in _EXTRA_PIE_COMMANDS})
for key, name, label, tool_id in (
    ("CUTTER_PLANE", "Cutter Tweak: Plane", "draw_cutter_plane", DRAW_CUTTER_TOOL_ID),
    ("CUTTER_RING", "Cutter Tweak: Local Ring", "draw_cutter_local_ring", DRAW_CUTTER_LOCAL_RING_TOOL_ID),
    ("CUTTER_CONTOUR", "Cutter Tweak: Local Contour", "draw_cutter_local_contour", DRAW_CUTTER_LOCAL_CONTOUR_TOOL_ID),
    ("CUTTER_ARC", "Cutter Tweak: Arc", "draw_cutter_arc", DRAW_CUTTER_ARC_TOOL_ID),
    ("CUTTER_PATH", "Cutter Tweak: Path", "draw_cutter_path", DRAW_CUTTER_PATH_TOOL_ID),
    ("CUTTER_DRAW", "Cutter Tweak: Draw", "draw_cutter_draw", DRAW_CUTTER_DRAW_TOOL_ID),
):
    PIE_COMMAND_ITEMS += ((key, name, name),)
    PIE_COMMANDS[key] = {"label": label, "icon": "TOOL_SETTINGS", "operator": "wm.tool_set_by_id",
                         "properties": {"name": tool_id}, "mode": "OBJECT"}
for level in ("LOW", "MID", "HIGH"):
    key = "REMESH_" + level
    PIE_COMMAND_ITEMS += ((key, "Remesh " + level, "Run the " + level + " remesh preset"),)
    PIE_COMMANDS[key] = {"label": "Remesh " + level, "icon": "MOD_REMESH",
                         "operator": "object.polygroups_checked_quad_remesh", "remesh_preset": level}


def _operator_exists(operator_id):
    module_name, operator_name = operator_id.split(".", 1)
    try:
        getattr(getattr(bpy.ops, module_name), operator_name).get_rna_type()
    except (AttributeError, RuntimeError):
        return False
    return True


def _event_kwargs(key, ctrl, shift, alt):
    kwargs = {
        "type": key,
        "value": "PRESS",
    }
    if ctrl:
        kwargs["ctrl"] = True
    if shift:
        kwargs["shift"] = True
    if alt:
        kwargs["alt"] = True
    return kwargs


def _set_operator_properties(operator, properties):
    if not properties:
        return

    for name, value in properties.items():
        try:
            setattr(operator, name, value)
        except Exception:
            pass


def _draw_pie_command(layout, context, command_id):
    command = PIE_COMMANDS.get(command_id)
    if command is None:
        layout.separator()
        return

    operator_id = command["operator"]
    label = t(context, command["label"])
    if not _operator_exists(operator_id):
        row = layout.row()
        row.enabled = False
        row.label(text=label, icon="ERROR")
        return

    if command.get("mode") and context.mode != command["mode"]:
        layout = layout.row()
        layout.enabled = False
    operator = layout.operator(
        operator_id,
        text=label,
        icon=command.get("icon", "NONE"),
    )
    _set_operator_properties(operator, command.get("properties"))
    if command_id == "SMOOTH_SELECTION":
        operator.iterations = context.scene.polygroups_seam_preparation_settings.selection_smooth_iterations
    if command.get("remesh_preset"):
        from .core.remesh_defaults import get_remesh_preset_counts
        operator.quad_count = dict(get_remesh_preset_counts(context))[command["remesh_preset"]]


def refresh_keymaps(context=None):
    unregister_keymaps()
    register_keymaps()


def _preference_value(preferences, name, default):
    return getattr(preferences, name, default) if preferences is not None else default


def _active_workspace_tool_id(context):
    try:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
    except Exception:
        return ""

    return getattr(tool, "idname", "")


def _next_cutter_tool_id(context, preferences):
    active_tool_id = _active_workspace_tool_id(context)
    if active_tool_id in CUTTER_TOOL_ORDER:
        active_index = CUTTER_TOOL_ORDER.index(active_tool_id)
        return CUTTER_TOOL_ORDER[(active_index + 1) % len(CUTTER_TOOL_ORDER)]

    start_tool_id = _preference_value(
        preferences,
        "cutter_tweak_tool",
        DRAW_CUTTER_TOOL_ID,
    )
    if start_tool_id in CUTTER_TOOL_ORDER:
        return start_tool_id

    return DRAW_CUTTER_TOOL_ID


class AIRETOPO_OT_select_cutter_tweak(bpy.types.Operator):
    bl_idname = "wm.airetopo_select_cutter_tweak"
    bl_label = "Cycle Cutter Tweak Tool"
    bl_description = "Cycle through Cutter Tweak Plane, Arc, and Path workspace tools"
    bl_options = {"REGISTER"}

    def execute(self, context):
        preferences = get_preferences(context)
        tool_id = _next_cutter_tool_id(context, preferences)
        try:
            bpy.ops.wm.tool_set_by_id(name=tool_id)
        except Exception as error:
            self.report({"ERROR"}, f"Could not select Cutter Tweak tool: {error}")
            return {"CANCELLED"}

        self.report({"INFO"}, "Cutter Tweak tool selected")
        return {"FINISHED"}


class VIEW3D_MT_airetopo_pie(bpy.types.Menu):
    bl_idname = "VIEW3D_MT_airetopo_pie"
    bl_label = "AI Retopo Pie"

    def draw(self, context):
        preferences = get_preferences(context)
        pie = self.layout.menu_pie()
        for index in PIE_SLOT_DRAW_ORDER:
            slot = f"pie_slot_{index}"
            command_id = getattr(preferences, slot, "NONE") if preferences is not None else "NONE"
            _draw_pie_command(pie, context, command_id)


CLASSES = (
    AIRETOPO_OT_section_number,
    AIRETOPO_OT_select_cutter_tweak,
    VIEW3D_MT_airetopo_pie,
)


def register_keymaps():
    preferences = get_preferences(bpy.context)

    keyconfig = bpy.context.window_manager.keyconfigs.addon
    if keyconfig is None:
        return

    keymap = keyconfig.keymaps.new(name="3D View", space_type="VIEW_3D")

    if _preference_value(preferences, "enable_section_number_hotkeys", False):
        maps = [("User Interface", "EMPTY"), ("View2D Buttons List", "EMPTY")]
        if preferences.section_hotkey_scope == "VIEWPORT":
            maps.extend((("3D View Generic", "VIEW_3D"), ("Mesh", "EMPTY"),
                         ("Object Mode", "EMPTY"), ("Sculpt", "EMPTY")))
        for name, space_type in maps:
            number_map = keyconfig.keymaps.new(name=name, space_type=space_type)
            for key, digit in DIGIT_KEYS.items():
                item = number_map.keymap_items.new(
                    AIRETOPO_OT_section_number.bl_idname, key, "PRESS", head=True, repeat=False,
                )
                item.properties.digit = digit
                KEYMAP_ITEMS.append((number_map, item))

    if _preference_value(preferences, "enable_cutter_tweak_hotkey", True):
        item = keymap.keymap_items.new(
            AIRETOPO_OT_select_cutter_tweak.bl_idname,
            **_event_kwargs(
                _preference_value(preferences, "cutter_tweak_key", "D"),
                _preference_value(preferences, "cutter_tweak_ctrl", False),
                _preference_value(preferences, "cutter_tweak_shift", False),
                _preference_value(preferences, "cutter_tweak_alt", False),
            ),
        )
        KEYMAP_ITEMS.append((keymap, item))

    if _preference_value(preferences, "enable_pie_menu_hotkey", True):
        item = keymap.keymap_items.new(
            "wm.call_menu_pie",
            **_event_kwargs(
                _preference_value(preferences, "pie_menu_key", "C"),
                _preference_value(preferences, "pie_menu_ctrl", False),
                _preference_value(preferences, "pie_menu_shift", True),
                _preference_value(preferences, "pie_menu_alt", False),
            ),
        )
        item.properties.name = VIEW3D_MT_airetopo_pie.bl_idname
        KEYMAP_ITEMS.append((keymap, item))


def unregister_keymaps():
    cancel_pending_sections()
    for keymap, item in reversed(KEYMAP_ITEMS):
        try:
            keymap.keymap_items.remove(item)
        except Exception:
            pass
    KEYMAP_ITEMS.clear()


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    register_keymaps()
    bpy.app.handlers.load_pre.append(cancel_pending_sections)


def unregister():
    unregister_keymaps()
    if cancel_pending_sections in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(cancel_pending_sections)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
