"""Searchable pie slots and named presets stored in Blender add-on preferences."""
import json
import uuid
from pathlib import Path

import bpy
from bpy_extras.io_utils import ImportHelper, ExportHelper

from .hotkeys import PIE_COMMAND_ITEMS, PIE_COMMANDS
from .localization import get_preferences, get_language, t

BUILTIN_PRESETS = {
    'GENERAL': ('IMPORT_FILES', 'APPLY_CUTTER_SEAMS', 'GENERATE_POLYGROUPS', 'CUTTER_TWEAK',
                'UV_PACK', 'REMESH', 'CHECK_MATERIALS', 'PREPARE_BAKE'),
    'SEAMS': ('SELECT_LESS', 'SELECT_MORE', 'DELETE_FILL', 'SELECT_LINKED_SEAM',
              'MARK_SEAM', 'CLEAR_SELECTED_SEAMS', 'MARK_BOUNDARY_SEAM', 'KNIFE_SEAM_TOOL'),
}
COMMAND_IDS = {item[0] for item in PIE_COMMAND_ITEMS}
_COMMAND_NAMES = {item[0]: item[1] for item in PIE_COMMAND_ITEMS}
_ENUM_CACHE = {}
_LOADING = False
SLOT_DIRECTIONS = ('top', 'top_right', 'right', 'bottom_right', 'bottom', 'bottom_left', 'left', 'top_left')


def current_slots(preferences):
    return tuple(getattr(preferences, f'pie_slot_{index}') for index in range(1, 9))


def validate_slots(slots):
    if not isinstance(slots, (tuple, list)) or len(slots) != 8:
        raise ValueError('A pie preset must contain exactly eight slots')
    if any(not isinstance(item, str) or item not in COMMAND_IDS for item in slots):
        raise ValueError('The preset contains an unknown command; update the add-on or check the file')
    return tuple(slots)


def command_label(context, identifier):
    command = PIE_COMMANDS.get(identifier)
    return t(context, command['label']) if command else t(context, 'pie_empty')


def command_search_items(self, context):
    language = get_language(context)
    key = ('commands', language)
    if key not in _ENUM_CACHE:
        items = []
        for number, (identifier, english, description) in enumerate(PIE_COMMAND_ITEMS):
            label = command_label(context, identifier)
            if label != english:
                label += ' / ' + english
            items.append((identifier, label, description, PIE_COMMANDS.get(identifier, {}).get('icon', 'BLANK1'), number))
        _ENUM_CACHE[key] = tuple(items)
    return _ENUM_CACHE[key]


def preset_items(preferences, context):
    custom = tuple((item.preset_id, item.name, item.enum_value) for item in preferences.pie_presets)
    key = ('presets', get_language(context), custom)
    if key not in _ENUM_CACHE:
        _ENUM_CACHE[key] = (
            ('CURRENT', t(context, 'pie_current_layout'), '', 0),
            ('GENERAL', t(context, 'pie_preset_general'), '', 1),
            ('SEAMS', t(context, 'pie_preset_seams'), '', 2),
        ) + tuple((identifier, name, name, number) for identifier, name, number in custom)
    return _ENUM_CACHE[key]


def custom_preset(preferences):
    return next((item for item in preferences.pie_presets
                 if item.preset_id == preferences.active_pie_preset), None)


def preset_slots(preferences):
    identifier = preferences.active_pie_preset
    if identifier in BUILTIN_PRESETS:
        return BUILTIN_PRESETS[identifier]
    if identifier == 'CURRENT':
        data = preferences.pie_current_slots
        return validate_slots(json.loads(data)) if data else current_slots(preferences)
    item = custom_preset(preferences)
    if item is None:
        raise ValueError('The selected preset is no longer available')
    return validate_slots(json.loads(item.slots_json))


def _mark_dirty(context):
    if context is not None:
        context.preferences.is_dirty = True


def slot_updated(preferences, context):
    if not _LOADING:
        preferences.pie_current_slots = json.dumps(current_slots(preferences))
        _mark_dirty(context)


def apply_active_preset(preferences, context):
    global _LOADING
    if _LOADING:
        return
    if not preferences.pie_current_slots:
        # Preserve pre-existing custom slots on the first preset switch.
        preferences.pie_current_slots = json.dumps(current_slots(preferences))
    slots = preset_slots(preferences)
    _LOADING = True
    try:
        for index, command in enumerate(slots, 1):
            setattr(preferences, f'pie_slot_{index}', command)
    finally:
        _LOADING = False
    _mark_dirty(context)


