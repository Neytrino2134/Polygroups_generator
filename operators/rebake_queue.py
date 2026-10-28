"""Manual final-mesh queue; each asset completes repair/bake/LODs/export first."""
from contextlib import contextmanager
import bpy

from .sequential_jobs import SequentialJob
from .rebake_final import MID_PATTERN, FinalRebakeSession


@contextmanager
def child_dispatch():
    from . import sequential_jobs
    job = sequential_jobs.ACTIVE_JOB
    owned = job is not None and (getattr(job, '_is_rebake_queue', False) or getattr(job, '_is_relod', False))
    previous = getattr(job, '_rebake_dispatching', False) if owned else False
    if owned:
        job._rebake_dispatching = True
    try:
        yield
    finally:
        if owned:
            job._rebake_dispatching = previous


def editable(context):
    from . import sequential_jobs, phase2_pipeline, phase2_processing, import_queue, remesh_progress
    p = context.scene.polygroups_model_preparation_settings
    return (sequential_jobs.ACTIVE_JOB is None and phase2_pipeline.ACTIVE_PIPELINE is None
        and phase2_processing.ACTIVE_PHASE2 is None and import_queue.ACTIVE_QUEUE is None
        and remesh_progress.ACTIVE_REMESH is None and not p.phase2_rebake_queue_running
        and not p.phase2_final_is_running and not p.phase2_auto_render_running
        and not p.batch_is_running and not p.phase2_is_running and not p.phase2_pipeline_running
        and not context.scene.polygroups_baking_settings.bake_task_is_running
        and not context.scene.polygroups_render_settings.is_running)


class OBJECT_OT_polygroups_rebake_queue_edit(bpy.types.Operator):
    bl_idname = 'object.polygroups_rebake_queue_edit'
    bl_label = 'Edit ReBake Queue'
    bl_options = {'REGISTER', 'UNDO'}
    action: bpy.props.EnumProperty(items=(('ADD','Add to Queue','Add selected final MID meshes'),
        ('REMOVE','Remove','Remove one queue entry'),('CLEAR','Clear Queue','Remove all queue entries')))
    index: bpy.props.IntProperty(default=-1)

    @classmethod
    def poll(cls,context):
        return editable(context)

    def execute(self,context):
        p = context.scene.polygroups_model_preparation_settings
        if self.action == 'CLEAR':
            p.phase2_rebake_queue.clear()
        elif self.action == 'REMOVE':
            if not 0 <= self.index < len(p.phase2_rebake_queue):
                return {'CANCELLED'}
            p.phase2_rebake_queue.remove(self.index)
        else:
            targets = sorted((obj for obj in context.selected_objects
                              if obj.type == 'MESH' and MID_PATTERN.fullmatch(obj.name)),key=lambda obj:obj.name.casefold())
            if not targets:
                self.report({'WARNING'},'Select a final mesh named SM_..._NN_MID')
                return {'CANCELLED'}
            existing = {entry.target for entry in p.phase2_rebake_queue if entry.target}
            for target in targets:
                if target not in existing:
                    p.phase2_rebake_queue.add().target = target
                    existing.add(target)
        p.phase2_rebake_queue_status = f'{len(p.phase2_rebake_queue)} mesh(es) queued'
        p.phase2_rebake_queue_progress = 0
        return {'FINISHED'}


