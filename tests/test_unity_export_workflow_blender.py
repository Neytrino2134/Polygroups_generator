import sys, json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, Mock
from types import SimpleNamespace
import bpy, addon_utils
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators import unity_export_workflow as workflow
assert not bpy.ops.object.polygroups_prepare_and_export_unity.get_rna_type().properties['skip_lods'].default
dialog = SimpleNamespace(layout=Mock())
workflow.OBJECT_OT_polygroups_prepare_and_export_unity.draw(dialog, bpy.context)
dialog.layout.prop.assert_any_call(dialog, 'skip_lods')
scene=bpy.context.scene
s=scene.polygroups_mesh_finalization_settings
rs=scene.polygroups_render_settings
from polygroups_generator import ui
from polygroups_generator.custom_ui.schema import capture
export_section = ui.SECTION_PANEL_CLASSES.index(ui.VIEW3D_PT_polygroups_mesh_finalization)
assert not s.unity_skip_lods
for enabled in (False, True):
    s.unity_skip_lods = enabled
    model = capture(bpy.context, export_section)
    assert not model.errors, model.errors
    bindings = list(model.bindings.values())
    export_index = next(i for i, b in enumerate(bindings)
                        if b[0] == 'operator' and b[1] == 'object.polygroups_export_unity')
    skip_index = next(i for i, b in enumerate(bindings)
                      if b[0] == 'property' and b[2] == 'unity_skip_lods')
    prepare_index = next(i for i, b in enumerate(bindings)
                         if b[0] == 'operator' and b[1] == 'object.polygroups_prepare_and_export_unity')
    assert export_index < skip_index < prepare_index
    assert bindings[prepare_index][2].skip_lods == enabled
s.unity_skip_lods = False
assert s.unity_export_clear_asset_folder and s.unity_export_autosave
assert s.unity_export_gltf and s.unity_export_all_renders
assert s.unity_gltf_mode == 'COMBINED'
color=tuple(rs.freestyle_line_color)
assert abs(color[1] - ((122/255+0.055)/1.055)**2.4) < 1e-6
with TemporaryDirectory() as directory:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory)/'Test.blend'))
    preset=Path(directory)/'global_presets.json'
    with patch.object(workflow,'preset_path',return_value=preset):
        assert bpy.ops.object.polygroups_save_unity_export_preset(name='Orange') == {'FINISHED'}
        other=bpy.data.scenes.new('Other')
        bpy.context.window.scene=other
        other.polygroups_mesh_finalization_settings.unity_export_gltf=False
        other.polygroups_render_settings.freestyle_line_color=(0,0,1,1)
        assert bpy.ops.object.polygroups_load_unity_export_preset(preset='Orange') == {'FINISHED'}
        assert other.polygroups_mesh_finalization_settings.unity_export_gltf
        assert tuple(other.polygroups_render_settings.freestyle_line_color) == color
        bpy.context.window.scene=scene
    s.unity_export_all_renders=False
    s.unity_export_fbx=False
    s.unity_auto_increment_index=False
    s.unity_export_directory=str(Path(directory)/'!Unity')
    s.smart_lods_count=2
    s.smart_lods_target_1=80
    s.smart_lods_target_2=40
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=6)
    source=bpy.context.object
    source.name='Source'
    assert bpy.ops.object.polygroups_prepare_and_export_unity(asset_name='Tree',name_index='13',version_index='02') == {'FINISHED'}
    assert source not in bpy.context.selected_objects and source.name == 'Source'
    assert {o.name for o in bpy.context.selected_objects} == {'Tree_13_02','Tree_13_02.LOD1'}
    output=Path(directory)/'!Unity'/'Tree_13_02'/'GLTF'/'Tree_13_02.gltf'
    data=json.loads(output.read_text())
    assert len(data['meshes']) == 2
    assert '2 LODs' in s.unity_export_status
    selected = set(bpy.context.selected_objects)
    existing = set(bpy.data.objects)
    geometry = {obj: (len(obj.data.vertices), len(obj.data.polygons)) for obj in selected}
    with patch.object(bpy.ops.object, 'polygroups_smart_lods_prepare',
                      side_effect=AssertionError('Skip LODs generated geometry')):
        assert bpy.ops.object.polygroups_prepare_and_export_unity(
            asset_name='Existing', name_index='14', version_index='03', skip_lods=True,
        ) == {'FINISHED'}
    assert set(bpy.data.objects) == existing
    assert set(bpy.context.selected_objects) == selected
    assert {obj.name for obj in selected} == {'Existing_14_03', 'Existing_14_03.LOD1'}
    assert all((len(obj.data.vertices), len(obj.data.polygons)) == geometry[obj] for obj in selected)
    output = Path(directory)/'!Unity'/'Existing_14_03'/'GLTF'/'Existing_14_03.gltf'
    assert len(json.loads(output.read_text())['meshes']) == 2
    assert bpy.ops.object.polygroups_prepare_and_export_unity(
        asset_name='Existing', name_index='14', version_index='03', skip_lods=True,
    ) == {'FINISHED'}
print('UNITY_EXPORT_WORKFLOW_PASSED')
