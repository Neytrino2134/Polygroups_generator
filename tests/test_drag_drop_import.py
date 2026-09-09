"""Blender smoke test for the AI Retopo glTF drag-and-drop handler."""

from pathlib import Path
import sys
from types import SimpleNamespace

import addon_utils
import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon_utils.enable(ROOT.name, default_set=True)

from polygroups_generator.operators.batch_import import AIRETOPO_FH_gltf
from polygroups_generator.operators.batch_import import OBJECT_OT_polygroups_batch_import


handler = bpy.types.FileHandler.bl_rna_get_subclass_py("AIRETOPO_FH_gltf")
assert handler is AIRETOPO_FH_gltf
assert handler.bl_label == "Import AI Retopo Toolkit"
assert handler.bl_import_operator == "object.polygroups_batch_import"
assert handler.bl_file_extensions == ".glb;.gltf"
assert handler.poll_drop(SimpleNamespace(area=SimpleNamespace(type="VIEW_3D")))
assert not handler.poll_drop(SimpleNamespace(area=SimpleNamespace(type="TEXT_EDITOR")))

registered_operator = bpy.types.Operator.bl_rna_get_subclass_py(
    "OBJECT_OT_polygroups_batch_import"
)
assert registered_operator is OBJECT_OT_polygroups_batch_import
use_file_selection = bpy.ops.object.polygroups_batch_import.get_rna_type().properties[
    "use_file_selection"
]
assert use_file_selection.default is True
assert "filepath" in bpy.ops.object.polygroups_batch_import.get_rna_type().properties


class Properties:
    def __init__(self, filepath_is_set):
        self.filepath_is_set = filepath_is_set

    def is_property_set(self, name):
        return name == "filepath" and self.filepath_is_set


calls = []
window_manager = SimpleNamespace(
    invoke_props_dialog=lambda operator, **kwargs: calls.append(("dialog", operator, kwargs))
    or {"RUNNING_MODAL"},
    fileselect_add=lambda operator: calls.append(("files", operator)),
)
invoke_context = SimpleNamespace(window_manager=window_manager)
drop_operator = SimpleNamespace(
    use_file_selection=True,
    properties=Properties(True),
    filepath="model.glb",
    files=[SimpleNamespace(name="model.glb")],
    bl_label="Import AI Retopo Toolkit",
)
assert OBJECT_OT_polygroups_batch_import.invoke(
    drop_operator, invoke_context, None,
) == {"RUNNING_MODAL"}
assert calls[-1][0] == "dialog"

file_operator = SimpleNamespace(
    use_file_selection=True,
    properties=Properties(False),
    filepath="",
    files=[],
    bl_label="Import AI Retopo Toolkit",
)
assert OBJECT_OT_polygroups_batch_import.invoke(
    file_operator, invoke_context, None,
) == {"RUNNING_MODAL"}
assert calls[-1][0] == "files"


class Layout:
    def __init__(self):
        self.properties = []
        self.enabled = True
        self.use_property_split = False
        self.use_property_decorate = True

    def prop(self, _data, property_name, *args, **kwargs):
        self.properties.append(property_name)
        return self

    def row(self, *args, **kwargs):
        return self

    def column(self, *args, **kwargs):
        return self

    def label(self, *args, **kwargs):
        return None


layout = Layout()
OBJECT_OT_polygroups_batch_import.draw(SimpleNamespace(layout=layout), bpy.context)
for property_name in (
    "file_import_auto_rename_objects",
    "file_import_apply_weld",
    "file_import_disable_view_assist",
    "file_import_auto_remesh",
    "file_import_remesh_method",
    "file_import_remesh_preset",
    "file_import_clear_material",
    "file_import_auto_smart_uv_project",
    "file_import_separate_collections",
):
    assert property_name in layout.properties, property_name

addon_utils.disable(ROOT.name, default_set=True)
assert bpy.types.FileHandler.bl_rna_get_subclass_py("AIRETOPO_FH_gltf") is None
print("DRAG_DROP_IMPORT_OK", flush=True)
