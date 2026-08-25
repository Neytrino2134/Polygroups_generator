import os

import bpy

from .localization import get_preferences


_DEVICE = None
_HANDLES = []


def _notification_sound_path():
    return os.path.join(os.path.dirname(__file__), "Source", "Notification.mp3")


def play_operation_done_sound(context=None):
    preferences = get_preferences(context or bpy.context)
    if not getattr(preferences, "play_sound_after_operations", True):
        return

    path = _notification_sound_path()
    if not os.path.exists(path):
        return

    try:
        import aud

        global _DEVICE
        if _DEVICE is None:
            _DEVICE = aud.Device()
        handle = _DEVICE.play(aud.Sound(path))
        _HANDLES.append(handle)
        del _HANDLES[:-8]
    except Exception:
        pass
