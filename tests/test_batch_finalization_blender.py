"""Real Phase 2 Batch Finalization: FAB/Unity, defaults, naming and stop rollback."""
import sys,tempfile
from pathlib import Path
from types import SimpleNamespace
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False
addon_utils.enable(ROOT.name,default_set=True)
from polygroups_generator.operators import sequential_jobs as jobs
from polygroups_generator.operators.smart_lods import OBJECT_OT_polygroups_generate_smart_lods as Smart, LOD_SOURCE
from polygroups_generator.operators.batch_finalization import layer_tree
s=bpy.context.scene.polygroups_mesh_finalization_settings
p=bpy.context.scene.polygroups_model_preparation_settings
assert p.phase2_final_lod_engine=='UNREAL' and p.phase2_final_rename_engine=='FAB'
assert s.unreal_lod_keep_high and s.unreal_lod_high_suffix=='_MID'
assert set(s.bl_rna.properties['unreal_lod_high_suffix'].enum_items.keys())=={'_HIGH','_MID'}
s.smart_lods_count=2;s.smart_lods_target_1=80;s.smart_lods_target_2=40
s.unreal_lod_copy_textures=False;s.unity_copy_textures=False
s.unity_generate_text_labels=False

def fixture():
 for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
 for col in list(bpy.data.collections):bpy.data.collections.remove(col)
 sources=[]
 for index in (1,2):
  col=bpy.data.collections.new(f'Generated.{index:03d}');bpy.context.scene.collection.children.link(col)
  bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8)
  obj=bpy.context.object;obj.name=f'Retopo_12_Highpoly_Generated.{index:03d}'
  for previous in list(obj.users_collection):previous.objects.unlink(obj)
  col.objects.link(obj);col.hide_viewport=col.hide_render=True;sources.append(obj)
 bpy.context.view_layer.update()
 for layer in bpy.context.view_layer.layer_collection.children:layer.exclude=True
 return sources

with tempfile.TemporaryDirectory(dir=ROOT,prefix='test_batch_final_') as directory:
 bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory)/'Working.blend'))
 for engine,rename in (('UNREAL','FAB'),('UNITY','FAB'),('UNITY','UNITY'),('UNREAL','UNITY')):
  sources=fixture();p.phase2_final_lod_engine=engine;p.phase2_final_rename_engine=rename
  s.unreal_lod_random_collection_color = engine != 'UNREAL'
  s.unreal_lod_collection_color = 'COLOR_04'
  assert bpy.ops.object.polygroups_batch_finalization(asset='desert stones',name_index='07',version_index='03')=={'FINISHED'}
  assert s.smart_lods_progress==100 and p.phase2_final_progress==100
  assert not s.smart_lods_is_running and not p.phase2_final_is_running and jobs.ACTIVE_JOB is None
  for index in (3,4):
   if rename=='FAB':
    base=f'SM_Desert_Stones_07_{index:02d}'
    assert all(base+suffix in bpy.data.objects for suffix in ('_MID','_LOD0','_LOD1'))
    col=bpy.data.collections[f'Desert_Stones_07_{index:02d}_Collection']
    assert col.color_tag!='NONE'
    if not s.unreal_lod_random_collection_color:assert col.color_tag=='COLOR_04'
   else:
    base=f'Desert_Stones_07_{index:02d}'
    assert base in bpy.data.objects and base+'.LOD1' in bpy.data.objects
  assert all(col.hide_viewport for col in bpy.data.collections if col.name.startswith('Generated.'))
 # Generation and renaming can each be used independently.
 for generate,rename in ((True,False),(False,True)):
  sources=fixture();p.phase2_final_lods=generate;p.phase2_final_rename=rename
  p.phase2_final_lod_engine='UNREAL';p.phase2_final_rename_engine='FAB'
  assert bpy.ops.object.polygroups_batch_finalization(asset='dry rocks',name_index='02',version_index='01')=={'FINISHED'}
  if generate:
   assert all(source.name+'_LOD0' in bpy.data.objects for source in sources)
  else:
   assert all(f'SM_Dry_Rocks_02_{index:02d}_MID' in bpy.data.objects for index in (1,2))
 p.phase2_final_lods=p.phase2_final_rename=True
 # Generator cancellation deletes only the incomplete pack, preserves sources.
 sources=fixture()
 for layer in layer_tree(bpy.context.view_layer.layer_collection):
  layer.exclude=False;layer.collection.hide_viewport=False
 bpy.context.view_layer.update()
 for source in sources:source.select_set(True)
 bpy.context.view_layer.objects.active=sources[0]
 class Worker:
  active_only=False
  report=lambda *a:None
  source_steps=Smart.source_steps
  batch_steps=Smart.batch_steps
 worker=Worker();iterator=worker.batch_steps(bpy.context)
 fraction,message=next(iterator);assert 'Arrange' in message
 fraction,message=next(iterator);assert 'LOD0' in message and 0<fraction<1
 iterator.close()
 assert all(source.name in bpy.data.objects for source in sources)
 assert not any(obj.get(LOD_SOURCE) for obj in bpy.data.objects)
 from polygroups_generator.custom_ui.schema import capture
 for section in (1,12):
  model=capture(bpy.context,section)
  assert not model.errors,model.errors
print('BATCH_FINALIZATION_PIPELINES_PASSED')
