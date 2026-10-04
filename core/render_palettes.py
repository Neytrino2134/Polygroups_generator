"""Editable scene palette library and portable JSON exchange."""
import json
import bpy
import bpy.utils.previews
from bpy.app.handlers import persistent
from bpy_extras.io_utils import ImportHelper, ExportHelper

_swatches = None


def clear_swatches():
    global _swatches
    if _swatches is not None:
        bpy.utils.previews.remove(_swatches)
        _swatches = None


def color_icon(rgba):
    """Clickable, full-brightness sRGB swatch instead of a disabled color field."""
    global _swatches
    if _swatches is None:
        _swatches = bpy.utils.previews.new()
    rgb = [12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055 for v in rgba[:3]]
    pixels = tuple(round(max(0, min(1, v)) * 255) for v in rgb) + (255,)
    key = str(pixels)
    if key not in _swatches:
        if len(_swatches) >= 512:
            clear_swatches()
            _swatches = bpy.utils.previews.new()
        preview = _swatches.new(key)
        preview.image_size = (32, 32)
        # Preview pixels are packed RGBA bytes in display (sRGB) space.
        packed = pixels[0] | (pixels[1] << 8) | (pixels[2] << 16) | (pixels[3] << 24)
        if packed >= 2 ** 31:
            packed -= 2 ** 32
        preview.image_pixels = [packed] * (32 * 32)
    return _swatches[key].icon_id


def apply_line_color(context, rgba):
    context.scene.polygroups_render_settings.freestyle_line_color = rgba
    for layer in context.scene.view_layers:
        for lineset in layer.freestyle_settings.linesets:
            if lineset.linestyle is not None:
                lineset.linestyle.color = rgba[:3]
                lineset.linestyle.alpha = rgba[3]
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


