"""Blender background regression for cutter backup creation and restore."""
import sys
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

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

target.data.vertices[0].co.x += 5
assert bpy.ops.object.polygroups_restore_cutter_backup(current_action="KEEP") == {"FINISHED"}
restored = bpy.context.active_object
assert restored.name == "Backup Test Mesh"
assert tuple(restored.data.vertices[0].co) == tuple(original_vertex)
assert bpy.data.objects.get("Current_Backup Test Mesh") is target
assert bpy.data.objects.get(backup.name) is backup

# Delete-current restore replaces the active object and still preserves backup.
previous = restored
previous_name = previous.name
previous.data.vertices[0].co.y += 3
assert bpy.ops.object.polygroups_restore_cutter_backup(current_action="DELETE") == {"FINISHED"}
restored = bpy.context.active_object
assert bpy.data.objects.get(previous_name) is restored
assert restored.name == "Backup Test Mesh"
assert tuple(restored.data.vertices[0].co) == tuple(original_vertex)
assert bpy.data.objects.get(backup.name) is backup

addon_utils.disable(ROOT.name, default_set=True)
print("CUTTER_BACKUP_TESTS_PASSED")
