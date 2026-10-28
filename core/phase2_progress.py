"""Phase 2 progress presentation shared by Start Phase 2 and Progress and Queue."""
import json
import bpy
import blf


def duration(seconds):
    seconds = max(0, int(seconds))
    return f'{seconds//3600:02d}:{seconds//60%60:02d}:{seconds%60:02d}'


def draw_pipeline_progress(layout, context, p):
    box = layout.box()
    box.label(text='Phase 2 | ' + (p.phase2_pipeline_state or 'Ready'), icon='INFO')
    box.progress(factor=p.phase2_pipeline_progress/100, type='BAR',
                 text=f'Overall {p.phase2_pipeline_progress:.1f}% | Stages {p.phase2_pipeline_done}/{p.phase2_pipeline_total}')
    box.progress(factor=p.phase2_pipeline_stage_progress/100, type='BAR', text=f'Current pass {p.phase2_pipeline_stage_progress:.1f}%')
    box.progress(factor=p.phase2_pipeline_detail_progress/100, type='BAR',
                 text=f'{p.phase2_pipeline_detail} | {p.phase2_pipeline_detail_progress:.1f}%')
    box.label(text=p.phase2_pipeline_status)
    box.label(text=f'Total {duration(p.phase2_pipeline_elapsed)} | Current pass {duration(p.phase2_pipeline_stage_seconds)}')
    box.label(text=f'Restore collection {duration(p.phase2_pipeline_collection_seconds)}')
    try:
        rows = json.loads(p.phase2_pipeline_queue)
        timings = json.loads(p.phase2_pipeline_collection_times)
    except ValueError:
        rows, timings = [], []
    icons = dict(DONE='CHECKMARK', FAILED='ERROR', RUNNING='TIME', PENDING='RADIOBUT_OFF',
                 STOPPED='CANCEL', SKIPPED='REMOVE')
    for item in rows:
        box.label(text=f'{item["label"]} | {item["state"]} | {item["progress"]:.0f}% | {duration(item["seconds"])}',
                  icon=icons.get(item['state'], 'INFO'))
    for item in timings[-4:]:
        box.label(text=f'{item["collection"]}: {duration(item["seconds"])}')
    if p.phase2_pipeline_running:
        row = box.row(align=True)
        if p.phase2_pipeline_paused:
            row.operator('object.polygroups_phase2_pipeline_control', text='Resume', icon='PLAY').action = 'RESUME'
        else:
            row.operator('object.polygroups_phase2_pipeline_control', text='Pause after Current', icon='PAUSE').action = 'PAUSE'
        row = box.row(align=True)
        row.operator('object.polygroups_phase2_pipeline_control', text='Stop after Stage').action = 'STOP_STAGE'
        row.operator('object.polygroups_phase2_pipeline_control', text='Stop Now', icon='CANCEL').action = 'STOP_NOW'


