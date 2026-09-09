from .custom_icons import icon_kwargs
import os
import sys
import time
from types import SimpleNamespace

import bpy

from .localization import get_preferences
from .localization import t
from .properties import SECTION_SUBSECTION_PROPERTIES
from .core.remesh_defaults import get_remesh_preset_counts
from .core.import_timing import format_duration


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


_DRAWING_SECTION = None
_DETACHED_TARGET = None
_DETACHED_LAYOUT = None
_GROUP_DISCOVERY = None
_SEARCH_PROBING = False
_SEARCH_FILTER_GROUPS = None
_SEARCH_FILTER_TERMS = ()


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
    global _SEARCH_PROBING
    result = _SearchResult(query)
    title = t(context, panel_class.bl_text_key)
    title_text = f"{title} {panel_class.__name__}"
    if all(term in title_text.casefold().replace("_", " ") for term in result.terms):
        result.section_match = True
    _SEARCH_PROBING = True
    try:
        draw_section_panel_content(
            panel_class,
            context,
            _SearchProbeLayout(result),
            getattr(panel_class, "visibility_property", ""),
        )
    finally:
        _SEARCH_PROBING = False
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


def draw_collapsible_box(layout, settings, property_name, label, icon):
    key = settings.path_from_id() + "." + property_name
    if isinstance(layout, _SearchProbeLayout):
        return layout.grouped(key, label)
    if _GROUP_DISCOVERY is not None:
        _GROUP_DISCOVERY.append(dict(section=_DRAWING_SECTION.__name__, group=key, title=label))
        return _NullLayout()
    if _DETACHED_TARGET is not None:
        if key == _DETACHED_TARGET:
            return _DETACHED_LAYOUT.column(align=True)
        if isinstance(layout, _NullLayout):
            return _NullLayout()
    if _SEARCH_FILTER_GROUPS is not None and key not in _SEARCH_FILTER_GROUPS:
        return None
    if isinstance(layout, _FilteredLayout):
        layout = layout.layout
    box = layout.box()
    header = box.row(align=True)
    controls = header.row(align=True)
    controls.alignment = "LEFT"
    is_open = _SEARCH_FILTER_GROUPS is not None or getattr(settings, property_name)
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
    subsection_properties = SECTION_SUBSECTION_PROPERTIES.get(property_name, ())
    if subsection_properties and _SEARCH_FILTER_GROUPS is None:
        actions = header.row(align=True)
        actions.alignment = "RIGHT"
        collapse = actions.operator(
            "object.airetopo_set_section_subsection_visibility",
            text="",
            icon="REMOVE",
        )
        collapse.section_property = property_name
        collapse.visible = False
        expand = actions.operator(
            "object.airetopo_set_section_subsection_visibility",
            text="",
            icon="ADD",
        )
        expand.section_property = property_name
        expand.visible = True
    preferences = get_preferences(bpy.context)
    experimental_features = bool(
        preferences and getattr(preferences, "enable_experimental_features", False)
    )
    if experimental_features and _DRAWING_SECTION is not None and _DETACHED_TARGET is None:
        actions = header.row(align=True)
        actions.alignment = "RIGHT"
        detach = actions.operator("wm.airetopo_detach_group", text="", icon="XRAY", emboss=False)
        detach.section = _DRAWING_SECTION.__name__
        detach.group = key
        detach.title = label

    if not is_open:
        return None

    content = box.column(align=True)
    content.separator()
    if _SEARCH_FILTER_GROUPS is not None:
        return _FilteredLayout(content, _SEARCH_FILTER_TERMS)
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


def draw_section_header_icon(self, context):
    self.layout.label(text="", icon=self.bl_icon)


def addon_version_string():
    package_name = __package__.split(".")[0]
    addon_module = sys.modules.get(package_name)
    version = getattr(addon_module, "bl_info", {}).get("version", (0, 0, 0))
    return ".".join(str(item) for item in version)


def update_panel_labels(context=None):
    for cls in SECTION_PANEL_CLASSES:
        text_key = getattr(cls, "bl_text_key", None)
        if text_key is None:
            continue

        cls.bl_label = f"{cls.bl_order:02d} | {t(context, text_key)}"


def section_content_visible(panel, context):
    if _SEARCH_PROBING or _SEARCH_FILTER_GROUPS is not None:
        return True
    if _DETACHED_TARGET is not None:
        return True
    settings = getattr(context.scene, "airetopo_panel_visibility_settings", None)
    if settings is None:
        return True

    property_name = getattr(panel, "visibility_property", "")
    return bool(getattr(settings, property_name, True))


def draw_section_panel_content(panel_class, context, layout, visibility_property):
    global _DRAWING_SECTION
    previous_section = _DRAWING_SECTION
    _DRAWING_SECTION = panel_class
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
        layout.label(text="Section draw error. Check console.", icon="ERROR")
    finally:
        _DRAWING_SECTION = previous_section


def draw_detached_group(context, layout, section, group):
    global _DETACHED_TARGET, _DETACHED_LAYOUT
    panel_class = next((cls for cls in SECTION_PANEL_CLASSES if cls.__name__ == section), None)
    if panel_class is None:
        return
    _DETACHED_TARGET, _DETACHED_LAYOUT = group, layout
    try:
        draw_section_panel_content(panel_class, context, _NullLayout(), "")
    finally:
        _DETACHED_TARGET, _DETACHED_LAYOUT = None, None


def collect_window_groups(context):
    global _GROUP_DISCOVERY
    _GROUP_DISCOVERY = []
    try:
        for panel_class in SECTION_PANEL_CLASSES:
            draw_section_panel_content(panel_class, context, _NullLayout(), "")
        return list(_GROUP_DISCOVERY)
    finally:
        _GROUP_DISCOVERY = None


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


class VIEW3D_PT_polygroups_generator(bpy.types.Panel):
    bl_label = f"AI Retopo Toolkit v{addon_version_string()}"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_order = 0

    def draw(self, context):
        global _SEARCH_FILTER_GROUPS, _SEARCH_FILTER_TERMS
        preferences = get_preferences(context)
        layout = self.layout
        visible_layout = layout
        visibility = context.scene.airetopo_panel_visibility_settings
        search_query = visibility.panel_search.strip()
        if search_query:
            # Search results replace unrelated header/status UI while the real
            # search field is drawn directly above the first matching section.
            layout = _NullLayout()
        if preferences is not None:
            from .preferences import draw_global_notices

            draw_global_notices(layout, context, preferences)
        from . import custom_autosave

        session_box = layout.box()
        session_expanded = bool(
            preferences is None or preferences.show_panel_session_status
        )
        session_header = session_box.row(align=True)
        if preferences is not None:
            session_header.prop(
                preferences,
                "show_panel_session_status",
                text=t(context, "panel_session_status"),
                icon="TRIA_DOWN" if session_expanded else "TRIA_RIGHT",
                emboss=False,
            )
        else:
            session_header.label(text=t(context, "panel_session_status"), icon="TRIA_DOWN")

        if session_expanded:
            save_status = custom_autosave.status_snapshot()
            status_row = session_box.row(align=True)
            event = save_status["event"]
            if event == "CUSTOM":
                status_row.label(text=t(context, "autosave_status_success"), icon="CHECKMARK")
            elif event == "REGULAR":
                status_row.label(text=t(context, "regular_save_status_success"), icon="CHECKMARK")
            elif event == "ERROR":
                status_row.alert = True
                status_row.label(text=t(context, "autosave_status_error"), icon="ERROR")
            elif event == "RECOVERY":
                status_row.label(text=t(context, "autosave_recovery_created"), icon="RECOVER_LAST")
            else:
                status_row.label(text=t(context, "save_status_waiting"), icon="TIME")
            autosave_row = session_box.row(align=True)
            autosave_row.label(
                text=t(context, "last_autosave_time", value=save_status["autosave_time"]),
                icon="RECOVER_LAST",
            )
            autosave_actions = autosave_row.row(align=True)
            autosave_actions.enabled = bool(save_status["autosave_path"])
            open_autosave = autosave_actions.operator(
                "wm.airetopo_open_recent_autosave",
                text=t(context, "load_latest_autosave"),
                icon="FILE_REFRESH",
            )
            open_autosave.filepath = save_status["autosave_path"]
            show_autosave = autosave_actions.operator(
                "wm.airetopo_show_file_in_browser",
                text="",
                icon="FILE_FOLDER",
            )
            show_autosave.filepath = save_status["autosave_path"]

            regular_row = session_box.row(align=True)
            regular_row.label(
                text=t(context, "last_regular_save_time", value=save_status["regular_save_time"]),
                icon="FILE_TICK",
            )
            regular_actions = regular_row.row(align=True)
            regular_actions.enabled = bool(save_status["regular_save_path"])
            open_regular = regular_actions.operator(
                "wm.airetopo_open_saved_file",
                text=t(context, "load_latest_save"),
                icon="FILE_BLEND",
            )
            open_regular.filepath = save_status["regular_save_path"]
            show_regular = regular_actions.operator(
                "wm.airetopo_show_file_in_browser",
                text="",
                icon="FILE_FOLDER",
            )
            show_regular.filepath = save_status["regular_save_path"]
            recovery = custom_autosave.recovery_snapshot()
            if recovery["active"]:
                session_box.separator()
                recovery_box = session_box.box()
                recovery_box.label(
                    text=t(context, "recovered_file", value=os.path.basename(recovery["restored"])),
                    icon="FILE_BLEND",
                )
                if recovery["original"]:
                    recovery_box.label(
                        text=t(context, "original_file", value=os.path.basename(recovery["original"])),
                        icon="FILE_TICK",
                    )
                    save_original = recovery_box.row(align=True)
                    save_original.alert = True
                    save_original.operator(
                        "wm.airetopo_save_recovery_to_original",
                        text=t(context, "save_recovery_to_original"),
                        icon="FILE_TICK",
                    )
                    recovery_box.label(text=t(context, "save_recovery_warning"), icon="ERROR")
                else:
                    recovery_box.operator(
                        "wm.save_as_mainfile",
                        text=t(context, "save_recovery_as"),
                        icon="FILE_NEW",
                    )
            if not getattr(bpy.data, "filepath", ""):
                session_box.separator()
                recent_box = session_box.box()
                recent_expanded = bool(
                    preferences is None or preferences.show_panel_recent_autosaves
                )
                recent_header = recent_box.row(align=True)
                if preferences is not None:
                    recent_header.prop(
                        preferences,
                        "show_panel_recent_autosaves",
                        text=t(context, "recent_autosaves"),
                        icon="TRIA_DOWN" if recent_expanded else "TRIA_RIGHT",
                        emboss=False,
                    )
                else:
                    recent_header.label(text=t(context, "recent_autosaves"), icon="TRIA_DOWN")
                if recent_expanded:
                    recent_entries = custom_autosave.recent_autosaves()
                    if recent_entries:
                        recent_column = recent_box.column(align=True)
                        for entry in recent_entries:
                            modified = time.strftime(
                                "%d.%m.%Y %H:%M",
                                time.localtime(entry["modified"]),
                            )
                            entry_row = recent_column.row(align=True)
                            operator = entry_row.operator(
                                "wm.airetopo_open_recent_autosave",
                                text=f'{entry["name"]}  ·  {modified}',
                                icon="FILE_BLEND",
                            )
                            operator.filepath = entry["filepath"]
                            show_file = entry_row.operator(
                                "wm.airetopo_show_file_in_browser",
                                text="",
                                icon="FILE_FOLDER",
                            )
                            show_file.filepath = entry["filepath"]
                        recent_box.label(text=t(context, "recent_autosave_save_as_hint"), icon="INFO")
                    else:
                        recent_box.label(text=t(context, "no_recent_autosaves"), icon="INFO")
            if preferences and preferences.enable_dev_mode:
                session_box.separator()
                restart_column = session_box.column(align=True)
                restart_column.operator(
                    "wm.airetopo_dev_restart",
                    text=t(context, "dev_restart"),
                    icon="FILE_REFRESH",
                )
                restart_column.operator(
                    "wm.airetopo_dev_restart_current",
                    text=t(context, "dev_restart_current"),
                    icon="FILE_TICK",
                )
                restart_column.operator(
                    "wm.airetopo_dev_restart_without_saving",
                    text=t(context, "dev_restart_without_saving"),
                    icon="LOOP_BACK",
                )

        header = layout.row(align=True)
        expand_operator = header.operator(
            "object.airetopo_set_all_section_visibility",
            text=t(context, "show_all_sections"),
            icon="TRIA_DOWN",
        )
        expand_operator.visible = True
        collapse_operator = header.operator(
            "object.airetopo_set_all_section_visibility",
            text=t(context, "hide_all_sections"),
            icon="TRIA_RIGHT",
        )
        collapse_operator.visible = False
        header.separator()
        header.prop(
            visibility,
            "single_section_mode",
            text="",
            icon="SOLO_ON" if visibility.single_section_mode else "SOLO_OFF",
            toggle=True,
        )
        header.separator()
        settings_operator = header.operator(
            "wm.airetopo_toggle_panel_settings",
            text="",
            icon="PREFERENCES",
            depress=bool(preferences and preferences.show_panel_settings),
        )
        del settings_operator

        if preferences is not None and preferences.show_panel_settings:
            box = layout.box()
            box.prop(preferences, "interface_language", text=t(context, "language"))
            box.label(text=t(context, "main_description"))
            box.operator(
                "object.airetopo_restore_panel_defaults",
                text=t(context, "restore_defaults"),
                icon="LOOP_BACK",
            )
            box.separator()
            box.label(text=t(context, "preferences_pie_menu"), icon="MENU_PANEL")
            box.prop(preferences, "active_pie_preset", text=t(context, "pie_active_preset"))
            box.separator()
            box.label(text=t(context, "updates"), icon="FILE_REFRESH")
            update_row = box.row(align=True)
            update_row.operator(
                "wm.airetopo_check_updates",
                text=t(context, "check_updates"),
                icon="VIEWZOOM",
            )
            update_row.operator(
                "wm.airetopo_update_addon",
                text=t(context, "update_addon"),
                icon="IMPORT",
            )
            box.label(text=t(context, "update_status", value=preferences.update_status))
            if (
                preferences.update_branch
                or preferences.update_current_commit
                or preferences.update_remote_commit
            ):
                box.label(
                    text=t(
                        context,
                        "update_commits",
                        branch=preferences.update_branch or "-",
                        current=preferences.update_current_commit or "-",
                        remote=preferences.update_remote_commit or "-",
                    ),
                )
            if preferences.update_last_checked:
                box.label(
                    text=t(
                        context,
                        "update_last_checked",
                        value=preferences.update_last_checked,
                    ),
                )
            box.separator()
            box.prop(
                preferences,
                "use_env_openai_api_key",
                text=t(context, "use_env_openai_api_key"),
            )
            box.prop(preferences, "openai_api_key", text=t(context, "openai_api_key"))
            box.separator()
            box.prop(
                preferences,
                "use_env_gemini_api_key",
                text=t(context, "use_env_gemini_api_key"),
            )
            box.prop(preferences, "gemini_api_key", text=t(context, "gemini_api_key"))

        layout = visible_layout
        search_row = layout.row(align=True)
        search_row.prop(
            visibility,
            "panel_search",
            text="",
            icon="VIEWZOOM",
            placeholder=t(context, "panel_search"),
        )
        if search_query:
            clear_search = search_row.operator("wm.context_set_string", text="", icon="X")
            clear_search.data_path = "scene.airetopo_panel_visibility_settings.panel_search"
            clear_search.value = ""
        search_match_count = 0
        for panel_class, visibility_property in SECTION_PANEL_VISIBILITY:
            search_result = None
            if search_query:
                search_result = _probe_panel(panel_class, context, search_query)
                if not search_result.section_match:
                    continue
                search_match_count += 1
                outer_key = visibility.path_from_id() + "." + visibility_property
                search_result.groups.add(outer_key)
                _SEARCH_FILTER_GROUPS = search_result.groups
                _SEARCH_FILTER_TERMS = search_result.terms
            try:
                content = draw_collapsible_box(
                    layout,
                    visibility,
                    visibility_property,
                    f"{panel_class.bl_order:02d} | {t(context, panel_class.bl_text_key)}",
                    panel_class.bl_icon,
                )
                if content is not None:
                    draw_section_panel_content(panel_class, context, content, visibility_property)
            finally:
                _SEARCH_FILTER_GROUPS = None
                _SEARCH_FILTER_TERMS = ()
        if search_query and search_match_count == 0:
            layout.label(text=t(context, "panel_search_no_results"), icon="INFO")