class RenderPaletteColor(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(default="Color")
    color: bpy.props.FloatVectorProperty(size=4, subtype="COLOR", min=0, max=1, default=(1, 1, 1, 1))


class RenderPalette(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(default="Palette")
    colors: bpy.props.CollectionProperty(type=RenderPaletteColor)
    color_index: bpy.props.IntProperty(default=0, min=0)


class RenderPaletteGroup(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(default="Group")
    palettes: bpy.props.CollectionProperty(type=RenderPalette)
    palette_index: bpy.props.IntProperty(default=0, min=0)


EXAMPLE = (
    ("Void Black", "05070A"), ("Deep Navy", "07131F"),
    ("Surface Blue", "0B2033"), ("Flow Cyan", "00D9F5"),
    ("Electric Blue", "168BFF"), ("Flow Violet", "875CFF"),
    ("Pulse Purple", "B44CFF"),
)


def srgb_to_linear(value):
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


@persistent
def ensure_libraries(*args):
    for scene in bpy.data.scenes:
        settings = scene.polygroups_render_settings
        if settings.palette_library_initialized:
            continue
        group = settings.palette_groups.add()
        group.name = "Example Collection"
        palette = group.palettes.add()
        palette.name = "Primary Colors"
        for name, code in EXAMPLE:
            color = palette.colors.add()
            color.name = name
            color.color = tuple(srgb_to_linear(int(code[i:i+2], 16) / 255) for i in (0, 2, 4)) + (1,)
        settings.palette_library_initialized = True


def selected(settings):
    group = settings.palette_groups[settings.palette_group_index] if 0 <= settings.palette_group_index < len(settings.palette_groups) else None
    palette = group.palettes[group.palette_index] if group and 0 <= group.palette_index < len(group.palettes) else None
    color = palette.colors[palette.color_index] if palette and 0 <= palette.color_index < len(palette.colors) else None
    return group, palette, color


class RENDER_OT_palette_edit(bpy.types.Operator):
    bl_idname = "render.polygroups_palette_edit"
    bl_label = "Edit Palette Library"
    bl_options = {"UNDO", "INTERNAL"}
    action: bpy.props.EnumProperty(items=[(s, s, "") for s in ("ADD_GROUP", "REMOVE_GROUP", "ADD_PALETTE", "REMOVE_PALETTE", "ADD_COLOR", "REMOVE_COLOR", "CAPTURE", "APPLY")])

    def execute(self, context):
        ensure_libraries()
        settings = context.scene.polygroups_render_settings
        group, palette, color = selected(settings)
        action = self.action
        if action == "ADD_GROUP":
            settings.palette_groups.add().name = "New Group"
            settings.palette_group_index = len(settings.palette_groups) - 1
        elif action == "REMOVE_GROUP" and group:
            settings.palette_groups.remove(settings.palette_group_index)
            settings.palette_group_index = max(0, min(settings.palette_group_index, len(settings.palette_groups) - 1))
        elif action == "ADD_PALETTE" and group:
            group.palettes.add().name = "New Palette"
            group.palette_index = len(group.palettes) - 1
        elif action == "REMOVE_PALETTE" and palette:
            group.palettes.remove(group.palette_index)
            group.palette_index = max(0, min(group.palette_index, len(group.palettes) - 1))
        elif action in {"ADD_COLOR", "CAPTURE"} and palette:
            item = palette.colors.add()
            item.name = "Line Color" if action == "CAPTURE" else "New Color"
            item.color = settings.freestyle_line_color
            palette.color_index = len(palette.colors) - 1
        elif action == "REMOVE_COLOR" and color:
            palette.colors.remove(palette.color_index)
            palette.color_index = max(0, min(palette.color_index, len(palette.colors) - 1))
        elif action == "APPLY" and color:
            apply_line_color(context, color.color)
        else:
            return {"CANCELLED"}
        return {"FINISHED"}


def library_data(settings):
    return [{"name": g.name, "palettes": [{"name": p.name, "colors": [{"name": c.name, "color": list(c.color)} for c in p.colors]} for p in g.palettes]} for g in settings.palette_groups]


class RENDER_OT_palette_export(bpy.types.Operator, ExportHelper):
    bl_idname = "render.polygroups_palette_export"
    bl_label = "Export Palette Library"
    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        try:
            with open(self.filepath, "w", encoding="utf-8") as stream:
                json.dump({"version": 1, "groups": library_data(context.scene.polygroups_render_settings)}, stream, ensure_ascii=False, indent=2)
        except OSError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class RENDER_OT_palette_import(bpy.types.Operator, ImportHelper):
    bl_idname = "render.polygroups_palette_import"
    bl_label = "Import Palette Library"
    bl_options = {"UNDO"}
    filter_glob: bpy.props.StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        try:
            with open(self.filepath, encoding="utf-8") as stream:
                data = json.load(stream)
            assert data["version"] == 1
            groups = data["groups"]
            # Validate the complete file before changing the library.
            for group in groups:
                assert isinstance(group["name"], str)
                for palette in group["palettes"]:
                    assert isinstance(palette["name"], str)
                    for color in palette["colors"]:
                        assert isinstance(color["name"], str)
                        assert len(color["color"]) == 4 and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in color["color"])
        except (OSError, ValueError, KeyError, TypeError, AssertionError) as error:
            self.report({"ERROR"}, f"Invalid palette library: {error}")
            return {"CANCELLED"}
        settings = context.scene.polygroups_render_settings
        for source_group in groups:
            group = settings.palette_groups.add()
            group.name = source_group["name"]
            for source_palette in source_group["palettes"]:
                palette = group.palettes.add()
                palette.name = source_palette["name"]
                for source_color in source_palette["colors"]:
                    color = palette.colors.add()
                    color.name, color.color = source_color["name"], source_color["color"]
        settings.palette_group_index = max(0, len(settings.palette_groups) - 1)
        return {"FINISHED"}


class RENDER_UL_palette_colors(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        swatch = row.row()
        swatch.ui_units_x = 1.5
        swatch.prop(item, "color", text="")
        row.prop(item, "name", text="", emboss=False)


def draw_library(layout, settings):
    if not settings.palette_library_initialized:
        if not bpy.app.timers.is_registered(ensure_libraries):
            bpy.app.timers.register(ensure_libraries, first_interval=0.0)
        layout.label(text="Initializing palette library...")
        return
    group, palette, color = selected(settings)
    layout.label(text="Groups", icon="FILE_FOLDER")
    row = layout.row()
    row.template_list("UI_UL_list", "render_palette_groups", settings, "palette_groups", settings, "palette_group_index", rows=2)
    buttons = row.column(align=True)
    for action, icon in (("ADD_GROUP", "ADD"), ("REMOVE_GROUP", "REMOVE")):
        buttons.operator("render.polygroups_palette_edit", text="", icon=icon).action = action
    if group:
        layout.prop(group, "name", text="Group")
        row = layout.row()
        row.template_list("UI_UL_list", "render_palettes", group, "palettes", group, "palette_index", rows=2)
        buttons = row.column(align=True)
        for action, icon in (("ADD_PALETTE", "ADD"), ("REMOVE_PALETTE", "REMOVE")):
            buttons.operator("render.polygroups_palette_edit", text="", icon=icon).action = action
    if palette:
        layout.prop(palette, "name", text="Palette")
        row = layout.row()
        row.template_list("RENDER_UL_palette_colors", "", palette, "colors", palette, "color_index", rows=7)
        buttons = row.column(align=True)
        for action, icon in (("ADD_COLOR", "ADD"), ("REMOVE_COLOR", "REMOVE")):
            buttons.operator("render.polygroups_palette_edit", text="", icon=icon).action = action
        layout.operator("render.polygroups_palette_edit", text="Save Current Line Color", icon="ADD").action = "CAPTURE"
    if color:
        layout.prop(color, "name", text="Color")
        layout.prop(color, "color", text="RGBA")
        layout.operator("render.polygroups_palette_edit", text="Apply to Freestyle Line Color", icon="CHECKMARK").action = "APPLY"
    row = layout.row(align=True)
    row.operator("render.polygroups_palette_import", text="Import", icon="IMPORT")
    row.operator("render.polygroups_palette_export", text="Export", icon="EXPORT")


class RENDER_OT_palette_quick_apply(bpy.types.Operator):
    bl_idname = "render.polygroups_palette_quick_apply"
    bl_label = "Apply Line Color Preset"
    bl_description = "Immediately apply this palette color to Freestyle lines"
    bl_options = {"UNDO", "INTERNAL"}
    group_index: bpy.props.IntProperty(min=0)
    palette_index: bpy.props.IntProperty(min=0)
    color_index: bpy.props.IntProperty(min=0)

    def execute(self, context):
        settings = context.scene.polygroups_render_settings
        if settings.is_running:
            return {"CANCELLED"}
        try:
            group = settings.palette_groups[self.group_index]
            palette = group.palettes[self.palette_index]
            color = palette.colors[self.color_index]
        except IndexError:
            return {"CANCELLED"}
        apply_line_color(context, color.color)
        settings.palette_group_index = self.group_index
        group.palette_index = self.palette_index
        palette.color_index = self.color_index
        return {"FINISHED"}


class RENDER_OT_palette_popup(bpy.types.Operator):
    bl_idname = "render.polygroups_palette_popup"
    bl_label = "Line Color Palettes"
    bl_description = "Choose a saved palette color for Freestyle lines"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        ensure_libraries()
        return context.window_manager.invoke_popup(self, width=300)

    def execute(self, context):
        return {"FINISHED"}

    def draw(self, context):
        settings = context.scene.polygroups_render_settings
        layout = self.layout
        layout.enabled = not settings.is_running
        found = False
        for group_index, group in enumerate(settings.palette_groups):
            if not any(palette.colors for palette in group.palettes):
                continue
            layout.label(text=group.name, icon="FILE_FOLDER")
            for palette_index, palette in enumerate(group.palettes):
                if not palette.colors:
                    continue
                box = layout.box().column(align=True)
                box.label(text=palette.name, icon="COLOR")
                for color_index, color in enumerate(palette.colors):
                    found = True
                    row = box.row(align=True)
                    for text, icon_value in (("", color_icon(color.color)), (color.name, 0)):
                        op = row.operator("render.polygroups_palette_quick_apply", text=text, icon_value=icon_value)
                        op.group_index = group_index
                        op.palette_index = palette_index
                        op.color_index = color_index
        if not found:
            layout.label(text="Add colors in Render > Color Palettes", icon="INFO")


PROPERTY_CLASSES = (RenderPaletteColor, RenderPalette, RenderPaletteGroup)
OPERATOR_CLASSES = (RENDER_UL_palette_colors, RENDER_OT_palette_edit, RENDER_OT_palette_import, RENDER_OT_palette_export, RENDER_OT_palette_quick_apply, RENDER_OT_palette_popup)
