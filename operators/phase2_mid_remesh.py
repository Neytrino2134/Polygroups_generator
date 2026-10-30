"""MID remesh adapter for the cooperative Phase 2 queue."""
import math
import bmesh
import bpy
from ..core.remesh_job import RemeshJob, remesh_backend
from ..core.remesh_defaults import get_remesh_preset_counts
from ..pin_edges import pin_layer
from ..core.mesh_ngons import ngon_count, triangulated_ngon_copy
from .topology_guard import apply_topology_guard


def smart_seams_22(context, obj):
    if context.object and context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.hide_viewport = obj.hide_render = obj.hide_select = False
    obj.hide_set(False);obj.select_set(True)
    context.view_layer.objects.active = obj
    if obj.data.users > 1:
        obj.data = obj.data.copy()
    settings = context.scene.polygroups_seam_preparation_settings
    saved = settings.smart_seam_angle_limit, settings.smart_seam_replace
    try:
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data)
        pins = pin_layer(bm)
        for vertex in bm.verts:vertex.hide_set(False)
        for edge in bm.edges:
            edge.hide_set(False);edge.seam = False
            if pins is not None:edge[pins] = 0
        for face in bm.faces:
            face.hide_set(False)
            for uv in bm.loops.layers.uv.values():
                for loop in face.loops:loop[uv].pin_uv = False
        bmesh.update_edit_mesh(obj.data)
        bpy.ops.mesh.select_all(action='SELECT')
        settings.smart_seam_angle_limit = math.radians(22)
        settings.smart_seam_replace = True
        if 'FINISHED' not in bpy.ops.mesh.polygroups_mark_smart_angle_seams('EXEC_DEFAULT'):
            raise RuntimeError('Smart Seams Generator failed')
    finally:
        if context.object and context.object.mode != 'OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        settings.smart_seam_angle_limit, settings.smart_seam_replace = saved


class Phase2MidRemesh:
    def __init__(self, context, collection, report, source=None, preset='MID', result_name=None):
        from .phase2_processing import LOW
        candidates = [(int(m[1]), obj) for obj in collection.all_objects if obj.type=='MESH'
                      and obj.name.lower().startswith('retopo_') and (m := LOW.fullmatch(obj.name))]
        if not candidates:raise ValueError('MID Remesh requires a numbered Retopo mesh')
        self.source = source or max(candidates,key=lambda item:item[0])[1]
        if self.source.type != 'MESH' or not any(obj == self.source for obj in collection.all_objects):
            raise ValueError('Remesh source must be a mesh in the Generated collection')
        if preset not in {'MID', 'HIGH'}:
            raise ValueError(f'Unsupported remesh preset: {preset}')
        if result_name and bpy.data.objects.get(result_name) is not None:
            raise ValueError(f'Remesh output already exists: {result_name}')
        self.preset, self.result_name = preset, result_name
        self.source_visibility = self.source.hide_viewport,self.source.hide_render,self.source.hide_get()
        self.job = None;self.saved = [];self.finished = False
        self.report = report

    def start(self, context):
        backend = remesh_backend(context)
        if self.preset == 'HIGH' and ngon_count(self.source.data):
            if self.source.library or self.source.data.library or any(
                    mod.type == 'MULTIRES' and mod.total_levels for mod in self.source.modifiers):
                raise RuntimeError('HIGH Remesh requires local Retopo_01 n-gons without existing Multires levels')
            original_mesh = self.source.data
            prepared_mesh = triangulated_ngon_copy(original_mesh)
            self.source.data = prepared_mesh
            if original_mesh.users == 0 and not original_mesh.library:
                bpy.data.meshes.remove(original_mesh)
        smart_seams_22(context,self.source)
        p=context.scene.polygroups_model_preparation_settings;q=context.scene.qremesher
        for settings,name,value in ((q,'target_count',dict(get_remesh_preset_counts(context))[self.preset]),
                                    (q,'autodetect_hard_edges',False),(p,'remesh_auto_unwrap_checker',False)):
            self.saved.append((settings,name,getattr(settings,name)));setattr(settings,name,value)
        self.job = RemeshJob(backend,self.report)
        self.job.start(context)

    def poll(self):
        done, progress = self.job.poll()
        self.job.pipeline_progress = progress
        return done, progress

    def finish(self, context):
        objects=self.job.finish(context)
        meshes=[obj for obj in objects if obj.type=='MESH']
        if len(meshes)!=1:raise RuntimeError(f'{self.preset} Remesh must produce one mesh')
        result=meshes[0]
        smart_seams_22(context,result)
        guarded=self.topology_guard(context,result)
        if 'FINISHED' not in bpy.ops.object.polygroups_unwrap_angle_based('EXEC_DEFAULT'):
            raise RuntimeError(f'{self.preset} Remesh UV unwrap failed')
        if guarded and 'FINISHED' not in bpy.ops.object.polygroups_uvpackmaster_pack('EXEC_DEFAULT'):
            # Topology Guard is always followed by unwrap + UVPackmaster PACK.
            raise RuntimeError(f'{self.preset} Remesh UVPackmaster PACK failed')
        if self.result_name:
            result.name = self.result_name
            if result.name != self.result_name:
                raise RuntimeError(f'Remesh output name is occupied: {self.result_name}')
        self.finished=True
        self.restore()
        return result

    def topology_guard(self, context, result):
        """Make the new seams disks before the unwrap; only for the Unreal MID result, not the HIGH highpoly."""
        if self.preset != 'MID' or not context.scene.polygroups_model_preparation_settings.phase2_topology_guard_highest:
            return False
        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        result.select_set(True)
        context.view_layer.objects.active = result
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            found, _created, generated = apply_topology_guard(
                context, result, context.scene.polygroups_seam_finalization_settings,
                selected_only=False, unwrap=False)
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')
        if found.timed_out:
            self.report({'WARNING'}, f'{result.name}: Topology Guard stopped at its time limit')
        elif generated or found.knots:
            self.report({'INFO'}, f'{result.name}: Topology Guard collapsed {found.knots} knot(s), '
                                  f'added {generated} seam edge(s)')
        return True

    def restore(self):
        for settings,name,value in self.saved:setattr(settings,name,value)
        self.saved.clear()

    def abort(self):
        if self.job is not None and not self.finished:self.job.abort()
        self.restore()
        if not self.finished:
            try:
                self.source.hide_viewport,self.source.hide_render,hidden=self.source_visibility
                self.source.hide_set(hidden)
            except ReferenceError:pass
