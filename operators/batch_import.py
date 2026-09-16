import os
import re
import time
from math import ceil

import bpy
from bpy_extras.io_utils import ImportHelper
from bpy_extras.io_utils import poll_file_object_drop
from mathutils import Vector

from ..core.generated_index import indexed_object_name



FORMAT_EXTENSIONS = {
    "USD": {".usd", ".usda", ".usdc"},
    "FBX": {".fbx"},
    "OBJ": {".obj"},
    "STL": {".stl"},
    "GLB": {".glb", ".gltf"},
    "3MF": {".3mf"},
    "BLEND": {".blend"},
}

AUTO_EXTENSIONS = set().union(*(
    extensions for format_name, extensions in FORMAT_EXTENSIONS.items()
    if format_name != "BLEND"
))
SUPPORTED_FILTER_GLOB = "*.usd;*.usda;*.usdc;*.fbx;*.obj;*.stl;*.glb;*.gltf;*.3mf"

IMPORT_OPERATOR_CANDIDATES = {
    ".usd": (("wm", "usd_import"),),
    ".usda": (("wm", "usd_import"),),
    ".usdc": (("wm", "usd_import"),),
    ".fbx": (("import_scene", "fbx"),),
    ".obj": (("wm", "obj_import"), ("import_scene", "obj")),
    ".stl": (("wm", "stl_import"), ("import_mesh", "stl")),
    ".glb": (("import_scene", "gltf"),),
    ".gltf": (("import_scene", "gltf"),),
    ".3mf": (
        ("wm", "import_3mf"),
        ("wm", "threemf_import"),
        ("import_mesh", "threemf"),
    ),
}


def find_import_operator(extension):
    for module_name, operator_name in IMPORT_OPERATOR_CANDIDATES.get(extension, ()):
        module = getattr(bpy.ops, module_name, None)
        if module is None:
            continue

        try:
            operator = getattr(module, operator_name)
        except AttributeError:
            continue

        return operator

    return None


def collect_import_files(directory, import_format, include_subfolders=False):
    if import_format == "AUTO":
        extensions = AUTO_EXTENSIONS
    else:
        extensions = FORMAT_EXTENSIONS[import_format]

    files = []
    if include_subfolders:
        filepaths = (
            os.path.join(root, filename)
            for root, _subdirectories, filenames in os.walk(directory)
            for filename in filenames
        )
    else:
        filepaths = (
            os.path.join(directory, filename)
            for filename in os.listdir(directory)
        )

    for filepath in filepaths:
        if not os.path.isfile(filepath):
            continue

        extension = os.path.splitext(filepath)[1].lower()
        if extension in extensions:
            files.append(filepath)

    files.sort(key=lambda path: os.path.relpath(path, directory).lower())
    return files


def collect_selected_import_files(directory, selected_files, import_format):
    if import_format == "AUTO":
        extensions = AUTO_EXTENSIONS
    else:
        extensions = FORMAT_EXTENSIONS[import_format]

    files = []
    for selected_file in selected_files:
        filepath = os.path.join(directory, selected_file.name)
        extension = os.path.splitext(filepath)[1].lower()
        if os.path.isfile(filepath) and extension in extensions:
            files.append(filepath)

    files.sort(key=lambda path: os.path.basename(path).lower())
    return files


def object_world_bounds(obj):
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_corner = Vector((
        min(corner.x for corner in corners),
        min(corner.y for corner in corners),
        min(corner.z for corner in corners),
    ))
    max_corner = Vector((
        max(corner.x for corner in corners),
        max(corner.y for corner in corners),
        max(corner.z for corner in corners),
    ))
    return min_corner, max_corner


