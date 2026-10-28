"""Shared panel drawing, search and detached-group traversal."""
from ..custom_icons import icon_kwargs
import os
import json
import sys
import time
from types import SimpleNamespace
import bpy
from ..localization import get_preferences
from ..localization import t
from ..properties import SECTION_VISIBILITY_PROPERTIES
from ..core.remesh_defaults import get_remesh_preset_counts
from ..core.import_timing import format_duration
from ..ui_state import state


def quad_remesher_status(context):
    try:
        import addon_utils
    except ImportError:
        addon_utils = None

    installed = addon_utils is not None and any(
        module.__name__ == "quad_remesher"
        for module in addon_utils.modules()
    )
    loaded = False
    enabled = False

    if addon_utils is not None:
        try:
            loaded, enabled = addon_utils.check("quad_remesher")
        except Exception:
            loaded = False
            enabled = False

    has_settings = hasattr(context.scene, "qremesher")
    has_operator = hasattr(bpy.ops, "qremesher") and hasattr(
        bpy.ops.qremesher,
        "remesh",
    )

    return installed, enabled or loaded, has_settings and has_operator


def uvpackmaster_status(context):
    try:
        import addon_utils
    except ImportError:
        addon_utils = None

    installed = addon_utils is not None and any(
        module.__name__ == "uvpackmaster4"
        for module in addon_utils.modules()
    )
    loaded = False
    enabled = False

    if addon_utils is not None:
        try:
            loaded, enabled = addon_utils.check("uvpackmaster4")
        except Exception:
            loaded = False
            enabled = False

    has_settings = hasattr(context.scene, "uvpm4_props") and hasattr(
        context.scene.uvpm4_props,
        "default_main_props",
    )
    has_operator = hasattr(bpy.ops, "uvpackmaster4") and hasattr(
        bpy.ops.uvpackmaster4,
        "pack",
    )

    return installed, enabled or loaded, has_settings and has_operator


def _normalized_search_terms(value):
    return tuple(term for term in value.casefold().replace("_", " ").split() if term)


class _SearchResult:
    def __init__(self, query):
        self.terms = _normalized_search_terms(query)
        self.section_match = False
        self.groups = set()

    def record(self, values, group_path=()):
        haystack = " ".join(str(value) for value in values if value).casefold().replace("_", " ")
        if self.terms and all(term in haystack for term in self.terms):
            self.section_match = True
            self.groups.update(group_path)


class _SearchProbeLayout:
    """Collect searchable UI text without creating visible Blender controls."""

    def __init__(self, result, group_path=()):
        object.__setattr__(self, "result", result)
        object.__setattr__(self, "group_path", group_path)

    def grouped(self, key, label):
        child = _SearchProbeLayout(self.result, self.group_path + (key,))
        child.result.record((label,), child.group_path)
        return child

    def row(self, *args, **kwargs):
        return self

    def column(self, *args, **kwargs):
        return self

    def box(self, *args, **kwargs):
        return self

    def split(self, *args, **kwargs):
        return self

    def grid_flow(self, *args, **kwargs):
        return self

    def label(self, *args, **kwargs):
        self.result.record((kwargs.get("text", ""),), self.group_path)

    def operator(self, identifier, *args, **kwargs):
        text = kwargs.get("text")
        if text is None:
            try:
                module, name = identifier.split(".", 1)
                text = getattr(getattr(bpy.ops, module), name).get_rna_type().name
            except Exception:
                text = ""
        self.result.record((text,), self.group_path)
        return SimpleNamespace()

    def prop(self, data, property_name, *args, **kwargs):
        text = kwargs.get("text")
        if text is None:
            try:
                text = data.bl_rna.properties[property_name].name
            except Exception:
                text = ""
        self.result.record((text,), self.group_path)
        return self

    def prop_search(self, data, property_name, search_data, search_property, *args, **kwargs):
        del search_data, search_property
        return self.prop(data, property_name, *args, **kwargs)

    def __getattr__(self, name):
        return lambda *args, **kwargs: self

    def __setattr__(self, name, value):
        if name in {"result", "group_path"}:
            object.__setattr__(self, name, value)


def _search_text_matches(text, terms):
    haystack = str(text or "").casefold().replace("_", " ")
    return bool(terms) and all(term in haystack for term in terms)


class _FilteredLayout:
    """Draw only controls whose visible labels match the active search."""

    def __init__(self, layout, terms):
        object.__setattr__(self, "layout", layout)
        object.__setattr__(self, "terms", terms)

    def _child(self, method, *args, **kwargs):
        return _FilteredLayout(getattr(self.layout, method)(*args, **kwargs), self.terms)

    def row(self, *args, **kwargs):
        return self._child("row", *args, **kwargs)

    def column(self, *args, **kwargs):
        return self._child("column", *args, **kwargs)

    def box(self, *args, **kwargs):
        return self._child("box", *args, **kwargs)

    def split(self, *args, **kwargs):
        return self._child("split", *args, **kwargs)

    def grid_flow(self, *args, **kwargs):
        return self._child("grid_flow", *args, **kwargs)

    def label(self, *args, **kwargs):
        if _search_text_matches(kwargs.get("text", ""), self.terms):
            return self.layout.label(*args, **kwargs)
        return None

    def operator(self, identifier, *args, **kwargs):
        text = kwargs.get("text")
        if text is None:
            try:
                module, name = identifier.split(".", 1)
                text = getattr(getattr(bpy.ops, module), name).get_rna_type().name
            except Exception:
                text = ""
        if _search_text_matches(text, self.terms):
            return self.layout.operator(identifier, *args, **kwargs)
        return SimpleNamespace()

    def prop(self, data, property_name, *args, **kwargs):
        text = kwargs.get("text")
        if text is None:
            try:
                text = data.bl_rna.properties[property_name].name
            except Exception:
                text = ""
        if _search_text_matches(text, self.terms):
            return self.layout.prop(data, property_name, *args, **kwargs)
        return self

    def prop_search(self, data, property_name, search_data, search_property, *args, **kwargs):
        text = kwargs.get("text")
        if text is None:
            try:
                text = data.bl_rna.properties[property_name].name
            except Exception:
                text = ""
        if _search_text_matches(text, self.terms):
            return self.layout.prop_search(
                data, property_name, search_data, search_property, *args, **kwargs
            )
        return self

    def separator(self, *args, **kwargs):
        return None

    def __getattr__(self, name):
        # Unnamed templates cannot match a name query. Layout-producing APIs
        # still return a wrapper so later named controls can be evaluated.
        attribute = getattr(self.layout, name)
        if not callable(attribute):
            return attribute
        return lambda *args, **kwargs: self

    def __setattr__(self, name, value):
        if name in {"layout", "terms"}:
            object.__setattr__(self, name, value)
        else:
            setattr(self.layout, name, value)


