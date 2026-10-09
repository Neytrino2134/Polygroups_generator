import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import bpy, addon_utils
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators.render_queue import ensure_render_support_visible
scene=bpy.context.scene
for name,kind in [('Scene','MESH'),('Camera','CAMERA'),('Light','LIGHT')]:
    col=bpy.data.collections.new(name)
    scene.collection.children.link(col)
    data=(bpy.data.meshes.new(name) if kind=='MESH' else bpy.data.cameras.new(name) if kind=='CAMERA' else bpy.data.lights.new(name,'POINT'))
    obj=bpy.data.objects.new(name,data)
    col.objects.link(obj)
    obj.hide_render=obj.hide_viewport=True
    obj.hide_set(True)
    col.hide_render=col.hide_viewport=True
    layer=bpy.context.view_layer.layer_collection.children[col.name]
    layer.hide_viewport=True
ensure_render_support_visible(bpy.context)
for name in ('Scene','Camera','Light'):
    col=bpy.data.collections[name]
    assert not col.hide_render and not col.hide_viewport
    assert not col.objects[0].hide_get()
    assert not col.objects[0].hide_render and not col.objects[0].hide_viewport
with TemporaryDirectory() as directory:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory)/'Test.blend'))
    bpy.ops.mesh.primitive_cube_add()
    obj=bpy.context.object
    obj.name='Test_00_01'
    obj['unity_prepared']=True
    s=scene.polygroups_mesh_finalization_settings
    s.unity_export_directory=str(Path(directory)/'!Unity')
    s.unity_export_fbx=False
    s.unity_export_gltf=True
    s.unity_export_clear_asset_folder=True
    s.unity_export_autosave=True
    folder=Path(s.unity_export_directory)/obj.name
    (folder/'Old').mkdir(parents=True)
    (folder/'Old'/'stale.txt').write_text('stale')
    (folder/'stale.png').write_text('stale')
    assert bpy.ops.object.polygroups_export_unity()=={'FINISHED'}
    assert not (folder/'Old').exists() and not (folder/'stale.png').exists()
    assert (folder/'GLTF'/f'{obj.name}.gltf').is_file()
    assert Path(bpy.data.filepath).is_file()
print('UNITY_EXPORT_START_PASSED')
