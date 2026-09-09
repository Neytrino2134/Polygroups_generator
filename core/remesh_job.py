"""Non-modal adapter for the installed Quad Remesher engine integration."""

import importlib
import math
import re
import subprocess
import time
from types import SimpleNamespace

import bpy

from .remesh_cursor import RemeshCursor
from .material_seams import mark_material_boundary_seams


def next_retopo_name(source_name, result=None):
    match = re.fullmatch(r"Retopo_(?:(\d+)_)?(.+)", source_name)
    base = match.group(2) if match else source_name
    generation = (int(match.group(1) or 1) + 1) if match else 1
    while True:
        if generation == 1 and bpy.data.objects.get(f"Retopo_01_{base}") is not None:
            generation = 2
        name = f"Retopo_{base}" if generation == 1 else f"Retopo_{generation:02d}_{base}"
        existing = bpy.data.objects.get(name)
        if existing is None or existing == result:
            return name
        generation += 1


def disable_previous_remesh(source):
    """Disable the previous generation using Outliner's viewport and render toggles."""
    if source is None or source not in set(bpy.data.objects):
        return
    source.hide_set(True)
    source.hide_viewport = True
    source.hide_render = True


def remesh_backend(context):
    if not hasattr(context.scene, "qremesher"):
        raise RuntimeError("Enable Quad Remesher before using Auto Remesh")
    operator_type = bpy.types.Operator.bl_rna_get_subclass_py("QREMESHER_OT_remesh")
    if operator_type is None:
        raise RuntimeError("Quad Remesher is not available")
    module = importlib.import_module(operator_type.__module__)
    if not all(callable(getattr(module, name, None)) for name in (
        "doRemeshing_Start", "doRemeshing_Finish",
    )):
        raise RuntimeError("This Quad Remesher version does not support queued remeshing")
    return module


class RemeshJob:
    def __init__(self, backend, report):
        self.backend = backend
        self.state = SimpleNamespace(
            report=report, remeshProcess=None, IsRemeshing=False,
            progressFilename=None, retopoFilename=None,
        )
        self.started = time.monotonic()
        self.exited = None
        self.message = ""
        self.cursor = None

    def start(self, context):
        preparation = context.scene.polygroups_model_preparation_settings
        self.auto_generate_seams = preparation.remesh_auto_generate_seams
        self.auto_unwrap_checker = preparation.remesh_auto_unwrap_checker
        self.source = context.active_object
        self.source_name = self.source.name
        self.source_collections = tuple(self.source.users_collection)
        # Every add-on Remesh entry point, including import queues, starts here.
        # Enforce this for each job even if defaults were already applied or the
        # user enabled angle detection in Quad Remesher between runs.
        context.scene.qremesher.autodetect_hard_edges = False
        if preparation.remesh_pregenerate_polygroups:
            if "FINISHED" not in bpy.ops.object.generate_polygroups():
                raise RuntimeError("Generate PolyGroups did not finish")
        self.cursor = RemeshCursor(context)
        self.backend.doRemeshing_Start(self.state, context)
        if not self.state.IsRemeshing:
            raise RuntimeError("Quad Remesher could not start; check its installation and license")

    def poll(self):
        value, message = None, ""
        try:
            with open(self.state.progressFilename, encoding="utf-8") as stream:
                lines = stream.read().splitlines()
            value = float(lines[0])
            message = " ".join(lines[1:])
            self.message = message
            if not math.isfinite(value):
                value = None
        except (OSError, ValueError, IndexError, TypeError):
            pass  # The engine may be in the middle of writing the file.
        if self.cursor is not None and value is not None and value >= 0:
            self.cursor.percent = max(self.cursor.percent, min(99.0, value * 100))
        if value == 2:
            return True, 1.0
        if value is not None and value < 0:
            raise RuntimeError(message or f"Quad Remesher failed ({value})")
        process = self.state.remeshProcess
        if process is not None and process.poll() is not None:
            if self.exited is None:
                self.exited = time.monotonic()
            if time.monotonic() - self.exited > 2:
                raise RuntimeError("Quad Remesher exited without a completed result")
        if value is None and time.monotonic() - self.started > 40:
            raise RuntimeError("Quad Remesher did not report progress within 40 seconds")
        return False, max(0.0, min(1.0, value or 0.0))

    def finish(self, context):
        before = set(bpy.data.objects)
        self.backend.doRemeshing_Finish(self.state, context)
        outputs = sorted(set(bpy.data.objects) - before, key=lambda obj: obj.name)
        meshes = [obj for obj in outputs if obj.type == "MESH"]
        if not meshes:
            raise RuntimeError("Quad Remesher did not create a mesh")
        for obj in meshes:
            obj.name = next_retopo_name(self.source_name, obj)
            if getattr(self, "auto_generate_seams", False):
                if obj.data.users > 1:
                    obj.data = obj.data.copy()
                mark_material_boundary_seams(obj)
        collections = [collection for collection in self.source_collections
                       if collection in set(bpy.data.collections)]
        if not collections:
            collections = [context.scene.collection]
        for obj in outputs:
            for collection in collections:
                if obj.name not in collection.objects:
                    collection.objects.link(obj)
            for collection in list(obj.users_collection):
                if collection not in collections:
                    collection.objects.unlink(obj)
        context.view_layer.update()
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in meshes:
            obj.select_set(True)
        context.view_layer.objects.active = meshes[0]
        if getattr(self, "auto_unwrap_checker", False):
            for obj in meshes:
                context.view_layer.objects.active = obj
                if "FINISHED" not in bpy.ops.object.polygroups_unwrap_angle_based():
                    raise RuntimeError(f"Angle Based unwrap failed for {obj.name}")
                if "FINISHED" not in bpy.ops.object.polygroups_apply_checker_material():
                    raise RuntimeError(f"Applying checker material failed for {obj.name}")
            context.view_layer.objects.active = meshes[0]
        match = re.fullmatch(r"Retopo_(?:(\d+)_)?(.+)", self.source_name)
        if match and match.group(1) is None:
            source = self.source
            first_name = f"Retopo_01_{match.group(2)}"
            existing = bpy.data.objects.get(first_name)
            if existing is None or existing == source:
                source.name = first_name
            else:
                self.state.report({"WARNING"}, f"Source name kept: {first_name} already exists")
        disable_previous_remesh(self.source)
        if self.cursor is not None:
            self.cursor.close()
        return outputs

    def abort(self):
        if self.cursor is not None:
            self.cursor.close()
        process = self.state.remeshProcess
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


