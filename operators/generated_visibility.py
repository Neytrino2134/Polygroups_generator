import re

import bpy


GENERATED_COLLECTION = re.compile(r"^Generated\.(\d+)$")


def generated_paths(view_layer):
    paths = []

    def visit(layer, parents):
        path = parents + (layer,)
        match = GENERATED_COLLECTION.fullmatch(layer.collection.name)
        if match:
            paths.append((int(match.group(1)), path))
        for child in layer.children:
            visit(child, path)

    visit(view_layer.layer_collection, ())
    return [path for number, path in sorted(paths, key=lambda item: (item[0], item[1][-1].name))]


def current_generated_path(context, paths):
    obj = context.active_object
    active_layer = context.view_layer.active_layer_collection
    if obj is not None:
        candidates = [path for path in paths if path[-1].collection in obj.users_collection]
        if not candidates:
            candidates = [path for path in paths if obj.name in path[-1].collection.all_objects]
        if candidates:
            return next((path for path in candidates if active_layer == path[-1]),
                        max(candidates, key=len))
        return None
    return next((path for path in paths if path[-1] == active_layer), None)


def controls_available(context):
    return (context.mode == "OBJECT"
            and not context.scene.polygroups_model_preparation_settings.batch_is_running
            and not context.scene.polygroups_remesh_status.is_running)


class OBJECT_OT_polygroups_object_visibility(bpy.types.Operator):
    bl_idname = "object.polygroups_object_visibility"
    bl_label = "Highpoly / Retopo Visibility"
    bl_description = "Enable or disable matching scene objects in all viewports using the monitor toggle"
    bl_options = {"REGISTER", "UNDO"}

    prefix: bpy.props.EnumProperty(items=(
        ("Highpoly_", "Highpoly", "Objects starting with Highpoly_"),
        ("Retopo_", "Retopo", "Objects starting with Retopo_"),
    ))
    hidden: bpy.props.BoolProperty(default=True)

    @classmethod
    def poll(cls, context):
        return controls_available(context)

    def execute(self, context):
        objects = [obj for obj in context.scene.objects if obj.name.startswith(self.prefix)]
        for obj in objects:
            obj.hide_viewport = self.hidden
        self.report({"INFO"}, f"{'Disabled' if self.hidden else 'Enabled'} in viewport: {len(objects)} object(s)")
        return {"FINISHED"}


class OBJECT_OT_polygroups_generated_collection(bpy.types.Operator):
    bl_idname = "object.polygroups_generated_collection"
    bl_label = "Generated Collection"
    bl_description = "Isolate or switch numbered Generated collections using View Layer checkboxes"
    bl_options = {"REGISTER", "UNDO"}

    action: bpy.props.EnumProperty(items=(
        ("ISOLATE", "Isolate Other Collections", "Exclude other Generated.N collections"),
        ("PREVIOUS", "Previous Collection", "Disable this collection and enable the previous number"),
        ("NEXT", "Next Collection", "Disable this collection and enable the next number"),
    ))

    @classmethod
    def poll(cls, context):
        return controls_available(context) and current_generated_path(context, generated_paths(context.view_layer)) is not None

    def execute(self, context):
        paths = generated_paths(context.view_layer)
        current = current_generated_path(context, paths)
        if current is None:
            self.report({"WARNING"}, "Select an object in a Generated.N collection")
            return {"CANCELLED"}
        target = current
        source = context.active_object
        preferred_prefix = "Highpoly_" if source and source.name.startswith("Highpoly_") else "Retopo_"
        if self.action != "ISOLATE":
            index = paths.index(current) + (1 if self.action == "NEXT" else -1)
            if not 0 <= index < len(paths):
                self.report({"INFO"}, "No next collection" if self.action == "NEXT" else "No previous collection")
                return {"CANCELLED"}
            target = paths[index]
            if current[-1] not in target:
                current[-1].exclude = True
        else:
            for path in paths:
                if path[-1] not in target:
                    path[-1].exclude = True

        # Include the target's ancestors too, so nested Generated collections work.
        for layer in target[1:]:
            layer.exclude = False
        context.view_layer.update()
        context.view_layer.active_layer_collection = target[-1]
        if self.action != "ISOLATE":
            for obj in context.selected_objects:
                obj.select_set(False)
            context.view_layer.objects.active = None
            candidates = [obj for obj in target[-1].collection.all_objects
                          if obj.name in context.view_layer.objects
                          and obj.visible_get(view_layer=context.view_layer)
                          and not obj.hide_select]
            candidates.sort(key=lambda obj: (
                not obj.name.startswith(preferred_prefix),
                not obj.name.startswith(("Retopo_", "Highpoly_")), obj.name,
            ))
            if candidates:
                candidates[0].select_set(True)
                context.view_layer.objects.active = candidates[0]
        self.report({"INFO"}, target[-1].collection.name)
        return {"FINISHED"}
