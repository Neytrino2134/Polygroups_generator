"""Close the temporary Blender Render window once a render has finished."""
import bpy


def is_render_window(window):
    screen = window.screen
    if not screen.is_temporary:
        return False
    for area in screen.areas:
        if area.type == 'IMAGE_EDITOR':
            image = getattr(area.spaces.active, 'image', None)
            if image is not None and image.type == 'RENDER_RESULT':
                return True
    return False


def close_render_windows():
    """Close every temporary Render window; returns how many were closed. Call only when no render is running."""
    if bpy.app.background or bpy.app.is_job_running('RENDER'):
        return 0
    closed = 0
    manager = bpy.context.window_manager
    for window in list(manager.windows):
        if not is_render_window(window):
            continue
        try:
            with bpy.context.temp_override(window=window, screen=window.screen):
                bpy.ops.wm.window_close()
            closed += 1
        except (RuntimeError, ReferenceError):
            pass
    return closed