def _probe_panel(panel_class, context, query):
    result = _SearchResult(query)
    title = t(context, panel_class.bl_text_key)
    title_text = f"{title} {panel_class.__name__}"
    if all(term in title_text.casefold().replace("_", " ") for term in result.terms):
        result.section_match = True
    state.search_probing = True
    try:
        draw_section_panel_content(
            panel_class,
            context,
            _SearchProbeLayout(result),
            getattr(panel_class, "visibility_property", ""),
        )
    finally:
        state.search_probing = False
    return result


class _NullLayout:
    """Traverse other groups without emitting controls into a detached panel."""
    def __getattr__(self, name):
        if name == "operator":
            return lambda *args, **kwargs: SimpleNamespace()
        return lambda *args, **kwargs: self


def draw_topic(layout, context, key, label, icon):
    return draw_collapsible_box(layout, context.scene.airetopo_panel_visibility_settings,
                                 "topic_" + key, t(context, label), icon)


def draw_mesh_editing(layout, context, prefix, loose_parts=False):
    settings = context.scene.polygroups_model_preparation_settings
    manual = draw_topic(layout, context, prefix + "_manual", "mesh_edit_manual", "EDITMODE_HLT")
    if manual is not None:
        column = manual.column(align=True)
        column.operator("mesh.polygroups_delete_and_fill",
                        text=t(context, "delete_and_fill"), icon="MESH_DATA")
        if loose_parts:
            column.separator()
            column.prop(settings, "small_loose_part_metric", text=t(context, "small_loose_part_metric"))
            column.prop(settings, "small_loose_part_threshold_percent",
                        text=t(context, "small_loose_part_threshold"))
            row = column.row(align=True)
            row.operator("object.polygroups_small_loose_parts",
                         text=t(context, "select_small_loose_parts"), icon="RESTRICT_SELECT_OFF").delete = False
            row.operator("object.polygroups_small_loose_parts",
                         text=t(context, "delete_small_loose_parts"), icon="TRASH").delete = True
    auto = draw_topic(layout, context, prefix + "_auto", "mesh_edit_auto", "MODIFIER")
    if auto is not None:
        column = auto.column(align=True)
        for prop in ("fold_repair_folds", "fold_repair_degenerate", "fold_repair_zero_area", "fold_repair_dangling", "fold_repair_stretched_triangles"):
            column.prop(settings, prop, text=t(context, prop))
        if settings.fold_repair_stretched_triangles:
            column.prop(settings, 'fold_repair_stretch_ratio', text=t(context, 'fold_repair_stretch_ratio'))
        column.prop(settings, 'fold_repair_selected_only', text=t(context, 'fold_repair_selected_only'))
        row = column.row(align=True)
        row.enabled = (settings.fold_repair_folds or settings.fold_repair_degenerate or settings.fold_repair_zero_area
                       or settings.fold_repair_stretched_triangles or settings.fold_repair_dangling)
        for action, label, icon in (("SELECT", "fold_repair_find", "VIEWZOOM"),
                                    ("REPAIR", "fold_repair_apply", "MOD_TRIANGULATE")):
            op = row.operator("mesh.polygroups_repair_mesh_folds", text=t(context, label), icon=icon)
            op.action = action
            op.fix_folds = settings.fold_repair_folds
            op.fix_degenerate = settings.fold_repair_degenerate
            op.fix_zero_area = settings.fold_repair_zero_area
            op.fix_dangling = settings.fold_repair_dangling
            op.fix_stretched_triangles = settings.fold_repair_stretched_triangles
            op.stretched_triangle_ratio = settings.fold_repair_stretch_ratio
            op.selected_only = settings.fold_repair_selected_only
        quality = column.operator("mesh.polygroups_repair_mesh_folds",
                                  text=t(context, "fold_repair_quality"), icon="UV")
        quality.action = 'SELECT_QUALITY'
        quality.selected_only = settings.fold_repair_selected_only
        column.label(text=t(context, "fold_repair_quality_hint"))
        if settings.fold_repair_dangling:
            column.label(text=t(context, "fold_repair_dangling_hint"), icon="INFO")
        column.label(text=t(context, "fold_repair_hint"))
        column.label(text=t(context, "fold_repair_uv_hint"))


def draw_session_subgroup(layout, context, preferences, property_name, text_key, icon):
    label = t(context, text_key)
    if preferences and state.custom_capturing and hasattr(layout, 'grouped'):
        return layout.grouped(preferences, property_name, label, icon)
    box = layout.box()
    opened = preferences is None or getattr(preferences, property_name)
    if preferences:
        box.prop(preferences, property_name, text=label,
                 icon='TRIA_DOWN' if opened else 'TRIA_RIGHT', emboss=False)
    else:
        box.label(text=label, icon=icon)
    return box if opened else None