class OBJECT_OT_polygroups_rebake_queue_run(SequentialJob,bpy.types.Operator):
    bl_idname = 'object.polygroups_rebake_queue_run'
    bl_label = 'ReBake Final Mesh Queue'
    phase2_job = True
    phase2_running_property = 'phase2_rebake_queue_running'
    _is_rebake_queue = True
    _rebake_dispatching = False
    repair_mesh: bpy.props.BoolProperty(default=True,options={'SKIP_SAVE'})
    delete_current_lods: bpy.props.BoolProperty(default=False,options={'SKIP_SAVE'})
    create_lods: bpy.props.BoolProperty(default=False,options={'SKIP_SAVE'})
    export_selected: bpy.props.BoolProperty(default=False,options={'SKIP_SAVE'})

    @classmethod
    def poll(cls,context):
        return editable(context) and bool(context.scene.polygroups_model_preparation_settings.phase2_rebake_queue)

    def execute(self,context):
        p = context.scene.polygroups_model_preparation_settings
        self.entries = list(p.phase2_rebake_queue)
        self.current = None
        try:
            # Complete read-only preflight for the list before changing any mesh.
            for entry in self.entries:
                self.current = entry
                if entry.target is None or entry.target.name not in context.scene.objects:
                    raise ValueError('Queued mesh is missing from the current scene')
                FinalRebakeSession(context,entry.target,context.scene.polygroups_baking_settings,
                    create_lods=self.create_lods,export_selected=self.export_selected,repair_mesh=self.repair_mesh,
                    delete_current_lods=self.delete_current_lods,use_selection=False)
            for entry in self.entries:
                entry.state,entry.message = 'PENDING',''
            self.current = None
        except (ValueError,RuntimeError) as error:
            if self.current is not None:
                self.current.state,self.current.message = 'FAILED',str(error)
            p.phase2_rebake_queue_status = 'Preflight failed: ' + str(error)
            self.report({'ERROR'},p.phase2_rebake_queue_status)
            return {'CANCELLED'}
        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        return self.start_job(context,self.steps(context),modal=not bpy.app.background)

    def update_job(self,context,fraction,message):
        p = self._job_scene.polygroups_model_preparation_settings
        p.phase2_rebake_queue_progress = max(0,min(100,100*fraction))
        p.phase2_rebake_queue_status = message
        context.window_manager.progress_update(p.phase2_rebake_queue_progress)
        from .import_queue import redraw
        redraw(context)

    def advance_job(self,context):
        if self.stop_requested and context.scene.polygroups_baking_settings.bake_task_is_running:
            context.scene.polygroups_model_preparation_settings.phase2_rebake_queue_status = 'Stopping after current mesh'
            return {'RUNNING_MODAL'}
        return super().advance_job(context)

    def steps(self,context):
        from .phase2_zbrush_export import export_visibility
        bake = context.scene.polygroups_baking_settings
        total = len(self.entries)
        for index,entry in enumerate(self.entries):
            self.current = entry
            target = entry.target
            entry.state,entry.message = 'RUNNING',''
            try:
                if target is None or target.name not in context.scene.objects:
                    raise ValueError('Queued mesh is missing from the current scene')
                with export_visibility(context,target):
                    bpy.ops.object.select_all(action='DESELECT')
                    target.select_set(True)
                    context.view_layer.objects.active = target
                    with child_dispatch():
                        result = bpy.ops.object.polygroups_bake_task('INVOKE_DEFAULT',prepare_materials=True,
                            rebake_final=True,rebake_repair_mesh=self.repair_mesh,
                            rebake_delete_current_lods=self.delete_current_lods,
                            rebake_create_lods=self.create_lods,rebake_export_selected=self.export_selected)
                    if not {'FINISHED','RUNNING_MODAL'} & result:
                        raise RuntimeError(bake.bake_task_message or 'ReBake could not start')
                    while bake.bake_task_is_running:
                        yield (index+bake.bake_task_progress/100)/total, f'{index+1}/{total}: {target.name} | {bake.bake_task_message}'
                    if bake.bake_task_stage != 'DONE':
                        raise RuntimeError(bake.bake_task_message or 'ReBake failed')
                entry.state,entry.message = 'DONE',bake.bake_task_message
            except Exception as error:
                entry.state,entry.message = 'FAILED',str(error)
                raise
            yield (index+1)/total,f'{index+1}/{total}: {target.name} completed'
        self.current = None

    def finish_job(self,context,stopped=False,error=''):
        if getattr(self,'_job_done',False):
            return self._job_result
        bake = self._job_scene.polygroups_baking_settings
        if self.current is not None and self.current.state == 'RUNNING':
            self.current.state = 'DONE' if bake.bake_task_stage == 'DONE' else 'FAILED' if error else 'CANCELLED'
            self.current.message = error or bake.bake_task_message
        result = super().finish_job(context,stopped=stopped,error=error)
        p = self._job_scene.polygroups_model_preparation_settings
        p.phase2_rebake_queue_status = ('Failed: '+error if error else 'Stopped' if stopped else
                                       f'Completed {len(self.entries)} mesh(es)')
        if not stopped and not error:
            p.phase2_rebake_queue_progress = 100
        return result


CLASSES = (OBJECT_OT_polygroups_rebake_queue_edit,OBJECT_OT_polygroups_rebake_queue_run)
