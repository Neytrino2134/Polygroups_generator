"""Actual scene+alpha vs alpha-only renders, skip-existing and UI defaults."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import addon_utils
import bpy

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import auto_render as auto,render_queue as rq
from polygroups_generator.custom_ui.schema import capture

context=bpy.context;scene=context.scene
p=scene.polygroups_model_preparation_settings;s=scene.polygroups_render_settings
assert p.phase2_auto_transparent and not p.phase2_auto_skip_scene
p.phase2_auto_multiview=False;p.phase2_auto_freestyle=False;p.phase2_auto_textures=False
for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
collection=bpy.data.collections.new('Transparent_00_01_Collection');scene.collection.children.link(collection)
bpy.ops.mesh.primitive_cube_add(location=(0,0,1))
obj=context.object;obj.name='SM_Transparent_00_01_MID'
for old in list(obj.users_collection):old.objects.unlink(obj)
collection.objects.link(obj)
real_config=auto.configure_auto_render


def small(ctx):
    real_config(ctx)
    s.resolution_x=s.resolution_y=64;s.resolution_scale=100
    s.render_engine='CYCLES';s.max_samples=1
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=1


def alpha(path):
    image=bpy.data.images.load(str(path),check_existing=False)
    values=list(image.pixels[:])[3::4]
    bpy.data.images.remove(image)
    return min(values),max(values)


with tempfile.TemporaryDirectory(dir=ROOT,prefix='test_transparent_only_') as directory:
    root=Path(directory);bpy.ops.wm.save_as_mainfile(filepath=str(root/'Working.blend'))
    s.skip_existing=False;s.overwrite_existing=True;s.output_directory=str(root/'Both')
    with patch.object(auto,'configure_auto_render',small):
        assert bpy.ops.object.polygroups_phase2_auto_render()=={'FINISHED'}
    files=list((root/'Both').rglob('*.png'));assert len(files)==2,files
    transparent=next(path for path in files if '_transparent' in path.name)
    opaque=next(path for path in files if path!=transparent)
    assert alpha(transparent)[0]<.01 and alpha(transparent)[1]>.99
    assert alpha(opaque)[0]>.99
    p.phase2_auto_scene=False
    p.phase2_auto_skip_scene=True
    assert p.phase2_auto_transparent and p.phase2_run_transparent
    # Runtime also handles saved/inconsistent flags without a scene pass.
    p.phase2_auto_transparent=False
    s.output_directory=str(root/'Only')
    with patch.object(auto,'configure_auto_render',small):
        assert bpy.ops.object.polygroups_phase2_auto_render()=={'FINISHED'}
    files=list((root/'Only').rglob('*.png'));assert len(files)==1,files
    assert '_transparent' in files[0].name and alpha(files[0])[0]<.01 and alpha(files[0])[1]>.99
    assert s.last_output_path==str(files[0])
    jobs=rq._load_queue(s);assert len(jobs)==1 and jobs[0]['skip_scene_render']
    assert rq.job_output_paths(s,jobs[0])==[str(files[0])]
    # No opaque counterpart exists, and it must not be required for skipping.
    s.skip_existing=True;s.overwrite_existing=False
    with patch.object(auto,'configure_auto_render',small),patch.object(auto,'render_asset_job') as render:
        assert bpy.ops.object.polygroups_phase2_auto_render()=={'FINISHED'}
        assert not render.called
    s.freestyle_edges=s.freestyle_as_render_pass=True
    outputs=rq.job_output_paths(s,jobs[0])
    assert len(outputs)==3 and all('_transparent' in Path(path).name for path in outputs)
    assert rq.job_output_paths(s,{**jobs[0],'texture_kind':'Combined'})==[jobs[0]['output_path']]
    # The Start Phase 2 coordinator uses the same transparent-only backend.
    for name in ('restore','prepare','export','blend','zbrush','cleanup'):
        setattr(p,'phase2_run_'+name,False)
    p.phase2_run_render=True;p.phase2_run_transparent=False
    s.output_directory=str(root/'PipelineOnly');s.skip_existing=False;s.overwrite_existing=True
    with patch.object(auto,'configure_auto_render',small):
        assert bpy.ops.object.polygroups_start_phase2()=={'FINISHED'}
    pipeline_files=list((root/'PipelineOnly').rglob('*.png'))
    assert len(pipeline_files)==1 and '_transparent' in pipeline_files[0].name
    assert alpha(pipeline_files[0])[0]<.01
    assert p.phase2_pipeline_state=='COMPLETED'
    assert not scene.render.film_transparent and not s.is_running
    panel=capture(context,1);assert not panel.errors,panel.errors
    assert any(binding[0]=='property' and binding[2]=='phase2_auto_skip_scene' for binding in panel.bindings.values())
print('AUTO_RENDER_TRANSPARENT_DEFAULT_ONLY_ALPHA_AND_SKIP_OK',flush=True)