def preset_updated(preferences, context):
    try:
        apply_active_preset(preferences, context)
    except (ValueError, TypeError) as error:
        # Do not partially replace the current layout with a damaged preset.
        preferences['active_pie_preset'] = 0
        print('AI Retopo pie preset:', error)


def add_preset(preferences, name, slots):
    slots = validate_slots(slots)
    name = ' '.join(name.split())[:80]
    if not name:
        raise ValueError('Enter a preset name')
    # Import and Save As always create a new preset; existing names are retained.
    existing = {item.name.casefold() for item in preferences.pie_presets}
    base, suffix = name, 2
    while name.casefold() in existing:
        name = f'{base} ({suffix})'
        suffix += 1
    item = preferences.pie_presets.add()
    item.name = name
    item.preset_id = uuid.uuid4().hex
    item.enum_value = preferences.pie_next_preset_number
    preferences.pie_next_preset_number += 1
    item.slots_json = json.dumps(slots)
    preferences.active_pie_preset = item.preset_id
    return item


def preset_document(preferences):
    item = custom_preset(preferences)
    name = item.name if item else preferences.active_pie_preset.title()
    return {'schema': 'airetopo.pie', 'version': 1, 'name': name, 'slots': list(current_slots(preferences))}


def parse_preset_document(document):
    if not isinstance(document, dict) or document.get('schema') != 'airetopo.pie' or document.get('version') != 1:
        raise ValueError('Not a supported AI Retopo pie preset')
    name = document.get('name')
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise ValueError('The preset needs a valid name')
    return name, validate_slots(document.get('slots'))


class AIRETOPO_PG_pie_preset(bpy.types.PropertyGroup):
    preset_id: bpy.props.StringProperty()
    enum_value: bpy.props.IntProperty(min=3, default=3)
    slots_json: bpy.props.StringProperty()


class AIRETOPO_OT_search_pie_command(bpy.types.Operator):
    bl_idname = 'wm.airetopo_search_pie_command'
    bl_label = 'Search Pie Menu Command'
    bl_description = 'Search commands by English or translated name and assign one to this slot'
    bl_property = 'command'

    slot: bpy.props.IntProperty(default=1, min=1, max=8, options={'HIDDEN', 'SKIP_SAVE'})
    command: bpy.props.EnumProperty(items=command_search_items)

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        preferences = get_preferences(context)
        if preferences is None:
            return {'CANCELLED'}
        setattr(preferences, f'pie_slot_{self.slot}', self.command)
        return {'FINISHED'}


class AIRETOPO_OT_save_pie_preset_as(bpy.types.Operator):
    bl_idname = 'wm.airetopo_save_pie_preset_as'
    bl_label = 'Save Pie Preset As'
    bl_description = 'Save the current eight slots as a new named preset'
    preset_name: bpy.props.StringProperty(name='Preset Name', maxlen=80)

    def invoke(self, context, event):
        self.preset_name = t(context, 'pie_new_preset')
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        preferences = get_preferences(context)
        try:
            item = add_preset(preferences, self.preset_name, current_slots(preferences))
        except ValueError as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        _mark_dirty(context)
        self.report({'INFO'}, t(context, 'pie_preset_saved', name=item.name))
        return {'FINISHED'}


class AIRETOPO_OT_save_pie_preset(bpy.types.Operator):
    bl_idname = 'wm.airetopo_save_pie_preset'
    bl_label = 'Save Pie Preset'
    bl_description = 'Update the active user preset with the current slots'

    @classmethod
    def poll(cls, context):
        preferences = get_preferences(context)
        return preferences is not None and custom_preset(preferences) is not None

    def execute(self, context):
        preferences = get_preferences(context)
        item = custom_preset(preferences)
        item.slots_json = json.dumps(current_slots(preferences))
        _mark_dirty(context)
        self.report({'INFO'}, t(context, 'pie_preset_saved', name=item.name))
        return {'FINISHED'}


class AIRETOPO_OT_load_pie_preset(bpy.types.Operator):
    bl_idname = 'wm.airetopo_load_pie_preset'
    bl_label = 'Load Pie Preset'
    bl_description = 'Reload the saved slots of the active preset'

    def execute(self, context):
        try:
            apply_active_preset(get_preferences(context), context)
        except (ValueError, TypeError) as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