def arrange_objects_zx(objects, spacing=0.1, mode="LINE", rows=1):
    arranged_objects = [obj for obj in objects if obj and obj.type == "MESH"]
    if not arranged_objects:
        return 0

    arranged_objects.sort(key=lambda obj: obj.name.lower())
    rows = max(1, int(rows))
    if mode == "LINE":
        rows = 1
    else:
        rows = min(rows, len(arranged_objects))

    columns = max(1, ceil(len(arranged_objects) / rows))
    spacing = max(0.0, spacing)
    bounds = [object_world_bounds(obj) for obj in arranged_objects]
    sizes = [
        (
            max_corner.x - min_corner.x,
            max_corner.z - min_corner.z,
        )
        for min_corner, max_corner in bounds
    ]
    column_widths = [0.0] * columns
    row_heights = [0.0] * rows

    for index, (width, height) in enumerate(sizes):
        row = index // columns
        column = index % columns
        column_widths[column] = max(column_widths[column], width)
        row_heights[row] = max(row_heights[row], height)

    x_positions = [bounds[0][0].x]
    for column in range(1, columns):
        previous_width = column_widths[column - 1]
        x_positions.append(x_positions[-1] + previous_width + spacing)

    z_positions = [bounds[0][0].z]
    for row in range(1, rows):
        previous_height = row_heights[row - 1]
        z_positions.append(z_positions[-1] + previous_height + spacing)

    for index, obj in enumerate(arranged_objects):
        row = index // columns
        column = index % columns
        min_corner, _max_corner = object_world_bounds(obj)
        obj.location.x += x_positions[column] - min_corner.x
        obj.location.z += z_positions[row] - min_corner.z

    return len(arranged_objects)


class OBJECT_OT_polygroups_select_import_folder(bpy.types.Operator):
    bl_idname = "object.polygroups_select_import_folder"
    bl_label = "Select Folder"
    bl_description = "Select a folder for batch import"
    bl_options = {"REGISTER"}

    directory: bpy.props.StringProperty(
        subtype="DIR_PATH",
        options={"HIDDEN"},
    )
    filepath: bpy.props.StringProperty(
        subtype="DIR_PATH",
        options={"HIDDEN"},
    )
    filter_folder: bpy.props.BoolProperty(
        default=True,
        options={"HIDDEN"},
    )

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def invoke(self, context, event):
        settings = context.scene.polygroups_model_preparation_settings
        self.directory = bpy.path.abspath(settings.batch_import_directory)
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        settings = context.scene.polygroups_model_preparation_settings
        directory = self.directory or os.path.dirname(self.filepath)

        if not directory or not os.path.isdir(bpy.path.abspath(directory)):
            self.report({"WARNING"}, "Select a valid folder")
            return {"CANCELLED"}

        settings.batch_import_directory = directory
        return {"FINISHED"}


class OBJECT_OT_polygroups_scan_import_folder(bpy.types.Operator):
    bl_idname = "object.polygroups_scan_import_folder"
    bl_label = "Scan Folder"
    bl_description = "Count supported mesh files in the selected import folder"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and not context.scene.polygroups_model_preparation_settings.batch_is_running

    def execute(self, context):
        settings = context.scene.polygroups_model_preparation_settings
        directory = bpy.path.abspath(settings.batch_import_directory)

        if not directory or not os.path.isdir(directory):
            self.report({"WARNING"}, "Select a valid import folder")
            return {"CANCELLED"}

        files = collect_import_files(
            directory,
            settings.batch_import_format,
            include_subfolders=settings.batch_include_subfolders,
        )
        if settings.batch_import_format == "BLEND" and bpy.data.filepath:
            current_file = os.path.normcase(os.path.abspath(bpy.data.filepath))
            files = [
                filepath for filepath in files
                if os.path.normcase(os.path.abspath(filepath)) != current_file
            ]
        settings.batch_total_count = len(files)
        settings.batch_imported_count = 0
        settings.batch_failed_count = 0
        settings.batch_last_error = ""
        settings.batch_stage = "QUEUED"
        settings.batch_imported_object_count = 0
        settings.batch_remaining_count = len(files)
        settings.batch_import_progress = 0.0
        settings.batch_current_progress = 0.0
        settings.batch_elapsed_seconds = 0.0
        settings.batch_current_seconds = 0.0
        settings.batch_average_seconds = 0.0
        settings.batch_eta_seconds = -1.0
        settings.batch_current_file = "Scan complete"

        self.report({"INFO"}, f"Found {len(files)} supported file(s)")
        return {"FINISHED"}


GENERATED_COLLECTION_PATTERN = re.compile(r"^Generated(?:\.(\d+))?$", re.IGNORECASE)


def _next_generated_collection_index():
    indices = []
    for collection in bpy.data.collections:
        match = GENERATED_COLLECTION_PATTERN.fullmatch(collection.name)
        if match is not None and match.group(1) is not None:
            indices.append(int(match.group(1)))
    return max(indices, default=0) + 1


