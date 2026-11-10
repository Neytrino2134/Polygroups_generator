from math import isqrt

import bpy


def uvpackmaster_packing_schemes(context, *, ui_drawing=False):
    from uvpackmaster4.spipeline.engine.g_scheme.access import GroupingSchemeAccess

    return GroupingSchemeAccess(context, desc_id="packing", ui_drawing=ui_drawing)


class POLYGROUPS_MT_uvpackmaster_schemes(bpy.types.Menu):
    bl_idname = "POLYGROUPS_MT_uvpackmaster_schemes"
    bl_label = "Grouping Schemes"

    def draw(self, context):
        access = uvpackmaster_packing_schemes(context, ui_drawing=True)
        for scheme in sorted(access.g_schemes, key=lambda item: item.name.casefold()):
            choice = self.layout.operator("uvpackmaster4.browse_grouping_schemes", text=scheme.name)
            choice.gs_access_desc_id = "packing"
            choice.active_g_scheme_uuid = scheme.uuid


def _target_box_grid(count, layout):
    if layout == "VERTICAL":
        return 1, count
    if layout == "HORIZONTAL" or count <= 2:
        return count, 1
    columns = isqrt(count - 1) + 1
    return columns, (count + columns - 1) // columns


class OBJECT_OT_polygroups_uvpackmaster_preset(bpy.types.Operator):
    bl_idname = "object.polygroups_uvpackmaster_preset"
    bl_label = "UVPackmaster Packing Preset"
    bl_options = {"UNDO"}

    preset: bpy.props.EnumProperty(items=(
        ("SINGLE_TILE", "Single Tile", "Pack all islands into UV 0–1 without grouping"),
        ("GROUPS_TO_TILES", "Groups to Tiles", "Use a manual grouping scheme"),
    ))
    group_count: bpy.props.IntProperty(name="Scheme Groups", default=2, min=1, max=1001, soft_max=16)
    scheme_picker_open: bpy.props.BoolProperty(options={"HIDDEN", "SKIP_SAVE"})

    def update_scheme_name(self, context):
        if not self.scheme_picker_open:
            return
        scheme = context.scene.uvpm4_props.grouping_schemes.get(self.scheme_name)
        if scheme:
            self.group_count = len(scheme.groups)
        elif not self.scheme_name:
            self.group_count = 2

    scheme_name: bpy.props.StringProperty(
        name="Scheme", description="Select an existing scheme or leave empty to create one",
        options={"SKIP_SAVE"}, update=update_scheme_name,
    )
    target_boxes: bpy.props.BoolProperty(
        name="Group Target Boxes", default=True,
        description="Replace target boxes with one region per group in UV 0–1",
    )
    box_layout: bpy.props.EnumProperty(name="Box Layout", default="GRID", items=(
        ("HORIZONTAL", "Horizontal", "Arrange boxes from left to right"),
        ("VERTICAL", "Vertical", "Arrange boxes from bottom to top"),
        ("GRID", "Grid", "Arrange boxes in a grid, starting from the bottom left"),
    ))

    @classmethod
    def poll(cls, context):
        return getattr(context.scene, "uvpm4_props", None) is not None

    def invoke(self, context, event):
        if self.preset == "SINGLE_TILE":
            return self.execute(context)
        scheme = uvpackmaster_packing_schemes(context, ui_drawing=True).active_g_scheme
        self.scheme_picker_open = True
        self.scheme_name = scheme.name if scheme else ""
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        scene_props = context.scene.uvpm4_props
        layout.prop_search(self, "scheme_name", scene_props, "grouping_schemes", icon="GROUP_UVS")
        scheme = scene_props.grouping_schemes.get(self.scheme_name)
        if not self.scheme_name:
            layout.label(text="Create a new grouping scheme", icon="ADD")
        layout.prop(self, "group_count")
        if scheme and self.group_count < len(scheme.groups):
            layout.label(text="Extra groups will be removed from this scheme", icon="INFO")
        layout.prop(self, "target_boxes")
        if self.target_boxes and self.group_count > 1:
            layout.prop(self, "box_layout")
            columns, rows = _target_box_grid(self.group_count, self.box_layout)
            layout.label(text=f"{columns} × {rows} in UV 0–1")

    def execute(self, context):
        from uvpackmaster4.app_iface import get_main_props
        from uvpackmaster4.spipeline.engine.geom.box import UVPM4_Box
        from uvpackmaster4.spipeline.engine.types import GroupingMethod, GroupLayoutMode, PackModeId

        main_props = get_main_props(context)
        if self.preset == "SINGLE_TILE":
            main_props.custom_target_box_enable = False
            main_props.active_pack_mode_id = PackModeId.SINGLE_TILE.value()
            return {"FINISHED"}

        columns, rows = _target_box_grid(self.group_count, self.box_layout)
        if self.target_boxes and 1 / max(columns, rows) <= UVPM4_Box.DIMENSION_MIN_LIMIT:
            self.report({"ERROR"}, "Target boxes are too small for this layout. Use Grid or reduce Scheme Groups.")
            return {"CANCELLED"}

        access = uvpackmaster_packing_schemes(context)
        if self.scheme_name:
            selected = access.g_schemes.get(self.scheme_name)
            if selected is None:
                self.report({"ERROR"}, f"Grouping scheme not found: {self.scheme_name}")
                return {"CANCELLED"}
            access.set_active_g_scheme_uuid(selected.uuid)
        if self.properties.is_property_set("scheme_name") and not self.scheme_name:
            scheme = access.create_g_scheme()
        else:
            scheme = access.active_g_scheme or access.create_g_scheme()
        scheme.options.group_layout_mode = GroupLayoutMode.MANUAL.value()
        scheme.options.base.dynamic_tiles_all = False

        while len(scheme.groups) > self.group_count:
            index = next(i for i in reversed(range(len(scheme.groups))) if not scheme.groups[i].is_default())
            scheme.remove_group(index)
        used_numbers = {group.num for group in scheme.groups}
        free_numbers = (number for number in range(1, 1001) if number not in used_numbers)
        while len(scheme.groups) < self.group_count:
            scheme.add_group_with_target_box(g_num=next(free_numbers))

        if self.target_boxes:
            scheme.options.base.last_group_complementary = False
            for index, group in enumerate(scheme.groups):
                row, column = divmod(index, columns)
                group.dynamic_tiles = False
                group.target_boxes.clear()
                box = group.target_boxes.add()
                box.p1_x, box.p1_y = column / columns, row / rows
                box.p2_x, box.p2_y = (column + 1) / columns, (row + 1) / rows
                group.active_target_box_idx = 0

        main_props.group_method_pack = GroupingMethod.MANUAL.value()
        main_props.active_pack_mode_id = PackModeId.GROUPS_TO_TILES.value()
        return {"FINISHED"}


