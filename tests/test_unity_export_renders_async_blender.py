"""Launch without --background: actual FBX/GLTF and all render outputs/progress."""
import json
import sys
import tempfile
import time
from pathlib import Path
import bpy
import addon_utils

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
CANCEL='--cancel-check' in sys.argv
RESULT=Path(tempfile.gettempdir())/('polygroups_unity_export_renders_cancel_result.json' if CANCEL else 'polygroups_unity_export_renders_result.json')
OUTPUT=Path(tempfile.mkdtemp(prefix='unity_export_renders_'))
state={'progress':[],'statuses':[]}
started=time.monotonic()

def finish(error=None):
    from polygroups_generator.operators import turnaround_animation as ta
    scene=bpy.context.scene
    rs=scene.polygroups_render_settings
    source=state.pop('source',None)
    original=state.pop('original',None)
    camera=scene.camera
    folder=OUTPUT/'!Unity'/'TestAsset'
    result=dict(state)
    result.update(error=error,output=str(folder),status=rs.animation_status,final_progress=rs.animation_progress,
        lod_images=len(list((folder/'TestAsset_LODS').glob('*.webp'))),
        views=len(list((folder/'TestAsset_Turnaround').glob('*.webp'))),
        videos=len(list((folder/'TestAsset_Turnaround').glob('*.webm'))),
        fbx=len(list((folder/'FBX').glob('*.fbx'))),gltf=len(list((folder/'GLTF').glob('*.gltf'))),
        no_render_animation_folder=not list(folder.rglob('Render Animation')),
        selected_restored=bpy.context.active_object==source and set(bpy.context.selected_objects)=={source},
        settings_restored=original[:-1]==(rs.resolution_x,rs.resolution_y,rs.image_format,rs.animation_container,
                                    rs.output_directory,scene.render.use_freestyle) and
                          max(abs(original[-1][i][j]-camera.matrix_world[i][j]) for i in range(4) for j in range(4))<1e-5,
        task_cleared=ta._ACTIVE_RENDER_TASK is None,unlocked=not rs.is_running)
    result['active']=bpy.context.active_object.name if bpy.context.active_object else None
    result['selected']=[obj.name for obj in bpy.context.selected_objects]
    result['settings_before']=list(original[:-1]) if original else None
    result['settings_after']=[rs.resolution_x,rs.resolution_y,rs.image_format,rs.animation_container,rs.output_directory,scene.render.use_freestyle]
    result['camera_before']=[list(row) for row in original[-1]] if original else None
    result['camera_after']=[list(row) for row in camera.matrix_world]
    if error is None:
        try:
            assert result['fbx']==1 and result['gltf']==1
            assert all(result[key] for key in ('selected_restored','settings_restored','task_cleared','unlocked','no_render_animation_folder'))
            document=json.loads(next((folder/'GLTF').glob('*.gltf')).read_text())
            assert all(item['uri'].startswith('data:') for item in document['buffers'])
            if CANCEL:
                assert 'cancelled' in result['status'] and result['final_progress']<100
            else:
                assert result['lod_images']==4 and result['views']==4 and result['videos']==1, result
                assert result['final_progress']==100 and any(0<p<100 for p in state['progress'])
                assert (folder/'TestAsset_LODS'/'MeshInfo.json').is_file()
        except Exception as exc:
            result['error']=repr(exc)
    RESULT.write_text(json.dumps(result),encoding='utf-8')
    bpy.ops.wm.quit_blender()

def check():
    rs=bpy.context.scene.polygroups_render_settings
    state['progress'].append(rs.animation_progress)
    if not state['statuses'] or state['statuses'][-1]!=rs.animation_status:
        state['statuses'].append(rs.animation_status)
    if not rs.is_running:
        finish()
        return None
    if CANCEL and not state.get('cancel_requested'):
        from polygroups_generator.operators import turnaround_animation as ta
        if ta._ACTIVE_RENDER_TASK._frames_done >= 1:
            # Exercise the same cleanup path as Blender's render_cancel handler.
            ta._ACTIVE_RENDER_TASK._on_render_cancel(bpy.context.scene)
            state['cancel_requested']=True
    if time.monotonic()-started>120:
        finish('timeout')
        return None
    return .1

def start():
    try:
        addon_utils.enable(ROOT.name,default_set=False)
        scene=bpy.context.scene
        source=bpy.context.active_object
        source.name='TestAsset'
        source['unity_prepared']=True
        lod=source.copy()
        lod.data=source.data.copy()
        lod.name='TestAsset.LOD1'
        lod.location.x=4
        scene.collection.objects.link(lod)
        bpy.ops.object.select_all(action='DESELECT')
        source.select_set(True)
        bpy.context.view_layer.objects.active=source
        bpy.context.view_layer.update()
        state['source']=source
        settings=scene.polygroups_mesh_finalization_settings
        settings.unity_export_directory=str(OUTPUT/'!Unity')
        settings.unity_export_gltf=True
        settings.unity_export_all_renders=True
        settings.unity_render_mesh_info=True
        settings.unity_render_freestyle=False
        rs=scene.polygroups_render_settings
        rs.render_engine='EEVEE'
        rs.animation_frame_count=2
        rs.transparent_background=True
        state['original']=(rs.resolution_x,rs.resolution_y,rs.image_format,rs.animation_container,
                           rs.output_directory,scene.render.use_freestyle,scene.camera.matrix_world.copy())
        window=bpy.context.window_manager.windows[0]
        area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
        region=next(r for r in area.regions if r.type=='WINDOW')
        with bpy.context.temp_override(window=window,area=area,region=region):
            result=bpy.ops.object.polygroups_export_unity('INVOKE_DEFAULT')
        assert result=={'RUNNING_MODAL'},result
        bpy.app.timers.register(check,first_interval=.1)
    except Exception as exc:
        finish(repr(exc))
    return None

bpy.app.timers.register(start,first_interval=1)