def _source_generated_collection_names(filepath):
    with bpy.data.libraries.load(filepath, link=False) as (source, _target):
        names = [
            name for name in source.collections
            if GENERATED_COLLECTION_PATTERN.fullmatch(name)
        ]
    return sorted(
        names,
        key=lambda name: (
            GENERATED_COLLECTION_PATTERN.fullmatch(name).group(1) is not None,
            int(GENERATED_COLLECTION_PATTERN.fullmatch(name).group(1) or 0),
            name.lower(),
        ),
    )


def _remove_appended_objects(objects):
    data_blocks = {getattr(obj, "data", None) for obj in objects}
    data_blocks.discard(None)
    for obj in objects:
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    orphaned = {data for data in data_blocks if data.users == 0}
    if orphaned:
        bpy.data.batch_remove(ids=orphaned)


def _discard_appended_collection(collection):
    collections = []
    pending = [collection]
    while pending:
        current = pending.pop()
        if current in collections:
            continue
        collections.append(current)
        pending.extend(current.children)
    _remove_appended_objects(set(collection.all_objects))
    for current in reversed(collections):
        if current.name in bpy.data.collections:
            bpy.data.collections.remove(current, do_unlink=True)


def append_generated_collections(filepath, scene, start_index, include_highpoly=False):
    """Append matching collections and return (next index, collections, meshes)."""
    source_names = _source_generated_collection_names(filepath)
    if not source_names:
        return start_index, [], []
    with bpy.data.libraries.load(filepath, link=False) as (_source, target):
        target.collections = source_names

    appended_collections = []
    appended_meshes = []
    index = start_index
    for collection in target.collections:
        if collection is None:
            continue
        objects = list(collection.all_objects)
        has_retopo = any(obj.name.lower().startswith("retopo_") for obj in objects)
        has_included_highpoly = include_highpoly and any(
            obj.name.lower().startswith("highpoly_") for obj in objects
        )
        if not has_retopo and not has_included_highpoly:
            _discard_appended_collection(collection)
            continue
        collection.name = f"Generated.{index:03d}"
        scene.collection.children.link(collection)
        for obj in objects:
            if not include_highpoly and obj.name.lower().startswith("highpoly_"):
                _remove_appended_objects((obj,))
                continue
            # A direct Generated.N membership makes Auto Fix Index deterministic,
            # including for objects originally stored in nested child collections.
            if obj.name not in collection.objects:
                collection.objects.link(obj)
            if obj.type == "MESH":
                appended_meshes.append((obj, f"{index:03d}"))
        appended_collections.append(collection)
        index += 1
    return index, appended_collections, appended_meshes


def _fix_appended_generated_indices(entries):
    targets = [(obj, indexed_object_name(obj.name, index)) for obj, index in entries]
    for ordinal, (obj, _target_name) in enumerate(targets):
        obj.name = f"__AIRETOPO_BLEND_APPEND_{ordinal:06d}__"
    for obj, target_name in targets:
        obj.name = target_name


