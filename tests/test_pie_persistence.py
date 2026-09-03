"""Two-process preference persistence check; use an isolated BLENDER_USER_CONFIG.

Run with -- write, then without --factory-startup with -- read.
"""
import os
import sys
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
assert 'airetopo-pie-test-' in os.environ.get('BLENDER_USER_CONFIG', ''), 'Use an isolated test config'
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator import pie_presets as pie
prefs = bpy.context.preferences.addons[ROOT.name].preferences
if sys.argv[-1] == 'write':
    prefs.active_pie_preset = 'SEAMS'
    bpy.ops.wm.airetopo_save_pie_preset_as(preset_name='Persistent seams')
    prefs.pie_slot_8 = 'VERTEX_SEAM_TOOL'
    bpy.ops.wm.airetopo_save_pie_preset()
    assert bpy.ops.wm.save_userpref() == {'FINISHED'}
    print('PIE_PREFERENCES_WRITTEN', flush=True)
else:
    assert len(prefs.pie_presets) == 1
    assert pie.custom_preset(prefs).name == 'Persistent seams'
    assert prefs.pie_slot_8 == 'VERTEX_SEAM_TOOL'
    assert pie.current_slots(prefs) == pie.preset_slots(prefs)
    identifier = prefs.active_pie_preset
    prefs.active_pie_preset = 'GENERAL'
    assert pie.current_slots(prefs) == pie.BUILTIN_PRESETS['GENERAL']
    prefs.active_pie_preset = identifier
    assert prefs.pie_slot_8 == 'VERTEX_SEAM_TOOL'
    print('PIE_PREFERENCES_RELOADED', flush=True)
