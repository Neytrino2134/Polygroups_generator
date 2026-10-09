import sys,json,tempfile,time
from pathlib import Path
import bpy,addon_utils
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
OUTPUT=Path(tempfile.mkdtemp(prefix='unity_prepare_export_'))
RESULT=Path(tempfile.gettempdir())/'polygroups_prepare_export_result.json'
state={}
started=time.monotonic()
def finish(error=None):
    RESULT.write_text(json.dumps({'error':error,'output':str(OUTPUT),'status':bpy.context.scene.polygroups_render_settings.animation_status}),encoding='utf-8')
    bpy.ops.wm.quit_blender()
def check():
    rs=bpy.context.scene.polygroups_render_settings
    if rs.is_running:
        if time.monotonic()-started>150:
            finish('timeout')
            return None
        return .2
    try:
        folder=OUTPUT/'!Unity'/'Tree_13_02'
        assert len(list((folder/'FBX').glob('*.fbx')))==2
        assert len(list((folder/'GLTF').glob('*.gltf')))==1
        assert len(list((folder/'Tree_13_02_LODS').glob('*.webp')))==2
        assert len(list((folder/'Tree_13_02_Turnaround').glob('*.webp')))==4
        assert len(list((folder/'Tree_13_02_Turnaround').glob('*.webm')))==1
        assert rs.animation_progress==100
        assert not any(c.get('polygroups_turnaround_collection') for c in bpy.data.collections)
        assert state['source'] not in bpy.context.selected_objects
        finish()
    except Exception as error:
        finish(repr(error))
    return None
def start():
    try:
        addon_utils.enable(ROOT.name,default_set=False)
        bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT/'Test.blend'))
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=6)
        source=bpy.context.object
        source.name='Source'
        state['source']=source
        scene=bpy.context.scene
        s=scene.polygroups_mesh_finalization_settings
        rs=scene.polygroups_render_settings
        s.smart_lods_count=2
        s.smart_lods_target_1=80
        s.smart_lods_target_2=40
        s.unity_render_freestyle=False
        s.unity_export_directory=str(OUTPUT/'!Unity')
        rs.render_engine='EEVEE'
        rs.animation_frame_count=2
        window=bpy.context.window
        area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
        region=next(r for r in area.regions if r.type=='WINDOW')
        with bpy.context.temp_override(window=window,area=area,region=region):
            assert bpy.ops.object.polygroups_prepare_and_export_unity('EXEC_DEFAULT',asset_name='Tree',name_index='13',version_index='02')=={'FINISHED'}
        assert rs.is_running
        bpy.app.timers.register(check,first_interval=.2)
    except Exception as error:
        finish(repr(error))
    return None
bpy.app.timers.register(start,first_interval=1)