def draw_start(layout, context, p):
    controls_enabled = not (p.phase2_pipeline_running or p.batch_is_running or p.phase2_is_running
                           or p.phase2_final_is_running or p.phase2_auto_render_running or p.phase2_rebake_queue_running
                           or p.phase2_relod_running or context.scene.polygroups_mesh_finalization_settings.smart_lods_is_running)
    start = layout.column(align=True)
    start.enabled = controls_enabled
    start.operator('object.polygroups_start_phase2', text='Start Phase 2 Process', icon='PLAY')
    recovery = layout.row()
    recovery.operator('object.polygroups_phase2_reset_state', text='Reset State', icon='FILE_REFRESH')
    from ..ui_panels.common import draw_collapsible_box
    from ..localization import t
    process = draw_collapsible_box(layout, p, 'phase2_show_process_settings',
                                   t(context, 'phase2_process_settings'), 'PREFERENCES')
    if process is not None:
        controls = process.column(align=True)
        controls.enabled = controls_enabled
        draw_process_settings(controls, context, p)
    unity = p.phase2_run_engine == 'UNITY'
    rebake = draw_collapsible_box(layout, p, 'phase2_show_rebake', 'Rebake Final Mesh', 'FILE_REFRESH')
    if rebake is not None:
        draw_rebake(rebake, context, p)
    rename = draw_collapsible_box(layout, p, 'phase2_show_rename_final', 'Rename Final Mesh', 'SORTALPHA')
    if rename is not None:
        controls = rename.column(align=True)
        controls.enabled = controls_enabled and not context.scene.polygroups_baking_settings.bake_task_is_running
        for name in ('phase2_rename_asset', 'phase2_rename_name_index', 'phase2_rename_version_index'):
            controls.prop(p, name)
        rename.label(text='All prepared asset collections in this scene', icon='INFO')
        controls.prop(p, 'phase2_rename_fbx')
        controls.prop(p, 'phase2_rename_blend')
        controls.prop(p, 'phase2_rename_json')
        rename.label(text='Export pipeline: ' + ('Unity' if unity else 'Unreal / FAB'))
        controls.operator('object.polygroups_rename_final_meshes', text='Rename Final Meshes', icon='SORTALPHA')
    relod = draw_collapsible_box(layout, p, 'phase2_show_relod', 'ReLOD', 'MOD_DECIM')
    if relod is not None:
        controls = relod.column(align=True)
        controls.enabled = controls_enabled and not context.scene.polygroups_baking_settings.bake_task_is_running
        controls.prop(p, 'phase2_relod_delete_current_lods')
        controls.prop(p, 'phase2_relod_reexport')
        controls.prop(p, 'phase2_relod_json')
        controls.prop(context.scene.polygroups_mesh_finalization_settings, 'smart_lods_smart_arrange')
        controls.prop(p, 'phase2_relod_method')
        if p.phase2_relod_method == 'UV_PRESERVE':
            controls.prop(p, 'phase2_relod_seam_mode')
        controls.label(text='All _MID / _HIGH meshes in scene (MID preferred)', icon='INFO')
        controls.label(text='Uses Smart LOD count and triangle budgets')
        controls.operator('object.polygroups_relod', text='Re-create LODs', icon='FILE_REFRESH')
    status = draw_collapsible_box(layout, p, 'phase2_show_status', 'Status and Statistics', 'INFO')
    if status is not None:
        draw_start_status(status, context, p)


def draw_process_settings(options, context, p):
    options.prop(p, 'phase2_run_restore')
    sub = options.column(align=True)
    sub.enabled = p.phase2_run_restore
    sub.label(text='Restore Mode')
    modes = sub.row(align=True)
    for value, label in (('IMPORT', 'Import Only'), ('REBAKE', 'Import + Rebake')):
        mode = modes.operator('wm.context_set_enum', text=label,
                              depress=(p.phase2_run_mode == 'IMPORT') == (value == 'IMPORT'))
        mode.data_path = 'scene.polygroups_model_preparation_settings.phase2_run_mode'
        mode.value = value
    sub.prop(p, 'phase2_run_mid')
    resculpt = sub.column(align=True)
    resculpt.enabled = p.phase2_run_mode != 'IMPORT'
    resculpt.prop(p, 'phase2_run_resculpt_retopo01')
    steps = resculpt.column(align=True)
    steps.enabled = p.phase2_run_resculpt_retopo01
    steps.prop(p, 'phase2_run_high_remesh')
    steps.prop(p, 'phase2_run_repair_resculpt')
    steps.prop(p, 'phase2_run_bake_resculpt')
    options.separator(type='LINE')
    options.prop(p, 'phase2_run_prepare')
    options.prop(p, 'phase2_run_engine', expand=True)
    s = context.scene.polygroups_mesh_finalization_settings
    unity = p.phase2_run_engine == 'UNITY'
    sub = options.column(align=True)
    sub.enabled = p.phase2_run_prepare
    sub.prop(s, 'unity_asset_name' if unity else 'unreal_lod_asset_name', text='Asset Name')
    sub.prop(s, 'unity_name_index' if unity else 'unreal_lod_name_index', text='Name Index')
    sub.prop(s, 'unity_asset_index' if unity else 'unreal_lod_version_index', text='Version Index')
    sub.operator('object.polygroups_unity_load_from_file', text='Load from File', icon='FILE_BLEND').target = 'PHASE2'
    options.prop(p, 'phase2_run_export')
    sub = options.row(align=True)
    sub.enabled = p.phase2_run_export
    sub.prop(p, 'phase2_export_glb')
    sub.prop(p, 'phase2_export_fbx')
    options.prop(p, 'phase2_run_blend')
    sub = options.column(align=True)
    sub.enabled = p.phase2_run_blend
    sub.prop(p, 'phase2_blend_export_generated')
    highpoly = sub.row()
    highpoly.enabled = p.phase2_blend_export_generated
    highpoly.prop(p, 'phase2_blend_export_highpoly')
    options.prop(p, 'phase2_run_zbrush')
    from ..localization import t
    zbrush = options.column(align=True)
    zbrush.enabled = p.phase2_run_zbrush
    zbrush.prop(p, 'phase2_run_zbrush_at_end', text=t(context, 'phase2_zbrush_at_end'))
    options.prop(p, 'phase2_run_cleanup')
    options.separator(type='LINE')
    options.prop(p, 'phase2_run_render')
    sub = options.column(align=True)
    sub.enabled = p.phase2_run_render
    mode = sub.row()
    mode.enabled = not p.phase2_auto_skip_scene
    mode.prop(p, 'phase2_run_transparent')
    sub.prop(p, 'phase2_auto_skip_scene')


