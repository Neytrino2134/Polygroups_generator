"""Queue processing helpers."""
import bpy
import bmesh
from ..core.remesh_defaults import apply_quad_remesher_defaults_once, get_remesh_preset_counts
from .small_islands import plan_merge
from .relax_seams import relax_seams
from .object_seam_cutter import (
    _delete_loose_geometry_for_autofix,
    _fill_open_nonmanifold_boundaries,
    _remove_fin_faces_for_autofix,
    _triangulate_ngons_for_autofix,
)
from .queue_storage import (
    move_to_collection,
)


class QueueProcessingMixin:
    """Workflow methods sharing the owning ImportQueue state."""

    def restore_bake_settings(self):
        if self.saved_bake_settings is None:
            return
        use_auto, autogenerate_smart, use_smart, save_textures, selected_to_active = self.saved_bake_settings
        bake = self.scene.polygroups_baking_settings
        bake.autogenerate_smart_cage = False
        bake.use_auto_cage = False
        if autogenerate_smart:
            bake.autogenerate_smart_cage = True
        elif use_auto:
            bake.use_auto_cage = True
        else:
            bake.use_smart_cage = use_smart
        bake.auto_save_textures_after_bake = save_textures
        bake.use_selected_to_active = selected_to_active
        self.saved_bake_settings = None

    def collect_bake_created(self):
        if self.bake_snapshot is None:
            return
        target, objects, meshes, materials, images = self.bake_snapshot
        created_objects = {
            obj for obj in set(bpy.data.objects) - objects
            if obj.get("polygroups_smart_cage")
            and obj.get("smart_cage_target_object") == target
        }
        self.owned_objects.update(created_objects)
        self.file_objects.extend(obj for obj in created_objects if obj not in self.file_objects)
        self.owned_meshes.update(obj.data for obj in created_objects if obj.data not in meshes)
        target_materials = {material for material in target.data.materials if material is not None}
        self.owned_bake_materials.update(target_materials - materials)
        for material in target_materials:
            if material.node_tree is None:
                continue
            self.owned_bake_images.update(
                node.image for node in material.node_tree.nodes
                if node.type == "TEX_IMAGE" and node.image is not None and node.image not in images
            )
        self.bake_snapshot = None

    def start_auto_bake(self, context, target):
        self.select_source(context, target)
        if not bpy.data.filepath:
            raise RuntimeError("Save the blend file before Auto Bake so textures have an output folder")
        if target.data.uv_layers.active is None:
            raise RuntimeError(f"Auto Bake needs a UV map on {target.name}")
        bake = self.scene.polygroups_baking_settings
        if self.saved_bake_settings is None:
            self.saved_bake_settings = (
                bake.use_auto_cage, bake.autogenerate_smart_cage, bake.use_smart_cage,
                bake.auto_save_textures_after_bake, bake.use_selected_to_active,
            )
        bake.autogenerate_smart_cage = False
        bake.use_auto_cage = False
        if self.settings.batch_autobake_cage_mode == "SMART":
            bake.autogenerate_smart_cage = True
        else:
            bake.use_auto_cage = True
        bake.auto_save_textures_after_bake = True
        bake.use_selected_to_active = True
        self.bake_snapshot = (
            target, set(bpy.data.objects), set(bpy.data.meshes),
            set(bpy.data.materials), set(bpy.data.images),
        )
        result = bpy.ops.object.polygroups_checked_prepare_and_bake("EXEC_DEFAULT")
        if "CANCELLED" in result:
            raise RuntimeError(f"Auto Bake could not start for {target.name}")

    def restore_remesh_settings(self):
        if self.saved_remesh_settings is None:
            return
        use_materials, prepare, seams = self.saved_remesh_settings
        if hasattr(self.scene, "qremesher"):
            self.scene.qremesher.use_materials = use_materials
        self.settings.remesh_pregenerate_polygroups = prepare
        self.settings.remesh_auto_generate_seams = seams
        self.saved_remesh_settings = None

    def refresh_processing_settings(self, context):
        """Apply settings edited while paused to the next queued file."""
        settings = self.settings
        prefix = self.prefix
        self.rename = getattr(settings, prefix + "_auto_rename_objects")
        self.weld = getattr(settings, prefix + "_apply_weld")
        self.auto_remesh = getattr(settings, prefix + "_auto_remesh")
        self.remesh_method = getattr(settings, prefix + "_remesh_method")
        self.voxel_size = getattr(settings, prefix + "_voxel_size")
        self.clear_material = getattr(settings, prefix + "_clear_material")
        self.separate = getattr(settings, prefix + "_separate_collections")
        self.disable_completed_collection = self.batch_stages and self.separate
        if self.redo_mode:
            self.disable_completed_collection = False
        self.auto_smart_uv_project = bool(
            getattr(settings, prefix + "_auto_smart_uv_project")
            and (self.auto_remesh or self.batch_stages)
        )
        self.auto_unwrap_method = getattr(settings, prefix + "_auto_unwrap_method")
        if self.batch_stages:
            self.remove_small_loose_parts = settings.batch_first_remove_small_loose_parts
            self.small_loose_part_metric = settings.batch_first_small_loose_part_metric
            self.small_loose_part_threshold = settings.batch_first_small_loose_part_threshold_percent
        else:
            self.remove_small_loose_parts = settings.file_import_remove_small_loose_parts
            self.small_loose_part_metric = settings.file_import_small_loose_part_metric
            self.small_loose_part_threshold = settings.file_import_small_loose_part_threshold_percent
        self.quad_count = dict(get_remesh_preset_counts(context))[
            getattr(settings, prefix + "_remesh_preset")
        ]
        self.weld_distance = settings.weld_distance
        self.arrange = settings.batch_auto_arrange_objects
        if self.redo_mode:
            self.arrange = False
        self.arrange_options = (
            settings.batch_arrange_spacing,
            settings.batch_arrange_mode,
            settings.batch_arrange_rows,
            settings.batch_arrange_plane,
            settings.batch_arrange_alignment,
            settings.batch_arrange_secondary_spacing,
        )
        self.auto_save = bool(self.batch_stages and settings.batch_auto_save)
        self.auto_save_interval = max(1, settings.batch_auto_save_interval)
        self.save_generated_separately = bool(
            self.batch_stages
            and self.separate
            and settings.batch_save_generated_separately
        )

    def configure_passes(self, context):
        settings = self.settings
        self.passes = []
        if not self.batch_stages:
            if self.auto_remesh:
                self.passes.append((1, self.remesh_method, self.quad_count,
                                    self.auto_smart_uv_project, self.auto_unwrap_method))
        else:
            if settings.batch_stage_2_enabled:
                self.passes.append((2, self.remesh_method if self.auto_remesh else None,
                                    self.quad_count, self.auto_smart_uv_project,
                                    self.auto_unwrap_method))
            for number in (3, 4):
                if getattr(settings, f"batch_stage_{number}_enabled"):
                    preset = getattr(settings, f"batch_stage_{number}_remesh_preset")
                    self.passes.append((
                        number,
                        "QUAD" if getattr(settings, f"batch_stage_{number}_auto_remesh") else None,
                        dict(get_remesh_preset_counts(context))[preset],
                        getattr(settings, f"batch_stage_{number}_auto_unwrap"),
                        getattr(settings, f"batch_stage_{number}_auto_unwrap_method"),
                    ))
        self.stage = (self.first_cleanup_stage()
                      if self.batch_stages and not settings.batch_stage_2_enabled
                      else "PASS_SETUP")

    def tracked(self, action):
        """Track only IDs created by our synchronous action, even if it fails."""
        before_objects = set(bpy.data.objects)
        before_collections = set(bpy.data.collections)
        before_meshes = set(bpy.data.meshes)
        before_materials = set(bpy.data.materials)
        before_images = set(bpy.data.images)
        try:
            return action()
        finally:
            self.owned_objects.update(set(bpy.data.objects) - before_objects)
            self.owned_collections.update(set(bpy.data.collections) - before_collections)
            self.owned_meshes.update(set(bpy.data.meshes) - before_meshes)
            self.owned_materials.update(set(bpy.data.materials) - before_materials)
            self.owned_images.update(set(bpy.data.images) - before_images)

    def select_source(self, context, obj):
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for selected in context.selected_objects:
            selected.select_set(False)
        obj.hide_viewport = False
        obj.hide_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj

    def split_narrow_island(self, context, obj, second=False):
        self.select_source(context, obj)
        if obj.data.users > 1:
            obj.data = obj.data.copy()
            self.owned_meshes.add(obj.data)
        narrow = (self.settings if second
                  else self.scene.polygroups_seam_finalization_settings)
        prefix = "batch_second_narrow_island_" if second else "narrow_island_"
        source = 'UV' if obj.data.uv_layers.active is not None else 'MESH'
        action = 'SPLIT' if source == 'UV' else 'SEAMS'
        result = bpy.ops.mesh.polygroups_split_narrow_islands(
            source=source, action=action,
            width=getattr(narrow, prefix + "width"),
            max_width_percent=(self.settings.batch_narrow_island_max_width_percent
                               if not second else getattr(narrow, prefix + "max_width_percent")),
            min_island_area_percent=getattr(narrow, prefix + "min_area_percent"),
            min_faces=getattr(narrow, prefix + "min_faces"),
            min_length=getattr(narrow, prefix + "min_length"),
            selected_only=False,
            create_edges=getattr(narrow, prefix + "create_edges"),
            smart_relax=getattr(narrow, prefix + "smart_relax"),
        )
        if 'FINISHED' not in result:
            raise RuntimeError(f'Narrow Island Splitter failed for {obj.name}')

    def merge_small_islands(self, context, obj, second=False):
        self.select_source(context, obj)
        settings = self.settings
        prefix = "batch_second_small_island_" if second else "batch_small_island_"
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            removed, _total, _small, _merged = plan_merge(
                bm,
                getattr(settings, prefix + "threshold"),
                protect_sharp=getattr(settings, prefix + "protect_sharp"),
                protect_materials=getattr(settings, prefix + "protect_materials"),
                protect_pinned=getattr(settings, prefix + "protect_pinned"),
            )
            if removed:
                if obj.data.users > 1:
                    obj.data = obj.data.copy()
                    self.owned_meshes.add(obj.data)
                bm.edges.ensure_lookup_table()
                for index in removed:
                    bm.edges[index].seam = False
                bm.to_mesh(obj.data)
                obj.data.update()
        finally:
            bm.free()

    def smart_relax_edges(self, context, obj):
        self.select_source(context, obj)
        if obj.data.users > 1:
            obj.data = obj.data.copy()
            self.owned_meshes.add(obj.data)
        seam_settings = self.scene.polygroups_seam_preparation_settings
        bpy.ops.object.mode_set(mode="EDIT")
        try:
            relax_seams(
                context, "SMART",
                seam_settings.seam_relax_iterations,
                seam_settings.seam_relax_corner_angle,
                seam_settings.seam_relax_protection_radius,
                use_corner_angle=seam_settings.seam_relax_use_corner_angle,
                select_result=False,
                selected_area_only=False,
            )
        finally:
            bpy.ops.object.mode_set(mode="OBJECT")

    def autofix_second_pass(self, context, obj):
        self.select_source(context, obj)
        if obj.data.users > 1:
            obj.data = obj.data.copy()
            self.owned_meshes.add(obj.data)
        settings = self.settings
        if getattr(settings, f"batch_stage_{self.pass_number}_autofix_fin_loose"):
            _remove_fin_faces_for_autofix(context, obj)
            _delete_loose_geometry_for_autofix(context, obj)
        if getattr(settings, f"batch_stage_{self.pass_number}_autofix_close_nonmanifold"):
            _fill_open_nonmanifold_boundaries(obj)
        if getattr(settings, f"batch_stage_{self.pass_number}_autofix_triangulate_ngons"):
            _triangulate_ngons_for_autofix(obj)

    def repair_completed_pass_geometry(self, context, targets):
        if not self.batch_stages or not self.pass_method or self.pass_number not in (2, 3, 4):
            return
        property_name = ("batch_first_geometry_repair" if self.pass_number == 2 else
                         f"batch_stage_{self.pass_number}_geometry_repair")
        if not getattr(self.settings, property_name):
            return
        for obj in targets:
            self.select_source(context, obj)
            if obj.data.users > 1:
                obj.data = obj.data.copy()
                self.owned_meshes.add(obj.data)
            result = bpy.ops.mesh.polygroups_repair_mesh_folds(
                'EXEC_DEFAULT', action='REPAIR', fix_folds=True,
                fix_degenerate=True, fix_zero_area=True, selected_only=False,
                fix_stretched_triangles=self.settings.fold_repair_stretched_triangles,
                fix_dangling=self.settings.fold_repair_dangling,
                stretched_triangle_ratio=self.settings.fold_repair_stretch_ratio,
            )
            if 'FINISHED' not in result:
                raise RuntimeError(f'Geometry Repair failed after remesh pass {self.pass_number - 1}: {obj.name}')

    def first_cleanup_stage(self):
        if not self.batch_stages:
            return "PASS_SETUP"
        if self.settings.batch_narrow_island_enabled:
            return "NARROW_SPLIT"
        if self.settings.batch_small_islands_enabled:
            return "SMALL_ISLANDS"
        return "PASS_SETUP"

    def second_cleanup_stage(self):
        if not self.batch_stages:
            return "PASS_SETUP"
        if self.settings.batch_second_narrow_island_enabled:
            return "SECOND_NARROW_SPLIT"
        if self.settings.batch_second_small_islands_enabled:
            return "SECOND_SMALL_ISLANDS"
        return "PASS_SETUP"

    def pre_unwrap_stage(self, loose_cleanup_done=False):
        if self.batch_stages and self.pass_number in (3, 4):
            self.mesh_index = 0
            if (not loose_cleanup_done and getattr(
                    self.settings, f"batch_stage_{self.pass_number}_remove_small_loose_parts")):
                return "REMOVE_SMALL_LOOSE_PARTS"
            if getattr(self.settings, f"batch_stage_{self.pass_number}_autofix_enabled"):
                return "AUTOFIX_SECOND"
            return "UNWRAP_PASS"
        if (
            self.remove_small_loose_parts
            and self.pass_number == (2 if self.batch_stages else 1)
        ):
            self.mesh_index = 0
            return "REMOVE_SMALL_LOOSE_PARTS"
        if (
            self.batch_stages
            and self.pass_number == 2
            and self.settings.batch_first_uv_repair_enabled
        ):
            self.mesh_index = 0
            return "FIRST_UV_REPAIR"
        return "UNWRAP_PASS"

    def finalization_stage(self):
        self.mesh_index = 0
        if self.batch_stages and self.settings.batch_smart_decimate_enabled:
            self.pass_number = 11
            return "SMART_DECIMATE"
        if self.batch_stages and self.settings.batch_smart_lods_enabled:
            self.pass_number = 12
            return "SMART_LODS"
        return "COMPLETE"

    def finalize_mesh(self, context, obj):
        settings = self.settings
        self.select_source(context, obj)
        if self.stage == "SMART_DECIMATE":
            from .smart_decimate import SEAMS_DECIMATE_MODIFIER_NAME, SMART_DECIMATE_MODIFIER_NAME
            result = self.tracked(lambda: bpy.ops.object.polygroups_smart_decimate(
                triangle_limit=settings.batch_smart_decimate_triangle_limit,
                duplicate_and_apply=False,
            ))
            if "FINISHED" not in result:
                raise RuntimeError(f"Smart Decimate failed for {obj.name}: check UV seam edges")
            for name in (SEAMS_DECIMATE_MODIFIER_NAME, SMART_DECIMATE_MODIFIER_NAME):
                # UV repair already applies each pass on UV-mapped meshes.
                if obj.modifiers.get(name) is None:
                    continue
                if "FINISHED" not in self.tracked(lambda: bpy.ops.object.modifier_apply(modifier=name)):
                    raise RuntimeError(f"Applying {name} failed for {obj.name}")
            self.file_record.setdefault("finalization", []).append({
                "object": obj.name, "stage": 11,
                "triangle_limit": settings.batch_smart_decimate_triangle_limit,
                "output_tris": self.count_tris([obj]),
                "limit_reached": self.count_tris([obj]) <= settings.batch_smart_decimate_triangle_limit,
            })
        else:
            lod_settings = self.scene.polygroups_mesh_finalization_settings
            names = ["smart_lods_count", "smart_lods_final_decimate", "smart_lods_triangulate_all",
                     "smart_lods_decimate_method", "smart_lods_uv_seam_mode"]
            names.extend(f"smart_lods_target_{i}" for i in range(1, 6))
            previous = {name: getattr(lod_settings, name) for name in names + ["smart_lods_auto_arrange"]}
            before = set(bpy.data.objects)
            try:
                for name in names:
                    setattr(lod_settings, name, getattr(settings, "batch_" + name))
                lod_settings.smart_lods_auto_arrange = False
                result = self.tracked(lambda: bpy.ops.object.polygroups_generate_smart_lods(active_only=True))
                if "FINISHED" not in result:
                    raise RuntimeError(f"Smart LODs failed for {obj.name}")
            finally:
                for name, value in previous.items():
                    setattr(lod_settings, name, value)
            outputs = sorted(set(bpy.data.objects) - before, key=lambda item: item.name)
            self.file_objects.extend(outputs)
            if self.collection:
                move_to_collection(outputs, self.collection)
            self.result_meshes.extend(item for item in outputs if item.type == "MESH")
            self.file_record.setdefault("finalization", []).append({
                "object": obj.name, "stage": 12,
                "decimate_method": settings.batch_smart_lods_decimate_method,
                "fallback": settings.batch_smart_lods_final_decimate,
                "triangulate": settings.batch_smart_lods_triangulate_all,
                "lods": [{"object": item.name, "output_tris": self.count_tris([item]),
                          "triangle_limit": getattr(settings, f"batch_smart_lods_target_{index}"),
                          "limit_reached": self.count_tris([item]) <= getattr(settings, f"batch_smart_lods_target_{index}")}
                         for index, item in enumerate((item for item in outputs if item.type == "MESH"), 1)],
            })

    def replace_remesh_material(self, obj):
        # Only change the generated result, including when a backend shares data.
        if obj.data.users > 1:
            obj.data = obj.data.copy()
            self.owned_meshes.add(obj.data)
        material = bpy.data.materials.new(name="Remesh Gray")
        self.owned_gray_materials.add(material)
        material.use_nodes = True
        gray = (0.5, 0.5, 0.5, 1.0)
        material.diffuse_color = gray
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = gray
        bsdf.inputs["Roughness"].default_value = 0.5
        obj.data.materials.clear()
        obj.data.materials.append(material)
        obj.material_slots[0].link = "DATA"
        obj.active_material_index = 0
        for polygon in obj.data.polygons:
            polygon.material_index = 0

    def arrange_groups(self):
        from .batch_import import arrange_objects_zx

        # Translate each file as a unit so highpoly/retopo pairs stay aligned.
        anchors = [anchor for anchor, objects in self.groups]
        old_positions = {obj: obj.matrix_world.translation.copy() for obj in anchors}
        arrange_objects_zx(anchors, *self.arrange_options, preserve_order=True)
        self.view_layer.update()
        deltas = {obj: obj.matrix_world.translation - old_positions[obj] for obj in anchors}
        for anchor in anchors:
            anchor.matrix_world.translation = old_positions[anchor]
        self.view_layer.update()
        for anchor, objects in self.groups:
            delta = deltas[anchor]
            matrices = {obj: obj.matrix_world.copy() for obj in objects}
            def parent_depth(obj):
                depth = 0
                while obj.parent:
                    depth += 1
                    obj = obj.parent
                return depth
            for obj in sorted(objects, key=parent_depth):
                matrix = matrices[obj]
                matrix.translation += delta
                obj.matrix_world = matrix
                self.view_layer.update()

    @staticmethod
    def count_tris(objects):
        return sum(max(0, len(poly.vertices) - 2)
                   for obj in set(objects) if obj.type == "MESH" for poly in obj.data.polygons)
