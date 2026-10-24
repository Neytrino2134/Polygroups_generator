"""Setup Resculpting resolves hidden same-collection sources like Autobake."""
import sys
from pathlib import Path
from unittest.mock import patch
import bpy, addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import resculpting as sculpt
ctx=bpy.context
for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
def mesh(name,col):
 bpy.ops.mesh.primitive_cube_add();obj=ctx.object;obj.name=name
 for old in list(obj.users_collection):old.objects.unlink(obj)
 col.objects.link(obj);return obj
col=bpy.data.collections.new('Generated.001');ctx.scene.collection.children.link(col)
other=bpy.data.collections.new('Generated.002');ctx.scene.collection.children.link(other)
high=mesh('Highpoly_Generated.001',col)
low=mesh('Retopo_02_Highpoly_Generated.001',col)
wrong=mesh('Highpoly_Generated.002',other)
s=ctx.scene.polygroups_resculpting_settings;s.multires_levels=1
high.hide_viewport=high.hide_render=high.hide_select=True;high.hide_set(True)
bpy.ops.object.select_all(action='DESELECT');low.select_set(True);wrong.select_set(True)
ctx.view_layer.objects.active=low
real=sculpt.add_multires_modifier
def inspect(context,obj,levels):
 assert obj==low and context.active_object==low
 assert high.select_get() and not high.hide_viewport and not high.hide_render and not high.hide_get()
 return real(context,obj,levels)
with patch.object(sculpt,'add_multires_modifier',inspect):
 assert bpy.ops.object.polygroups_setup_resculpting()=={'FINISHED'}
assert low.modifiers[sculpt.SHRINKWRAP_MODIFIER_NAME].target==high
assert low.modifiers[sculpt.MULTIRES_MODIFIER_NAME].total_levels==1
assert high.hide_viewport and high.hide_render and high.hide_get() and high.hide_select
assert not high.select_get() and ctx.active_object==low and low.select_get()
assert bpy.ops.object.polygroups_setup_resculpting()=={'FINISHED'}
assert len(low.modifiers)==2
# A namesake outside the matching collection cannot be used as the source.
other.objects.link(high);col.objects.unlink(high)
assert bpy.ops.object.polygroups_setup_resculpting()=={'CANCELLED'}
assert high.hide_viewport and high.hide_render
col.objects.link(high);other.objects.unlink(high)
# Failures also leave the source hidden and the Retopo mesh active.
try:
 with patch.object(sculpt,'add_multires_modifier',side_effect=RuntimeError('Injected failure')):
  bpy.ops.object.polygroups_setup_resculpting()
except RuntimeError:pass
else:raise AssertionError('Expected setup failure')
assert high.hide_viewport and high.hide_render and high.hide_get()
assert ctx.active_object==low and low.select_get()
print('RESCULPT_AUTO_HIGHPOLY_SELECTION_AND_VISIBILITY_PASSED')
