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
        if close_window(window):
            closed += 1
    return closed


def close_window(window):
    """Blender 5.x refuses to override the context with a temporary screen (TypeError); try the
    plain window override, and when Blender still refuses leave the window open: a window that
    cannot be closed must never stop the render queue."""
    for override in (dict(window=window), dict(window=window, screen=window.screen)):
        try:
            with bpy.context.temp_override(**override):
                bpy.ops.wm.window_close()
            return True
        except Exception:
            continue
    return False