class VIEW3D_PT_polygroups_model_preparation(bpy.types.Panel):
    bl_label = "03 |"
    bl_text_key = "section_model_preparation"
    bl_icon = "AUTOMERGE_ON"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 3
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout.box()
        settings = context.scene.polygroups_model_preparation_settings

        content = draw_topic(layout, context, "prepare_0", t(context, "model_preparation_group_prepare"), "AUTOMERGE_ON")
        if content is not None:
            column = content.column(align=True)
            column.operator(
                "object.polygroups_rename_and_apply_weld",
                text=t(context, "rename_apply_weld"),
                icon="AUTOMERGE_ON",
            )
            column.separator()
            column.operator(
                "object.polygroups_rename_objects",
                text=t(context, "rename_objects"),
                icon="OUTLINER_COLLECTION",
            )
            column.prop(settings, "weld_distance", text=t(context, "weld_distance"))
            column.operator(
                "object.polygroups_apply_weld",
                text=t(context, "apply_weld"),
                icon="AUTOMERGE_ON",
            )

        content = draw_topic(layout, context, "prepare_1", t(context, "model_preparation_group_mesh_edit"), "EDITMODE_HLT")
        if content is not None:
            content.operator(
                "mesh.polygroups_delete_and_fill",
                text=t(context, "delete_and_fill"),
                icon="MESH_DATA",
            )

        content = draw_topic(layout, context, "prepare_2", t(context, "model_preparation_group_manage"), "OUTLINER_COLLECTION")
        if content is not None:
            column = content.column(align=True)
            for prefix, label in (("Highpoly_", "Highpoly"), ("Retopo_", "Retopo")):
                row = column.row(align=True)
                for hidden, key, icon in ((True, "hide_all_named", "RESTRICT_VIEW_ON"),
                                          (False, "show_all_named", "RESTRICT_VIEW_OFF")):
                    operator = row.operator("object.polygroups_object_visibility",
                                            text=t(context, key, value=label), icon=icon)
                    operator.prefix = prefix
                    operator.hidden = hidden
            column.operator("object.polygroups_generated_collection",
                            text=t(context, "isolate_generated_collections"),
                            icon="OUTLINER_COLLECTION").action = "ISOLATE"
            row = column.row(align=True)
            row.operator("object.polygroups_generated_collection",
                         text=t(context, "previous_generated_collection"), icon="TRIA_LEFT").action = "PREVIOUS"
            row.operator("object.polygroups_generated_collection",
                         text=t(context, "next_generated_collection"), icon="TRIA_RIGHT").action = "NEXT"
            column.separator()
            column.operator(
                "object.polygroups_fix_all_generated_indices",
                text=t(context, "fix_all_generated_indices"),
                icon="FILE_REFRESH",
            )

        content = draw_topic(layout, context, "prepare_3", t(context, "model_preparation_group_seams"), "EDGE_SEAM")
        if content is not None:
            column = content.column(align=True)
            column.operator(
                "mesh.polygroups_mark_material_boundaries_seam",
                text=t(context, "generate_seams_materials"),
                icon="EDGE_SEAM",
            )
            column.prop(context.scene.polygroups_generator_settings, "checker_scale",
                        text=t(context, "checker_scale"))
            column.operator(
                "object.polygroups_apply_checker_material",
                text=t(context, "apply_checker_material"),
                icon="TEXTURE",
            )
            column.operator(
                "object.polygroups_unwrap_angle_based",
                text=t(context, "unwrap_angle_based"),
                icon="UV",
            )


def draw_import_remesh_options(layout, context, settings, prefix):
    column = layout.column(align=True)
    column.enabled = not settings.batch_is_running
    column.prop(settings, prefix + "_auto_remesh", text="Auto Remesh")
    enabled = getattr(settings, prefix + "_auto_remesh")
    method_row = column.row(align=True)
    method_row.enabled = enabled
    method_row.prop(settings, prefix + "_remesh_method", expand=True)
    if enabled:
        method = getattr(settings, prefix + "_remesh_method")
        if method == "QUAD":
            presets = column.row(align=True)
            presets.prop(settings, prefix + "_remesh_preset", expand=True)
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
        column.prop(
            settings,
            prefix + "_auto_smart_uv_project",
            text=t(context, "auto_smart_uv_project"),
        )
    column.prop(settings, prefix + "_separate_collections", text=t(context, "import_separate_collections"))


def draw_import_progress(layout, context, settings):
    box = layout.box()
    box.progress(factor=settings.batch_import_progress / 100, type="BAR",
                 text=f'{t(context, "import_total_progress")}: {settings.batch_import_progress:.1f}%')
    box.progress(factor=settings.batch_current_progress / 100, type="BAR",
                 text=f'{t(context, "import_current_progress")}: {settings.batch_current_progress:.1f}%')
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
        pause = row.row(align=True)
        pause.enabled = not settings.batch_stop_requested
        pause.operator("object.polygroups_import_control",
                       text=t(context, "import_resume" if settings.batch_is_paused else "import_pause"),
                       icon="PLAY" if settings.batch_is_paused else "PAUSE").action = "PAUSE"
        row.operator("object.polygroups_import_control", text=t(context, "import_stop")).action = "STOP"
        row.operator("object.polygroups_import_control", text=t(context, "import_cancel"), icon="CANCEL").action = "CANCEL"


class VIEW3D_PT_polygroups_import(bpy.types.Panel):
    bl_label = "01 |"
    bl_text_key = "section_import"
    bl_icon = "FILE_FOLDER"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 1
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout
        settings = context.scene.polygroups_model_preparation_settings

        content = draw_topic(layout, context, "import_0", t(context, "import_group_source"), "FILE_FOLDER")
        if content is not None:
            files_box = content.column(align=True)
            files_box.prop(settings, "batch_import_format", text=t(context, "format"))
            files_row = files_box.row(align=True)
            files_row.enabled = not settings.batch_is_running
            file_operator = files_row.operator(
                "object.polygroups_batch_import",
                text=t(context, "import_files"),
                icon="FILE_FOLDER",
            )
            file_operator.use_file_selection = True

        content = draw_topic(layout, context, "import_1", t(context, "import_group_processing"), "MODIFIER")
        if content is not None:
            files_box = content.column(align=True)
            files_box.prop(
                settings,
                "file_import_auto_rename_objects",
                text=t(context, "auto_rename_objects"),
            )
            files_box.prop(settings, "file_import_apply_weld", text=t(context, "apply_weld"))
            files_box.prop(settings, "file_import_disable_view_assist",
                           text=t(context, "disable_view_assist"))
            draw_import_remesh_options(files_box, context, settings, "file_import")

        content = draw_topic(layout, context, "import_2", t(context, "import_group_progress"), "INFO")
        if content is not None:
            draw_import_progress(content, context, settings)


class VIEW3D_PT_polygroups_batch_import(bpy.types.Panel):
    bl_label = "02 |"
    bl_text_key = "section_batch_import"
    bl_icon = "FILE_REFRESH"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 2
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout
        settings = context.scene.polygroups_model_preparation_settings

        content = draw_topic(layout, context, "batch_0", t(context, "import_group_source"), "FILE_FOLDER")
        if content is not None:
            folder_row = content.row(align=True)
            folder_row.label(text=t(context, "folder"))
            folder_row.operator("object.polygroups_select_import_folder", text="", icon="FILE_FOLDER")

            folder_path = settings.batch_import_directory or t(context, "no_folder_selected")
            content.label(text=folder_path, icon="FILE_FOLDER")
            content.prop(settings, "batch_import_format", text=t(context, "format"))
            subfolders_row = content.row()
            subfolders_row.enabled = not settings.batch_is_running
            subfolders_row.prop(settings, "batch_include_subfolders", text=t(context, "include_subfolders"))
            scan_row = content.row(align=True)
            scan_row.enabled = not settings.batch_is_running
            scan_row.operator(
                "object.polygroups_scan_import_folder",
                text=t(context, "scan_folder"),
                icon="VIEWZOOM",
            )

        content = draw_topic(layout, context, "batch_1", t(context, "import_group_processing"), "MODIFIER")
        if content is not None:
            content.prop(settings, "batch_auto_rename_objects", text=t(context, "auto_rename_objects"))
            content.prop(settings, "batch_apply_weld", text=t(context, "apply_weld"))
            content.prop(settings, "batch_disable_view_assist",
                         text=t(context, "disable_view_assist"))
            draw_import_remesh_options(content, context, settings, "batch")

        content = draw_topic(layout, context, "batch_2", t(context, "arrange_objects"), "SNAP_EDGE")
        if content is not None:
            arrange_box = content.column(align=True)
            arrange_box.prop(settings, "batch_auto_arrange_objects", text=t(context, "auto_arrange_imports"))
            arrange_box.prop(settings, "batch_arrange_spacing", text=t(context, "arrange_spacing"))
            arrange_box.prop(settings, "batch_arrange_mode", text=t(context, "arrange_mode"))
            rows_row = arrange_box.row(align=True)
            rows_row.enabled = settings.batch_arrange_mode == "GRID"
            rows_row.prop(settings, "batch_arrange_rows", text=t(context, "arrange_rows"))
            arrange_row = arrange_box.row(align=True)
            arrange_row.enabled = not settings.batch_is_running
            arrange_row.operator(
                "object.polygroups_arrange_batch_objects",
                text=t(context, "arrange_selected"),
                icon="ALIGN_CENTER",
            )

        content = draw_topic(layout, context, "batch_3", t(context, "import_group_run"), "PLAY")
        if content is not None:
            operator_row = content.row(align=True)
            operator_row.enabled = not settings.batch_is_running
            operator_row.operator_context = "EXEC_DEFAULT"
            start_import = operator_row.operator(
                "object.polygroups_batch_import",
                text=t(context, "import_folder"),
                icon="PLAY",
            )
            start_import.use_file_selection = False

        content = draw_topic(layout, context, "batch_4", t(context, "import_group_progress"), "INFO")
        if content is not None:
            draw_import_progress(content, context, settings)


class VIEW3D_PT_polygroups_remesh(bpy.types.Panel):
    bl_label = "06 |"
    bl_text_key = "section_remesh"
    bl_icon = "MOD_REMESH"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 6
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout.box()
        content = draw_topic(layout, context, "remesh_0", 'Remesh Controls', "MOD_REMESH")
        if content is not None:
            self.draw_remesh_controls(context, content)
        content = draw_topic(layout, context, "remesh_1", 'Remesh Progress', "INFO")
        if content is not None:
            self.draw_remesh_progress(context, content)

    def draw_remesh_controls(self, context, layout):
        installed, enabled, available = quad_remesher_status(context)

        if not installed:
            layout.label(text=t(context, "quad_not_installed"), icon="ERROR")
            layout.label(text=t(context, "quad_install_hint"))
            return

        if not enabled or not available:
            layout.label(text=t(context, "quad_not_enabled"), icon="ERROR")
            layout.label(text=t(context, "quad_enable_hint"))
            return

        qremesher = context.scene.qremesher

        status = context.scene.polygroups_remesh_status
        content = layout
        if content is not None:
            content = content.column()
            content.enabled = not status.is_running and not context.scene.polygroups_model_preparation_settings.batch_is_running
            content.operator(
                "object.polygroups_checked_quad_remesh",
                text=t(context, "remesh_it"),
                icon="MOD_REMESH",
            )

            preset_row = content.row(align=True)
            remesh_row = content.row(align=True)
            for label, quad_count in get_remesh_preset_counts(context):
                preset = preset_row.operator(
                    "object.polygroups_set_quad_count_preset", text=label,
                )
                preset.quad_count = quad_count
                remesh = remesh_row.operator(
                    "object.polygroups_checked_quad_remesh", text=f"Remesh {label}",
                )
                remesh.quad_count = quad_count

            content.prop(qremesher, "target_count", text=t(context, "quad_count"))
            content.prop(qremesher, "use_materials", text=t(context, "use_materials"))
            content.prop(context.scene.polygroups_model_preparation_settings,
                         "remesh_pregenerate_polygroups", text="Pregenerate Poly Groups")
            content.prop(context.scene.polygroups_model_preparation_settings,
                         "remesh_auto_generate_seams", text="Auto Generate Seams")
            content.prop(context.scene.polygroups_model_preparation_settings,
                         "remesh_auto_unwrap_checker", text="Auto Unwrap and Apply Checker")

            symmetry_row = content.row(align=True)
            symmetry_row.label(text=t(context, "symmetry"))
            symmetry_row.prop(qremesher, "symmetry_x")

            if status.is_running:
                content.operator("object.polygroups_cancel_remesh", text=t(context, "import_cancel"), icon="CANCEL")

    def draw_remesh_progress(self, context, content):
        status = context.scene.polygroups_remesh_status
        if content is not None:
            progress_box = content.column(align=True)
            if status.stage:
                progress_box.label(text=t(context, "remesh_stage_" + status.stage))
                progress_box.label(text=t(context, "remesh_source", value=status.source_name))
                progress_box.progress(factor=status.progress / 100, type="BAR", text=f"{status.progress:.1f}%")
                progress_box.label(text=t(context, "remesh_elapsed", value=format_duration(status.elapsed_seconds)))
                if status.stage == "DONE":
                    progress_box.label(text=t(context, "remesh_completed_polygons", value=f"{status.polygon_count:,}"), icon="CHECKMARK")
                    progress_box.label(text=status.result_name)
                elif status.message:
                    progress_box.label(text=status.message, icon="ERROR" if status.stage == "FAILED" else "INFO")
            else:
                progress_box.label(text=t(context, "import_group_progress"), icon="INFO")