class OBJECT_OT_polygroups_append_generated_blends(bpy.types.Operator):
    bl_idname = "object.polygroups_append_generated_blends"
    bl_label = "Append Generated Collections"
    bl_description = "Append Generated and Generated.N collections from every scanned blend file"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, "polygroups_model_preparation_settings", None)
        return bool(settings and settings.batch_import_format == "BLEND" and not settings.batch_is_running)

    def execute(self, context):
        settings = context.scene.polygroups_model_preparation_settings
        directory = bpy.path.abspath(settings.batch_import_directory)
        if not directory or not os.path.isdir(directory):
            self.report({"WARNING"}, "Select a valid import folder")
            return {"CANCELLED"}
        files = collect_import_files(directory, "BLEND", settings.batch_include_subfolders)
        current_file = os.path.normcase(os.path.abspath(bpy.data.filepath)) if bpy.data.filepath else ""
        files = [
            filepath for filepath in files
            if os.path.normcase(os.path.abspath(filepath)) != current_file
        ]
        if not files:
            self.report({"WARNING"}, "No external blend files found")
            return {"CANCELLED"}

        next_index = _next_generated_collection_index()
        imported_collections = []
        imported_meshes = []
        matched_files = 0
        failed = []
        for filepath in files:
            try:
                next_index, collections, meshes = append_generated_collections(
                    filepath,
                    context.scene,
                    next_index,
                    settings.batch_append_include_highpoly,
                )
            except Exception as error:
                failed.append(f"{os.path.basename(filepath)}: {error}")
                continue
            imported_collections.extend(collections)
            imported_meshes.extend(meshes)
            if collections:
                matched_files += 1

        _fix_appended_generated_indices(imported_meshes)
        settings.batch_imported_count = len(imported_collections)
        settings.batch_imported_object_count = len(imported_meshes)
        settings.batch_failed_count = len(failed)
        settings.batch_remaining_count = 0
        settings.batch_import_progress = 1.0 if imported_collections else 0.0
        settings.batch_current_progress = settings.batch_import_progress
        settings.batch_stage = "DONE" if imported_collections else "ERROR"
        settings.batch_current_file = "Blend append complete"
        settings.batch_last_error = "\n".join(failed)
        if not imported_collections:
            self.report({"WARNING"}, "No Generated or Generated.N collections were found")
            return {"CANCELLED"}
        message = f"Appended {len(imported_collections)} Generated collection(s) from {matched_files} file(s)"
        if failed:
            message += f"; {len(failed)} file(s) failed"
        self.report({"WARNING"} if failed else {"INFO"}, message)
        return {"FINISHED"}


