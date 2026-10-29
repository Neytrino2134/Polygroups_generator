"""Shared widest-asset origin columns across differently sized source packs."""
import sys,math
from pathlib import Path
import addon_utils,bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent));addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.core.smart_arrange import SmartArrangeGrid,arrange_scene_lods
from polygroups_generator.operators.smart_lods import LOD_SOURCE,LOD_INDEX
from polygroups_generator.operators.import_queue import ImportQueue
from polygroups_generator.operators.relod import ReLODPlan
from polygroups_generator.custom_ui.schema import capture
from polygroups_generator import ui
c=bpy.context;s=c.scene.polygroups_mesh_finalization_settings;p=c.scene.polygroups_model_preparation_settings
assert s.smart_lods_smart_arrange and s.smart_decimate_smart_arrange
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
s.smart_lods_count=2;s.smart_lods_target_1=20;s.smart_lods_target_2=8;s.smart_lods_create_text=True;s.smart_lods_prepare_mode='UNREAL'

def cube(name,size,offset,location):
 bpy.ops.mesh.primitive_cube_add(size=size,location=location)
 obj=c.object;obj.name=name
 for v in obj.data.vertices:v.co.x+=offset
 return obj
sources=[cube('SM_Narrow_01_01_MID',1,5,(7,4,2)),cube('SM_Wide_01_01_MID',4,-3,(-6,-5,3))]
sources[1].rotation_euler.z=.2;sources[1].scale=(1.5,.7,1)
# Modifiers must affect the frozen width, not just the original mesh dimensions.
array=sources[0].modifiers.new('Width','ARRAY');array.count=2;array.relative_offset_displace=(3,0,0)
c.view_layer.update()
coords={obj:tuple(tuple(v.co) for v in obj.data.vertices) for obj in sources}
plan=SmartArrangeGrid(c,sources,s.smart_lods_spacing)
for obj in c.selected_objects:obj.select_set(False)
for obj in sources:obj.select_set(True)
c.view_layer.objects.active=sources[0]
assert bpy.ops.object.polygroups_generate_smart_lods()=={'FINISHED'}
for row,src in enumerate(sources):
 assert tuple(tuple(v.co) for v in src.data.vertices)==coords[src]
 assert abs(src.matrix_world.translation.x-plan.origin.x)<1e-5
 for index in range(2):
  lod=bpy.data.objects[src.name[:-4]+'_LOD'+str(index)]
  expected=plan.origin.x+(index+1)*plan.x_step
  assert abs(lod.matrix_world.translation.x-expected)<1e-5,(lod.name,lod.location.x,expected)
  assert abs(lod.matrix_world.translation.y-(plan.origin.y+row*plan.y_step))<1e-5
  assert lod.children and lod.children[0].parent==lod
# Off-centre envelopes keep adjacent columns separated, including transformed widest source.
for src in sources:
 pack=[src]+sorted((o for o in c.scene.objects if o.get(LOD_SOURCE)==src.name and o.type=='MESH'),key=lambda o:o[LOD_INDEX])
 for a,b in zip(pack,pack[1:]):
  right=max((a.matrix_world@Vector(v)).x for v in a.evaluated_get(c.evaluated_depsgraph_get()).bound_box)
  left=min((b.matrix_world@Vector(v)).x for v in b.bound_box)
  assert left>=right+.0999,(a.name,b.name,right,left)
# Sequential ReLOD receives a scene-wide grid, not a separate width for each source.
p.phase2_relod_delete_current_lods=True
assert bpy.ops.object.polygroups_relod()=={'FINISHED'}
for index in range(2):
 xs=[bpy.data.objects[src.name[:-4]+'_LOD'+str(index)].matrix_world.translation.x for src in sources]
 assert abs(xs[0]-xs[1])<1e-5,xs
# ReBake keeps an arranged row: grid X only, the MID's own Y.
keep=SmartArrangeGrid(c,sources,s.smart_lods_spacing,keep_rows=True)
probe=bpy.data.objects[sources[1].name[:-4]+'_LOD0']
sources[1].location.y+=3.7;c.view_layer.update()
keep.place(probe,sources[1],1)
assert abs(probe.matrix_world.translation.y-sources[1].matrix_world.translation.y)<1e-5
assert abs(probe.matrix_world.translation.x-(keep.origin.x+keep.x_step))<1e-5
sources[1].location.y-=3.7;keep.place(probe,sources[1],1);c.view_layer.update()
# Phase 1 group translations must not destroy the shared columns.
for obj in c.scene.objects:
 if obj.type=='MESH' and obj.get(LOD_SOURCE)==sources[1].name:obj.location.x+=99