class VIEW3D_PT_polygroups_seam_preparation(bpy.types.Panel):
    bl_label = "04 |"
    bl_text_key = "section_seam_preparation"
    bl_icon = "EDGE_SEAM"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 4
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout
        seam_settings = context.scene.polygroups_seam_preparation_settings

        layout.prop(
            seam_settings,
            "show_seams_object_mode",
            text=t(context, "show_seams_object_mode"),
            toggle=True,
            icon="EDGE_SEAM",
        )
        if seam_settings.show_seams_object_mode:
            layout.prop(
                seam_settings,
                "seam_overlay_max_polygons",
                text=t(context, "seam_overlay_max_polygons"),
            )
            draw_overlay_polygon_limit_status(
                layout,
                context,
                seam_settings.seam_overlay_max_polygons,
                "seam_overlay_skipped",
            )

        content = draw_collapsible_box(layout, seam_settings, "show_selection_group", t(context, "seam_group_selection"), "FACESEL")
        if content is not None:
            tools_column = content.column(align=True)
            tools_column.prop(seam_settings, "prefer_linked_seam", text=t(context, "prefer_linked_seam"))
            selection_row = tools_column.row(align=True)
            selection_row.operator("mesh.select_more", text=t(context, "select_more"), icon="ADD")
            selection_row.operator("mesh.select_less", text=t(context, "select_less"), icon="REMOVE")
            linked_operator = tools_column.operator(
                "mesh.select_linked", text=t(context, "select_linked_seam"), icon="LINKED",
            )
            linked_operator.delimit = {"SEAM"}
            tools_column.separator()
            tools_column.prop(
                seam_settings,
                "selection_smooth_iterations",
                text=t(context, "smooth_iterations"),
            )

            smooth_operator = tools_column.operator(
                "mesh.polygroups_smooth_face_selection",
                text=t(context, "smooth_face_selection"),
                icon="MOD_SMOOTH",
            )
            smooth_operator.iterations = seam_settings.selection_smooth_iterations

        content = draw_collapsible_box(layout, seam_settings, "show_mesh_edit_group", t(context, "model_preparation_group_mesh_edit"), "EDITMODE_HLT")
        if content is not None:
            content.operator(
                "mesh.polygroups_delete_and_fill",
                text=t(context, "delete_and_fill"),
                icon="MESH_DATA",
            )

        content = draw_collapsible_box(layout, seam_settings, "show_mark_clear_group", t(context, "seam_group_mark_clear"), "EDGE_SEAM")
        if content is not None:
            tools_column = content.column(align=True)
            tools_column.operator(
                "mesh.polygroups_mark_selected_edges_seam",
                text=t(context, "mark_selected_edges_seam"),
                icon="EDGESEL",
            )
            tools_column.operator(
                "mesh.polygroups_mark_selection_boundary_seam",
                text=t(context, "mark_selection_boundary_seam"),
                icon="EDGESEL",
            )
            tools_column.operator(
                "mesh.polygroups_clear_selected_edges_seam",
                text=t(context, "clear_selected_edges_seam"),
                icon="X",
            )
            tools_column.operator(
                "mesh.polygroups_clear_inside_edges_seam",
                text=t(context, "clear_inside_edges_seam"),
                icon="X",
            )

            tools_column.operator(
                "mesh.polygroups_edge_seam_path",
                text=t(context, "connect_vertices_edge_seam_path"),
                **icon_kwargs("edge_seam_path_pin" if seam_settings.seam_path_pin else "edge_seam_path", "EDGE_SEAM"),
            )

            tools_column.separator()
            tools_column.label(text=t(context, "pin_edges"))
            pin_row = tools_column.row(align=True)
            pin_row.operator("mesh.polygroups_pin_selected_seams", text=t(context, "pin_selected_seams"), **icon_kwargs("pin_vertices", "PINNED"))
            pin_row.operator("mesh.polygroups_unpin_selected_edges", text=t(context, "unpin_selected"), **icon_kwargs("unpin_vertices", "UNPINNED"))
            tools_column.operator("mesh.polygroups_clear_all_pins", text=t(context, "clear_all_pins"), **icon_kwargs("unpin_vertices", "X"))
            tools_column.prop(seam_settings, "seam_path_pin", text=t(context, "mark_as_pinned"))

        content = draw_collapsible_box(layout, seam_settings, "show_smart_mark_seams_group", t(context, "seam_group_smart_mark"), "EDGE_SEAM")
        if content is not None:
            tools_column = content.column(align=True)
            tools_column.prop(seam_settings, "smart_seam_angle_limit", text=t(context, "smart_seam_angle_limit"))
            tools_column.prop(seam_settings, "smart_seam_filter_iterations")
            tools_column.prop(seam_settings, "smart_seam_min_area")
            tools_column.prop(seam_settings, "smart_seam_smoothness")
            tools_column.prop(seam_settings, "smart_seam_replace")
            tools_column.prop(seam_settings, "smart_seam_pin_generated", text=t(context, "pin_generated"))
            tools_column.prop(seam_settings, "smart_seam_create_edges")
            if seam_settings.smart_seam_create_edges:
                tools_column.prop(seam_settings, "smart_seam_edge_preference")
            tools_column.prop(
                seam_settings, "smart_seam_auto_relax",
                text=t(context, "smart_seam_auto_relax"), toggle=True,
            )
            if seam_settings.smart_seam_auto_relax:
                tools_column.prop(
                    seam_settings, "seam_relax_iterations",
                    text=t(context, "seam_relax_iterations"),
                )
                tools_column.label(
                    text=t(context, "seam_relax_selected_area_only"),
                    icon="CHECKBOX_HLT",
                )
                corner_row = tools_column.row(align=True)
                corner_row.prop(
                    seam_settings, "seam_relax_use_corner_angle",
                    text=t(context, "seam_relax_use_corner_angle"), toggle=True,
                )
                corner_angle = corner_row.row(align=True)
                corner_angle.enabled = seam_settings.seam_relax_use_corner_angle
                corner_angle.prop(seam_settings, "seam_relax_corner_angle", text="")
                tools_column.prop(
                    seam_settings, "seam_relax_protection_radius",
                    text=t(context, "seam_relax_protection_radius"),
                )
            tools_column.prop(seam_settings, "smart_seam_path_turn")
            tools_column.prop(seam_settings, "smart_seam_path_corridor")
            tools_column.operator(
                "mesh.polygroups_mark_smart_angle_seams",
                text=t(context, "mark_smart_angle_seams"),
                **icon_kwargs("smart_seams_generator_pin" if seam_settings.smart_seam_pin_generated else "smart_seams_generator", "UV"),
            )

        settings = context.scene.polygroups_generator_settings
        content = draw_collapsible_box(layout, settings, "show_small_islands", t(context, "small_islands_group"), "EDGE_SEAM")
        if content is not None:
            content.prop(settings, "small_island_threshold", text=t(context, "small_islands_threshold"))
            content.prop(settings, "small_island_selected_area", text=t(context, "small_islands_selected"))
            content.prop(settings, "small_island_protect_pinned", text=t(context, "small_islands_pinned"))
            content.prop(settings, "small_island_protect_sharp", text=t(context, "small_islands_sharp"))
            content.prop(settings, "small_island_protect_materials", text=t(context, "small_islands_materials"))
            row = content.row(align=True)
            row.operator("mesh.polygroups_merge_small_islands", text=t(context, "small_islands_preview"), icon="VIEWZOOM").preview = True
            row.operator(
                "mesh.polygroups_analyze_and_merge_seams",
                text=t(context, "small_islands_analyze_merge"),
                icon="AUTOMERGE_ON",
            )
            if settings.small_island_status:
                content.label(text=settings.small_island_status)

        content = draw_collapsible_box(layout, seam_settings, "show_mark_clear_tools_group", t(context, "seam_group_mark_clear_tools"), "TOOL_SETTINGS")
        if content is not None:
            tools_column = content.column(align=True)
            tools_column.prop(seam_settings, "seam_eraser_clear_mode", expand=True)
            edge_tool = tools_column.operator(
                "mesh.polygroups_select_seam_tool",
                text=t(context, "select_edge_seam_tool"),
                **icon_kwargs("edge_seam_path_pin" if seam_settings.seam_path_pin else "edge_seam_path", "VERTEXSEL"),
            )
            edge_tool.tool_id = "polygroups_generator.edge_seam_path_tool"
            for key, tool_id in (("seam_eraser", "polygroups_generator.seam_eraser_tool"),
                                 ("edge_seam_eraser", "polygroups_generator.edge_seam_eraser_tool")):
                icon_key = key + ("_pin" if seam_settings.seam_eraser_clear_mode == "PINNED" else "")
                button = tools_column.operator("mesh.polygroups_select_seam_tool", text=t(context, key), **icon_kwargs(icon_key, "X"))
                button.tool_id = tool_id

        content = draw_collapsible_box(layout, seam_settings, "show_check_group", t(context, "seam_group_check"), "VIEWZOOM")
        if content is not None:
            draw_seam_gap_controls(content, context, seam_settings)
            content.separator(type="LINE")
            relax_column = content.column(align=True)
            relax_column.label(text=t(context, "seam_relax"), icon="MOD_SMOOTH")
            relax_column.prop(
                seam_settings, "seam_relax_mode",
                text=t(context, "seam_relax_mode"), expand=True,
            )
            relax_column.prop(
                seam_settings, "seam_relax_iterations",
                text=t(context, "seam_relax_iterations"),
            )
            relax_column.prop(
                seam_settings, "seam_relax_selected_area_only",
                text=t(context, "seam_relax_selected_area_only"), toggle=True,
            )
            if seam_settings.seam_relax_mode == "SMART":
                corner_row = relax_column.row(align=True)
                corner_row.prop(
                    seam_settings, "seam_relax_use_corner_angle",
                    text=t(context, "seam_relax_use_corner_angle"), toggle=True,
                )
                corner_angle = corner_row.row(align=True)
                corner_angle.enabled = seam_settings.seam_relax_use_corner_angle
                corner_angle.prop(seam_settings, "seam_relax_corner_angle", text="")
                relax_column.prop(
                    seam_settings, "seam_relax_protection_radius",
                    text=t(context, "seam_relax_protection_radius"),
                )
            relax_column.operator(
                "mesh.polygroups_relax_seams",
                text=t(context, "seam_relax"), icon="MOD_SMOOTH",
            )

        content = draw_collapsible_box(layout, seam_settings, "show_cut_group", t(context, "seam_group_cut"), "MOD_BEVEL")
        if content is not None:
            connect_column = content.column(align=True)
            connect_column.prop(seam_settings, "seam_path_pin", text=t(context, "mark_as_pinned"))
            connect_column.operator(
                "mesh.polygroups_connect_vertex_seam",
                text=t(context, "connect_vertices_seam"),
                icon="EDGE_SEAM",
            )
            connect_tool = connect_column.operator(
                "mesh.polygroups_select_seam_tool",
                text=t(context, "select_vertex_seam_tool"),
                **icon_kwargs("connect_vertex_seam_pin" if seam_settings.seam_path_pin else "connect_vertex_seam", "VERTEXSEL"),
            )
            connect_tool.tool_id = "polygroups_generator.connect_vertex_seam_tool"
            knife_content = draw_collapsible_box(
                content,
                seam_settings,
                "show_knife_seam_settings",
                t(context, "knife_seam"),
                "MOD_BEVEL",
            )
            if knife_content is not None:
                self.draw_knife_seam(context, knife_content)

            quick_knife_content = draw_collapsible_box(
                content,
                seam_settings,
                "show_quick_knife_seam_settings",
                t(context, "quick_knife_seam"),
                "MOD_BEVEL",
            )
            if quick_knife_content is not None:
                self.draw_quick_knife_seam(context, quick_knife_content)

            object_cutter_content = draw_collapsible_box(
                content,
                seam_settings,
                "show_object_seam_cutter_settings",
                t(context, "object_seam_cutter"),
                "MESH_PLANE",
            )
            if object_cutter_content is not None:
                self.draw_object_seam_cutter(context, object_cutter_content)

    def draw_knife_seam(self, context, layout):
        settings = context.scene.polygroups_knife_seam_settings

        layout.prop(settings, "cut_mode", text=t(context, "knife_cut_mode"))
        if settings.cut_mode == "POLYLINE":
            layout.label(text=t(context, "knife_polyline_hint"), icon="INFO")
        layout.prop(settings, "xray", text=t(context, "xray"))
        layout.prop(settings, "use_occlude_geometry", text=t(context, "occlude_geometry"))
        layout.prop(settings, "only_selected", text=t(context, "only_selected"))
        layout.prop(settings, "mark_seam", text=t(context, "mark_as_seam"))
        layout.prop(
            settings,
            "clear_selection_after_cutting",
            text=t(context, "clear_selection_after_cutting"),
        )

        tool_operator = layout.operator(
            "mesh.polygroups_select_seam_tool",
            text=t(context, "select_knife_tool"),
            **icon_kwargs("knife_seam", "SCULPTMODE_HLT"),
        )
        tool_operator.tool_id = "polygroups_generator.knife_seam_tool"

    def draw_quick_knife_seam(self, context, layout):
        quick_settings = context.scene.polygroups_quick_knife_seam_settings

        layout.prop(quick_settings, "use_fill", text=t(context, "fill"))
        layout.prop(quick_settings, "threshold", text=t(context, "threshold"))
        layout.prop(quick_settings, "mark_seam", text=t(context, "mark_as_seam"))
        layout.prop(
            quick_settings,
            "clear_selection_after_cutting",
            text=t(context, "clear_selection_after_cutting"),
        )

        tool_operator = layout.operator(
            "mesh.polygroups_select_seam_tool",
            text=t(context, "select_quick_knife_tool"),
            **icon_kwargs("quick_knife_seam", "MOD_BEVEL"),
        )
        tool_operator.tool_id = "polygroups_generator.quick_knife_seam_tool"

    def draw_object_seam_cutter(self, context, layout):
        settings = context.scene.polygroups_object_seam_cutter_settings

        layout.prop(settings, "cutter_size_multiplier", text=t(context, "cutter_size"))
        layout.prop(settings, "cutter_arc_segments", text=t(context, "cylinder_segments"))
        layout.prop(settings, "cutter_local_ring_fit_mode", text=t(context, "local_ring_fit_mode"))
        layout.prop(settings, "cutter_local_ring_segments", text=t(context, "local_ring_segments"))
        layout.prop(settings, "cutter_local_ring_radius_offset", text=t(context, "local_ring_radius_offset"))
        layout.prop(settings, "cutter_contour_points", text=t(context, "contour_points"))
        layout.prop(settings, "cutter_contour_offset", text=t(context, "contour_offset"))
        layout.label(text=t(context, "cutter_apply_method"))
        draw_enum_icon_toggle(
            layout,
            "scene.polygroups_object_seam_cutter_settings",
            settings,
            "cutter_apply_method",
            (
                ("BOOLEAN", "Boolean", "MOD_BOOLEAN"),
                ("KNIFE", "Knife", "EDGESEL"),
            ),
        )
        layout.label(text=t(context, "cutter_boolean_solver"))
        draw_enum_icon_toggle(
            layout,
            "scene.polygroups_object_seam_cutter_settings",
            settings,
            "cutter_boolean_solver",
            (
                ("FLOAT", "Float", "VIEWZOOM"),
                ("EXACT", "Exact", "CHECKMARK"),
            ),
        )
        autofix_row = layout.row(align=True)
        autofix_row.prop(
            settings,
            "cutter_auto_fix_mesh",
            text=t(context, "cutter_auto_fix_mesh"),
            toggle=True,
        )
        fin_toggle = autofix_row.row(align=True)
        fin_toggle.enabled = settings.cutter_auto_fix_mesh
        fin_toggle.prop(
            settings,
            "cutter_auto_fix_fin_faces",
            text="",
            icon="FACESEL",
            toggle=True,
        )
        seam_toggle = autofix_row.row(align=True)
        seam_toggle.enabled = settings.cutter_auto_fix_mesh
        seam_toggle.prop(
            settings,
            "cutter_auto_fix_seam_check",
            text="",
            icon="VIEWZOOM",
            toggle=True,
        )
        islands_toggle = autofix_row.row(align=True)
        islands_toggle.enabled = settings.cutter_auto_fix_mesh
        islands_toggle.prop(
            settings,
            "cutter_auto_fix_small_islands",
            text="",
            icon="AUTOMERGE_ON",
            toggle=True,
        )
        islands_threshold = autofix_row.row(align=True)
        islands_threshold.enabled = (
            settings.cutter_auto_fix_mesh and settings.cutter_auto_fix_small_islands
        )
        islands_threshold.prop(
            settings,
            "cutter_auto_fix_small_islands_threshold",
            text="Threshold",
        )
        weld_toggle = autofix_row.row(align=True)
        weld_toggle.enabled = settings.cutter_auto_fix_mesh
        weld_toggle.prop(
            settings,
            "cutter_auto_fix_weld",
            text="",
            icon="AUTOMERGE_ON",
            toggle=True,
        )
        weld_distance = autofix_row.row(align=True)
        weld_distance.enabled = settings.cutter_auto_fix_mesh and settings.cutter_auto_fix_weld
        weld_distance.prop(
            settings,
            "cutter_auto_fix_weld_distance",
            text="Weld",
        )
        relax_toggle = autofix_row.row(align=True)
        relax_toggle.enabled = settings.cutter_auto_fix_mesh
        relax_toggle.prop(
            settings,
            "cutter_auto_fix_smart_relax_seams",
            text="",
            icon="MOD_SMOOTH",
            toggle=True,
        )
        triangulate_toggle = autofix_row.row(align=True)
        triangulate_toggle.enabled = settings.cutter_auto_fix_mesh
        triangulate_toggle.prop(
            settings,
            "cutter_auto_fix_triangulate_ngons",
            text="",
            icon="MOD_TRIANGULATE",
            toggle=True,
        )
        status_box = layout.box()
        status_box.label(text="Apply Cutter Seams Status", icon="MOD_BOOLEAN")
        if settings.cutter_apply_stage:
            status_box.label(text=settings.cutter_apply_message)
            status_box.progress(
                factor=settings.cutter_apply_progress / 100,
                type="BAR",
                text=f"{settings.cutter_apply_progress:.0f}%",
            )
            if settings.cutter_apply_is_running:
                status_box.label(text="Press Esc to cancel", icon="INFO")
        else:
            status_box.label(text="Ready")
        layout.prop(settings, "cutter_alpha", text=t(context, "cutter_alpha"))
        layout.prop(settings, "cutter_solidify_thickness", text=t(context, "plane_thickness"))
        layout.prop(settings, "cutter_thickness", text=t(context, "cutter_thickness"))
        layout.prop(settings, "cutter_extrude", text=t(context, "cutter_extrude"))
        layout.prop(settings, "cutter_path_render_u", text=t(context, "path_render_u"))
        tilt_row = layout.row(align=True)
        tilt_operator = tilt_row.operator("object.polygroups_tilt_cutter_path", text=t(context, "tilt_minus"))
        tilt_operator.mode = "DECREASE"
        tilt_operator = tilt_row.operator("object.polygroups_tilt_cutter_path", text=t(context, "tilt_plus"))
        tilt_operator.mode = "INCREASE"
        curve_row = layout.row(align=True)
        curve_row.operator("object.polygroups_bezier_cutter_paths", text=t(context, "curve_bezier"))
        curve_row.operator("object.polygroups_toggle_cyclic_cutter_paths", text=t(context, "curve_cyclic"))
        curve_row.operator("object.polygroups_smooth_cutter_paths", text=t(context, "curve_smooth"))
        curve_row.operator("object.polygroups_smooth_cutter_path_tilt", text=t(context, "curve_smooth_tilt"))
        layout.prop(settings, "continue_path_cutters", text=t(context, "continue_path_cutters"))
        layout.prop(settings, "cutter_path_join_distance", text=t(context, "path_join_distance"))
        layout.prop(settings, "cutter_draw_min_point_distance", text=t(context, "draw_point_distance"))
        layout.prop(settings, "cutter_draw_simplify_distance", text=t(context, "draw_simplify_distance"))
        stabilize_row = layout.row(align=True)
        stabilize_row.prop(settings, "cutter_draw_stabilize_stroke",
                           text=t(context, "draw_stabilize_stroke"), toggle=True)
        stabilize_settings = stabilize_row.row(align=True)
        stabilize_settings.enabled = settings.cutter_draw_stabilize_stroke
        stabilize_settings.prop(settings, "cutter_draw_stabilize_radius",
                                text=t(context, "draw_stabilize_radius"))
        stabilize_settings.prop(settings, "cutter_draw_stabilize_factor",
                                text=t(context, "draw_stabilize_factor"))
        layout.prop(settings, "continue_draw_strokes", text=t(context, "continue_draw_strokes"))
        layout.prop(settings, "cutter_draw_join_distance", text=t(context, "draw_join_distance"))
        layout.prop(settings, "auto_convert_draw_strokes", text=t(context, "auto_convert_draw_strokes"))
        layout.prop(
            settings,
            "auto_convert_draw_strokes_on_apply",
            text=t(context, "auto_convert_draw_strokes_on_apply"),
        )
        layout.prop(
            settings,
            "delete_draw_strokes_after_convert",
            text=t(context, "delete_draw_strokes_after_convert"),
        )
        layout.prop(
            settings,
            "hide_cutters_after_apply",
            text=t(context, "hide_cutters_after_apply"),
        )
        layout.prop(
            settings,
            "delete_cutters_after_apply",
            text=t(context, "delete_cutters_after_apply"),
        )
        layout.label(text=t(context, "ctrl_draw_hint"), icon="MOUSE_LMB")
        layout.prop(settings, "cutter_mirror_axis", text=t(context, "mirror_axis"), expand=True)
        layout.operator(
            "object.polygroups_copy_mirror_cutters",
            text=t(context, "copy_mirror_cutters"),
            icon="MOD_MIRROR",
        )
        layout.separator()
        tool_operator = layout.operator(
            "wm.tool_set_by_id",
            text=t(context, "select_draw_cutter_plane"),
            **icon_kwargs("draw_cutter_plane", "MESH_PLANE"),
        )
        tool_operator.name = "polygroups_generator.draw_cutter_plane_tool"
        layout.operator(
            "object.polygroups_draw_cutter_plane",
            text=t(context, "draw_cutter_plane"),
            **icon_kwargs("draw_cutter_plane", "MESH_PLANE"),
        )
        grid_box = layout.box()
        grid_box.label(text=t(context, "draw_cutter_grid"), **icon_kwargs("draw_cutter_grid", "MESH_CUBE"))
        from .tools import draw_grid_settings
        draw_grid_settings(context, grid_box)
        grid_box.operator("wm.tool_set_by_id", text=t(context, "select_draw_cutter_grid"),
                          **icon_kwargs("draw_cutter_grid", "MESH_CUBE")).name = "polygroups_generator.draw_cutter_grid_tool"
        grid_box.operator("object.polygroups_draw_cutter_grid", text=t(context, "draw_cutter_grid"), **icon_kwargs("draw_cutter_grid", "MESH_CUBE"))
        tool_operator = layout.operator(
            "wm.tool_set_by_id",
            text=t(context, "select_draw_cutter_arc"),
            **icon_kwargs("draw_cutter_arc", "CURVE_BEZCURVE"),
        )
        tool_operator.name = "polygroups_generator.draw_cutter_arc_tool"
        layout.operator(
            "object.polygroups_draw_cutter_arc",
            text=t(context, "draw_cutter_arc"),
            **icon_kwargs("draw_cutter_arc", "CURVE_BEZCURVE"),
        )
        tool_operator = layout.operator(
            "wm.tool_set_by_id",
            text=t(context, "select_draw_cutter_local_ring"),
            **icon_kwargs("draw_cutter_local_ring", "MESH_CIRCLE"),
        )
        tool_operator.name = "polygroups_generator.draw_cutter_local_ring_tool"
        layout.operator(
            "object.polygroups_draw_cutter_local_ring",
            text=t(context, "draw_cutter_local_ring"),
            **icon_kwargs("draw_cutter_local_ring", "MESH_CIRCLE"),
        )
        tool_operator = layout.operator(
            "wm.tool_set_by_id",
            text=t(context, "select_draw_cutter_local_contour"),
            **icon_kwargs("draw_cutter_local_contour", "MESH_CIRCLE"),
        )
        tool_operator.name = "polygroups_generator.draw_cutter_local_contour_tool"
        layout.operator(
            "object.polygroups_draw_cutter_local_contour",
            text=t(context, "draw_cutter_local_contour"),
            **icon_kwargs("draw_cutter_local_contour", "MESH_CIRCLE"),
        )
        tool_operator = layout.operator(
            "wm.tool_set_by_id",
            text=t(context, "select_draw_cutter_path"),
            **icon_kwargs("draw_cutter_path", "CURVE_PATH"),
        )
        tool_operator.name = "polygroups_generator.draw_cutter_path_tool"
        layout.operator(
            "object.polygroups_draw_cutter_path",
            text=t(context, "draw_cutter_path"),
            **icon_kwargs("draw_cutter_path", "CURVE_PATH"),
        )
        layout.operator(
            "object.polygroups_join_cutter_paths",
            text=t(context, "join_cutter_paths"),
            icon="AUTOMERGE_ON",
        )
        tool_operator = layout.operator(
            "wm.tool_set_by_id",
            text=t(context, "select_draw_cutter_draw"),
            **icon_kwargs("draw_cutter_draw", "GREASEPENCIL"),
        )
        tool_operator.name = "polygroups_generator.draw_cutter_draw_tool"
        layout.operator(
            "object.polygroups_draw_cutter_draw",
            text=t(context, "draw_cutter_draw"),
            **icon_kwargs("draw_cutter_draw", "GREASEPENCIL"),
        )
        layout.operator(
            "object.polygroups_join_draw_strokes",
            text=t(context, "join_draw_strokes"),
            icon="AUTOMERGE_ON",
        )
        layout.operator(
            "object.polygroups_convert_draw_strokes_to_cutter_paths",
            text=t(context, "convert_draw_strokes_to_cutter_paths"),
            icon="CURVE_PATH",
        )
        tilt_row = layout.row(align=True)
        tilt_operator = tilt_row.operator(
            "object.polygroups_tilt_cutter_path",
            text=t(context, "tilt_minus"),
        )
        tilt_operator.mode = "DECREASE"
        tilt_operator = tilt_row.operator(
            "object.polygroups_tilt_cutter_path",
            text=t(context, "tilt_plus"),
        )
        tilt_operator.mode = "INCREASE"
        curve_row = layout.row(align=True)
        curve_row.operator("object.polygroups_bezier_cutter_paths", text=t(context, "curve_bezier"))
        curve_row.operator("object.polygroups_toggle_cyclic_cutter_paths", text=t(context, "curve_cyclic"))
        curve_row.operator("object.polygroups_smooth_cutter_paths", text=t(context, "curve_smooth"))
        curve_row.operator("object.polygroups_smooth_cutter_path_tilt", text=t(context, "curve_smooth_tilt"))
        apply_row = layout.row(align=True)
        apply_row.enabled = any(
            obj.type in {"MESH", "CURVE"}
            and obj.get("polygroups_object_seam_cutter")
            for obj in context.selected_objects
        ) and not settings.cutter_apply_is_running
        apply_row.operator(
            "object.polygroups_apply_cutter_seams",
            text=t(context, "apply_cutter_seams"),
            icon="MOD_BOOLEAN",
        )
        apply_row.operator(
            "object.polygroups_create_cutter_backup",
            text="",
            icon="DUPLICATE",
        )
        apply_row.operator(
            "object.polygroups_restore_cutter_backup",
            text="",
            icon="RECOVER_LAST",
        )
        layout.operator(
            "object.polygroups_restore_cutter_backup",
            text="Restore Backup",
            icon="RECOVER_LAST",
        )
        layout.operator(
            "object.polygroups_split_object_by_cutters",
            text=t(context, "split_object"),
            icon="MOD_EXPLODE",
        )

        utility_row = layout.row(align=True)
        utility_row.operator(
            "object.polygroups_select_cutter_planes",
            text=t(context, "select"),
            icon="RESTRICT_SELECT_OFF",
        )
        utility_row.operator(
            "object.polygroups_clear_cutter_planes",
            text=t(context, "clear"),
            icon="TRASH",
        )

        if settings.last_cutter_count or settings.last_marked_edge_count:
            layout.separator()
            layout.label(text=t(context, "last_cutters", value=settings.last_cutter_count))
            layout.label(text=t(context, "last_seam_edges", value=settings.last_marked_edge_count))


