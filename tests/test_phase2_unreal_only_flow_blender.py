"""Unreal-only Phase 2 (no ZBrush): Generated.N goes to its own !Blend file and is deleted afterwards,
and the temporary !Unreal/FBX/Textures paths never stay on the source images."""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
bpy.context.preferences.use_preferences_save = False
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.operators import phase2_pipeline_stages as stages
from polygroups_generator.operators import phase2_start_dialog as dialog

ctx = bpy.context
p = ctx.scene.polygroups_model_preparation_settings
dialog.apply_start_preset(p, 'UNREAL')
assert not p.phase2_run_zbrush and p.phase2_run_blend and p.phase2_blend_export_generated and p.phase2_blend_delete_generated
keys = [entry[0] for entry in stages.selected_stages(p)]
assert 'BLEND' in keys and 'ZBRUSH' not in keys and 'CLEANUP' not in keys, keys

for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj)
for col in list(bpy.data.collections):
    bpy.data.collections.remove(col)
root = Path(tempfile.mkdtemp())
(root / 'Textures' / 'Stone_01_01').mkdir(parents=True)
bpy.ops.wm.save_as_mainfile(filepath=str(root / 'Proj.blend'))


def mesh(name, col):
    data = bpy.data.meshes.new(name)
    data.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new(name, data)
    col.objects.link(obj)
    return obj


asset = bpy.data.collections.new('Stone_01_01_Collection')
ctx.scene.collection.children.link(asset)
generated = bpy.data.collections.new('Generated.001')
ctx.scene.collection.children.link(generated)
mid = mesh('SM_Stone_01_01_MID', asset)
mesh('Retopo_01', generated)
image = bpy.data.images.new('T_Stone_01_01_BaseColor', 8, 8)
image.file_format = 'PNG'
texture = root / 'Textures' / 'Stone_01_01' / 'T_Stone_01_01_BaseColor.png'
image.save(filepath=str(texture))
image.filepath_raw = bpy.path.relpath(str(texture))
image.source = 'FILE'
material = bpy.data.materials.new('M_Stone_01_01')
material.use_nodes = True
node = material.node_tree.nodes.new('ShaderNodeTexImage')
node.image = image
material.node_tree.links.new(node.outputs['Color'], material.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
mid.data.materials.append(material)
source_path = image.filepath

p.phase2_export_fbx, p.phase2_export_glb, p.phase2_export_gltf = True, False, False
p.phase2_export_engine = 'FAB'
run = SimpleNamespace(settings=p, plan=[(key, key, None, None) for key in keys],
                      override=lambda settings, name, value: setattr(settings, name, value))
list(stages.export_prepared(run, ctx))
assert image.filepath == source_path, image.filepath       # FBX export only borrowed the paths
assert (root / '!Unreal' / 'FBX' / 'Textures' / 'T_Stone_01_01_BaseColor.png').is_file()
list(stages.export_blend(run, ctx))
assert image.filepath == source_path, image.filepath
assert (root / '!Blend' / 'Generated.001.blend').is_file() and (root / '!Blend' / 'Stone_01_01.blend').is_file()
assert 'Generated.001' not in bpy.data.collections and 'Retopo_01' not in bpy.data.objects
assert 'Stone_01_01_Collection' in bpy.data.collections
print('phase2 unreal only flow ok')
