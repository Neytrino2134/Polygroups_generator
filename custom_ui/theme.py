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
    # COLOR RNA stores scene-linear RGB; POST_PIXEL shaders expect display RGB.
    return tuple(12.92*c if c <= .0031308 else 1.055*c**(1/2.4)-.055
                 for c in prefs.custom_ui_accent) + (1,)


def heading(prefs):
    return tuple(prefs.custom_ui_heading_color) + (1,)


def button(prefs):
    return tuple(prefs.custom_ui_button_color) + (1,)


def text_color(prefs, muted=False):
    return tuple(c * (.7 if muted else 1) for c in prefs.custom_ui_text_color) + (1,)


def surface(color, prefs):
    if color == BACKGROUND:
        color = tuple(prefs.custom_ui_bg) + (color[3],)
    elif color in (SURFACE, RAISED):
        color = tuple(prefs.custom_ui_secondary_bg) + (color[3],)
    elif color == BORDER:
        color = tuple(prefs.custom_ui_accent_bg) + (color[3],)
    return tuple(min(1, c * prefs.custom_ui_brightness) for c in color[:3]) + (color[3],)