def draw_section_fold_actions(header, property_name):
    actions = header.row(align=True)
    actions.alignment = 'RIGHT'
    for visible, icon in ((False, 'REMOVE'), (True, 'ADD')):
        op = actions.operator('object.airetopo_set_section_subsection_visibility', text='', icon=icon)
        op.section_property = property_name
        op.visible = visible


def draw_collapsible_box(layout, settings, property_name, label, icon):
    if state.custom_capturing and hasattr(layout, 'grouped'):
        return layout.grouped(settings, property_name, label, icon)
    key = settings.path_from_id() + "." + property_name
    if isinstance(layout, _SearchProbeLayout):
        return layout.grouped(key, label)
    if state.group_discovery is not None:
        state.group_discovery.append(dict(section=state.drawing_section.__name__, group=key, title=label))
        return _NullLayout()
    if state.detached_target is not None:
        if key == state.detached_target:
            return state.detached_layout.column(align=True)
        if isinstance(layout, _NullLayout):
            return _NullLayout()
    if state.search_filter_groups is not None and key not in state.search_filter_groups:
        return None
    if isinstance(layout, _FilteredLayout):
        layout = layout.layout
    box = layout.box()
    header = box.row(align=True)
    controls = header.row(align=True)
    controls.alignment = "LEFT"
    is_open = state.search_filter_groups is not None or getattr(settings, property_name)
    controls.prop(
        settings,
        property_name,
        text="",
        icon="TRIA_DOWN" if is_open else "TRIA_RIGHT",
        emboss=False,
    )
    title = controls.row(align=True)
    title.alignment = "LEFT"
    title.prop(
        settings,
        property_name,
        text=label,
        icon=icon,
        emboss=False,
    )
    if property_name in SECTION_VISIBILITY_PROPERTIES and state.search_filter_groups is None:
        draw_section_fold_actions(header, property_name)
    preferences = get_preferences(bpy.context)
    experimental_features = bool(
        preferences and getattr(preferences, "enable_experimental_features", False)
    )
    if experimental_features and state.drawing_section is not None and state.detached_target is None:
        actions = header.row(align=True)
        actions.alignment = "RIGHT"
        detach = actions.operator("wm.airetopo_detach_group", text="", icon="XRAY", emboss=False)
        detach.section = state.drawing_section.__name__
        detach.group = key
        detach.title = label

    if not is_open:
        return None

    content = box.column(align=True)
    content.separator()
    if state.search_filter_groups is not None:
        return _FilteredLayout(content, state.search_filter_terms)
    return content


def draw_enum_icon_toggle(layout, data_path, settings, property_name, items):
    row = layout.row(align=True)
    current_value = getattr(settings, property_name)
    for value, label, icon in items:
        operator = row.operator(
            "wm.context_set_enum",
            text=label,
            icon=icon,
            depress=current_value == value,
        )
        operator.data_path = f"{data_path}.{property_name}"
        operator.value = value
    return row


def draw_fab_variant_visibility(layout):
    for variant in ("HIGH", "LOW", "MID"):
        row = layout.row(align=True)
        row.label(text=variant)
        hide = row.operator("object.polygroups_fab_variant_visibility", text="Hide", icon="HIDE_ON")
        hide.variant, hide.hidden = variant, True
        show = row.operator("object.polygroups_fab_variant_visibility", text="Show", icon="HIDE_OFF")
        show.variant, show.hidden = variant, False


def draw_section_header_icon(self, context):
    self.layout.label(text="", icon=self.bl_icon)


def addon_version_string():
    package_name = __package__.split(".")[0]
    addon_module = sys.modules.get(package_name)
    version = getattr(addon_module, "bl_info", {}).get("version", (0, 0, 0))
    return ".".join(str(item) for item in version)


def update_panel_labels(context=None):
    for cls in state.section_panel_classes:
        text_key = getattr(cls, "bl_text_key", None)
        if text_key is None:
            continue

        cls.bl_label = f"{cls.bl_order:02d} | {t(context, text_key)}"


def section_content_visible(panel, context):
    if state.custom_capturing:
        return True
    if state.search_probing or state.search_filter_groups is not None:
        return True
    if state.detached_target is not None:
        return True
    settings = getattr(context.scene, "airetopo_panel_visibility_settings", None)
    if settings is None:
        return True

    property_name = getattr(panel, "visibility_property", "")
    return bool(getattr(settings, property_name, True))


def draw_section_panel_content(panel_class, context, layout, visibility_property):
    previous_section = state.drawing_section
    state.drawing_section = panel_class
    panel = SimpleNamespace(
        layout=layout,
        visibility_property=visibility_property,
    )
    for name in dir(panel_class):
        if not name.startswith("draw"):
            continue

        value = getattr(panel_class, name, None)
        if callable(value):
            setattr(panel, name, value.__get__(panel, panel_class))

    try:
        panel_class.draw(panel, context)
    except Exception as error:
        print(f"AI Retopo Toolkit: failed to draw {panel_class.__name__}: {error}")
        if hasattr(layout, 'errors'):
            layout.errors.append(f'{panel_class.__name__}: {error}')
        layout.label(text="Section draw error. Check console.", icon="ERROR")
    finally:
        state.drawing_section = previous_section


def draw_detached_group(context, layout, section, group):
    panel_class = next((cls for cls in state.section_panel_classes if cls.__name__ == section), None)
    if panel_class is None:
        return
    state.detached_target, state.detached_layout = group, layout
    try:
        draw_section_panel_content(panel_class, context, _NullLayout(), "")
    finally:
        state.detached_target, state.detached_layout = None, None


def collect_window_groups(context):
    state.group_discovery = []
    try:
        for panel_class in state.section_panel_classes:
            draw_section_panel_content(panel_class, context, _NullLayout(), "")
        return list(state.group_discovery)
    finally:
        state.group_discovery = None