class VIEW3D_PT_polygroups_tools(bpy.types.Panel):
    bl_label = "05 |"
    bl_text_key = "section_polygroups"
    bl_icon = "MATERIAL"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_order = 5
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout.box()
        settings = context.scene.polygroups_generator_settings
        content = draw_collapsible_box(layout, settings, "show_group_generation", t(context, "generate_polygroups"), "MATERIAL")
        if content is not None:
            column = content.column(align=True)
            draw_material_mode_buttons(column, context, settings)
            column.prop(settings, "checker_scale", text=t(context, "checker_scale"))
            column.separator()
            column.operator(
                "object.polygroups_checked_generate_polygroups",
                text=t(context, "generate_polygroups"),
                icon="MATERIAL",
            )
            column.operator(
                "object.polygroups_apply_material_mode",
                text=t(context, "apply_material_mode"),
                icon="NODE_MATERIAL",
            )
            column.operator(
                "object.polygroups_apply_checker_material",
                text=t(context, "apply_checker_material"),
                icon="TEXTURE",
            )

        content = draw_collapsible_box(layout, settings, "show_group_uv", t(context, "small_islands_uv"), "UV")
        if content is not None:
            column = content.column(align=True)
            column.operator(
                "mesh.polygroups_mark_material_boundaries_seam",
                text=t(context, "generate_seams_materials"),
                icon="EDGE_SEAM",
            )
            column.operator(
                "object.polygroups_unwrap_angle_based",
                text=t(context, "unwrap_angle_based"),
                icon="UV",
            )

        content = draw_collapsible_box(layout, settings, "show_group_materials", t(context, "small_islands_manage"), "MATERIAL")
        if content is not None:
            column = content.column(align=True)
            column.operator(
                "object.face_sets_to_materials",
                text=t(context, "face_sets_to_materials"),
                icon="SHADING_TEXTURE",
            )
            column.operator(
                "object.clear_polygroups_materials",
                text=t(context, "clear_polygroups_materials"),
                icon="TRASH",
            )


