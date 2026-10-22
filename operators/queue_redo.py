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
    redo_source,
)


class QueueRedoMixin:
    """Workflow methods sharing the owning ImportQueue state."""

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