def draw_material_mode_buttons(layout, context, settings):
    layout.label(text=t(context, "material_mode"))

    first_row = layout.row(align=True)
    source_operator = first_row.operator(
        "wm.context_set_enum",
        text=t(context, "material_source_texture"),
        depress=settings.material_mode == "TEXTURE_ONLY",
    )
    source_operator.data_path = "scene.polygroups_generator_settings.material_mode"
    source_operator.value = "TEXTURE_ONLY"

    tint_operator = first_row.operator(
        "wm.context_set_enum",
        text=t(context, "material_texture_color"),
        depress=settings.material_mode == "TEXTURE_TINT",
    )
    tint_operator.data_path = "scene.polygroups_generator_settings.material_mode"
    tint_operator.value = "TEXTURE_TINT"

    second_row = layout.row(align=True)
    color_operator = second_row.operator(
        "wm.context_set_enum",
        text=t(context, "material_random_color"),
        depress=settings.material_mode == "COLOR_ONLY",
    )
    color_operator.data_path = "scene.polygroups_generator_settings.material_mode"
    color_operator.value = "COLOR_ONLY"

    checker_operator = second_row.operator(
        "wm.context_set_enum",
        text=t(context, "material_checker_texture"),
        depress=settings.material_mode == "CHECKER_TEXTURE",
    )
    checker_operator.data_path = "scene.polygroups_generator_settings.material_mode"
    checker_operator.value = "CHECKER_TEXTURE"


def draw_optional_prop(layout, data, property_name, text="", **kwargs):
    if data is None or not hasattr(data, property_name):
        return False

    try:
        layout.prop(data, property_name, text=text, **kwargs)
    except Exception:
        return False

    return True


def draw_overlay_polygon_limit_status(layout, context, polygon_limit, text_key):
    active_object = context.active_object
    if (
        polygon_limit <= 0
        or active_object is None
        or active_object.type != "MESH"
        or len(active_object.data.polygons) <= polygon_limit
    ):
        return
    layout.label(
        text=t(
            context,
            text_key,
            polygons=f"{len(active_object.data.polygons):,}",
            limit=f"{polygon_limit:,}",
        ),
        icon="INFO",
    )


def draw_ai_input_image_controls(layout, context, settings, provider):
    layout.prop_search(
        settings,
        "input_image_name",
        bpy.data,
        "images",
        text=t(context, "ai_input_image"),
    )

    image_row = layout.row(align=True)
    base_operator = image_row.operator(
        "object.airetopo_select_material_image",
        text=t(context, "select_base_color_image"),
        icon="MATERIAL",
    )
    base_operator.provider = provider
    base_operator.image_kind = "BASE_COLOR"

    normal_operator = image_row.operator(
        "object.airetopo_select_material_image",
        text=t(context, "select_normal_map_image"),
        icon="NORMALS_FACE",
    )
    normal_operator.provider = provider
    normal_operator.image_kind = "NORMAL"

    preview_operator = image_row.operator(
        "object.airetopo_preview_input_image",
        text=t(context, "preview_input_image"),
        icon="IMAGE",
    )
    preview_operator.provider = provider


def draw_seam_gap_controls(layout, context, settings):
    gap_box = layout.box()
    gap_box.label(text=t(context, "seam_gap_check"), icon="VIEWZOOM")
    gap_column = gap_box.column(align=True)
    gap_column.prop(settings, "seam_gap_max_edges", text=t(context, "seam_gap_max_edges"))
    gap_column.prop(settings, "seam_gap_max_distance", text=t(context, "seam_gap_max_distance"))
    gap_column.prop(settings, "seam_gap_include_junctions", text=t(context, "seam_gap_include_junctions"))
    action_row = gap_column.row(align=True)
    check_operator = action_row.operator(
        "mesh.polygroups_check_seam_gaps",
        text=t(context, "check_seam_gaps"),
        icon="VIEWZOOM",
    )
    check_operator.mode = "SELECT"
    close_operator = action_row.operator(
        "mesh.polygroups_check_seam_gaps",
        text=t(context, "close_seam_gaps"),
        icon="EDGE_SEAM",
    )
    close_operator.mode = "MARK"
    gap_column.operator(
        "mesh.polygroups_check_and_close_seam_gaps",
        text=t(context, "check_and_close_seam_gaps"),
        icon="CHECKMARK",
    )
    gap_column.operator(
        "mesh.polygroups_connect_seam_gap_pairs",
        text=t(context, "connect_seam_gap_pairs"),
        icon="AUTOMERGE_ON",
    )
    gap_box.label(text=t(context, "seam_gap_status", value=settings.seam_gap_status), icon="INFO")