class VIEW3D_PT_polygroups_baking(bpy.types.Panel):
    bl_label = "10 |"
    bl_text_key = "section_baking"
    bl_icon = "RENDER_STILL"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 10
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout.box()
        settings = context.scene.polygroups_baking_settings

        content = draw_topic(layout, context, "bake_0", 'Save Project', "FILE_BLEND")
        if content is not None:
            column = content.column(align=True)
            column.label(text=t(context, "baking_save_blend_reminder"), icon="INFO")
            save_row = column.row(align=True)
            save_row.operator(
                "object.polygroups_save_blend_file",
                text=t(context, "save_blend_file"),
                icon="FILE_BLEND",
            )
            save_row.operator(
                "object.polygroups_save_blend_file_as",
                text=t(context, "save_blend_file_as"),
                icon="FILE_FOLDER",
            )
            column.separator()

        content = draw_topic(layout, context, "bake_1", 'Cage Settings', "MOD_SHRINKWRAP")
        if content is not None:
            column = content.column(align=True)
            column.prop(settings, "cage_extrusion", text=t(context, "cage_extrusion"))
            auto_cage_box = column.box()
            auto_cage_box.prop(settings, "use_auto_cage", text=t(context, "auto_cage"))
            auto_cage_column = auto_cage_box.column(align=True)
            auto_cage_column.prop(settings, "auto_cage_coverage", text=t(context, "auto_cage_coverage"), slider=True)
            auto_cage_column.prop(settings, "auto_cage_margin", text=t(context, "auto_cage_margin"))
            auto_cage_column.prop(settings, "auto_cage_margin_percent", text=t(context, "auto_cage_margin_percent"), slider=True)
            auto_cage_column.prop(settings, "auto_cage_safe_zone", text=t(context, "auto_cage_safe_zone"), slider=True)
            auto_cage_column.prop(settings, "auto_cage_max", text=t(context, "auto_cage_max"))
            auto_cage_column.prop(settings, "auto_cage_sample_limit", text=t(context, "auto_cage_samples"))
            auto_cage_column.operator(
                "object.polygroups_calculate_auto_cage",
                text=t(context, "calculate_auto_cage"),
                icon="MOD_SHRINKWRAP",
            )
            auto_cage_box.label(text=t(context, "auto_cage_status", value=settings.auto_cage_status), icon="INFO")
            column.prop(settings, "ray_distance", text=t(context, "ray_distance"))

        content = draw_topic(layout, context, "bake_2", 'Bake Settings', "RENDER_STILL")
        if content is not None:
            column = content.column(align=True)
            column.prop(settings, "bake_resolution", text=t(context, "bake_resolution"))
            column.prop(settings, "bake_margin", text=t(context, "bake_margin"))
            column.prop(settings, "bake_background_mode", text=t(context, "bake_background"))
            column.label(text=t(context, "bake_alpha_hint"), icon="IMAGE_ALPHA")
            column.prop(settings, "image_prefix", text=t(context, "image_prefix"))
            column.prop(settings, "use_selected_to_active", text=t(context, "selected_to_active"))

            pass_row = column.row(align=True)
            pass_row.prop(settings, "bake_base_color", text=t(context, "base_color"))
            pass_row.prop(settings, "bake_normal", text=t(context, "normal"))
            column.prop(
                settings,
                "auto_save_textures_after_bake",
                text=t(context, "auto_save_textures_after_bake"),
            )
            column.prop(
                settings,
                "disable_highpoly_after_bake",
                text=t(context, "disable_highpoly_after_bake"),
            )
            column.prop(
                settings,
                "auto_fix_generated_index",
                text=t(context, "auto_fix_generated_index"),
            )
            pack_box = column.box()
            pack_header = pack_box.row(align=True)
            pack_header.prop(
                settings,
                "show_auto_pack_uv_settings",
                text="",
                icon=(
                    "TRIA_DOWN"
                    if settings.show_auto_pack_uv_settings
                    else "TRIA_RIGHT"
                ),
                emboss=False,
            )
            pack_header.prop(
                settings,
                "auto_pack_uv_before_bake",
                text=t(context, "auto_pack_uv_before_bake"),
            )
            if settings.show_auto_pack_uv_settings:
                pack_settings = pack_box.column(align=True)
                installed, enabled, available = uvpackmaster_status(context)
                if not installed:
                    pack_settings.label(text=t(context, "uvpackmaster_not_installed"), icon="ERROR")
                elif not enabled or not available:
                    pack_settings.label(text=t(context, "uvpackmaster_not_enabled"), icon="ERROR")
                else:
                    main_props = context.scene.uvpm4_props.default_main_props
                    draw_optional_prop(
                        pack_settings, main_props, "rotation_enable",
                        text=t(context, "uvpackmaster_rotation_enable"),
                    )
                    draw_optional_prop(
                        pack_settings, main_props, "margin",
                        text=t(context, "uvpackmaster_margin"),
                    )
                    rotation_row = pack_settings.row(align=True)
                    rotation_row.enabled = bool(getattr(main_props, "rotation_enable", True))
                    draw_optional_prop(
                        rotation_row, main_props, "rotation_step",
                        text=t(context, "uvpackmaster_rotation_step"),
                    )
                    draw_optional_prop(
                        pack_settings, main_props, "heuristic_enable",
                        text=t(context, "uvpackmaster_heuristic_search"),
                    )
                    draw_optional_prop(
                        pack_settings, main_props, "heuristic_max_wait_time",
                        text=t(context, "uvpackmaster_max_wait_time"),
                    )
            column.separator()
            auto_bake_row = column.row(align=True)
            auto_bake_row.scale_y = 1.3
            auto_bake_row.enabled = not settings.bake_task_is_running
            auto_bake_row.operator(
                "object.polygroups_checked_prepare_and_bake",
                text=t(context, "prepare_and_bake"),
                icon="RENDER_RESULT",
            )

        content = draw_topic(layout, context, "bake_3", 'Bake Operations', "RENDER_STILL")
        if content is not None:
            column = content.column(align=True)
            if settings.bake_task_stage:
                status_box = column.box()
                status_box.label(text=t(context, "bake_task_status"), icon="TIME")
                status_box.label(text=settings.bake_task_message)
                if settings.bake_task_stage != "CANCELLED":
                    status_box.progress(
                        factor=settings.bake_task_progress / 100.0,
                        type="BAR",
                        text=f"{settings.bake_task_progress:.0f}%",
                    )
            material_box = column.box()
            material_box.enabled = not settings.bake_task_is_running
            material_box.label(text=t(context, "material_setup"), icon="MATERIAL")
            material_box.operator(
                "object.polygroups_check_material_textures",
                text=t(context, "check_material_textures"),
                icon="NODE_MATERIAL",
            )
            material_box.operator(
                "object.polygroups_prepare_highpoly_bake_materials",
                text=t(context, "prepare_highpoly_texture_only"),
                icon="MATERIAL",
            )
            material_box.operator(
                "object.polygroups_checked_prepare_lowpoly_bake_material",
                text=t(context, "prepare_lowpoly_bake_material"),
                icon="TEXTURE",
            )

            bake_box = column.box()
            bake_box.enabled = not settings.bake_task_is_running
            bake_box.label(text=t(context, "bake_action"), icon="RENDER_STILL")
            bake_box.operator(
                "object.polygroups_checked_bake_selected_to_active",
                text=t(context, "bake_selected_to_active"),
                icon="RENDER_STILL",
            )
            bake_box.operator(
                "object.polygroups_checked_prepare_and_bake",
                text=t(context, "prepare_and_bake"),
                icon="RENDER_RESULT",
            )

            save_box = column.box()
            save_box.enabled = not settings.bake_task_is_running
            save_box.label(text=t(context, "save_textures_group"), icon="FILE_FOLDER")
            save_box.operator(
                "object.polygroups_save_bake_textures",
                text=t(context, "save_textures"),
                icon="FILE_FOLDER",
            )
            save_box.operator(
                "object.polygroups_merge_bake_textures",
                text=t(context, "merge_materials_textures"),
                icon="NODE_COMPOSITING",
            )

        content = draw_topic(layout, context, "bake_4", 'Cleanup', "TRASH")
        if content is not None:
            column = content.column(align=True)
            column.separator()
            column.operator(
                "object.polygroups_clear_bake_temp_images",
                text=t(context, "clear_all_bake_images"),
                icon="TRASH",
            )


class VIEW3D_PT_polygroups_uv_preparation(bpy.types.Panel):
    bl_label = "09 |"
    bl_text_key = "section_uv_preparation"
    bl_icon = "UV"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 9
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout.box()

        content = draw_topic(layout, context, "uv_0", 'UV Unwrap', "UV")
        if content is not None:
            smart_column = content.column(align=True)
            smart_column.operator(
                "object.polygroups_smart_uv_unwrap",
                text=t(context, "smart_uv_unwrap"),
                icon="UV",
            )
            smart_column.prop(
                context.scene.polygroups_seam_finalization_settings,
                "smart_uv_unwrap_auto_pack",
                text=t(context, "auto_pack"),
            )
            content.separator()
            content.operator(
                "object.polygroups_unwrap_angle_based",
                text=t(context, "unwrap_angle_based"),
                icon="UV",
            )
            content.separator()

        content = draw_topic(layout, context, "uv_1", 'UVPackmaster Packing', "UV_SYNC_SELECT")
        if content is not None:
            installed, enabled, available = uvpackmaster_status(context)

            if not installed:
                content.label(text=t(context, "uvpackmaster_not_installed"), icon="ERROR")
                content.label(text=t(context, "uvpackmaster_install_hint"))
                return

            if not enabled or not available:
                content.label(text=t(context, "uvpackmaster_not_enabled"), icon="ERROR")
                content.label(text=t(context, "uvpackmaster_enable_hint"))
                return

            main_props = context.scene.uvpm4_props.default_main_props
            content.label(text=t(context, "uvpackmaster_available"), icon="CHECKMARK")

            pack_row = content.row(align=True)
            pack_row.scale_y = 1.3
            pack_row.operator(
                "object.polygroups_uvpackmaster_pack",
                text=t(context, "uvpackmaster_pack"),
                icon="UV",
            )

            content.separator()
            draw_optional_prop(
                content,
                main_props,
                "rotation_enable",
                text=t(context, "uvpackmaster_rotation_enable"),
            )
            draw_optional_prop(
                content,
                main_props,
                "margin",
                text=t(context, "uvpackmaster_margin"),
            )

            rotation_row = content.row(align=True)
            rotation_row.enabled = bool(getattr(main_props, "rotation_enable", True))
            draw_optional_prop(
                rotation_row,
                main_props,
                "rotation_step",
                text=t(context, "uvpackmaster_rotation_step"),
            )

            draw_optional_prop(
                content,
                main_props,
                "heuristic_enable",
                text=t(context, "uvpackmaster_heuristic_search"),
            )
            draw_optional_prop(
                content,
                main_props,
                "heuristic_max_wait_time",
                text=t(context, "uvpackmaster_max_wait_time"),
            )


