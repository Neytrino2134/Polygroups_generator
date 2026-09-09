import bpy

from ..core.generated_index import (
    fix_object_generated_index,
    generated_collection_info,
    indexed_object_name,
    plain_generated_collection,
    temporary_generated_name,
)


def _fix_objects(objects):
    changed = 0
    skipped = 0
    for obj in objects:
        if obj.type != "MESH":
            continue
        if fix_object_generated_index(obj):
            changed += 1
        else:
            skipped += 1
    return changed, skipped


class OBJECT_OT_polygroups_fix_all_generated_indices(bpy.types.Operator):
    bl_idname = "object.polygroups_fix_all_generated_indices"
    bl_label = "Fix All Generated Indices"
    bl_description = "Match mesh object name indices to their numbered Generated.N collections"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, _context):
        entries = []
        used_targets = set()
        fallback_index = 1
        for obj in sorted(bpy.data.objects, key=lambda item: item.name.lower()):
            if obj.type != "MESH":
                continue
            collection, index = generated_collection_info(obj)
            if collection is not None:
                target_name = indexed_object_name(obj.name, index)
                entries.append((obj, target_name, False))
                used_targets.add(target_name.lower())
                continue
            if plain_generated_collection(obj) is None:
                continue
            target_name = temporary_generated_name(obj.name, fallback_index)
            while target_name.lower() in used_targets:
                fallback_index += 1
                target_name = temporary_generated_name(obj.name, fallback_index, preserve_existing=False)
            fallback_index += 1
            entries.append((obj, target_name, True))
            used_targets.add(target_name.lower())

        original_names = {obj: obj.name for obj, _target, _plain in entries}
        # Vacate every destination first. Blender object names are global, so a
        # one-pass rename can otherwise inherit an unwanted automatic suffix.
        for ordinal, (obj, _target, _plain) in enumerate(entries):
            obj.name = f"__AIRETOPO_INDEX_FIX_{ordinal:06d}__"
        for obj, target_name, _plain in entries:
            obj.name = target_name

        changed = sum(original_names[obj] != obj.name for obj, _target, _plain in entries)
        temporary = sum(plain for _obj, _target, plain in entries)
        self.report(
            {"INFO"},
            f"Fixed {changed} object name(s); kept {temporary} Generated object(s) as .Temp.N",
        )
        return {"FINISHED"}


class OBJECT_OT_polygroups_fix_selected_generated_indices(bpy.types.Operator):
    bl_idname = "object.polygroups_fix_selected_generated_indices"
    bl_label = "Fix Selected Generated Indices"
    bl_description = "Match selected mesh object name indices to their numbered Generated.N collections"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    @classmethod
    def poll(cls, context):
        return any(obj.type == "MESH" for obj in context.selected_objects)

    def execute(self, context):
        changed, skipped = _fix_objects(context.selected_objects)
        self.report({"INFO"}, f"Fixed {changed} selected object name(s); unchanged or unnumbered: {skipped}")
        return {"FINISHED"}