def draw_import_remesh_options(layout, context, settings, prefix, stacked_labels=False):
    column = layout.column(align=True)
    column.enabled = not settings.batch_is_running or settings.batch_stage == "PAUSED"
    column.prop(settings, prefix + "_auto_remesh", text="Auto Remesh")
    enabled = getattr(settings, prefix + "_auto_remesh")
    if stacked_labels:
        column.label(text=settings.bl_rna.properties[prefix + "_remesh_method"].name)
    method_row = column.row(align=True)
    method_row.enabled = enabled
    method_row.prop(settings, prefix + "_remesh_method", expand=True, **({"text": ""} if stacked_labels else {}))
    if enabled:
        method = getattr(settings, prefix + "_remesh_method")
        if method == "QUAD":
            if stacked_labels:
                column.label(text=settings.bl_rna.properties[prefix + "_remesh_preset"].name)
            presets = column.row(align=True)
            presets.prop(settings, prefix + "_remesh_preset", expand=True, **({"text": ""} if stacked_labels else {}))
            count = dict(get_remesh_preset_counts(context))[
                getattr(settings, prefix + "_remesh_preset")
            ]
            column.label(text=f'{t(context, "quad_count")}: {count:,}')
        else:
            column.prop(
                settings,
                prefix + "_voxel_size",
                text=t(context, "voxel_size"),
            )
        column.prop(settings, prefix + "_clear_material", text="Clear Material")
        if prefix == "file_import":
            column.prop(
                settings,
                "file_import_remove_small_loose_parts",
                text=t(context, "remove_small_loose_parts"),
            )
            loose_cleanup = column.column(align=True)
            loose_cleanup.enabled = settings.file_import_remove_small_loose_parts
            loose_cleanup.prop(
                settings,
                "file_import_small_loose_part_metric",
                text=t(context, "small_loose_part_metric"),
            )
            loose_cleanup.prop(
                settings,
                "file_import_small_loose_part_threshold_percent",
                text=t(context, "small_loose_part_threshold"),
            )
        column.prop(
            settings,
            prefix + "_auto_smart_uv_project",
            text=t(context, "auto_smart_uv_project"),
        )
        if stacked_labels:
            column.label(text=t(context, "import_unwrap_method"))
        unwrap_method_row = column.row(align=True)
        unwrap_method_row.enabled = getattr(settings, prefix + "_auto_smart_uv_project")
        unwrap_method_row.prop(
            settings,
            prefix + "_auto_unwrap_method",
            text="" if stacked_labels else t(context, "import_unwrap_method"),
            expand=True,
        )
        if getattr(settings, prefix + "_auto_unwrap_method") == "SMART":
            surface_angle_row = column.row(align=True)
            surface_angle_row.enabled = getattr(settings, prefix + "_auto_smart_uv_project")
            surface_angle_row.prop(
                context.scene.polygroups_seam_preparation_settings,
                "smart_seam_angle_limit",
                text=t(context, "smart_seam_angle_limit"),
            )
    column.prop(settings, prefix + "_separate_collections", text=t(context, "import_separate_collections"))


def draw_batch_stage_heading(layout, title, settings, stage_number, property_name=None, active=True):
    layout.separator(type="LINE")
    row = layout.row(align=True)
    heading = row.row(align=True)
    if property_name:
        heading.enabled = active and (not settings.batch_is_running or settings.batch_stage == "PAUSED")
        heading.prop(settings, property_name, text=title)
    else:
        heading.label(text=title)
    expanded = bool(settings.batch_expanded_stages & (1 << (stage_number - 1)))
    row.operator("object.polygroups_toggle_batch_stage", text="",
                 icon="TRIA_UP" if expanded else "TRIA_DOWN", emboss=False).stage = stage_number
    layout.separator(type="LINE")
    return expanded


def draw_import_progress(layout, context, settings):
    if settings.phase2_pipeline_state and not settings.batch_is_running:
        from ..core.phase2_progress import draw_pipeline_progress
        draw_pipeline_progress(layout, context, settings)
        return
    from ..operators.import_queue import redo_collections, selected_redo_collection

    box = layout.box()
    box.progress(factor=settings.batch_import_progress / 100, type="BAR",
                 text=f'{t(context, "import_total_progress")}: {settings.batch_import_progress:.1f}%')
    box.progress(factor=settings.batch_current_progress / 100, type="BAR",
                 text=f'{t(context, "import_current_progress")}: {settings.batch_current_progress:.1f}%')
    box.progress(factor=settings.batch_remesh_progress / 100, type="BAR",
                 text=f'{t(context, "import_remesh_progress")}: {settings.batch_remesh_progress:.1f}%')
    box.progress(factor=settings.batch_baking_progress / 100, type="BAR",
                 text=f'{t(context, "import_baking_progress")}: {settings.batch_baking_progress:.1f}%')
    box.label(text=t(context, "import_elapsed_time", value=format_duration(settings.batch_elapsed_seconds)))
    box.label(text=t(context, "import_current_time", value=format_duration(settings.batch_current_seconds)))
    if settings.batch_imported_count:
        box.label(text=t(context, "import_average_time", value=format_duration(settings.batch_average_seconds)))
    if settings.batch_eta_seconds >= 0:
        box.label(text=t(context, "import_remaining_time", value=format_duration(settings.batch_eta_seconds)))
    elif settings.batch_is_running:
        box.label(text=t(context, "import_estimating_time"))
    box.label(text=t(context, "total_files", value=settings.batch_total_count))
    box.label(text=t(context, "import_completed", value=settings.batch_imported_count))
    box.label(text=t(context, "import_failed", value=settings.batch_failed_count))
    box.label(text=t(context, "remaining_files", value=settings.batch_remaining_count))
    if settings.batch_current_file:
        box.label(text=t(context, "current_file", value=settings.batch_current_file))
    if settings.batch_stage:
        box.label(text=t(context, "import_stage_" + settings.batch_stage))
    if settings.batch_last_error:
        box.label(text=settings.batch_last_error, icon="ERROR")
    if settings.batch_is_running:
        if settings.batch_cancel_requested:
            box.label(text=t(context, "import_cancelling"))
        elif settings.batch_stop_requested:
            box.label(text=t(context, "import_stopping"))
        elif settings.batch_is_paused and settings.batch_stage != "PAUSED":
            box.label(text=t(context, "import_pausing"))
        row = box.row(align=True)
        row.enabled = not settings.batch_cancel_requested
        controls = row.row(align=True)
        controls.enabled = not settings.batch_stop_requested
        if settings.batch_stage == "PAUSED":
            controls.operator(
                "object.polygroups_import_control",
                text=t(context, "import_do_next"),
                icon="FRAME_NEXT",
            ).action = "NEXT_ONE"
            controls.operator(
                "object.polygroups_import_control",
                text=t(context, "import_do_next_all"),
                icon="PLAY",
            ).action = "NEXT_ALL"
        else:
            controls.operator(
                "object.polygroups_import_control",
                text=t(context, "import_resume" if settings.batch_is_paused else "import_pause"),
                icon="PLAY" if settings.batch_is_paused else "PAUSE",
            ).action = "PAUSE"
        row.operator("object.polygroups_import_control", text=t(context, "import_stop")).action = "STOP"
        row.operator("object.polygroups_import_control", text=t(context, "import_cancel"), icon="CANCEL").action = "CANCEL"
    elif redo_collections(context.view_layer):
        collections = redo_collections(context.view_layer)
        collection = selected_redo_collection(context)
        index = collections.index(collection)
        box.separator(type="LINE")
        box.label(text=t(context, "batch_redo_title"))
        row = box.row(align=True)
        previous = row.row(align=True)
        previous.enabled = index > 0
        previous.operator("object.polygroups_batch_redo_select", text="", icon="TRIA_LEFT").direction = "PREVIOUS"
        row.label(text=collection.name, icon="OUTLINER_COLLECTION")
        following = row.row(align=True)
        following.enabled = index < len(collections) - 1
        following.operator("object.polygroups_batch_redo_select", text="", icon="TRIA_RIGHT").direction = "NEXT"
        redo = box.operator("object.polygroups_batch_import", text=t(context, "batch_redo_button"), icon="FILE_REFRESH")
        redo.use_file_selection = False
        redo.redo_collection_name = collection.name


