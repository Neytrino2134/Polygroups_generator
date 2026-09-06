"""Blender background regression for cutter backup creation and restore."""
import sys
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
from polygroups_generator.operators import object_seam_cutter as cutter

bpy.ops.mesh.primitive_cube_add()
target = bpy.context.active_object
target.name = "Backup Test Mesh"
original_vertex = target.data.vertices[0].co.copy()

assert bpy.ops.object.polygroups_create_cutter_backup() == {"FINISHED"}
backup = bpy.data.objects["Backup_Backup Test Mesh"]
assert backup.hide_viewport and backup.hide_render
assert backup.data is not target.data

# A second request reuses the original backup.
assert bpy.ops.object.polygroups_create_cutter_backup() == {"FINISHED"}
assert len([obj for obj in bpy.data.objects if obj.name.startswith("Backup_Backup Test Mesh")]) == 1

# Cutter snapshots accumulate across apply iterations. Reusing one cutter updates
# its snapshot instead of creating a duplicate.
bpy.ops.mesh.primitive_plane_add(size=2)
first_cutter = bpy.context.active_object
first_cutter.name = "First Saved Cutter"
first_cutter[cutter.CUTTER_PROP] = True
first_cutter[cutter.CUTTER_TYPE_PROP] = "PLANE"
cutter._remember_applied_cutters(bpy.context, target, [first_cutter])
first_cutter.location.x = 2.5
cutter._remember_applied_cutters(bpy.context, target, [first_cutter])

bpy.ops.mesh.primitive_plane_add(size=3)
second_cutter = bpy.context.active_object
second_cutter.name = "Second Saved Cutter"
second_cutter[cutter.CUTTER_PROP] = True
second_cutter[cutter.CUTTER_TYPE_PROP] = "PLANE"
cutter._remember_applied_cutters(bpy.context, target, [second_cutter])

snapshots = [
    obj for obj in bpy.data.objects
    if obj.get(cutter.CUTTER_BACKUP_SNAPSHOT_PROP)
    and obj.get(cutter.CUTTER_BACKUP_OWNER_PROP) == backup.name
]
assert len(snapshots) == 2
assert next(obj for obj in snapshots if obj.get(cutter.CUTTER_ORIGINAL_NAME_PROP) == first_cutter.name).location.x == 2.5
for saved_cutter in (first_cutter, second_cutter):
    bpy.data.objects.remove(saved_cutter, do_unlink=True)

target.select_set(True)
bpy.context.view_layer.objects.active = target

target.data.vertices[0].co.x += 5
assert bpy.ops.object.polygroups_restore_cutter_backup(
    current_action="KEEP", restore_cutters=False,
) == {"FINISHED"}
restored = bpy.context.active_object
assert restored.name == "Backup Test Mesh"
assert tuple(restored.data.vertices[0].co) == tuple(original_vertex)
assert bpy.data.objects.get("Current_Backup Test Mesh") is target
assert bpy.data.objects.get(backup.name) is backup
assert not [
    obj for obj in bpy.data.objects
    if obj.get(cutter.CUTTER_INSTANCE_ID_PROP)
    and not obj.get(cutter.CUTTER_BACKUP_SNAPSHOT_PROP)
]

# Delete-current restore replaces the active object and still preserves backup.
previous = restored
previous_name = previous.name
previous.data.vertices[0].co.y += 3
assert bpy.ops.object.polygroups_restore_cutter_backup(
    current_action="DELETE", restore_cutters=True,
) == {"FINISHED"}
restored = bpy.context.active_object
assert bpy.data.objects.get(previous_name) is restored
assert restored.name == "Backup Test Mesh"
assert tuple(restored.data.vertices[0].co) == tuple(original_vertex)
assert bpy.data.objects.get(backup.name) is backup

live_cutters = [
    obj for obj in bpy.data.objects
    if obj.get(cutter.CUTTER_INSTANCE_ID_PROP)
    and not obj.get(cutter.CUTTER_BACKUP_SNAPSHOT_PROP)
]
assert {obj.name for obj in live_cutters} == {"First Saved Cutter", "Second Saved Cutter"}
assert bpy.data.objects["First Saved Cutter"].location.x == 2.5

# Repeated restore replaces cutters with the same remembered IDs.
assert bpy.ops.object.polygroups_restore_cutter_backup(
    current_action="DELETE", restore_cutters=True,
) == {"FINISHED"}
live_cutters = [
    obj for obj in bpy.data.objects
    if obj.get(cutter.CUTTER_INSTANCE_ID_PROP)
    and not obj.get(cutter.CUTTER_BACKUP_SNAPSHOT_PROP)
]
assert len(live_cutters) == 2

addon_utils.disable(ROOT.name, default_set=True)
print("CUTTER_BACKUP_TESTS_PASSED")