def draw_rebake(layout, context, p):
    manual = layout.column(align=True)
    manual.operator_context = 'INVOKE_DEFAULT'
    manual.enabled = not (context.scene.polygroups_baking_settings.bake_task_is_running
        or p.phase2_pipeline_running or p.batch_is_running or p.phase2_is_running
        or p.phase2_final_is_running or p.phase2_auto_render_running or p.phase2_rebake_queue_running
        or p.phase2_relod_running or context.scene.polygroups_mesh_finalization_settings.smart_lods_is_running)
    rebake = manual.operator('object.polygroups_rebake_final_mesh', text='ReBake Final Mesh', icon='FILE_REFRESH')
    rebake.create_lods = p.phase2_rebake_create_lods
    rebake.export_selected = p.phase2_rebake_create_lods and p.phase2_rebake_export_selected
    rebake.repair_mesh = p.phase2_rebake_repair_mesh
    rebake.use_queue = True
    rebake.delete_current_lods = p.phase2_rebake_delete_current_lods
    queue = manual.box()
    queue.label(text=f'ReBake Queue: {len(p.phase2_rebake_queue)} mesh(es)')
    controls = queue.row(align=True)
    controls.operator('object.polygroups_rebake_queue_edit',text='Add to Queue',icon='ADD').action='ADD'
    controls.operator('object.polygroups_rebake_queue_edit',text='Clear List',icon='TRASH').action='CLEAR'
    icons = dict(DONE='CHECKMARK',FAILED='ERROR',RUNNING='TIME',CANCELLED='CANCEL')
    for index,entry in enumerate(p.phase2_rebake_queue):
        row=queue.row(align=True)
        row.label(text=f'{index+1}. {entry.target.name if entry.target else "Missing mesh"}',
                  icon=icons.get(entry.state,'RADIOBUT_OFF'))
        remove=row.operator('object.polygroups_rebake_queue_edit',text='',icon='X')
        remove.action,remove.index='REMOVE',index
        if entry.message and entry.state=='FAILED':
            queue.label(text=entry.message,icon='ERROR')
    manual.prop(p, 'phase2_rebake_repair_mesh')
    if p.phase2_rebake_repair_mesh:
        repair = manual.column(align=True)
        for name in ('phase2_rebake_repair_folds','phase2_rebake_repair_coincident',
                     'phase2_rebake_repair_zero_area','phase2_rebake_repair_stretched'):
            repair.prop(p,name)
        if p.phase2_rebake_repair_stretched:
            repair.prop(p,'fold_repair_stretch_ratio')
        repair.prop(p,'phase2_rebake_repack_uv')
    manual.prop(p, 'phase2_rebake_delete_current_lods')
    manual.prop(p, 'phase2_rebake_create_lods')
    exports = manual.column(align=True)
    exports.enabled = p.phase2_rebake_create_lods
    exports.prop(p, 'phase2_rebake_export_selected')


