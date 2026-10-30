"""Phase 2 start presets (Unreal Export / Unreal Export + ZBrush) and the start confirmation dialog."""
import bpy

from ..core.asset_names import asset_name

PRESETS = (
    ('UNREAL', 'Unreal Export', 'MID / LOW FBX, Blend and render only: no highpoly resculpting and no ZBrush'),
    ('UNREAL_ZBRUSH', 'Unreal Export + ZBrush', 'Whole pipeline including Retopo_01 resculpting, rebake and ZBrush ZTL'),
)
# Highpoly options that only the ZBrush pipeline needs.
HIGHPOLY_OPTIONS = ('phase2_run_resculpt_retopo01', 'phase2_run_high_remesh', 'phase2_run_repair_resculpt',
                    'phase2_run_bake_resculpt')
SHARED_ON = ('phase2_run_restore', 'phase2_run_prepare', 'phase2_run_export', 'phase2_run_blend',
             'phase2_run_render', 'phase2_run_mid', 'phase2_export_fbx', 'phase2_blend_export_generated',
             'phase2_blend_export_highpoly', 'phase2_blend_export_retopo01', 'phase2_autosave',
             'phase2_auto_skip_scene', 'phase2_run_guard_highest', 'phase2_run_loose_parts',
             'phase2_run_fix_source', 'phase2_run_uv_repair')


def apply_start_preset(p, preset):
    """Write one of the Start Phase 2 presets; shared properties follow through their sync updates."""
    zbrush = preset == 'UNREAL_ZBRUSH'
    for name in ('phase2_auto_bake', 'phase2_mesh_auto_repair', 'phase2_repack_after_repair', 'phase2_repair_artifacts'):
        setattr(p, name, True)
    for name in SHARED_ON:
        setattr(p, name, True)
    p.phase2_run_engine = 'FAB'
    p.phase2_export_glb = False
    for name in HIGHPOLY_OPTIONS:
        setattr(p, name, zbrush)
    # Both presets fix the MID source and result; ZBrush also guards its HIGH remesh
    # (rebaked there). Retopo_01 itself is never guarded.
    p.phase2_run_topology_guard = zbrush
    p.phase2_run_zbrush = zbrush
    p.phase2_run_cleanup = zbrush


def active_start_preset(p):
    if p.phase2_run_zbrush and p.phase2_run_resculpt_retopo01:
        return 'UNREAL_ZBRUSH'
    if not p.phase2_run_zbrush and not p.phase2_run_resculpt_retopo01 and p.phase2_run_mode != 'IMPORT':
        return 'UNREAL'
    return ''


def draw_start_presets(layout, p):
    row = layout.row(align=True)
    active = active_start_preset(p)
    for key, label, _description in PRESETS:
        row.operator('object.polygroups_phase2_start_preset', text=label, depress=active == key,
                     icon='EXPORT' if key == 'UNREAL' else 'MOD_MULTIRES').preset = key


