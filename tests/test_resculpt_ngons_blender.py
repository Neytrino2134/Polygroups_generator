"""Setup Resculpting triangulates n-gons before Multires; ZBrush rejects old bases."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=False)
from polygroups_generator.core.mesh_ngons import ngon_count
from polygroups_generator.operators import resculpting, phase2_zbrush_export

context = bpy.context
collection = bpy.data.collections.new('Generated.901')
context.scene.collection.children.link(collection)


def polygon_mesh(name):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (2, .5, 0), (2, 1.5, 0),
                      (1, 2, 0), (0, 1.5, 0), (-1, .5, 0),
                      (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
                     [], [(0, 1, 2, 3, 4, 5, 6), (7, 8, 9, 10)])
    uv = mesh.uv_layers.new(name='UVMap')
    for polygon in mesh.polygons:
        for index in polygon.loop_indices:
            vertex = mesh.vertices[mesh.loops[index].vertex_index]
            uv.data[index].uv = (vertex.co.x, vertex.co.y)
    return mesh


high_mesh = polygon_mesh('High')
high = bpy.data.objects.new('Highpoly_Generated.901', high_mesh)
collection.objects.link(high)
source_mesh = polygon_mesh('Shared low')
low = bpy.data.objects.new('Retopo_01_Highpoly_Generated.901', source_mesh)
other = bpy.data.objects.new('Unrelated shared mesh', source_mesh)
collection.objects.link(low)
collection.objects.link(other)
context.view_layer.objects.active = low
low.select_set(True)
settings = context.scene.polygroups_resculpting_settings
settings.multires_levels = 1
settings.apply_shrinkwrap = False
assert ngon_count(low.data) == 1

real_add_multires = resculpting.add_multires_modifier


def checked_multires(ctx, obj, levels):
    assert obj == low and ngon_count(obj.data) == 0
    assert ngon_count(other.data) == 1 and obj.data != other.data
    assert sorted(len(face.vertices) for face in obj.data.polygons) == [3, 3, 3, 3, 3, 4]
    assert obj.data.uv_layers.active is not None
    return real_add_multires(ctx, obj, levels)


with patch.object(resculpting, 'add_multires_modifier', checked_multires):
    assert bpy.ops.object.polygroups_setup_resculpting() == {'FINISHED'}
assert low.name == 'Resculpting_01_Highpoly_Generated.901'
assert low.modifiers[resculpting.MULTIRES_MODIFIER_NAME].total_levels == 1
assert ngon_count(low.data) == 0 and ngon_count(other.data) == 1

# Legacy Multires bases are repaired on per-level export copies.
legacy = bpy.data.objects.new('Resculpting_01_Highpoly_Generated.902', polygon_mesh('Legacy'))
legacy_groups = legacy.data.attributes.new('.sculpt_face_set', 'INT', 'FACE')
legacy_groups.data.foreach_set('value', [7, 9])
context.scene.collection.objects.link(legacy)
modifier = legacy.modifiers.new('PolyGroups Multires', 'MULTIRES')
context.view_layer.objects.active = legacy
legacy.select_set(True)
bpy.ops.object.multires_subdivide(modifier=modifier.name, mode='CATMULL_CLARK')
modifier.levels = 1
with tempfile.TemporaryDirectory(dir=ROOT, prefix='test_resculpt_ngons_') as directory:
    root = Path(directory)
    actual_export = phase2_zbrush_export._export_obj
    exported_levels = []

    def checked_export(ctx, exported_obj, filepath):
        assert ngon_count(exported_obj.data) == 0
        assert exported_obj.modifiers.get('PolyGroups Multires') is not None
        exported_levels.append(exported_obj.modifiers['PolyGroups Multires'].levels)
        return actual_export(ctx, exported_obj, filepath)

    with patch.object(phase2_zbrush_export, '_export_obj', checked_export):
        record = phase2_zbrush_export.export_object_levels(context, legacy, 'Generated.902', root)
    assert len(record['levels']) == 2
    assert record['polygroups'] == 2
    assert exported_levels == [0, 1]
    for level in record['levels']:
        exported = root / level['obj']
        faces = [line.split() for line in exported.read_text(encoding='utf-8').splitlines()
                 if line.startswith('f ')]
        assert len(faces) == level['faces']
        assert max(len(face) - 1 for face in faces) <= 4
    assert record['levels'][0]['faces'] == 6
assert ngon_count(legacy.data) == 1
assert modifier.total_levels == 1 and modifier.levels == 1
print('RESCULPT_NGONS_BEFORE_MULTIRES_AND_ZBRUSH_EXPORT_OK', flush=True)
