"""Blender regression: legacy contour sketches support Apply and Mirror."""
import sys
from pathlib import Path
import addon_utils
import bpy
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)
bpy.context.preferences.addons[ROOT.name].preferences.play_sound_after_operations = False
from polygroups_generator.operators import object_seam_cutter as c
settings = bpy.context.scene.polygroups_object_seam_cutter_settings
settings.cutter_auto_fix_mesh = False
settings.hide_cutters_after_apply = False
settings.delete_cutters_after_apply = False
for method in ("BOOLEAN", "KNIFE"):
    for name, in_collection in (("Local_Contour_Sketch", False), ("Local_Contour_Sketch.001", True), ("Legacy contour", True)):
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        target = bpy.context.object
        bpy.ops.mesh.primitive_plane_add(size=4)
        sketch = bpy.context.object
        sketch.name = name
        if in_collection:
            collection = bpy.data.collections.get("Seam Cutters Local Contour")
            if collection is None:
                collection = bpy.data.collections.new("Seam Cutters Local Contour")
                bpy.context.scene.collection.children.link(collection)
            for owner in list(sketch.users_collection):
                owner.objects.unlink(sketch)
            collection.objects.link(sketch)
            assert sketch in c._cutter_collection_objects()
        target.select_set(True)
        bpy.context.view_layer.objects.active = target
        assert c._selected_cutters_only(bpy.context) == [sketch]
        assert not c._is_target_mesh_candidate(sketch)
        settings.cutter_apply_method = method
        assert bpy.ops.object.polygroups_copy_mirror_cutters() == {"FINISHED"}
        mirror = bpy.data.objects[sketch.name + "_Mirror"]
        assert mirror[c.CUTTER_TYPE_PROP] == "LOCAL_CONTOUR"
        mirror.select_set(False)
        assert bpy.ops.object.polygroups_apply_cutter_seams() == {"FINISHED"}
        assert sum(edge.use_seam for edge in target.data.edges) >= 4, (method, name)
        assert sketch[c.CUTTER_TYPE_PROP] == "LOCAL_CONTOUR"
print("LOCAL_CONTOUR_CUTTER_APPLY_OK", flush=True)