class OBJECT_OT_polygroups_batch_import(bpy.types.Operator, ImportHelper):
    bl_idname = "object.polygroups_batch_import"
    bl_label = "Import AI Retopo Toolkit"
    bl_description = "Import mesh files from a folder one by one"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    use_file_selection: bpy.props.BoolProperty(
        # N-panel buttons set this explicitly. FileHandler drag-and-drop uses
        # the default and supplies directory/files directly.
        default=True,
        options={"HIDDEN", "SKIP_SAVE"},
    )
    redo_collection_name: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    directory: bpy.props.StringProperty(
        subtype="DIR_PATH",
        options={"HIDDEN"},
    )
    files: bpy.props.CollectionProperty(
        type=bpy.types.OperatorFileListElement,
        options={"HIDDEN"},
    )
    filter_glob: bpy.props.StringProperty(
        default=SUPPORTED_FILTER_GLOB,
        options={"HIDDEN"},
    )

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def draw(self, context):
        from ..localization import t
        from ..ui import draw_import_remesh_options

        layout = self.layout
        settings = context.scene.polygroups_model_preparation_settings
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(settings, "file_import_automatic_processing",
                    text=t(context, "import_automatic_processing"))
        if settings.file_import_automatic_processing:
            layout.label(text=t(context, "import_automatic_uses_batch_settings"), icon="MODIFIER")
        else:
            layout.label(text=t(context, "import_simple_processing"), icon="MODIFIER")
            layout.prop(settings, "file_import_auto_rename_objects",
                        text=t(context, "auto_rename_objects"))
            layout.prop(settings, "file_import_apply_weld", text=t(context, "apply_weld"))
            layout.prop(settings, "file_import_disable_view_assist",
                        text=t(context, "disable_view_assist"))
            draw_import_remesh_options(layout, context, settings, "file_import")

    def execute(self, context):
        from . import import_queue
        from .remesh_progress import ACTIVE_REMESH

        settings = context.scene.polygroups_model_preparation_settings
        if settings.batch_import_format == "BLEND":
            self.report({"WARNING"}, "Use Append Generated Collections for Blend format")
            return {"CANCELLED"}
        if import_queue.ACTIVE_QUEUE is not None or ACTIVE_REMESH is not None:
            self.report({"WARNING"}, "An import queue or Remesh is already running")
            return {"CANCELLED"}
        redo_collection_name = getattr(self, "redo_collection_name", "")
        file_selection = self.use_file_selection and not redo_collection_name
        try:
            redo_collection = None
            if redo_collection_name:
                redo_collection = bpy.data.collections.get(redo_collection_name)
                if import_queue.redo_source(redo_collection) is None:
                    raise RuntimeError("Choose a Generated.N collection with its original highpoly")
                files = [redo_collection.name]
            else:
                directory = bpy.path.abspath(self.directory if file_selection else settings.batch_import_directory)
                if not directory or not os.path.isdir(directory):
                    raise RuntimeError("Select a valid import folder")
                files = (collect_selected_import_files(directory, self.files, settings.batch_import_format)
                         if file_selection else collect_import_files(
                             directory, settings.batch_import_format, settings.batch_include_subfolders))
            if not files:
                raise RuntimeError("No supported mesh files found")
            if redo_collection is not None:
                self._queue = import_queue.ImportQueue(
                    context, files, False, self.report, redo_collection=redo_collection,
                )
            elif file_selection and settings.file_import_automatic_processing:
                self._queue = import_queue.ImportQueue(
                    context, files, True, self.report, automatic_processing=True,
                )
            else:
                self._queue = import_queue.ImportQueue(context, files, file_selection, self.report)
        except Exception as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self._queue.begin()
        import_queue.ACTIVE_QUEUE = self._queue
        self._timer = context.window_manager.event_timer_add(0.2, window=context.window)
        self._queue.timer = self._timer
        self._next_tick = time.monotonic() + 0.2
        context.window_manager.modal_handler_add(self)
        import_queue.redraw(context)
        return {"RUNNING_MODAL"}

    def invoke(self, context, event):
        from ..core.remesh_cursor import update_remesh_cursor
        update_remesh_cursor(context, event)
        if self.use_file_selection and not self.redo_collection_name:
            return ImportHelper.invoke_popup(self, context)
        return self.execute(context)

    def modal(self, context, event):
        from ..core.remesh_cursor import update_remesh_cursor
        update_remesh_cursor(context, event)
        from . import import_queue

        if self._queue.finished:
            self._finish(context)
            return {"FINISHED"}
        if event.type == "ESC":
            if self._queue.settings.batch_stage == "PAUSED":
                return {"RUNNING_MODAL"}
            self._queue.settings.batch_cancel_requested = True
        elif event.type != "TIMER":
            return {"PASS_THROUGH"}
        else:
            # Blender's Event exposes no timer handle. Other modal tools may
            # emit TIMER events too, so limit queue steps using elapsed time.
            now = time.monotonic()
            if now < self._next_tick:
                return {"PASS_THROUGH"}
            self._next_tick = now + 0.2
        try:
            with context.temp_override(scene=self._queue.scene, view_layer=self._queue.view_layer):
                self._queue.step(context)
        except Exception as error:
            self.report({"ERROR"}, str(error))
            self._queue.finish(context, "STOPPED")
        import_queue.redraw(context)
        if self._queue.finished:
            self._finish(context)
            # Keep an undo entry for completed work, including a stopped queue.
            return {"FINISHED"}
        return {"PASS_THROUGH"}

    def _finish(self, context):
        from . import import_queue

        if self._timer is not None and self._queue.timer is not None:
            context.window_manager.event_timer_remove(self._timer)
        self._timer = None
        self._queue.timer = None
        import_queue.ACTIVE_QUEUE = None

    def cancel(self, context):
        if getattr(self, "_queue", None) is not None:
            self._queue.finish(context, "CANCELLED", rollback=True)
        self._finish(context)


class AIRETOPO_FH_gltf(bpy.types.FileHandler):
    bl_idname = "AIRETOPO_FH_gltf"
    bl_label = "Import AI Retopo Toolkit"
    bl_import_operator = OBJECT_OT_polygroups_batch_import.bl_idname
    bl_file_extensions = ".glb;.gltf"

    @classmethod
    def poll_drop(cls, context):
        return poll_file_object_drop(context)


class OBJECT_OT_polygroups_arrange_batch_objects(bpy.types.Operator):
    bl_idname = "object.polygroups_arrange_batch_objects"
    bl_label = "Arrange Objects"
    bl_description = "Arrange selected mesh objects in a line or rows on the ZX plane"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(obj.type == "MESH" for obj in context.selected_objects)

    def execute(self, context):
        settings = context.scene.polygroups_model_preparation_settings
        selected_mesh_objects = [
            obj for obj in context.selected_objects if obj.type == "MESH"
        ]
        arranged_count = arrange_objects_zx(
            selected_mesh_objects,
            settings.batch_arrange_spacing,
            settings.batch_arrange_mode,
            settings.batch_arrange_rows,
        )

        self.report({"INFO"}, f"Arranged {arranged_count} object(s)")
        return {"FINISHED"}