def draw_batch_processing(content, context, settings):
    editable = not settings.batch_is_running or settings.batch_stage == "PAUSED"
    outside = content.column(align=True)
    outside.enabled = editable
    outside.prop(settings, "batch_disable_view_assist", text=t(context, "disable_view_assist"))
    separate = outside.row(align=True)
    separate.enabled = not settings.batch_phase2_enabled
    separate.prop(settings, "batch_separate_collections", text=t(context, "import_separate_collections"))

    content.separator()
    content.label(text=t(context, "batch_stages"), icon="MODIFIER")
    if draw_batch_stage_heading(content, t(context, "batch_stage_basics"), settings, 1):
        basics = content.column(align=True)
        basics.enabled = editable
        basics.prop(settings, "batch_auto_rename_objects", text=t(context, "auto_rename_objects"))
        basics.prop(settings, "batch_apply_weld", text=t(context, "apply_weld"))

    if draw_batch_stage_heading(content, t(context, "batch_stage_first"),
                                settings, 2, "batch_stage_2_enabled"):
        first = content.column(align=True)
        first.enabled = editable and settings.batch_stage_2_enabled
        first.prop(settings, "batch_auto_remesh", text="Auto Remesh")
        first_remesh_options = first.column(align=True)
        first_remesh_options.enabled = settings.batch_auto_remesh
        method = first_remesh_options.row(align=True)
        method.prop(settings, "batch_remesh_method", expand=True)
        if settings.batch_remesh_method == "QUAD":
            first_remesh_options.prop(settings, "batch_remesh_preset", expand=True)
        else:
            first_remesh_options.prop(settings, "batch_voxel_size", text=t(context, "voxel_size"))
        first_remesh_options.prop(settings, "batch_clear_material", text="Clear Material")
        first.prop(
            settings,
            "batch_first_remove_small_loose_parts",
            text=t(context, "remove_small_loose_parts"),
        )
        loose_cleanup = first.column(align=True)
        loose_cleanup.enabled = settings.batch_first_remove_small_loose_parts
        loose_cleanup.prop(
            settings,
            "batch_first_small_loose_part_metric",
            text=t(context, "small_loose_part_metric"),
        )
        loose_cleanup.prop(
            settings,
            "batch_first_small_loose_part_threshold_percent",
            text=t(context, "small_loose_part_threshold"),
        )
        first.prop(settings, "batch_auto_smart_uv_project", text=t(context, "auto_smart_uv_project"))
        unwrap_method = first.row()
        unwrap_method.enabled = settings.batch_auto_smart_uv_project
        unwrap_method.prop(settings, "batch_auto_unwrap_method", text=t(context, "import_unwrap_method"))
        if settings.batch_auto_unwrap_method == "SMART":
            angle = first.row()
            angle.enabled = settings.batch_auto_smart_uv_project
            angle.prop(settings, "batch_first_surface_angle", text=t(context, "smart_seam_angle_limit"))
        first.separator()
        first.prop(settings, "batch_first_uv_repair_enabled", text=t(context, "uv_repair"))
        first.prop(settings, "batch_first_geometry_repair", text=t(context, "batch_geometry_repair"))
        first.prop(settings, "fold_repair_dangling", text=t(context, "fold_repair_dangling"))
        repair = first.column(align=True)
        repair.enabled = settings.batch_first_uv_repair_enabled
        repair.prop(settings, "batch_first_uv_repair_threshold", text=t(context, "uv_repair_threshold"))
        repair.prop(settings, "batch_first_uv_repair_min_faces", text=t(context, "uv_repair_min_faces"))
        repair.prop(settings, "batch_first_uv_repair_surface_angle", text=t(context, "uv_repair_surface_angle"))
        repair.prop(settings, "batch_first_uv_repair_pin_generated", text=t(context, "uv_repair_pin_generated"))

    if draw_batch_stage_heading(content, t(context, "batch_stage_narrow"),
                                settings, 3, "batch_narrow_island_enabled"):
        narrow_stage = content.column(align=True)
        narrow_stage.enabled = editable and settings.batch_narrow_island_enabled
        narrow = context.scene.polygroups_seam_finalization_settings
        for property_name, label in (
            ("narrow_island_width", "narrow_island_width"),
            ("batch_narrow_island_max_width_percent", "narrow_island_max_width_percent"),
            ("narrow_island_min_area_percent", "narrow_island_min_area_percent"),
            ("narrow_island_min_faces", "narrow_island_min_faces"),
            ("narrow_island_min_length", "narrow_island_min_length"),
            ("narrow_island_create_edges", "narrow_island_create_edges"),
            ("narrow_island_smart_relax", "narrow_island_smart_relax"),
        ):
            owner = settings if property_name.startswith("batch_") else narrow
            narrow_stage.prop(owner, property_name, text=t(context, label))

    if draw_batch_stage_heading(content, t(context, "batch_stage_small_islands"),
                                settings, 4, "batch_small_islands_enabled"):
        small_stage = content.column(align=True)
        small_stage.enabled = editable and settings.batch_small_islands_enabled
        for property_name, label in (
            ("batch_small_island_threshold", "small_islands_threshold"),
            ("batch_small_island_protect_pinned", "small_islands_pinned"),
            ("batch_small_island_protect_sharp", "small_islands_sharp"),
            ("batch_small_island_protect_materials", "small_islands_materials"),
        ):
            small_stage.prop(settings, property_name, text=t(context, label))

    for number, title in (
        (3, t(context, "batch_stage_second")),
        (4, t(context, "batch_stage_third")),
    ):
        stage_number = 5 if number == 3 else 8
        if draw_batch_stage_heading(content, title, settings, stage_number,
                                    f"batch_stage_{number}_enabled"):
            stage = content.column(align=True)
            stage.enabled = editable and getattr(settings, f"batch_stage_{number}_enabled")
            if number == 4:
                stage.prop(settings, "batch_stage_4_reset_smart_seams", text=t(context, "batch_reset_smart_seams"))
                reset_angle = stage.row()
                reset_angle.enabled = settings.batch_stage_4_reset_smart_seams
                reset_angle.prop(settings, "batch_stage_4_reset_smart_seams_angle",
                                 text=t(context, "smart_seam_angle_limit"))
                stage.separator()
            stage.prop(settings, f"batch_stage_{number}_auto_remesh", text="Auto Remesh (Quad)")
            remesh_options = stage.column(align=True)
            remesh_options.enabled = getattr(settings, f"batch_stage_{number}_auto_remesh")
            preset = getattr(settings, f"batch_stage_{number}_remesh_preset")
            remesh_options.prop(settings, f"batch_stage_{number}_remesh_preset", expand=True)
            remesh_options.label(text=f'{preset}: {dict(get_remesh_preset_counts(context))[preset]:,} quads')
            remesh_options.prop(settings, f"batch_stage_{number}_use_materials", text=t(context, "use_materials"))
            remesh_options.prop(settings, f"batch_stage_{number}_prepare_polygroups", text=t(context, "batch_prepare_polygroups"))
            remesh_options.prop(settings, f"batch_stage_{number}_material_seams", text=t(context, "batch_material_seams"))
            remesh_options.prop(settings, f"batch_stage_{number}_smart_relax_edges", text="Smart Relax Edges")
            stage.prop(settings, f"batch_stage_{number}_remove_small_loose_parts",
                       text=t(context, "remove_small_loose_parts"))
            loose_cleanup = stage.column(align=True)
            loose_cleanup.enabled = getattr(settings, f"batch_stage_{number}_remove_small_loose_parts")
            loose_cleanup.prop(settings, f"batch_stage_{number}_small_loose_part_metric",
                               text=t(context, "small_loose_part_metric"))
            loose_cleanup.prop(settings, f"batch_stage_{number}_small_loose_part_threshold_percent",
                               text=t(context, "small_loose_part_threshold"))
            stage.prop(settings, f"batch_stage_{number}_autofix_enabled", text=t(context, "batch_second_autofix"))
            autofix = stage.column(align=True)
            autofix.enabled = getattr(settings, f"batch_stage_{number}_autofix_enabled")
            for suffix in ("fin_loose", "close_nonmanifold", "triangulate_ngons"):
                autofix.prop(settings, f"batch_stage_{number}_autofix_{suffix}",
                             text=t(context, "batch_second_autofix_" + suffix))
            if number == 4:
                stage.prop(settings, "batch_stage_4_topology_guard", text=t(context, "batch_topology_guard"))
            stage.prop(settings, f"batch_stage_{number}_auto_unwrap", text=t(context, "auto_smart_uv_project"))
            unwrap_method = stage.row(align=True)
            unwrap_method.enabled = getattr(settings, f"batch_stage_{number}_auto_unwrap")
            unwrap_method.prop(
                settings, f"batch_stage_{number}_auto_unwrap_method",
                text=t(context, "import_unwrap_method"),
            )

            stage.prop(settings, f"batch_stage_{number}_uv_repair_enabled", text=t(context, "uv_repair"))
            stage.prop(settings, f"batch_stage_{number}_geometry_repair", text=t(context, "batch_geometry_repair"))
            stage.prop(settings, "fold_repair_dangling", text=t(context, "fold_repair_dangling"))
            repair = stage.column(align=True)
            repair.enabled = getattr(settings, f"batch_stage_{number}_uv_repair_enabled")
            for suffix in ("threshold", "min_faces", "surface_angle", "pin_generated"):
                repair.prop(settings, f"batch_stage_{number}_uv_repair_{suffix}",
                            text=t(context, "uv_repair_" + suffix))

        if number == 3:
            if draw_batch_stage_heading(content, t(context, "batch_stage_second_narrow"),
                                        settings, 6, "batch_second_narrow_island_enabled"):
                second_narrow = content.column(align=True)
                second_narrow.enabled = editable and settings.batch_second_narrow_island_enabled
                for suffix, label in (
                    ("width", "narrow_island_width"),
                    ("max_width_percent", "narrow_island_max_width_percent"),
                    ("min_area_percent", "narrow_island_min_area_percent"),
                    ("min_faces", "narrow_island_min_faces"),
                    ("min_length", "narrow_island_min_length"),
                    ("create_edges", "narrow_island_create_edges"),
                    ("smart_relax", "narrow_island_smart_relax"),
                ):
                    second_narrow.prop(settings, f"batch_second_narrow_island_{suffix}",
                                       text=t(context, label))

            if draw_batch_stage_heading(content, t(context, "batch_stage_second_small_islands"),
                                        settings, 7, "batch_second_small_islands_enabled"):
                second_small = content.column(align=True)
                second_small.enabled = editable and settings.batch_second_small_islands_enabled
                for suffix, label in (
                    ("threshold", "small_islands_threshold"),
                    ("protect_pinned", "small_islands_pinned"),
                    ("protect_sharp", "small_islands_sharp"),
                    ("protect_materials", "small_islands_materials"),
                ):
                    second_small.prop(settings, f"batch_second_small_island_{suffix}",
                                      text=t(context, label))

    # Phase 2 does packing, baking and LODs itself; stages 9-12 stay off while it is on.
    standalone = not settings.batch_phase2_enabled
    if draw_batch_stage_heading(content, t(context, "batch_stage_packing"),
                                settings, 9, "batch_stage_5_enabled", standalone):
        pack = content.column(align=True)
        pack.enabled = editable and settings.batch_stage_5_enabled
        installed, enabled, available = uvpackmaster_status(context)
        pack.label(text=t(context, "batch_pack_available" if available else "batch_pack_missing"),
                   icon="CHECKMARK" if available else "ERROR")

    if draw_batch_stage_heading(content, t(context, "batch_stage_autobake"),
                                settings, 10, "batch_autobake_enabled", standalone):
        autobake = content.column(align=True)
        autobake.enabled = editable and settings.batch_autobake_enabled
        autobake.prop(settings, "batch_autobake_cage_mode", expand=True)

    if draw_batch_stage_heading(content, t(context, "batch_stage_smart_decimate"),
                                settings, 11, "batch_smart_decimate_enabled", standalone):
        decimate = content.column(align=True)
        decimate.enabled = editable and settings.batch_smart_decimate_enabled
        decimate.prop(context.scene.polygroups_mesh_finalization_settings, "smart_decimate_smart_arrange")
        decimate.prop(settings, "batch_smart_decimate_triangle_limit", text=t(context, "smart_decimate_triangle_limit"))

    if draw_batch_stage_heading(content, t(context, "batch_stage_smart_lods"),
                                settings, 12, "batch_smart_lods_enabled", standalone):
        lods = content.column(align=True)
        lods.enabled = editable and settings.batch_smart_lods_enabled
        lods.prop(settings, "batch_smart_lods_count", text=t(context, "batch_lods_count"))
        for index in range(1, settings.batch_smart_lods_count + 1):
            lods.prop(settings, f"batch_smart_lods_target_{index}", text=f"LOD{index-1} Tris")
        draw_lod_decimate_method(lods, context, settings, "batch_smart_lods_")
        lods.prop(settings, "batch_smart_lods_final_decimate", text=t(context, "batch_lods_fallback"))
        lods.prop(settings, "batch_smart_lods_triangulate_all", text=t(context, "batch_lods_triangulate"))

    if draw_batch_stage_heading(content, t(context, "batch_stage_phase2"),
                                settings, 13, "batch_phase2_enabled"):
        phase2 = content.column(align=True)
        phase2.enabled = editable and settings.batch_phase2_enabled
        phase2.label(text=t(context, "batch_phase2_hint"), icon="INFO")
        phase2.label(text=t(context, "batch_phase2_replaces"))
        phase2.label(text=t(context, "batch_phase2_needs_separate"))
        # Same settings as the Phase 2 queue options; edits here change Phase 2 too.
        phase2.prop(settings, "phase2_clear_generated", text=t(context, "phase2_clear"))
        phase2.separator()
        phase2.prop(settings, "phase2_run_engine", expand=True)
        meshes = phase2.row(align=True)
        meshes.prop(settings, "phase2_export_glb")
        meshes.prop(settings, "phase2_export_fbx")
        final = context.scene.polygroups_mesh_finalization_settings
        unity = settings.phase2_run_engine == "UNITY"
        names = phase2.column(align=True)
        names.prop(final, "unity_asset_name" if unity else "unreal_lod_asset_name", text="Asset Name")
        names.prop(final, "unity_name_index" if unity else "unreal_lod_name_index", text="Name Index")
        names.prop(final, "unity_asset_index" if unity else "unreal_lod_version_index", text="Version Index")