class VIEW3D_PT_airetopo_ai_generation(bpy.types.Panel):
    bl_label = "11 |"
    bl_text_key = "section_ai_generation"
    bl_icon = "IMAGE_DATA"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 11
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout
        openai_settings = context.scene.airetopo_ai_generation_settings

        prompt_library_content = draw_collapsible_box(
            layout,
            openai_settings,
            "show_prompt_library_settings",
            t(context, "prompt_library"),
            "TEXT",
        )
        if prompt_library_content is not None:
            self.draw_prompt_library(context, prompt_library_content)

        openai_content = draw_collapsible_box(
            layout,
            openai_settings,
            "show_openai_image_settings",
            t(context, "openai_image"),
            "IMAGE_DATA",
        )
        if openai_content is not None:
            self.draw_openai_image(context, openai_content)

        google_content = draw_collapsible_box(
            layout,
            openai_settings,
            "show_google_image_settings",
            t(context, "google_image"),
            "IMAGE_DATA",
        )
        if google_content is not None:
            self.draw_google_image(context, google_content)

    def draw_prompt_library(self, context, layout):
        settings = context.scene.airetopo_ai_generation_settings
        column = layout.column(align=True)
        column.prop(settings, "prompt_library_collection", text=t(context, "prompt_collection"))
        column.prop(settings, "prompt_library_prompt", text=t(context, "prompt_file"))

        load_row = column.row(align=True)
        openai_operator = load_row.operator(
            "object.airetopo_load_library_prompt",
            text=t(context, "load_to_openai"),
            icon="IMPORT",
        )
        openai_operator.provider = "OPENAI"
        openai_operator.mode = "REPLACE"

        google_operator = load_row.operator(
            "object.airetopo_load_library_prompt",
            text=t(context, "load_to_google"),
            icon="IMPORT",
        )
        google_operator.provider = "GOOGLE"
        google_operator.mode = "REPLACE"

        both_operator = load_row.operator(
            "object.airetopo_load_library_prompt",
            text=t(context, "load_to_both"),
            icon="IMPORT",
        )
        both_operator.provider = "BOTH"
        both_operator.mode = "REPLACE"

        append_row = column.row(align=True)
        append_openai_operator = append_row.operator(
            "object.airetopo_load_library_prompt",
            text=t(context, "append_to_openai"),
            icon="ADD",
        )
        append_openai_operator.provider = "OPENAI"
        append_openai_operator.mode = "APPEND"

        append_google_operator = append_row.operator(
            "object.airetopo_load_library_prompt",
            text=t(context, "append_to_google"),
            icon="ADD",
        )
        append_google_operator.provider = "GOOGLE"
        append_google_operator.mode = "APPEND"

        utility_row = column.row(align=True)
        utility_row.operator(
            "object.airetopo_refresh_prompt_library",
            text=t(context, "refresh_prompt_library"),
            icon="FILE_REFRESH",
        )
        utility_row.operator(
            "object.airetopo_open_prompt_library_folder",
            text=t(context, "open_prompt_folder"),
            icon="FILE_FOLDER",
        )

        if settings.prompt_library_status:
            column.label(text=settings.prompt_library_status, icon="INFO")

    def draw_openai_image(self, context, layout):
        settings = context.scene.airetopo_ai_generation_settings
        preferences = get_preferences(context)
        has_env_key = bool(os.environ.get("OPENAI_API_KEY", ""))
        has_saved_key = bool(preferences and preferences.openai_api_key)
        uses_env_key = bool(preferences and preferences.use_env_openai_api_key)
        has_api_key = (has_env_key or has_saved_key) if uses_env_key else has_saved_key
        if not has_api_key:
            layout.label(text=t(context, "ai_key_missing"), icon="ERROR")

        column = layout.column(align=True)
        draw_ai_input_image_controls(column, context, settings, "OPENAI")
        column.separator()
        column.prop(settings, "prompt", text=t(context, "ai_prompt"))
        column.prop(settings, "model", text=t(context, "ai_model"))
        column.prop(settings, "size", text=t(context, "ai_size"))
        column.prop(settings, "quality", text=t(context, "ai_quality"))
        column.prop(settings, "output_format", text=t(context, "ai_output_format"))

        column.separator()
        generate_row = column.row(align=True)
        generate_row.enabled = not settings.is_generating
        generate_row.operator(
            "object.airetopo_generate_openai_image",
            text=t(context, "generate_openai_image"),
            icon="IMAGE_DATA",
        )

        result_row = column.row(align=True)
        result_row.enabled = bool(settings.last_image_name or settings.last_image_path)
        open_operator = result_row.operator(
            "object.airetopo_open_generated_image",
            text=t(context, "open_image_editor"),
            icon="IMAGE",
        )
        open_operator.provider = "OPENAI"
        save_operator = result_row.operator(
            "object.airetopo_save_generated_image",
            text=t(context, "save_image"),
            icon="FILE_FOLDER",
        )
        save_operator.provider = "OPENAI"

        column.separator()
        status = t(context, "ai_generating") if settings.is_generating else settings.last_status
        column.label(text=t(context, "ai_status", value=status or t(context, "ai_no_status")))
        if settings.last_image_name:
            column.label(text=t(context, "ai_last_image", value=settings.last_image_name), icon="IMAGE")

    def draw_google_image(self, context, layout):
        settings = context.scene.airetopo_google_image_settings
        preferences = get_preferences(context)
        has_env_key = bool(os.environ.get("GEMINI_API_KEY", ""))
        has_saved_key = bool(preferences and preferences.gemini_api_key)
        uses_env_key = bool(preferences and preferences.use_env_gemini_api_key)
        has_api_key = (has_env_key or has_saved_key) if uses_env_key else has_saved_key
        if not has_api_key:
            layout.label(text=t(context, "google_key_missing"), icon="ERROR")

        column = layout.column(align=True)
        draw_ai_input_image_controls(column, context, settings, "GOOGLE")
        column.separator()
        column.prop(settings, "prompt", text=t(context, "ai_prompt"))
        column.prop(settings, "model", text=t(context, "ai_model"))
        column.prop(settings, "aspect_ratio", text=t(context, "ai_aspect_ratio"))
        column.prop(settings, "image_size", text=t(context, "ai_image_size"))
        column.prop(settings, "output_format", text=t(context, "ai_output_format"))

        column.separator()
        generate_row = column.row(align=True)
        generate_row.enabled = not settings.is_generating
        generate_row.operator(
            "object.airetopo_generate_google_image",
            text=t(context, "generate_google_image"),
            icon="IMAGE_DATA",
        )

        result_row = column.row(align=True)
        result_row.enabled = bool(settings.last_image_name or settings.last_image_path)
        open_operator = result_row.operator(
            "object.airetopo_open_generated_image",
            text=t(context, "open_image_editor"),
            icon="IMAGE",
        )
        open_operator.provider = "GOOGLE"
        save_operator = result_row.operator(
            "object.airetopo_save_generated_image",
            text=t(context, "save_image"),
            icon="FILE_FOLDER",
        )
        save_operator.provider = "GOOGLE"

        column.separator()
        status = t(context, "ai_generating") if settings.is_generating else settings.last_status
        column.label(text=t(context, "ai_status", value=status or t(context, "ai_no_status")))
        if settings.last_image_name:
            column.label(text=t(context, "ai_last_image", value=settings.last_image_name), icon="IMAGE")


class VIEW3D_PT_polygroups_resculpting(bpy.types.Panel):
    bl_label = "07 |"
    bl_text_key = "section_resculpting"
    bl_icon = "MOD_MULTIRES"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 7
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout.box()
        settings = context.scene.polygroups_resculpting_settings

        content = draw_topic(layout, context, "sculpt_0", 'Multires and Shrinkwrap Settings', "MOD_MULTIRES")
        if content is not None:
            column = content.column(align=True)
            column.prop(settings, "multires_levels", text=t(context, "multires_levels"))
            column.prop(settings, "shrinkwrap_limit", text=t(context, "shrinkwrap_limit"))
            column.prop(settings, "shrinkwrap_offset", text=t(context, "shrinkwrap_offset"))

        content = draw_topic(layout, context, "sculpt_1", 'Prepare Sculpting', "SCULPTMODE_HLT")
        if content is not None:
            column = content.column(align=True)
            column.separator()
            column.operator(
                "object.polygroups_setup_resculpting",
                text=t(context, "setup_resculpting"),
                icon="MOD_MULTIRES",
            )

            row = column.row(align=True)
            row.operator(
                "object.polygroups_add_multires",
                text=t(context, "multires"),
                icon="MOD_MULTIRES",
            )
            row.operator(
                "object.polygroups_add_shrinkwrap_to_highpoly",
                text=t(context, "shrinkwrap"),
                icon="MOD_SHRINKWRAP",
            )


class VIEW3D_PT_polygroups_seam_finalization(bpy.types.Panel):
    bl_label = "08 |"
    bl_text_key = "section_seam_finalization"
    bl_icon = "EDGE_SEAM"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 8
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout.box()
        settings = context.scene.polygroups_generator_settings
        seam_settings = context.scene.polygroups_seam_finalization_settings
        display_settings = context.scene.polygroups_seam_preparation_settings
        content = draw_topic(layout, context, "seam_final_0", 'Seam Settings', "PREFERENCES")
        if content is not None:
            column = content.column(align=True)
            column.prop(
                display_settings,
                "show_seams_object_mode",
                text=t(context, "show_seams_object_mode"),
                toggle=True,
                icon="EDGE_SEAM",
            )
            if display_settings.show_seams_object_mode:
                column.prop(
                    display_settings,
                    "seam_overlay_max_polygons",
                    text=t(context, "seam_overlay_max_polygons"),
                )
                draw_overlay_polygon_limit_status(
                    column,
                    context,
                    display_settings.seam_overlay_max_polygons,
                    "seam_overlay_skipped",
                )
            column.prop(seam_settings, "auto_unwrap_after_seam", text=t(context, "auto_unwrap"))
            column.prop(
                seam_settings,
                "auto_average_islands_scale_after_unwrap",
                text=t(context, "auto_average_islands_scale"),
            )
            column.prop(
                seam_settings,
                "prefer_backside_longitudinal_seam",
                text=t(context, "prefer_backside_longitudinal_seam"),
            )
            column.prop(seam_settings, "double_longitudinal_seam", text=t(context, "double_longitudinal_seam"))

        content = draw_topic(layout, context, "seam_final_1", 'Mark Seams', "EDGE_SEAM")
        if content is not None:
            column = content.column(align=True)
            column.separator()
            column.operator(
                "mesh.polygroups_mark_selected_edges_seam",
                text=t(context, "mark_selected_edges_seam"),
                icon="EDGESEL",
            )
            column.operator(
                "mesh.polygroups_mark_selection_boundary_seam",
                text=t(context, "mark_selection_boundary_seam"),
                icon="EDGESEL",
            )
            column.operator(
                "mesh.polygroups_mark_material_boundaries_seam",
                text=t(context, "generate_seams_materials"),
                icon="EDGE_SEAM",
            )
            column.operator(
                "mesh.polygroups_mark_longitudinal_seam",
                text=t(context, "create_longitudinal_seam"),
                icon="EDGESEL",
            )
            column.operator(
                "mesh.polygroups_mark_boundary_and_longitudinal_seam",
                text=t(context, "boundary_longitudinal_seam"),
                icon="EDGE_SEAM",
            )

        content = draw_topic(layout, context, "seam_final_2", 'Seam Gap Check', "VIEWZOOM")
        if content is not None:
            column = content.column(align=True)
            draw_seam_gap_controls(column, context, context.scene.polygroups_seam_preparation_settings)

        content = draw_topic(layout, context, "seam_final_3", 'Checker Preview', "TEXTURE")
        if content is not None:
            column = content.column(align=True)
            column.separator()
            column.prop(
                seam_settings,
                "show_checker_solid_mode",
                text=t(context, "show_checker_solid_mode"),
                toggle=True,
                icon="SHADING_SOLID",
            )
            column.prop(settings, "checker_scale", text=t(context, "checker_scale"))
            if seam_settings.show_checker_solid_mode:
                column.prop(
                    seam_settings,
                    "checker_overlay_opacity",
                    text=t(context, "checker_overlay_opacity"),
                )
                column.prop(
                    seam_settings,
                    "checker_overlay_max_polygons",
                    text=t(context, "checker_overlay_max_polygons"),
                )
                active_object = context.active_object
                polygon_limit = seam_settings.checker_overlay_max_polygons
                if (
                    polygon_limit > 0
                    and active_object is not None
                    and active_object.type == "MESH"
                    and len(active_object.data.polygons) > polygon_limit
                ):
                    column.label(
                        text=t(
                            context,
                            "checker_overlay_skipped",
                            polygons=f"{len(active_object.data.polygons):,}",
                            limit=f"{polygon_limit:,}",
                        ),
                        icon="INFO",
                    )
            column.operator(
                "object.polygroups_apply_checker_material",
                text=t(context, "apply_checker_material"),
                icon="TEXTURE",
            )

        content = draw_topic(layout, context, "seam_final_4", 'UV Unwrap', "UV")
        if content is not None:
            column = content.column(align=True)
            column.separator()
            column.operator(
                "object.polygroups_unwrap_angle_based",
                text=t(context, "unwrap_angle_based"),
                icon="UV",
            )
            column.operator(
                "object.polygroups_smart_uv_project",
                text=t(context, "smart_uv_project"),
                icon="UV",
            )
            column.operator(
                "object.polygroups_average_islands_scale",
                text=t(context, "average_islands_scale"),
                icon="UV_SYNC_SELECT",
            )