class VoxelRemeshJob:
    """Synchronous adapter matching RemeshJob for Blender's Remesh modifier."""

    def __init__(self, voxel_size, report):
        self.voxel_size = max(float(voxel_size), 0.000001)
        self.report = report
        self.source = None

    def start(self, context):
        preparation = context.scene.polygroups_model_preparation_settings
        self.auto_generate_seams = preparation.remesh_auto_generate_seams
        self.auto_unwrap_checker = preparation.remesh_auto_unwrap_checker
        self.source = context.active_object
        self.source_name = self.source.name
        self.source_collections = tuple(self.source.users_collection)
        if preparation.remesh_pregenerate_polygroups:
            if "FINISHED" not in bpy.ops.object.generate_polygroups():
                raise RuntimeError("Generate PolyGroups did not finish")

    def poll(self):
        return True, 1.0

    def finish(self, context):
        source = self.source
        if source is None or source not in set(bpy.data.objects):
            raise RuntimeError("Voxel Remesh source object is no longer available")

        result = source.copy()
        result.data = source.data.copy()
        collections = [
            collection for collection in self.source_collections
            if collection in set(bpy.data.collections)
        ] or [context.scene.collection]
        for collection in collections:
            collection.objects.link(result)

        for selected in context.selected_objects:
            selected.select_set(False)
        result.hide_set(False)
        result.select_set(True)
        context.view_layer.objects.active = result
        modifier = result.modifiers.new(name="Voxel Remesh", type="REMESH")
        modifier.mode = "VOXEL"
        modifier.voxel_size = self.voxel_size
        try:
            applied = bpy.ops.object.modifier_apply(modifier=modifier.name)
            if "FINISHED" not in applied:
                raise RuntimeError("Blender cancelled the Voxel Remesh modifier")
        except Exception:
            mesh = result.data
            bpy.data.objects.remove(result, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
            raise

        result.name = next_retopo_name(self.source_name, result)
        if self.auto_generate_seams:
            mark_material_boundary_seams(result)
        if self.auto_unwrap_checker:
            if "FINISHED" not in bpy.ops.object.polygroups_unwrap_angle_based():
                raise RuntimeError(f"Angle Based unwrap failed for {result.name}")
            if "FINISHED" not in bpy.ops.object.polygroups_apply_checker_material():
                raise RuntimeError(f"Applying checker material failed for {result.name}")
        disable_previous_remesh(source)
        context.view_layer.update()
        return [result]

    def abort(self):
        pass
