"""Number-key section toggles, with a short modal wait for 10–13."""

import time

import bpy
from bpy.app.handlers import persistent

from ..localization import get_preferences


DIGIT_KEYS = dict(zip(
    ("ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE"),
    range(10),
))
PENDING = []


@persistent
def cancel_pending_sections(*_args):
    for operator in list(PENDING):
        operator.cleanup()


def section_context_allowed(context):
    preferences = get_preferences(context)
    if not preferences or not preferences.enable_section_number_hotkeys:
        return False
    if not context.area or context.area.type != "VIEW_3D" or not context.region:
        return False
    if preferences.section_hotkey_scope == "SIDEBAR":
        return (context.region.type == "UI"
                and context.region.active_panel_category == "AI Retopo")
    return context.region.type in {"WINDOW", "UI"}


def toggle_section(context, number):
    from ..properties import SECTION_VISIBILITY_PROPERTIES

    if not 1 <= number <= len(SECTION_VISIBILITY_PROPERTIES):
        return
    settings = context.scene.airetopo_panel_visibility_settings
    name = SECTION_VISIBILITY_PROPERTIES[number - 1]
    setattr(settings, name, not getattr(settings, name))
    # Only redraw section contents. Reassigning sidebar visibility/category
    # triggers Blender's region updates and can make the entire panel flicker.
    context.area.tag_redraw()


class AIRETOPO_OT_section_number(bpy.types.Operator):
    bl_idname = "wm.airetopo_section_number"
    bl_label = "Toggle AI Retopo Section"
    bl_description = "Toggle sections with 1–9, 0 for 10, or quickly type 10–13"
    bl_options = {"INTERNAL"}

    digit: bpy.props.IntProperty(default=1, min=0, max=9, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return section_context_allowed(context)

    def invoke(self, context, event):
        if getattr(event, "is_repeat", False):
            return {"CANCELLED"}
        if self.digit != 1:
            toggle_section(context, self.digit or 10)
            return {"FINISHED"}
        cancel_pending_sections()
        self._area = context.area
        self._scene = context.scene
        self._window = context.window
        self._wm = context.window_manager
        self._done = False
        self._released = False
        self._deadline = time.monotonic() + get_preferences(context).section_digit_interval
        self._timer = self._wm.event_timer_add(0.03, window=self._window)
        PENDING.append(self)
        self._wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def cleanup(self):
        if getattr(self, "_timer", None) is not None:
            self._wm.event_timer_remove(self._timer)
            self._timer = None
        self._done = True
        if self in PENDING:
            PENDING.remove(self)

    def cancel(self, context):
        self.cleanup()

    def modal(self, context, event):
        if self._done:
            return {"CANCELLED"}
        if (context.area != self._area or context.scene != self._scene
                or context.window != self._window or not section_context_allowed(context)):
            self.cleanup()
            return {"CANCELLED", "PASS_THROUGH"}
        if event.type in {"ESC", "WINDOW_DEACTIVATE"}:
            self.cleanup()
            return {"CANCELLED"}
        if event.type == "ONE" and event.value == "RELEASE":
            self._released = True
            return {"RUNNING_MODAL"}
        if event.type in DIGIT_KEYS and getattr(event, "is_repeat", False):
            return {"RUNNING_MODAL"}
        if event.type == "TIMER":
            if time.monotonic() >= self._deadline:
                toggle_section(context, 1)
                self.cleanup()
                return {"FINISHED"}
            return {"PASS_THROUGH"}
        if event.value == "PRESS" and event.type in DIGIT_KEYS:
            if event.ctrl or event.shift or event.alt or event.oskey:
                self.cleanup()
                return {"CANCELLED", "PASS_THROUGH"}
            if event.type == "ONE" and not self._released:
                return {"RUNNING_MODAL"}
            digit = DIGIT_KEYS[event.type]
            if time.monotonic() < self._deadline and digit <= 3:
                toggle_section(context, 10 + digit)
            else:
                toggle_section(context, 1)
                toggle_section(context, digit or 10)
            self.cleanup()
            return {"FINISHED"}
        if event.value == "PRESS":
            # Don't retain a modal listener while the user starts editing a
            # field, running a transform, or invoking another command.
            self.cleanup()
            return {"CANCELLED", "PASS_THROUGH"}
        return {"PASS_THROUGH"}