class VIEW3D_PT_polygroups_mesh_finalization(bpy.types.Panel):
    bl_label = "12 |"
    bl_text_key = "section_mesh_finalization"
    bl_icon = "MOD_DECIM"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 12
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout
        settings = context.scene.polygroups_mesh_finalization_settings

        decimate_content = draw_collapsible_box(
            layout,
            settings,
            "show_smart_decimate_settings",
            t(context, "decimate"),
            "MOD_DECIM",
        )
        if decimate_content is not None:
            self.draw_decimate(context, decimate_content)

        check_content = draw_collapsible_box(
            layout,
            settings,
            "show_mesh_check_settings",
            t(context, "check_mesh"),
            "VIEWZOOM",
        )
        if check_content is not None:
            self.draw_mesh_check(context, check_content)

        fab_content = draw_collapsible_box(
            layout,
            settings,
            "show_fab_rename_settings",
            t(context, "fab_rename"),
            "OUTLINER_OB_MESH",
        )
        if fab_content is not None:
            self.draw_fab_rename(context, fab_content)

        unity_content = draw_collapsible_box(
            layout, settings, "show_unity_rename_settings", "Unity Rename", icon="OUTLINER_OB_MESH",
        )
        if unity_content is not None:
            unity_content.label(text="Unity Prepare")
            unity_content.prop(settings, "unity_asset_name", text=t(context, "fab_asset_name"))
            row = unity_content.row(align=True)
            row.prop(settings, "unity_asset_index", text=t(context, "fab_asset_index"))
            row.prop(settings, "unity_auto_increment_index", text="", icon="ADD")
            unity_content.prop(settings, "unity_copy_textures", text=t(context, "copy_textures"))
            row = unity_content.row(align=True)
            for lod in range(6):
                row.operator("object.polygroups_prepare_unity", text=f"LOD{lod}").lod = f"LOD{lod}"
            unity_content.operator(
                "object.polygroups_prepare_unity", text="Prepare Meshes (Auto LOD)", icon="SORTSIZE",
            ).auto_lods = True

        export_content = draw_collapsible_box(
            layout,
            settings,
            "show_mesh_export_settings",
            t(context, "mesh_export"),
            "EXPORT",
        )
        if export_content is not None:
            self.draw_mesh_export(context, export_content)

    def draw_decimate(self, context, layout):
        settings = context.scene.polygroups_mesh_finalization_settings
        column = layout.column(align=True)
        column.prop(
            settings,
            "smart_decimate_duplicate_and_apply",
            text=t(context, "duplicate_and_apply_decimate"),
        )
        row = column.row(align=True)
        smart_decimate_operator = row.operator(
            "object.polygroups_smart_decimate",
            text=t(context, "smart_decimate"),
            icon="MOD_DECIM",
        )
        row.prop(
            settings,
            "smart_decimate_ratio",
            text=t(context, "ratio"),
        )
        smart_decimate_operator.ratio = settings.smart_decimate_ratio
        smart_decimate_operator.duplicate_and_apply = (
            settings.smart_decimate_duplicate_and_apply
        )

    def draw_mesh_check(self, context, layout):
        settings = context.scene.polygroups_mesh_finalization_settings
        column = layout.column(align=True)

        action_row = column.row(align=True)
        action_row.operator(
            "object.polygroups_check_mesh",
            text=t(context, "check_mesh"),
            icon="VIEWZOOM",
        )
        action_row.operator(
            "object.polygroups_create_mesh_backup",
            text=t(context, "create_bkp"),
            icon="DUPLICATE",
        )

        has_results = settings.mesh_check_status != "Not checked"
        has_any_issue = any(
            (
                settings.mesh_check_inconsistent_normals,
                settings.mesh_check_inward_normals,
                settings.mesh_check_ngons,
                settings.mesh_check_nonmanifold_edges,
                settings.mesh_check_boundary_loops,
                settings.mesh_check_loose_vertices,
                settings.mesh_check_loose_edges,
                settings.mesh_check_zero_area_faces,
                settings.mesh_check_duplicate_vertices,
                settings.mesh_check_thin_protrusions,
            )
        )
        if not has_results:
            status_icon = "INFO"
        elif has_any_issue:
            status_icon = "ERROR"
        else:
            status_icon = "CHECKMARK"
        column.label(text=t(context, "mesh_check_status", value=settings.mesh_check_status), icon=status_icon)

        def draw_issue_row(text_key, value, operator_id=None, operator_text_key=None, icon="ERROR"):
            if not value:
                return
            row = column.row(align=True)
            row.label(text=t(context, text_key, value=value), icon=icon)
            if operator_id:
                row.operator(
                    operator_id,
                    text=t(context, operator_text_key),
                )

        def draw_protrusion_buttons(row):
            row.operator(
                "object.polygroups_select_thin_protrusions",
                text=t(context, "select_thin_protrusions"),
            )
            row.operator(
                "object.polygroups_delete_thin_protrusions",
                text=t(context, "delete_thin_protrusions"),
            )

        if has_results and has_any_issue:
            normal_total = (
                settings.mesh_check_inconsistent_normals
                + settings.mesh_check_inward_normals
            )
            draw_issue_row(
                "mesh_check_normal_issues",
                normal_total,
                "object.polygroups_fix_mesh_normals",
                "fix_normals",
            )
            draw_issue_row(
                "mesh_check_ngons",
                settings.mesh_check_ngons,
                "object.polygroups_triangulate_ngons",
                "triangulate_ngons",
            )

            if settings.mesh_check_nonmanifold_edges:
                row = column.row(align=True)
                row.label(
                    text=t(
                        context,
                        "mesh_check_nonmanifold_edges",
                        value=settings.mesh_check_nonmanifold_edges,
                    ),
                    icon="ERROR",
                )
                row.operator(
                    "object.polygroups_clean_mesh",
                    text=t(context, "clean_mesh"),
                )
                draw_protrusion_buttons(row)

            draw_issue_row(
                "mesh_check_boundary_loops",
                settings.mesh_check_boundary_loops,
                "object.polygroups_fill_nonmanifold",
                "fill_nonmanifold",
            )

            loose_total = settings.mesh_check_loose_vertices + settings.mesh_check_loose_edges
            draw_issue_row(
                "mesh_check_loose_geometry",
                loose_total,
                "object.polygroups_delete_loose_geometry",
                "delete_loose",
            )

            cleanup_total = (
                settings.mesh_check_zero_area_faces
                + settings.mesh_check_duplicate_vertices
            )
            draw_issue_row(
                "mesh_check_cleanup_issues",
                cleanup_total,
                "object.polygroups_clean_mesh",
                "clean_mesh",
            )

            if settings.mesh_check_thin_protrusions:
                row = column.row(align=True)
                row.label(
                    text=t(
                        context,
                        "mesh_check_thin_protrusions",
                        value=settings.mesh_check_thin_protrusions,
                    ),
                    icon="ERROR",
                )
                draw_protrusion_buttons(row)

        column.separator()
        column.prop(
            settings,
            "show_all_mesh_fix_operators",
            text=t(context, "show_all_fix_operators"),
            toggle=True,
            icon="HIDE_OFF" if settings.show_all_mesh_fix_operators else "HIDE_ON",
        )
        if settings.show_all_mesh_fix_operators:
            all_box = column.box()
            all_column = all_box.column(align=True)

            row = all_column.row(align=True)
            row.operator(
                "object.polygroups_fix_mesh_normals",
                text=t(context, "fix_normals"),
            )
            row.operator(
                "object.polygroups_triangulate_ngons",
                text=t(context, "triangulate_ngons"),
            )

            row = all_column.row(align=True)
            row.operator(
                "object.polygroups_fill_nonmanifold",
                text=t(context, "fill_nonmanifold"),
            )
            row.operator(
                "object.polygroups_delete_loose_geometry",
                text=t(context, "delete_loose"),
            )

            row = all_column.row(align=True)
            draw_protrusion_buttons(row)
            row.operator(
                "object.polygroups_clean_mesh",
                text=t(context, "clean_mesh"),
                icon="BRUSH_DATA",
            )

    def draw_fab_rename(self, context, layout):
        settings = context.scene.polygroups_mesh_finalization_settings
        column = layout.column(align=True)
        column.prop(settings, "fab_asset_name", text=t(context, "fab_asset_name"))

        index_row = column.row(align=True)
        index_row.prop(settings, "fab_asset_index", text=t(context, "fab_asset_index"))
        index_row.prop(
            settings,
            "fab_auto_increment_index",
            text=t(context, "auto_increment_index"),
        )
        column.prop(settings, "fab_copy_textures", text=t(context, "copy_textures"))
        column.prop(
            settings,
            "fab_collection_color_tag",
            text=t(context, "fab_collection_color_tag"),
        )

        variant_row = column.row(align=True)
        high_operator = variant_row.operator(
            "object.polygroups_prepare_fab_variant",
            text="HIGH",
        )
        high_operator.variant = "HIGH"
        mid_operator = variant_row.operator(
            "object.polygroups_prepare_fab_variant",
            text="MID",
        )
        mid_operator.variant = "MID"
        low_operator = variant_row.operator(
            "object.polygroups_prepare_fab_variant",
            text="LOW",
        )
        low_operator.variant = "LOW"

        column.operator(
            "object.polygroups_auto_prepare_fab_selection",
            text=t(context, "auto_prepare_fab_selection"),
            icon="CHECKMARK",
        )

    def draw_mesh_export(self, context, layout):
        settings = context.scene.polygroups_mesh_finalization_settings
        content = draw_topic(layout, context, "export_0", 'Fab Export', "EXPORT")
        if content is not None:
            column = content.column(align=True)
            column.prop(
                settings,
                "mesh_export_format",
                text=t(context, "mesh_export_format"),
            )
            column.operator(
                "object.polygroups_export_selected_meshes",
                text=t(context, "export_selected_meshes"),
                icon="EXPORT",
            )

        content = draw_topic(layout, context, "export_1", 'Unity Export', "EXPORT")
        if content is not None:
            column = content.column(align=True)
            column.prop(settings, "unity_export_directory")
            column.prop(settings, "unity_export_overwrite")
            column.prop(settings, "unity_use_auto_rig_pro")
            column.operator("object.polygroups_export_unity", icon="EXPORT")

        content = draw_topic(layout, context, "export_2", 'Export Blend Assets', "FILE_BLEND")
        if content is not None:
            column = content.column(align=True)
            column.separator()
            blend_box = column.box()
            blend_column = blend_box.column(align=True)
            blend_column.prop(settings, "blend_export_directory", text=t(context, "blend_export_directory"))
            picker_row = blend_column.row(align=True)
            picker_row.prop(
                settings,
                "blend_export_static_collection_picker",
                text=t(context, "blend_export_static_collection_picker"),
            )
            picker_row.operator(
                "object.polygroups_add_blend_static_collection",
                text="",
                icon="ADD",
            )
            picker_row.operator(
                "object.polygroups_clear_blend_static_collections",
                text="",
                icon="TRASH",
            )
            blend_column.prop(
                settings,
                "blend_export_static_collections",
                text=t(context, "blend_export_static_collections"),
            )
            option_column = blend_column.column(align=True)
            option_column.prop(
                settings,
                "blend_export_individual_assets",
                text=t(context, "blend_export_individual_assets"),
            )
            option_column.prop(settings, "blend_export_all_low", text=t(context, "blend_export_all_low"))
            option_column.prop(settings, "blend_export_all_mid", text=t(context, "blend_export_all_mid"))
            option_column.prop(
                settings,
                "blend_export_include_render_settings",
                text=t(context, "blend_export_include_render_settings"),
            )
            option_column.prop(
                settings,
                "blend_export_overwrite_existing",
                text=t(context, "blend_export_overwrite_existing"),
            )

            action_row = blend_column.row(align=True)
            action_row.operator(
                "object.polygroups_scan_blend_assets",
                text=t(context, "blend_export_scan"),
                icon="VIEWZOOM",
            )
            action_row.operator(
                "object.polygroups_export_blend_assets",
                text=t(context, "blend_export_start"),
                icon="FILE_BLEND",
            )

            blend_column.label(text=t(context, "blend_export_status", value=settings.blend_export_status))
            stats_row = blend_column.row(align=True)
            stats_row.label(text=t(context, "blend_export_collections", value=settings.blend_export_collection_count))
            stats_row.label(text=t(context, "blend_export_files", value=settings.blend_export_file_count))
            stats_row = blend_column.row(align=True)
            stats_row.label(text=t(context, "blend_export_low", value=settings.blend_export_low_count))
            stats_row.label(text=t(context, "blend_export_mid", value=settings.blend_export_mid_count))


