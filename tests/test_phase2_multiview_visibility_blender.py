"""Three visible disconnected multiview silhouettes, Hero, and transparent companions."""
import sys,tempfile
from pathlib import Path
from unittest.mock import patch
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
bpy.context.preferences.use_preferences_save=False;addon_utils.enable(ROOT.name,default_set=True)
from polygroups_generator.operators import auto_render as auto,render_queue as rq
from polygroups_generator.operators.render_selected import selected_bounds
context=bpy.context;scene=context.scene;p=scene.polygroups_model_preparation_settings;s=scene.polygroups_render_settings
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
col=bpy.data.collections.new('Scene_Stones_01_01_Collection');scene.collection.children.link(col)
bpy.ops.mesh.primitive_cube_add(location=(0,0,1));source=context.object
source.name='SM_Scene_Stones_01_01_MID';source.scale=(2,3,1)
for old in list(source.users_collection):old.objects.unlink(source)
col.objects.link(source);context.view_layer.update()
p.phase2_auto_transparent=True;p.phase2_auto_scene_prefix='Scene'
p.phase2_auto_freestyle=False;p.phase2_auto_textures=False
s.max_samples=1;s.skip_existing=False
real_config=auto.configure_auto_render;real_render=rq._render_current_job;real_spread=auto.spread_multiview
seen=[];old_overlap=[]
def bounds(obj):
 points,_,_=selected_bounds(context,[obj]);return min(v.x for v in points),max(v.x for v in points)
def spread(ctx,views):
 f,l,r=map(bounds,views)
 old_overlap.append(l[1]>f[0] and r[0]<f[1])
 real_spread(ctx,views)
 f,l,r=map(bounds,views)
 assert l[1]<f[0] and r[0]>f[1]
def config(ctx):real_config(ctx);s.resolution_scale=25
def render(ctx,settings,job):
 views=[obj for obj in scene.objects if obj.get(rq.MULTIVIEW_PROP) and not obj.hide_render]
 assert len(views)==(3 if job['view_mode']=='Multiview' else 1),(job['view_mode'],[o.name for o in views])
 assert all(not obj.hide_viewport and obj.visible_get() for obj in views)
 points,_,_=selected_bounds(ctx,views)
 assert s.studio_distance-s.studio_radius>max(v.y for v in points)-s.studio_scene_position.location.y
 seen.append(job['view_mode']);real_render(ctx,settings,job)

def components(path):
 image=bpy.data.images.load(str(path));w,h=image.size;pixels=list(image.pixels[:]);bpy.data.images.remove(image)
 mask={i for i in range(w*h) if pixels[4*i+3]>.5};areas=[]
 while mask:
  seed=mask.pop();stack=[seed];area=0
  while stack:
   at=stack.pop();area+=1;x,y=at%w,at//w
   for other in ((at-1 if x else -1),(at+1 if x+1<w else -1),(at-w if y else -1),(at+w if y+1<h else -1)):
    if other in mask:mask.remove(other);stack.append(other)
  if area>30:areas.append(area)
 assert pixels[3]==0 and max(pixels[3::4])>.9
 return areas
with tempfile.TemporaryDirectory(dir=ROOT,prefix='test_mv_visible_') as directory:
 root=Path(directory);bpy.ops.wm.save_as_mainfile(filepath=str(root/'Working.blend'));s.output_directory=str(root/'Renders')
 with patch.object(auto,'configure_auto_render',config),patch.object(auto,'spread_multiview',spread),patch.object(rq,'_render_current_job',render):
  assert bpy.ops.object.polygroups_phase2_auto_render()=={'FINISHED'}
 assert all(old_overlap) and seen==['Multiview','Hero']
 files=list((root/'Renders').rglob('*.png'));assert len(files)==4,files
 multi=next(path for path in files if 'Multiview' in path.name and '_transparent' in path.name)
 hero=next(path for path in files if 'Hero' in path.name and '_transparent' in path.name)
 assert len(components(multi))==3,components(multi)
 assert len(components(hero))==1,components(hero)
 assert s.transparent_background and s.scene_collection_prefix=='Scene'
print('PHASE2_MULTIVIEW_THREE_SILHOUETTES_AND_TRANSPARENT_PASSED')
