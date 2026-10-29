"""Name Index / Version Index fields with left and right arrows that step the value by 01."""
import bpy

from .unity_export_workflow import step_naming_index

OWNERS = {
    'FINALIZATION': lambda context: context.scene.polygroups_mesh_finalization_settings,
    'PREPARATION': lambda context: context.scene.polygroups_model_preparation_settings,
}


def draw_index(layout, settings, field, text=None, owner='FINALIZATION'):
    """Draw ``field`` of ``settings`` between decrease / increase arrows."""
    row = layout.row(align=True)

    def arrow(icon, delta):
        button = row.operator('object.polygroups_step_naming_index', text='', icon=icon)
        button.owner, button.field, button.delta = owner, field, delta

    arrow('TRIA_LEFT', -1)
    row.prop(settings, field, text=text)
    arrow('TRIA_RIGHT', 1)
    return row


class OBJECT_OT_polygroups_step_naming_index(bpy.types.Operator):
    bl_idname = 'object.polygroups_step_naming_index'
    bl_label = 'Step Index'
    bl_description = 'Change the index by 1'
    bl_options = {'UNDO', 'INTERNAL'}
    owner: bpy.props.EnumProperty(items=(('FINALIZATION', '', ''), ('PREPARATION', '', '')), options={'SKIP_SAVE'})
    field: bpy.props.StringProperty(options={'SKIP_SAVE'})
    delta: bpy.props.IntProperty(default=1, options={'SKIP_SAVE'})

    def execute(self, context):
        settings = OWNERS[self.owner](context)
        if self.field not in settings.bl_rna.properties:
            return {'CANCELLED'}
        value = getattr(settings, self.field)
        setattr(settings, self.field, step_naming_index(value, self.delta, self.field.endswith('name_index')))
        return {'FINISHED'}


CLASSES = (OBJECT_OT_polygroups_step_naming_index,)
