"""Queue redo helpers."""
import bpy
from .rename_objects import (
    ensure_collection_visible_in_view_layer,
    get_next_object_index,
    layer_collection_paths,
    rename_and_move_objects,
)
from ..core.remesh_cursor import RemeshCursor
from .queue_storage import (
    RETOPO_PASS,
    redo_source,
)


class QueueRedoMixin:
    """Workflow methods sharing the owning ImportQueue state."""

    def prepare_resume(self, context):
        """Continue a collection whose Retopo mesh finished remesh pass 1 or 2.

        Pass 1 (Retopo_ / Retopo_01) resumes at 3. Narrow Island Splitter, pass 2 (Retopo_02) at
        6. Narrow Island Splitter; the queue then runs the remaining remesh passes up to stage 8."""
        info = self.resume
        collection, source = info["collection"], info["source"]
        high = redo_source(collection)
        if info["finished"]:
            raise RuntimeError("Retopo_03 is the end of Phase 1: nothing to resume")
        if high is None or source.name not in bpy.data.objects:
            raise RuntimeError("The selected Retopo mesh has no matching highpoly")
        if not ensure_collection_visible_in_view_layer(context, collection):
            raise RuntimeError("The selected Generated collection is not in this View Layer")
        self.collection = collection
        collection.color_tag = "COLOR_05"
        self.meshes = [high]
        self.file_record["input_tris"] = self.count_tris(self.meshes)
        self.file_objects = [high, source]
        self.pass_sources = [source]
        self.configure_passes(context)
        finished_pass = 2 if info["level"] == 1 else 3
        self.passes = [entry for entry in self.passes if entry[0] > finished_pass]
        self.pass_index = 0
        if not any(entry[1] for entry in self.passes):
            raise RuntimeError("Enable a later Remesh pass (stage 5 or 8) to resume this collection")
        self.redo_source_visibility = (source, source.hide_viewport, source.hide_get(), source.hide_render)
        source.hide_viewport = False
        source.hide_set(False)
        self.select_source(context, source)
        if self.cursor is None:
            self.cursor = RemeshCursor(context, label="Resume")
        # Results of later passes are rebuilt; the finished ones stay untouched.
        later = []
        for obj in collection.objects:
            match = RETOPO_PASS.fullmatch(obj.name)
            if match and obj != source and int(match.group(1) or 1) > info["level"]:
                later.append(obj)
        if later:
            backup = bpy.data.collections.new(f"__PolygroupsRedoBackup_{collection.name}")
            self.redo_backup_collection = backup
            for index, obj in enumerate(later):
                links = list(obj.users_collection)
                self.redo_backup.append((obj, obj.name, links))
                for previous in links:
                    previous.objects.unlink(obj)
                backup.objects.link(obj)
                obj.name = f"__PolygroupsRedoBackup_{collection.name}_{index:03d}"
        self.second_cleanup_done = info["level"] > 1
        self.stage = self.first_cleanup_stage() if info["level"] == 1 else self.second_cleanup_stage()
        self.mesh_index = 0

    def prepare_redo(self, context):
        collection = self.redo_collection
        source = redo_source(collection)
        if source is None or collection.name not in bpy.data.collections:
            raise RuntimeError("The selected Generated collection has no matching highpoly")
        if not ensure_collection_visible_in_view_layer(context, collection):
            raise RuntimeError("The selected Generated collection is not in this View Layer")
        self.collection = collection
        collection.color_tag = "COLOR_05"
        self.meshes = [source]
        self.file_record["input_tris"] = self.count_tris(self.meshes)
        self.file_objects = [source]
        self.pass_sources = [source]
        self.configure_passes(context)
        if not any(method for _number, method, _count, _unwrap, _unwrap_method in self.passes):
            raise RuntimeError("Enable at least one Remesh pass before rebuilding this collection")
        self.redo_source_visibility = (source, source.hide_viewport, source.hide_get(), source.hide_render)
        self.select_source(context, source)
        if self.cursor is None:
            self.cursor = RemeshCursor(context, label="Redo")
        old_results = [obj for obj in list(collection.objects) if obj.name.startswith("Retopo_")]
        if old_results:
            backup = bpy.data.collections.new(f"__PolygroupsRedoBackup_{collection.name}")
            self.redo_backup_collection = backup
            for index, obj in enumerate(old_results):
                links = list(obj.users_collection)
                self.redo_backup.append((obj, obj.name, links))
                for previous in links:
                    previous.objects.unlink(obj)
                backup.objects.link(obj)
                obj.name = f"__PolygroupsRedoBackup_{collection.name}_{index:03d}"

    def discard_redo_backup(self):
        materials = set()
        images = set()
        for obj, _name, _links in self.redo_backup:
            if obj.name in bpy.data.objects:
                mesh = obj.data if obj.type == "MESH" else None
                if mesh is not None:
                    materials.update(material for material in mesh.materials if material is not None)
                bpy.data.objects.remove(obj, do_unlink=True)
                if mesh is not None and mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
        for material in materials:
            if material.node_tree is not None:
                images.update(node.image for node in material.node_tree.nodes
                              if node.type == "TEX_IMAGE" and node.image is not None)
            if material.users == 0:
                bpy.data.materials.remove(material)
        for image in images:
            if image.users == 0:
                bpy.data.images.remove(image)
        self.redo_backup.clear()
        if self.redo_backup_collection is not None:
            bpy.data.collections.remove(self.redo_backup_collection)
            self.redo_backup_collection = None
        if self.redo_source_visibility is not None and not self.settings.batch_autobake_enabled:
            source, hidden_viewport, hidden_local, hidden_render = self.redo_source_visibility
            if source.name in bpy.data.objects:
                source.hide_viewport = hidden_viewport
                source.hide_set(hidden_local)
                source.hide_render = hidden_render
        self.redo_source_visibility = None

    def restore_redo_backup(self):
        if not self.redo_mode:
            return
        for obj in self.owned_objects & set(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in self.owned_meshes & set(bpy.data.meshes):
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        for material in (self.owned_gray_materials | self.owned_bake_materials) & set(bpy.data.materials):
            if material.users == 0:
                bpy.data.materials.remove(material)
        for image in self.owned_bake_images & set(bpy.data.images):
            if image.users == 0:
                bpy.data.images.remove(image)
        self.owned_objects.clear()
        self.owned_meshes.clear()
        self.owned_gray_materials.clear()
        self.owned_bake_materials.clear()
        self.owned_bake_images.clear()
        for obj, name, links in self.redo_backup:
            if obj.name not in bpy.data.objects:
                continue
            obj.name = name
            for collection in links:
                if collection.name in bpy.data.collections:
                    collection.objects.link(obj)
        self.redo_backup.clear()
        if self.redo_backup_collection is not None:
            bpy.data.collections.remove(self.redo_backup_collection)
            self.redo_backup_collection = None
        if self.redo_source_visibility is not None:
            source, hidden_viewport, hidden_local, hidden_render = self.redo_source_visibility
            if source.name in bpy.data.objects:
                source.hide_viewport = hidden_viewport
                source.hide_set(hidden_local)
                source.hide_render = hidden_render
            self.redo_source_visibility = None
