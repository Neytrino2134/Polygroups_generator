import bpy
import re


def collection_is_in_tree(parent_collection, target_collection):
    for child_collection in parent_collection.children:
        if child_collection == target_collection:
            return True
        if collection_is_in_tree(child_collection, target_collection):
            return True
    return False


def layer_collection_paths(layer_collection, target_collection, path=None):
    if path is None:
        path = ()

    current_path = path + (layer_collection,)
    if layer_collection.collection == target_collection:
        yield current_path

    for child_layer_collection in layer_collection.children:
        yield from layer_collection_paths(
            child_layer_collection,
            target_collection,
            current_path,
        )


def ensure_collection_visible_in_view_layer(context, collection):
    if collection is None:
        return False

    collection.hide_viewport = False
    context.view_layer.update()

    paths = list(layer_collection_paths(context.view_layer.layer_collection, collection))
    if not paths:
        return False

    for path in paths:
        for layer_collection in path[1:]:
            layer_collection.exclude = False
            layer_collection.hide_viewport = False

    context.view_layer.update()
    return True


def get_or_create_generated_collection(context, collection_name):
    generated_collection = bpy.data.collections.get(collection_name)
    if generated_collection is None:
        generated_collection = bpy.data.collections.new(collection_name)

    if not collection_is_in_tree(context.scene.collection, generated_collection):
        context.scene.collection.children.link(generated_collection)

    ensure_collection_visible_in_view_layer(context, generated_collection)
    return generated_collection


def rename_and_move_objects(
    context,
    objects,
    collection_name="Generated",
    object_prefix="Highpoly_Generated",
    start_index=None,
):
    selected_objects = list(objects)
    generated_collection = get_or_create_generated_collection(context, collection_name)
    if start_index is None:
        start_index = get_next_object_index(object_prefix)

    for index, obj in enumerate(selected_objects, start=start_index):
        obj.name = f"__polygroups_rename_temp_{index:03d}"

    for index, obj in enumerate(selected_objects, start=start_index):
        obj.name = f"{object_prefix}.{index:03d}"

        for collection in list(obj.users_collection):
            collection.objects.unlink(obj)

        generated_collection.objects.link(obj)

    return len(selected_objects)


def get_next_object_index(object_prefix="Highpoly_Generated"):
    patterns = (
        re.compile(rf"^{re.escape(object_prefix)}\.(\d+)$"),
        re.compile(rf"^{re.escape(object_prefix)}_(\d+)(?:\.\d+)?$"),
    )
    max_index = 0

    for obj in bpy.data.objects:
        for pattern in patterns:
            match = pattern.match(obj.name)
            if match:
                max_index = max(max_index, int(match.group(1)))
                break

    return max_index + 1


class OBJECT_OT_polygroups_rename_objects(bpy.types.Operator):
    bl_idname = "object.polygroups_rename_objects"
    bl_label = "Rename Objects"
    bl_description = "Rename selected objects and move them to the Generated collection"
    bl_options = {"REGISTER", "UNDO"}

    collection_name = "Generated"
    object_prefix = "Highpoly_Generated"

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        selected_objects = list(context.selected_objects)
        renamed_count = rename_and_move_objects(
            context,
            selected_objects,
            self.collection_name,
            self.object_prefix,
        )

        self.report(
            {"INFO"},
            f"Renamed and moved {renamed_count} object(s) to {self.collection_name}",
        )
        return {"FINISHED"}
