"""Inspect or repair folds, collapsed edges and singleton UV outliers transactionally."""
import bmesh
import bpy

from ..core.mesh_fold_repair import repair_local_folds, inspect_triangle_quality
from ..localization import t


class MESH_OT_polygroups_repair_mesh_folds(bpy.types.Operator):
    bl_idname = 'mesh.polygroups_repair_mesh_folds'
    bl_label = 'Repair Mesh Folds'
    bl_description = ('Repair local folds, zero-length edges and enabled singleton triangle '
                      'UV outliers while preserving surrounding topology and UV seams')
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.EnumProperty(items=(
        ('REPAIR', 'Repair', 'Repair the active mesh'),
        ('SELECT_QUALITY', 'Find Thin / UV', 'Inspect thin triangles and distorted UV without changing them'),
        ('SELECT', 'Find Problems', 'Select repairable patches without changing geometry')),
        default='REPAIR')
    fix_folds: bpy.props.BoolProperty(name='Repair Folded Pockets', default=True,
        description='Repair folded pockets and merge flat, twisted or crossed-quad tips without moving neighboring vertices')
    fix_degenerate: bpy.props.BoolProperty(name='Merge Coincident Vertices', default=True,
        description='Collapse only near-zero edges belonging to degenerate triangles')
    fix_zero_area: bpy.props.BoolProperty(name='Repair Zero Area at UV Seams', default=False,
        description='Merge identical endpoints of zero-area faces; preserve corner UVs and union seam/sharp flags')
    selected_only: bpy.props.BoolProperty(name='Selected Area Only', default=False,
        description='Use selected defect faces as seeds; include the minimal surrounding patch')
    fix_stretched_triangles: bpy.props.BoolProperty(name='Merge Stretched Single Triangles', default=True,
        description='Find single-face triangle UV islands with extreme scale/stretch and weld their vertices to the face center when the surrounding surface stays valid')
    stretched_triangle_ratio: bpy.props.FloatProperty(name='Triangle Stretch Ratio', default=50, min=2, max=10000,
        description='Minimum UV anisotropy or linear texel-scale ratio to neighboring faces for a singleton triangle')
    thin_quality: bpy.props.FloatProperty(name='Thin Triangle Quality', default=.01, min=.000001, max=.5,
        description='Scale-independent quality: 1 is equilateral, 0 is degenerate')
    uv_stretch: bpy.props.FloatProperty(name='UV Stretch Ratio', default=50, min=1.1, max=10000,
        description='Maximum UV Jacobian singular-value ratio before flagging a triangle')

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.mode in {'OBJECT', 'EDIT'}

    def execute(self, context):
        obj = context.active_object
        edit = obj.mode == 'EDIT'
        if (obj.data.users != 1 or (edit and len(context.objects_in_mode) != 1)
                or obj.data.library or (self.action == 'REPAIR' and obj.data.shape_keys)):
            self.report({'ERROR'}, t(context, 'fold_repair_single_mesh'))
            return {'CANCELLED'}
        if self.selected_only and not edit:
            self.report({'ERROR'}, t(context, 'fold_repair_selection_mode'))
            return {'CANCELLED'}
        source = bmesh.from_edit_mesh(obj.data) if edit else bmesh.new()
        if not edit:
            source.from_mesh(obj.data)
        work = source.copy()
        try:
            if self.action == 'SELECT_QUALITY':
                affected, quality = inspect_triangle_quality(
                    work, self.selected_only, self.thin_quality, self.uv_stretch)
                result = dict(affected=affected, folds=0, collapsed=0, remaining_degenerate=0)
            else:
                result = repair_local_folds(work, self.fix_folds, self.fix_degenerate,
                    self.selected_only, fix_zero_area=self.fix_zero_area,
                    fix_stretched_triangles=self.fix_stretched_triangles,
                    stretched_triangle_ratio=self.stretched_triangle_ratio)
            if self.action in {'SELECT', 'SELECT_QUALITY'}:
                source.select_mode = {'FACE'}
                context.tool_settings.mesh_select_mode = (False, False, True)
                for seq in (source.faces, source.edges, source.verts):
                    for item in seq:
                        item.select_set(False)
                source.faces.index_update()
                for face in source.faces:
                    if face.index in result['affected']:
                        face.select_set(True)
                source.select_flush_mode()
                if edit:
                    bmesh.update_edit_mesh(obj.data, destructive=False)
                else:
                    source.to_mesh(obj.data)
                    bpy.ops.object.mode_set(mode='EDIT')
            elif result['folds'] or result['collapsed'] or result.get('stretched'):
                # Only the validated working mesh reaches the user's datablock.
                if edit:
                    bpy.ops.object.mode_set(mode='OBJECT')
                work.to_mesh(obj.data)
                obj.data.update()
                if edit:
                    bpy.ops.object.mode_set(mode='EDIT')
            if self.action == 'SELECT_QUALITY':
                self.report({'INFO'}, t(context, 'fold_repair_quality_result', **quality))
            else:
                self.report({'INFO'}, t(context, 'fold_repair_result',
                    folds=result['folds'], collapsed=result['collapsed'],
                    stretched=result.get('stretched', 0),
                    zero=result.get('remaining_zero_triangles', 0),
                    remaining=max(0, result['remaining_degenerate'] - result.get('remaining_zero_triangles', 0)),
                    action=t(context, 'fold_repair_found' if self.action == 'SELECT' else 'fold_repair_fixed')))
        except (ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        finally:
            work.free()
            if not edit:
                source.free()
        return {'FINISHED'}