arrange_scene_lods(c,s.smart_lods_spacing)
for index in range(2):
 xs=[bpy.data.objects[src.name[:-4]+'_LOD'+str(index)].matrix_world.translation.x for src in sources]
 assert abs(xs[0]-xs[1])<1e-5
# Decimate copies share a single column sized from both differently sized originals.
s.smart_decimate_duplicate_and_apply=True
copies=[]
for src in sources:
 for o in c.selected_objects:o.select_set(False)
 src.select_set(True);c.view_layer.objects.active=src
 assert bpy.ops.object.polygroups_uv_preserve_decimate(duplicate=True,triangle_limit=20)=={'FINISHED'}
 copies.append(c.object)
assert abs(copies[0].matrix_world.translation.x-copies[1].matrix_world.translation.x)<1e-5
# Switch off: duplicate keeps the original location.
s.smart_decimate_smart_arrange=False
src=sources[0];c.view_layer.objects.active=src
assert bpy.ops.object.polygroups_uv_preserve_decimate(duplicate=True,triangle_limit=20)=={'FINISHED'}
assert (c.object.matrix_world.translation-src.matrix_world.translation).length<1e-5
s.smart_decimate_smart_arrange=True
c.view_layer.objects.active=sources[0]
assert bpy.ops.object.polygroups_uv_preserve_decimate(duplicate=True,triangle_limit=20)=={'FINISHED'}
assert c.object.matrix_world.translation.x>copies[0].matrix_world.translation.x
assert abs(copies[0].matrix_world.translation.x-copies[1].matrix_world.translation.x)<1e-5
model=capture(c,ui.SECTION_PANEL_CLASSES.index(ui.VIEW3D_PT_polygroups_mesh_finalization))
assert not model.errors,model.errors
props={b[2] for b in model.bindings.values() if b[0]=='property'}
assert {'smart_decimate_smart_arrange','smart_lods_smart_arrange'}<=props
# Real Phase 1 finalization, followed by its file-group layout, must reflow old packs.
phase_sources=[]
for number,width in ((101,.6),(102,7)):
 src=cube(f'Retopo_12_Highpoly_Generated.{number:03d}',width,0,(number,0,0))
 col=bpy.data.collections.new(f'Generated.{number:03d}');c.scene.collection.children.link(col)
 for owner in list(src.users_collection):owner.objects.unlink(src)
 col.objects.link(src);phase_sources.append(src)
p.batch_smart_lods_enabled=True;p.batch_smart_lods_count=2
p.batch_smart_lods_target_1=20;p.batch_smart_lods_target_2=8
q=ImportQueue.__new__(ImportQueue);q.scene=c.scene;q.view_layer=c.view_layer;q.settings=p
q.stage='SMART_LODS';q.tracked=lambda action:action();q.file_objects=[];q.result_meshes=[];q.file_record={};q.collection=None
for src in phase_sources:q.finalize_mesh(c,src)
def lods(src):
 return sorted((obj for obj in c.scene.objects if obj.type=='MESH' and obj.get(LOD_SOURCE)==src.name),key=lambda obj:obj[LOD_INDEX])
def aligned():
 for index in range(2):
  xs=[lods(src)[index].matrix_world.translation.x for src in phase_sources]
  assert abs(xs[0]-xs[1])<1e-5,xs
aligned()
q.groups=[(src,[src]+lods(src)+[child for lod in lods(src) for child in lod.children]) for src in phase_sources]
q.arrange_options=(.1,'GRID',2,'XY','ORIGIN',1)
q.arrange_groups();aligned()
# Phase 2 Batch Finalization uses the same widest-source plan for all sources.
for src in phase_sources:
 for lod in lods(src):
  for child in list(lod.children):bpy.data.objects.remove(child,do_unlink=True)
  bpy.data.objects.remove(lod,do_unlink=True)
import tempfile
with tempfile.TemporaryDirectory() as directory:
 bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory)/'SmartArrange.blend'))
 p.phase2_final_lods=True;p.phase2_final_rename=False
 assert bpy.ops.object.polygroups_batch_finalization(asset='Grid',name_index='01',version_index='01')=={'FINISHED'}
 aligned()
print('SMART_ARRANGE_SHARED_COLUMNS_MODIFIERS_PHASE1_PHASE2_AND_RELOD_OK',flush=True)
