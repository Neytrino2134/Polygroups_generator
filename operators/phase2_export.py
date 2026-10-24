"""Select prepared collections and delegate to the section-12 exporters."""
import re
import bpy
from .phase2_processing import available
from .rename_objects import ensure_collection_visible_in_view_layer


def prepared_meshes(context):
    result = set()
    for col in context.scene.collection.children_recursive:
        if not col.name.endswith('_Collection'):
            continue
        for obj in col.all_objects:
            if (obj.type == 'MESH' and not obj.get('polygroups_render_multiview')
                    and not obj.get('polygroups_texture_plane')
                    and (re.search(r'_(MID|HIGH|LOD\d+)$', obj.name, re.I) or obj.get('unity_prepared'))):
                result.add(obj)
    return sorted(result, key=lambda obj: obj.name.casefold())


class OBJECT_OT_polygroups_phase2_export(bpy.types.Operator):
    bl_idname = 'object.polygroups_phase2_export'
    bl_label = 'Export Prepared Models'
    bl_description = 'Select prepared MID/HIGH/LOD meshes in all scene _Collection assets and use section 12 export'

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and available(context)

    def execute(self, context):
        p = context.scene.polygroups_model_preparation_settings
        s = context.scene.polygroups_mesh_finalization_settings
        if not any((p.phase2_export_fbx, p.phase2_export_glb, p.phase2_export_gltf)):
            self.report({'WARNING'}, 'Enable FBX, GLB or GLTF')
            return {'CANCELLED'}
        meshes = prepared_meshes(context)
        if not meshes:
            p.phase2_export_status = 'No prepared meshes in scene _Collection assets'
            self.report({'WARNING'}, p.phase2_export_status)
            return {'CANCELLED'}
        for obj in meshes:
            for col in obj.users_collection:
                if col in context.scene.collection.children_recursive:
                    ensure_collection_visible_in_view_layer(context, col)
            obj.hide_viewport = obj.hide_select = False
            obj.hide_set(False)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in meshes:
            obj.select_set(True)
        context.view_layer.objects.active = meshes[0]
        unity = p.phase2_export_engine == 'UNITY'
        prefix = 'unity_export_' if unity else 'mesh_export_'
        fields = {prefix+'fbx': p.phase2_export_fbx, prefix+'glb': p.phase2_export_glb,
                  prefix+'gltf': p.phase2_export_gltf, prefix+'info_format': 'JSON' if p.phase2_export_json else 'NONE'}
        if not unity:
            fields['mesh_export_sort'] = p.phase2_export_sort
        else:
            # Autosave before temporary export overrides, preserving section-12
            # settings on disk as well as restoring them in memory afterward.
            fields['unity_export_autosave'] = False
        saved = {name: (getattr(s, name), s.is_property_set(name)) for name in fields}
        try:
            if unity and saved['unity_export_autosave'][0]:
                if 'FINISHED' not in bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath):
                    raise RuntimeError('Autosave before Unity export failed')
            for name, value in fields.items():
                setattr(s, name, value)
            p.phase2_export_status = f'Exporting {len(meshes)} prepared meshes'
            p.phase2_status = p.phase2_export_status
            p.phase2_final_progress = 0
            if unity:
                result = bpy.ops.object.polygroups_export_unity('EXEC_DEFAULT', batch_prepared=True, batch_sort=p.phase2_export_sort)
            else:
                result = bpy.ops.object.polygroups_export_selected_meshes('EXEC_DEFAULT')
            p.phase2_export_status = (f'Exported {len(meshes)} meshes | {p.phase2_export_engine}'
                                      if 'FINISHED' in result else 'Export failed')
            p.phase2_status = p.phase2_export_status
            p.phase2_final_progress = 100 if 'FINISHED' in result else 0
            return result
        except (RuntimeError, ValueError, OSError) as error:
            p.phase2_export_status = 'Export failed: ' + str(error)
            p.phase2_status = p.phase2_export_status
            self.report({'ERROR'}, p.phase2_export_status)
            return {'CANCELLED'}
        finally:
            for name, (value, was_set) in saved.items():
                setattr(s, name, value) if was_set else s.property_unset(name)