def draw_start_status(layout, context, p):
    from ..localization import t
    draw_pipeline_progress(layout, context, p)
    if p.phase2_status:
        layout.label(text=p.phase2_status, icon='INFO')
    if p.phase2_final_is_running or p.phase2_auto_render_running or p.phase2_final_progress:
        layout.progress(factor=p.phase2_final_progress/100, type='BAR', text=f'{p.phase2_final_progress:.0f}%')
    if p.phase2_total_count:
        layout.progress(factor=(p.phase2_done_count+p.phase2_failed_count)/p.phase2_total_count,
                        type='BAR', text=t(context, 'phase2_progress', done=p.phase2_done_count,
                        failed=p.phase2_failed_count, total=p.phase2_total_count))
    if p.phase2_is_running:
        layout.operator('object.polygroups_phase2_stop', text=t(context, 'phase2_stop'), icon='PAUSE')
    if p.phase2_final_is_running or p.phase2_auto_render_running:
        layout.operator('object.polygroups_stop_lod_job', icon='CANCEL')
    layout.label(text='ReBake: '+p.phase2_rebake_queue_status)
    if p.phase2_rebake_queue_running or p.phase2_rebake_queue_progress:
        layout.progress(factor=p.phase2_rebake_queue_progress/100, type='BAR', text=p.phase2_rebake_queue_status)
    if p.phase2_rebake_queue_running:
        layout.operator('object.polygroups_stop_lod_job', text='Stop after Current Mesh', icon='CANCEL')
    layout.label(text=f'ReLOD: {p.phase2_relod_status} | {p.phase2_relod_done}/{p.phase2_relod_total}')
    if p.phase2_relod_running or p.phase2_relod_progress:
        layout.progress(factor=p.phase2_relod_progress/100, type='BAR', text=p.phase2_relod_status)
    if p.phase2_relod_running:
        layout.operator('object.polygroups_stop_lod_job', text='Stop ReLOD', icon='CANCEL')
    layout.label(text='Rename: '+p.phase2_rename_status)


class PipelineOverlay:
    def __init__(self, context):
        self.scene = context.scene
        self.handle = None
        if not bpy.app.background:
            self.handle = bpy.types.SpaceView3D.draw_handler_add(self.draw, (), 'WINDOW', 'POST_PIXEL')

    def draw(self):
        if bpy.context.scene != self.scene:
            return
        p = self.scene.polygroups_model_preparation_settings
        scale = bpy.context.preferences.system.ui_scale
        lines = [f'Phase 2: {p.phase2_pipeline_progress:.1f}% | Stages {p.phase2_pipeline_done}/{p.phase2_pipeline_total}',
                 p.phase2_pipeline_status,
                 f'{p.phase2_pipeline_detail}: {p.phase2_pipeline_detail_progress:.1f}%',
                 f'Total {duration(p.phase2_pipeline_elapsed)} | Pass {duration(p.phase2_pipeline_stage_seconds)} | Collection {duration(p.phase2_pipeline_collection_seconds)}']
        blf.size(0, 14*scale)
        for i, line in enumerate(reversed(lines)):
            x, y = 18*scale, (20+i*21)*scale
            blf.color(0, 0, 0, 0, 1)
            blf.position(0, x+1, y-1, 0)
            blf.draw(0, line)
            blf.color(0, 1, 1, 1, 1)
            blf.position(0, x, y, 0)
            blf.draw(0, line)

    def close(self):
        if self.handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self.handle, 'WINDOW')
            self.handle = None
