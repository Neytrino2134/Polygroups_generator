"""Flat surfaces and blue/cyan accents. Values are display RGB for POST_PIXEL."""
def rgba(value, alpha=1):
    return tuple(int(value[i:i+2], 16) / 255 for i in (0, 2, 4)) + (alpha,)


BACKGROUND = rgba('10191F')
SURFACE = rgba('152127')
RAISED = rgba('202E37')
BORDER = rgba('31434F')
TEXT = rgba('EAF3FF')
MUTED = rgba('9EB3C5')
SELECTED = rgba('11344E')
BLUE = rgba('08A8F5')
ERROR = rgba('FF788A')


def accent(prefs):
    return tuple(prefs.custom_ui_accent) + (1,)


def surface(color, prefs):
    return tuple(min(1, c * prefs.custom_ui_brightness) for c in color[:3]) + (color[3],)