class WM_OT_polygroups_uvpackmaster_edit_scheme_boxes(bpy.types.Operator):
    bl_idname = "wm.polygroups_uvpackmaster_edit_scheme_boxes"
    bl_label = "Edit Scheme Target Boxes"
    bl_description = "Edit the active packing scheme's target boxes in the UV Editor"

    @classmethod
    def poll(cls, context):
        return (context.area is not None and context.window is not None
                and hasattr(context.scene, "uvpm4_props")
                and not context.scene.polygroups_baking_settings.uv_bake_is_running)

    def execute(self, context):
        from uvpackmaster4.app_iface import get_prefs
        from uvpackmaster4.spipeline.engine.types import PackModeId

        prefs = get_prefs()
        scheme = uvpackmaster_packing_schemes(context, ui_drawing=True).active_g_scheme
        if prefs.box_rendering or prefs.group_scheme_boxes_editing:
            self.report({"WARNING"}, "Finish the active UVPackmaster box rendering first")
            return {"CANCELLED"}
        if scheme is None or not scheme.target_box_editing():
            self.report({"WARNING"}, "Select a grouping scheme with a Manual group layout")
            return {"CANCELLED"}

        window, screen, origin = context.window, context.screen, context.area
        active = context.active_object
        edit_object = None
        temporary_area = None

        def restore_view():
            # The native modal operator must release its draw handlers before the area closes.
            if window not in bpy.context.window_manager.windows[:]:
                return None
            if window.screen != screen:
                return 0.2
            with bpy.context.temp_override(window=window):
                if (edit_object is not None and bpy.context.active_object == edit_object
                        and edit_object.mode == "EDIT"):
                    bpy.ops.object.mode_set(mode="OBJECT")
                if temporary_area is not None and temporary_area in screen.areas[:]:
                    with bpy.context.temp_override(area=temporary_area):
                        bpy.ops.screen.area_close()
                for area in screen.areas:
                    area.tag_redraw()
            return None

        def wait_for_finish():
            if window not in bpy.context.window_manager.windows[:]:
                return None
            if prefs.box_rendering or prefs.group_scheme_boxes_editing:
                return 0.1
            return restore_view()

        try:
            uv_area = next((area for area in screen.areas if area.ui_type == "UV"), None)
            if uv_area is None:
                existing_areas = set(screen.areas)
                if "FINISHED" not in bpy.ops.screen.area_split(direction="VERTICAL", factor=0.5):
                    raise RuntimeError("Open a UV Editor to edit the scheme target boxes")
                temporary_area = next((area for area in screen.areas if area not in existing_areas), None)
                if temporary_area is None:
                    raise RuntimeError("Could not open a temporary UV Editor")
                uv_area = temporary_area
                uv_area.ui_type = "UV"
            region = next(region for region in uv_area.regions if region.type == "WINDOW")
            if active is not None and active.type == "MESH" and context.mode == "OBJECT" and active.select_get():
                if "FINISHED" in bpy.ops.object.mode_set(mode="EDIT"):
                    edit_object = active
            with context.temp_override(area=uv_area, region=region):
                result = bpy.ops.uvpackmaster4.render_grouping_scheme_boxes(
                    "EXEC_DEFAULT", gs_access_desc_id="packing", mode_id=PackModeId.GROUPS_TO_TILES.value(),
                )
            if "RUNNING_MODAL" not in result or not prefs.box_rendering:
                raise RuntimeError("UVPackmaster could not start editing the scheme target boxes")
        except (RuntimeError, StopIteration) as error:
            if prefs.box_rendering:
                bpy.ops.uvpackmaster4.finish_box_rendering("EXEC_DEFAULT")
            if prefs.group_scheme_boxes_editing:
                bpy.app.timers.register(wait_for_finish, first_interval=0.1)
            else:
                restore_view()
            self.report({"WARNING"}, str(error) or "UV Editor has no window region")
            return {"CANCELLED"}

        origin.tag_redraw()
        uv_area.tag_redraw()
        bpy.app.timers.register(wait_for_finish, first_interval=0.1)
        return {"FINISHED"}