class VIEW3D_PT_polygroups_render(bpy.types.Panel):
    bl_label = "13 |"
    bl_text_key = "section_render"
    bl_icon = "RENDER_STILL"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Retopo"
    bl_parent_id = "VIEW3D_PT_polygroups_generator"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 13
    draw_header = draw_section_header_icon

    def draw(self, context):
        if not section_content_visible(self, context):
            return

        layout = self.layout.box()
        settings = context.scene.polygroups_render_settings
        content = draw_topic(layout, context, "render_0", 'Render Queue', "RENDER_STILL")
        if content is not None:
            column = content.column(align=True)

            row = column.row(align=True)
            row.enabled = not settings.is_running
            row.operator(
                "object.polygroups_scan_render_queue",
                text=t(context, "render_scan_queue"),
                icon="VIEWZOOM",
            )
            row.operator(
                "object.polygroups_start_render_queue",
                text=t(context, "render_start"),
                icon="RENDER_STILL",
            )

            current_row = column.row(align=True)
            current_row.enabled = not settings.is_running
            current_row.operator(
                "object.polygroups_render_current_state",
                text=t(context, "render_current_state"),
                icon="RENDER_RESULT",
            )

            row = column.row(align=True)
            row.operator(
                "object.polygroups_continue_render_queue",
                text=t(context, "render_continue"),
                icon="PLAY",
            )
            row.enabled = not settings.is_running and settings.total_count > 0
            stop_row = column.row(align=True)
            stop_row.enabled = settings.is_running
            stop_row.operator(
                "object.polygroups_stop_render_queue",
                text=t(context, "render_stop"),
                icon="CANCEL",
            )

        content = draw_topic(layout, context, "render_1", 'Quality and Output', "PREFERENCES")
        if content is not None:
            column = content.column(align=True)
            column.separator()
            column.prop(settings, "render_engine", text=t(context, "render_engine"))
            column.prop(settings, "max_samples", text=t(context, "render_max_samples"))
            resolution_row = column.row(align=True)
            resolution_row.prop(settings, "resolution_x", text=t(context, "render_resolution_x"))
            resolution_row.prop(settings, "resolution_y", text=t(context, "render_resolution_y"))
            column.prop(settings, "resolution_scale", text=t(context, "render_resolution_scale"))
            column.prop(settings, "output_directory", text=t(context, "render_output_directory"))

            options_row = column.row(align=True)
            options_row.prop(settings, "render_low", text=t(context, "render_low"))
            options_row.prop(settings, "render_mid", text=t(context, "render_mid"))
            column.prop(settings, "transparent_background", text=t(context, "render_transparent_background"))
            scene_row = column.row(align=True)
            scene_row.enabled = settings.transparent_background
            scene_row.prop(settings, "scene_collection_prefix", text=t(context, "render_scene_collection_prefix"))
            column.prop(settings, "skip_existing", text=t(context, "render_skip_existing"))
            column.prop(settings, "overwrite_existing", text=t(context, "render_overwrite_existing"))

        content = draw_topic(layout, context, "render_2", 'Multiple Views', "CAMERA_DATA")
        if content is not None:
            column = content.column(align=True)
            column.separator()
            column.prop(settings, "multiview_render", text=t(context, "render_multiview"))
            multiview_row = column.row(align=True)
            multiview_row.enabled = settings.multiview_render
            multiview_row.prop(settings, "multiview_offset", text=t(context, "render_multiview_offset"))
            clear_row = column.row(align=True)
            clear_row.enabled = not settings.is_running
            clear_row.operator(
                "object.polygroups_clear_multiview_render",
                text=t(context, "render_clear_multiview"),
                icon="TRASH",
            )

        content = draw_topic(layout, context, "render_3", 'Freestyle Edges', "EDGE_SEAM")
        if content is not None:
            column = content.column(align=True)
            column.separator()
            column.prop(settings, "freestyle_edges", text=t(context, "render_freestyle_edges"))
            freestyle_column = column.column(align=True)
            freestyle_column.enabled = settings.freestyle_edges
            freestyle_column.prop(settings, "freestyle_as_render_pass", text=t(context, "render_freestyle_as_pass"))
            freestyle_column.prop(settings, "freestyle_line_thickness", text=t(context, "render_freestyle_thickness"))
            freestyle_column.prop(settings, "freestyle_line_color", text=t(context, "render_freestyle_color"))
            freestyle_row = column.row(align=True)
            freestyle_row.enabled = not settings.is_running
            freestyle_row.operator(
                "object.polygroups_mark_freestyle_edges",
                text=t(context, "render_mark_freestyle"),
                icon="EDGESEL",
            )
            freestyle_row.operator(
                "object.polygroups_clear_freestyle_edges",
                text=t(context, "render_clear_freestyle"),
                icon="TRASH",
            )

        content = draw_topic(layout, context, "render_4", 'Progress', "INFO")
        if content is not None:
            column = content.column(align=True)
            column.separator()
            column.label(text=t(context, "render_status", value=settings.status))
            column.label(text=t(context, "render_collections", value=settings.collection_count))
            column.label(text=t(context, "render_queued", value=settings.total_count))
            column.label(text=t(context, "render_rendered", value=settings.rendered_count))
            column.label(text=t(context, "render_remaining", value=settings.remaining_count))
            if settings.current_collection or settings.current_object:
                column.label(
                    text=t(
                        context,
                        "render_current",
                        collection=settings.current_collection or "-",
                        object=settings.current_object or "-",
                    ),
                )
            if settings.last_output_path:
                column.label(text=t(context, "render_last_output", value=settings.last_output_path), icon="FILE_IMAGE")


class WM_OT_airetopo_toggle_view_assists(bpy.types.Operator):
    bl_idname = "wm.airetopo_toggle_view_assists"
    bl_label = "Toggle View Assists"
    bl_description = "Show or hide Object Mode seams and the Solid Mode checker together"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        seam_settings = context.scene.polygroups_seam_preparation_settings
        checker_settings = context.scene.polygroups_seam_finalization_settings
        enable = not (
            seam_settings.show_seams_object_mode
            and checker_settings.show_checker_solid_mode
        )
        seam_settings.show_seams_object_mode = enable
        checker_settings.show_checker_solid_mode = enable
        if not enable:
            from .seam_object_overlay import clear_cache as clear_seam_overlay_cache
            from .uv_checker_overlay import clear_cache as clear_checker_overlay_cache

            clear_seam_overlay_cache()
            clear_checker_overlay_cache()
        self.report(
            {"INFO"},
            t(context, "view_assists_enabled" if enable else "view_assists_disabled"),
        )
        return {"FINISHED"}


SECTION_PANEL_CLASSES = (
    VIEW3D_PT_polygroups_import,
    VIEW3D_PT_polygroups_batch_import,
    VIEW3D_PT_polygroups_model_preparation,
    VIEW3D_PT_polygroups_seam_preparation,
    VIEW3D_PT_polygroups_tools,
    VIEW3D_PT_polygroups_remesh,
    VIEW3D_PT_polygroups_resculpting,
    VIEW3D_PT_polygroups_seam_finalization,
    VIEW3D_PT_polygroups_uv_preparation,
    VIEW3D_PT_polygroups_baking,
    VIEW3D_PT_airetopo_ai_generation,
    VIEW3D_PT_polygroups_mesh_finalization,
    VIEW3D_PT_polygroups_render,
)

CLASSES = (
    VIEW3D_PT_polygroups_generator,
    WM_OT_airetopo_toggle_view_assists,
)

SECTION_PANEL_VISIBILITY = (
    (VIEW3D_PT_polygroups_import, "show_import_section"),
    (VIEW3D_PT_polygroups_batch_import, "show_batch_import_section"),
    (VIEW3D_PT_polygroups_model_preparation, "show_model_preparation_section"),
    (VIEW3D_PT_polygroups_seam_preparation, "show_seam_preparation_section"),
    (VIEW3D_PT_polygroups_tools, "show_polygroups_section"),
    (VIEW3D_PT_polygroups_remesh, "show_remesh_section"),
    (VIEW3D_PT_polygroups_resculpting, "show_resculpting_section"),
    (VIEW3D_PT_polygroups_seam_finalization, "show_seam_finalization_section"),
    (VIEW3D_PT_polygroups_uv_preparation, "show_uv_preparation_section"),
    (VIEW3D_PT_polygroups_baking, "show_baking_section"),
    (VIEW3D_PT_airetopo_ai_generation, "show_ai_generation_section"),
    (VIEW3D_PT_polygroups_mesh_finalization, "show_mesh_finalization_section"),
    (VIEW3D_PT_polygroups_render, "show_render_section"),
)

for section_class, visibility_property in SECTION_PANEL_VISIBILITY:
    section_class.visibility_property = visibility_property


def draw_edge_menu(self, context):
    """AI Retopo seam and pinned-edge commands in Edge (Ctrl+E)."""
    layout = self.layout
    layout.separator()
    layout.label(text=t(context, "edge_menu_group"), icon="EDGE_SEAM")
    layout.prop(
        context.scene.polygroups_seam_preparation_settings,
        "seam_path_pin",
        text=t(context, "mark_as_pinned"),
    )
    layout.prop(
        context.scene.polygroups_seam_finalization_settings,
        "auto_unwrap_after_seam",
        text=t(context, "auto_unwrap"),
        toggle=True,
        icon="UV",
    )
    layout.operator(
        "mesh.polygroups_connect_vertex_seam",
        text=t(context, "connect_vertices_seam"),
        icon="EDGE_SEAM",
    )
    layout.operator(
        "mesh.polygroups_edge_seam_path",
        text=t(context, "connect_vertices_edge_seam_path"),
        **icon_kwargs("edge_seam_path", "EDGE_SEAM"),
    )
    layout.separator()
    layout.operator(
        "mesh.polygroups_mark_selected_edges_seam",
        text=t(context, "mark_selected_edges_seam"),
        icon="EDGESEL",
    )
    layout.operator(
        "mesh.polygroups_mark_selection_boundary_seam",
        text=t(context, "mark_selection_boundary_seam"),
        icon="FACESEL",
    )
    layout.operator(
        "mesh.polygroups_clear_selected_edges_seam",
        text=t(context, "clear_selected_edges_seam"),
        icon="X",
    )
    layout.operator(
        "mesh.polygroups_clear_inside_edges_seam",
        text=t(context, "clear_inside_edges_seam"),
        icon="X",
    )
    layout.separator()
    layout.operator("mesh.polygroups_pin_selected_seams", text=t(context, "pin_selected_seams"), **icon_kwargs("pin_vertices", "PINNED"))
    layout.operator("mesh.polygroups_unpin_selected_edges", text=t(context, "unpin_selected"), **icon_kwargs("unpin_vertices", "UNPINNED"))
    layout.operator("mesh.polygroups_clear_all_pins", text=t(context, "clear_all_pins"), **icon_kwargs("unpin_vertices", "X"))


def draw_outliner_header(self, context):
    """Compact duplicates of Management controls in the Outliner header."""
    row = self.layout.row(align=True)
    row.separator()
    previous = row.operator(
        "object.polygroups_generated_collection",
        text="Prev",
        icon="TRIA_LEFT",
    )
    previous.action = "PREVIOUS"
    following = row.operator(
        "object.polygroups_generated_collection",
        text="Next",
        icon="TRIA_RIGHT",
    )
    following.action = "NEXT"
    row.separator()
    hide_highpoly = row.operator(
        "object.polygroups_object_visibility",
        text="",
        icon="RESTRICT_VIEW_ON",
    )
    hide_highpoly.prefix = "Highpoly_"
    hide_highpoly.hidden = True
    show_highpoly = row.operator(
        "object.polygroups_object_visibility",
        text="",
        icon="RESTRICT_VIEW_OFF",
    )
    show_highpoly.prefix = "Highpoly_"
    show_highpoly.hidden = False
    row.separator()
    hide_lowpoly = row.operator(
        "object.polygroups_object_visibility",
        text="",
        icon="RESTRICT_VIEW_ON",
    )
    hide_lowpoly.prefix = "Retopo_"
    hide_lowpoly.hidden = True
    show_lowpoly = row.operator(
        "object.polygroups_object_visibility",
        text="",
        icon="RESTRICT_VIEW_OFF",
    )
    show_lowpoly.prefix = "Retopo_"
    show_lowpoly.hidden = False


def draw_view_assists_header(self, context):
    """Combined seam/checker overlay toggle in every 3D View header."""
    scene = getattr(context, "scene", None)
    if scene is None:
        return
    seam_settings = getattr(scene, "polygroups_seam_preparation_settings", None)
    checker_settings = getattr(scene, "polygroups_seam_finalization_settings", None)
    if seam_settings is None or checker_settings is None:
        return
    enabled = bool(
        seam_settings.show_seams_object_mode
        and checker_settings.show_checker_solid_mode
    )
    row = self.layout.row(align=True)
    row.separator()
    row.operator(
        "wm.airetopo_toggle_view_assists",
        text="",
        icon="HIDE_OFF" if enabled else "HIDE_ON",
        depress=enabled,
    )


OBJECT_SELECT_TOOL_IDS = {
    "builtin.select",
    "builtin.select_box",
    "builtin.select_circle",
    "builtin.select_lasso",
}


def draw_object_select_tool_actions(self, context):
    """AI Retopo actions beside native Object Mode selection-tool settings."""
    if context.mode != "OBJECT":
        return
    tool = context.workspace.tools.from_space_view3d_mode("OBJECT", create=False)
    if tool is None or tool.idname not in OBJECT_SELECT_TOOL_IDS:
        return

    layout = self.layout
    layout.separator()
    remesh_row = layout.row(align=True)
    remesh_row.label(text="Remesh:")
    for label, quad_count in get_remesh_preset_counts(context):
        operator = remesh_row.operator(
            "object.polygroups_checked_quad_remesh",
            text=label,
        )
        operator.quad_count = quad_count

    layout.separator()
    layout.operator(
        "object.polygroups_unwrap_angle_based",
        text="Unwrap",
        icon="UV",
    )
    layout.operator(
        "object.polygroups_uvpackmaster_pack",
        text="Pack",
        icon="UV_SYNC_SELECT",
    )
    layout.operator(
        "object.polygroups_checked_prepare_and_bake",
        text="Auto Bake",
        icon="RENDER_RESULT",
    )


def draw_view_assists_shading_pie(self, context):
    """Add the combined overlay toggle to Blender's standard Z shading pie."""
    scene = getattr(context, "scene", None)
    if scene is None:
        return
    seam_settings = getattr(scene, "polygroups_seam_preparation_settings", None)
    checker_settings = getattr(scene, "polygroups_seam_finalization_settings", None)
    if seam_settings is None or checker_settings is None:
        return
    enabled = bool(
        seam_settings.show_seams_object_mode
        and checker_settings.show_checker_solid_mode
    )
    pie = self.layout.menu_pie()
    pie.operator(
        "wm.airetopo_toggle_view_assists",
        text=t(context, "toggle_view_assists"),
        icon="HIDE_OFF" if enabled else "HIDE_ON",
        depress=enabled,
    )


def draw_object_apply_menu(self, context):
    """Add the cutter workflow to Object Mode's Ctrl+A menu."""
    self.layout.separator()
    self.layout.operator(
        "object.polygroups_apply_cutter_seams",
        text=t(context, "apply_cutter_seams"),
        icon="EDGE_SEAM",
    )


def register():
    update_panel_labels(bpy.context)
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_edit_mesh_edges.append(draw_edge_menu)
    bpy.types.VIEW3D_MT_object_apply.append(draw_object_apply_menu)
    bpy.types.VIEW3D_MT_shading_pie.append(draw_view_assists_shading_pie)
    bpy.types.OUTLINER_HT_header.prepend(draw_outliner_header)
    bpy.types.VIEW3D_HT_header.append(draw_view_assists_header)
    bpy.types.VIEW3D_HT_tool_header.append(draw_object_select_tool_actions)


def unregister():
    bpy.types.VIEW3D_HT_tool_header.remove(draw_object_select_tool_actions)
    bpy.types.VIEW3D_HT_header.remove(draw_view_assists_header)
    bpy.types.OUTLINER_HT_header.remove(draw_outliner_header)
    bpy.types.VIEW3D_MT_shading_pie.remove(draw_view_assists_shading_pie)
    bpy.types.VIEW3D_MT_object_apply.remove(draw_object_apply_menu)
    bpy.types.VIEW3D_MT_edit_mesh_edges.remove(draw_edge_menu)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
