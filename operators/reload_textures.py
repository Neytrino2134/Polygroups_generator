"""Reload every file-based image of the scene's assets from disk (Image > Reload for all textures)."""
import os

import bpy


def file_images():
    """Images stored on disk: not generated, packed, render results or viewer images."""
    for image in bpy.data.images:
        if image.source not in {'FILE', 'SEQUENCE', 'MOVIE'} or image.packed_file or image.type in {'RENDER_RESULT', 'COMPOSITING'}:
            continue
        if image.filepath:
            yield image


def reload_all_textures():
    """Returns (reloaded, missing) image counts; a missing file never stops the others."""
    reloaded, missing = 0, []
    for image in file_images():
        path = bpy.path.abspath(image.filepath, library=image.library)
        if not os.path.exists(path):
            missing.append(image.name)
            continue
        try:
            image.reload()
            reloaded += 1
        except RuntimeError:
            missing.append(image.name)
    return reloaded, missing


class OBJECT_OT_polygroups_reload_all_textures(bpy.types.Operator):
    bl_idname = 'object.polygroups_reload_all_textures'
    bl_label = 'Reload All Textures'
    bl_description = 'Reload the textures of all assets from disk, like Image > Reload for every file-based image'
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        p = context.scene.polygroups_model_preparation_settings
        return not (p.phase2_pipeline_running or p.phase2_is_running or p.phase2_auto_render_running
                    or p.phase2_final_is_running or p.batch_is_running)

    def execute(self, context):
        reloaded, missing = reload_all_textures()
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        if missing:
            shown = ', '.join(missing[:5]) + (f' and {len(missing) - 5} more' if len(missing) > 5 else '')
            self.report({'WARNING'}, f'Reloaded {reloaded} texture(s); file not found: {shown}')
        else:
            self.report({'INFO'}, f'Reloaded {reloaded} texture(s) from disk')
        return {'FINISHED'}
