"""View-layer transitions, family Show/Hide, and resculpted Multires controls."""
import sys
from pathlib import Path
from unittest.mock import patch
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import phase2_processing as phase
ctx=bpy.context;p=ctx.scene.polygroups_model_preparation_settings
p.phase2_mesh_auto_repair=False
p.phase2_mid_remesh=False
def cube(name,col):
 bpy.ops.mesh.primitive_cube_add();obj=ctx.object;obj.name=name
 for old in list(obj.users_collection):old.objects.unlink(obj)
 col.objects.link(obj);return obj
collections=[]
for index in (1,2,3):
 col=bpy.data.collections.new(f'Generated.{index:03d}');ctx.scene.collection.children.link(col)
 cube(f'Retopo_12_Highpoly_Generated.{index:03d}',col);collections.append(col)
def layer(col):return next(l for l in ctx.view_layer.layer_collection.children if l.collection==col)
q=phase.Phase2Queue(ctx,[('mock',col.name) for col in collections],False,False,lambda *args:None);q.begin()
with patch.object(phase,'restore_collection',side_effect=collections):
 for i,col in enumerate(collections):
  q.step(ctx)
  assert not layer(col).exclude and not col.hide_viewport and not col.hide_render
  for previous in collections[:i]:
   assert layer(previous).exclude and not previous.hide_viewport and not previous.hide_render
 q.step(ctx)
assert q.finished and not layer(collections[-1]).exclude
# A failed next restore must not hide the last available collection.
q=phase.Phase2Queue(ctx,[('mock','first'),('mock','missing')],False,False,lambda *args:None);q.begin()
with patch.object(phase,'restore_collection',side_effect=[collections[0],ValueError('Missing next collection')]):
 q.step(ctx);q.step(ctx);q.step(ctx)
assert q.finished and not layer(collections[0]).exclude
# Stop before the next restore retains the current collection too.
q=phase.Phase2Queue(ctx,[('mock','first'),('mock','second')],False,False,lambda *args:None);q.begin()
with patch.object(phase,'restore_collection',return_value=collections[0]):q.step(ctx)
q.stop_requested=True;q.step(ctx)
assert q.finished and not layer(collections[0]).exclude
col=collections[-1]
sculpt=cube('Resculpting_01_Highpoly_Generated.003',col)
suffix=cube('Rock_Resculpting',col)
other=cube('OtherMesh',col)
for obj in (sculpt,suffix,other):obj.modifiers.new('Custom Multires','MULTIRES')
col.hide_viewport=col.hide_render=True;layer(col).exclude=True
sculpt.hide_viewport=sculpt.hide_render=True
assert bpy.ops.object.polygroups_phase2_mesh_visibility(family='RESCULPTING',show=True)=={'FINISHED'}
assert sculpt.visible_get() and suffix.visible_get() and not layer(col).exclude
assert not col.hide_viewport and not col.hide_render
assert bpy.ops.object.polygroups_phase2_mesh_visibility(family='RESCULPTING',show=False)=={'FINISHED'}
assert all(o.hide_viewport and o.hide_render and not o.hide_get() for o in (sculpt,suffix))
assert not other.hide_viewport and not other.hide_render
assert bpy.ops.object.polygroups_phase2_mesh_visibility(family='RETOPO',show=True)=={'FINISHED'}
assert all(o.visible_get() for o in ctx.scene.objects if o.name.startswith('Retopo_'))
assert bpy.ops.object.polygroups_phase2_mesh_visibility(family='RETOPO',show=False)=={'FINISHED'}
assert all(o.hide_viewport and o.hide_render and not o.hide_get() for o in ctx.scene.objects if o.name.startswith('Retopo_'))
assert bpy.ops.object.polygroups_phase2_mesh_visibility(family='RESCULPTING',show=True)=={'FINISHED'}
assert all(not o.hide_viewport and not o.hide_render and o.visible_get() for o in (sculpt,suffix))
assert bpy.ops.object.polygroups_phase2_multires_visibility(enable=False)=={'FINISHED'}
assert all(not m.show_viewport and not m.show_render for o in (sculpt,suffix) for m in o.modifiers)
assert other.modifiers[0].show_viewport and other.modifiers[0].show_render
assert bpy.ops.object.polygroups_phase2_multires_visibility(enable=True)=={'FINISHED'}
assert all(m.show_viewport and m.show_render and m.total_levels==0 for o in (sculpt,suffix) for m in o.modifiers)
from polygroups_generator.custom_ui.schema import capture
p.phase2_show_manual_cleanup=True
assert not capture(ctx,1).errors
print('PHASE2_VIEW_LAYER_TRANSITIONS_AND_MANUAL_VISIBILITY_PASSED')
