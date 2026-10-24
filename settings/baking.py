"""Baking workflow RNA property groups."""
from .callbacks import (
    _auto_cage_mode_update,
    _smart_cage_mode_update,
    _smart_cage_strength_get,
    _smart_cage_strength_set,
    bpy,
)


class POLYGROUPS_PG_baking_settings(bpy.types.PropertyGroup):
    bake_task_is_running: bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})
    bake_task_stage: bpy.props.StringProperty(default="", options={"SKIP_SAVE"})
    bake_task_message: bpy.props.StringProperty(default="", options={"SKIP_SAVE"})
    bake_task_progress: bpy.props.FloatProperty(
        default=0.0, min=0.0, max=100.0, subtype="PERCENTAGE", options={"SKIP_SAVE"},
    )
    bake_resolution: bpy.props.IntProperty(
        name="Bake Resolution",
        description="Width and height for generated bake images",
        default=2048,
        min=16,
        max=16384,
        soft_max=8192,
    )
    bake_margin: bpy.props.IntProperty(
        name="Bake Margin",
        description="Bake margin in pixels",
        default=16,
        min=0,
        max=256,
    )
    bake_background_mode: bpy.props.EnumProperty(
        name="Bake Background",
        description="How Base Color background pixels are filled; Normal backgrounds always use a neutral normal",
        items=(
            ("BLACK", "Black", "Fill Base Color pixels outside the baked surface with black"),
            ("EXTEND", "Edge Extend", "Extend Base Color from the nearest baked edge into the background"),
        ),
        default="EXTEND",
    )
    ray_distance: bpy.props.FloatProperty(
        name="Ray Distance",
        description="Maximum ray distance for selected-to-active baking",
        default=0.0,
        min=0.0,
        soft_max=1.0,
        step=0.5,
        precision=4,
    )
    cage_extrusion: bpy.props.FloatProperty(
        name="Cage Extrusion",
        description="Cage extrusion for selected-to-active baking",
        default=0.01,
        min=0.0,
        soft_max=1.0,
        step=0.5,
        precision=4,
    )
    use_auto_cage: bpy.props.BoolProperty(
        name="AutoCage",
        description="Automatically calculate cage extrusion from selected highpoly and active lowpoly before baking",
        default=True,
        update=_auto_cage_mode_update,
    )
    auto_cage_coverage: bpy.props.FloatProperty(
        name="Coverage",
        description="Highpoly surface coverage percentile used for automatic cage extrusion",
        default=99.8,
        min=90.0,
        max=99.8,
        precision=1,
        subtype="PERCENTAGE",
    )
    auto_cage_margin: bpy.props.FloatProperty(
        name="Safety Margin",
        description="Fixed extra distance added to the automatic cage extrusion",
        default=0.005,
        min=0.0,
        soft_max=0.02,
        precision=5,
        unit="LENGTH",
    )
    auto_cage_margin_percent: bpy.props.FloatProperty(
        name="Size Margin",
        description="Object-size relative margin added to the automatic cage extrusion",
        default=0.001,
        min=0.0,
        max=0.05,
        precision=4,
        subtype="FACTOR",
    )
    auto_cage_safe_zone: bpy.props.FloatProperty(
        name="Safe Zone",
        description="Extra percentage added on top of the calculated automatic cage extrusion",
        default=8.5,
        min=0.0,
        max=10.0,
        precision=1,
        subtype="PERCENTAGE",
    )
    auto_cage_max: bpy.props.FloatProperty(
        name="Max Cage",
        description="Maximum allowed automatic cage extrusion; 0 disables the limit",
        default=0.05,
        min=0.0,
        soft_max=1.0,
        precision=4,
        unit="LENGTH",
    )
    auto_cage_sample_limit: bpy.props.IntProperty(
        name="Samples",
        description="Maximum highpoly sample points used for AutoCage analysis",
        default=10000,
        min=100,
        max=200000,
        soft_max=50000,
    )
    auto_cage_status: bpy.props.StringProperty(
        name="AutoCage Status",
        default="Not calculated",
    )
    use_smart_cage: bpy.props.BoolProperty(name="Use Smart Cage Object", default=False,
        description="Использовать выбранный и проверенный Smart Cage при запекании вместо обычного выдавливания Auto Cage")
    autogenerate_smart_cage: bpy.props.BoolProperty(name="Autogenerate Smart Cage", default=False,
        description="Использовать Smart Cage при запекании; если для lowpoly нет cage, создать его автоматически",
        update=_smart_cage_mode_update)
    smart_cage_object: bpy.props.PointerProperty(name="Cage Object", type=bpy.types.Object,
        description="Объект cage для запекания; создаётся кнопкой Generate и должен соответствовать активному lowpoly")
    smart_cage_margin: bpy.props.FloatProperty(name="Minimum Clearance", default=0.001,
        description="Минимальный базовый отступ от lowpoly в мировых единицах; отдельный модификатор Displace, по умолчанию 0.001",
        min=0.000001, soft_max=0.1, precision=5, unit="LENGTH")
    smart_cage_started_clearance: bpy.props.FloatProperty(name="Started Clearance", default=0.05,
        description="Сила адаптивного Smart Cage Displace при генерации; веса стартуют с 0.001 и растут там, где не покрыт highpoly",
        min=0.000001, soft_max=1.0, precision=4, unit="LENGTH")
    smart_cage_max: bpy.props.FloatProperty(name="Maximum Offset", default=0.0,
        min=0.0, soft_max=1.0, precision=4, unit="LENGTH",
        description="Верхний предел общего отступа в мировых единицах; 0 означает автоматический предел по размеру lowpoly")
    smart_cage_smoothing: bpy.props.FloatProperty(name="Weight Smoothing", default=0.35,
        description="Насколько решатель распределяет нужное увеличение весов на соседние вершины; применяется при Generate",
        min=0.0, max=1.0, subtype="FACTOR")
    smart_cage_iterations: bpy.props.IntProperty(name="Solver Iterations", default=20, min=1, max=100,
        description="Максимум шагов постепенного увеличения весов; больше шагов дают решателю больше времени, но замедляют Generate")
    smart_cage_samples: bpy.props.IntProperty(name="Coverage Samples", default=20000, min=100, max=500000,
        description="Сколько точек поверхности highpoly проверить на покрытие; больше точек повышают точность и время расчёта")
    smart_cage_avoid_self: bpy.props.BoolProperty(name="Avoid Self Intersections", default=True,
        description="Ограничивать расширение cage в щелях и местах, где его части могут пересечь друг друга")
    smart_cage_status: bpy.props.StringProperty(name="Smart Cage Status", default="Not generated",
        description="Результат последней проверки; после изменения весов или толщины нажмите Validate Smart Cage")
    smart_cage_live_thickness: bpy.props.FloatProperty(name="Live Cage Thickness",
        description="Текущая сила адаптивного Displace на готовом cage; меняется сразу, шаг ввода 0.001, после правки проверьте cage",
        step=0.1, precision=3, options=set(),
        get=_smart_cage_strength_get("Smart Cage Displace"),
        set=_smart_cage_strength_set("Smart Cage Displace"))
    smart_cage_live_clearance: bpy.props.FloatProperty(name="Live Extra Clearance",
        description="Дополнительный равномерный отступ готового cage; меняется сразу, шаг ввода 0.001, может ухудшить зазоры",
        step=0.1, precision=3, options=set(),
        get=_smart_cage_strength_get("Smart Cage Extra Clearance"),
        set=_smart_cage_strength_set("Smart Cage Extra Clearance"))
    smart_cage_reduce_self: bpy.props.FloatProperty(name="Reduce Self Intersections",
        description="Отрицательная сила отдельного Displace для вершин Smart Cage Self Intersections; от 0 до -1, шаг 0.001",
        min=-1.0, max=0.0, step=0.1, precision=3, options=set(),
        get=_smart_cage_strength_get("Smart Cage Reduce Self Intersections"),
        set=_smart_cage_strength_set("Smart Cage Reduce Self Intersections"))
    image_prefix: bpy.props.StringProperty(
        name="Image Prefix",
        description="Prefix for generated bake images",
        default="Bake_Temp",
    )
    use_selected_to_active: bpy.props.BoolProperty(
        name="Selected To Active",
        description="Bake from selected source meshes to the active target mesh",
        default=True,
    )
    bake_base_color: bpy.props.BoolProperty(
        name="Base Color",
        description="Bake source Base Color to the active target",
        default=True,
    )
    bake_normal: bpy.props.BoolProperty(
        name="Normal",
        description="Bake source normals to the active target",
        default=True,
    )
    bake_artifact_mask: bpy.props.BoolProperty(
        name="Projection Artifact Mask",
        description="Mark reversed tangent normals and proven ray misses using native Cycles coverage passes",
        default=True,
    )
    bake_artifact_self_intersections: bpy.props.BoolProperty(
        name="Include Cage Self Intersections",
        description="Also mark areas where the cage intersects itself in the artifact mask",
        default=False,
    )
    bake_artifact_geometry: bpy.props.BoolProperty(
        name="Include Geometric Intersections", default=False,
        description="Add legacy cage/highpoly warnings, which may include harmless intersections",
    )
    bake_artifact_match_normal: bpy.props.BoolProperty(
        name="Match Normal Resolution", default=True,
        description="Classify at actual normal resolution; manual mode only conservatively downsamples the output",
    )
    bake_artifact_mode: bpy.props.EnumProperty(
        name="Analysis", default='FULL',
        items=(('FULL', 'Full Projection', 'Reversed normals and ray misses; two native coverage passes'),
               ('NORMAL_ONLY', 'Normal Inversion Only', 'Reduced cost: inverted normals only; ray misses are not detected')),
    )
    bake_artifact_resolution: bpy.props.IntProperty(
        name="Artifact Mask Resolution",
        description="Advanced output downsampling; cannot exceed the actual normal resolution",
        default=2048, min=16, max=16384, soft_max=8192,
    )
    bake_artifact_inherit_margin: bpy.props.BoolProperty(
        name="Inherit Bake Margin", default=True,
        description="Expand the artifact mask by Bake Settings margin plus additional pixels",
    )
    bake_artifact_radius: bpy.props.IntProperty(
        name="Additional Mask Expansion (px)",
        description="Extra pixels added to the inherited Bake Margin, or the entire expansion when inheritance is disabled",
        default=2, min=0, max=32,
    )
    bake_artifact_autofill: bpy.props.BoolProperty(
        name="Autofill Artifacts", default=True,
        description="Fill masked Normal and Base Color texels inward from healthy pixels in the same UV island",
    )
    bake_artifact_autofill_blur: bpy.props.IntProperty(
        name="Autofill Blur (px)", default=2, min=0, max=16,
        description="Gaussian smoothing radius applied only to newly filled pixels; normal vectors are normalized",
    )
    auto_save_textures_after_bake: bpy.props.BoolProperty(
        name="Auto Save Textures After Bake",
        description="Run Save Textures automatically after Prepare And Bake finishes",
        default=True,
    )
    disable_highpoly_after_bake: bpy.props.BoolProperty(
        name="Disable Highpoly After Bake",
        description="Disable baked highpoly source objects in viewports after a successful bake",
        default=True,
    )
    auto_fix_generated_index: bpy.props.BoolProperty(
        name="Auto Fix Generated Index",
        description="Before baking, force selected mesh name indices to match their Generated.N collections",
        default=True,
    )
    auto_pack_uv_before_bake: bpy.props.BoolProperty(
        name="Auto Pack UV Before Bake",
        description="Pack the active lowpoly UVs with UVPackmaster before baking",
        default=False,
    )
    show_auto_pack_uv_settings: bpy.props.BoolProperty(
        name="Show Auto Pack UV Settings",
        description="Expand UVPackmaster settings used before baking",
        default=False,
        options={"SKIP_SAVE"},
    )


class POLYGROUPS_PG_resculpting_settings(bpy.types.PropertyGroup):
    apply_shrinkwrap: bpy.props.BoolProperty(name="Apply Shrinkwrap", default=True,
        description="Apply Shrinkwrap during Setup Resculpting")
    multires_levels: bpy.props.IntProperty(
        name="Multires Levels",
        description="Subdivision levels to create on the active lowpoly mesh",
        default=2,
        min=0,
        max=6,
        soft_max=3,
    )
    shrinkwrap_limit: bpy.props.FloatProperty(
        name="Shrinkwrap Limit",
        description="Projection limit for the Shrinkwrap modifier",
        default=0.01,
        min=0.0,
        soft_max=0.1,
        precision=4,
        unit="LENGTH",
    )
    shrinkwrap_offset: bpy.props.FloatProperty(
        name="Shrinkwrap Offset",
        description="Surface offset for the Shrinkwrap modifier",
        default=0.0,
        soft_min=-0.1,
        soft_max=0.1,
        precision=4,
        unit="LENGTH",
    )
