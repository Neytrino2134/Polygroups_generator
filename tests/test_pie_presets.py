"""Blender --background --factory-startup --python-exit-code 1 --python this_file."""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator import hotkeys, pie_presets as pie
from polygroups_generator.localization import TEXT

context = bpy.context
prefs = context.preferences.addons[ROOT.name].preferences
assert pie.current_slots(prefs) == pie.BUILTIN_PRESETS['GENERAL']
assert prefs.active_pie_preset == 'CURRENT'
# Original enum indices must not move when new commands are appended.
assert [item[0] for item in hotkeys.PIE_COMMAND_ITEMS[:12]] == [
    'NONE', 'IMPORT_FILES', 'APPLY_CUTTER_SEAMS', 'GENERATE_POLYGROUPS',
    'RENAME_WELD', 'REMESH', 'UV_PACK', 'CHECK_MATERIALS', 'PREPARE_BAKE',
    'SAVE_TEXTURES', 'CLEAR_BAKE_IMAGES', 'CUTTER_TWEAK',
][:12]
# Preserve an existing custom layout when first selecting an example preset.
prefs.pie_slot_1 = 'DELETE_FILL'
original = pie.current_slots(prefs)
prefs.active_pie_preset = 'SEAMS'
assert pie.current_slots(prefs) == pie.BUILTIN_PRESETS['SEAMS']
prefs.active_pie_preset = 'GENERAL'
assert pie.current_slots(prefs) == pie.BUILTIN_PRESETS['GENERAL']
prefs.active_pie_preset = 'CURRENT'
assert pie.current_slots(prefs) == original
assert bpy.ops.wm.airetopo_save_pie_preset_as(preset_name='My Layout') == {'FINISHED'}
first_id = prefs.active_pie_preset
assert pie.custom_preset(prefs).name == 'My Layout'
# Slot picker assigns without executing a modeling operator.
assert bpy.ops.wm.airetopo_search_pie_command(slot=2, command='SELECT_LINKED_SEAM') == {'FINISHED'}
assert prefs.pie_slot_2 == 'SELECT_LINKED_SEAM'
assert pie.current_slots(prefs) != pie.preset_slots(prefs)
assert bpy.ops.wm.airetopo_save_pie_preset() == {'FINISHED'}
saved = pie.current_slots(prefs)
prefs.pie_slot_2 = 'NONE'
assert bpy.ops.wm.airetopo_load_pie_preset() == {'FINISHED'}
assert pie.current_slots(prefs) == saved
assert bpy.ops.wm.airetopo_save_pie_preset_as(preset_name='My Layout') == {'FINISHED'}
assert pie.custom_preset(prefs).name == 'My Layout (2)'
assert len(prefs.pie_presets) == 2
second_id = prefs.active_pie_preset
assert bpy.ops.wm.airetopo_delete_pie_preset() == {'FINISHED'}
assert prefs.active_pie_preset == 'CURRENT' and pie.current_slots(prefs) == saved
assert len(prefs.pie_presets) == 1
prefs.active_pie_preset = first_id
assert pie.current_slots(prefs) == saved
# File round-trip creates a new preset; malformed files do not change anything.
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'pie.json'
    assert bpy.ops.wm.airetopo_export_pie_preset(filepath=str(path)) == {'FINISHED'}
    assert json.loads(path.read_text(encoding='utf-8'))['slots'] == list(saved)
    assert bpy.ops.wm.airetopo_import_pie_preset(filepath=str(path)) == {'FINISHED'}
    assert len(prefs.pie_presets) == 2
    assert prefs.active_pie_preset not in (first_id, second_id)
    assert pie.current_slots(prefs) == saved
    name, slots = pie.parse_preset_document(json.loads(path.read_text(encoding='utf-8')))
    assert tuple(slots) == saved
    document = json.loads(path.read_text(encoding='utf-8'))
    document['slots'][0] = 'python.exec'
    try:
        pie.parse_preset_document(document)
    except ValueError:
        pass
    else:
        raise AssertionError('unknown commands were accepted')
    assert len(prefs.pie_presets) == 2
# Both UI languages stay searchable by English and translated labels.
for language in ('EN', 'RU'):
    prefs.interface_language = language
    items = pie.command_search_items(None, context)
    linked = next(item for item in items if item[0] == 'SELECT_LINKED_SEAM')
    assert 'Select Linked' in linked[1]
    assert TEXT[language]['select_linked_seam'] in linked[1]
    assert len(items) == len(hotkeys.PIE_COMMAND_ITEMS)
    assert len({item[0] for item in items}) == len(items)
prefs.interface_language = 'EN'
# Validate all integrated command IDs and their property arguments against RNA.
optional = {'UV_PACK'}
icons = bpy.types.UILayout.bl_rna.functions['operator'].parameters['icon'].enum_items
for identifier, command in hotkeys.PIE_COMMANDS.items():
    assert command['icon'] in icons, (identifier, command['icon'])
    if identifier in optional:
        continue
    module, name = command['operator'].split('.')
    rna = getattr(getattr(bpy.ops, module), name).get_rna_type()
    for prop in command.get('properties', {}):
        assert prop in rna.properties, (identifier, prop)
assert hotkeys.PIE_COMMANDS['SELECT_LINKED_SEAM']['properties']['delimit'] == {'SEAM'}
assert 'KNIFE_SEAM_TOOL' in pie.BUILTIN_PRESETS['SEAMS']
# Rendering the active menu must pass the forced Seam delimiter to Blender,
# and presets must affect the actual eight displayed commands.
class Layout:
    def __init__(self):
        self.commands = []
    def menu_pie(self):
        return self
    def row(self, **kwargs):
        return self
    def column(self, **kwargs):
        return self
    def label(self, **kwargs):
        pass
    def prop(self, *args, **kwargs):
        pass
    def separator(self):
        self.commands.append(('NONE', SimpleNamespace()))
    def operator(self, identifier, **kwargs):
        properties = SimpleNamespace()
        self.commands.append((identifier, properties))
        return properties

prefs.active_pie_preset = 'SEAMS'
layout = Layout()
hotkeys.VIEW3D_MT_airetopo_pie.draw(SimpleNamespace(layout=layout), context)
assert len(layout.commands) == 8
directions = dict(zip(('W', 'E', 'S', 'N', 'NW', 'NE', 'SW', 'SE'), layout.commands))
for direction, command in zip(('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'), pie.current_slots(prefs)):
    assert directions[direction][0] == hotkeys.PIE_COMMANDS[command]['operator']
linked = next(props for name, props in layout.commands if name == 'mesh.select_linked')
assert linked.delimit == {'SEAM'}
layout = Layout()
pie.draw_pie_settings(prefs, context, layout)
assert [props.slot for name, props in layout.commands if name == 'wm.airetopo_search_pie_command'] == list(range(1, 9))
assert context.preferences.is_dirty
print('PIE_PRESET_TESTS_PASSED', len(hotkeys.PIE_COMMAND_ITEMS), 'commands', flush=True)