class AIRETOPO_OT_delete_pie_preset(bpy.types.Operator):
    bl_idname = 'wm.airetopo_delete_pie_preset'
    bl_label = 'Delete Pie Preset'
    bl_description = 'Remove the active user preset, keeping its slots as the current layout'

    @classmethod
    def poll(cls, context):
        return AIRETOPO_OT_save_pie_preset.poll(context)

    def execute(self, context):
        preferences = get_preferences(context)
        identifier = preferences.active_pie_preset
        preferences.pie_current_slots = json.dumps(current_slots(preferences))
        preferences.active_pie_preset = 'CURRENT'
        for index, item in enumerate(preferences.pie_presets):
            if item.preset_id == identifier:
                preferences.pie_presets.remove(index)
                break
        _mark_dirty(context)
        return {'FINISHED'}


class AIRETOPO_OT_export_pie_preset(bpy.types.Operator, ExportHelper):
    bl_idname = 'wm.airetopo_export_pie_preset'
    bl_label = 'Export Pie Preset'
    filename_ext = '.json'
    filter_glob: bpy.props.StringProperty(default='*.json', options={'HIDDEN'})

    def execute(self, context):
        try:
            Path(self.filepath).write_text(json.dumps(preset_document(get_preferences(context)),
                                                     ensure_ascii=False, indent=2), encoding='utf-8')
        except OSError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


class AIRETOPO_OT_import_pie_preset(bpy.types.Operator, ImportHelper):
    bl_idname = 'wm.airetopo_import_pie_preset'
    bl_label = 'Import Pie Preset As New'
    filename_ext = '.json'
    filter_glob: bpy.props.StringProperty(default='*.json', options={'HIDDEN'})

    def execute(self, context):
        try:
            path = Path(self.filepath)
            if path.stat().st_size > 262144:
                raise ValueError('Preset file is too large')
            name, slots = parse_preset_document(json.loads(path.read_text(encoding='utf-8-sig')))
            item = add_preset(get_preferences(context), name, slots)
        except (OSError, ValueError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        _mark_dirty(context)
        self.report({'INFO'}, t(context, 'pie_preset_saved', name=item.name))
        return {'FINISHED'}


def draw_pie_settings(preferences, context, layout):
    layout.operator_context = 'INVOKE_DEFAULT'
    layout.label(text=t(context, 'preferences_pie_menu'), icon='MENU_PANEL')
    row = layout.row(align=True)
    row.prop(preferences, 'active_pie_preset', text=t(context, 'pie_active_preset'))
    row.operator('wm.airetopo_load_pie_preset', text='', icon='FILE_REFRESH')
    row = layout.row(align=True)
    row.operator('wm.airetopo_save_pie_preset_as', text=t(context, 'pie_save_as'), icon='ADD')
    row.operator('wm.airetopo_save_pie_preset', text=t(context, 'pie_save'), icon='FILE_TICK')
    row.operator('wm.airetopo_delete_pie_preset', text='', icon='TRASH')
    row = layout.row(align=True)
    row.operator('wm.airetopo_import_pie_preset', text=t(context, 'pie_import'), icon='IMPORT')
    export = row.operator('wm.airetopo_export_pie_preset', text=t(context, 'pie_export'), icon='EXPORT')
    export.filepath = 'pie_preset.json'
    if current_slots(preferences) != preset_slots(preferences):
        layout.label(text=t(context, 'pie_modified'), icon='INFO')
    layout.label(text=t(context, 'pie_search_hint'), icon='VIEWZOOM')
    column = layout.column(align=True)
    column.operator_context = 'INVOKE_DEFAULT'
    for index, command in enumerate(current_slots(preferences), 1):
        row = column.row(align=True)
        row.label(text=t(context, 'pie_slot', index=index) + ' — ' + t(context, 'pie_direction_' + SLOT_DIRECTIONS[index - 1]))
        picker = row.operator('wm.airetopo_search_pie_command', text=command_label(context, command), icon='VIEWZOOM')
        picker.slot = index
    layout.label(text=t(context, 'pie_preferences_hint'))


CLASSES = (
    AIRETOPO_PG_pie_preset, AIRETOPO_OT_search_pie_command,
    AIRETOPO_OT_save_pie_preset_as, AIRETOPO_OT_save_pie_preset,
    AIRETOPO_OT_load_pie_preset, AIRETOPO_OT_delete_pie_preset,
    AIRETOPO_OT_export_pie_preset, AIRETOPO_OT_import_pie_preset,
)
