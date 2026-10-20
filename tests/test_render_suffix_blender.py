"""Mesh selection group and selected-only HIGH/MID/LOW suffix replacement."""
from pathlib import Path
import sys
import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.custom_ui.schema import capture, walk
from polygroups_generator import ui
from polygroups_generator.properties import SECTION_SUBSECTION_PROPERTIES

s = bpy.context.scene.polygroups_render_settings
assert 'topic_render_11' in SECTION_SUBSECTION_PROPERTIES['show_render_section']
result = capture(bpy.context, ui.SECTION_PANEL_CLASSES.index(ui.VIEW3D_PT_polygroups_render))
assert not result.errors, result.errors
groups = [n for n in walk(result.node) if n['kind'] == 'group']
assert any(n['id'].endswith('.topic_render_11') for n in groups)
assert len([b for b in result.bindings.values() if b[0] == 'property' and b[2] == 'render_low']) == 1
bpy.ops.object.select_all(action='DESELECT')
objects = []
for name in ('A_HIGH', 'B_mid', 'C_LOW.001', 'D_LOD0', 'E', 'Unselected_LOW'):
    obj = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    bpy.context.scene.collection.objects.link(obj)
    obj.select_set(name != 'Unselected_LOW')
    objects.append(obj)
s.render_rename_suffix = 'MID'
assert bpy.ops.object.polygroups_render_rename_suffix() == {'FINISHED'}
assert [obj.name for obj in objects] == ['A_MID', 'B_MID', 'C_MID.001', 'D_LOD0', 'E', 'Unselected_LOW']
s.render_rename_suffix = 'LOW'
blocker = bpy.data.objects.new('A_LOW', None)
bpy.context.scene.collection.objects.link(blocker)
before = [obj.name for obj in objects]
assert bpy.ops.object.polygroups_render_rename_suffix() == {'CANCELLED'}
assert [obj.name for obj in objects] == before
bpy.data.objects.remove(blocker, do_unlink=True)
assert bpy.ops.object.polygroups_render_rename_suffix() == {'FINISHED'}
assert [obj.name for obj in objects][:3] == ['A_LOW', 'B_LOW', 'C_LOW.001']
s.render_rename_suffix = 'HIGH'
assert bpy.ops.object.polygroups_render_rename_suffix() == {'FINISHED'}
assert [obj.name for obj in objects][:3] == ['A_HIGH', 'B_HIGH', 'C_HIGH.001']
print('RENDER_SUFFIX_PASSED')