def draw_lod_decimate_method(layout, context, settings, prefix):
    """LOD decimate method menu; seam protection applies to UV Preserve only."""
    layout.prop(context.scene.polygroups_mesh_finalization_settings, "smart_lods_smart_arrange")
    layout.prop(settings, prefix + "decimate_method", text=t(context, "lod_decimate_method"))
    seams = layout.row(align=True)
    seams.enabled = getattr(settings, prefix + "decimate_method") == "UV_PRESERVE"
    seams.prop(settings, prefix + "uv_seam_mode", text=t(context, "uv_decimate_seam_mode"))


def draw_studio_position(layout, context, target, obj, axes, label):
    layout.label(text=label)
    scale = context.scene.unit_settings.scale_length
    for axis in axes:
        row = layout.row(align=True)
        minus_icon, plus_icon = ('TRIA_LEFT', 'TRIA_RIGHT') if axis == 'X' else ('TRIA_DOWN', 'TRIA_UP')
        minus = row.operator("render.polygroups_move_studio", text="", icon=minus_icon)
        minus.target, minus.axis, minus.direction = target, axis, 'NEGATIVE'
        value = obj.matrix_world.translation['XYZ'.index(axis)] * scale
        caption = t(context, 'studio_axis_' + axis.lower())
        row.label(text=f"{caption}: {value:.2f} m")
        plus = row.operator("render.polygroups_move_studio", text="", icon=plus_icon)
        plus.target, plus.axis, plus.direction = target, axis, 'POSITIVE'
