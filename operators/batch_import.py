import os
import time
from math import ceil

import bpy
from mathutils import Vector



FORMAT_EXTENSIONS = {
    "USD": {".usd", ".usda", ".usdc"},
    "FBX": {".fbx"},
    "OBJ": {".obj"},
    "STL": {".stl"},
    "GLB": {".glb", ".gltf"},
    "3MF": {".3mf"},
}

AUTO_EXTENSIONS = set().union(*FORMAT_EXTENSIONS.values())
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


class OBJECT_OT_polygroups_batch_import(bpy.types.Operator):
    bl_idname = "object.polygroups_batch_import"
    bl_label = "Batch Import"
    bl_description = "Import mesh files from a folder one by one"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    use_file_selection: bpy.props.BoolProperty(
        default=False,
        options={"HIDDEN", "SKIP_SAVE"},
    )
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

    def execute(self, context):
        from . import import_queue

        settings = context.scene.polygroups_model_preparation_settings
        if import_queue.ACTIVE_QUEUE is not None:
            self.report({"WARNING"}, "An import queue is already running")
            return {"CANCELLED"}
        file_selection = self.use_file_selection
        directory = bpy.path.abspath(self.directory if file_selection else settings.batch_import_directory)
        if not directory or not os.path.isdir(directory):
            self.report({"WARNING"}, "Select a valid import folder")
            return {"CANCELLED"}
        try:
            files = (collect_selected_import_files(directory, self.files, settings.batch_import_format)
                     if file_selection else collect_import_files(
                         directory, settings.batch_import_format, settings.batch_include_subfolders))
            if not files:
                raise RuntimeError("No supported mesh files found")
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
        if self.use_file_selection:
            context.window_manager.fileselect_add(self)
            return {"RUNNING_MODAL"}
        return self.execute(context)

    def modal(self, context, event):
        from . import import_queue

        if self._queue.finished:
            self._finish(context)
            return {"FINISHED"}
        if event.type == "ESC":
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