class OBJECT_OT_polygroups_uvpackmaster_pack(bpy.types.Operator):
    bl_idname = "object.polygroups_uvpackmaster_pack"
    bl_label = "PACK"
    bl_description = "Run UVPackmaster Pack with a safe heuristic max wait time"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        if not hasattr(context.scene, "uvpm4_props"):
            self.report({"ERROR"}, "UVPackmaster 4 properties were not found.")
            return {"CANCELLED"}

        obj = context.active_object
        context.view_layer.objects.active = obj
        if obj.mode != "EDIT":
            if obj.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            bpy.ops.object.mode_set(mode="EDIT")

        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type="FACE")
        bpy.ops.mesh.reveal()
        bpy.ops.mesh.select_all(action="SELECT")

        main_props = context.scene.uvpm4_props.default_main_props
        if hasattr(main_props, "heuristic_max_wait_time") and main_props.heuristic_max_wait_time <= 0:
            main_props.heuristic_max_wait_time = 3

        try:
            # EXEC_DEFAULT keeps this wrapper alive until UVPackmaster finishes
            # its heuristic search (bounded by Max Wait Time).
            return bpy.ops.uvpackmaster4.pack(
                "EXEC_DEFAULT",
                mode_id="__active__",
                pack_op_type="0",
            )
        except Exception as error:
            self.report({"ERROR"}, f"UVPackmaster packing failed: {error}")
            return {"CANCELLED"}
        finally:
            if obj.mode == "EDIT":
                try:
                    bpy.ops.object.mode_set(mode="OBJECT")
                except Exception as error:
                    self.report({"WARNING"}, f"Could not return to Object Mode: {error}")
