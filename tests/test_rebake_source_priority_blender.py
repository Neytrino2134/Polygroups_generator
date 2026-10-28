"""Explicit source, collection-scoped priority and temporary library fallback."""
import sys, tempfile
from pathlib import Path
import bpy, addon_utils
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent));addon_utils.enable(ROOT.name,default_set=False)
from polygroups_generator.operators.rebake_final import resolve_final_source, MissingFinalSourceError
from polygroups_generator.operators.rebake_source import TemporaryRebakeSource
c=bpy.context
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)

def mesh(name,collection):
    obj=bpy.data.objects.new(name,bpy.data.meshes.new(name));collection.objects.link(obj);return obj
def collection(name):
    result=bpy.data.collections.new(name);c.scene.collection.children.link(result);return result
def only_target():
    for obj in c.selected_objects:obj.select_set(False)
    target.select_set(True);c.view_layer.objects.active=target

target=mesh('SM_Source_Test_01_01_MID',c.scene.collection)
generated=collection('Generated.001')
resculpt=mesh('Resculpting_01_Highpoly_Generated.001',generated)
high=mesh('Highpoly_Generated.001',generated)
manual=mesh('Any selected sculpt',c.scene.collection)
only_target()
assert resolve_final_source(c,target)==high
manual.select_set(True)
assert resolve_final_source(c,target)==manual
assert resolve_final_source(c,target,use_selection=False)==high
resculpt.select_set(True)
try:resolve_final_source(c,target)
except ValueError as error:assert 'one Highpoly' in str(error)
else:raise AssertionError('Multiple selected sources accepted')
only_target()
bpy.data.objects.remove(high,do_unlink=True)
assert resolve_final_source(c,target)==resculpt
outside=mesh('Highpoly_Generated.001',c.scene.collection)
assert resolve_final_source(c,target)==resculpt
duplicate=mesh('Resculpting_01_Highpoly_Generated.01',generated)
try:resolve_final_source(c,target)
except ValueError as error:assert 'ambiguous' in str(error)
else:raise AssertionError('Ambiguous local source accepted')
bpy.data.objects.remove(duplicate,do_unlink=True)
generated.objects.unlink(resculpt);c.scene.collection.objects.link(resculpt)
try:resolve_final_source(c,target)
except MissingFinalSourceError:raise AssertionError('Existing empty collection must not silently import')
except ValueError as error:assert 'no Highpoly' in str(error)
else:raise AssertionError('Source outside Generated collection accepted')
bpy.data.collections.remove(generated)
try:resolve_final_source(c,target)
except MissingFinalSourceError:pass
else:raise AssertionError('Missing collection did not request file fallback')
print('REBAKE_EXPLICIT_AND_LOCAL_SOURCE_PRIORITY_OK',flush=True)

with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);(root/'!Blend').mkdir()
    bpy.ops.wm.save_as_mainfile(filepath=str(root/'Working.blend'))
    generated=collection('Generated.1')
    # The direct Highpoly is an orphan in this first library: ignore it and
    # choose the Resculpting member, even though both names exist in the file.
    orphan=mesh('Highpoly_Generated.1',c.scene.collection)
    fallback=mesh('Resculpting_01_Highpoly_Generated.1',generated)
    file=root/'!Blend'/'Generated.1.blend'
    bpy.data.libraries.write(str(file),{generated,orphan},compress=True)
    original_objects=set(bpy.data.objects)
    session=TemporaryRebakeSource(1)
    imported=session.load(c)
    assert imported in session.collection.all_objects[:] and imported!=fallback
    assert imported.name.startswith('Resculpting_01_Highpoly_Generated')
    session.cleanup();assert set(bpy.data.objects)==original_objects
    # Both source kinds inside the collection: direct Highpoly always wins.
    c.scene.collection.objects.unlink(orphan);generated.objects.link(orphan)
    bpy.data.libraries.write(str(file),{generated},compress=True)
    session=TemporaryRebakeSource(1);imported=session.load(c)
    assert imported!=orphan and imported.name.startswith('Highpoly_Generated')
    session.cleanup();assert set(bpy.data.objects)==original_objects
    # A different numeric suffix width is accepted for collection/file/object.
    assert session.path==file
print('REBAKE_EXTERNAL_MEMBER_PRIORITY_COLLISIONS_AND_CLEANUP_OK',flush=True)