class OBJECT_OT_polygroups_phase2_start_preset(bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_start_preset'
    bl_label = 'Start Phase 2 Preset'
    bl_description = 'Set the Phase 2 passes for an Unreal export, optionally with Retopo_01 resculpting and ZBrush'
    bl_options = {'REGISTER', 'UNDO'}
    preset: bpy.props.EnumProperty(items=PRESETS)

    @classmethod
    def poll(cls, context):
        p = context.scene.polygroups_model_preparation_settings
        return not (p.phase2_pipeline_running or p.phase2_is_running or p.phase2_final_is_running
                    or p.phase2_auto_render_running or p.batch_is_running)

    def execute(self, context):
        apply_start_preset(context.scene.polygroups_model_preparation_settings, self.preset)
        return {'FINISHED'}


def asset_fields(p):
    unity = p.phase2_run_engine == 'UNITY'
    return (('unity_asset_name', 'unity_name_index', 'unity_asset_index') if unity else
            ('unreal_lod_asset_name', 'unreal_lod_name_index', 'unreal_lod_version_index'))


class OBJECT_OT_polygroups_phase2_confirm_start(bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_confirm_start'
    bl_label = 'Start Phase 2'
    bl_description = 'Check the Phase 2 passes, asset name, indices and export format, then start'
    bl_options = {'INTERNAL'}
    then: bpy.props.EnumProperty(items=(
        ('PHASE2', 'Start Phase 2', ''), ('IMPORT', 'Import then Phase 2', ''),
        ('IMPORT_SELECTED', 'Import selected then Phase 2', '')), options={'SKIP_SAVE'})

    def invoke(self, context, event):
        text = 'Start Phase 2' if self.then == 'PHASE2' else 'Import + Phase 2'
        return context.window_manager.invoke_props_dialog(self, width=460, confirm_text=text)

    def problems(self, context):
        p = context.scene.polygroups_model_preparation_settings
        s = context.scene.polygroups_mesh_finalization_settings
        found = []
        if p.phase2_run_prepare:
            asset, name_index, version_index = (getattr(s, field) for field in asset_fields(p))
            if not asset_name(asset):
                found.append('Enter an Asset Name')
            if not name_index.isdigit() or not version_index.isdigit():
                found.append('Name Index and Version Index must be numbers')
        if p.phase2_run_export and not (p.phase2_export_glb or p.phase2_export_fbx or p.phase2_export_gltf):
            found.append('Choose GLB or FBX')
        if not bpy.data.filepath:
            found.append('Save the blend file first')
        return found

    def draw(self, context):
        from .asset_translation import draw_asset_name
        from .index_step import draw_index
        from .phase2_pipeline_stages import selected_stages
        p = context.scene.polygroups_model_preparation_settings
        s = context.scene.polygroups_mesh_finalization_settings
        layout = self.layout
        layout.use_property_split = False
        draw_start_presets(layout, p)
        saves = layout.column(align=True)
        saves.prop(p, 'phase2_autosave')
        saves.prop(p, 'phase2_autosave_after_finish')
        fixes = layout.column(align=True)
        fixes.prop(p, 'phase2_run_loose_parts')
        fixes.prop(p, 'phase2_run_guard_highest')
        fixes.prop(p, 'phase2_run_uv_repair')
        fixes.prop(p, 'phase2_run_fix_source')
        if active_start_preset(p) == 'UNREAL_ZBRUSH':
            options = layout.column(align=True)
            options.prop(p, 'phase2_run_skip_rebake', icon='FF')
            guard = options.row()
            guard.enabled = not p.phase2_run_skip_rebake
            guard.prop(p, 'phase2_run_topology_guard')
        steps = layout.box()
        steps.label(text='Phase 2 will run', icon='INFO')
        for _key, label, _prop, _function in selected_stages(p):
            steps.label(text=label, icon='CHECKMARK')
        if self.then != 'PHASE2':
            steps.label(text='Starts after Import Processing finishes', icon='TIME')
        layout.prop(p, 'phase2_run_engine', expand=True)
        if p.phase2_run_prepare:
            asset, name_index, version_index = asset_fields(p)
            names = layout.column(align=True)
            draw_asset_name(names, context, s, asset, text='Asset Name')
            names.operator('object.polygroups_unity_load_from_file', text='Load from File', icon='FILE_BLEND').target = 'PHASE2'
            draw_index(names, s, name_index, 'Name Index')
            draw_index(names, s, version_index, 'Version Index')
        if p.phase2_run_export:
            row = layout.row(align=True)
            row.label(text='Export Format')
            row.prop(p, 'phase2_export_fbx', toggle=True)
            row.prop(p, 'phase2_export_glb', toggle=True)
        for problem in self.problems(context):
            layout.label(text=problem, icon='ERROR')

    def execute(self, context):
        problems = self.problems(context)
        if problems:
            self.report({'ERROR'}, problems[0])
            return {'CANCELLED'}
        p = context.scene.polygroups_model_preparation_settings
        s = context.scene.polygroups_mesh_finalization_settings
        if p.phase2_run_prepare:
            field = asset_fields(p)[0]
            setattr(s, field, asset_name(getattr(s, field)))
        if self.then == 'PHASE2':
            return bpy.ops.object.polygroups_start_phase2('INVOKE_DEFAULT')
        return bpy.ops.object.polygroups_batch_import(
            'EXEC_DEFAULT', use_file_selection=False, do_selected=self.then == 'IMPORT_SELECTED')


CLASSES = (OBJECT_OT_polygroups_phase2_start_preset, OBJECT_OT_polygroups_phase2_confirm_start)
